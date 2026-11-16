# Runs 36-38: the ~5 s restart after the release is a firmware reset, not watchdog 2, not the PMP, not a wake (2026-11-16)

## Premise check before run 36

- In the decoded sleep program (live SRAM under 13.5: sequences 0-3 byte-identical to the
  2026-11-08 dump), the power chip's 0x0201 = 01 is written in **sequence 1** (0x08204), after
  sequence 0 has run all its gate polls (#45 0x23b71c090, #47 0x23b71c360). Runs 27b and 32 read
  04 -> 01, so the engine got past both gates. The gate records of runs 27-35b were taken before
  the engine ran (slow part, release) and show only Linux's state; they did not show the stall.
- The engine's program SRAM ignores AP writes (no fault); its progress registers (0x23d2b8028,
  0x23d2b8040) read boot values after a restart.
- The second power chip (SPMI controller 0x23d0e1300, slave 0xf, no Linux driver) is readable:
  0x2808 = 04 both after a run and after a cold start, so it marks nothing.
  Tool: `tools/tb/m1-pmu-dump`.
- The power chip's abnormal-restart counter 0x9f02 does not move on these restarts (acceptance
  script: "wake-restart", not "watchdog").

## Run 36 (j1116-071814-901e, kernel 7.2.11-run36 = 4f3b5f364, cold start before)

`wd2_extend_s=100`: after the release the boot core waits for the engine to arm watchdog 2
(5 s) and moves the deadline to 100 s. Record 0x9f10-17 `d2 01 04 05 64 01 00 01`: seen armed
on the first read (control 4, 5 s), read back 100 s.

| M3 / M1 clock | Event |
|---|---|
| 12:49:26.59 | rmmod apple-sep, suspend; Thunderbolt paths torn down |
| 12:49:29.996 | USB4 host disconnected (the release ~3.4 s after the suspend) |
| **12:49:35.5** | **the M1's type-C partner disappears on the M3 Max: the M1 restarts** |
| 12:49:53 | next kernel start |

0x0201 04 -> 01; 0x9f02 unchanged. **The restart stays ~5.5 s after the release with watchdog 2
at 100 s: it is not watchdog 2.**

## Run 37 (j1116-073205-9163, kernel 7.2.11-run37 = 663f8994d)

Run 36 plus, together: the PMP started (`apple_pmp_v1_hold=1`, apple-pmp-v1) and idled between
slpw and slpa (`pmp_idle=1`, as macOS; macOS will not sleep without it, try61), and `mac_off=1`
(atc0_common, gfx, i2c0, i2c3 off in the slow part, as at macOS's commit). Record
`d2 01 04 05 64 01 01 01`: watchdog 2 moved, **PMP idle acked (byte 6 = 01)**.

rmmod 13:03:28.89, USB4 host disconnected 13:03:32.58, type-C partner gone between 13:03:36.84
and 13:03:37.85: **again ~5 s after the release.** Neither the PMP idle nor the four domains
change the restart.

## What it establishes

- The sleep sequence reaches sequence 1 and the chip restarts ~5-6 s after the release by
  something other than watchdog 2 and not counted as a watchdog reset. Under the earlier system
  firmware (runs 1-11) the same program slept until the alarm; the restart is new with 13.5.
- SMC, AOP and NVMe syslogs in the next boot say nothing about it; the SMC keys that look like
  causes (MSXN, MSXn) are the same in every snapshot today.

## Run 38 (j1116-074211-b310, kernel 7.2.11-run38 = bd065c9c9)

Run 36 with `wake_mask=4`: every AP wake source masked (the 60 s alarm kept: the frozen acceptance
script needs it). Record `d2 01 04 05 64 01 00 01`: watchdog 2 moved to 100 s.
rmmod 13:13:35.60, USB4 host disconnected 13:13:38.82, the M1's type-C partner gone between
13:13:43.67 and 13:13:44.69: **~5 s after the release again, with no wake source open.**
0x9f02 unchanged.

## Conclusion of the three-run budget

Under system firmware 13.5 the M1 is reset ~5 s after the release by something outside the AP:
not watchdog 2, not an AP wake source, not counted by the power chip as a watchdog reset, and
unmoved by the PMP idle or by atc0_common/gfx/i2c0/i2c3. The candidates left are the SMC and
power-chip firmware (and the AOP), which only a trace of macOS 13.5 can separate. Per the agreed
rule, the next step is the m1n1 hypervisor: trace macOS 13.5's entry with the two SPMI controllers
(0x23d0d9300, 0x23d0e1300) and the AOP mailbox added to the traced zones, which the 2026-11-07
traces did not cover.

Raw state: var/m1-state/*-run36, *-run37, pmu-*.txt (private).
