"""Host-only push contracts; webpush is stubbed before every delivery attempt."""

from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException

from m1lab import notifications
from m1lab.core.models import (
    CommandKind,
    CommandStatus,
    JobCreate,
    OwnerCommand,
    ProcedureDraft,
    ReviewDisposition,
    ReviewRecord,
    SessionCreate,
    SessionPhase,
    TypedOperation,
    UsageUpdate,
    utc_now,
)
from m1lab.notifications import PushConfig, PushNotifications


ENDPOINT = "https://web.push.apple.com/synthetic-host-fixture"
SUBSCRIPTION = {"endpoint": ENDPOINT, "p256dh": "p" * 87, "auth": "a" * 22}
PRIVATE_DETAIL = "private synthetic investigation detail"


@pytest.fixture
def push_setup(core, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, "webpush", lambda **kwargs: sent.append(kwargs))
    key = tmp_path / "synthetic-vapid-private-key"
    key.write_text("Synthetic placeholder: stubbed webpush never reads this key.")
    config = PushConfig(
        public_key="k" * 87, private_key=str(key), subject="mailto:fixture@example.invalid",
    )
    session = core.create_session(SessionCreate(
        objective=PRIVATE_DETAIL, owner="synthetic-owner", host_identity="synthetic-host",
    ))
    push = PushNotifications(core, session.id, config, owner_login=session.owner)
    assert push.enabled
    return session, push, config, sent


def _command(core, session_id, kind):
    current = core.session(session_id)
    result = core.submit(OwnerCommand(
        session_id=session_id, owner=current.owner, expected_revision=current.revision,
        kind=kind, payload={},
    ))
    assert result.status is CommandStatus.APPLIED


def _await_approval(core, session_id):
    """Create an authoritative pending approval without dispatching any operation."""
    _command(core, session_id, CommandKind.START)
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session_id, title=PRIVATE_DETAIL,
        operations=[TypedOperation(
            kind="write_register", parameters={"address": "0x1000", "value": 1},
            mutates_target=True, timeout_seconds=1,
        )],
    ))
    now = utc_now()
    reviewer = core.create_job(JobCreate(
        session_id=session_id, kind="review",
        lease_expires_at=now + timedelta(minutes=1), deadline_at=now + timedelta(minutes=2),
        evidence_manifest={"mode": "synthetic-host-review", "review_target": {
            "procedure_id": procedure.procedure_id,
            "procedure_revision": procedure.revision, "procedure_digest": procedure.digest,
        }},
    ))
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    core.record_review(ReviewRecord(
        session_id=session_id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, procedure_digest=procedure.digest,
        reviewer_job_id=reviewer.id, disposition=ReviewDisposition.ACCEPTED,
    ))
    assert core.session(session_id).phase is SessionPhase.AWAITING_APPROVAL


def _workflow(core, session_id):
    return {
        "session": core.session(session_id),
        "events": core.events(session_id),
        **{kind: core.list_records(session_id, kind) for kind in (
            "procedures", "reviews", "approvals", "operations", "jobs",
        )},
    }


