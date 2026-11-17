# Gaps and contradictions in the spec, as reported by the test authors

Copied without change from section 7 of the test suite's notes (`TESTS.md` at commit bd9e01c of the driver repository). The test authors read only the spec. Each item is a question to the spec, to be answered from observations.

## 7. Gaps and contradictions found in the spec

### Found in the fifth round (V1-V12), most important first

V1. **The spec cannot say what the wake does with a sub-block that was off before the sleep.**
   In every capture all four words read 1 before the sleep and are written 1 at the wake:
   "written 1" and "written back" are the same thing there. The decision (put back what was
   found) and its reasons are in section 11. R22a also does not say what the sub-blocks are, so
   nothing tells whether a deep sleep with them off, as Linux has them, is a state macOS's
   sequence works from at all.
V2. **Most of what the driver writes is a value macOS computed from its own machine's state,
   and the spec gives the value, not the rule.** In capture D (`replay-pre-d.tsv`,
   `replay-post-d.tsv`) 177 of the writes before the sleep and 782 of those after the wake
   follow a read of the same word and differ from it by bits set or cleared; 318 more after
   the wake differ from it otherwise. Where the spec words a rule the suite now follows it (R21, R23,
   R5; R36w, R19w, R8w, R6w as "written back"). Where it gives only values the suite still
   requires the values (list in section 11): for those words the driver writes macOS's state
   onto a machine that may hold another, and neither the spec nor a reading says otherwise.
V3. **R36w's rule is not in the spec.** E6-1 says of the 991 words "913 carry the value last
   read here, 18 the value last written, 38 another value" (the counts do not add up: gap 11).
   The extracts give, in D, F and G alike: 913 as read; `0x23b104100`+4k = what `0x23b104180`+4k
   read; `0x23b104180`+4k = that inverted; `0x23b105028`+`0x80`k = what it read, inverted;
   `0x23b105024`+`0x80`k = `0x80000001`. Tested so. What the words are (which reads "masked",
   which write masks) is inferred from this alone.
V4. **What a sub-block's status word reads while the sub-block is on was never captured**
   (macOS reads it only after writing 0), nor what a write of 0 does to a sub-block that is
   off (the reading read the words; nothing wrote them). The simulated machine answers the
   first with the first value read after the write and the second with "nothing changes".
