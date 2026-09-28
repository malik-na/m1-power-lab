#!/usr/bin/env python3
"""Bounded, read-only EP0 diagnostic for one reviewed USB bus-port.

This reads only standard USB device and configuration-string descriptors. It neither
configures nor claims an interface. The native USB label is not target identity.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable


PORT = re.compile(r"[1-9][0-9]*-[1-9][0-9]*(?:\.[1-9][0-9]*)*\Z")
NATIVE = ("1d6b", "0104")
PROXY = ("1209", "316d")
DIAG_PREFIX = "M1Lab diag:v1:"
STAGES = frozenset(("acm_bind", "tty_wait", "launch_wait", "launch_received",
                    "capture", "capture_done"))
STATES = frozenset(("not_attached", "attached", "powered", "reconnecting",
                    "unauthenticated", "default", "address", "configured",
                    "suspended", "unknown"))
ERROR_TYPES = frozenset(("TimeoutError", "ValueError", "OSError", "ImportError",
                         "RuntimeError", "AssertionError", "TypeError", "Exception"))
PRODUCT = "M1Lab native candidate"
SERIAL = "m1lab-native-candidate"
CONFIG_STRING_INDEX = 4
MAX_OUTPUT = 256 * 1024
MAX_SECONDS = 480
CONTROL_TIMEOUT_MS = 250


class UsbControl(ctypes.Structure):
    _fields_ = [
        ("request_type", ctypes.c_uint8), ("request", ctypes.c_uint8),
        ("value", ctypes.c_uint16), ("index", ctypes.c_uint16),
        ("length", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
        ("data", ctypes.c_void_p),
    ]


# Linux USBDEVFS_CONTROL = _IOWR('U', 0, struct usbdevfs_ctrltransfer).
# The transfer fields and request below are fixed; no arbitrary control input.
USBDEVFS_CONTROL = 0xC0000000 | (ctypes.sizeof(UsbControl) << 16) | (ord("U") << 8)
assert ctypes.sizeof(UsbControl) == 24
_libc = ctypes.CDLL(None, use_errno=True)


class ProbeFailure(ValueError):
    """Stable, non-payload diagnostic for one fixed probe phase."""

    def __init__(self, stage: str, code: str, errno_value: int | None = None) -> None:
        super().__init__(f"{stage}:{code}")
        self.stage = stage
        self.code = code
        self.errno_value = errno_value


def get_descriptor(fd: int, descriptor_type: int, index: int, length: int) -> bytes:
    if (descriptor_type, index, length) not in (
        (1, 0, 18), (2, 0, 9), (3, 0, 4), (3, 2, 254),
        (3, 3, 254), (3, CONFIG_STRING_INDEX, 254),
    ):
        raise ValueError("descriptor request outside fixed diagnostic allowlist")
    buffer = (ctypes.c_ubyte * length)()
    control = UsbControl(0x80, 6, (descriptor_type << 8) | index,
                         0 if index == 0 else 0x0409, length,
                         CONTROL_TIMEOUT_MS, ctypes.addressof(buffer))
    result = _libc.ioctl(fd, USBDEVFS_CONTROL, ctypes.byref(control))
    if result < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return bytes(buffer[:result])


def decode_string(raw: bytes) -> str:
    if len(raw) < 2 or raw[1] != 3 or raw[0] != len(raw) or len(raw) % 2:
        raise ValueError("malformed USB string descriptor")
    value = raw[2:].decode("utf-16-le", errors="strict")
    return value


def validate_diagnostic(value: str) -> str:
    if not value.startswith(DIAG_PREFIX) or len(value) > 126:
        raise ValueError("configuration string outside diagnostic grammar")
    parts = value[len(DIAG_PREFIX):].split(":")
    if len(parts) == 2 and parts[0] in STAGES and parts[1] in STATES:
        return value
    if (len(parts) == 4 and parts[0] == "fail" and parts[1] in STAGES
            and parts[2] in ERROR_TYPES and parts[3] in STATES):
        return value
    raise ValueError("configuration string outside diagnostic grammar")


def _number(path: Path, limit: int) -> int:
    raw = path.read_text(encoding="ascii").strip()
    if not raw.isdecimal() or not 1 <= int(raw) <= limit:
        raise ValueError(f"invalid {path.name}")
    return int(raw)


def identity(port: str, sysfs_root: Path) -> tuple[str, str, int, int] | None:
    """Read exact-port sysfs identity; None means this port is disconnected."""
    base = sysfs_root / port
    if not base.exists():
        return None
    vendor = (base / "idVendor").read_text(encoding="ascii").strip().lower()
    product = (base / "idProduct").read_text(encoding="ascii").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(r"[0-9a-f]{4}", product):
        raise ValueError("invalid USB VID:PID at selected port")
    return vendor, product, _number(base / "busnum", 999), _number(base / "devnum", 127)


def probe_native(
    port: str, sysfs_root: Path, device_root: Path,
    transfer: Callable[[int, int, int, int], bytes] = get_descriptor,
) -> dict[str, object]:
    def request(stage: str, kind: int, index: int, length: int) -> bytes:
        try:
            return transfer(fd, kind, index, length)
        except (OSError, ValueError) as exc:
            raise ProbeFailure(stage, "control_request_failed",
                               exc.errno if isinstance(exc, OSError) else None) from exc

    def require(condition: bool, stage: str, code: str) -> None:
        if not condition:
            raise ProbeFailure(stage, code)

    def decoded(stage: str, raw: bytes) -> str:
        try:
            return decode_string(raw)
        except (ValueError, UnicodeError) as exc:
            raise ProbeFailure(stage, "string_invalid") from exc

    before = identity(port, sysfs_root)
    require(before is not None and before[:2] == NATIVE, "validation", "native_absent")
    assert before is not None
    _, _, bus, dev = before
    node = device_root / f"{bus:03d}" / f"{dev:03d}"
    fd = os.open(node, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 189 or (
            os.minor(info.st_rdev) != (bus - 1) * 128 + dev - 1
        ):
            raise ProbeFailure("validation", "usbfs_node_mismatch")
        require(identity(port, sysfs_root) == before, "validation", "identity_changed_before")
        device = request("device", 1, 0, 18)
        require(len(device) == 18 and device[0:2] == b"\x12\x01"
                and device[8:12] == b"\x6b\x1d\x04\x01", "device", "descriptor_mismatch")
        require(device[14:17] == bytes((1, 2, 3)), "device", "string_indices_changed")
        configuration = request("configuration", 2, 0, 9)
        require(len(configuration) == 9 and configuration[0:2] == b"\x09\x02"
                and configuration[5] == 1, "configuration", "descriptor_mismatch")
        require(configuration[6] == CONFIG_STRING_INDEX,
                "configuration", "diagnostic_index_missing")
        language = request("language", 3, 0, 4)
        require(language == b"\x04\x03\x09\x04", "language", "language_mismatch")
        product = request("product", 3, 2, 254)
        serial = request("serial", 3, 3, 254)
        diagnostic = request("diagnostic", 3, CONFIG_STRING_INDEX, 254)
        require(identity(port, sysfs_root) == before, "validation", "identity_changed_after")
        require(decoded("product", product) == PRODUCT, "product", "label_mismatch")
        require(decoded("serial", serial) == SERIAL, "serial", "label_mismatch")
        try:
            diagnostic_text = validate_diagnostic(decoded("diagnostic", diagnostic))
        except ValueError as exc:
            if isinstance(exc, ProbeFailure):
                raise
            raise ProbeFailure("diagnostic", "grammar_invalid") from exc
        return {
            "bus": bus, "device": dev, "device_descriptor_hex": device.hex(),
            "configuration_descriptor_hex": configuration.hex(),
            "language_descriptor_hex": language.hex(), "product_descriptor_hex": product.hex(),
            "serial_descriptor_hex": serial.hex(), "diagnostic_descriptor_hex": diagnostic.hex(),
            "product": PRODUCT, "diagnostic": diagnostic_text,
        }
    finally:
        os.close(fd)


def _append(fd: int, item: dict[str, object], used: int) -> int:
    line = (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if used + len(line) > MAX_OUTPUT:
        raise ValueError("diagnostic output bound reached")
    view = memoryview(line)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("diagnostic output write failed")
        view = view[count:]
    return used + len(line)


def watch(
    port: str, output: Path, seconds: int, *,
    sysfs_root: Path = Path("/sys/bus/usb/devices"),
    device_root: Path = Path("/dev/bus/usb"),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    probe: Callable[[str, Path, Path], dict[str, object]] = probe_native,
) -> str:
    if not PORT.fullmatch(port) or not 1 <= seconds <= MAX_SECONDS:
        raise ValueError("select one concrete bus-port and 1..480 seconds")
    output = output.absolute()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        deadline = monotonic() + seconds
        used = _append(fd, {"schema": "m1lab.native-usb-diagnostic.v1", "kind": "header",
                            "port": port, "max_seconds": seconds,
                            "identity_proven": False, "native_capture_proven": False}, 0)
        print(json.dumps({"ready": True, "schema": "m1lab.native-usb-diagnostic.v1",
                          "port": port, "max_seconds": seconds, "output": str(output)}), flush=True)
        seen_native = False
        previous: tuple[object, ...] | None = None
        result = "deadline"
        while monotonic() < deadline:
            stamp = {"utc": datetime.now(timezone.utc).isoformat(), "monotonic": monotonic()}
            try:
                selected = identity(port, sysfs_root)
                if selected is not None and selected[:2] == NATIVE:
                    seen_native = True
                    if deadline - monotonic() < 2.0:
                        observation: dict[str, object] = {"kind": "native_probe_skipped_deadline"}
                    else:
                        observation = {"kind": "native", **probe(port, sysfs_root, device_root)}
                elif selected is not None and selected[:2] == PROXY:
                    observation = {"kind": "proxy_at_port", "bus": selected[2], "device": selected[3]}
                    if seen_native:
                        result = "proxy_at_port_after_native"
                elif selected is None:
                    observation = {"kind": "disconnected"}
                else:
                    observation = {"kind": "unexpected_device", "vid": selected[0], "pid": selected[1]}
            except ProbeFailure as exc:
                observation = {"kind": "probe_error", "stage": exc.stage,
                               "error_code": exc.code, "errno": exc.errno_value}
            except (OSError, ValueError, UnicodeError) as exc:
                observation = {"kind": "probe_error", "stage": "validation",
                               "error_code": "sysfs_or_node_unavailable",
                               "errno": exc.errno if isinstance(exc, OSError) else None}
            key = tuple(sorted((name, str(value)) for name, value in observation.items()))
            if key != previous or result != "deadline":
                used = _append(fd, {"schema": "m1lab.native-usb-diagnostic.v1", "port": port,
                                    **stamp, **observation}, used)
                previous = key
            if result != "deadline":
                break
            if deadline - monotonic() < 2.0:
                break
            sleep(min(1.0, max(0.0, deadline - monotonic())))
        return result
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb-topology", required=True, help="exact host bus-port, e.g. 1-2")
    parser.add_argument("--output", required=True, type=Path, help="new private JSONL path")
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    try:
        outcome = watch(args.usb_topology, args.output, args.seconds)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"native USB diagnostic: {exc}\n")
    print(json.dumps({"outcome": outcome, "output": str(args.output.absolute()),
                      "identity_proven": False, "native_capture_proven": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
