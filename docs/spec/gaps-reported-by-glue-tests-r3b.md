# Spec gaps reported by the glue tests, round 3b: watchdog 1's first arming, the panic, Linux's watchdog (spec round 15b, lab `f411b43`)

From the test author of glue round 3b (tests workspace `~/Work/deepsleep-glue-tests-r3`, commit
`2a849a8`, `TESTS.md` sections "Round 3b" and "Gaps in the spec or the interface"). Written from
the spec (D7 (a), (c), (d), (e) and D8 (c) of round 15b; line numbers of `f411b43`) and the glue's
interface view only. The tests define one new interface function for D7 (a) and (e),
`int apple_ds_sleep_step_start(bool linux_wdt)` (the sleep step's first call; the C half passes
whether Linux's watchdog core drives watchdog 1), so no gap is needed for the host side. Each item
names the spec text and what the tests do until the spec stage answers.

- **GL10. A `run_on` not answered: the disarm or the panic?** D7 (c) l. 4847 lists "a `run_on`
  the glue made that was not answered (its -ETIMEDOUT)" among the ways back that end in the
  disarm; the exception, l. 4852, takes "a core the glue parked [that] cannot be given back (its
  `run_on` not answered, or not answered when it is to be released)" to the record and a panic.
  Every `run_on` of the entry is to a parked core (the Stop and PowerDown jobs), so the two
  overlap. Not stated: whether a core that did not answer its job but may still answer its
  release goes the disarm way (the glue tries the release first) or the panic way at once. Tests:
  only that the Rust half leaves watchdog 1 armed on these returns (both readings agree there);
  the choice is the C reviewer's.
- **GL11. Which callback is "the sleep step".** D7 (a) l. 4819 defines it as "the step in Linux's
  suspend path in which the glue parks cores 1-7 and calls `enter`". The glue's log lines put a
  record ('Da') and the power-chip clock read in `begin`, the cores' going offline in `prepare`,
  `dump`'s reads in `prepare_late`, and the parking check and `enter` later. If these are separate
  callbacks, which one starts the step? Must the arming (and D7 (e)'s check) precede `begin`'s
  record and clock read and the cores' offlining (then N also covers the device suspend between
  those callbacks, which l. 4837 leaves outside the glue), or only the callback that calls `enter`
  (then the offlining in `prepare` comes before the arming, against "before the glue parks any
  core")? And does D7 (e)'s "no device access at all in that sleep" (l. 4902) include `begin`'s
  record and read, made before the check? Tests: the host cannot see it; review item 23.
- **GL12. D7 (e) without Linux's watchdog device.** Not stated: what the check gives when
  `23d2b0000.watchdog` has no driver bound (module not loaded, node disabled): "not driving" (the
  sleep goes on) or a refusal. Nor whether "marked as running in hardware" (l. 4900) means Linux's
  `WDOG_HW_RUNNING` flag only (no device access is allowed, so not the control register). Tests:
  the C half passes a boolean; review item 24.
- **GL13. The panic and the glue's own panic record.** D7 (c) reason (4), l. 4872: "the record is
  made before the panic, so the reset leaves it standing in the power chip", and l. 4857 "no other
  device write after the record". The glue's interface has a panic notifier that writes a 'P'
  record into the same ten bytes `0x9f04`-`0x9f0d`, which on this panic would replace D8 (c) (1)'s
  record and be a device write after it. Not stated: whether the notifier stands down on this
  panic, or its 'P' record is the record the exception means. Tests: none (the C half's); review
  item 25.
