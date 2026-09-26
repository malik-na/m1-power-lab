"""Synthetic real-socket checks for durable dispatch refusal; no devices."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import multiprocessing as mp
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time

import pytest

from m1lab.adapters.hardware import (
    HardwareCapability, HardwareDispatch, HardwareError, HardwareResult,
    HardwareResultStatus, InspectRegister, TargetSnapshot,
)
from m1lab.adapters.helper_server import (
    HelperHardwareAdapter, HelperOwnerError, HelperOwnerLock, HelperServer,
    close_exclusive_helper, start_exclusive_helper,
)


class Backend:
    def __init__(self, *, fail_after_entry=False):
        self.calls = []
        self.fail_after_entry = fail_after_entry

    def inspect(self):
        return TargetSnapshot(
            adapter="synthetic-test-only", available=True, qualified=True,
            mode="synthetic", target_id="synthetic-target", boot_epoch="synthetic-boot",
            configuration_digest="a" * 64,
            capabilities=(HardwareCapability("inspect_register", 1, False, 4),),
            observed_at=datetime.now(timezone.utc), message="Synthetic gate fixture only.",
        )

    def execute(self, dispatch):
        self.calls.append(dispatch)
        if self.fail_after_entry:
            raise OSError("synthetic backend failed after entry")
        now = datetime.now(timezone.utc)
        return HardwareResult(
            operation_id=dispatch.operation_id, status=HardwareResultStatus.COMPLETED,
            started_at=now, finished_at=now, boot_epoch="synthetic-boot",
            payload=b"\x01\x00\x00\x00",
        )


class CrashingBackend(Backend):
    def execute(self, dispatch):
        del dispatch
        os._exit(17)


def _crash_after_reservation_worker(root: str, ready) -> None:
    directory = Path(root)
    _owner, server = start_exclusive_helper(
        directory / "owner.lock", directory / "helper.sock", CrashingBackend,
    )
    ready.send("ready")
    ready.close()
    # serve_once reserves and fsyncs before entering CrashingBackend.execute.
    # The child exits without graceful server/guard/owner cleanup.
    server.serve_once()


def dispatch(operation_id="operation-1", coordinator_operation_id="coordinator-1", address=0x1000):
    return HardwareDispatch(
        operation_id=operation_id, coordinator_operation_id=coordinator_operation_id,
        session_id="session", target_identity="synthetic-target",
        target_snapshot_id="snapshot", configuration_digest="a" * 64,
        procedure_id="procedure", procedure_revision=1, review_id="review",
        approval_id=None, approval_scope=None, boot_epoch="synthetic-boot",
        procedure_digest="b" * 64, artifact_digests=(), operation_index=0,
        operation=InspectRegister(address, 4),
        deadline=datetime.now(timezone.utc) + timedelta(seconds=5),
    )


@contextmanager
def running_helper(root: Path, backend: Backend, *, guarded=True):
    socket_path = root / "helper.sock"
    if guarded:
        owner, server = start_exclusive_helper(root / "owner.lock", socket_path, lambda: backend)
    else:
        owner = None
        server = HelperServer(socket_path, backend)
        server.listen()
    stopped = Event()
    errors = []
    thread = Thread(
        target=server.serve_forever, args=(stopped,),
        kwargs={"poll_interval_seconds": 0.05, "on_error": errors.append}, daemon=True,
    )
    thread.start()
    try:
        yield HelperHardwareAdapter(socket_path), errors, server
    finally:
        stopped.set()
        thread.join(timeout=6)
        if owner is None:
            server.close()
        else:
            close_exclusive_helper(owner, server)
        assert not thread.is_alive()


@pytest.fixture
def root():
    with TemporaryDirectory(prefix="m1-guard-", dir="/tmp") as directory:
        yield Path(directory)


def test_same_operation_id_or_same_coordinator_step_cannot_reenter_backend(root):
    backend = Backend()
    first = dispatch()
    with running_helper(root, backend) as (client, _, _server):
        assert client.execute(first).status is HardwareResultStatus.COMPLETED
        for repeated in (
            first,
            replace(dispatch("operation-1", "different-coordinator", 0x2000)),
            dispatch("operation-2", "coordinator-1", 0x2000),
        ):
            with pytest.raises(HardwareError, match="operation outcome is unknown"):
                client.execute(repeated)
        assert backend.calls == [first]
        assert client.inspect().available is True
        journal = (root / "owner.lock.deny").read_bytes()
        assert b"synthetic-target" not in journal
        assert b"coordinator-1" not in journal


def test_success_intent_survives_helper_restart(root):
    first = dispatch()
    backend = Backend()
    with running_helper(root, backend) as (client, _, _server):
        assert client.execute(first).status is HardwareResultStatus.COMPLETED
    second_backend = Backend()
    with running_helper(root, second_backend) as (client, _, _server):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch("changed-request", "coordinator-1", 0x2000))
        assert second_backend.calls == []


def test_ambiguous_backend_entry_is_reserved_across_restart(root):
    failing = Backend(fail_after_entry=True)
    with running_helper(root, failing) as (client, _, _server):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch())
        assert len(failing.calls) == 1
    recovered = Backend()
    with running_helper(root, recovered) as (client, _, _server):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch("new-id", "coordinator-1"))
        assert recovered.calls == []


def test_process_death_after_reservation_refuses_same_step_after_restart(root):
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_crash_after_reservation_worker, args=(str(root), child))
    process.start()
    child.close()
    try:
        assert parent.poll(5), "synthetic crashing helper did not become ready"
        assert parent.recv() == "ready"
        client = HelperHardwareAdapter(root / "helper.sock")
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch())
        process.join(timeout=5)
        assert process.exitcode == 17
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)

    recovered = Backend()
    with running_helper(root, recovered) as (client, _, _server):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch("new-request-after-crash", "coordinator-1"))
        assert recovered.calls == []


@pytest.mark.parametrize("content", [b"not-json\n", b'{"version":1', b"x" * (1_048_576 + 1)])
def test_corrupt_or_oversized_journal_prevents_backend_construction(root, content):
    (root / "owner.lock.deny").write_bytes(content)
    (root / "owner.lock.deny").chmod(0o600)
    constructed = []
    with pytest.raises(HardwareError, match="deny journal"):
        start_exclusive_helper(root / "owner.lock", root / "helper.sock", lambda: constructed.append(True))
    assert constructed == []


def test_capacity_exhaustion_prevents_backend_entry(root, monkeypatch):
    import m1lab.adapters.helper_dispatch_guard as guard_module

    backend = Backend()
    with running_helper(root, backend) as (client, _, _server):
        monkeypatch.setattr(guard_module, "MAX_DENY_JOURNAL_ENTRIES", 0)
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch())
        assert backend.calls == []


def test_failed_fsync_poisons_guard_and_prevents_later_entry(root, monkeypatch):
    import m1lab.adapters.helper_dispatch_guard as guard_module

    backend = Backend()
    with running_helper(root, backend) as (client, _, server):
        original = guard_module.os.fsync
        guard_fd = server.dispatch_guard._fd

        def fail_journal_fsync(fd):
            if fd == guard_fd:
                raise OSError("synthetic disk failure")
            return original(fd)

        monkeypatch.setattr(guard_module.os, "fsync", fail_journal_fsync)
        for operation_id, coordinator_id in (("operation-1", "coordinator-1"), ("operation-2", "coordinator-2")):
            with pytest.raises(HardwareError, match="operation outcome is unknown"):
                client.execute(dispatch(operation_id, coordinator_id))
        assert backend.calls == []


def test_direct_server_without_guard_refuses_dispatch(root):
    backend = Backend()
    with running_helper(root, backend, guarded=False) as (client, _, _server):
        assert client.inspect().available is True
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch())
        assert backend.calls == []


def test_deadline_elapsed_during_durable_reservation_never_enters_backend(root):
    backend = Backend()
    with running_helper(root, backend) as (client, _, server):
        original_reserve = server.dispatch_guard.reserve
        reserved = Event()

        def slow_reserve(request):
            original_reserve(request)
            time.sleep(0.7)
            reserved.set()

        server.dispatch_guard.reserve = slow_reserve
        first = replace(
            dispatch(), deadline=datetime.now(timezone.utc) + timedelta(seconds=0.5),
        )
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(first)
        assert reserved.wait(timeout=2)
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch("new-id", "coordinator-1"))
        assert backend.calls == []
        assert (root / "owner.lock.deny").stat().st_size > 0


def test_startup_collision_cleans_backend_before_unlock_without_unlinking_live_socket(root):
    socket_path = root / "helper.sock"
    events = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as active:
        active.bind(str(socket_path))
        active.listen(1)

        def cleanup():
            events.append("cleanup")
            with pytest.raises(HelperOwnerError, match="another helper owns"):
                with HelperOwnerLock(root / "owner.lock"):
                    pass

        with pytest.raises(HelperOwnerError, match="already listening"):
            start_exclusive_helper(
                root / "owner.lock", socket_path, Backend,
                backend_cleanup=cleanup,
            )
        assert events == ["cleanup"]
        assert socket_path.exists()
        active.settimeout(1)
        accepted, _ = active.accept()
        accepted.close()
        with HelperOwnerLock(root / "owner.lock"):
            pass


def test_normal_close_runs_backend_cleanup_once_while_lock_is_held(root):
    events = []

    def cleanup():
        events.append("cleanup")
        with pytest.raises(HelperOwnerError, match="another helper owns"):
            with HelperOwnerLock(root / "owner.lock"):
                pass

    owner, server = start_exclusive_helper(
        root / "owner.lock", root / "helper.sock", Backend,
        backend_cleanup=cleanup,
    )
    close_exclusive_helper(owner, server)
    server.close()
    assert events == ["cleanup"]
    with HelperOwnerLock(root / "owner.lock"):
        pass
