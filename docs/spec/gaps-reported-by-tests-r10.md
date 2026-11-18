# Spec gaps reported by the tests, round 10 (spec round 13, lab `c8b735c`)

From the test author of round 10 (tests workspace `~/Work/deepsleep-tests-r10`, commit `eb9f9a0`,
`TESTS.md` section 16). Written from the spec alone; each item names the spec text and what the
suite does until the spec stage answers. Most important first is not claimed; Z2, Z3, Z4 and Z6
bear most on D6.


- **Z1. C3's nine values: no interface is stated.** 8.2 C3 says the driver hands them to the
  glue. The suite adds `DeepSleep::c3_readings(&self) -> [u32; 9]`, valid after `enter` returns
  `Ok` until the next `enter` (its own choice), and what it returns with `cand_c3` off or after a
  failed entry is not specified.
- **Z2. D6 (c), "to the value the driver read before its first write of it".** The entry writes
  words it does not read first (macOS makes such writes, and section 8 repeats them). Whether D6
  requires a read before each such write (which would add reads the captures do not have at
  those places), or leaves those words as written, is not stated. The suite holds only words read
  before their first write.
- **Z3. D6 (c) and the watchdogs' and interrupt controller's words.** Taken literally, (c) puts
  back R15's writes of the watchdog block (`0x23d2b0000`, `0x23d2b0010`, `0x23d2b8008`,
  `0x23d2b800c`, `0x23d2b000c`) to their earlier values, which with watchdog 1 armed by the glue
  (D7) could rewind its count; and a "set" word of the interrupt controller (R36's
  `0x23b104100`+4k) written back with the value read does not clear what the entry set. The suite
  leaves the watchdog block out and holds the interrupt words to the letter (the value written).
- **Z4. D6 (e), cores "given back to Linux".** At the logic's interface a core is parked by
  `run_on(core, CoreJob::Stop)` and writes its stop bit (R11); what giving it back is (a job, a
  write of the stop/start block, the glue's) is not stated. The suite only allows core start
  words among the writes after the wait and leaves the start/stop block out of the put-back.
- **Z5. D6 (c), "in the reverse order of its own changes"**, for a word the entry changed at
  several places (a sub-block's word, a domain word turned on by R50 and off later): the order is
  not defined. The suite holds the order only between words whose entry writes do not interleave.
- **Z6. D6, which waits.** Section 8 states two waits of the entry as waits: R16's poll and R22a's
  status words. A domain's turn-off has none ("a wait for it is not observed", R56), and a
  coprocessor's reply that does not come is not an error (D3; the fourth round's decision). Whether
  a coprocessor's bounded wait is a D6 wait (end the entry) or stays a "go on" is not said; the
  suite keeps "go on" (`Ok`, as before) and tests D6 at R16 and R22a only.
- **Z7. D6 (c) for a domain put back to request 4 before the sleep.** R57: request 4 is never
  written over request 0 in any capture, and before the sleep no request 4 write is observed; D1's
  forms are those of the wake. The suite's machine accepts the write for a word found at request 4
  and does not judge its form.
- **Z8. C5 revised, its four reads.** "First R PMS, SIO_BUSIF, SIO, SIO_CPU": whether in that order
  and whether section 8's or D3's own reads of the same words at that place may stand for them is
  not said. The suite requires each read at C5's place before its first access of the twelve and
  decides on the last such read; their order is not held. C5's own bounded wait (D5 (e)) is not
  tested: a domain frozen for C5's wait stays frozen for section 8's later steps on the same word.
- **Z9. C3's places (ii) and (iii).** "Immediately after R22's write" is taken as: the first three
  device accesses after it (before R23's SIO accesses, which R62 (b) otherwise has alone there);
  "at the commit point, before the cores' final writes" as: after the entry's last write of
  `0x23d2c4000` and before the first core's final write.
- **Z10. D7's places are inside `enter`.** D7 (a) puts the glue's arming at 8.2's entry start
  ("after D3's decisions on the coprocessors, before the driver's first device write"), and (b)
  at the commit point; both lie inside `enter`, which the glue calls as one step. As with gap X4,
  the glue needs a hook there, or the owner accepts the arming just before `enter` (which differs
  by D3's reads only) and R61's four as the logic's last writes or right after `enter` returns.

## Gaps of the eleventh fill and the review (Z11-Z13), carried from deepsleep-tests-r10 TESTS.md section 16 at d628d4a

- **Z11. What the SIO family reads after C12's turn-on with bit 28.** macOS's idle value of
  SIO_BUSIF, SIO and SIO_CPU is `0x1400024f` (state 4; spec l. 2096-2115, 4.2a), the wake snapshot
  has them `0x0f0003ff` right after their turn-on (l. 5036). If on the machine C12's turn-on (form
  4, ending with bit 28) lets them drop to state 4 before C5's reads, C5 with C12 always reads only
  (its gate asks bits 4-7 = `0xf`), and C5 never acts with C12 on. The suite's default machine
  does that (the capture's value after a bit-28 write); C5's tests with C12 use a machine where the
  family stays at 0xf. Settles it: one read of each of the three right after C12's turn-on on the
  M1, and whether C5's gate is meant on the state or on the request.
- **Z12. D6 (b) and C15's write of `0x23b718004`.** D6 (b) forbids any write of `0x23b718004` after
  a D6 wait (R22). C15 (immediately before R22a) writes `0x23b718004` = `0xf` after reading it; on
  R22a's failure rule 3 puts it back to the value read, which under Linux (L23's machine, `0`) is
  R22's own value. The suite lets the put-back write through (once, to the value read) and forbids
  any other write of that word after the wait.
- **Z13. D8 (a) "valid inside the glue's commit-point step".** While `enter(&mut self, ..)` runs the
  glue cannot call `c3_readings(&self)` on the same driver (Rust's borrow rules; a `no_std` driver
  kept in a static is no different without `unsafe`). The suite hands the nine values to the step
  as its argument (`Hw::commit_point(&mut self, c3: &[Option<u32>; 9])`), the same nine the

Reviewer's note on Z12 (review of d628d4a): D6 (c) rule 3 would put `0x23b718004` back to the value C15 read. Under Linux that value is 0, which is R22's trigger value (the write the always-on side's sleep step follows, R62), which D6 (b) forbids. No current test reaches this case (capture D's pre-value is `0xf`, and C15 comes after R16). The spec should settle it before the driver implements rule 3 for that word.
