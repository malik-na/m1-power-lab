"""Native Linux identity self-report; synthetic host execution only."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from m1lab.adapters.native_harness import (
    NativeHarnessError, NativeResultAssembler, decode_native_result_frame,
    encode_native_result_frame, make_native_result_frame,
)
from test_native_capture import _COLLECTOR, _frames, _import, captured


BOOT_ID = "12345678-1234-4abc-8def-123456789abc"
BOOT_SOURCE = Path(__file__).resolve().parents[2] / "target" / "native_boot.py"


def _module(name: str, source: Path):
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observed(config: str) -> dict[str, str]:
    return {
        "boot_id": BOOT_ID,
        "kernel_release": "7.1.13-3-2-ARCH",
        "configuration_sha256": config,
    }


def test_legacy_identity_reencodes_with_exact_original_bytes_and_checksum(captured):
    _session, _image, _manifest, _launch, _artifact, stream, _root = captured
    legacy = _frames(stream)[0]
    frame = decode_native_result_frame(legacy)
    assert frame.observed_linux is None
    assert encode_native_result_frame(frame) == legacy
    assert b'"observed_linux"' not in legacy


def test_observed_identity_round_trip_and_assembler_binding(captured):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    frame = make_native_result_frame(
        frame_kind="identity", run_id=launch.run_id,
        image_sha256=launch.image_sha256, target_identity=launch.target_identity,
        boot_epoch=launch.boot_epoch,
        configuration_sha256=launch.configuration_sha256, sequence=0,
        observed_linux=_observed(launch.configuration_sha256),
    )
    encoded = encode_native_result_frame(frame)
    assert b'"observed_linux"' in encoded
    assert decode_native_result_frame(encoded).observed_linux.boot_id == BOOT_ID
    assembler = NativeResultAssembler(launch, image)
    assembler.accept(encoded)
    result = assembler.capture()
    assert result.observed_linux.kernel_release == "7.1.13-3-2-ARCH"
    assert result.identity_verified is False
    assert result.launch_binding_verified is True


@pytest.mark.parametrize("field,value", [
    ("boot_id", "not-a-uuid"),
    ("kernel_release", "release\nprivate-data"),
    ("configuration_sha256", "not-a-digest"),
])
def test_malformed_observation_is_refused(captured, field, value):
    _session, _image, _manifest, launch, _artifact, stream, _root = captured
    document = json.loads(_frames(stream)[0][4:])
    observation = _observed(launch.configuration_sha256)
    observation[field] = value
    document["observed_linux"] = observation
    document["frame_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in document.items() if k != "frame_sha256"},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(NativeHarnessError):
        decode_native_result_frame(struct.pack(">I", len(body)) + body)


def test_mismatched_observed_configuration_refuses_identity(captured):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    frame = make_native_result_frame(
        frame_kind="identity", run_id=launch.run_id,
        image_sha256=launch.image_sha256, target_identity=launch.target_identity,
        boot_epoch=launch.boot_epoch,
        configuration_sha256=launch.configuration_sha256, sequence=0,
        observed_linux=_observed("0" * 64),
    )
    assembler = NativeResultAssembler(launch, image)
    with pytest.raises(NativeHarnessError, match="observed Linux configuration"):
        assembler.accept(encode_native_result_frame(frame))
    assert assembler.capture().status == "unknown"


def test_observation_is_identity_only(captured):
    _session, _image, _manifest, launch, _artifact, _stream, _root = captured
    with pytest.raises(ValueError, match="identity frames"):
        make_native_result_frame(
            frame_kind="data", run_id=launch.run_id,
            image_sha256=launch.image_sha256, target_identity=launch.target_identity,
            boot_epoch=launch.boot_epoch,
            configuration_sha256=launch.configuration_sha256, sequence=1,
            payload=b"synthetic\n",
            observed_linux=_observed(launch.configuration_sha256),
        )


def test_native_boot_observes_fixed_paths_and_refuses_configuration_mismatch(tmp_path, monkeypatch):
    collector = _module("identity_collector", _COLLECTOR)
    boot = _module("identity_boot", BOOT_SOURCE)
    boot_id = tmp_path / "boot_id"
    boot_id.write_text(BOOT_ID + "\n")
    configuration = tmp_path / "image-config.json"
    configuration.write_bytes(b'{"fixture":"native-image"}\n')
    monkeypatch.setattr(boot, "BOOT_ID", boot_id)
    monkeypatch.setattr(boot, "IMAGE_CONFIG", configuration)
    launch = {"configuration_sha256": hashlib.sha256(configuration.read_bytes()).hexdigest()}
    observed = boot._observe_linux(launch, collector)
    assert observed["boot_id"] == BOOT_ID
    assert observed["kernel_release"]
    assert observed["configuration_sha256"] == launch["configuration_sha256"]
    with pytest.raises(collector.CaptureError, match="does not match"):
        boot._observe_linux({"configuration_sha256": "0" * 64}, collector)
    configuration.unlink()
    with pytest.raises(FileNotFoundError):
        boot._observe_linux(launch, collector)


_CHILD_WITH_OBSERVATION = """
import importlib.util
import os
from pathlib import Path
import sys
source, launch_path, boot_id, release = sys.argv[1:]
spec = importlib.util.spec_from_file_location('native_capture_observed', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._sysfs_snapshot = lambda: {
    'device_tree_model': 'synthetic-host-fixture',
    'power_supplies': [], 'thermal_zones': [],
}
launch = module.load_launch(Path(launch_path))
module._emit(sys.stdout.fileno(), launch, observed_linux={
    'boot_id': boot_id, 'kernel_release': release,
    'configuration_sha256': launch['configuration_sha256'],
})
"""


def test_collector_child_emits_observed_identity_and_import_stays_unverified(core, captured):
    session_id, _image, _manifest, _launch, _artifact, _stream, root = captured
    process = subprocess.run(
        [sys.executable, "-c", _CHILD_WITH_OBSERVATION,
         str(_COLLECTOR), str(root / "launch.json"), BOOT_ID, "7.1.13-3-2-ARCH"],
        capture_output=True, timeout=8,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    first = decode_native_result_frame(_frames(process.stdout)[0])
    assert first.observed_linux.boot_id == BOOT_ID
    capture, _raw, artifact = _import(core, captured, process.stdout)
    assert capture.status == "complete"
    assert capture.observed_linux.boot_id == BOOT_ID
    document = json.loads(core.read_session_artifact(session_id, artifact.id))
    assert document["observed_linux"]["boot_id"] == BOOT_ID
    assert document["identity_verified"] is False
    assert document["physical_source_verified"] is False
    assert document["capture_timing_verified"] is False


def test_sensitive_kernel_release_is_omitted_from_screened_capture(core, captured):
    session_id, _image, _manifest, _launch, _artifact, _stream, root = captured
    release = "7.1.13-ghp_" + "a" * 30
    process = subprocess.run(
        [sys.executable, "-c", _CHILD_WITH_OBSERVATION,
         str(_COLLECTOR), str(root / "launch.json"), BOOT_ID, release],
        capture_output=True, timeout=8,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    assert decode_native_result_frame(_frames(process.stdout)[0]).observed_linux.kernel_release == release
    capture, raw, artifact = _import(core, captured, process.stdout)
    assert core.read_session_artifact(session_id, raw.id) == process.stdout
    assert capture.observed_linux is None
    document = json.loads(core.read_session_artifact(session_id, artifact.id))
    assert document["observed_linux"] is None
    assert document["observed_linux_screening"] == "omitted_sensitive_observation"
    assert document["identity_verified"] is False
    assert document["physical_source_verified"] is False
