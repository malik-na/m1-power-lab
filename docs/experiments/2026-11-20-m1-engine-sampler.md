# What does the always-on engine do in the 3 s after Linux's commit? (milestone 1, runs 5-6)

```
Question      With cores 1-7 down and core 0 sampling for 3 s before its own last write: do
              0x23d2b8028 (sequence enter/exit bits), 0x23d2b8040 (progress code) and watchdog 2
              (control, count) change, and when?
Known         At Linux's commit: 0x23d2b8028 = 0x01000000 (sequence 12 entered), watchdog 2
              control 4, bite 5 s (runs 1-2). Sequence 0 never starts after the commit (0x0201
              never 01, no 5 s reset; runs 1-4). macOS with a core kept up (det13/det14):
              0x23d2b8028 >> 24 stayed 0x01, progress low byte 0x20, watchdog 2 counted and the
              SoC reset about 5 s after [evidence 2026-11-17 Hypervisor round 6, section 2].
              Only sequence 1 disarms watchdog 2 in the decoded program [var/recfg brief 0x082a0].
Prior art     det13/det14 sampler under macOS (same words); recfg decode var/recfg.
Outcomes      A  all four unchanged for 3 s (watchdog 2 control 4, counting) -> the engine waits,
                 as macOS's did with a core up; the reset time after core 0 then goes down says
                 whether watchdog 2 still bites (about 5 s: it was armed all along and something
                 later in the normal runs stops it) or not (about 165 s).
              B  watchdog 2 control goes to 0 at time t, 0x23d2b8028 unchanged -> something outside
                 the decoded sequences disarms it at t (look at what Linux does at t).
              C  0x23d2b8028 changes (another sequence's bit) -> the engine moves on with core 0 up;
                 the bit names the sequence (0: AWAKE->AOP_DDR; 4-7: the S2R_AOP/AWAKE paths).
              D  no record / not captured -> inconclusive (a reset during sampling: the time tells).
Tell apart    The packed k and the full-word k values (one per run); the reset time (5-10 s vs
              about 165 s); 0x0201 before/after.
Not covered   What the engine waits on, if A.
Safety        Sampling is reads of always-on words only, bounded to 3 s on core 0, before the
              existing probe record; wdt=150 armed; boot-once; second-agent safety check.
Budget        1 build, 1-2 runs, 2 agents.
Result        A, with the short reset. Run 5, 2026-11-20 02:55:02 (kernel 7.2.11-m1samp =
              probe/m1-leads 6fe52a780, m1fix=7, m1samp_ms=3000, probe_k=140, cand 0xffffe):
              record 44 71 8c 80 0c 20 f1 ff 90 00 = 'q', k=140 = 0xfff1200c, 144 captured:
              0x23d2b8028 at sequence 12 and unchanged, 0x23d2b8040 = 0x20 unchanged, watchdog 2
              control 4 at the end and unchanged, no change of any of the three in 3 s.
              Reset: stock kernel started 02:55:22, 20 s after the start (165-169 s in runs 1-4
              with core 0 going down at once); fault shadow 0x000800; 0x0201 04 -> 04; 0xd000 03.
              So with core 0 held 3 s the engine waits in sequence 12 with watchdog 2 counting and
              the SoC resets about 5 s after the commit, as macOS's did with a core up (det13/14).
              With every core down within 1.65 ms (runs 1-4) watchdog 2 never bites: the engine
              takes Linux's cores-idle and goes on to a state that stops watchdog 2 without
              entering sequence 0 (inferred: sequence 0 would arm watchdog 2 for 5 s and only
              sequence 1 disarms it, after 0x0201 = 01; neither a 5 s reset nor 01 is ever read).
              What stops watchdog 2 there is not read.
              Run 6 not spent. Raw: var/milestone1/run5.log, run5-start.txt, run5-after.txt.
```
