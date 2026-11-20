# What does the Secure Enclave's domain read at Linux's commit, with the entry as milestone 2 ran it? (milestone 3, run 1)

```
Question      With the entry as milestone 2 ran it (cand 0xffffe, no SEP message), what do the SEP's
              domain 0x23b700c00 and PMGR 0x23b74c200 read at core 0's last write, and does sequence 0
              start?
Known         macOS 13.5: no SEP message; 0x23b700c00 = 0x1000230f (request f, state 0, bits 8-9 and
              28 set: gated by automatic power) awake and at its commit [cards/coprocessors.md; 
              cards/power-domains.md; spec C1].
              Stock Omarchy (7.3.0-0test5) on the M1, 2026-11-20 04:58, SEPOS booted and idle (Touch ID
              ready): 0x23b700c00 = 0x1000230f, 0x23b74c200 = 0x4 (read with /dev/mem, rd.py).
              Probe kernels load apple_sep too (m2cache dmesg: SEPOS booted at 8.2 s), but the sensor
              bring-up fails and retries every 10 s ("retrying in 10 s", real-dmesg-before.txt of
              milestone-2 run 8): the SEP has traffic, so it may not be gated at the entry. Its value
              there and at the commit was never read under a probe kernel.
              C1 (in 0xffffe) runs R56 form 2 on 0x23b700c00 only if bits 4-7 read nonzero
              [dsk-probe-m1-leads logic/cand.rs 595-601].
              Old driver (second-hand): under 13.5 the SEP gates itself ~1.4-3 s after its driver's
              last exchange; its entries read 0x23b700c00 gated and some reached sequence 1
              [docs/evidence/2026-11-16-run26-watch/README.md 10-12; var/run22-src/run22.sh 20-26].
Prior art     Aurora proto.rs op_sleep (0x020c0800, reply 0x00010800), pm_shim.c sep_pm_commit_stop
              (send, wait for the reply, poll the domain's bit 10 before the commit; T8140) [aurora-ref
              linux-integration 1f38ff8f4]; asahi-docs hw/soc/sep.md (message layout).
Outcomes      A  0x0201 04 -> 01 or a reset 5-7 s after the commit -> sequence 0 started without a
                 message: tell Naeem at once, stop running.
              B  k 172: SEP state (bits 4-7) f at the commit (C1 did not take, or a sender woke it),
                 04 -> 04, 165 s -> the SEP is fully on at Linux's commit, unlike macOS: run 2 tests it.
              C  k 172: SEP state 0 with request 0 (C1's form 2: low bits 0x3f0/0x300) -> forced off
                 by C1, not macOS's 0x1000230f: run 2 tests the message-gated state.
              D  k 172: 0x1000230f-like (request f, state 0, bit 28) -> the SEP was already gated as
                 macOS's at the commit and sequence 0 still did not start: the SEP is very likely not
                 the gate; run 2 still runs (the message is the brief's test) but A is not expected.
              E  record missing / k 172 not captured -> inconclusive: repeat once.
Tell apart    k 172's bytes (SEP bits 0-15, 24-31; 0x23b74c200 bits 0-7) in the 'q' record; the
              userspace read of both words just before the entry (start file); 0x0201; reset time.
Not covered   What the SEP does after the commit; bits of 0x23b74c200 above 7 (k 171 not in the
              record of this run).
Safety        Probe kernel probe/m3-sep, safety-checked; wdt=150 armed in begin; apple_wdt unbound;
              boot-once; reads only at the commit; claim taken.
Budget        1 build (shared with run 2), 1 run, the probe and safety agents.
Result        B. Run 1, 2026-11-20 05:15:23 (probe/m3-sep ecbbcc4aa, m3s-k172.cmdline, cand 0xffffe):
              before the entry 0x23b700c00 = 0x1f0022ff (state f, fully on), 0x23b74c200 = 0x4;
              record 44 71 ac 80 ff 20 1f 04 90 00 = k 172 = 0x041f20ff: at core 0's last write
              0x23b700c00 = 0x1f0020ff (request f, state f, bit 28) and 0x23b74c200 bits 0-7 = 0x04
              (bit 2 set); stock kernel up 05:18:09 = 166 s after the start; 0x0201 04 -> 04. The SEP
              is fully on at Linux's commit although C1 runs form 2 on it (why it reads on again: not
              read). Stock Omarchy, same machine, SEPOS idle: 0x1000230f (macOS's value) at 05:29:48.
              Raw: var/milestone3/run1-pre.txt, run1-start.txt, run1-after.txt, runs.tsv.
```
