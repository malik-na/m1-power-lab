from __future__ import annotations

import importlib.util
from datetime import timedelta
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from m1lab.cli import _backup_bundle
import m1lab.core.journal as journal_module
from m1lab.core.journal import JOURNAL_DISK_RESERVE_BYTES, LARGE_ARTIFACT_DISK_RESERVE_BYTES
from m1lab.core.errors import NotFoundError, ValidationError
from m1lab.core.models import (
    CommandKind,
    DispatchRequest,
    JobCreate,
    OwnerCommand,
    ProcedureDraft,
    ReviewDisposition,
    ReviewRecord,
    SessionCreate,
    TargetMode,
    TargetSnapshot,
    TypedOperation,
    utc_now,
)
from m1lab.core.coordinator import CoreApp
from m1lab.paths import AppPaths


def new_session(core, owner="owner"):
    return core.create_session(
        SessionCreate(
            objective="Validate immutable artifact recovery",
            owner=owner,
            host_identity="thinkpad",
        )
    )


def load_restore_module():
    script = Path(__file__).parents[2] / "scripts" / "restore-backup.py"
    spec = importlib.util.spec_from_file_location("m1lab_restore_backup", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deduplicated_artifact_has_distinct_session_publications(core):
    first = new_session(core, "owner-a")
    second = new_session(core, "owner-b")
    first_record = core.publish_artifact(
        b"same immutable evidence",
        media_type="text/plain",
        provenance={"session_id": first.id, "record_type": "trace", "source": "a"},
    )
    second_record = core.publish_artifact(
        b"same immutable evidence",
        media_type="text/plain",
        provenance={"session_id": second.id, "record_type": "trace", "source": "b"},
    )

    assert first_record.id == second_record.id
    assert first_record.publication_id != second_record.publication_id
    assert core.read_session_artifact(first.id, first_record.id) == b"same immutable evidence"
    assert core.read_session_artifact(second.id, second_record.id) == b"same immutable evidence"
    unrelated = new_session(core, "owner-c")
    with pytest.raises(NotFoundError, match="not published in session"):
        core.read_artifact(unrelated.id, first_record.id)
    with pytest.raises(NotFoundError, match="not published in session"):
        core.read_session_artifact(first.id, "artifact_unrelated")


@pytest.mark.parametrize("corruption", ["missing", "truncated", "same_size"])
def test_reconciliation_detects_artifact_damage_and_recovers_restored_content(
    core, corruption
):
    session = new_session(core)
    artifact = core.publish_artifact(
        b"immutable artifact payload",
        media_type="text/plain",
        provenance={"session_id": session.id, "record_type": "trace"},
    )
    path = core.journal.paths.artifacts / artifact.relative_path
    original = path.read_bytes()
    if corruption == "missing":
        path.unlink()
    elif corruption == "truncated":
        path.write_bytes(original[:-4])
    else:
        path.write_bytes(b"X" * len(original))

    with pytest.raises(ValidationError, match="unavailable"):
        core.read_session_artifact(session.id, artifact.id)

    report = core.reconcile()

    assert artifact.id in report.missing_artifact_ids
    assert core.artifact(artifact.id).available is False
    with pytest.raises(ValidationError, match="unavailable"):
        core.read_session_artifact(session.id, artifact.id)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(original)
    restored = core.reconcile()
    assert artifact.id not in restored.missing_artifact_ids
    assert core.artifact(artifact.id).available is True
    assert core.read_session_artifact(session.id, artifact.id) == original


def test_reconciliation_reports_orphan_artifact_files(core):
    orphan = core.journal.paths.artifacts / "ff" / "orphan"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"not in metadata")

    report = core.reconcile()

    assert "ff/orphan" in report.orphan_artifact_paths


