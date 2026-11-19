# Does the always-on program start sequence 0 once the AOP is told "AP power 0x201"? (milestone 2)

```
Question      With Linux's entry as in ds29 (cand 0xffffe) plus macOS's R4 message to the AOP
              ("AP power 0x201" on the management endpoint, echoed), and optionally the AOP's
              sensor stops and ordered queue stops first, does sequence 0 start after the commit?
Known         macOS sends the AOP "AP power 0x201" in every entry, after its sensor intervals 0 and
              queue stops, between the SMC's slpw and slpa [spec R4 line 4032;
              docs/evidence/2026-11-16-hv-linux-entry/README.md, side by side].
              The clean-room kernels never send it: the AOP hook (drivers/soc/apple/aop.rs
              s2r_hook, line 2436) is built only with CONFIG_APPLE_S2R_RS, which the clean-room
              config does not set (~/.cache/m1-s2r-kb/io-clean/config: APPLE_AOP=m,
              APPLE_DEEPSLEEP=y, no APPLE_S2R_RS). Linux itself boots the AOP (ds28 dmesg 1063-1128,
              "AOP IS READY"); it is running at the entry.
              The old driver (s2r_rs, run 39, CONFIG_APPLE_S2R_RS) sent it, and its runs read
              0x0201 = 01 after the restart (sequence 1 ran) [evidence 2026-11-16-run39-aop-sensors].
              No clean-room run has read 01 or reset at 5 s [docs/cards/state.md].
              The SMC handshake (slpw, WKTP 2, slpa, AP 0x201) is sent by macsmc.c 625-662 in every
              mem suspend when macsmc is bound (it is, ds28 dmesg 984); whether it succeeded in a
              clean-room run is not read.
              The sequences are named for AOP states (AWAKE->AOP_DDR ...); sequence 0 hands off to
              the AOP at 0x23d2c001c (write 0x50, poll &0xaa0 == 0xa0)
              [var/recfg/t8103-recfg-brief.txt 27-28].
Prior art     Old driver's AOP steps (evidence run 39, lx4); aop.rs s2r_hook (the code that sent it);
              macOS 135r5/135r6 AOP traces (evidence 2026-11-16-hv-macos135-wake).
Outcomes      A  0x0201 = 01 after the run (pre 04)       -> sequence 1 ran: the AOP message was the
                 missing piece; build lane next. A reset at 5-7 s after the commit with 01 or 04
                 (sequence 0 started and stalled) means the same for sequence 0's start.
              B  0x0201 04 -> 04, reset at the watchdog-1 time (about 165 s), AOP status "echoed"
                 -> the AOP message alone is not enough (run m1aop=3 next, then lead 1's diff).
              C  AOP status not "echoed" (no hook, error)  -> inconclusive: the message never went.
              D  the M1 wakes or powers down by itself     -> stop, tell Naeem at once.
Tell apart    0x0201 before and after; the reset time from the start; k 144 bits 24-27 (AOP status),
              bits 28-30 (SMC handshake).
Not covered   Which part of the AOP's state the program reads; whether the wake then works.
Safety        Kernel probe/m2-aop (safety-checked), wdt=150 armed in begin and at the commit,
              boot-once, apple_wdt unbound by start.sh. The AOP messages are the ones macOS and the
              old driver send; every way back sends AP power 0x20 (and the queue starts). No loader
              change, nothing needs Naeem.
Budget        1 build, 1-2 runs (m1aop=1, then m1aop=3 if B), 2 agents (probe, safety).
Result        B (m1aop=1). Run 3, 2026-11-20 03:46:20 (probe/m2-aop a9680e86b, m1fix=0,
              probe_k=144, cand 0xffffe): record 44 71 90 80 00 8c 02 f1 8d 00 = 'q', k=144 =
              0xf1028c00: AOP status 1 (AP power 0x201 echoed), SMC slpw, slpa and AP 0x201 all ok
              (bits 28-30), all 24 words captured. Stock kernel started 03:49:05 = 165 s after the
              start; 0x0201 04 -> 04; shadow 0x000800. The AOP message with the SMC handshake is
              not enough for sequence 0. Raw: var/milestone2/run3-start.txt, run3-after.txt.
              B (m1aop=3). Run 4, 03:51:18, sensors off + 8 ordered queue stops + AP power 0x201,
              probe_k=157: record 44 71 9d 80 10 00 00 00 8d 00; stock kernel 03:54:03 = 165 s;
              0x0201 04 -> 04. The old driver's whole AOP sequence is not enough either.
              Side reading: k 157 = 0x23b718004 = 0x00000010 at core 0's last write.
              Raw: var/milestone2/run4-start.txt, run4-after.txt, runs.tsv.
```
