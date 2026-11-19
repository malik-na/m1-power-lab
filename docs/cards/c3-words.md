# Card: the C3 words `0x23b058000` / `0x23b05c000` / `0x23b060000`

Three power-manager performance-state words; no application processor ever writes them under macOS, and they follow `pmp`'s events.
Linux now reaches its commit with macOS's values in them (ds28) and still does not wake. 2026-11-20.

Values are written `058000/05c000/060000`. Every reading has the form d x `0x111` [D8 (f) reasons; 8.2 C3].

## Established: values

| When | Values | Source |
|---|---|---|
| m1n1 proxy, no OS (301 samples, 300 s) | `0x444/0x666/0x333` | [1.7h "Before any operating system"; 8.2 C3] |
| Linux awake, stock kernel, `pmp` never started | `0x444/0x666/0x333`, do not follow cluster states | [L27; L29] |
| Linux awake with the `pmp` client (ds27p) | `0x444/0x444/0x333` | [evidence "ds28", the record] |
| macOS boot, after `pmp`'s start and opening | `0x444/0x444/0x444` | [1.7h "The words at boot"; R75 (a)] |
| macOS boot, first sample after `0x0020e00000550000` | `0x333/0x444/0x222` | [R75 (b)] |
| macOS awake (85 snapshots) | `0x333/0x444/0x222` | [8.2 C3] |
| macOS at the commit (15 detached captures) | `0x333/0x444/0x222` | [8.2 C3] |
| at every wake, before macOS runs (22 wakes) | `0x333/0x555/0x333` | [8.2 C3; 1.7h "Wake"] |
| macOS after the wake's 0x55 word (W+0.5 s) | `0x333/0x444/0x222` | [1.7h "Wake"] |
| earlier Linux driver's commit under the hypervisor (`pmp` started, 0x55 sent) | `0x333/0x444/0x222` | [L28; L30] |
| ds21 commit, C1-C17, no `pmp` | `0x444/0x666/0x333` at all three places | [evidence "ds21", record 1] |
| ds28 / ds29 commit, C1-C18 | `0x333/0x444/0x222` at all three places | [evidence "ds28"; "ds29"] |

## Established: what moves them
- No core writes them under macOS; only 32-bit reads of the first word of the last two pages, 48 boots [R70].
- Each change comes in the first 250 ms sample after a `pmp` event [R75; 1.7h "What it adds"].
- Hypervisor round 10 (det33, det34b): start + opening gives `0x444/0x444/0x444`; the endpoint-`0x20` word `0x0020e00000550000` gives `0x333/0x444/0x222`, and PMP/PMS_SRAM first read `0x1000030f` [1.7h; evidence "Hypervisor round 10"].
- Hypervisor round 11 (det35-det37, the 0x55 word dropped): 060000 stayed `0x444` with `pmp` running; in det36's entry 058000 reached `0x333` after `…540000` and 060000 `0x222` after `pmp`'s stop; the chip powered down and woke [R75 (c); evidence "Hypervisor round 11"].
- Hypervisor round 12 (det38, det39): macOS's translator holds 113 entries and the opening region holds energy-model bytes and 41 records; with them `pmp` runs under Linux (ds27p) [R76; handoff "What tonight established"].
- macOS's entry: `…550001`, `…540001`, `0x208` `0x63` answered, `…550000`, `…540000`, then R4, R5 [R73].
- macOS's wake: `…630001`, both `…0001` words, then both `…0000` words [R74].
- Writing them from Linux hung: ds20 `cand_c3` (round-12 write) stayed dark, record 'a' [L25]; macOS with Linux's values written in reached no commit, 2/2 [1.7g, HV-CHANGED].
- The ds28 record: `44 56 43 32 24 43 f2 00 00 00` = codes 3 4 2 at each place [evidence "ds28", "The record, by D8 (f)"].
- The ds21 record: `44 56 64 43 36 64 f3 00 00 00` = codes 4 6 3 at each place [evidence "ds21", "Record 1"].

## Decided
- The logic writes none of the three, with or without any switch [R70; 8.2 C3 revised round 13].
- With `cand_c3`, the logic reads them at (i) entry start, (ii) right after R22's trigger, (iii) after R38's third write [8.2 C3; D8 (a)].
- The nine values reach the glue as the commit-point step's argument; the glue writes one C3 record there [D8 (a), (b), (f)].
- C18: the `pmp` client starts `pmp` at boot and sends macOS's endpoint-`0x20` words, so the words reach macOS's values by `pmp`'s events [8.2 C18; D9-D11; D17].

## Decided, not a reading: the always-on program's decode
- Sleep sequence 0 writes 058000 = 3, then 05c000 = 4, each with a bit-31 wait; later both = 2 [8.2 C3 "The always-on program"; documentation of program memory].
- Wake sequence 4 writes all three 0; sequence 7 writes 058000 and 05c000 = 2 [same].
- macOS's awake values are already sequence 0's first targets; Linux's (4, 6) are not [same].

## Open
- Whether the 0x55 word causes the change, and what writes the words (`pmp`, the always-on side or the hardware). One read: a delayed send of the word under the hypervisor, not yet run [R75 "Not established"; 1.7h "Limits"].
- Whether their values at the commit matter to the power-down: ds28 has macOS's values and no wake, so they are not enough alone [evidence "ds28"; R75 "Not established"].
- Whether `pmp` was running at ds28's commit: the client's entry-part log [evidence "ds28", "What ds28 does not show"].

## Read more
- `docs/spec/macos-13.5-sleep-wake-observed.md` lines 6568-6691 (8.2 C3)
- same file, lines 1051-1375 (1.7h: `pmp`'s start, endpoint `0x20`, rounds 10-12)
- same file, R70-R76 at lines 4711-4880
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` lines 2096-2333 (hypervisor round 10), 3125-3378 (round 11)
- same file, lines 3956-4256 (hypervisor round 12), 4613-4691 (ds27p)
