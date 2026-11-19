# Card: the power-chip records `0x9f04`-`0x9f0d` and the bytes read after a run

The glue's ten scratch bytes are the only Linux state that survives the reset; each record is 'D' plus a letter.
Read them, and `0x0201`, the fault shadow and `0xd000`, after every run with `tools/tb/m1-pmu-dump`. 2026-11-20.

## Established: how the bytes behave
- Ten bytes, 'D' (`0x44`), then the letter; bit 7 of byte 1 = SError pending [evidence "How the fault record works"; "Run ds10"].
- Written as three SPMI commands: `0x9f04`-`07`, `0x9f08`-`0b`, `0x9f0c`-`0d`; in ds16 and ds16b the third did not land [evidence "Run ds16b"].
- `0x9f0d` is cleared at boot: dsh1's trace wrote `0xc8`, it read 0 after [evidence "Hypervisor round 1"; `tools/m1n1/read-breadcrumb.sh`].
- Only the last record survives a reset [D8 (f)].

## Established: the letters

| Rec | Who writes it, when | Bytes 2-9 | Source |
|---|---|---|---|
| 'Da' | glue `begin`, after arming watchdog 1 | not decoded; ds20 C3 `44 61 00 ...` = armed, commit not reached | [D7 GL11; evidence "Runs ds20"] |
| 'T' | glue, a logic wait ran out (D6) | 2-6 address LE (40 bits), 7 kind and core, 8-9 access count low 16 bits LE | [D6 (g); D8 (c); evidence "ds21", record 2] |
| 'P' | glue's panic notifier | as 'T': the last access | [D7 GL13; evidence "Run ds10"] |
| 'E' | glue's die notifier (oops) | as 'T' | [D7 GL15; evidence "Readings" (ds3)] |
| 'W' | commit-point step, no other record set | as 'T'; always `0x23d2c4000`, write by core 0 | [D8 (b); L17] |
| 'C' | commit-point step, `snap=2` | 2-3 M (words neither written nor as read before), then 16-bit indices; bit 15 clear = expected value was the reading before the entry | [evidence "Run ds16"] |
| 'c' | commit-point step, the commit walk | 2-3 index, bit 15 = changed by itself; 4-7 value LE | [L24] |
| 'V' | commit-point step, `cand_c3` on | the C3 record, D8 (f) (below) | [D8 (f); evidence "ds21"] |
| 'Q'/'q' | core 0 after cores 1-7's final writes, `probe=1`; 'q' = watchdog armed | 2-3 k, bit 15 = captured; 4-7 value; 8-9 values captured | [D8 (e); evidence "Runs ds19p-74, ds19p-75"] |
| 'Dr' | `wakemark` bit 0: before `apple_ds_leave_early` (90 s bite) | not decoded | [evidence "ds29"] |
| 'DA' | `wakemark` bit 1: core 0's WFI returned > alarm + 2 s after the commit-point step | not decoded | [evidence "ds29"] |
| 'Dw' | the kernel's wake path finished (`end`) | not decoded | [`tools/m1n1/read-breadcrumb.sh` letter table; not in spec or evidence] |
| 'X' | "other failure" | seen once (dsh1): `00 f5 1d 00 00 61 05 00`, not decoded | [evidence "Hypervisor round 1"; read-breadcrumb.sh] |

- Byte 7 seen: `0x10` = 32-bit read by core 0, `0x30` = 32-bit write by core 0; the kind/core split is not written out; every example has core 0 [evidence "ds21", record 2].
- One record per commit-point step: 'C' or 'c', else 'V', else 'W' [D8 (b)].

## Decided: the C3 record ('D','V') [D8 (f)]
- Slot s = 0..8: (i) entry start, (ii) after R22, (iii) after R38, each `058000`, `05c000`, `060000`.
- Code of slot s in byte 2 + s/2: low nibble for even s, high for odd. d (0-`0xd`) = value d x `0x111`; `0xe` = other; `0xf` = not read.
- Byte 6 high nibble: highest slot coded `0xe`, or `0xf`. Bytes 7-9: that slot's value in part, else 0.

## Worked examples
1. ds20 C5 alone: `44 54 c0 01 70 3b 02 10 80 00` [evidence "Runs ds20"].
   'D','T' (`0x54`, bit 7 clear) | bytes 2-6 LE `0x023b7001c0` = SIO_BUSIF `0x23b7001c0` | `0x10` 32-bit read, core 0 | count `0x0080`. A wait on SIO_BUSIF ran out.
2. ds28 C1-C18: `44 56 43 32 24 43 f2 00 00 00` [evidence "ds28"].
   'D','V' | `0x43` -> slot 0 = 3, slot 1 = 4 | `0x32` -> 2, 3 | `0x24` -> 4, 2 | `0x43` -> 3, 4 | `0xf2` -> slot 8 = 2, no `0xe`.
   So `0x333/0x444/0x222` at all three places; the commit point was reached.

## Established: the other bytes
- `0x0201`: always-on program decode: sleep sequence 1 writes `01`, sequence 5 `02`, wake sequence 10 `00` [evidence "Observation round 4"; spec 4.4].
- `0x0201` after runs: `04` after ds16, ds17 and ds20; `00` after ds19p and ds21-ds29 [evidence "Run ds17"; "Runs ds19p-74"; "Runs ds20"; "ds21"; "ds29"].
- `0x9f03` "boot-error-stage": `0x50` after resets, `0x00` after macOS's wakes [evidence "Observation round 4"; spec 1.7d].
- Fault shadow `0xa47b`-`d`, LE word: bit 11 `wdog,reset_in_1`; bit 10 `btn_rst`; bit 12 `dbg_rst,reset_in_2`; bit 18 `dblclick_timeout` [evidence "Observation round 4"].
- `00 08 00` (bit 11) also after macOS's alarm wake K: it does not separate a reset from a wake [spec 1.7d "The power chip after each run"].
- `0xd000` alarm control (enable bit `0x40`): `0x41` after resets before the alarm time, `0x01` after wakes [spec E6; 1.7d].
- `0xd000` `03` / `0xd00c` `01` only after ds10-ds12 and dsh1, whose alarm passed with Linux up; "fired" is the lab guide's inference [evidence "Observation round 4"].
- Breadcrumb loader (not installed now): `0x9f0b` 'Z','M','U','N','H', `0x9f0c` wake-source bits [evidence "The boot loader's wake breadcrumb"].

## Open
- 'Da', 'Dr', 'DA', 'Dw' bytes 2-9: not in the spec or evidence. One read: the glue's record code in the kernel tree [evidence "ds29"].
- Whether `0x0201` `00` after ds21-ds29 means entry `01` then wake `00`, or never written: `0x0201` read just before the sleep [evidence "ds21", "Against ds20"].

## Read more
- `docs/spec/macos-13.5-sleep-wake-observed.md` lines 5483-5598 (D8 (b), (c), (e), (f))
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` lines 48-55 and 3420-3450 (layouts)
- same file, lines 756-893 (Observation round 4: `0x0201`, fault shadow, `0xd000`)
- `tools/m1n1/read-breadcrumb.sh` (decoder and letter table)
- `tools/tb/m1-pmu-dump` (what is read after a run)
