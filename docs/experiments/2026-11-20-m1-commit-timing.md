# How long from Linux's first 0x23d2c4000 write to the cores' last writes? (milestone 1, runs 4-5)

```
Question      Ticks (24 MHz) from the logic's first write of 0x23d2c4000 to core 0's last
              power-down write (run 4, k=118) and to the last of cores 1-7's (run 5, k=119).
Known         macOS: first 0x23d2c4000 write at T-0.0154 s, T = the last core's sleep-path
              record [spec R62 / R24]. Aurora sleep.c 3443-3445: "under 33 ms from the complex
              words to the WFI (the engine's bound for the cores to go idle)". Linux: never
              measured. Runs 1-3 today: sequence 0 never starts after Linux's commit.
Prior art     Aurora sleep.c 3443-3445 (T8140/T8132 bound, measured there, not on t8103).
Outcomes      A  k=118 or 119 above 33 ms (792,000 ticks) -> Linux misses the bound Aurora names;
                 the next probe shortens the stretch (what fills it: the commit-point step's SPMI
                 record, the watchdog re-arm, the per-core run_on hand-offs).
              B  both under about 16 ms (macOS's)          -> timing is not the difference.
              C  between 16 and 33 ms                       -> not ruled out on t8103 (its bound is
                 unmeasured); a shorter stretch would test it.
              D  not captured                               -> inconclusive.
Tell apart    The record's 32-bit value, ticks / 24,000 = ms.
Not covered   t8103's own bound; when the engine samples the cores.
Safety        Kernel probe/m1-leads a18064d55 (safety-checked), wdt=150, boot-once, m1fix=3.
Budget        0 builds, 2 runs.
Result        B. Run 4, 2026-11-20 02:41:55 (probe/m1-leads a18064d55, m1fix=3, probe_k=118,
              started by hand on the test boot): record 44 71 76 80 8e 9a 00 00 80 00 = 'q', k=118,
              39,566 ticks = 1.65 ms from the first 0x23d2c4000 write to core 0's last power-down
              write (macOS about 15.4 ms to its last core; Aurora's bound 33 ms). Core 0 writes
              after cores 1-7's jobs have returned (kernel_hw.rs 1544), so run 5 (k=119) was not
              spent. 0x0201 04 before, 04 after; kernel back 169 s after the start. Raw:
              var/milestone1/run4-start.txt, run4-after.txt. Timing is not too slow; whether too
              fast matters is not shown.
```
