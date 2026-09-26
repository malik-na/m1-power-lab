"""Host pipe checks for the native image's one-launch reader."""

from __future__ import annotations

import importlib.util
import errno
import os
from pathlib import Path
import threading
import time

import pytest


_SOURCE = Path(__file__).resolve().parents[2] / "target" / "native_boot.py"
_SPEC = importlib.util.spec_from_file_location("m1lab_native_boot_test", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
native_boot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(native_boot)


def test_approval_headroom_does_not_extend_or_prevent_short_native_capture():
    launch = {
        "parameters": {"sample_count": 3, "sample_period_ms": 1000},
        "_remaining_deadline_seconds": 600,
    }
    native_boot._check_capture_window(launch, time.monotonic() + 149)
    with pytest.raises(ValueError, match="capture exceeds native window"):
        native_boot._check_capture_window(launch, time.monotonic() + 2)


def test_fragmented_one_line_launch_is_received_from_pipe():
    read_fd, write_fd = os.pipe()

    def send() -> None:
        try:
            for part in (b'{"schema_version":', b'"m1lab.native-launch.v1"', b'}\n'):
                os.write(write_fd, part)
                time.sleep(0.01)
        finally:
            os.close(write_fd)

    writer = threading.Thread(target=send)
    writer.start()
    try:
        assert native_boot._launch_line(read_fd, time.monotonic() + 1) == (
            b'{"schema_version":"m1lab.native-launch.v1"}'
        )
    finally:
        os.close(read_fd)
        writer.join(timeout=1)
    assert not writer.is_alive()


def test_partial_launch_then_eof_is_rejected():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b'{"schema_version":')
        os.close(write_fd)
        with pytest.raises(OSError, match="closed during launch"):
            native_boot._launch_line(read_fd, time.monotonic() + 1)
    finally:
        os.close(read_fd)


def test_empty_eof_waits_only_until_fixed_deadline():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            native_boot._launch_line(read_fd, started + 0.12)
    finally:
        os.close(read_fd)
    elapsed = time.monotonic() - started
    assert 0.10 <= elapsed < 0.75


def test_udc_timeout_identifies_stage_before_native_launch(monkeypatch, capsys):
    monkeypatch.setattr(native_boot, "_command", lambda *_args: None)
    monkeypatch.setattr(native_boot, "BOOT_SECONDS", 0.12)

    class NoUdc:
        def glob(self, _pattern):
            return iter(())

    original_path = native_boot.Path
    monkeypatch.setattr(
        native_boot, "Path",
        lambda path: NoUdc() if path == "/sys/class/udc" else original_path(path),
    )
    assert native_boot.main() == 2
    output = capsys.readouterr().out
    assert "M1Lab stage=udc_wait\n" in output
    assert "M1Lab failure stage=udc_wait type=TimeoutError\n" in output
    assert "launch_wait" not in output


def test_configfs_acm_link_resolves_function_from_process_cwd(monkeypatch, tmp_path):
    gadget = tmp_path / "sys/kernel/config/usb_gadget/m1lab"
    gadget.parent.mkdir(parents=True)
    udc = tmp_path / "sys/class/udc"
    (udc / "synthetic-udc").mkdir(parents=True)
    channel = tmp_path / "dev/ttyGS0"
    channel.parent.mkdir()
    channel.touch()
    monkeypatch.setattr(native_boot, "GADGET", gadget)
    monkeypatch.setattr(native_boot, "_command", lambda *_args: None)
    original_path = native_boot.Path
    original_mkdir = original_path.mkdir

    def configfs_mkdir(path, *args, **kwargs):
        result = original_mkdir(path, *args, **kwargs)
        if path == gadget:
            for directory in ("strings", "configs", "functions"):
                original_mkdir(gadget / directory)
        return result

    monkeypatch.setattr(original_path, "mkdir", configfs_mkdir)
    monkeypatch.setattr(
        native_boot, "Path",
        lambda path: udc if path == "/sys/class/udc" else (
            channel if path == "/dev/ttyGS0" else original_path(path)
        ),
    )
    original_symlink_to = original_path.symlink_to

    def configfs_symlink_to(link, target, *args, **kwargs):
        # Configfs resolves function targets from the process cwd, unlike a
        # regular filesystem symlink whose relative target uses the link parent.
        resolved = original_path(target).resolve()
        if resolved != gadget / "functions/acm.usb0" or not resolved.is_dir():
            raise FileNotFoundError(errno.ENOENT, "configfs function target", str(target))
        return original_symlink_to(link, target, *args, **kwargs)

    monkeypatch.setattr(original_path, "symlink_to", configfs_symlink_to)
    stages = []
    assert native_boot._configure_gadget(time.monotonic() + 1, stages.append) == channel
    assert (gadget / "configs/c.1/acm.usb0").readlink() == gadget / "functions/acm.usb0"
    assert stages[-2:] == ["acm_bind", "tty_wait"]


@pytest.mark.parametrize("wire", [b"{}\n{}\n", b"x" * 32 + b"\n"])
def test_multiple_or_oversized_launch_line_is_rejected(monkeypatch, wire):
    monkeypatch.setattr(native_boot, "MAX_LAUNCH_BYTES", 32)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, wire)
        os.close(write_fd)
        with pytest.raises(ValueError, match="one JSON line|size bound"):
            native_boot._launch_line(read_fd, time.monotonic() + 1)
    finally:
        os.close(read_fd)
