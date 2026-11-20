# What is AON_AP_DEADLINE (0x23d2b8008) at Linux's commit, and does writing it 0 let sequence 0 start? (milestone 4, item 4)

```
Question      Aurora writes aon-misc+0x08 = 0 from the AP with watchdog 2 (sleep.c 3335-3340,
              1f38ff8f4). What does 0x23d2b8008 read just before R22 and at core 0's last write,
              and with it written 0 there, does sequence 0 start?
Known         On t8103 the always-on side arms watchdog 2 itself (R62); at Linux's commit watchdog 2
              reads 5 s, control 4, as macOS's [watchdogs.md; 2026-11-20-m1-engine-start.md]. The
              deadline word: never read on the M1, nor macOS's value at its commit (not recorded).
              The probe does not write watchdog 2 or 0 (an AP-armed watchdog 2 would make a 5 s
              reset ambiguous).
Prior art     Aurora sleep.c 148, 3335-3340, 3460-3475.
Outcomes      A  0x0201 04 -> 01 or a 5-7 s reset -> batch positive: halve.
              B  04 -> 04, ~165 s, k 174 = 0 -> the word was 0 already: condition met, ruled out.
              C  04 -> 04, ~165 s, k 174 != 0, k 175 = 0 -> zeroing it does not start sequence 0.
              D  k 175 != 0 after the write -> something rewrote it; inconclusive for this item.
Tell apart    k 174 / k 175 / k 173 bit 12, 0x0201, the reset time.
Not covered   macOS's value at its commit (no reading of macOS has it).
Safety        Probe kernel probe/m4-batch (boot once, m1-bootonce), safety-checked by a second
              agent before run 1; claim taken; watchdog 1 held at 120 s through /dev/watchdog0 from
              before any trigger (m3run.sh idle mode), apple_wdt unbound by start.sh, wdt=150
              armed in begin and at the commit point; the M1 comes back on stock by the watchdog.
              Nothing needs Naeem.
Budget        Shares milestone 4's build (2 at most) and run 1 (4 runs at most); 1 agent writes the
              probe, 1 checks it.
Result        Partly read. Runs 1-4 had bit 3 on: k 173 bit 12 = 0 (0x23d2b8008 reads 0 at core 0's
              last write, after the write of 0); 0x0201 04 -> 04, 165 s. k 174 (its value before the
              write) was not recorded: the 4 runs went to the wake-source readings. So: 0 at the
              commit does not start sequence 0; whether Linux had it nonzero before: not read.
```
