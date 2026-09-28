#!/usr/bin/env python3
"""One RAM-only USB ACM capture; no interactive command or disk interface."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
import errno
import hashlib
import os
from pathlib import Path
import select
import stat
import subprocess
import termios
import time
import tty


BOOT_SECONDS = 150
MAX_LAUNCH_BYTES = 256 * 1024
GADGET = Path("/sys/kernel/config/usb_gadget/m1lab")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
IMAGE_CONFIG = Path("/etc/m1lab/image-config.json")
MAX_IMAGE_CONFIG_BYTES = 256 * 1024
CONSOLE = Path("/dev/tty0")
_STAGE_CODES = {stage: index for index, stage in enumerate((
    "python_entry", "module_phy_apple_atc", "module_tps6598x", "module_dwc3_apple",
    "module_libcomposite", "module_usb_f_acm", "configfs_mount", "udc_wait",
    "acm_bind", "tty_wait", "launch_wait", "launch_received", "capture", "capture_done",
))}
_DIAGNOSTIC_STAGES = frozenset({
    "acm_bind", "tty_wait", "launch_wait", "launch_received", "capture", "capture_done",
})
_UDC_STATES = {
    value: value.replace(" ", "_") for value in (
        "not attached", "attached", "powered", "reconnecting", "unauthenticated",
        "default", "address", "configured", "suspended",
    )
}
_DIAGNOSTIC_ERRORS = (
    TimeoutError, ValueError, OSError, ImportError, RuntimeError, AssertionError, TypeError,
)
_STATE_CODES = {"unknown": 0, **{state: index for index, state in enumerate(_UDC_STATES.values(), 1)}}
_DIGITS = (
    ("111", "101", "101", "101", "111"),
    ("010", "110", "010", "010", "111"),
    ("111", "001", "111", "100", "111"),
    ("111", "001", "111", "001", "111"),
    ("101", "101", "111", "001", "001"),
    ("111", "100", "111", "001", "111"),
    ("111", "100", "111", "101", "111"),
    ("111", "001", "001", "001", "001"),
    ("111", "101", "111", "101", "111"),
    ("111", "101", "111", "001", "111"),
)


def _error_kind(error: Exception | None) -> str:
    if error is None:
        return "None"
    return next((kind.__name__ for kind in _DIAGNOSTIC_ERRORS
                 if isinstance(error, kind)), "Exception")


def _console_overlay(stage: str, state: str, error: Exception | None = None) -> None:
    """One bounded best-effort write to the visible VT, never the result channel."""
    if stage not in _STAGE_CODES:
        return
    state = state if state in _STATE_CODES else "unknown"
    kind = _error_kind(error)
    error_code = (("None", *[item.__name__ for item in _DIAGNOSTIC_ERRORS], "Exception").index(kind))
    digits = f"{_STAGE_CODES[stage]:02d}{error_code}{_STATE_CODES[state]}"
    lines = ["M1LAB DIAG - STAGE / ERROR / USB", "       STAGE                ERROR          USB"]
    for row in range(5):
        parts = ["".join("###" if pixel == "1" else "   " for pixel in _DIGITS[int(digit)][row])
                 for digit in digits]
        line = parts[0] + "  " + parts[1] + "     " + parts[2] + "     " + parts[3]
        lines.extend((line, line))
    lines.extend((f"S{digits[:2]} {stage} E{error_code} {kind} U{digits[3]} {state}",
                  "DIAGNOSTIC ONLY - NOT SAMPLES OR SUCCESS"))
    # Save/restore cursor and attributes. Do not clear the screen, change the
    # scrolling region, or suppress kernel messages; redraw only these rows.
    payload = ("\x1b7\x1b[0;37;40m" + "".join(
        f"\x1b[{row};1H{line.ljust(64)}" for row, line in enumerate(lines, 1)
    ) + "\x1b8").encode("ascii")
    try:
        fd = os.open(CONSOLE, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK
                     | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev), os.minor(info.st_rdev)) != (4, 0):
                return
            os.write(fd, payload)  # No retry or drain if the VT cannot accept it.
        finally:
            os.close(fd)
    except OSError:
        pass


class _ConfigurationDiagnostic:
    """Experimental iConfiguration hint; never identity or sample evidence."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.controller: Path | None = None
        self.state = "unknown"

    def _value(self, stage: str, error: Exception | None = None) -> str:
        state = "unknown"
        if self.controller is not None:
            try:
                with (self.controller / "state").open("rb") as source:
                    raw = source.read(65)
                if len(raw) <= 64:
                    state = _UDC_STATES.get(raw.decode("ascii").strip(), "unknown")
            except (OSError, UnicodeError):
                pass
        self.state = state
        if error is None:
            return f"M1Lab diag:v1:{stage}:{state}"
        return f"M1Lab diag:v1:fail:{stage}:{_error_kind(error)}:{state}"

    def prepare(self, configuration: Path, controller: Path) -> None:
        self.controller = controller
        self.path = configuration / "strings/0x409/configuration"
        try:
            self.path.parent.mkdir()
            # Nonempty before bind reserves iConfiguration. Keep the product
            # and serial labels unchanged for the existing capture transport.
            value = self._value("acm_bind") + "\n"
            _console_overlay("acm_bind", self.state)
            self.path.write_text(value, encoding="ascii")
        except OSError:
            pass

    def update(self, stage: str, error: Exception | None = None) -> None:
        if stage not in _STAGE_CODES:
            return
        # First show the current stage with cached state, even if the next
        # sysfs read or configuration-string write blocks in a kernel driver.
        _console_overlay(stage, self.state, error)
        if self.path is None or stage not in _DIAGNOSTIC_STAGES:
            return
        previous_state = self.state
        value = self._value(stage, error).encode("ascii") + b"\n"
        if self.state != previous_state:
            _console_overlay(stage, self.state, error)
        try:
            # Open only the existing configfs attribute; do not recreate it.
            fd = os.open(self.path, os.O_WRONLY | os.O_TRUNC | os.O_CLOEXEC)
            try:
                os.write(fd, value)
            finally:
                os.close(fd)
        except OSError:
            pass  # Diagnostics must not mask a capture or its original failure.


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("native startup deadline expired")
    return remaining


