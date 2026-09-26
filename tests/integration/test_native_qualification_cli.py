"""Explicit operator CLI wiring for the native helper, using no physical device."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path

import pytest

from m1lab import cli
from m1lab.adapters.hardware import HardwareCapability, TargetSnapshot as HelperSnapshot
from m1lab.core import CommandKind, OwnerCommand, ProcedureDraft, SessionCreate, TypedOperation
from m1lab.core.models import utc_now


class SyntheticHelper:
    calls: list[Path] = []

    def __init__(self, socket_path: Path):
        self.calls.append(socket_path)

    def inspect(self) -> HelperSnapshot:
        return HelperSnapshot(
            adapter="synthetic-cli-helper", available=True, qualified=False,
            mode="proxy", target_id="synthetic-target", boot_epoch="synthetic-boot",
            configuration_digest="d" * 64,
            capabilities=(HardwareCapability("run_native_candidate", 1, True, 1_048_576),),
            observed_at=utc_now(), message="synthetic fixture",
        )

    def execute(self, _dispatch):
        raise AssertionError("unreviewed CLI procedure must not dispatch")


@pytest.fixture
def cli_session(core, monkeypatch):
    session = core.create_session(SessionCreate(
        objective="CLI native fixture", owner="test-owner", host_identity="synthetic-host",
        target_identity="synthetic-target",
    ))
    monkeypatch.setenv("M1LAB_DATA_DIR", str(core.journal.paths.root))
    monkeypatch.setattr(cli, "HelperHardwareAdapter", SyntheticHelper)
    SyntheticHelper.calls = []
    return session


def test_native_commands_require_explicit_session_before_opening_core(cli_session, capsys):
    for action in ("native-inspect", "native-run"):
        arguments = ["--helper-socket", "/tmp/synthetic-helper.sock"]
        if action == "native-run":
            arguments += ["--procedure-id", "procedure-1", "--procedure-revision", "1",
                          "--target-snapshot", "snapshot-1"]
        with pytest.raises(SystemExit) as error:
            cli.main([action, *arguments])
        assert error.value.code == 2
        assert "explicit --session" in capsys.readouterr().err
    assert SyntheticHelper.calls == []


def test_native_inspect_records_unqualified_proxy_snapshot(core, cli_session, capsys):
    cli.main(["--json", "--session", cli_session.id, "native-inspect",
              "--helper-socket", "/tmp/synthetic-helper.sock"])

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "proxy"
    assert output["recovery"]["qualified"] is False
    assert output["capabilities"] == ["run_native_candidate"]
    assert core.snapshot(cli_session.id).latest_target.id == output["id"]
    assert SyntheticHelper.calls == [Path("/tmp/synthetic-helper.sock")]


def test_native_run_enables_gate_but_refuses_missing_review(core, cli_session, monkeypatch, capsys):
    cli.main(["--json", "--session", cli_session.id, "native-inspect",
              "--helper-socket", "/tmp/synthetic-helper.sock"])
    target_id = json.loads(capsys.readouterr().out)["id"]
    core.submit(OwnerCommand(
        session_id=cli_session.id, owner=cli_session.owner,
        expected_revision=core.session(cli_session.id).revision,
        kind=CommandKind.START, payload={},
    ))
    digests = [core.publish_artifact(
        content, provenance={"session_id": cli_session.id, "role": "synthetic-test"},
    ).sha256 for content in (b"payload", b"image", b"launch")]
    procedure = core.register_procedure(ProcedureDraft(
        session_id=cli_session.id, title="Synthetic native qualification",
        operations=[TypedOperation(
            kind="run_native_candidate", mutates_target=True, timeout_seconds=30,
            parameters=dict(zip(
                ("payload_sha256", "image_manifest_sha256", "launch_manifest_sha256"), digests,
            )),
        )],
        prerequisites={"run_native_candidate"}, artifact_digests=set(digests),
        physical_attendance="required",
    ))
    opened_with: list[bool] = []
    original_open = cli.CoreApp.open

    def tracked_open(*args, **kwargs):
        opened_with.append(kwargs.get("allow_native_qualification", False))
        return original_open(*args, **kwargs)

    monkeypatch.setattr(cli.CoreApp, "open", tracked_open)
    with pytest.raises(SystemExit) as error:
        cli.main(["--session", cli_session.id, "native-run",
                  "--helper-socket", "/tmp/synthetic-helper.sock",
                  "--procedure-id", procedure.procedure_id,
                  "--procedure-revision", str(procedure.revision),
                  "--target-snapshot", target_id])

    assert error.value.code == 2
    assert "exact procedure revision lacks an accepted review" in capsys.readouterr().err
    assert opened_with == [True]
    assert core.list_records(cli_session.id, "operations") == []


def test_native_run_requires_coordinator_lease(core, cli_session, monkeypatch, capsys):
    @contextmanager
    def denied_lease(_path):
        raise ValueError("another coordinator process owns this data directory")
        yield

    monkeypatch.setattr(cli, "_coordinator_lease", denied_lease)
    with pytest.raises(SystemExit) as error:
        cli.main(["--session", cli_session.id, "native-run",
                  "--helper-socket", "/tmp/synthetic-helper.sock",
                  "--procedure-id", "procedure-1", "--procedure-revision", "1",
                  "--target-snapshot", "snapshot-1"])
    assert error.value.code == 2
    assert "another coordinator process" in capsys.readouterr().err
    assert SyntheticHelper.calls == []
