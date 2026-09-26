"""Fixed, one-shot tethered native candidate backend for a separately owned helper.

Construction never opens a device. The caller must hold the exclusive helper
owner lock around this context and impose an independent worker watchdog.
This backend is not wired into normal observer or application startup.
"""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
from tempfile import TemporaryFile
import time
from uuid import uuid4

from .hardware import (
    HardwareCapability, HardwareDispatch, HardwareError, HardwareResult,
    HardwareResultStatus, MAX_RESULT_BYTES, RunNativeCandidate, TargetSnapshot,
)
from .m1n1_observer import M1N1Observer
from .native_bundle import NativeCandidateBundle
from .native_usb import NativeUsbTransport


_TOPOLOGY = re.compile(r"[0-9]+-[0-9]+(?:\.[0-9]+)*\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TTY = re.compile(r"ttyACM[0-9]+\Z")
_BOOTARGS = "console=tty0 earlycon rdinit=/init panic=10"
_DEVICE_ENV_KEY = "M1N1DEVICE"
_MAX_TOOL_BYTES = 128 << 20
_MAX_PROXYCLIENT_FILES = 4096
_MAX_PROXYCLIENT_BYTES = 256 << 20
_MAX_LOG_BYTES = 64 << 10
_POLL_SECONDS = 0.1
_RETURN_RESERVE_SECONDS = 10.0


class NativeCandidateError(HardwareError):
    """The fixed candidate could not establish a complete native round trip."""


class NativeCandidateBackend:
    """One target, one connection generation, and at most one boot attempt."""

    def __init__(
        self, *, artifact_root: Path, usb_topology: str,
        expected_proxy_serial_sha256: str, python_path: Path, python_sha256: str,
        boot_script_path: Path, boot_script_sha256: str, proxyclient_path: Path,
        proxyclient_sha256: str,
        sysfs_root: Path = Path("/sys/class/tty"), device_root: Path = Path("/dev"),
    ) -> None:
        if not _TOPOLOGY.fullmatch(usb_topology):
            raise ValueError("native candidate USB topology is invalid")
        for digest in (
            expected_proxy_serial_sha256, python_sha256, boot_script_sha256,
            proxyclient_sha256,
        ):
            if not _DIGEST.fullmatch(digest):
                raise ValueError("native candidate digest must be lowercase SHA-256")
        for path in (artifact_root, python_path, boot_script_path, proxyclient_path,
                     sysfs_root, device_root):
            if not Path(path).is_absolute():
                raise ValueError("native candidate paths must be absolute")
        if Path(boot_script_path).name != "linux.py":
            raise ValueError("native candidate boot script must be the reviewed linux.py")
        self.artifact_root = Path(artifact_root)
        self.usb_topology = usb_topology
        self.expected_proxy_serial_sha256 = expected_proxy_serial_sha256
        self.python_path = Path(python_path)
        self.python_sha256 = python_sha256
        self.boot_script_path = Path(boot_script_path)
        self.boot_script_sha256 = boot_script_sha256
        self.proxyclient_path = Path(proxyclient_path)
        self.proxyclient_sha256 = proxyclient_sha256
        self.sysfs_root = Path(sysfs_root)
        self.device_root = Path(device_root)
        fixed = {
            "usb_topology": usb_topology,
            "proxy_serial_sha256": expected_proxy_serial_sha256,
            "python_sha256": python_sha256,
            "python_path": str(python_path),
            "boot_script_sha256": boot_script_sha256,
            "boot_script_path": str(boot_script_path),
            "proxyclient_path": str(proxyclient_path),
            "proxyclient_sha256": proxyclient_sha256,
            "device_env_key": _DEVICE_ENV_KEY,
            "bootargs": _BOOTARGS,
        }
        self.configuration_digest = hashlib.sha256(json.dumps(
            fixed, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        self.target_identity = f"m1n1-serial-sha256:{expected_proxy_serial_sha256}"
        self._observer: M1N1Observer | None = None
        self._connection_epoch: str | None = None
        self._used = False

    def __enter__(self) -> NativeCandidateBackend:
        if self._observer is not None or self._used:
            raise NativeCandidateError("candidate backend is already open or used")
        self._verify_tools()
        deadline = time.monotonic() + 5.0
        device = self._wait_for_tty("1209", "316d", deadline, proxy=True)
        self._open_observer(device)
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self._close_observer()
        self._used = True

    def inspect(self) -> TargetSnapshot:
        if self._observer is None or self._connection_epoch is None:
            return self._unavailable()
        observed = self._observer.inspect()
        if not observed.available or observed.mode != "proxy" or observed.target_id != self.target_identity:
            self._close_observer()
            return self._unavailable()
        return TargetSnapshot(
            adapter="m1n1-native-candidate", available=True, qualified=False,
            mode="proxy", target_id=self.target_identity,
            boot_epoch=self._connection_epoch,
            configuration_digest=self.configuration_digest,
            capabilities=(HardwareCapability("run_native_candidate", 1, True, MAX_RESULT_BYTES),),
            observed_at=observed.observed_at,
            message="Owned proxy connection generation; not independent boot attestation.",
        )

    def execute(self, dispatch: HardwareDispatch) -> HardwareResult:
        started_at = datetime.now(timezone.utc)
        if self._used or self._observer is None or self._connection_epoch is None:
            raise NativeCandidateError("native candidate has no unused owned proxy connection")
        operation = dispatch.operation
        if not isinstance(operation, RunNativeCandidate):
            raise NativeCandidateError("backend accepts only run_native_candidate")
        if (dispatch.target_identity != self.target_identity
                or dispatch.boot_epoch != self._connection_epoch
                or dispatch.configuration_digest != self.configuration_digest
                or not {
                    operation.payload_sha256, operation.image_manifest_sha256,
                    operation.launch_manifest_sha256,
                }.issubset(dispatch.artifact_digests)):
            raise NativeCandidateError("native candidate dispatch does not match owned connection or artifacts")
        approval = dispatch.approval_scope
        if (dispatch.approval_id is None or approval is None
                or approval["physical_attendance_confirmed"] is not True
                or approval["repeat_limit"] != 1
                or approval["boot_epoch"] != dispatch.boot_epoch
                or approval["configuration_digest"] != dispatch.configuration_digest):
            raise NativeCandidateError("native candidate requires exact attended one-run approval")
        self._used = True
        total_deadline = time.monotonic() + (dispatch.deadline - started_at).total_seconds()
        raw = b""
        stop_reason = "not_started"
        complete = False
        tool_started = False
        tool_exit: int | None = None
        boot_log = b""
        return_epoch: str | None = None
        reason = "native candidate did not complete"
        try:
            self._verify_tools()
            with NativeCandidateBundle(
                self.artifact_root, image_manifest_sha256=operation.image_manifest_sha256,
                payload_sha256=operation.payload_sha256,
                launch_manifest_sha256=operation.launch_manifest_sha256,
            ) as bundle:
                assert bundle.launch is not None and bundle.image is not None
                launch, image = bundle.launch, bundle.image
                if (launch.target_identity != dispatch.target_identity
                        or launch.boot_epoch != dispatch.boot_epoch
                        or launch.configuration_sha256 != image.configuration_sha256):
                    raise NativeCandidateError("native launch differs from approved proxy dispatch")
                capture_deadline = min(
                    total_deadline - _RETURN_RESERVE_SECONDS,
                    time.monotonic() + (launch.deadline - datetime.now(timezone.utc)).total_seconds(),
                )
                if capture_deadline <= time.monotonic():
                    raise NativeCandidateError("native launch has insufficient bounded return window")
                proxy_device = self._observer.device
                self._close_observer()
                with TemporaryFile(mode="w+b") as log:
                    process = subprocess.Popen(
                        [str(self.python_path), str(self.boot_script_path), "-b", _BOOTARGS,
                         str(bundle.kernel), str(bundle.dtb), str(bundle.initramfs)],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        cwd=self.proxyclient_path,
                        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(self.proxyclient_path),
                             _DEVICE_ENV_KEY: str(proxy_device), "PYTHONDONTWRITEBYTECODE": "1"},
                        start_new_session=True,
                        preexec_fn=partial(_bind_child_to_worker, os.getpid()),
                    )
                    tool_started = True
                    try:
                        device = self._wait_for_tty("1d6b", "0104", capture_deadline, proxy=False)
                        with NativeUsbTransport(
                            device, expected_usb_topology=self.usb_topology,
                            sysfs_root=self.sysfs_root, device_root=self.device_root,
                        ) as transport:
                            receipt = transport.capture(
                                launch, image, deadline_monotonic=capture_deadline,
                                max_stream_bytes=MAX_RESULT_BYTES,
                            )
                        raw = receipt.raw_stream
                        stop_reason = receipt.stop_reason
                        complete = (
                            receipt.capture.status == "complete"
                            and receipt.capture.observed_linux is not None
                            and receipt.terminal_received_before_deadline
                            and len(receipt.raw_stream) <= MAX_RESULT_BYTES
                        )
                    except Exception as exc:
                        stop_reason = f"capture_{type(exc).__name__}"[:80]
                    finally:
                        try:
                            tool_exit = _finish_process(process, total_deadline)
                        finally:
                            log.seek(0)
                            boot_log = log.read(_MAX_LOG_BYTES + 1)
                    if len(boot_log) > _MAX_LOG_BYTES:
                        reason = "boot tool log exceeded its fixed bound"
                        complete = False
                # The proxy USB connection must re-enumerate and pass five
                # fresh read-only requests before the helper reports return.
                if time.monotonic() < total_deadline:
                    try:
                        returned_device = self._wait_for_tty(
                            "1209", "316d", total_deadline - 5.1, proxy=True,
                        )
                        self._open_observer(returned_device)
                        if time.monotonic() < total_deadline:
                            return_epoch = self._connection_epoch
                        else:
                            self._close_observer()
                    except Exception:
                        self._close_observer()
                if complete and tool_exit == 0 and return_epoch is not None:
                    reason = "Native capture and fresh proxy return observed; physical qualification remains open."
                elif reason == "native candidate did not complete":
                    reason = "Native launch, capture, or proxy return remained unverified."
        except Exception as exc:
            if not tool_started:
                raise
            reason = f"Native attempt outcome unknown after tool entry ({type(exc).__name__})."
        values = {
            "return_boot_epoch": return_epoch,
            "native_stop_reason": stop_reason,
            "boot_tool_exit_code": tool_exit,
            "boot_log_bytes": len(boot_log),
            "boot_log_sha256": hashlib.sha256(boot_log).hexdigest(),
            "boot_log_tail": boot_log.decode("utf-8", errors="replace")[-4096:],
            "connection_generation_only": True,
        }
        return HardwareResult(
            operation_id=dispatch.operation_id,
            status=(HardwareResultStatus.COMPLETED
                    if complete and tool_exit == 0 and return_epoch is not None
                    else HardwareResultStatus.UNKNOWN),
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            boot_epoch=dispatch.boot_epoch, values=values, payload=raw, message=reason,
        )

    def _verify_tools(self) -> None:
        _verify_file_hash(self.python_path, self.python_sha256)
        _verify_file_hash(self.boot_script_path, self.boot_script_sha256)
        if compute_proxyclient_sha256(self.proxyclient_path) != self.proxyclient_sha256:
            raise NativeCandidateError("fixed proxyclient library digest differs from pin")

    def _open_observer(self, device: Path) -> None:
        observer = M1N1Observer(
            device, expected_usb_topology=self.usb_topology,
            expected_serial_sha256=self.expected_proxy_serial_sha256,
            sysfs_root=self.sysfs_root, device_root=self.device_root,
        )
        observer.__enter__()
        self._observer = observer
        self._connection_epoch = uuid4().hex
        if not self.inspect().available:
            self._close_observer()
            raise NativeCandidateError("five-request proxy observation failed")

    def _close_observer(self) -> None:
        observer, self._observer = self._observer, None
        self._connection_epoch = None
        if observer is not None:
            observer.__exit__(None, None, None)

    def _wait_for_tty(self, vid: str, pid: str, deadline: float, *, proxy: bool) -> Path:
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("selected USB tty did not appear before deadline")
            matches = []
            entries = list(self.sysfs_root.glob("ttyACM*"))
            if len(entries) > 64:
                raise NativeCandidateError("too many candidate tty entries")
            for entry in entries:
                if not _TTY.fullmatch(entry.name):
                    continue
                try:
                    interface = (entry / "device").resolve(strict=True)
                    usb = interface.parent
                    if (interface.name != f"{self.usb_topology}:1.0"
                            or usb.name != self.usb_topology
                            or _read_sysfs(interface / "bInterfaceNumber") != "00"
                            or _read_sysfs(usb / "idVendor").lower() != vid
                            or _read_sysfs(usb / "idProduct").lower() != pid):
                        continue
                    serial = _read_sysfs(usb / "serial")
                    if proxy:
                        if hashlib.sha256(serial.encode()).hexdigest() != self.expected_proxy_serial_sha256:
                            continue
                    elif serial != "m1lab-native-candidate":
                        continue
                    device = self.device_root / entry.name
                    if device.exists():
                        matches.append(device)
                except (OSError, UnicodeError):
                    continue
            if len(matches) > 1:
                raise NativeCandidateError("ambiguous tty at the selected USB topology")
            if matches:
                if time.monotonic() >= deadline:
                    raise TimeoutError("selected USB tty appeared after deadline")
                return matches[0]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("selected USB tty did not appear before deadline")
            time.sleep(min(_POLL_SECONDS, remaining))

    def _unavailable(self) -> TargetSnapshot:
        return TargetSnapshot(
            adapter="m1n1-native-candidate", available=False, qualified=False,
            mode="disconnected", target_id=None, boot_epoch=None, capabilities=(),
            observed_at=datetime.now(timezone.utc), message="No owned proxy connection.",
        )


def _read_sysfs(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(257)
    if not raw or len(raw) > 256:
        raise NativeCandidateError("USB identity field is empty or over bound")
    return raw.decode("utf-8").strip()


def compute_proxyclient_sha256(root: Path) -> str:
    """Digest the fixed import tree; this also computes an operator pin.

    Version one hashes each included file's relative path, declared size and
    exact bytes in bytewise path order. Only Python bytecode caches are omitted.
    """

    root = Path(root)
    try:
        if not stat.S_ISDIR(root.lstat().st_mode):
            raise NativeCandidateError("fixed proxyclient library is not a real directory")
        pending = [root]
        files: list[tuple[bytes, Path, os.stat_result]] = []
        total_size = 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        raise NativeCandidateError("fixed proxyclient library contains a symlink")
                    path = Path(entry.path)
                    if stat.S_ISDIR(info.st_mode):
                        if entry.name != "__pycache__":
                            pending.append(path)
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        raise NativeCandidateError("fixed proxyclient library contains a nonregular file")
                    if path.suffix in {".pyc", ".pyo"}:
                        continue
                    total_size += info.st_size
                    if (len(files) >= _MAX_PROXYCLIENT_FILES
                            or total_size > _MAX_PROXYCLIENT_BYTES):
                        raise NativeCandidateError("fixed proxyclient library exceeds its tree bound")
                    relative = os.fsencode(path.relative_to(root).as_posix())
                    files.append((relative, path, info))
        if not files:
            raise NativeCandidateError("fixed proxyclient library has no pinned files")
        digest = hashlib.sha256(b"m1lab.proxyclient-tree.v1\0")
        for relative, path, info in sorted(files, key=lambda item: item[0]):
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            digest.update(info.st_size.to_bytes(8, "big"))
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(fd)
                if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != info.st_ino
                        or opened.st_dev != info.st_dev or opened.st_size != info.st_size):
                    raise NativeCandidateError("fixed proxyclient library changed during open")
                count = 0
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    while chunk := stream.read(1 << 20):
                        count += len(chunk)
                        if count > info.st_size:
                            raise NativeCandidateError("fixed proxyclient file grew during hashing")
                        digest.update(chunk)
                if count != info.st_size or os.fstat(fd).st_size != info.st_size:
                    raise NativeCandidateError("fixed proxyclient file changed during hashing")
            finally:
                os.close(fd)
        return digest.hexdigest()
    except OSError as exc:
        raise NativeCandidateError("fixed proxyclient library is unavailable") from exc


def _verify_file_hash(path: Path, expected: str) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_TOOL_BYTES:
            raise NativeCandidateError("fixed boot tool is not a bounded regular file")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(fd)
            if opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
                raise NativeCandidateError("fixed boot tool changed during open")
            digest = hashlib.sha256()
            with os.fdopen(fd, "rb", closefd=False) as stream:
                while chunk := stream.read(1 << 20):
                    digest.update(chunk)
            if digest.hexdigest() != expected or os.fstat(fd).st_size != info.st_size:
                raise NativeCandidateError("fixed boot tool digest differs from pin")
        finally:
            os.close(fd)
    except OSError as exc:
        raise NativeCandidateError("fixed boot tool is unavailable") from exc


def _bind_child_to_worker(expected_parent: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        os._exit(127)
    if os.getppid() != expected_parent:
        os._exit(127)
    resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_LOG_BYTES, _MAX_LOG_BYTES))


def _finish_process(process: subprocess.Popen[bytes], deadline: float) -> int | None:
    grace_deadline = min(deadline, time.monotonic() + 2.0)
    while process.poll() is None and time.monotonic() < grace_deadline:
        try:
            return process.wait(timeout=min(_POLL_SECONDS, grace_deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        return process.wait(timeout=max(0.1, min(1.0, deadline - time.monotonic())))
    except subprocess.TimeoutExpired:
        return None
