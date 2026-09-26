from __future__ import annotations

from datetime import timedelta
import fcntl
import os
from pathlib import Path
import shlex
import subprocess

import pytest

from m1lab.core.models import CommandKind, JobCreate, OwnerCommand, SessionCreate, utc_now


@pytest.fixture
def maintenance_check(core, tmp_path):
    """Run the real check branch without root or host service/account changes."""
    source = Path(__file__).resolve().parents[2] / "scripts" / "release.sh"
    script = source.read_text(encoding="utf-8")
    root_guard = '[[ ${EUID} -eq 0 ]] || { echo "run this command with sudo" >&2; exit 1; }'
    assert script.count(root_guard) == 1
    assert script.count("STATE_ROOT=/var/lib/m1-power-lab") == 1
    assert script.count("HELPER_STATE=/var/lib/m1-power-lab-helper") == 1
    script = script.replace(root_guard, ": # Root requirement bypassed in isolated test copy")
    script = script.replace(
        "STATE_ROOT=/var/lib/m1-power-lab",
        f"STATE_ROOT={shlex.quote(str(core.journal.paths.root))}",
    )
    helper_state = tmp_path / "helper-state"
    script = script.replace(
        "HELPER_STATE=/var/lib/m1-power-lab-helper",
        f"HELPER_STATE={shlex.quote(str(helper_state))}",
    )
    test_script = tmp_path / "release.sh"
    test_script.write_text(script, encoding="utf-8")
    # Avoid the lock-creation ownership branch; exercise the real flock call.
    (core.journal.paths.root / "coordinator.lock").touch()
    helper_state.mkdir()
    (helper_state / "owner.lock").touch()
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    for name, status in {"id": 0, "install": 0}.items():
        command = mock_bin / name
        command.write_text(f"#!/bin/sh\nexit {status}\n", encoding="utf-8")
        command.chmod(0o755)
    systemctl = mock_bin / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        "if [ \"$3\" = m1-power-lab-helper.service ]; then\n"
        "  if [ \"${MOCK_HELPER_ACTIVE:-0}\" = 1 ]; then exit 0; fi\n"
        "  if [ \"${MOCK_HELPER_ACTIVE_AFTER_LOCK:-0}\" = 1 ]; then\n"
        "    if [ -e \"$MOCK_HELPER_QUERY_MARKER\" ]; then exit 0; fi\n"
        "    touch \"$MOCK_HELPER_QUERY_MARKER\"\n"
        "  fi\n"
        "fi\n"
        "exit 3\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    def check(*, helper_active=False, helper_after_lock=False):
        marker = tmp_path / "helper-query-marker"
        marker.unlink(missing_ok=True)
        return subprocess.run(
            ["bash", str(test_script), "check"],
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ['PATH']}",
                "MOCK_HELPER_ACTIVE": "1" if helper_active else "0",
                "MOCK_HELPER_ACTIVE_AFTER_LOCK": "1" if helper_after_lock else "0",
                "MOCK_HELPER_QUERY_MARKER": str(marker),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    check.helper_state = helper_state
    return check


def test_maintenance_refuses_active_helper_before_or_after_lock(maintenance_check):
    active = maintenance_check(helper_active=True)
    assert active.returncode != 0
    assert "m1-power-lab-helper.service is active" in active.stderr

    raced = maintenance_check(helper_after_lock=True)
    assert raced.returncode != 0
    assert "m1-power-lab-helper.service became active" in raced.stderr


def test_maintenance_holds_helper_owner_lock_and_preserves_deny_history(maintenance_check):
    lock_path = maintenance_check.helper_state / "owner.lock"
    deny_path = maintenance_check.helper_state / "owner.lock.deny"
    deny_path.write_bytes(b"existing-deny-history\n")
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = maintenance_check()
        assert blocked.returncode != 0
        assert "helper owner lock is held" in blocked.stderr
        fcntl.flock(stream, fcntl.LOCK_UN)

    allowed = maintenance_check()
    assert allowed.returncode == 0, allowed.stderr
    assert "clear for maintenance" in allowed.stdout
    assert deny_path.read_bytes() == b"existing-deny-history\n"


