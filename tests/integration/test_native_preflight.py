"""Read-only host preflight over synthetic USB metadata; no physical hardware."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat

import pytest

from m1lab.adapters.native_candidate import NativeCandidateBackend, compute_proxyclient_sha256


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "native-preflight.py"
_SPEC = importlib.util.spec_from_file_location("m1lab_native_preflight_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
preflight = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(preflight)
_SERIAL = "synthetic-private-serial-never-print"
_DIGEST = hashlib.sha256(_SERIAL.encode()).hexdigest()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    library = tmp_path / "proxyclient"
    library.mkdir()
    (library / "module.py").write_bytes(b"# synthetic library\n")
    python = tmp_path / "python3"
    python.write_bytes(b"synthetic interpreter\n")
    python.chmod(0o700)
    script = tmp_path / "linux.py"
    script.write_bytes(b"# synthetic boot script\n")
    config = {
        "artifact_root": str(artifacts), "usb_topology": "1-1",
        "expected_proxy_serial_sha256": _DIGEST,
        "python_path": str(python), "python_sha256": hashlib.sha256(python.read_bytes()).hexdigest(),
        "boot_script_path": str(script), "boot_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "proxyclient_path": str(library), "proxyclient_sha256": compute_proxyclient_sha256(library),
    }
    config_path = tmp_path / "native-helper.json"
    config_path.write_text(json.dumps(config))
    sysfs_root, device_root = tmp_path / "sys", tmp_path / "dev"
    sysfs_root.mkdir()
    device_root.mkdir()

    # Ordinary temporary files stand in for device nodes. Only metadata is faked.
    original_lstat = Path.lstat

    def lstat(path):
        info = original_lstat(path)
        if path.parent == device_root:
            values = list(info)
            values[0] = stat.S_IFCHR | stat.S_IMODE(info.st_mode)
            return os.stat_result(values)
        return info

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(NativeCandidateBackend, "__enter__", lambda _self: pytest.fail("backend entered"))
    monkeypatch.setattr(NativeCandidateBackend, "_open_observer", lambda *_args: pytest.fail("serial observer opened"))
    original_open, original_io_open = os.open, io.open

    def guard_open(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path).parent == device_root:
            pytest.fail("serial device opened")
        return original_open(path, *args, **kwargs)

    def guard_io_open(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path).parent == device_root:
            pytest.fail("serial device opened")
        return original_io_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", guard_open)
    monkeypatch.setattr(io, "open", guard_io_open)

    def proxy(topology="1-1", tty="ttyACM0", serial=_SERIAL, interface_number="00"):
        usb = tmp_path / "usb" / topology
        usb.mkdir(parents=True, exist_ok=True)
        (usb / "idVendor").write_text("1209\n")
        (usb / "idProduct").write_text("316d\n")
        (usb / "serial").write_text(serial + "\n")
        interface = usb / f"{topology}:1.{int(interface_number, 16)}"
        interface.mkdir(exist_ok=True)
        (interface / "bInterfaceNumber").write_text(interface_number + "\n")
        entry = sysfs_root / tty
        entry.mkdir()
        (entry / "device").symlink_to(interface)
        # Bypass only the test's open guard to prepare the fake device.
        with original_io_open(device_root / tty, "w"):
            pass

    def check(**kwargs):
        report = preflight.preflight(config_path, sysfs_root=sysfs_root, device_root=device_root, **kwargs)
        assert _SERIAL not in json.dumps(report)
        return report

    return config, config_path, device_root, proxy, check


def codes(report):
    return {item["code"] for item in report["blockers"]}


def test_matching_proxy_and_pins_pass_without_opening_device(environment):
    _, _, _, proxy, check = environment
    proxy()
    report = check()
    assert report["status"] == "ready"
    assert report["tools"]["pins_match"] is True
    assert report["artifact_root"]["accessible"] is True
    match = report["usb"]["matches"][0]
    assert match["topology"] == "1-1"
    assert match["serial_sha256"] == _DIGEST
    assert match["device"]["accessible"] is True


def test_wrong_port_and_denied_access_are_both_actionable(environment, monkeypatch):
    _, _, device_root, proxy, check = environment
    proxy(topology="1-2")
    original_access = os.access
    monkeypatch.setattr(os, "access", lambda path, mode, **kwargs:
                        False if Path(path).parent == device_root else original_access(path, mode, **kwargs))
    report = check()
    assert report["status"] == "blocked"
    assert codes(report) == {"topology_mismatch", "device_inaccessible"}
    assert report["usb"]["configured_topology"] == "1-1"
    assert report["usb"]["matches"][0]["topology"] == "1-2"
    assert all(item["action"] for item in report["blockers"])


@pytest.mark.parametrize("second_port,expected_code", [("1-2", "proxy_ambiguous"), ("1-1", "usb_scan_invalid")])
def test_matching_proxy_must_be_unique(environment, second_port, expected_code):
    _, _, _, proxy, check = environment
    proxy()
    proxy(topology=second_port, tty="ttyACM1")
    report = check()
    assert report["status"] == "blocked"
    assert expected_code in codes(report)


@pytest.mark.parametrize("serial,interface", [("different-private-serial", "00"), (_SERIAL, "02")])
def test_wrong_identity_or_interface_is_not_selected(environment, serial, interface):
    _, _, _, proxy, check = environment
    proxy(serial=serial, interface_number=interface)
    report = check()
    assert codes(report) == {"proxy_not_found"}
    assert serial not in json.dumps(report)
    assert report["usb"]["matches"] == []


def test_missing_device_node_is_a_blocker(environment):
    _, _, device_root, proxy, check = environment
    proxy()
    (device_root / "ttyACM0").unlink()
    assert codes(check()) == {"proxy_not_found"}


@pytest.mark.parametrize("damage", ["missing", "unknown_key", "duplicate_key", "invalid_digest"])
def test_missing_or_invalid_configuration_is_safe_json(environment, damage, capsys):
    config, config_path, _, _, _ = environment
    if damage == "missing":
        config_path.unlink()
    elif damage == "unknown_key":
        config["secret"] = _SERIAL
        config_path.write_text(json.dumps(config))
    elif damage == "duplicate_key":
        config_path.write_text(json.dumps(config)[:-1] + ',"usb_topology":"1-2"}')
    else:
        config["python_sha256"] = _SERIAL
        config_path.write_text(json.dumps(config))
    assert preflight.main(["--config", str(config_path)]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert _SERIAL not in output
    assert codes(report) == {"config_invalid"}


@pytest.mark.parametrize("damage", ["changed_tool", "symlink_tool", "missing_artifacts", "not_executable"])
def test_file_prerequisites_follow_backend_rules(environment, damage):
    config, _, _, proxy, check = environment
    proxy()
    if damage == "changed_tool":
        Path(config["boot_script_path"]).write_text("changed\n")
        expected = "tool_pins_invalid"
    elif damage == "symlink_tool":
        tool = Path(config["boot_script_path"])
        original = tool.with_name("original.py")
        tool.rename(original)
        tool.symlink_to(original)
        expected = "tool_pins_invalid"
    elif damage == "missing_artifacts":
        Path(config["artifact_root"]).rmdir()
        expected = "artifact_root_unavailable"
    else:
        Path(config["python_path"]).chmod(0o600)
        expected = "python_not_executable"
    assert expected in codes(check())


def test_optional_socket_is_metadata_only_and_not_required(environment, monkeypatch, tmp_path):
    _, _, _, proxy, check = environment
    proxy()
    path = tmp_path / "helper.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        monkeypatch.setattr(socket, "socket", lambda *_args: pytest.fail("socket connection attempted"))
        report = check(helper_socket=path)
        assert report["status"] == "ready"
        assert report["helper_socket"]["socket"] is True
        assert report["helper_socket"]["listening"] == "not_probed"
    path.unlink()
    report = check(helper_socket=path)
    assert report["status"] == "ready"
    assert report["helper_socket"]["present"] is False
