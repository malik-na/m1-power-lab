"""The CLI can select immutable capture context beyond the automatic window."""

from __future__ import annotations

import pytest

from m1lab import cli
from m1lab.config import Settings
from m1lab.core.models import SessionCreate
from m1lab.investigator.prompts import build_manifest


def _session(core):
    return core.create_session(SessionCreate(
        objective="Inspect saved native capture context",
        owner="test-owner",
        host_identity="test-host",
    ))


def _settings(monkeypatch, core, tmp_path):
    monkeypatch.setenv("M1LAB_DATA_DIR", str(core.journal.paths.root))
    monkeypatch.setenv("M1LAB_CODEX_RUNTIME", "app-server")
    monkeypatch.setenv("M1LAB_WORKSPACE", str(tmp_path / "workspace"))
    return Settings.from_env()


def _args(session_id, *artifact_ids):
    command = ["--session", session_id, "investigate", "Inspect this capture"]
    for artifact_id in artifact_ids:
        command.extend(("--artifact-id", artifact_id))
    return cli.parser().parse_args(command)


def _capture(core, session_id, number):
    return core.publish_artifact(
        f'{{"sample":{number}}}'.encode(),
        media_type="application/vnd.m1lab.native-capture+json;version=1",
        provenance={"session_id": session_id, "record_type": "native_capture"},
    )


def test_selected_capture_beyond_automatic_window_reaches_investigation_context(
    core, tmp_path, monkeypatch,
):
    session = _session(core)
    settings = _settings(monkeypatch, core, tmp_path)
    captures = [_capture(core, session.id, index) for index in range(34)]
    target = captures[0]
    selected = captures[1]
    seen = []

    async def fake_run(core, request, settings):
        seen.append(request)
        return build_manifest(core, request, [])

    monkeypatch.setattr(cli, "_run_investigation", fake_run)
    automatic = cli._dispatch(_args(session.id), settings, core)
    manifest = cli._dispatch(_args(session.id, target.id, selected.id), settings, core)

    assert target.id not in {item["id"] for item in automatic["artifacts"]}
    assert seen[1].artifact_ids == [target.id, selected.id]
    assert target.id in {item["id"] for item in manifest["artifacts"]}
    assert selected.id in {item["id"] for item in manifest["artifacts"]}
    assert any(
        item["artifact_id"] == target.id and '"sample":0' in item["excerpt"]
        for item in manifest["artifact_excerpts"]
    )


def test_selected_capture_must_belong_to_session(core, tmp_path, monkeypatch):
    session = _session(core)
    other = _session(core)
    settings = _settings(monkeypatch, core, tmp_path)
    foreign = _capture(core, other.id, 1)

    async def fake_run(core, request, settings):
        return build_manifest(core, request, [])

    monkeypatch.setattr(cli, "_run_investigation", fake_run)
    with pytest.raises(ValueError, match="unknown or cross-session artifacts"):
        cli._dispatch(_args(session.id, foreign.id), settings, core)


def test_duplicate_artifact_selection_is_rejected(core, tmp_path, monkeypatch):
    session = _session(core)
    settings = _settings(monkeypatch, core, tmp_path)
    capture = _capture(core, session.id, 1)
    with pytest.raises(ValueError, match="artifact_ids must not contain duplicates"):
        cli._dispatch(_args(session.id, capture.id, capture.id), settings, core)
