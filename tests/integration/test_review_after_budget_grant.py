"""A completed exact review survives a settled allowance exhaustion."""

from __future__ import annotations

from datetime import timedelta

import pytest

from m1lab.core.errors import ConflictError
from m1lab.core.models import (
    CommandKind, CommandStatus, JobCreate, OwnerCommand, ProcedureDraft,
    ReviewDisposition, ReviewRecord, SessionCreate, SessionPhase,
    TypedOperation, UsageUpdate, utc_now,
)


def _command(core, session, kind, payload=None):
    result = core.submit(OwnerCommand(
        session_id=session.id, owner=session.owner,
        expected_revision=core.session(session.id).revision,
        kind=kind, payload=payload or {},
    ))
    assert result.status is CommandStatus.APPLIED, result.outcome


def _completed_exact_review(core):
    session = core.create_session(SessionCreate(
        objective="Synthetic budget review continuation", owner="test-owner",
        host_identity="synthetic-host", token_limit=10,
    ))
    _command(core, session, CommandKind.START)
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session.id, title="Reviewed synthetic operation",
        operations=[TypedOperation(
            kind="simulate_boot", parameters={"next_boot_epoch": "synthetic-next"},
            mutates_target=True, timeout_seconds=5,
        )],
    ))
    now = utc_now()
    reviewer = core.create_job(JobCreate(
        session_id=session.id, kind="review",
        lease_expires_at=now + timedelta(minutes=1),
        deadline_at=now + timedelta(minutes=2),
        evidence_manifest={"review_target": {
            "procedure_id": procedure.procedure_id,
            "procedure_revision": procedure.revision,
            "procedure_digest": procedure.digest,
        }},
    ))
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    review = ReviewRecord(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, procedure_digest=procedure.digest,
        reviewer_job_id=reviewer.id, disposition=ReviewDisposition.ACCEPTED,
    )
    core.report_usage(UsageUpdate(
        report_id="synthetic-exhaustion", session_id=session.id,
        source_id="synthetic-reviewer", input_tokens=10, output_tokens=0,
        terminal=True,
    ))
    assert core.session(session.id).phase is SessionPhase.BUDGET_EXHAUSTED
    return session, review


def test_exact_completed_review_requires_explicit_token_grant(core):
    session, review = _completed_exact_review(core)
    with pytest.raises(ConflictError, match="awaiting review"):
        core.record_review(review)
    assert core.list_records(session.id, "reviews") == []

    _command(core, session, CommandKind.GRANT_TOKENS, {"tokens": 20})
    assert core.session(session.id).phase is SessionPhase.BUDGET_EXHAUSTED
    assert core.snapshot(session.id).budget.admission_open
    recorded = core.record_review(review)

    assert recorded.id == review.id
    assert core.session(session.id).phase is SessionPhase.AWAITING_APPROVAL
    assert len(core.list_records(session.id, "reviews")) == 1


def test_usage_uncertainty_still_blocks_review_after_grant(core):
    session, review = _completed_exact_review(core)
    _command(core, session, CommandKind.GRANT_TOKENS, {"tokens": 20})
    core.mark_usage_uncertain(session.id, "synthetic-reviewer", "synthetic unsettled usage")
    assert not core.snapshot(session.id).budget.admission_open
    with pytest.raises(ConflictError, match="awaiting review"):
        core.record_review(review)
    assert core.list_records(session.id, "reviews") == []


def test_paused_session_still_refuses_review_with_open_allowance(core):
    session, review = _completed_exact_review(core)
    _command(core, session, CommandKind.GRANT_TOKENS, {"tokens": 20})
    _command(core, session, CommandKind.PAUSE)
    assert core.session(session.id).phase is SessionPhase.PAUSED
    assert core.snapshot(session.id).budget.admission_open
    with pytest.raises(ConflictError, match="awaiting review"):
        core.record_review(review)
    assert core.list_records(session.id, "reviews") == []
