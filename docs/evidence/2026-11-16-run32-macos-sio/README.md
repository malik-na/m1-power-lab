# Run 32: the SIO island in macOS's state still does not report ready (2026-11-16)

Kernel 7.2.11-run31 (b96f16080, `sio_on`). Run 31's command line with ps_fpwm1 released (no
`pmgr_pwrstate.always_on=fpwm1`), `fpwm_settle=0` (it runs before sio_on and would refuse fpwm1's
parent-missing word) and `sio_on=1`: the parents on and fpwm1 off, the state macOS hands over
(try55, try62). Cable in, force-discharge at the gate (07:25:41.87, Discharging -0.38 A), 0x0201
= 04 before. fpwm1 read 0x000002ff before the gate (the PWM driver holds it while awake).
Lab job j1116-015428-ece3.

| | run 27b | run 31 (sio_on, fpwm1 held) | run 32 (sio_on, fpwm1 released) |
|---|---|---|---|
| open gates, slow part / release | #45 #47 / #45 #47 | #45 #47 / #45 #47 | **#45 #47 / #45 #47** |
| fpwm1's own power-state gate (SEQ0_GATES index 1) | closed | closed | **closed** |
| 0x0201 | 04 -> 01 | 04 -> 04 | **04 -> 01** |
| ENTRY -> SoC reset (next kernel start minus 10.84 s) | ~11.1 s | ~6 s | **~10.8 s** |

Next kernel start: 1794794191.72 (date) - 19.43 (uptime) = 07:26:12.29; postmortem: next boot
21 s after the recorded entry, A1 "04 -> 01". The M3 Max saw the Thunderbolt host disconnect at
07:25:50.68 (with the entry) and the M1's type-C detach at 07:25:56.65; with the SIO parents
switched by sio_on the detach is not a reliable reset marker (the type-C controllers sit on i2c0
in the SIO island), so the reset time comes from the next kernel's start.

## What it establishes

- With its parents on, a released fpwm1 no longer blocks: its own power-state gate is closed
  (run 28, without sio_on, refused on fpwm1 = 0xa00). The parent relation inferred in run 29 holds.
- The SIO island's gate #45 still does not report ready in the macOS-like state, so the parents
  and fpwm1 are not the whole cause. The ending is run 27b's again: the chip's sequence runs
  (0x0201 -> 01) and the SoC resets ~11 s after the entry.
- Run 31's early reset (~0.5 s after the commit, 0x0201 unchanged) belongs to the state with the
  parents on and fpwm1 held on, which macOS never produces.

Open: what else #45 waits on. Candidates not yet tested: the power-gate records themselves (the
sleep program writes 0x80080860-style values to them before polling; Linux leaves 0x800403xx), the
other island members' states after sio_on (only fpwm1's is visible in the record), and #47's
PCIe / NVMe island, which is open in every run so far.