@pytest.mark.parametrize(
    ("category", "title", "body", "path"),
    [
        ("approval", "Approval requested", "Review a pending request in M1 Power Lab.", "/approvals"),
        ("recovery", "Recovery needs attention", "Review the current recovery state in M1 Power Lab.", "/overview"),
        ("budget", "Work allowance reached", "Review the current allowance in M1 Power Lab.", "/overview"),
        ("completion", "Investigation complete", "Review the current status in M1 Power Lab.", "/overview"),
    ],
)
def test_push_payloads_are_generic_and_delivery_claims_survive_new_dispatcher(
    core, push_setup, category, title, body, path,
):
    session, push, config, sent = push_setup
    push.subscribe(**SUBSCRIPTION)
    if category == "approval":
        _await_approval(core, session.id)
    elif category == "recovery":
        core.mark_usage_uncertain(session.id, "synthetic-source", PRIVATE_DETAIL)
    elif category == "budget":
        core.report_usage(UsageUpdate(
            report_id="synthetic-report", session_id=session.id, source_id="synthetic-source",
            input_tokens=core.snapshot(session.id).budget.token_limit, output_tokens=0,
            terminal=True,
        ))
    else:
        _command(core, session.id, CommandKind.COMPLETE)
    before = _workflow(core, session.id)

    push.dispatch_pending()

    assert sent
    tags = []
    for call in sent:
        payload = json.loads(call["data"])
        tags.append(payload["tag"])
        assert payload == {
            "category": category, "title": title, "body": body, "path": path,
            "tag": payload["tag"],
        }
        assert payload["tag"].startswith(f"m1lab-{category}-")
        assert PRIVATE_DETAIL not in call["data"]
        assert session.id not in call["data"]
        assert session.owner not in call["data"]
        assert call["subscription_info"]["endpoint"] == ENDPOINT
        assert call["timeout"] == 8
        assert call["ttl"] == 300
    assert len(tags) == len(set(tags))
    deliveries = len(sent)
    push.dispatch_pending()
    restored = PushNotifications(core, session.id, config, owner_login=session.owner)
    restored.dispatch_pending()
    assert len(sent) == deliveries
    assert _workflow(core, session.id) == before


def test_enrollment_skips_old_events_and_revocation_stops_delivery(core, push_setup):
    session, push, _, sent = push_setup
    assert not push.enrolled()
    core.mark_usage_uncertain(session.id, "before-enrollment", PRIVATE_DETAIL)
    push.subscribe(**SUBSCRIPTION)
    assert push.enrolled()
    push.dispatch_pending()
    assert sent == []

    core.mark_usage_uncertain(session.id, "after-enrollment", PRIVATE_DETAIL)
    push.dispatch_pending()
    assert len(sent) == 1
    assert push.unsubscribe(endpoint=ENDPOINT)
    assert not push.unsubscribe(endpoint=ENDPOINT)
    assert not push.enrolled()
    core.mark_usage_uncertain(session.id, "after-revocation", PRIVATE_DETAIL)
    push.dispatch_pending()
    assert len(sent) == 1

    push.subscribe(**SUBSCRIPTION)
    assert push.enrolled()
    push.dispatch_pending()
    assert len(sent) == 1
    core.mark_usage_uncertain(session.id, "after-reenrollment", PRIVATE_DETAIL)
    push.dispatch_pending()
    assert len(sent) == 2


@pytest.mark.parametrize("failure", ["unavailable", "expired"])
def test_failed_push_preserves_pending_approval_and_expiry_revokes_subscription(
    core, push_setup, monkeypatch, failure,
):
    session, push, _, sent = push_setup

    def fail_delivery(**kwargs):
        sent.append(kwargs)
        if failure == "expired":
            raise WebPushException("Synthetic endpoint expired", response=SimpleNamespace(status_code=410))
        raise ConnectionError("Synthetic push service unavailable")

    monkeypatch.setattr(notifications, "webpush", fail_delivery)
    push.subscribe(**SUBSCRIPTION)
    _await_approval(core, session.id)
    before = _workflow(core, session.id)
    push.dispatch_pending()
    assert len(sent) == 1
    assert _workflow(core, session.id) == before
    assert core.session(session.id).phase is SessionPhase.AWAITING_APPROVAL
    assert core.list_records(session.id, "approvals") == []
    assert core.list_records(session.id, "operations") == []
    delivery = core.journal.one(
        "SELECT status,attempts FROM push_deliveries WHERE session_id=?", (session.id,),
    )
    assert delivery["status"] == ("expired" if failure == "expired" else "failed")
    assert delivery["attempts"] == 1
    assert push.enrolled() is (failure != "expired")
    push.dispatch_pending()
    assert len(sent) == 1
    if failure == "expired":
        core.mark_usage_uncertain(session.id, "after-expiry", PRIVATE_DETAIL)
        push.dispatch_pending()
        assert len(sent) == 1