V5. **The status bytes above the low one are not explained.** `0x494900`, `0x515100` under
   macOS; `0x7f7f00`, `0x6c6c00`, `0x616100` under Linux with the sub-blocks off; the second
   and third byte are equal in all of them (R22a notes it for macOS's). The second sub-block
   reads 0 in both states. The low byte reads 2 while a sub-block stops; no other value of it
   was seen, and "low byte 0" is all the suite waits for.
V6. **R22 still names `0x494900`** ("polled until it reads `0x494900`") next to R22a's "until
   its low byte is 0". The suite follows R22a.
V7. **What the poll of `0x23b718004` at the wake (W1-2a) ends on is not stated** (the captures
   read `0x1f` 9 to 239 times and then `0x2f`). The suite does not require a value there;
   the simulated machine shows those two.
V8. **R16's wait is stated as a value** ("`0x200001c04` polled until it reads 0") and is tested
   as stated. The captures show it falling from `0x41e0`; whether a machine in another state
   starts elsewhere, or ends elsewhere, is not known. The entry passed it on the machine.
V9. **What SIO_CPU's control word reads once the driver has turned the domain on under Linux is
   not known** (gap T7). R23 is tested as "bit 28 cleared in what it reads"; the machine's
   variation (bits 9 and 26) is the suite's.
V10. **That the six words of R21 keep their value through the sleep** is in the extracts (each
   reads after the wake what was last written before it, D, F, G) and not in the spec's text.
   The suite accepts either reading of "set again at the wake": the value read before the
   sleep, or the value read at the wake with bit 63 set.
V11. **The words the entry writes 0 are "written back" only by R19w's sentence.** The fixtures
   had the nine as fixed values (`0xf`, 1, `0x1000000015`, `0xa000000000000000`: the same in
   six captures of one machine). They are now what the entry found; that the driver must read
   each before it writes 0 (macOS does) follows.
V12. **R22a's source** is given as `db/cap*.db`, which the test author does not open; the reads
   are in `phases-pre-<cap>.tsv` of all six captures and agree with R22a (6 to 9, 1, 2 or 3,
   1 or 2 reads).

### Found in the fourth round (F1-F10), most important first

F1. **The spec has no coprocessor in any state but running and answering when the sleep
   actions begin.** E3, R4 and R5 are six captures of macOS, whose own drivers booted `sio` and
   `pmp`. What macOS does with one that is stopped, or silent, was never captured; nothing in
   the spec says a kernel sleep path can meet one. Everything this round requires before the
   sleep is the owner's decision (section 10), not an observation.
F2. **Nothing in the spec says what the wake does with a coprocessor that did not run before
   the sleep.** W3 and R32 show `pmp` and `sio` started and booted, always after an entry that
   found them running. The decision (leave it stopped) and its reasons are in section 10. Its
   consequences are not observed either: whether the rest of the `pmp` wake action (the block
   written back, the translator's ten writes with `0x23b3000fc` = 1) is right for a `pmp` that
   stays stopped, and that a caller whose own drivers expect `sio` and `pmp` after the wake
   must start them itself.
F3. **What a stopped or a silent coprocessor's mailbox reads was not read on the machine.** The
   readings give +`0x44` only. The simulated machine reads +`0x8114` as `0x20001` (nothing
   waiting, counts 0, bit 0 set) and +`0x8110` as "taken" after a message nobody takes. If bit
   0 of +`0x8114` is already clear on the machine, the write the tests require (what was read,
   bit 0 cleared) changes nothing; if +`0x8114` or +`0x8110` read otherwise than a wait
   expects, the tests do not see it.
F4. **A zero `WakeInputs` value.** The spec does not say what `0x235004200`, `0x235004210`,
   `0x23b300200` are or where macOS takes their values from (gap S2), so it gives no ground to
   treat 0 specially: the tests require the caller's value written as given, 0 included.
   Whether a translator may be switched on (W1-8: `0x2350040fc` = 3; W3: `0x23b3000fc` = 1)
   with 0 in these words is not known; under macOS they never held 0 in a capture. The readings
   pair the zeros with coprocessors that are not started at the wake, which is the only reason
   to think it harmless.
F5. **The machine has not yet got past `sio`.** The readings end at the first message to `sio`.
   Everything after it on a machine in that state is untried: `0x23b3000fc` written with `pmp`
   stopped by someone else, the 49,152 reads of the block of a `pmp` that was not stopped by
   this entry (the earlier reading: with `pmp` running a read there resets the machine; with
   `pmp` stopped it is how macOS reads it), the translators' steps of R10 on translators Linux
   had set up.
F6. **Whether +`0x44` = 0 stops a coprocessor that does not answer** as it stops one that has
   acknowledged "coprocessor power `0x201`", and why `sio` reads `0x10` there at all after its
   own driver failed to start it, is not known. Nor what becomes of the message left in its
   mailbox.
F7. **How long a reply may take is not in the spec.** Every time is an upper bound (A8) and
   under the hypervisor. The driver's bound is a number of reads (`Hw` has no clock); the
   tests only fix that 250 reads without a reply are not yet "no answer" and that 2^28 are.
F8. **`Co::Silent(1)`** (the first message echoed, the second not acknowledged) is no reading.
   It is the owner's rule applied one message later, and what such a coprocessor has done with
   "AP power `0x201`" is unknown.
F9. **+`0x48`**, which macOS reads (`0x2e`) before +`0x44` in both sleep actions, is answered
   with the capture's value whatever the coprocessor's state; the spec does not say what it is.
F10. **Section 1.9 and T1 stand as written**: R50 turns the domains of `sio` on, and a domain
   that is on is still not a coprocessor that runs. T1 is no longer a gap of the tests (the
   three states are tested); it is still one of the spec.

### Found in the second round (S1-S13), most important first

S1. **W2 leaves out a write.** In all six captures core 0 writes `0xc5acce55` to
   `0x21N.30fb0` (`0x211330fb0` for core 7 ... `0x211030fb0` for core 4) once per core it
   starts, in start order, between the last active action and the first wake action
   (`phases-post-<cap>.tsv`). The spec's W2 has only the start words from the hypervisor's
   log. Tested as the extracts show it. That it comes before that core's start words rests on
   the times of D, E and F (0.5 ms before; A and B have no times for start words, G's event
   file is not among the extracts). What the word is, is not known.
S2. **Three address-translator words are written at the wake with a value from nowhere.**
   `0x235004200`, `0x235004210` (W1-8) and `0x23b300200` (the `pmp` wake action) differ in
   every capture (`0x80822760`, `0x80821e18`, ...) and are not read in the sleep path. The spec
   says "30 writes" for W1-8 and does not mention the ten translator writes of the `pmp` wake
   action at all. The tests require the writes and take the three values from the caller
   (`WakeInputs`). Whether they point at something macOS owns (so that another system must put
   its own value there) cannot be told from the captures.
S3. **Three wake-side actions write back configuration that is read nowhere before the sleep**:
   the pin controller's 474 writes (W1-9), PCIe's 110 (W1-10), the audio switch's 106 (W3). They
   are identical in six captures, all of the same macOS on the same machine at the login
   window, so the captures cannot tell a fixed table from "whatever macOS's drivers had
   configured". Tested as observed, value for value. On a system that configures these devices
   otherwise the same values may be wrong; the pre-sleep contents of these words are in no
   extract, so a driver that saved them instead cannot be run on the simulated machine (it
   would be an unknown read).
S4. **macOS takes every reply by interrupt; what a polling driver must wait on is inferred.**
   The spec describes a mailbox as "writes +0x8800/+0x8808, reads +0x8830/+0x8838". That
   `+0x8114` tells whether a message waits (`0x10....` against `0x2....`) is read off the
   values in the extracts, with no statement of what the bits mean; `+0x8110` after a send
   shows both forms and is not modelled. Likewise for the power chip in E3 and W3: the captures
   show status words `+0x320`..`+0x380` read and `+0x378` written 1 in the interrupt handler.
S5. **R9's place.** The spec is "not certain" which driver sends the `0x9f01` commands (three
   cores active). In all six captures they fall in the watchdog's sleep action, after its two
   words and before the SPMI controllers' action. The tests require only what could matter: the
   write happens before the stop bits and before `0x23d0d9338` is written 1 (after it the
   captures frame every command with writes of that word, E6-3; before it they do not), and at
   the wake after that word is written back. The order of R9 against the watchdog's two words
   is not required.
S6. **One access width is not decidable.** The PCIe quiesce action's write of `0x690000004`
   (E5-3): the spec's `widths.tsv` has that word written with 16 and with 32 bits, six times
   each; the kernel path writes it once, from a pc that accesses nothing else, and the other
   write lies outside the phase extracts. The tests give it no width; the interface has no
   16-bit access. (No other access in scope is 8 or 16 bits.)
S7. **R12 / E5-1 misstate the sensor writes.** Fourteen sensors have their control word at
   +`0x8`, three (`0x23b2c4000`, `0x23b2c8000`, `0x23b2cc000`) at +`0x10`; the text gives
   +`0x10` for all. "Bit 25 set instead" is: the value read back after the first write (on most
   sensors bit 16 has dropped: `0x13c00` -> `0x3c00`), with bit 25. The two MTR actions write
   the same word. Tested as the extracts show it.
S8. **R6w's count is misleading.** "49,143 of the 49,154 words first written in this action"
   counts by first write; in all six captures every one of the 49,152 words of the block is
   written back with the value read in E3 (checked by the fixture script). The write-back is
   the first thing in the `pmp` wake action, before its translator's writes.
S9. **Free orders.** The three SPMI controllers (at the sleep and at the wake), the two address
   translators of R10 and the temperature sensors come in different orders in different
   captures; any order passes.
S10. **The wake status read's place in W3** (between `pmp` and `sio` in all six) is not
   required: it is a read, on another core in some captures.
S11. **Alarm wakes write one more SPMI word.** In A and G (both hypervisor alarms) the power
   chip's wake action also writes `0x23d0d9320` = 4. Left open (the power chip's bus words are
   judged by what reaches the power chip).
