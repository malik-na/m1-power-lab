# Run 31: turning the SIO parents on changes the ending, but does not clear #45 (2026-11-16)

Hypothesis under test (from run 29): the SIO island's gate #45 never reports ready because Linux
has the island's parents (sio_busif, sio, sio_cpu) off at the commit, while macOS has them on.
Fix under test: kernel 7.2.11-run31 = linux-aurora m1power/s2r-rs1-135 b96f16080 (`sio_on`: at the
end of the slow part write the three parents' target to f, parent first, and wait for sio_busif and
sio to read actual f and sio_cpu actual 4, macOS's commit value). Host tests 21/21 (red commit
706e2db42 before the fix e4285c899). Run 27b's command line + `sio_on=1`, fpwm1 still held on,
cable in, force-discharge at the gate (07:08:52.87, Discharging -0.37 A), 0x0201 = 04 before.
Lab job j1116-013745-ca2d. Dry run skipped: the driver writes nothing to the chip in dry mode
after interrupts are off (`writes_off()`), so a dry run could not show the fix.

| | run 27b (no sio_on) | run 31 (sio_on=1) |
|---|---|---|
| stage 0x9f0a | 'R' | 'R': sio_on did not refuse, the release was reached |
| open gates at the slow part / at the release | #45 #47 / #45 #47 | **#45 #47 / #45 #47** |
| 0x0201 | 04 -> 01 | **04 -> 04** (postmortem: "the chip's own sequence did not run") |
| entry to next boot (postmortem) | 25 s | **20 s** |
| ENTRY -> USB4 port dies (M3 Max) | +5.8 s | +5.8 s |
| ENTRY -> M1 type-C detach (M3 Max) | +11.1 s | +6.6 s |
| SoC reset (next kernel start 07:09:12.94 minus 10.84 s firmware) | ~5.3 s after the port | **~0.4-0.8 s after the port** |

## What it establishes

- The hypothesis "parents on at the commit lets #45 clear" is **refuted** as tested: the gate
  scan (taken after sio_on) still shows #45 open, and the chip resets ~0.5 s after the commit,
  before the sleep program's first write to 0x0201 (sequence 1), instead of waiting ~5 s on #45.
- The SIO parents matter to the chip: changing only them moved the ending by ~5 s.
- The state tested is one macOS never has: parents on with fpwm1 held on. macOS asks fpwm1 off
  (target 0) in the same burst (try55, try62). The macOS-faithful state is parents on AND fpwm1
  released; with fpwm1 released Linux leaves it parent-missing (run 28), and the driver's
  fpwm_settle check, which runs before sio_on, refuses that.
- The type-C controllers sit on i2c0 inside the SIO island, so the detach moving is not by itself
  the reset; the reset time comes from the next kernel's start.

Next: the macOS-faithful state: fpwm1 released, sio_on, and fpwm_settle off (or sio_on moved
before it), with gate_record showing whether fpwm1's own power-state gate (#2) is clear.
