# Card: the Linux sleep entry and its commit point

What Linux's deep-sleep entry does, in order, named by the spec's requirement ids; what "the commit point" is.
Established: with every candidate on, the entry reaches the commit point every time, and the M1 never wakes. 2026-11-20.

## Decided: the order (glue = kernel C/arm64 half; logic = tested Rust driver)

| # | Step | Source |
|---|---|---|
| 1 | `begin`: D7 (e)'s check (Linux's `apple_wdt` not driving watchdog 1, no device access), then R61's four writes arm watchdog 1, then the 'Da' record | [D7 (a), (e); GL11] |
| 2 | Linux's device suspend; the `pmp` client's entry part (C18) runs in `prepare_late` | [D10 (b); evidence "ds28" kernel `a8d9ef4b8`] |
| 3 | Other cores offline and parked; `enter` calls the logic | [D7 GL11, GL14] |
| 4 | Coprocessors by their state: running = macOS's steps, stopped = nothing, silent = bounded wait then register stop | [D3, D3 (b), (c)] |
| 5 | "Entry start": the candidates' first accesses (C2, C6, C12 ...; C3 read (i)) | [8.2 "Common to every candidate"; D8 (d)] |
| 6 | Logic runs section 8's steps below; R16's or R22a's wait running out = D6 failure | [D6] |
| 7 | After R38's third `0x23d2c4000` write and C3 read (iii): the glue's commit-point step | [D8 (b)] |
| 8 | Final writes: cores 1-7, core 0 last; no device write in between | [R43, R44, R39; D8 (b)] |

**Section 8's steps, in macOS's order** (one phrase each; each is what macOS was seen to do):

| Id | Step | Id | Step |
|---|---|---|---|
| R1 | display coprocessor off; DISP0_CPU0, DISP0_FE, RMX off | R2 | memory-controller burst stopped |
| R3 | `smc`: `MBSE`=slpw, `WKTP`=2, slpa, AP power `0x201` | R4 | AP/coprocessor power `0x201` to each coprocessor |
| R5 | `sio`, `pmp` stopped (+`0x8114` bit 0, +`0x44`=0) | R5a | `dcp`, `dcpext`, `gfx-asc`, `ans` stopped the same way |
| R6 | `pmp` SRAM `0x23b52c000`.. read out (196,608 bytes) | R7 | GFX, DISPEXT, DISP0, RMX, APCIE_ST domains off |
| R8 | SPMI controllers +`0x338`=1 | R9 | power chip `0x9f01`=`0x50` |
| R10 | PCIe port 0 and `sio` translators +`0xfc` to 0 | R11 | cores 1-7 write stop bits; only core 0 touches devices after |
| R12 | temperature sensors stopped | R13 | three words written `0xffffffff` |
| R14 | the 17 PCIe writes | R15 | watchdog page: counts 0, `0x23d2b000c`=0 |
| R16 | memory controller quiesce, poll `0x200001c04` | R17 | `0x200155000`, planes, DCSn+`0x7a0` to 0 |
| R18 | five clock muxes `0x80100000` | R19 | timer/cluster words written 0 |
| R20 | three blocks +`0x14`, +`0x2bc` | R21 | bit 63 cleared in four cluster words |
| R22a | four power-manager sub-blocks stopped | R22 | `0x23b718000`, `0x23b718004` = 0 (the trigger) |
| R23 | SIO_CPU bit 28 cleared | R24 | `0x23d2c4000`=1 ("Starting S2R timer") |
| R36 | interrupt controller masked | R37 | `0x23d2c4000`=1, second time |
| R38 | alarm via SPMI (`0xd00c`, `0xd008`, `0xd00e`, `0xd000`=`41`), then `0x23d2c4000`=1, third time | R39 | no device write after; all eight cores go down within 31 us |

[spec section 8, R1-R39; R25 forbids other domain writes in the entry]

## Decided: the commit point
- macOS's "commit" = core 0's final write `CYC_OVRD_EL1`=`0x3000001`, the last of the eight [8.1; R43, R44].
- Linux's "commit point" = the glue's commit-point step: after R38's third `0x23d2c4000` write and C3 (iii), before any core's final write [D8 (b)].
- In the step: one record (`snap=2` 'C' or walk 'c', else the C3 record with `cand_c3`, else 'W'), R60's `0x23d0d9378`=1, then R61's four writes re-arm watchdog 1 [D8 (b); D7 (b)].
- After the step no glue access but `probe=1`'s record after the first final write [D8 (b), (e)].

## Established
- ds16: the round-7 driver reached the commit point ('C' record); M1 dark, no reset, no wake [evidence "Run ds16"].
- ds17 on: 'W' records, last access a 32-bit write of `0x23d2c4000` by core 0; watchdog reset [L17; evidence "Run ds17"].
- ds20: every switch alone but C3 and C5 reached the commit and reset; C3 and C5 alone hung before it [evidence "Runs ds20"].
- ds21 `0x3fffe` (C1-C17): commit reached, C3 record [evidence "ds21"].
- ds28 `0xffffe` (C1-C18 + bit 19): commit reached in every RESET row, C3 words at macOS's values [evidence "ds28"].
- ds29 (two runs) and the breadcrumb run: commit reached, no wake marker, no breadcrumb, kernel up 165 s after the start [evidence "ds29"; "The boot loader's wake breadcrumb"].
- macOS reaches its commit with the same words and powers down; Linux with them does not wake [8.2 C3; evidence "ds28"].
- The always-on program's first step (watchdog 2 armed for 5 s) follows R22's `0x23b718004`=0 under macOS by 1.3-7.5 us [R62].

## Open
- Does the SoC power down after Linux's commit and never wake, or never power down? Settles it: a breadcrumb positive control, or a power reading that separates the two [evidence "The boot loader's wake breadcrumb", "What this run does not show"].
- Whether the always-on program starts after Linux's commit: read watchdog 2 and `0x23d2b8028` right after the logic's `0x23b718004`=0 [open question 56; 8.2 "Where the Linux outcome points"].
- How long each watchdog stretch S1-S6 takes on the test kernel: the glue's `CNTVCT_EL0` log [D7 (d); open question 82].

## Read more
- `docs/spec/macos-13.5-sleep-wake-observed.md` lines 3996-4260 (section 8, R1-R39)
- same file, D8 at lines 5455-5598 (the commit point, the records)
- same file, D7 at lines 5149-5454 (where the glue arms and disarms)
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` "ds28" (line 4692) and "ds29" (line 4797)
- `docs/agents/handoff-2026-11-19.md` (state and next step)
