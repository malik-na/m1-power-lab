from __future__ import annotations

from datetime import timedelta
import hashlib
import sqlite3
from typing import Any

from m1lab.paths import AppPaths

from .budgets import BudgetLedger
from .errors import ConflictError, CoreError, NotFoundError, ValidationError
from .journal import Journal, _file_sha256, iso, json_dump, json_load
from .models import (
    ACTIVE_PHASES,
    ApprovalRecord,
    ApprovalScope,
    ArtifactRecord,
    CommandKind,
    CommandResult,
    CommandStatus,
    DispatchEnvelope,
    DispatchRequest,
    EligibilityResult,
    EventRecord,
    JobCreate,
    JobRecord,
    OperationAuthorization,
    OperationOutcome,
    OperationRecord,
    OperationState,
    OwnerCommand,
    ProcedureDraft,
    ProcedureRecord,
    ReconciliationReport,
    ReservationRecord,
    ReservationRequest,
    ReviewDisposition,
    ReviewRecord,
    SessionCreate,
    SessionPhase,
    SessionRecord,
    SessionSnapshot,
    TargetMode,
    TargetSnapshot,
    UsageResult,
    UsageUpdate,
    new_id,
    utc_now,
)


class CoreApp:
    """Deep module for durable state, policy, eligibility and reconciliation."""

    def __init__(self, journal: Journal):
        self.journal = journal
        self.budgets = BudgetLedger(journal)

    @classmethod
    def open(cls, paths: AppPaths) -> "CoreApp":
        return cls(Journal(paths))

    def close(self) -> None:
        self.journal.close()

    def create_session(self, request: SessionCreate) -> SessionRecord:
        session_id = new_id("session")
        now = utc_now()
        record = SessionRecord(
            id=session_id,
            revision=1,
            phase=SessionPhase.PREPARING,
            created_at=now,
            updated_at=now,
            lifetime_tokens=0,
            lifetime_active_seconds=0,
            usage_uncertain=False,
            **request.model_dump(exclude={"active_seconds", "token_limit"}),
        )
        with self.journal.transaction() as tx:
            self._insert_session(tx, record)
            tx.execute(
                "INSERT INTO allowance_epochs(session_id,kind,token_delta,active_seconds_value,created_at,note) VALUES (?,'initial',?,?,?,'default allowance')",
                (session_id, request.token_limit, request.active_seconds, iso(now)),
            )
            self._history(tx, record, "created")
            self.journal.append_event(
                tx,
                kind="session.created",
                session_id=session_id,
                subject_id=session_id,
                data={"revision": 1, "objective": record.objective},
            )
        return self.session(session_id)

    def session(self, session_id: str) -> SessionRecord:
        row = self.journal.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        if row is None:
            raise NotFoundError(f"session {session_id} does not exist")
        return self._session_from_row(row)

    def snapshot(self, session_id: str) -> SessionSnapshot:
        session = self.session(session_id)
        target_row = self.journal.one(
            "SELECT * FROM target_snapshots WHERE session_id=? ORDER BY observed_at DESC LIMIT 1",
            (session_id,),
        )
        cursor = self.journal.one(
            "SELECT COALESCE(MAX(cursor), 0) AS cursor FROM events WHERE session_id=?", (session_id,)
        )
        commands = self.journal.one(
            "SELECT COUNT(*) AS count FROM owner_commands WHERE session_id=? AND status='received'",
            (session_id,),
        )
        operations = self.journal.one(
            "SELECT COUNT(*) AS count FROM operations WHERE session_id=? AND state IN ('intent','dispatched','unknown_effect')",
            (session_id,),
        )
        return SessionSnapshot(
            session=session,
            budget=self.budgets.snapshot(session_id),
            pending_commands=commands["count"] if commands else 0,
            pending_operations=operations["count"] if operations else 0,
            latest_target=self._target_from_row(target_row) if target_row else None,
            last_event_cursor=cursor["cursor"] if cursor else 0,
        )

    def events(self, session_id: str | None = None, *, after: int = 0, limit: int = 200) -> list[EventRecord]:
        return self.journal.events(session_id=session_id, after=after, limit=limit)

    def submit(self, command: OwnerCommand) -> CommandResult:
        with self.journal.transaction() as tx:
            prior = tx.execute("SELECT * FROM owner_commands WHERE id=?", (command.id,)).fetchone()
            if prior:
                if not self._same_command_request(prior, command):
                    raise ConflictError(
                        f"command ID {command.id} is already bound to a different request"
                    )
                return CommandResult(
                    command_id=command.id,
                    status=prior["status"],
                    session_id=prior["session_id"],
                    session_revision=prior["resulting_revision"],
                    outcome=json_load(prior["outcome_json"], {}),
                )
            row = tx.execute("SELECT * FROM sessions WHERE id=?", (command.session_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"session {command.session_id} does not exist")
            session = self._session_from_row(row)
            rejection = None
            if command.owner != session.owner:
                rejection = "owner identity does not match the session owner"
            elif command.expected_revision != session.revision:
                rejection = f"stale session revision: expected {command.expected_revision}, current {session.revision}"
            if rejection:
                return self._store_command(tx, command, CommandStatus.REJECTED, session.revision, {"reason": rejection})

            old_phase = session.phase
            try:
                outcome = self._apply_command(tx, session, command)
            except (CoreError, ValueError, TypeError) as exc:
                return self._store_command(
                    tx,
                    command,
                    CommandStatus.REJECTED,
                    session.revision,
                    {"reason": str(exc)},
                )
            session.revision += 1
            session.updated_at = utc_now()
            self._update_session(tx, session)
            if old_phase != session.phase:
                session = self._record_phase_change_in_tx(
                    tx, session, old_phase, f"owner command {command.kind.value}"
                )
            self._history(tx, session, f"owner_command:{command.kind}")
            result = self._store_command(tx, command, CommandStatus.APPLIED, session.revision, outcome)
            self.journal.append_event(
                tx,
                kind="owner_command.applied",
                session_id=session.id,
                subject_id=command.id,
                data={"kind": command.kind, "revision": session.revision, **outcome},
            )
            return result

    def _apply_command(self, tx: sqlite3.Connection, session: SessionRecord, command: OwnerCommand) -> dict[str, Any]:
        payload = command.payload
        if command.kind == CommandKind.START:
            if session.phase != SessionPhase.PREPARING:
                raise ConflictError("start is allowed only while preparing")
            session.phase = SessionPhase.INVESTIGATING
        elif command.kind == CommandKind.PAUSE:
            if session.phase in {SessionPhase.COMPLETED, SessionPhase.STOPPED}:
                raise ConflictError("a terminal session cannot be paused")
            session.phase = SessionPhase.PAUSED
        elif command.kind == CommandKind.RESUME:
            if session.phase not in {SessionPhase.PAUSED, SessionPhase.BUDGET_EXHAUSTED}:
                raise ConflictError("resume requires a paused or budget-exhausted session")
            if not self.budgets.snapshot(session.id).admission_open:
                raise ConflictError("the session budget does not permit resume")
            session.phase = SessionPhase.INVESTIGATING
        elif command.kind == CommandKind.STOP:
            session.phase = SessionPhase.STOPPED
        elif command.kind == CommandKind.COMPLETE:
            session.phase = SessionPhase.COMPLETED
        elif command.kind == CommandKind.STEER:
            if not str(payload.get("message", "")).strip():
                raise ValidationError("steering requires a message")
        elif command.kind == CommandKind.GRANT_TOKENS:
            amount = int(payload.get("tokens", 0))
            if amount <= 0:
                raise ValidationError("token grant must be positive")
            tx.execute(
                "INSERT INTO allowance_epochs(session_id,kind,token_delta,active_seconds_value,created_at,command_id,note) VALUES (?,'token_grant',?,0,?,?,?)",
                (session.id, amount, iso(), command.id, str(payload.get("note", ""))),
            )
        elif command.kind in {CommandKind.EXTEND_TIME, CommandKind.RESET_TIME}:
            seconds = int(payload.get("seconds", 0))
            if seconds <= 0:
                raise ValidationError("time amount must be positive")
            value = seconds
            kind = "time_extension"
            if command.kind == CommandKind.RESET_TIME:
                value += self.budgets.snapshot(session.id).active_seconds_used
                kind = "time_reset"
            tx.execute(
                "INSERT INTO allowance_epochs(session_id,kind,token_delta,active_seconds_value,created_at,command_id,note) VALUES (?,?,0,?,?,?,?)",
                (session.id, kind, value, iso(), command.id, str(payload.get("note", ""))),
            )
        elif command.kind == CommandKind.APPROVE:
            if session.phase is not SessionPhase.AWAITING_APPROVAL:
                raise ConflictError("approval requires a session awaiting approval")
            self._approve_in_tx(tx, session, command)
            session.phase = SessionPhase.INVESTIGATING
        elif command.kind == CommandKind.REVOKE:
            approval_id = str(payload.get("approval_id", ""))
            changed = tx.execute(
                "UPDATE approvals SET revoked_at=? WHERE id=? AND session_id=? AND revoked_at IS NULL",
                (iso(), approval_id, session.id),
            )
            if not changed.rowcount:
                raise NotFoundError(f"active approval {approval_id} does not exist")
        elif command.kind == CommandKind.DENY:
            if session.phase is not SessionPhase.AWAITING_APPROVAL:
                raise ConflictError("denial requires a session awaiting approval")
            if not all(payload.get(key) is not None for key in (
                "procedure_id", "procedure_revision", "procedure_digest"
            )):
                raise ValidationError("denial requires exact procedure id, revision, and digest")
            procedure = self._procedure_in_tx(
                tx, str(payload["procedure_id"]), int(payload["procedure_revision"])
            )
            if (
                procedure.session_id != session.id
                or payload["procedure_digest"] != procedure.digest
            ):
                raise ValidationError("denial does not match the exact procedure revision")
            self._require_current_pending_approval(tx, session, procedure)
            session.phase = SessionPhase.INVESTIGATING
        return {"phase": session.phase}

    def _approve_in_tx(self, tx: sqlite3.Connection, session: SessionRecord, command: OwnerCommand) -> ApprovalRecord:
        payload = command.payload
        procedure = self._procedure_in_tx(tx, str(payload.get("procedure_id", "")), int(payload.get("procedure_revision", 0)))
        if procedure.session_id != session.id:
            raise ValidationError("procedure belongs to another session")
        self._require_current_pending_approval(tx, session, procedure)
        scope = ApprovalScope.model_validate(payload.get("scope", {}))
        approval = ApprovalRecord(
            id=new_id("approval"),
            session_id=session.id,
            procedure_id=procedure.procedure_id,
            procedure_revision=procedure.revision,
            procedure_digest=procedure.digest,
            owner=session.owner,
            scope=scope,
            created_at=utc_now(),
        )
        tx.execute(
            "INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,NULL,?)",
            (
                approval.id,
                approval.session_id,
                approval.procedure_id,
                approval.procedure_revision,
                approval.procedure_digest,
                approval.owner,
                json_dump(scope.model_dump(mode="json")),
                0,
                iso(approval.created_at),
            ),
        )
        return approval

    def publish_artifact(self, content: bytes, *, media_type: str = "application/octet-stream", provenance: dict[str, Any] | None = None) -> ArtifactRecord:
        provenance = provenance or {}
        session_id = provenance.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("artifact provenance requires a session_id")
        self.session(session_id)
        return self.journal.publish_artifact(content, media_type=media_type, provenance=provenance)

    def artifact(self, artifact_id: str) -> ArtifactRecord:
        return self.journal.artifact(artifact_id)

    def session_artifact(self, session_id: str, artifact_id: str) -> ArtifactRecord:
        self.session(session_id)
        return self.journal.artifact_for_session(session_id, artifact_id)

    def read_artifact(
        self, session_id: str, artifact_id: str, *, max_bytes: int = 4_000_000
    ) -> bytes:
        """Read verified content only through a publication in the given session."""
        return self.read_session_artifact(
            session_id, artifact_id, max_bytes=max_bytes
        )

    def read_session_artifact(
        self, session_id: str, artifact_id: str, *, max_bytes: int = 4_000_000
    ) -> bytes:
        if not 1 <= max_bytes <= 64_000_000:
            raise ValidationError("artifact read bound must be 1..64,000,000 bytes")
        self.session(session_id)
        return self.journal.read_artifact_for_session(
            session_id, artifact_id, max_bytes=max_bytes
        )

    def artifacts(self, session_id: str, *, record_type: str | None = None) -> list[ArtifactRecord]:
        records = self.list_records(session_id, "artifacts")
        if record_type is None:
            return records
        return [item for item in records if item.provenance.get("record_type") == record_type]

    def record_target(self, snapshot: TargetSnapshot) -> TargetSnapshot:
        self.session(snapshot.session_id)
        with self.journal.transaction() as tx:
            tx.execute(
                "INSERT INTO target_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot.id, snapshot.session_id, snapshot.identity, snapshot.boot_epoch, snapshot.mode,
                    snapshot.configuration_digest, json_dump(sorted(snapshot.capabilities)),
                    json_dump(snapshot.recovery), iso(snapshot.observed_at), iso(snapshot.fresh_until) if snapshot.fresh_until else None,
                ),
            )
            self.journal.append_event(tx, kind="target.observed", session_id=snapshot.session_id, subject_id=snapshot.id, data=snapshot.model_dump(mode="json"))
        return snapshot

    def register_procedure(self, draft: ProcedureDraft) -> ProcedureRecord:
        canonical = draft.model_dump(mode="json")
        digest = hashlib.sha256(json_dump(canonical).encode()).hexdigest()
        with self.journal.transaction() as tx:
            session_row = tx.execute(
                "SELECT phase FROM sessions WHERE id=?", (draft.session_id,)
            ).fetchone()
            if session_row is None:
                raise NotFoundError(f"session {draft.session_id} does not exist")
            if SessionPhase(session_row["phase"]) not in {
                SessionPhase.INVESTIGATING,
                SessionPhase.INTERPRETING,
            }:
                raise ConflictError("procedure registration requires investigation or interpretation")
            prior = tx.execute("SELECT MAX(revision) AS revision FROM procedures WHERE procedure_id=?", (draft.procedure_id,)).fetchone()
            revision = (prior["revision"] or 0) + 1
            record = ProcedureRecord(**draft.model_dump(), revision=revision, digest=digest, created_at=utc_now())
            tx.execute("INSERT INTO procedures VALUES (?,?,?,?,?,?)", (record.procedure_id, revision, record.session_id, digest, record.model_dump_json(), iso(record.created_at)))
            self.journal.append_event(tx, kind="procedure.registered", session_id=record.session_id, subject_id=record.procedure_id, data={"revision": revision, "digest": digest})
            self._transition_phase_in_tx(
                tx,
                record.session_id,
                SessionPhase.AWAITING_REVIEW,
                "procedure awaiting independent review",
            )
        return record

    def record_review(self, review: ReviewRecord) -> ReviewRecord:
        with self.journal.transaction() as tx:
            session_row = tx.execute(
                "SELECT phase FROM sessions WHERE id=?", (review.session_id,)
            ).fetchone()
            if session_row is None:
                raise NotFoundError(f"session {review.session_id} does not exist")
            if SessionPhase(session_row["phase"]) is not SessionPhase.AWAITING_REVIEW:
                raise ConflictError("review recording requires a session awaiting review")
            procedure = self._procedure_in_tx(tx, review.procedure_id, review.procedure_revision)
            if procedure.session_id != review.session_id or procedure.digest != review.procedure_digest:
                raise ValidationError("review does not match the exact procedure revision")
            reviewer = tx.execute(
                "SELECT session_id, kind, state FROM jobs WHERE id=?",
                (review.reviewer_job_id,),
            ).fetchone()
            if reviewer is None:
                raise ValidationError("reviewer job does not exist")
            if (
                reviewer["session_id"] != review.session_id
                or reviewer["kind"] != "review"
                or reviewer["state"] != "completed"
            ):
                raise ValidationError("reviewer job must be a completed review job in this session")
            tx.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?)", (review.id, review.session_id, review.procedure_id, review.procedure_revision, review.procedure_digest, review.disposition, review.model_dump_json(), iso(review.created_at)))
            self.journal.append_event(tx, kind="procedure.reviewed", session_id=review.session_id, subject_id=review.id, data={"procedure_id": review.procedure_id, "revision": review.procedure_revision, "disposition": review.disposition})
            next_phase = (
                SessionPhase.AWAITING_APPROVAL
                if review.disposition is ReviewDisposition.ACCEPTED
                and any(operation.mutates_target for operation in procedure.operations)
                else SessionPhase.INVESTIGATING
            )
            self._transition_phase_in_tx(
                tx,
                review.session_id,
                next_phase,
                f"procedure review {review.disposition.value}",
            )
        return review

    def authorize_operation(self, request: DispatchRequest) -> OperationAuthorization:
        with self.journal.transaction() as tx:
            reasons: list[str] = []
            session_row = tx.execute("SELECT * FROM sessions WHERE id=?", (request.session_id,)).fetchone()
            if session_row is None:
                raise NotFoundError(f"session {request.session_id} does not exist")
            session = self._session_from_row(session_row)
            procedure = self._procedure_in_tx(tx, request.procedure_id, request.procedure_revision)
            target_row = tx.execute("SELECT * FROM target_snapshots WHERE id=?", (request.target_snapshot_id,)).fetchone()
            if target_row is None:
                raise NotFoundError(f"target snapshot {request.target_snapshot_id} does not exist")
            target = self._target_from_row(target_row)
            if session.phase not in ACTIVE_PHASES:
                reasons.append(f"session phase {session.phase} does not admit work")
            if procedure.session_id != session.id or target.session_id != session.id:
                reasons.append("procedure or target belongs to another session")
            if request.adapter_mode not in {TargetMode.REPLAY, TargetMode.SYNTHETIC}:
                reasons.append("real hardware dispatch is disabled in this build")
            if request.adapter_mode != target.mode:
                reasons.append("adapter mode does not match the target snapshot")
            if not target.is_fresh(utc_now()):
                reasons.append("target snapshot is stale")
            missing = procedure.prerequisites - target.capabilities
            if missing:
                reasons.append("missing target capabilities: " + ", ".join(sorted(missing)))
            reasons.extend(
                self._procedure_artifact_blockers(tx, procedure, session.id)
            )
            estimated_artifact_bytes = sum(
                max(0, int(operation.parameters.get("length", 0)))
                for operation in procedure.operations
                if operation.kind == "capture_memory"
            ) + len(procedure.operations) * 64 * 1024
            try:
                self.journal.ensure_artifact_capacity(estimated_artifact_bytes)
            except ValidationError as exc:
                reasons.append(str(exc))
            budget = self.budgets.snapshot(session.id)
            if not budget.admission_open:
                reasons.extend(budget.blockers)
            if request.estimated_tokens > budget.tokens_remaining or request.estimated_active_seconds > budget.active_seconds_remaining:
                reasons.append("estimated work exceeds remaining allowance")
            ambiguous = tx.execute(
                "SELECT id, state FROM operations WHERE session_id=? "
                "AND state IN ('intent','dispatched','unknown_effect') LIMIT 1",
                (session.id,),
            ).fetchone()
            if ambiguous is not None:
                reasons.append(
                    f"operation {ambiguous['id']} is unresolved ({ambiguous['state']})"
                )
            review_row = tx.execute("SELECT * FROM reviews WHERE procedure_id=? AND procedure_revision=? AND procedure_digest=? ORDER BY created_at DESC LIMIT 1", (procedure.procedure_id, procedure.revision, procedure.digest)).fetchone()
            review_id = None
            if review_row is None or review_row["disposition"] != ReviewDisposition.ACCEPTED:
                reasons.append("exact procedure revision lacks an accepted review")
            else:
                review_id = review_row["id"]
            mutates = any(op.mutates_target for op in procedure.operations)
            approval_id = None
            if mutates:
                approval = self._matching_approval(tx, procedure, target)
                if approval is None:
                    reasons.append("state-changing procedure lacks a current exact approval")
                else:
                    approval_id = approval["id"]
            eligibility = EligibilityResult(eligible=not reasons, reasons=reasons, approval_id=approval_id, review_id=review_id)
            if reasons:
                return OperationAuthorization(eligibility=eligibility)
            operation_id = new_id("operation")
            deadline = utc_now() + timedelta(seconds=sum(op.timeout_seconds for op in procedure.operations))
            envelope = DispatchEnvelope(
                operation_id=operation_id, session_id=session.id, procedure_id=procedure.procedure_id,
                procedure_revision=procedure.revision, procedure_digest=procedure.digest,
                target_identity=target.identity, target_snapshot_id=target.id, boot_epoch=target.boot_epoch,
                configuration_digest=target.configuration_digest, adapter_mode=request.adapter_mode,
                operations=procedure.operations, deadline_at=deadline,
            )
            tx.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)", (operation_id, session.id, procedure.procedure_id, procedure.revision, procedure.digest, approval_id, review_id, target.id, target.boot_epoch, request.adapter_mode, int(mutates), OperationState.INTENT, envelope.model_dump_json(), "{}", iso()))
            self.journal.append_event(tx, kind="operation.intent_recorded", session_id=session.id, subject_id=operation_id, data={"procedure_id": procedure.procedure_id, "procedure_revision": procedure.revision, "boot_epoch": target.boot_epoch})
            return OperationAuthorization(eligibility=eligibility, envelope=envelope)

    def mark_dispatched(self, envelope: DispatchEnvelope) -> None:
        operation_id = envelope.operation_id
        with self.journal.transaction() as tx:
            row = tx.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"operation {operation_id} does not exist")
            if row["state"] != OperationState.INTENT:
                raise ConflictError(f"operation is {row['state']}, not an undispatched intent")
            stored_envelope = DispatchEnvelope.model_validate_json(row["envelope_json"])
            if stored_envelope != envelope:
                raise ConflictError("dispatch envelope differs from the authorized durable intent")
            session = tx.execute("SELECT phase FROM sessions WHERE id=?", (row["session_id"],)).fetchone()
            if session is None or SessionPhase(session["phase"]) not in ACTIVE_PHASES:
                raise ConflictError("session no longer admits dispatch")
            if envelope.deadline_at <= utc_now():
                raise ConflictError("authorized dispatch envelope has expired")
            budget = self.budgets.snapshot(row["session_id"])
            if not budget.admission_open:
                raise ConflictError(
                    "budget no longer admits dispatch: " + "; ".join(budget.blockers)
                )
            procedure = self._procedure_in_tx(
                tx, row["procedure_id"], row["procedure_revision"]
            )
            estimated_artifact_bytes = sum(
                max(0, int(operation.parameters.get("length", 0)))
                for operation in procedure.operations
                if operation.kind == "capture_memory"
            ) + len(procedure.operations) * 64 * 1024
            self.journal.ensure_artifact_capacity(estimated_artifact_bytes)
            artifact_blockers = self._procedure_artifact_blockers(
                tx, procedure, row["session_id"]
            )
            if artifact_blockers:
                raise ConflictError("; ".join(artifact_blockers))
            target_row = tx.execute(
                "SELECT * FROM target_snapshots WHERE id=?", (row["target_snapshot_id"],)
            ).fetchone()
            latest_target_row = tx.execute(
                "SELECT * FROM target_snapshots WHERE session_id=? ORDER BY observed_at DESC LIMIT 1",
                (row["session_id"],),
            ).fetchone()
            if target_row is None or latest_target_row is None:
                raise ConflictError("target state is unavailable at dispatch")
            target = self._target_from_row(target_row)
            latest_target = self._target_from_row(latest_target_row)
            if not target.is_fresh(utc_now()):
                raise ConflictError("authorized target snapshot is stale at dispatch")
            if (
                latest_target.identity != target.identity
                or latest_target.boot_epoch != target.boot_epoch
                or latest_target.configuration_digest != target.configuration_digest
                or latest_target.mode != target.mode
            ):
                raise ConflictError("target identity, boot epoch, configuration, or mode changed before dispatch")
            if row["mutates_target"] and not row["approval_id"]:
                raise ConflictError("state-changing operation has no exact approval at dispatch")
            tx.execute("UPDATE operations SET state=?, dispatched_at=? WHERE id=?", (OperationState.DISPATCHED, iso(), operation_id))
            if row["approval_id"]:
                approval = tx.execute(
                    "SELECT * FROM approvals WHERE id=?", (row["approval_id"],)
                ).fetchone()
                if approval is None:
                    raise ConflictError("approval disappeared before dispatch")
                scope = ApprovalScope.model_validate(json_load(approval["scope_json"]))
                if (
                    approval["revoked_at"] is not None
                    or approval["procedure_id"] != row["procedure_id"]
                    or approval["procedure_revision"] != row["procedure_revision"]
                    or approval["procedure_digest"] != row["procedure_digest"]
                    or scope.expires_at < utc_now()
                    or approval["uses"] >= scope.repeat_limit
                    or scope.target_identity != target.identity
                    or (scope.boot_epoch is not None and scope.boot_epoch != target.boot_epoch)
                    or (
                        scope.configuration_digest is not None
                        and scope.configuration_digest != target.configuration_digest
                    )
                    or (
                        procedure.physical_attendance == "required"
                        and not scope.physical_attendance_confirmed
                    )
                ):
                    raise ConflictError("approval scope is no longer valid at dispatch")
                consumed = tx.execute(
                    "UPDATE approvals SET uses=uses+1 WHERE id=? AND revoked_at IS NULL AND uses=?",
                    (approval["id"], approval["uses"]),
                )
                if consumed.rowcount != 1:
                    raise ConflictError("approval was concurrently changed before dispatch")
            self.journal.append_event(tx, kind="operation.dispatched", session_id=row["session_id"], subject_id=operation_id, data={"boot_epoch": row["boot_epoch"]})
            self._transition_phase_in_tx(
                tx, row["session_id"], SessionPhase.EXECUTING, "target operation dispatched"
            )

    def finish_operation(self, operation_id: str, outcome: OperationOutcome) -> None:
        with self.journal.transaction() as tx:
            row = tx.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"operation {operation_id} does not exist")
            if row["state"] not in {OperationState.INTENT, OperationState.DISPATCHED, OperationState.UNKNOWN_EFFECT}:
                raise ConflictError(f"operation already has terminal state {row['state']}")
            if row["state"] == OperationState.UNKNOWN_EFFECT:
                raise ConflictError(
                    "an unknown-effect operation requires evidence-backed reconciliation"
                )
            if row["state"] == OperationState.INTENT and outcome.state != OperationState.NO_EFFECT:
                raise ValidationError("an undispatched intent can only finish as no_effect")
            for artifact_id in outcome.artifact_ids:
                try:
                    self.journal.artifact_path_for_session(row["session_id"], artifact_id)
                except (NotFoundError, ValidationError) as exc:
                    raise ValidationError(
                        f"operation artifact {artifact_id} is unavailable in this session"
                    ) from exc
            tx.execute("UPDATE operations SET state=?, result_json=?, completed_at=? WHERE id=?", (outcome.state, outcome.model_dump_json(), iso(), operation_id))
            self.journal.append_event(tx, kind="operation.finished", session_id=row["session_id"], subject_id=operation_id, data=outcome.model_dump(mode="json"))
            self._transition_phase_in_tx(
                tx,
                row["session_id"],
                SessionPhase.RECOVERING
                if outcome.state is OperationState.UNKNOWN_EFFECT
                else SessionPhase.INTERPRETING,
                f"operation finished as {outcome.state.value}",
            )

    def reconcile_operation(
        self,
        operation_id: str,
        *,
        resolved_state: OperationState,
        evidence_artifact_ids: list[str],
        note: str,
    ) -> None:
        if resolved_state not in {
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.NO_EFFECT,
        }:
            raise ValidationError("reconciliation must resolve to succeeded, failed, or no_effect")
        if not evidence_artifact_ids or not note.strip():
            raise ValidationError("reconciliation requires evidence artifacts and a note")
        with self.journal.transaction() as tx:
            row = tx.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"operation {operation_id} does not exist")
            if row["state"] != OperationState.UNKNOWN_EFFECT:
                raise ConflictError("only an unknown-effect operation can be reconciled")
            for artifact_id in evidence_artifact_ids:
                try:
                    self.journal.artifact_path_for_session(row["session_id"], artifact_id)
                except (NotFoundError, ValidationError) as exc:
                    raise ValidationError(
                        f"reconciliation artifact {artifact_id} is unavailable in this session"
                    ) from exc
            result = {
                "resolved_state": resolved_state.value,
                "evidence_artifact_ids": evidence_artifact_ids,
                "note": note.strip(),
            }
            tx.execute(
                "UPDATE operations SET state=?, reconciliation_json=?, completed_at=? WHERE id=?",
                (OperationState.RECONCILED, json_dump(result), iso(), operation_id),
            )
            self.journal.append_event(
                tx,
                kind="operation.reconciled",
                session_id=row["session_id"],
                subject_id=operation_id,
                data=result,
            )
            self._transition_phase_in_tx(
                tx,
                row["session_id"],
                SessionPhase.INTERPRETING,
                f"unknown operation reconciled as {resolved_state.value}",
            )
    def reconcile(self) -> ReconciliationReport:
        report = ReconciliationReport(active_clock_uncertain_sessions=self.budgets.reconcile_clock())
        with self.journal.transaction() as tx:
            for row in tx.execute("SELECT * FROM operations WHERE state IN ('intent','dispatched')").fetchall():
                if row["state"] == OperationState.INTENT:
                    tx.execute("UPDATE operations SET state=?, completed_at=? WHERE id=?", (OperationState.NO_EFFECT, iso(), row["id"]))
                    report.no_effect_operation_ids.append(row["id"])
                    next_phase = SessionPhase.INTERPRETING
                    reason = "undispatched operation reconciled as no effect"
                else:
                    tx.execute("UPDATE operations SET state=?, reconciliation_json=? WHERE id=?", (OperationState.UNKNOWN_EFFECT, json_dump({"reason": "coordinator restarted without a conclusive outcome"}), row["id"]))
                    report.unknown_operation_ids.append(row["id"])
                    next_phase = SessionPhase.RECOVERING
                    reason = "dispatched operation has unknown effect after restart"
                phase_row = tx.execute(
                    "SELECT phase FROM sessions WHERE id=?", (row["session_id"],)
                ).fetchone()
                if phase_row is not None and SessionPhase(phase_row["phase"]) not in {
                    SessionPhase.PAUSED,
                    SessionPhase.COMPLETED,
                    SessionPhase.STOPPED,
                }:
                    self._transition_phase_in_tx(
                        tx, row["session_id"], next_phase, reason
                    )
            job_sessions: set[str] = set()
            for row in tx.execute("SELECT * FROM jobs WHERE state IN ('admitted','running')").fetchall():
                tx.execute("UPDATE jobs SET state='unknown', updated_at=? WHERE id=?", (iso(), row["id"]))
                tx.execute("UPDATE sessions SET usage_uncertain=1, updated_at=? WHERE id=?", (iso(), row["session_id"]))
                self.journal.append_event(tx, kind="job.usage_uncertain", session_id=row["session_id"], subject_id=row["id"], data={"reason": "coordinator restarted before terminal usage reconciliation"})
                job_sessions.add(row["session_id"])
            for session_id in job_sessions:
                phase_row = tx.execute(
                    "SELECT phase FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                if phase_row is not None:
                    self.budgets._sync_activity(
                        tx, session_id, SessionPhase(phase_row["phase"])
                    )
            for row in tx.execute("SELECT * FROM artifacts").fetchall():
                path = self.journal.paths.artifacts / row["relative_path"]
                try:
                    valid = (
                        path.is_file()
                        and path.stat().st_size == row["size_bytes"]
                        and _file_sha256(path) == row["sha256"]
                    )
                except OSError:
                    valid = False
                if not valid:
                    if row["available"]:
                        tx.execute("UPDATE artifacts SET available=0 WHERE id=?", (row["id"],))
                        self._append_artifact_availability_events(
                            tx, row["id"], available=False
                        )
                    report.missing_artifact_ids.append(row["id"])
                elif not row["available"]:
                    tx.execute("UPDATE artifacts SET available=1 WHERE id=?", (row["id"],))
                    self._append_artifact_availability_events(
                        tx, row["id"], available=True
                    )
        known = {row["relative_path"] for row in self.journal.all("SELECT relative_path FROM artifacts")}
        report.orphan_artifact_paths = sorted(str(path.relative_to(self.journal.paths.artifacts)) for path in self.journal.paths.artifacts.rglob("*") if path.is_file() and str(path.relative_to(self.journal.paths.artifacts)) not in known)
        return report

    def report_usage(self, update: UsageUpdate) -> UsageResult:
        return self.budgets.report_usage(update)

    def reserve_budget(self, request: ReservationRequest) -> ReservationRecord:
        return self.budgets.reserve(request)

    def release_budget(self, reservation_id: str) -> None:
        self.budgets.release_reservation(reservation_id)

    def mark_usage_uncertain(self, session_id: str, source_id: str, reason: str) -> None:
        self.budgets.mark_usage_uncertain(session_id, source_id, reason)

    def resolve_usage_uncertainty(self, session_id: str, *, upper_bound_tokens: int, evidence: str, owner_decision: bool = False) -> None:
        self.budgets.resolve_usage_uncertainty(session_id, upper_bound_tokens=upper_bound_tokens, evidence=evidence, owner_decision=owner_decision)

    def create_job(self, request: JobCreate) -> JobRecord:
        now = utc_now()
        if request.lease_expires_at <= now or request.deadline_at <= now:
            raise ValidationError("job lease and deadline must be in the future")
        record = JobRecord(id=new_id("job"), state="admitted", created_at=now, updated_at=now, **request.model_dump())
        with self.journal.transaction() as tx:
            session_row = tx.execute(
                "SELECT * FROM sessions WHERE id=?", (request.session_id,)
            ).fetchone()
            if session_row is None:
                raise NotFoundError(f"session {request.session_id} does not exist")
            session = self._session_from_row(session_row)
            wait_kinds = {
                SessionPhase.AWAITING_REVIEW: {"review", "chat"},
                SessionPhase.AWAITING_APPROVAL: {"chat"},
            }
            phase_admits = session.phase in ACTIVE_PHASES or request.kind in wait_kinds.get(
                session.phase, set()
            )
            if not phase_admits or not self.budgets.snapshot(session.id).admission_open:
                raise ConflictError("session state or budget does not admit a new job")
            self.journal.ensure_artifact_capacity()
            tx.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (record.id, record.session_id, record.kind, None, record.state, iso(record.lease_expires_at), iso(record.deadline_at), json_dump(record.evidence_manifest), "{}", iso(now), iso(now)))
            self.budgets._sync_activity(tx, session.id, session.phase)
            self.journal.append_event(tx, kind="job.admitted", session_id=record.session_id, subject_id=record.id, data={"kind": record.kind, "deadline_at": iso(record.deadline_at)})
        return record

    def update_job(self, job_id: str, *, state: str, runtime_id: str | None = None, result: dict[str, Any] | None = None) -> JobRecord:
        if state not in {"running", "interrupted", "completed", "failed", "unknown"}:
            raise ValidationError(f"invalid job state {state}")
        with self.journal.transaction() as tx:
            row = tx.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"job {job_id} does not exist")
            transitions = {
                "admitted": {"admitted", "running", "interrupted", "failed", "unknown"},
                "running": {"running", "interrupted", "completed", "failed", "unknown"},
                "interrupted": {"interrupted"},
                "completed": {"completed"},
                "failed": {"failed"},
                "unknown": {"unknown"},
            }
            if state not in transitions.get(row["state"], set()):
                raise ConflictError(f"job transition {row['state']} -> {state} is invalid")
            tx.execute("UPDATE jobs SET state=?, runtime_id=COALESCE(?,runtime_id), result_json=?, updated_at=? WHERE id=?", (state, runtime_id, json_dump(result or {}), iso(), job_id))
            session_row = tx.execute(
                "SELECT phase FROM sessions WHERE id=?", (row["session_id"],)
            ).fetchone()
            if session_row is None:
                raise NotFoundError(f"session {row['session_id']} does not exist")
            self.budgets._sync_activity(
                tx, row["session_id"], SessionPhase(session_row["phase"])
            )
            self.journal.append_event(tx, kind=f"job.{state}", session_id=row["session_id"], subject_id=job_id, data=result or {})
            updated = tx.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job_from_row(updated)

    def job(self, job_id: str) -> JobRecord:
        row = self.journal.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row is None:
            raise NotFoundError(f"job {job_id} does not exist")
        return self._job_from_row(row)

    def list_sessions(self, *, limit: int = 100) -> list[SessionRecord]:
        return [self._session_from_row(row) for row in self.journal.all("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (min(max(limit, 1), 1000),))]

    def list_records(self, session_id: str, kind: str) -> list[Any]:
        """Read current typed records for operator interfaces."""
        mappings = {
            "procedures": ("SELECT record_json FROM procedures WHERE session_id=? ORDER BY created_at DESC", ProcedureRecord, "record_json"),
            "reviews": ("SELECT record_json FROM reviews WHERE session_id=? ORDER BY created_at DESC", ReviewRecord, "record_json"),
            "approvals": ("SELECT * FROM approvals WHERE session_id=? ORDER BY created_at DESC", None, None),
            "operations": ("SELECT * FROM operations WHERE session_id=? ORDER BY created_at DESC", None, None),
            "jobs": ("SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC", None, None),
            "artifacts": (
                "SELECT a.*, l.id AS publication_id, l.provenance_json AS link_provenance_json, "
                "l.created_at AS link_created_at FROM artifacts a JOIN artifact_links l ON l.artifact_id=a.id "
                "WHERE l.session_id=? ORDER BY l.created_at DESC",
                None,
                None,
            ),
        }
        if kind not in mappings:
            raise ValidationError(f"unsupported record kind {kind}")
        sql, model, column = mappings[kind]
        rows = self.journal.all(sql, (session_id,))
        if model:
            return [model.model_validate_json(row[column]) for row in rows]
        if kind == "jobs":
            return [self._job_from_row(row) for row in rows]
        if kind == "approvals":
            return [ApprovalRecord(id=row["id"], session_id=row["session_id"], procedure_id=row["procedure_id"], procedure_revision=row["procedure_revision"], procedure_digest=row["procedure_digest"], owner=row["owner"], scope=ApprovalScope.model_validate(json_load(row["scope_json"])), uses=row["uses"], revoked_at=row["revoked_at"], created_at=row["created_at"]) for row in rows]
        if kind == "operations":
            return [self._operation_from_row(row) for row in rows]
        return [self.journal._artifact_from_row(row) for row in rows]

    def _matching_approval(self, tx, procedure: ProcedureRecord, target: TargetSnapshot):
        rows = tx.execute("SELECT * FROM approvals WHERE procedure_id=? AND procedure_revision=? AND procedure_digest=? AND revoked_at IS NULL ORDER BY created_at DESC", (procedure.procedure_id, procedure.revision, procedure.digest)).fetchall()
        now = utc_now()
        for row in rows:
            scope = ApprovalScope.model_validate(json_load(row["scope_json"]))
            if scope.expires_at < now or row["uses"] >= scope.repeat_limit or scope.target_identity != target.identity:
                continue
            if scope.boot_epoch and scope.boot_epoch != target.boot_epoch:
                continue
            if scope.configuration_digest and scope.configuration_digest != target.configuration_digest:
                continue
            if procedure.physical_attendance == "required" and not scope.physical_attendance_confirmed:
                continue
            return row
        return None

    def _procedure_artifact_blockers(
        self, tx: sqlite3.Connection, procedure: ProcedureRecord, session_id: str
    ) -> list[str]:
        blockers: list[str] = []
        for digest in sorted(procedure.artifact_digests):
            artifact = tx.execute(
                "SELECT DISTINCT a.* FROM artifacts a "
                "JOIN artifact_links l ON l.artifact_id=a.id "
                "WHERE a.sha256=? AND l.session_id=?",
                (digest, session_id),
            ).fetchone()
            if artifact is None:
                blockers.append(
                    f"procedure artifact {digest} is not published in this session"
                )
                continue
            try:
                self.journal.artifact_path_for_session(session_id, artifact["id"])
            except (NotFoundError, ValidationError):
                blockers.append(f"procedure artifact {digest} is unavailable or corrupt")
        return blockers

    def _append_artifact_availability_events(
        self, tx: sqlite3.Connection, artifact_id: str, *, available: bool
    ) -> None:
        linked_sessions = [
            row["session_id"]
            for row in tx.execute(
                "SELECT DISTINCT session_id FROM artifact_links "
                "WHERE artifact_id=? AND session_id IS NOT NULL",
                (artifact_id,),
            ).fetchall()
        ]
        for session_id in linked_sessions or [None]:
            self.journal.append_event(
                tx,
                kind="artifact.available" if available else "artifact.unavailable",
                session_id=session_id,
                subject_id=artifact_id,
                data={
                    "reason": (
                        "file restored and digest verified"
                        if available
                        else "file missing, truncated, or digest mismatch"
                    )
                },
            )

    def _transition_phase_in_tx(
        self,
        tx: sqlite3.Connection,
        session_id: str,
        phase: SessionPhase,
        reason: str,
    ) -> SessionRecord:
        """Atomically advance a worker-driven lifecycle transition."""
        row = tx.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"session {session_id} does not exist")
        session = self._session_from_row(row)
        previous = session.phase
        if previous is phase:
            self.budgets._sync_activity(tx, session.id, session.phase)
            return session
        if previous in {SessionPhase.COMPLETED, SessionPhase.STOPPED}:
            raise ConflictError(f"terminal session cannot transition from {previous.value}")
        session.phase = phase
        session.revision += 1
        session.updated_at = utc_now()
        self._update_session(tx, session)
        refreshed = self._record_phase_change_in_tx(
            tx, session, previous, reason
        )
        self._history(tx, refreshed, reason)
        return refreshed

    def _record_phase_change_in_tx(
        self,
        tx: sqlite3.Connection,
        session: SessionRecord,
        previous: SessionPhase,
        reason: str,
    ) -> SessionRecord:
        self.budgets._sync_activity(tx, session.id, session.phase)
        refreshed = self._session_from_row(
            tx.execute("SELECT * FROM sessions WHERE id=?", (session.id,)).fetchone()
        )
        self.journal.append_event(
            tx,
            kind="session.phase_changed",
            session_id=session.id,
            subject_id=session.id,
            data={
                "from_phase": previous.value,
                "phase": refreshed.phase.value,
                "revision": refreshed.revision,
                "reason": reason,
            },
        )
        return refreshed

    def _require_current_pending_approval(
        self,
        tx: sqlite3.Connection,
        session: SessionRecord,
        procedure: ProcedureRecord,
    ) -> None:
        latest = tx.execute(
            "SELECT procedure_id, procedure_revision, procedure_digest, disposition "
            "FROM reviews WHERE session_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (session.id,),
        ).fetchone()
        if (
            latest is None
            or latest["procedure_id"] != procedure.procedure_id
            or latest["procedure_revision"] != procedure.revision
            or latest["procedure_digest"] != procedure.digest
            or latest["disposition"] != ReviewDisposition.ACCEPTED
            or not any(operation.mutates_target for operation in procedure.operations)
        ):
            raise ValidationError("procedure is not the current accepted mutating review")

    def _procedure_in_tx(self, tx, procedure_id: str, revision: int) -> ProcedureRecord:
        row = tx.execute("SELECT record_json FROM procedures WHERE procedure_id=? AND revision=?", (procedure_id, revision)).fetchone()
        if row is None:
            raise NotFoundError(f"procedure {procedure_id} revision {revision} does not exist")
        return ProcedureRecord.model_validate_json(row["record_json"])

    def _store_command(self, tx, command, status, revision, outcome):
        tx.execute("INSERT INTO owner_commands VALUES (?,?,?,?,?,?,?,?,?,?)", (command.id, command.session_id, command.owner, command.kind, command.expected_revision, json_dump(command.payload), iso(command.submitted_at), status, json_dump(outcome), revision))
        return CommandResult(command_id=command.id, status=status, session_id=command.session_id, session_revision=revision, outcome=outcome)

    def _same_command_request(self, row: sqlite3.Row, command: OwnerCommand) -> bool:
        return (
            row["session_id"] == command.session_id
            and row["owner"] == command.owner
            and row["kind"] == command.kind
            and row["expected_revision"] == command.expected_revision
            and row["payload_json"] == json_dump(command.payload)
        )

    def _insert_session(self, tx, record: SessionRecord) -> None:
        tx.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (record.id, record.revision, record.objective, record.owner, record.host_identity, record.target_identity, json_dump(record.policy), record.phase, iso(record.created_at), iso(record.updated_at), record.lifetime_tokens, record.lifetime_active_seconds, int(record.usage_uncertain)))

    def _update_session(self, tx, record: SessionRecord) -> None:
        tx.execute("UPDATE sessions SET revision=?, phase=?, updated_at=?, lifetime_tokens=?, lifetime_active_seconds=?, usage_uncertain=? WHERE id=?", (record.revision, record.phase, iso(record.updated_at), record.lifetime_tokens, record.lifetime_active_seconds, int(record.usage_uncertain), record.id))

    def _history(self, tx, record, reason):
        tx.execute("INSERT INTO session_history(session_id,revision,record_json,reason,occurred_at) VALUES (?,?,?,?,?)", (record.id, record.revision, record.model_dump_json(), reason, iso()))

    def _session_from_row(self, row) -> SessionRecord:
        return SessionRecord(id=row["id"], revision=row["revision"], objective=row["objective"], owner=row["owner"], host_identity=row["host_identity"], target_identity=row["target_identity"], policy=json_load(row["policy_json"], {}), phase=row["phase"], created_at=row["created_at"], updated_at=row["updated_at"], lifetime_tokens=row["lifetime_tokens"], lifetime_active_seconds=row["lifetime_active_seconds"], usage_uncertain=bool(row["usage_uncertain"]))

    def _target_from_row(self, row) -> TargetSnapshot:
        return TargetSnapshot(id=row["id"], session_id=row["session_id"], identity=row["identity"], boot_epoch=row["boot_epoch"], mode=row["mode"], configuration_digest=row["configuration_digest"], capabilities=set(json_load(row["capabilities_json"], [])), recovery=json_load(row["recovery_json"], {}), observed_at=row["observed_at"], fresh_until=row["fresh_until"])

    def _job_from_row(self, row) -> JobRecord:
        return JobRecord(id=row["id"], session_id=row["session_id"], kind=row["kind"], runtime_id=row["runtime_id"], state=row["state"], evidence_manifest=json_load(row["evidence_manifest_json"], {}), result=json_load(row["result_json"], {}), lease_expires_at=row["lease_expires_at"], deadline_at=row["deadline_at"], created_at=row["created_at"], updated_at=row["updated_at"])

    def _operation_from_row(self, row) -> OperationRecord:
        return OperationRecord(id=row["id"], session_id=row["session_id"], procedure_id=row["procedure_id"], procedure_revision=row["procedure_revision"], procedure_digest=row["procedure_digest"], approval_id=row["approval_id"], review_id=row["review_id"], target_snapshot_id=row["target_snapshot_id"], boot_epoch=row["boot_epoch"], adapter_mode=row["adapter_mode"], mutates_target=bool(row["mutates_target"]), state=row["state"], envelope=DispatchEnvelope.model_validate_json(row["envelope_json"]), result=json_load(row["result_json"], {}), created_at=row["created_at"], dispatched_at=row["dispatched_at"], completed_at=row["completed_at"], reconciliation=json_load(row["reconciliation_json"]) if row["reconciliation_json"] else None)
