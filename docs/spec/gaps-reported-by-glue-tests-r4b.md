# Spec gaps reported by the glue tests, round 4b: the `pmp` client (spec round 15c, lab `22077e2`)

From the test author of glue round 4b (tests workspace `~/Work/deepsleep-glue-tests-r4`, commit
`7325945` on `b0ba479`; `TESTS.md` section "Round 4b"). Written from the spec at `22077e2` and the
interface view (`interface/pmp_client.rs.iface`) only. Round 15c answered all of G1-G27; the tests
now follow those answers. Two places are still open; each item names the spec text and what the
tests do until the spec stage answers.

- **G28. `message` after an entry part the switch skipped.** D10 (e): "on at boot, off at an
  entry: that entry part and the wake part after it make nothing; `pmp`, still running, falls to the
  logic's own rule (... with PMS_SRAM self-gating at `0x1000030f` it may find it off and leave `pmp`
  running ...), and the client counts `pmp` as not its own until the next boot". D10 (f): the client
  answers words outside its waits "While `pmp` runs in the client's view (from R71 (e) at boot to the
  entry part's R5 stop, and from R5w at a wake whose handshake got through to the next entry part's
  stop)", and sends nothing "after a part that gave `pmp` up ((e))". Not stated: whether a skipped
  entry part ends the client's view of `pmp` running (no R5 stop was made, and the skipped part is
  not in (e)'s list of parts that give `pmp` up), so whether LOG and type-8/type-4 words are still
  echoed and buffer requests answered by `message` after it. Tests: not held (the later entry and
  wake parts with the switch on are held to make nothing).
- **G29. Where a wait's bound starts when other words arrive inside the wait.** D11 (d): "every
  wait's bound is 1 s, except `0x000200000023b549`'s, 6 s ...; the client may make a bound longer, up
  to twice these. In test form: no wait ends before its bound unless its word has come, and every
  wait ends." The table measures each gap "from the word the awaited one follows"; D10 (f) has the
  client answer other words while it waits ("that word stays awaited"). Not stated: whether the
  bound runs from the start of the wait (the word the awaited one follows) or restarts at each
  other word answered, nor whether a stream of unrelated words may extend a wait without end. The
  interface's `PmpHw` gives the client no clock: it can count only its `recv` timeouts that ran out
  and its `delay_us`. Tests: a wait that ran out lasted at least its bound less 10 ms from the
  client's last device access or word before it ended, and the client's own waiting there (its
  `recv` timeouts that ran out and its delays) is at most twice the bound plus 1%; a word 900 ms late
  (5.89 s for `0x000200000023b549`) is waited for. A wait extended by unrelated words is not tested.

Also recorded (not a gap): through the glue at kernel `283e914ef`, D9 (b)'s test form (i) fails for
`cand` 0, `0x40000`, `0x40100`, each with PMS_SRAM `0x1f0003ff` and `0x1000030f` (98,271 forbidden
accesses each: R5's register stop, the two +`0xfc` writes and R6 in the entry; R6w and R55 at the
wake). That is D3 (b), the logic's change through its own cycle (spec D9 (b) round 15c). In that
simulated wake the logic made no control-page access (no R5w), which corrects round 4's report.
