# Run 33: awake check of the SIO sleep step (2026-11-16)

**Question.** Does SIO acknowledge RTKit idle at suspend_late, and does it come back at resume_early?

**Setup.**
- Kernel 7.2.11-run33 (linux-aurora `m1power/s2r-rs1-135` f30994508). Lab job j1116-023845-db34, cmdline `apple_sio.s2r_idle=1`.
- apple_s2r_rs was not enabled, so there was no deep-sleep entry.
- One s2idle cycle ran with `pm_test=platform`. That runs the suspend, suspend_late and noirq steps, holds 5 s, and resumes.
- The boot used the boot.bin with the `sio` alias, so m1n1 set SIO up and apple-sio started it (protocol v9).

**Result.**

- Idle worked. `system sleep: coprocessor to RTKit idle: 0` at 19.81 s, before the 5 s hold.
- Wake failed. `RTKit: IOP power acknowledgment failed: -62`, then `after system sleep: coprocessor woken: -62` at 26.08 s.
- At resume, just before that, the power-state driver logged `PS fpwm1: Failed to reach power state 0xf (requested 0xf, now: 0xa4f)`. That word has bit 11 set: the parent is missing. A SIO-island parent was off at that moment.
- The coprocessor's status word was 0x2e before the cycle and 0x8 after. SIO stayed unusable for the rest of that boot. The machine returned to the stock kernel afterwards, as every lab job does.

**Reading (inferred, not read directly during the hold).**
- The power-state driver gives a domain that is on at boot `GENPD_FLAG_DEFER_OFF`. The kernel's power-domain framework keeps such a domain on at runtime, and the live summary does show `sio_cpu on` with its only device runtime-suspended.
- In the noirq suspend step, though, the framework powers it off. SIO's idle state lasts only while it is powered, so it lost its state and could not answer the wake.
- macOS keeps sio_busif, sio and sio_cpu on through its sleep commit, and leaves the island's power-down to the chip's own sleep program.

**Next.** Repeat the check with `sio_cpu` held on through system sleep (`pmgr_pwrstate.always_on=sio_cpu`; its parents stay on with it). Then a real entry with SIO idle can test gate #45.
