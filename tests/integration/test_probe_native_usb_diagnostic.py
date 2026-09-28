"""Synthetic-only checks for the fixed unconfigured USB descriptor probe."""

from __future__ import annotations

import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "scripts/probe-native-usb-diagnostic.py"
SPEC = importlib.util.spec_from_file_location("native_usb_diagnostic", SOURCE)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def _device(root: Path, port: str, vendor: str, product: str, *, bus: int = 1, dev: int = 15) -> None:
    base = root / port
    base.mkdir(parents=True, exist_ok=True)
    for name, value in (("idVendor", vendor), ("idProduct", product),
                        ("busnum", str(bus)), ("devnum", str(dev))):
        (base / name).write_text(value + "\n")


def _string(value: str) -> bytes:
    encoded = value.encode("utf-16-le")
    return bytes([len(encoded) + 2, 3]) + encoded


def test_fixed_usbfs_controls_only_read_device_and_product(monkeypatch):
    requests = []

    class FakeLibc:
        def ioctl(self, fd, command, pointer):
            control = ctypes.cast(pointer, ctypes.POINTER(probe.UsbControl)).contents
            requests.append((fd, command, control.request_type, control.request,
                             control.value, control.index, control.length, control.timeout))
            reply = {0x100: b"\x12\x01" + b"\x00" * 16,
                     0x200: b"\x09\x02\x4b\x00\x02\x01\x04\x80\x01",
                     0x300: b"\x04\x03\x09\x04",
                     0x302: _string(probe.PRODUCT),
                     0x303: _string(probe.SERIAL),
                     0x304: _string("M1Lab diag:v1:launch_wait:address")}[control.value]
            ctypes.memmove(control.data, reply, len(reply))
            return len(reply)

    monkeypatch.setattr(probe, "_libc", FakeLibc())
    for desc_type, index, length in ((1, 0, 18), (2, 0, 9), (3, 0, 4),
                                     (3, 2, 254), (3, 3, 254), (3, 4, 254)):
        assert probe.get_descriptor(7, desc_type, index, length)
    assert [(row[2], row[3], row[4], row[5], row[6], row[7]) for row in requests] == [
        (0x80, 6, 0x100, 0, 18, 250),
        (0x80, 6, 0x200, 0, 9, 250),
        (0x80, 6, 0x300, 0, 4, 250),
        (0x80, 6, 0x302, 0x409, 254, 250),
        (0x80, 6, 0x303, 0x409, 254, 250),
        (0x80, 6, 0x304, 0x409, 254, 250),
    ]
    assert all(row[1] == probe.USBDEVFS_CONTROL for row in requests)
    with pytest.raises(ValueError, match="allowlist"):
        probe.get_descriptor(7, 2, 0, 75)


@pytest.mark.parametrize("value", [probe.PRODUCT, probe.SERIAL,
                                     "M1Lab diag:v1:tty_wait:address"])
def test_string_descriptor_decoding(value):
    assert probe.decode_string(_string(value)) == value


@pytest.mark.parametrize("value", [
    "M1Lab diag:v1:tty_wait:address",
    "M1Lab diag:v1:fail:tty_wait:TimeoutError:address",
])
def test_diagnostic_accepts_only_target_enumerations(value):
    assert probe.validate_diagnostic(value) == value


@pytest.mark.parametrize("value", [
    "M1Lab diag:v1:other:address", "M1Lab diag:v1:tty_wait:other",
    "M1Lab diag:v1:fail:tty_wait:FileNotFoundError:address",
    "M1Lab diag:v1:tty_wait:address\nsecret",
])
def test_diagnostic_rejects_unknown_or_private_payload(value):
    with pytest.raises(ValueError, match="grammar"):
        probe.validate_diagnostic(value)


@pytest.mark.parametrize("raw", [
    b"\x04\x03x", b"\x04\x02x\x00", b"\x04\x03\xff\xd8",
])
def test_product_string_rejects_malformed_or_unscreened_content(raw):
    with pytest.raises((ValueError, UnicodeError)):
        probe.decode_string(raw)


