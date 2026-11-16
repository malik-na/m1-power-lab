# Run 35: with SIO idle, the driver refused before the commit (2026-11-16)

Lab job j1116-063331-8519. Kernel 7.2.11-run33 (f30994508 = run 31's b96f16080 plus the
apple-sio `s2r_idle` step), m1n1 with the `sio` alias. Run 32's command line plus
`apple_sio.s2r_idle=1 pmgr_pwrstate.always_on=sio_cpu`. Cable in, force-discharge set at the
gate (12:04:46, Discharging), no cold start (0x0201 = 01 before and after).

Question: does gate #45 (the SIO island) report ready once SIO is in RTKit idle?
**Not answered.** There was no entry.

## What happened

| Step | Record |
|---|---|
| Boot | apple-sio bound, SIO protocol v9, `sio_cpu kept on by always_on=` |
| Before the gate | sio_busif, sio, sio_cpu all `0x1400024f` (target f, actual 4, auto bit 28 set); ASC control 0x10, status 0x2e |
| suspend_late | `system sleep: coprocessor to RTKit idle: 0 (cpu control 0x10 status 0x2e)` |
| s2r last stage, `sio_on` | read sio_busif `0x1400024f`, write `0x1400024f`, 50 ms later still `0x1400024f` |
| Result | `fail precheck 0x23b7001c0 0x1400024f`: the write returned EIO, acceptance A1 FAIL, `THE ENTRY RETURNED` |
| resume_early | `after system sleep: coprocessor woken: -62` (as runs 33 and 34) |

Also in this cycle: both display coprocessors answered RTKit idle with -62
(`apple-dcp 271c00000.dcp` and `231c00000.dcp`). Not checked against runs 31 and 32.

## What it establishes

- The refusal is this driver's own check, not the chip. `sio_on` (run 30) waits for
  sio_busif and sio to read actual f. With SIO running and idle they read actual 4
  (clock-gated) because the auto flag (bit 28) is set. In runs 31 and 32 SIO never ran, so
  the check passed.
- macOS commits sio and sio_busif as `0x0f0000ff`: target f, actual f, auto flag clear.
  Linux leaves the auto flag set. That difference is the likely reason actual stays at 4
  (inferred; not tested).

Open: whether `sio_on` clearing the auto flag on sio_busif and sio (macOS's commit value)
lets the precheck pass, and then whether gate #45 reports ready.
