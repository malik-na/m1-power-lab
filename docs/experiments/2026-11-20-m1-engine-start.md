# Does the always-on engine start after Linux's commit? (milestone 1, run 1)

```
Question      Just before Linux's first write of 0x23d2c4000 (the commit), is watchdog 2 armed,
              as it is under macOS (bite 0x7270e00, control 4)?
Known         macOS: watchdog 2 armed by the always-on engine 1.3-7.5 us after R22's
              0x23b718004 = 0, before the first 0x23d2c4000 write, five captures [spec R62].
              Linux: never read (open question 56; cards sleep-entry.md, watchdogs.md).
              No Linux run since ds16 ended in the engine's 5-7 s reset [watchdogs.md].
Prior art     The probe is in the kernel already: ds29 (52669b5bb) probe.rs k 12-15 = watchdog 2
              count, bite, control and 0x23d2b8028 just before that write; record 'q'.
              Aurora sleep.c 3390-3403: "the engine's first step polls for DCS at this state".
Outcomes      A  'q', k=14 captured, value 4 (bit 2)  -> the engine started; it then neither
                 bit at 5 s nor woke: it got past its first steps (look at masks next).
              B  'q', k=14 captured, value 0           -> the engine never started: the SoC never
                 powers down; leads 2-3 (DCS state 4, AMCC) and R22's preconditions first.
              C  no 'q', or k not captured (bit 15 clear) -> inconclusive; read the record reason.
              D  reset 5-7 s after the commit           -> engine started and stalled (as failed
                 macOS runs); the time alone tells.
Tell apart    Record bytes 0x9f04-0d: [1]='q', [2..3]=0x800e, [4..7] the control. D by the reset
              time (about 20 s up vs 165 s).
Not covered   Whether the engine then powered the SoC down; what it waits on.
Safety        Kernel ds29 as run before (wdt=150 armed at begin and at the commit), boot-once,
              apple_wdt unbound by m1-cand-runs; probe code reads only and writes the record
              into 0x9f04-0d. No loader change.
Budget        0 builds, 1 run, 0 agents.
Result        A. Run 2026-11-20 02:18 (kernel ds29, cand 0xffffe, probe_k=14): record
              44 71 0e 80 04 00 00 00 4c 00 = 'q', k=14 captured, watchdog 2 control = 4 (armed),
              76 values captured. Reset (stock kernel up) 181 s after the sleep's start (poll
              granularity 3 s; earlier runs 165 s by the boot time). 0x0201 = 04 after; its value
              before the run was not read, so it tells nothing here. Camera: desktop.
              Raw: var/milestone1/runs.tsv, var/milestone1/run1-m1q14.log,
              var/m1-look/20261120-022151-state-now.jpg.
              So the always-on engine starts under Linux and does not end in its 5 s watchdog 2
              reset (no reset near 5-7 s): it gets past the step that disarms watchdog 2.
```
