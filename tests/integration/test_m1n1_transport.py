"""PTY-only checks for the pinned m1n1 v1.6.1 observation subset."""

from __future__ import annotations

import os
import pty
import select
import struct
import threading
import time

import pytest

from m1lab.adapters import m1n1_transport
from m1lab.adapters.m1n1_transport import M1N1ReadOnlyTransport, M1N1TransportError


def checksum(data: bytes) -> int:
    # Independent peer implementation of uartproxy.c:72-101.
    value = 0xDEADBEEF
    for byte in data:
        value = ((value * 31337) + (byte ^ 0x5A)) % (1 << 32)
    return value ^ 0xADDEDBAD


def read_exact(fd: int, size: int) -> bytes:
    data = b""
    while len(data) < size:
        assert select.select([fd], [], [], 2)[0]
        data += os.read(fd, size - len(data))
    return data


def reply(command: int, payload: bytes = b"", *, status: int = 0) -> bytes:
    body = struct.pack("<Ii", command, status) + payload.ljust(24, b"\0")
    return body + struct.pack("<I", checksum(body))


@pytest.fixture
def peer():
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    try:
        yield master, path
    finally:
        os.close(slave)
        os.close(master)


def test_exact_read_only_wire_sequence_and_identity(peer):
    master, path = peer
    observed: list[bytes] = []
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            for index, opcode in enumerate((None, 0, 0x13, 4, 3)):
                request = read_exact(master, 64)
                observed.append(request)
                expected_command = 0x00AA55FF if index == 0 else 0x01AA55FF
                expected_payload = (struct.pack("<Q", 0) if opcode is None else struct.pack("<Q", opcode)).ljust(56, b"\0")
                expected_body = struct.pack("<I", expected_command) + expected_payload
                assert request == expected_body + struct.pack("<I", checksum(expected_body))
                if opcode is None:
                    data = struct.pack("<Q", 0)
                else:
                    value = {0: 0, 0x13: 0x8103, 4: 0x805574000, 3: 0x805CAC088}[opcode]
                    data = struct.pack("<QqQ", opcode, 0, value)
                os.write(master, reply(expected_command, data))
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=serve)
    worker.start()
    with M1N1ReadOnlyTransport(path) as transport:
        identity = transport.observe(deadline_monotonic=time.monotonic() + 2)
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not errors
    assert len(observed) == 5
    assert (identity.chip_id, identity.base, identity.bootargs_address) == (
        0x8103, 0x805574000, 0x805CAC088
    )


@pytest.mark.parametrize("kind", ["checksum", "status", "opcode", "feature"])
def test_bad_reply_fails_closed(peer, kind):
    master, path = peer

    def serve() -> None:
        read_exact(master, 64)
        if kind == "feature":
            packet = reply(0x00AA55FF, struct.pack("<Q", 1))
        elif kind == "status":
            packet = reply(0x00AA55FF, status=-4)
        elif kind == "opcode":
            packet = reply(0x01AA55FF)
        else:
            packet = reply(0x00AA55FF)[:-1] + b"\x00"
        os.write(master, packet)

    worker = threading.Thread(target=serve)
    worker.start()
    with M1N1ReadOnlyTransport(path) as transport:
        with pytest.raises(M1N1TransportError):
            transport.observe(deadline_monotonic=time.monotonic() + 1)
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_trickle_bytes_cannot_extend_total_deadline(peer):
    master, path = peer
    stopped = threading.Event()

    def serve() -> None:
        read_exact(master, 64)
        packet = reply(0x00AA55FF)
        for byte in packet:
            if stopped.is_set():
                return
            try:
                os.write(master, bytes([byte]))
            except OSError:
                return
            time.sleep(0.025)

    worker = threading.Thread(target=serve)
    worker.start()
    start = time.monotonic()
    try:
        with M1N1ReadOnlyTransport(path) as transport:
            with pytest.raises(M1N1TransportError, match="deadline"):
                transport.observe(deadline_monotonic=start + 0.15)
    finally:
        stopped.set()
        worker.join(timeout=2)
    assert time.monotonic() - start < 0.7


@pytest.mark.parametrize("kind", ["proxy_status", "proxy_opcode", "truncated"])
def test_proxy_reply_error_or_truncation_fails_closed(peer, kind):
    master, path = peer

    def serve() -> None:
        read_exact(master, 64)
        os.write(master, reply(0x00AA55FF))
        read_exact(master, 64)
        if kind == "truncated":
            os.write(master, reply(0x01AA55FF)[:15])
        else:
            opcode = 3 if kind == "proxy_opcode" else 0
            status = -1 if kind == "proxy_status" else 0
            os.write(master, reply(0x01AA55FF, struct.pack("<QqQ", opcode, status, 0)))

    worker = threading.Thread(target=serve)
    worker.start()
    with M1N1ReadOnlyTransport(path) as transport:
        with pytest.raises(M1N1TransportError):
            transport.observe(deadline_monotonic=time.monotonic() + 0.25)
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_kernel_exclusive_tty_open(peer):
    _master, path = peer
    with M1N1ReadOnlyTransport(path):
        with pytest.raises(OSError):
            os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    os.close(fd)


def test_setup_failure_releases_tty_exclusivity(peer, monkeypatch):
    _master, path = peer

    def fail_setup(_fd, _when, _settings):
        raise OSError("synthetic termios setup failure")

    monkeypatch.setattr(m1n1_transport.termios, "tcsetattr", fail_setup)
    with pytest.raises(OSError, match="synthetic"):
        with M1N1ReadOnlyTransport(path):
            pass
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    os.close(fd)
