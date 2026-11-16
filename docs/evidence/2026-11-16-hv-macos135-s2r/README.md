# macOS 13.5 under the m1n1 hypervisor completes a real suspend-to-RAM and wakes on 13.5 firmware (2026-11-16)

Setup: Macintosh HD (macOS 13.5, 22G74) with Permissive Security and m1n1 bd6a43d4 (branch
`m1power/m1-sptm-native`) as its boot object; kernelcache 13.5 (Darwin 22.6.0, xnu-8796.141.3);
system and OS firmware 13.5 (iBoot-8422.141.2). Tracer `tools/hv-trace-kit/hv_s2r_trace.py` armed
from boot, now including the SEP, SIO and NVMe (ANS) mailboxes. Raw files (private):
`tools/hv-trace-kit/runs/20261116-mac135/`.

## Two m1n1 fixes were needed for a pre-SPTM guest on 13.5 firmware

iBoot 13.5 programs and **locks** CTRR-A (memory-controller and CPU side) around its own
DeviceTree + TrustCache before jumping to a raw boot object. m1n1's pre-SPTM path passed that
through:

1. macOS panicked in `arm_vm_init`: `phystokv: illegal PA: 0x803be8000` = iBoot's original
   DeviceTree (m1n1 base - 0xb4000), read from the AMCC CTRR-A bounds (`0x200000680/684`: pages
   0xa68..0xa94 = 0x8029a0000..0x802a53fff, lock = 1). Fix ~/m1n1 31359cdc: `VirtualAMCC` presents
   the relocated DeviceTree..TrustCache range, unlocked, for pre-SPTM guests.
2. macOS then faulted on `msr CTRR_A_LWR_EL1` (CPU CTRR locked too). Fix bb15bb28: shadow
   CTRR_LOCK/CTRR_A_LWR/CTRR_A_UPR/CTRR_CTL_EL1.

## Sleep 1 (default hypervisor mode): not a real sleep

Commit (`0x23d2c4000 = 1`) at 14:19:58; the hypervisor's default mode exits the CPUs into m1n1
instead of letting them power down. The M1 was power-cycled ~11 s later (type-C partner gone at
14:20:09.5); PMU `boot_error_count 1`, `boot_error_stage 0x50`, fault shadow `00 08`. Expected
for a chip whose cores never go down; not comparable.

## Sleep 2 (real S2R pass-through, `harness/real_s2r.py`, wake mode "resume"): a full cycle

| M3 clock | Event |
|---|---|
| 14:27:54 | macOS: SMC `MBSE` slpw, slpa; power chip alarm block (0xd000 = 0x41); commit x2 |
| 14:27:55.1 | USB link drops: the SoC went down |
| 14:27:55.76 | m1n1 back: `HV: S2R wake entry: AON wake status +0x1c=0 +0x20=0x400000 +0x24=0` |
| | nonce matches; m1n1 re-enters the guest on CPU 0; macOS redoes its CTRR setup |
| after | macOS writes SMC `MBSE` = "wake" (616b6177) and keeps running |

No reset, the type-C controller never dropped. The wake was immediate (~0.65 s): wake source 54
(word 1 bit 22, the power chip's interrupt line).

## What it establishes

- On this machine and firmware, the chip's sleep program, the hardware wake and a resume work,
  when the wake lands in code that handles it (m1n1's S2R wake entry, locked RVBAR = its image).
- The ~5 s "wake-restart" of every Linux run under 13.5 is therefore specific to the Linux path.
  Hypothesis (untested): after the commit the SoC wakes at once, the boot CPU restarts at the
  locked RVBAR (the Omarchy stub's m1n1 stage 1), nothing completes the wake (no SMC `wake`),
  and the system is power-cycled ~5 s later. In every 13.5 Linux run the stage byte 0x9f0a
  still read 'R' (the driver's pre-release mark): no wake-path note was written.

Next: identify the code at the Linux boot's RVBAR and whether it handles a wake; diff this
trace's last seconds before the commit against Linux run 36.