def test_backup_restore_preserves_database_artifacts_and_provenance(core, tmp_path):
    session = new_session(core)
    artifact = core.publish_artifact(
        b"evidence survives restore",
        media_type="text/plain",
        provenance={"session_id": session.id, "record_type": "trace", "origin": "test"},
    )
    bundle = tmp_path / "backup.zip"

    result = _backup_bundle(core, bundle)

    assert result["artifacts"] == 1
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {
            "m1lab.sqlite3",
            "manifest.json",
            f"artifacts/{artifact.relative_path}",
        }
    restored_root = tmp_path / "restored"
    load_restore_module().restore(bundle, restored_root)
    restored = CoreApp.open(AppPaths(restored_root))
    try:
        assert restored.read_session_artifact(session.id, artifact.id) == b"evidence survives restore"
        restored_publication = restored.artifacts(session.id)[0]
        assert restored_publication.provenance["origin"] == "test"
        assert restored.journal.one("PRAGMA quick_check")[0] == "ok"
    finally:
        restored.close()


def test_backup_fails_instead_of_omitting_unavailable_referenced_artifact(core, tmp_path):
    session = new_session(core)
    artifact = core.publish_artifact(
        b"must not silently disappear",
        provenance={"session_id": session.id, "record_type": "trace"},
    )
    (core.journal.paths.artifacts / artifact.relative_path).unlink()
    core.reconcile()

    with pytest.raises(ValueError, match="unavailable|missing|invalid"):
        _backup_bundle(core, tmp_path / "incomplete.zip")
    assert not (tmp_path / "incomplete.zip").exists()


def test_backup_fails_on_same_size_corruption_before_reconciliation(core, tmp_path):
    session = new_session(core)
    artifact = core.publish_artifact(
        b"corrupt but still marked available",
        provenance={"session_id": session.id, "record_type": "trace"},
    )
    path = core.journal.paths.artifacts / artifact.relative_path
    path.write_bytes(b"X" * artifact.size_bytes)

    with pytest.raises(ValueError, match="integrity validation"):
        _backup_bundle(core, tmp_path / "corrupted.zip")
    assert not (tmp_path / "corrupted.zip").exists()


def test_restore_rejects_manifest_database_mismatch_without_replacing_current_data(
    core, tmp_path
):
    session = new_session(core)
    artifact = core.publish_artifact(
        b"verified evidence",
        provenance={"session_id": session.id, "record_type": "trace"},
    )
    good_bundle = tmp_path / "good.zip"
    _backup_bundle(core, good_bundle)
    bad_bundle = tmp_path / "bad.zip"
    with zipfile.ZipFile(good_bundle) as source, zipfile.ZipFile(bad_bundle, "w") as target:
        manifest = json.loads(source.read("manifest.json"))
        manifest["artifacts"][0]["size_bytes"] += 1
        target.writestr("manifest.json", json.dumps(manifest))
        for name in source.namelist():
            if name != "manifest.json":
                target.writestr(name, source.read(name))

    restored_root = tmp_path / "existing"
    existing = CoreApp.open(AppPaths(restored_root))
    existing_session = new_session(existing, "keep-me")
    existing_artifact = existing.publish_artifact(
        b"pre-existing data remains", provenance={"session_id": existing_session.id}
    )
    existing.close()
    with pytest.raises(SystemExit, match="metadata|manifest|wrong (archive )?size"):
        load_restore_module().restore(bad_bundle, restored_root)
    existing = CoreApp.open(AppPaths(restored_root))
    try:
        assert existing.session(existing_session.id).owner == "keep-me"
        assert existing.read_session_artifact(
            existing_session.id, existing_artifact.id
        ) == b"pre-existing data remains"
        with pytest.raises(NotFoundError):
            existing.session(session.id)
    finally:
        existing.close()


def test_new_artifact_publication_preserves_journal_disk_reserve(core, monkeypatch):
    session = new_session(core)
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(total=10_000, used=9_999, free=1),
    )

    with pytest.raises(ValidationError, match="disk reserve"):
        core.publish_artifact(
            b"x",
            provenance={"session_id": session.id, "record_type": "capture"},
        )
    assert core.artifacts(session.id) == []


