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
filesystem input or output. The J313 candidate recipe in
`target/native-image.recipe.json` assembles pinned prebuilt ALARM packages;
see [native image instructions](NATIVE-HARNESS.md). It does not claim to
reproduce the distribution's kernel compilation.

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
The candidate recipe records the assembly tool and package inputs. Native
execution and return behavior remain physical qualification gates.

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
launch binding, output bounds, and the collector record schema. The screened
view rejects duplicate JSON keys and is rebuilt from the recognized fields.
It also checks that a protocol-complete capture contains the requested number
of samples; a mismatch is reported as an unknown capture while preserving the
separate protocol status.
Frame identity and boot-epoch values are echoes from the launch manifest. The
host records their match as `launch_binding_verified`; it leaves
`identity_verified=false` until an independent live-target observation exists.
Raw binary frames are not inserted into Codex context; use the screened
decoded artifact for analysis. Offline import explicitly records
`physical_source_verified=false` and
`capture_timing_verified=false`; even a protocol-complete file is not a
verified target observation or a scientific measurement. The future live
adapter must receive frames before the launch deadline and establish the
physical source and mode itself.

The host library now provides `receive_native_capture` for a caller-owned,
exclusively accessed nonblocking descriptor. It validates the published
image/launch bindings, fixes a monotonic receive deadline, retains incomplete
prefix/frame bytes on timeout or channel loss, and uses the same sample
screening and artifact publication as file import. A terminal frame ends one
run without requiring channel EOF; trailing bytes in that same read invalidate
the capture. Traffic arriving afterward belongs to the channel owner's next
state decision. The receiver never retries, opens/configures/closes a device,
launches target work, or changes the lab session phase.

Descriptor evidence records `stream_acquisition`, including why acquisition
stopped and whether a terminal frame arrived before the host deadline.
`target_stop_verified` remains false, including after a timeout or complete
frame. Target identity, physical source and target capture timing remain
unverified. Real channel ownership, independent identity, supervisor wiring,
mode transitions and recovery still require qualification. Acquisition does
not enable a live hardware dispatch route.

`native-receive` exposes this receiver through the owner CLI. Connect the
channel owner's result pipe to stdin and select the prepared launch artifacts:

```bash
M1LAB_DATA_DIR=/path/to/harness-state m1lab --session SESSION_ID native-receive \
  --launch-artifact LAUNCH_ARTIFACT_ID \
  --image-manifest-artifact IMAGE_MANIFEST_ID
```

This command requires a pipe or socket on stdin and opens no target device.
It prints the capture status and stored artifact IDs as JSON. Channel loss or
deadline expiry publishes an unknown capture with retained raw bytes. Inspect
the returned capture status even when the command itself succeeds in storing
evidence. A terminal frame does not prove target stop or recovery. Use
`native-import` below for a saved regular file. Keep setup captures in a
separate state directory while the live lab has an unresolved usage hold.

```bash
m1lab --session SESSION_ID native-import \
  --launch-artifact LAUNCH_ARTIFACT_ID \
  --image-manifest-artifact IMAGE_MANIFEST_ID /path/to/result.frames
```
