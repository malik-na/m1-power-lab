# Milestone 1 report: Aurora's leads, read on the M1 (2026-11-20)

Probe lane. 5 of 8 M1 runs, 5 sub-agents, 1 probe branch (`~/Work/dsk-probe-m1-leads`,
`probe/m1-leads`, `52669b5bb..6fe52a780`, never merged). Cards: `docs/experiments/2026-11-20-m1-*.md`.

## Finding

After Linux's commit the SoC never begins to power down. The always-on program is in sequence 12
with watchdog 2 armed at the commit (as macOS), takes Linux's cores going idle (all down within
1.65 ms), stops watchdog 2, and never enters sequence 0 (AWAKE->AOP_DDR): no 5 s reset, `0x0201`
never 01 (read 04 before and after). Held 3 s with core 0 up, it waits in sequence 12 and watchdog
2 resets the SoC at about 5 s, as macOS did with a core up. So the missing piece sits between the
engine's cores-idle check and sequence 0's first write; the wake path is not reached at all.

## The leads

| Lead | Reading on the M1 | Verdict |
|---|---|---|
| 1 Wake masks | Linux 153 of 154 sources enabled; set to macOS's values (read back, 16 unmasked), no status pending: no change | out (not sufficient) |
| 2 DCS state 4 / PMC voters | C3 words `0x333/0x444/0x222` at the commit (state 4); PMC voters: no t8103 word named, not read | DCS out; voters unread |
| 3 AMCC error enables | word0 bit 25 / word1 bit 8 clear on planes 0-3 at the commit, before any fix | out |
| 4 Gate records | `0x23b71c090` bit 30 clear, `0x23b71c360` set at the commit, as macOS's | out |
| 5 RVBAR | cpu0 `0x00100008025dc001`: locked to the loader image `0x8025dc000` | locked (aura's note does not hold); wake path design right |
| Timing (Aurora's 33 ms) | 1.65 ms from the first `0x23d2c4000` write to core 0's last write | out (not slow) |

## Recommendation

Not the build lane yet: Aurora's driver structure with t8103 tables would add masks and AMCC
clearing, which change nothing here. One more probe milestone first, on the engine's step after
the cores go idle:
1. A macOS-vs-Linux diff of the always-on blocks the engine reads there (`0x23d2c4000`-`0ff`,
   `0x23d2b8000`-`0ff`, `0x23d2c0000`-`0ff` AOP config, the CPU cluster power-state words) at each
   commit: the macOS side from the hypervisor's commit lists (`var/recfg/commit-snap-list*.json`
   may already hold them), the Linux side from one probe run (k table, as here).
2. The 11 SMC shared-memory writes macOS makes after its last `0x23d2c4000` write
   (`0x23fe5f1f8`-`220`, spec section 4, D step 4): Linux makes none; what they are is not read.
3. The sampler at 20 ms and 50 ms instead of 3 s (two runs) bounds the engine's cores-idle window.
The build lane follows once one of these makes sequence 0 start (`0x0201` = 01 after a run).

## Left over

- The M1 is in stock Omarchy, claim released. Probe kernels: `var/kernels/m1leads/`, `var/kernels/m1samp/`.
- `tools/tb/m1-cand-runs`: reads `0x0201` before the sleep (nvmem name globbed: `spmi_nvmem3` on the
  test kernel) and waits 45 s for the start step; its start still failed twice on the probe kernel
  (too early in boot), so runs 3-5 used the session's own start script. Not fixed.
- Nothing committed.
