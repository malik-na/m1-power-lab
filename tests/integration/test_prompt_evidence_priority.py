"""Current selected evidence survives a crowded investigation manifest."""

from __future__ import annotations

from m1lab.core.models import SessionCreate
from m1lab.investigator.models import EvidenceExcerpt, InvestigationRequest
from m1lab.investigator.prompts import build_manifest, build_prompt


def _session(core):
    return core.create_session(SessionCreate(
        objective="Inspect the selected launch",
        owner="test-owner",
        host_identity="test-host",
    ))


def _request(session_id, tmp_path, **changes):
    return InvestigationRequest(
        session_id=session_id,
        instruction="Assess the exact selected launch and operator observation.",
        cwd=tmp_path.resolve(),
        model="synthetic-model",
        **changes,
    )


def test_explicit_launch_and_last_operator_evidence_precede_automatic_history(core, tmp_path):
    session = _session(core)
    launch_text = "EXACT_LAUNCH_CONFIGURATION=" + "L" * 14_000
    launch = core.publish_artifact(
        launch_text.encode(),
        media_type="application/vnd.m1lab.native-launch-manifest+json",
        provenance={"session_id": session.id, "record_type": "native_launch"},
    )
    # Four 16 KiB automatic excerpts would exhaust the shared excerpt budget
    # before a later-sorted selected artifact in the old implementation.
    junk = []
    index = 0
    while len(junk) < 5:
        artifact = core.publish_artifact(
            (f"old runtime event {index}:" + "J" * 16_000).encode(),
            media_type="application/vnd.m1lab.runtime-event+json",
            provenance={"session_id": session.id, "record_type": "runtime_event"},
        )
        if artifact.id < launch.id:
            junk.append(artifact)
        index += 1
        assert index < 100

    evidence = [
        EvidenceExcerpt(label=f"operator-{number}", content=f"operator {number}: " + "E" * 16_000)
        for number in range(3)
    ]
    evidence_artifacts = [
        core.publish_artifact(
            item.content.encode(), media_type="text/plain",
            provenance={"session_id": session.id, "kind": "investigation_evidence"},
        )
        for item in evidence
    ]
    request = _request(session.id, tmp_path, artifact_ids=[launch.id], evidence=evidence)

    manifest = build_manifest(core, request, evidence_artifacts)
    prompt = build_prompt(request, manifest)

    assert manifest["artifacts"][0]["id"] == launch.id
    assert [item["artifact_id"] for item in manifest["artifact_excerpts"][:4]] == [
        launch.id, *(item.id for item in evidence_artifacts)
    ]
    assert "EXACT_LAUNCH_CONFIGURATION=" in prompt
    assert "operator 2:" in prompt
    assert evidence_artifacts[-1].id in prompt


def test_exact_review_procedure_survives_manifest_compaction(core, tmp_path):
    session = _session(core)

    class Procedure:
        def __init__(self, number):
            self.procedure_id = f"procedure-{number}"
            self.revision = 1
            self.digest = f"digest-{number}"
            self.number = number

        def model_dump(self, mode):
            return {
                "procedure_id": self.procedure_id,
                "revision": self.revision,
                "digest": self.digest,
                "operations": [{"kind": "exact-review-operation", "parameters": [self.number]}],
                "notes": "P" * 7_000,
            }

    procedures = [Procedure(index) for index in range(30)]
    target = procedures[12]

    class CoreWithProcedureHistory:
        def __init__(self, underlying):
            self.underlying = underlying

        def __getattr__(self, name):
            return getattr(self.underlying, name)

        def list_records(self, session_id, kind):
            if kind == "procedures":
                return procedures
            return self.underlying.list_records(session_id, kind)

    request = _request(
        session.id, tmp_path, kind="review", review_procedure_id=target.procedure_id,
    )
    manifest = build_manifest(CoreWithProcedureHistory(core), request, [])
    prompt = build_prompt(request, manifest)

    assert manifest["bounds"]["manifest_truncated"] is True
    assert manifest["review_target"]["procedure_id"] == target.procedure_id
    assert manifest["review_procedure"]["operations"][0]["kind"] == "exact-review-operation"
    assert '"review_procedure"' in prompt
