# Spec gaps reported by the tests, round 10f (spec round 15d, lab `14e4c78`)

From the logic's test author of round 10f (tests workspace `~/Work/deepsleep-tests-r10f`,
commit `80ec294`, `TESTS.md` section 16, "Round 10f"). Written from the spec alone (`spec/` as
copied at lab `14e4c78`); no driver source was read. Each item names the spec text and what the
suite does until the spec stage answers. Both come from D5's round-15d note on a turn-on whose wait
runs out (l. 4798-4819), which the suite now tests in the entry, the put-back and the wake.

- **R10F-1. The wake's own write of a domain whose turn-on ran out in the entry.** D5's note leaves
  such a word "as the second write left it (request `0xf` ... bit 28 clear)" and says "Later steps
  act on the word as they find it", naming R23, D6's put-back and D5 (f)'s put-back by form 1. It
  does not name the case where macOS's own wake writes the word, so that D5 (f) leaves it to
  "the wake's write as section 8 has it": W1-2c's power-domain writes, which the suite holds to
  the scenario's capture (class P; R40 "back to the state it had before the sleep", [UNKNOWN],
  one domain in one capture). C12's children (UART8, written `0x44` by capture G's wake) and C11's
  FPWM1 (written `0x340` by F's wake, R40) are such words. On the round-10f driver, with the word
  held off in the entry, the wake writes UART8 `0xf4` and FPWM1 `0x3f0` instead. Is the wake's write
  of such a word macOS's value at that place (the capture's), a value derived from what the entry
  left (and then which), or D5 (f)'s put-back? *Until answered:* the suite holds a run whose entry
  meets a held word to the entry only (`tests/bit28.rs`, `entry_held`); its wake is not judged.
- **R10F-2. `leave_late` after a D1 turn-on whose wait ran out at the wake.** D5's note: "the wait's
  end is the driver's to report as its other waits', and the entry goes on by (e) (on D6's path by
  D6 (d))". For the entry and the put-back that is stated; for D1's turn-ons at the wake
  (`leave_late`) neither the report nor the going on is. The round-10f driver, with MSG held off
  after the wake, makes MSG's first two writes and a bounded wait, then returns
  `Err(WaitTimedOut { addr: 0x23d280078 })`; on capture D's Linux machine SOC_SPMI0 (found
  `0xf000244`) is then not written in `leave_late` and ends at the request 0 (the other words were
  not looked at). Does `leave_late`
  return an error, and does the put-back of the remaining words go on first (as D6 (d) has it for
  the entry's put-back)? *Until answered:* the suite accepts `Ok` (then the whole cycle is held) or
  `Err(WaitTimedOut)` naming the word (then only "no violation"); what else is put back after the
  wait is not judged.

Choices the suite made that need no answer to go on (TESTS.md section 16, round 10f): the
simulator holds a word's state through a turn-on (before the sleep, and new, after the wake); C16's
GPIO is not held (with it off, section 8's steps write the pin controller in a domain that is not
on); R23 meeting a parent of C12's family with bit 28 clear, form 5 and R30's table at the wake are
not reached; for a silent coprocessor a write of +`0x8114` with bit 0 clear at the wake stays free
(D3 (c) names only `0x20001`); bit 0 of `cand` stays unspecified and unset (D9 (b) names bits
18-31).