def _command(deadline: float, *args: str) -> None:
    subprocess.run(args, check=True, timeout=min(10, _remaining(deadline)))


def _launch_line(
    fd: int, deadline: float, *, on_wait: Callable[[], None] | None = None,
) -> bytes:
    """Receive exactly one bounded JSON line from the exclusive host owner."""
    content = bytearray()
    while len(content) <= MAX_LAUNCH_BYTES:
        remaining = _remaining(deadline)
        if on_wait is not None:
            try:
                on_wait()
            except OSError:
                pass
        timeout = min(1, _remaining(deadline)) if on_wait is not None else remaining
        if not select.select([fd], [], [], timeout)[0]:
            if on_wait is not None:
                continue  # Refresh diagnostics without extending the deadline.
            raise TimeoutError("no native launch received")
        try:
            chunk = os.read(fd, min(4096, MAX_LAUNCH_BYTES + 1 - len(content)))
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EIO) or content:
                raise
            time.sleep(min(0.05, _remaining(deadline)))
            continue
        if not chunk:
            if content:
                raise OSError("native channel closed during launch")
            time.sleep(min(0.05, _remaining(deadline)))
            continue
        content.extend(chunk)
        if b"\n" in content:
            if not content.endswith(b"\n") or content.count(b"\n") != 1:
                raise ValueError("native launch must be one JSON line")
            if len(content) > MAX_LAUNCH_BYTES:
                break
            return bytes(content[:-1])
    raise ValueError("native launch exceeds size bound")


