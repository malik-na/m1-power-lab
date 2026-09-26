"""One attended native qualification attempt through a preauthorized helper.

This service does not construct a physical backend or enable a live route.
An uncertain dispatched attempt always remains unknown until reconciliation.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from m1lab.adapters.hardware import (
    HardwareAdapter, HardwareDispatch, HardwareResult, HardwareResultStatus,
    RunNativeCandidate,
)
from m1lab.adapters.native_harness import (
    MAX_NATIVE_MANIFEST_BYTES, decode_native_image_manifest, decode_native_launch_manifest,
)
from m1lab.core import (
    CoreApp, DispatchEnvelope, DispatchRequest, OperationAuthorization,
    OperationOutcome, OperationState, TargetMode, TargetSnapshot,
)
from m1lab.core.models import utc_now
from m1lab.native_runs import (
    IMAGE_MANIFEST_MEDIA_TYPE, LAUNCH_MANIFEST_MEDIA_TYPE, import_native_capture,
)

from .models import ExecutionReport, StepEvidence


class NativeQualificationError(RuntimeError):
    """A native attempt cannot cross its reviewed dispatch boundary."""


class NativeQualificationService:
    """Record proxy snapshots and execute one exact, attended candidate."""

    def __init__(self, core: CoreApp, adapter: HardwareAdapter) -> None:
        self._core = core
        self._adapter = adapter

    def inspect_and_record(self, session_id: str, *, fresh_for_seconds: int = 30) -> TargetSnapshot:
        if not 1 <= fresh_for_seconds <= 30:
            raise ValueError("native proxy snapshot freshness must be 1..30 seconds")
        observed = self._adapter.inspect()
        self._require_proxy(observed, require_candidate_capability=True)
        return self._record_observation(session_id, observed, fresh_for_seconds)

    def _record_observation(self, session_id, observed, fresh_for_seconds: int) -> TargetSnapshot:
        snapshot = TargetSnapshot(
            session_id=session_id, identity=observed.target_id,
            boot_epoch=observed.boot_epoch, mode=TargetMode.PROXY,
            configuration_digest=observed.configuration_digest,
            capabilities={item.name for item in observed.capabilities
                          if item.name == "run_native_candidate" and item.version == 1
                          and item.mutating and item.max_result_bytes == 1_048_576},
            recovery={
                "adapter": observed.adapter, "qualified": False,
                "native_qualification_attempt": True, "message": observed.message,
            },
            observed_at=observed.observed_at,
            fresh_until=observed.observed_at + timedelta(seconds=fresh_for_seconds),
        )
        return self._core.record_target(snapshot)

    def authorize_and_run(self, request: DispatchRequest) -> ExecutionReport:
        return self.run_authorization(self._core.authorize_operation(request))

    def run_authorization(self, authorization: OperationAuthorization) -> ExecutionReport:
        if not authorization.eligibility.eligible or authorization.envelope is None:
            reasons = "; ".join(authorization.eligibility.reasons) or "authorization denied"
            raise NativeQualificationError(reasons)
        return self._run(authorization.envelope)

    def _run(self, envelope: DispatchEnvelope) -> ExecutionReport:
        records = self._core.list_records(envelope.session_id, "operations")
        if not any(record.id == envelope.operation_id and record.envelope == envelope
                   and record.state is OperationState.INTENT for record in records):
            raise NativeQualificationError("native envelope differs from the durable intent")
        artifact_ids: list[str] = []
        evidence: list[StepEvidence] = []
        try:
            operation, launch_id, image_id, launch_configuration = self._preflight(envelope)
            observed = self._adapter.inspect()
            self._require_proxy(observed, require_candidate_capability=True)
            if (observed.target_id != envelope.target_identity
                    or observed.boot_epoch != envelope.boot_epoch
                    or observed.configuration_digest != envelope.configuration_digest):
                raise NativeQualificationError("proxy target changed before native dispatch")
        except Exception as exc:
            return self._finish(
                envelope, OperationState.NO_EFFECT, artifact_ids, evidence,
                f"native pre-dispatch validation failed: {type(exc).__name__}: {exc}",
                "adapter was not invoked",
            )

        try:
            self._core.mark_dispatched(envelope)
        except Exception as exc:
            # Only a still-identical durable intent may be finished here.
            records = self._core.list_records(envelope.session_id, "operations")
            if not any(record.id == envelope.operation_id and record.envelope == envelope
                       and record.state is OperationState.INTENT for record in records):
                raise
            return self._finish(
                envelope, OperationState.NO_EFFECT, artifact_ids, evidence,
                f"native dispatch admission failed: {type(exc).__name__}: {exc}",
                "adapter was not invoked",
            )

        dispatch_id = f"{envelope.operation_id}:0"
        deadline = min(
            envelope.deadline_at,
            utc_now() + timedelta(seconds=envelope.operations[0].timeout_seconds),
        )
        dispatch_started = utc_now()
        result: HardwareResult | None = None
        return_snapshot: TargetSnapshot | None = None
        try:
            dispatch = HardwareDispatch(
                operation_id=dispatch_id,
                coordinator_operation_id=envelope.operation_id,
                session_id=envelope.session_id,
                target_identity=envelope.target_identity,
                target_snapshot_id=envelope.target_snapshot_id,
                configuration_digest=envelope.configuration_digest,
                procedure_id=envelope.procedure_id,
                procedure_revision=envelope.procedure_revision,
                review_id=envelope.review_id,
                approval_id=envelope.approval_id,
                approval_scope=envelope.approval_scope,
                boot_epoch=envelope.boot_epoch,
                procedure_digest=envelope.procedure_digest,
                artifact_digests=tuple(envelope.artifact_digests),
                operation_index=0,
                operation=operation,
                deadline=deadline,
                scope={"session_id": envelope.session_id, "procedure_id": envelope.procedure_id,
                       "step_index": "0", "source": "native_qualification"},
            )
            result = self._adapter.execute(dispatch)
            returned_at = utc_now()
            raw_id, result_id = self._publish_helper_result(envelope, result, artifact_ids)
            evidence.append(StepEvidence(
                index=0, kind="run_native_candidate", dispatch_id=dispatch_id,
                status=result.status.value, result_artifact_id=result_id,
                payload_artifact_id=raw_id, started_at=result.started_at,
                finished_at=result.finished_at, boot_epoch=result.boot_epoch,
            ))
            if result.payload:
                with TemporaryDirectory(prefix="m1lab-helper-stream-") as directory:
                    saved = Path(directory) / "capture.bin"
                    saved.write_bytes(result.payload)
                    capture, raw_record, normalized = import_native_capture(
                        self._core, envelope.session_id,
                        launch_artifact_id=launch_id,
                        image_manifest_artifact_id=image_id,
                        stream_path=saved,
                    )
                for artifact_id in (raw_record.id, normalized.id):
                    if artifact_id not in artifact_ids:
                        artifact_ids.append(artifact_id)
            else:
                capture = None
            return_snapshot = self._observe_return(envelope.session_id)
            return_epoch = result.values.get("return_boot_epoch")
            complete = (
                result.status is HardwareResultStatus.COMPLETED
                and result.operation_id == dispatch_id
                and result.boot_epoch == envelope.boot_epoch
                and dispatch_started <= result.started_at <= result.finished_at <= deadline
                and returned_at <= deadline
                and capture is not None and capture.status == "complete"
                and capture.observed_linux is not None
                and capture.observed_linux.configuration_sha256 == launch_configuration
                and type(return_epoch) is str and bool(return_epoch)
                and return_epoch != envelope.boot_epoch
                and return_snapshot.identity == envelope.target_identity
                and return_snapshot.configuration_digest == envelope.configuration_digest
                and return_snapshot.boot_epoch == return_epoch
            )
            if complete:
                return self._finish(
                    envelope, OperationState.SUCCEEDED, artifact_ids, evidence,
                    "native candidate returned with matching capture and new proxy boot epoch",
                    f"proxy return observed at boot epoch {return_epoch}",
                    return_snapshot_id=return_snapshot.id,
                )
            return self._finish(
                envelope, OperationState.UNKNOWN_EFFECT, artifact_ids, evidence,
                "native candidate return or capture did not meet qualification conditions",
                "requires reconciliation before further target work",
                return_snapshot_id=return_snapshot.id,
            )
        except Exception as exc:
            if return_snapshot is None:
                try:
                    return_snapshot = self._observe_return(envelope.session_id)
                except Exception:
                    pass
            return self._finish(
                envelope, OperationState.UNKNOWN_EFFECT, artifact_ids, evidence,
                f"native dispatch outcome is uncertain: {type(exc).__name__}: {exc}",
                "requires reconciliation before further target work",
                return_snapshot_id=return_snapshot.id if return_snapshot else None,
            )

    def _preflight(self, envelope: DispatchEnvelope) -> tuple[RunNativeCandidate, str, str, str]:
        if envelope.adapter_mode is not TargetMode.PROXY or len(envelope.operations) != 1:
            raise NativeQualificationError("native qualification requires one proxy operation")
        typed = envelope.operations[0]
        parameters = typed.parameters
        keys = {"payload_sha256", "image_manifest_sha256", "launch_manifest_sha256"}
        if (typed.kind != "run_native_candidate" or not typed.mutates_target
                or set(parameters) != keys
                or not set(parameters.values()).issubset(envelope.artifact_digests)
                or len(set(parameters.values())) != 3):
            raise NativeQualificationError("native qualification operation or artifact set is not exact")
        operation = RunNativeCandidate(**parameters)
        artifacts = self._core.artifacts(envelope.session_id)
        by_digest = {digest: [item for item in artifacts if item.available and item.sha256 == digest]
                     for digest in parameters.values()}
        payload = next((item for item in by_digest[operation.payload_sha256]
                        if item.provenance.get("role") == "payload"), None)
        image_record = next((item for item in by_digest[operation.image_manifest_sha256]
                             if item.media_type == IMAGE_MANIFEST_MEDIA_TYPE), None)
        launch_record = next((item for item in by_digest[operation.launch_manifest_sha256]
                              if item.media_type == LAUNCH_MANIFEST_MEDIA_TYPE
                              and image_record is not None
                              and item.provenance.get("image_manifest_artifact_id") == image_record.id
                              and payload is not None
                              and item.provenance.get("image_artifact_id") == payload.id), None)
        if payload is None or image_record is None or launch_record is None:
            raise NativeQualificationError("approved native artifacts are not published in this session")
        image_bytes = self._core.read_session_artifact(
            envelope.session_id, image_record.id, max_bytes=MAX_NATIVE_MANIFEST_BYTES,
        )
        launch_bytes = self._core.read_session_artifact(
            envelope.session_id, launch_record.id, max_bytes=MAX_NATIVE_MANIFEST_BYTES,
        )
        if (hashlib.sha256(image_bytes).hexdigest() != operation.image_manifest_sha256
                or hashlib.sha256(launch_bytes).hexdigest() != operation.launch_manifest_sha256):
            raise NativeQualificationError("approved native manifest bytes changed")
        image = decode_native_image_manifest(image_bytes)
        launch = decode_native_launch_manifest(launch_bytes)
        launch.validate_against_image(image)
        if launch.image_sha256 != operation.payload_sha256 or not any(
            item.role == "payload" and item.sha256 == operation.payload_sha256
            for item in image.outputs
        ):
            raise NativeQualificationError("approved payload digest differs from native manifests")
        return operation, launch_record.id, image_record.id, launch.configuration_sha256

    @staticmethod
    def _require_proxy(observed, *, require_candidate_capability: bool = False) -> None:
        capability = next((item for item in observed.capabilities
                           if item.name == "run_native_candidate" and item.version == 1
                           and item.mutating and item.max_result_bytes == 1_048_576), None)
        if (not observed.available or observed.mode != TargetMode.PROXY.value
                or not observed.target_id or not observed.boot_epoch
                or not observed.configuration_digest
                or (require_candidate_capability and capability is None)):
            raise NativeQualificationError("fixed native proxy capability or identity is unavailable")

    def _observe_return(self, session_id: str) -> TargetSnapshot:
        observed = self._adapter.inspect()
        self._require_proxy(observed)
        return self._record_observation(session_id, observed, 30)

    def _publish_helper_result(
        self, envelope: DispatchEnvelope, result: HardwareResult, artifact_ids: list[str],
    ) -> tuple[str | None, str]:
        provenance = {
            "session_id": envelope.session_id, "operation_id": envelope.operation_id,
            "procedure_id": envelope.procedure_id, "procedure_digest": envelope.procedure_digest,
            "source": "native_helper", "qualification": "attempt_only",
            "physical_source_verified": False, "target_stop_verified": False,
        }
        raw_id = None
        if result.payload:
            raw = self._core.publish_artifact(
                result.payload, media_type="application/octet-stream",
                provenance={**provenance, "record_type": "native_helper_stream",
                            "stream_acquisition": {"mode": "saved_helper_stream",
                                                   "target_stop_verified": False}},
            )
            raw_id = raw.id
            artifact_ids.append(raw_id)
        record = self._core.publish_artifact(
            json.dumps({
                "dispatch_id": result.operation_id, "status": result.status.value,
                "started_at": result.started_at.isoformat(),
                "finished_at": result.finished_at.isoformat(),
                "boot_epoch": result.boot_epoch, "values": dict(result.values),
                "message": result.message, "payload_artifact_id": raw_id,
                "payload_sha256": result.payload_sha256,
                "stream_acquisition": {"mode": "saved_helper_stream",
                                       "target_stop_verified": False},
            }, sort_keys=True, separators=(",", ":")).encode(),
            media_type="application/json",
            provenance={**provenance, "record_type": "native_helper_result"},
        )
        artifact_ids.append(record.id)
        return raw_id, record.id

    def _finish(
        self, envelope: DispatchEnvelope, state: OperationState,
        artifact_ids: list[str], evidence: list[StepEvidence],
        message: str, target_condition: str, *, return_snapshot_id: str | None = None,
    ) -> ExecutionReport:
        details = {
            "message": message, "steps": [step.model_dump(mode="json") for step in evidence],
            "return_snapshot_id": return_snapshot_id,
        }
        self._core.finish_operation(envelope.operation_id, OperationOutcome(
            state=state, result=details, artifact_ids=artifact_ids,
            target_condition=target_condition,
        ))
        return ExecutionReport(
            operation_id=envelope.operation_id, state=state, message=message,
            steps=evidence, artifact_ids=artifact_ids,
            target_condition=target_condition, details=details,
        )