S12. **What is not in any action.** Between the last active action and the core starts the
   extracts show four pin-controller writes (`0x23c1001a8`, `0x23c10080c`, `0x23c1002dc`,
   `0x23c100814`) and an SPMI status write: interrupt handling, not required. The error
   handler's `0x200021004` write in E3 likewise.
S13. **The scratch bytes after the wake** (`0x9f08`-`0x9f0b` = `ff ff 47 50` in D) are the
   hypervisor's (A10); the machine answers a read with them all the same.

### Found in the first round, most important first

1. **The guarded words (A3) hide what macOS writes on a bare machine.** Before the sleep: SIO and
   SIO_BUSIF (R23a; macOS was shown `0x1f0000ff` while the hardware held `0x1400024f`). After
   the wake: UART_P, UART0, SIO, SIO_BUSIF, which macOS wrote from composed values. The tests
   neither require nor forbid writes to these words. Likewise the devices removed from the
   device tree (A2, the first USB-C port) and ATC0_COMMON, ATC0_USB, ATC0_USB_AON: nothing in
   the captures says what is done with them, and a machine without the hypervisor has them.
2. **Access width (1.8, R49) is given for the words macOS's access log shows, and only for
   them.** Where the tests therefore do not hold the driver to a width:
   - *The core start/stop words* `0x23b754000`-`0x23b75400c` (R11, R32) and *the guarded words*
     (gap 1): their accesses are not in the access log (1.2 item 4, A3, A4), so `widths.tsv` has
     no line for them. R49's "32 bits unless listed" was not taken to cover words that have no
     line at all (every 32-bit word macOS accessed has one). Either width passes.
   - *Words only the snapshots know* (705 of the words the simulated machine holds): macOS never
     accessed them, a driver that reads one is held only to the earlier rule (section 4).
   - *Which access had which width* is not in `widths.tsv` for the words seen with two. Twelve of
     the thirteen at `0x23b549000` are in the driver's part (read in E5-8d, written in W1-2h). The
     fixture takes 64 bits for them: in every capture the power manager's accesses come from a
     pc whose other accesses are all 64-bit, and six of the twelve carry a value over 32 bits
     there; the 32-bit accesses are the `pmp` driver's (out of scope), which also accesses the
     upper halves `+4` as words of their own. The tests require 64 bits and forbid a 32-bit access
     of these twelve. (Second round: the 32-bit accesses are in scope now. The power manager's
     stay 64-bit; the sweep of R6 / R6w reads and writes the twelve, and their upper halves, as
     32 bits.)
   - *A direction macOS never used* (274 listed words never read, 327 never written): the tests
     apply the one width seen to both directions, on R49's statement that reads and writes of a
     word never differed.
   - *What the hardware does* with another width is `[UNKNOWN]`; the simulated machine records
     the access as a violation and otherwise behaves as if the width had been right.

   Section 1.8 against `widths.tsv`: the numbers "105,382 ... 852 ... 38 ... 1" count lines of
   the file (106,273), not address-and-direction pairs; of the 106,235 pairs 105,344 are only
   32-bit, 828 only 64-bit, 25 only 16-bit, and 38 have two widths (24 as 32 and 64, 13 as 16 and
   32, 1 as 8 and 32). The thirteenth word of the block at `0x23b549000`, `+0x400`, was read as
   8 and 32 bits, not 32 and 64, and as 8 bits in captures A and B only, which the sentences
   "the same two in every capture" and "the width of a word is the same in every capture it
   appears in" do not cover. Neither touches the driver's part: `+0x400` is not accessed in it.
