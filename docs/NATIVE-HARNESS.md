# J313 native harness candidate

The candidate is a RAM-only Linux image for the observed MacBookAir10,1 J313.
It uses the signed ALARM `linux-asahi 7.1.13.asahi3-2` package, its matching
DTB/modules, and 37 pinned Arch Linux ARM userspace packages. The lock records
URLs, versions, sizes and SHA-256 values. Assembly uses the Python standard
library; no cross compiler or host package installation is required.

This is a candidate, not a qualified known-good return image. The current
live lab stays paused with its unresolved usage hold. Build and capture
preparation use a separate state directory with the model runtime disabled.

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

## Qualification still required

Host emulation has exercised the actual ARM64 Python/BusyBox/kmod binaries
and collector with synthetic samples. It does not exercise the M1 kernel,
USB controller, sensor drivers or reboot. The source review found no concrete
boot blocker; the selected exact image/procedure still needs review before
execution through the coordinator/helper path.

Next is exact-artifact review and one owner-attended M1 capture, with
independent identity checks and observed return/re-identification. Preserve the
existing normal ALARM boot path and physical recovery instructions. Never
mark this candidate `known_good` solely because assembly or emulation passed.
Scientific sensor qualification and investigation remain stopped.

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

The helper stages only the three verified boot files, closes the proxy
descriptor, invokes the pinned tethered boot tool once, receives the bounded
native stream, and observes the same proxy USB identity again. The boot client
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
