"""One candidate native capture over an exclusively owned USB ACM tty.

The caller holds the helper owner lock. USB labels here are public device
descriptors, not authenticated physical identity or dispatch qualification.
This transport never retries a launch or selects another device.
"""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import fcntl
import math
import os
from pathlib import Path
import re
import select
import stat
import termios
import time

from .native_harness import (
    NativeHarnessError,
    NativeImageManifest,
    NativeLaunchManifest,
    decode_native_launch_manifest,
    encode_native_manifest,
)
from .native_stream import (
    MAX_NATIVE_STREAM_BYTES, NativeStreamReceipt, receive_native_result_stream,
)


_TTY_NAME = re.compile(r"ttyACM[0-9]+\Z")
_TOPOLOGY = re.compile(r"[0-9]+-[0-9]+(?:\.[0-9]+)*\Z")
_MAX_LAUNCH_LINE_BYTES = 256 * 1024


class NativeUsbError(RuntimeError):
    """A candidate channel failed; target execution state is not inferred."""


class NativeUsbTransport:
    """Own one fixed ACM tty for one launch and result receipt."""

    def __init__(
        self,
        device: Path,
        *,
        expected_usb_topology: str,
        sysfs_root: Path = Path("/sys/class/tty"),
        device_root: Path = Path("/dev"),
    ) -> None:
        self.device = Path(device)
        self.device_root = Path(device_root)
        self.sysfs_root = Path(sysfs_root)
        if self.device.parent != self.device_root or not _TTY_NAME.fullmatch(self.device.name):
            raise ValueError("device must be a direct ttyACM path in the device root")
        if not _TOPOLOGY.fullmatch(expected_usb_topology):
            raise ValueError("expected USB topology must be a concrete bus-port path")
        self.expected_usb_topology = expected_usb_topology
        self._fd: int | None = None
        self._original_termios: list[object] | None = None
        self._attempted = False

    def __enter__(self) -> NativeUsbTransport:
        if self._fd is not None or self._attempted:
            raise NativeUsbError("native candidate channel is already open or used")
        self._verify_usb_binding()
        flags = os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.device, flags)
        original = None
        try:
            if not os.isatty(fd):
                raise NativeUsbError("selected device is not a tty")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(fd, termios.TIOCEXCL)
            original = termios.tcgetattr(fd)
            settings = termios.tcgetattr(fd)
            settings[0] = 0
            settings[1] = 0
            settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            settings[3] = 0
            settings[4] = termios.B115200
            settings[5] = termios.B115200
            settings[6][termios.VMIN] = 0
            settings[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            self._verify_usb_binding()
            self._original_termios = original
            self._fd = fd
            return self
        except BaseException:
            if original is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
                except OSError:
                    pass
            try:
                fcntl.ioctl(fd, termios.TIOCNXCL)
            except OSError:
                pass
            os.close(fd)
            raise

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        fd, self._fd = self._fd, None
        self._attempted = True
        if fd is None:
            return
        try:
            if self._original_termios is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSANOW, self._original_termios)
                except OSError:
                    pass  # A disconnected USB tty may not accept cleanup.
            try:
                fcntl.ioctl(fd, termios.TIOCNXCL)
            except OSError:
                pass
        finally:
            self._original_termios = None
            os.close(fd)

    def capture(
        self, launch: NativeLaunchManifest, image: NativeImageManifest,
        *, deadline_monotonic: float | None = None,
        max_stream_bytes: int | None = None,
    ) -> NativeStreamReceipt:
        """Send one validated launch and receive on the same bounded channel."""

        if self._fd is None or self._attempted:
            raise NativeUsbError("native candidate channel is closed or already used")
        encoded = encode_native_manifest(launch)
        launch = decode_native_launch_manifest(encoded)
        launch.validate_against_image(image)
        line = encoded + b"\n"
        if len(line) > _MAX_LAUNCH_LINE_BYTES:
            raise NativeHarnessError("native launch line exceeds target bound")
        if (deadline_monotonic is not None
                and (type(deadline_monotonic) not in (int, float)
                     or not math.isfinite(deadline_monotonic))):
            raise ValueError("native capture deadline must be a finite monotonic timestamp")
        if max_stream_bytes is None:
            max_stream_bytes = MAX_NATIVE_STREAM_BYTES
        if type(max_stream_bytes) is not int or not 1 <= max_stream_bytes <= MAX_NATIVE_STREAM_BYTES:
            raise ValueError("native stream byte limit is invalid")
        self._attempted = True
        self._verify_usb_binding()
        deadline = time.monotonic() + (launch.deadline - datetime.now(timezone.utc)).total_seconds()
        if deadline_monotonic is not None:
            deadline = min(deadline, deadline_monotonic)
        try:
            _write_all(self._fd, line, deadline)
        except (OSError, TimeoutError) as exc:
            raise NativeUsbError("native launch send ended ambiguously; never retry") from exc
        return receive_native_result_stream(
            self._fd, launch, image, deadline_monotonic=deadline,
            max_stream_bytes=max_stream_bytes,
        )

    def _verify_usb_binding(self) -> None:
        try:
            info = self.device.stat()
            if not stat.S_ISCHR(info.st_mode):
                raise NativeUsbError("selected path is not a character device")
            if self.device_root == Path("/dev") and self.device.is_symlink():
                raise NativeUsbError("selected tty path must not be a symlink")
            interface = (self.sysfs_root / self.device.name / "device").resolve(strict=True)
            usb_device = interface.parent
            if interface.name != f"{self.expected_usb_topology}:1.0":
                raise NativeUsbError("USB interface topology differs from expected")
            if usb_device.name != self.expected_usb_topology:
                raise NativeUsbError("USB device topology differs from expected")
            if _read_sysfs(interface / "bInterfaceNumber") != "00":
                raise NativeUsbError("USB interface is not interface 00")
            if _read_sysfs(usb_device / "idVendor").lower() != "1d6b":
                raise NativeUsbError("USB vendor ID differs from candidate")
            if _read_sysfs(usb_device / "idProduct").lower() != "0104":
                raise NativeUsbError("USB product ID differs from candidate")
            if _read_sysfs(usb_device / "serial") != "m1lab-native-candidate":
                raise NativeUsbError("USB public serial differs from candidate")
        except (OSError, UnicodeError) as exc:
            raise NativeUsbError("USB binding files are unavailable") from exc


def _read_sysfs(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(257)
    if not raw or len(raw) > 256:
        raise NativeUsbError("USB binding field is empty or exceeds its bound")
    return raw.decode("utf-8").strip()


def _write_all(fd: int, payload: bytes, deadline: float) -> None:
    remaining = memoryview(payload)
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("native launch send deadline expired")
        try:
            _, writable, _ = select.select([], [fd], [], timeout)
            if not writable:
                raise TimeoutError("native launch channel did not become writable")
            written = os.write(fd, remaining)
        except (InterruptedError, BlockingIOError):
            continue
        if written <= 0:
            raise OSError(errno.EPIPE, "native launch channel closed")
        remaining = remaining[written:]
