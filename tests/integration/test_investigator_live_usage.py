"""Job-local usage caps and cooperative event consumption; no model processes."""

from __future__ import annotations

import asyncio

import pytest

from m1lab.adapters import JobHandle, JobStatus, RuntimeEvent, TokenUsage
from m1lab.core import CoreApp, CommandKind, OwnerCommand, SessionCreate, UsageUpdate
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.service import InvestigationOrchestrator
from m1lab.paths import AppPaths


THREAD = "persisted-usage-thread"


class QueuedRuntime:
    def __init__(self, label, updates, *, before_event=None, burst=0):
        self.label = label
        self.updates = updates
        self.before_event = before_event
        self.burst = burst
        self.handle = None
        self.current_usage = None
        self.interruptions = []
        self.delivered = 0
        self.finished = False
        self.closed = False

    async def start_job(self, request):
        return self._start(False)

    async def resume_job(self, thread_id, request):
        assert thread_id == THREAD
        return self._start(True)

    def _start(self, resumed):
        self.handle = JobHandle(self.label, THREAD, f"turn-{self.label}", JobStatus.RUNNING, resumed)
        return self.handle

    async def events(self, job_id):
        queue = asyncio.Queue()
        method = "item/agentMessage/delta" if self.burst else "thread/tokenUsage/updated"
        for sequence, usage in enumerate(self.updates if not self.burst else [1] * self.burst, 1):
            queue.put_nowait((sequence, usage))
        while not queue.empty():
            sequence, value = await queue.get()  # Prequeued get does not suspend.
            if self.before_event is not None:
                self.before_event(sequence)
            self.current_usage = TokenUsage(total_tokens=value, cumulative=True)
            self.delivered += 1
            yield RuntimeEvent(sequence, job_id, method, THREAD, self.handle.turn_id, {})
            if self.interruptions:
                break
        self.finished = True

    def status(self, job_id):
        return JobHandle(job_id, THREAD, self.handle.turn_id,
                         JobStatus.INTERRUPTED if self.interruptions else JobStatus.COMPLETED,
                         self.handle.resumed)

    def usage(self, job_id):
        return self.current_usage

    async def interrupt(self, job_id):
        self.interruptions.append((job_id, self.current_usage.total_tokens))

    async def close(self):
        self.closed = True


def _session(core, *, tokens=5000):
    record = core.create_session(SessionCreate(
        objective="Synthetic live-usage admission", owner="owner", host_identity="host",
        token_limit=tokens, active_seconds=3600,
    ))
    core.submit(OwnerCommand(
        session_id=record.id, owner=record.owner, kind=CommandKind.START,
        expected_revision=record.revision,
    ))
    return record.id


def _request(session_id, workspace, estimated_tokens):
    return InvestigationRequest(
        session_id=session_id, instruction="Inspect retained synthetic evidence",
        cwd=workspace, model="gpt-6-sol", kind="chat", estimated_tokens=estimated_tokens,
        estimated_active_seconds=30, deadline_seconds=30,
    )


async def _turn(core, workspace, session_id, runtime, *, resumed, estimated_tokens):
    orchestrator = InvestigationOrchestrator(core, runtime, workspace=workspace)
    try:
        request = _request(session_id, workspace, estimated_tokens)
        launch = (await orchestrator.resume(THREAD, request) if resumed
                  else await orchestrator.start(request))
        return await asyncio.wait_for(orchestrator.wait(launch.job_id), timeout=3)
    finally:
        await orchestrator.close()


@pytest.mark.parametrize("updates,expected_state,total,interrupt_at", [
    ([700, 730, 730, 710, 799], "completed", 799, None),
    ([750, 799, 800, 850], "interrupted", 800, 800),
])
def test_resumed_chat_counts_only_this_jobs_charges_after_restart(
    tmp_path, updates, expected_state, total, interrupt_at,
):
    paths = AppPaths(tmp_path / "data")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    core = CoreApp.open(paths)
    try:
        sid = _session(core)
        original = QueuedRuntime("original", [700])
        first_job = asyncio.run(_turn(core, workspace, sid, original,
                                      resumed=False, estimated_tokens=1000))
        assert first_job.state == "completed" and not original.interruptions
        assert core.session(sid).lifetime_tokens == 700
    finally:
        core.close()
    # A fresh orchestrator must use the durable cumulative baseline, rather
    # than comparing all 700+ thread tokens against the new 100-token job.
    reopened = CoreApp.open(paths)
    try:
        runtime = QueuedRuntime("resumed", updates)
        job = asyncio.run(_turn(reopened, workspace, sid, runtime,
                                resumed=True, estimated_tokens=100))
        assert job.state == expected_state
        assert runtime.interruptions == ([] if interrupt_at is None else [(runtime.label, interrupt_at)])
        assert reopened.session(sid).lifetime_tokens == total
        assert job.result["usage"]["uncertain"] is (interrupt_at is not None)
        assert reopened.snapshot(sid).budget.usage_uncertain is (interrupt_at is not None)
        assert reopened.snapshot(sid).budget.tokens_reserved == 0
        assert reopened.job(first_job.id).state == "completed"
    finally:
        reopened.close()