def test_maintenance_refuses_helper_state_symlink(maintenance_check, tmp_path):
    helper_state = maintenance_check.helper_state
    (helper_state / "owner.lock").unlink()
    helper_state.rmdir()
    target = tmp_path / "alternate-helper-state"
    target.mkdir()
    helper_state.symlink_to(target, target_is_directory=True)

    refused = maintenance_check()

    assert refused.returncode != 0
    assert "helper state path must not be a symbolic link" in refused.stderr


def test_maintenance_refuses_fifo_at_helper_owner_lock(maintenance_check):
    lock_path = maintenance_check.helper_state / "owner.lock"
    lock_path.unlink()
    os.mkfifo(lock_path)

    refused = maintenance_check()

    assert refused.returncode != 0
    assert "helper owner lock path must be a regular file" in refused.stderr


@pytest.mark.parametrize("job_state", ["admitted", "running", "unknown"])
def test_maintenance_requires_settled_jobs_and_resolved_usage(core, maintenance_check, job_state):
    session = core.create_session(
        SessionCreate(objective="Maintenance regression", owner="owner", host_identity="host")
    )

    def command(kind):
        current = core.session(session.id)
        core.submit(
            OwnerCommand(
                session_id=current.id,
                owner=current.owner,
                expected_revision=current.revision,
                kind=kind,
                payload={},
            )
        )

    command(CommandKind.START)
    deadline = utc_now() + timedelta(minutes=5)
    job = core.create_job(
        JobCreate(
            session_id=session.id,
            kind="chat",
            lease_expires_at=deadline,
            deadline_at=deadline,
        )
    )
    if job_state == "running":
        core.update_job(job.id, state="running")
    elif job_state == "unknown":
        core.mark_job_unknown(job.id, reason="startup response uncertain", result={})
    command(CommandKind.PAUSE)

    blocked = maintenance_check()
    assert blocked.returncode != 0
    blocker = "uncertain_usage=1" if job_state == "unknown" else "unresolved_jobs=1"
    assert blocker in blocked.stderr

    if job_state == "unknown":
        core.resolve_usage_uncertainty(
            session.id,
            upper_bound_tokens=0,
            evidence="Test trace establishes failure before model invocation",
        )
        assert core.job(job.id).state == "unknown"
        allowed = maintenance_check()
        assert allowed.returncode == 0, allowed.stderr
        assert "clear for maintenance" in allowed.stdout
        assert core.job(job.id).state == "unknown"


@pytest.mark.parametrize(
    ("setup_sql", "blocker"),
    [
        (
            "INSERT INTO reservations VALUES "
            "('reservation','session','test',1,1,'2999-01-01T00:00:00+00:00',"
            "'2026-01-01T00:00:00+00:00',NULL)",
            "active_reservations=1",
        ),
        (
            "INSERT INTO active_segments(session_id,boot_id,started_utc,started_monotonic) "
            "VALUES ('session','boot','2026-01-01T00:00:00+00:00',0)",
            "open_active_segments=1",
        ),
        *[
            (
                "INSERT INTO operations "
                "(id,session_id,procedure_id,procedure_revision,procedure_digest,review_id,"
                "target_snapshot_id,boot_epoch,adapter_mode,mutates_target,state,"
                "envelope_json,result_json,created_at) VALUES "
                f"('operation','session','procedure',1,'digest','review','target','boot',"
                f"'replay',0,'{state}','{{}}','{{}}','2026-01-01T00:00:00+00:00')",
                "unresolved_operations=1",
            )
            for state in ("intent", "dispatched", "unknown_effect")
        ],
    ],
)
def test_maintenance_keeps_other_durable_guards(core, maintenance_check, setup_sql, blocker):
    # Populate one guard at a time without requiring a hardware/runtime execution.
    with core.journal.transaction() as tx:
        tx.execute(setup_sql)
    result = maintenance_check()
    assert result.returncode != 0
    assert blocker in result.stderr
