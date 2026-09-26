from __future__ import annotations

import asyncio

from m1lab.application import CoordinatorFacade
from m1lab.cli import _replay_demo
from m1lab.core.models import OperationState, SessionCreate, SessionPhase
from m1lab.science import ScientificRecordStore
from m1lab.web.facade import Owner


def test_complete_replay_loop_is_consistent_across_cli_core_and_web(core):
    session = core.create_session(
        SessionCreate(
            objective="Demonstrate the host replay investigation loop",
            owner="owner",
            host_identity="thinkpad",
        )
    )

    result = _replay_demo(core, session.id)

    assert result["qualification"] == (
        "host replay only; cannot establish behavior on a physical M1 target"
    )
    assert result["final_phase"] == SessionPhase.INTERPRETING
    assert result["read_only"]["state"] == OperationState.SUCCEEDED
    assert result["mutating"]["state"] == OperationState.SUCCEEDED

    procedures = core.list_records(session.id, "procedures")
    operations = core.list_records(session.id, "operations")
    assert {item.procedure_id for item in procedures} == {
        result["read_only"]["procedure_id"],
        result["mutating"]["procedure_id"],
    }
    assert {item.id for item in operations} == {
        result["read_only"]["operation_id"],
        result["mutating"]["operation_id"],
    }
    assert {item.mutates_target for item in operations} == {False, True}
    assert all(item.state is OperationState.SUCCEEDED for item in operations)
    assert len(core.list_records(session.id, "approvals")) == 1

    scientific = result["scientific_evidence"]
    assert scientific["limitation"] == (
        "Replay evidence validates the host workflow only and cannot establish M1 behavior."
    )
    assert core.session_artifact(session.id, scientific["artifact_id"]).available
    science_record = next(
        item
        for item in ScientificRecordStore(core).list(session.id)
        if item.record.id == scientific["record_id"]
    )
    assert science_record.record.statement.startswith("Host replay only:")
    replay_artifacts = [
        item
        for item in core.artifacts(session.id)
        if item.provenance.get("operation_id")
    ]
    assert replay_artifacts
    assert all(item.provenance.get("evidence_scope") == "host_only" for item in replay_artifacts)

    facade = CoordinatorFacade(core, session.id)
    view = asyncio.run(
        facade.get_view(
            "overview",
            Owner(login="owner", display_name="Owner", source="local"),
        )
    )
    assert view["session"]["state"] == result["final_phase"]
    assert {item["procedure_id"] for item in view["experiments"]} == {
        result["read_only"]["procedure_id"],
        result["mutating"]["procedure_id"],
    }
    assert {item["operation_id"] for item in view["experiments"]} == {
        result["read_only"]["operation_id"],
        result["mutating"]["operation_id"],
    }
    assert scientific["record_id"] in {item["id"] for item in view["evidence"]}

    event_kinds = [event.kind for event in core.events(session.id)]
    assert event_kinds.count("operation.intent_recorded") == 2
    assert event_kinds.count("operation.dispatched") == 2
    assert event_kinds.count("operation.finished") == 2
