"""Real synthetic subprocess transport failures; no Codex/model/network calls."""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import sys

import pytest

from m1lab.adapters import runtime as runtime_module
from m1lab.adapters.runtime import AppServerCodexAdapter, JobRequest, JobStatus


FAKE_APP_SERVER = r'''
import json
import os
from pathlib import Path
import signal
import sys
import time

root = Path(__file__).parent
signal.signal(signal.SIGTERM, signal.SIG_IGN)
(root / "server.pid").write_text(str(os.getpid()))
for line in sys.stdin:
    message = json.loads(line)
    method = message["method"]
    if method == "initialized":
        continue
    if method == "initialize":
        result = {}
    elif method == "thread/start":
        result = {"thread": {"id": "synthetic-thread"},
                  "activePermissionProfile": {"id": "m1lab-read-only"}}
    elif method == "turn/start":
        result = {"turn": {"id": "synthetic-turn"}}
    else:
        raise RuntimeError("unexpected synthetic RPC")
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
    if method == "turn/start":
        # The test triggers failure only after start_job has returned, so no
        # pending RPC's error handler can incidentally perform the cleanup.
        until = time.monotonic() + 10
        while not (root / "break-transport").exists():
            if time.monotonic() >= until:
                sys.exit(2)
            time.sleep(0.01)
        if (root / "failure-kind").read_text() == "malformed-json":
            print("{malformed-json", flush=True)
        else:
            os.close(sys.stdout.fileno())
        # Transport failure is deliberately independent of process lifetime.
        # Ignore SIGTERM so the adapter must complete its bounded escalation.
        time.sleep(60)
        break
'''


def _group_exists(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.parametrize("failure_kind", ["malformed-json", "stdout-eof"])
def test_transport_failure_stops_process_group_before_unknown_terminal_is_visible(
    tmp_path, monkeypatch, failure_kind
):
    executable = tmp_path / "synthetic-app-server"
    executable.write_text(f"#!{sys.executable}\n" + FAKE_APP_SERVER)
    executable.chmod(0o700)
    (tmp_path / "failure-kind").write_text(failure_kind)
    monkeypatch.setattr(runtime_module, "PROCESS_SHUTDOWN_GRACE_SECONDS", 0.05)
    adapter = AppServerCodexAdapter(
        executable=str(executable),
        expected_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        startup_timeout_seconds=2,
        request_timeout_seconds=2,
        environment={"HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / "fake-codex-home")},
    )

    async def exercise():
        pid = None
        try:
            handle = await asyncio.wait_for(adapter.start_job(JobRequest(
                prompt="Synthetic transport fixture only.",
                cwd=tmp_path,
                model="synthetic-model",
                deadline_seconds=30,
            )), timeout=5)
            assert handle.status is JobStatus.RUNNING
            pid = int((tmp_path / "server.pid").read_text())
            assert _group_exists(pid)
            (tmp_path / "break-transport").touch()

            async def observe_terminal():
                async for event in adapter.events(handle.job_id):
                    if event.method == "runtime/terminal":
                        assert event.payload["status"] == "unknown"
                        # Check at notification delivery, before explicit close
                        # and well before the original job's 30-second deadline.
                        assert not _group_exists(pid), "unknown terminal exposed while runtime group survives"
                        return event
                pytest.fail("transport failure ended events without an unknown terminal")

            terminal = await asyncio.wait_for(observe_terminal(), timeout=3)
            expected_message = "invalid JSON" if failure_kind == "malformed-json" else "stdout closed"
            assert expected_message in terminal.payload["message"]
            assert adapter.status(handle.job_id).status is JobStatus.UNKNOWN
            assert adapter.usage(handle.job_id) is None
        finally:
            # Both the expected red assertion and any future shutdown deadlock
            # must leave no synthetic process behind.
            try:
                await asyncio.wait_for(adapter.close(), timeout=2)
            finally:
                pid_path = tmp_path / "server.pid"
                if pid is None and pid_path.exists():
                    pid = int(pid_path.read_text())
                if pid is not None:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process = adapter._process
                if process is not None:
                    await asyncio.wait_for(process.wait(), timeout=2)

    asyncio.run(exercise())


def test_cancelled_close_caller_does_not_abandon_shared_process_cleanup(monkeypatch):
    async def exercise():
        adapter = AppServerCodexAdapter(expected_sha256="0" * 64)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(60)",
            start_new_session=True,
        )
        # Isolate the close contract with a real process and no protocol startup.
        adapter._process = process
        entered = asyncio.Event()
        release = asyncio.Event()
        cancelled_cleanup = asyncio.Event()
        terminate = adapter._terminate_process_group
        callers = []

        async def blocked_termination(process):
            entered.set()
            try:
                await release.wait()
                await terminate(process, grace_seconds=0.05)
            except asyncio.CancelledError:
                cancelled_cleanup.set()
                raise

        monkeypatch.setattr(adapter, "_terminate_process_group", blocked_termination)
        try:
            first = asyncio.create_task(adapter.close())
            callers.append(first)
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert _group_exists(process.pid)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(first, timeout=2)
            assert not cancelled_cleanup.is_set(), "caller cancellation cancelled process cleanup"

            second_started = asyncio.Event()

            async def close_again():
                second_started.set()
                await adapter.close()

            second = asyncio.create_task(close_again())
            callers.append(second)
            await asyncio.wait_for(second_started.wait(), timeout=2)
            assert not second.done(), "subsequent close returned before cleanup completed"
            assert _group_exists(process.pid)
            release.set()
            await asyncio.wait_for(second, timeout=2)
            assert process.returncode is not None
            assert not _group_exists(process.pid)
        finally:
            release.set()
            for caller in callers:
                if not caller.done():
                    caller.cancel()
            try:
                await asyncio.wait_for(adapter.close(), timeout=2)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.wait_for(process.wait(), timeout=2)
                await asyncio.wait_for(asyncio.gather(*callers, return_exceptions=True), timeout=2)

    asyncio.run(exercise())
