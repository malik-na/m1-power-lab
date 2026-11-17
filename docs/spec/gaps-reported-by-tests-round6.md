# Gaps and contradictions in the spec, sixth round, as reported by the test author

Copied without change from section 7 of the test suite's notes (`TESTS.md` at commit e0161ed of the driver repository), written against the spec at 88788ac. The test author read only the spec. Each item is a question to the spec, to be answered from observations. Q6 carries a decision by the orchestrator (the wake puts back the power-domain requests the entry changed); it is a decision about Linux, not an observation of macOS.

### Found in the sixth round (Q1-Q15), most important first

Q1. **The spec states the domains' state at the commit (R54) and no way to it from the state
   Linux leaves.** 14 words are requested on under Linux that macOS has at 0, 12 have the
   request 4 (4.2a). (a) *No rule for requesting a domain off.* The spec shows turn-offs as
   examples in at least four forms: one write `0x23f0` (DISP0_FE), `0x3f0` (buses, MCA, FPWM1);
   two writes `0x0f0400ff` then `0x0f0403f0` (DISP0_CPU0), `0x0f0020ff` then `0x0f0023f0` (GFX),
   `0xf` then `0x300` (RMX); what is read before, between and after is not stated, nor what
   decides the form. The tests compare no value: only that the last write requests 0, nothing
   requests the word on, core 0 writes 32 bits, and the domains below go first. (b) *macOS never
   turns one of these domains off without first shutting down what is behind it* (R1, R4, R7:
   the display coprocessors' and the graphics coprocessor's mailbox exchanges, "each after its
   coprocessor's R4 exchange"); E1 and E2 give those exchanges as counts of words ("167 / 177
   words written", "13 endpoints are started ... stopped"), not as sequences a test could hold
   a driver to, and DISP0_CPU0 reads `0x1404024f` under Linux, the value it has under macOS
   with its coprocessor running. Whether `dcp`, `dcpext`, the second port's devices run at the
   driver's entry under Linux was not read (L11 does not list them). The tests require the
   request 0 and nothing of the devices. (c) *The request 4* appears in no capture before the
   sleep; that a write of the request 0 is what takes such a word to macOS's state is taken
   from the wake only (W1-2c: `0x344` written `0x340`). *Settles it:* the turn-off of each of
   the 14 as a rule (value read, values written, reads awaited), the E1/E2 exchanges in full
   or a statement that the driver is not to make them, and these devices' state read under
   Linux at the driver's entry.
Q2. **Words that are no domain words differ under Linux (L2) and the spec shows no way to
   macOS's value.** `DCSn`+`0x7b0` reads 3 on all eight DRAM controllers (0 in every snapshot of
   macOS, which never accesses the word); six clock words at `0x23b0400d4`-`0x23b0400e8` read
   `0x8N100100` (macOS `0x100`); the rest of the 54 clock words of L1, the NCO's first word, three words
   at `0x23b058000`.., five always-on clock words. R51 states macOS's values as the state at
   the commit; R47 says macOS leaves the memory and DRAM controllers' words as they were. No
   capture shows a write that produces macOS's value, so the tests neither require the values
   nor allow a write of the 528 words of R47. If one of these is what keeps the chip up (L7)
   the suite cannot say so. Most of L2's clock words are given as counts ("18 words ...
   `0x86100100` / `0x87100100`"), without addresses. *Settles it:* for each word, who writes it
   under macOS and when (a capture of the boot, or of the audio and display drivers' own
   shutdown), or a reading of what changes when Linux writes macOS's value.
Q3. **R52: words that change between macOS awake and the commit with no logged write**, the
   same way in G and H: PMP to `0x1f0f03ff`, PMS_SRAM, ANS2, `0x23b71c0f0`, `0x23b720030`..,
   nine clock words, two always-on clock words. Under Linux before the entry they read
   otherwise (PMP `0x1f0000ff`, `0x23b720030` `0x01616161`, ...), and they were not read at
   Linux's commit (L11). If they are the hardware's answer to something macOS does that the
   driver does not, the tests cannot see it: nothing is required. *Settles it:* the spec's
   own open question 34, and the 858 words read at Linux's commit.
Q4. **R54 contradicts sections 3 (E7) and 4.1 for three words, and rests on artefact A2 for
   four more.** ATC0_COMMON, ATC0_USB_AON and ATC0_USB are "on" in R54's list (the snapshot);
   macOS's own last write to each requests off (`0x23f0`, `0x3f0`, `0x3f0`), the hypervisor
   holds those writes and applies them after the snapshot, and the chip went down with the
   three off (4.1 "After the snapshot", R27, R48). The tests hold the driver to neither.
   ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB are at the request 0 in R54 with no mark,
   and the driver is held to that; but macOS had no driver for that port in any capture (A2),
   and under Linux, with the Thunderbolt cable in, they are on. What macOS does with the first
   port's domains on a machine where it drives the port is in no capture.
Q5. **R51 points to a file, not to values.** "The 858 words of `commit-state-gh.tsv` read as
   that file's `H_det9_commit` column": the test author reads the spec only. The spec's text
   gives the 137 domain words in full (4.2a) and the other 721 as counts and examples. R51 is
   tested as far as R54, R47 and the sub-block words go.
