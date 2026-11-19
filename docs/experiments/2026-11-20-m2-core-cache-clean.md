# Does the P cluster finish powering down, and sequence 0 start, when each core cleans its L1 first? (milestone 2)

```
Question      If every core cleans and invalidates its L1 data cache by set/way with its cache off
              (SCTLR.C = 0) just before its WFI, after the logic's final ACC_OVRD/CYC_OVRD writes,
              does 0x23b718004 read state 0 at core 0's last write, and does sequence 0 start?
Known         Reading: at core 0's last write (cores 1-7 down) 0x23b718004 = 0x10 [run 4 of this
              milestone, k 157; var/milestone2/run4-after.txt]. Bits 4-7 are a state: at macOS's
              wake the word is written 0xf and reads 0x1f 154-246 times, then 0x2f [spec 3457-3462];
              after macOS's power-down it reads 0 before the wake writes it [spec 3749]. So state 1
              at Linux's commit = the P cluster has not reached off (inference from those readings;
              macOS's own value at its commit was never read).
              Code reading (allowed tree): the clean-room cores do `dsb; isb; wfi` with MMU and
              caches on and no cache clean [~/Work/dsk-probe-m1-leads drivers/soc/apple/deepsleep/
              glue.c 409-490; logic/cores.rs 99-111].
              Old driver (second-hand, NOT a hardware reading): the old team's private plan says its
              secondaries ran the old kernel's assembly, which "cleans its L1 cache with translation
              off" [var/catchup/PLAN.md 149-153]; the old status board records an image check of
              run 18's kernel: "1024 dc cisw then ACC/CYC/wfi" [var/catchup/hv-STATUS.md 103]. Both
              files are in the lab repo; both describe the old code (smp_apple_asm.S), they are not
              readings of the M1. The off-limits trees were not opened.
              macOS: cache maintenance is not trapped by the hypervisor, so macOS's is unobserved
              [spec 598-601].
Prior art     The old plan/status lines above; Arm set/way clean (CCSIDR 0x700fe03a: 8 ways x 128
              sets, var/catchup/hv-STATUS.md 103).
Outcomes      A  0x0201 04 -> 01, or a reset 5-7 s after the commit -> sequence 0 started: the cache
                 state held the cluster up; build lane next.
              B  k 157 = 0x00, 0x0201 04 -> 04, 165 s -> the P cluster now goes off and the engine
                 still does not start: cache is not it; the next gate is elsewhere.
              C  k 157 = 0x10 again, 04 -> 04, 165 s -> the clean does not change the cluster state:
                 the cluster is held up by something else (ATC0 card next).
              D  wakes or powers down by itself -> stop, tell Naeem at once.
Tell apart    k 157 (0x00 vs 0x10); 0x0201; the reset time.
Not covered   L2 (core 0 cleans L1 only, as the old routine); E cluster word 0x23b718000 (k 156).
Safety        Probe kernel with a switch (m1fix bit 4), off by default, safety-checked; wdt=150;
              boot-once; a core whose WFI returns turns its cache back on.
Budget        1 build (shared with the ATC0 card), 1 run, 2 agents.
Result        C. Run 5, 2026-11-20 04:14:59 (probe/m2-cache e1442a487, m1fix=16, m1aop=0,
              probe_k=157, cand 0xffffe): record 44 71 9d 80 10 00 00 00 8d 00 = k 157 =
              0x23b718004 = 0x10 again; stock kernel 04:17:44 = 165 s after the start; 0x0201
              04 -> 04. An L1 clean with the cache off before every core's WFI does not start
              sequence 0. Caveat on k 157: it is read by core 0 right after cores 1-7's final-write
              jobs return, so it may catch the P cluster still on its way down; whether the cluster
              ever reaches 0 under Linux is not read. Raw: var/milestone2/run5-start.txt, run5-after.txt.
```
