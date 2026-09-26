"""Synthetic subprocess checks for the persistent helper supervisor."""

from __future__ import annotations

from datetime import datetime, timezone
import multiprocessing as mp
import os
from pathlib import Path
import runpy
import signal
import socket
import struct
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace

import pytest

from m1lab.adapters.hardware import HardwareUnavailable, TargetSnapshot
from m1lab.adapters.helper_protocol import encode_inspect_request
from m1lab.adapters.helper_server import HelperHardwareAdapter, HelperOwnerError, HelperOwnerLock
from m1lab.adapters.helper_supervisor import HelperSupervisor, HelperSupervisorError


class SyntheticContext:
    def __init__(self, mode: str = "normal", events: str | None = None):
        self.mode = mode
        self.events = events

    def __enter__(self):
        if self.mode == "startup-hang":
            while True:
                time.sleep(1)
        return self

    def __exit__(self, *_args):
        if self.mode == "cleanup-hang":
            while True:
                time.sleep(1)
        if self.events:
            root = Path(self.events).parent
            assert not _can_connect(root / "helper.sock")
            with pytest.raises(HelperOwnerError):
                with HelperOwnerLock(root / "owner.lock"):
                    pass
            Path(self.events).write_text("socket-closed-backend-closed-owner-held")

    def inspect(self):
        if self.mode == "inspect-hang":
            while True:
                time.sleep(1)
        if self.mode == "crash":
            os._exit(17)
        return TargetSnapshot(
            adapter="synthetic-supervisor-test", available=True, qualified=False,
            mode="proxy", target_id="synthetic-only", boot_epoch=None,
            capabilities=(), observed_at=datetime.now(timezone.utc),
            message="Synthetic fixture; no physical target.",
        )

    def execute(self, _dispatch):
        raise HardwareUnavailable("synthetic observer cannot dispatch")


def _wait_for(predicate, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.025)
    return predicate()


def _start_thread(
    root: Path, mode: str = "normal", *, request_seconds: float = 1.0,
    owner_pidfd: int | None = None,
):
    stopped = Event()
    errors = []
    supervisor = HelperSupervisor(
        root, SyntheticContextFactory(mode, str(root / "backend.closed")),
        startup_seconds=1.0, request_seconds=request_seconds, cleanup_seconds=0.5,
    )

    def run():
        try:
            supervisor.run(stopped, owner_pidfd=owner_pidfd)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run)
    thread.start()
    return supervisor, stopped, thread, errors


class SyntheticContextFactory:
    def __init__(self, mode: str, events: str):
        self.mode = mode
        self.events = events

    def __call__(self):
        return SyntheticContext(self.mode, self.events)


def test_persistent_worker_serves_multiple_inspections_and_closes_in_order():
    with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
        root = Path(directory)
        supervisor, stopped, thread, errors = _start_thread(root)
        try:
            assert _wait_for(supervisor.socket_path.exists), errors
            client = HelperHardwareAdapter(supervisor.socket_path)
            first, second = client.inspect(), client.inspect()
            assert first.available and second.available
            assert not first.qualified and not second.qualified
            assert first.boot_epoch is second.boot_epoch is None
            assert first.capabilities == second.capabilities == ()
            with pytest.raises(HelperOwnerError):
                with HelperOwnerLock(root / "owner.lock"):
                    pass
        finally:
            stopped.set()
            thread.join(timeout=3)
        assert not thread.is_alive()
        assert errors == []
        assert not supervisor.socket_path.exists()
        assert (root / "backend.closed").read_text() == "socket-closed-backend-closed-owner-held"
        with HelperOwnerLock(root / "owner.lock"):
            pass


