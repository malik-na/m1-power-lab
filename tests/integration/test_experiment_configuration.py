"""Configuration drift at the real coordinator/executor seam, using replay."""

from dataclasses import replace

import pytest

from m1lab.adapters import InspectRegister, ReplayHardwareAdapter, ReplayStep
from m1lab.cli import _record_replay_review
from m1lab.core.models import (
    CommandKind, DispatchRequest, OperationState, OwnerCommand, ProcedureDraft,
    SessionCreate, TargetMode, TypedOperation,
)
from m1lab.experiment.service import ExperimentService


class ChangingConfigurationReplay(ReplayHardwareAdapter):
    def __init__(self, *, change_after_first):
        operation = InspectRegister(0x1000, 4)
        super().__init__([ReplayStep(operation, values={"value": 1})] * 2)
        self.configuration = "a" * 64
        self.change_after_first = change_after_first

    def inspect(self):
        return replace(super().inspect(), configuration_digest=self.configuration)

    def execute(self, dispatch):
        result = super().execute(dispatch)
        if self.change_after_first:
            self.configuration = "b" * 64
        return result


@pytest.mark.parametrize("when", ["before-dispatch", "after-first-result"])
def test_configuration_drift_blocks_further_execution_and_preserves_evidence(core, when):
    session = core.create_session(SessionCreate(
        objective="Synthetic configuration drift qualification", owner="owner", host_identity="host",
    ))
    core.submit(OwnerCommand(
        session_id=session.id, owner=session.owner, kind=CommandKind.START,
        expected_revision=session.revision, payload={},
    ))
    adapter = ChangingConfigurationReplay(change_after_first=when == "after-first-result")
    service = ExperimentService(core, adapter)
    target = service.inspect_and_record(session.id)
    assert target.configuration_digest == adapter.configuration
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session.id, title="Read two synthetic registers",
        operations=[TypedOperation(
            kind="inspect_register", parameters={"address": 0x1000, "width_bytes": 4},
            mutates_target=False, timeout_seconds=5,
        )] * 2,
        prerequisites={"inspect_register"},
    ))
    _record_replay_review(core, procedure, scope="synthetic test only", concerns=[])
    authorization = core.authorize_operation(DispatchRequest(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, target_snapshot_id=target.id,
        adapter_mode=TargetMode.REPLAY, estimated_active_seconds=10,
    ))
    assert authorization.eligibility.eligible
    if when == "before-dispatch":
        adapter.configuration = "b" * 64

    report = service.run_authorization(authorization)

    assert "configuration" in report.message
    if when == "before-dispatch":
        assert report.state is OperationState.NO_EFFECT
        assert adapter.remaining_steps == 2
        assert report.artifact_ids == []
    else:
        assert report.state is OperationState.UNKNOWN_EFFECT
        assert adapter.remaining_steps == 1
        assert len(report.steps) == 1
        assert report.artifact_ids
        assert all(core.session_artifact(session.id, aid).available for aid in report.artifact_ids)
    stored = core.list_records(session.id, "operations")
    assert len(stored) == 1
    assert stored[0].state is report.state
