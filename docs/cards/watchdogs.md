# Card: watchdogs 0, 1 and 2

Watchdog 1 is the one the glue arms so every sleep run ends without hands; watchdog 2 is armed by the always-on side for 5 s.
A reset at begin + `wdt` + about 15 s means no wake reached any CPU code. 2026-11-20.

## Established: the blocks (all at 24 MHz)

| Watchdog | Count / bite / control | What it does | Source |
|---|---|---|---|
| 0 | count `0x23d2b0000`, control `0x23d2b000c` | counts with control 0; macOS zeroes count and control in the entry | [R15; 1.7c; spec section 5 "Watchdogs before the sleep"] |
| 1 | `0x23d2b0010` / `0x23d2b0014` / `0x23d2b001c` | resets the M1 when count reaches bite with control 4; Linux's `apple_wdt` (`23d2b0000.watchdog`, `/dev/watchdog0`) drives it | [R61; evidence "ds21", "Watchdog reads"] |
| 2 | `0x23d2b0020` / `0x23d2b0024` / `0x23d2b002c` | armed 5 s (`0x7270e00`), control 4, by the always-on side at its first step | [R62; 4.1c] |

- Watchdog 1 at macOS's commit: bite 60 s, control 0 (not armed by macOS) [4.1c, table].
- Watchdog 2 awake: bite `0x80befc00`, control 0; at macOS's commit 5 s, control 4; at the wake 5 s, control 0, count 0.326 s [4.1c; R62].
- Watchdog 2's count starts 1.3-7.5 us after macOS's `W 0x23b718004` = 0 (R22), five captures; macOS writes nothing to it [R62].
- Neither count is carried through a sleep (13.9 ms at the wake after 89.5 s asleep); watchdog 1's bite and control survive [R61; spec section 5].
- Watchdog 1 armed at macOS's commit (150 s) did not stop the power-down or the alarm wake (J, K) [R61].
- The always-on program (decode): sleep sequence 0 and wake sequence 10 each arm watchdog 2 for 5 s [4.4; 8.2 C3].
- Failed macOS runs under the hypervisor ended in a reset 5-7 s after the commit; an earlier Linux driver did the same (L18) [8.2 "Where the Linux outcome points"; 4.4].
- No Linux run since ds16 has ended in that 5-7 s reset [8.2 "Where the Linux outcome points"].
- ds20 C3 and C5 runs, watchdog 1 armed only at the commit, hung before it: dark until the power button [L25].
- Stock Omarchy: systemd holds `/dev/watchdog0` with a 30 s runtime timeout (`90-maclab-watchdog.conf`); the test command line `systemd.watchdog_sec=0` leaves it unheld [L31; L32; evidence "ds21", "Watchdog reads"].
- ds28's first run, `apple_wdt` driving watchdog 1: the sleep was refused (-EBUSY), no device access; unbound, it slept [evidence "ds28", "The refused sleep"].
- The M1's loader mb2 re-arms watchdog 1 on its reset path when control bit 2 is set: 45 s, then 75 s before the kernel's entry [evidence "The boot loader's wake breadcrumb", provenance].

## Decided: the glue (D7 as of round 15d)
- `wdt` = N: the check first in `begin` (no device access): Linux's watchdog core must not drive watchdog 1 (`WDOG_ACTIVE`, `WDOG_HW_RUNNING`); else -EBUSY, nothing armed [D7 (e)].
- No driver bound = "not driving", sleep goes on; a bound driver the glue cannot read = refusal [D7 (e) GL12].
- So `apple_wdt` must be unbound (or inactive) before a `wdt` sleep: its resume would restart the count with the glue's bite, and the glue's disarm would stop systemd's watchdog [D7 (e) reasons (1), (2)].
- Arm = R61's four writes: control 0, count 0, bite N x 24,000,000, control 4 [R61; D7 (a)].
- Armed first in `begin`, before 'Da', any core offline, any read or `enter` [D7 (a), GL11].
- Re-armed in the commit-point step, last before the first core's final write [D7 (b); D8 (b)].
- The logic's R15 write of `0x23d2b0010` = 0 restarts the count; it does not disarm [D7 (d)].
- Disarm = count 0, bite B (Linux's driver's own), control 0; the glue's last device write on every way back [D7 (c), review point (b)].
- Exception: a parked core whose release is not answered: record, then panic, left armed [D7 (c)].
- N above 178 s cannot be armed (32-bit bite at 24 MHz): the sleep is refused [D7 (d), review point (a)].
- N at least twice each stretch S1-S6; N = 30 until they are measured [D7 (d)].
- The lab's runner refuses a sleep with `wdt` off (`ALLOW_NO_WDT=1` only on Naeem's ask) [AGENTS.md; `tools/tb/guest/ds-real.sh`].

## Established: what a reset at N seconds means (wdt = N, alarm A)
- Watchdog 1 reset to the stock kernel's start is about 15 s [evidence "ds28", "Times against what each outcome predicts"].
- Start + N + 15 s, the C3 or 'W' record standing: no wake reached a CPU (ds28: 135 s at N = 120; ds29: 165 s at N = 150) [evidence "ds28"; "ds29"].
- ds29 `wakemark=3` would give A + 60 + 15 s (stub) or A + 90 + 15 s ('Dr') if a wake reached the kernel [evidence "ds29"].
- Breadcrumb loader: a wake reaching the reset vector gives A + 30 to A + 75 s plus boot [evidence "The boot loader's wake breadcrumb"].
- A reset 5-7 s after the commit points at watchdog 2: the always-on program started and stalled [8.2 "Where the Linux outcome points"].
- Fault shadow bit 11 `wdog,reset_in_1` follows both a watchdog reset and macOS's alarm wake [spec 1.7d].

## Open
- Whether the always-on program arms watchdog 2 after Linux's `0x23b718004` = 0: read watchdog 2 and `0x23d2b8028` there [open question 56].
- `WDOG_HW_RUNNING` at boot on the test kernel [open question 81].
- The stretches S1-S6 on the test kernel: the glue's `CNTVCT_EL0` log after the disarm [open question 82; D7 (d)].

## Read more
- `docs/spec/macos-13.5-sleep-wake-observed.md` lines 5149-5454 (D7)
- same file, lines 2677-2788 (4.1c: watchdogs at the commit)
- same file, lines 4571-4610 (R61, R62)
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` lines 3485-3535 (watchdog reads, ds21)
- same file, lines 4692-4850 (ds28, ds29 timings)
