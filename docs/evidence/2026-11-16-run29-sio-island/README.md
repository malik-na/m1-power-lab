# Run 29 (dry): why the SIO island never reports ready (2026-11-16)

Diagnosis, not a fix. Run 27b's setup (kernel 7.2.11-run26, fpwm1 held on, cable in,
force-discharge at the gate) with the driver's `dry=1`: everything up to the commit is real,
then the driver returns into the same boot and prints its trace; with `gate_record=1` the trace
holds every power word the chip's sleep program checks, read at the end of the slow part.
Lab job j1116-012036-ae98: suspend entry 43.47 s, exit 44.78 s, 338 trace lines, no driver
failure. Raw: var/m1-state/run29/dmesg.txt (private).

## The SIO island as Linux hands it to the chip

| Domain | Linux, run 29 (slow-part end) | macOS at its commit (try55 = try62) |
|---|---|---|
| sio_busif, sio | 0x0f000200: off (target 0) | 0x0f0000ff: **target f (on)** |
| sio_cpu | 0x0f000200: off | 0x0400024f: target f |
| uart_p, uart0 | off | 0x100000ff: on (likely the hypervisor's console UART) |
| fpwm1 | 0x000002ff: **on** (held by always_on) | 0x000003f0: target 0 (asked off) |
| fpwm0, fpwm2 | 0x00000244: **state 4** | no write |
| i2c0, i2c3, aes, spi1-3 | off | target 0 (asked off) |
| every other child | off | no write |
| gate #45 (0x23b71c090) | 0x8004030c: bit 30 = 0, not ready | |

macOS values: var/recfg/macos-commit-values.json (hypervisor traces try55, try62, private).

## Diagnosis

The chip's sleep program switches the SIO island off itself, children first and sio / sio_busif
last, then waits for the island's power gate (#45) to report ready. macOS prepares for that: it
turns sio_busif and sio on (target f) about 1 ms before the commit and asks the children off.
Linux does the reverse: its power-domain framework has already switched sio_busif and sio off at
suspend, while the PWM domains in the same island stay powered (fpwm1 held on, fpwm0/fpwm2 at
state 4), because Linux's device tree gives ps_fpwm0-2 no parent. With the parents gone, the PWM
domains cannot be switched off cleanly: released (runs 19, 28) fpwm1 reports parent-missing
(0xa00); held (runs 22, 27b) the island still has powered members and #45 never sets. The sleep
program then waits until its own watchdog resets the SoC ~5 s later (run 26 watch, run 27b).

Status: the mechanism is inferred from three agreeing observations (run 29's island state,
runs 28/19's parent-missing flag, macOS's commit values); it is not yet proven by a run that
changes it.

## Source

- `arch/arm64/boot/dts/apple/t8103-pmgr.dtsi`: ps_fpwm0 (l.240), ps_fpwm1 (l.248), ps_fpwm2
  (l.261) lack `power-domains = <&ps_sio>`, which every other SIO child has (e.g. ps_i2c0).
  On the M1 the loader supplies the device tree; the run kernels act through
  `pmgr_pwrstate.always_on=`.
- `drivers/soc/apple/s2r_seq.rs:1661-1664` (step 3d): for SIO_PS (sio, sio_busif, sio_cpu) the
  driver only clears bit 28; it never sets their target back on as macOS does.

## Next (a fix, not part of this diagnosis)

Smallest change expected: in the driver's last stage, before the cluster words, write sio_busif,
sio and sio_cpu to macOS's commit values (target f) and wait for them to read on; then a dry run
to see #45 and the island, then a real run with gate_record to see whether #45 is still open.
