"""Bounded, reproducible build execution and session-linked publication.

Build recipes are explicit typed data owned by the application configuration;
they are never accepted from a model proposal or a hardware request. Commands
run with ``shell=False`` in a detached worktree and a fresh allowlisted
environment. This module builds and records artifacts but never dispatches
them to a target.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Literal
from uuid import uuid4

from m1lab.adapters.native_harness import (
    ManifestArtifact,
    NativeImageManifest,
    encode_native_manifest,
)
from m1lab.core import ArtifactRecord, CoreApp
from m1lab.core.models import ACTIVE_PHASES


MAX_BUILD_PATCH_BYTES = 16 * 1_048_576
MAX_BUILD_ARTIFACT_BYTES = 2 * 1_024 * 1_024 * 1_024
MAX_BUILD_TOTAL_BYTES = 4 * 1_024 * 1_024 * 1_024
MAX_BUILD_LOG_BYTES = 2 * 1_048_576
MAX_BUILD_RECIPE_BYTES = 256 * 1024
MAX_RECIPE_COMMANDS = 32
MAX_RECIPE_SECONDS = 3 * 60 * 60


class BuildError(ValueError):
    """A build source, command, artifact, or publication failed closed."""


@dataclass(frozen=True, slots=True)
class BuildCommand:
    argv: tuple[str, ...]
    timeout_seconds: int = 3600
    working_directory: str = "."

    def __post_init__(self) -> None:
        if isinstance(self.argv, (str, bytes)):
            raise ValueError("build command arguments must be a sequence of argument strings")
        object.__setattr__(self, "argv", tuple(self.argv))
        if not self.argv or len(self.argv) > 128:
            raise ValueError("build command must contain 1..128 arguments")
        if any(not isinstance(item, str) or not item or "\x00" in item or len(item) > 4096 for item in self.argv):
            raise ValueError("build command arguments must be non-empty bounded strings")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= MAX_RECIPE_SECONDS:
            raise ValueError("build command timeout is outside the supported bound")
        _relative_path(self.working_directory, allow_dot=True)


@dataclass(frozen=True, slots=True)
class BuildFile:
    name: str
    role: str
    path: str
    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name
            or len(self.name) > 160
            or not isinstance(self.role, str)
            or not self.role
            or len(self.role) > 80
        ):
            raise ValueError("build file name and role must be bounded non-empty strings")
        if not isinstance(self.media_type, str) or not self.media_type or len(self.media_type) > 160:
            raise ValueError("build file media type is invalid")
        _relative_path(self.path)


@dataclass(frozen=True, slots=True)
class BuildRecipe:
    recipe_id: str
    architecture: str
    commands: tuple[BuildCommand, ...]
    tools: tuple[BuildCommand, ...]
    configuration: BuildFile
    inputs: tuple[BuildFile, ...]
    outputs: tuple[BuildFile, ...]
    firmware_references: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    toolchain_search_paths: tuple[Path, ...] = (Path("/usr/bin"), Path("/bin"))
    maximum_runtime_seconds: int = 3600
    maximum_output_bytes: int = 16 * 1_048_576
    return_behavior: str = "No target execution is performed by the build pipeline."

    def __post_init__(self) -> None:
        for name in (
            "commands",
            "tools",
            "inputs",
            "outputs",
            "firmware_references",
            "dependencies",
            "toolchain_search_paths",
        ):
            if isinstance(getattr(self, name), (str, bytes)):
                raise ValueError(f"build recipe {name} must be a sequence")
        for name in (
            "commands",
            "tools",
            "inputs",
            "outputs",
            "firmware_references",
            "dependencies",
            "toolchain_search_paths",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not isinstance(self.recipe_id, str) or not self.recipe_id or len(self.recipe_id) > 128:
            raise ValueError("build recipe ID is invalid")
        if not isinstance(self.architecture, str) or not self.architecture or len(self.architecture) > 80:
            raise ValueError("build architecture is invalid")
        if not self.commands or len(self.commands) > MAX_RECIPE_COMMANDS:
            raise ValueError("build recipe requires 1..32 fixed commands")
        if not self.tools or len(self.tools) > 32:
            raise ValueError("build recipe requires 1..32 tool version commands")
        if not self.outputs or len(self.outputs) > 64:
            raise ValueError("build recipe requires 1..64 output artifacts")
        if any(not isinstance(item, BuildCommand) for item in (*self.commands, *self.tools)):
            raise ValueError("build commands and tool versions must be typed BuildCommand values")
        if not isinstance(self.configuration, BuildFile) or any(
            not isinstance(item, BuildFile) for item in (*self.inputs, *self.outputs)
        ):
            raise ValueError("build inputs and outputs must be typed BuildFile values")
        if len(self.inputs) > 128 or len(self.dependencies) > 127 or len(self.firmware_references) > 128:
            raise ValueError("build recipe has too many inputs, dependencies, or firmware references")
        if not self.firmware_references:
            raise ValueError("build recipe must declare the target firmware references")
        if type(self.maximum_runtime_seconds) is not int or not 1 <= self.maximum_runtime_seconds <= MAX_RECIPE_SECONDS:
            raise ValueError("build runtime bound is invalid")
        if type(self.maximum_output_bytes) is not int or not 1 <= self.maximum_output_bytes <= 16 * 1_048_576:
            raise ValueError("native result output bound is invalid")
        if not isinstance(self.return_behavior, str) or not self.return_behavior or len(self.return_behavior) > 512:
            raise ValueError("build return behavior must be documented")
        if self.configuration.role != "configuration":
            raise ValueError("build configuration file must use the configuration role")
        names = [item.name for item in (*self.inputs, *self.outputs, self.configuration)]
        if len(names) != len(set(names)):
            raise ValueError("build artifact names must be unique")
        if {"build_recipe.json", "source_diff.patch"}.intersection(names):
            raise ValueError("build artifact names use a reserved provenance filename")
        required_outputs = {"kernel", "dtb", "initramfs", "collector", "payload"}
        output_roles = {item.role for item in self.outputs}
        if len(output_roles) != len(self.outputs):
            raise ValueError("each native build output must have a unique role")
        if not required_outputs.issubset(output_roles):
            raise ValueError("build outputs must include kernel, dtb, initramfs, collector, and payload")
        if not any(item.role in {"rootfs", "root_filesystem"} for item in (*self.inputs, *self.outputs)):
            raise ValueError("build recipe must record a root filesystem input or output")
        for path in self.toolchain_search_paths:
            if not isinstance(path, Path) or not path.is_absolute() or not path.is_dir():
                raise ValueError("toolchain search paths must be existing absolute directories")
        for value in (*self.dependencies, *self.firmware_references):
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError("dependency and firmware references must be bounded strings")


@dataclass(frozen=True, slots=True)
class NativeBuildPublication:
    build_id: str
    build_role: Literal["known_good", "candidate"]
    manifest: NativeImageManifest
    manifest_artifact: ArtifactRecord
    artifacts: tuple[ArtifactRecord, ...]


def load_build_recipe(path: Path) -> BuildRecipe:
    """Load a strict local recipe document with no duplicate or extra keys."""

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise BuildError(f"could not read build recipe: {exc}") from exc
    if not content or len(content) > MAX_BUILD_RECIPE_BYTES:
        raise BuildError("build recipe is empty or exceeds its size bound")
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise BuildError(f"build recipe is not valid strict JSON: {exc}") from exc
    required = {
        "schema_version",
        "recipe_id",
        "architecture",
        "commands",
        "tools",
        "configuration",
        "inputs",
        "outputs",
        "firmware_references",
    }
    allowed = required | {
        "firmware_references",
        "dependencies",
        "toolchain_search_paths",
        "maximum_runtime_seconds",
        "maximum_output_bytes",
        "return_behavior",
    }
    if not isinstance(document, dict) or not required.issubset(document) or set(document) - allowed:
        raise BuildError("build recipe has unknown or missing top-level fields")
    if document["schema_version"] != "m1lab.build-recipe.v1":
        raise BuildError("unsupported build recipe schema version")
    try:
        commands = tuple(_decode_build_command(item) for item in _expect_list(document, "commands"))
        tools = tuple(_decode_build_command(item) for item in _expect_list(document, "tools"))
        inputs = tuple(_decode_build_file(item) for item in _expect_list(document, "inputs"))
        outputs = tuple(_decode_build_file(item) for item in _expect_list(document, "outputs"))
        configuration = _decode_build_file(document["configuration"])
        firmware = _expect_optional_string_list(document, "firmware_references")
        dependencies = _expect_optional_string_list(document, "dependencies")
        search_paths = document.get("toolchain_search_paths", ["/usr/bin", "/bin"])
        if not isinstance(search_paths, list) or any(not isinstance(item, str) for item in search_paths):
            raise BuildError("toolchain_search_paths must be an array of absolute paths")
        return BuildRecipe(
            recipe_id=document["recipe_id"],
            architecture=document["architecture"],
            commands=commands,
            tools=tools,
            configuration=configuration,
            inputs=inputs,
            outputs=outputs,
            firmware_references=firmware,
            dependencies=dependencies,
            toolchain_search_paths=tuple(Path(_restore_recipe_text(item)) for item in search_paths),
            maximum_runtime_seconds=document.get("maximum_runtime_seconds", 3600),
            maximum_output_bytes=document.get("maximum_output_bytes", 16 * 1_048_576),
            return_behavior=_restore_recipe_text(
                document.get(
                    "return_behavior", "No target execution is performed by the build pipeline."
                )
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, BuildError):
            raise
        raise BuildError(f"build recipe fields are invalid: {exc}") from exc


def build_and_publish(
    core: CoreApp,
    session_id: str,
    source_repository: Path,
    workspace: Path,
    recipe: BuildRecipe,
    *,
    build_role: Literal["known_good", "candidate"],
) -> NativeBuildPublication:
    """Build a pinned source snapshot and publish all source/output evidence.

    The caller provides an application-owned recipe, never model-supplied
    commands. Dirty tracked changes are captured as a binary patch artifact;
    untracked files and dirty submodules are rejected because they cannot be
    reproduced from the recorded diff.
    """

    if not isinstance(build_role, str) or build_role not in {"known_good", "candidate"}:
        raise ValueError("build_role must be known_good or candidate")
    budget_started = time.monotonic()
    core.session(session_id)
    snapshot = core.snapshot(session_id)
    if snapshot.session.phase not in ACTIVE_PHASES:
        raise BuildError("target builds require an active investigation phase")
    if not snapshot.budget.admission_open:
        raise BuildError("session budget admission is closed: " + "; ".join(snapshot.budget.blockers))
    available_seconds = int(snapshot.budget.active_seconds_remaining)
    maximum_seconds = min(recipe.maximum_runtime_seconds, available_seconds)
    if maximum_seconds <= 0:
        raise BuildError("session has no remaining active-time allowance for a build")
    repository = _git_output(source_repository, ["rev-parse", "--show-toplevel"]).decode().strip()
    repository_path = Path(repository).resolve(strict=True)
    commit = _git_output(repository_path, ["rev-parse", "HEAD"]).decode().strip()
    if len(commit) not in (40, 64) or any(char not in "0123456789abcdef" for char in commit):
        raise BuildError("source repository returned an invalid commit ID")
    status = _git_output(repository_path, ["status", "--porcelain=v1", "--untracked-files=all"]).decode()
    if any(line.startswith("??") for line in status.splitlines()):
        raise BuildError("untracked source files are not reproducible build inputs")
    if (repository_path / ".gitmodules").is_file():
        raise BuildError("repositories with submodules need an explicit pinned dependency recipe")
    patch = _git_output(repository_path, ["diff", "--binary", "HEAD", "--"])
    if len(patch) > MAX_BUILD_PATCH_BYTES:
        raise BuildError("source diff exceeds the reproducible build patch bound")
    if (
        _git_output(repository_path, ["rev-parse", "HEAD"]).decode().strip() != commit
        or _git_output(repository_path, ["status", "--porcelain=v1", "--untracked-files=all"]).decode() != status
        or _git_output(repository_path, ["diff", "--binary", "HEAD", "--"]) != patch
    ):
        raise BuildError("source repository changed while its build snapshot was being captured")

    work_root = workspace.expanduser().absolute()
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work_root.is_symlink() or not work_root.is_dir() or work_root.stat().st_uid != os.getuid():
        raise BuildError("build work root must be a real directory owned by the current user")
    if shutil.disk_usage(work_root).free < MAX_BUILD_TOTAL_BYTES + 512 * 1_048_576:
        raise BuildError("build work root lacks space for bounded outputs and cleanup reserve")
    core.journal.ensure_artifact_capacity(additional_bytes=MAX_BUILD_TOTAL_BYTES)
    build_id = f"build_{uuid4().hex}"
    session_inputs: list[ArtifactRecord] = []
    session_outputs: list[ArtifactRecord] = []
    pending_artifacts: list[tuple[str, str, bytes | Path, str, int, str]] = []
    input_manifest: list[ManifestArtifact] = []
    output_manifest: list[ManifestArtifact] = []
    total_artifact_bytes = 0
    config_digest: str | None = None
    collector_digest: str | None = None
    total_deadline = budget_started + maximum_seconds
    with tempfile.TemporaryDirectory(prefix=f"{build_id}_", dir=work_root) as temporary:
        worktree = Path(temporary) / "src"
        worktree_added = False
        try:
            _git_output(repository_path, ["worktree", "add", "--detach", str(worktree), commit])
            worktree_added = True
            if patch:
                _git_input(worktree, ["apply", "--binary", "-"], patch)
            epoch = int(_git_output(repository_path, ["show", "-s", "--format=%ct", commit]).decode().strip())
            environment = _build_environment(recipe, Path(temporary), epoch)
            tool_versions: list[str] = []
            tool_digests: list[tuple[Path, str]] = []
            for tool in recipe.tools:
                executable = _resolve_tool(tool.argv[0], environment["PATH"])
                executable_digest = _file_sha256(executable)
                output = _run_command(core, session_id, worktree, tool, environment, total_deadline)
                version_lines = output.decode("utf-8", "replace").splitlines()
                version = version_lines[0] if version_lines else ""
                tool_versions.append(
                    f"{Path(tool.argv[0]).name}: {_redact_build_paths(version)[:512]} "
                    f"executable_sha256={executable_digest}"
                )
                tool_digests.append((executable, executable_digest))
            for command in recipe.commands:
                _run_command(core, session_id, worktree, command, environment, total_deadline)

            resulting_commit = _git_output(worktree, ["rev-parse", "HEAD"]).decode().strip()
            resulting_patch = _git_output(worktree, ["diff", "--binary", "HEAD", "--"])
            if resulting_commit != commit or resulting_patch != patch:
                raise BuildError("build commands changed tracked source or the worktree commit")
            if any(_file_sha256(path) != digest for path, digest in tool_digests):
                raise BuildError("a toolchain executable changed while the build was running")
            _require_active_build_session(core, session_id, total_deadline)
            if patch:
                total_artifact_bytes = _check_build_size(total_artifact_bytes, len(patch))
                pending_artifacts.append((
                    "source_diff.patch",
                    "source_diff",
                    patch,
                    hashlib.sha256(patch).hexdigest(),
                    len(patch),
                    "application/vnd.git-patch",
                ))
                input_manifest.append(_manifest_artifact("source_diff.patch", "source_diff", patch))

            recipe_bytes = _recipe_bytes(recipe)
            total_artifact_bytes = _check_build_size(total_artifact_bytes, len(recipe_bytes))
            pending_artifacts.append((
                "build_recipe.json",
                "build_recipe",
                recipe_bytes,
                hashlib.sha256(recipe_bytes).hexdigest(),
                len(recipe_bytes),
                "application/json",
            ))
            input_manifest.append(_manifest_artifact("build_recipe.json", "build_recipe", recipe_bytes))

            for item in (recipe.configuration, *recipe.inputs):
                _require_active_build_session(core, session_id, total_deadline)
                artifact_path, artifact_size, artifact_digest = _describe_build_file(worktree, item.path)
                total_artifact_bytes = _check_build_size(total_artifact_bytes, artifact_size)
                pending_artifacts.append((
                    item.name,
                    item.role,
                    artifact_path,
                    artifact_digest,
                    artifact_size,
                    item.media_type,
                ))
                entry = ManifestArtifact(
                    name=item.name,
                    role=item.role,
                    sha256=artifact_digest,
                    size_bytes=artifact_size,
                )
                input_manifest.append(entry)
                if item is recipe.configuration:
                    config_digest = artifact_digest

            for item in recipe.outputs:
                _require_active_build_session(core, session_id, total_deadline)
                artifact_path, artifact_size, artifact_digest = _describe_build_file(worktree, item.path)
                total_artifact_bytes = _check_build_size(total_artifact_bytes, artifact_size)
                pending_artifacts.append((
                    item.name,
                    item.role,
                    artifact_path,
                    artifact_digest,
                    artifact_size,
                    item.media_type,
                ))
                entry = ManifestArtifact(
                    name=item.name,
                    role=item.role,
                    sha256=artifact_digest,
                    size_bytes=artifact_size,
                )
                output_manifest.append(entry)
                if item.role == "collector":
                    collector_digest = artifact_digest

            if config_digest is None or collector_digest is None:
                raise BuildError("build recipe did not produce configuration and collector evidence")
            if time.monotonic() > total_deadline:
                raise BuildError("build exceeded its total runtime bound")
            manifest = NativeImageManifest(
                architecture=recipe.architecture,
                source_commit=commit,
                source_tree_clean=not bool(patch),
                source_diff_sha256=hashlib.sha256(patch).hexdigest() if patch else None,
                toolchain="; ".join(Path(tool.argv[0]).name for tool in recipe.tools),
                toolchain_version="\n".join(tool_versions),
                configuration_sha256=config_digest,
                firmware_references=recipe.firmware_references,
                dependencies=tuple((*recipe.dependencies, f"m1lab-recipe:{recipe.recipe_id}")),
                inputs=tuple(input_manifest),
                outputs=tuple(output_manifest),
                collector_sha256=collector_digest,
                maximum_runtime_seconds=recipe.maximum_runtime_seconds,
                maximum_output_bytes=recipe.maximum_output_bytes,
                return_behavior=recipe.return_behavior,
            )
            encoded_manifest = encode_native_manifest(manifest)
            _require_active_build_session(core, session_id, total_deadline)
            for name, role, content, digest, size_bytes, media_type in pending_artifacts:
                _require_active_build_session(core, session_id, total_deadline)
                provenance = _build_provenance(session_id, build_id, build_role, role)
                if isinstance(content, Path):
                    record = core.publish_artifact_file(
                        content,
                        expected_sha256=digest,
                        expected_size=size_bytes,
                        max_bytes=MAX_BUILD_ARTIFACT_BYTES,
                        media_type=media_type,
                        provenance=provenance,
                    )
                else:
                    record = _publish_bytes(
                        core, session_id, build_id, build_role, role, content, media_type
                    )
                if role == "source_diff" or any(item.name == name for item in input_manifest):
                    session_inputs.append(record)
                else:
                    session_outputs.append(record)
            manifest_record = _publish_bytes(
                core,
                session_id,
                build_id,
                build_role,
                "native_image_manifest",
                encoded_manifest,
                "application/vnd.m1lab.native-image-manifest+json",
            )
            return NativeBuildPublication(
                build_id=build_id,
                build_role=build_role,
                manifest=manifest,
                manifest_artifact=manifest_record,
                artifacts=tuple((*session_inputs, *session_outputs)),
            )
        finally:
            if worktree_added:
                _git_output(repository_path, ["worktree", "remove", "--force", str(worktree)])


def _build_environment(recipe: BuildRecipe, temporary: Path, source_epoch: int) -> dict[str, str]:
    scratch = temporary / "scratch"
    home = scratch / "home"
    cache = scratch / "cache"
    tmp = scratch / "tmp"
    for path in (home, cache, tmp):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = os.pathsep.join(str(item) for item in recipe.toolchain_search_paths)
    return {
        "PATH": path,
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(source_epoch),
    }


def _run_command(
    core: CoreApp,
    session_id: str,
    root: Path,
    command: BuildCommand,
    environment: dict[str, str],
    total_deadline: float,
) -> bytes:
    cwd = _inside(root, command.working_directory, allow_dot=True)
    if not cwd.is_dir():
        raise BuildError("build command working directory is missing")
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                command.argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
            )
            deadline = min(time.monotonic() + command.timeout_seconds, total_deadline)
            next_admission_check = 0.0
            try:
                while process.poll() is None:
                    now = time.monotonic()
                    if now >= next_admission_check:
                        _require_active_build_session(core, session_id, total_deadline)
                        next_admission_check = now + 1
                    if os.fstat(output.fileno()).st_size > MAX_BUILD_LOG_BYTES:
                        raise BuildError("build command output exceeded its log bound")
                    if shutil.disk_usage(root).free < 512 * 1_048_576:
                        raise BuildError("build stopped to preserve 512 MiB of host disk reserve")
                    if now >= deadline:
                        raise BuildError("build command exceeded its time bound")
                    time.sleep(0.1)
            except BaseException:
                if process.poll() is None:
                    _kill_process_group(process)
                raise
            output.seek(0)
            log = output.read(MAX_BUILD_LOG_BYTES + 1)
            if len(log) > MAX_BUILD_LOG_BYTES:
                raise BuildError("build command output exceeded its log bound")
            if process.returncode != 0:
                raise BuildError(
                    f"build command exited with status {process.returncode}: "
                    f"{log.decode('utf-8', 'replace')[-2000:]}"
                )
            return log
    except OSError as exc:
        raise BuildError(f"build command could not start: {exc}") from exc


def _require_active_build_session(core: CoreApp, session_id: str, deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise BuildError("build exhausted the session active-time allowance")
    snapshot = core.snapshot(session_id)
    if snapshot.session.phase not in ACTIVE_PHASES or not snapshot.budget.admission_open:
        raise BuildError("build interrupted because the session paused or budget admission closed")


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _describe_build_file(root: Path, relative: str) -> tuple[Path, int, str]:
    path = _inside(root, relative)
    try:
        info = path.lstat()
        if not path.is_file() or path.is_symlink() or info.st_size <= 0:
            raise BuildError(f"build artifact is missing, empty, or not a regular file: {relative}")
        if info.st_size > MAX_BUILD_ARTIFACT_BYTES:
            raise BuildError(f"build artifact exceeds its {MAX_BUILD_ARTIFACT_BYTES}-byte bound")
        digest = _file_sha256(path)
        after = path.lstat()
    except OSError as exc:
        raise BuildError(f"could not hash build artifact {relative}: {exc}") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_size != info.st_size
        or after.st_mtime_ns != info.st_mtime_ns
    ):
        raise BuildError(f"build artifact changed while being read: {relative}")
    return path, info.st_size, digest


def _resolve_tool(executable: str, search_path: str) -> Path:
    resolved = shutil.which(executable, path=search_path)
    if resolved is None:
        raise BuildError(f"declared tool is not available in its allowlisted PATH: {executable}")
    path = Path(resolved).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise BuildError(f"declared tool is not an executable regular file: {executable}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_bytes(
    core: CoreApp,
    session_id: str,
    build_id: str,
    build_role: Literal["known_good", "candidate"],
    role: str,
    content: bytes,
    media_type: str,
) -> ArtifactRecord:
    return core.publish_artifact(
        content,
        media_type=media_type,
        provenance=_build_provenance(session_id, build_id, build_role, role),
    )


def _build_provenance(
    session_id: str,
    build_id: str,
    build_role: Literal["known_good", "candidate"],
    role: str,
) -> dict[str, str]:
    return {
        "session_id": session_id,
        "record_type": "native_build_artifact",
        "build_id": build_id,
        "build_role": build_role,
        "role": role,
    }


def _manifest_artifact(name: str, role: str, content: bytes) -> ManifestArtifact:
    return ManifestArtifact(
        name=name,
        role=role,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _recipe_bytes(recipe: BuildRecipe) -> bytes:
    def file_spec(item: BuildFile) -> dict[str, str]:
        return {
            "name": item.name,
            "role": item.role,
            "path": item.path,
            "media_type": item.media_type,
        }

    def command_spec(item: BuildCommand) -> dict[str, object]:
        return {
            "argv": [_portable_recipe_text(argument) for argument in item.argv],
            "timeout_seconds": item.timeout_seconds,
            "working_directory": item.working_directory,
        }

    document = {
        "schema_version": "m1lab.build-recipe.v1",
        "recipe_id": recipe.recipe_id,
        "architecture": recipe.architecture,
        "commands": [command_spec(item) for item in recipe.commands],
        "tools": [command_spec(item) for item in recipe.tools],
        "configuration": file_spec(recipe.configuration),
        "inputs": [file_spec(item) for item in recipe.inputs],
        "outputs": [file_spec(item) for item in recipe.outputs],
        "firmware_references": [_portable_recipe_text(item) for item in recipe.firmware_references],
        "dependencies": [_portable_recipe_text(item) for item in recipe.dependencies],
        "toolchain_search_paths": [
            _portable_recipe_text(str(path)) for path in recipe.toolchain_search_paths
        ],
        "maximum_runtime_seconds": recipe.maximum_runtime_seconds,
        "maximum_output_bytes": recipe.maximum_output_bytes,
        "return_behavior": _portable_recipe_text(recipe.return_behavior),
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"duplicate build recipe key: {key}")
        result[key] = value
    return result


def _expect_list(document: dict[str, object], key: str) -> list[object]:
    value = document[key]
    if not isinstance(value, list):
        raise BuildError(f"build recipe {key} must be an array")
    return value


def _expect_optional_string_list(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BuildError(f"build recipe {key} must be an array of strings")
    return tuple(_restore_recipe_text(item) for item in value)


def _decode_build_command(value: object) -> BuildCommand:
    if not isinstance(value, dict):
        raise BuildError("build command must be an object")
    required = {"argv"}
    allowed = required | {"timeout_seconds", "working_directory"}
    if not required.issubset(value) or set(value) - allowed:
        raise BuildError("build command has unknown or missing fields")
    argv = value["argv"]
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise BuildError("build command argv must be an array of strings")
    timeout = value.get("timeout_seconds", 3600)
    working_directory = value.get("working_directory", ".")
    if type(timeout) is not int or not isinstance(working_directory, str):
        raise BuildError("build command timeout or working directory has an invalid type")
    return BuildCommand(
        tuple(_restore_recipe_text(item) for item in argv),
        timeout_seconds=timeout,
        working_directory=working_directory,
    )


def _decode_build_file(value: object) -> BuildFile:
    if not isinstance(value, dict):
        raise BuildError("build file declaration must be an object")
    required = {"name", "role", "path"}
    allowed = required | {"media_type"}
    if not required.issubset(value) or set(value) - allowed:
        raise BuildError("build file declaration has unknown or missing fields")
    if any(not isinstance(value[key], str) for key in required):
        raise BuildError("build file name, role, and path must be strings")
    media_type = value.get("media_type", "application/octet-stream")
    if not isinstance(media_type, str):
        raise BuildError("build file media type must be a string")
    return BuildFile(
        name=value["name"],
        role=value["role"],
        path=value["path"],
        media_type=media_type,
    )


def _redact_build_paths(value: str) -> str:
    home = str(Path.home())
    if home and home != "/":
        value = value.replace(home, "~")
    return value


def _portable_recipe_text(value: str) -> str:
    if not isinstance(value, str):
        raise BuildError("build recipe text fields must be strings")
    home = str(Path.home())
    return value.replace(home, "__M1LAB_USER_HOME__") if home and home != "/" else value


def _restore_recipe_text(value: str) -> str:
    if not isinstance(value, str):
        raise BuildError("build recipe text fields must be strings")
    return value.replace("__M1LAB_USER_HOME__", str(Path.home()))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _check_build_size(current: int, addition: int) -> int:
    total = current + addition
    if total > MAX_BUILD_TOTAL_BYTES:
        raise BuildError("build artifacts exceed the total publication bound")
    return total


def _inside(root: Path, relative: str, *, allow_dot: bool = False) -> Path:
    normalized = _relative_path(relative, allow_dot=allow_dot)
    candidate = root if normalized == "." else root.joinpath(*PurePosixPath(normalized).parts)
    root_resolved = root.resolve(strict=True)
    resolved = candidate.resolve(strict=False)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise BuildError("build recipe path escapes its detached worktree")
    current = root_resolved
    if normalized != ".":
        for part in PurePosixPath(normalized).parts:
            current = current / part
            if current.is_symlink():
                raise BuildError("build recipe paths cannot follow symlinks")
    return candidate


def _relative_path(value: str, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("build recipe paths must be strings")
    path = PurePosixPath(value)
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts) and not (allow_dot and value == ".")
    ):
        if allow_dot and value == ".":
            return value
        raise ValueError("build recipe paths must be relative and cannot traverse parent directories")
    return value


def _git_output(repository: Path, args: list[str]) -> bytes:
    return _git(repository, args, None)


def _git_input(repository: Path, args: list[str], content: bytes) -> bytes:
    return _git(repository, args, content)


def _git(repository: Path, args: list[str], content: bytes | None) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=30,
            check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError(f"git command failed: {exc}") from exc
    if result.returncode != 0:
        raise BuildError(f"git command failed: {result.stderr.decode('utf-8', 'replace')[-2000:]}")
    return result.stdout
