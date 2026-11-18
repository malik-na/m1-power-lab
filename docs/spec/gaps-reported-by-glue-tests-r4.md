# Spec gaps reported by the glue tests, round 4: the `pmp` client (spec round 15, lab `44db922`)

From the test author of glue round 4 (tests workspace `~/Work/deepsleep-glue-tests-r4`, branch
`glue-tests-r4`, commit `0cfa104`, `TESTS.md` section "Gaps and choices"). Written from the spec
(1.7h, R71-R75, L29, L30, 8.2 C18, D9-D11, and R4, R5, R5a, R5w, R6, R6w, R55, R70, D3, D5 where
C18 refers to them) only. The `pmp` client does not exist yet; the tests define its interface
(`interface/pmp_client.rs.iface`: a host-testable core reaching the machine through a trait
`PmpHw` of 32-bit reads and writes, one 8-bit read, mailbox `send` / bounded `recv`, `delay_us`,
`alloc_buffer`, `translator_ttbr`). Each item names the spec text and what the tests do until the
spec stage answers. G4, G13, G18 and G19 bear most on what the client does.

- **G1. Boot with a domain not on.** C18 (b) and D10 (a): the boot runs "once PMP, PMS_SRAM and
  PMS are on", "each read with state `0xf` and bit 28 set". Not stated: what the client does when
  its probe finds one of them not so (L29: PMS_SRAM `0x0f000300` under the stock kernel). Tests:
  nothing to `pmp`, no domain write, an error.
- **G2. SRAM writes at boot above `0x23b540000`.** R71 (b): "no other SRAM write below
  `0x23b540000`"; 1.7h: `0x23b540000` on is logged in full in no boot. Tests: no SRAM write at boot
  but the block's.
- **G3. R71 (c)'s first +`0xfc` = 0: once or twice.** R71 (c) lists "streams off (+`0xfc` = 0)"
  once; 1.7h item 3 shows W +`0xfc` = 0, R +`0x80`-`0x8c`, W +`0xfc` = 0. Tests: a repeat of the same
  write in a row counts as one.
- **G4. The start-up's order with the kernel RTKit library allowed.** R72 gives macOS's order
  (STARTEP 1, 2, 3, then 4, sent before the first EPMAP reply); D11 (c) lets the client use "the
  kernel's RTKit library ... where its words are those of L30's start" (SET_IOP_POWER `0x220`
  before HELLO_REPLY; STARTEP 1-4 after the EPMAP words), and L30 does not give where its buffer
  replies fall. Tests hold only what both share: HELLO_REPLY first (SET_IOP_POWER `0x220` alone
  may precede it), each EPMAP reply after its word, STARTEP 1-4 ascending after the first EPMAP
  word, each buffer reply after its request, AP power `0x20` after `pmp`'s IOP power `0x20`,
  STARTEP `0x20` after the AP echo. Settles it: whether macOS's order is required, and which of
  L30's words beside SET_IOP_POWER `0x220` are allowed.
- **G5. The IOVA fields and the buffers' sizes.** D11 (c): "buffer sizes as macOS's replies (4,
  `0x10`, 1), IOVAs the client's"; D11 (a): the opening's IOVA "an address the client has mapped".
  Not stated: the IOVA field's bits (tests: 0-43 in a buffer reply, 0-31 in the opening, from
  macOS's and L30's words), the size field's unit (bytes per unit; the tests do not hold the bytes
  allocated), the opening's buffer size, and whether the four buffers may share memory (tests:
  distinct).
- **G6. "At once" and "not waited for" as time.** D10 (a): the 0x55 word "is sent at once" after
  the opening; D11 (a): code-`0xe` words "are not answered". Tests: less than 10 ms of the client's
  time from the opening's last answer to the 0x55 word, from `…550001` to `0x0020800000630000`,
  from `…550000` to AP power `0x201`, and across the wake's five words.
