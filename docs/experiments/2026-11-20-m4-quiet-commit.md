# Does sequence 0 start when nothing touches a device after R38's third write, as macOS? (milestone 4, extra run)

```
Question      With no device access by the glue from R38's third 0x23d2c4000 write to the cores'
              WFIs (no SPMI record, no watchdog-1 re-arm, no probe reads; m4fix bit 6), does the
              always-on engine start sequence 0?
Known         macOS makes no device write after its third 0x23d2c4000 write; all eight cores go
              down within 31 us (R39). Aurora: "No SPMI from here on" (sleep.c 3501, 1f38ff8f4).
              Our glue, with wdt, always writes its record to the power chip over SPMI in the
              commit-point step after that write, then re-arms watchdog 1 (R61's four writes)
              (kernel_hw.rs commit_step, write_record) [sleep-entry.md D8 (b)]. Every clean-room
              sleep run had both. Milestones 1-4: 0x0201 04 -> 04, back at 165 s, in every run.
Prior art     Aurora sleep.c 3486-3505; spec R39, D8 (b), D7 (b).
Outcomes      A  0x0201 04 -> 01 (sequence 1 ran), or a reset 5-7 s after the start of the sleep
                 window (watchdog 2: sequence 0 started and stalled), or a wake at the alarm ->
                 our write after the commit held the engine: tell Naeem at once.
              B  04 -> 04, back at about 165 s -> the write is ruled out.
              C  'DA' in 0x9f04 (core 0's WFI returned after alarm + 2 s) with 04 -> core 0 did not
                 stay down; B's meaning holds for the engine.
              D  the sleep did not start (no 'Da', test kernel still up, other time) ->
                 inconclusive; read real.out/dmesg.
Tell apart    0x0201 after the run (nvmem); the reset time against the start (5-7 s, about 165 s,
              or alarm 20 s + boot); the record bytes: the last one written before the window
              stands (see Safety), 'DA' if core 0 ran late, 'Dr' if a wake reached the kernel.
              There is no commit record and no probe k in this run: begin's 'Da' stands unless an
              outcome overwrites it, so a reset with 'Da' does not by itself show the commit was
              reached; every earlier run of this entry did reach it (ds28 on; m4 runs 1-4).
Not covered   Which device access, if A; anything before R38's third write.
Safety        Watchdog 1 is armed in begin (R61, wdt=150) before any core goes offline, and the
              logic's R15 write of 0x23d2b0010 = 0 restarts its count without disarming it
              (watchdogs.md, D7 (d)); the commit-point step's re-arm is left out, so the bite
              comes 150 s after begin's arming or R15's restart, a few seconds before the usual:
              the run still ends by itself, at about the same time. Watchdog 1 held at 120 s from
              before any trigger (m3run.sh idle), apple_wdt unbound, claim, boot once. Delta
              safety-checked by a second agent before the run.
Budget        1 build (build 3), 1 run (2 if the first does not start), 2 agents; Naeem's "Yes,
              run it" (2026-11-20, relayed by the orchestrator session).
Result        (after the run)
```