3. **What powers the chip down is not established** (open question 14) and the wait instruction
   is not in any log. The interface leaves the wait to the caller; the simulated machine takes
   "the eighth core has written `CYC_OVRD_EL1` = `0x3000001`" as the power-down.
4. **R28 / W1-0 / W2 are incomplete about the cluster pair.** The text gives
   `0x210e49008`, `0x210e49000` to core 0 and "the first pair on its own block" to every other
   core. `phases-post-<d,e,f,g>.tsv` show core 7, the first core of the performance cluster to
   start, also writing `0x211e49008` = `0xff5fffffffffffff`, `0x211e49000` = 1. Tested as the
   extracts show it.
5. **The HID/EHID values are read-modify-writes over values the hypervisor had already set**
   (A7 runs before macOS; almost every value read equals the value written). What macOS would
   write on a chip that comes up without the hypervisor is not known. The tests check the final
   value and the order of first writes per register, not the repeats.
6. **The alarm** (open question 16): how macOS chooses the four bytes is unknown. They are an
   input of `enter`.
7. **How cores 1-7 are told to power down 89 ms after their stop bit**, with the interrupt
   controller already masked (open question 19), is not visible. `Hw::run_on` leaves it to the
   glue.
8. **The pre-sleep value of 28 of the 82 power-domain words written at the wake is in no
   extract** (the snapshots list 74 domain words). The simulated machine cannot answer a read of
   them before the sleep. R40 ("back to the state before the sleep") rests on one domain, FPWM1,
   in one capture.
9. **W1-4:** one written value (the write to `0x2000e1004`) differs between captures; the spec says
   "one written value differs from A and B" without the rule. Its value is not checked.
10. **No failure path.** What macOS does when a wait does not end, or when an entry is cancelled
    inside the kernel path (open question 25), was never captured. `Error::WaitTimedOut` exists
    for the implementer; no test produces it.
