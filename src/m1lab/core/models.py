from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SessionPhase(StrEnum):
    PREPARING = "preparing"
    INVESTIGATING = "investigating"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    INTERPRETING = "interpreting"
    PAUSED = "paused"
    RECOVERING = "recovering"
    BUDGET_EXHAUSTED = "budget_exhausted"
    COMPLETED = "completed"
    STOPPED = "stopped"


ACTIVE_PHASES = frozenset(
    {
        SessionPhase.INVESTIGATING,
        SessionPhase.EXECUTING,
        SessionPhase.INTERPRETING,
        SessionPhase.RECOVERING,
    }
)


class CommandKind(StrEnum):
    START = "start"
    STEER = "steer"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    COMPLETE = "complete"
    GRANT_TOKENS = "grant_tokens"
    EXTEND_TIME = "extend_time"
    RESET_TIME = "reset_time"
    APPROVE = "approve"
    DENY = "deny"
    REVOKE = "revoke"


class CommandStatus(StrEnum):
    RECEIVED = "received"
    APPLIED = "applied"
    REJECTED = "rejected"


class ReviewDisposition(StrEnum):
    ACCEPTED = "accepted"
    CHANGES_REQUIRED = "changes_required"
    REJECTED = "rejected"


class OperationState(StrEnum):
    INTENT = "intent"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NO_EFFECT = "no_effect"
    UNKNOWN_EFFECT = "unknown_effect"
    RECONCILED = "reconciled"


TERMINAL_OPERATION_STATES = frozenset(
    {
        OperationState.SUCCEEDED,
        OperationState.FAILED,
        OperationState.NO_EFFECT,
        OperationState.RECONCILED,
    }
)


class TargetMode(StrEnum):
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"
    PROXY = "proxy"
    HYPERVISOR = "hypervisor"
    NATIVE = "native"


class SessionCreate(BaseModel):
    objective: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    host_identity: str = Field(min_length=1)
    target_identity: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    active_seconds: int = Field(default=3 * 60 * 60, gt=0)
    token_limit: int = Field(default=100_000_000, gt=0)


class SessionRecord(BaseModel):
    id: str
    revision: int
    objective: str
    owner: str
    host_identity: str
    target_identity: str | None
    policy: dict[str, Any]
    phase: SessionPhase
    created_at: datetime
    updated_at: datetime
    lifetime_tokens: int = 0
    lifetime_active_seconds: float = 0
    usage_uncertain: bool = False


class OwnerCommand(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cmd"))
    session_id: str
    owner: str = Field(min_length=1)
    kind: CommandKind
    expected_revision: int
    payload: dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=utc_now)


class CommandResult(BaseModel):
    command_id: str
    status: CommandStatus
    session_id: str
    session_revision: int
    outcome: dict[str, Any] = Field(default_factory=dict)


class EventRecord(BaseModel):
    cursor: int
    session_id: str | None
    kind: str
    subject_id: str | None
    data: dict[str, Any]
    occurred_at: datetime


class ArtifactRecord(BaseModel):
    id: str
    publication_id: str | None = None
    sha256: str
    size_bytes: int
    media_type: str
    relative_path: str
    provenance: dict[str, Any]
    created_at: datetime
    available: bool


class TargetSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("target"))
    session_id: str
    identity: str
    boot_epoch: str
    mode: TargetMode
    configuration_digest: str
    capabilities: set[str] = Field(default_factory=set)
    recovery: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=utc_now)
    fresh_until: datetime | None = None

    def is_fresh(self, now: datetime) -> bool:
        return self.fresh_until is None or self.fresh_until >= now


class TypedOperation(BaseModel):
    kind: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$")
    parameters: dict[str, Any] = Field(default_factory=dict)
    mutates_target: bool = False
    timeout_seconds: int = Field(gt=0, le=86_400)


class ProcedureDraft(BaseModel):
    procedure_id: str = Field(default_factory=lambda: new_id("procedure"))
    session_id: str
    title: str = Field(min_length=1)
    operations: list[TypedOperation] = Field(min_length=1)
    prerequisites: set[str] = Field(default_factory=set)
    artifact_digests: set[str] = Field(default_factory=set)
    limits: dict[str, Any] = Field(default_factory=dict)
    abort_conditions: list[str] = Field(default_factory=list)
    cleanup: list[TypedOperation] = Field(default_factory=list)
    recovery: dict[str, Any] = Field(default_factory=dict)
    physical_attendance: Literal["not_required", "required"] = "not_required"
    expected_benefit: str = ""
    failure_severity: str = "unknown"
    hypothesis_id: str | None = None
    protocol_id: str | None = None
    redesign_checkpoint_id: str | None = None


class ProcedureRecord(ProcedureDraft):
    revision: int
    digest: str
    created_at: datetime


class ReviewRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("review"))
    session_id: str
    procedure_id: str
    procedure_revision: int
    procedure_digest: str
    reviewer_job_id: str
    disposition: ReviewDisposition
    blocking_findings: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def blocking_findings_require_changes(self) -> "ReviewRecord":
        if self.blocking_findings and self.disposition == ReviewDisposition.ACCEPTED:
            raise ValueError("an accepted review cannot contain blocking findings")
        return self