@pytest.mark.parametrize(
    ("mode", "trigger", "fragment"),
    [
        ("startup-hang", False, ("starting deadline",)),
        ("inspect-hang", True, ("busy deadline",)),
        ("crash", True, ("control channel failed", "exited unexpectedly")),
    ],
)
def test_stall_or_crash_reaps_worker_without_restart(mode, trigger, fragment):
    with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
        root = Path(directory)
        supervisor, stopped, thread, errors = _start_thread(root, mode, request_seconds=0.3)
        try:
            if trigger:
                assert _wait_for(supervisor.socket_path.exists)
                HelperHardwareAdapter(supervisor.socket_path).inspect()
            thread.join(timeout=4)
            assert not thread.is_alive()
            assert len(errors) == 1 and isinstance(errors[0], HelperSupervisorError)
            assert any(item in str(errors[0]) for item in fragment)
            assert not supervisor.socket_path.exists() or not _can_connect(supervisor.socket_path)
            with HelperOwnerLock(root / "owner.lock"):
                pass
        finally:
            stopped.set()
            thread.join(timeout=2)


def _can_connect(path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.1)
            client.connect(str(path))
            return True
    except OSError:
        return False


def test_partial_client_request_is_bounded_without_backend_entry():
    with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
        root = Path(directory)
        supervisor, stopped, thread, errors = _start_thread(root, request_seconds=0.3)
        try:
            assert _wait_for(supervisor.socket_path.exists)
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(str(supervisor.socket_path))
                thread.join(timeout=3)
            assert not thread.is_alive()
            assert len(errors) == 1
            assert "busy deadline" in str(errors[0])
            with HelperOwnerLock(root / "owner.lock"):
                pass
        finally:
            stopped.set()
            thread.join(timeout=2)


def test_hung_backend_cleanup_is_killed_and_releases_owner_lock():
    with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
        root = Path(directory)
        supervisor, stopped, thread, errors = _start_thread(root, "cleanup-hang")
        try:
            assert _wait_for(supervisor.socket_path.exists)
            assert HelperHardwareAdapter(supervisor.socket_path).inspect().available
            stopped.set()
            thread.join(timeout=3)
            assert not thread.is_alive()
            assert len(errors) == 1
            assert "cleanup did not exit normally" in str(errors[0])
            assert not _can_connect(supervisor.socket_path)
            with HelperOwnerLock(root / "owner.lock"):
                pass
        finally:
            stopped.set()
            thread.join(timeout=2)


def _supervisor_process(root: str, mode: str) -> None:
    supervisor = HelperSupervisor(Path(root), SyntheticContextFactory(mode, str(Path(root) / "backend.closed")))
    supervisor.run(Event())


