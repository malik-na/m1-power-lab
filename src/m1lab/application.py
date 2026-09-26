"""Application wiring between the durable coordinator and operator surfaces."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
import os
from typing import Any

from m1lab.core import (
    ACTIVE_PHASES,
    ApprovalScope,
    CommandKind,
    CoreApp,
    OwnerCommand,
    SessionPhase,
)
from m1lab.core.errors import CoreError
from m1lab.core.journal import json_load
from m1lab.core.models import utc_now
from m1lab.investigator import InvestigationOrchestrator, InvestigationRequest
from m1lab.notifications import PushConfig, PushNotifications
from m1lab.host import HostAdmissionPolicy, LinuxHostMonitor
from m1lab.science import (
    EvidenceBrief,
    Exclusion,
    ProtocolAdherence,
    PublishedScientificRecord,
    RegressionCheck,
    ScientificRecord,
    ScientificRecordStore,
)
from m1lab.web.facade import (
    CommandReceipt,
    OperatorCommand,
    Owner,
    UIEvent,
    ViewName,
)


_COMMANDS: dict[str, CommandKind] = {
    "session.start": CommandKind.START,
    "session.steer": CommandKind.STEER,
    "session.pause": CommandKind.PAUSE,
    "session.resume": CommandKind.RESUME,
    "session.stop": CommandKind.STOP,
    "session.complete": CommandKind.COMPLETE,
    "conversation.send": CommandKind.STEER,
    "budget.add_tokens": CommandKind.GRANT_TOKENS,
    "budget.extend_time": CommandKind.EXTEND_TIME,
    "budget.reset_time": CommandKind.RESET_TIME,
    "approval.approve": CommandKind.APPROVE,
    "approval.deny": CommandKind.DENY,
    "approval.revoke": CommandKind.REVOKE,
}

_LOG = logging.getLogger(__name__)


def latest_session_id(core: CoreApp) -> str | None:
    row = core.journal.one("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1")
    return str(row["id"]) if row else None


class CoordinatorFacade:
    """Shape coordinator state for the web UI and translate owner commands."""

    def __init__(
        self,
        core: CoreApp,
        session_id: str,
        *,
        investigator: InvestigationOrchestrator | None = None,
        model: str = "gpt-6-sol",
        workspace: str | os.PathLike[str] | None = None,
        host_monitor: LinuxHostMonitor | None = None,
        push_config: PushConfig | None = None,
    ):
        self.core = core
        self.session_id = session_id
        self.investigator = investigator
        self.model = model
        self.workspace = os.fspath(workspace or os.getcwd())
        self.host_monitor = host_monitor or LinuxHostMonitor(core.journal.paths.root)
        self.push_notifications = PushNotifications(
            core,
            session_id,
            push_config or PushConfig(),
            owner_login=core.session(session_id).owner,
        )

    def push_status(self, owner: Owner) -> dict[str, Any]:
        self._require_push_owner(owner)
        return {
            "enabled": self.push_notifications.enabled,
            "enrolled": self.push_notifications.enrolled(),
            "public_key": self.push_notifications.public_key or None,
        }

    def subscribe_push(
        self, owner: Owner, *, endpoint: str, p256dh: str, auth: str
    ) -> None:
        self._require_push_owner(owner)
        if not self.push_notifications.enabled:
            raise RuntimeError("push delivery is not configured")
        self.push_notifications.subscribe(endpoint=endpoint, p256dh=p256dh, auth=auth)

    def unsubscribe_push(self, owner: Owner, *, endpoint: str) -> bool:
        self._require_push_owner(owner)
        return self.push_notifications.unsubscribe(endpoint=endpoint)

    async def run_push_notifications(self) -> None:
        await self.push_notifications.run()

    async def run_host_safety(self) -> None:
        """Pause active work and interrupt Codex when host readiness is lost."""

        if self.investigator is None:
            return
        handled_jobs: set[str] = set()
        while True:
            try:
                blockers = HostAdmissionPolicy().blockers(self.host_monitor.sample())
            except Exception:
                _LOG.exception("host readiness sample failed")
                blockers = ["host readiness could not be sampled"]
            try:
                if not blockers:
                    handled_jobs.clear()
                else:
                    session = self.core.session(self.session_id)
                    live_jobs = {
                        job.id
                        for job in self.core.list_records(self.session_id, "jobs")
                        if job.state in {"admitted", "running"}
                    }
                    should_pause = session.phase in ACTIVE_PHASES
                    new_jobs = live_jobs - handled_jobs
                    if should_pause or new_jobs:
                        changed = self.core.pause_for_host_safety(self.session_id, blockers)
                        targets = new_jobs
                        interrupted, failures = await self._interrupt_active_jobs(targets)
                        handled_jobs.update(targets)
                        if changed or targets:
                            _LOG.warning(
                                "host readiness paused or guarded session %s; interruption requested for %s job(s), %s failed",
                                self.session_id,
                                interrupted,
                                failures,
                            )
            except Exception:
                _LOG.exception("host readiness safety action failed")
            await asyncio.sleep(5)

    def _require_push_owner(self, owner: Owner) -> None:
        if owner.login != self.core.session(self.session_id).owner:
            raise PermissionError("selected session belongs to a different owner")

    async def get_view(self, view: ViewName, owner: Owner) -> dict[str, Any]:
        snapshot = self.core.snapshot(self.session_id)
        session = snapshot.session
        if owner.login != session.owner:
            raise PermissionError("selected session belongs to a different owner")
        budget = snapshot.budget
        target = snapshot.latest_target
        host_snapshot = self.host_monitor.sample()
        alerts: list[dict[str, str]] = []
        if budget.blockers:
            alerts.append(
                {
                    "level": "warning",
                    "title": "Work admission is closed",
                    "detail": "; ".join(budget.blockers),
                }
            )
        if target is None:
            alerts.append(
                {
                    "level": "warning",
                    "title": "No target observation",
                    "detail": "Inspect a replay target or complete live transport qualification.",
                }
            )
        elif target.mode.value in {"replay", "synthetic"}:
            alerts.append(
                {
                    "level": "info",
                    "title": "Replay mode",
                    "detail": "Results exercise the workflow and do not establish M1 hardware behavior.",
                }
            )
        host_blockers = HostAdmissionPolicy().blockers(host_snapshot)
        if host_blockers:
            alerts.append(
                {
                    "level": "warning",
                    "title": "Host lab readiness is incomplete",
                    "detail": "; ".join(host_blockers),
                }
            )

        common: dict[str, Any] = {
            "revision": str(session.revision),
            "session": {
                "id": session.id,
                "state": _ui_phase(session.phase),
                "phase": session.phase.value,
                "objective": session.objective,
                "updated_at": session.updated_at.isoformat(),
            },
            "target": _target_view(target),
            "host": host_snapshot.as_view(),
            "budgets": {
                "tokens_used": budget.tokens_used,
                "tokens_limit": budget.token_limit,
                "active_seconds": round(budget.active_seconds_used, 1),
                "active_seconds_limit": round(budget.active_seconds_limit, 1),
                "lifetime_tokens": session.lifetime_tokens,
                "usage_state": "uncertain" if budget.usage_uncertain else "known",
                "epoch": "current",
            },
            "alerts": alerts,
            "pending_approval_count": self._pending_approval_count(),
            "current_step": self._current_step(),
            "experiments": self._experiments(),
            "evidence": self._evidence(),
            "approvals": self._pending_approvals(session.revision, target),
            "active_approvals": self._active_approvals(session.revision, target),
            "recovery": _recovery_view(target),
            "recovery_actions": [],
            "messages": self._messages(),
            "jobs": self._jobs(),
        }
        return common

    async def submit(self, command: OperatorCommand, owner: Owner) -> CommandReceipt:
        kind = _COMMANDS.get(command.kind)
        if kind is None:
            return CommandReceipt(
                command_id=command.command_id,
                status="rejected",
                revision=str(self.core.session(self.session_id).revision),
                message=f"Command {command.kind!r} is unavailable in this qualification state.",
            )
        try:
            expected_revision = int(command.expected_revision)
        except ValueError:
            return CommandReceipt(
                command.command_id,
                "rejected",
                str(self.core.session(self.session_id).revision),
                "Expected revision must be an integer.",
            )

        try:
            payload = dict(command.payload)
            if kind is CommandKind.STEER:
                payload["message"] = str(payload.get("message", "")).strip()
            elif kind is CommandKind.GRANT_TOKENS:
                payload = {"tokens": _positive_int(payload.get("amount")), "note": "owner web command"}
            elif kind is CommandKind.EXTEND_TIME:
                payload = {
                    "seconds": 60 * _positive_int(payload.get("minutes")),
                    "note": "owner web command",
                }
            elif kind is CommandKind.RESET_TIME:
                payload = {
                    "seconds": 60 * _positive_int(payload.get("minutes", 180)),
                    "note": "owner web command",
                }
            elif kind is CommandKind.APPROVE:
                payload = self._approval_payload(command.target_id, payload)
            elif kind is CommandKind.DENY:
                procedure_id, procedure_revision, procedure_digest = _procedure_ref(command.target_id)
                payload = {
                    "procedure_id": procedure_id,
                    "procedure_revision": procedure_revision,
                    "procedure_digest": procedure_digest,
                }
            elif kind is CommandKind.REVOKE:
                payload = {"approval_id": command.target_id}
            result = self.core.submit(
                OwnerCommand(
                    id=command.command_id,
                    session_id=self.session_id,
                    owner=owner.login,
                    kind=kind,
                    expected_revision=expected_revision,
                    payload=payload,
                )
            )
        except (CoreError, ValueError, TypeError) as exc:
            return CommandReceipt(
                command.command_id,
                "rejected",
                str(self.core.session(self.session_id).revision),
                str(exc),
            )
        message = str(result.outcome.get("reason") or f"{command.kind} recorded")
        if (
            result.status.value == "applied"
            and kind in {CommandKind.PAUSE, CommandKind.STOP}
            and self.investigator is not None
        ):
            interrupted, failures = await self._interrupt_active_jobs()
            message += f"; interruption requested for {interrupted} active job(s)"
            if failures:
                message += f"; {failures} job(s) require usage reconciliation"
        if (
            result.status.value == "applied"
            and command.kind == "conversation.send"
            and self.investigator is not None
        ):
            request = InvestigationRequest(
                session_id=self.session_id,
                instruction=payload["message"],
                cwd=self.workspace,
                model=self.model,
                kind="chat",
                estimated_tokens=100_000,
                estimated_active_seconds=900,
                deadline_seconds=900,
            )
            try:
                thread_id = self._latest_thread_id()
                launch = (
                    await self.investigator.resume(thread_id, request)
                    if thread_id
                    else await self.investigator.start(request)
                )
                message = f"Message recorded; Codex job {launch.job_id} is {launch.state}."
            except Exception as exc:
                message = f"Message recorded; Codex job was not admitted: {exc}"
        return CommandReceipt(
            command_id=result.command_id,
            status=result.status.value,
            revision=str(result.session_revision),
            message=message,
            event_cursor=str(self.core.snapshot(self.session_id).last_event_cursor),
        )

    async def stream_events(self, after_cursor: str | None, owner: Owner):
        session = self.core.session(self.session_id)
        if owner.login != session.owner:
            raise PermissionError("selected session belongs to a different owner")
        try:
            cursor = int(after_cursor or 0)
        except ValueError:
            cursor = 0
            yield UIEvent("", "snapshot_required", str(self.core.session(self.session_id).revision))
        current_cursor = self.core.snapshot(self.session_id).last_event_cursor
        if cursor > current_cursor:
            cursor = current_cursor
            yield UIEvent(
                str(cursor),
                "snapshot_required",
                str(self.core.session(self.session_id).revision),
                {"reason": "event cursor is ahead of this session"},
            )
        quiet_cycles = 0
        while True:
            events = self.core.events(self.session_id, after=cursor, limit=200)
            if events:
                quiet_cycles = 0
                for event in events:
                    cursor = event.cursor
                    yield UIEvent(
                        cursor=str(event.cursor),
                        kind=event.kind,
                        revision=str(self.core.session(self.session_id).revision),
                        payload={**event.data, "summary": _event_summary(event.kind)},
                    )
            else:
                quiet_cycles += 1
                if quiet_cycles >= 3:
                    quiet_cycles = 0
                    yield UIEvent(
                        cursor=str(cursor),
                        kind="heartbeat",
                        revision=str(self.core.session(self.session_id).revision),
                    )
            await asyncio.sleep(5)

    def export(self) -> dict[str, Any]:
        snapshot = self.core.snapshot(self.session_id)
        events = []
        cursor = 0
        while True:
            page = self.core.events(self.session_id, after=cursor, limit=2_000)
            if not page:
                break
            events.extend(page)
            cursor = page[-1].cursor
        records = {
            kind: [item.model_dump(mode="json") for item in self.core.list_records(self.session_id, kind)]
            for kind in ("procedures", "reviews", "approvals", "operations", "jobs", "artifacts")
        }
        records["scientific"] = [
            item.model_dump(mode="json")
            for item in ScientificRecordStore(self.core).list(self.session_id)
        ]
        return {
            "format": "m1-power-lab-export-v2",
            "exported_at": utc_now().isoformat(),
            "session": snapshot.session.model_dump(mode="json"),
            "budget": snapshot.budget.model_dump(mode="json"),
            "target": snapshot.latest_target.model_dump(mode="json") if snapshot.latest_target else None,
            "target_history": [
                dict(row)
                for row in self.core.journal.all(
                    "SELECT * FROM target_snapshots WHERE session_id=? ORDER BY observed_at",
                    (self.session_id,),
                )
            ],
            "events": [event.model_dump(mode="json") for event in events],
            "records": records,
        }

    def artifact(self, artifact_id: str) -> tuple[bytes, str]:
        record = self.core.session_artifact(self.session_id, artifact_id)
        content = self.core.read_artifact(
            self.session_id, artifact_id, max_bytes=64_000_000
        )
        return content, record.media_type

    def scientific_records(self) -> tuple[PublishedScientificRecord, ...]:
        return ScientificRecordStore(self.core).list(self.session_id)

    def scientific_brief(self) -> EvidenceBrief:
        records = self.scientific_records()
        if not records:
            raise ValueError("no scientific records are published for this session")
        return ScientificRecordStore(self.core).brief(records[:64])

    def publish_scientific_record(self, record: ScientificRecord) -> PublishedScientificRecord:
        if record.session_id != self.session_id:
            raise ValueError("scientific record belongs to a different session")
        return ScientificRecordStore(self.core).publish(record)

    def derive_scientific_result(
        self,
        *,
        hypothesis_id: str,
        protocol_id: str,
        observation_pairs: tuple[tuple[str, str], ...],
        adherence: ProtocolAdherence,
        regressions: tuple[RegressionCheck, ...] = (),
        exclusions: tuple[Exclusion, ...] = (),
        analysis_code_refs: tuple[str, ...] = (),
    ) -> PublishedScientificRecord:
        return ScientificRecordStore(self.core).derive_and_publish(
            session_id=self.session_id,
            hypothesis_id=hypothesis_id,
            protocol_id=protocol_id,
            observation_pairs=observation_pairs,
            adherence=adherence,
            regressions=regressions,
            exclusions=exclusions,
            analysis_code_refs=analysis_code_refs,
        )

    def _approval_payload(
        self, procedure_id: str | None, requested_scope: dict[str, Any]
    ) -> dict[str, Any]:
        procedure_id, procedure_revision, procedure_digest = _procedure_ref(procedure_id)
        row = self.core.journal.one(
            "SELECT revision, digest FROM procedures WHERE procedure_id=? AND revision=? AND digest=? AND session_id=?",
            (procedure_id, procedure_revision, procedure_digest, self.session_id),
        )
        target = self.core.snapshot(self.session_id).latest_target
        if row is None or target is None:
            raise ValueError("the exact procedure and target must be available")
        scope = ApprovalScope(
            target_identity=target.identity,
            boot_epoch=target.boot_epoch,
            configuration_digest=target.configuration_digest,
            repeat_limit=min(_positive_int(requested_scope.get("repeat", 1)), 100),
            expires_at=utc_now()
            + timedelta(minutes=min(_positive_int(requested_scope.get("minutes", 15)), 1440)),
            physical_attendance_confirmed=str(
                requested_scope.get("physical_attendance", "")
            ).lower()
            in {"on", "true", "1", "yes"},
        )
        return {
            "procedure_id": procedure_id,
            "procedure_revision": procedure_revision,
            "scope": scope.model_dump(mode="json"),
        }

    def _experiments(self) -> list[dict[str, Any]]:
        rows = self.core.journal.all(
            "SELECT p.procedure_id, p.record_json, o.id AS operation_id, o.state, o.result_json FROM procedures p "
            "LEFT JOIN operations o ON o.procedure_id=p.procedure_id AND o.procedure_revision=p.revision "
            "WHERE p.session_id=? ORDER BY p.created_at DESC LIMIT 30",
            (self.session_id,),
        )
        result = []
        for row in rows:
            procedure = json_load(row["record_json"], {})
            outcome = row["state"] or "planned"
            result.append(
                {
                    "procedure_id": row["procedure_id"],
                    "operation_id": row["operation_id"],
                    "title": procedure.get("title", "Untitled procedure"),
                    "status": outcome,
                    "revision": procedure.get("revision"),
                    "outcome": outcome,
                    "question": procedure.get("expected_benefit") or "Recorded procedure",
                    "prediction": procedure.get("expected_benefit") or "—",
                    "control": ", ".join(procedure.get("abort_conditions", [])) or "—",
                    "cost": procedure.get("limits", {}),
                    "procedure": ", ".join(op.get("kind", "") for op in procedure.get("operations", [])),
                    "interpretation": json_load(row["result_json"], {}).get("target_condition") if row["result_json"] else None,
                }
            )
        return result

    def _evidence(self) -> list[dict[str, Any]]:
        store = ScientificRecordStore(self.core)
        scientific = store.list(self.session_id)
        compact_scientific = scientific[:64]
        summaries = {
            item.record_id: item
            for item in store.manifest(compact_scientific).entries
        } if scientific else {}
        science_rows = [
            {
                "id": published.record.id,
                "kind": f"science.{published.record.record_type}",
                "title": published.record.record_type.replace("_", " ").title(),
                "summary": summaries[published.record.id].summary,
                "recorded_at": published.created_at.isoformat(),
                "revision": "immutable",
                "artifact_url": f"/api/artifacts/{published.artifact_id}",
            }
            for published in compact_scientific
        ]
        event_rows = [
            {
                "id": event.subject_id or f"event-{event.cursor}",
                "kind": event.kind,
                "title": _event_summary(event.kind),
                "summary": _summarize_data(event.data),
                "recorded_at": event.occurred_at.isoformat(),
                "revision": event.data.get("revision", "—"),
                "artifact_url": (
                    f"/api/artifacts/{event.subject_id}"
                    if event.kind == "artifact.published" and event.subject_id
                    else None
                ),
            }
            for event in reversed(self.core.events(self.session_id, limit=100))
        ]
        return (science_rows + event_rows)[:100]

    def _pending_approval_count(self) -> int:
        return len(self._pending_approvals(self.core.session(self.session_id).revision, self.core.snapshot(self.session_id).latest_target))

    def _pending_approvals(self, session_revision: int, target: Any) -> list[dict[str, Any]]:
        if self.core.session(self.session_id).phase is not SessionPhase.AWAITING_APPROVAL:
            return []
        if target is None:
            return []
        rows = self.core.journal.all(
            "SELECT p.* FROM procedures p WHERE p.session_id=? AND EXISTS ("
            "SELECT 1 FROM reviews r WHERE r.procedure_id=p.procedure_id "
            "AND r.procedure_revision=p.revision AND r.procedure_digest=p.digest "
            "AND r.disposition='accepted') ORDER BY p.created_at DESC",
            (self.session_id,),
        )
        denied = set()
        for command_row in self.core.journal.all(
            "SELECT payload_json FROM owner_commands WHERE session_id=? AND kind='deny' AND status='applied'",
            (self.session_id,),
        ):
            payload = json_load(command_row["payload_json"], {})
            denied.add(
                (
                    payload.get("procedure_id"),
                    payload.get("procedure_revision"),
                    payload.get("procedure_digest"),
                )
            )
        pending = []
        for row in rows:
            if (row["procedure_id"], row["revision"], row["digest"]) in denied:
                continue
            record = json_load(row["record_json"], {})
            operations = record.get("operations", [])
            if not any(op.get("mutates_target") for op in operations):
                continue
            if self._has_valid_approval(row, target, record):
                continue
            recovery = record.get("recovery", {})
            review_row = self.core.journal.one(
                "SELECT record_json FROM reviews WHERE procedure_id=? AND procedure_revision=? "
                "AND procedure_digest=? AND disposition='accepted' ORDER BY created_at DESC LIMIT 1",
                (row["procedure_id"], row["revision"], row["digest"]),
            )
            review = json_load(review_row["record_json"], {}) if review_row else {}
            pending.append(
                {
                    "id": f"{row['procedure_id']}@{row['revision']}@{row['digest']}",
                    "session_revision": session_revision,
                    "procedure_revision": row["revision"],
                    "digest": row["digest"][:12],
                    "title": record.get("title", "Procedure approval"),
                    "summary": f"Exact procedure revision {row['revision']} · {row['digest'][:12]}",
                    "risk_level": _risk_level(record),
                    "operations": ", ".join(op.get("kind", "") for op in operations),
                    "benefit": record.get("expected_benefit", "—"),
                    "failure_severity": record.get("failure_severity", "unknown"),
                    "attendance": record.get("physical_attendance", "not_required"),
                    "recovery": recovery.get("summary", json.dumps(recovery) if recovery else "not recorded"),
                    "expires_at": "15 minutes after approval",
                    "review_findings": "; ".join(
                        [*review.get("blocking_findings", []), *review.get("concerns", [])]
                    ),
                }
            )
        return pending

    def _active_approvals(self, session_revision: int, target: Any) -> list[dict[str, Any]]:
        rows = self.core.journal.all(
            "SELECT * FROM approvals WHERE session_id=? AND revoked_at IS NULL ORDER BY created_at DESC",
            (self.session_id,),
        )
        active = []
        for row in rows:
            scope = json_load(row["scope_json"], {})
            if not _scope_is_current(scope, row["uses"], target):
                continue
            active.append(
                {
                    "id": row["id"],
                    "revision": session_revision,
                    "title": f"Procedure {row['procedure_id']}",
                    "scope": f"target {scope.get('target_identity')} · boot {scope.get('boot_epoch')}",
                    "remaining": f"{scope.get('repeat_limit', 1) - row['uses']} use(s) remaining",
                }
            )
        return active

    def _has_valid_approval(self, procedure_row: Any, target: Any, record: dict[str, Any]) -> bool:
        rows = self.core.journal.all(
            "SELECT * FROM approvals WHERE procedure_id=? AND procedure_revision=? "
            "AND procedure_digest=? AND revoked_at IS NULL",
            (procedure_row["procedure_id"], procedure_row["revision"], procedure_row["digest"]),
        )
        for row in rows:
            scope = json_load(row["scope_json"], {})
            if not _scope_is_current(scope, row["uses"], target):
                continue
            if (
                record.get("physical_attendance") == "required"
                and not scope.get("physical_attendance_confirmed")
            ):
                continue
            return True
        return False

    async def _interrupt_active_jobs(
        self, only_job_ids: set[str] | None = None
    ) -> tuple[int, int]:
        if self.investigator is None:
            return 0, 0
        interrupted = 0
        failures = 0
        for job in self.core.list_records(self.session_id, "jobs"):
            if job.state not in {"admitted", "running"}:
                continue
            if only_job_ids is not None and job.id not in only_job_ids:
                continue
            try:
                await self.investigator.interrupt(job.id)
                interrupted += 1
            except Exception as exc:
                failures += 1
                self.core.mark_usage_uncertain(
                    self.session_id,
                    job.runtime_id or job.id,
                    f"lifecycle interruption failed: {exc}",
                )
        return interrupted, failures

    def _messages(self) -> list[dict[str, Any]]:
        rows = self.core.journal.all(
            "SELECT payload_json, submitted_at, status FROM owner_commands "
            "WHERE session_id=? AND kind='steer' ORDER BY submitted_at LIMIT 100",
            (self.session_id,),
        )
        messages = [
            {
                "role": "owner",
                "text": json_load(row["payload_json"], {}).get("message", ""),
                "created_at": row["submitted_at"],
                "status": row["status"],
            }
            for row in rows
        ]
        for row in self.core.journal.all(
            "SELECT result_json, updated_at, state FROM jobs WHERE session_id=? "
            "AND kind IN ('investigate','analyze','conclude','chat') ORDER BY created_at",
            (self.session_id,),
        ):
            result = json_load(row["result_json"], {})
            summaries = result.get("event_summaries", [])
            excerpt = ""
            for summary in reversed(summaries):
                if summary.get("method") == "item/completed":
                    excerpt = _extract_model_text(summary.get("payload_excerpt", ""))
                    break
            messages.append(
                {
                    "role": "assistant",
                    "text": excerpt or result.get("message") or "Codex job recorded no textual result.",
                    "created_at": row["updated_at"],
                    "status": row["state"],
                }
            )
        messages.sort(key=lambda item: str(item.get("created_at", "")))
        return messages

    def _latest_thread_id(self) -> str | None:
        row = self.core.journal.one(
            "SELECT result_json FROM jobs WHERE session_id=? AND state IN ('completed','interrupted') "
            "ORDER BY updated_at DESC LIMIT 1",
            (self.session_id,),
        )
        if row is None:
            return None
        value = json_load(row["result_json"], {}).get("thread_id")
        return str(value) if value else None

    async def close(self) -> None:
        if self.investigator is not None:
            await self.investigator.close()

    async def interrupt_job(self, job_id: str, owner: Owner) -> dict[str, Any]:
        session = self.core.session(self.session_id)
        if owner.login != session.owner:
            raise PermissionError("selected session belongs to a different owner")
        job = self.core.job(job_id)
        if job.session_id != self.session_id:
            raise ValueError("job does not belong to the selected session")
        if job.state not in {"admitted", "running"}:
            raise ValueError(f"job is already {job.state}")
        if self.investigator is None:
            raise ValueError("the live Codex runtime is unavailable in this coordinator")
        result = await self.investigator.interrupt(job_id)
        return {
            "job_id": result.job_id,
            "runtime_id": result.runtime_id,
            "requested": result.requested,
        }

    def _jobs(self) -> list[dict[str, Any]]:
        rows = self.core.journal.all(
            "SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC LIMIT 20",
            (self.session_id,),
        )
        return [
            {
                "title": row["kind"],
                "status": row["state"],
                "usage": json_load(row["result_json"], {}).get("usage", "usage pending"),
            }
            for row in rows
        ]

    def _current_step(self) -> dict[str, Any] | None:
        row = self.core.journal.one(
            "SELECT record_json FROM procedures WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (self.session_id,),
        )
        if row is None:
            return {
                "status": "planned",
                "title": "Record the first bounded procedure",
                "detail": "Use replay mode to qualify the complete coordinator path.",
            }
        record = json_load(row["record_json"], {})
        return {
            "status": "recorded",
            "title": record.get("title", "Latest procedure"),
            "detail": record.get("expected_benefit", "Awaiting execution or interpretation."),
        }


def _positive_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("a positive integer is required") from exc
    if result <= 0:
        raise ValueError("a positive integer is required")
    return result


def _procedure_ref(value: str | None) -> tuple[str, int, str]:
    if not value:
        raise ValueError("an exact procedure reference is required")
    parts = value.rsplit("@", 2)
    if len(parts) != 3:
        raise ValueError("procedure reference is incomplete")
    procedure_id, revision_text, digest = parts
    try:
        revision = int(revision_text)
    except ValueError as exc:
        raise ValueError("procedure revision is invalid") from exc
    if not procedure_id or revision <= 0 or len(digest) != 64:
        raise ValueError("procedure reference is invalid")
    return procedure_id, revision, digest


def _scope_is_current(scope: dict[str, Any], uses: int, target: Any) -> bool:
    if target is None or uses >= int(scope.get("repeat_limit", 1)):
        return False
    try:
        expires_at = datetime.fromisoformat(str(scope["expires_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    if expires_at.tzinfo is None or expires_at < utc_now():
        return False
    return (
        scope.get("target_identity") == target.identity
        and (scope.get("boot_epoch") in {None, target.boot_epoch})
        and (scope.get("configuration_digest") in {None, target.configuration_digest})
    )


def _ui_phase(phase: SessionPhase) -> str:
    return phase.value


def _target_view(target: Any) -> dict[str, Any]:
    if target is None:
        return {"name": "M1 target", "mode": "disconnected", "freshness": "unknown", "recovery": "unqualified"}
    fresh = target.is_fresh(utc_now())
    return {
        "name": target.identity,
        "mode": target.mode.value,
        "boot_epoch": target.boot_epoch,
        "freshness": "fresh" if fresh else "stale",
        "recovery": target.recovery.get("status", "unqualified"),
        "last_contact": target.observed_at.isoformat(),
    }


def _recovery_view(target: Any) -> dict[str, str]:
    if target is None:
        return {"level": "Unknown", "status": "unqualified", "detail": "No target snapshot exists."}
    return {
        "level": target.recovery.get("level", "Replay" if target.mode.value == "replay" else "Unknown"),
        "status": target.recovery.get("status", "unqualified"),
        "detail": target.recovery.get("detail", "Physical target recovery has not been qualified."),
        "owner_instruction": target.recovery.get("owner_instruction", ""),
    }


def _risk_level(record: dict[str, Any]) -> str:
    severity = str(record.get("failure_severity", "unknown")).lower()
    if severity in {"critical", "high", "severe"}:
        return "high"
    if any(op.get("mutates_target") for op in record.get("operations", [])):
        return "medium"
    return "low"


def _event_summary(kind: str) -> str:
    return kind.replace(".", " ").replace("_", " ").capitalize()


def _summarize_data(data: dict[str, Any]) -> str:
    text = json.dumps(data, sort_keys=True, default=str)
    return text if len(text) <= 360 else text[:357] + "…"


def _extract_model_text(payload_excerpt: str) -> str:
    try:
        payload = json.loads(payload_excerpt)
    except (TypeError, json.JSONDecodeError):
        return ""
    candidates: list[str] = []

    def collect(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, str) and key in {"text", "output_text", "summary", "content"}:
            candidates.append(value)

    collect(payload)
    return "\n\n".join(item for item in candidates if item.strip())[:8_000]
