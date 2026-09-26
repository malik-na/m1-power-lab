"""Approved artifact-store bundle mapping with tiny synthetic tar files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
from pathlib import Path
import tarfile

import pytest

from m1lab.adapters.native_bundle import NativeBundleError, NativeCandidateBundle
from m1lab.adapters.native_harness import (
    ManifestArtifact, NativeImageManifest, NativeLaunchManifest, encode_native_manifest,
)


_FILES = {
    "Image.gz": b"synthetic kernel bytes",
    "j313.dtb": b"synthetic device tree bytes",
    "initramfs.cpio.gz": b"synthetic RAM filesystem bytes",
}


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _store(root: Path, content: bytes) -> str:
    digest = _digest(content)
    path = root / digest[:2] / digest[2:4] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return digest


def _tar(members: list[tuple[str, bytes]] | None = None) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, content in (members if members is not None else [*_FILES.items(), ("collector.py", b"ignored")]):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def _bundle(
    root: Path, *, tar_bytes: bytes | None = None,
    output_limit_bytes: int = 4096, sample_count: int = 2,
    launch_image_sha256: str | None = None,
) -> dict:
    payload = tar_bytes if tar_bytes is not None else _tar()
    payload_digest = _store(root, payload)
    roles = {"Image.gz": "kernel", "j313.dtb": "dtb", "initramfs.cpio.gz": "initramfs"}
    outputs = tuple(
        ManifestArtifact(name=name, role=roles[name], sha256=_digest(content), size_bytes=len(content))
        for name, content in _FILES.items()
    ) + (ManifestArtifact(
        name="payload.tar", role="payload", sha256=payload_digest, size_bytes=len(payload),
    ),)
    image = NativeImageManifest(
        architecture="aarch64", source_commit="a" * 40, source_tree_clean=True,
        toolchain="synthetic fixture", toolchain_version="1", configuration_sha256="b" * 64,
        outputs=outputs, collector_sha256="c" * 64,
        maximum_runtime_seconds=300, maximum_output_bytes=524_288,
        return_behavior="synthetic fixture only",
    )
    image_digest = _store(root, encode_native_manifest(image))
    launch = NativeLaunchManifest(
        run_id="synthetic-run", image_manifest_sha256=image_digest,
        image_sha256=launch_image_sha256 or payload_digest,
        target_identity="synthetic-target", boot_epoch="synthetic-boot",
        configuration_sha256=image.configuration_sha256,
        parameters={"sample_count": sample_count, "sample_period_ms": 100},
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
        output_limit_bytes=output_limit_bytes, recovery_expectation="synthetic fixture only",
    )
    launch_digest = _store(root, encode_native_manifest(launch))
    return dict(
        artifact_root=root, image_manifest_sha256=image_digest,
        payload_sha256=payload_digest, launch_manifest_sha256=launch_digest,
    )


def test_stages_only_three_verified_boot_files_and_cleans_up(tmp_path):
    args = _bundle(tmp_path / "artifacts")
    with NativeCandidateBundle(**args) as bundle:
        assert bundle.image is not None and bundle.launch is not None
        assert bundle.launch.image_sha256 == args["payload_sha256"]
        paths = {"Image.gz": bundle.kernel, "j313.dtb": bundle.dtb,
                 "initramfs.cpio.gz": bundle.initramfs}
        assert {path.name for path in paths.values()} == set(_FILES)
        for name, path in paths.items():
            assert path.read_bytes() == _FILES[name]
        assert {item.name for item in bundle.kernel.parent.iterdir()} == set(_FILES)
        staged_dir = bundle.kernel.parent
    assert not staged_dir.exists()
    assert bundle.image is bundle.launch is bundle.kernel is bundle.dtb is bundle.initramfs is None


def test_tampered_or_symlinked_artifact_is_refused(tmp_path):
    args = _bundle(tmp_path / "artifacts")
    digest = args["payload_sha256"]
    path = args["artifact_root"] / digest[:2] / digest[2:4] / digest
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(NativeBundleError, match="digest"):
        with NativeCandidateBundle(**args):
            pass
    path.unlink()
    target = tmp_path / "untrusted.tar"
    target.write_bytes(_tar())
    path.symlink_to(target)
    with pytest.raises(NativeBundleError, match="regular"):
        with NativeCandidateBundle(**args):
            pass


def test_payload_digest_must_match_launch_and_image(tmp_path):
    args = _bundle(tmp_path / "artifacts", launch_image_sha256="0" * 64)
    with pytest.raises(ValueError, match="image digest"):
        with NativeCandidateBundle(**args):
            pass


def test_duplicate_tar_member_is_refused_and_staging_cleaned(tmp_path, monkeypatch):
    members = list(_FILES.items()) + [("Image.gz", b"second kernel")]
    args = _bundle(tmp_path / "artifacts", tar_bytes=_tar(members))
    import m1lab.adapters.native_bundle as native_bundle

    original = native_bundle.TemporaryDirectory
    directories = []

    def tracked(*args, **kwargs):
        temporary = original(*args, dir=tmp_path, **kwargs)
        directories.append(Path(temporary.name))
        return temporary

    monkeypatch.setattr(native_bundle, "TemporaryDirectory", tracked)
    with pytest.raises(NativeBundleError, match="duplicate"):
        with NativeCandidateBundle(**args):
            pass
    assert len(directories) == 1 and not directories[0].exists()


@pytest.mark.parametrize("kind", ["unsafe", "symlink"])
def test_unsafe_or_nonregular_boot_member_is_refused(tmp_path, kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, content in _FILES.items():
            if name == "Image.gz":
                if kind == "unsafe":
                    info = tarfile.TarInfo("../Image.gz")
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
                else:
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.SYMTYPE
                    info.linkname = "j313.dtb"
                    archive.addfile(info)
            else:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    args = _bundle(tmp_path / "artifacts", tar_bytes=stream.getvalue())
    with pytest.raises(NativeBundleError, match="unsafe|nonregular"):
        with NativeCandidateBundle(**args):
            pass


@pytest.mark.parametrize(
    ("limit", "samples"), [(262_145, 2), (4096, 121)],
)
def test_candidate_capture_limits_are_enforced_before_staging(tmp_path, limit, samples):
    args = _bundle(tmp_path / "artifacts", output_limit_bytes=limit, sample_count=samples)
    with pytest.raises(NativeBundleError, match="candidate"):
        with NativeCandidateBundle(**args):
            pass
