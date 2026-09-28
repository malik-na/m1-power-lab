# J313 native harness candidate

The candidate is a RAM-only Linux image for the observed MacBookAir10,1 J313.
It uses the signed ALARM `linux-asahi 7.1.13.asahi3-2` package, its matching
DTB/modules, and 37 pinned Arch Linux ARM userspace packages. The lock records
URLs, versions, sizes and SHA-256 values. Assembly uses the Python standard
library; no cross compiler or host package installation is required.

This is a candidate, not a qualified known-good return image. The installed
workspace supports bounded analysis of retained evidence; native dispatch
remains disabled there. Build and capture preparation use a separate state
directory with the model runtime disabled. See [current status](STATUS.md).

## Why the boot log and native logs use different channels

The m1n1 proxy connection is bidirectional: the ThinkPad sends commands and
receives replies and a retained boot transcript. Native boot then shuts down
m1n1 USB and transfers control to Linux. Linux must configure its own USB ACM
gadget before the ThinkPad can open a serial channel for launch data, results
or later logs. The same cable does not preserve the earlier firmware channel.

The observed failure is in this handoff. Linux advertises its USB identity,
but host SET_CONFIGURATION times out with error `-110`; no usable native ACM
channel appears. Screen diagnostics can continue even though USB logs cannot
reach the ThinkPad. A separately bounded, owner-authorized private camera
recording is the current fallback for that diagnostic screen. It records no
audio and stops with the attempt. It is not a measurement or result transport.

