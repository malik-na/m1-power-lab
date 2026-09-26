# Physical lab inventory

Last observed: 2026-09-26 on the ThinkPad, including an owner-authorized
direct m1n1 setup probe during the Mac's boot. Earlier Apple Linux facts below
were collected before development moved to the ThinkPad.

This is a partial inventory. Initial host collection omitted USB enumeration;
subsequent USB metadata and direct proxy observations are recorded below.
The direct setup probe does not qualify the application's live helper path.

## Observed ThinkPad host

| Field | Observed value | Source |
|---|---|---|
| Hardware | Lenovo ThinkPad T480; product and board `20L6S09700` | DMI from `scripts/collect-host-inventory.py` |
| CPU / memory | Intel Core i5-8350U, 8 logical CPUs; 16,633,233,408 bytes RAM | `/proc/cpuinfo`, `/proc/meminfo` |
| Firmware | Lenovo BIOS `N24ET81W (1.56 )`, dated `09/06/2025` | DMI |
| OS / kernel | Omarchy 4.0.4, `7.2.5-3-omarchy`, x86_64 | `/etc/os-release`, kernel release |
| Python / Git | 3.14.7 / 2.55.0 | version probes |
| Available build tools | GCC 16.2.1, Clang 22.1.8, GNU Make 4.4.1 | version probes |
| Missing build tools | AArch64 GCC cross compilers, Rust/Cargo, CMake, Ninja | PATH probes |
| m1n1 | No executable on PATH; local clean checkout `06a4601a351ebfd1abb6abba9a44c34e40d94776`, tagged `v1.6.1` | PATH probe and subsequent local Git inspection |
| USB | `lsusb` available; subsequent metadata and proxy probe recorded below | inventory collector and owner-authorized setup probe |

The inventory reported `usb_devices_enumerated=false`,
`usb_devices_opened=false`, and no serial numbers. On this host, the 36 host
tests passed and the replay demo completed on 2026-09-26. These results do not
qualify an M1 connection or power measurement.

Follow-up on 2026-09-26: a local m1n1 source checkout was found at
`/home/naeem/Projects/m1n1`, detached at clean commit
`06a4601a351ebfd1abb6abba9a44c34e40d94776`. The host has a separate
Python 3.14.7 environment at `/home/naeem/Projects/m1n1-venv` and an earlier
standalone connection script at `/home/naeem/Projects/m1n1-connect.py`. The
script opens `/dev/ttyACM0` directly for NOP handshakes and proxy identity
queries; at discovery it was inspected but not run. That device path was absent during this
follow-up check. The Mac's running m1n1 build identity and the compatibility
of host and target revisions remain unverified. The owner reports the Mac is
running its normal Asahi/ALARM installation, with m1n1 proxy mode reportedly
on and a USB cable connected to the ThinkPad. The owner subsequently identified
the connector path as ThinkPad USB-A to Mac USB-C; exact physical port positions
and any adapters remain unrecorded.

At 12:20 UTC on 2026-09-26, the inventory collector ran with `--include-usb`
outside the execution sandbox so host device-node permissions were visible.
It read sysfs and file metadata only, with no device opening or serial-number
collection. Six devices were enumerated: two Linux root hubs, `8087:0a2b`,
`04f2:b604` (integrated camera), `06cb:009a`, and `0bda:0316` (USB card reader).
No Apple/m1n1 device was observed, and the host had no `ttyACM*`, `ttyUSB*`, or
`/dev/m1n1` node. This does not establish cable data capability or what will
enumerate during the Mac's next boot. The live lab pause and usage hold remain
intact; no reboot or proxy command was performed during that metadata check.

### Owner-authorized proxy setup probe

Later on 2026-09-26, the owner explicitly requested running the existing
connection script. The initial attempt failed because `/dev/ttyACM0` was
absent. A three-minute wait caught the interface during a subsequent boot,
but the connection failed before opening it with permission denied. The
owner then authorized sudo access. A second bounded wait ran as `naeem` with
temporary primary group `uucp`; no account memberships, udev rules, or device
permissions were changed. It verified USB ID `1209:316d` before running the
existing script exactly once with `timeout --kill-after=2s 15s`.

