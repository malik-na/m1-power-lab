#!/usr/bin/env python3
"""Decode a short QR calibration token from a private, local 1280x720 recording.

The timestamps are sampled positions relative to the beginning of the recording.
They do not claim when the token first appeared or disappeared between samples.
Only the JSON result is written to stdout; video frames stay in memory.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time


SCHEMA = "m1lab.optical-calibration-decoder.v1"
WIDTH = 1280
HEIGHT = 720
SAMPLE_HZ = 2
FRAME_BYTES = WIDTH * HEIGHT
MAX_VIDEO_BYTES = 1024 * 1024 * 1024
MAX_DURATION_SECONDS = 480
MAX_FRAMES = MAX_DURATION_SECONDS * SAMPLE_HZ
MAX_WALL_SECONDS = 180
MAX_TOKEN_BYTES = 128
PGM_HEADER = f"P5\n{WIDTH} {HEIGHT}\n255\n".encode("ascii")
HEX = re.compile(r"[0-9a-fA-F]+\Z")


class DecodeError(ValueError):
    """A bounded failure code that never embeds a path or frame content."""


def expected_bytes(value: str) -> bytes:
    if not value or len(value) % 2 or len(value) > MAX_TOKEN_BYTES * 2 or not HEX.fullmatch(value):
        raise DecodeError("expected_hex_invalid")
    return bytes.fromhex(value)


def _video_file(path: Path) -> Path:
    path = path.absolute()
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_VIDEO_BYTES:
        raise DecodeError("video_size_or_type_invalid")
    return path


def _duration(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return result if result.is_finite() and result > 0 else None


def probe_video(path: Path) -> Decimal:
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=15, check=False)
    if result.returncode or len(result.stdout) > 32 * 1024:
        raise DecodeError("video_probe_failed")
    try:
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        if (stream["width"], stream["height"]) != (WIDTH, HEIGHT):
            raise DecodeError("video_dimensions_invalid")
        duration = (_duration(metadata.get("format", {}).get("duration"))
                    or _duration(stream.get("duration")))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        if isinstance(exc, DecodeError):
            raise
        raise DecodeError("video_probe_invalid") from exc
    if duration is None or duration > MAX_DURATION_SECONDS:
        raise DecodeError("video_duration_invalid")
    return duration


def _read_frame(fd: int, deadline: float) -> bytes | None:
    frame = bytearray()
    while len(frame) < FRAME_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DecodeError("scan_deadline_exceeded")
        if not select.select([fd], [], [], min(remaining, 1.0))[0]:
            continue
        chunk = os.read(fd, min(FRAME_BYTES - len(frame), 64 * 1024))
        if not chunk:
            if frame:
                raise DecodeError("frame_truncated")
            return None
        frame.extend(chunk)
    return bytes(frame)


def _qr_payload(frame: bytes, deadline: float) -> bytes | None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DecodeError("scan_deadline_exceeded")
    result = subprocess.run(
        ["zbarimg", "--nodbus", "-1", "--raw", "-q", "--set", "*.enable=0",
         "--set", "qrcode.enable=1", "-"],
        input=PGM_HEADER + frame, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=min(5.0, remaining), check=False,
    )
    if result.returncode == 4 and not result.stdout:
        return None
    if result.returncode != 0:
        raise DecodeError("qr_decoder_failed")
    if not 0 < len(result.stdout) <= MAX_TOKEN_BYTES:
        raise DecodeError("decoded_payload_size_invalid")
    return result.stdout


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def scan_video(path: Path, expected: bytes) -> dict[str, object]:
    """Return a JSON-safe verification result; nonmatches are never verified."""
    if not 0 < len(expected) <= MAX_TOKEN_BYTES:
        raise DecodeError("expected_hex_invalid")
    video = _video_file(path)
    duration = probe_video(video)
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"setpts=PTS-STARTPTS,fps={SAMPLE_HZ}:round=near,format=gray",
        "-frames:v", str(MAX_FRAMES + 1), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    assert process.stdout is not None
    deadline = time.monotonic() + MAX_WALL_SECONDS
    frames = 0
    count = 0
    first_ms: int | None = None
    last_ms: int | None = None
    wrong_payload: bytes | None = None
    wrong_ms: int | None = None
    try:
        while True:
            frame = _read_frame(process.stdout.fileno(), deadline)
            if frame is None:
                break
            if frames >= MAX_FRAMES:
                raise DecodeError("frame_limit_exceeded")
            timestamp_ms = frames * 1000 // SAMPLE_HZ
            frames += 1
            payload = _qr_payload(frame, deadline)
            if payload is None:
                continue
            if payload != expected:
                wrong_payload, wrong_ms = payload, timestamp_ms
                break
            count += 1
            if first_ms is None:
                first_ms = timestamp_ms
            last_ms = timestamp_ms
        if wrong_payload is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DecodeError("scan_deadline_exceeded")
            if process.wait(timeout=remaining) != 0:
                raise DecodeError("video_decode_failed")
    finally:
        process.stdout.close()
        _stop(process)

    verified = count > 0 and wrong_payload is None
    return {
        "schema": SCHEMA,
        "verified": verified,
        "status": "verified" if verified else "unexpected_payload" if wrong_payload else "missing_payload",
        "video_duration_seconds": str(duration),
        "sample_interval_ms": 1000 // SAMPLE_HZ,
        "frames_scanned": frames,
        "expected_payload_hex": expected.hex(),
        "decoded_payload_hex": (wrong_payload.hex() if wrong_payload is not None
                                else expected.hex() if count else None),
        "first_timestamp_ms": first_ms,
        "last_timestamp_ms": last_ms,
        "count": count,
        "unexpected_timestamp_ms": wrong_ms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path, help="private local 1280x720 video")
    parser.add_argument("--expected-hex", required=True, help="1..128 expected QR bytes, hex encoded")
    arguments = parser.parse_args(argv)
    try:
        result = scan_video(arguments.video, expected_bytes(arguments.expected_hex))
    except (DecodeError, OSError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, DecodeError):
            code = str(exc)
        elif isinstance(exc, subprocess.TimeoutExpired):
            code = "external_tool_timeout"
        else:
            code = "input_or_tool_unavailable"
        result = {"schema": SCHEMA, "verified": False, "status": "error", "error_code": code}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
