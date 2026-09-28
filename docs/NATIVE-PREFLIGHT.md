# Read-only native preflight

From the repository checkout, with the project environment installed:

```sh
.venv/bin/python scripts/native-preflight.py \
  --config build/native-helper-config.json
```

The command prints JSON and exits `0` when the checked prerequisites pass, or
`1` when it finds concrete blockers. Each blocker includes an action. Keep the
output private: it includes local paths and the hashed target identity, but
never the raw USB serial or the configuration contents.

It uses the helper launcher's exact configuration parser and the native
backend's parameter validation, tool-pin checks and USB matching rules. It
checks the reviewed interpreter, `linux.py`, proxyclient tree and artifact-root
presence/access. It discovers matching m1n1 USB interface **00** across ports
and compares the discovered topology with the configured topology. More than
one matching identity is a blocker. It reports the tty node's type, owner,
group and effective read/write access without opening that node.

For example, a target configured at `1-1` but found at `1-2` produces
`topology_mismatch`. Reconnect at the configured port, or review and update
`usb_topology` in the private configuration before starting a new helper. A
matching `/dev/ttyACM0` without read/write access produces
`device_inaccessible`; have the device administrator check its group/udev
policy and use a fresh login/session after any group change. This command
never edits configuration, changes permissions or invokes `sudo`.

Optionally add `--helper-socket /absolute/private/state/helper.sock` to report
socket presence, type, ownership and access. This is metadata only: a present
socket may be stale, and an absent socket is not a blocker before the helper
starts. The command does not connect to the socket or send target requests.

A passing preflight does not establish exclusive serial ownership, proxy RPC
readiness, an approved launch, complete artifact contents, or native hardware
qualification. An unplug or permission change can invalidate the snapshot.
Continue with the exact attended workflow in [NATIVE-HARNESS.md](NATIVE-HARNESS.md).
