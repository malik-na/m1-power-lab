"""Synthetic runtime-boundary resume checks; no model or worker process runs."""

from __future__ import annotations

import asyncio

import pytest

from m1lab.adapters import JobHandle, JobStatus, RuntimeEvent, SandboxMode, TokenUsage
from m1lab.core.coordinator import CoreApp
from m1lab.core.errors import ConflictError
from m1lab.core.models import CommandKind, CommandStatus, OwnerCommand, SessionCreate
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.prompts import OUTPUT_SCHEMA
from m1lab.investigator.service import InvestigationOrchestrator
from m1lab.paths import AppPaths
from m1lab.science import (
    ClaimEvidence,
    DecisionRecord,
    EvidenceDirection,
    ExperimentProtocol,
    HypothesisRecord,
    OutcomeCategory,
    ProtocolAdherence,
    ScientificRecordStore,
    StudyMode,
    derive_power_result,
)


THREAD_ID = "synthetic-persisted-thread"
QUESTION = "The failed synthetic collection leaves mechanism A unresolved."


class ScriptedRuntime:
    """Finite recorded outcomes; never starts a process or reaches a provider."""

    def __init__(self, label, outcome, total_tokens):
        self.label = label
        self.outcome = outcome
        self.total_tokens = total_tokens
        self.calls = []
        self.closed = False
        self.handle = None

    async def start_job(self, request):
        self.calls.append(("start", None, request))
        return self._handle(resumed=False)

    async def resume_job(self, thread_id, request):
        self.calls.append(("resume", thread_id, request))
        assert thread_id == THREAD_ID
        return self._handle(resumed=True)

    def _handle(self, *, resumed):
        self.handle = JobHandle(
            self.label, THREAD_ID, f"turn-{self.label}", JobStatus.RUNNING, resumed,
        )
        return self.handle

    async def events(self, job_id):
        assert job_id == self.label
        yield RuntimeEvent(
            sequence=1, job_id=job_id, method="item/completed", thread_id=THREAD_ID,
            turn_id=self.handle.turn_id,
            payload={"text": "Synthetic proposal only. Owner approval is still required."},
        )

    def status(self, job_id):
        assert job_id == self.label
        return JobHandle(
            self.label, THREAD_ID, self.handle.turn_id, self.outcome, self.handle.resumed,
        )

    def usage(self, job_id):
        assert job_id == self.label
        return None if self.total_tokens is None else TokenUsage(
            total_tokens=self.total_tokens, cumulative=True,
        )

    async def interrupt(self, job_id):
        raise AssertionError(f"finite scripted runtime unexpectedly interrupted: {job_id}")

    async def close(self):
        self.closed = True


def _publish_failed_science(core, session_id):
    store = ScientificRecordStore(core)
    hypothesis = HypothesisRecord(
        session_id=session_id, mode=StudyMode.EXPLORATION,
        statement="Synthetic mechanism A reduces paired power.",
        proposed_mechanism="Host-only fixture", predicted_effect="At least 10% reduction",
        primary_metric="power_watts",
    )
    store.publish(hypothesis)
    protocol = ExperimentProtocol(
        session_id=session_id, hypothesis_id=hypothesis.id, mode=hypothesis.mode,
        title="Synthetic incomplete collection", workload="No physical experiment",
        baseline_configuration={"arm": "baseline"}, changed_configuration={"arm": "changed"},
        baseline_configuration_digest="synthetic-baseline", changed_configuration_digest="synthetic-changed",
        controlled_conditions=("No hardware",), block_order="Two synthetic pairs",
        independent_restart="Synthetic epochs", warmup="None", sampling="No samples returned",
        stopping_rule="Stop after missing collection",
    )
    store.publish(protocol)
    result = derive_power_result(
        session_id=session_id, hypothesis_id=hypothesis.id, hypothesis=hypothesis,
        protocol=protocol, observations=(), observation_pairs=(),
        adherence=ProtocolAdherence(
            protocol_id=protocol.id, protocol_frozen_before_collection=True,
            independently_restarted_blocks=0, workload_matched=True,
            configuration_matched=True, sampling_complete=False,
            violations=("Synthetic collection returned no observations.",),
        ),
    )
    assert result.outcome is OutcomeCategory.INVALID
    store.publish(result)
    counter = ClaimEvidence(
        session_id=session_id, hypothesis_id=hypothesis.id, mode=hypothesis.mode,
        claim="No valid evidence supports the proposed reduction.",
        direction=EvidenceDirection.COUNTERS, strength="strong", rationale=QUESTION,
        record_refs=(result.id,), limitations=("Synthetic host fixture only.",),
    )
    store.publish(counter)
    store.publish(DecisionRecord(
        session_id=session_id, hypothesis_id=hypothesis.id, protocol_id=protocol.id,
        derived_result_id=result.id, mode=hypothesis.mode, outcome=result.outcome,
        conclusion="Collection invalid; no negative or positive finding.",
        next_action="Inspect the missing synthetic collection before another experiment.",
        counterevidence=(counter,), unresolved_uncertainties=(QUESTION,),
    ))
    return store


