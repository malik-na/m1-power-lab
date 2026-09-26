from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from m1lab.adapters.runtime import JobHandle, JobStatus, RuntimeEvent
from m1lab.application import CoordinatorFacade
from m1lab.core.models import CommandKind, OwnerCommand, SessionCreate, SessionPhase, utc_now
from m1lab.host import HostAdmissionPolicy, HostSnapshot
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.service import InvestigationOrchestrator
from m1lab.web.facade import Owner


class HostSampler:
    def __init__(self):
        self.snapshot = HostSnapshot(
            observed_at=utc_now(),
            power_source="ac",
            battery_percent=75,
            maximum_temperature_c=60,
            thermal_state="normal",
            disk_free_bytes=6 * 1024**3,
            disk_total_bytes=100 * 1024**3,
            lab_mode="sleep/lid inhibitor held; host behavior unqualified",
        )
        self.sampled = asyncio.Event()
        self.error = None

    def sample(self):
        self.sampled.set()
        if self.error is not None:
            raise self.error
        return self.snapshot


class InterruptibleRuntime:
    """Bounded runtime stub; the application and durable coordinator are real."""

    def __init__(self):
        self.started = 0
        self.interruptions = []
        self.interrupted = asyncio.Event()
        self.queue = asyncio.Queue()
        self.handle = None

    async def start_job(self, request):
        self.started += 1
        self.handle = JobHandle("runtime-job", "thread", "turn", JobStatus.RUNNING)
        return self.handle

    async def interrupt(self, job_id):
        self.interruptions.append(job_id)
        self.handle = replace(self.handle, status=JobStatus.INTERRUPTED)
        self.queue.put_nowait(
            RuntimeEvent(1, job_id, "turn/completed", "thread", "turn", {"status": "interrupted"})
        )
        self.queue.put_nowait(None)
        self.interrupted.set()

    async def events(self, job_id):
        while (event := await self.queue.get()) is not None:
            yield event

    def status(self, job_id):
        return self.handle

    def usage(self, job_id):
        return None

    async def close(self):
        pass


@pytest.mark.parametrize(
    ("changes", "blocker", "view_field", "visible"),
    [
        ({"power_source": "battery"}, "host AC power is not confirmed", "power", "battery"),
        ({"power_source": "unknown"}, "host AC power is not confirmed", "power", "unknown"),
        (
            {"maximum_temperature_c": 90, "thermal_state": "critical"},
            "host temperature is at least 90 °C", "thermal", "90.0 °C",
        ),
        (
            {"disk_free_bytes": 5 * 1024**3 - 1},
            "host disk has less than 5.0 GiB free", "disk", "free",
        ),
        (
            {"maximum_temperature_c": None, "thermal_state": "unknown"},
            "host thermal state is unavailable", "thermal", "unknown",
        ),
        (
            {"lab_mode": "sleep/lid inhibitor requested but not confirmed"},
            "configured sleep/lid inhibitor is not confirmed", "lab_mode", "not confirmed",
        ),
        ({"sample_error": True}, "host readiness could not be sampled", None, None),
    ],
    ids=["ac-loss", "unknown-power", "thermal-limit", "disk-limit", "unknown-temperature", "inhibitor-unconfirmed", "sampler-failure"],
)
def test_host_readiness_loss_is_visible_blocks_admission_and_interrupts_work(
    core, tmp_path, changes, blocker, view_field, visible
):
    async def exercise():
        session = core.create_session(
            SessionCreate(objective="Host availability acceptance", owner="owner", host_identity="host")
        )
        core.submit(
            OwnerCommand(
                session_id=session.id, owner=session.owner, kind=CommandKind.START,
                expected_revision=session.revision, payload={},
            )
        )
        sampler = HostSampler()
        healthy = sampler.snapshot
        runtime = InterruptibleRuntime()
        workspace = tmp_path / "workspace"
        investigator = InvestigationOrchestrator(
            core, runtime, workspace=workspace,
            host_blockers=lambda: HostAdmissionPolicy().blockers(sampler.sample()),
        )
        facade = CoordinatorFacade(
            core, session.id, investigator=investigator, workspace=workspace, host_monitor=sampler,
        )
        owner = Owner(session.owner, "Owner", "local")
        request = InvestigationRequest(
            session_id=session.id, instruction="Inspect host evidence", cwd=workspace,
            model="test-model", estimated_tokens=10_000,
        )
        supervisor = None
        try:
            launch = await investigator.start(request)
            if changes.get("sample_error"):
                sampler.error = OSError("host sampler unavailable")
                view = await facade.get_view("overview", owner)
                assert view["host"] == {
                    "state": "unavailable",
                    "power": "unknown",
                    "thermal": "unknown",
                    "disk": "unknown",
                    "lab_mode": "unavailable",
                    "observed_at": "unavailable",
                }
                assert any(
                    alert["title"] == "Host lab readiness is incomplete"
                    and blocker in alert["detail"]
                    for alert in view["alerts"]
                )
            else:
                sampler.snapshot = replace(healthy, **changes)
                view = await facade.get_view("overview", owner)
                assert visible in view["host"][view_field]
                assert any(blocker in alert["detail"] for alert in view["alerts"])
            # Admission refuses immediately, before the periodic supervisor acts.
            error_type = OSError if sampler.error else ValueError
            error_message = "host sampler unavailable" if sampler.error else "host work admission is closed"
            with pytest.raises(error_type, match=error_message):
                await investigator.start(request)
            assert runtime.started == 1
            assert len(core.list_records(session.id, "jobs")) == 1

            supervisor = asyncio.create_task(facade.run_host_safety())
            await asyncio.wait_for(runtime.interrupted.wait(), timeout=2)
            job = await investigator.wait(launch.job_id)
            assert job.state == "interrupted"
            assert core.session(session.id).phase is SessionPhase.PAUSED
            assert runtime.interruptions == [launch.runtime_id]
            assert core.session(session.id).usage_uncertain is True
            assert any(
                event.kind == "host.readiness_blocked" and blocker in event.data["blockers"]
                for event in core.events(session.id)
            )
            reservation = core.journal.one(
                "SELECT released_at FROM reservations WHERE id=?", (job.result["reservation_id"],)
            )
            assert reservation["released_at"] is not None

            supervisor.cancel()
            await asyncio.gather(supervisor, return_exceptions=True)
            sampler.snapshot = healthy
            sampler.error = None
            sampler.sampled.clear()
            supervisor = asyncio.create_task(facade.run_host_safety())
            await asyncio.wait_for(sampler.sampled.wait(), timeout=2)
            recovered = await facade.get_view("overview", owner)
            assert not any(
                alert["title"] == "Host lab readiness is incomplete"
                for alert in recovered["alerts"]
            )
            assert core.session(session.id).phase is SessionPhase.PAUSED
            assert core.session(session.id).usage_uncertain is True
            assert runtime.started == 1
        finally:
            if supervisor is not None:
                supervisor.cancel()
                await asyncio.gather(supervisor, return_exceptions=True)
            await investigator.close()

    asyncio.run(exercise())
