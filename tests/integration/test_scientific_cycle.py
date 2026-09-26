"""Synthetic host qualification only; no model calls or physical M1 evidence."""

from __future__ import annotations

from datetime import timedelta
import json

import pytest

from m1lab.core.coordinator import CoreApp
from m1lab.core.errors import ValidationError
from m1lab.core.models import (
    CommandKind,
    CommandStatus,
    DispatchRequest,
    JobCreate,
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
from m1lab.paths import AppPaths
from m1lab.science import (
    ClaimEvidence,
    DecisionRecord,
    EvidenceDirection,
    ExperimentProtocol,
    HypothesisRecord,
    MeasurementProvenance,
    ObservationRecord,
    OutcomeCategory,
    ProtocolAdherence,
    RedesignCheckpointRecord,
    ScientificRecordStore,
    StudyMode,
    derive_power_result,
)


def _hypothesis(session_id, statement):
    return HypothesisRecord(
        session_id=session_id,
        mode=StudyMode.EXPLORATION,
        statement=statement,
        proposed_mechanism="Synthetic fixture mechanism; no physical claim.",
        predicted_effect="At least 10% lower paired power in the synthetic fixture.",
        primary_metric="power_watts",
        falsifiers=("The paired reduction is below 10%.",),
    )


def _protocol(hypothesis, *, checkpoint_id=None):
    return ExperimentProtocol(
        session_id=hypothesis.session_id,
        hypothesis_id=hypothesis.id,
        mode=hypothesis.mode,
        title="Host-only paired replay",
        workload="deterministic synthetic samples",
        baseline_configuration={"fixture": "baseline"},
        changed_configuration={"fixture": "changed"},
        baseline_configuration_digest="synthetic-baseline",
        changed_configuration_digest="synthetic-changed",
        controlled_conditions=("No hardware or model invocation",),
        block_order="baseline then changed in each synthetic block",
        independent_restart="distinct synthetic boot epoch per block",
        warmup="not applicable to replay",
        sampling="one already averaged watts value per synthetic arm",
        stopping_rule="exactly two independent paired blocks",
        frozen_at=utc_now(),
        redesign_checkpoint_id=checkpoint_id,
    )


def _publish_result(core, store, hypothesis, protocol, *, changed=(9.0, 9.0), valid=True):
    """Derive real host records from explicit, labeled synthetic raw values."""
    observations = []
    pairs = []
    for block_number, changed_watts in enumerate(changed):
        block_observations = []
        for arm, watts in (("baseline", 10.0), ("changed", changed_watts)):
            raw = core.publish_artifact(
                json.dumps({"synthetic": True, "arm": arm, "watts": watts}).encode(),
                media_type="application/json",
                provenance={
                    "session_id": hypothesis.session_id,
                    "evidence_scope": "host_only",
                    "source": "deterministic scientific-cycle fixture",
                },
            )
            observation = ObservationRecord(
                session_id=hypothesis.session_id,
                hypothesis_id=hypothesis.id,
                protocol_id=protocol.id,
                mode=hypothesis.mode,
                arm=arm,
                independent_block_id=f"{protocol.id}-block-{block_number}",
                description="Synthetic host fixture, not a physical power measurement.",
                measurements={"power_watts": watts},
                provenance=MeasurementProvenance(
                    source="synthetic host replay",
                    target_identity="synthetic-m1",
                    target_boot_epoch=f"synthetic-boot-{block_number}",
                    target_configuration_digest=(
                        protocol.baseline_configuration_digest
                        if arm == "baseline"
                        else protocol.changed_configuration_digest
                    ),
                    collector_host="host-test",
                    clock="synthetic sample order",
                    units={"power_watts": "W"},
                    raw_artifact_ids=(raw.id,),
                    raw_artifact_digests=(raw.sha256,),
                ),
            )
            store.publish(observation)
            observations.append(observation)
            block_observations.append(observation.id)
        pairs.append(tuple(block_observations))
    result = derive_power_result(
        session_id=hypothesis.session_id,
        hypothesis_id=hypothesis.id,
        hypothesis=hypothesis,
        protocol=protocol,
        observations=observations,
        observation_pairs=pairs,
        adherence=ProtocolAdherence(
            protocol_id=protocol.id,
            protocol_frozen_before_collection=True,
            independently_restarted_blocks=2,
            workload_matched=True,
            configuration_matched=True,
            sampling_complete=valid,
            violations=() if valid else ("Synthetic incomplete collection",),
        ),
    )
    store.publish(result)
    return result


def test_observations_change_the_decision_and_survive_reopening_the_brief(tmp_path):
    paths = AppPaths(tmp_path / "scientific-cycle")
    core = CoreApp.open(paths)
    try:
        session = core.create_session(
            SessionCreate(objective="Host-only scientific cycle", owner="owner", host_identity="host")
        )
        store = ScientificRecordStore(core)
        selected = _hypothesis(session.id, "Synthetic mechanism A remains the leading explanation.")
        competitor = _hypothesis(session.id, "Synthetic mechanism B is an unresolved competitor.")
        store.publish(selected)
        # Publication order must not override the later explicit decision about A.
        store.publish(competitor)
        protocol = _protocol(selected)
        store.publish(protocol)
        result = _publish_result(core, store, selected, protocol, changed=(8.0, 8.0))
        assert result.outcome is OutcomeCategory.POSITIVE
        assert len(result.observation_ids) == 4

        support = ClaimEvidence(
            session_id=session.id,
            hypothesis_id=selected.id,
            mode=selected.mode,
            claim="The synthetic paired reduction exceeds the frozen threshold.",
            direction=EvidenceDirection.SUPPORTS,
            strength="strong",
            rationale="Both synthetic pairs changed from 10 W to 8 W.",
            record_refs=(result.id,),
            limitations=("Host logic qualification only",),
        )
        counter = ClaimEvidence(
            session_id=session.id,
            hypothesis_id=selected.id,
            mode=selected.mode,
            claim="The same result does not distinguish the competing synthetic mechanism.",
            direction=EvidenceDirection.COUNTERS,
            strength="moderate",
            rationale="Mechanism B predicts the same reduction in this fixture.",
            record_refs=(competitor.id, result.id),
            limitations=("No physical M1 observation",),
        )
        store.publish(support)
        store.publish(counter)
        decision = DecisionRecord(
            session_id=session.id,
            hypothesis_id=selected.id,
            protocol_id=protocol.id,
            derived_result_id=result.id,
            mode=selected.mode,
            outcome=result.outcome,
            conclusion="Synthetic A is supported, but the competing explanation remains unresolved.",
            decision_delta="The paired replay supports A; next distinguish A from B.",
            next_action="Reuse the existing synthetic capture for a cheaper discriminating analysis.",
            evidence=(support,),
            counterevidence=(counter,),
            unresolved_uncertainties=("Synthetic evidence cannot establish physical M1 behavior.",),
        )
        # A typed decision cannot relabel the deterministic result as negative.
        with pytest.raises(ValueError, match="outcome must match"):
            store.publish(decision.model_copy(update={"outcome": OutcomeCategory.NEGATIVE}))
        store.publish(decision)
        published = store.list(session.id)
        before = store.brief(published)
        identities = {item.record.id: (item.artifact_id, item.sha256) for item in published}
    finally:
        core.close()

    reopened = CoreApp.open(paths)
    try:
        store = ScientificRecordStore(reopened)
        restored = store.list(session.id)
        after = store.brief(restored)
        assert {item.record.id: (item.artifact_id, item.sha256) for item in restored} == identities
        assert after == before
        records = {item.record.id: item.record for item in restored}
        assert records[decision.id].derived_result_id == result.id
        assert set(records[result.id].observation_ids) == set(result.observation_ids)
        assert {item["hypothesis_id"] for item in after.competing_hypotheses} == {
            selected.id, competitor.id,
        }
        assert all(item["prediction"] for item in after.competing_hypotheses)
        assert any(result.id in item for item in after.strongest_support)
        assert any(competitor.id in item for item in after.strongest_counterevidence)
        assert after.finding == decision.conclusion
        assert after.decision_delta == decision.decision_delta
        assert after.next_action == decision.next_action
        assert after.limitations == decision.unresolved_uncertainties
        assert after.resource_limits
        assert after.hypothesis == selected.statement
    finally:
        reopened.close()


@pytest.mark.parametrize("invalid_between", [False, True], ids=["consecutive", "invalid-does-not-reset"])
def test_two_valid_inconclusive_results_require_redesign_and_separate_review(core, invalid_between):
    session = core.create_session(
        SessionCreate(objective="Host-only redesign qualification", owner="owner", host_identity="host")
    )
    started = core.submit(
        OwnerCommand(
            session_id=session.id, owner=session.owner, kind=CommandKind.START,
            expected_revision=session.revision, payload={},
        )
    )
    assert started.status is CommandStatus.APPLIED
    store = ScientificRecordStore(core)
    hypothesis = _hypothesis(session.id, "Synthetic mechanism requires a discriminating experiment.")
    store.publish(hypothesis)
    first_protocol = _protocol(hypothesis)
    store.publish(first_protocol)
    # Exactly 10% reduction has zero threshold contrast: valid, but inconclusive.
    first = _publish_result(core, store, hypothesis, first_protocol)
    assert first.outcome is OutcomeCategory.INCONCLUSIVE
    assert not store.brief(store.list(session.id)).redesign_checkpoint_required

    if invalid_between:
        invalid_protocol = _protocol(hypothesis)
        store.publish(invalid_protocol)
        invalid = _publish_result(core, store, hypothesis, invalid_protocol, valid=False)
        assert invalid.outcome is OutcomeCategory.INVALID
        brief = store.brief(store.list(session.id))
        assert not brief.redesign_checkpoint_required
        assert any(invalid.id in item and "invalid" in item for item in brief.failed_attempts)

    second_protocol = _protocol(hypothesis)
    store.publish(second_protocol)
    second = _publish_result(core, store, hypothesis, second_protocol)
    assert second.outcome is OutcomeCategory.INCONCLUSIVE
    brief = store.brief(store.list(session.id))
    assert brief.redesign_checkpoint_required
    assert brief.uninformative_streak == 2
    assert brief.redesign_hypothesis_ids == (hypothesis.id,)
    assert all(any(result.id in item for item in brief.failed_attempts) for result in (first, second))

    with pytest.raises(ValueError, match="redesign checkpoint"):
        store.publish(_protocol(hypothesis))
    draft = ProcedureDraft(
        session_id=session.id,
        title="Synthetic replay follow-up",
        hypothesis_id=hypothesis.id,
        protocol_id=second_protocol.id,
        operations=[TypedOperation(
            kind="inspect_register", parameters={"address": "0x1000"},
            mutates_target=False, timeout_seconds=1,
        )],
        prerequisites={"inspect_register"},
    )
    with pytest.raises(ValidationError, match="redesign checkpoint"):
        core.register_procedure(draft)
    assert core.list_records(session.id, "procedures") == []

    checkpoint = RedesignCheckpointRecord(
        session_id=session.id, hypothesis_id=hypothesis.id, mode=hypothesis.mode,
        triggering_result_ids=(first.id, second.id),
        findings="The synthetic contrasts lie exactly on the threshold.",
        redesign="Use a synthetic contrast that distinguishes A from B before repeating.",
    )
    with pytest.raises(ValueError, match="two latest inconclusive"):
        store.publish(checkpoint.model_copy(update={"triggering_result_ids": (second.id, first.id)}))
    store.publish(checkpoint)
    with pytest.raises(ValueError, match="cite its checkpoint"):
        store.publish(_protocol(hypothesis))
    redesigned = _protocol(hypothesis, checkpoint_id=checkpoint.id)
    store.publish(redesigned)
    procedure = core.register_procedure(draft.model_copy(update={
        "protocol_id": redesigned.id, "redesign_checkpoint_id": checkpoint.id,
    }))
    assert core.session(session.id).phase is SessionPhase.AWAITING_REVIEW
    target = core.record_target(TargetSnapshot(
        session_id=session.id, identity="synthetic-m1", boot_epoch="synthetic-boot",
        mode=TargetMode.REPLAY, configuration_digest="synthetic-changed",
        capabilities={"inspect_register"},
    ))
    request = DispatchRequest(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, target_snapshot_id=target.id,
        adapter_mode=TargetMode.REPLAY,
    )
    denied = core.authorize_operation(request)
    assert not denied.eligibility.eligible
    assert "exact procedure revision lacks an accepted review" in denied.eligibility.reasons
    assert core.list_records(session.id, "operations") == []

    now = utc_now()
    reviewer = core.create_job(JobCreate(
        session_id=session.id, kind="review",
        lease_expires_at=now + timedelta(minutes=1), deadline_at=now + timedelta(minutes=2),
        evidence_manifest={"mode": "synthetic-host-review", "review_target": {
            "procedure_id": procedure.procedure_id,
            "procedure_revision": procedure.revision, "procedure_digest": procedure.digest,
        }},
    ))
    review = ReviewRecord(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, procedure_digest=procedure.digest,
        reviewer_job_id=reviewer.id, disposition=ReviewDisposition.ACCEPTED,
    )
    with pytest.raises(ValidationError, match="completed review job"):
        core.record_review(review)
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    core.record_review(review)
    authorized = core.authorize_operation(request)
    assert authorized.eligibility.eligible, authorized.eligibility.reasons
    assert authorized.envelope is not None
    # Stop at host authorization: no adapter or hardware is invoked.
