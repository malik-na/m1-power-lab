from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from m1lab.core.errors import ConflictError, ValidationError
from m1lab.core.models import (
    CommandKind,
    CommandStatus,
    DispatchRequest,
    JobCreate,
    OperationOutcome,
    OperationState,
    OwnerCommand,
    ProcedureDraft,
    ReviewDisposition,
    ReviewRecord,
    SessionCreate,
    SessionPhase,
    TargetMode,
    TargetSnapshot,
    TypedOperation,
    utc_now,
)
from m1lab.application import CoordinatorFacade
from m1lab.web.facade import Owner


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        self.value = value


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr("m1lab.core.budgets.time.monotonic", value.monotonic)
    return value


def create_session(core):
    return core.create_session(
        SessionCreate(
            objective="Characterize M1 power behavior",
            owner="owner",
            host_identity="thinkpad",
            active_seconds=10_000,
            token_limit=1_000_000,
        )
    )


def command(core, session_id, kind, payload=None):
    session = core.session(session_id)
    return core.submit(
        OwnerCommand(
            session_id=session_id,
            owner=session.owner,
            kind=kind,
            expected_revision=session.revision,
            payload=payload or {},
        )
    )


def job_request(session_id, kind):
    now = utc_now()
    return JobCreate(
        session_id=session_id,
        kind=kind,
        lease_expires_at=now + timedelta(minutes=5),
        deadline_at=now + timedelta(minutes=10),
    )


def procedure(session_id, *, mutates=True):
    return ProcedureDraft(
        session_id=session_id,
        title="Bounded register experiment",
        operations=[
            TypedOperation(
                kind="write_register" if mutates else "inspect_register",
                parameters={"address": "0x1000"},
                mutates_target=mutates,
                timeout_seconds=10,
            )
        ],
        prerequisites={"write_register" if mutates else "inspect_register"},
        abort_conditions=["target identity changes"],
        recovery={"method": "reboot"},
    )


def complete_review(core, record, disposition=ReviewDisposition.ACCEPTED):
    reviewer = core.create_job(job_request(record.session_id, "review"))
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    return core.record_review(
        ReviewRecord(
            session_id=record.session_id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            procedure_digest=record.digest,
            reviewer_job_id=reviewer.id,
            disposition=disposition,
        )
    )


