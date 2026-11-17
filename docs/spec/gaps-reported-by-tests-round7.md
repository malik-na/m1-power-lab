# Gaps and contradictions in the spec, seventh round, as reported by the test author

Copied without change (below the line) from section 7 of the test suite's notes (`TESTS.md` at
commit c718bb7 of the driver repository), written against the spec at b794596. The test author
read only the spec. Each item is a question to the spec, to be answered from observations.

Three decisions were asked of Naeem by the test author. The orchestrator applied these defaults
(reported to Naeem, who may change them). They are decisions about Linux, not observations of
macOS, and belong in the spec beside D1, marked as decisions:

- **D2 (to W3).** The wake leaves the coprocessors the entry stopped (`dcp`, `dcpext`, and any
  other it stopped by R5a) as they are: it does not restart or boot them. Bringing a device's
  coprocessor back after a sleep is left to that device's own Linux driver. (D1 still puts the
  power domains back.)
- **D3 (to W1).** For `dcp`, `dcpext`, `gfx-asc` and `ans` the rule decided earlier for `sio` and
  `pmp` holds: found running, the driver does what macOS does, its messages included; found
  stopped, it sends nothing; silent, a bounded wait and then the register stop. A coprocessor
  whose power domain is found off is not touched at all.
- **D4 (to W4).** The driver is held to all seven first-port domains being requested off at the
  commit, as R54 has it, although that rests on the hypervisor's artefacts A2/A3; D1 puts them
  back at the wake.

A new Linux reading bears on W1: run ds15 in
`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` (the coprocessors' state words read
under Linux just before the driver's entry).

---

### Found in the seventh round (W1-W14), most important first

W1. **R7 and R5a make a coprocessor's stop the precondition of turning its domain off, and
   nothing was read of these coprocessors under Linux.** Linux leaves DISP0_CPU0 and
   DISPEXT_CPU0 on (L1); whether `dcp` and `dcpext` run then, what their +`0x44`, +`0x48`,
   +`0x8110`, +`0x8114` read, which endpoints are started, the spec says was not read (L11, open
   question 42). macOS stops endpoints `0x20`-`0x2c`, which it started itself; what `dcp` answers
   to an endpoint stop for an endpoint that is not started, or to "AP power `0x201`" while
   Linux's own display driver is suspended, is in no capture. `dcp`'s E1 stop follows
   endpoint-`0x37`/`0x02` traffic whose payloads are not in the log, and "what a coprocessor
   does if step 1 is skipped, or if it is stopped by step 2 alone, is not observed" (E2a). The
   tests hold the driver to macOS's exchange where the coprocessor runs and answers, and apply
   the fourth round's decision where it does not (found stopped: nothing sent; silent: the
   exchange as far as it gets, a bounded wait, the register stop). The default machine has
   `dcp` and `dcpext` running and answering as under macOS: that default is no reading.
   *Settles it:* the four words of each of `dcp`, `dcpext`, `gfx-asc`, `ans` read under Linux at
   the driver's entry; and one run of the stop under Linux with every reply logged.
W2. **What a domain word that reports state 4 with bit 28 set does when it is turned off by
   macOS's forms is not observed, and the machine that ds14 met is exactly that.** DISP0_CPU0
   reads `0x1404024f` under Linux. macOS only ever turned the word off from state `0xf`, which
   it read right after `dcp`'s stop "with no write by macOS to the word" (E2a); the same word
   reads state `0xf` in five awake snapshots with `dcp` running, so the stop is not shown to be
   the cause. The simulated machine assumes (a) the word reads state `0xf` once its coprocessor
   is stopped, and (b) form 2's first write (bit 28 cleared, the request kept) brings it to state
   `0xf` also from state 4, on the strength of one word: SIO_CPU, written `0x0400024f` from
   `0x1400024f` in R23 and holding `0x0f0002ff` at the commit, at an unknown moment. If neither
   holds on the machine, the second write leaves a word that still reports a state, and R56 says
   only that a wait "is not observed": the tests then neither require nor forbid one, and a
   driver that waits may not return. L13 does not say what the sixth round's driver wrote: that
   it left bit 28 set is read off the value afterwards (`0x14040240`), and the machine's answer
   to that is built on it. *Settles it:* open question 43's readings; the value the driver
   wrote in ds14; and a run of form 2 on DISP0_CPU0 under Linux reading the word after each
   write, with and without `dcp` stopped first.
