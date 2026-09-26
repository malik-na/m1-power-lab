from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import threading
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

from m1lab.paths import AppPaths

from .errors import NotFoundError, ValidationError
from .models import ArtifactRecord, EventRecord, new_id, utc_now


SCHEMA_VERSION = 3
JOURNAL_DISK_RESERVE_BYTES = 512 * 1024 * 1024
LARGE_ARTIFACT_THRESHOLD_BYTES = 1 * 1024 * 1024
LARGE_ARTIFACT_DISK_RESERVE_BYTES = 1024 * 1024 * 1024


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    objective TEXT NOT NULL,
    owner TEXT NOT NULL,
    host_identity TEXT NOT NULL,
    target_identity TEXT,
    policy_json TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    lifetime_tokens INTEGER NOT NULL DEFAULT 0,
    lifetime_active_seconds REAL NOT NULL DEFAULT 0,
    usage_uncertain INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS session_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    record_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(session_id, revision)
);
CREATE TABLE IF NOT EXISTS events (
    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    kind TEXT NOT NULL,
    subject_id TEXT,
    data_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_session_cursor ON events(session_id, cursor);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    owner_login TEXT NOT NULL,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth_secret TEXT NOT NULL,
    enrolled_after_cursor INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS push_subscriptions_active
    ON push_subscriptions(session_id, revoked_at);
CREATE TABLE IF NOT EXISTS push_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_cursor INTEGER NOT NULL,
    subscription_id TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT,
    completed_at TEXT,
    UNIQUE(session_id, event_cursor, subscription_id, category)
);
CREATE TABLE IF NOT EXISTS push_cursors (
    session_id TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_commands (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    expected_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    resulting_revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS allowance_epochs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    token_delta INTEGER NOT NULL DEFAULT 0,
    active_seconds_value REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    command_id TEXT,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS active_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    boot_id TEXT NOT NULL,
    started_utc TEXT NOT NULL,
    started_monotonic REAL NOT NULL,
    ended_utc TEXT,
    ended_monotonic REAL,
    elapsed_seconds REAL,
    uncertain INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_active_segment
    ON active_segments(session_id) WHERE ended_utc IS NULL;
CREATE TABLE IF NOT EXISTS usage_sources (
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    cumulative_tokens INTEGER NOT NULL DEFAULT 0,
    accounted_tokens INTEGER NOT NULL DEFAULT 0,
    terminal INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(session_id, source_id)
);
CREATE TABLE IF NOT EXISTS usage_reports (
    report_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cumulative INTEGER NOT NULL,
    token_delta INTEGER NOT NULL,
    terminal INTEGER NOT NULL,
    reported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    tokens INTEGER NOT NULL,
    active_seconds INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    released_at TEXT
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    available INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_links (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    session_id TEXT,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(artifact_id, provenance_json)
);
CREATE INDEX IF NOT EXISTS artifact_links_session ON artifact_links(session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS target_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    identity TEXT NOT NULL,
    boot_epoch TEXT NOT NULL,
    mode TEXT NOT NULL,
    configuration_digest TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    recovery_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    fresh_until TEXT
);
CREATE INDEX IF NOT EXISTS targets_session_time ON target_snapshots(session_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS procedures (
    procedure_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(procedure_id, revision),
    UNIQUE(procedure_id, digest)
);
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    procedure_id TEXT NOT NULL,
    procedure_revision INTEGER NOT NULL,
    procedure_digest TEXT NOT NULL,
    disposition TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    procedure_id TEXT NOT NULL,
    procedure_revision INTEGER NOT NULL,
    procedure_digest TEXT NOT NULL,
    owner TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    procedure_id TEXT NOT NULL,
    procedure_revision INTEGER NOT NULL,
    procedure_digest TEXT NOT NULL,
    approval_id TEXT,
    review_id TEXT NOT NULL,
    target_snapshot_id TEXT NOT NULL,
    boot_epoch TEXT NOT NULL,
    adapter_mode TEXT NOT NULL,
    mutates_target INTEGER NOT NULL,
    state TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dispatched_at TEXT,
    completed_at TEXT,
    reconciliation_json TEXT
);
CREATE INDEX IF NOT EXISTS operations_session_state ON operations(session_id, state);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    runtime_id TEXT,
    state TEXT NOT NULL,
    lease_expires_at TEXT,
    deadline_at TEXT,
    evidence_manifest_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def json_load(value: str | bytes | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def iso(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("persisted timestamps must be timezone-aware")
    return current.astimezone(timezone.utc).isoformat()


class Journal:
    """Authoritative SQLite journal and immutable artifact store."""

    def __init__(self, paths: AppPaths):
        paths.prepare()
        self.paths = paths
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(paths.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._connection.execute(
                "INSERT OR IGNORE INTO artifact_links(id,artifact_id,session_id,provenance_json,created_at) "
                "SELECT 'link_' || substr(id,10), id, json_extract(provenance_json,'$.session_id'), "
                "provenance_json, created_at FROM artifacts"
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, iso()),
            )
            self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(sql, params).fetchone()

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._connection.execute(sql, params).fetchall())

    def append_event(
        self,
        tx: sqlite3.Connection,
        *,
        kind: str,
        session_id: str | None,
        subject_id: str | None,
        data: Mapping[str, Any],
    ) -> int:
        cursor = tx.execute(
            "INSERT INTO events(session_id, kind, subject_id, data_json, occurred_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, kind, subject_id, json_dump(data), iso()),
        ).lastrowid
        assert cursor is not None
        return cursor

    def events(self, *, session_id: str | None = None, after: int = 0, limit: int = 200) -> list[EventRecord]:
        limit = min(max(limit, 1), 2_000)
        if session_id is None:
            rows = self.all("SELECT * FROM events WHERE cursor > ? ORDER BY cursor LIMIT ?", (after, limit))
        else:
            rows = self.all(
                "SELECT * FROM events WHERE session_id = ? AND cursor > ? ORDER BY cursor LIMIT ?",
                (session_id, after, limit),
            )
        return [
            EventRecord(
                cursor=row["cursor"],
                session_id=row["session_id"],
                kind=row["kind"],
                subject_id=row["subject_id"],
                data=json_load(row["data_json"], {}),
                occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

    def publish_artifact(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        provenance: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(content).hexdigest()
        artifact_id = f"artifact_{digest}"
        relative_path = f"{digest[:2]}/{digest[2:4]}/{digest}"
        destination = self.paths.artifacts / relative_path
        now = utc_now()
        existing = self.one("SELECT * FROM artifacts WHERE sha256 = ?", (digest,))
        if existing is not None:
            if (
                not destination.is_file()
                or destination.stat().st_size != existing["size_bytes"]
                or _file_sha256(destination) != existing["sha256"]
            ):
                raise ValidationError(f"artifact {artifact_id} metadata exists but its file is missing or invalid")
            return self._link_existing_artifact(existing, provenance or {}, now)

        self.ensure_artifact_capacity(len(content))

        staging = self.paths.staging / f"{uuid4().hex}.partial"
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with staging.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.ensure_artifact_capacity(staged_bytes=len(content))
            os.replace(staging, destination)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            with self.transaction() as tx:
                tx.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        artifact_id,
                        digest,
                        len(content),
                        media_type,
                        relative_path,
                        json_dump(provenance or {}),
                        iso(now),
                    ),
                )
                self.append_event(
                    tx,
                    kind="artifact.published",
                    session_id=(provenance or {}).get("session_id"),
                    subject_id=artifact_id,
                    data={"sha256": digest, "size_bytes": len(content), "media_type": media_type},
                )
        finally:
            staging.unlink(missing_ok=True)
        row = self.one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        assert row is not None
        return self._link_existing_artifact(row, provenance or {}, now, emit_event=False)

    def ensure_artifact_capacity(
        self, additional_bytes: int = 0, *, staged_bytes: int = 0
    ) -> None:
        """Keep database and cleanup space available before admitting writes."""
        if additional_bytes < 0 or staged_bytes < 0:
            raise ValueError("artifact byte counts cannot be negative")
        reserve = (
            LARGE_ARTIFACT_DISK_RESERVE_BYTES
            if max(additional_bytes, staged_bytes) >= LARGE_ARTIFACT_THRESHOLD_BYTES
            else JOURNAL_DISK_RESERVE_BYTES
        )
        free_bytes = shutil.disk_usage(self.paths.root).free
        if free_bytes + staged_bytes - additional_bytes < reserve:
            required = reserve + additional_bytes - staged_bytes
            raise ValidationError(
                "artifact admission stopped to preserve the disk reserve "
                f"({free_bytes} bytes free; {required} bytes required)"
            )

    def _link_existing_artifact(
        self,
        row: sqlite3.Row,
        provenance: Mapping[str, Any],
        created_at: datetime,
        *,
        emit_event: bool = True,
    ) -> ArtifactRecord:
        provenance_json = json_dump(provenance)
        link_id = "link_" + hashlib.sha256(
            f"{row['id']}:{provenance_json}".encode()
        ).hexdigest()
        with self.transaction() as tx:
            restored = not bool(row["available"])
            if restored:
                tx.execute("UPDATE artifacts SET available=1 WHERE id=?", (row["id"],))
            inserted = tx.execute(
                "INSERT OR IGNORE INTO artifact_links VALUES (?,?,?,?,?)",
                (link_id, row["id"], provenance.get("session_id"), provenance_json, iso(created_at)),
            )
            actual = tx.execute(
                "SELECT id, created_at FROM artifact_links WHERE artifact_id=? AND provenance_json=?",
                (row["id"], provenance_json),
            ).fetchone()
            assert actual is not None
            link_id = actual["id"]
            if emit_event and inserted.rowcount:
                self.append_event(
                    tx,
                    kind="artifact.linked",
                    session_id=provenance.get("session_id"),
                    subject_id=row["id"],
                    data={"publication_id": link_id, "sha256": row["sha256"]},
                )
            if restored:
                self.append_event(
                    tx,
                    kind="artifact.available",
                    session_id=provenance.get("session_id"),
                    subject_id=row["id"],
                    data={"reason": "content was supplied again and its digest was verified"},
                )
        return self._artifact_from_row(row).model_copy(
            update={
                "publication_id": link_id,
                "provenance": dict(provenance),
                "created_at": actual["created_at"],
                "available": True,
            }
        )

    def artifact(self, artifact_id: str) -> ArtifactRecord:
        row = self.one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        if row is None:
            raise NotFoundError(f"artifact {artifact_id} does not exist")
        return self._artifact_from_row(row)

    def artifact_for_session(self, session_id: str, artifact_id: str) -> ArtifactRecord:
        row = self.one(
            "SELECT a.*, l.id AS publication_id, "
            "l.provenance_json AS link_provenance_json, l.created_at AS link_created_at "
            "FROM artifacts a JOIN artifact_links l ON l.artifact_id=a.id "
            "WHERE a.id=? AND l.session_id=? ORDER BY l.created_at DESC LIMIT 1",
            (artifact_id, session_id),
        )
        if row is None:
            raise NotFoundError(
                f"artifact {artifact_id} is not published in session {session_id}"
            )
        return self._artifact_from_row(row)

    def read_artifact_for_session(
        self, session_id: str, artifact_id: str, *, max_bytes: int
    ) -> bytes:
        record = self.artifact_for_session(session_id, artifact_id)
        if not record.available:
            raise ValidationError(f"artifact {artifact_id} is unavailable")
        if record.size_bytes > max_bytes:
            raise ValidationError(
                f"artifact {artifact_id} exceeds the {max_bytes}-byte read bound"
            )
        path = self.paths.artifacts / record.relative_path
        try:
            with path.open("rb") as stream:
                content = stream.read(max_bytes + 1)
        except OSError as exc:
            raise ValidationError(f"artifact {artifact_id} is unavailable") from exc
        if (
            len(content) != record.size_bytes
            or len(content) > max_bytes
            or hashlib.sha256(content).hexdigest() != record.sha256
        ):
            raise ValidationError(f"artifact {artifact_id} is unavailable")
        return content

    def artifact_path_for_session(self, session_id: str, artifact_id: str) -> Path:
        record = self.artifact_for_session(session_id, artifact_id)
        if not record.available:
            raise ValidationError(f"artifact {artifact_id} is unavailable")
        path = self.paths.artifacts / record.relative_path
        if not _artifact_file_matches(path, record.size_bytes, record.sha256):
            raise ValidationError(f"artifact {artifact_id} is unavailable")
        return path

    def _artifact_from_row(self, row: sqlite3.Row) -> ArtifactRecord:
        keys = set(row.keys())
        return ArtifactRecord(
            id=row["id"],
            publication_id=row["publication_id"] if "publication_id" in keys else None,
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            media_type=row["media_type"],
            relative_path=row["relative_path"],
            provenance=json_load(
                row["link_provenance_json"] if "link_provenance_json" in keys else row["provenance_json"],
                {},
            ),
            created_at=row["link_created_at"] if "link_created_at" in keys else row["created_at"],
            available=bool(row["available"]),
        )

    def backup_database(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self._connection.backup(target)
            finally:
                target.close()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_file_matches(path: Path, size_bytes: int, sha256: str) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size == size_bytes
            and _file_sha256(path) == sha256
        )
    except OSError:
        return False
