"""Coordinator/executor/Unix IPC together, with an explicitly synthetic target.

The test-only replay subclass carries calls over IPC without enabling a live
adapter in ExperimentService. No device, model, or installed session is used.
"""

from dataclasses import replace

import pytest

from m1lab.adapters import HardwareError, ReplayHardwareAdapter
from m1lab.cli import _record_replay_review
from m1lab.core import (
    CommandKind, ConflictError, DispatchRequest, OperationState, OwnerCommand,
    ProcedureDraft, SessionCreate, TargetMode, TypedOperation,
)
from m1lab.experiment.service import ExperimentError, ExperimentService

from test_hardware_helper import helper  # Real socket fixture; synthetic backend only.


class SocketReplayFixture(ReplayHardwareAdapter):
    def __init__(self, client):
        super().__init__()
        self.client = client

    def inspect(self):
        return self.client.inspect()

    def execute(self, dispatch):
        return self.client.execute(dispatch)


def _prepare(core, backend, client):
    backend.snapshot = replace(backend.snapshot, adapter="replay", mode="replay")
    session = core.create_session(SessionCreate(
        objective="Synthetic coordinator through helper IPC acceptance",
        owner="owner", host_identity="synthetic-host",
    ))
    core.submit(OwnerCommand(
        session_id=session.id, owner=session.owner, kind=CommandKind.START,
        expected_revision=session.revision,
    ))
    service = ExperimentService(core, SocketReplayFixture(client))
    target = service.inspect_and_record(session.id)
    procedure = core.register_procedure(ProcedureDraft(
        session_id=session.id, title="Two synthetic register observations",
        operations=[TypedOperation(
            kind="inspect_register", parameters={"address": 0x1000, "width_bytes": 4},
            timeout_seconds=5,
        )] * 2,
        prerequisites={"inspect_register"},
    ))
    review = _record_replay_review(core, procedure, scope="Synthetic IPC fixture only", concerns=[])
    authorization = core.authorize_operation(DispatchRequest(
        session_id=session.id, procedure_id=procedure.procedure_id,
        procedure_revision=procedure.revision, target_snapshot_id=target.id,
        adapter_mode=TargetMode.REPLAY, estimated_active_seconds=10,
    ))
    assert authorization.eligibility.eligible
    return session, service, authorization, review


@pytest.mark.parametrize("disconnect", [False, True], ids=["complete", "ambiguous"])
def test_coordinator_records_helper_outcome_and_never_replays_it(core, helper, disconnect):
    _, backend, client, _, _ = helper
    session, service, authorization, review = _prepare(core, backend, client)
    backend.fail_after_entry = disconnect

    report = service.run_authorization(authorization)

    expected = OperationState.UNKNOWN_EFFECT if disconnect else OperationState.SUCCEEDED
    assert report.state is expected
    assert len(backend.calls) == (1 if disconnect else 2)
    assert report.artifact_ids
    for artifact_id in report.artifact_ids:
        artifact = core.session_artifact(session.id, artifact_id)
        assert artifact.available
        assert artifact.provenance["physical_m1_claims"] == "not_supported"
    stored = core.list_records(session.id, "operations")
    assert len(stored) == 1 and stored[0].state is expected
    dispatch = backend.calls[0]
    assert dispatch.coordinator_operation_id == report.operation_id
    assert dispatch.review_id == review.id
    assert dispatch.procedure_digest == authorization.envelope.procedure_digest
    assert dispatch.configuration_digest == authorization.envelope.configuration_digest
    assert dispatch.operation_index == 0
    before = list(backend.calls)

    # Both the coordinator and the helper refuse replay after an uncertain or
    # completed outcome. A transport reconnect does not provide new authority.
    with pytest.raises(ConflictError):
        service.run_authorization(authorization)
    backend.fail_after_entry = False
    with pytest.raises(HardwareError, match="unknown"):
        client.execute(dispatch)
    assert backend.calls == before


def test_changed_authorized_envelope_never_reaches_helper_execution(core, helper):
    _, backend, client, _, _ = helper
    session, service, authorization, _ = _prepare(core, backend, client)
    forged = authorization.envelope.model_copy(update={"review_id": "different-review"})

    with pytest.raises(ConflictError, match="durable intent"):
        service.run(forged)

    assert backend.calls == []
    assert core.list_records(session.id, "operations")[0].state is OperationState.INTENT


def test_real_helper_client_does_not_enable_live_experiment_service(core, helper):
    _, backend, client, _, _ = helper
    with pytest.raises(ExperimentError, match="only the deterministic replay adapter"):
        ExperimentService(core, client)
    assert backend.calls == []
