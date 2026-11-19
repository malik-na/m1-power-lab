# Wake path: from the always-on wake to Linux's wake calls

What has to happen, in order, for a wake to reach Linux, and what each run saw of it.
2026-11-20. No Linux sleep has yet been seen to reach any step after the commit.

## The chain (each step must happen for the next)

| # | Step | Source |
|---|---|---|
| 1 | The always-on side wakes the SoC (alarm, wake source 54 = power chip's interrupt line). | [evidence 2026-11-16-hv-macos135-s2r, Sleep 2] |
| 2 | The boot CPU restarts at its RVBAR, locked by iBoot to the stage-2 loader (m1n1 in `boot.bin`). | [m1n1-mb2-breadcrumb `src/s2r.h` header comment; evidence 2026-11-07-linux-s2r, Run 2] |
| 3 | The loader's reset vector `cpu_reset` -> `_cpu_reset_c`; a cold boot enters at `_start` instead. | [m1n1-mb2-breadcrumb `src/start.S` `cpu_reset`; `tools/m1n1/read-breadcrumb.sh` header] |
| 4 | `s2r_reset_enter`: a wake is told by the mailbox: magic `S2RMBOX1` and `quiet`=1 (set at hand-off) and a slot for this MPIDR. | [`src/s2r.c` 98-115, 209-217; `src/startup.c` 262] |
| 5 | `s2r_reset_resume`: reads core 0's slot `entry`; empty -> boot CPU parks in WFE; set -> clears it, counts `resumes`, jumps at EL2 with the MMU off. | [`src/s2r.c` 122-168; `src/s2r.h` comment] |
| 6 | The entry is `cpu_resume` (or the `wakemark` stub, then `cpu_resume`); the kernel resumes from `cpu_suspend`. | [`~/Work/deepsleep-kernel` `glue.c` 1002-1020 `ds_arm_mailbox`; `resume.S`] |
| 7 | The glue runs the logic's wake calls: `leave_early`, `start_cores`, `leave_late`; then the record `'Dw'`. | [`glue.c` 1410-1440] |

- The mailbox lives in the loader's RAM, published at `/chosen/asahi,s2r-mailbox` by `s2r_publish` (kboot). [`src/s2r.c` 180-207; `src/kboot.c` 6555]
- Layout: magic, version 1, ncpus, rvbar, quiet, boot MPIDR, resumes, then one slot per core (MPIDR, RVBAR reg, start regs, `entry`, `resets`, `stage`). [`src/s2r.h`]
- On bare metal the address read `0x802df4a40` (2026-11-17); under the hypervisor no loader publishes one and `tools/hv-trace-kit/harness/ds_mailbox.py` fakes it (reset vector 0, nothing reads it at a wake). [evidence 2026-11-17-deepsleep-clean-runs, ds12 "The mailbox"]
- The glue writes core 0's slot with `cpu_resume`, cores 1-7 with the spin-table pen. [`glue.c` 1012-1018]
- mb2's own reset path arms watchdog 1 to 45 s in `s2r_reset_enter` and 75 s before the jump, only if its control bit 2 is set. [evidence 2026-11-17, breadcrumb section; `src/s2r.c` 53-70]
- For when a wake arrives: the P cluster is unpowered and the secondaries' RVBAR must be restored. [handoff-2026-11-19, Next step]

## Established

- macOS under the hypervisor m1n1 (`bd6a43d4`) does the whole chain: wake entry logged `AON wake status +0x1c=0 +0x20=0x400000 +0x24=0`, nonce checked, guest re-entered on CPU 0, about 0.65 s after the commit. [evidence 2026-11-16-hv-macos135-s2r, Sleep 2]
- macOS itself reads `0x23d00401c`-`2c` after the wake; `0x23d004020` = `0x400000`. [spec R33]
- macOS's first wake writes, interrupt controller, power manager, memory controller, then cores 7,6,3,2,5,1,4. [spec R28-R32, section 6 W1-W3]
- 2026-11-07 loader (omacom `bc79acc4` + lab commits): watchdog 1 "progress meter" at each reset-path stage gave 181.0 s: not even the first instruction at the RVBAR ran. [evidence 2026-11-07-linux-s2r, Runs 3-12, test 8]
- ds29 (`wakemark=3`, alarm 20 s, `wdt=150`), two runs: both up again 165 s after the start, the C3 record only, neither `'Dr'` nor `'DA'`: no wake reached the kernel. [evidence 2026-11-17, ds29]
- Breadcrumb run 2026-11-20 01:36 (loader `91d54c2`, `'Z'` at the reset vector into `0x9f0b`): 165 s, `0x9f0b`-`0c` = `00 00`. Outcome B: no wake reached the boot CPU. [docs/experiments/2026-11-20-boot-loader-breadcrumb.md; evidence 2026-11-17, breadcrumb section]
- The power chip's alarm did fire after a Linux commit on 2026-11-07 (`0xd000` 0x41 -> 0x01). [evidence 2026-11-07-linux-s2r, Run 2]

## Decided

- Loader marks: `0x9f0b` = `'Z'` vector ran, `'M'` mailbox gone, `'U'` no slot, `'N'` no entry (parked), `'H'` jumping; `0x9f0c` = wake-source bits. [`tools/m1n1/read-breadcrumb.sh` header]
- The kernel's `wakemark` bit 0: stub bites at 60 s, `leave_early` at 90 s and `'Dr'`; bit 1: `'DA'` if core 0's WFI returns after alarm + 2 s. [`glue.c` `wakemark` parameter]
- The installed loader is back to `0a1e47f3` (no breadcrumb). [docs/experiments/2026-11-20-boot-loader-breadcrumb.md, Result]

## Open

- Which one: the SoC never powers down; it powers down and nothing wakes it; or it woke with memory lost (looks like B). Read that settles it: a power-down signature (the M1's own draw, or `0x0201` after the reset) in one sleep. [experiment card "Not covered"; evidence 2026-11-17, Observation round 4 table]
- The breadcrumb code has never been seen to write. Read that settles it: start the loader's reset path on purpose (a reset after the hand-off, outside a sleep) and read `0x9f0b`. [experiment card, Result]
- The M3's draw (flat about 8.1 W) does not tell powered-down from up. [evidence 2026-11-17, ds28, ds29]

## Read more

- `docs/experiments/2026-11-20-boot-loader-breadcrumb.md`
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, sections "ds29" and "The boot loader's wake breadcrumb"
- `docs/evidence/2026-11-16-hv-macos135-s2r/README.md`
- `docs/spec/macos-13.5-sleep-wake-observed.md` section 6 (W0-W3), R28-R33
- `~/Work/m1n1-mb2-breadcrumb` `src/s2r.c`, `src/s2r.h`