11. **Counts in the spec that the extracts contradict.** W1-1 lists `0x23b100010`, 896, 48 and 22
    words for 991 writes (sum 967); the extracts show 56 words at `0x23b104100`-`0x23b1041ec`,
    22 at `0x23b105024`.., and 16 at `0x23b106000`-`0x23b1060f0` (sum 991). E6-1 says of the 991
    words "913 ... 18 ... 38 another value" (sum 969); `saverestore-d.tsv` gives 913, 18, 60.
    The fixtures follow the extracts.
12. **R43:** cores 3 and 0 read `ACC_OVRD_EL1` as `0x1800101526076207` before writing it; the
    spec does not say why (shared within a cluster?). The simulated machine gives every core
    the earlier value.
13. **Where a wait starts.** The captures cannot tell whether `0x200001c04` begins to fall at the
    write of `0x200001c00` or at the release of the pulse after it; the simulated machine starts
    it at the last write before the first changed read (the release). The same holds for
    `0x200001c04` after the wake.
14. **The simulated contents before the sleep in scenarios D and F** are the idle snapshot taken
    well before the entry (about 238 s before T in D), brought up to date only for the domain words the entry wrote; scenario G
    uses the snapshot at the commit. Words that changed between idle and the entry without a
    logged write are stale in D and F.
15. **Core stop and start order** (4, 1, 5, 2, 3, 6, 7 and 7, 6, 3, 2, 5, 1, 4) are identical in
    all six captures and therefore required here, though nothing says they matter.

### Found in the third round (T1-T12), most important first

T1. **A domain that is on is not a coprocessor that runs.** E3 presupposes `sio` and `pmp`
   running: the driver tells each to power down through its mailbox and waits for the reply
   (R4). The spec shows a coprocessor being started only at the wake (W3: +`0x44` = `0x10`, the
   boot exchange; for `sio` the 30 translator writes of W1-8 before). If the caller had `sio`'s
   domains off, `sio` was not running, and nothing in the spec says what state it is in once
   its domains are turned on, nor what macOS would do then. The tests leave it as the capture:
   once `SIO_BUSIF`, `SIO`, `SIO_CPU` are on the simulated `sio` answers as in macOS. On the
   machine the reply of R4 may never come. (Fourth round: it did not come. Section 10; the
   default scenario still answers, `Scenario::found` gives the other states.)