A returned m1n1 connection does not prove that Linux RAM or its log buffers
survived the reboot. The current image has no validated persistent log handoff.
The m1n1 hypervisor offers a Linux virtual console, but it takes the connected
USB port away from the guest and changes power-management behavior; it cannot
reproduce this native USB handoff unchanged or qualify native power. See the
[m1n1 handoff](https://github.com/AsahiLinux/m1n1/blob/v1.6.1/src/main.c)
and [Linux guest console documentation](https://asahilinux.org/docs/sw/tethered-boot/#booting-a-kernel-under-the-hypervisor).

## Build

Fetch each file from `target/native-image.lock.json` into
`build/native-inputs/userspace-packages/`; place the kernel package directly
under `build/native-inputs/`. The first acquisition's signature checks are in
`docs/evidence/2026-09-26-native-packages.json`. The signing keyring was
bootstrapped through the official HTTPS repository; this is not an independent
external trust anchor. The assembler verifies every package size and digest
before extraction. It runs no package install hooks.

For local assembly without journal publication:

```bash
python target/build_native_image.py \
  --lock target/native-image.lock.json \
  --packages build/native-inputs/userspace-packages \
  --kernel-package build/native-inputs/linux-asahi-7.1.13.asahi3-2-aarch64.pkg.tar.xz \
  --output build/native-candidate
```

The output directory must be new. Outputs are `Image`, `Image.gz`,
`j313.dtb`, `initramfs.cpio.gz`, source snapshots, `bundle-metadata.json`,
`payload.tar`, and an unpacked rootfs. `inputs/` preserves exact package
bytes, the lock, and the kernel provider's package/build metadata. Timestamps,
archive ownership, ordering and compression headers are fixed. This
reproduces assembly from published binaries, not their upstream compilation.

For immutable, session-linked publication, use the existing owner CLI with
`target/native-image.recipe.json` and `--role candidate`. Its package cache
paths target this ThinkPad's `~/Work/m1-power-lab`; adjust those explicit
paths if moving the checkout. Commit source files first, since the build
runner rejects untracked source. The runner builds in a detached worktree
and records source/patch, recipe, tool executable, all package inputs and
output hashes. The compressed initramfs also serves as the rootfs artifact.

```bash
M1LAB_DATA_DIR="$PWD/build/harness-state" M1LAB_CODEX_RUNTIME=disabled \
  .venv/bin/m1lab --session HARNESS_SESSION_ID build \
  --source-repo "$PWD" --recipe target/native-image.recipe.json --role candidate
```

## Finite target behavior

`/init` mounts devtmpfs, proc, sysfs and RAM tmpfs. It does not mount internal
storage, launch a login shell, start networking, or apply firmware changes.
The boot program loads the fixed USB module set, creates one ACM gadget,
and requires exactly one available USB device controller. It relies on the
kernel's port role switch; absent or ambiguous controllers fail the attempt.

The gadget uses USB `1d6b:0104` and the public serial label
`m1lab-native-candidate`. That label is not physical identity evidence.
The host channel owner must bind the expected physical USB path, acquire
exclusive ownership, configure raw serial, then send exactly one compact
`m1lab.native-launch.v1` JSON object followed by a newline. The target accepts
at most 256 KiB and validates the launch using the in-image collector. Before
sampling, it reads Linux's boot UUID and kernel release and hashes the exact
packaged lock at `/etc/m1lab/image-config.json`; missing or mismatched
configuration refuses capture. The identity frame carries this bounded
`observed_linux` self-report, followed by the checksummed native result frames.
It does not authenticate physical origin. No shell commands are accepted.
Use the matching updated host decoder: legacy frames still decode, but older
strict hosts cannot accept the new identity object.

`m1lab.adapters.native_usb.NativeUsbTransport` provides the corresponding
host ACM exchange for a caller holding the helper owner lock. It checks the
fixed USB labels and configured physical port before/after exclusive tty
open, sends the launch once, and shares one monotonic deadline across send
and receipt. Partial send is ambiguous; receive failures retain raw bytes.
The transport never retries or changes devices. The explicit attended helper
path below uses a 1 MiB wire cap and reserves time to observe proxy return.
Synthetic PTY coverage does not qualify the actual USB channel.

The requested sample duration must fit both its launch deadline and the
remaining 150-second native window. Approval expiry may be later than the
native window; it never extends the collector's sample duration. Use a short
setup capture with enough time for enumeration;
a Linux clock mismatch fails launch validation instead of inventing timing.
After capture, the target allows two seconds for output delivery and requests
reboot. A separate userspace watchdog requests reboot at 180 seconds from
init. A stuck kernel may defeat either path. Host timeout or complete framing
does not prove target stop, delivery, or recovery.

## Experimental USB startup diagnostic

A diagnostic candidate preallocates a configuration string before UDC binding,
then updates it with a fixed startup stage and sampled UDC state. Product and
serial labels stay unchanged. Failure strings include only a fixed exception
category. The existing finite boot and watchdog limits remain; the diagnostic
never carries samples, physical identity, or proof of recovery. Concurrent
string reads may be stale or torn, and an EP0 failure can make the string
unavailable entirely.

`scripts/probe-native-usb-diagnostic.py` reads only a fixed set of standard
GET_DESCRIPTOR requests from the selected bus-port. It checks native VID/PID,
public labels and descriptor indices, validates the diagnostic format, and
writes a new private JSONL file capped at 256 KiB. It never configures, resets,
or claims an interface. A same-port proxy observation is only a USB observation;
the exclusive helper separately verifies proxy identity and connection generation.

Run the probe only from an exact-hash-verified, root-owned volatile copy as part
of the reviewed attended procedure. The privileged wrapper starts it before
dispatch, records a fresh process-bound readiness file, and enforces an outer
480-second timeout with bounded termination and reaping. Running the mutable
checkout script directly with `sudo` would bypass that reviewed staging boundary.
The probe prints readiness before polling. The outer timeout is necessary because
the 250 ms USB transfer timeout cannot bound every kernel mutex or filesystem
wait. The standalone tool reserves two seconds before beginning a six-request
batch. It exits on its observation deadline or a same-port proxy return after
native enumeration. Failed reads establish no target stage. This channel must
be demonstrated on the actual candidate before relying on it for diagnosis.

The ninth attempt did not establish that channel: native USB enumerated, but
the host timed out setting configuration 1, and the fixed probe's fresh
device-descriptor reads returned timeout or protocol errors before it could
request the configuration string. It captured zero result bytes and samples.
The proxy returned on a new checked connection; the next useful observation
is the owner's exact last console line. See
[ninth-attempt evidence](evidence/2026-09-28-native-ninth-attempt.json).

## Qualification still required

Host emulation has exercised the actual ARM64 Python/BusyBox/kmod binaries
and collector with synthetic samples. It does not exercise the M1 kernel,
USB controller, sensor drivers or reboot. The ninth physical attempt exposed
an unresolved USB configuration failure before native capture.

An additional native boot needs new exact-artifact review and attended
authorization. Preserve the existing normal ALARM boot path and physical
recovery instructions. The current priority is the owner's exact last console
line from the failed startup. Never mark this candidate `known_good` solely
because assembly or emulation passed. Scientific sensor qualification and
power investigation remain stopped; bounded analysis of retained technical
evidence is available in the installed workspace.

After a capture is published, its screened `native_capture` artifact can be
summarized without opening a device, then selected as technical context for a
bounded Codex turn:

```bash
m1lab --session HARNESS_ID native-summary \
  --capture-artifact CAPTURE_ARTIFACT_ID
m1lab --session HARNESS_ID investigate \
  --artifact-id CAPTURE_ARTIFACT_ID \
  "Assess the captured sensor fields and remaining measurement unknowns."
```

`--artifact-id` is repeatable and accepts only artifacts in the selected
session. The raw binary stream stays preserved separately. A complete capture
does not establish sensor units, a whole-device power boundary, or a scientific
observation; qualify those before deriving a power result.

## Explicit attended qualification path

This path is separate from normal application startup and the installed lab.
Use a dedicated harness state directory and explicit session ID. It requires
an accepted review of the exact procedure and artifacts, followed by a
single-use owner approval bound to the target, owned proxy connection
generation, helper configuration and physical attendance. The coordinator
rechecks these at dispatch. Neither CLI command resumes or reconciles a
session; existing accounting and unresolved-operation gates still apply.

1. Prepare the boot client environment using the hash-pinned
   `scripts/m1n1-client-requirements.txt`. Select a regular interpreter file
   inside that environment (a copied interpreter works; a symlink is refused).
   Inventory and pin the existing `linux.py` executable and proxyclient tree.
2. Create a private configuration JSON with exactly these string fields:
   `artifact_root`, `usb_topology`, `expected_proxy_serial_sha256`,
   `python_path`, `python_sha256`, `boot_script_path`, `boot_script_sha256`,
   `proxyclient_path`, `proxyclient_sha256`. Paths must be absolute. The fixed boot command selects the owned tty through `M1N1DEVICE` and
   accepts no command text from a procedure. Keep the serial digest in private setup
   evidence. Publish the reviewed configuration/tool provenance with the
   procedure's artifacts.
3. From an operator process with the required device access, launch
   `scripts/serve-native-helper.py --state-dir PRIVATE_HELPER_STATE
   --config PRIVATE_CONFIG --owner-pid PARENT_PID`. The PID must be its
   immediate parent. Keep this process alive through preparation and return.
   Use a stable helper state directory so the durable denial journal survives
   restarts. The worker holds exclusive ownership; supervisor bounds are
   12 seconds startup, 480 seconds per request and 3 seconds per cleanup stage.
4. Use `m1lab --session HARNESS_ID native-inspect --helper-socket SOCKET`.
   The result is explicitly unqualified. Its epoch is a conservative owned
   connection generation, not independently attested target boot identity.
   Prepare the image-bound launch against this identity and epoch, with a
   short sample duration, output limit at most 262144 bytes and a finite
   expiry allowing review and boot. Register exactly one mutating
   `run_native_candidate` operation with the payload, image manifest and
   launch manifest SHA-256 parameters, required physical attendance, and a
   timeout at most 480 seconds. Additional reviewed tool artifacts are allowed.
5. Complete separate exact review and attended owner approval. Refresh the
   recorded proxy snapshot immediately before dispatch (freshness is at most
   30 seconds). Run `m1lab --session HARNESS_ID native-run --helper-socket
   SOCKET --procedure-id PROCEDURE --procedure-revision REVISION
   --target-snapshot SNAPSHOT` once.

Each helper backend permits one launch. After an attempt it can retain the
returned proxy for observation, but it no longer advertises launch capability.
Reconcile the outcome, stop the owned helper cleanly, and explicitly start a
fresh helper before preparing another launch. Keep the same private state
directory and denial journal. The new connection needs a new launch manifest,
exact review and attended approval; restarting never retries an old operation.

The helper stages only the three verified boot files, closes the proxy
descriptor, invokes the pinned tethered boot tool once, receives the bounded
native stream, and observes the same proxy USB identity again. A watcher in that
same helper starts immediately after the boot client and remains active during
native startup and capture. It scans the bound USB identity across tty renumbering,
distinguishes the original enumeration from a return, and opens the returning
proxy immediately for fixed read-only inspection. An early return without a
complete capture remains unknown. The watcher must end before a result is
reported; a stuck watcher terminates the helper worker under supervision.

For attended manual recovery, stop the failed helper, arm a bounded identity-bound
catcher and verify that it is waiting **before** asking the owner to reboot.
Do not wait for a completed reboot or assume the interface is always `ttyACM0`:
the proxy window can expire and continue into the installed OS.

The boot client
gets an owned pseudo-terminal on stdin for pySerial Miniterm. After capture
finishes or fails, the helper sends Miniterm's Ctrl+] exit byte and applies
bounded process-group cleanup. This host-console control is included in the
helper configuration digest; changed launcher behavior requires fresh review
and approval. No owner keyboard input is forwarded. A complete
capture alone is insufficient: success also requires a new owned proxy
connection and matching Linux image configuration. Raw received bytes are
published before interpretation. Lost capture, launcher failure or missing
return remains unknown, with no automatic repeat or promotion to known-good.
The published capture retains unverified physical source and timing flags.
Failure of the kernel or USB path may still require owner physical recovery.

The USB composition follows the [Linux configfs gadget interface](https://www.kernel.org/doc/html/latest/usb/gadget_configfs.html).
The kernel/DTB/initramfs bundle follows the [Asahi tethered boot interface](https://asahilinux.org/docs/sw/tethered-boot/);
the existing m1n1 proxy serial channel is not assumed to survive native boot.