def _resume_after_reopening(tmp_path, *, prior_status, prior_usage, resolution_bound):
    paths = AppPaths(tmp_path / "resume-state")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    core = CoreApp.open(paths, max_concurrent_jobs=1)
    runtime = ScriptedRuntime("before-restart", prior_status, prior_usage)
    try:
        session = core.create_session(SessionCreate(
            objective="Synthetic job resume qualification", owner="owner", host_identity="host",
            token_limit=1000,
        ))
        assert core.submit(OwnerCommand(
            session_id=session.id, owner=session.owner, kind=CommandKind.START,
            expected_revision=session.revision, payload={},
        )).status is CommandStatus.APPLIED
        store = _publish_failed_science(core, session.id)
        request = InvestigationRequest(
            session_id=session.id, instruction="Preserve the failed collection and unresolved question.",
            cwd=workspace, model="synthetic-model", kind="investigate",
            estimated_tokens=300, estimated_active_seconds=30, deadline_seconds=30,
            reasoning_effort="medium",
        )
        orchestrator = InvestigationOrchestrator(core, runtime, workspace=workspace)

        async def initial_turn():
            try:
                launch = await orchestrator.start(request)
                return await asyncio.wait_for(orchestrator.wait(launch.job_id), timeout=3)
            finally:
                await orchestrator.close()

        prior_job = asyncio.run(initial_turn())
        assert prior_job.state == prior_status.value
        assert prior_job.result["proposal_only"] is True
        assert core.snapshot(session.id).budget.usage_uncertain
        assert core.snapshot(session.id).budget.tokens_used == (prior_usage or 0)
        records = store.list(session.id)
        identities = {item.record.id: (item.artifact_id, item.sha256) for item in records}
        brief = store.brief(records).model_dump(exclude={"resource_limits"})
        assert brief["failed_attempts"]
        assert brief["limitations"] == (QUESTION,)
    finally:
        core.close()
    assert runtime.closed

    # All scripted work is terminal and closed before reopening. This does not
    # qualify a real surviving process, cgroup cleanup, or coordinator lease.
    reopened = CoreApp.open(paths, max_concurrent_jobs=1)
    resumed_runtime = ScriptedRuntime("after-restart", JobStatus.COMPLETED, 200)
    resumed_orchestrator = InvestigationOrchestrator(reopened, resumed_runtime, workspace=workspace)
    try:
        reopened.reconcile()
        store = ScientificRecordStore(reopened)
        assert store.brief(store.list(session.id)).model_dump(exclude={"resource_limits"}) == brief
        assert reopened.job(prior_job.id).result == prior_job.result

        async def resumed_turn():
            try:
                with pytest.raises(ConflictError, match="budget admission is closed"):
                    await resumed_orchestrator.resume(THREAD_ID, request)
                assert resumed_runtime.calls == []
                assert len(reopened.list_records(session.id, "jobs")) == 1
                reopened.resolve_usage_uncertainty(
                    session.id, upper_bound_tokens=resolution_bound,
                    evidence=(
                        "Synthetic runtime is closed and cannot consume more tokens. "
                        "Interrupted fixture: add a conservative 20-token bound beyond 120 reported. "
                        "Unknown fixture: scripted startup ran no provider or subprocess, bound zero."
                    ),
                )
                assert not reopened.snapshot(session.id).budget.usage_uncertain
                with pytest.raises(ConflictError, match="reservation exceeds the remaining allowance"):
                    await resumed_orchestrator.resume(
                        THREAD_ID, request.model_copy(update={"estimated_tokens": 1001}),
                    )
                assert resumed_runtime.calls == []
                assert len(reopened.list_records(session.id, "jobs")) == 1
                launch = await resumed_orchestrator.resume(THREAD_ID, request)
                return await asyncio.wait_for(resumed_orchestrator.wait(launch.job_id), timeout=3)
            finally:
                await resumed_orchestrator.close()

        resumed_job = asyncio.run(resumed_turn())
        assert resumed_job.state == "completed"
        assert resumed_job.kind == "investigate"
        assert resumed_job.id != prior_job.id
        assert resumed_job.result["resumed"] is True
        assert resumed_job.result["proposal_only"] is True
        assert resumed_job.evidence_manifest["resume"] == {"thread_id": THREAD_ID}
        assert resumed_job.evidence_manifest["scientific_brief"]["finding"] == brief["finding"]
        assert resumed_job.evidence_manifest["scientific_brief"]["failed_attempts"] == list(brief["failed_attempts"])
        assert resumed_job.evidence_manifest["admission"]["estimated_tokens"] == 300
        action, thread_id, scoped = resumed_runtime.calls[0]
        assert (action, thread_id) == ("resume", THREAD_ID)
        assert len(resumed_runtime.calls) == 1
        assert scoped.cwd == workspace
        assert scoped.model == request.model
        assert scoped.deadline_seconds == 30
        assert scoped.reasoning_effort == "medium"
        assert scoped.sandbox is SandboxMode.READ_ONLY
        assert scoped.writable_roots == ()
        assert dict(scoped.output_schema) == OUTPUT_SCHEMA
        assert QUESTION in scoped.prompt
        assert all(record_id in scoped.prompt for record_id in identities)
        restored = store.list(session.id)
        assert {item.record.id: (item.artifact_id, item.sha256) for item in restored} == identities
        assert store.brief(restored).model_dump(exclude={"resource_limits"}) == brief
        assert reopened.job(prior_job.id).state == prior_status.value
        budget = reopened.snapshot(session.id).budget
        assert budget.tokens_used == 200 + resolution_bound
        assert budget.tokens_reserved == 0
        assert not budget.usage_uncertain
        for kind in ("procedures", "reviews", "approvals", "operations"):
            assert reopened.list_records(session.id, kind) == []
    finally:
        reopened.close()


def test_interrupted_investigator_resumes_after_reopen_with_evidence_and_accounting(tmp_path):
    _resume_after_reopening(
        tmp_path, prior_status=JobStatus.INTERRUPTED, prior_usage=120, resolution_bound=20,
    )


def test_reconciled_unknown_primary_can_resume_without_erasing_unknown_history(tmp_path):
    _resume_after_reopening(
        tmp_path, prior_status=JobStatus.UNKNOWN, prior_usage=None, resolution_bound=0,
    )