W3. **D1 puts the domains back and says nothing of the coprocessors the entry stopped. A
   decision is needed.** After the wake calls DISP0_CPU0 and DISPEXT_CPU0 are on again and `dcp`
   and `dcpext` are stopped (+`0x44` = 0, bit 0 of +`0x8114` clear): a state Linux did not leave,
   and one the spec says is not observed ("a display domain turned on and left on with its
   coprocessor not started", 4.3). R5a gives the register side of a restart (+`0x8114` =
   `0x20001`, +`0x44` read 0, written `0x10`), which in macOS is followed by the coprocessor's
   boot exchange and thirteen endpoint starts, its own driver's work (E2, W4). The tests require
   the wake to write nothing to these coprocessors; a start is a violation on the simulated
   machine, which has no boot for them. *Needs the owner's word:* leave them stopped for
   Linux's display driver to find, restart them by the two register writes, or boot them; the
   last needs the boot exchange in the spec as a sequence.
W4. **R54's off for the first port's seven words rests on artefacts.** macOS requested
   ATC0_COMMON, ATC0_USB_AON, ATC0_USB off at boot because the hypervisor had taken the port's
   devices out of its device tree (A2), and ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB are
   0 "on a machine where macOS had no driver for the first port"; R54 itself says their state
   with the port driven by macOS is not observed. The driver is held to all seven off at the
   commit and to putting them back (D1). Under Linux they are on, and the Thunderbolt link the
   machine is driven over is behind them. What the three guarded words read once macOS's
   writes reach the hardware, and what the chip comes back with for them after a sleep without
   the hypervisor, are in no capture (macOS was given composed values; `0x23ff`, `0x3ff` after the
   wake are the hypervisor's): the machine takes the second port's values and section 10's.
   *Settles it:* the spec's own open question 41 (a capture without A2).
W5. **R56's forms leave open what the driver meets outside macOS's values.** (a) RMX's second
   write is given as the literal `0x300` where the rule gives `0x0f0003f0`; the word read
   `0x0f0003ff` each time, so "bits 4-7 and 24-27 cleared too" and "the constant `0x300`" cannot
   be told apart; under Linux RMX reads `0x1f0000ff` and after its first write, on the machine,
   `0x0f0000ff`. The tests require `0x300`. (b) The nine domains with "no observed turn-off"
   (ATC1_COMMON, ATC0_PCIE, ..., MSG) are on under Linux and off in R54: the tests hold them to
   form 1, which is what R56's general statement gives for a word with bit 28 clear. (c) Form 3
   is "wake only"; the tests use it before the sleep for the twelve words Linux has at the
   request 4, the one form the spec has for such a word. (d) A word with bit 28 set and the
   request 4, or one that does not read bits 24-27 `0xf` after form 2's first write, is in no
   capture and on no test machine.
W6. **The display's address translators are in R5a and not in the tests.** `dart-disp0`
   `0x2313040fc` is written `0x7ffe`, `0x7fee`, `0x7fee` before `dcp`'s messages and `dart-dcp`
   `0x23130c0fc` `0x7ffe` twice after its stop, in E1 only; `dcp`'s second stop in E2 has neither.
   The values come without the reads before them (a rule on what the word held, or constants?),
   1.9 names no domain for the two blocks, and what they hold under Linux is not read. Not
   required. *Settles it:* the reads around those writes, the blocks' domain, and whether the
   E2 stop omits them because they were already written.
W7. **Small things about R5a's exchange.** "An endpoint stop to each of endpoints `0x20` to
   `0x2c` in turn": the order is not compared. The answer `0x0087000000000000` is taken to
   come on the endpoint the stop went to. "IOP_POWER_ACK `0x201`" is taken to be
   `0x0070000000000201`, the word `sio` and `pmp` answer with. E2a gives the value of +`0x8114`
   "read" as `0x2ff00`, `0x27700`, ...: those end in 00 and are the values written (the read
   with bit 0 cleared). The widths of these coprocessors' words are not in the spec's text
   (its `widths.tsv` is not the test author's to open): not held.
W8. **Under D1 the wake writes the request 4 over the request 0**, which R57 says no capture
   shows; the form stays free and the machine reports 4. The sixth round's Q6 (a)-(e) stand
   under D1 as they were: where in the wake, the bits above the request, R40 resting on one
   domain. New with 4.3: DISP0_CPU0 and DISPEXT_CPU0 are turned on at the wake with
   `0x0f040000` though they read `0x0f000300`; the tests hold the putting back to that.
W9. **Widths.** 1.8 names ten PCIe words seen with 16 and 32 bits and says which access is
   which for one (`0x690000004`). The others are not in the driver's part as the fixtures have
   it. The guarded words and the core start/stop words are 32 bits at boot and not recorded
   during the entry and the wake (open question 39): either width still passes for them.
   `0x690000004` is itself a word whose width differs between two writes, which R49's "the
   width of a word never changed between reads and writes" no longer covers.
W10. **The words that are no domain words and differ under Linux** (L2, now with addresses;
   appendix B has macOS's values): 70 words, among them `DCSn`+`0x7b0` = 3 on all eight DRAM
   controllers, 50 clock words, the NCO. "Never written by macOS in any log" but the five
   muxes and the audio path's two (open question 44). Not required, as in the sixth round (Q2,
   Q3): if one of them is what keeps the chip up (L7), the suite cannot say so.
W11. **No behaviour for a commit after which the chip stays up, or for a wake without a
   power-down** (open question 45; L7, L8; 6.4 lists the reads whose values come from the
   power-down). As in the sixth round (Q7): every simulated chip goes down.
W12. **Two rules the spec says are not observed**: which bits end the poll of `0x23b718004`
   (open question 46; the tests require the last read to be `0x2f`), and which reading tells
   macOS that a wake was the alarm's (open question 47; the writes of `0x23d0d9320`, `0x23d0d9360`
   are left open).
W13. **Blocks without a domain** (open question 48): the temperature sensors, pin controllers,
   watchdog, SPMI controllers, NCO, R20's three blocks, `dart-apcie0`, `dart-pmp`, the display's
   translators. Never closed on the simulated machine.
W14. **The machine's choices that are no observation**, in one place: a coprocessor's stop
   makes its domain word read state `0xf` (W2); a word asked for 0 with bit 28 set keeps its
   state whatever state that is (L13 has state 4 only); GFX and APCIE_ST "found on" take
   macOS's awake values; the first port's values (W4); `dcp` and `dcpext` answer under Linux as
   under macOS (W1).

**Sixth-round gaps the revised spec answers:** Q1 (4.3, R56, R57, E2a, R5a; what remains: W1,
W2, W5, W6), Q4 (R54 by macOS's own requests; what remains: W4), Q5 (appendix B), Q6 (recorded
as D1; W3, W8), Q8 and Q9 (stated as not observed: W12), Q10 (R31), Q11 (R5: one read, one
value), Q12 (1.9: parents, virtual domains, sizes; W13), Q13 (bit 11 only while a turn-on is
awaited), Q14 (the 13 words are on awake), Q15 (L9, R12, L12, bits 8 and 9 per domain), and the
second round's S6 (the 16-bit write). Still open as they were: Q2, Q3 (W10), Q7 (W11).

