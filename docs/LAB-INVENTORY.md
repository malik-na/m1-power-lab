# Physical lab inventory

Last observed: 2026-09-26 from the current Codex execution shell.

This is a partial inventory. The current execution shell is on the Apple target,
not the planned ThinkPad host. No target control or mutation was performed while
collecting these read-only host facts.

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

These facts describe where this shell runs. They do not qualify the planned
ThinkPad host or a ThinkPad-to-Mac connection.

## Planned host and physical connection

For the next T480 visit, collect current host facts without opening USB
devices or recording their serial numbers:

```bash
python3 scripts/collect-host-inventory.py --output /tmp/t480-host-inventory.json
```

If the host m1n1 source checkout is available, add `--m1n1-repo PATH` to
record its current commit; check and record working-tree changes separately.
Review the JSON before attaching it to the lab record. The collector reports
only currently enumerated USB product IDs, labels, sysfs port paths, and
device-node permissions; cable identity, physical port mapping, target recovery,
and mode qualification still require owner-observed entries below.

| Field | State | Required observation |
|---|---|---|
| ThinkPad T480 identity, CPU, RAM, firmware | Unverified from this shell | Run inventory commands on the T480 and record exact outputs |
| ThinkPad OS, kernel, installed toolchain | Unverified | Capture on the T480 |
| Cable, adapters, port mapping | Unknown | Owner identifies the actual cable and both physical ports; inspect connection on the T480 |
| USB permissions and device identity | Unknown | Install/use USB inspection tooling on the T480, then capture enumeration and permissions with the Mac connected |
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

1. Run the host-side inventory on the ThinkPad T480; this must be done in its
   own shell because the current shell is on the Mac.
2. With the owner present, identify the cable and ports and collect USB device
   identity and permission evidence on the ThinkPad.
3. Record host and target m1n1 revisions and build details.
4. Keep proxy, hypervisor, and native modes gated until the matching recovery
   path and owner-attendance requirements are demonstrated.

Until those steps are complete, the transport and every live target mode remain
unqualified. No proxy command or state-changing target operation was attempted.
