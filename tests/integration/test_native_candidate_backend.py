"""Synthetic native backend ordering and result retention; no target or device."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from m1lab.adapters.hardware import (
    HardwareDispatch, HardwareResultStatus, RunNativeCandidate, TargetSnapshot,
)
from m1lab.adapters import native_candidate as module


PAYLOAD, IMAGE, LAUNCH = "a" * 64, "b" * 64, "c" * 64
SERIAL = "d" * 64


def _backend(tmp_path):
    library = tmp_path / "proxyclient"
    library.mkdir()
    (library / "module.py").write_bytes(b"# synthetic import module\n")
    python = tmp_path / "python3"
    python.write_bytes(b"synthetic Python executable\n")
    script = tmp_path / "linux.py"
    script.write_bytes(b"synthetic boot script\n")
    return module.NativeCandidateBackend(
        artifact_root=tmp_path, usb_topology="1-1",
        expected_proxy_serial_sha256=SERIAL,
        python_path=python, python_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),
        boot_script_path=script,
        boot_script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        proxyclient_path=library,
        proxyclient_sha256=module.compute_proxyclient_sha256(library),
        sysfs_root=tmp_path / "sys", device_root=tmp_path / "dev",
    )


def _dispatch(backend, *, seconds=30):
    now = datetime.now(timezone.utc)
    return HardwareDispatch(
        operation_id="native-op", coordinator_operation_id="coordinator-op",
        session_id="session", target_identity=backend.target_identity,
        target_snapshot_id="snapshot", configuration_digest=backend.configuration_digest,
        procedure_id="procedure", procedure_revision=1, review_id="review",
        approval_id="approval", approval_scope={
            "target_identity": backend.target_identity, "boot_epoch": backend._connection_epoch,
            "configuration_digest": backend.configuration_digest, "repeat_limit": 1,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "physical_attendance_confirmed": True,
        },
        boot_epoch=backend._connection_epoch, procedure_digest="1" * 64,
        artifact_digests=(PAYLOAD, IMAGE, LAUNCH), operation_index=0,
        operation=RunNativeCandidate(PAYLOAD, IMAGE, LAUNCH),
        deadline=now + timedelta(seconds=seconds),
    )


def _synthetic_environment(monkeypatch, backend, events, *, raw=b"fixed frame bytes",
                           status="complete", observed=True, return_proxy=True,
                           capture_error=False, tool_exit=0, launch_seconds=20,
                           boot_log=b""):
    monkeypatch.setattr(backend, "_verify_tools", lambda: events.append("verify_tools"))

    def tty(vid, _pid, _deadline, *, proxy):
        events.append("find_proxy" if proxy else "find_native")
        events.append(("tty_deadline", vid, _deadline))
        if proxy and "launch" in events and not return_proxy:
            raise TimeoutError("synthetic proxy did not return")
        return backend.device_root / ("ttyACM0" if proxy else "ttyACM1")

    monkeypatch.setattr(backend, "_wait_for_tty", tty)

    class Observer:
        def __init__(self, device, **_kw):
            self.device = device

        def __enter__(self):
            events.append("observer_open")
            return self

        def __exit__(self, *_args):
            events.append("observer_close")

        def inspect(self):
            events.append("five_read_inspection")
            return TargetSnapshot(
                adapter="synthetic-observer", available=True, qualified=False,
                mode="proxy", target_id=backend.target_identity, boot_epoch=None,
                configuration_digest=None, capabilities=(),
                observed_at=datetime.now(timezone.utc),
            )

    class Bundle:
        def __init__(self, *_args, **_kw):
            pass

        def __enter__(self):
            events.append("bundle_open")
            self.launch = SimpleNamespace(
                target_identity=backend.target_identity,
                boot_epoch=backend._connection_epoch,
                configuration_sha256="2" * 64,
                deadline=datetime.now(timezone.utc) + timedelta(seconds=launch_seconds),
            )
            self.image = SimpleNamespace(configuration_sha256="2" * 64)
            self.kernel = backend.artifact_root / "Image.gz"
            self.dtb = backend.artifact_root / "j313.dtb"
            self.initramfs = backend.artifact_root / "initramfs.cpio.gz"
            return self

        def __exit__(self, *_args):
            events.append("bundle_close")

    class Transport:
        def __init__(self, *_args, **_kw):
            pass

        def __enter__(self):
            events.append("native_open")
            return self

        def __exit__(self, *_args):
            events.append("native_close")

        def capture(self, _launch, _image, *, deadline_monotonic, max_stream_bytes):
            events.append("capture")
            events.append(("capture_bound", deadline_monotonic, max_stream_bytes))
            if capture_error:
                raise OSError("synthetic capture lost")
            return SimpleNamespace(
                raw_stream=raw, stop_reason="terminal" if status == "complete" else "deadline",
                terminal_received_before_deadline=status == "complete",
                capture=SimpleNamespace(
                    status=status, observed_linux=object() if observed else None,
                ),
            )

    class Process:
        pid = 999999

        def poll(self):
            return tool_exit

        def wait(self, timeout):
            return tool_exit

    def popen(argv, **kwargs):
        events.append("launch")
        assert argv[:4] == [str(backend.python_path), str(backend.boot_script_path),
                            "-b", "console=tty0 earlycon rdinit=/init panic=10"]
        assert argv[4:] == [str(backend.artifact_root / "Image.gz"),
                            str(backend.artifact_root / "j313.dtb"),
                            str(backend.artifact_root / "initramfs.cpio.gz")]
        assert kwargs["env"]["M1N1DEVICE"] == str(backend.device_root / "ttyACM0")
        assert "PORT" not in kwargs["env"]
        assert kwargs["env"]["PYTHONPATH"] == str(backend.proxyclient_path)
        assert kwargs["start_new_session"] is True
        assert isinstance(kwargs["preexec_fn"], partial)
        kwargs["stdout"].write(boot_log)
        return Process()

    monkeypatch.setattr(module, "M1N1Observer", Observer)
    monkeypatch.setattr(module, "NativeCandidateBundle", Bundle)
    monkeypatch.setattr(module, "NativeUsbTransport", Transport)
    monkeypatch.setattr(module.subprocess, "Popen", popen)


def test_complete_synthetic_round_trip_closes_proxy_before_launch(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events)
    with backend:
        dispatch = _dispatch(backend)
        initial = backend.inspect()
        assert initial.available and not initial.qualified
        assert initial.boot_epoch
        result = backend.execute(dispatch)
        assert result.status is HardwareResultStatus.COMPLETED
        assert result.payload == b"fixed frame bytes"
        assert result.boot_epoch == dispatch.boot_epoch
        assert result.values["return_boot_epoch"] != dispatch.boot_epoch
        assert backend.inspect().boot_epoch == result.values["return_boot_epoch"]
    assert events.index("observer_close") < events.index("launch") < events.index("native_open")
    assert events.index("native_close") < events.index("find_proxy", events.index("launch"))
    assert backend.inspect().available is False


def test_device_environment_key_changes_configuration_digest(tmp_path):
    backend = _backend(tmp_path)
    old_configuration = {
        "usb_topology": backend.usb_topology,
        "proxy_serial_sha256": backend.expected_proxy_serial_sha256,
        "python_sha256": backend.python_sha256,
        "python_path": str(backend.python_path),
        "boot_script_sha256": backend.boot_script_sha256,
        "boot_script_path": str(backend.boot_script_path),
        "proxyclient_path": str(backend.proxyclient_path),
        "proxyclient_sha256": backend.proxyclient_sha256,
        "bootargs": "console=tty0 earlycon rdinit=/init panic=10",
    }
    old_digest = hashlib.sha256(json.dumps(
        old_configuration, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert backend.configuration_digest != old_digest
    old_configuration["device_env_key"] = "M1N1DEVICE"
    assert backend.configuration_digest == hashlib.sha256(json.dumps(
        old_configuration, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def test_backend_refuses_inexact_approval_before_tool_entry(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events)
    with backend:
        dispatch = _dispatch(backend)
        approval = dict(dispatch.approval_scope)
        approval["repeat_limit"] = 2
        with pytest.raises(module.NativeCandidateError, match="one-run approval"):
            backend.execute(replace(dispatch, approval_scope=approval))
    assert "launch" not in events


def test_additional_reviewed_artifact_digest_does_not_block_fixed_bundle(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events)
    with backend:
        dispatch = _dispatch(backend)
        dispatch = replace(dispatch, artifact_digests=dispatch.artifact_digests + ("3" * 64,))
        result = backend.execute(dispatch)
    assert result.status is HardwareResultStatus.COMPLETED
    assert events.count("launch") == 1


def test_failed_boot_tool_retains_bounded_log_evidence_in_unknown_result(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    events = []
    log = b"synthetic traceback: missing proxy device\n" + b"x" * 6000
    _synthetic_environment(monkeypatch, backend, events, tool_exit=2, boot_log=log)
    with backend:
        result = backend.execute(_dispatch(backend))
    assert result.status is HardwareResultStatus.UNKNOWN
    assert result.values["boot_tool_exit_code"] == 2
    assert result.values["boot_log_bytes"] == len(log)
    assert result.values["boot_log_sha256"] == hashlib.sha256(log).hexdigest()
    assert result.values["boot_log_tail"] == log.decode()[-4096:]
    assert len(result.values["boot_log_tail"]) == 4096
    assert events.count("launch") == 1


@pytest.mark.parametrize("dispatch_seconds,launch_seconds", [(30, 20), (20, 30)])
def test_capture_cutoff_is_minimum_and_proxy_return_uses_envelope(
    tmp_path, monkeypatch, dispatch_seconds, launch_seconds
):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events, launch_seconds=launch_seconds)
    with backend:
        result = backend.execute(_dispatch(backend, seconds=dispatch_seconds))
    assert result.status is HardwareResultStatus.COMPLETED
    capture_bound = next(item for item in events if isinstance(item, tuple)
                         and item[0] == "capture_bound")
    return_bound = [item for item in events if isinstance(item, tuple)
                    and item[:2] == ("tty_deadline", "1209")][-1]
    assert capture_bound[2] == module.MAX_RESULT_BYTES
    assert return_bound[2] > capture_bound[1]
    remaining = capture_bound[1] - time.monotonic()
    assert remaining <= min(launch_seconds, dispatch_seconds - 10)


@pytest.mark.parametrize("options", [
    {"status": "unknown", "raw": b"partial wire"},
    {"observed": False},
    {"return_proxy": False},
    {"capture_error": True},
    {"tool_exit": 2},
])
def test_ambiguous_synthetic_attempt_is_unknown_and_never_reboots(
    tmp_path, monkeypatch, options
):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events, **options)
    with backend:
        dispatch = _dispatch(backend)
        result = backend.execute(dispatch)
    assert result.status is HardwareResultStatus.UNKNOWN
    expected = b"" if options.get("capture_error") else options.get("raw", b"fixed frame bytes")
    assert result.payload == expected
    assert events.count("launch") == 1


def test_fixed_tool_digest_is_checked_without_executing(tmp_path):
    tool = tmp_path / "linux.py"
    tool.write_bytes(b"synthetic fixed tool\n")
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    module._verify_file_hash(tool, digest)
    tool.write_bytes(b"changed\n")
    with pytest.raises(module.NativeCandidateError, match="digest differs"):
        module._verify_file_hash(tool, digest)


def test_proxyclient_tree_pin_is_deterministic_and_ignores_only_bytecode(tmp_path):
    root = tmp_path / "proxyclient"
    package = root / "nested"
    package.mkdir(parents=True)
    source = package / "module.py"
    source.write_bytes(b"value = 1\n")
    first = module.compute_proxyclient_sha256(root)
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython.pyc").write_bytes(b"cache")
    (package / "module.pyc").write_bytes(b"bytecode")
    assert module.compute_proxyclient_sha256(root) == first
    source.write_bytes(b"value = 2\n")
    assert module.compute_proxyclient_sha256(root) != first
    source.write_bytes(b"value = 1\n")
    (package / "data.bin").write_bytes(b"resource")
    assert module.compute_proxyclient_sha256(root) != first
    (package / "data.bin").unlink()
    (package / "link.py").symlink_to(source)
    with pytest.raises(module.NativeCandidateError, match="symlink"):
        module.compute_proxyclient_sha256(root)


def test_changed_proxyclient_import_module_is_refused_before_boot(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    events = []
    _synthetic_environment(monkeypatch, backend, events)
    monkeypatch.setattr(
        backend, "_verify_tools",
        module.NativeCandidateBackend._verify_tools.__get__(backend),
    )
    with backend:
        dispatch = _dispatch(backend)
        (backend.proxyclient_path / "module.py").write_bytes(b"changed import module\n")
        with pytest.raises(module.NativeCandidateError, match="library digest differs"):
            backend.execute(dispatch)
    assert "launch" not in events


def test_boot_child_gets_worker_death_signal_and_process_group(tmp_path):
    read_fd, write_fd = os.pipe()
    parent = os.fork()
    if parent == 0:
        os.close(read_fd)
        try:
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                start_new_session=True,
                preexec_fn=partial(module._bind_child_to_worker, os.getpid()),
            )
            os.write(write_fd, str(child.pid).encode() + b"\n")
            time.sleep(30)
        finally:
            os._exit(0)
    os.close(write_fd)
    try:
        child_pid = int(os.read(read_fd, 32).strip())
        os.kill(parent, signal.SIGKILL)
        os.waitpid(parent, 0)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            stat_path = Path(f"/proc/{child_pid}/stat")
            try:
                state = stat_path.read_text().split()[2]
            except (FileNotFoundError, ProcessLookupError):
                break
            if state == "Z":
                break
            time.sleep(0.05)
        else:
            os.killpg(child_pid, signal.SIGKILL)
            pytest.fail("bootstrap child survived worker death")
    finally:
        os.close(read_fd)


def test_boot_process_group_is_killed_at_timeout():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    try:
        status = module._finish_process(process, time.monotonic() + 0.2)
        assert status == -signal.SIGKILL
        assert process.poll() == -signal.SIGKILL
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
