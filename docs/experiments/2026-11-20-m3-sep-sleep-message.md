# Does sequence 0 start when the Secure Enclave is told to sleep and reads gated before the entry? (milestone 3, run 2)

```
Question      If the SEP is sent its sleep request before the entry, answers, and its domain
              0x23b700c00 reads gated (bits 4-7 = 0) before the sleep starts, does the always-on
              engine start sequence 0 after Linux's commit?
Known         See 2026-11-20-m3-sep-at-commit.md (run 1) for the SEP's word at the commit without a
              message. macOS sends no SEP message at its entry; its SEP is gated by automatic power
              (0x1000230f) [cards/coprocessors.md]. The old driver (second-hand) had the SEP gated
              before every entry, by message or by idling after rmmod apple-sep, and some of its runs
              reached sequence 1 [var/catchup/PLAN.md 22-23, 126-133; run26-watch README 10-12].
              Aurora (T8140): "a commit with it running never returned" [coprocessors.md].
Prior art     The message: Aurora proto.rs op_sleep(): control endpoint 0, type 0x0c, param 0x02,
              tag 8 -> msg0 0x00000000020c0800; reply 0x0000000000010800 (endpoint 0, tag 8, type 1);
              timeout 5 s [aurora-ref linux-integration 1f38ff8f4, drivers/soc/apple/proto.rs 94-104,
              192-202, 325-345]. The lab's old plan records the same type/param with tag 1,
              0x00000000020c0100, then "its word reads 0x1000230f" [var/catchup/PLAN.md 22-23].
              This run sends tag 0x7f (the probe driver hands out 0x01-0x7e), msg0
              0x00000000020c7f00, via /sys/module/apple_sep/parameters/probe_sleep (probe/m3-sep
              ecbbcc4aa; side notes probe-m3-sep.md).
              Aurora's commit path waits for the domain's bit 10 (DEV_DISABLE) after the reply
              [pm_shim.c sep_pm_commit_stop]; on t8103 macOS's gated word has bit 10 clear, so this
              run waits for state 0 (bits 4-7) instead.
Outcomes      A  0x0201 04 -> 01, or a reset 5-7 s after the commit -> the SEP gated by message lets
                 sequence 0 start: tell Naeem at once, stop running.
              B  SEP answered, pre-entry word gated, k 172 gated at the commit, 0x0201 04 -> 04, reset
                 at 165 s -> the SEP is ruled out: by the stop condition the deep-sleep work stops.
              C  no reply, or the word never reads gated within 10 s -> the message did not take; the
                 run is not started (no sleep); fix the probe or the wait once (budget: up to 4 runs).
              D  gated before the entry but k 172 reads state f at the commit (something woke it) ->
                 inconclusive for the question; find the sender, repeat once.
Tell apart    The probe's dmesg lines (reply raw, ms) and the userspace poll of 0x23b700c00 before
              the entry (run file); k 172 at the commit; 0x0201 after; the reset time.
Not covered   The SEP's wake (doorbell 0xffffffffa4829303 in Aurora; not needed: no run is expected
              to resume Linux); bits of 0x23b74c200 above 7.
Safety        Same kernel and switches as run 1; the message is the only new device access (one
              mailbox send); wdt=150 armed in begin; apple_wdt unbound; boot-once; claim taken. The SEP
              stays asleep until the reset; the next boot (stock) boots SEPOS afresh.
Budget        The build of run 1, 1 run (2 if C or D), no extra agent.
Result        C, three times; the sleep was never started, so the question is not answered.
              Run 2 05:19:45, tag 0x7f (msg0 0x020c7f00); run 3 05:23:28, tag 8 (msg0 0x020c0800,
              Aurora's trace, apple_sep.probe_sleep_tag=8): the driver's senders stopped (busy 0x0),
              the request was sent, no reply in 5 s and no message at all from the SEP after it;
              0x23b700c00 stayed 0x1f0022ff (dmesg "probe_sleep: no reply within 5000 ms").
              Run 4 05:27:16 (the old recipe, var/run22-src/run22.sh 20-26): rmmod apple_sep (rc 0);
              0x23b700c00 read 0x1f0022ff in all 30 polls over 50 s: the enclave did not gate itself.
              Each boot was held by watchdog 1 (120 s, /dev/watchdog0 held open) and came back on stock
              by itself. On every probe boot the SEP's Touch ID sensor bring-up fails
              (REGISTER_SERIAL ETIMEDOUT, "retrying in 10 s") and the entropy survey reads EIO; on stock
              apple-mesa binds the sensor and the SEP reads 0x1000230f when idle. That the failed
              sensor keeps the SEP on is an inference, not read.
              Raw: var/milestone3/run2-pre.txt, run2-sep-dmesg.txt, run3-pre.txt, run4-pre.txt, runs.tsv.
```
