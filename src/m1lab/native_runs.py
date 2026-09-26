"""Prepare native launch evidence and preserve bounded result streams.

This module opens no device and dispatches no target operation. A prepared
launch is an immutable artifact; file import and caller-owned descriptor input
preserve raw streams and record protocol results separately from physical
qualification. Neither acquisition path dispatches target work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

from m1lab.adapters import (
    MAX_NATIVE_FRAME_BYTES,
    MAX_NATIVE_MANIFEST_BYTES,
    MAX_NATIVE_OUTPUT_BYTES,
    NativeCapture,
    NativeHarnessError,
    NativeImageManifest,
    NativeLaunchManifest,
    NativeResultAssembler,
    decode_native_image_manifest,
    decode_native_launch_manifest,
    encode_native_manifest,
)
from m1lab.core import ArtifactRecord, CoreApp
from m1lab.core.models import new_id, utc_now
from m1lab.adapters.native_stream import MAX_NATIVE_STREAM_BYTES, receive_native_result_stream


IMAGE_MANIFEST_MEDIA_TYPE = "application/vnd.m1lab.native-image-manifest+json"
LAUNCH_MANIFEST_MEDIA_TYPE = "application/vnd.m1lab.native-launch-manifest+json"
CAPTURE_STREAM_MEDIA_TYPE = "application/octet-stream"
CAPTURE_MEDIA_TYPE = "application/vnd.m1lab.native-capture+json;version=1"
MAX_CAPTURE_STREAM_BYTES = MAX_NATIVE_STREAM_BYTES
MAX_CAPTURE_SAMPLES = 4094
MAX_SAMPLE_PERIOD_MS = 60_000
MIN_LAUNCH_HEADROOM_MS = 1000
MAX_PROPERTY_BYTES = 256
SUPPLY_PROPERTIES = frozenset(
    {
        "type", "present", "online", "status", "health", "technology",
        "capacity", "capacity_level", "voltage_now", "current_now", "power_now",
        "energy_now", "energy_full", "energy_full_design", "charge_now",
        "charge_full", "charge_full_design", "temp", "temp_ambient",
    }
)
THERMAL_PROPERTIES = frozenset({"type", "temp", "mode", "policy"})


def prepare_native_launch(
    core: CoreApp,
    session_id: str,
    *,
    image_manifest_artifact_id: str,
    image_artifact_id: str,
    target_identity: str,
    boot_epoch: str,
    sample_count: int,
    sample_period_ms: int,
    deadline_seconds: int,
    output_limit_bytes: int,
    recovery_expectation: str,
) -> tuple[NativeLaunchManifest, ArtifactRecord]:
    """Validate an owner-specified launch against published image evidence."""

    from m1lab.investigator.prompts import scrub_text

    for value in (target_identity, boot_epoch, recovery_expectation):
        if not isinstance(value, str) or scrub_text(value) != value:
            raise NativeHarnessError("launch identity or recovery text contains sensitive data")
    artifacts = {item.id: item for item in core.artifacts(session_id)}
    session = core.session(session_id)
    if session.target_identity is None or session.target_identity != target_identity:
        raise NativeHarnessError("launch target identity must match the selected session")
    manifest_artifact = artifacts.get(image_manifest_artifact_id)
    if manifest_artifact is None or not manifest_artifact.available:
        raise NativeHarnessError("image manifest is unavailable in the selected session")
    if manifest_artifact.media_type != IMAGE_MANIFEST_MEDIA_TYPE:
        raise NativeHarnessError("selected artifact is not a native image manifest")
    image_artifact = artifacts.get(image_artifact_id)
    if image_artifact is None or not image_artifact.available:
        raise NativeHarnessError("selected image artifact is unavailable in the selected session")
    if image_artifact.provenance.get("role") != "payload":
        raise NativeHarnessError("native launch must bind the declared payload artifact")
    manifest_bytes = core.read_session_artifact(
        session_id, manifest_artifact.id, max_bytes=MAX_NATIVE_MANIFEST_BYTES
    )
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_artifact.sha256:
        raise NativeHarnessError("published image manifest digest does not match its bytes")
    image = decode_native_image_manifest(manifest_bytes)
    if not any(
        item.role == "payload" and item.sha256 == image_artifact.sha256
        for item in image.outputs
    ):
        raise NativeHarnessError("selected payload is not declared by the image manifest")
    if type(deadline_seconds) is not int or not 1 <= deadline_seconds <= 3600:
        raise NativeHarnessError("native launch deadline must be 1..3600 seconds")
    parameters = {"sample_count": sample_count, "sample_period_ms": sample_period_ms}
    _collector_parameters(parameters)
    if sample_count * sample_period_ms > deadline_seconds * 1000 - MIN_LAUNCH_HEADROOM_MS:
        raise NativeHarnessError("native collector samples require at least one second of launch headroom")
    if (
        type(output_limit_bytes) is not int
        or not 4096 <= output_limit_bytes <= min(MAX_NATIVE_OUTPUT_BYTES, image.maximum_output_bytes)
    ):
        raise NativeHarnessError("native launch output limit exceeds the image or protocol bound")
    launch = NativeLaunchManifest(
        run_id=new_id("native_run"),
        image_manifest_sha256=manifest_artifact.sha256,
        image_sha256=image_artifact.sha256,
        target_identity=target_identity,
        boot_epoch=boot_epoch,
        configuration_sha256=image.configuration_sha256,
        parameters=parameters,
        deadline=utc_now() + timedelta(seconds=deadline_seconds),
        output_limit_bytes=output_limit_bytes,
        recovery_expectation=recovery_expectation,
    )
    launch.validate_against_image(image)
    launch_artifact = core.publish_artifact(
        encode_native_manifest(launch),
        media_type=LAUNCH_MANIFEST_MEDIA_TYPE,
        provenance={
            "session_id": session_id,
            "record_type": "native_launch_manifest",
            "run_id": launch.run_id,
            "image_manifest_artifact_id": manifest_artifact.id,
            "image_artifact_id": image_artifact.id,
            "physical_dispatch_performed": False,
        },
    )
    return launch, launch_artifact


def import_native_capture(
    core: CoreApp,
    session_id: str,
    *,
    launch_artifact_id: str,
    image_manifest_artifact_id: str,
    stream_path: Path,
) -> tuple[NativeCapture, ArtifactRecord, ArtifactRecord]:
    """Preserve and parse a bounded result stream without asserting its origin."""

    launch, image = _capture_manifests(
        core, session_id, launch_artifact_id, image_manifest_artifact_id,
        require_current_deadline=False,
    )
    raw_stream = _read_stream_file(stream_path)
    capture = _parse_saved_capture(raw_stream, launch, image)
    return _publish_capture(
        core, session_id, launch_artifact_id, image_manifest_artifact_id,
        launch, raw_stream, capture,
        acquisition={"mode": "file", "terminal_received_before_deadline": False,
                     "target_stop_verified": False},
    )


def receive_native_capture(
    core: CoreApp,
    session_id: str,
    *,
    launch_artifact_id: str,
    image_manifest_artifact_id: str,
    fd: int,
) -> tuple[NativeCapture, ArtifactRecord, ArtifactRecord]:
    """Preserve bounded descriptor input; no dispatch or physical qualification.

    The owner of the channel supplies an exclusively owned nonblocking fd.
    This function does not open, configure, or close the channel. In particular,
    a host timeout neither stops target execution nor authorizes a retry.
    """

    launch, image = _capture_manifests(
        core, session_id, launch_artifact_id, image_manifest_artifact_id,
        require_current_deadline=True,
    )
    receipt = receive_native_result_stream(fd, launch, image)
    return _publish_capture(
        core, session_id, launch_artifact_id, image_manifest_artifact_id,
        launch, receipt.raw_stream, receipt.capture,
        acquisition={"mode": "descriptor", "stop_reason": receipt.stop_reason,
                     "terminal_received_before_deadline": receipt.terminal_received_before_deadline,
                     "target_stop_verified": False},
    )


def _capture_manifests(
    core: CoreApp,
    session_id: str,
    launch_artifact_id: str,
    image_manifest_artifact_id: str,
    *,
    require_current_deadline: bool,
) -> tuple[NativeLaunchManifest, NativeImageManifest]:
    artifacts = {item.id: item for item in core.artifacts(session_id)}
    launch_artifact = artifacts.get(launch_artifact_id)
    if (
        launch_artifact is None
        or not launch_artifact.available
        or launch_artifact.media_type != LAUNCH_MANIFEST_MEDIA_TYPE
    ):
        raise NativeHarnessError("launch manifest is unavailable or has the wrong media type")
    image_artifact = artifacts.get(image_manifest_artifact_id)
    if (
        image_artifact is None
        or not image_artifact.available
        or image_artifact.media_type != IMAGE_MANIFEST_MEDIA_TYPE
    ):
        raise NativeHarnessError("image manifest is unavailable or has the wrong media type")
    launch_bytes = core.read_session_artifact(
        session_id, launch_artifact.id, max_bytes=MAX_NATIVE_MANIFEST_BYTES
    )
    image_bytes = core.read_session_artifact(
        session_id, image_artifact.id, max_bytes=MAX_NATIVE_MANIFEST_BYTES
    )
    if hashlib.sha256(launch_bytes).hexdigest() != launch_artifact.sha256:
        raise NativeHarnessError("published launch manifest digest does not match its bytes")
    if hashlib.sha256(image_bytes).hexdigest() != image_artifact.sha256:
        raise NativeHarnessError("published image manifest digest does not match its bytes")
    launch = decode_native_launch_manifest(
        launch_bytes, require_current_deadline=require_current_deadline
    )
    _collector_parameters(launch.parameters)
    image = decode_native_image_manifest(image_bytes)
    if launch_artifact.provenance.get("image_manifest_artifact_id") != image_artifact.id:
        raise NativeHarnessError("launch artifact references a different image manifest")
    selected_image_id = launch_artifact.provenance.get("image_artifact_id")
    selected_image = artifacts.get(selected_image_id) if isinstance(selected_image_id, str) else None
    if selected_image is None or not selected_image.available:
        raise NativeHarnessError("launch image artifact is unavailable in the selected session")
    if selected_image.provenance.get("role") != "payload":
        raise NativeHarnessError("launch artifact does not identify a payload output")
    if selected_image.sha256 != launch.image_sha256 or not any(
        output.role == "payload" and output.sha256 == selected_image.sha256
        for output in image.outputs
    ):
        raise NativeHarnessError("launch image digest does not match its published image output")
    launch.validate_against_image(image, require_current_deadline=require_current_deadline)
    return launch, image


def _parse_saved_capture(
    raw_stream: bytes, launch: NativeLaunchManifest, image: NativeImageManifest
) -> NativeCapture:
    # This command imports a completed file after acquisition. It validates
    # frame integrity and launch binding, but cannot attest when or where the
    # file was captured. The live adapter must use the default deadline check.
    assembler = NativeResultAssembler(launch, image, enforce_receive_deadline=False)
    offset = 0
    message = ""
    while offset < len(raw_stream):
        if len(raw_stream) - offset < 4:
            message = "result stream ended inside a frame length prefix"
            break
        frame_size = struct.unpack_from(">I", raw_stream, offset)[0]
        if not 1 <= frame_size <= MAX_NATIVE_FRAME_BYTES:
            message = "result stream contains an invalid frame length"
            break
        end = offset + 4 + frame_size
        if end > len(raw_stream):
            message = "result stream ended inside a frame"
            break
        try:
            assembler.accept(raw_stream[offset:end])
        except NativeHarnessError as exc:
            message = str(exc)[:1024]
            offset = end
            break
        offset = end
    capture = assembler.capture(message)
    if message and capture.status != "unknown":
        capture = NativeCapture(
            status="unknown",
            identity_verified=capture.identity_verified,
            launch_binding_verified=capture.launch_binding_verified,
            payload=capture.payload,
            frame_count=capture.frame_count,
            message=message,
        )
    return capture


def _publish_capture(
    core: CoreApp,
    session_id: str,
    launch_artifact_id: str,
    image_manifest_artifact_id: str,
    launch: NativeLaunchManifest,
    raw_stream: bytes,
    capture: NativeCapture,
    *,
    acquisition: dict[str, object],
) -> tuple[NativeCapture, ArtifactRecord, ArtifactRecord]:
    expected_sample_count, _ = _collector_parameters(launch.parameters)
    raw_artifact = core.publish_artifact(
        raw_stream,
        media_type=CAPTURE_STREAM_MEDIA_TYPE,
        provenance={
            "session_id": session_id,
            "record_type": "native_result_stream",
            "launch_artifact_id": launch_artifact_id,
            "image_manifest_artifact_id": image_manifest_artifact_id,
            "protocol_status": capture.status,
            "identity_verified": False,
            "launch_binding_verified": capture.launch_binding_verified,
            "physical_source_verified": False,
            "capture_timing_verified": False,
            "stream_acquisition": acquisition,
        },
    )
    from m1lab.investigator.prompts import scrub_text

    screened_payload, screening = _screen_capture_payload(
        capture.payload,
        expected_sample_count=expected_sample_count,
        protocol_status=capture.status,
    )
    accepted_status = capture.status
    if screening.startswith("omitted_"):
        accepted_status = "unknown"
    safe_capture = NativeCapture(
        status=accepted_status,
        identity_verified=False,
        launch_binding_verified=capture.launch_binding_verified,
        payload=screened_payload,
        frame_count=capture.frame_count,
        message=scrub_text(capture.message or (
            "collector payload did not match the recognized schema or requested sample count"
            if accepted_status == "unknown" and capture.status != "unknown" else ""
        ))[:1024],
    )
    capture_document = safe_capture.model_dump(mode="json")
    capture_document["protocol_status"] = capture.status
    capture_document["physical_source_verified"] = False
    capture_document["capture_timing_verified"] = False
    capture_document["stream_acquisition"] = acquisition
    capture_document["payload_screening"] = screening
    capture_document["raw_stream_artifact_id"] = raw_artifact.id
    normalized_artifact = core.publish_artifact(
        json.dumps(
            capture_document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8"),
        media_type=CAPTURE_MEDIA_TYPE,
        provenance={
            "session_id": session_id,
            "record_type": "native_capture",
            "launch_artifact_id": launch_artifact_id,
            "image_manifest_artifact_id": image_manifest_artifact_id,
            "raw_stream_artifact_id": raw_artifact.id,
            "capture_status": safe_capture.status,
            "protocol_status": capture.status,
            "identity_verified": False,
            "launch_binding_verified": capture.launch_binding_verified,
            "physical_source_verified": False,
            "capture_timing_verified": False,
            "payload_screening": screening,
            "stream_acquisition": acquisition,
        },
    )
    return safe_capture, raw_artifact, normalized_artifact


def _collector_parameters(parameters: dict[str, object]) -> tuple[int, int]:
    """Validate the fixed collector schema, including saved launch artifacts."""

    if set(parameters) != {"sample_count", "sample_period_ms"}:
        raise NativeHarnessError("native collector parameters must contain sample_count and sample_period_ms only")
    count, period = parameters["sample_count"], parameters["sample_period_ms"]
    if (
        type(count) is not int or not 1 <= count <= MAX_CAPTURE_SAMPLES
        or type(period) is not int or not 100 <= period <= MAX_SAMPLE_PERIOD_MS
        or count * period > 3_600_000
    ):
        raise NativeHarnessError("native collector sample parameters are outside their bounds")
    return count, period


def _screen_capture_payload(
    payload: bytes,
    *,
    expected_sample_count: int,
    protocol_status: str,
) -> tuple[bytes, str]:
    """Return only scrubbed records matching the launch's bounded sample count."""

    from m1lab.investigator.prompts import scrub_text

    if not payload:
        if protocol_status == "complete" and expected_sample_count > 0:
            return b"", "omitted_sample_count_mismatch"
        return b"", "empty"
    safe_lines: list[bytes] = []
    expected_index = 0
    previous_monotonic_ns = -1
    for line in payload.splitlines():
        if not line or len(line) > 1_048_576:
            return b"", "omitted_unknown_record_shape"
        try:
            record = json.loads(
                line.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, ValueError, RecursionError):
            return b"", "omitted_unknown_record_shape"
        if not _valid_raw_sample(record):
            return b"", "omitted_unknown_record_shape"
        if (
            record["sample_index"] != expected_index
            or record["monotonic_ns"] <= previous_monotonic_ns
        ):
            return b"", "omitted_invalid_sample_sequence"
        screened = scrub_text(line.decode("utf-8")).encode("utf-8")
        try:
            screened_record = json.loads(
                screened.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, ValueError, RecursionError):
            return b"", "omitted_screening_failure"
        if not _valid_raw_sample(screened_record):
            return b"", "omitted_screening_failure"
        safe_lines.append(
            json.dumps(
                screened_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        )
        expected_index += 1
        previous_monotonic_ns = record["monotonic_ns"]
    if expected_index > expected_sample_count or (
        protocol_status == "complete" and expected_index != expected_sample_count
    ):
        return b"", "omitted_sample_count_mismatch"
    output = b"\n".join(safe_lines) + b"\n"
    if len(output) > MAX_NATIVE_OUTPUT_BYTES:
        return b"", "omitted_screened_output_over_bound"
    return output, "screened_known_collector_records"


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("capture record contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"capture record contains invalid JSON constant {value}")


def _valid_raw_sample(record: object) -> bool:
    if not isinstance(record, dict) or set(record) != {
        "format", "sample_index", "observed_at_utc", "monotonic_ns", "sources", "interpretation"
    }:
        return False
    if (
        record["format"] != "m1lab.raw-sysfs-sample.v1"
        or type(record["sample_index"]) is not int
        or not 0 <= record["sample_index"] < MAX_CAPTURE_SAMPLES
        or type(record["monotonic_ns"]) is not int
        or record["monotonic_ns"] < 0
        or not isinstance(record["observed_at_utc"], str)
        or len(record["observed_at_utc"]) > 64
        or record["interpretation"]
        != "raw Linux sysfs values; units and whole-device measurement boundary are not inferred"
    ):
        return False
    try:
        observed_at = datetime.fromisoformat(record["observed_at_utc"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        return False
    sources = record["sources"]
    if not isinstance(sources, dict) or set(sources) != {
        "device_tree_model", "power_supplies", "thermal_zones"
    }:
        return False
    model = sources["device_tree_model"]
    if model is not None and (not isinstance(model, str) or len(model) > MAX_PROPERTY_BYTES):
        return False
    for key, properties, maximum in (
        ("power_supplies", SUPPLY_PROPERTIES, 32),
        ("thermal_zones", THERMAL_PROPERTIES, 128),
    ):
        entries = sources[key]
        if not isinstance(entries, list) or len(entries) > maximum:
            return False
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"name", "attributes"}
                or not isinstance(entry["name"], str)
                or len(entry["name"]) > 128
                or not isinstance(entry["attributes"], dict)
                or set(entry["attributes"]) - properties
            ):
                return False
            if any(
                not isinstance(value, str) or len(value.encode("utf-8")) > MAX_PROPERTY_BYTES
                for value in entry["attributes"].values()
            ):
                return False
    return True


def _read_stream_file(path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise NativeHarnessError("result stream path cannot be opened safely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size < 0 or info.st_size > MAX_CAPTURE_STREAM_BYTES:
            raise NativeHarnessError("result stream must be a bounded regular file")
        chunks: list[bytes] = []
        remaining = MAX_CAPTURE_STREAM_BYTES + 1
        while remaining:
            try:
                chunk = os.read(fd, min(1024 * 1024, remaining))
            except OSError as exc:
                raise NativeHarnessError("result stream could not be read") from exc
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_CAPTURE_STREAM_BYTES:
            raise NativeHarnessError("result stream exceeds its size bound")
        return content
    finally:
        os.close(fd)
