# Reproducible target builds

`m1lab.builds` provides the host-side runner used by target-specific build
recipes. It accepts an application-owned `BuildRecipe`; model proposals and
hardware requests cannot supply build commands. Each recipe declares fixed
argument arrays for build and tool-version commands, repository-relative
configuration/inputs/outputs, firmware references, dependencies, toolchain
search paths, result bounds, and return behavior. Every tool-version command
also records the resolved executable SHA-256 and rejects a tool binary that
changes during the build. Commands execute with
`shell=False` in a detached worktree with a fresh environment and temporary
home/cache directories.

An owner starts a build from an active session with:

```bash
m1lab --session SESSION_ID build \
  --recipe /path/to/owner-reviewed-recipe.json \
  --source-repo /path/to/target-source \
  --role candidate
```

Use `--role known_good` for a reviewed return image. Recipe JSON uses the
`m1lab.build-recipe.v1` schema and rejects duplicate keys, unknown fields,
and unsupported artifact roles. Commands are argument arrays launched with
`shell=False`. It must declare
`kernel`, `dtb`, `initramfs`, `collector`, and `payload` outputs and a root
filesystem input or output. No M1-specific recipe is included yet because the
ThinkPad cross-toolchain and target source inventory have not been recorded.

The runner requires an active session with enough remaining active time. It
stops build processes if the session pauses, the budget closes, the deadline is
reached, command output exceeds its bound, or the 512 MiB scratch-disk reserve
would be crossed. Tracked dirty changes are captured as a binary patch and
applied to the detached worktree; untracked files and repositories containing
submodules are rejected because their full source state is not captured.
Generated tracked-source changes are rejected. Artifacts are hashed and
published by streaming without loading root filesystem images into memory.
Individual artifacts are limited to 2 GiB and total build data to 4 GiB, with
the journal and worktree disk reserves checked before and during the build.

Recipes declare kernel, DTB, initramfs, collector, payload, and root filesystem
artifacts. The runner publishes each input/output and the immutable image
manifest to the session artifact store. The manifest records the source commit
and patch digest, exact recipe artifact, tool versions and executable hashes, configuration, input
and output hashes, firmware references, dependencies, collector, and finite
run limits. Build provenance distinguishes `known_good` and `candidate`.

The manifest and its artifact digests are evidence for a separate exact
procedure review. Any changed output has a different content digest, so a
previous procedure or approval cannot silently authorize it. The builder only
creates and records artifacts; it does not load or execute them on the target.
The M1-specific recipe cannot be selected until the ThinkPad toolchain and
source inventory are recorded. Native execution and return behavior remain
physical qualification gates.

The standalone [`native_capture.py`](../target/native_capture.py) source is a
bounded Linux collector for a future native image. It emits the host's native
result protocol and preserves allowlisted power-supply and thermal sysfs values
as raw strings. It performs no unit conversion or whole-device power
calculation. A recipe must include Python 3, hash the exact collector source,
and install it in the target root filesystem. This source does not qualify the
M1 sensors, channel, return path, or recovery behavior; see the
[collector notes](../target/README.md).

The host CLI can validate and publish a launch manifest against a session's
published image manifest and output artifact. It requires the target identity
to match the session and records the explicitly supplied boot epoch and
recovery expectation. Preparing this artifact does not start a target
operation:

```bash
m1lab --session SESSION_ID native-launch \
  --image-manifest-artifact IMAGE_MANIFEST_ID \
  --image-artifact PAYLOAD_ARTIFACT_ID \
  --target-identity TARGET_ID --boot-epoch EXPECTED_BOOT_EPOCH \
  --sample-count 60 --sample-period-ms 1000 \
  --deadline-seconds 120 --output-limit-bytes 1048576 \
  --recovery-expectation "qualified mode-specific recovery instructions"
```

`m1lab native-import` preserves a saved framed stream and a normalized,
credential-screened capture artifact after checking framing, digests, sequence,
launch binding, and output bounds. Raw binary frames are not inserted into
Codex context; use the screened decoded artifact for analysis. Offline import
explicitly records `physical_source_verified=false` and
`capture_timing_verified=false`; even a protocol-complete file is not a
verified target observation or a scientific measurement. The future live
adapter must receive frames before the launch deadline and establish the
physical source and mode itself.

```bash
m1lab --session SESSION_ID native-import \
  --launch-artifact LAUNCH_ARTIFACT_ID \
  --image-manifest-artifact IMAGE_MANIFEST_ID /path/to/result.frames
```
