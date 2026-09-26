#!/usr/bin/env python3
"""Verify and restore an m1lab backup bundle while the coordinator is stopped."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
import zipfile

JOURNAL_DISK_RESERVE_BYTES = 512 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("data_root", type=Path)
    args = parser.parse_args()
    restore(args.bundle.resolve(), args.data_root.resolve())


def restore(bundle: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "coordinator.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("coordinator is running; stop it before restoring") from exc

        with tempfile.TemporaryDirectory(prefix=".m1lab-restore-", dir=root.parent) as temporary:
            stage = Path(temporary)
            database = stage / "m1lab.sqlite3"
            artifact_root = stage / "artifacts"
            artifact_root.mkdir()
            with zipfile.ZipFile(bundle) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise SystemExit("backup contains duplicate archive members")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("format") != "m1lab-backup-v1":
                    raise SystemExit("unsupported backup format")
                manifest_artifacts = manifest.get("artifacts")
                if not isinstance(manifest_artifacts, list):
                    raise SystemExit("backup artifact manifest is invalid")
                _validate_manifest_artifacts(manifest_artifacts)
                expected_names = {
                    "manifest.json",
                    "m1lab.sqlite3",
                    *(f"artifacts/{item['relative_path']}" for item in manifest_artifacts),
                }
                if set(names) != expected_names:
                    raise SystemExit("backup archive members do not match its manifest")
                required_bytes = sum(
                    archive.getinfo(name).file_size
                    for name in expected_names
                    if name != "manifest.json"
                )
                free_bytes = shutil.disk_usage(root.parent).free
                if free_bytes - required_bytes < JOURNAL_DISK_RESERVE_BYTES:
                    raise SystemExit(
                        "restore stopped to preserve the disk reserve "
                        f"({free_bytes} bytes free; "
                        f"{required_bytes + JOURNAL_DISK_RESERVE_BYTES} bytes required)"
                    )
                _extract_member(archive, "m1lab.sqlite3", database)
                for item in manifest_artifacts:
                    digest = _digest(item.get("sha256"))
                    relative = item["relative_path"]
                    archive_info = archive.getinfo(f"artifacts/{relative}")
                    if archive_info.file_size != item["size_bytes"]:
                        raise SystemExit(
                            f"artifact {item.get('id')} has the wrong archive size"
                        )
                    relative_path = PurePosixPath(relative)
                    if relative_path.is_absolute() or ".." in relative_path.parts:
                        raise SystemExit("backup contains an unsafe artifact path")
                    destination = artifact_root.joinpath(*relative_path.parts)
                    _extract_member(archive, f"artifacts/{relative}", destination)
                    if destination.stat().st_size != int(item["size_bytes"]):
                        raise SystemExit(f"artifact {item.get('id')} has the wrong size")
                    if _file_digest(destination) != digest:
                        raise SystemExit(f"artifact {item.get('id')} failed digest validation")

            _validate_database(database, artifact_root, manifest_artifacts)
            database.chmod(0o600)
            artifact_root.chmod(0o700)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            previous = root / f"restore-previous-{stamp}"
            previous.mkdir()
            moved: list[tuple[Path, Path]] = []
            installed: list[Path] = []
            try:
                for name in ("m1lab.sqlite3", "m1lab.sqlite3-wal", "m1lab.sqlite3-shm", "artifacts"):
                    current = root / name
                    if current.exists():
                        saved = previous / name
                        os.replace(current, saved)
                        moved.append((saved, current))
                os.replace(database, root / "m1lab.sqlite3")
                installed.append(root / "m1lab.sqlite3")
                os.replace(artifact_root, root / "artifacts")
                installed.append(root / "artifacts")
            except BaseException:
                for current in reversed(installed):
                    if current.is_dir():
                        shutil.rmtree(current)
                    else:
                        current.unlink(missing_ok=True)
                for saved, current in reversed(moved):
                    if not current.exists() and saved.exists():
                        os.replace(saved, current)
                raise
    print(json.dumps({"restored": str(bundle), "data_root": str(root), "previous": str(previous)}))


def _extract_member(archive: zipfile.ZipFile, name: str, destination: Path) -> None:
    try:
        source = archive.open(name)
    except KeyError as exc:
        raise SystemExit(f"backup is missing {name}") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source, destination.open("xb") as target:
        os.fchmod(target.fileno(), 0o600)
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _validate_database(
    database: Path, artifacts: Path, manifest_artifacts: list[dict[str, object]]
) -> None:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise SystemExit(f"SQLite quick_check failed: {result}")
        rows = connection.execute(
            "SELECT id, sha256, size_bytes, relative_path, available FROM artifacts"
        ).fetchall()
        manifest_by_id = {str(item["id"]): item for item in manifest_artifacts}
        if len(manifest_by_id) != len(manifest_artifacts):
            raise SystemExit("backup manifest contains duplicate artifact IDs")
        if len(rows) != len(manifest_artifacts):
            raise SystemExit("backup manifest does not cover every database artifact")
        dangling = connection.execute(
            "SELECT COUNT(*) FROM artifact_links l LEFT JOIN artifacts a "
            "ON a.id=l.artifact_id WHERE a.id IS NULL"
        ).fetchone()[0]
        if dangling:
            raise SystemExit("database contains artifact links without artifact metadata")
        for row in rows:
            manifest = manifest_by_id.get(row["id"])
            if not row["available"]:
                raise SystemExit(f"database artifact {row['id']} was unavailable at backup")
            if manifest is None or any(
                manifest[field] != row[field]
                for field in ("sha256", "size_bytes", "relative_path")
            ):
                raise SystemExit(f"backup manifest disagrees with artifact {row['id']}")
            path = artifacts / row["relative_path"]
            if not path.is_file() or path.stat().st_size != row["size_bytes"]:
                raise SystemExit(f"database artifact {row['id']} is absent or has the wrong size")
            if _file_digest(path) != row["sha256"]:
                raise SystemExit(f"database artifact {row['id']} failed digest validation")
    finally:
        connection.close()


def _validate_manifest_artifacts(items: list[object]) -> None:
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    for value in items:
        if not isinstance(value, dict):
            raise SystemExit("backup artifact manifest entry is invalid")
        digest = _digest(value.get("sha256"))
        expected_id = f"artifact_{digest}"
        expected_path = f"{digest[:2]}/{digest[2:4]}/{digest}"
        if (
            value.get("id") != expected_id
            or value.get("relative_path") != expected_path
            or type(value.get("size_bytes")) is not int
            or value["size_bytes"] < 0
        ):
            raise SystemExit("backup artifact metadata is inconsistent")
        if expected_id in seen_ids or expected_path in seen_paths:
            raise SystemExit("backup manifest contains duplicate artifacts")
        seen_ids.add(expected_id)
        seen_paths.add(expected_path)


def _digest(value: object) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SystemExit("backup contains an invalid SHA-256 digest")
    return text


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
