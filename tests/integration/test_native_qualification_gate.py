"""Synthetic CoreApp state checks for the default-disabled native exception."""

from __future__ import annotations

from datetime import timedelta

import pytest

from m1lab.core.coordinator import CoreApp
from m1lab.core.errors import ConflictError
from m1lab.core.models import (
    CommandKind, CommandStatus, DispatchRequest, JobCreate, OwnerCommand,
    ProcedureDraft, ReviewDisposition, ReviewRecord, SessionCreate,
    TargetMode, TargetSnapshot, TypedOperation, utc_now,
)
from m1lab.paths import AppPaths


@pytest.fixture
def enabled_core(tmp_path):
    core = CoreApp.open(AppPaths(tmp_path / "enabled"), allow_native_qualification=True)
    try:
        yield core
    finally:
        core.close()


def _owner_command(core, session, kind, payload=None):
    result = core.submit(OwnerCommand(
        session_id=session.id, owner=session.owner,
        expected_revision=core.session(session.id).revision,
        kind=kind, payload=payload or {},
    ))
    assert result.status is CommandStatus.APPLIED, result.outcome


def _reviewed_candidate(core, *, kind="run_native_candidate", artifact_mismatch=False,
                        extra_artifact=False, omit_operation_digest=False,
                        attended=True, repeat_limit=1):
    session = core.create_session(SessionCreate(
        objective="Synthetic attended native qualification gate",
        owner="synthetic-owner", host_identity="synthetic-host",
        target_identity="synthetic-m1",
    ))
    _owner_command(core, session, CommandKind.START)
    digests = []
    for name in ("payload", "image-manifest", "launch-manifest"):
        artifact = core.publish_artifact(
            f"synthetic-{name}".encode(),
            provenance={"session_id": session.id, "role": name, "source": "host-test"},
        )
        digests.append(artifact.sha256)
    target = core.record_target(TargetSnapshot(
        session_id=session.id, identity="synthetic-m1", boot_epoch="synthetic-boot",
        mode=TargetMode.PROXY, configuration_digest="a" * 64,
        capabilities={"run_native_candidate"},
        observed_at=utc_now(), fresh_until=utc_now() + timedelta(seconds=20),
    ))
    parameters = dict(zip(
        ("payload_sha256", "image_manifest_sha256", "launch_manifest_sha256"), digests,
    ))
    if artifact_mismatch:
        parameters["launch_manifest_sha256"] = "f" * 64
    reviewed_digests = set(digests)
    if omit_operation_digest:
        reviewed_digests.remove(digests[-1])
    if extra_artifact:
        extra = core.publish_artifact(
            b"synthetic fixed launcher configuration",
            provenance={"session_id": session.id, "role": "launcher-config", "source": "host-test"},
        )
        reviewed_digests.add(extra.sha256)
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session.id, title="One attended synthetic qualification",
        operations=[TypedOperation(
            kind=kind, parameters=parameters, mutates_target=True, timeout_seconds=120,
        )],
        prerequisites={"run_native_candidate"}, artifact_digests=reviewed_digests,
        physical_attendance="required",
    ))
    now = utc_now()
    reviewer = core.create_job(JobCreate(
        session_id=session.id, kind="review",
        evidence_manifest={"review_target": {
            "procedure_id": procedure.procedure_id,
            "procedure_revision": procedure.revision,
            "procedure_digest": procedure.digest,
        }},
        lease_expires_at=now + timedelta(minutes=1),
        deadline_at=now + timedelta(minutes=2),
    ))
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    core.record_review(ReviewRecord(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, procedure_digest=procedure.digest,
        reviewer_job_id=reviewer.id, disposition=ReviewDisposition.ACCEPTED,
    ))
    _owner_command(core, session, CommandKind.APPROVE, {
        "procedure_id": procedure.procedure_id,
        "procedure_revision": procedure.revision,
        "scope": {
            "target_identity": target.identity, "boot_epoch": target.boot_epoch,
            "configuration_digest": target.configuration_digest,
            "repeat_limit": repeat_limit,
            "expires_at": (utc_now() + timedelta(minutes=5)).isoformat(),
            "physical_attendance_confirmed": attended,
        },
    })
    request = DispatchRequest(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, target_snapshot_id=target.id,
        adapter_mode=TargetMode.PROXY,
    )
    return session, request


def test_default_core_refuses_proxy_qualification(core):
    session, request = _reviewed_candidate(core)
    authorization = core.authorize_operation(request)
    assert not authorization.eligibility.eligible
    assert authorization.envelope is None
    assert "disabled" in "; ".join(authorization.eligibility.reasons)
    assert not core.list_records(session.id, "operations")


def test_enabled_core_records_only_exact_attended_intent(enabled_core):
    session, request = _reviewed_candidate(enabled_core)
    authorization = enabled_core.authorize_operation(request)
    assert authorization.eligibility.eligible, authorization.eligibility.reasons
    envelope = authorization.envelope
    assert envelope is not None
    assert envelope.adapter_mode is TargetMode.PROXY
    assert len(envelope.operations) == 1
    assert envelope.approval_id and envelope.review_id
    enabled_core.mark_dispatched(envelope)
    operation = enabled_core.list_records(session.id, "operations")[0]
    assert operation.state.value == "dispatched"
    assert enabled_core.list_records(session.id, "approvals")[0].uses == 1


def test_extra_published_reviewed_artifact_does_not_block_candidate(enabled_core):
    session, request = _reviewed_candidate(enabled_core, extra_artifact=True)
    authorization = enabled_core.authorize_operation(request)
    assert authorization.eligibility.eligible, authorization.eligibility.reasons
    assert authorization.envelope is not None
    assert len(authorization.envelope.artifact_digests) == 4


@pytest.mark.parametrize("variation", ["wrong_op", "artifact", "missing_digest", "attendance", "repeat"])
def test_enabled_core_refuses_nonexact_qualification(enabled_core, variation):
    session, request = _reviewed_candidate(
        enabled_core,
        kind="inspect_register" if variation == "wrong_op" else "run_native_candidate",
        artifact_mismatch=variation == "artifact",
        omit_operation_digest=variation == "missing_digest",
        attended=variation != "attendance",
        repeat_limit=2 if variation == "repeat" else 1,
    )
    authorization = enabled_core.authorize_operation(request)
    assert not authorization.eligibility.eligible
    assert authorization.envelope is None
    assert not enabled_core.list_records(session.id, "operations")


@pytest.mark.parametrize("interruption", ["pause", "usage_hold", "revoke"])
def test_dispatch_rechecks_intervening_owner_state(enabled_core, interruption):
    session, request = _reviewed_candidate(enabled_core)
    authorization = enabled_core.authorize_operation(request)
    envelope = authorization.envelope
    assert envelope is not None
    if interruption == "pause":
        _owner_command(enabled_core, session, CommandKind.PAUSE)
    elif interruption == "usage_hold":
        enabled_core.mark_usage_uncertain(session.id, "synthetic-source", "synthetic usage hold")
    else:
        _owner_command(enabled_core, session, CommandKind.REVOKE,
                       {"approval_id": envelope.approval_id})

    with pytest.raises(ConflictError):
        enabled_core.mark_dispatched(envelope)
    assert enabled_core.list_records(session.id, "operations")[0].state.value == "intent"
    assert enabled_core.list_records(session.id, "approvals")[0].uses == 0
