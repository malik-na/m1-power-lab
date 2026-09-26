"""Durable orchestration of bounded Codex investigation turns.

This module deliberately has no hardware dependency. Model output is stored as
evidence/proposals and cannot dispatch a target operation.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from pathlib import Path
from typing import Any, Callable

from m1lab.adapters import (
    CodexRuntime,
    JobHandle,
    JobRequest,
    JobStatus,
    RuntimeEvent,
    RuntimeOutcomeUnknown,
    SandboxMode,
    TokenUsage,
)
from m1lab.core import CoreApp, JobCreate, JobRecord, ReservationRequest, UsageUpdate
from m1lab.core.models import utc_now

from .models import InvestigationRequest, JobInterruption, JobLaunch
from .prompts import OUTPUT_SCHEMA, bounded, build_manifest, build_prompt, scrub_text


_EVENT_ARTIFACT_METHODS = frozenset({"item/completed", "turn/completed", "runtime/terminal", "runtime/unavailable"})
_MAX_SUMMARIES = 120


class InvestigationOrchestrator:
    """Coordinates CoreApp admission and a CodexRuntime without hardware access."""

    def __init__(
        self,
        core: CoreApp,
        runtime: CodexRuntime,
        *,
        workspace: Path,
        host_blockers: Callable[[], list[str]] | None = None,
    ) -> None:
        if not workspace.is_absolute():
            raise ValueError("Codex workspace must be absolute")
        self._core = core
        self._runtime = runtime
        self._workspace = workspace.resolve()
        self._host_blockers = host_blockers
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._runtime_ids: dict[str, str] = {}
        self._reservations: dict[str, str] = {}

    async def start(self, request: InvestigationRequest) -> JobLaunch:
        return await self._launch(request, thread_id=None)

    async def resume(self, thread_id: str, request: InvestigationRequest) -> JobLaunch:
        if not thread_id or len(thread_id) > 256:
            raise ValueError("thread_id must be 1..256 characters")
        return await self._launch(request, thread_id=thread_id)

    async def interrupt(self, job_id: str) -> JobInterruption:
        record = self._core.job(job_id)
        runtime_id = record.runtime_id or self._runtime_ids.get(job_id)
        if runtime_id is None:
            raise RuntimeError(f"job {job_id} has no runtime identity")
        await self._runtime.interrupt(runtime_id)
        return JobInterruption(job_id=job_id, runtime_id=runtime_id, requested=True)

    async def wait(self, job_id: str) -> JobRecord:
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.shield(task)
        return self._core.job(job_id)

    def job(self, job_id: str) -> JobRecord:
        return self._core.job(job_id)

    async def close(self) -> None:
        active_runtime_ids = [
            self._runtime_ids[job_id]
            for job_id, task in self._tasks.items()
            if not task.done() and job_id in self._runtime_ids
        ]
        try:
            if active_runtime_ids:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(self._runtime.interrupt(runtime_id) for runtime_id in active_runtime_ids),
                        return_exceptions=True,
                    ),
                    timeout=5.0,
                )
        except TimeoutError:
            pass
        finally:
            await self._runtime.close()
        active = [task for task in self._tasks.values() if not task.done()]
        if active:
            try:
                await asyncio.wait_for(asyncio.gather(*active, return_exceptions=True), timeout=10.0)
            except TimeoutError:
                for task in active:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*active, return_exceptions=True)

    async def _launch(self, request: InvestigationRequest, *, thread_id: str | None) -> JobLaunch:
        if request.cwd.resolve() != self._workspace:
            raise ValueError("Codex job cwd must be the configured dedicated workspace")
        self._require_host_readiness()
        evidence_artifacts = []
        for evidence in request.evidence:
            cleaned = scrub_text(evidence.content).encode("utf-8")
            clean_label = scrub_text(evidence.label)
            evidence_artifacts.append(
                self._core.publish_artifact(
                    cleaned,
                    media_type=evidence.media_type,
                    provenance={
                        "session_id": request.session_id,
                        "kind": "investigation_evidence",
                        "label": clean_label,
                        "credential_scrubbed": True,
                        "personal_data_patterns_scrubbed": ["email address", "home-directory prefix"],
                    },
                )
            )

        manifest = build_manifest(self._core, request, evidence_artifacts)
        prompt = build_prompt(request, manifest)
        now = utc_now()
        deadline_at = now + timedelta(seconds=request.deadline_seconds)
        reservation = self._core.reserve_budget(
            ReservationRequest(
                session_id=request.session_id,
                purpose=f"Codex {request.kind} turn",
                tokens=request.estimated_tokens,
                active_seconds=request.estimated_active_seconds,
                expires_at=deadline_at,
            )
        )
        manifest = dict(manifest)
        manifest["admission"] = {
            "reservation_id": reservation.id,
            "estimated_tokens": request.estimated_tokens,
            "estimated_active_seconds": request.estimated_active_seconds,
        }
        if thread_id is not None:
            manifest["resume"] = {"thread_id": thread_id}

        durable: JobRecord | None = None
        handle: JobHandle | None = None
        try:
            self._require_host_readiness()
            durable = self._core.create_job(
                JobCreate(
                    session_id=request.session_id,
                    kind=request.kind,
                    parent_job_id=request.parent_job_id,
                    evidence_manifest=manifest,
                    lease_expires_at=deadline_at,
                    deadline_at=deadline_at,
                )
            )
            runtime_request = JobRequest(
                prompt=prompt,
                cwd=request.cwd,
                model=request.model,
                deadline_seconds=request.deadline_seconds,
                sandbox=SandboxMode.READ_ONLY,
                output_schema=OUTPUT_SCHEMA,
                reasoning_effort=request.reasoning_effort,
            )
            self._require_host_readiness()
            handle = (
                await self._runtime.start_job(runtime_request)
                if thread_id is None
                else await self._runtime.resume_job(thread_id, runtime_request)
            )
            running = self._core.update_job(
                durable.id,
                state="running" if not handle.status.terminal else _core_state(handle.status),
                runtime_id=handle.job_id,
                result=_initial_result(handle, reservation.id),
            )
        except BaseException as exc:
            if durable is not None:
                outcome_unknown = isinstance(exc, RuntimeOutcomeUnknown) or (
                    handle is not None and handle.status is not JobStatus.UNAVAILABLE
                )
                result = {
                    "error": _safe_error(exc),
                    "reservation_id": reservation.id,
                    "outcome_uncertain": outcome_unknown,
                    "thread_id": handle.thread_id if handle is not None else thread_id,
                    "turn_id": handle.turn_id if handle is not None else None,
                }
                if outcome_unknown:
                    self._core.mark_job_unknown(
                        durable.id,
                        reason=_safe_error(exc),
                        result=result,
                        runtime_id=handle.job_id if handle is not None else None,
                    )
                else:
                    self._core.update_job(
                        durable.id,
                        state="failed",
                        result=result,
                    )
            self._release_once(durable.id if durable else None, reservation.id)
            raise

        self._runtime_ids[durable.id] = handle.job_id
        self._reservations[durable.id] = reservation.id
        task = asyncio.create_task(
            self._consume(
                durable.id,
                request.session_id,
                handle,
                reservation.id,
                request.estimated_tokens,
            ),
            name=f"m1lab-investigator-{durable.id}",
        )
        self._tasks[durable.id] = task
        task.add_done_callback(lambda _task, job_id=durable.id: self._task_finished(job_id))
        return JobLaunch(
            job_id=durable.id,
            runtime_id=handle.job_id,
            thread_id=handle.thread_id,
            state=running.state,
        )

    def _require_host_readiness(self) -> None:
        if self._host_blockers is None:
            return
        blockers = self._host_blockers()
        if blockers:
            raise ValueError("host work admission is closed: " + "; ".join(blockers))

    async def _consume(
        self,
        job_id: str,
        session_id: str,
        handle: JobHandle,
        reservation_id: str,
        estimated_tokens: int,
    ) -> None:
        summaries: list[dict[str, Any]] = []
        artifact_ids: list[str] = []
        last_sequence = 0
        consumption_error: BaseException | None = None
        interruption_requested = False
        try:
            async for event in self._runtime.events(handle.job_id):
                last_sequence = max(last_sequence, event.sequence)
                summary = _event_summary(event)
                if summary is not None:
                    summaries.append(summary)
                    summaries = summaries[-_MAX_SUMMARIES:]
                if event.method in _EVENT_ARTIFACT_METHODS:
                    artifact = self._core.publish_artifact(
                        json.dumps(_event_document(event), sort_keys=True, ensure_ascii=False).encode(),
                        media_type="application/vnd.m1lab.runtime-event+json",
                        provenance={
                            "session_id": session_id,
                            "job_id": job_id,
                            "runtime_id": handle.job_id,
                            "sequence": event.sequence,
                            "method": event.method,
                        },
                    )
                    artifact_ids.append(artifact.id)
                if event.method == "thread/tokenUsage/updated":
                    should_interrupt = self._account_live_usage(
                        session_id,
                        job_id,
                        handle,
                        event.sequence,
                        estimated_tokens,
                    )
                    if should_interrupt and not interruption_requested:
                        interruption_requested = True
                        await self._runtime.interrupt(handle.job_id)
                self._core.update_job(
                    job_id,
                    state="running" if not handle.status.terminal else _core_state(handle.status),
                    runtime_id=handle.job_id,
                    result={
                        **_initial_result(handle, reservation_id),
                        "event_summaries": summaries,
                        "event_artifact_ids": artifact_ids,
                        "last_runtime_sequence": last_sequence,
                    },
                )
                if (
                    not interruption_requested
                    and self._core.budget_limit_reached(session_id)
                ):
                    interruption_requested = True
                    await self._runtime.interrupt(handle.job_id)
        except BaseException as exc:
            consumption_error = exc

        try:
            final_handle = self._runtime.status(handle.job_id)
        except BaseException as exc:
            final_handle = JobHandle(
                handle.job_id, handle.thread_id, handle.turn_id, JobStatus.UNKNOWN,
                handle.resumed, _safe_error(exc),
            )
        if consumption_error is not None and final_handle.status not in {JobStatus.UNKNOWN, JobStatus.FAILED}:
            final_handle = JobHandle(
                final_handle.job_id,
                final_handle.thread_id,
                final_handle.turn_id,
                JobStatus.UNKNOWN,
                final_handle.resumed,
                _safe_error(consumption_error),
            )

        try:
            try:
                usage_result = self._account_usage(session_id, job_id, final_handle)
            except BaseException as exc:
                usage_result = {
                    "reported": False,
                    "uncertain": True,
                    "reason": f"usage reconciliation failed: {_safe_error(exc)}",
                }
                try:
                    self._core.mark_usage_uncertain(
                        session_id,
                        final_handle.thread_id or final_handle.job_id,
                        str(usage_result["reason"]),
                    )
                except BaseException:
                    pass
            result = {
                **_initial_result(final_handle, reservation_id),
                "event_summaries": summaries,
                "event_artifact_ids": artifact_ids,
                "last_runtime_sequence": last_sequence,
                "usage": usage_result,
                "proposal_only": True,
            }
            if consumption_error is not None:
                result["stream_error"] = _safe_error(consumption_error)
            self._core.update_job(
                job_id,
                state=_core_state(final_handle.status),
                runtime_id=handle.job_id,
                result=result,
            )
        finally:
            self._release_once(job_id, reservation_id)

    def _account_live_usage(
        self,
        session_id: str,
        job_id: str,
        handle: JobHandle,
        sequence: int,
        admitted_tokens: int,
    ) -> bool:
        usage = self._runtime.usage(handle.job_id)
        if usage is None:
            return False
        if usage.total_tokens is not None:
            input_tokens, output_tokens = usage.total_tokens, 0
        elif usage.input_tokens is not None and usage.output_tokens is not None:
            input_tokens, output_tokens = usage.input_tokens, usage.output_tokens
        else:
            return False
        observed = input_tokens + output_tokens
        self._core.report_usage(
            UsageUpdate(
                report_id=f"usage:{job_id}:live:{sequence}",
                session_id=session_id,
                source_id=handle.thread_id or handle.job_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cumulative=usage.cumulative is not False,
                terminal=False,
            )
        )
        return (
            observed >= admitted_tokens
            or self._core.budget_limit_reached(session_id)
            or self._core.snapshot(session_id).budget.usage_uncertain
        )

    def _account_usage(self, session_id: str, job_id: str, handle: JobHandle) -> dict[str, Any]:
        try:
            usage = self._runtime.usage(handle.job_id)
        except BaseException as exc:
            usage = None
            usage_error = _safe_error(exc)
        else:
            usage_error = None

        if handle.status is JobStatus.UNAVAILABLE:
            self._core.report_usage(
                UsageUpdate(
                    report_id=f"usage:{job_id}:terminal",
                    session_id=session_id,
                    source_id=handle.thread_id or handle.job_id,
                    input_tokens=0,
                    output_tokens=0,
                    cumulative=True,
                    terminal=True,
                )
            )
            return {"reported": True, "tokens": 0, "uncertain": False}

        normalized, uncertainty = _normalize_terminal_usage(usage)
        if handle.status is JobStatus.INTERRUPTED and normalized is not None:
            # Counts may cover an earlier completed response; cancellation can
            # leave the last response unreported even after a usage notification.
            uncertainty = "interrupted response usage coverage was not confirmed"
        if usage_error:
            uncertainty = f"runtime usage lookup failed: {usage_error}"
        if normalized is not None:
            input_tokens, output_tokens, cumulative = normalized
            self._core.report_usage(
                UsageUpdate(
                    report_id=f"usage:{job_id}:terminal",
                    session_id=session_id,
                    source_id=handle.thread_id or handle.job_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cumulative=cumulative,
                    terminal=handle.status is not JobStatus.INTERRUPTED,
                )
            )
        if uncertainty is not None:
            self._core.mark_usage_uncertain(session_id, handle.thread_id or handle.job_id, uncertainty)
        return {
            "reported": normalized is not None,
            "tokens": None if normalized is None else normalized[0] + normalized[1],
            "cumulative": None if normalized is None else normalized[2],
            "uncertain": uncertainty is not None,
            "reason": uncertainty,
            "provider": bounded(usage.raw) if usage is not None else None,
        }

    def _release_once(self, job_id: str | None, reservation_id: str) -> None:
        if job_id is not None:
            known = self._reservations.pop(job_id, reservation_id)
            if known != reservation_id:
                raise RuntimeError("reservation identity changed while job was running")
        try:
            self._core.release_budget(reservation_id)
        except Exception as exc:
            if "does not exist" not in str(exc):
                raise

    def _task_finished(self, job_id: str) -> None:
        self._runtime_ids.pop(job_id, None)
        self._tasks.pop(job_id, None)


def _normalize_terminal_usage(usage: TokenUsage | None) -> tuple[tuple[int, int, bool] | None, str | None]:
    if usage is None:
        return None, "terminal provider usage was absent"
    if usage.total_tokens is not None:
        cumulative = usage.cumulative is not False
        uncertainty = None if usage.cumulative is not None else "provider total token scope was ambiguous"
        if (
            usage.input_tokens is not None
            and usage.output_tokens is not None
            and usage.total_tokens < usage.input_tokens + usage.output_tokens
        ):
            uncertainty = "provider total tokens were smaller than its input/output counts"
        return (usage.total_tokens, 0, cumulative), uncertainty
    if usage.input_tokens is None or usage.output_tokens is None:
        return None, "terminal provider usage omitted total or input/output counts"
    cumulative = usage.cumulative is not False
    uncertainty = None if usage.cumulative is not None else "provider usage scope was ambiguous"
    return (usage.input_tokens, usage.output_tokens, cumulative), uncertainty


def _initial_result(handle: JobHandle, reservation_id: str) -> dict[str, Any]:
    return {
        "runtime_status": handle.status.value,
        "thread_id": handle.thread_id,
        "turn_id": handle.turn_id,
        "resumed": handle.resumed,
        "message": scrub_text(handle.message),
        "reservation_id": reservation_id,
        "proposal_only": True,
    }


def _event_summary(event: RuntimeEvent) -> dict[str, Any] | None:
    if event.method == "thread/tokenUsage/updated":
        return {"sequence": event.sequence, "method": event.method, "usage_updated": True}
    if event.method.startswith(("item/", "turn/", "runtime/")):
        payload = bounded(event.payload)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {
            "sequence": event.sequence,
            "method": event.method,
            "thread_id": event.thread_id,
            "turn_id": event.turn_id,
            "payload_excerpt": encoded[:4_000],
        }
    return None


def _event_document(event: RuntimeEvent) -> dict[str, Any]:
    raw = json.dumps(dict(event.payload), sort_keys=True, ensure_ascii=False, default=str)
    scrubbed = scrub_text(raw)
    return {
        "format": "m1lab-runtime-event-v1",
        "sequence": event.sequence,
        "method": event.method,
        "thread_id": event.thread_id,
        "turn_id": event.turn_id,
        "payload_json": scrubbed,
        "payload_truncated": False,
    }


def _core_state(status: JobStatus) -> str:
    return {
        JobStatus.STARTING: "running",
        JobStatus.RUNNING: "running",
        JobStatus.COMPLETED: "completed",
        JobStatus.INTERRUPTED: "interrupted",
        JobStatus.FAILED: "failed",
        JobStatus.UNAVAILABLE: "failed",
        JobStatus.UNKNOWN: "unknown",
    }[status]


def _safe_error(exc: BaseException) -> str:
    return scrub_text(f"{type(exc).__name__}: {exc}")[:4_000]
