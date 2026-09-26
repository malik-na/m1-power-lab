"""Durable, append-only refusal of repeated helper dispatch intents.

The coordinator SQLite journal remains authoritative for outcomes. This small
local deny journal records only digests needed to refuse duplicate execution.
It is opened under the exclusive helper owner lock and is never pruned here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from threading import Lock

from .hardware import HardwareDispatch, HardwareError
from .helper_protocol import encode_request


MAX_DENY_JOURNAL_BYTES = 1_048_576
MAX_DENY_JOURNAL_ENTRIES = 4096
_FIELDS = frozenset({"version", "operation", "lineage", "request"})
_HEX = frozenset("0123456789abcdef")


class HelperDispatchGuard:
    """Reserve each validated dispatch before any device backend entry."""

    def __init__(self, owner_lock_path: Path):
        lock_path = Path(owner_lock_path).expanduser().absolute()
        self.path = lock_path.with_name(lock_path.name + ".deny")
        self._lock = Lock()
        self._fd: int | None = None
        self._invalid = False
        self._operations: set[str] = set()
        self._lineages: set[str] = set()
        self._size = 0
        self._open()

    def _open(self) -> None:
        existed = self.path.exists()
        flags = os.O_CREAT | os.O_RDWR | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
            self._fd = fd
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise HardwareError("helper deny journal is not a private regular file")
            if not existed:
                directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            if info.st_size > MAX_DENY_JOURNAL_BYTES:
                raise HardwareError("helper deny journal exceeds its capacity")
            self._size = info.st_size
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, info.st_size)
            if len(raw) != info.st_size or (raw and not raw.endswith(b"\n")):
                raise HardwareError("helper deny journal is truncated")
            entries = raw.splitlines()
            if len(entries) > MAX_DENY_JOURNAL_ENTRIES:
                raise HardwareError("helper deny journal exceeds its entry capacity")
            for line in entries:
                record = _decode_record(line)
                if record["operation"] in self._operations or record["lineage"] in self._lineages:
                    raise HardwareError("helper deny journal has duplicate intent keys")
                self._operations.add(record["operation"])
                self._lineages.add(record["lineage"])
        except Exception:
            self.close()
            raise

    def reserve(self, dispatch: HardwareDispatch) -> None:
        operation = _digest(dispatch.operation_id.encode("utf-8"))
        lineage = _digest(json.dumps(
            [dispatch.coordinator_operation_id, dispatch.operation_index],
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        request = _digest(encode_request(dispatch))
        record = {"version": 1, "operation": operation, "lineage": lineage, "request": request}
        line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        with self._lock:
            if self._fd is None or self._invalid:
                raise HardwareError("helper deny journal is unavailable")
            if operation in self._operations or lineage in self._lineages:
                raise HardwareError("helper refused a duplicate dispatch intent")
            if (len(self._operations) >= MAX_DENY_JOURNAL_ENTRIES
                    or self._size + len(line) > MAX_DENY_JOURNAL_BYTES):
                raise HardwareError("helper deny journal capacity is exhausted")
            try:
                written = os.write(self._fd, line)
                if written != len(line):
                    raise OSError("short helper deny journal write")
                os.fsync(self._fd)
            except OSError as exc:
                self._invalid = True
                raise HardwareError("helper deny journal reservation failed") from exc
            self._operations.add(operation)
            self._lineages.add(lineage)
            self._size += len(line)

    def close(self) -> None:
        with self._lock:
            fd, self._fd = self._fd, None
            if fd is not None:
                os.close(fd)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decode_record(line: bytes) -> dict:
    try:
        record = json.loads(line.decode("ascii"), object_pairs_hook=_unique_fields)
    except (UnicodeError, ValueError) as exc:
        raise HardwareError("helper deny journal contains an invalid record") from exc
    if not isinstance(record, dict) or set(record) != _FIELDS or type(record["version"]) is not int or record["version"] != 1:
        raise HardwareError("helper deny journal contains an invalid record")
    if any(type(record[name]) is not str or len(record[name]) != 64
           or any(char not in _HEX for char in record[name])
           for name in ("operation", "lineage", "request")):
        raise HardwareError("helper deny journal contains an invalid digest")
    return record


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate helper deny journal field")
        record[key] = value
    return record