def test_review_and_approval_waits_have_durable_phases_and_account_only_live_work(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    clock.set(10)

    record = core.register_procedure(procedure(session.id, mutates=True))
    waiting = core.snapshot(session.id)
    assert (waiting.session.phase, waiting.session.revision) == (
        SessionPhase.AWAITING_REVIEW,
        3,
    )
    assert waiting.budget.active_seconds_used == pytest.approx(10)

    with pytest.raises(ConflictError):
        core.create_job(job_request(session.id, "investigate"))

    clock.set(100)
    first = core.create_job(job_request(session.id, "review"))
    clock.set(103)
    second = core.create_job(job_request(session.id, "chat"))
    core.update_job(first.id, state="running")
    clock.set(108)
    core.update_job(first.id, state="completed")
    assert core.snapshot(session.id).budget.active_seconds_used == pytest.approx(18)
    clock.set(112)
    core.update_job(second.id, state="failed")
    assert core.snapshot(session.id).budget.active_seconds_used == pytest.approx(22)

    review = core.record_review(
        ReviewRecord(
            session_id=session.id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            procedure_digest=record.digest,
            reviewer_job_id=first.id,
            disposition=ReviewDisposition.ACCEPTED,
        )
    )
    assert review.disposition is ReviewDisposition.ACCEPTED
    awaiting = core.session(session.id)
    assert (awaiting.phase, awaiting.revision) == (SessionPhase.AWAITING_APPROVAL, 4)

    approval = command(
        core,
        session.id,
        CommandKind.APPROVE,
        {
            "procedure_id": record.procedure_id,
            "procedure_revision": record.revision,
            "procedure_digest": record.digest,
            "scope": {
                "target_identity": "m1",
                "repeat_limit": 1,
                "expires_at": (utc_now() + timedelta(hours=1)).isoformat(),
            },
        },
    )
    assert approval.status is CommandStatus.APPLIED
    assert (core.session(session.id).phase, core.session(session.id).revision) == (
        SessionPhase.INVESTIGATING,
        5,
    )

    phase_events = [event for event in core.events(session.id) if event.kind == "session.phase_changed"]
    assert [event.data["phase"] for event in phase_events] == [
        "investigating",
        "awaiting_review",
        "awaiting_approval",
        "investigating",
    ]


@pytest.mark.parametrize(
    ("mutates", "disposition", "expected"),
    [
        (False, ReviewDisposition.ACCEPTED, SessionPhase.INVESTIGATING),
        (True, ReviewDisposition.CHANGES_REQUIRED, SessionPhase.INVESTIGATING),
        (True, ReviewDisposition.REJECTED, SessionPhase.INVESTIGATING),
    ],
)
def test_non_mutating_or_unaccepted_review_returns_to_investigation(
    core, clock, mutates, disposition, expected
):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    record = core.register_procedure(procedure(session.id, mutates=mutates))
    complete_review(core, record, disposition)
    current = core.session(session.id)
    assert (current.phase, current.revision) == (expected, 4)


def test_dispatch_outcome_and_unknown_reconciliation_advance_phase_and_revision(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    target = core.record_target(
        TargetSnapshot(
            session_id=session.id,
            identity="m1",
            boot_epoch="boot-1",
            mode=TargetMode.REPLAY,
            configuration_digest="config-1",
            capabilities={"inspect_register"},
        )
    )
    record = core.register_procedure(procedure(session.id, mutates=False))
    complete_review(core, record)
    authorization = core.authorize_operation(
        DispatchRequest(
            session_id=session.id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
        )
    )
    assert authorization.eligibility.eligible
    assert authorization.envelope is not None
    assert core.list_records(session.id, "operations")[0].state is OperationState.INTENT

    core.mark_dispatched(authorization.envelope)
    assert core.list_records(session.id, "operations")[0].state is OperationState.DISPATCHED
    assert (core.session(session.id).phase, core.session(session.id).revision) == (
        SessionPhase.EXECUTING,
        5,
    )
    core.finish_operation(
        authorization.envelope.operation_id,
        OperationOutcome(state=OperationState.UNKNOWN_EFFECT),
    )
    assert core.list_records(session.id, "operations")[0].state is OperationState.UNKNOWN_EFFECT
    assert (core.session(session.id).phase, core.session(session.id).revision) == (
        SessionPhase.RECOVERING,
        6,
    )
    retry = core.authorize_operation(
        DispatchRequest(
            session_id=session.id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
        )
    )
    assert not retry.eligibility.eligible
    assert any("is unresolved (unknown_effect)" in reason for reason in retry.eligibility.reasons)
    with pytest.raises(ValidationError, match="reconciliation requires evidence artifacts"):
        core.reconcile_operation(
            authorization.envelope.operation_id,
            resolved_state=OperationState.NO_EFFECT,
            evidence_artifact_ids=[],
            note="",
        )
    evidence = core.publish_artifact(
        b"target rebooted and register state verified",
        media_type="text/plain",
        provenance={"session_id": session.id, "record_type": "reconciliation"},
    )
    core.reconcile_operation(
        authorization.envelope.operation_id,
        resolved_state=OperationState.NO_EFFECT,
        evidence_artifact_ids=[evidence.id],
        note="Fresh inspection confirms no effect.",
    )
    assert (core.session(session.id).phase, core.session(session.id).revision) == (
        SessionPhase.INTERPRETING,
        7,
    )
    operation = core.list_records(session.id, "operations")[0]
    assert operation.state is OperationState.RECONCILED


def test_denial_requires_exact_pending_procedure_and_returns_to_investigation(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    record = core.register_procedure(procedure(session.id, mutates=True))
    complete_review(core, record)

    inexact = command(
        core,
        session.id,
        CommandKind.DENY,
        {"procedure_id": record.procedure_id},
    )
    assert inexact.status is CommandStatus.REJECTED
    assert core.session(session.id).phase is SessionPhase.AWAITING_APPROVAL

    exact = command(
        core,
        session.id,
        CommandKind.DENY,
        {
            "procedure_id": record.procedure_id,
            "procedure_revision": record.revision,
            "procedure_digest": record.digest,
        },
    )
    assert exact.status is CommandStatus.APPLIED
    assert core.session(session.id).phase is SessionPhase.INVESTIGATING


def test_operator_view_exposes_exact_wait_and_only_current_approval_controls(core, clock):
    session = create_session(core)
    owner = Owner(login=session.owner, display_name="Owner", source="local")
    facade = CoordinatorFacade(core, session.id)
    command(core, session.id, CommandKind.START)
    target = core.record_target(
        TargetSnapshot(
            session_id=session.id,
            identity="m1",
            boot_epoch="boot-1",
            mode=TargetMode.REPLAY,
            configuration_digest="config-1",
            capabilities={"write_register"},
        )
    )
    assert target.identity == "m1"
    record = core.register_procedure(procedure(session.id, mutates=True))

    review_wait = asyncio.run(facade.get_view("overview", owner))
    assert review_wait["session"]["state"] == "awaiting_review"
    assert review_wait["approvals"] == []

    complete_review(core, record)
    approval_wait = asyncio.run(facade.get_view("approvals", owner))
    assert approval_wait["session"]["state"] == "awaiting_approval"
    assert len(approval_wait["approvals"]) == 1

    command(
        core,
        session.id,
        CommandKind.DENY,
        {
            "procedure_id": record.procedure_id,
            "procedure_revision": record.revision,
            "procedure_digest": record.digest,
        },
    )
    after_denial = asyncio.run(facade.get_view("approvals", owner))
    assert after_denial["session"]["state"] == "investigating"
    assert after_denial["approvals"] == []


def test_restart_moves_dispatched_operation_to_recovery_with_a_new_revision(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    target = core.record_target(
        TargetSnapshot(
            session_id=session.id,
            identity="m1",
            boot_epoch="boot-1",
            mode=TargetMode.REPLAY,
            configuration_digest="config-1",
            capabilities={"inspect_register"},
        )
    )
    record = core.register_procedure(procedure(session.id, mutates=False))
    complete_review(core, record)
    authorization = core.authorize_operation(
        DispatchRequest(
            session_id=session.id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
        )
    )
    assert authorization.envelope is not None
    core.mark_dispatched(authorization.envelope)

    report = core.reconcile()

    assert report.unknown_operation_ids == [authorization.envelope.operation_id]
    recovered = core.session(session.id)
    assert (recovered.phase, recovered.revision) == (SessionPhase.RECOVERING, 6)
    operation = core.list_records(session.id, "operations")[0]
    assert operation.state is OperationState.UNKNOWN_EFFECT


def test_restart_resolves_undispatched_intent_as_no_effect(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    target = core.record_target(
        TargetSnapshot(
            session_id=session.id,
            identity="m1",
            boot_epoch="boot-1",
            mode=TargetMode.REPLAY,
            configuration_digest="config-1",
            capabilities={"inspect_register"},
        )
    )
    record = core.register_procedure(procedure(session.id, mutates=False))
    complete_review(core, record)
    authorization = core.authorize_operation(
        DispatchRequest(
            session_id=session.id,
            procedure_id=record.procedure_id,
            procedure_revision=record.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
        )
    )
    assert authorization.envelope is not None
    assert core.list_records(session.id, "operations")[0].state is OperationState.INTENT

    report = core.reconcile()

    assert report.no_effect_operation_ids == [authorization.envelope.operation_id]
    assert core.list_records(session.id, "operations")[0].state is OperationState.NO_EFFECT
    assert core.session(session.id).phase is SessionPhase.INTERPRETING


def test_restart_closes_wait_clock_after_final_live_job_becomes_unknown(core, clock):
    session = create_session(core)
    command(core, session.id, CommandKind.START)
    clock.set(10)
    core.register_procedure(procedure(session.id, mutates=False))
    clock.set(20)
    reviewer = core.create_job(job_request(session.id, "review"))
    clock.set(25)

    core.reconcile()

    snapshot = core.snapshot(session.id)
    assert snapshot.session.phase is SessionPhase.AWAITING_REVIEW
    assert snapshot.budget.active_seconds_used == pytest.approx(15)
    assert core.job(reviewer.id).state == "unknown"
    clock.set(100)
    assert core.snapshot(session.id).budget.active_seconds_used == pytest.approx(15)
