"""Real, short-video checks for the offline optical calibration decoder."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "scripts/decode-optical-calibration.py"
SPEC = importlib.util.spec_from_file_location("optical_calibration_decoder", SOURCE)
assert SPEC and SPEC.loader
decoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decoder)


@pytest.fixture(scope="module", autouse=True)
def external_tools():
    if any(shutil.which(name) is None for name in ("ffmpeg", "ffprobe", "zbarimg", "qrencode")):
        pytest.skip("ffmpeg, ffprobe, zbarimg, and qrencode are required")


def _run(*args: str) -> None:
    subprocess.run(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                   timeout=20, check=True)


def _qr_video(directory: Path, token: bytes) -> Path:
    qr = directory / "token.png"
    video = directory / "token.mkv"
    _run("qrencode", "-8", "-s", "12", "-o", str(qr), token.decode("ascii"))
    _run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-loop", "1", "-framerate", "2", "-i", str(qr), "-t", "2",
         "-vf", "pad=1280:720:(ow-iw)/2:(oh-ih)/2:white",
         "-r", "2", "-c:v", "ffv1", str(video))
    return video


def _cli(video: Path, expected: bytes) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(SOURCE), "--video", str(video),
         "--expected-hex", expected.hex()],
        capture_output=True, timeout=30, check=False,
    )
    assert not result.stderr
    return result.returncode, json.loads(result.stdout)


def test_real_qr_video_decodes_exact_bytes_and_sample_times(tmp_path):
    token = b"M1LAB-CAL:7a3f91"
    video = _qr_video(tmp_path, token)

    code, result = _cli(video, token)

    assert code == 0
    assert result["schema"] == decoder.SCHEMA
    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["expected_payload_hex"] == token.hex()
    assert result["decoded_payload_hex"] == token.hex()
    assert result["frames_scanned"] == 4
    assert result["count"] == 4
    assert result["first_timestamp_ms"] == 0
    assert result["last_timestamp_ms"] == 1500
    assert result["sample_interval_ms"] == 500

    code, wrong = _cli(video, b"M1LAB-CAL:different")
    assert code == 1
    assert wrong["verified"] is False
    assert wrong["status"] == "unexpected_payload"
    assert wrong["decoded_payload_hex"] == token.hex()
    assert wrong["count"] == 0
    assert wrong["unexpected_timestamp_ms"] == 0


def test_missing_qr_is_a_failed_json_result(tmp_path):
    video = tmp_path / "white.mkv"
    _run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=1280x720:r=2:d=2",
         "-c:v", "ffv1", str(video))

    code, result = _cli(video, b"M1LAB-CAL:7a3f91")

    assert code == 1
    assert result["verified"] is False
    assert result["status"] == "missing_payload"
    assert result["decoded_payload_hex"] is None
    assert result["first_timestamp_ms"] is None
    assert result["last_timestamp_ms"] is None
    assert result["count"] == 0


def test_timestamps_follow_token_window_with_empty_frames(tmp_path):
    token = b"M1LAB-CAL:window"
    qr = tmp_path / "token.png"
    video = tmp_path / "window.mkv"
    _run("qrencode", "-8", "-s", "12", "-o", str(qr), token.decode("ascii"))
    _run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=1280x720:r=2:d=3",
         "-loop", "1", "-framerate", "2", "-i", str(qr),
         "-filter_complex", "[0:v][1:v]overlay=(W-w)/2:(H-h)/2:enable='between(t,1,2)'",
         "-t", "3", "-r", "2", "-c:v", "ffv1", str(video))

    code, result = _cli(video, token)

    assert code == 0
    assert result["verified"] is True
    assert result["frames_scanned"] == 6
    assert result["count"] == 3
    assert result["first_timestamp_ms"] == 1000
    assert result["last_timestamp_ms"] == 2000


def test_rejects_non_720p_video_and_invalid_expected_hex(tmp_path):
    small = tmp_path / "small.mkv"
    _run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=640x360:r=2:d=1",
         "-c:v", "ffv1", str(small))

    code, result = _cli(small, b"M1LAB-CAL:7a3f91")
    assert code == 1
    assert result == {"schema": decoder.SCHEMA, "verified": False,
                      "status": "error", "error_code": "video_dimensions_invalid"}
    with pytest.raises(decoder.DecodeError, match="expected_hex_invalid"):
        decoder.expected_bytes("abc")
    with pytest.raises(decoder.DecodeError, match="expected_hex_invalid"):
        decoder.expected_bytes("41" * 129)
