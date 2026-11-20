# Which wake source is pending and unmasked at Linux's commit, and does masking it let sequence 0 start? (milestone 4, run 3)

```
Question      Run 1's k 173 bit 13: a wake status bit is pending and unmasked at core 0's last
              write. Which of the 16 sources macOS leaves unmasked is it, and with it masked
              before the cores' final writes (m4fix bit 5), does sequence 0 start?
Known         Run 1 (m4fix 31, m1fix 11: masks at macOS's values, ATC0 left on): bit 13 set.
              Run 2 (k 180): word 1 (sources 32-63, alarm line 54 included) has none.
              Milestone 1 run 3 (m1fix 3, ATC0 off): no pending bit at the 0x23d2c4000 point.
              Spec C14 (line 3236): "No wake source both unmasked and pending (a bounce at once,
              not a stall)"; Linux at its commit: not read until now. macOS's status at its commit:
              not read (0 / 0x400000 / 0 at every wake). Remaining unmasked sources: AOP 12, 14,
              26, 27, 64; SMC 76, 81; ATC0/ATC1 CIO and USB 131-134 (the Thunderbolt cable is on
              ATC0) [ap-wake-sources-j313.txt].
Prior art     Aurora sleep.c 2276-2381 (masks, refuses with a pending source); spec C14.
Outcomes      A  0x0201 04 -> 01 or a 5-7 s reset -> the pending source held the engine; masking
                 it lets sequence 0 start: tell Naeem; run 4 confirms with bit 5 alone.
              B  04 -> 04, ~165 s, k 185 names a source -> that source is pending at Linux's
                 commit, and masking it does not start sequence 0 (with the batch).
              C  k 185 = 0 (bits 0-23) -> nothing pending at the commit-point step's start; the
                 run-1 bit came later (between that step and core 0's last write).
              D  no record -> inconclusive.
Tell apart    k 185 bits 0-15 (bit i = the i-th source in the file's order), 0x0201, reset time.
Not covered   Whether macOS has the same source pending at its commit (no reading of macOS).
Safety        Build 2 (probe/m4-batch 0ac81077f): reads plus bit 5's mask-bit sets; the wdt
              re-arm stays the last write; second-agent check of the delta; otherwise as
              2026-11-20-m4-deep-wfi.md.
Budget        Build 2 of 2; run 3 (and 4 if A).
Result        C, then B. Run 3 (build 2 0ac81077f, m4-k185.cmdline, m4fix 63 with the masking): k 185
              = 0x80000000: none of the 16 sources nor any other bit pending and unmasked at the
              commit-point step's start; 0x0201 04 -> 04, 165 s. Run 4 (m4-k186.cmdline, m4fix 31,
              run 1's switches): k 186 = 0x80000000 at core 0's last write: nothing pending;
              04 -> 04, 165 s. Run 1's bit 13 did not repeat; in runs 3 and 4 no source was both
              unmasked and pending (spec C14 met at Linux's commit), and sequence 0 still did not
              start. Not the gate. Which source run 1 saw: unknown.
```
