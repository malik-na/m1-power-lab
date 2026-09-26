#!/usr/bin/env python3
"""Bounded Linux target collector that emits m1lab.native-result.v1 frames.

This reads only allowlisted sysfs telemetry and writes framed records to the
caller-owned stdout descriptor. It does not modify target state, infer watts,
or claim that a reported Linux sensor measures whole-device power.
"""

from __future__ import annotations

import argparse
import base64
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import struct
import sys
import time
from datetime import datetime, timezone
from typing import Any


PROTOCOL = "m1lab.native-result.v1"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_FRAME_BYTES = 1_500_000
MAX_CHUNK_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 16 * 1_048_576
MAX_FRAMES = 4096
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPLY_PROPERTIES = (
    "type", "present", "online", "status", "health", "technology",
    "capacity", "capacity_level", "voltage_now", "current_now", "power_now",
    "energy_now", "energy_full", "energy_full_design", "charge_now",
    "charge_full", "charge_full_design", "temp", "temp_ambient",
)
THERMAL_PROPERTIES = ("type", "temp", "mode", "policy")
PROPERTY_BYTES = 256
MAX_SUPPLIES = 32
MAX_THERMAL_ZONES = 128


class CaptureError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CaptureError("launch manifest contains a duplicate key")
        value[key] = item
    return value


def _reject_json_constant(_value: str) -> None:
    raise CaptureError("launch manifest contains an invalid JSON number")


