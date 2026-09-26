from __future__ import annotations

import asyncio
import json

import pytest

from m1lab.adapters.runtime import (
    AppServerCodexAdapter,
    NoopCodexAdapter,
    RuntimeEvent,
    RuntimeUnavailable,
)
from m1lab.core.models import SessionCreate
from m1lab.investigator.models import InvestigationRequest
from m1lab.investigator.service import InvestigationOrchestrator, _event_document


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
