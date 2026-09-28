"""Summaries recheck retained captures; host fixtures never qualify hardware."""

import base64
import hashlib
import json

import pytest

from test_native_capture import captured, _frames, _import  # noqa: F401

from m1lab import cli
from m1lab.adapters.native_harness import (
    NativeHarnessError, decode_native_result_frame, encode_native_result_frame,
)
from m1lab.core.models import SessionCreate
from m1lab.native_runs import CAPTURE_MEDIA_TYPE
from m1lab.native_summary import summarize_native_capture


def test_complete_summary_has_lineage_sensor_fields_and_timing_without_writes(core, captured):
    session_id, *_, stream, _root = captured
    _capture, raw, normalized = _import(core, captured, stream)
    before = core.snapshot(session_id)
    artifact_ids = [item.id for item in core.artifacts(session_id)]

    summary = summarize_native_capture(core, session_id, normalized.id)

    assert summary["status"] == "complete"
    assert summary["raw_stream_sha256"] == raw.sha256
    assert summary["recognized_samples"] == summary["expected_samples"] == 2
    assert summary["missing_samples"] == 0
    assert summary["timing"]["interval_count"] == 1
    assert summary["timing"]["median_interval_ms"] > 0
    assert summary["sensor_fields"] == [{
        "source": "power_supplies", "name": "synthetic-battery", "field": "capacity",
        "samples_present": 2, "samples_missing": 0,
        "first_raw_value": "73", "last_raw_value": "73",
    }]
    assert summary["measurement_qualified"] is False
    assert summary["physical_source_verified"] is False
    assert summary["capture_timing_verified"] is False
    assert core.snapshot(session_id) == before
    assert [item.id for item in core.artifacts(session_id)] == artifact_ids


def test_truncated_terminal_is_unknown_even_with_all_samples(core, captured):
    session_id, *_, stream, _root = captured
    _capture, _raw, normalized = _import(core, captured, stream[:-9])

    summary = summarize_native_capture(core, session_id, normalized.id)

    assert summary["recognized_samples"] == 2
    assert summary["status"] == "unknown"
    assert "incomplete" in summary["qualification_gaps"][0]
    assert summary["measurement_qualified"] is False


def test_no_frames_does_not_invent_samples_or_cadence(core, captured):
    session_id = captured[0]
    _capture, _raw, normalized = _import(core, captured, b"")

    summary = summarize_native_capture(core, session_id, normalized.id)

    assert summary["recognized_samples"] == 0
    assert summary["missing_samples"] == 2
    assert summary["sensor_fields"] == []
    assert summary["timing"]["median_interval_ms"] is None
    assert any("No power-supply" in gap for gap in summary["qualification_gaps"])


def test_missing_field_and_reported_cadence_are_counted_from_samples(core, captured):
    session_id, *_, stream, _root = captured
    frames = []
    for wire in _frames(stream):
        frame = decode_native_result_frame(wire)
        if frame.frame_kind == "data":
            sample = json.loads(base64.b64decode(frame.payload_base64))
            sample["monotonic_ns"] = 1_000_000_000 + sample["sample_index"] * 125_000_000
            if sample["sample_index"] == 1:
                sample["sources"]["power_supplies"] = []
            payload = json.dumps(sample).encode() + b"\n"
            frame = frame.model_copy(update={
                "payload_base64": base64.b64encode(payload).decode(),
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            })
        frames.append(encode_native_result_frame(frame))
    _capture, _raw, normalized = _import(core, captured, b"".join(frames))

    summary = summarize_native_capture(core, session_id, normalized.id)

    assert summary["status"] == "complete"
    assert summary["timing"]["median_interval_ms"] == 125
    assert summary["timing"]["maximum_absolute_period_error_ms"] == 25
    assert summary["sensor_fields"][0]["samples_present"] == 1
    assert summary["sensor_fields"][0]["samples_missing"] == 1


def test_summary_refuses_foreign_artifact_and_wrong_media_type(core, captured):
    session_id, *_, stream, _root = captured
    _capture, raw, normalized = _import(core, captured, stream)
    other = core.create_session(SessionCreate(
        objective="Other", owner="test-owner", host_identity="synthetic-host",
    ))
    for sid, artifact_id in ((other.id, normalized.id), (session_id, raw.id)):
        with pytest.raises(NativeHarnessError, match="unavailable"):
            summarize_native_capture(core, sid, artifact_id)


def test_summary_detects_changed_normalization_instead_of_trusting_document(core, captured):
    session_id, *_, stream, _root = captured
    _capture, _raw, normalized = _import(core, captured, stream)
    document = json.loads(core.read_session_artifact(session_id, normalized.id))
    document["payload"] = ""
    altered = core.publish_artifact(
        json.dumps(document).encode(), media_type=CAPTURE_MEDIA_TYPE,
        provenance=normalized.provenance,
    )
    with pytest.raises(NativeHarnessError, match="differs from its retained raw"):
        summarize_native_capture(core, session_id, altered.id)


def test_cli_summarizes_selected_capture_and_requires_session(core, captured, monkeypatch, capsys):
    session_id, *_, stream, _root = captured
    _capture, _raw, normalized = _import(core, captured, stream)
    monkeypatch.setenv("M1LAB_DATA_DIR", str(core.journal.paths.root))
    monkeypatch.setenv("M1LAB_CODEX_RUNTIME", "disabled")
    cli.main(["--json", "--session", session_id, "native-summary",
              "--capture-artifact", normalized.id])
    assert json.loads(capsys.readouterr().out)["recognized_samples"] == 2
    with pytest.raises(SystemExit) as error:
        cli.main(["native-summary", "--capture-artifact", normalized.id])
    assert error.value.code == 2
    assert "explicit --session" in capsys.readouterr().err
