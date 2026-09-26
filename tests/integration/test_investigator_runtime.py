from __future__ import annotations

import asyncio
import json
import signal
import sys
import time

import pytest

from m1lab.adapters.runtime import (
    AppServerCodexAdapter,
    JobRequest,
    JobStatus,
    NoopCodexAdapter,
    RuntimeEvent,
    RuntimeRequestNotSent,
    RuntimeUnavailable,
    RuntimeOutcomeUnknown,
)
from m1lab.core.errors import ConflictError
from m1lab.core.models import CommandKind, OwnerCommand, SessionCreate
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.service import InvestigationOrchestrator, _event_document
from m1lab.adapters import runtime as runtime_module


def test_runtime_rejects_unallowlisted_environment_override():
    with pytest.raises(ValueError, match="not allowlisted"):
        AppServerCodexAdapter(
            executable="/usr/bin/codex",
            expected_sha256="0" * 64,
            environment={"OPENAI_API_KEY": "must-not-be-forwarded"},
        )


def test_runtime_requires_exact_binary_pin_before_start(tmp_path):
    executable = tmp_path / "codex"
    executable.write_text("codex binary placeholder")
    executable.chmod(0o755)
    adapter = AppServerCodexAdapter(
        executable=str(executable), expected_sha256="0" * 64
    )

    async def start():
        try:
            await adapter._ensure_started()
        finally:
            await adapter.close()

    with pytest.raises(RuntimeUnavailable, match="SHA-256 pin mismatch"):
        asyncio.run(start())


def test_runtime_rpc_sends_and_correlates_json_rpc_2_message():
    class Stdin:
        def __init__(self):
            self.messages: list[bytes] = []

        def write(self, message: bytes) -> None:
            self.messages.append(message)

        async def drain(self) -> None:
            return None

    class Process:
        returncode = None

        def __init__(self):
            self.stdin = Stdin()

    adapter = AppServerCodexAdapter(
        expected_sha256="0" * 64, request_timeout_seconds=1
    )
    adapter._process = Process()

    async def send_and_receive():
        task = asyncio.create_task(adapter._rpc("initialize", {"clientInfo": {}}))
        while not adapter._process.stdin.messages:
            await asyncio.sleep(0)
        request = json.loads(adapter._process.stdin.messages[0])
        assert request["jsonrpc"] == "2.0"
        await adapter._route_message(
            {"jsonrpc": "2.0", "id": request["id"], "result": {"ready": True}}
        )
        return await task

    assert asyncio.run(send_and_receive()) == {"ready": True}


def test_runtime_rpc_timeout_for_turn_start_is_outcome_unknown():
    class Stdin:
        def write(self, message: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

    class Process:
        returncode = None
        stdin = Stdin()

    adapter = AppServerCodexAdapter(
        expected_sha256="0" * 64, request_timeout_seconds=0.001
    )
    adapter._process = Process()

    async def close_without_process_management():
        return None

    adapter.close = close_without_process_management

    with pytest.raises(RuntimeOutcomeUnknown, match="turn/start may have been accepted"):
        asyncio.run(adapter._rpc("turn/start", {"threadId": "thread"}))


def test_runtime_pre_write_failure_is_known_no_effect():
    class Stdin:
        pass

    class Process:
        returncode = None
        stdin = Stdin()

    adapter = AppServerCodexAdapter(expected_sha256="0" * 64)
    adapter._process = Process()

    async def fail_before_write(message):
        raise RuntimeRequestNotSent("transport became unavailable before write")

    adapter._write_json = fail_before_write

    with pytest.raises(RuntimeRequestNotSent):
        asyncio.run(adapter._rpc("turn/start", {"threadId": "thread"}))


def test_turn_start_without_returned_identity_is_outcome_unknown(tmp_path):
    adapter = AppServerCodexAdapter(expected_sha256="0" * 64)

    async def ready():
        return None

    async def rpc(method, params):
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        return {}

    async def close_without_process_management():
        return None

    adapter._ensure_started = ready
    adapter._rpc = rpc
    adapter.close = close_without_process_management
    request = JobRequest(
        prompt="Analyze only the supplied evidence.",
        cwd=tmp_path,
        model="test-model",
        deadline_seconds=10,
    )

    with pytest.raises(RuntimeOutcomeUnknown, match="turn/start succeeded without a turn identity"):
        asyncio.run(adapter.start_job(request))

    assert next(iter(adapter._jobs.values())).handle.status is JobStatus.UNKNOWN


def test_state_changing_rpc_internal_error_is_outcome_unknown():
    class Stdin:
        def __init__(self):
            self.messages = []

        def write(self, message):
            self.messages.append(message)

        async def drain(self):
            return None

    class Process:
        returncode = None

        def __init__(self):
            self.stdin = Stdin()

    adapter = AppServerCodexAdapter(expected_sha256="0" * 64)
    adapter._process = Process()

    async def close_without_process_management():
        return None

    adapter.close = close_without_process_management

    async def reject():
        task = asyncio.create_task(adapter._rpc("turn/start", {}))
        while not adapter._process.stdin.messages:
            await asyncio.sleep(0)
        request = json.loads(adapter._process.stdin.messages[0])
        await adapter._route_message(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32000, "message": "internal error"},
            }
        )
        with pytest.raises(RuntimeOutcomeUnknown, match="may have been accepted"):
            await task

    asyncio.run(reject())


