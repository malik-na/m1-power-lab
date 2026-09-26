"""Typed hardware boundary and a deterministic replay implementation.

Nothing in this module opens a device.  The real m1n1 adapter intentionally
remains unavailable until transport, target identity, result collection and
recovery have been qualified on the lab machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import threading
import time
from types import MappingProxyType
from typing import Mapping, Protocol, TypeAlias, runtime_checkable


MAX_CAPTURE_BYTES = 1_048_576
MAX_REPLAY_WAIT_MS = 30_000
MAX_RESULT_BYTES = 1_048_576
MAX_SCOPE_ENTRIES = 64
M1N1_QUALIFICATION_MESSAGE = (
    "Live m1n1 access is unavailable: qualify the physical target identity, "
    "exclusive transport, boot-epoch detection, bounded result channel, and "
    "recovery procedure before installing a real adapter."
)


class HardwareError(RuntimeError):
    """Base error raised at the hardware adapter boundary."""


class HardwareUnavailable(HardwareError):
    """The requested hardware transport is not available or qualified."""


class ReplayMismatch(HardwareError):
    """A replay dispatch does not match the next recorded operation."""


@dataclass(frozen=True, slots=True)
class HardwareCapability:
    name: str
    version: int
    mutating: bool
    max_result_bytes: int = 0

    def __post_init__(self) -> None:
        if not self.name or self.version < 1:
            raise ValueError("capability requires a name and positive version")
        if not 0 <= self.max_result_bytes <= MAX_RESULT_BYTES:
            raise ValueError("capability result bound is invalid")


@dataclass(frozen=True, slots=True)
class TargetSnapshot:
    adapter: str
    available: bool
    qualified: bool
    mode: str
    target_id: str | None
    boot_epoch: str | None
    capabilities: tuple[HardwareCapability, ...]
    observed_at: datetime
    message: str = ""

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class InspectRegister:
    """Read a fixed-width value from a replay trace."""

    address: int
    width_bytes: int
    kind: str = field(default="inspect_register", init=False)

    def __post_init__(self) -> None:
        if not 0 <= self.address <= (1 << 64) - 1:
            raise ValueError("register address is outside uint64")
        if self.width_bytes not in (1, 2, 4, 8):
            raise ValueError("register width must be 1, 2, 4, or 8 bytes")
        if self.address + self.width_bytes > 1 << 64:
            raise ValueError("register read wraps the address space")


@dataclass(frozen=True, slots=True)
class CaptureMemory:
    """Capture a bounded contiguous range from a replay trace."""

    address: int
    length: int
    kind: str = field(default="capture_memory", init=False)

    def __post_init__(self) -> None:
        if not 0 <= self.address <= (1 << 64) - 1:
            raise ValueError("capture address is outside uint64")
        if not 1 <= self.length <= MAX_CAPTURE_BYTES:
            raise ValueError(f"capture length must be 1..{MAX_CAPTURE_BYTES}")
        if self.address + self.length > 1 << 64:
            raise ValueError("memory capture wraps the address space")


@dataclass(frozen=True, slots=True)
class WaitForReplay:
    """Replay a bounded passage of time without sleeping by default."""

    duration_ms: int
    kind: str = field(default="wait", init=False)

    def __post_init__(self) -> None:
        if not 0 <= self.duration_ms <= MAX_REPLAY_WAIT_MS:
            raise ValueError(f"wait must be 0..{MAX_REPLAY_WAIT_MS} ms")


@dataclass(frozen=True, slots=True)
class SimulateBoot:
    """Advance to an explicitly recorded replay boot epoch."""

    next_boot_epoch: str
    kind: str = field(default="simulate_boot", init=False)

    def __post_init__(self) -> None:
        if not self.next_boot_epoch or len(self.next_boot_epoch) > 128:
            raise ValueError("next boot epoch must be 1..128 characters")


HardwareOperation: TypeAlias = (
    InspectRegister | CaptureMemory | WaitForReplay | SimulateBoot
)


@dataclass(frozen=True, slots=True)
class HardwareDispatch:
    operation_id: str
    coordinator_operation_id: str
    session_id: str
    target_identity: str
    target_snapshot_id: str
    configuration_digest: str
    procedure_id: str
    procedure_revision: int
    review_id: str
    approval_id: str | None
    approval_scope: Mapping[str, object] | None
    boot_epoch: str
    procedure_digest: str
    artifact_digests: tuple[str, ...]
    operation_index: int
    operation: HardwareOperation
    deadline: datetime
    artifact_digest: str | None = None
    scope: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_id or len(self.operation_id) > 128:
            raise ValueError("operation_id must be 1..128 characters")
        if not self.coordinator_operation_id or len(self.coordinator_operation_id) > 128:
            raise ValueError("coordinator_operation_id must be 1..128 characters")
        for name, value in (
            ("session_id", self.session_id),
            ("target_identity", self.target_identity),
            ("target_snapshot_id", self.target_snapshot_id),
            ("procedure_id", self.procedure_id),
        ):
            if not value or len(value) > 160:
                raise ValueError(f"{name} must be 1..160 characters")
        if self.procedure_revision < 1 or self.operation_index < 0:
            raise ValueError("procedure revision and operation index are invalid")
        if not self.review_id or len(self.review_id) > 128:
            raise ValueError("dispatch requires the exact accepted review ID")
        if self.approval_id is not None and (
            not self.approval_id or len(self.approval_id) > 128
        ):
            raise ValueError("approval ID must be 1..128 characters")
        if (self.approval_id is None) != (self.approval_scope is None):
            raise ValueError("approval ID and exact approval scope must travel together")
        if self.approval_scope is not None:
            approval = dict(self.approval_scope)
            expected_approval_fields = {
                "target_identity",
                "boot_epoch",
                "configuration_digest",
                "repeat_limit",
                "expires_at",
                "physical_attendance_confirmed",
            }
            if set(approval) != expected_approval_fields:
                raise ValueError("approval scope has unknown or missing fields")
            if approval.get("target_identity") != self.target_identity:
                raise ValueError("approval scope target does not match the dispatch target")
            if approval.get("boot_epoch") not in (None, self.boot_epoch):
                raise ValueError("approval scope boot epoch does not match the dispatch")
            if approval.get("configuration_digest") not in (None, self.configuration_digest):
                raise ValueError("approval scope configuration does not match the dispatch")
            expires_at = approval.get("expires_at")
            if not isinstance(expires_at, str):
                raise ValueError("approval scope is missing its expiry")
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None or expiry <= _utc_now():
                raise ValueError("approval scope has expired or has no timezone")
            if type(approval.get("repeat_limit")) is not int or approval["repeat_limit"] < 1:
                raise ValueError("approval scope repeat limit is invalid")
            if type(approval.get("physical_attendance_confirmed")) is not bool:
                raise ValueError("approval scope attendance flag is invalid")
            object.__setattr__(self, "approval_scope", MappingProxyType(approval))
        if not self.boot_epoch or len(self.boot_epoch) > 128:
            raise ValueError("boot_epoch must be 1..128 characters")
        _require_sha256(self.procedure_digest, "procedure_digest")
        _require_sha256(self.configuration_digest, "configuration_digest")
        if len(self.artifact_digests) > 256:
            raise ValueError("dispatch contains too many artifact digests")
        if len(set(self.artifact_digests)) != len(self.artifact_digests):
            raise ValueError("dispatch artifact digests must be unique")
        for digest in self.artifact_digests:
            _require_sha256(digest, "artifact_digest")
        if self.artifact_digest is not None:
            _require_sha256(self.artifact_digest, "artifact_digest")
        if self.deadline.tzinfo is None or self.deadline.utcoffset() is None:
            raise ValueError("deadline must be timezone-aware")
        if self.deadline <= _utc_now():
            raise ValueError("dispatch deadline has expired")
        if len(self.scope) > MAX_SCOPE_ENTRIES:
            raise ValueError("dispatch scope has too many entries")
        normalized: dict[str, str] = {}
        for key, value in self.scope.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("dispatch scope keys and values must be strings")
            if not key or len(key) > 128 or len(value) > 1_024:
                raise ValueError("dispatch scope entry exceeds its bound")
            normalized[key] = value
        object.__setattr__(self, "scope", MappingProxyType(normalized))


class HardwareResultStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HardwareResult:
    operation_id: str
    status: HardwareResultStatus
    started_at: datetime
    finished_at: datetime
    boot_epoch: str
    values: Mapping[str, int | float | str | bool | None] = field(default_factory=dict)
    payload: bytes = b""
    message: str = ""

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("result timestamps must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("result finishes before it starts")
        if len(self.payload) > MAX_RESULT_BYTES:
            raise ValueError("result payload exceeds adapter bound")
        if len(self.message) > 4_096:
            raise ValueError("result message exceeds adapter bound")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @property
    def payload_sha256(self) -> str | None:
        return hashlib.sha256(self.payload).hexdigest() if self.payload else None


@runtime_checkable
class HardwareAdapter(Protocol):
    def inspect(self) -> TargetSnapshot:
        """Return the adapter's current observed target state."""

    def execute(self, dispatch: HardwareDispatch) -> HardwareResult:
        """Execute exactly one typed, already-authorized dispatch."""


