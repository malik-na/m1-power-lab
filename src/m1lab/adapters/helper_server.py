"""Linux local IPC boundary for an exclusive hardware-helper process.

The module does not select or open target devices. A deployment constructs its
fixed, in-package backend only after acquiring ``HelperOwnerLock``. One typed
request is accepted per same-UID Unix-socket connection; transport ambiguity
is never retried here.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import logging
import os
from pathlib import Path
import socket
import stat
import struct
import time
from threading import Event
from typing import Callable

from .hardware import (
    CaptureMemory,
    HardwareAdapter,
    HardwareDispatch,
    HardwareError,
    HardwareResult,
    HardwareResultStatus,
    InspectRegister,
    MAX_RESULT_BYTES,
    RunNativeCandidate,
    TargetSnapshot,
)
from .helper_protocol import (
    MAX_HELPER_REQUEST_BYTES,
    MAX_HELPER_RESPONSE_BYTES,
    HelperProtocolError,
    MAX_HELPER_SNAPSHOT_BYTES,
    decode_snapshot,
    decode_request,
    decode_result,
    encode_inspect_request,
    encode_request,
    encode_result,
    encode_snapshot,
    is_inspect_request,
    read_helper_frame_until,
    write_helper_frame_until,
)
from .helper_dispatch_guard import HelperDispatchGuard


MAX_HELPER_HANDSHAKE_SECONDS = 5.0
MAX_HELPER_SOCKET_PATH_BYTES = 100
_LOG = logging.getLogger(__name__)


class HelperOwnerError(RuntimeError):
    """The exclusive helper owner or its local IPC boundary is unavailable."""


class HelperOwnerLock(AbstractContextManager["HelperOwnerLock"]):
    """Nonblocking advisory lock held for the full lifetime of a helper owner."""

    def __init__(self, path: Path):
        self.path = path.expanduser().absolute()
        self._fd: int | None = None

    def __enter__(self) -> "HelperOwnerLock":
        if self._fd is not None:
            raise HelperOwnerError("helper owner lock is already held by this object")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or not stat.S_ISDIR(parent.st_mode):
            raise HelperOwnerError("helper lock directory must be owned by the current user")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise HelperOwnerError("helper lock path must be a user-owned regular file")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, HelperOwnerError) as exc:
            if "fd" in locals():
                os.close(fd)
            if isinstance(exc, HelperOwnerError):
                raise
            raise HelperOwnerError("another helper owns the target lock") from exc
        self._fd = fd
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        if self._fd is not None:
            fd, self._fd = self._fd, None
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


class HelperHardwareAdapter:
    """Client for the same-user helper socket; it never opens a device."""

    def __init__(self, socket_path: Path, *, expected_uid: int | None = None):
        self.socket_path = socket_path.expanduser().absolute()
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        _validate_socket_path(self.socket_path)
        if type(self.expected_uid) is not int or self.expected_uid < 0:
            raise ValueError("helper peer UID must be a non-negative integer")

    def inspect(self) -> TargetSnapshot:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(MAX_HELPER_HANDSHAKE_SECONDS)
            client.connect(str(self.socket_path))
            _verify_peer_uid(client, self.expected_uid)
            client.setblocking(False)
            deadline = time.monotonic() + MAX_HELPER_HANDSHAKE_SECONDS
            write_helper_frame_until(
                client.fileno(), encode_inspect_request(),
                maximum=MAX_HELPER_REQUEST_BYTES, deadline_monotonic=deadline,
            )
            frame = read_helper_frame_until(
                client.fileno(), maximum=MAX_HELPER_SNAPSHOT_BYTES,
                deadline_monotonic=deadline,
            )
            return decode_snapshot(frame[4:])
        except (OSError, TimeoutError, HelperOwnerError, HelperProtocolError) as exc:
            return TargetSnapshot(
                adapter="m1n1-helper-unavailable",
                available=False,
                qualified=False,
                mode="disconnected",
                target_id=None,
                boot_epoch=None,
                capabilities=(),
                observed_at=datetime.now(timezone.utc),
                message=f"Helper inspection unavailable: {exc}",
            )
        finally:
            client.close()

    def execute(self, dispatch: HardwareDispatch) -> HardwareResult:
        remaining = (dispatch.deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise HardwareError("helper dispatch deadline expired before connection")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(min(MAX_HELPER_HANDSHAKE_SECONDS, remaining))
            client.connect(str(self.socket_path))
            _verify_peer_uid(client, self.expected_uid)
            client.setblocking(False)
            deadline = time.monotonic() + remaining
            write_helper_frame_until(
                client.fileno(),
                encode_request(dispatch),
                maximum=MAX_HELPER_REQUEST_BYTES,
                deadline_monotonic=deadline,
            )
            frame = read_helper_frame_until(
                client.fileno(),
                maximum=MAX_HELPER_RESPONSE_BYTES,
                deadline_monotonic=deadline,
            )
            result = decode_result(
                frame[4:], expected_operation_id=dispatch.operation_id
            )
            if result.boot_epoch != dispatch.boot_epoch:
                raise HardwareError("helper result boot epoch differs from the dispatch")
            return result
        except (OSError, TimeoutError, HelperProtocolError) as exc:
            raise HardwareError(
                f"helper transport ended ambiguously; operation outcome is unknown: {exc}"
            ) from exc
        finally:
            client.close()


class HelperServer:
    """Serve single-operation connections after an exclusive owner lock."""

    def __init__(
        self,
        socket_path: Path,
        adapter: HardwareAdapter,
        *,
        expected_uid: int | None = None,
        dispatch_guard: HelperDispatchGuard | None = None,
        backend_cleanup: Callable[[], None] | None = None,
    ):
        self.socket_path = socket_path.expanduser().absolute()
        self.adapter = adapter
        self.dispatch_guard = dispatch_guard
        self._backend_cleanup = backend_cleanup
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        _validate_socket_path(self.socket_path)
        if type(self.expected_uid) is not int or self.expected_uid < 0:
            raise ValueError("helper peer UID must be a non-negative integer")
        self._listener: socket.socket | None = None

    def listen(self, *, backlog: int = 8) -> None:
        if self._listener is not None:
            raise HelperOwnerError("helper server is already listening")
        if not 1 <= backlog <= 128:
            raise ValueError("helper socket backlog must be 1..128")
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_info = parent.stat()
        if parent_info.st_uid != os.getuid() or not stat.S_ISDIR(parent_info.st_mode):
            raise HelperOwnerError("helper socket directory must be owned by the current user")
        _remove_stale_socket(self.socket_path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            listener.listen(backlog)
            self._listener = listener
        except OSError:
            listener.close()
            _remove_stale_socket(self.socket_path, allow_missing=True)
            raise

    def serve_once(self) -> None:
        if self._listener is None:
            raise HelperOwnerError("helper server is not listening")
        connection, _ = self._listener.accept()
        with connection:
            _verify_peer_uid(connection, self.expected_uid)
            connection.setblocking(False)
            handshake_deadline = time.monotonic() + MAX_HELPER_HANDSHAKE_SECONDS
            request_frame = read_helper_frame_until(
                connection.fileno(),
                maximum=MAX_HELPER_REQUEST_BYTES,
                deadline_monotonic=handshake_deadline,
            )
            if is_inspect_request(request_frame[4:]):
                snapshot = self.adapter.inspect()
                write_helper_frame_until(
                    connection.fileno(), encode_snapshot(snapshot),
                    maximum=MAX_HELPER_SNAPSHOT_BYTES,
                    deadline_monotonic=handshake_deadline,
                )
                return
            dispatch = decode_request(request_frame[4:])
            remaining = (dispatch.deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                raise HardwareError("helper rejected an expired dispatch before execution")
            operation_deadline = time.monotonic() + remaining
            preflight_snapshot = self.adapter.inspect()
            _validate_dispatch_target(dispatch, preflight_snapshot)
            if dispatch.deadline <= datetime.now(timezone.utc):
                raise HardwareError("helper rejected a dispatch whose deadline elapsed during preflight")
            if self.dispatch_guard is None:
                raise HardwareError("helper dispatch guard is unavailable")
            self.dispatch_guard.reserve(dispatch)
            if (dispatch.deadline <= datetime.now(timezone.utc)
                    or time.monotonic() >= operation_deadline):
                raise HardwareError("helper rejected a dispatch whose deadline elapsed after reservation")
            result = self.adapter.execute(dispatch)
            if result.operation_id != dispatch.operation_id:
                raise HardwareError("device backend returned a mismatched operation ID")
            if result.boot_epoch != dispatch.boot_epoch:
                raise HardwareError("device backend returned a mismatched boot epoch")
            if isinstance(dispatch.operation, RunNativeCandidate):
                try:
                    returned = self.adapter.inspect()
                except Exception:
                    returned = None
                capability = next(
                    item for item in preflight_snapshot.capabilities
                    if item.name == "run_native_candidate" and item.version == 1
                )
                if (len(result.payload) > capability.max_result_bytes
                        or not _native_return_verified(dispatch, result, returned)):
                    result = replace(
                        result, status=HardwareResultStatus.UNKNOWN,
                        message=(result.message[:4000] + " Native return could not be verified.")[:4096],
                    )
            else:
                _validate_dispatch_target(dispatch, self.adapter.inspect())
            write_helper_frame_until(
                connection.fileno(),
                encode_result(result),
                maximum=MAX_HELPER_RESPONSE_BYTES,
                deadline_monotonic=operation_deadline,
            )

    def serve_forever(
        self,
        stop_event: Event,
        *,
        poll_interval_seconds: float = 0.5,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Accept bounded one-operation connections until shutdown is requested.

        A malformed client or failed operation closes only that connection.
        The error callback receives the exception after the connection has
        closed; without one, failures are logged and the next client is served.
        Backend construction and device ownership remain the caller's job.
        """

        if self._listener is None:
            raise HelperOwnerError("helper server is not listening")
        if not isinstance(stop_event, Event):
            raise TypeError("helper stop_event must be a threading.Event")
        if not 0.05 <= poll_interval_seconds <= 10:
            raise ValueError("helper poll interval must be between 0.05 and 10 seconds")

        self._listener.settimeout(poll_interval_seconds)
        try:
            while not stop_event.is_set():
                try:
                    self.serve_once()
                except TimeoutError:
                    # A frame timeout belongs to its client; keep the owner
                    # process available for subsequent connections.
                    continue
                except OSError as exc:
                    if self._listener is None:
                        break
                    self._report_server_error(exc, on_error)
                except Exception as exc:
                    self._report_server_error(exc, on_error)
        finally:
            if self._listener is not None:
                self._listener.settimeout(None)

    @staticmethod
    def _report_server_error(
        error: Exception, callback: Callable[[Exception], None] | None
    ) -> None:
        if callback is not None:
            callback(error)
        else:
            _LOG.warning(
                "helper connection failed; any dispatched operation may have an unknown effect: %s",
                error,
                exc_info=error,
            )

    def close(self) -> None:
        listener, self._listener = self._listener, None
        try:
            if listener is not None:
                listener.close()
                _remove_stale_socket(self.socket_path, allow_missing=True)
        finally:
            try:
                if self.dispatch_guard is not None:
                    self.dispatch_guard.close()
            finally:
                cleanup, self._backend_cleanup = self._backend_cleanup, None
                if cleanup is not None:
                    cleanup()

    def __enter__(self) -> "HelperServer":
        self.listen()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()