The probe completed successfully (exit 0) using
`/home/naeem/Projects/m1n1-venv/bin/python -u /home/naeem/Projects/m1n1-connect.py`.
The inspected script SHA-256 was
`f6b6b0898b3090a8da9ebfe21da436eb3490bf9b8df6fa1aa1a1c3f36e4c3f16`.

| Observation | Value |
|---|---|
| USB identity and host topology | `1209:316d`, host path `1-1`, interface `1-1:1.0` |
| Serial nodes after the probe | `/dev/ttyACM0` and `/dev/ttyACM1`, mode `0660`, owner `root:uucp` |
| Target boot banner | `m1n1 v1.6.1`, running in EL2 |
| Reported model / target / board | `MacBookAir10,1` / `J313` / `0x26` |
| NOP transport and proxy handshakes | Both succeeded |
| Chip ID returned by proxy | `0x8103` |
| m1n1 base / boot-arguments address | `0x805574000` / `0x805cac088` |
| Firmware reported in boot output | OS `13.5 (iBoot-8422.141.2)`; system `unknown (mBoot-20457.0.125.0.2)` |

This demonstrates a working data path and direct proxy replies for this boot.
The script closed its serial connection; it sent no exit/continue-boot command.
The target banner matches the host checkout's release tag, but the exact target
build digest/commit and independent per-device identity remain unverified.
No coordinator boot-epoch record, exclusive helper ownership, normal reviewed
dispatch, mode-return recovery, native result channel, or measurement was
qualified by this probe. The installed lab service and its paused usage hold
were not changed.

An isolated `m1lab diagnostics` run on the T480 on 2026-09-26 observed AC power,
12% battery, 62 °C maximum temperature, and 7.7 GiB free disk space. A second
sample measured 63 °C and 8,292,458,496 bytes free. The current admission
policy found no blocker at those instants (AC required, temperature below
90 °C, at least 5 GiB free). Sleep/lid inhibition was not requested; lid,
AC-loss, thermal-pressure, low-disk, and shutdown responses remain unqualified.

The `e6fc7ba` release was installed on the T480 and started in loopback mode
with replay hardware and Codex runtime disabled. The service ran as `m1lab`
and listened only on `127.0.0.1:8765`. The `f58395f` update, rollback to
`e6fc7ba`, and return to `f58395f` each started and returned HTTP 200 for
`/overview` with zero restarts during the check. The original session survived
the update with its budget unchanged. Release `97363a8` fixed restoration
staging for the service account; a fresh bundle was restored over the stopped
live data root, and the service restarted with HTTP 200, zero restarts, and
the same session and full budget. Release `10934e9` was later installed with
the Codex app-server enabled; a host-only turn completed as `m1lab` with
provider-reported usage of 19,816 tokens. The service uses pinned Codex
0.156 and `gpt-6-sol` at medium reasoning effort. This does not establish
long-term host availability or a physical M1 result.
Release `3c49b9e` added the service-account logind inhibitor permission. With
opt-in lab mode enabled, logind listed the `m1lab` service holding
`sleep:idle:handle-lid-switch` in block mode while `/overview` returned HTTP
200. The lock was absent after stopping the service and returning to the
original environment. Physical lid closure was not tested.
Tailscale Serve was then configured to proxy to the loopback service. On the
T480, HTTPS `/overview` returned HTTP 200, exact owner identity was required
for direct loopback requests, and no public Funnel entry was enabled. The
owner-matched investigation session remains paused. Full workflows from the
iPhone 12 mini and tailnet policy have not been checked.
The T480 also has a stable service-owned VAPID key pair, and the enabled push
config endpoint responds over Serve. The owner subsequently reported iPhone
enrollment, confirmed by `enrolled=true` from the HTTPS endpoint. Notification
delivery remains unqualified.

## Observed execution machine

