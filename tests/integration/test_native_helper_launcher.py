"""The explicit native helper launcher validates owner and fixed configuration."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "serve-native-helper.py"
_SPEC = importlib.util.spec_from_file_location("m1lab_native_helper_launcher_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
launcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launcher)


def _config(tmp_path: Path) -> dict[str, str]:
    return {
        "artifact_root": str(tmp_path / "artifacts"),
        "usb_topology": "1-1",
        "expected_proxy_serial_sha256": "a" * 64,
        "python_path": str(tmp_path / "python"),
        "python_sha256": "b" * 64,
        "boot_script_path": str(tmp_path / "linux.py"),
        "boot_script_sha256": "c" * 64,
        "proxyclient_path": str(tmp_path / "proxyclient"),
        "proxyclient_sha256": "d" * 64,
    }


def test_valid_config_passes_fixed_backend_factory_and_parent_lease(tmp_path, monkeypatch):
    config_path = tmp_path / "native-helper.json"
    config_path.write_text(json.dumps(_config(tmp_path)))
    read_fd, write_fd = os.pipe()
    calls = []

    class FakeSupervisor:
        def __init__(self, state_dir, backend_factory, **deadlines):
            calls.append((state_dir, backend_factory, deadlines))

        def run(self, stopped, *, owner_pidfd):
            assert not stopped.is_set()
            assert owner_pidfd == read_fd
            os.fstat(owner_pidfd)

    monkeypatch.setattr(launcher.os, "pidfd_open", lambda pid: read_fd if pid == os.getppid() else None)
    monkeypatch.setattr(launcher, "HelperSupervisor", FakeSupervisor)
    monkeypatch.setattr(launcher.signal, "signal", lambda *_args: None)
    try:
        result = launcher.main([
            "--state-dir", str(tmp_path / "state"), "--config", str(config_path),
            "--owner-pid", str(os.getppid()),
        ])
    finally:
        os.close(write_fd)

    assert result == 0
    assert len(calls) == 1
    state_dir, factory, deadlines = calls[0]
    assert state_dir == tmp_path / "state"
    assert deadlines == {"startup_seconds": 12, "request_seconds": 480, "cleanup_seconds": 3}
    assert factory.func is launcher.NativeCandidateBackend
    assert factory.keywords["boot_script_path"] == tmp_path / "linux.py"
    assert factory.keywords["proxyclient_sha256"] == "d" * 64
    assert factory.keywords["diagnostic_dir"] == tmp_path / "state" / "boot-logs"
    with pytest.raises(OSError):
        os.fstat(read_fd)  # launcher closed its owner lease


@pytest.mark.parametrize("damage", ["extra_key", "wrong_type", "duplicate_key"])
def test_invalid_config_fails_before_backend_construction(tmp_path, monkeypatch, damage):
    config = _config(tmp_path)
    if damage == "extra_key":
        config["backend_class"] = "arbitrary.module.Backend"
    elif damage == "wrong_type":
        config["python_sha256"] = 123
    config_path = tmp_path / "invalid.json"
    encoded = json.dumps(config)
    if damage == "duplicate_key":
        encoded = encoded[:-1] + ',"python_sha256":"d"}'
    config_path.write_text(encoded)
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(launcher.os, "pidfd_open", lambda _pid: read_fd)
    monkeypatch.setattr(launcher, "NativeCandidateBackend", lambda **_kwargs: pytest.fail("backend constructed"))
    monkeypatch.setattr(launcher, "HelperSupervisor", lambda *_args, **_kwargs: pytest.fail("supervisor constructed"))
    try:
        assert launcher.main([
            "--state-dir", str(tmp_path / "state"), "--config", str(config_path),
            "--owner-pid", str(os.getppid()),
        ]) == 1
    finally:
        os.close(write_fd)
    with pytest.raises(OSError):
        os.fstat(read_fd)


def test_missing_or_nonparent_owner_never_starts_helper(tmp_path, monkeypatch):
    config_path = tmp_path / "native-helper.json"
    config_path.write_text(json.dumps(_config(tmp_path)))
    monkeypatch.setattr(launcher.os, "pidfd_open", lambda _pid: pytest.fail("pidfd opened"))
    monkeypatch.setattr(launcher, "NativeCandidateBackend", lambda **_kwargs: pytest.fail("backend constructed"))
    monkeypatch.setattr(launcher, "HelperSupervisor", lambda *_args, **_kwargs: pytest.fail("supervisor constructed"))
    with pytest.raises(SystemExit) as help_exit:
        launcher.main(["--help"])
    assert help_exit.value.code == 0
    with pytest.raises(SystemExit) as missing:
        launcher.main(["--state-dir", str(tmp_path / "state"), "--config", str(config_path)])
    assert missing.value.code == 2
    assert launcher.main([
        "--state-dir", str(tmp_path / "state"), "--config", str(config_path),
        "--owner-pid", str(os.getppid() + 100000),
    ]) == 1
