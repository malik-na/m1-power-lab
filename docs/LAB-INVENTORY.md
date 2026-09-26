# Physical lab inventory

Last observed: 2026-09-26 on the ThinkPad over Tailscale, and on the Apple
machine from the current Codex execution shell.

This is a partial inventory. The ThinkPad host facts were collected with the
read-only inventory script, without USB enumeration. No target control or
mutation was performed.

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
| m1n1 | No executable on PATH; no source checkout supplied; commit unknown | PATH and source probe |
| USB | `lsusb` available; enumeration deliberately omitted | inventory collection flags |

The inventory reported `usb_devices_enumerated=false`,
`usb_devices_opened=false`, and no serial numbers. On this host, the 36 host
tests passed and the replay demo completed on 2026-09-26. These results do not
qualify an M1 connection or power measurement.

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
0.156 and `gpt-6-sol` at medium reasoning effort. This establishes neither
Tailscale Serve access nor long-term host availability or a physical M1 result.
Release `3c49b9e` added the service-account logind inhibitor permission. With
opt-in lab mode enabled, logind listed the `m1lab` service holding
`sleep:idle:handle-lid-switch` in block mode while `/overview` returned HTTP
200. The lock was absent after stopping the service and returning to the
original environment. Physical lid closure was not tested.

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
| Cable, adapters, port mapping | Unknown | Owner identifies the actual cable and both physical ports; inspect connection on the T480 |
| USB permissions and device identity | Unknown | With the Mac connected, opt in to enumeration and permission capture on the T480 |
| Host/target m1n1 commits | Unknown | Record both checked-out revisions and build identities before proxy qualification |
| Owner attendance | Required for physical connect, reset, recovery, and mode transitions | Owner must be present for each such operation |

## Modes and recovery matrix

| Mode | Capability | Software reboot | Independent physical reset | Firmware recovery | Attendance |
|---|---|---|---|---|---|
| Disconnected | Known possible; no USB device enumerated in this observation | Not assessed | Not assessed | Not assessed | Required to establish physical state |
| Linux boot on observed Mac | Observed running | Not assessed | Not assessed | Not assessed | Required for physical recovery |
| m1n1 proxy | Unknown; no helper, cable, or target round trip qualified | Unknown | Unknown | Unknown | Required; do not start until recovery is qualified |
| m1n1 hypervisor | Unknown | Unknown | Unknown | Unknown | Required; not qualified |
| Native experiment | Unknown | Unknown | Unknown | Unknown | Required; not qualified |

## Bounded next attempt

1. With the owner present, identify the cable and ports and opt in to USB
   device identity and permission inventory on the ThinkPad.
2. Record host and target m1n1 revisions and build details.
3. Keep proxy, hypervisor, and native modes gated until the matching recovery
   path and owner-attendance requirements are demonstrated.

Until those steps are complete, the transport and every live target mode remain
unqualified. No proxy command or state-changing target operation was attempted.