def start_exclusive_helper(
    lock_path: Path,
    socket_path: Path,
    backend_factory: Callable[[], HardwareAdapter],
    *,
    backend_cleanup: Callable[[], None] | None = None,
) -> tuple[HelperOwnerLock, HelperServer]:
    """Acquire ownership before constructing a fixed in-process backend.

    The caller must keep the returned lock alive until after the server closes.
    Production wiring should provide a statically selected backend factory; do
    not derive an import path, command, or module from remote request data.
    """

    lock = HelperOwnerLock(lock_path)
    lock.__enter__()
    guard = None
    server = None
    backend_started = False
    try:
        guard = HelperDispatchGuard(lock.path)
        backend_started = True
        backend = backend_factory()
        server = HelperServer(
            socket_path, backend, dispatch_guard=guard,
            backend_cleanup=backend_cleanup,
        )
        server.listen()
    except Exception:
        try:
            if server is not None:
                server.close()
            else:
                try:
                    if guard is not None:
                        guard.close()
                finally:
                    if backend_started and backend_cleanup is not None:
                        backend_cleanup()
        finally:
            lock.__exit__(None, None, None)
        raise
    return lock, server


def close_exclusive_helper(lock: HelperOwnerLock, server: HelperServer) -> None:
    """Close the endpoint before releasing its device-ownership lease."""

    try:
        server.close()
    finally:
        lock.__exit__(None, None, None)