@pytest.mark.parametrize("mode", ["normal", "inspect-hang"])
def test_parent_death_kills_worker_and_releases_owner_lock(mode):
    with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
        root = Path(directory)
        process = mp.get_context("spawn").Process(target=_supervisor_process, args=(directory, mode))
        process.start()
        socket_path = root / "helper.sock"
        try:
            assert _wait_for(socket_path.exists)
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(str(socket_path))
                worker_pid = struct.unpack(
                    "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )[0]
                if mode == "inspect-hang":
                    payload = encode_inspect_request()
                    connection.sendall(struct.pack("!I", len(payload)) + payload)
                    time.sleep(0.1)
            assert worker_pid != process.pid
            os.kill(process.pid, signal.SIGKILL)
            process.join(timeout=2)
            assert not process.is_alive()
            assert _wait_for(lambda: not _pid_alive(worker_pid))
            with HelperOwnerLock(root / "owner.lock"):
                pass
        finally:
            if process.is_alive():
                process.kill()
                process.join(timeout=2)


def _pid_alive(pid: int) -> bool:
    status = Path(f"/proc/{pid}/stat")
    try:
        if status.read_text().split()[2] == "Z":
            return False
    except FileNotFoundError:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _idle_owner() -> None:
    while True:
        time.sleep(1)


def test_dead_coordinator_lease_refuses_worker_start():
    owner = mp.get_context("spawn").Process(target=_idle_owner)
    owner.start()
    pidfd = os.pidfd_open(owner.pid)
    try:
        owner.kill()
        owner.join(timeout=2)
        with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
            root = Path(directory)
            supervisor = HelperSupervisor(root, SyntheticContextFactory("normal", str(root / "backend.closed")))
            with pytest.raises(HelperSupervisorError, match="lease ended"):
                supervisor.run(Event(), owner_pidfd=pidfd)
            assert not supervisor.socket_path.exists()
            assert not (root / "backend.closed").exists()
    finally:
        os.close(pidfd)
        if owner.is_alive():
            owner.kill()
            owner.join(timeout=2)


def test_invalid_coordinator_lease_refuses_worker_start():
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    try:
        with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
            root = Path(directory)
            supervisor = HelperSupervisor(root, SyntheticContextFactory("normal", str(root / "backend.closed")))
            with pytest.raises(HelperSupervisorError, match="lease"):
                supervisor.run(Event(), owner_pidfd=read_fd)
            assert not supervisor.socket_path.exists()
    finally:
        os.close(write_fd)


def test_coordinator_death_kills_hung_request_and_releases_lock():
    owner = mp.get_context("spawn").Process(target=_idle_owner)
    owner.start()
    pidfd = os.pidfd_open(owner.pid)
    try:
        with TemporaryDirectory(prefix="m1-supervisor-", dir="/tmp") as directory:
            root = Path(directory)
            supervisor, stopped, thread, errors = _start_thread(
                root, "inspect-hang", request_seconds=5.0, owner_pidfd=pidfd,
            )
            try:
                assert _wait_for(supervisor.socket_path.exists)
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.connect(str(supervisor.socket_path))
                    payload = encode_inspect_request()
                    connection.sendall(struct.pack("!I", len(payload)) + payload)
                    time.sleep(0.1)
                    owner.kill()
                    owner.join(timeout=2)
                    thread.join(timeout=3)
                assert not thread.is_alive()
                assert len(errors) == 1
                assert "lease ended" in str(errors[0])
                with HelperOwnerLock(root / "owner.lock"):
                    pass
            finally:
                stopped.set()
                thread.join(timeout=2)
    finally:
        os.close(pidfd)
        if owner.is_alive():
            owner.kill()
            owner.join(timeout=2)


def _serve_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "serve-m1n1-helper.py"
    return runpy.run_path(str(script))


def test_fixed_coordinator_generation_query_rejects_inactive_or_changed_data(monkeypatch):
    module = _serve_module()
    query = module["_coordinator_generation"]
    calls = []

    def show(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="ActiveState=active\nMainPID=2345\nInvocationID=" + "a" * 32 + "\n")

    monkeypatch.setattr(query.__globals__["subprocess"], "run", show)
    assert query() == (2345, "a" * 32)
    assert calls == [(module["_SYSTEMCTL_SHOW"], {
        "check": True, "capture_output": True, "text": True, "timeout": 3,
    })]
    assert calls[0][0][2] == "m1-power-lab.service"

    def inactive(_command, **_kwargs):
        return SimpleNamespace(stdout="ActiveState=inactive\nMainPID=0\nInvocationID=" + "a" * 32 + "\n")

    monkeypatch.setattr(query.__globals__["subprocess"], "run", inactive)
    with pytest.raises(HelperSupervisorError, match="not an active"):
        query()


@pytest.mark.parametrize("changed", [False, True])
def test_cli_checks_generation_twice_and_closes_pidfd(monkeypatch, capsys, changed):
    module = _serve_module()
    main = module["main"]
    generations = iter([(2345, "a" * 32), (2345, ("b" if changed else "a") * 32)])
    main.__globals__["_coordinator_generation"] = lambda: next(generations)
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(main.__globals__["os"], "pidfd_open", lambda _pid: read_fd)
    monkeypatch.setattr(main.__globals__["signal"], "signal", lambda *_args: None)
    runs = []

    class FakeSupervisor:
        def __init__(self, *_args):
            pass

        def run(self, _stopped, *, owner_pidfd):
            runs.append(owner_pidfd)

    main.__globals__["HelperSupervisor"] = FakeSupervisor
    try:
        result = main([
            "--state-dir", "/tmp/unused-supervisor-test", "--device", "/dev/ttyACM0",
            "--usb-topology", "1-1", "--expected-serial-sha256", "a" * 64,
            "--require-coordinator-service",
        ])
        assert result == (1 if changed else 0)
        assert runs == ([] if changed else [read_fd])
        with pytest.raises(OSError):
            os.fstat(read_fd)
        if changed:
            assert "generation changed" in capsys.readouterr().err
    finally:
        os.close(write_fd)