class ApprovalScope(BaseModel):
    target_identity: str
    boot_epoch: str | None = None
    configuration_digest: str | None = None
    repeat_limit: int = Field(default=1, gt=0)
    expires_at: datetime
    physical_attendance_confirmed: bool = False

    @model_validator(mode="after")
    def expiry_is_aware(self) -> "ApprovalScope":
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("approval expiry must be timezone-aware")
        return self


class ApprovalRecord(BaseModel):
    id: str
    session_id: str
    procedure_id: str
    procedure_revision: int
    procedure_digest: str
    owner: str
    scope: ApprovalScope
    uses: int = 0
    revoked_at: datetime | None = None
    created_at: datetime


class BudgetSnapshot(BaseModel):
    token_limit: int
    tokens_used: int
    tokens_reserved: int
    tokens_remaining: int
    active_seconds_limit: float
    active_seconds_used: float
    active_seconds_reserved: float
    active_seconds_remaining: float
    usage_uncertain: bool
    admission_open: bool
    blockers: list[str] = Field(default_factory=list)


class SessionSnapshot(BaseModel):
    session: SessionRecord
    budget: BudgetSnapshot
    pending_commands: int
    pending_operations: int
    latest_target: TargetSnapshot | None
    last_event_cursor: int


class EligibilityResult(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    review_id: str | None = None


class DispatchRequest(BaseModel):
    session_id: str
    procedure_id: str
    procedure_revision: int
    target_snapshot_id: str
    adapter_mode: TargetMode
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_active_seconds: int = Field(default=0, ge=0)


class DispatchEnvelope(BaseModel):
    operation_id: str
    session_id: str
    procedure_id: str
    procedure_revision: int
    procedure_digest: str
    target_identity: str
    target_snapshot_id: str
    boot_epoch: str
    configuration_digest: str
    review_id: str = ""
    approval_id: str | None = None
    approval_scope: dict[str, Any] | None = None
    adapter_mode: TargetMode
    operations: list[TypedOperation]
    artifact_digests: list[str] = Field(default_factory=list)
    deadline_at: datetime


class OperationAuthorization(BaseModel):
    eligibility: EligibilityResult
    envelope: DispatchEnvelope | None = None


class OperationOutcome(BaseModel):
    state: Literal[
        OperationState.SUCCEEDED,
        OperationState.FAILED,
        OperationState.NO_EFFECT,
        OperationState.UNKNOWN_EFFECT,
    ]
    result: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    target_condition: str | None = None


class OperationRecord(BaseModel):
    id: str
    session_id: str
    procedure_id: str
    procedure_revision: int
    procedure_digest: str
    approval_id: str | None
    review_id: str
    target_snapshot_id: str
    boot_epoch: str
    adapter_mode: TargetMode
    mutates_target: bool
    state: OperationState
    envelope: DispatchEnvelope
    result: dict[str, Any]
    created_at: datetime
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    reconciliation: dict[str, Any] | None = None


class ReconciliationReport(BaseModel):
    unknown_operation_ids: list[str] = Field(default_factory=list)
    no_effect_operation_ids: list[str] = Field(default_factory=list)
    missing_artifact_ids: list[str] = Field(default_factory=list)
    orphan_artifact_paths: list[str] = Field(default_factory=list)
    active_clock_uncertain_sessions: list[str] = Field(default_factory=list)


class UsageUpdate(BaseModel):
    report_id: str
    session_id: str
    source_id: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cumulative: bool = True
    terminal: bool = False
    reported_at: datetime = Field(default_factory=utc_now)


class UsageResult(BaseModel):
    accepted: bool
    token_delta: int
    lifetime_tokens: int


class JobCreate(BaseModel):
    session_id: str
    kind: Literal["investigate", "implement", "analyze", "review", "conclude", "chat"]
    parent_job_id: str | None = None
    evidence_manifest: dict[str, Any] = Field(default_factory=dict)
    lease_expires_at: datetime
    deadline_at: datetime

    @model_validator(mode="after")
    def lease_precedes_deadline(self) -> "JobCreate":
        if (
            self.lease_expires_at.tzinfo is None
            or self.lease_expires_at.utcoffset() is None
            or self.deadline_at.tzinfo is None
            or self.deadline_at.utcoffset() is None
        ):
            raise ValueError("job lease and deadline must be timezone-aware")
        if self.lease_expires_at > self.deadline_at:
            raise ValueError("job lease cannot outlive its absolute deadline")
        if "_m1lab_parent_job_id" in self.evidence_manifest:
            raise ValueError("job evidence manifest uses a reserved coordinator field")
        return self


class JobRecord(JobCreate):
    id: str
    runtime_id: str | None = None
    state: Literal["admitted", "running", "interrupted", "completed", "failed", "unknown"]
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ReservationRequest(BaseModel):
    session_id: str
    purpose: str
    tokens: int = Field(ge=0)
    active_seconds: int = Field(ge=0)
    expires_at: datetime

    @model_validator(mode="after")
    def expiry_is_aware(self) -> "ReservationRequest":
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("reservation expiry must be timezone-aware")
        return self


class ReservationRecord(ReservationRequest):
    id: str
    created_at: datetime
    released_at: datetime | None = None