@pytest.mark.parametrize("guard", ["session_limit", "unknown_coverage"])
def test_resumed_chat_still_interrupts_for_session_guards(core, tmp_path, guard):
    sid = _session(core, tokens=1000)
    core.report_usage(UsageUpdate(
        report_id="prior-turn", session_id=sid, source_id=THREAD,
        input_tokens=700, output_tokens=0, cumulative=True, terminal=True,
    ))

    def before_event(_sequence):
        if guard == "session_limit":
            core.report_usage(UsageUpdate(
                report_id="sibling-turn", session_id=sid, source_id="other-thread",
                input_tokens=300, output_tokens=0, cumulative=True, terminal=True,
            ))
        else:
            core.mark_usage_uncertain(sid, "other-thread", "Synthetic missing terminal coverage")

    # The resumed turn has charged zero new tokens when the other guard closes.
    runtime = QueuedRuntime("guarded", [700], before_event=before_event)
    job = asyncio.run(_turn(core, tmp_path, sid, runtime, resumed=True, estimated_tokens=100))
    assert job.state == "interrupted"
    assert runtime.interruptions == [(runtime.label, 700)]
    assert core.session(sid).lifetime_tokens == (1000 if guard == "session_limit" else 700)
    assert core.snapshot(sid).budget.usage_uncertain
    assert core.snapshot(sid).budget.tokens_reserved == 0


def test_prequeued_event_burst_yields_before_draining_and_preserves_records(core, tmp_path):
    sid = _session(core)
    runtime = QueuedRuntime("burst", [], burst=150)

    async def exercise():
        orchestrator = InvestigationOrchestrator(core, runtime, workspace=tmp_path)
        try:
            launch = await orchestrator.start(_request(sid, tmp_path, 100))

            async def heartbeat():
                # This task is queued after the consumer: it gets a chance to
                # serve other work only if event processing actually suspends.
                return runtime.delivered, core.job(launch.job_id).result["last_runtime_sequence"]

            tick = asyncio.create_task(heartbeat())
            job = await asyncio.wait_for(orchestrator.wait(launch.job_id), timeout=3)
            return await tick, job
        finally:
            await orchestrator.close()

    (delivered_at_tick, recorded_at_tick), job = asyncio.run(exercise())
    assert 0 < delivered_at_tick < runtime.burst
    assert recorded_at_tick == delivered_at_tick
    assert runtime.finished and runtime.delivered == runtime.burst
    assert job.state == "completed"
    assert job.result["last_runtime_sequence"] == runtime.burst
    assert job.result["event_summaries"][-1]["sequence"] == runtime.burst
    assert not runtime.interruptions
    assert core.session(sid).lifetime_tokens == 1
    assert not core.snapshot(sid).budget.usage_uncertain
    assert core.snapshot(sid).budget.tokens_reserved == 0


def test_cancellation_between_burst_events_retires_runtime_and_reconciles(core, tmp_path):
    sid = _session(core)
    runtime = QueuedRuntime("cancelled-burst", [], burst=150)

    async def exercise():
        orchestrator = InvestigationOrchestrator(core, runtime, workspace=tmp_path)
        try:
            launch = await orchestrator.start(_request(sid, tmp_path, 100))

            async def cancel_consumer():
                assert 0 < runtime.delivered < runtime.burst
                orchestrator._tasks[launch.job_id].cancel()

            cancellation = asyncio.create_task(cancel_consumer())
            job = await asyncio.wait_for(orchestrator.wait(launch.job_id), timeout=3)
            await cancellation
            assert runtime.closed
            return job
        finally:
            await orchestrator.close()

    job = asyncio.run(exercise())
    assert job.state == "unknown"
    assert job.result["usage"]["reported"] is True
    assert job.result["usage"]["uncertain"] is True
    assert core.session(sid).lifetime_tokens == 1
    assert core.snapshot(sid).budget.usage_uncertain
    assert core.snapshot(sid).budget.tokens_reserved == 0
