"""Coordinator-native attempt with controlled synthetic helper observations."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from m1lab.adapters.hardware import (
    HardwareCapability, HardwareResult, HardwareResultStatus, TargetSnapshot,
)
from m1lab.adapters.native_harness import (
    ObservedLinuxIdentity, decode_native_result_frame, encode_native_result_frame,
)
from m1lab.core.coordinator import CoreApp
from m1lab.core.models import (
    CommandKind, CommandStatus, DispatchRequest, JobCreate, OperationState,
    OwnerCommand, ProcedureDraft, ReviewDisposition, ReviewRecord, TargetMode,
    TypedOperation, utc_now,
)
from m1lab.experiment.native_qualification import NativeQualificationError, NativeQualificationService
from m1lab.paths import AppPaths

from test_native_capture import _capture, _frames


class CandidateAdapter:
    def __init__(self, configuration_digest: str, payload: bytes):
        self.snapshot = TargetSnapshot(
            adapter="synthetic-native-helper", available=True, qualified=False,
            mode="proxy", target_id="synthetic-target", boot_epoch="synthetic-boot",
            configuration_digest=configuration_digest,
            capabilities=(HardwareCapability("run_native_candidate", 1, True, 1_048_576),),
            observed_at=utc_now(), message="Synthetic fixture; not physical evidence.",
        )
        self.payload = payload
        self.calls = []
        self.mode = "complete"

    def inspect(self):
        return replace(self.snapshot, observed_at=utc_now())

    def execute(self, dispatch):
        self.calls.append(dispatch)
        if self.mode == "execute_error":
            raise OSError("synthetic helper channel lost after entry")
        initial_epoch = self.snapshot.boot_epoch
        if self.mode == "postflight_unavailable":
            self.snapshot = replace(self.snapshot, available=False, mode="disconnected")
        else:
            self.snapshot = replace(
                self.snapshot, boot_epoch="synthetic-return-boot",
                capabilities=() if self.mode == "return_without_candidate_capability" else self.snapshot.capabilities,
            )
        now = utc_now()
        return HardwareResult(
            operation_id=dispatch.operation_id,
            status=HardwareResultStatus.COMPLETED,
            started_at=now, finished_at=now,
            boot_epoch=initial_epoch,
            values={"return_boot_epoch": (
                "different-return" if self.mode == "wrong_return" else "synthetic-return-boot"
            )},
            payload=self.payload,
            message="synthetic only",
        )


def _owner_command(core, session_id, owner, kind, payload=None):
    result = core.submit(OwnerCommand(
        session_id=session_id, owner=owner,
        expected_revision=core.session(session_id).revision,
        kind=kind, payload=payload or {},
    ))
    assert result.status is CommandStatus.APPLIED, result.outcome


def _reviewed_attempt(core, tmp_path):
    session_id, image, image_artifact, launch, launch_artifact, stream, _ = _capture(core, tmp_path)
    session = core.session(session_id)
    _owner_command(core, session_id, session.owner, CommandKind.START)
    frames = _frames(stream)
    identity = decode_native_result_frame(frames[0])
    observed = ObservedLinuxIdentity(
        boot_id="12345678-1234-1234-1234-123456789abc",
        kernel_release="synthetic-kernel",
        configuration_sha256=image.configuration_sha256,
    )
    stream = encode_native_result_frame(identity.model_copy(update={"observed_linux": observed})) + b"".join(frames[1:])
    helper_configuration_digest = "d" * 64
    assert helper_configuration_digest != launch.configuration_sha256
    adapter = CandidateAdapter(helper_configuration_digest, stream)
    service = NativeQualificationService(core, adapter)
    target = service.inspect_and_record(session_id)
    assert target.recovery["qualified"] is False
    payload_artifact = core.session_artifact(
        session_id, launch_artifact.provenance["image_artifact_id"]
    )
    parameters = {
        "payload_sha256": payload_artifact.sha256,
        "image_manifest_sha256": image_artifact.sha256,
        "launch_manifest_sha256": launch_artifact.sha256,
    }
    reviewed_launcher = core.publish_artifact(
        b"synthetic reviewed launcher provenance",
        provenance={"session_id": session_id, "role": "launcher_tool", "source": "host-test"},
    )
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session_id, title="Synthetic attended native qualification",
        operations=[TypedOperation(
            kind="run_native_candidate", parameters=parameters,
            mutates_target=True, timeout_seconds=120,
        )],
        prerequisites={"run_native_candidate"},
        artifact_digests={*parameters.values(), reviewed_launcher.sha256},
        physical_attendance="required",
    ))
    now = utc_now()
    reviewer = core.create_job(JobCreate(
        session_id=session_id, kind="review",
        evidence_manifest={"review_target": {
            "procedure_id": procedure.procedure_id,
            "procedure_revision": procedure.revision,
            "procedure_digest": procedure.digest,
        }},
        lease_expires_at=now + timedelta(minutes=1),
        deadline_at=now + timedelta(minutes=2),
    ))
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    core.record_review(ReviewRecord(
        session_id=session_id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, procedure_digest=procedure.digest,
        reviewer_job_id=reviewer.id, disposition=ReviewDisposition.ACCEPTED,
    ))
    _owner_command(core, session_id, session.owner, CommandKind.APPROVE, {
        "procedure_id": procedure.procedure_id,
        "procedure_revision": procedure.revision,
        "scope": {
            "target_identity": target.identity, "boot_epoch": target.boot_epoch,
            "configuration_digest": target.configuration_digest,
            "repeat_limit": 1,
            "expires_at": (utc_now() + timedelta(minutes=5)).isoformat(),
            "physical_attendance_confirmed": True,
        },
    })
    request = DispatchRequest(
        session_id=session_id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision,
        target_snapshot_id=target.id, adapter_mode=TargetMode.PROXY,
    )
    return session_id, service, adapter, request, stream


@pytest.fixture
def enabled_core(tmp_path):
    core = CoreApp.open(AppPaths(tmp_path / "enabled"), allow_native_qualification=True)
    try:
        yield core
    finally:
        core.close()


@pytest.mark.parametrize("return_capability", [True, False])
def test_complete_native_attempt_requires_causal_capture_and_new_proxy_epoch(
    enabled_core, tmp_path, return_capability,
):
    session_id, service, adapter, request, stream = _reviewed_attempt(enabled_core, tmp_path)
    if not return_capability:
        adapter.mode = "return_without_candidate_capability"

    report = service.authorize_and_run(request)

    assert report.state is OperationState.SUCCEEDED
    assert len(adapter.calls) == 1
    assert adapter.calls[0].operation.kind == "run_native_candidate"
    assert adapter.calls[0].approval_id and adapter.calls[0].review_id
    assert adapter.calls[0].artifact_digests == tuple(sorted(request_digests(enabled_core, session_id)))
    assert len(adapter.calls[0].artifact_digests) == 4
    assert len(report.artifact_ids) >= 3
    raw = enabled_core.session_artifact(session_id, report.artifact_ids[0])
    assert enabled_core.read_session_artifact(session_id, raw.id) == stream
    helper_result = json.loads(enabled_core.read_session_artifact(session_id, report.artifact_ids[1]))
    assert helper_result["stream_acquisition"]["mode"] == "saved_helper_stream"
    assert helper_result["payload_artifact_id"] == raw.id
    target = enabled_core.snapshot(session_id).latest_target
    assert target.boot_epoch == "synthetic-return-boot"
    assert target.recovery["qualified"] is False
    assert report.details["return_snapshot_id"] == target.id
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.SUCCEEDED


def request_digests(core, session_id):
    return core.list_records(session_id, "operations")[0].envelope.artifact_digests


@pytest.mark.parametrize("mode", ["wrong_return", "postflight_unavailable"])
def test_mismatched_return_is_unknown_with_raw_evidence(enabled_core, tmp_path, mode):
    session_id, service, adapter, request, stream = _reviewed_attempt(enabled_core, tmp_path)
    adapter.mode = mode

    report = service.authorize_and_run(request)

    assert report.state is OperationState.UNKNOWN_EFFECT
    assert len(adapter.calls) == 1
    assert report.artifact_ids
    assert enabled_core.read_session_artifact(session_id, report.artifact_ids[0]) == stream
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.UNKNOWN_EFFECT


def test_preflight_epoch_change_finishes_no_effect_without_adapter_call(enabled_core, tmp_path):
    session_id, service, adapter, request, _ = _reviewed_attempt(enabled_core, tmp_path)
    authorization = enabled_core.authorize_operation(request)
    assert authorization.eligibility.eligible
    adapter.snapshot = replace(adapter.snapshot, boot_epoch="unexpected-before-dispatch")

    report = service.run_authorization(authorization)

    assert report.state is OperationState.NO_EFFECT
    assert adapter.calls == []
    assert report.artifact_ids == []
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.NO_EFFECT


def test_forged_authorization_cannot_cancel_durable_intent(enabled_core, tmp_path):
    session_id, service, adapter, request, _ = _reviewed_attempt(enabled_core, tmp_path)
    authorization = enabled_core.authorize_operation(request)
    forged = authorization.model_copy(update={
        "envelope": authorization.envelope.model_copy(update={"review_id": "other-review"}),
    })

    with pytest.raises(NativeQualificationError, match="durable intent"):
        service.run_authorization(forged)
    assert adapter.calls == []
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.INTENT


def test_execute_failure_remains_unknown_without_retry(enabled_core, tmp_path):
    session_id, service, adapter, request, _ = _reviewed_attempt(enabled_core, tmp_path)
    adapter.mode = "execute_error"

    report = service.authorize_and_run(request)

    assert report.state is OperationState.UNKNOWN_EFFECT
    assert len(adapter.calls) == 1
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.UNKNOWN_EFFECT


def test_import_failure_keeps_helper_stream_and_uncertain_outcome(enabled_core, tmp_path, monkeypatch):
    session_id, service, adapter, request, stream = _reviewed_attempt(enabled_core, tmp_path)
    import m1lab.experiment.native_qualification as native_qualification

    def fail_import(*_args, **_kwargs):
        raise ValueError("synthetic import failure")

    monkeypatch.setattr(native_qualification, "import_native_capture", fail_import)
    report = service.authorize_and_run(request)
    assert report.state is OperationState.UNKNOWN_EFFECT
    assert len(adapter.calls) == 1
    assert enabled_core.read_session_artifact(session_id, report.artifact_ids[0]) == stream
    assert enabled_core.list_records(session_id, "operations")[0].state is OperationState.UNKNOWN_EFFECT