@dataclass(frozen=True, slots=True)
class ReplayStep:
    operation: HardwareOperation
    status: HardwareResultStatus = HardwareResultStatus.COMPLETED
    values: Mapping[str, int | float | str | bool | None] = field(default_factory=dict)
    payload: bytes = b""
    message: str = ""

    def __post_init__(self) -> None:
        if len(self.payload) > MAX_RESULT_BYTES:
            raise ValueError("replay payload exceeds adapter bound")
        if len(self.message) > 4_096:
            raise ValueError("replay message exceeds adapter bound")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


class ReplayHardwareAdapter:
    """Strict sequential playback of pre-recorded typed operations.

    A call consumes a step only after its operation and boot epoch match.  The
    adapter never interprets command strings, imports payload code, or touches
    USB/serial devices.
    """

    def __init__(
        self,
        steps: tuple[ReplayStep, ...] | list[ReplayStep] = (),
        *,
        target_id: str = "replay-target",
        boot_epoch: str = "replay-boot-1",
        real_time_waits: bool = False,
    ) -> None:
        if not target_id or not boot_epoch:
            raise ValueError("replay target and boot epoch must be non-empty")
        self._steps = tuple(steps)
        self._target_id = target_id
        self._boot_epoch = boot_epoch
        self._real_time_waits = real_time_waits
        self._cursor = 0
        self._lock = threading.Lock()
        self._execution_lock = threading.Lock()

    @property
    def remaining_steps(self) -> int:
        with self._lock:
            return len(self._steps) - self._cursor

    def inspect(self) -> TargetSnapshot:
        with self._lock:
            boot_epoch = self._boot_epoch
        return TargetSnapshot(
            adapter="replay",
            available=True,
            qualified=False,
            mode="replay",
            target_id=self._target_id,
            boot_epoch=boot_epoch,
            capabilities=_REPLAY_CAPABILITIES,
            observed_at=_utc_now(),
            message="Synthetic replay only; this does not establish live hardware behavior.",
        )

    def execute(self, dispatch: HardwareDispatch) -> HardwareResult:
        # Preserve the single-target operation contract even when a caller
        # invokes the adapter concurrently.
        with self._execution_lock:
            return self._execute_serialized(dispatch)

    def _execute_serialized(self, dispatch: HardwareDispatch) -> HardwareResult:
        started = _utc_now()
        if dispatch.deadline <= started:
            raise HardwareError("dispatch deadline has expired")

        with self._lock:
            if dispatch.boot_epoch != self._boot_epoch:
                raise ReplayMismatch(
                    f"boot epoch mismatch: expected {self._boot_epoch!r}, "
                    f"received {dispatch.boot_epoch!r}"
                )
            if self._cursor >= len(self._steps):
                raise ReplayMismatch("replay trace is exhausted")
            step = self._steps[self._cursor]
            if type(step.operation) is not type(dispatch.operation) or step.operation != dispatch.operation:
                raise ReplayMismatch(
                    f"step {self._cursor} expects {step.operation!r}, "
                    f"received {dispatch.operation!r}"
                )
            self._cursor += 1

            if isinstance(dispatch.operation, SimulateBoot) and step.status is HardwareResultStatus.COMPLETED:
                self._boot_epoch = dispatch.operation.next_boot_epoch
            result_boot_epoch = self._boot_epoch

        if self._real_time_waits and isinstance(dispatch.operation, WaitForReplay):
            remaining = (dispatch.deadline - _utc_now()).total_seconds()
            delay = dispatch.operation.duration_ms / 1_000
            if delay > remaining:
                return HardwareResult(
                    operation_id=dispatch.operation_id,
                    status=HardwareResultStatus.UNKNOWN,
                    started_at=started,
                    finished_at=_utc_now(),
                    boot_epoch=result_boot_epoch,
                    message="replay deadline elapsed before the recorded wait completed",
                )
            time.sleep(delay)

        return HardwareResult(
            operation_id=dispatch.operation_id,
            status=step.status,
            started_at=started,
            finished_at=_utc_now(),
            boot_epoch=result_boot_epoch,
            values=step.values,
            payload=step.payload,
            message=step.message,
        )


class M1n1HardwareAdapter:
    """Explicitly unavailable placeholder for the future qualified adapter."""

    def inspect(self) -> TargetSnapshot:
        return TargetSnapshot(
            adapter="m1n1-unavailable",
            available=False,
            qualified=False,
            mode="disconnected",
            target_id=None,
            boot_epoch=None,
            capabilities=(),
            observed_at=_utc_now(),
            message=M1N1_QUALIFICATION_MESSAGE,
        )

    def execute(self, dispatch: HardwareDispatch) -> HardwareResult:
        del dispatch
        raise HardwareUnavailable(M1N1_QUALIFICATION_MESSAGE)


_REPLAY_CAPABILITIES = (
    HardwareCapability("inspect_register", 1, False, 8),
    HardwareCapability("capture_memory", 1, False, MAX_CAPTURE_BYTES),
    HardwareCapability("wait", 1, False, 0),
    HardwareCapability("simulate_boot", 1, True, 0),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
