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
coordinator dispatch, durable duplicate-dispatch protection, or production
helper wiring. A persistent helper also needs a supervisor and qualified
failure/cleanup behavior; the generic adapter interface alone cannot bound a
blocked backend.

Proxy access does not establish a native Linux result channel. The exact
kernel, DTB, initramfs, root filesystem, collector and payload build inputs,
known-good return image, mode transitions and independent recovery still need
qualification. No power measurement or scientific result follows from this
setup check. See [qualification](QUALIFICATION.md) and
[build requirements](BUILDING.md).