Q6. **What the wake is to do with the domains the driver itself changed before the sleep:
   decided by the owner (section 12), not answered by the spec.** R40 (`[UNKNOWN]`, one domain
   in one capture) says macOS writes each domain back to the state it had before the sleep; the
   captures' wake values (W1-2c) are macOS's state, which with R54 is the state at the commit,
   not what the entry found. The decision: macOS's sequence stays, and after it the domains
   the entry changed are put back to the request it found. What the spec cannot settle about
   that, and the tests therefore leave free or assume: (a) *the request 4*: no capture shows it
   written over the request 0 (macOS only ever writes 0 over it, `0x344` -> `0x340`); the
   written value is free, the machine reports 4. (b) *Turning the display's and the second
   port's domains on with nothing behind them started*: macOS turns these on only together
   with booting their coprocessors (W4, out of scope); the tests require the three writes of
   every turn-on and nothing of the devices; whether a domain turned on so is in the state
   Linux's drivers left it in is unknown. (c) *The place*: "when the wake calls are done" is
   taken as the end of `leave_late`, after its last other write; the spec has no place for it.
   (d) The bits above the request are the hardware's: only the request is compared. (e) R40
   itself still rests on FPWM1 in capture F. As the driver stood, its wake waited on FPWM0's
   word, found at `0x244`, and gave up (section 1).
Q7. **No behaviour for an entry that ends without the chip going down, or for the wake on a
   machine that did not go down** (L7, L8; open question 25; first-round gap 10). On the
   machine the entry returned and the chip stayed up; the wake's writes were then made on a
   chip that had not been reset and ended in an SError at the audio switch (its domains were
   off: at a real wake the action turns them on first) or in a wait on `0x23b718004` that did
   not end. The suite has nothing for it: every simulated chip goes down, every wake is a real
   one. Which of the wake's steps presuppose a reset is not in the spec.
Q8. **The rule of R30's poll is not stated.** "Read until it changes: `0x1f` ... then `0x2f`":
   which bits are awaited is not said, and under Linux, without a power-down, the poll did not
   end (L8; what was read is not known). The tests require the last read before the next write
   to be `0x2f`, the one value the captures end on.
Q9. **R35: `0x23d0d9320` written 0 then 4 "after each alarm wake".** What tells macOS that the
   wake was the alarm's (the read of `0xd00c` = `01`, an interrupt, the wake status) is not
   stated; all three alarms were the hypervisor's. Left open: a write of that word is neither
   required nor forbidden.
Q10. **R31's "then `0x4000000`".** W1-4 has 33 writes (1 + 4 x 6 + 8), one of them to
   `0x2000e1004`; a second write of `0x4000000` to that word is not among them, and E0 and E3
   show the same value written to `0x200021004` by something outside any action. When and by
   what it is written at the wake is not stated; it is not required.
Q11. **R5 and R5w give reads without saying what they are for.** +`0x48` is read (`0x2e`)
   before a coprocessor is stopped; a documentation page calls it a status with "stopped" and
   "idle" bits; whether macOS waits on a value there, and what it does on another, is not
   observed. The tests require the read and nothing of its value. For a coprocessor that does
   not run or answer, and for a sub-block that is off, the spec now says in so many words that
   nothing was observed (R5, R22a, open questions 31, 33, 37): the decisions of the fourth and
   fifth rounds (sections 10, 11) stand as decisions, not as observations.
Q12. **Which block lies in which domain is still partial** (1.9). The device tree's domains
   are given per node, with block addresses but no sizes ("`0x681000000`.."); `sio` and its
   translator name virtual domains (`SIO-CPU-V`, `SIO-CPU-DART`) that are not words of the
   table; PCIe's translator, `dart-pmp` and the blocks of R20 (`0x234008000`, `0x279008000`)
   are not placed; "no domain is named" for the sensors, pin controllers, watchdogs, SPMI. The
   machine closes what it can (section 4) and the rest is never closed.
Q13. **FPWM1 and the bits no capture shows.** Under Linux FPWM1 reads `0xa00` (requested off;
   bits 9 and 11), under macOS it is on in four captures and off in one (R40); R54 lists it
   as on. Not held either way. Bit 11 (also GFX `0x0f002b00`) is in no capture before a
   turn-on; what macOS writes there is not known (gap T7 stands).
Q14. **13 words are on at the commit that section 1.9 does not observe when the sleep actions
   begin** (DWI, PMS_BUSIF, PCIE_REF, APCIE, DEBUG, NUB_SPMI0, NUB_SPMI1, NUB_AON, NUB_GPIO,
   NUB_FABRIC, NUB_SRAM, DEBUG_USB, DEBUG_AUTH). Linux has them on. Were one found off, R54
   requires it on at the commit; that it is turned on as R50's domains are is assumed, and no
   simulated machine has one off.
Q15. **Small things.** L9 (`0x9f03` = `0x50`, `0x9f01` = `0x30` after a run) is not explained
   and R9 is tested as before. R12 gives the MTR word `0x23b2e0000` as values only. The
   cores' domain words (R53) differ under Linux by which core made the reading (L12). Section
   0's "(`0x3f0` is read back as `0x200`)" and E1-4's "`0x23f0` (reads `0x2100` then `0x2300`)"
   show bit 8 set on some words and not on others when a domain goes down; the machine takes
   macOS's commit value.