| Field | Observed value | Source |
|---|---|---|
| Hardware | Apple MacBook Air (M1, 2020), model identifier `MacBookAir10,1` | `/sys/firmware/devicetree/base/model`; `/sys/devices/virtual/dmi/id/product_name` |
| SoC | Apple M1; 4 Icestorm and 4 Firestorm cores reported | `lscpu` |
| OS | Arch Linux ARM (rolling) | `/etc/os-release` |
| Kernel | `7.1.13-3-2-ARCH`, aarch64 | `uname -a` |
| Python | 3.14.7 | `python --version` |
| Git | 2.55.0 | `git --version` |
| Clang | 22.1.8 | `clang --version` |
| GCC | 16.1.1 | `gcc --version` |
| USB inspection | `lsusb` unavailable; `/sys/bus/usb/devices` showed no enumerated devices | command and sysfs observation |
| m1n1 | Not found on `PATH`; build/commit unknown | `command -v m1n1` |
| Firmware / boot chain | Unknown; no firmware reference captured | Not observed |

These Apple-machine facts do not qualify a ThinkPad-to-Mac connection or the
Mac's current proxy mode.

## Planned host and physical connection

On the ThinkPad, collect host facts without sampling USB devices or recording
their serial numbers:

```bash
python3 scripts/collect-host-inventory.py --output /tmp/t480-host-inventory.json
```

If the host m1n1 source checkout is available, add `--m1n1-repo PATH` to
record its current commit and whether tracked files are modified. The inventory
contains only the change count, not repository paths or file contents; untracked
files are excluded from this status summary.
Review the JSON before attaching it to the lab record. It records available
versions of Git, native and AArch64 cross compilers, Rust/Cargo, Make, CMake,
and Ninja to support build provenance. USB enumeration is separate and opt-in
with `--include-usb`; defer it until the owner is ready to inventory the
connection. Even then, cable identity, physical port mapping, target recovery,
and mode qualification require owner-observed entries below.

| Field | State | Required observation |
|---|---|---|
| ThinkPad T480 identity, CPU, RAM, firmware | Observed above on 2026-09-26 | Recheck after relevant host updates |
| ThinkPad OS, kernel, installed toolchain | Observed above; AArch64 and several build tools missing | Install only tools required by the qualified build path |
| Cable, adapters, port mapping | Owner reports ThinkPad USB-A to Mac USB-C; exact positions and adapters unknown | Record physical port positions and cable/adapter details |
| USB permissions and device identity | Direct setup probe observed `1209:316d` at `1-1`; serial nodes `0660 root:uucp` | Establish independent per-target identity and exclusive helper ownership |
| Host/target m1n1 commits | Clean host `06a4601a351ebfd1abb6abba9a44c34e40d94776` tagged `v1.6.1`; target banner `v1.6.1` | Verify exact target build provenance before claiming matching builds |
| Owner attendance | Required for physical connect, reset, recovery, and mode transitions | Owner must be present for each such operation |

## Modes and recovery matrix

| Mode | Capability | Software reboot | Independent physical reset | Firmware recovery | Attendance |
|---|---|---|---|---|---|
| Disconnected | Known possible; no USB device enumerated in this observation | Not assessed | Not assessed | Not assessed | Required to establish physical state |
| Linux boot on observed Mac | Observed running | Not assessed | Not assessed | Not assessed | Required for physical recovery |
| m1n1 proxy | Direct NOP and identity-query round trip demonstrated; coordinator/helper path unqualified | Unknown | Unknown | Unknown | Required for further physical qualification |
| m1n1 hypervisor | Unknown | Unknown | Unknown | Unknown | Required; not qualified |
| Native experiment | Unknown | Unknown | Unknown | Unknown | Required; not qualified |

## Bounded next attempt

1. Preserve the observed cable arrangement; record remaining physical port
   positions and establish the exact target build and per-device identity.
2. Prepare a bounded return/re-identification procedure and recovery instructions
   from the pinned source for owner review before further target commands.
3. Qualify exclusive helper ownership, boot-epoch tracking, and reviewed
   coordinator dispatch before treating the application transport as ready.

Application transport, recovery, native results, and measurement remain
unqualified. The successful direct setup probe is limited evidence toward M2.