def _verify_peer_uid(connection: socket.socket, expected_uid: int) -> None:
    if not hasattr(socket, "SO_PEERCRED"):
        raise HelperOwnerError("Unix peer credentials are unavailable on this platform")
    try:
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", credentials)
    except OSError as exc:
        raise HelperOwnerError("could not verify helper socket peer credentials") from exc
    if uid != expected_uid:
        raise HelperOwnerError("helper socket peer UID is not authorized")


def _validate_dispatch_target(dispatch: HardwareDispatch, snapshot: TargetSnapshot) -> None:
    if isinstance(dispatch.operation, RunNativeCandidate):
        _validate_native_candidate_target(dispatch, snapshot)
        return
    if not snapshot.available or not snapshot.qualified:
        raise HardwareError("helper target is unavailable or not physically qualified")
    if snapshot.target_id != dispatch.target_identity:
        raise HardwareError("helper refused a dispatch for a different target identity")
    if snapshot.boot_epoch != dispatch.boot_epoch:
        raise HardwareError("helper refused a dispatch for a stale target boot epoch")
    if snapshot.configuration_digest != dispatch.configuration_digest:
        raise HardwareError("helper refused a dispatch for a stale target configuration")
    capabilities = {
        capability.name: capability
        for capability in snapshot.capabilities
        if capability.version == 1
    }
    operation = dispatch.operation
    if isinstance(operation, InspectRegister):
        capability = capabilities.get("inspect_register")
        required_bytes = operation.width_bytes
    elif isinstance(operation, CaptureMemory):
        capability = capabilities.get("capture_memory")
        required_bytes = operation.length
    else:
        raise HardwareError("helper rejected an unsupported live operation type")
    if capability is None or capability.mutating:
        raise HardwareError("helper target does not advertise this read-only operation")
    if required_bytes > capability.max_result_bytes:
        raise HardwareError("helper operation exceeds the advertised capability bound")


