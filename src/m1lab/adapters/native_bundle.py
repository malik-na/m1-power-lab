"""Verify approved coordinator artifacts and stage one finite native boot bundle."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import tarfile
from tempfile import TemporaryDirectory
from typing import BinaryIO

from .native_harness import (
    MAX_NATIVE_MANIFEST_BYTES,
    NativeImageManifest,
    NativeLaunchManifest,
    decode_native_image_manifest,
    decode_native_launch_manifest,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BOOT_FILES = {"kernel": "Image.gz", "dtb": "j313.dtb", "initramfs": "initramfs.cpio.gz"}
_MAX_TAR_BYTES = 1 << 30
_MAX_FILE_BYTES = 512 << 20
_MAX_BOOT_BYTES = 1 << 30
_MAX_TAR_MEMBERS = 64


class NativeBundleError(ValueError):
    """An approved artifact or boot file is missing, changed, or unsafe."""


def _checked_artifact(root: Path, digest: str, maximum: int) -> BinaryIO:
    if not _SHA256.fullmatch(digest):
        raise NativeBundleError("approved artifact digest is invalid")
    first, second = root / digest[:2], root / digest[:2] / digest[2:4]
    for directory in (root, first, second):
        try:
            info = directory.lstat()
        except OSError as exc:
            raise NativeBundleError("artifact store directory is unavailable") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise NativeBundleError("artifact store path is not a real directory")
    path = second / digest
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise NativeBundleError("approved artifact is not a bounded regular file")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NativeBundleError("approved artifact is unavailable") from exc
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != info.st_ino
                or opened.st_dev != info.st_dev or opened.st_size != info.st_size):
            raise NativeBundleError("approved artifact changed during open")
        actual = hashlib.sha256()
        count = 0
        with os.fdopen(os.dup(fd), "rb") as stream:
            while block := stream.read(1 << 20):
                count += len(block)
                if count > maximum:
                    raise NativeBundleError("approved artifact exceeds its bound")
                actual.update(block)
        if count != info.st_size or actual.hexdigest() != digest:
            raise NativeBundleError("approved artifact content digest differs")
        os.lseek(fd, 0, os.SEEK_SET)
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


class NativeCandidateBundle:
    """One verified image, launch, and three private boot-file paths."""

    def __init__(
        self,
        artifact_root: Path,
        *,
        image_manifest_sha256: str,
        payload_sha256: str,
        launch_manifest_sha256: str,
    ) -> None:
        self.artifact_root = Path(artifact_root).expanduser().absolute()
        self.image_manifest_sha256 = image_manifest_sha256
        self.payload_sha256 = payload_sha256
        self.launch_manifest_sha256 = launch_manifest_sha256
        self.image: NativeImageManifest | None = None
        self.launch: NativeLaunchManifest | None = None
        self.kernel: Path | None = None
        self.dtb: Path | None = None
        self.initramfs: Path | None = None
        self._temporary: TemporaryDirectory[str] | None = None

    def __enter__(self) -> NativeCandidateBundle:
        if self._temporary is not None:
            raise NativeBundleError("candidate bundle is already staged")
        with _checked_artifact(self.artifact_root, self.image_manifest_sha256, MAX_NATIVE_MANIFEST_BYTES) as source:
            image = decode_native_image_manifest(source.read())
        with _checked_artifact(self.artifact_root, self.launch_manifest_sha256, MAX_NATIVE_MANIFEST_BYTES) as source:
            launch = decode_native_launch_manifest(source.read())
        if image.digest() != self.image_manifest_sha256:
            raise NativeBundleError("image manifest is not canonical")
        launch.validate_against_image(image)
        if launch.output_limit_bytes > 262_144:
            raise NativeBundleError("candidate launch output exceeds helper result bound")
        params = launch.parameters
        if (set(params) != {"sample_count", "sample_period_ms"}
                or type(params["sample_count"]) is not int
                or not 1 <= params["sample_count"] <= 120
                or type(params["sample_period_ms"]) is not int
                or not 100 <= params["sample_period_ms"] <= 60_000
                or params["sample_count"] * params["sample_period_ms"] > 3_600_000):
            raise NativeBundleError("candidate collector parameters exceed bounds")
        outputs = {}
        for item in image.outputs:
            if item.role in (*_BOOT_FILES, "payload"):
                if item.role in outputs:
                    raise NativeBundleError("image manifest has duplicate candidate roles")
                outputs[item.role] = item
        if set(outputs) != {*_BOOT_FILES, "payload"}:
            raise NativeBundleError("image manifest lacks required candidate outputs")
        if (outputs["payload"].name != "payload.tar"
                or outputs["payload"].sha256 != self.payload_sha256
                or launch.image_sha256 != self.payload_sha256):
            raise NativeBundleError("candidate payload digest does not match launch and image")
        if not 0 < outputs["payload"].size_bytes <= _MAX_TAR_BYTES:
            raise NativeBundleError("candidate payload size exceeds its bound")
        for role, name in _BOOT_FILES.items():
            if outputs[role].name != name or not 0 < outputs[role].size_bytes <= _MAX_FILE_BYTES:
                raise NativeBundleError("image manifest boot output name or size is invalid")
        if sum(outputs[role].size_bytes for role in _BOOT_FILES) > _MAX_BOOT_BYTES:
            raise NativeBundleError("candidate boot files exceed total bound")
        temporary = TemporaryDirectory(prefix="m1lab-native-bundle-")
        self._temporary = temporary
        try:
            with _checked_artifact(self.artifact_root, self.payload_sha256, _MAX_TAR_BYTES) as source:
                if os.fstat(source.fileno()).st_size != outputs["payload"].size_bytes:
                    raise NativeBundleError("candidate payload size differs from image manifest")
                self._stage_boot_files(source, Path(temporary.name), outputs)
            self.image, self.launch = image, launch
            self.kernel = Path(temporary.name) / _BOOT_FILES["kernel"]
            self.dtb = Path(temporary.name) / _BOOT_FILES["dtb"]
            self.initramfs = Path(temporary.name) / _BOOT_FILES["initramfs"]
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        temporary, self._temporary = self._temporary, None
        self.image = self.launch = None
        self.kernel = self.dtb = self.initramfs = None
        if temporary is not None:
            temporary.cleanup()

    @staticmethod
    def _stage_boot_files(source: BinaryIO, destination: Path, outputs: dict) -> None:
        seen: set[str] = set()
        required = set(_BOOT_FILES.values())
        try:
            with tarfile.open(fileobj=source, mode="r:") as archive:
                for index, member in enumerate(archive, start=1):
                    if index > _MAX_TAR_MEMBERS:
                        raise NativeBundleError("candidate tar contains too many members")
                    if (member.name != Path(member.name).name or member.name in {"", ".", ".."}
                            or member.name in seen or not member.isfile()):
                        raise NativeBundleError("candidate tar contains duplicate, unsafe, or nonregular member")
                    seen.add(member.name)
                    if member.name not in required:
                        continue
                    role = next(role for role, name in _BOOT_FILES.items() if name == member.name)
                    expected = outputs[role]
                    if member.size != expected.size_bytes:
                        raise NativeBundleError("candidate boot file size differs from image manifest")
                    input_stream = archive.extractfile(member)
                    if input_stream is None:
                        raise NativeBundleError("candidate boot file cannot be read")
                    digest = hashlib.sha256()
                    count = 0
                    with input_stream, (destination / member.name).open("xb") as output_stream:
                        while block := input_stream.read(1 << 20):
                            count += len(block)
                            if count > expected.size_bytes:
                                raise NativeBundleError("candidate boot file exceeds declared size")
                            digest.update(block)
                            output_stream.write(block)
                    if count != expected.size_bytes or digest.hexdigest() != expected.sha256:
                        raise NativeBundleError("candidate boot file digest differs from image manifest")
        except (OSError, tarfile.TarError) as exc:
            raise NativeBundleError("candidate payload tar cannot be read") from exc
        if not required.issubset(seen):
            raise NativeBundleError("candidate payload tar lacks boot files")
