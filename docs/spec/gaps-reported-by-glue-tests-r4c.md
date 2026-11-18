# Spec gaps reported by the glue tests, round 4c: the `pmp` client (spec round 15d, lab `14e4c78`)

From the test author of glue round 4c (tests workspace `~/Work/deepsleep-glue-tests-r4`, commit
`4eb5fa4` on `c2b6493`; `TESTS.md` section "Round 4c"). Written from the spec at `14e4c78` and the
interface view (`interface/pmp_client.rs.iface`) only. Round 15d answered G28 and G29; the tests now
follow those answers and hold D12. The interface gained `PmpHw::now_us` (G29's time read) and
`PmpHw::log(part, step, values)` with the types `Part` and `Step` (D12; each step's values in the
interface's doc comments and in `TESTS.md`). Two places are open; each item names the spec text and
what the tests do until the spec stage answers.

- **G30. D12 (b)'s five reads where no R5 stop follows.** D12 (b): "On a wait that runs out, before
  R5's stop, the client reads once and logs: `pmp`'s A2I control word `0x23bc08110`, PMP ..., PMS_SRAM
  ..., PMS ... and `pmp`'s translator word +`0x40` ... These five reads are the only accesses D12
  adds, and only on that path". R5's stop follows a wait that runs out at boot (D10 (a)) and at the
  entry (D10 (b)). It does not follow one at the wake: D11 (d) "at the wake it leaves `pmp` as it is
  and reports" (the handshake's waits), and D10 (c)'s PMS_SRAM wait ("the client reports and makes
  nothing more in that wake"). The stop is made later by the next entry part (D10 (b), "The entry
  after a wake whose wait ran out ... R5's register stop"), in which no wait of its own ran out. Not
  stated: whether the five reads are made at a wake wait that runs out (they would settle the same
  questions there: whether a word towards `pmp` waits untaken, the translator's error word), and
  whether that next entry part makes them before its stop. Tests: at the wake (both kinds of wait)
  the reads of A2I and +`0x40` are allowed, not required; at that next entry part they are not
  allowed (its control-page accesses are R5's stop alone, D10 (b), D11 (f)).
- **G31. Where the count of words not answered by `message` is logged.** D12 (a): "Words received
  outside the waits and not answered (D10 (f), G28) are counted and the count logged at the part's
  end." Words handed to `message` (the mailbox's receive callback between parts) belong to no boot,
  entry or wake part; after a skipped entry (G28) all of them are such words. Not stated: whether their
  count is logged by the next part's end line, at each `message` call, or not at all. Tests: each word
  handed to `message` gets a `Received` line (held, D12 (a) "every word ... received", D10 (f) round
  15d "counted and logged"); `message` writes no `End` line, and where its count goes is not held. The
  boot's, entry's and wake's `End` lines count the words received inside that part (held at boot: a
  kdebug GET_BUFFER adds one).

A reading, not a gap: with the switch off at a part's start the part neither logs nor reads the
clock (D10 (e), "no call of any kind on the client's machine interface", now that both are on that
interface; D12's test form is "the switch on"), so D12 (c)'s first line is written only with the switch
on. Held by `c18_g_with_the_switch_off_the_client_does_nothing`.
