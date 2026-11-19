# Do Aurora's wake masks and AMCC enables let sequence 0 start? (milestone 1, runs 3-4)

```
Question      With the AP wake masks at macOS's values and the AMCC error enables cleared just
              before the commit (Aurora sleep.c 2276-2291, 3560-3571), does the always-on program
              start its power-down (sequence 0 -> 1) after Linux's commit?
Known         Linux leaves the masks 0 / 0x40 / 0 / 0 / 0 (153 of 154 sources enabled; run25,
              hwdb snapshot 2); macOS f3ffafff ffb97eff fffdeffe ffffffff 03ffff87 [R63].
              AMCC word0 bit 25 / word1 bit 8 at P+0x21000/0x21008 (inferred), zeroed by R17 in
              the entry; not read at the commit [cards/aurora-sleep-driver.md 1-2].
              Runs 1-2 today: sequence 0 never starts after Linux's commit (no 5 s watchdog 2
              reset, 0x0201 never 01) [2026-11-20-m1-sequence1.md].
Prior art     Aurora sleep.c (1f38ff8f4): masks every source but apple,wake-enable; clears the two
              AMCC enables before every commit ("turns the sleep around within 20 ms").
              2026-11-07/08 driver wrote macOS's masks among other changes, no wake [state.md].
Outcomes      Run 3: m1fix=3 (both), probe summary k.
              A  0x0201 01, 02 or 00 after, or a reset near 5-7 s, or WOKE -> the program started:
                 one of the two is the missing trigger; run 4 splits them (m1fix=1 alone).
              B  0x0201 unchanged, reset at the watchdog-1 time   -> neither is sufficient; the
                 summary still gives the commit readings: masks taken (bit 1), gate records
                 bit 30 (bits 2-3), AMCC enables (bits 4-5), wake status pending (bit 6).
              C  no probe record, or the summary not captured     -> inconclusive.
Tell apart    0x0201 before/after (runner), the reset time (5-7 s vs about 165 s), the record.
Not covered   Which of the two acts, if A (run 4). PMC voters: no t8103 word named.
Safety        Kernel probe/m1-leads (52669b5bb + reads + m1fix), wdt=150 at begin and the commit,
              boot-once. New writes: the five mask words and AMCC P+0x21000/0x21008 bits only.
              Second-agent safety check before the run.
Budget        1 build, 1-2 runs, 2 agents (build, safety).
Result        B. Run 3, 2026-11-20 02:37:11 (kernel 7.2.11-m1leads = probe/m1-leads a18064d55,
              cand 0xffffe, m1fix=3, probe_k=114; started by hand on the test boot because the
              runner's start step timed out): record 44 71 72 80 8a 10 00 80 80 00 = 'q', k=114,
              summary 0x8000108a, 128 values captured:
                bit 0 = 0  masks before enter not macOS's (Linux's 0/0x40/0/0/0, as known)
                bits 1, 7  masks at the 0x23d2c4000 point = macOS's; the fix's write read back
                bits 8-15  16 sources unmasked (macOS's 16)
                bit 2 = 0, bit 3 = 1  0x23b71c090 bit 30 clear, 0x23b71c360 bit 30 set: macOS's
                           state at its commit [power-domains.md 46]
                bits 4, 5 = 0  AMCC word0 bit 25 / word1 bit 8 clear, read before m1fix's clear:
                           already off at Linux's commit (R17)
                bit 6 = 0, bits 16-23 = 0  no wake-status bit pending
              0x0201: 04 before (test kernel, spmi_nvmem3), 04 after. Kernel back 166 s after the
              start (boot 02:39:57). Fault shadow 0x000800.
              So the masks at macOS's values and the AMCC enables off do not start sequence 0.
              Run 4 not needed (no A). Raw: var/milestone1/run3-start.txt, run3-after.txt.
```