T2. **Which block lies in which domain is not in the spec.** No table ties a device to a domain.
   The machine closes only the seven blocks of section 4 (names shared between block and domain,
   1.9's last item, 4.1). 1.9 says the temperature sensors lie "in several of these domains"
   without naming them. If the caller has the domain of an unplaced block off, the tests do
   not see it: gap T3 lists them.
T3. **Blocks the driver touches that could not be placed**, and so are never closed: the
   watchdog (`0x23d2b0000`, `0x23d2b8000`); the three SPMI controllers (`0x23d0d9000`,
   `0x23d0e1000`, `0x24a829000`) and the power chip behind the first; `pmp`'s address
   translator (`0x23b300000`) and the block of R6 (`0x23b52c000`-`0x23b55bffc`; 1.9's "the
   `pmp` block" may mean it); the temperature sensors; PCIe (`0x681000000`.., `0x690000000`) and
   its address translator (`0x681008000`); the pin controllers at `0x24a820000` and `0x23d1f0000`; the NCO,
   DWI, the audio switch (after the wake only); the power manager itself (`0x23b700000`,
   `0x23d280000`) and the cores' and clusters' blocks (`0x210000000`, `0x211000000`).
T4. **59 of the 137 words are not observed at E3 start**, among them domains whose names point
   at blocks the driver touches: `DWI`, `SOC_SPMI0`-`2`, `NUB_SPMI0`, `NUB_SPMI1`, `NUB_GPIO`,
   `NUB_AON`, `PMS_BUSIF`, `PCIE_REF`, `APCIE` (the table's parent of `APCIE_GP`, which is
   required). At the wake macOS turns `DWI`, `APCIE` and `PCIE_REF` on (from `0x244`) and by
   R40 that is the state before the sleep, but R40 is `[UNKNOWN]` and rests on one domain, and
   R50 does not list them. Not required; the machine does not know their state and neither
   closes their blocks nor checks them as parents.
T5. **What turning a domain on takes is known only as writes to its control word.** The rule of
   the three writes holds in all 573 turn-ons, but of the 19 domains the reading shows off
   under Linux the captures show only `AUDIO_P`, `PMS_SRAM` and `ANS2` brought on from the
   requested state 0 (at the wake), `SPI_P`, `UART_N`, `UART1`-`8` from `0x344` (request 4), and
   `GPIO`, `SIO_CPU` never from anything but on; `SIO_BUSIF`, `SIO`, `UART_P`, `UART0` are
   guarded (A3) and their writes are in no extract. Whether a domain that was really off needs
   more than its word (a clock, a reset, its device set up again) the captures cannot show: at
   the wake every device behind them is set up again by its own driver.
T6. **Parents.** The table names parents; the spec does not say what follows from that. Required
   here, parent's third write before the child's first, because E2 of every capture turns
   `RMX` on before `DISP0_FE` / `DISPEXT_FE` and those before `DISP0_CPU0` / `DISPEXT_CPU0`,
   and no capture shows a child requested on under a parent requested off. At the wake macOS
   writes `SPI_P`, `AUDIO_P`, `UART_N`, `UART1`-`8` before `SIO_CPU` (and, if the hypervisor's
   times are comparable, before the guarded `SIO_BUSIF`, `SIO`): there every one of them
   already reports on before it is written, so it is no counter-example, and no support either.
T7. **Bits of a control word other than the request.** Write 1 clears bits 8 and 9, write 3 sets
   bit 28; the spec gives neither a meaning (section 0 explains bits 0-7). After write 3 some
   words read with bits 24-27 and the report dropped (`RMX` `0x1000030f`), some keep them, some
   lose bit 28 (`I2C0` `0x2ff`): the machine answers with the capture's value at E3 start.
   Bits 10 and 11: the reading under Linux has `0xa00`; the captures show bit 11 once, in a
   read during a turn-on (`DISPEXT_FE` `0x2b4f`, capture F), never in a word before one. What
   macOS would write there is unknown: **bits 10 and 11 of the three writes are not compared.**
T8. **The words on with other bits** (`DCS0`-`7`, `PMP`, `SEP`, `APCIE_GP`: Linux `0x1f0002ff`,
   `0x1f0000ff`, `0x1f0020ff`; macOS `0x1000030f`, `0x1000230f`, `0x1400234f`). Decision:
   nothing is required of them. R50 states the requested state only; the other bits differ
   between macOS's own captures (`DCS1` `0x1f00030f` in F, `DCS6` `0x1f0003ff` in E, `APCIE_GP`
   `0x1f0023ff` in E), R46 says the six/two split of the DCS words is not fixed, and 4.1 reads
   `..3ff` against `..30f` as "coprocessor stopped" against idle: bits 4-7 and 24-27 are the
   hardware's report, not a state to establish. A write to such a word before the first sleep
   action is allowed as long as it keeps the request `0xf`.
T9. **The guarded words.** For `SIO`, `SIO_BUSIF`, `UART_P`, `UART0` the values of
   `ps-at-e3.tsv` are the hardware's under the hypervisor, and 1.9 says macOS's own request is
   not observed there. Decision: required on. macOS's own held writes request on
   (`0x0f0000ff` at E5-8j and at the wake, `0x100000ff` at boot and at the wake: section 3,
   W1-2), and R4 talks to `sio` in E3. `ATC0_COMMON` (`0x20ff` in the file): **not required**;
   macOS itself wrote `0x23f0`, off (the hypervisor had taken its devices out of the device
   tree, A2, and holds the port for its own link, R48). `FPWM1` (on in D, E, G, off in F):
   not required either way.
T10. **The wake still turns the display and second-port domains off.** W1-2c is tested as the
   capture has it (R30, R40): `DISP0_CPU0`, `DISPEXT_CPU0`, `GFX`, `MMX`, `RMX` `..3f0` and so
   on, because in the captures they were off before the sleep. R40 says macOS writes each
   domain back to the state it had before the sleep; on a machine where they were on before
   the sleep the driver's `leave_early` therefore does not do what macOS would. Left as it is
   (the brief for this round keeps those domains out of scope); whoever resumes the display
   after the wake finds its domains off.
T11. **The reading from the machine is partial here.** Which word held which of `0x200`,
   `0xf000200`, `0xa00`, `0xf000300`, `0xf002300` under Linux was not passed on with the brief;
   the assignment in `tests/sim/domains.rs` is the test author's (comment there). The expected
   writes are computed from what each word starts with, so another assignment changes no rule.
T12. **`ps_at_e3.py` reads this repository's `tests/fixtures/domain-words.tsv`** for the list of
   words (by absolute path): the spec's extract depends on a test fixture. The list is the
   table's own (137 control words), so nothing is wrong with the result.

