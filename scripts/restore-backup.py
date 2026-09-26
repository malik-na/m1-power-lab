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
                _extract_member(archive, "m1lab.sqlite3", database)
                for item in manifest.get("artifacts", []):
                    digest = _digest(item.get("sha256"))
                    relative = item.get("relative_path") or f"{digest[:2]}/{digest[2:4]}/{digest}"
                    relative_path = PurePosixPath(relative)
                    if relative_path.is_absolute() or ".." in relative_path.parts:
                        raise SystemExit("backup contains an unsafe artifact path")
                    destination = artifact_root.joinpath(*relative_path.parts)
                    _extract_member(archive, f"artifacts/{relative}", destination)
                    if destination.stat().st_size != int(item["size_bytes"]):
                        raise SystemExit(f"artifact {item.get('id')} has the wrong size")
                    if _file_digest(destination) != digest:
                        raise SystemExit(f"artifact {item.get('id')} failed digest validation")

            _validate_database(database, artifact_root)
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
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _validate_database(database: Path, artifacts: Path) -> None:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise SystemExit(f"SQLite quick_check failed: {result}")
        rows = connection.execute(
            "SELECT id, sha256, size_bytes, relative_path FROM artifacts WHERE available=1"
        ).fetchall()
        for row in rows:
            path = artifacts / row["relative_path"]
            if not path.is_file() or path.stat().st_size != row["size_bytes"]:
                raise SystemExit(f"database artifact {row['id']} is absent or has the wrong size")
            if _file_digest(path) != row["sha256"]:
                raise SystemExit(f"database artifact {row['id']} failed digest validation")
    finally:
        connection.close()


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
