# Run 40: macOS 13.5's late order, NVMe idle, PMP notes, lid angle write: the restart stays at 5.0 s (2026-11-16)

Kernel 7.2.11-run40 (s2r-rs1-135 24658c328, package sha256 338b056e…), run 39's set plus the four
differences the hypervisor trace showed (`docs/evidence/2026-11-16-hv-linux-entry/`):
`nvme_apple.s2r_idle=1`, `apple_s2r_rs.mac_late=1` with `apple_sio.s2r_late=1`,
`apple_pmp_v1.mac_notes=1`, and the lid angle interval on endpoint 0x25. Run over Thunderbolt only,
no lab: `tools/tb/m1-bootonce` (modules, initramfs, a one-shot Limine `protocol: linux` entry
`m1tb-run40`, `bootctl set-oneshot`), `run40.sh` started with `systemd-run`, run 39's cycle closed
first with `acceptance.sh postmortem`.

| M3 clock | Event |
|---|---|
| 21:00:12.23 | ENTRY: acceptance.sh cycle 60 |
| 21:00:14.50 | rmmod apple-sep |
| 21:00:17.46 | USB4 host disconnected (the release) |
| **21:00:22.48** | **SBX disconnected: the M1 restarts, 5.0 s after the release** |

Record 0x9f10-17 `d2 01 04 05 64 01 47 31`: watchdog 2 (sequence 0's) moved to 100 s; **byte 6 =
0x47: the late steps ran in macOS's order (boot stage 0x50, SIO idled, PMP idled, after the SMC's
AP power 0x201)**; byte 7: 8/8 AOP stops answered, 1 of 4 sensor writes accepted. Power chip after
the restart: 0x0201 = 01, 0x9f02 unchanged. The kernel log after `rmmod apple-sep` was not written
to the journal, so the NVMe idle is not confirmed by a line (its switch read Y before the entry).

**Runs 36-40 all restart 5.0-5.5 s after the release**, with: watchdog 2 moved, PMP idled early or
late, macOS's late order, domains off, every wake source masked, AOP sensors off and stops
acknowledged, NVMe idle. 0x0201 stays at sequence 1's 01 every time.

## What this leaves

The entry's device state now matches macOS's message for message (bar the 1-of-4 sensor writes).
What still differs is the commit itself: under the hypervisor macOS's last core goes down through
m1n1's real-S2R path; Linux goes down through its own final routine (`s2r_seq` enter, the boot
core's last stage, stage-1 m1n1's wake vector). Next: Linux as the hypervisor guest **with real S2R
pass-through**, so Linux's device state commits through the same path macOS used. A wake there puts
the fault in Linux's commit path; a reset ~5 s after the commit puts it in the device state.
