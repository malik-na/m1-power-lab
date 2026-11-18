# Spec gaps reported by the glue tests, round 3 (spec round 14, lab `377cbd2`)

From the kernel glue's test author of round 3 (tests workspace `~/Work/deepsleep-glue-tests-r3`, commit
`5f57d21`, `TESTS.md` section "Round 3" and "Gaps"). Written from the spec, the glue's interface view and
the logic's interface (its TESTS.md section 3 at `c6776ee`) only. Each item names the spec text and
what the tests do until the spec stage answers. GL1, GL2, GL3 bear most on what the glue writes.

- **GL1. D7 (b) and D8 (b) against decision G1 (the probe record).** G1 lets the glue write its
  probe record (`probe=1`, three SPMI writes) on core 0 after cores 1-7 went down and before its
  own final write. D7 (b) has the arming "in the glue's commit-point step ... after every other
  write of its own", and D8 (b) "After the step returns, the cores' final writes follow with no
  device write between". With `probe=1 wdt=N` the probe record is then a write of the glue's after
  the arming, between the cores' final writes; and R61's test line in 8.1 still says "before core
  0's final write". The tests: R61's four are the last device writes before the **first** core's
  final write (D7 (b), D8 (b)), and G1's record is still allowed after it (round 1's R60 test, and
  the probe's 'q' reason, "when watchdog 1 was armed at the commit point"). Settles it: whether G1
  stands beside D8 (b), and R61's line in 8.1 changed to the first core's final write.
- **GL2. The C3 record cannot hold nine 32-bit values.** D8 (a) leaves "its record's format, the
  power chip's bytes" to the glue, and the glue may write no power-chip register but
  `0x9f04`-`0x9f0d` (10 bytes, of which the glue's layout keeps two for 'D' and the reason) and the
  alarm. Nine values of 32 bits (with "not read" for each, D8 (a)) need 36 bytes or more. The tests
  hold only that the record tells apart Linux's values and each slot changed alone to another value
  8.2 C3 names (`0x222`-`0x666`); a lossy encoding that keeps those apart passes. Not stated:
  which bits of each value the record must keep, and whether a record that cannot hold them all
  may be several records over time (only the last survives a reset). Also: at the commit-point
  step all nine are `Some` (D8 (a)), and on D6's failure the step is not called; so the `None`
  that D8 (a) introduces to "say a place was not reached" never reaches a record the spec asks for.
  Whether the failure record should also say which of C3's places the entry reached (ds20's "the
  record could not say where the entry stopped", L25) is not stated.
- **GL3. Several records at the commit point.** With `cand_c3` the C3 record, with `snap=2` the
  'C' record, with `wdt` the glue's 'W'/'c' mark, with `probe=1` (after the first final write) the
  'Q'/'q' record: one 10-byte record survives. Which one wins is not stated. The tests hold the C3
  record to be the one standing when the cores go down with no option, `wdt`, `trace` and both
  (D8 (b) says "the glue makes its record there"; the 'W' mark is the glue's own invention, not in
  the spec, and D8 (b) leaves no room for a trace mark after the step); with `snap=2` or `probe=1`
  they hold nothing about it.
- **GL4. D8 (b) "The glue makes its record there" with `cand_c3` off.** Whether a record (nine
  `None`) is made at every commit point or only with the switch on is not stated. The tests take
  the second; round 1's test that no record is written with every option off stands.
- **GL5. Trace marks after the commit-point step.** The trace rule of the glue's interface puts a
  mark "before every `run_on`", so before the first PowerDown `run_on`; D8 (b)'s "the cores' final
  writes follow with no device write between" (after the step returns) excludes it. The tests
  follow D8 (b): no trace mark after R38's third write of `0x23d2c4000` (round 1's test changed).
  Whether "no device write" in D8 (b) is meant for the glue's diagnostics too is for the spec to say.
- **GL6. Where the failure record goes in D8 (c)'s order.** D8 (c): return the cores, disarm
  watchdog 1, return to the suspend path, "watchdog 1 last, so that a hang while the cores are
  returned still ends by itself". D6 (g) says the record names the wait but not when it is written.
  The round's brief has "disarms watchdog 1, writes the record naming the wait, and returns"; a
  record written after the disarm (raw polled SPMI commands) is not covered by the watchdog if the
  controller does not answer. The host tests cannot see the C half's order and accept either
  (reviewer item 18).
- **GL7. D7's disarm on returns to Linux other than D6's.** D7 (c) names only "D6's failure return".
  With D7 (a) the watchdog is armed before the logic runs, so every other way back to Linux before
  a power-down leaves it armed too: `run_on` not answered (-ETIMEDOUT, address 0), `snap=1`'s stop
  at the commit point. Not stated; reviewer item 19.
- **GL8. The interface: the 'T' record's kind and core.** record.rs gives a failure record the
  kind and core "of the last access" and the 'T' address "the error's". After D6's put-back the
  last access is a put-back access, so the 'T' record would name the error's word with the put-back
  access's kind and core. The tests follow D6 (g) ("word, width, core") and require kind 1
  (32-bit read) and core 0, the wait's own.
