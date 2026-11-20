# Does sequence 0 start when the Secure Enclave has gated itself, as on stock and macOS, before the entry? (milestone 3, run 5)

```
Question      With the probe kernel's SEP driver run as stock runs it (xART guard off), so that the
              enclave finishes its bring-up and gates itself (0x23b700c00 bits 4-7 = 0) before the
              sleep starts, does the always-on engine start sequence 0 after Linux's commit?
Known         Runs 2-4 (2026-11-20-m3-sep-sleep-message.md): on the probe kernel the SEP never
              answered and never gated. Its dmesg shows why it went silent: "xART guard: refused to
              rewrite a kind-4 record this Linux install did not create" (14.47 s), then LOAD_CATACOMB,
              REGISTER_SERIAL and the sleep request all time out. The probe tree's apple_sep sets the
              guard to 1 on T8103 (profile.rs 188-222, sep.rs 2775); the stock linux-aurora
              7.3.0-aurora0test5 driver sets it to 0 on M1 ("xART guard off"), its enclave finishes
              (sbio restores, sensor bound) and reads 0x1000230f idle (read 04:58, 05:29:48).
              omacom/linux-aurora#506 records the same: a refused locker in the activation, "the
              enclave then answered nothing more that boot".
              Run 1: SEP fully on at the commit (0x1f0020ff), 0x0201 04 -> 04.
Prior art     omacom/linux-aurora#506 (Naeem's, xart_guard_pins); Aurora proto.rs op_sleep.
Outcomes      A  pre-entry 0x1000230f-like, 0x0201 04 -> 01 or a reset 5-7 s after the commit ->
                 a gated SEP lets sequence 0 start: tell Naeem at once, stop running.
              B  pre-entry gated, k 172 gated at the commit, 0x0201 04 -> 04, back at ~165 s -> the
                 SEP is ruled out: by the stop condition the deep-sleep work stops.
              C  the SEP does not gate within the polls -> no sleep started; inconclusive.
              D  gated before, k 172 state f at the commit (the entry woke it) -> inconclusive;
                 the sender is to be found.
Tell apart    The polls of 0x23b700c00 before the entry (run5-pre.txt); k 172 at the commit; 0x0201;
              the reset time.
Not covered   macOS's other conditions at the commit are as in milestones 1-2; the SEP's wake.
Safety        Same safety-checked probe kernel (probe/m3-sep ecbbcc4aa) and switches as run 1, plus
              apple_sep.xart_guard=0 on the command line: the setting the M1's default kernel runs
              every boot. No new code; the run script only reads (/dev/mem) before the sleep, with
              watchdog 1 held at 120 s through the polls; wdt=150 armed in begin; boot-once; claim.
Budget        No build, 1 run (2 if C or D), no agent.
Result        B. Run 5, 2026-11-20 05:51:47 (probe/m3-sep ecbbcc4aa, m3s-k172-g0.cmdline, cand 0xffffe):
              "xART guard off", no refusal, sensor bound; 0x23b700c00 = 0x1000230f (macOS's value)
              at 05:51:39 and 05:51:46, 0x23b74c200 = 4; record 44 71 ac 80 0f 23 10 04 90 00 = k 172
              = 0x0410230f: at core 0's last write 0x23b700c00 = 0x1000230f and 0x23b74c200 low byte
              4; stock up 05:54:32 = 165 s after the start; 0x0201 04 -> 04. With the SEP gated as
              macOS's before the entry and at the commit, sequence 0 does not start: the SEP is not
              the gate. Raw: var/milestone3/run5-pre.txt, run5-start.txt, run5-after.txt, runs.tsv.
```
