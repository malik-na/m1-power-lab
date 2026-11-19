# How long does the always-on engine wait for the cores before watchdog 2 bites? (milestone 2, lead 3)

```
Question      With core 0 held 20 ms (run a) and 50 ms (run b) after cores 1-7 go down, does
              watchdog 2 reset the SoC about 5 s after the commit, or does the run end at
              watchdog 1 (about 165 s)?
Known         Core 0 down 1.65 ms after the first 0x23d2c4000 write: no watchdog-2 reset, the run
              ends at watchdog 1 [2026-11-20-m1-commit-timing.md]. Core 0 held 3 s: reset about 5 s
              after the commit, nothing moved in 3 s [2026-11-20-m1-engine-sampler.md]. macOS's
              cores go down 15.4 ms after its first write, all eight within 31 us [spec E6 step 5].
Prior art     Milestone 1's sampler (probe/m1-leads 6fe52a780, m1fix bit 2, m1samp_ms).
Outcomes      A  20 ms: about 165 s; 50 ms: about 165 s -> the window is over 50 ms; Linux's core
                 timing is not why sequence 0 does not start (with 1.65 ms well inside it).
              B  20 ms: about 165 s; 50 ms: about 5 s  -> the window lies between 20 and 50 ms.
              C  20 ms: about 5 s                       -> the window is under about 21.6 ms from the
                 first write; macOS's 15.4 ms is inside it, so timing is still not the difference;
                 run b not needed.
              D  any change of 0x23d2b8028 in the samples (k 140 bit 4) -> the engine moved with a
                 core up; read the bit's sequence.
Tell apart    The reset time from the start (about 20 s vs about 165 s); k 140 (packed sampler).
Not covered   What the engine does once the window is met.
Safety        Kernel m1samp (6fe52a780, safety-checked in milestone 1), reads only, wdt=150,
              boot-once.
Budget        0 builds, 1-2 runs.
Result        A. Run 1, 2026-11-20 03:34:43 (m1samp 6fe52a780, m1fix=7, m1samp_ms=20, probe_k=140,
              cand 0xffffe): record 44 71 8c 80 0c 20 f1 ff 90 00 = 'q', k=140 = 0xfff1200c (sequence
              12, progress 0x20, watchdog 2 control bit 2 set, nothing changed while sampled);
              stock kernel started 03:37:29 = 166 s after the start; 0x0201 04 -> 04; shadow 0x000800.
              Run 2, 03:39:01, m1samp_ms=50: the same record, stock kernel 03:41:46 = 165 s, 0x0201
              04 -> 04. Neither bit at 5 s: the engine accepts core 0 going down 50 ms late; 3 s late
              it does not (milestone-1 run 5). The window lies between 50 ms and 3 s; Linux's
              1.65 ms is well inside it. Timing is out.
              Raw: var/milestone2/run1-start.txt, run1-after.txt, run2-start.txt, run2-after.txt.
```