def test_runtime_close_escalates_when_app_server_ignores_sigterm(monkeypatch):
    monkeypatch.setattr(runtime_module, "PROCESS_SHUTDOWN_GRACE_SECONDS", 0.01)
    adapter = AppServerCodexAdapter(expected_sha256="0" * 64)

    async def stop_stubborn_child():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready',flush=True); time.sleep(30)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        await process.stdout.readline()
        adapter._process = process
        started = time.monotonic()
        await adapter.close()
        elapsed = time.monotonic() - started
        assert process.returncode == -signal.SIGKILL
        assert elapsed < 1

    asyncio.run(stop_stubborn_child())


def test_orchestrator_shutdown_interrupts_active_job_before_closing_runtime(core, tmp_path):
    class Runtime:
        def __init__(self):
            self.calls = []
            self.closed = None

        async def interrupt(self, runtime_id):
            self.calls.append(("interrupt", runtime_id))

        async def close(self):
            self.calls.append(("close", None))
            self.closed.set()

    async def shutdown():
        runtime = Runtime()
        runtime.closed = asyncio.Event()
        orchestrator = InvestigationOrchestrator(
            core, runtime, workspace=tmp_path / "workspace"
        )
        orchestrator._runtime_ids["job"] = "runtime-job"
        orchestrator._tasks["job"] = asyncio.create_task(runtime.closed.wait())

        await orchestrator.close()

        assert runtime.calls == [("interrupt", "runtime-job"), ("close", None)]

    asyncio.run(shutdown())


def test_runtime_event_artifact_preserves_complete_payload():
    original = "x" * 1_000_001
    event = RuntimeEvent(
        sequence=7,
        job_id="job",
        method="item/completed",
        thread_id="thread",
        turn_id="turn",
        payload={"text": original},
    )

    document = _event_document(event)

    assert document["payload_truncated"] is False
    assert '"text": "' + original + '"' in document["payload_json"]


def test_investigation_is_confined_to_configured_workspace(core, tmp_path):
    session = core.create_session(
        SessionCreate(objective="test runtime confinement", owner="owner", host_identity="host")
    )
    workspace = tmp_path / "dedicated"
    request = InvestigationRequest(
        session_id=session.id,
        instruction="inspect the selected evidence",
        cwd=tmp_path / "other",
        model="test-model",
    )
    orchestrator = InvestigationOrchestrator(
        core, NoopCodexAdapter(), workspace=workspace
    )

    with pytest.raises(ValueError, match="configured dedicated workspace"):
        asyncio.run(orchestrator.start(request))

    assert core.list_records(session.id, "jobs") == []


def test_ambiguous_runtime_start_is_durable_unknown_and_closes_admission(core, tmp_path):
    session = core.create_session(
        SessionCreate(
            objective="protect against duplicate paid turns",
            owner="owner",
            host_identity="host",
            token_limit=1_000_000,
        )
    )
    core.submit(
        OwnerCommand(
            session_id=session.id,
            owner=session.owner,
            kind=CommandKind.START,
            expected_revision=session.revision,
            payload={},
        )
    )

    class AmbiguousRuntime(NoopCodexAdapter):
        async def start_job(self, request):
            raise RuntimeOutcomeUnknown("turn/start response was lost")

    workspace = tmp_path / "workspace"
    runtime = AmbiguousRuntime()
    orchestrator = InvestigationOrchestrator(core, runtime, workspace=workspace)
    request = InvestigationRequest(
        session_id=session.id,
        instruction="inspect the selected evidence",
        cwd=workspace,
        model="test-model",
        estimated_tokens=10_000,
    )

    with pytest.raises(RuntimeOutcomeUnknown):
        asyncio.run(orchestrator.start(request))

    job = core.list_records(session.id, "jobs")[0]
    assert job.state == "unknown"
    assert job.result["outcome_uncertain"] is True
    assert core.session(session.id).usage_uncertain is True
    with pytest.raises(ConflictError, match="budget admission is closed"):
        asyncio.run(orchestrator.start(request))
    assert len(core.list_records(session.id, "jobs")) == 1
