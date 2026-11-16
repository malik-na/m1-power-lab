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

## Linux as the hypervisor guest with real S2R pass-through: not reached (runs lx5-lx7)

Guest image `var/hvlinux/guest-run40hv.bin` (run40 kernel and initramfs, run 40's command line
with `wake_path=0`, `m1hv.delay=120`), arming by `tools/hv-trace-kit/harness/drivelinux.sh`.
All three froze within 1.3-2.5 s of the guest start, before Linux reached user space, so real
S2R was never armed:

| Run | Console reader | Freeze |
|---|---|---|
| lx5 | opened after "Jumping" | t 1.33 s, guest m1n1 starting CPU 5 |
| lx6 | opened 25 s after "Jumping" | t 2.34 s, Linux hw-breakpoint init, trapped DBG* msr on CPU 3 |
| lx7 | running before the guest | t 2.43 s, same place (DBGBVR4_EL1 on CPU 3) |

The hypervisor stops answering (SIGINT gives no shell, proxy hung, power cycle needed). lx3/lx4
(run39 image) passed the same burst of ~200 trapped debug-register writes across the CPUs; the
freeze sits inside that burst at slightly different writes each time. Not the console reader
(lx7). Cause not known; the next step is the hypervisor's handling of concurrent sysreg traps,
not another retry.

**lx8 (debug registers untrapped, m1n1 c288f8d4 `M1N1_HV_NO_DEBUG_TRAP=1`):** froze 1-2 s after the
guest start in the guest m1n1's CPU 5 bring-up (trapped HID msr), as lx5 did. The debug-register
traps are not the cause. Setup is identical to lx3/lx4 (the one missing zone in lx5-lx8, the SMC
SRAM at 0x23fe5c000, is added only once the guest's SMC driver runs). Cause unknown.

**lx9 (freeze probe; hypervisor watchdog on CPU 7, guest on CPUs 0-6):** booted to user space and
made its entry (stopped by the driver: `cores-parked 0x0 0x7e`, seven guest cores where it expects
eight; an artefact of the probe). 4 s after the stopped entry everything from the M1 stopped at
once (trace, console, the AOP's 0.39 s light sensor reports). The host's stacks (SIGUSR2): main
thread waiting to read from the M1, and its interrupt byte blocked in the serial write: the M1 no
longer takes USB data, though the device stays enumerated. The hypervisor watchdog sent nothing.
No M3 kernel message at any of the five freeze times. So the freezes are not tied to early boot,
and either the hypervisor hangs in a way its watchdog cannot report over USB, or the USB link
itself dies while the guest runs on. The guest m1n1 build now leaves watchdog 1 armed
(`var/hvlinux/guest-run40hv-wd.bin`) so a hung hypervisor resets the Mac without a power cycle.

**lx10 (USB hub out of the M3, otherwise as lx7/lx8):** froze 2.4 s after the guest start, in the
guest driver's boot self-test. The hub is not the cause.

**Five console readers on one port.** `fuser /dev/ttyACM1` during lx10's freeze: five Python console
readers (started 13:53:04, 20:46:21, 21:09:28, 21:17:25, 22:26:37). Stopping `session.sh console`
killed its shell and left the reader running, so each run added one. The reader reopens the port
on any `SerialException`, and pyserial raises exactly that ("multiple access on port") when
several readers race for the same bytes, so the port was reopened over and over; the Mac logs each
as "ACM device opened" (2-4 in a row at every start, and as the last line before the freeze in lx5
and lx7). Readers alive per run: one in the macOS runs, two in lx3/lx4 (no freeze), three to five
in lx5-lx10 (all froze). Mechanism on the Mac's side not shown; untested until a run with one
reader. `session.sh console` now takes a lock, refuses a second reader and `exec`s the reader.
