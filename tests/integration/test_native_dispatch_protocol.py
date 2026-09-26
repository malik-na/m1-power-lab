"""Host-only contract tests for the fixed native candidate helper request."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from m1lab.adapters import HardwareDispatch, InspectRegister, RunNativeCandidate
from m1lab.adapters.helper_protocol import (
    HelperProtocolError, decode_request, decode_request_frame,
    encode_request, encode_request_frame,
)


PAYLOAD = "a" * 64
IMAGE = "b" * 64
LAUNCH = "c" * 64


def _dispatch(*, operation=None, approved=True, attendance=True, artifacts=None, seconds=30):
    now = datetime.now(timezone.utc)
    return HardwareDispatch(
        operation_id="native-op", coordinator_operation_id="coordinator-op",
        session_id="session", target_identity="target", target_snapshot_id="snapshot",
        configuration_digest="d" * 64, procedure_id="procedure",
        procedure_revision=1, review_id="review",
        approval_id="approval" if approved else None,
        approval_scope={
            "target_identity": "target", "boot_epoch": "epoch",
            "configuration_digest": "d" * 64, "repeat_limit": 1,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "physical_attendance_confirmed": attendance,
        } if approved else None,
        boot_epoch="epoch", procedure_digest="e" * 64,
        artifact_digests=(PAYLOAD, IMAGE, LAUNCH) if artifacts is None else artifacts,
        operation_index=0,
        operation=operation or RunNativeCandidate(PAYLOAD, IMAGE, LAUNCH),
        deadline=now + timedelta(seconds=seconds),
    )


def test_native_candidate_round_trip_has_only_three_digest_parameters():
    dispatch = _dispatch()
    frame = encode_request_frame(dispatch)
    decoded = decode_request_frame(frame)
    assert decoded == dispatch
    assert decoded.operation == RunNativeCandidate(PAYLOAD, IMAGE, LAUNCH)
    parameters = json.loads(encode_request(dispatch))["request"]["operation"]["parameters"]
    assert parameters == {
        "payload_sha256": PAYLOAD,
        "image_manifest_sha256": IMAGE,
        "launch_manifest_sha256": LAUNCH,
    }


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "/tmp/payload", "g" * 64])
def test_native_candidate_requires_lowercase_digests(bad):
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        RunNativeCandidate(bad, IMAGE, LAUNCH)


@pytest.mark.parametrize("changes", [
    {"approved": False},
    {"attendance": False},
    {"artifacts": (PAYLOAD, IMAGE)},
    {"seconds": 481},
])
def test_native_candidate_refuses_incomplete_envelope(changes):
    with pytest.raises(ValueError, match="native candidate"):
        _dispatch(**changes)


def test_native_candidate_decode_rechecks_envelope_and_strict_operation_fields():
    document = json.loads(encode_request(_dispatch()))
    document["request"]["approval_scope"]["physical_attendance_confirmed"] = False
    with pytest.raises(HelperProtocolError, match="native candidate"):
        decode_request(json.dumps(document).encode())

    document = json.loads(encode_request(_dispatch()))
    document["request"]["operation"]["parameters"]["path"] = "/tmp/payload"
    with pytest.raises(HelperProtocolError, match="unsupported operation or parameters"):
        decode_request(json.dumps(document).encode())


def test_legacy_inspection_request_round_trip_unchanged():
    legacy = replace(
        _dispatch(operation=InspectRegister(0x1000, 4), approved=False, artifacts=()),
        operation_id="legacy-op",
    )
    document = json.loads(encode_request(legacy))
    assert document["request"]["operation"] == {
        "kind": "inspect_register", "parameters": {"address": 4096, "width_bytes": 4}
    }
    assert decode_request_frame(encode_request_frame(legacy)) == legacy
