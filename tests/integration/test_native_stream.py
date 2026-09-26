"""Host descriptor acquisition of synthetic native frames; no target access."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import struct
import subprocess
import sys
from threading import Event, Thread
import time

import pytest

from m1lab.adapters.native_harness import (
    decode_native_result_frame, encode_native_result_frame, make_native_result_frame,
)
from m1lab.adapters.native_stream import receive_native_result_stream
from m1lab.native_runs import receive_native_capture

from test_native_capture import _CHILD, _COLLECTOR, _capture, _frames, captured


@contextmanager
def _pipe():
    reader, writer = os.pipe()
    os.set_blocking(reader, False)
    try:
        yield reader, writer
    finally:
        for fd in (reader, writer):
            try:
                os.close(fd)
            except OSError:
                pass


def _soon(launch, milliseconds=250):
    return launch.model_copy(update={
        "deadline": datetime.now(timezone.utc) + timedelta(milliseconds=milliseconds),
    })


def test_fragmented_real_pipe_completes_without_eof_and_keeps_descriptor_owned(captured):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    writer_done = Event()
    release_writer = Event()
    with _pipe() as (reader, writer):
        def emit():
            try:
                for offset in range(0, len(stream), 37):
                    os.write(writer, stream[offset:offset + 37])
                    time.sleep(0.0005)
                writer_done.set()
                release_writer.wait(timeout=2)
            finally:
                os.close(writer)

        thread = Thread(target=emit, daemon=True)
        thread.start()
        try:
            receipt = receive_native_result_stream(reader, launch, image)
            assert writer_done.wait(timeout=1)
            assert receipt.capture.status == "complete"
            assert receipt.raw_stream == stream
            assert receipt.terminal_received_before_deadline is True
            assert receipt.stop_reason
            assert os.get_blocking(reader) is False
            os.fstat(reader)
        finally:
            release_writer.set()
            thread.join(timeout=2)
        assert not thread.is_alive()


def test_blocking_descriptor_is_refused_without_changing_ownership(captured):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    reader, writer = os.pipe()
    try:
        assert os.get_blocking(reader) is True
        with pytest.raises((ValueError, RuntimeError), match="nonblocking|non-blocking"):
            receive_native_result_stream(reader, launch, image)
        assert os.get_blocking(reader) is True
        os.fstat(reader)
    finally:
        os.close(reader)
        os.close(writer)


@pytest.mark.parametrize("fragment", ["prefix", "body"])
def test_eof_preserves_incomplete_prefix_or_frame(captured, fragment):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    partial = stream[:2] if fragment == "prefix" else stream[:14]
    with _pipe() as (reader, writer):
        os.write(writer, partial)
        os.close(writer)
        receipt = receive_native_result_stream(reader, launch, image)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream == partial
    assert receipt.terminal_received_before_deadline is False
    assert receipt.stop_reason


@pytest.mark.parametrize("fragment", ["prefix", "body"])
def test_stalled_prefix_or_frame_times_out_without_claiming_target_stop(captured, fragment):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    partial = stream[:2] if fragment == "prefix" else stream[:14]
    with _pipe() as (reader, writer):
        os.write(writer, partial)
        receipt = receive_native_result_stream(reader, _soon(launch), image)
        os.fstat(writer)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream == partial
    assert receipt.terminal_received_before_deadline is False
    assert receipt.stop_reason


def test_slow_trickle_does_not_extend_total_receive_deadline(captured):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    stop_writer = Event()
    with _pipe() as (reader, writer):
        def trickle():
            for byte in stream[:16]:
                if stop_writer.is_set():
                    break
                os.write(writer, bytes([byte]))
                time.sleep(0.08)

        thread = Thread(target=trickle, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            receipt = receive_native_result_stream(reader, _soon(launch, milliseconds=300), image)
        finally:
            stop_writer.set()
            thread.join(timeout=2)
        assert not thread.is_alive()
    assert time.monotonic() - started < 0.8
    assert receipt.capture.status == "unknown"
    assert 1 <= len(receipt.raw_stream) < 16
    assert receipt.stop_reason == "deadline"
    assert receipt.terminal_received_before_deadline is False


def test_wire_cap_preserves_exact_bounded_prefix_and_refuses_frame(captured, monkeypatch):
    import m1lab.adapters.native_stream as native_stream

    _session, image, _manifest, launch, _artifact, stream, _root = captured
    advertised_frame_length = struct.unpack_from(">I", stream)[0]
    assert 12 < advertised_frame_length < 1_500_000
    monkeypatch.setattr(native_stream, "MAX_NATIVE_STREAM_BYTES", 12)
    with _pipe() as (reader, writer):
        os.write(writer, stream)
        receipt = receive_native_result_stream(reader, launch, image)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream == stream[:12]
    assert receipt.stop_reason == "stream_limit"
    assert receipt.terminal_received_before_deadline is False


def test_caller_wire_cap_preserves_exact_prefix_without_changing_global_default(captured):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    with _pipe() as (reader, writer):
        os.write(writer, stream)
        receipt = receive_native_result_stream(reader, launch, image, max_stream_bytes=17)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream == stream[:17]
    assert receipt.stop_reason == "stream_limit"


def test_caller_deadline_can_stop_before_signed_launch_deadline(captured):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    with _pipe() as (reader, writer):
        os.write(writer, stream[:2])
        started = time.monotonic()
        receipt = receive_native_result_stream(
            reader, launch, image, deadline_monotonic=started + 0.08,
        )
    assert receipt.raw_stream == stream[:2]
    assert receipt.stop_reason == "deadline"
    assert time.monotonic() - started < 0.5


def test_valid_sample_before_later_truncation_remains_in_unknown_capture(captured):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    frames = _frames(stream)
    partial = frames[0] + frames[1] + frames[2][:11]
    expected_sample = base64.b64decode(decode_native_result_frame(frames[1]).payload_base64)
    with _pipe() as (reader, writer):
        os.write(writer, partial)
        os.close(writer)
        receipt = receive_native_result_stream(reader, launch, image)
    assert receipt.capture.status == "unknown"
    assert receipt.capture.launch_binding_verified is True
    assert receipt.capture.payload == expected_sample
    assert receipt.raw_stream == partial
    assert receipt.stop_reason == "eof"


def test_oversized_frame_prefix_fails_closed_and_preserves_prefix(captured):
    _session, image, _manifest, launch, _artifact, _stream, _root = captured
    prefix = struct.pack(">I", 1_500_001)
    with _pipe() as (reader, writer):
        os.write(writer, prefix)
        receipt = receive_native_result_stream(reader, launch, image)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream == prefix
    assert receipt.terminal_received_before_deadline is False


@pytest.mark.parametrize("fault", ["checksum", "run", "trailer"])
def test_corrupt_mismatched_or_trailing_bytes_are_unknown(captured, fault):
    _session, image, _manifest, launch, _artifact, stream, _root = captured
    frames = _frames(stream)
    if fault == "checksum":
        faulty = bytearray(frames[0])
        position = faulty.index(b'"frame_sha256":"') + len(b'"frame_sha256":"')
        faulty[position] = ord("a") if faulty[position] != ord("a") else ord("b")
        payload = bytes(faulty) + b"".join(frames[1:])
    elif fault == "run":
        altered = decode_native_result_frame(frames[0]).model_copy(update={"run_id": "other-run"})
        payload = encode_native_result_frame(altered) + b"".join(frames[1:])
    else:
        payload = stream + b"trailing-bytes"
    with _pipe() as (reader, writer):
        os.write(writer, payload)
        os.close(writer)
        receipt = receive_native_result_stream(reader, launch, image)
    assert receipt.capture.status == "unknown"
    assert receipt.raw_stream.startswith(payload[:len(frames[0])])
    if fault == "trailer":
        assert receipt.raw_stream == payload
    assert receipt.terminal_received_before_deadline is False
    assert receipt.stop_reason


def test_descriptor_import_screens_sample_count_and_records_acquisition(core, captured):
    session_id, _image, manifest_artifact, launch, launch_artifact, stream, _root = captured
    frames = _frames(stream)
    shortened = b"".join(frames[:2]) + encode_native_result_frame(make_native_result_frame(
        frame_kind="end", run_id=launch.run_id,
        image_sha256=launch.image_sha256, target_identity=launch.target_identity,
        boot_epoch=launch.boot_epoch,
        configuration_sha256=launch.configuration_sha256,
        sequence=2, terminal_status="complete",
    ))
    with _pipe() as (reader, writer):
        os.write(writer, shortened)
        capture, raw_artifact, normalized_artifact = receive_native_capture(
            core, session_id,
            launch_artifact_id=launch_artifact.id,
            image_manifest_artifact_id=manifest_artifact.id,
            fd=reader,
        )
    assert capture.status == "unknown"
    assert capture.payload == b""
    assert core.read_session_artifact(session_id, raw_artifact.id) == shortened
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    acquisition = document["stream_acquisition"]
    assert acquisition["mode"] == "descriptor"
    assert acquisition["terminal_received_before_deadline"] is True
    assert acquisition["target_stop_verified"] is False
    assert acquisition["stop_reason"]
    assert document["protocol_status"] == "complete"
    assert document["payload_screening"] == "omitted_sample_count_mismatch"
    assert document["identity_verified"] is False
    assert document["physical_source_verified"] is False
    assert document["capture_timing_verified"] is False


def test_flowing_child_stdout_is_received_and_published_without_physical_claim(core, captured):
    session_id, _image, manifest_artifact, _launch, launch_artifact, _stream, root = captured
    process = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(_COLLECTOR), str(root / "launch.json")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        os.set_blocking(process.stdout.fileno(), False)
        capture, raw_artifact, normalized_artifact = receive_native_capture(
            core, session_id,
            launch_artifact_id=launch_artifact.id,
            image_manifest_artifact_id=manifest_artifact.id,
            fd=process.stdout.fileno(),
        )
        assert process.wait(timeout=5) == 0, process.stderr.read().decode(errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()

    assert capture.status == "complete"
    raw = core.read_session_artifact(session_id, raw_artifact.id)
    assert [decode_native_result_frame(frame).frame_kind for frame in _frames(raw)] == [
        "identity", "data", "data", "end",
    ]
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["stream_acquisition"]["mode"] == "descriptor"
    assert document["stream_acquisition"]["terminal_received_before_deadline"] is True
    assert document["stream_acquisition"]["target_stop_verified"] is False
    assert document["identity_verified"] is False
    assert document["physical_source_verified"] is False
    assert document["capture_timing_verified"] is False


def test_descriptor_timeout_publishes_unknown_without_target_stop_claim(core, tmp_path):
    captured = _capture(core, tmp_path, deadline_seconds=2)
    session_id, _image, manifest_artifact, launch, launch_artifact, stream, _root = captured
    partial = stream[:2]
    with _pipe() as (reader, writer):
        os.write(writer, partial)
        capture, raw_artifact, normalized_artifact = receive_native_capture(
            core, session_id,
            launch_artifact_id=launch_artifact.id,
            image_manifest_artifact_id=manifest_artifact.id,
            fd=reader,
        )
    assert capture.status == "unknown"
    assert core.read_session_artifact(session_id, raw_artifact.id) == partial
    document = json.loads(core.read_session_artifact(session_id, normalized_artifact.id))
    assert document["stream_acquisition"]["terminal_received_before_deadline"] is False
    assert document["stream_acquisition"]["target_stop_verified"] is False
    assert document["stream_acquisition"]["stop_reason"]