def test_probe_rechecks_selected_port_and_usbfs_device(monkeypatch, tmp_path):
    sysfs = tmp_path / "sysfs"
    _device(sysfs, "1-2", *probe.NATIVE)
    device = bytearray(bytes.fromhex("12011002000000406b1d0401010701020301"))
    assert len(device) == 18
    observed = []
    monkeypatch.setattr(probe.os, "open", lambda path, flags: observed.append((path, flags)) or 77)
    monkeypatch.setattr(probe.os, "close", lambda fd: None)
    monkeypatch.setattr(probe.os, "fstat", lambda fd: SimpleNamespace(
        st_mode=stat.S_IFCHR, st_rdev=os.makedev(189, 14),
    ))

    def transfer(fd, kind, index, length):
        if kind == 1:
            return bytes(device)
        if kind == 2:
            return b"\x09\x02\x4b\x00\x02\x01\x04\x80\x01"
        if index == 0:
            return b"\x04\x03\x09\x04"
        if index == 2:
            return _string(probe.PRODUCT)
        if index == 3:
            return _string(probe.SERIAL)
        return _string("M1Lab diag:v1:launch_wait:address")

    result = probe.probe_native("1-2", sysfs, tmp_path / "usb", transfer)
    assert result["product"] == probe.PRODUCT
    assert result["diagnostic"].startswith("M1Lab diag:v1:")
    assert observed[0][0] == tmp_path / "usb/001/015"
    assert observed[0][1] & os.O_NOFOLLOW
    assert observed[0][1] & os.O_RDWR

    def changed(fd, kind, index, length):
        if kind == 1:
            _device(sysfs, "1-2", *probe.NATIVE, dev=16)
            return bytes(device)
        return transfer(fd, kind, index, length)

    with pytest.raises(probe.ProbeFailure, match="identity_changed_after"):
        probe.probe_native("1-2", sysfs, tmp_path / "usb", changed)

    _device(sysfs, "1-2", *probe.NATIVE, dev=15)

    def failed_device(fd, kind, index, length):
        raise OSError(errno.ETIMEDOUT, "synthetic control timeout")

    with pytest.raises(probe.ProbeFailure) as error:
        probe.probe_native("1-2", sysfs, tmp_path / "usb", failed_device)
    assert (error.value.stage, error.value.code, error.value.errno_value) == (
        "device", "control_request_failed", errno.ETIMEDOUT,
    )

    def missing_index(fd, kind, index, length):
        if kind == 2:
            return b"\x09\x02\x4b\x00\x02\x01\x00\x80\x01"
        return transfer(fd, kind, index, length)

    with pytest.raises(probe.ProbeFailure) as error:
        probe.probe_native("1-2", sysfs, tmp_path / "usb", missing_index)
    assert (error.value.stage, error.value.code) == (
        "configuration", "diagnostic_index_missing",
    )


def test_watch_exits_on_proxy_return_and_writes_private_bounded_jsonl(tmp_path):
    sysfs = tmp_path / "sysfs"
    _device(sysfs, "1-2", *probe.NATIVE)
    ticks = [0.0]
    calls = []

    def clock():
        return ticks[0]

    def sleep(seconds):
        ticks[0] += seconds
        _device(sysfs, "1-2", *probe.PROXY, dev=16)

    def fake_probe(port, root, devroot):
        calls.append(port)
        return {"diagnostic": "M1Lab diag:v1:launch_wait:address", "device_descriptor_hex": "1201"}

    output = tmp_path / "diagnostic.jsonl"
    outcome = probe.watch("1-2", output, 4, sysfs_root=sysfs,
                          device_root=tmp_path, monotonic=clock, sleep=sleep, probe=fake_probe)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert outcome == "proxy_at_port_after_native"
    assert calls == ["1-2"]
    assert [row["kind"] for row in rows] == ["header", "native", "proxy_at_port"]
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_size < probe.MAX_OUTPUT
    assert all("identity" not in row and "capture" not in row for row in rows)
    with pytest.raises(FileExistsError):
        probe.watch("1-2", output, 4, sysfs_root=sysfs)


def test_short_deadline_never_starts_six_control_requests(tmp_path):
    sysfs = tmp_path / "sysfs"
    _device(sysfs, "1-2", *probe.NATIVE)
    calls = []
    output = tmp_path / "short.jsonl"
    outcome = probe.watch("1-2", output, 1, sysfs_root=sysfs,
                          monotonic=lambda: 0.0, sleep=lambda _: None,
                          probe=lambda *args: calls.append(args))
    assert outcome == "deadline"
    assert calls == []
    assert [json.loads(line)["kind"] for line in output.read_text().splitlines()] == [
        "header", "native_probe_skipped_deadline",
    ]


def test_watch_records_fixed_probe_phase_without_arbitrary_error_text(tmp_path):
    sysfs = tmp_path / "sysfs"
    _device(sysfs, "1-2", *probe.NATIVE)
    clock = [0.0]

    def failed_probe(*_args):
        raise probe.ProbeFailure("device", "control_request_failed", errno.ETIMEDOUT)

    output = tmp_path / "phase.jsonl"
    probe.watch("1-2", output, 3, sysfs_root=sysfs,
                monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
                probe=failed_probe)
    errors = [json.loads(line) for line in output.read_text().splitlines()
              if json.loads(line)["kind"] == "probe_error"]
    assert len(errors) == 1
    assert errors[0]["stage"] == "device"
    assert errors[0]["error_code"] == "control_request_failed"
    assert errors[0]["errno"] == errno.ETIMEDOUT
    assert "synthetic control timeout" not in output.read_text()


@pytest.mark.parametrize("port,seconds", [("1-2/../3", 4), ("1-2", 481), ("1-2", 0)])
def test_watch_rejects_unbounded_or_nonconcrete_selection_before_output(tmp_path, port, seconds):
    output = tmp_path / "absent.jsonl"
    with pytest.raises(ValueError):
        probe.watch(port, output, seconds)
    assert not output.exists()


def test_output_bound_refuses_extra_record_without_partial_line(tmp_path):
    output = tmp_path / "output.jsonl"
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with pytest.raises(ValueError, match="output bound"):
            probe._append(fd, {"data": "x" * 400}, probe.MAX_OUTPUT - 100)
        assert output.stat().st_size == 0
    finally:
        os.close(fd)