def _validate_native_candidate_target(dispatch: HardwareDispatch, snapshot: TargetSnapshot) -> None:
    """Allow one attended qualification run from the observed proxy state."""

    if not snapshot.available or snapshot.mode != "proxy":
        raise HardwareError("native candidate requires an available proxy target")
    if snapshot.target_id != dispatch.target_identity:
        raise HardwareError("native candidate target identity differs from the dispatch")
    if snapshot.boot_epoch != dispatch.boot_epoch:
        raise HardwareError("native candidate proxy boot epoch differs from the dispatch")
    if snapshot.configuration_digest != dispatch.configuration_digest:
        raise HardwareError("native candidate proxy configuration differs from the dispatch")
    operation = dispatch.operation
    assert isinstance(operation, RunNativeCandidate)
    required = {
        operation.payload_sha256, operation.image_manifest_sha256,
        operation.launch_manifest_sha256,
    }
    if len(required) != 3 or not required.issubset(dispatch.artifact_digests):
        raise HardwareError("native candidate requires its three reviewed artifact digests")
    approval = dispatch.approval_scope
    if (dispatch.approval_id is None or approval is None
            or approval["physical_attendance_confirmed"] is not True
            or approval["repeat_limit"] != 1
            or approval["boot_epoch"] != dispatch.boot_epoch
            or approval["configuration_digest"] != dispatch.configuration_digest):
        raise HardwareError("native candidate requires exact attended one-run approval")
    capability = next((item for item in snapshot.capabilities
                       if item.name == "run_native_candidate" and item.version == 1), None)
    if (capability is None or capability.mutating is not True
            or not 0 < capability.max_result_bytes <= MAX_RESULT_BYTES):
        raise HardwareError("native candidate capability is absent or not bounded")


def _native_return_verified(
    dispatch: HardwareDispatch, result: HardwareResult, snapshot: TargetSnapshot | None
) -> bool:
    if (snapshot is None or not snapshot.available or snapshot.mode != "proxy"
            or snapshot.target_id != dispatch.target_identity
            or snapshot.configuration_digest != dispatch.configuration_digest
            or not snapshot.boot_epoch or snapshot.boot_epoch == dispatch.boot_epoch):
        return False
    if result.status is HardwareResultStatus.COMPLETED:
        return result.values.get("return_boot_epoch") == snapshot.boot_epoch
    return True


def _validate_socket_path(path: Path) -> None:
    if not path.is_absolute() or len(os.fsencode(path)) > MAX_HELPER_SOCKET_PATH_BYTES:
        raise ValueError("helper socket path must be absolute and fit Linux sockaddr_un")


def _remove_stale_socket(path: Path, *, allow_missing: bool = False) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return
        return
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise HelperOwnerError("refusing to replace a non-socket or foreign helper path")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.2)
        probe.connect(str(path))
    except OSError as exc:
        import errno

        if exc.errno in {errno.ECONNREFUSED, errno.ENOENT}:
            path.unlink(missing_ok=True)
        else:
            raise HelperOwnerError("could not determine whether helper socket is active") from exc
    else:
        raise HelperOwnerError("another helper is already listening on this socket")
    finally:
        probe.close()
