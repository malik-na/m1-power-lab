#!/usr/bin/env python3
"""Assemble a deterministic RAM-only native image from pinned local packages."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import stat
import sys
import tarfile
import tempfile


SCHEMA = "m1lab.native-bundle-lock.v1"
SOURCE_DIR = Path(__file__).resolve().parent


class BundleError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_entry(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BundleError("package lock entry must be an object")
    name, filename, digest, size = (value.get(key) for key in ("name", "filename", "sha256", "size_bytes"))
    if not isinstance(name, str) or not name or "/" in name:
        raise BundleError("package name is invalid")
    if not isinstance(filename, str) or filename != Path(filename).name or not filename.endswith(".pkg.tar.xz"):
        raise BundleError(f"package filename is invalid: {name}")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise BundleError(f"package SHA-256 is invalid: {name}")
    if type(size) is not int or size <= 0:
        raise BundleError(f"package size is invalid: {name}")
    return {"name": name, "filename": filename, "sha256": digest, "size_bytes": size}


def _load_lock(path: Path) -> dict[str, object]:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"cannot read bundle lock: {exc}") from exc
    if not isinstance(lock, dict) or lock.get("schema_version") != SCHEMA:
        raise BundleError("bundle lock schema is invalid")
    epoch, release, packages = (lock.get(key) for key in ("source_date_epoch", "kernel_release", "packages"))
    if type(epoch) is not int or not 0 <= epoch <= 0xFFFFFFFF:
        raise BundleError("source_date_epoch must fit the cpio timestamp field")
    if not isinstance(release, str) or not release or "/" in release or release in {".", ".."}:
        raise BundleError("kernel_release is invalid")
    if not isinstance(packages, list) or not packages:
        raise BundleError("runtime package list is empty")
    normalized = [_package_entry(item) for item in packages]
    names = [item["name"] for item in normalized]
    filenames = [item["filename"] for item in normalized]
    if len(names) != len(set(names)) or len(filenames) != len(set(filenames)):
        raise BundleError("duplicate runtime package in lock")
    if "filesystem" not in names or not {"python", "busybox", "kmod"}.issubset(names):
        raise BundleError("runtime lock must include filesystem, python, busybox, and kmod")
    return {
        "source_date_epoch": epoch,
        "kernel_release": release,
        "kernel": _package_entry(lock.get("kernel")),
        "packages": normalized,
    }


def _checked_package(path: Path, entry: dict[str, object]) -> None:
    if path.is_symlink() or not path.is_file():
        raise BundleError(f"package is missing or not a regular file: {path}")
    if path.name != entry["filename"] or path.stat().st_size != entry["size_bytes"]:
        raise BundleError(f"package filename or size differs from lock: {path.name}")
    if _sha256(path) != entry["sha256"]:
        raise BundleError(f"package SHA-256 differs from lock: {path.name}")


def _member_name(name: str) -> str:
    while name.startswith("./"):
        name = name[2:]
    name = name.rstrip("/")
    if name in {"", "."}:
        return ""
    parts = PurePosixPath(name).parts
    if name.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise BundleError(f"unsafe package path: {name}")
    return name


def _link_target(name: str, target: str) -> str:
    if not target or "\x00" in target:
        raise BundleError(f"invalid package link: {name}")
    base = posixpath.dirname(name)
    rooted = target.lstrip("/") if target.startswith("/") else posixpath.join(base, target)
    normalized = posixpath.normpath(rooted)
    if normalized == ".." or normalized.startswith("../"):
        raise BundleError(f"package link escapes rootfs: {name}")
    return posixpath.relpath(normalized, base or ".")


def _safe_parent(root: Path, name: str) -> Path:
    current = root
    for component in PurePosixPath(name).parts[:-1]:
        current /= component
        if current.is_symlink():
            raise BundleError(f"package path traverses a rootfs symlink: {name}")
        if current.exists() and not current.is_dir():
            raise BundleError(f"package path has a non-directory parent: {name}")
        current.mkdir(exist_ok=True)
    return current


def _install_package(package: Path, root: Path) -> None:
    try:
        with tarfile.open(package, "r:xz") as archive:
            for member in archive:
                name = _member_name(member.name)
                if not name or ("/" not in name and name.startswith(".")):
                    continue  # package manager metadata is not runtime content
                parent = _safe_parent(root, name)
                destination = parent / PurePosixPath(name).name
                if member.isdir():
                    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
                        raise BundleError(f"package directory collides with another entry: {name}")
                    destination.mkdir(exist_ok=True)
                elif member.issym():
                    target = _link_target(name, member.linkname)
                    if destination.is_symlink():
                        if os.readlink(destination) != target:
                            raise BundleError(f"package symlink conflicts with another entry: {name}")
                    elif destination.exists():
                        raise BundleError(f"package symlink collides with another entry: {name}")
                    else:
                        destination.symlink_to(target)
                elif member.isfile() or member.islnk():
                    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
                        raise BundleError(f"package file collides with another entry: {name}")
                    source = archive.extractfile(member)
                    if source is None:
                        raise BundleError(f"cannot read package file: {name}")
                    with source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(member.mode & 0o777)
                else:
                    raise BundleError(f"unsupported package entry type: {name}")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BundleError(f"cannot extract {package.name}: {exc}") from exc


def _rootfs_entries(root: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = [(".", root)]

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda path: path.name):
            name = child.relative_to(root).as_posix()
            entries.append((name, child))
            if child.is_dir() and not child.is_symlink():
                visit(child)

    visit(root)
    return sorted(entries, key=lambda item: item[0].encode("utf-8"))


def _pad(output, size: int) -> None:
    output.write(b"\0" * (-size % 4))


def _cpio_entry(output, name: str, path: Path | None, inode: int, epoch: int) -> None:
    if path is None:  # TRAILER!!!
        mode, size, links, data = 0, 0, 1, None
    else:
        info = path.lstat()
        mode = info.st_mode
        links = 2 if stat.S_ISDIR(mode) else 1
        if stat.S_ISREG(mode):
            size, data = info.st_size, None
        elif stat.S_ISLNK(mode):
            data = os.readlink(path).encode("utf-8")
            size = len(data)
        elif stat.S_ISDIR(mode):
            size, data = 0, None
        else:
            raise BundleError(f"unsupported rootfs entry: {name}")
    encoded = name.encode("utf-8") + b"\0"
    fields = (inode, mode, 0, 0, links, epoch, size, 0, 0, 0, 0, len(encoded), 0)
    if any(value < 0 or value > 0xFFFFFFFF for value in fields):
        raise BundleError(f"rootfs entry exceeds cpio newc bounds: {name}")
    output.write(b"070701" + b"".join(f"{value:08x}".encode("ascii") for value in fields))
    output.write(encoded)
    _pad(output, 110 + len(encoded))
    if data is not None:
        output.write(data)
    elif size and path is not None:
        with path.open("rb") as source:
            shutil.copyfileobj(source, output)
    _pad(output, size)


def _write_initramfs(root: Path, destination: Path, epoch: int) -> None:
    with destination.open("wb") as compressed:
        with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=epoch, compresslevel=9) as output:
            entries = _rootfs_entries(root)
            for inode, (name, path) in enumerate(entries, start=1):
                _cpio_entry(output, name, path, inode, epoch)
            _cpio_entry(output, "TRAILER!!!", None, len(entries) + 1, epoch)


def _write_payload(output: Path, files: list[Path], epoch: int) -> None:
    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
        for path in sorted(files, key=lambda item: item.name):
            info = tarfile.TarInfo(path.name)
            info.size = path.stat().st_size
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = epoch
            with path.open("rb") as source:
                archive.addfile(info, source)


def build(lock_path: Path, packages_dir: Path, kernel_package: Path, output_dir: Path) -> None:
    lock = _load_lock(lock_path)
    packages = lock["packages"]
    assert isinstance(packages, list)
    _checked_package(kernel_package, lock["kernel"])
    for entry in packages:
        _checked_package(packages_dir / str(entry["filename"]), entry)
    if output_dir.exists() or output_dir.is_symlink():
        raise BundleError("output directory already exists; use a clean output path")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    epoch = lock["source_date_epoch"]
    release = lock["kernel_release"]
    assert isinstance(epoch, int) and isinstance(release, str)
    with tempfile.TemporaryDirectory(prefix=".native-bundle-", dir=output_dir.parent) as temporary:
        stage = Path(temporary)
        inputs = stage / "inputs"
        inputs.mkdir()
        shutil.copyfile(lock_path, inputs / "native-image.lock.json")
        for entry in packages:
            filename = str(entry["filename"])
            shutil.copyfile(packages_dir / filename, inputs / filename)
        shutil.copyfile(kernel_package, inputs / kernel_package.name)
        with tarfile.open(kernel_package, "r:xz") as kernel_archive:
            for member_name in (".PKGINFO", ".BUILDINFO"):
                try:
                    member = kernel_archive.getmember(member_name)
                    source = kernel_archive.extractfile(member)
                except KeyError as exc:
                    raise BundleError(f"kernel package lacks {member_name}") from exc
                if source is None:
                    raise BundleError(f"kernel package {member_name} is not a file")
                with source, (inputs / f"kernel{member_name}").open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        root = stage / "rootfs"
        root.mkdir()
        by_name = {str(entry["name"]): entry for entry in packages}
        ordered = [by_name["filesystem"], *(by_name[name] for name in sorted(by_name) if name != "filesystem")]
        for entry in ordered:
            _install_package(packages_dir / str(entry["filename"]), root)
        _install_package(kernel_package, root)

        kernel_in_root = root / "usr" / "lib" / "modules" / release / "vmlinuz"
        dtb_in_root = root / "usr" / "lib" / "modules" / release / "dtbs" / "t8103-j313.dtb"
        if not kernel_in_root.is_file() or not dtb_in_root.is_file():
            raise BundleError("pinned kernel package lacks vmlinuz or t8103-j313.dtb")
        shutil.copyfile(kernel_in_root, stage / "Image")
        shutil.copyfile(dtb_in_root, stage / "j313.dtb")
        with (stage / "Image.gz").open("wb") as compressed:
            with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=epoch, compresslevel=9) as output:
                with (stage / "Image").open("rb") as source:
                    shutil.copyfileobj(source, output)

        source_map = {
            "native-init": ("init", "init"),
            "native_capture.py": ("usr/lib/m1lab/native_capture.py", "collector.py"),
            "native_boot.py": ("usr/lib/m1lab/native_boot.py", "native_boot.py"),
            "native_usb_trace.py": ("usr/lib/m1lab/native_usb_trace.py", "native_usb_trace.py"),
        }
        source_hashes = {}
        for source_name, (root_name, output_name) in source_map.items():
            source = SOURCE_DIR / source_name
            if not source.is_file() or source.is_symlink():
                raise BundleError(f"target source is missing: {source_name}")
            destination = root / root_name
            if destination.exists() or destination.is_symlink():
                raise BundleError(f"target source collides with package: {root_name}")
            _safe_parent(root, root_name)
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if source_name == "native-init" else 0o644)
            shutil.copyfile(source, stage / output_name)
            source_hashes[source_name] = _sha256(source)

        config_name = "etc/m1lab/image-config.json"
        _safe_parent(root, config_name)
        config = root / config_name
        if config.exists() or config.is_symlink():
            raise BundleError(f"image config collides with package: {config_name}")
        shutil.copyfile(inputs / "native-image.lock.json", config)
        config.chmod(0o644)

        _write_initramfs(root, stage / "initramfs.cpio.gz", epoch)
        output_names = ("Image", "Image.gz", "j313.dtb", "initramfs.cpio.gz", "collector.py", "native_boot.py", "native_usb_trace.py")
        metadata = {
            "schema_version": "m1lab.native-bundle.v1",
            "source_date_epoch": epoch,
            "kernel_release": release,
            "lock_sha256": _sha256(lock_path),
            "kernel_package": lock["kernel"],
            "runtime_packages": sorted(packages, key=lambda item: str(item["name"])),
            "source_sha256": source_hashes,
            "outputs_sha256": {name: _sha256(stage / name) for name in output_names},
        }
        (stage / "bundle-metadata.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        _write_payload(stage / "payload.tar", [stage / name for name in (*output_names, "bundle-metadata.json")], epoch)
        stage.rename(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--kernel-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.lock, args.packages, args.kernel_package, args.output)
    except (BundleError, OSError) as exc:
        print(f"native bundle: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
