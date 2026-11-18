# Spec gaps reported by the glue tests, round 3c: the abort before `enter` and the exception's mark (spec round 15c, lab `22077e2`)

From the test author of glue round 3c (tests workspace `~/Work/deepsleep-glue-tests-r3`, commit
`41056de`, `TESTS.md` sections "Round 3c" and "Gaps in the spec or the interface"). Written from
the spec (D7 (a), (c), (e) and D8 (c) of round 15c; line numbers of `22077e2`) and the glue's
interface view only. Round 15c answered GL10-GL13; the host tests changed for GL10 and GL11 only
(no outcome changed at kernel `283e914ef`: 145 of 145 pass). Each item names the spec text and
what the tests do until the spec stage answers.

- **GL14. A core parked before `enter` when Linux aborts.** D7 (c) l. 4977 (GL11): "no core is
  parked before `enter`, so none to give back". The glue's log lines have "core %d (CPU%u)
  offline, parked" and "prepare: cores 1-7 go offline under deep-sleep control", and D7 (a) l.
  4902 lists "any core's going offline (in `prepare` or wherever the glue or Linux takes them
  offline)" before `enter`. By Linux's suspend path as the test author knows it (not read for this
  round: `kernel/power/suspend.c`, `suspend_enter`), the other cores go offline after
  `prepare_late`, and Linux can still abandon the suspend after that and before `enter`
  (`syscore_suspend` failing, a wakeup pending), bringing them back online itself before `wake`,
  `finish`, the devices' resume and `end`. If the glue parks a core when it goes offline, a core is
  parked in that abort. Not stated: (a) whether the glue's parking is at the offlining or only
  inside `enter`; (b) if at the offlining, whether a parked core that does not come back online in
  that abort is D7 (c)'s exception (record, panic) or Linux's own CPU-up error followed by `end`'s
  disarm (a Linux missing a core with nothing armed, against D7 (c)'s reason (iv)). Tests: none
  (the parking is the C half's); review item 28 (iii).
- **GL15. The die notifier and the exception's mark.** GL13 (D7 (c) l. 4980) stands the panic
  notifier down on the exception's panic; the glue also has a die notifier that writes an 'E'
  record into the same ten bytes `0x9f04`-`0x9f0d` (the interface's record.rs: "'E' die/oops").
  Not stated: whether an oops on another core during the exception's panic, or a die between the
  exception's record and its `panic()`, may write 'E' over D8 (c) (1)'s record, or stands down by
  the same mark. Tests: none; review item 31.
