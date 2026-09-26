# Bounded proxy harness check

The current development stage is harness implementation and end-to-end
verification. Scientific investigation has not started. The installed lab
session remains paused with its unresolved usage hold.

`scripts/probe-m1n1-helper.py` exercises a separate helper process and the
application's same-UID Unix-socket inspection protocol. The parent never opens
the target tty. This is an owner-run setup check, outside the investigation
coordinator; it cannot authorize or execute a procedure.

## What the check does

The helper binds the selected direct `/dev/ttyACM*` path to the expected USB
topology, interface `00`, VID:PID `1209:316d`, and SHA-256 of the USB serial.
It verifies these fields before and after opening the tty and after the
observation. Raw serial values are not emitted. This identifies the observed
USB device; it does not authenticate the firmware or prove a boot epoch.

The helper holds a file lock and uses Linux tty exclusivity. Check for existing
holders of both interfaces before starting: tty exclusivity cannot evict an
earlier open descriptor or exclude a privileged process. The helper restores
tty settings and closes the socket and tty before releasing its owner lock.
The one-shot probe's temporary lock is not a deployed global device lease.

Only five fixed protocol requests are available: transport NOP (features zero),
proxy NOP, chip ID, base address, and bootargs address. The entire wire sequence
has one five-second monotonic deadline. Replies must match checksum, command,
and status; chip ID must be `0x8103`. There is no automatic retry. The parent
uses a ten-second default watchdog plus up to two seconds for forced cleanup.
An abnormal child exit or incomplete evidence makes the check fail.

Successful JSON retains `qualified=false`, `boot_epoch=null`, and no admitted
capabilities. It records the fixed protocol's identity values, timestamp, and
qualification limits. The observer refuses all execution requests.

## Running the selected setup

Use this only while the owner has arranged the proxy connection and authorized
the bounded check. Verify current sysfs metadata and absence of existing tty
holders first. Supply the expected serial digest from that verified inventory,
not a newly accepted device after a reconnect. No permanent group, permission,
or udev changes are needed on the current ThinkPad:

```bash
sudo fuser -v /dev/ttyACM0 /dev/ttyACM1
sudo -u naeem -g uucp timeout 15s .venv/bin/python scripts/probe-m1n1-helper.py \
  --device /dev/ttyACM0 --usb-topology 1-1 \
  --expected-serial-sha256 EXPECTED_USB_SERIAL_SHA256
```

Record the source commit, exact invocation, exit status, and output. Do not
interpret an unavailable device or timed-out response as permission to reboot,
continue boot, reconnect to a different target, or retry a procedure.

## Gates still open

This check does not supply a verified target binary digest, boot epoch,
coordinator dispatch, or production helper wiring. The persistent supervisor
and duplicate guard described below have separate host qualification; this
one-shot physical record does not prove their failure behavior on the Mac.
The later [persistent helper record](evidence/2026-09-26-persistent-helper.json)
demonstrates two physical inspections and normal shutdown, socket removal and
lock release. Its dispatch journal stayed empty. Crash and timeout behavior
are covered by synthetic host tests, not physical recovery demonstrations.

Proxy access does not establish a native Linux result channel. The exact
kernel, DTB, initramfs, root filesystem, collector and payload build inputs,
known-good return image, mode transitions and independent recovery still need
qualification. No power measurement or scientific result follows from this
setup check. See [qualification](QUALIFICATION.md) and
[build requirements](BUILDING.md).

## Persistent helper development

`scripts/serve-m1n1-helper.py` runs a separate supervisor and one worker. Only
the worker constructs the fixed in-package observer and opens the tty. The
supervisor watches startup, each entire request (including protocol and journal
I/O), and cleanup. Its default bounds are eight seconds for startup, twelve for
a request, and three per shutdown stage. A failed worker is terminated, then
killed if needed, and reaped; it is never restarted automatically. Linux parent
death signaling stops the worker if its supervisor disappears.

The observer still exposes inspection only, no qualified capabilities or boot
epoch. The script accepts device and identity configuration, never backend
module names, commands, or executable proposals. The caller supplies a stable
private state directory; its `owner.lock`, `helper.sock`, and `owner.lock.deny`
must refer to the same selected target across explicit restarts. Production
state must not be placed in a temporary directory.

The deny journal adds a refusal check alongside the coordinator's authoritative
SQLite history. Before backend execution it persists and fsyncs digests of the
operation ID, coordinator operation plus step index, and canonical request.
Either repeated ID or repeated step is refused, including changed payloads or
new request IDs. Even an earlier success is not executed again. A crash or
deadline expiry after reservation leaves the intent denied. The helper
rechecks the deadline after the durable write and before execution.

The journal contains no outcomes or raw target payloads. It is limited to
1 MiB and 4096 entries; capacity exhaustion, malformed/truncated records, or
failed writes prevent dispatch. A write failure invalidates the open guard.
There is no automatic pruning or reset: do not delete the journal to retry a
request. Client ambiguity remains unknown and requires the coordinator's
evidence-backed reconciliation. The guard cannot prove a USB operation had no
effect or protect history that an operator removes.

Socket, guard and backend cleanup run before owner-lock release, including
startup failure. Direct helper servers without a guard may inspect but refuse
dispatch. The application still rejects a live helper adapter at its experiment
service boundary; the coordinator/IPC integration tests use an explicitly
synthetic replay fixture.

The installed application has `PrivateDevices=yes`. The physical helper needs
a separate service unit with its own constrained device access; spawning it
inside the application would inherit that device restriction. No helper unit
has been installed or enabled, no application device isolation has been
relaxed, and this development entry point does not resume the paused lab.
