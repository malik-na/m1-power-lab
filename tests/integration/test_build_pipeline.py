"""Host acceptance for the public, session-linked build runner.

The fixture builds text files in a disposable Git repository. It does not
create an M1 image or exercise the hardware, service, or model runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from m1lab.adapters.native_harness import decode_native_image_manifest
from m1lab.builds import BuildCommand, BuildError, BuildFile, BuildRecipe, build_and_publish
from m1lab.core.errors import NotFoundError
from m1lab.core.models import CommandKind, OwnerCommand, SessionCreate


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    ).stdout.strip()


@pytest.fixture
def source_repository(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Build Test")
    _git(source, "config", "user.email", "build@example.invalid")
    (source / "config.txt").write_text("revision one\n")
    (source / "rootfs.txt").write_text("fixture root filesystem\n")
    (source / "make_outputs.py").write_text(
        "from pathlib import Path\n"
        "from os import environ\n"
        "config = Path('config.txt').read_bytes()\n"
        "rootfs = Path('rootfs.txt').read_bytes()\n"
        "for name in ('kernel', 'dtb', 'initramfs', 'collector', 'payload'):\n"
        "    Path(name + '.bin').write_bytes(name.encode() + b':' + config + rootfs + environ['SOURCE_DATE_EPOCH'].encode())\n"
    )
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "fixture source")
    return source


@pytest.fixture
def active_session(core):
    session = core.create_session(
        SessionCreate(
            objective="Verify host build publication",
            owner="build-test",
            host_identity="test-host",
            active_seconds=60,
        )
    )
    result = core.submit(
        OwnerCommand(
            session_id=session.id,
            owner=session.owner,
            kind=CommandKind.START,
            expected_revision=session.revision,
        )
    )
    assert result.status == "applied"
    return session.id


def _recipe(*, command: BuildCommand | None = None) -> BuildRecipe:
    return BuildRecipe(
        recipe_id="host-fixture-v1",
        architecture="host-test-only",
        commands=(command or BuildCommand(("/usr/bin/python3", "make_outputs.py")),),
        tools=(BuildCommand(("/usr/bin/python3", "--version")),),
        configuration=BuildFile("config.txt", "configuration", "config.txt", "text/plain"),
        inputs=(BuildFile("rootfs.txt", "rootfs", "rootfs.txt", "text/plain"),),
        outputs=tuple(
            BuildFile(name + ".bin", name, name + ".bin")
            for name in ("kernel", "dtb", "initramfs", "collector", "payload")
        ),
        firmware_references=("test firmware reference only",),
        dependencies=("fixture source",),
        maximum_runtime_seconds=10,
    )


def _assert_worktree_clean(source: Path, workspace: Path) -> None:
    assert len(_git(source, "worktree", "list", "--porcelain").split("worktree ")) == 2
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize("dirty", [False, True])
def test_build_publishes_exact_source_and_immutable_session_artifacts(
    core, tmp_path: Path, source_repository: Path, active_session: str, dirty: bool
) -> None:
    source = source_repository
    commit = _git(source, "rev-parse", "HEAD")
    if dirty:
        (source / "config.txt").write_text("revision two\n")
    diff = subprocess.run(
        ["git", "-C", str(source), "diff", "--binary", "HEAD", "--"],
        check=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    ).stdout
    workspace = tmp_path / "builds"

    publication = build_and_publish(
        core, active_session, source, workspace, _recipe(), build_role="candidate"
    )

    manifest = publication.manifest
    assert manifest == decode_native_image_manifest(
        core.read_session_artifact(active_session, publication.manifest_artifact.id)
    )
    assert manifest.source_commit == commit
    assert manifest.source_tree_clean is (not dirty)
    assert manifest.source_diff_sha256 == (hashlib.sha256(diff).hexdigest() if dirty else None)
    assert manifest.configuration_sha256 == hashlib.sha256(
        (source / "config.txt").read_bytes()
    ).hexdigest()
    assert "executable_sha256=" in manifest.toolchain_version
    assert {item.role for item in manifest.outputs} == {
        "kernel", "dtb", "initramfs", "collector", "payload"
    }
    assert len(publication.artifacts) == 8 + int(dirty)
    by_role = {item.provenance["role"]: item for item in publication.artifacts}
    assert set(by_role) == {
        "build_recipe", "configuration", "rootfs", "kernel", "dtb",
        "initramfs", "collector", "payload", *(["source_diff"] if dirty else []),
    }
    for record in (*publication.artifacts, publication.manifest_artifact):
        assert record.provenance["session_id"] == active_session
        assert record.provenance["build_id"] == publication.build_id
        assert record.provenance["build_role"] == "candidate"
        content = core.read_session_artifact(active_session, record.id)
        assert record.sha256 == hashlib.sha256(content).hexdigest()
        assert record.size_bytes == len(content)
    assert json.loads(core.read_session_artifact(active_session, by_role["build_recipe"].id))[
        "recipe_id"
    ] == "host-fixture-v1"
    if dirty:
        assert core.read_session_artifact(active_session, by_role["source_diff"].id) == diff
    for entry in (*manifest.inputs, *manifest.outputs):
        record = by_role[entry.role]
        assert (record.sha256, record.size_bytes) == (entry.sha256, entry.size_bytes)
    expected_payload = (
        b"payload:"
        + (source / "config.txt").read_bytes()
        + (source / "rootfs.txt").read_bytes()
        + _git(source, "show", "-s", "--format=%ct", commit).encode()
    )
    payload_record = by_role["payload"]
    assert core.read_session_artifact(active_session, payload_record.id) == expected_payload
    (source / "config.txt").write_text("source changed after publication\n")
    assert core.read_session_artifact(active_session, payload_record.id) == expected_payload
    other = core.create_session(
        SessionCreate(objective="Unrelated", owner="other", host_identity="test-host")
    )
    with pytest.raises(NotFoundError, match="not published in session"):
        core.read_session_artifact(other.id, payload_record.id)
    assert len(core.artifacts(active_session, record_type="native_build_artifact")) == len(
        publication.artifacts
    ) + 1
    _assert_worktree_clean(source, workspace)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (BuildCommand(("/usr/bin/false",)), "exited with status"),
        (BuildCommand(("/usr/bin/sleep", "3"), timeout_seconds=1), "time bound"),
    ],
)
def test_failed_or_timed_out_build_leaves_no_publication_or_worktree(
    core,
    tmp_path: Path,
    source_repository: Path,
    active_session: str,
    command: BuildCommand,
    message: str,
) -> None:
    workspace = tmp_path / "builds"
    with pytest.raises(BuildError, match=message):
        build_and_publish(
            core, active_session, source_repository, workspace, _recipe(command=command),
            build_role="candidate",
        )
    assert core.artifacts(active_session, record_type="native_build_artifact") == []
    _assert_worktree_clean(source_repository, workspace)