def test_low_disk_closes_new_job_admission(core, monkeypatch):
    session = new_session(core)
    started = core.submit(
        OwnerCommand(
            session_id=session.id,
            owner=session.owner,
            kind=CommandKind.START,
            expected_revision=session.revision,
        )
    )
    assert started.status.value == "applied"
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(
            total=10_000, used=10_000, free=JOURNAL_DISK_RESERVE_BYTES - 1
        ),
    )
    now = utc_now()
    with pytest.raises(ValidationError, match="disk reserve"):
        core.create_job(
            JobCreate(
                session_id=session.id,
                kind="investigate",
                lease_expires_at=now + timedelta(minutes=1),
                deadline_at=now + timedelta(minutes=2),
            )
        )
    assert core.list_records(session.id, "jobs") == []


def test_large_artifact_requires_cleanup_reserve_after_capture(core, monkeypatch):
    session = new_session(core)
    payload = b"x" * (1024 * 1024)
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(
            total=10_000,
            used=10_000,
            free=LARGE_ARTIFACT_DISK_RESERVE_BYTES + len(payload) - 1,
        ),
    )
    with pytest.raises(ValidationError, match="disk reserve"):
        core.publish_artifact(
            payload,
            provenance={"session_id": session.id, "record_type": "large_capture"},
        )
    assert core.artifacts(session.id) == []


def test_disk_pressure_blocks_large_capture_before_dispatch(core, monkeypatch):
    session = new_session(core)
    core.submit(
        OwnerCommand(
            session_id=session.id,
            owner=session.owner,
            kind=CommandKind.START,
            expected_revision=session.revision,
        )
    )
    target = core.record_target(
        TargetSnapshot(
            session_id=session.id,
            identity="replay-m1",
            boot_epoch="boot-1",
            mode=TargetMode.REPLAY,
            configuration_digest="config-1",
            capabilities={"capture_memory"},
        )
    )
    procedure = core.register_procedure(
        ProcedureDraft(
            session_id=session.id,
            title="Large bounded capture",
            operations=[
                TypedOperation(
                    kind="capture_memory",
                    parameters={"address": 4096, "length": 1024 * 1024},
                    mutates_target=False,
                    timeout_seconds=10,
                )
            ],
            prerequisites={"capture_memory"},
        )
    )
    now = utc_now()
    reviewer = core.create_job(
        JobCreate(
            session_id=session.id,
            kind="review",
            evidence_manifest={
                "review_target": {
                    "procedure_id": procedure.procedure_id,
                    "procedure_revision": procedure.revision,
                    "procedure_digest": procedure.digest,
                }
            },
            lease_expires_at=now + timedelta(minutes=1),
            deadline_at=now + timedelta(minutes=2),
        )
    )
    core.update_job(reviewer.id, state="running")
    core.update_job(reviewer.id, state="completed")
    core.record_review(
        ReviewRecord(
            session_id=session.id,
            procedure_id=procedure.procedure_id,
            procedure_revision=procedure.revision,
            procedure_digest=procedure.digest,
            reviewer_job_id=reviewer.id,
            disposition=ReviewDisposition.ACCEPTED,
        )
    )
    estimate = 1024 * 1024 + 64 * 1024
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(
            total=10_000,
            used=10_000,
            free=LARGE_ARTIFACT_DISK_RESERVE_BYTES + estimate,
        ),
    )
    authorization = core.authorize_operation(
        DispatchRequest(
            session_id=session.id,
            procedure_id=procedure.procedure_id,
            procedure_revision=procedure.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
        )
    )
    assert authorization.eligibility.eligible
    assert authorization.envelope is not None
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(
            total=10_000, used=10_000, free=JOURNAL_DISK_RESERVE_BYTES - 1
        ),
    )

    with pytest.raises(ValidationError, match="disk reserve"):
        core.mark_dispatched(authorization.envelope)
    assert core.list_records(session.id, "operations")[0].state.value == "intent"