def _configure_gadget(
    deadline: float, mark: Callable[[str], None],
    diagnostic: _ConfigurationDiagnostic | None = None,
) -> Path:
    diagnostic = diagnostic if diagnostic is not None else _ConfigurationDiagnostic()
    for module in ("phy_apple_atc", "tps6598x", "dwc3_apple", "libcomposite", "usb_f_acm"):
        mark(f"module_{module}")
        _command(deadline, "/usr/bin/modprobe", module)
    mark("configfs_mount")
    _command(deadline, "/usr/bin/busybox", "mount", "-t", "configfs", "configfs", "/sys/kernel/config")
    # The connected port must enter peripheral mode through the kernel's role
    # switch. Do not guess a port or force a controller role on this candidate.
    mark("udc_wait")
    while True:
        controllers = sorted(Path("/sys/class/udc").glob("*"))
        if len(controllers) > 1:
            raise ValueError("ambiguous native USB device controller")
        if controllers:
            controller = controllers[0]
            break
        time.sleep(min(0.1, _remaining(deadline)))
    mark("acm_bind")
    GADGET.mkdir()
    (GADGET / "idVendor").write_text("0x1d6b\n")
    (GADGET / "idProduct").write_text("0x0104\n")
    strings = GADGET / "strings/0x409"
    strings.mkdir()
    (strings / "manufacturer").write_text("M1 Power Lab\n")
    (strings / "product").write_text("M1Lab native candidate\n")
    # Public label only, never used as physical identity evidence.
    (strings / "serialnumber").write_text("m1lab-native-candidate\n")
    configuration = GADGET / "configs/c.1"
    configuration.mkdir()
    diagnostic.prepare(configuration, controller)
    (configuration / "MaxPower").write_text("2\n")
    (GADGET / "functions/acm.usb0").mkdir()
    (configuration / "acm.usb0").symlink_to(GADGET / "functions/acm.usb0")
    (GADGET / "UDC").write_text(controller.name + "\n")
    mark("tty_wait")
    while not Path("/dev/ttyGS0").exists():
        time.sleep(min(0.1, _remaining(deadline)))
    return Path("/dev/ttyGS0")


def _observe_linux(launch: dict, collector: object) -> dict[str, str]:
    """Read fixed Linux boot facts and hash the exact packaged image config."""

    boot_fd = os.open(BOOT_ID, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        boot_id_bytes = os.read(boot_fd, 65)
    finally:
        os.close(boot_fd)
    try:
        boot_id = boot_id_bytes.decode("ascii").strip("\n")
    except UnicodeError as exc:
        raise ValueError("Linux boot ID is invalid") from exc
    config_fd = os.open(
        IMAGE_CONFIG,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        info = os.fstat(config_fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_IMAGE_CONFIG_BYTES:
            raise ValueError("packaged image configuration is not a bounded regular file")
        config = os.read(config_fd, MAX_IMAGE_CONFIG_BYTES + 1)
        if len(config) != info.st_size:
            raise ValueError("packaged image configuration changed while reading")
    finally:
        os.close(config_fd)
    observed = {
        "boot_id": boot_id,
        "kernel_release": os.uname().release,
        "configuration_sha256": hashlib.sha256(config).hexdigest(),
    }
    collector._validate_observed_linux(observed, launch)
    return observed


def main() -> int:
    deadline = time.monotonic() + BOOT_SECONDS
    fd = None
    stage = "python_entry"
    diagnostic = _ConfigurationDiagnostic()

    def mark(value: str) -> None:
        nonlocal stage
        stage = value
        print(f"M1Lab stage={value}", flush=True)
        diagnostic.update(value)

    try:
        mark("python_entry")
        channel = _configure_gadget(deadline, mark, diagnostic)
        fd = os.open(channel, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(fd, termios.TCSANOW)
        mark("launch_wait")
        raw = _launch_line(fd, deadline, on_wait=lambda: diagnostic.update(stage))
        mark("launch_received")
        launch_path = Path("/run/m1lab-launch.json")
        launch_path.write_bytes(raw)
        # -I excludes the script directory; load only this image's exact source.
        spec = importlib.util.spec_from_file_location("native_capture", Path(__file__).with_name("native_capture.py"))
        assert spec is not None and spec.loader is not None
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)
        launch = collector.load_launch(launch_path)
        # The immutable approval may expire later than this boot's window.
        # The collector stops at the earlier of its sample duration and that
        # expiry, so bound the requested duration here, not approval headroom.
        _check_capture_window(launch, deadline)
        observed_linux = _observe_linux(launch, collector)
        mark("capture")
        collector._emit(fd, launch, observed_linux=observed_linux)
        mark("capture_done")
        # Let queued result bytes reach the host before the reboot attempt.
        # No tcdrain: an absent host must not extend the finite window.
        time.sleep(min(2, _remaining(deadline)))
        return 0
    except Exception as exc:
        diagnostic.update(stage, exc)
        print(f"M1Lab failure stage={stage} type={type(exc).__name__}", flush=True)
        return 2
    finally:
        if fd is not None:
            os.close(fd)


def _check_capture_window(launch: dict, deadline: float) -> None:
    parameters = launch["parameters"]
    seconds = parameters["sample_count"] * parameters["sample_period_ms"] / 1000
    if seconds > _remaining(deadline):
        raise ValueError("capture exceeds native window")


if __name__ == "__main__":
    raise SystemExit(main())
