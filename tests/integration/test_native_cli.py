"""The operator CLI receives synthetic native frames through a real stdin pipe."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from test_native_capture import captured  # noqa: F401 - shared synthetic collector fixture


_ROOT = Path(__file__).resolve().parents[2]


def _command(core, captured):
    session_id, _image, manifest, _launch, launch_artifact, _stream, _root = captured
    env = os.environ.copy()
    env["M1LAB_DATA_DIR"] = str(core.journal.paths.root)
    env["M1LAB_CODEX_RUNTIME"] = "disabled"
    env["PYTHONPATH"] = str(_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        sys.executable, "-m", "m1lab", "--json", "--session", session_id,
        "native-receive", "--launch-artifact", launch_artifact.id,
        "--image-manifest-artifact", manifest.id,
    ]
    return command, env


def test_native_receive_pipe_publishes_complete_capture(core, captured):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    command, env = _command(core, captured)

    result = subprocess.run(command, input=stream, capture_output=True, env=env, timeout=8)

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    output = json.loads(result.stdout)
    assert output["capture"]["status"] == "complete"
    assert output["capture"]["identity_verified"] is False
    assert output["target_stop_verified"] is False
    assert core.read_session_artifact(session_id, output["raw_stream_artifact"]["id"]) == stream
    document = json.loads(core.read_session_artifact(session_id, output["capture_artifact"]["id"]))
    assert document["protocol_status"] == "complete"
    assert document["payload_screening"] == "screened_known_collector_records"
    assert document["stream_acquisition"]["mode"] == "descriptor"
    assert document["stream_acquisition"]["target_stop_verified"] is False


def test_native_receive_truncated_pipe_preserves_unknown_bytes(core, captured):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    command, env = _command(core, captured)
    partial = stream[:-9]

    result = subprocess.run(command, input=partial, capture_output=True, env=env, timeout=8)

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    output = json.loads(result.stdout)
    assert output["capture"]["status"] == "unknown"
    assert output["target_stop_verified"] is False
    assert core.read_session_artifact(session_id, output["raw_stream_artifact"]["id"]) == partial
    document = json.loads(core.read_session_artifact(session_id, output["capture_artifact"]["id"]))
    assert document["stream_acquisition"]["stop_reason"] == "eof"
    assert document["stream_acquisition"]["target_stop_verified"] is False


def test_native_receive_refuses_regular_file_stdin(core, captured, tmp_path):
    session_id, _image, _manifest, _launch, _artifact, stream, _root = captured
    command, env = _command(core, captured)
    saved = tmp_path / "saved-native-stream.bin"
    saved.write_bytes(stream)
    before = len(core.artifacts(session_id))

    with saved.open("rb") as source:
        result = subprocess.run(command, stdin=source, capture_output=True, env=env, timeout=8)

    assert result.returncode == 2
    assert b"stdin pipe or socket" in result.stderr
    assert len(core.artifacts(session_id)) == before
