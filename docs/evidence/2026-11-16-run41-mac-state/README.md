# Run 41: the power-state and clock words set as macOS has them at its commit: still a restart 5 s after the release (2026-11-16)

## The reading behind it

The tracer now reads 249 extra words when the last core reaches its commit (`S2R_SNAP_LIST`,
list `var/recfg/commit-snap-list.json`: the PMGR power-state, clock-generator and always-on words
the engine's wake sequences read, all read before under Linux). One non-real hypervisor run each:
macOS 13.5 (135snap1) and Linux run40 (lx12), 279 words, no read errors
(`var/commit-state/`, private). 54 differed: gpio and nine UART domains on under macOS, off under
Linux; display front ends and coprocessor cores, rmx, fpwm0-2, dpa0 off under macOS, on or idle
under Linux; six SoC clock words disabled under macOS, enabled under Linux; two always-on clock
words and the NCO word enabled under macOS; flag bits.

## Run 41

Kernel 7.2.11-run41 (s2r-rs1-135 fd1a33c5d, package sha256 eafdf5ef…), run 40's set plus
`mac_state=1` (those words set in the slow part). Over Thunderbolt (`tools/tb/m1-bootonce`).

| M3 clock | Event |
|---|---|
| 23:20:50.34 | Thunderbolt host disconnected (the release) |
| 23:21:20.32 | new host found, Omarchy, uptime 21.5 s at 23:21:28: a restart |

The same 30.0 s as runs 40 and lx11. 0x0201 = 01.

## What run 41 left at its commit (hv run lx13, same reading)

18 of the 54 words now equal macOS's. The 36 left:

- flag bits only (bits 8/9, "was clock/power gated" history): gpio, UARTs, sio_cpu, disp front
  ends, atc0_common: the target and actual states now match;
- eight SoC clock words differing in bit 8 alone: the write did not change it (a status bit);
- dcs0-4: actual state 4 (idle, auto-gated) under macOS, f (active) under Linux at the reading;
- **ps_gfx: macOS 0x0f002300, Linux 0x0f002b00: bit 11, transition in progress, still set under
  Linux** (target 0 written in the slow part since run 37; the GPU coprocessor's run control read
  0x10, running, before the entry);
- the watchdog words (Linux's 170 s net; timing).

## Next

- GFX: get its power-down to complete as under macOS (off early, coprocessor stopped, busy clear).
- Widen the reading to the memory-cache controller, the DRAM controllers and the AOP's
  configuration words (`var/recfg/commit-snap-list-wide.json`), on both systems.
