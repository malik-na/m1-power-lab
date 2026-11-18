# Spec gaps reported by the glue tests, round 3d: B's edge values and the counts at (a) and (b) (spec round 15d, lab `14e4c78`)

From the test author of glue round 3d (tests workspace `~/Work/deepsleep-glue-tests-r3`, commit
`939452f`, `TESTS.md` sections "Round 3d" and "Gaps in the spec or the interface"). Written from
the spec (D6 (f), D7 (c), (d), D8 (c) and D9 (b) of round 15d; line numbers of `14e4c78`) and the
glue's interface view only. Round 15d answered GL14 and GL15 (review items 34 and 36; no host
test). The tests added `apple_ds_wdt_linux_timeout(bool bound, u32 timeout, u32
max_hw_heartbeat_ms)` to the interface for B; at kernel `646563f83` 146 of 148 pass, the two
failing being the new tests that need that function. Each item names the spec text and what the
tests do until the spec stage answers.

- **GL16. B's edge values.** D7 (c) l. 5131-5134: B is the driver's `timeout` "capped at
  `max_hw_heartbeat_ms` / 1000, times 24,000,000". Not stated: (a) a `max_hw_heartbeat_ms` of 0
  (in Linux's watchdog core, as the test author knows it, 0 means the driver set no hardware
  maximum; the cap would then give B = 0, a bite of 0); (b) a `timeout` of 0; (c) a product above
  `0xffffffff` (a `max_hw_heartbeat_ms` above 178,999 with a `timeout` above 178); (d) whether
  "the bite Linux's driver last wrote" is the formula or the value the driver's own
  `set_timeout` computed when they differ (for example a driver that rounds). The tests use only
  timeouts of 30-500 s with caps of 99 and 178 s; reviewer item 33.
- **GL17. The counts at (a) and (b) are the Rust half's.** D7 (d) l. 5189-5198: the glue takes
  `CNTVCT_EL0` "at (a), at its call of `enter`, at the commit-point step (b), at `enter`'s return,
  at `end` and at the disarm" and logs them after the disarm. (a) is made in
  `apple_ds_sleep_step_start` and (b) inside `apple_ds_enter` (the Rust half; `d7a_...`,
  `d7b_...`), and the log is the C half's. Not stated: whether "at (a)" may be the C half's read
  just before or after `apple_ds_sleep_step_start` (the same instant within a call) and, for (b),
  how the value reaches the C half (the interface has no accessor; one would be, for example,
  `u64 apple_ds_count_at_commit_step(void)`, 0 when the step was not reached). The host cannot see
  `CNTVCT_EL0` reads (not trapped in user space here); no test; reviewer item 37.
