# Run 34: the SIO sleep check with sio_cpu held on (2026-11-16)

**Question.** Does SIO answer the wake from idle once its domains cannot be powered off? Run 33's wake timed out, and a SIO-island parent was off at resume.

**Setup.** The same kernel (7.2.11-run33), script and `pm_test=platform` cycle as run 33, plus `pmgr_pwrstate.always_on=sio_cpu`. Lab job j1116-024346-8c83.

**Result.**

- The power-state driver logged `domain sio_cpu kept on by always_on=`. The kernel's power-domain summary showed sio_cpu, sio, sio_busif and fpwm1 `on` before the cycle and after it. Run 33's `fpwm1 ... 0xa4f` error did not appear.
- Idle worked again. `system sleep: coprocessor to RTKit idle: 0 (cpu control 0x10 status 0x2e)`.
- The wake failed again, as in run 33. `RTKit: IOP power acknowledgment failed: -62`, then `after system sleep: coprocessor woken: -62`.
- The coprocessor status word went from 0x2e to 0x8. Read with m1n1's register map, whose bit names are partly guesses: 0x2e has IDLE (bit 5) and STOPPED (bit 1) set, so the core was halted in its idle wait. 0x8 has neither, and the IRQ-not-pending bit is clear, so after the wake request the core is running with an interrupt pending. It never acknowledged, and it logged no crash.

**Reading.** Run 33's power loss was real, but it is not why the wake fails. With the domains held on, SIO still accepts the idle and does not answer the INIT wake (0x220) that `apple_rtkit_wake` sends. This kernel has no record of any coprocessor waking successfully from RTKit idle. DCP uses the same call for deep sleep, but no deep sleep has ever woken.

**For gate #45.** The idle request itself is acknowledged. The wake only matters once the machine wakes from suspend-to-RAM at all, which it never has.
