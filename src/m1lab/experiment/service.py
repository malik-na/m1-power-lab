"""Bounded execution of authorized procedures against a replay target.

The service is the only bridge between the durable coordinator and the
hardware adapter.  It validates the complete envelope before crossing the
dispatch boundary, then sends exactly one typed operation per adapter call.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from typing import Any

from m1lab.adapters import (
    CaptureMemory,
    HardwareAdapter,
    HardwareDispatch,
    HardwareResult,
    HardwareResultStatus,
    InspectRegister,
    ReplayHardwareAdapter,
    SimulateBoot,
    WaitForReplay,
)
from m1lab.core import (
    CoreApp,
    DispatchEnvelope,
    DispatchRequest,
    OperationAuthorization,
    OperationOutcome,
    OperationState,
    TargetMode,
    TargetSnapshot,
    TypedOperation,
)
from m1lab.core.models import utc_now

from .models import ExecutionReport, StepEvidence


class ExperimentError(RuntimeError):
    """Base error for invalid or unavailable experiment execution."""


class EnvelopeRejected(ExperimentError):
    """An envelope does not match the executable replay boundary."""


class TargetChanged(ExperimentError):
    """Target identity or boot epoch changed before dispatch."""


class ExperimentService:
    """Authorize and execute deterministic replay procedures.

    Live m1n1 adapters are deliberately rejected even if they implement the
    hardware protocol.  Enabling live transport requires a different build
    after the physical qualification gates have been completed.
    """

    def __init__(self, core: CoreApp, adapter: HardwareAdapter) -> None:
        if not isinstance(adapter, ReplayHardwareAdapter):
            raise ExperimentError("only the deterministic replay adapter is enabled")
        self._core = core
        self._adapter = adapter

    def inspect_and_record(
        self,
        session_id: str,
        *,
        fresh_for_seconds: int = 30,
    ) -> TargetSnapshot:
        """Inspect replay state and store a short-lived coordinator snapshot."""

        if not 1 <= fresh_for_seconds <= 300:
            raise ValueError("snapshot freshness must be 1..300 seconds")
        observed = self._adapter.inspect()
        if (
            not observed.available
            or observed.adapter != "replay"
            or observed.mode != TargetMode.REPLAY.value
            or not observed.target_id
            or not observed.boot_epoch
        ):
            raise ExperimentError("the deterministic replay target is unavailable")
        capabilities = {capability.name for capability in observed.capabilities}
        configuration_digest = _configuration_digest(observed)
        snapshot = TargetSnapshot(
            session_id=session_id,
            identity=observed.target_id,
            boot_epoch=observed.boot_epoch,
            mode=TargetMode.REPLAY,
            configuration_digest=configuration_digest,
            capabilities=capabilities,
            recovery={
                "adapter": "replay",
                "message": observed.message,
                "remaining_steps": self._adapter.remaining_steps,
            },
            observed_at=observed.observed_at,
            fresh_until=observed.observed_at + timedelta(seconds=fresh_for_seconds),
        )
        return self._core.record_target(snapshot)

    def authorize_and_run(self, request: DispatchRequest) -> ExecutionReport:
        """Request durable authorization and run it when eligible."""

        authorization = self._core.authorize_operation(request)
        if not authorization.eligibility.eligible or authorization.envelope is None:
            reasons = "; ".join(authorization.eligibility.reasons) or "authorization denied"
            raise EnvelopeRejected(reasons)
        return self.run(authorization.envelope)

    def run_authorization(self, authorization: OperationAuthorization) -> ExecutionReport:
        """Run an authorization returned earlier by the coordinator."""

        if not authorization.eligibility.eligible or authorization.envelope is None:
            reasons = "; ".join(authorization.eligibility.reasons) or "authorization denied"
            raise EnvelopeRejected(reasons)
        return self.run(authorization.envelope)

    def run(self, envelope: DispatchEnvelope) -> ExecutionReport:
        """Execute an authorized envelope, preserving evidence at every step."""

        artifacts: list[str] = []
        evidence: list[StepEvidence] = []
        try:
            mapped = self._validate_and_map(envelope)
            self._verify_target(envelope.target_identity, envelope.boot_epoch)
        except Exception as exc:
            message = f"pre-dispatch validation failed: {exc}"
            outcome = OperationOutcome(
                state=OperationState.NO_EFFECT,
                result={"message": message, "stage": "pre_dispatch"},
                artifact_ids=[],
                target_condition="adapter was not invoked",
            )
            self._core.finish_operation(envelope.operation_id, outcome)
            return ExecutionReport(
                operation_id=envelope.operation_id,
                state=OperationState.NO_EFFECT,
                message=message,
                target_condition="adapter was not invoked",
            )

        expected_boot = envelope.boot_epoch
        # This is the point of possible effect: record DISPATCHED immediately
        # before the first adapter call, after all local validation and preflight.
        self._core.mark_dispatched(envelope)

        for index, (typed, hardware_operation) in enumerate(mapped):
            dispatch_id = f"{envelope.operation_id}:{index}"
            try:
                self._verify_target(envelope.target_identity, expected_boot)
                deadline = min(
                    envelope.deadline_at,
                    utc_now() + timedelta(seconds=typed.timeout_seconds),
                )
                result = self._adapter.execute(
                    HardwareDispatch(
                        operation_id=dispatch_id,
                        boot_epoch=expected_boot,
                        procedure_digest=envelope.procedure_digest,
                        operation=hardware_operation,
                        deadline=deadline,
                        scope={
                            "session_id": envelope.session_id,
                            "procedure_id": envelope.procedure_id,
                            "step_index": str(index),
                        },
                    )
                )
                step, step_artifacts = self._publish_result(envelope, index, typed, result)
                evidence.append(step)
                artifacts.extend(step_artifacts)

                if result.status is HardwareResultStatus.UNKNOWN:
                    return self._unknown(
                        envelope, evidence, artifacts, result.message or "adapter reported unknown effect"
                    )
                if result.status is HardwareResultStatus.FAILED:
                    self._verify_target(envelope.target_identity, expected_boot)
                    return self._finish(
                        envelope,
                        OperationState.FAILED,
                        evidence,
                        artifacts,
                        result.message or "adapter reported failure",
                        "observed after a definitive adapter failure",
                    )
                expected_after = (
                    hardware_operation.next_boot_epoch
                    if isinstance(hardware_operation, SimulateBoot)
                    else expected_boot
                )
                post = self._verify_target(envelope.target_identity, expected_after)
                if result.boot_epoch != expected_after or post.boot_epoch != expected_after:
                    return self._unknown(
                        envelope,
                        evidence,
                        artifacts,
                        "target boot epoch differed after dispatch",
                    )
                expected_boot = expected_after
            except Exception as exc:
                diagnostic_error: Exception | None = None
                try:
                    diagnostic_id = self._publish_diagnostic(envelope, index, dispatch_id, exc)
                    artifacts.append(diagnostic_id)
                except Exception as publish_exc:
                    # Hardware may already have acted.  Evidence publication
                    # failure must not disguise that uncertainty or discard
                    # artifact references captured by earlier steps.
                    diagnostic_error = publish_exc
                message = f"dispatch outcome is uncertain: {type(exc).__name__}: {exc}"
                if diagnostic_error is not None:
                    message += (
                        "; diagnostic artifact publication also failed: "
                        f"{type(diagnostic_error).__name__}: {diagnostic_error}"
                    )
                return self._unknown(
                    envelope,
                    evidence,
                    artifacts,
                    message,
                )

        try:
            self.inspect_and_record(envelope.session_id, fresh_for_seconds=300)
        except Exception as exc:
            return self._unknown(
                envelope,
                evidence,
                artifacts,
                f"execution completed but final target state could not be recorded: {type(exc).__name__}: {exc}",
            )
        return self._finish(
            envelope,
            OperationState.SUCCEEDED,
            evidence,
            artifacts,
            "all typed operations completed",
            f"replay target observed at boot epoch {expected_boot}",
        )

    def _validate_and_map(
        self, envelope: DispatchEnvelope
    ) -> list[tuple[TypedOperation, InspectRegister | CaptureMemory | WaitForReplay | SimulateBoot]]:
        if envelope.adapter_mode is not TargetMode.REPLAY:
            raise EnvelopeRejected("only replay envelopes may execute")
        if not envelope.operations:
            raise EnvelopeRejected("an envelope must contain at least one operation")
        if envelope.deadline_at <= utc_now():
            raise EnvelopeRejected("the envelope deadline has expired")
        mapped = [(operation, _map_operation(operation)) for operation in envelope.operations]
        for index, (typed, hardware) in enumerate(mapped):
            expected_mutation = isinstance(hardware, SimulateBoot)
            if typed.mutates_target != expected_mutation:
                raise EnvelopeRejected(
                    f"operation {index} mutation declaration does not match its typed capability"
                )
            if isinstance(hardware, SimulateBoot) and index != len(mapped) - 1:
                raise EnvelopeRejected("simulate_boot must be the final operation in a procedure")
        return mapped

    def _verify_target(self, target_identity: str, boot_epoch: str):
        observed = self._adapter.inspect()
        if not observed.available or observed.adapter != "replay" or observed.mode != "replay":
            raise TargetChanged("replay adapter is unavailable")
        if observed.target_id != target_identity:
            raise TargetChanged(
                f"target identity changed from {target_identity!r} to {observed.target_id!r}"
            )
        if observed.boot_epoch != boot_epoch:
            raise TargetChanged(
                f"boot epoch changed from {boot_epoch!r} to {observed.boot_epoch!r}"
            )
        return observed

    def _publish_result(
        self,
        envelope: DispatchEnvelope,
        index: int,
        operation: TypedOperation,
        result: HardwareResult,
    ) -> tuple[StepEvidence, list[str]]:
        provenance = {
            "session_id": envelope.session_id,
            "operation_id": envelope.operation_id,
            "procedure_id": envelope.procedure_id,
            "procedure_revision": envelope.procedure_revision,
            "procedure_digest": envelope.procedure_digest,
            "step_index": index,
            "typed_operation": operation.kind,
            "source": "replay_adapter",
        }
        ids: list[str] = []
        payload_id: str | None = None
        if result.payload:
            payload = self._core.publish_artifact(
                result.payload,
                media_type="application/octet-stream",
                provenance={**provenance, "role": "hardware_payload"},
            )
            payload_id = payload.id
            ids.append(payload.id)
        manifest = {
            "dispatch_id": result.operation_id,
            "status": result.status.value,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "boot_epoch": result.boot_epoch,
            "values": dict(result.values),
            "message": result.message,
            "payload_sha256": result.payload_sha256,
            "payload_artifact_id": payload_id,
        }
        record = self._core.publish_artifact(
            _canonical_json(manifest),
            media_type="application/json",
            provenance={**provenance, "role": "hardware_result"},
        )
        ids.append(record.id)
        return (
            StepEvidence(
                index=index,
                kind=operation.kind,
                dispatch_id=result.operation_id,
                status=result.status.value,
                result_artifact_id=record.id,
                payload_artifact_id=payload_id,
                started_at=result.started_at,
                finished_at=result.finished_at,
                boot_epoch=result.boot_epoch,
            ),
            ids,
        )

    def _publish_diagnostic(
        self, envelope: DispatchEnvelope, index: int, dispatch_id: str, exc: Exception
    ) -> str:
        record = self._core.publish_artifact(
            _canonical_json(
                {
                    "dispatch_id": dispatch_id,
                    "step_index": index,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "observed_at": utc_now().isoformat(),
                }
            ),
            media_type="application/json",
            provenance={
                "session_id": envelope.session_id,
                "operation_id": envelope.operation_id,
                "procedure_id": envelope.procedure_id,
                "procedure_digest": envelope.procedure_digest,
                "step_index": index,
                "role": "dispatch_diagnostic",
                "source": "experiment_service",
            },
        )
        return record.id

    def _finish(
        self,
        envelope: DispatchEnvelope,
        state: OperationState,
        evidence: list[StepEvidence],
        artifact_ids: list[str],
        message: str,
        target_condition: str,
    ) -> ExecutionReport:
        details = {"message": message, "steps": [item.model_dump(mode="json") for item in evidence]}
        self._core.finish_operation(
            envelope.operation_id,
            OperationOutcome(
                state=state,
                result=details,
                artifact_ids=artifact_ids,
                target_condition=target_condition,
            ),
        )
        return ExecutionReport(
            operation_id=envelope.operation_id,
            state=state,
            message=message,
            steps=evidence,
            artifact_ids=artifact_ids,
            target_condition=target_condition,
            details=details,
        )

    def _unknown(
        self,
        envelope: DispatchEnvelope,
        evidence: list[StepEvidence],
        artifact_ids: list[str],
        message: str,
    ) -> ExecutionReport:
        details = {"message": message, "steps": [item.model_dump(mode="json") for item in evidence]}
        self._core.finish_operation(
            envelope.operation_id,
            OperationOutcome(
                state=OperationState.UNKNOWN_EFFECT,
                result=details,
                artifact_ids=artifact_ids,
                target_condition="requires reconciliation before further target work",
            ),
        )
        return ExecutionReport(
            operation_id=envelope.operation_id,
            state=OperationState.UNKNOWN_EFFECT,
            message=message,
            steps=evidence,
            artifact_ids=artifact_ids,
            target_condition="requires reconciliation before further target work",
            core_state_recorded=True,
            details=details,
        )


def _map_operation(operation: TypedOperation):
    parameters = operation.parameters
    if operation.kind == "inspect_register":
        _require_keys(parameters, {"address", "width_bytes"})
        return InspectRegister(
            address=_require_int(parameters, "address"),
            width_bytes=_require_int(parameters, "width_bytes"),
        )
    if operation.kind == "capture_memory":
        _require_keys(parameters, {"address", "length"})
        return CaptureMemory(
            address=_require_int(parameters, "address"),
            length=_require_int(parameters, "length"),
        )
    if operation.kind == "wait":
        _require_keys(parameters, {"duration_ms"})
        return WaitForReplay(duration_ms=_require_int(parameters, "duration_ms"))
    if operation.kind == "simulate_boot":
        _require_keys(parameters, {"next_boot_epoch"})
        value = parameters["next_boot_epoch"]
        if not isinstance(value, str):
            raise EnvelopeRejected("next_boot_epoch must be a string")
        return SimulateBoot(next_boot_epoch=value)
    raise EnvelopeRejected(f"unsupported typed operation {operation.kind!r}")


def _require_keys(parameters: dict[str, Any], required: set[str]) -> None:
    keys = set(parameters)
    if keys != required:
        missing = sorted(required - keys)
        extra = sorted(keys - required)
        raise EnvelopeRejected(f"invalid parameters; missing={missing}, extra={extra}")


def _require_int(parameters: dict[str, Any], name: str) -> int:
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnvelopeRejected(f"{name} must be an integer")
    return value


def _configuration_digest(snapshot: Any) -> str:
    capabilities = [
        {
            "name": item.name,
            "version": item.version,
            "mutating": item.mutating,
            "max_result_bytes": item.max_result_bytes,
        }
        for item in snapshot.capabilities
    ]
    return hashlib.sha256(
        _canonical_json(
            {
                "adapter": snapshot.adapter,
                "mode": snapshot.mode,
                "target_id": snapshot.target_id,
                "capabilities": capabilities,
            }
        )
    ).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
