# Card: candidates C1-C18

Each candidate is an observed difference between macOS's state before its commit and Linux's, behind its own switch.
None, alone or all together, has let Linux's SoC power down and wake. 2026-11-20.

## Decided: the switch
- `apple_deepsleep.cand` bit n is Cn (C1 = `0x2` ... C17 = `0x20000`, C18 = `0x40000`); default off [D5; evidence "ds21", "The two runs"].
- Bit 19 (`0x80000`) is not a candidate: D13's `pmp` sampling at boot [D13].
- Bits 20, 21 (D14) withdrawn; bit 22 is D15's delayed client start [D14; D15].
- `0x3fffe` = C1-C17; `0xffffe` = C1-C18 plus bit 19; `0xc0000` = C18 plus bit 19 [evidence "ds21"; "ds28"].
- No candidate is a requirement; none is claimed to be needed for the power-down [8.2 "What these are"].

## Established: the table
"Alone (ds20)": one switch on, kernel ds20 `7cec0b40b`, `wdt=30`. "commit" = commit point reached, watchdog reset after.

| # | What (switch) | Alone (ds20) | macOS with Linux's state | Status |
|---|---|---|---|---|
| C1 | SEP domain to state 0 before R16 (`0x2`) | commit | not carried | [8.2 C1] |
| C2 | four power-manager sub-blocks on at entry start (`0x4`) | not run | down | [8.2 C2] |
| C3 | the three C3 words read at three places, no write (`0x8`) | DARK, record 'a' | no commit (2/2) | revised round 13: the write withdrawn [8.2 C3] |
| C4 | DCSn+`0x7b0` = 0 (`0x10`) | commit | write not taken | [8.2 C4] |
| C5 | twelve request-4 domains to 0, gated on PMS and SIO family (`0x20`) | DARK, 'T' on SIO_BUSIF | down | revised rounds 13, 14, 14b [8.2 C5] |
| C6 | `0x23b71c000` (and `040`) set at entry start (`0x40`) | not run | down | [8.2 C6] |
| C7 | `0x23d24003c`, `0x23d240048` bit 31 (`0x80`) | not run | down | [8.2 C7] |
| C8 | `pmp` stopped whatever PMS_SRAM reads (`0x100`) | commit | not carried | [8.2 C8] |
| C9 | ATC1 domains and MSG off (`0x200`) | commit | not run | [8.2 C9] |
| C10 | APCIE_GP to 0 after R14 (`0x400`) | commit | not carried | [8.2 C10] |
| C11 | FPWM1, GFX without bit 11 (`0x800`) | not run | not carried | [8.2 C11] |
| C12 | SIO family on at entry start, R23 clears bit 28 (`0x1000`) | not run | not carried | [8.2 C12] |
| C13 | timers disabled at each final write (`0x2000`) | commit | not carried | [8.2 C13] |
| C14 | audio clocks as macOS leaves them (`0x4000`) | not run | not run | [8.2 C14] |
| C15 | `0x23b718000`/`004` at `0xf` before R22 (`0x8000`) | commit | not carried | [8.2 C15] |
| C16 | GPIO domain on (`0x10000`) | not run | not run | [8.2 C16] |
| C17 | 28 SoC clock words' bits 24-27 = 7 (`0x20000`) | commit | no commit (2/2) | [8.2 C17] |
| C18 | `pmp` started at boot, messaged and stopped as macOS (`0x40000`) | not run | 0x55 word dropped: down | kernel side's, D9-D11, D17 [8.2 C18] |

[outcome columns: 8.2 "What the runs have shown so far"; evidence "Runs ds20, candidate switches one at a time"; macOS column is [HV-CHANGED], 1.7g]

## Established: together
- ds20 `0x3ffd6` (all but C3, C5): commit, 'W', reset 63 s [evidence "Run ds20, all candidate switches but C3 and C5 together"].
- ds21 `0x3fffe` (C1-C17): commit, C3 record `64 43 36 64 f3`: Linux's values `0x444/0x666/0x333` at all three places, reset 63 s [evidence "ds21"].
- ds21 `0x1020` (C5 with C12): commit, 'W', reset 62 s; C5's own four reads not recorded [evidence "ds21"].
- ds28 `0xffffe` (C1-C18): commit, C3 record `43 32 24 43 f2`: macOS's `0x333/0x444/0x222` at all three places, reset at the `wdt` time [evidence "ds28"].
- ds28 row B (`B_without_pmp`, mask not recorded): ds21's record byte for byte [evidence "ds28"].
- ds29 and the breadcrumb run (`0xffffe`): the same C3 record, no wake reached any CPU code [evidence "ds29"; "The boot loader's wake breadcrumb"].
- ds20 C3 alone and C5 alone hung before the commit; with others (ds21) both reached it. Kernels differ in logic and glue, so which change fixed it is not read [evidence "ds21", "Against ds20"].

## Decided
- C3 now makes no write: reads at entry start, after R22's trigger, after R38's third write [8.2 C3; R70; D8 (a)].
- C18 is the `pmp` client's, not the logic's; the client must map macOS's 113 entries and fill the opening region before the opening [D9; D17].

## Open
- Which candidates acted in `0x3fffe` / `0xffffe` beyond C3's reads: no record carries them; a per-candidate log or record [evidence "ds21", "What these runs do not show"].
- C5's four gate reads in a real run: a record that carries them [open question 74].
- Whether `pmp` was running or stopped at ds28's commit: the client's entry-part log from that sleep [evidence "ds28", "What ds28 does not show"].

## Read more
- `docs/spec/macos-13.5-sleep-wake-observed.md` lines 6451-7195 (8.2; summary table 7147, outcome table 7170)
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` lines 2053-2095 (ds20)
- same file, lines 3379-3535 (ds21)
- same file, lines 4692-4796 (ds28)
- `var/commit-walk/ds20-cand.tsv`, `ds21-cand.tsv`, `ds28-all.tsv` (private run rows)
