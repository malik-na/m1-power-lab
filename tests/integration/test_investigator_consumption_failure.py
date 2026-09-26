from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from m1lab.adapters.runtime import JobHandle, JobStatus, RuntimeEvent, TokenUsage
from m1lab.core.errors import ConflictError
from m1lab.core.models import CommandKind, OwnerCommand, SessionCreate
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.service import InvestigationOrchestrator


class ScriptedRuntime:
    """Keep work running until explicitly retired; never launch a process/model."""

    def __init__(self, close_error=None):
        self.queue = asyncio.Queue()
        self.handle = None
        self.closed = False
        self.starts = 0
        self.observed_usage = TokenUsage(total_tokens=120, cumulative=True)
        self.close_error = close_error

    async def start_job(self, request):
        assert not self.closed
        self.starts += 1
        self.handle = JobHandle("runtime-job", "thread", "turn", JobStatus.RUNNING)
        return self.handle

    async def events(self, job_id):
        while (event := await self.queue.get()) is not None:
            yield event

    def status(self, job_id):
        return self.handle

    def usage(self, job_id):
        return self.observed_usage

    async def interrupt(self, job_id):
        # An accepted interruption request alone does not retire the work.
        pass

    async def close(self):
        if self.close_error is not None:
            error, self.close_error = self.close_error, None
            raise error
        self.closed = True
        self.handle = replace(self.handle, status=JobStatus.UNKNOWN)
        self.queue.put_nowait(None)


@pytest.mark.parametrize(
    "close_error_type", [None, OSError, asyncio.CancelledError],
    ids=["cleanup-succeeds", "cleanup-fails", "cleanup-cancelled"],
)
def test_event_artifact_failure_preserves_partial_usage_and_requires_runtime_retirement(
    core, tmp_path, monkeypatch, close_error_type
):
    session = core.create_session(
        SessionCreate(
            objective="Contain failure while recording runtime evidence",
            owner="owner", host_identity="host", token_limit=1_000_000,
        )
    )
    core.submit(
        OwnerCommand(
            session_id=session.id, owner=session.owner, kind=CommandKind.START,
            expected_revision=session.revision, payload={},
        )
    )

    async def exercise():
        runtime = ScriptedRuntime(
            close_error_type("synthetic cleanup failure") if close_error_type else None
        )
        workspace = tmp_path / "workspace"
        investigator = InvestigationOrchestrator(core, runtime, workspace=workspace)
        request = InvestigationRequest(
            session_id=session.id, instruction="Inspect selected evidence",
            cwd=workspace, model="test-model", estimated_tokens=10_000,
        )
        try:
            launch = await investigator.start(request)
            original_publish = core.publish_artifact

            def fail_runtime_artifact(content, *, media_type, provenance):
                if media_type == "application/vnd.m1lab.runtime-event+json":
                    raise OSError("synthetic event artifact publication failed")
                return original_publish(content, media_type=media_type, provenance=provenance)

            monkeypatch.setattr(core, "publish_artifact", fail_runtime_artifact)
            runtime.queue.put_nowait(
                RuntimeEvent(
                    1, launch.runtime_id, "thread/tokenUsage/updated", "thread", "turn",
                    {"tokenUsage": {"total": {"totalTokens": 120}}},
                )
            )
            runtime.queue.put_nowait(
                RuntimeEvent(
                    2, launch.runtime_id, "item/completed", "thread", "turn",
                    {"item": {"id": "item", "type": "agentMessage", "text": "synthetic"}},
                )
            )
            job = await asyncio.wait_for(investigator.wait(launch.job_id), timeout=2)

            if close_error_type:
                assert not runtime.closed
                assert runtime.status(launch.runtime_id).status is JobStatus.RUNNING
                assert job.state == "running"
                assert job.result["cleanup_completed"] is False
                assert "synthetic cleanup failure" in job.result["cleanup_error"]
                assert "synthetic event artifact publication failed" in job.result["stream_error"]
                assert core.session(session.id).usage_uncertain is True
                assert core.session(session.id).lifetime_tokens == 120
                source = core.journal.one(
                    "SELECT terminal FROM usage_sources WHERE session_id=? AND source_id=?",
                    (session.id, "thread"),
                )
                assert source["terminal"] == 0
                reservation = core.journal.one(
                    "SELECT released_at FROM reservations WHERE id=?",
                    (job.result["reservation_id"],),
                )
                assert reservation["released_at"] is None
                with pytest.raises(ConflictError, match="budget admission is closed"):
                    await investigator.start(request)
                assert runtime.starts == 1
                # Explicit cleanup can retry, but does not erase durable uncertainty.
                await runtime.close()
                assert runtime.closed
                assert core.session(session.id).usage_uncertain is True
                assert core.job(job.id).state == "running"
                return

            # Assert before the test's cleanup closes the runtime itself.
            assert runtime.closed, "event recording failure left model work running"
            assert runtime.status(launch.runtime_id).status.terminal
            assert job.state == "unknown"
            assert "synthetic event artifact publication failed" in job.result["stream_error"]
            assert job.result["usage"]["reported"] is True
            assert job.result["usage"]["tokens"] == 120
            assert job.result["usage"]["uncertain"] is True
            assert core.session(session.id).usage_uncertain is True
            assert core.session(session.id).lifetime_tokens == 120
            source = core.journal.one(
                "SELECT accounted_tokens, terminal FROM usage_sources "
                "WHERE session_id=? AND source_id=?", (session.id, "thread"),
            )
            assert source["accounted_tokens"] == 120
            assert source["terminal"] == 0
            reservation = core.journal.one(
                "SELECT released_at FROM reservations WHERE id=?", (job.result["reservation_id"],),
            )
            assert reservation["released_at"] is not None
            with pytest.raises(ConflictError, match="budget admission is closed"):
                await investigator.start(request)
            assert runtime.starts == 1
            assert len(core.list_records(session.id, "jobs")) == 1
        finally:
            await investigator.close()

    asyncio.run(exercise())
