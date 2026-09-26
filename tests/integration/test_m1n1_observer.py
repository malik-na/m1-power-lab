"""Synthetic identity fixtures; these tests never open an M1 device."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pty
import runpy
import subprocess
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from m1lab.adapters.hardware import HardwareUnavailable
from m1lab.adapters.m1n1_observer import M1N1Observer
from m1lab.adapters.m1n1_transport import ProxyIdentity


class FakeTransport:
    def __init__(self, device: Path):
        self.device = device
        self.closed = False
        self.deadlines = []
        self.failure = None
        self.identity = ProxyIdentity(chip_id=0x8103, base=0x100000, bootargs_address=0x200000)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def observe(self, *, deadline_monotonic: float):
        self.deadlines.append(deadline_monotonic)
        if self.failure is not None:
            raise self.failure
        return self.identity


@pytest.fixture
def fixture(tmp_path):
    master, slave = pty.openpty()
    try:
        device_root = tmp_path / "dev"
        device_root.mkdir()
        device = device_root / "ttyACM0"
        device.symlink_to(os.ttyname(slave))
        usb_device = tmp_path / "sys" / "devices" / "1-1"
        interface = usb_device / "1-1:1.0"
        interface.mkdir(parents=True)
        (usb_device / "idVendor").write_text("1209\n")
        (usb_device / "idProduct").write_text("316d\n")
        (usb_device / "serial").write_text("private-fixture-serial\n")
        (interface / "bInterfaceNumber").write_text("00\n")
        sysfs_root = tmp_path / "sys" / "class" / "tty"
        tty_class = sysfs_root / device.name
        tty_class.mkdir(parents=True)
        (tty_class / "device").symlink_to(interface, target_is_directory=True)
        transports = []

        def factory(path):
            transport = FakeTransport(path)
            transports.append(transport)
            return transport

        observer = M1N1Observer(
            device,
            expected_usb_topology="1-1",
            expected_serial_sha256=hashlib.sha256(b"private-fixture-serial").hexdigest(),
            sysfs_root=sysfs_root,
            device_root=device_root,
            transport_factory=factory,
        )
        yield observer, transports, usb_device, interface
    finally:
        os.close(master)
        os.close(slave)


def test_observation_is_fresh_bounded_and_never_dispatch_qualified(fixture):
    observer, transports, _, _ = fixture
    with observer:
        before = time.monotonic()
        snapshot = observer.inspect()
        after = time.monotonic()
        assert snapshot.available is True
        assert snapshot.qualified is False
        assert snapshot.mode == "proxy"
        assert snapshot.boot_epoch is None
        assert snapshot.capabilities == ()
        assert "private-fixture-serial" not in snapshot.message
        assert transports[0].device == observer.device
        assert len(transports[0].deadlines) == 1
        assert before < transports[0].deadlines[0] <= after + 5.0
        assert observer.last_identity == transports[0].identity
        with pytest.raises(HardwareUnavailable, match="never dispatches"):
            observer.execute(None)
    assert transports[0].closed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idVendor", "ffff\n"),
        ("idProduct", "0000\n"),
        ("serial", "different\n"),
    ],
)
def test_usb_identity_mismatch_prevents_transport_open(fixture, field, value):
    observer, transports, usb_device, _ = fixture
    (usb_device / field).write_text(value)
    with pytest.raises(HardwareUnavailable):
        observer.__enter__()
    assert transports == []


def test_interface_mismatch_prevents_transport_open(fixture):
    observer, transports, _, interface = fixture
    (interface / "bInterfaceNumber").write_text("01\n")
    with pytest.raises(HardwareUnavailable):
        observer.__enter__()
    assert transports == []


def test_changed_usb_identity_after_open_closes_transport(fixture):
    observer, transports, usb_device, _ = fixture
    with observer:
        (usb_device / "serial").write_text("other-device\n")
        snapshot = observer.inspect()
        assert not snapshot.available and not snapshot.qualified
        assert observer.last_identity is None
        assert transports[0].closed
        assert observer.inspect().available is False
        assert len(transports[0].deadlines) == 0


@pytest.mark.parametrize("wrong_chip", [False, True], ids=["transport-failure", "wrong-chip"])
def test_failed_or_wrong_chip_observation_invalidates_without_retry(fixture, wrong_chip):
    observer, transports, _, _ = fixture
    with observer:
        if wrong_chip:
            transports[0].identity = ProxyIdentity(0x9999, 0x100000, 0x200000)
        else:
            transports[0].failure = TimeoutError("synthetic deadline")
        snapshot = observer.inspect()
        assert not snapshot.available and not snapshot.qualified
        assert transports[0].closed
        assert len(transports[0].deadlines) == 1
        assert observer.inspect().available is False
        assert len(transports[0].deadlines) == 1


def test_probe_script_missing_device_reports_bounded_redacted_failure():
    script = Path(__file__).resolve().parents[2] / "scripts" / "probe-m1n1-helper.py"
    result = subprocess.run(
        [sys.executable, str(script), "--device", "/dev/ttyACM999999",
         "--expected-serial-sha256", "a" * 64, "--max-total-seconds", "6"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["available"] is False
    assert output["qualified"] is False
    assert output["proxy_identity"] is None
    assert "no dispatch qualification" in output["limitations"]
    assert "error_type" not in output


def _probe_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "probe-m1n1-helper.py"
    return runpy.run_path(str(script))


def test_probe_closes_socket_then_tty_then_owner_lock():
    module = _probe_module()
    serve_one = module["_serve_one"]
    events = []

    class Observer:
        last_identity = ProxyIdentity(0x8103, 0x100000, 0x200000)

        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            events.append("tty-open")
            return self

        def __exit__(self, *_args):
            events.append("tty-close")

    class Server:
        def serve_once(self):
            events.append("serve")

        def close(self):
            events.append("socket-close")

    class Owner:
        def __exit__(self, *_args):
            events.append("owner-unlock")

    class Connection:
        def send(self, message):
            events.append(message["event"])

        def close(self):
            events.append("pipe-close")

    def start(_lock, _socket, factory):
        events.append("owner-lock")
        factory()
        return Owner(), Server()

    serve_one.__globals__["M1N1Observer"] = Observer
    serve_one.__globals__["start_exclusive_helper"] = start
    serve_one(Connection(), "/tmp/owner", "/tmp/socket", "/dev/ttyACM0", "1-1", "a" * 64)
    assert events == [
        "owner-lock", "tty-open", "ready", "serve", "done",
        "socket-close", "tty-close", "owner-unlock", "pipe-close",
    ]


@pytest.mark.parametrize(
    ("forced", "child_error"),
    [(False, False), (True, False), (False, True)],
    ids=["nonzero-exit", "forced-termination", "clean-exit-child-error"],
)
def test_probe_rejects_available_snapshot_when_helper_fails(capsys, monkeypatch, forced, child_error):
    module = _probe_module()
    main = module["main"]
    messages = [
        {"event": "ready"},
        ({"event": "error", "error_type": "SyntheticFailure"} if child_error else
         {"event": "done", "proxy_identity": {"chip_id": 0x8103, "base": 1, "bootargs_address": 2}}),
    ]

    class Connection:
        def poll(self, _timeout):
            return bool(messages)

        def recv(self):
            return messages.pop(0)

        def close(self):
            pass

    class Process:
        def __init__(self, **_kwargs):
            self.exitcode = 0 if forced or child_error else 9
            self.alive = forced

        def start(self):
            pass

        def join(self, **_kwargs):
            pass

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.alive = False
            self.exitcode = -15

    class Context:
        def Pipe(self, **_kwargs):
            return Connection(), Connection()

        def Process(self, **kwargs):
            return Process(**kwargs)

    class Adapter:
        def __init__(self, _path):
            pass

        def inspect(self):
            return SimpleNamespace(
                available=True, qualified=False, mode="proxy", boot_epoch=None,
                capabilities=(), observed_at=datetime.now(timezone.utc), message="synthetic",
            )

    main.__globals__["M1N1Observer"] = lambda *_args, **_kwargs: None
    main.__globals__["HelperHardwareAdapter"] = Adapter
    monkeypatch.setattr(main.__globals__["mp"], "get_context", lambda _method: Context())
    assert main(["--device", "/dev/ttyACM0", "--expected-serial-sha256", "a" * 64]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["available"] is False
    assert output["mode"] == "disconnected"
    assert output["qualified"] is False
    assert output["proxy_identity"] is None
    assert "observed_at" not in output
    assert "message" not in output
    assert ("observation" if child_error else "cleanup") in output["error"]
