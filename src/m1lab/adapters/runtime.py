"""Codex runtime boundary and local app-server transport.

The app-server adapter is inert until ``start_job`` or ``resume_job`` is
called.  It intentionally exposes only the stable conversation lifecycle
methods needed by the coordinator.  In particular it never exposes
``thread/shellCommand``, ``command/exec`` or experimental ``process/*`` RPCs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


MAX_PROMPT_CHARS = 2_000_000
MAX_EVENT_LINE_BYTES = 8 * 1_048_576
MAX_STDERR_CHARS = 64_000
PROCESS_SHUTDOWN_GRACE_SECONDS = 3.0
_OUTGOING_METHODS = frozenset(
    {"initialize", "thread/start", "thread/resume", "turn/start", "turn/interrupt"}
)
_STATE_CHANGING_METHODS = frozenset({"thread/start", "thread/resume", "turn/start"})
_NON_EXECUTING_RPC_ERROR_CODES = frozenset({-32600, -32601, -32602})
_CHILD_ENVIRONMENT_KEYS = frozenset(
    {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)


class RuntimeErrorBase(RuntimeError):
    """Base error raised at the Codex runtime boundary."""


class RuntimeUnavailable(RuntimeErrorBase):
    """The configured runtime is disabled or could not be started."""


class RuntimeRequestNotSent(RuntimeUnavailable):
    """The runtime was unavailable before an RPC could be written."""


class RuntimeProtocolError(RuntimeErrorBase):
    """The app-server stream violated the expected JSON-RPC contract."""


class RuntimeRequestRejected(RuntimeProtocolError):
    """The app-server explicitly rejected an RPC before performing its action."""


class RuntimeOutcomeUnknown(RuntimeErrorBase):
    """A state-changing app-server request may have been accepted without confirmation."""


class SandboxMode(StrEnum):
    READ_ONLY = "readOnly"
    WORKSPACE_WRITE = "workspaceWrite"


class JobStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

    @property
    def terminal(self) -> bool:
        return self in {
            JobStatus.COMPLETED,
            JobStatus.INTERRUPTED,
            JobStatus.FAILED,
            JobStatus.UNAVAILABLE,
            JobStatus.UNKNOWN,
        }


@dataclass(frozen=True, slots=True)
class JobRequest:
    prompt: str
    cwd: Path
    model: str
    deadline_seconds: float
    sandbox: SandboxMode = SandboxMode.READ_ONLY
    writable_roots: tuple[Path, ...] = ()
    output_schema: Mapping[str, Any] | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if not self.prompt or len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"prompt must be 1..{MAX_PROMPT_CHARS} characters")
        if not self.cwd.is_absolute():
            raise ValueError("job cwd must be absolute")
        if not self.model or len(self.model) > 128:
            raise ValueError("job model must be 1..128 characters")
        if not 0 < self.deadline_seconds <= 86_400:
            raise ValueError("deadline_seconds must be in (0, 86400]")
        roots = tuple(self.writable_roots)
        if self.sandbox is SandboxMode.READ_ONLY and roots:
            raise ValueError("read-only jobs cannot declare writable roots")
        if len(roots) > 32 or any(not root.is_absolute() for root in roots):
            raise ValueError("writable_roots must contain at most 32 absolute paths")
        workspace = self.cwd.resolve()
        resolved_roots = tuple(root.resolve() for root in roots)
        if any(root != workspace and not root.is_relative_to(workspace) for root in resolved_roots):
            raise ValueError("writable roots must be inside the job workspace")
        object.__setattr__(self, "cwd", workspace)
        object.__setattr__(self, "writable_roots", resolved_roots)
        if self.output_schema is not None:
            encoded = json.dumps(self.output_schema, separators=(",", ":"))
            if len(encoded) > 256_000:
                raise ValueError("output schema exceeds 256,000 characters")
            object.__setattr__(self, "output_schema", MappingProxyType(dict(self.output_schema)))
        if self.reasoning_effort not in {None, "low", "medium", "high", "xhigh"}:
            raise ValueError("Codex job effort must be low, medium, high, or xhigh")


@dataclass(frozen=True, slots=True)
class JobHandle:
    job_id: str
    thread_id: str | None
    turn_id: str | None
    status: JobStatus
    resumed: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None
    cumulative: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_output_tokens,
            self.total_tokens,
        ):
            if value is not None and value < 0:
                raise ValueError("token counts cannot be negative")
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    sequence: int
    job_id: str
    method: str
    thread_id: str | None
    turn_id: str | None
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@runtime_checkable
class CodexRuntime(Protocol):
    async def start_job(self, request: JobRequest) -> JobHandle:
        """Create a thread and begin one bounded turn."""

    async def resume_job(self, thread_id: str, request: JobRequest) -> JobHandle:
        """Resume a recorded thread and begin one bounded turn."""

    async def interrupt(self, job_id: str) -> None:
        """Request interruption of the active turn."""

    async def events(self, job_id: str) -> AsyncIterator[RuntimeEvent]:
        """Yield events through and including a terminal turn event."""

    def status(self, job_id: str) -> JobHandle:
        """Return the last locally observed job state."""

    def usage(self, job_id: str) -> TokenUsage | None:
        """Return the latest provider-reported usage, if any."""

    async def close(self) -> None:
        """Stop the local transport process and reader tasks."""


@dataclass(slots=True)
class _JobState:
    handle: JobHandle
    queue: asyncio.Queue[RuntimeEvent | None]
    usage: TokenUsage | None = None
    deadline_task: asyncio.Task[None] | None = None


class AppServerCodexAdapter:
    """Minimal stdio JSON-RPC client for ``codex app-server``.

    The coordinator must still provide OS-level isolation, lease cleanup and
    budget admission.  A deadline here is a useful interruption request, not
    proof that the subprocess or upstream work has stopped.
    """

    def __init__(
        self,
        *,
        executable: str = "codex",
        expected_sha256: str,
        environment: Mapping[str, str] | None = None,
        startup_timeout_seconds: float = 15.0,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        if not executable:
            raise ValueError("Codex executable must be non-empty")
        if re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256) is None:
            raise ValueError("expected_sha256 must be a 64-character SHA-256 digest")
        disallowed = set(environment or {}) - _CHILD_ENVIRONMENT_KEYS
        if disallowed:
            raise ValueError("runtime environment keys are not allowlisted: " + ", ".join(sorted(disallowed)))
        self._executable = executable
        self._expected_sha256 = expected_sha256.lower()
        self._environment = dict(environment) if environment is not None else None
        self._startup_timeout = startup_timeout_seconds
        self._request_timeout = request_timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._jobs: dict[str, _JobState] = {}
        self._turn_to_job: dict[str, str] = {}
        self._thread_to_jobs: dict[str, list[str]] = {}
        self._request_id = 0
        self._event_sequence = 0
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._stderr_tail = ""
        self._initialized = False
        self._closed = False

    async def start_job(self, request: JobRequest) -> JobHandle:
        await self._ensure_started()
        thread_params = {
            "model": request.model,
            "cwd": str(request.cwd),
            "approvalPolicy": "never",
            "sandbox": _legacy_sandbox(request.sandbox),
            "serviceName": "m1-power-lab",
        }
        response = await self._rpc("thread/start", thread_params)
        thread_id = _nested_string(response, "thread", "id")
        if thread_id is None:
            await self.close()
            raise RuntimeOutcomeUnknown("thread/start succeeded without a thread identity")
        return await self._start_turn(thread_id, request, resumed=False)

    async def resume_job(self, thread_id: str, request: JobRequest) -> JobHandle:
        if not thread_id or len(thread_id) > 256:
            raise ValueError("thread_id must be 1..256 characters")
        await self._ensure_started()
        response = await self._rpc(
            "thread/resume",
            {
                "threadId": thread_id,
                "model": request.model,
                "cwd": str(request.cwd),
                "approvalPolicy": "never",
                "sandbox": _legacy_sandbox(request.sandbox),
            },
        )
        resumed_id = _nested_string(response, "thread", "id")
        if resumed_id != thread_id:
            await self.close()
            raise RuntimeOutcomeUnknown("thread/resume succeeded with an untrusted thread identity")
        return await self._start_turn(thread_id, request, resumed=True)

    async def interrupt(self, job_id: str) -> None:
        state = self._require_job(job_id)
        handle = state.handle
        if handle.status.terminal:
            return
        if handle.thread_id is None or handle.turn_id is None:
            raise RuntimeProtocolError("running job has no thread/turn identity")
        await self._rpc(
            "turn/interrupt",
            {"threadId": handle.thread_id, "turnId": handle.turn_id},
        )

    async def events(self, job_id: str) -> AsyncIterator[RuntimeEvent]:
        state = self._require_job(job_id)
        while True:
            event = await state.queue.get()
            if event is None:
                break
            yield event

    def status(self, job_id: str) -> JobHandle:
        return self._require_job(job_id).handle

    def usage(self, job_id: str) -> TokenUsage | None:
        return self._require_job(job_id).usage

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for state in self._jobs.values():
            if state.deadline_task is not None:
                state.deadline_task.cancel()
        process = self._process
        if process is not None and process.returncode is None:
            await self._terminate_process_group(process)
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task is not None),
            return_exceptions=True,
        )
        self._fail_pending(RuntimeUnavailable("Codex app-server adapter closed"))
        for state in self._jobs.values():
            if not state.handle.status.terminal:
                self._finish_job(state, JobStatus.UNKNOWN, "runtime closed before terminal status")

    async def _ensure_started(self) -> None:
        if self._closed:
            raise RuntimeUnavailable("Codex app-server adapter is closed")
        async with self._start_lock:
            if self._closed:
                raise RuntimeUnavailable("Codex app-server adapter is closed")
            if self._process is not None:
                if self._process.returncode is not None:
                    raise RuntimeUnavailable(
                        f"Codex app-server exited with {self._process.returncode}: "
                        f"{self._stderr_tail}"
                    )
                if self._initialized:
                    return
            else:
                # Do not hand every service secret to the model runtime. Codex
                # authentication is read from CODEX_HOME/HOME; callers may add
                # an explicit variable through ``environment`` when required.
                env = {
                    key: value
                    for key, value in os.environ.items()
                    if key in _CHILD_ENVIRONMENT_KEYS
                }
                if self._environment is not None:
                    env.update(self._environment)
                await self._verify_executable(env)
                try:
                    self._process = await asyncio.create_subprocess_exec(
                        self._executable,
                        "app-server",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                        start_new_session=True,
                        limit=MAX_EVENT_LINE_BYTES + 1,
                    )
                except (OSError, ValueError) as exc:
                    raise RuntimeUnavailable(f"could not start Codex app-server: {exc}") from exc
                self._reader_task = asyncio.create_task(
                    self._read_stdout(), name="m1lab-codex-stdout"
                )
                self._stderr_task = asyncio.create_task(
                    self._read_stderr(), name="m1lab-codex-stderr"
                )
            try:
                await asyncio.wait_for(
                    self._rpc(
                        "initialize",
                        {
                            "clientInfo": {
                                "name": "m1_power_lab",
                                "title": "M1 Power Lab",
                                "version": "0.1.0",
                            }
                        },
                    ),
                    timeout=self._startup_timeout,
                )
                await self._notify("initialized", {})
                self._initialized = True
            except BaseException:
                await self.close()
                raise

    async def _verify_executable(self, env: Mapping[str, str]) -> None:
        executable = shutil.which(self._executable, path=env.get("PATH"))
        if executable is None:
            raise RuntimeUnavailable(f"pinned Codex executable was not found: {self._executable}")
        try:
            resolved = Path(executable).resolve(strict=True)
            digest = hashlib.sha256()
            with resolved.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            actual_sha256 = digest.hexdigest()
        except OSError as exc:
            raise RuntimeUnavailable(f"could not verify pinned Codex executable: {exc}") from exc
        if actual_sha256 != self._expected_sha256:
            raise RuntimeUnavailable(
                "Codex executable SHA-256 pin mismatch "
                f"(expected {self._expected_sha256}, got {actual_sha256})"
            )
        self._executable = str(resolved)

    async def _start_turn(
        self, thread_id: str, request: JobRequest, *, resumed: bool
    ) -> JobHandle:
        job_id = str(uuid4())
        starting = JobHandle(job_id, thread_id, None, JobStatus.STARTING, resumed)
        state = _JobState(starting, asyncio.Queue())
        self._jobs[job_id] = state
        self._thread_to_jobs.setdefault(thread_id, []).append(job_id)
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": request.prompt}],
            "cwd": str(request.cwd),
            "model": request.model,
            "approvalPolicy": "never",
            "sandboxPolicy": _sandbox_policy(request),
        }
        if request.output_schema is not None:
            params["outputSchema"] = dict(request.output_schema)
        # Keep app-server turns below Ultra so proactive subagent work cannot
        # bypass M1 Power Lab's durable helper-job and usage scheduler.
        params["effort"] = request.reasoning_effort or "medium"
        try:
            response = await self._rpc("turn/start", params)
            turn_id = _nested_string(response, "turn", "id")
            if turn_id is None:
                await self.close()
                raise RuntimeOutcomeUnknown("turn/start succeeded without a turn identity")
            self._turn_to_job[turn_id] = job_id
            if state.handle.turn_id is None:
                state.handle = JobHandle(job_id, thread_id, turn_id, JobStatus.RUNNING, resumed)
            elif state.handle.turn_id != turn_id:
                await self.close()
                raise RuntimeOutcomeUnknown("turn/start returned conflicting turn identities")
            if state.handle.status.terminal:
                return state.handle
            state.deadline_task = asyncio.create_task(
                self._enforce_deadline(job_id, request.deadline_seconds),
                name=f"m1lab-codex-deadline-{job_id}",
            )
            return state.handle
        except RuntimeOutcomeUnknown as exc:
            self._finish_job(state, JobStatus.UNKNOWN, str(exc))
            raise
        except BaseException as exc:
            self._finish_job(state, JobStatus.FAILED, str(exc))
            raise

    async def _enforce_deadline(self, job_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            state = self._jobs.get(job_id)
            if state is not None and not state.handle.status.terminal:
                try:
                    await asyncio.wait_for(self.interrupt(job_id), timeout=5.0)
                except (RuntimeErrorBase, TimeoutError) as exc:
                    self._finish_job(state, JobStatus.UNKNOWN, f"deadline interrupt failed: {exc}")
                    process = self._process
                    if process is not None and process.returncode is None:
                        await self._terminate_process_group(process)
                    return
                for _ in range(20):
                    await asyncio.sleep(0.25)
                    if state.handle.status.terminal:
                        return
                self._finish_job(
                    state,
                    JobStatus.UNKNOWN,
                    "deadline interrupt was not confirmed by a terminal event",
                )
                process = self._process
                if process is not None and process.returncode is None:
                    await self._terminate_process_group(process)
        except asyncio.CancelledError:
            return

    async def _rpc(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if method not in _OUTGOING_METHODS:
            raise RuntimeProtocolError(f"RPC method is not allowlisted: {method}")
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeUnavailable("Codex app-server is not running")
        self._request_id += 1
        request_id = self._request_id
        future: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
            "params": dict(params),
        }
        try:
            # Each request ID is written exactly once. Retrying state-changing
            # RPCs here could duplicate thread or turn creation after an
            # ambiguous transport failure.
            await self._write_json(message)
            return await asyncio.wait_for(future, timeout=self._request_timeout)
        except TimeoutError as exc:
            if method in _STATE_CHANGING_METHODS:
                await self.close()
                raise RuntimeOutcomeUnknown(
                    f"{method} may have been accepted; its response was not received"
                ) from exc
            raise RuntimeProtocolError(f"timed out waiting for {method}") from exc
        except RuntimeErrorBase as exc:
            if method in _STATE_CHANGING_METHODS and not isinstance(
                exc, (RuntimeRequestRejected, RuntimeRequestNotSent)
            ):
                await self.close()
                raise RuntimeOutcomeUnknown(
                    f"{method} may have been accepted before the runtime connection failed: {exc}"
                ) from exc
            raise
        except asyncio.CancelledError as exc:
            if method in _STATE_CHANGING_METHODS:
                await asyncio.shield(self.close())
                raise RuntimeOutcomeUnknown(
                    f"{method} may have been accepted before the request was cancelled"
                ) from exc
            raise
        finally:
            self._pending.pop(request_id, None)

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        if method != "initialized":
            raise RuntimeProtocolError(f"notification is not allowlisted: {method}")
        await self._write_json({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    async def _write_json(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise RuntimeRequestNotSent("Codex app-server transport is unavailable")
        encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        async with self._write_lock:
            try:
                process.stdin.write(encoded)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise RuntimeUnavailable("Codex app-server pipe closed") from exc

    async def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        failure: BaseException | None = None
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_EVENT_LINE_BYTES:
                    raise RuntimeProtocolError("app-server event exceeds line-size bound")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeProtocolError("app-server emitted invalid JSON") from exc
                if not isinstance(message, dict):
                    raise RuntimeProtocolError("app-server emitted a non-object JSON value")
                await self._route_message(message)
        except asyncio.CancelledError:
            return
        except BaseException as exc:
            failure = exc
        finally:
            if failure is None and not self._closed:
                failure = RuntimeUnavailable("Codex app-server stdout closed")
            if failure is not None:
                self._fail_pending(failure)
                for state in self._jobs.values():
                    if not state.handle.status.terminal:
                        self._finish_job(state, JobStatus.UNKNOWN, str(failure))

    async def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            while True:
                chunk = await process.stderr.read(4_096)
                if not chunk:
                    return
                text = chunk.decode(errors="replace")
                self._stderr_tail = (self._stderr_tail + text)[-MAX_STDERR_CHARS:]
        except asyncio.CancelledError:
            return

    async def _route_message(self, message: Mapping[str, Any]) -> None:
        response_id = message.get("id")
        method = message.get("method")
        if isinstance(response_id, int) and not isinstance(method, str):
            future = self._pending.get(response_id)
            if future is None or future.done():
                return
            error = message.get("error")
            if error is not None:
                code = error.get("code") if isinstance(error, dict) else None
                error_type = (
                    RuntimeRequestRejected
                    if code in _NON_EXECUTING_RPC_ERROR_CODES
                    else RuntimeProtocolError
                )
                future.set_exception(error_type(f"app-server RPC error: {error}"))
                return
            result = message.get("result", {})
            if not isinstance(result, dict):
                future.set_exception(RuntimeProtocolError("app-server result is not an object"))
            else:
                future.set_result(result)
            return
        if isinstance(response_id, (int, str)) and isinstance(method, str):
            await self._reject_server_request(response_id, method)
            return
        if isinstance(method, str):
            params = message.get("params", {})
            if isinstance(params, dict):
                self._record_notification(method, params)

    async def _reject_server_request(self, request_id: int | str, method: str) -> None:
        # Approval, elicitation, dynamic-tool and attestation requests are not
        # part of this adapter.  The job uses approvalPolicy=never; any request
        # that still arrives fails closed instead of gaining coordinator power.
        await self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"M1 Power Lab client does not implement server request {method}",
                },
            }
        )

    def _record_notification(self, method: str, params: Mapping[str, Any]) -> None:
        thread_id = _string(params.get("threadId")) or _nested_string(params, "thread", "id")
        turn_id = _string(params.get("turnId")) or _nested_string(params, "turn", "id")
        job_id = self._turn_to_job.get(turn_id or "")
        if job_id is None and thread_id is not None:
            candidates = self._thread_to_jobs.get(thread_id, [])
            for candidate in reversed(candidates):
                if not self._jobs[candidate].handle.status.terminal:
                    job_id = candidate
                    break
        if job_id is None:
            return
        state = self._jobs[job_id]
        if turn_id is not None:
            self._turn_to_job[turn_id] = job_id
            handle = state.handle
            if handle.turn_id is None:
                state.handle = JobHandle(
                    handle.job_id,
                    handle.thread_id,
                    turn_id,
                    JobStatus.RUNNING,
                    handle.resumed,
                    handle.message,
                )
        self._event_sequence += 1
        event = RuntimeEvent(
            self._event_sequence,
            job_id,
            method,
            thread_id or state.handle.thread_id,
            turn_id or state.handle.turn_id,
            params,
        )
        state.queue.put_nowait(event)
        if method == "thread/tokenUsage/updated":
            state.usage = _normalize_usage(params)
        if method == "turn/completed":
            raw_status = _nested_string(params, "turn", "status")
            status = {
                "completed": JobStatus.COMPLETED,
                "interrupted": JobStatus.INTERRUPTED,
                "failed": JobStatus.FAILED,
            }.get(raw_status or "", JobStatus.UNKNOWN)
            message = ""
            error = params.get("turn")
            if isinstance(error, dict) and isinstance(error.get("error"), dict):
                message = _string(error["error"].get("message")) or ""
            self._finish_job(state, status, message, enqueue_terminal=False)

    def _finish_job(
        self,
        state: _JobState,
        status: JobStatus,
        message: str,
        *,
        enqueue_terminal: bool = True,
    ) -> None:
        if state.handle.status.terminal:
            return
        handle = state.handle
        state.handle = JobHandle(
            handle.job_id,
            handle.thread_id,
            handle.turn_id,
            status,
            handle.resumed,
            message[:4_096],
        )
        if state.deadline_task is not None and state.deadline_task is not asyncio.current_task():
            state.deadline_task.cancel()
        if enqueue_terminal:
            self._event_sequence += 1
            state.queue.put_nowait(
                RuntimeEvent(
                    self._event_sequence,
                    handle.job_id,
                    "runtime/terminal",
                    handle.thread_id,
                    handle.turn_id,
                    {"status": status.value, "message": message[:4_096]},
                )
            )
        state.queue.put_nowait(None)

    def _require_job(self, job_id: str) -> _JobState:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"unknown runtime job: {job_id}") from exc

    def _fail_pending(self, error: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    @staticmethod
    def _signal_process_group(process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        except (PermissionError, OSError):
            if sig is signal.SIGTERM:
                process.terminate()
            else:
                process.kill()

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
        *,
        grace_seconds: float | None = None,
    ) -> None:
        grace = PROCESS_SHUTDOWN_GRACE_SECONDS if grace_seconds is None else grace_seconds
        self._signal_process_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
        except TimeoutError:
            pass
        if self._process_group_exists(process.pid):
            self._signal_process_group(process, signal.SIGKILL)
        if process.returncode is None:
            await process.wait()

    @staticmethod
    def _process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


class NoopCodexAdapter:
    """Offline adapter that records an explicit unavailable disposition."""

    def __init__(self, reason: str = "Codex runtime is disabled for offline operation") -> None:
        self._reason = reason
        self._jobs: dict[str, _JobState] = {}
        self._sequence = 0

    async def start_job(self, request: JobRequest) -> JobHandle:
        del request
        return self._new_unavailable_job(resumed=False)

    async def resume_job(self, thread_id: str, request: JobRequest) -> JobHandle:
        del request
        if not thread_id:
            raise ValueError("thread_id must be non-empty")
        return self._new_unavailable_job(resumed=True, thread_id=thread_id)

    async def interrupt(self, job_id: str) -> None:
        self._require_job(job_id)

    async def events(self, job_id: str) -> AsyncIterator[RuntimeEvent]:
        state = self._require_job(job_id)
        while True:
            event = await state.queue.get()
            if event is None:
                break
            yield event

    def status(self, job_id: str) -> JobHandle:
        return self._require_job(job_id).handle

    def usage(self, job_id: str) -> TokenUsage | None:
        self._require_job(job_id)
        return None

    async def close(self) -> None:
        return None

    def _new_unavailable_job(
        self, *, resumed: bool, thread_id: str | None = None
    ) -> JobHandle:
        job_id = str(uuid4())
        handle = JobHandle(
            job_id,
            thread_id,
            None,
            JobStatus.UNAVAILABLE,
            resumed,
            self._reason,
        )
        queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()
        self._sequence += 1
        queue.put_nowait(
            RuntimeEvent(
                self._sequence,
                job_id,
                "runtime/unavailable",
                thread_id,
                None,
                {"status": JobStatus.UNAVAILABLE.value, "message": self._reason},
            )
        )
        queue.put_nowait(None)
        self._jobs[job_id] = _JobState(handle, queue)
        return handle

    def _require_job(self, job_id: str) -> _JobState:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"unknown runtime job: {job_id}") from exc


def _legacy_sandbox(mode: SandboxMode) -> str:
    return mode.value


def _sandbox_policy(request: JobRequest) -> dict[str, Any]:
    if request.sandbox is SandboxMode.READ_ONLY:
        return {
            "type": "readOnly",
            "access": {
                "type": "restricted",
                "includePlatformDefaults": True,
                "readableRoots": [str(request.cwd)],
            },
        }
    return {
        "type": "workspaceWrite",
        "writableRoots": [str(path) for path in request.writable_roots],
        "readOnlyAccess": {
            "type": "restricted",
            "includePlatformDefaults": True,
            "readableRoots": [str(request.cwd)],
        },
        "networkAccess": False,
    }


def _normalize_usage(params: Mapping[str, Any]) -> TokenUsage:
    usage: Mapping[str, Any] = params
    for key in ("tokenUsage", "usage", "total"):
        candidate = usage.get(key)
        if isinstance(candidate, dict):
            usage = candidate
    return TokenUsage(
        input_tokens=_integer_from(usage, "inputTokens", "input_tokens"),
        cached_input_tokens=_integer_from(
            usage, "cachedInputTokens", "cached_input_tokens", "cachedTokens"
        ),
        output_tokens=_integer_from(usage, "outputTokens", "output_tokens"),
        reasoning_output_tokens=_integer_from(
            usage, "reasoningOutputTokens", "reasoning_output_tokens", "reasoningTokens"
        ),
        total_tokens=_integer_from(usage, "totalTokens", "total_tokens"),
        cumulative=True,
        raw=params,
    )


def _integer_from(mapping: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _nested_string(mapping: Mapping[str, Any], *keys: str) -> str | None:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return _string(value)


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
