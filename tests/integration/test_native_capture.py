"""Host-only native collector bytes through a real subprocess and CoreApp store."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

import pytest

from m1lab.adapters.native_harness import (
    ManifestArtifact, NativeHarnessError, NativeImageManifest,
    NativeResultAssembler, decode_native_launch_manifest,
    decode_native_result_frame, encode_native_manifest, encode_native_result_frame,
    make_native_result_frame,
)
from m1lab.core.models import SessionCreate
from m1lab.native_runs import (
    IMAGE_MANIFEST_MEDIA_TYPE, LAUNCH_MANIFEST_MEDIA_TYPE,
    import_native_capture, prepare_native_launch,
)


_COLLECTOR = Path(__file__).resolve().parents[2] / "target" / "native_capture.py"
_CHILD = """
import importlib.util
import sys
from pathlib import Path

script, launch = sys.argv[1:]
spec = importlib.util.spec_from_file_location("synthetic_native_capture", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._sysfs_snapshot = lambda: {
    "device_tree_model": "synthetic-host-fixture",
    "power_supplies": [{"name": "synthetic-battery", "attributes": {"capacity": "73"}}],
    "thermal_zones": [],
}
sys.argv = [script, "--launch-manifest", launch]
raise SystemExit(module.main())
"""


def _frames(stream: bytes) -> list[bytes]:
    frames = []
    offset = 0
    while offset < len(stream):
        length = struct.unpack_from(">I", stream, offset)[0]
        end = offset + 4 + length
        frames.append(stream[offset:end])
        offset = end
    return frames


def _capture(core, tmp_path, *, sample_count=2, deadline_seconds=5, output_limit_bytes=4096):
    session = core.create_session(SessionCreate(
        objective="Synthetic native collector integration", owner="test-owner",
        host_identity="synthetic-host", target_identity="synthetic-target",
    ))
    payload = b"synthetic-image-payload"
    image_artifact = core.publish_artifact(
        payload, media_type="application/octet-stream",
        provenance={"session_id": session.id, "role": "payload", "source": "synthetic-test"},
    )
    image = NativeImageManifest(
        architecture="host-test-only", source_commit="a" * 40,
        source_tree_clean=True, toolchain="synthetic-test", toolchain_version="1",
        configuration_sha256="c" * 64,
        outputs=(ManifestArtifact(
            name="payload.bin", role="payload", sha256=image_artifact.sha256,
            size_bytes=len(payload),
        ),),
        collector_sha256="d" * 64, maximum_runtime_seconds=30,
        maximum_output_bytes=65_536, return_behavior="synthetic host return",
    )
    manifest_artifact = core.publish_artifact(
        encode_native_manifest(image), media_type=IMAGE_MANIFEST_MEDIA_TYPE,
        provenance={"session_id": session.id, "record_type": "native_image_manifest"},
    )
    launch, launch_artifact = prepare_native_launch(
        core, session.id,
        image_manifest_artifact_id=manifest_artifact.id,
        image_artifact_id=image_artifact.id,
        target_identity="synthetic-target", boot_epoch="synthetic-boot",
        sample_count=sample_count, sample_period_ms=100, deadline_seconds=deadline_seconds,
        output_limit_bytes=output_limit_bytes,
        recovery_expectation="Synthetic host fixture only.",
    )
    launch_path = tmp_path / "launch.json"
    launch_path.write_bytes(core.read_session_artifact(session.id, launch_artifact.id))
    result = subprocess.run(
        [sys.executable, "-c", _CHILD, str(_COLLECTOR), str(launch_path)],
        capture_output=True, timeout=8,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout
    return session.id, image, manifest_artifact, launch, launch_artifact, result.stdout, tmp_path


@pytest.fixture
def captured(core, tmp_path):
    return _capture(core, tmp_path)


def _import(core, captured, stream: bytes):
    session_id, _image, manifest_artifact, _launch, launch_artifact, _original, root = captured
    path = root / "capture.bin"
    path.write_bytes(stream)
    return import_native_capture(
        core, session_id,
        launch_artifact_id=launch_artifact.id,
        image_manifest_artifact_id=manifest_artifact.id,
        stream_path=path,
    )


def test_complete_child_capture_is_stored_and_screened_without_physical_qualification(core, captured):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    wire = [decode_native_result_frame(frame) for frame in _frames(stream)]
    assert [frame.frame_kind for frame in wire] == ["identity", "data", "data", "end"]

    capture, raw_artifact, normalized_artifact = _import(core, captured, stream)

    assert capture.status == "complete"
    assert capture.launch_binding_verified is True
    assert capture.identity_verified is False
    assert core.read_session_artifact(session_id, raw_artifact.id) == stream
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["protocol_status"] == "complete"
    assert document["payload_screening"] == "screened_known_collector_records"
    assert document["physical_source_verified"] is False
    assert document["capture_timing_verified"] is False
    samples = [json.loads(line) for line in capture.payload.splitlines()]
    assert [sample["sample_index"] for sample in samples] == [0, 1]
    assert all(sample["sources"]["device_tree_model"] == "synthetic-host-fixture" for sample in samples)


@pytest.mark.parametrize("damage", ["truncated", "invalid_checksum"])
def test_damaged_child_stream_is_preserved_with_unknown_status(core, captured, damage):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    if damage == "truncated":
        damaged = stream[:-9]
    else:
        damaged = bytearray(stream)
        last_start = len(stream) - len(_frames(stream)[-1])
        position = damaged.index(b'"frame_sha256":"', last_start) + len(b'"frame_sha256":"')
        damaged[position] = ord("a") if damaged[position] != ord("a") else ord("b")
        damaged = bytes(damaged)

    capture, raw_artifact, normalized_artifact = _import(core, captured, damaged)

    assert capture.status == "unknown"
    assert capture.identity_verified is False
    assert core.read_session_artifact(session_id, raw_artifact.id) == damaged
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["status"] == "unknown"
    assert document["physical_source_verified"] is False


@pytest.mark.parametrize("field", ["run_id", "boot_epoch"])
def test_mismatched_child_identity_frame_fails_closed(core, captured, field):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    frames = _frames(stream)
    identity = decode_native_result_frame(frames[0])
    altered = identity.model_copy(update={field: "different-synthetic-value"})
    forged_stream = encode_native_result_frame(altered) + b"".join(frames[1:])

    capture, raw_artifact, normalized_artifact = _import(core, captured, forged_stream)

    assert capture.status == "unknown"
    assert capture.launch_binding_verified is False
    assert capture.identity_verified is False
    assert core.read_session_artifact(session_id, raw_artifact.id) == forged_stream
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["protocol_status"] == "unknown"
    assert document["physical_source_verified"] is False


def test_complete_protocol_with_missing_sample_is_screened_out(core, captured):
    session_id, _image, _manifest, launch, _artifact, stream, _root = captured
    frames = _frames(stream)
    shortened = b"".join(frames[:2]) + encode_native_result_frame(make_native_result_frame(
        frame_kind="end", run_id=launch.run_id,
        image_sha256=launch.image_sha256, target_identity=launch.target_identity,
        boot_epoch=launch.boot_epoch,
        configuration_sha256=launch.configuration_sha256,
        sequence=2, terminal_status="complete",
    ))

    capture, raw_artifact, normalized_artifact = _import(core, captured, shortened)

    assert capture.status == "unknown"
    assert capture.payload == b""
    assert core.read_session_artifact(session_id, raw_artifact.id) == shortened
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["protocol_status"] == "complete"
    assert document["payload_screening"] == "omitted_sample_count_mismatch"
    assert document["physical_source_verified"] is False


def test_saved_capture_imports_after_deadline_but_live_paths_refuse(core, tmp_path):
    captured = _capture(core, tmp_path, deadline_seconds=2)
    session_id, image, _manifest, launch, launch_artifact, stream, _root = captured
    wait = (launch.deadline - datetime.now(timezone.utc)).total_seconds() + 0.1
    if wait > 0:
        time.sleep(wait)
    saved_launch = core.read_session_artifact(session_id, launch_artifact.id)

    with pytest.raises((NativeHarnessError, ValueError)):
        decode_native_launch_manifest(saved_launch)
    with pytest.raises(NativeHarnessError, match="deadline"):
        NativeResultAssembler(launch, image)

    capture, raw_artifact, normalized_artifact = _import(core, captured, stream)
    assert capture.status == "complete"
    assert capture.identity_verified is False
    assert core.read_session_artifact(session_id, raw_artifact.id) == stream
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["capture_timing_verified"] is False


def test_bounded_ten_sample_schedule_completes_in_real_child(core, tmp_path):
    _session_id, _image, _manifest, _launch, _artifact, stream, _root = _capture(
        core, tmp_path, sample_count=10, output_limit_bytes=16_384,
    )
    wire = [decode_native_result_frame(frame) for frame in _frames(stream)]
    assert [frame.frame_kind for frame in wire].count("data") == 10
    assert wire[-1].frame_kind == "end"
    assert wire[-1].terminal_status == "complete"


def test_child_reaches_payload_cap_and_import_preserves_partial_samples(core, tmp_path):
    captured = _capture(core, tmp_path, sample_count=20, output_limit_bytes=4096)
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    wire = [decode_native_result_frame(frame) for frame in _frames(stream)]
    data_count = sum(frame.frame_kind == "data" for frame in wire)
    assert 0 < data_count < 20
    assert wire[-1].frame_kind == "end"
    assert wire[-1].terminal_status == "partial"

    capture, raw_artifact, normalized_artifact = _import(core, captured, stream)

    assert capture.status == "partial"
    assert capture.payload
    assert len(capture.payload.splitlines()) == data_count
    assert core.read_session_artifact(session_id, raw_artifact.id) == stream
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["payload_screening"] == "screened_known_collector_records"
    assert document["physical_source_verified"] is False


def test_launch_rejects_sample_duration_equal_to_deadline(core, captured):
    session_id, _image, manifest_artifact, _launch, launch_artifact, _stream, _root = captured
    image_artifact_id = launch_artifact.provenance["image_artifact_id"]
    before = len(core.artifacts(session_id, record_type="native_launch_manifest"))

    with pytest.raises(NativeHarnessError, match="headroom"):
        prepare_native_launch(
            core, session_id,
            image_manifest_artifact_id=manifest_artifact.id,
            image_artifact_id=image_artifact_id,
            target_identity="synthetic-target", boot_epoch="synthetic-boot",
            sample_count=20, sample_period_ms=100, deadline_seconds=2,
            output_limit_bytes=4096, recovery_expectation="Synthetic host fixture only.",
        )
    assert len(core.artifacts(session_id, record_type="native_launch_manifest")) == before


@pytest.mark.parametrize(
    "parameters",
    [
        {"sample_count": True, "sample_period_ms": 100},
        {"sample_count": 2},
        {"sample_count": 2, "sample_period_ms": 100, "extra": 1},
        {"sample_count": 2, "sample_period_ms": 99},
    ],
    ids=["bool-count", "missing-period", "extra-field", "short-period"],
)
def test_saved_launch_with_malformed_collector_parameters_refuses_import(core, captured, parameters):
    session_id, _image, manifest_artifact, _launch, launch_artifact, stream, root = captured
    document = json.loads(core.read_session_artifact(session_id, launch_artifact.id))
    document["parameters"] = parameters
    malformed = core.publish_artifact(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode(),
        media_type=LAUNCH_MANIFEST_MEDIA_TYPE,
        provenance=dict(launch_artifact.provenance),
    )
    stream_path = root / "malformed-launch-stream.bin"
    stream_path.write_bytes(stream)

    with pytest.raises(NativeHarnessError, match="collector"):
        import_native_capture(
            core, session_id,
            launch_artifact_id=malformed.id,
            image_manifest_artifact_id=manifest_artifact.id,
            stream_path=stream_path,
        )
    assert core.artifacts(session_id, record_type="native_result_stream") == []
