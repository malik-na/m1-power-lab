"""Bounded process supervisor for one persistent, locally owned helper.

The supervisor never constructs a backend or opens a target device. Its worker
holds the owner lock from before backend entry until after socket and backend
cleanup. A failed worker is never restarted automatically.
"""

from __future__ import annotations

import ctypes
import math
import multiprocessing as mp
from multiprocessing.connection import Connection
import os
from pathlib import Path
import select
import signal
import stat
from threading import Event
import time
from typing import Callable

from .helper_server import start_exclusive_helper


class HelperSupervisorError(RuntimeError):
    """The helper could not start, remain responsive, or close cleanly."""


def _kill_on_parent_death(expected_parent: int) -> None:
    # Linux PR_SET_PDEATHSIG. Check PID again to close the fork/prctl race.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "could not bind helper lifetime to supervisor")
    if os.getppid() != expected_parent:
        os._exit(1)


def _worker_main(
    control: Connection,
    expected_parent: int,
    lock_path: Path,
    socket_path: Path,
    backend_factory: Callable[[], object],
) -> None:
    owner = server = backend_context = None
    try:
        _kill_on_parent_death(expected_parent)

        def open_backend():
            nonlocal backend_context
            backend_context = backend_factory()
            return backend_context.__enter__()

        def close_backend() -> None:
            if backend_context is not None:
                backend_context.__exit__(None, None, None)

        owner, server = start_exclusive_helper(
            lock_path, socket_path, open_backend, backend_cleanup=close_backend,
        )
        control.send("ready")
        # Accept repeatedly, while keeping the backend and owner lock alive.
        assert server._listener is not None
        while True:
            if control.poll():
                if control.recv() != "stop":
                    raise HelperSupervisorError("unknown supervisor instruction")
                break
            readable, _, _ = select.select([server._listener], [], [], 0.1)
            if not readable:
                continue
            control.send(("busy", time.monotonic()))
            try:
                server.serve_once()
            except Exception:
                # A malformed request belongs to its connection. The parent
                # bounds the entire request, including backend and journal I/O.
                pass
            finally:
                control.send("idle")
        control.send("stopping")
    except Exception as exc:
        try:
            control.send(("error", type(exc).__name__))
        except (BrokenPipeError, EOFError, OSError):
            pass
        raise
    finally:
        try:
            if server is not None:
                server.close()
        finally:
            try:
                if owner is not None:
                    owner.__exit__(None, None, None)
            finally:
                control.close()


class HelperSupervisor:
    """Run one helper worker until stopped, with bounded failure cleanup."""

    def __init__(
        self,
        state_dir: Path,
        backend_factory: Callable[[], object],
        *,
        startup_seconds: float = 8.0,
        request_seconds: float = 12.0,
        cleanup_seconds: float = 3.0,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser().absolute()
        self.backend_factory = backend_factory
        for value in (startup_seconds, request_seconds, cleanup_seconds):
            if not 0 < value < float("inf"):
                raise ValueError("supervisor deadlines must be finite and positive")
        self.startup_seconds = startup_seconds
        self.request_seconds = request_seconds
        self.cleanup_seconds = cleanup_seconds
        self.lock_path = self.state_dir / "owner.lock"
        self.socket_path = self.state_dir / "helper.sock"
        if len(os.fsencode(self.socket_path)) > 100:
            raise ValueError("helper socket path exceeds Linux sockaddr_un bound")

    def run(self, stop_event: Event) -> None:
        """Block until a requested stop; raise on worker failure or timeout."""

        if not isinstance(stop_event, Event):
            raise TypeError("stop_event must be a threading.Event")
        self._prepare_state_dir()
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(
            target=_worker_main,
            args=(child, os.getpid(), self.lock_path, self.socket_path, self.backend_factory),
        )
        try:
            process.start()
            child.close()
            phase = "starting"
            deadline = time.monotonic() + self.startup_seconds
            while not stop_event.is_set():
                if not process.is_alive():
                    raise HelperSupervisorError("helper worker exited unexpectedly")
                if phase != "idle" and time.monotonic() >= deadline:
                    raise HelperSupervisorError(f"helper {phase} deadline expired")
                wait = 0.05 if phase == "idle" else min(0.05, max(0.0, deadline - time.monotonic()))
                try:
                    if not parent.poll(wait):
                        continue
                    message = parent.recv()
                except (EOFError, BrokenPipeError, OSError) as exc:
                    raise HelperSupervisorError("helper control channel failed") from exc
                if message == "ready" and phase == "starting":
                    phase = "idle"
                elif (isinstance(message, tuple) and len(message) == 2
                      and message[0] == "busy" and phase == "idle"
                      and type(message[1]) is float and math.isfinite(message[1])):
                    phase = "busy"
                    deadline = message[1] + self.request_seconds
                elif message == "idle" and phase == "busy":
                    phase = "idle"
                elif isinstance(message, tuple) and message[0] == "error":
                    raise HelperSupervisorError(f"helper worker failed: {message[1]}")
                else:
                    raise HelperSupervisorError("helper control sequence is invalid")
            try:
                parent.send("stop")
            except (BrokenPipeError, EOFError, OSError) as exc:
                raise HelperSupervisorError("helper control channel failed during shutdown") from exc
            process.join(timeout=self.cleanup_seconds)
            if process.is_alive() or process.exitcode != 0:
                raise HelperSupervisorError("helper cleanup did not exit normally")
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=self.cleanup_seconds)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=self.cleanup_seconds)
                if process.is_alive():
                    raise HelperSupervisorError("helper worker could not be reaped")
            process.close()

    def _prepare_state_dir(self) -> None:
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.state_dir.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise HelperSupervisorError("helper state directory must be private and owned by this user")
