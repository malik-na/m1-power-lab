# Spec gaps reported by the tests, round 10e (spec round 15c, lab `22077e2`)

From the logic's test author of round 10e (tests workspace `~/Work/deepsleep-tests-r10e`,
commit `51f0997`, `TESTS.md` section 16, "Round 10e"). Written from the spec alone (`spec/` as copied at lab
`22077e2`); no driver source was read. Each item names the spec text and what the suite does
until the spec stage answers. R10E-1 bears on what a logic following D3 (b) may write; R10E-2
on a state the machine has been read in (L15: `sio` marked running and silent).

- **R10E-1. `sio`'s translator for a `sio` found stopped.** D3 (b) (l. 4698-4703) gives a `sio` or
  `pmp` found stopped "no write to its control page, mailbox page or translator", and 8.1's row
  D3 (b) "no write to its blocks or translator". For `pmp` the translator writes are its own
  action's (R73's two +`0xfc` writes, R55). For `sio` the only translator writes in section 8 are
  R10's +`0xfc` stepping of `dart-sio` (`0x2350040fc`, in the translators' own action at the end
  of E3) and W1-8's 30 writes in the wake's early part (with the caller's two inputs
  `0x235004200`, `0x235004210`). Neither R10 nor W1-8 is conditioned on `sio`'s state, D3 (b)'s
  "Reasons" are about R5w and R6 only, and the R6 note (l. 3943-3947) names "R5, R5w for a `sio`"
  alone. Are R10's four writes and W1-8's 30 writes of `dart-sio` made for a `sio` found stopped?
  *Until answered:* the suite accepts, on each side separately, either all of the captures'
  writes or none (`check_sleep_actions`, `check_whole_early`); a part of them is refused.
- **R10E-2. A `sio` or `pmp` found marked running and silent.** D3 has the entry stop it after a
  bounded wait (R5's register stop). The R6 note says R6w, R55 and R5w are made for a `pmp` (R5w
  for a `sio`) "that the same entry stopped", and D9 (b)'s table "the logic, **only if** its entry
  stopped `pmp`". The entry did stop a silent one. Is "only if" also "if" here: does the wake make
  R5w (+`0x44` = `0x10`, which starts the firmware) for a coprocessor that did not answer before
  the sleep, and R6w and R55 for such a `pmp`? *Until answered:* the suite keeps the fourth
  round's decision (TESTS.md section 10): for a silent one the wake makes R6w and R55 (for
  `pmp`) and no R5w and no boot exchange.
- **R10E-3. `cand_c18` at the logic's interface.** D9 (b) says the logic "does not read the
  switch", and C18 is bit 18 (`0x40000`) of `cand`. The logic's `set_candidates` was specified by
  the suite (round 9) with bits 18-31 zero and unspecified. Does the glue hand the logic `cand`
  with bit 18 as it is, or with bit 18 cleared? *Until answered:* the suite holds the logic to
  making the same accesses with bit 18 set as without it, access for access, in every state it
  runs it in (`tests/foundstopped.rs`).

Choices the suite made that the spec leaves open but that need no answer to go on (TESTS.md
section 16, round 10e): for a coprocessor found stopped, a read of its control page other than
+`0x44` and +`0x48` is refused (D3 (b) names those two as the reads that stay allowed); `sio` is
held to D9 (b)'s test form (i) as `pmp` is (no access to its block at the wake); "the twelve
64-bit reads/writes" are allowed as 64-bit accesses only (R49). D9 (b)'s test form (iii) (`pmp`'s
domain off) is not reached by the suite's machine, which has PMS_SRAM on by R50 before `pmp`'s
place (the round-9 gap Y1, unchanged).
