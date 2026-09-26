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
