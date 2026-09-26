"""Narrow m1n1 v1.6.1 USB proxy observation transport.

No m1n1 setup module is imported. This exposes no target writes, arbitrary
proxy requests, exit, reboot, memory reads, or boot transition operations.
The caller supplies one monotonic deadline for the complete observation.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import select
import struct
import termios
import time


_UART_NOP = 0x00AA55FF
_UART_PROXY = 0x01AA55FF
_PROXY_NOP = 0x000
_GET_BOOTARGS = 0x003
_GET_BASE = 0x004
_GET_CHIPID = 0x013
_REPLY_PREFIX = b"\xff\x55\xaa"
_MAX_PREFIX_BYTES = 4096


class M1N1TransportError(RuntimeError):
    """A bounded proxy observation failed; target state is not inferred."""


@dataclass(frozen=True, slots=True)
class ProxyIdentity:
    chip_id: int
    base: int
    bootargs_address: int


def _checksum(data: bytes) -> int:
    value = 0xDEADBEEF
    for byte in data:
        value = (value * 31337 + (byte ^ 0x5A)) & 0xFFFFFFFF
    return value ^ 0xADDEDBAD


def _frame(command: int, payload: bytes = b"") -> bytes:
    if len(payload) > 56:
        raise ValueError("m1n1 command payload exceeds 56 bytes")
    body = struct.pack("<I", command) + payload.ljust(56, b"\0")
    return body + struct.pack("<I", _checksum(body))


class M1N1ReadOnlyTransport:
    """Own one tty and perform only fixed, read-only identity RPCs.

    TIOCEXCL prevents later opens by ordinary users; it cannot revoke a file
    descriptor opened earlier. The caller must establish existing port ownership.
    """

    def __init__(self, device: str | Path):
        self.device = Path(device)
        self._fd: int | None = None
        self._original_termios: list[object] | None = None

    def __enter__(self) -> M1N1ReadOnlyTransport:
        if self._fd is not None:
            raise M1N1TransportError("serial device is already open")
        flags = os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.device, flags)
        try:
            if not os.isatty(fd):
                raise M1N1TransportError("selected device is not a tty")
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
            self._original_termios = original
            self._fd = fd
            return self
        except BaseException:
            try:
                fcntl.ioctl(fd, termios.TIOCNXCL)
            except OSError:
                pass
            os.close(fd)
            raise

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                if self._original_termios is not None:
                    try:
                        termios.tcsetattr(fd, termios.TCSANOW, self._original_termios)
                    except OSError:
                        pass  # The USB tty can disappear before cleanup.
                try:
                    fcntl.ioctl(fd, termios.TIOCNXCL)
                except OSError:
                    pass
            finally:
                self._original_termios = None
                os.close(fd)

    def observe(self, *, deadline_monotonic: float) -> ProxyIdentity:
        """Use one overall deadline for NOP and three identity queries."""
        if self._fd is None:
            raise M1N1TransportError("serial device is closed")
        if not 0 < deadline_monotonic < float("inf"):
            raise ValueError("a finite monotonic deadline is required")
        nop = self._exchange(_UART_NOP, struct.pack("<Q", 0), deadline_monotonic)
        if struct.unpack_from("<Q", nop)[0] != 0:
            raise M1N1TransportError("target enabled an unexpected proxy feature")
        self._proxy(_PROXY_NOP, deadline_monotonic)
        chip = self._proxy(_GET_CHIPID, deadline_monotonic)
        base = self._proxy(_GET_BASE, deadline_monotonic)
        bootargs = self._proxy(_GET_BOOTARGS, deadline_monotonic)
        return ProxyIdentity(chip_id=chip, base=base, bootargs_address=bootargs)

    def _proxy(self, opcode: int, deadline: float) -> int:
        # The opcode is supplied only by fixed calls in observe().
        payload = self._exchange(_UART_PROXY, struct.pack("<Q", opcode), deadline)
        reply_opcode, status, value = struct.unpack_from("<QqQ", payload)
        if reply_opcode != opcode or status != 0:
            raise M1N1TransportError("proxy opcode or status mismatch")
        return value

    def _exchange(self, command: int, payload: bytes, deadline: float) -> bytes:
        self._write_all(_frame(command, payload), deadline)
        prefix = bytearray()
        scanned = 0
        while True:
            prefix += self._read_exact(1, deadline)
            scanned += 1
            if scanned > _MAX_PREFIX_BYTES:
                raise M1N1TransportError("reply prefix exceeds bounded console output")
            if len(prefix) > 4:
                del prefix[0]
            if len(prefix) == 4 and prefix[:3] == _REPLY_PREFIX:
                break
        reply = bytes(prefix) + self._read_exact(32, deadline)
        if _checksum(reply[:-4]) != struct.unpack_from("<I", reply, 32)[0]:
            raise M1N1TransportError("m1n1 reply checksum mismatch")
        reply_command, status = struct.unpack_from("<Ii", reply)
        if reply_command != command or status != 0:
            raise M1N1TransportError("m1n1 reply command or status mismatch")
        return reply[8:32]

    def _write_all(self, payload: bytes, deadline: float) -> None:
        assert self._fd is not None
        remaining = memoryview(payload)
        while remaining:
            self._wait(deadline, writable=True)
            try:
                count = os.write(self._fd, remaining)
            except BlockingIOError:
                continue
            if count <= 0:
                raise M1N1TransportError("serial write ended before command completion")
            remaining = remaining[count:]

    def _read_exact(self, size: int, deadline: float) -> bytes:
        assert self._fd is not None
        data = bytearray()
        while len(data) < size:
            self._wait(deadline, writable=False)
            try:
                part = os.read(self._fd, size - len(data))
            except BlockingIOError:
                continue
            if not part:
                raise M1N1TransportError("serial read ended before reply completion")
            data += part
        return bytes(data)

    def _wait(self, deadline: float, *, writable: bool) -> None:
        assert self._fd is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise M1N1TransportError("m1n1 observation deadline expired")
        try:
            ready = select.select(
                [] if writable else [self._fd],
                [self._fd] if writable else [],
                [],
                remaining,
            )
        except OSError as exc:
            if exc.errno == errno.EINTR:
                return self._wait(deadline, writable=writable)
            raise M1N1TransportError("serial readiness check failed") from exc
        if not (ready[1] if writable else ready[0]):
            raise M1N1TransportError("m1n1 observation deadline expired")
