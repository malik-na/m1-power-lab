"""Candidate ACM binding and one-shot capture against a PTY, never a device."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import pty
import select
import termios
from threading import Thread
import time

import pytest

from m1lab.adapters.native_harness import encode_native_manifest
from m1lab.adapters.native_usb import NativeUsbError, NativeUsbTransport

from test_native_capture import captured


@pytest.fixture
def channel(tmp_path, monkeypatch):
    master, slave = pty.openpty()
    original_settings = termios.tcgetattr(slave)
    root = tmp_path / "dev"
    root.mkdir()
    device = root / "ttyACM0"
    device.symlink_to(os.ttyname(slave))
    usb = tmp_path / "sys" / "devices" / "1-1"
    interface = usb / "1-1:1.0"
    interface.mkdir(parents=True)
    (usb / "idVendor").write_text("1d6b\n")
    (usb / "idProduct").write_text("0104\n")
    (usb / "serial").write_text("m1lab-native-candidate\n")
    (interface / "bInterfaceNumber").write_text("00\n")
    sysfs = tmp_path / "sys" / "class" / "tty" / device.name
    sysfs.mkdir(parents=True)
    (sysfs / "device").symlink_to(interface, target_is_directory=True)
    real_open = os.open
    opens = []

    def open_fixture(path, flags, *args, **kwargs):
        if Path(path) == device:
            assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
            opens.append(path)
            return real_open(os.ttyname(slave), flags, *args, **kwargs)
        return real_open(path, flags, *args, **kwargs)

    # Production opens the direct path with O_NOFOLLOW. The synthetic ttyACM
    # symlink is mapped to the PTY only at that exact os.open call.
    monkeypatch.setattr(os, "open", open_fixture)
    transport = NativeUsbTransport(
        device, expected_usb_topology="1-1",
        sysfs_root=sysfs.parent, device_root=root,
    )
    try:
        yield transport, master, slave, usb, interface, opens, original_settings
    finally:
        os.close(master)
        os.close(slave)


def _read_line(fd: int) -> bytes:
    received = bytearray()
    deadline = time.monotonic() + 2
    while b"\n" not in received:
        assert select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]
        received += os.read(fd, 4096)
    return bytes(received)


def test_one_launch_and_complete_receipt_use_same_owned_tty(captured, channel):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    transport, master, slave, _usb, _interface, opens, original_settings = channel
    seen = []

    def target():
        seen.append(_read_line(master))
        remaining = memoryview(stream)
        while remaining:
            assert select.select([], [master], [], 2)[1]
            remaining = remaining[os.write(master, remaining):]

    with transport:
        worker = Thread(target=target)
        worker.start()
        receipt = transport.capture(launch, image)
        worker.join(timeout=3)
        assert not worker.is_alive()
        assert receipt.capture.status == "complete"
        assert receipt.raw_stream == stream
        assert receipt.stop_reason == "terminal"
        assert receipt.terminal_received_before_deadline is True
        with pytest.raises(NativeUsbError, match="already used"):
            transport.capture(launch, image)
    assert seen == [encode_native_manifest(launch) + b"\n"]
    assert len(opens) == 1
    assert termios.tcgetattr(slave) == original_settings


@pytest.mark.parametrize(
    ("field", "value"),
    [("idProduct", "0000\n"), ("serial", "other\n")],
)
def test_wrong_public_usb_binding_refuses_open(channel, field, value):
    transport, _master, _slave, usb, _interface, opens, _settings = channel
    (usb / field).write_text(value)
    with pytest.raises(NativeUsbError, match="differs"):
        transport.__enter__()
    assert opens == []


def test_binding_change_after_open_refuses_channel(channel, monkeypatch):
    transport, _master, _slave, usb, _interface, opens, _settings = channel
    real_open = os.open

    def change_after_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if Path(path) == transport.device:
            (usb / "idProduct").write_text("0000\n")
        return fd

    monkeypatch.setattr(os, "open", change_after_open)
    with pytest.raises(NativeUsbError, match="product ID"):
        transport.__enter__()
    assert len(opens) == 1


def test_receive_deadline_keeps_partial_evidence_and_never_resends(captured, channel):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    transport, master, _slave, _usb, _interface, _opens, _settings = channel
    short_launch = launch.model_copy(update={
        "deadline": datetime.now(timezone.utc) + timedelta(milliseconds=350),
    })
    seen = []

    def target():
        seen.append(_read_line(master))
        os.write(master, b"\x00\x00")

    with transport:
        worker = Thread(target=target)
        worker.start()
        receipt = transport.capture(short_launch, image)
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert receipt.capture.status == "unknown"
        assert receipt.raw_stream == b"\x00\x00"
        assert receipt.stop_reason == "deadline"
        with pytest.raises(NativeUsbError, match="already used"):
            transport.capture(short_launch, image)
    assert len(seen) == 1


def test_caller_capture_bounds_wire_bytes_without_changing_signed_launch(captured, channel):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    transport, master, _slave, _usb, _interface, _opens, _settings = channel
    seen = []

    def target():
        seen.append(_read_line(master))
        os.write(master, stream[:40])

    with transport:
        worker = Thread(target=target)
        worker.start()
        receipt = transport.capture(
            launch, image, deadline_monotonic=time.monotonic() + 1,
            max_stream_bytes=17,
        )
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert receipt.raw_stream == stream[:17]
    assert receipt.stop_reason == "stream_limit"
    assert seen == [encode_native_manifest(launch) + b"\n"]


def test_partial_send_failure_is_ambiguous_and_never_retried(captured, channel, monkeypatch):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    transport, master, _slave, _usb, _interface, _opens, _settings = channel
    import m1lab.adapters.native_usb as native_usb

    def fail_after_prefix(fd, _payload, _deadline):
        os.write(fd, b"{")
        raise TimeoutError("synthetic send expiry")

    monkeypatch.setattr(native_usb, "_write_all", fail_after_prefix)
    with transport:
        with pytest.raises(NativeUsbError, match="ambiguously; never retry"):
            transport.capture(launch, image)
        assert select.select([master], [], [], 1)[0]
        assert os.read(master, 1) == b"{"
        with pytest.raises(NativeUsbError, match="already used"):
            transport.capture(launch, image)
