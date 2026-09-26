"""Bounded acquisition from a caller-owned native result descriptor.

This module never opens a device, launches target work, or establishes physical
identity. A host timeout says nothing about whether the target has stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import os
import select
import struct
import time
from typing import Literal

from .native_harness import (
    MAX_NATIVE_FRAME_BYTES,
    NativeCapture,
    NativeHarnessError,
    NativeImageManifest,
    NativeLaunchManifest,
    NativeResultAssembler,
)


MAX_NATIVE_STREAM_BYTES = 32 * 1024 * 1024
StreamStopReason = Literal[
    "terminal", "eof", "deadline", "framing_error", "io_error", "stream_limit"
]


@dataclass(frozen=True)
class NativeStreamReceipt:
    capture: NativeCapture
    raw_stream: bytes
    stop_reason: StreamStopReason
    terminal_received_before_deadline: bool


def receive_native_result_stream(
    fd: int, launch: NativeLaunchManifest, image: NativeImageManifest
) -> NativeStreamReceipt:
    """Receive one finite stream without changing or closing its descriptor.

    The caller must provide exclusive access to a nonblocking descriptor. The
    terminal frame delimits a run; any trailing bytes in that same read make
    it invalid. Later traffic is left to the owner of the channel. Accepted
    frames and incomplete wire bytes are retained on failure, up to the stream
    cap. Sample schema/count screening belongs to the publication boundary.
    """

    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    except (OSError, ValueError) as exc:
        raise NativeHarnessError("native result descriptor is unavailable") from exc
    if not flags & os.O_NONBLOCK:
        raise NativeHarnessError("native result descriptor must be nonblocking")
    # Set the monotonic bound before validation so setup cannot extend it.
    started = time.monotonic()
    remaining = (launch.deadline - datetime.now(timezone.utc)).total_seconds()
    deadline = started + remaining
    assembler = NativeResultAssembler(launch, image)
    raw = bytearray()
    offset = 0
    reason: StreamStopReason = "eof"
    message = "result channel closed without a terminal frame"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reason, message = "deadline", "host receive deadline elapsed; target stop is unverified"
            break
        if len(raw) >= MAX_NATIVE_STREAM_BYTES:
            reason, message = "stream_limit", "result channel reached its wire-byte limit"
            break
        try:
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                reason, message = "deadline", "host receive deadline elapsed; target stop is unverified"
                break
            chunk = os.read(fd, min(65_536, MAX_NATIVE_STREAM_BYTES - len(raw)))
        except (InterruptedError, BlockingIOError):
            continue
        except (OSError, ValueError):
            reason, message = "io_error", "result channel read failed; target stop is unverified"
            break
        raw.extend(chunk)
        if time.monotonic() >= deadline:
            reason, message = "deadline", "host receive deadline elapsed; target stop is unverified"
            break
        if not chunk:
            break
        invalid = False
        while len(raw) - offset >= 4:
            if time.monotonic() >= deadline:
                reason, message = "deadline", "host receive deadline elapsed; target stop is unverified"
                invalid = True
                break
            frame_size = struct.unpack_from(">I", raw, offset)[0]
            if not 1 <= frame_size <= MAX_NATIVE_FRAME_BYTES:
                reason, message = "framing_error", "result stream contains an invalid frame length"
                invalid = True
                break
            end = offset + 4 + frame_size
            if end > len(raw):
                break
            try:
                assembler.accept(bytes(raw[offset:end]))
            except NativeHarnessError as exc:
                reason, message = "framing_error", str(exc)[:1024]
                invalid = True
                break
            offset = end
            if assembler.has_terminal_frame:
                if offset != len(raw):
                    reason, message = "framing_error", "result stream contains bytes after its terminal frame"
                    invalid = True
                    break
                if time.monotonic() >= deadline:
                    reason, message = "deadline", "host receive deadline elapsed; target stop is unverified"
                    invalid = True
                    break
                return NativeStreamReceipt(assembler.capture(), bytes(raw), "terminal", True)
        if invalid:
            break
    capture = assembler.capture(message)
    # A terminal marker followed by garbage or expiry cannot remain complete.
    capture = capture.model_copy(update={"status": "unknown", "message": message})
    return NativeStreamReceipt(capture, bytes(raw), reason, False)