def _read_bounded_manifest(path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_MANIFEST_BYTES:
            raise CaptureError("launch manifest is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = MAX_MANIFEST_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise CaptureError("launch manifest exceeds its size bound")
        return raw
    finally:
        os.close(fd)


def load_launch(path: Path) -> dict[str, Any]:
    try:
        raw = _read_bounded_manifest(path)
        launch = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CaptureError("launch manifest cannot be read as JSON") from exc
    required = {
        "schema_version", "run_id", "image_manifest_sha256", "image_sha256",
        "target_identity", "boot_epoch", "configuration_sha256", "parameters",
        "deadline", "output_limit_bytes", "recovery_expectation",
    }
    if not isinstance(launch, dict) or set(launch) != required:
        raise CaptureError("launch manifest has missing or unknown fields")
    if launch["schema_version"] != "m1lab.native-launch.v1":
        raise CaptureError("unsupported launch manifest version")
    for field in ("image_manifest_sha256", "image_sha256", "configuration_sha256"):
        if not isinstance(launch[field], str) or not SHA256_RE.fullmatch(launch[field]):
            raise CaptureError("launch manifest contains an invalid digest")
    for field, limit in (("run_id", 128), ("target_identity", 160), ("boot_epoch", 128),
                         ("recovery_expectation", 512)):
        if not isinstance(launch[field], str) or not launch[field] or len(launch[field]) > limit:
            raise CaptureError("launch manifest contains an invalid identity field")
    if type(launch["output_limit_bytes"]) is not int or not 4096 <= launch["output_limit_bytes"] <= MAX_OUTPUT_BYTES:
        raise CaptureError("launch output limit is outside collector bounds")
    parameters = launch["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != {"sample_count", "sample_period_ms"}:
        raise CaptureError("collector parameters must contain sample_count and sample_period_ms only")
    sample_count = parameters["sample_count"]
    period_ms = parameters["sample_period_ms"]
    if type(sample_count) is not int or not 1 <= sample_count <= MAX_FRAMES - 2:
        raise CaptureError("sample_count is outside collector bounds")
    if type(period_ms) is not int or not 100 <= period_ms <= 60_000:
        raise CaptureError("sample_period_ms is outside collector bounds")
    if sample_count * period_ms > 3_600_000:
        raise CaptureError("requested capture exceeds one hour")
    deadline = launch["deadline"]
    if not isinstance(deadline, str):
        raise CaptureError("launch deadline must be a timestamp")
    try:
        parsed_deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureError("launch deadline is invalid") from exc
    if parsed_deadline.tzinfo is None:
        raise CaptureError("launch deadline has no timezone")
    deadline_seconds = (parsed_deadline - datetime.now(timezone.utc)).total_seconds()
    requested_seconds = sample_count * period_ms / 1000
    if not 0 < deadline_seconds <= 3600 or requested_seconds > deadline_seconds:
        raise CaptureError("launch deadline cannot contain the requested bounded capture")
    launch["_remaining_deadline_seconds"] = deadline_seconds
    launch["_deadline_observed_monotonic"] = time.monotonic()
    return launch


def _read_attribute(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            value = stream.read(PROPERTY_BYTES + 1)
        if len(value) > PROPERTY_BYTES:
            return "[truncated]"
        return value.decode("utf-8", errors="replace").strip("\x00\r\n ")
    except OSError:
        return None


def _directory_names(root: Path, pattern: str, maximum: int) -> list[Path]:
    try:
        return sorted((item for item in root.glob(pattern) if item.is_dir()), key=lambda item: item.name)[:maximum]
    except OSError:
        return []


def _sysfs_snapshot() -> dict[str, Any]:
    supplies: list[dict[str, Any]] = []
    for supply in _directory_names(Path("/sys/class/power_supply"), "*", MAX_SUPPLIES):
        values = {name: value for name in SUPPLY_PROPERTIES
                  if (value := _read_attribute(supply / name)) is not None}
        if values:
            supplies.append({"name": supply.name[:128], "attributes": values})
    zones: list[dict[str, Any]] = []
    for zone in _directory_names(Path("/sys/class/thermal"), "thermal_zone*", MAX_THERMAL_ZONES):
        values = {name: value for name in THERMAL_PROPERTIES
                  if (value := _read_attribute(zone / name)) is not None}
        if values:
            zones.append({"name": zone.name[:128], "attributes": values})
    model = _read_attribute(Path("/sys/firmware/devicetree/base/model"))
    return {"device_tree_model": model, "power_supplies": supplies, "thermal_zones": zones}


def _frame(
    launch: dict[str, Any], kind: str, sequence: int, *, payload: bytes = b"",
    terminal_status: str | None = None,
) -> bytes:
    document: dict[str, Any] = {
        "schema_version": PROTOCOL,
        "frame_kind": kind,
        "run_id": launch["run_id"],
        "image_sha256": launch["image_sha256"],
        "target_identity": launch["target_identity"],
        "boot_epoch": launch["boot_epoch"],
        "configuration_sha256": launch["configuration_sha256"],
        "sequence": sequence,
        "payload_base64": base64.b64encode(payload).decode("ascii") if payload else "",
        "payload_sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        "terminal_status": terminal_status,
        "frame_sha256": "0" * 64,
    }
    unsigned = {key: value for key, value in document.items() if key != "frame_sha256"}
    document["frame_sha256"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    encoded = canonical_json(document)
    if len(encoded) > MAX_FRAME_BYTES:
        raise CaptureError("encoded result frame exceeds its bound")
    return struct.pack(">I", len(encoded)) + encoded


def _write_all(fd: int, data: bytes, deadline: float) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("result channel deadline elapsed")
        _, writable, _ = select.select([], [fd], [], remaining)
        if not writable:
            raise TimeoutError("result channel did not become writable")
        try:
            written = os.write(fd, view[offset:])
        except InterruptedError:
            continue
        except BlockingIOError:
            continue
        if written <= 0:
            raise OSError(errno.EPIPE, "result channel closed")
        offset += written


def _emit(fd: int, launch: dict[str, Any]) -> tuple[int, int]:
    descriptor_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, descriptor_flags | os.O_NONBLOCK)
    count = launch["parameters"]["sample_count"]
    period = launch["parameters"]["sample_period_ms"] / 1000
    started = time.monotonic()
    elapsed = started - launch["_deadline_observed_monotonic"]
    remaining_to_launch_deadline = launch["_remaining_deadline_seconds"] - elapsed
    if remaining_to_launch_deadline <= 0:
        fcntl.fcntl(fd, fcntl.F_SETFL, descriptor_flags)
        raise CaptureError("launch deadline elapsed before capture started")
    hard_deadline = started + min(count * period, remaining_to_launch_deadline)
    # Leave room for the final sample's scheduled slot as the count grows.
    terminal_reserve = min(0.25, period * 0.1)
    data_deadline = hard_deadline - terminal_reserve
    sequence = 0
    total_payload = 0
    frames = 0
    try:
        _write_all(fd, _frame(launch, "identity", sequence), data_deadline)
        sequence += 1
        frames += 1
        for sample_index in range(count):
            scheduled = started + sample_index * period
            remaining = scheduled - time.monotonic()
            if remaining > 0:
                time.sleep(min(remaining, max(0.0, data_deadline - time.monotonic())))
            if time.monotonic() >= data_deadline:
                _write_all(fd, _frame(launch, "end", sequence, terminal_status="partial"), hard_deadline)
                frames += 1
                return frames, total_payload
            record = {
                "format": "m1lab.raw-sysfs-sample.v1",
                "sample_index": sample_index,
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_ns": time.monotonic_ns(),
                "sources": _sysfs_snapshot(),
                "interpretation": "raw Linux sysfs values; units and whole-device measurement boundary are not inferred",
            }
            chunk = canonical_json(record) + b"\n"
            if time.monotonic() >= data_deadline:
                _write_all(fd, _frame(launch, "end", sequence, terminal_status="partial"), hard_deadline)
                frames += 1
                return frames, total_payload
            if len(chunk) > MAX_CHUNK_BYTES or total_payload + len(chunk) > launch["output_limit_bytes"]:
                _write_all(fd, _frame(launch, "end", sequence, terminal_status="partial"), hard_deadline)
                frames += 1
                return frames, total_payload
            if sequence > MAX_FRAMES - 2:
                _write_all(fd, _frame(launch, "end", sequence, terminal_status="partial"), hard_deadline)
                frames += 1
                return frames, total_payload
            _write_all(fd, _frame(launch, "data", sequence, payload=chunk), data_deadline)
            sequence += 1
            frames += 1
            total_payload += len(chunk)
        _write_all(fd, _frame(launch, "end", sequence, terminal_status="complete"), hard_deadline)
        frames += 1
        return frames, total_payload
    finally:
        fcntl.fcntl(fd, fcntl.F_SETFL, descriptor_flags)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        launch = load_launch(args.launch_manifest)
        frames, payload_bytes = _emit(sys.stdout.fileno(), launch)
        print(f"capture frames={frames} payload_bytes={payload_bytes}", file=sys.stderr)
        return 0
    except (CaptureError, OSError, TimeoutError, ValueError, TypeError, RecursionError) as exc:
        # Avoid printing host paths or raw exception contents into captured evidence.
        print(f"native capture stopped ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