- **G7. Buffer requests after the boot.** C18 (b): "While running: ... buffer requests answered".
  Which buffer (the boot's again, a new one) and of what size is not stated. Not tested.
- **G8. Control-page accesses beyond R71, R5 and R5w.** The spec lists R71 (d), (e) at boot, R5's
  five at the entry and R5w's four at the wake. Tests allow exactly those on `pmp`'s control page
  (for instance no read of +`0x48` at boot, no check of +`0x44` before the entry's words).
- **G9. The two reads before each translator +`0xfc` write.** R5a: each write "after a read of
  +`0x100`+4s and of +`0xfc`"; 1.7h (R73): +`0xfc` then +`0x100` for s = 0, +`0x13c` then +`0xfc` for
  s = 15. Tests: both reads since the previous write, either order; +`0x40`, +`0x100c` reads
  allowed, not required.
- **G10. Other accesses in the entry part.** C18 (d) lists the steps; tests allow before R5's stop
  only reads of PMP, PMS_SRAM, PMS, and nothing interleaved with R6's 49,152 reads.
- **G11. Both domains off at the wake.** C18 (f): "if PMP or PMS_SRAM does not read state `0xf`
  with bit 28, turn it on as R74's forms". Not stated: the order when both are off. Tests: W1-2's
  (PMP first).
- **G12. After a boot whose wait ran out.** D11 (d): "the client stops `pmp` by R5's register stop
  and leaves it stopped (Linux then runs as without C18, L29)". Tests: the later entry and wake
  parts make no call at all.
- **G13. After an entry wait that ran out.** D11 (d): "at the entry it goes on to R5's register
  stop". Not stated: whether the translator's two +`0xfc` writes and R6 still follow the stop, and
  what the wake part does after such an entry (R6w and R55 need R6's words and a stopped `pmp`).
  Tests hold the stop, no word after the wait, +`0x44` 0, an error; nothing about the rest.
- **G14. After a wake wait that ran out.** D11 (d): "at the wake it leaves `pmp` as it is and
  reports". Tests: no write and no word after the wait; reads allowed. Not stated: what the next
  entry part does with a `pmp` restarted without the five words (stop it as at a normal entry, or
  treat it as not running).
- **G15. PMS_SRAM that never reports state `0xf` at the wake** (R74: "read until state `0xf`").
  Not stated: what follows the bound (go on to R6w, or report and leave `pmp` stopped). Tests: the
  wait ends.
- **G16. No buffer to be had at boot.** Not in the spec. Tests: an error, no 0x55 word, `pmp` not
  left running.
- **G17. "No access with the switch off" (C18 (g)).** Tests: no call of any kind to the client's
  machine interface (no wait, no buffer, no translator value either).
- **G18. The switch per step.** C18 (g) and D5: "no access with the switch off". The C half reads
  `cand` at each entry (round 2). Not stated: a switch on at boot and off at an entry (tests: that
  entry and the wake after it do nothing), on at an entry and off at the wake after it (tests:
  that wake does nothing, `pmp` stays stopped), off at boot and on later (tests: the client never
  acts, `pmp` was never started).
- **G19. The bounds of waits other than for `0x000200000023b549`.** D11 (d): "no shorter than ten
  times the longest gap observed for that word in the captures"; the spec gives that gap only for
  `0x000200000023b549` (0.59 s, det34b). Not given: the gaps for HELLO, the EPMAP words, the IOP
  power `0x20`, the AP echoes, `0x0`, the two answers at boot, `0x0020900000630000`, AP `0x201`'s
  echo and `0x0070000000000201`. Tests: 5.89 s for `0x000200000023b549`; 1 ms for the entry's
  three answers in one test; 100 us elsewhere. (Review, amended: the fill had 300 ms for those
  three, which could fail a spec-correct client: 1.7h bounds their gaps by 17 ms
  (`0x0020800000630000` to `…550000`, T-0.816 to T-0.799) and 2 ms (R4 to R6's start, T-0.432 to
  T-0.43), so a bound of ten times that meets D11 (d) and need not wait 300 ms. Asked: the gaps
  for these words, so that a test can hold the floor itself.)
- **G20. SET_IOP_POWER `0x220`'s word.** L30 names it; its 64-bit word is not in the spec. Tests take
  the reference's layout (section 0: type 6 in bits 52-59): `0x0060000000000220`.
- **G21. The kernel library's own waits.** D11 (d): "every wait of the client is bounded". If the
  kernel RTKit library is used (D11 (c)), its waits for HELLO, the EPMAP words and the power
  states are its own. Tests: each is one of the client's waits, ending in R5's stop at boot.
- **G22. R5's register stop with no R4 before it.** D11 (d) at boot: "stops `pmp` by R5's register
  stop"; R5 is stated after R4's exchange, which a boot that timed out has not sent. Tests: R5's
  five accesses only, no R4 words.
- **G23. The kernel RTKit library and a host-testable client.** For the words to be tested, the
  interface has the client's core send every RTKit word itself through the mailbox; so the kernel
  library is not used for `pmp`. D11 (c) permits the library and does not require it; if the spec
  stage wants the library's words (L30) instead of macOS's (R72), G4 is the place.
- **G24. Messages outside the client's waits.** C18 (b): LOG and type-8 words echoed, buffer
  requests answered "while running". Not stated: after which point (tests: from the boot's start
  until the entry's stop, and again after a wake that got through).

Also, outside the tests (the C half's reviewer list in `TESTS.md`): C18 (a)'s device tree has the
translator's tunables and `iommus = <&pmp_dart 0>` in the reference tree (L29); if Linux's own
translator driver binds `dart-pmp`, it writes +`0xfc`, +`0x200`, +`0x100`, +`0x13c` itself, beside
the client's R71 (c) and R55 writes. Which of the two owns the translator is not stated.

## Fill (after the audit and the critic; tests commit `3acfeb1` in `~/Work/deepsleep-glue-tests-r4`)

Amended:
- **G5.** Tests now accept an IOVA anywhere inside a buffer the client mapped (D11 (a) "an address
  the client has mapped"), not only a buffer's start; the four IOVAs stay distinct.
- **G6.** "Not waited for" (code-`0xe` words, D11 (a); the wake's five words) is now held by
  structure: no receive with a timeout between those words and the next request, or the part's
  return. A delay is allowed, so macOS's own gaps pass (0.37 s before R4 at the entry, R73; 24 ms
  over the wake's five, 1.7h). "At once" for the 0x55 word at boot (D10 (a)) is still held as
  under 10 ms.
- **G7.** Buffer requests after the boot are now tested: one reply on the same endpoint, macOS's
  size field, an IOVA in a mapped buffer. Which buffer (the boot's again or a new one) is still
  not stated.
- **G24.** Tests: no action at all after the entry part has stopped `pmp` (before the wake), after
  a boot whose wait ran out, after a boot that found a domain off; an echo after a wake that got
  through (C18 (b) "While running", D3 "found stopped, it sends nothing").

New:
- **G25. LOG words during the wake's short handshake.** C18 (b) has LOG words echoed "while
  running"; R74 records none at the wake. Not stated: whether one arriving during the handshake
  is echoed. Tests hold the echo at boot and at the entry, not at the wake.
- **G26. D9 (b) and the logic as it is.** D9 (b) says the logic, with `pmp` found stopped at entry
  start (+`0x44` 0, +`0x48` `0x2e`, PMP `0x1f0f03ff`, PMS_SRAM `0x1f0003ff`), makes no access to
  `pmp`'s mailbox page, its control page beyond C8's reads, its SRAM except the twelve words, or its
  translator, and that section 8 "already gives" this and "does not change". The round's brief says
  the logic gets no new behaviour. Against the logic at kernel `HEAD` (`d441389d4`), D9 (b)'s test
  fails for `cand` 0, `0x40000` and `0x40100`:
  - at the entry: R5's register stop on `pmp` (+`0x8114` R/W, +`0x44` W 0), translator +`0xfc` W 0
    twice, and R6's 49,152 reads;
  - at the wake: R6w, R55 and R5w;
  - 98,271 forbidden accesses with `0x40000`.

  Both cannot hold. Either the logic changes (through its own cycle), or D9 (b) is restated
  (for example, the client leaves `pmp` in a state that the logic's C8/D3 treats as "domain off").
  This needs a decision from Naeem and the spec stage.
- **G27. Values the tests use that no capture shows.** The tests use these to hold "echoed",
  "answered before the next word", and R5's and R5a's rules as rules, not constants:
  - LOG and type-8 words with payloads;
  - EPMAP words at the wake with other bitmaps (`0x0080000000000017`, `0x0088000100000003`);
  - unrelated messages arriving ahead of an awaited answer (a LOG word, `0x00c0000000000000`,
    `0x0020b00000550023`);
  - +`0x8114` reading `sio`'s `0x24401` / `0x28801` for `pmp`;
  - +`0xfc` reading `0x8001` at the entry.

  Whether `pmp` ever sends these or reads so is not in the captures.
