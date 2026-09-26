# Native Linux capture source

`native_capture.py` is a standalone, read-only target-side collector for a
future native Linux image. It consumes an immutable
`m1lab.native-launch.v1` manifest and emits the existing
`m1lab.native-result.v1` length-prefixed, checksummed identity/data/end frames
to stdout. The host owns and configures that descriptor; this program does not
open USB, serial, or network devices.

The identity frame repeats identity and boot-epoch values from the launch
manifest. This binds frames to the requested launch, but does not independently
observe or authenticate the physical target. The host assembler reports this
as `launch_binding_verified`; `identity_verified` remains false until a live
adapter verifies the target through an independent qualified observation.

The launch `parameters` object must contain only `sample_count` and
`sample_period_ms`. The program limits the run to one hour, the protocol frame
limit, the launch output limit, and the launch deadline. Its monotonic deadline
bounds sampling and result-channel writes. Reaching a sample or output bound
emits a `partial` terminal frame when the channel still accepts output; a
stalled or incomplete frame remains unknown to the host. A stuck kernel driver
read cannot be interrupted by this process, so the host timeout and target
recovery path still require qualification.

Launch preparation reserves at least one second beyond the requested sampling
duration for startup. This is a minimum scheduling margin, not a promise that
an unqualified physical launch will finish in that time; the collector still
refuses a launch whose remaining deadline cannot contain the requested work.
The terminal-frame reserve fits within the final sample interval so increasing
the sample count does not systematically omit the last samples.

`output_limit_bytes` bounds decoded sample payload bytes. Base64, JSON, and
length prefixes add channel bytes; frame size and count have separate bounds,
and offline import caps the whole saved stream at 32 MiB. These are protocol
limits, not a measured channel-throughput or observer-effect qualification.

Each data frame contains one newline-terminated
`m1lab.raw-sysfs-sample.v1` JSON record. It samples a fixed allowlist under
`/sys/class/power_supply` and `/sys/class/thermal`, plus the device-tree model.
Values are retained as raw strings with UTC and monotonic timestamps. The
collector does not convert units, select an energy boundary, compute watts,
classify sensor independence, or claim whole-device power. Missing properties
are omitted; no absent value becomes zero. A complete capture means only that
the requested raw samples were framed and emitted.

An owner-reviewed build recipe must place Python 3 and this source in the
target image, hash the exact collector source, and bind the launch manifest to
that image. `m1lab native-launch` prepares the manifest as a session artifact;
`m1lab native-import` preserves a returned byte stream and publishes a
credential-screened view of recognized collector records. Raw binary frames
are not inserted into Codex context. Offline import deliberately marks target
identity, physical source, and capture timing as unverified,
even when frame checksums and sequence are valid. Neither command dispatches a
target operation. The collector source is now available, but no M1-specific
recipe, image, result transport, or return path is qualified. Do not use its
output as power evidence until the sensor provenance, observer effect,
physical channel, and recovery gates are qualified on the actual setup.

Host integration tests run this collector in a separate Python process with
synthetic sysfs snapshots, transport its real framed output through a pipe,
and import it into isolated coordinator artifact storage. Offline import can
accept an expired saved launch while live decoding retains its deadline gate.
These tests establish software behavior only; they do not run on the Mac.

The host's descriptor receiver can also consume the collector's stdout as it
flows, preserving partial wire bytes on channel failure and applying the same
sample screening before publishing a capture. This is a host acquisition
primitive for future qualified channel wiring. Its receive deadline bounds
host waiting; it cannot stop a stuck target or demonstrate recovery.
