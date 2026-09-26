"""Inspect-only physical m1n1 backend for a single owned USB proxy connection.

This module does not qualify dispatch, boot epochs, or recovery. A caller must
hold the helper owner lock for the whole context lifetime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import stat
import time
from typing import Callable

from .hardware import HardwareDispatch, HardwareUnavailable, TargetSnapshot
from .m1n1_transport import M1N1ReadOnlyTransport, ProxyIdentity


_TTY_NAME = re.compile(r"ttyACM[0-9]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_CHIP = 0x8103
_MAX_INSPECTION_SECONDS = 5.0


class M1N1Observer:
    """Own a verified tty and expose only bounded observations."""

    def __init__(
        self,
        device: Path,
        *,
        expected_usb_topology: str,
        expected_serial_sha256: str,
        sysfs_root: Path = Path("/sys/class/tty"),
        device_root: Path = Path("/dev"),
        transport_factory: Callable[[Path], M1N1ReadOnlyTransport] = M1N1ReadOnlyTransport,
    ) -> None:
        self.device = Path(device)
        self.device_root = Path(device_root)
        self.sysfs_root = Path(sysfs_root)
        if self.device.parent != self.device_root or not _TTY_NAME.fullmatch(self.device.name):
            raise ValueError("device must be a direct ttyACM path in the device root")
        if not re.fullmatch(r"[0-9]+-[0-9]+(?:\.[0-9]+)*", expected_usb_topology):
            raise ValueError("expected USB topology must be a concrete bus-port path")
        if not _SHA256.fullmatch(expected_serial_sha256):
            raise ValueError("expected serial SHA-256 must be 64 lowercase hex characters")
        self.expected_usb_topology = expected_usb_topology
        self.expected_serial_sha256 = expected_serial_sha256
        self._transport_factory = transport_factory
        self._transport: M1N1ReadOnlyTransport | None = None
        self._invalid = False
        self.last_identity: ProxyIdentity | None = None

    def __enter__(self) -> M1N1Observer:
        if self._transport is not None or self._invalid:
            raise HardwareUnavailable("observer is already open or invalidated")
        self._verify_usb_identity()
        try:
            transport = self._transport_factory(self.device)
            self._transport = transport.__enter__()
            self._verify_usb_identity()
        except Exception:
            self._invalidate()
            raise
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self._invalidate()

    def inspect(self) -> TargetSnapshot:
        if self._transport is None or self._invalid:
            return self._unavailable("observer has no owned connection")
        try:
            self._verify_usb_identity()
            identity = self._transport.observe(
                deadline_monotonic=time.monotonic() + _MAX_INSPECTION_SECONDS
            )
            self._verify_usb_identity()
            if identity.chip_id != _EXPECTED_CHIP:
                raise HardwareUnavailable("observed chip ID differs from expected M1")
            self.last_identity = identity
            return TargetSnapshot(
                adapter="m1n1-read-only-observer",
                available=True,
                qualified=False,
                mode="proxy",
                target_id=f"m1n1-serial-sha256:{self.expected_serial_sha256}",
                boot_epoch=None,
                capabilities=(),
                observed_at=datetime.now(timezone.utc),
                message="Five fixed read-only m1n1 proxy requests completed; dispatch and recovery remain unqualified.",
            )
        except Exception as exc:
            self._invalidate()
            return self._unavailable(f"bounded m1n1 observation failed: {type(exc).__name__}")

    def execute(self, dispatch: HardwareDispatch):
        del dispatch
        raise HardwareUnavailable("read-only observer never dispatches target operations")

    def _verify_usb_identity(self) -> None:
        try:
            info = self.device.stat()
            if not stat.S_ISCHR(info.st_mode):
                raise HardwareUnavailable("selected path is not a character device")
            if self.device_root == Path("/dev") and self.device.is_symlink():
                raise HardwareUnavailable("selected tty path must not be a symlink")
            interface = (self.sysfs_root / self.device.name / "device").resolve(strict=True)
            usb_device = interface.parent
            if interface.name != f"{self.expected_usb_topology}:1.0":
                raise HardwareUnavailable("USB interface topology differs from expected")
            if usb_device.name != self.expected_usb_topology:
                raise HardwareUnavailable("USB device topology differs from expected")
            if _read_sysfs(interface / "bInterfaceNumber") != "00":
                raise HardwareUnavailable("USB interface is not interface 00")
            if _read_sysfs(usb_device / "idVendor").lower() != "1209":
                raise HardwareUnavailable("USB vendor ID differs from expected")
            if _read_sysfs(usb_device / "idProduct").lower() != "316d":
                raise HardwareUnavailable("USB product ID differs from expected")
            serial = _read_sysfs(usb_device / "serial")
            digest = hashlib.sha256(serial.encode("utf-8")).hexdigest()
            if digest != self.expected_serial_sha256:
                raise HardwareUnavailable("USB serial digest differs from expected")
        except (OSError, UnicodeError) as exc:
            raise HardwareUnavailable("USB identity files are unavailable") from exc

    def _invalidate(self) -> None:
        transport, self._transport = self._transport, None
        self._invalid = True
        self.last_identity = None
        if transport is not None:
            transport.__exit__(None, None, None)

    @staticmethod
    def _unavailable(reason: str) -> TargetSnapshot:
        return TargetSnapshot(
            adapter="m1n1-read-only-observer", available=False, qualified=False,
            mode="disconnected", target_id=None, boot_epoch=None, capabilities=(),
            observed_at=datetime.now(timezone.utc), message=reason,
        )


def _read_sysfs(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(257)
    if not raw or len(raw) > 256:
        raise HardwareUnavailable("USB identity field is empty or exceeds its bound")
    return raw.decode("utf-8").strip()
