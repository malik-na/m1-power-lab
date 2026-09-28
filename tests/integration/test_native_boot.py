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
    (udc / "synthetic-udc/state").write_text("not attached\n")
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
        elif path == gadget / "configs/c.1":
            original_mkdir(path / "strings")
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
    original_write_text = original_path.write_text
    configuration_at_bind = []

    def write_text(path, value, *args, **kwargs):
        if path == gadget / "UDC":
            configuration_at_bind.append(
                (gadget / "configs/c.1/strings/0x409/configuration").read_text()
            )
        return original_write_text(path, value, *args, **kwargs)

    monkeypatch.setattr(original_path, "write_text", write_text)
    stages = []
    assert native_boot._configure_gadget(time.monotonic() + 1, stages.append) == channel
    assert (gadget / "configs/c.1/acm.usb0").readlink() == gadget / "functions/acm.usb0"
    assert stages[-2:] == ["acm_bind", "tty_wait"]
    assert configuration_at_bind == ["M1Lab diag:v1:acm_bind:not_attached\n"]
    assert (gadget / "strings/0x409/product").read_text() == "M1Lab native candidate\n"
    assert (gadget / "strings/0x409/serialnumber").read_text() == "m1lab-native-candidate\n"


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


@pytest.fixture
def configuration_diagnostic(tmp_path):
    configuration = tmp_path / "configs/c.1"
    (configuration / "strings").mkdir(parents=True)
    controller = tmp_path / "udc/controller"
    controller.mkdir(parents=True)
    (controller / "state").write_text("address\n")
    diagnostic = native_boot._ConfigurationDiagnostic()
    diagnostic.update("python_entry")  # No attribute exists before preparation.
    diagnostic.update("acm_bind")
    diagnostic.prepare(configuration, controller)
    return diagnostic, controller


def test_configuration_diagnostic_updates_only_fixed_stages_and_states(configuration_diagnostic):
    diagnostic, controller = configuration_diagnostic
    assert diagnostic.path.read_text() == "M1Lab diag:v1:acm_bind:address\n"
    for stage in ("tty_wait", "launch_wait", "launch_received", "capture", "capture_done"):
        (controller / "state").write_text("configured\n")
        diagnostic.update(stage)
        encoded = diagnostic.path.read_bytes()
        assert encoded == f"M1Lab diag:v1:{stage}:configured\n".encode("ascii")
        assert len(encoded.rstrip()) <= 126
    before = diagnostic.path.read_bytes()
    diagnostic.update("untrusted private stage")
    assert diagnostic.path.read_bytes() == before
    (controller / "state").write_text("private unexpected controller data" * 5)
    diagnostic.update("launch_wait")
    assert diagnostic.path.read_text() == "M1Lab diag:v1:launch_wait:unknown\n"


@pytest.mark.parametrize("error,kind", [
    (TimeoutError("private detail"), "TimeoutError"),
    (PermissionError("private detail"), "OSError"),
    (ValueError("private detail"), "ValueError"),
    (KeyError("private detail"), "Exception"),
])
def test_configuration_failure_reports_fixed_type_without_error_text(configuration_diagnostic, error, kind):
    diagnostic, _controller = configuration_diagnostic
    diagnostic.update("capture", error)
    assert diagnostic.path.read_text() == f"M1Lab diag:v1:fail:capture:{kind}:address\n"
    assert len(diagnostic.path.read_bytes().rstrip()) <= 126
    diagnostic.update("capture_done")
    assert diagnostic.path.read_text() == "M1Lab diag:v1:capture_done:address\n"


def test_configuration_io_failures_are_best_effort_and_do_not_recreate_attribute(configuration_diagnostic, monkeypatch):
    diagnostic, controller = configuration_diagnostic
    diagnostic.path.unlink()
    diagnostic.update("launch_wait", ValueError("original failure"))
    assert not diagnostic.path.exists()
    monkeypatch.setattr(native_boot.os, "open", lambda *_a, **_k: (_ for _ in ()).throw(OSError("denied")))
    diagnostic.update("capture_done")
    diagnostic.update("capture", ValueError("original failure"))
    unavailable = native_boot._ConfigurationDiagnostic()
    unavailable.prepare(controller / "absent/configuration", controller)
    unavailable.update("tty_wait")


@pytest.mark.parametrize("diagnostic_fails", [False, True])
def test_launch_diagnostic_refresh_preserves_original_deadline(monkeypatch, diagnostic_fails):
    now = [0.0]
    waits = []
    refreshes = []
    monkeypatch.setattr(native_boot.time, "monotonic", lambda: now[0])

    def select(_read, _write, _error, timeout):
        waits.append(timeout)
        now[0] += timeout
        return [], [], []

    def refresh():
        refreshes.append(now[0])
        if diagnostic_fails:
            raise OSError("synthetic diagnostic unavailable")

    monkeypatch.setattr(native_boot.select, "select", select)
    with pytest.raises(TimeoutError, match="startup deadline"):
        native_boot._launch_line(12345, 2.5, on_wait=refresh)
    assert waits == [1, 1, 0.5]
    assert refreshes == [0.0, 1.0, 2.0]
    assert now[0] == 2.5


def test_failed_launch_diagnostic_does_not_mask_received_launch():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"{}\n")

        def unavailable():
            raise OSError("diagnostic unavailable")

        assert native_boot._launch_line(read_fd, time.monotonic() + 1, on_wait=unavailable) == b"{}"
    finally:
        os.close(read_fd)
        os.close(write_fd)
