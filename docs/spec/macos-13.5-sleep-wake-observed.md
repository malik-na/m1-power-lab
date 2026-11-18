# macOS 13.5 on the M1 MacBook Air: what it is observed to do around deep sleep

Status: observation record, written 2026-11-17 from two captures (A, B) and brought up to date
the same day with a third (D, section 1.4), which has the last accesses before power-down, and
with two more taken with the cable out (E, F, sections 1.5, 1.6, 10, 11), and with one that
adds a register snapshot at the commit and each core's system registers on the way down (G,
sections 1.7, 3 E7, 4), and with a repeat of G whose commit snapshot also covers all 137
power-domain words (H, sections 1.7a, 4; round of 2026-11-17 evening), and with a third idle
sleep that also reads the commit list with macOS awake (I, sections 1.7b, 4.1b; round of
2026-11-17 night), and with the seventh round of the test author's questions answered from the
same eight captures, the Linux runs ds15 and "Linux awake", and reference code (round 7,
2026-11-17 late night), and with a ninth capture that arms watchdog 1 at the commit (J, section
1.7c), the Linux runs ds16 to ds17-3 that reach the commit and do not power down (section 12,
L16-L18), and a comparison of macOS's commit with Linux's (section 4.4) (round 8, 2026-11-17
near midnight), and with a tenth capture that records each core's own state at its final
write and the always-on block's words at the commit (K, section 1.7d), four runs in which the
instrument left that state in place or kept the last core running after the commit, none of
which powered down (section 1.7d), and the conditions a reference on other Apple chips names for
the hardware's power-down set against the M1 readings (section 4.4a) (round 9, 2026-11-18), and
with an eleventh capture that reads watchdog 2 inside macOS's writes of `0x23d2c4000`, the CPU
start/stop block and the whole power-gate page at the commit (L, sections 1.7e, 4.1d), two more
captures in which the instrument left each core's timers as macOS left them and the chip still
powered down, and two runs in which it left only the pending virtual interrupts and the chip
did not (section 1.7e, E7) (round 10, 2026-11-18), and with two runs in which the instrument
cleared the power-gate header word `0x23b71c000` before the cores' final writes and the chip
still powered down and woke, a second Linux reading of that word, and the requirements since
round 6 restated as statements a test can check (sections 1.7f, 8.1) (round 11, 2026-11-18),
and with the Linux readings of run ds19 and its probe runs (each core clean at its final write,
the SoC still up) and every observed difference between macOS's state at and before its commit
and Linux's written out as candidate requirements C1-C17, each to be tried behind its own switch
(section 8.2, decision D5) (round 12, 2026-11-18), and with the candidates carried into macOS
under the hypervisor (section 1.7g), the Linux runs of the candidate switches (section 12,
L25-L28), what the captures say about who writes the words of candidate C3 (8.2 C3, R70), C3 and
C5 revised, and decisions D6 and D7 on the driver's failure path and its watchdog (round 13,
2026-11-19), and with the round-10 test author's gaps Z1-Z10 answered: D6's waits, put-back
and cores made exact, D7's first arming moved before `enter` and its second into the glue's
commit-point step, the logic's interface to the glue as decision D8, C3's places and C5's four reads made exact (round 14,
2026-11-19), and with the same test author's gaps Z11-Z13 answered: C15's two words never put
back on D6's failure path, C5's gate on the request and the state together, C3's nine values
handed to the commit-point step as its argument (round 14b, 2026-11-19), and with the glue test
author's gaps GL1-GL8 answered: the probe record beside the commit-point step, the C3 record's
layout, one record per commit point, no glue access after the step, the failure record before
the disarm, watchdog 1 disarmed on every return to Linux, the failure record's fields the wait's
(round 14c, 2026-11-19), and with macOS's start of `pmp` and its endpoint-`0x20` words read from the
hypervisor's round-10 captures, the round-11 runs in which the instrument dropped the word
`0x0020e00000550000` (section 1.7h, R71-R75), `pmp` under Linux (not started by the stock kernel,
started by an earlier module; L29, L30), and starting, messaging and stopping `pmp` under Linux as a
candidate of the kernel side's, with decisions D9-D11 (8.2 C18) (round 15, 2026-11-19), and with
two points of the glue's C and arm64 review settled as decisions: the first arming of watchdog 1
moved to the glue's first device access of its sleep step, and the "left armed" exception ending in
a panic, with Linux's own driver of watchdog 1 not active as a precondition of a `wdt` run (D7 (a),
(c), (e); L31) (round 15b, 2026-11-19), and with the glue test author's gaps GL10-GL13 and the `pmp`
client's test author's gaps G1-G27 answered: the sleep step defined as the glue's suspend callbacks
from `begin` to `end`, a `run_on` not answered sent the panic way only when the release also fails,
the panic leaving the exception's record standing, D7 (e)'s check on Linux's flags only; the
watchdog read under the test command line (L32); which of the logic and the client makes each of
`pmp`'s steps (D3 (b), D9 (b) restated), the client's start-up order without the kernel's RTKit
library, its buffers, its waits' bounds and its ways out (D9-D11) (round 15c, 2026-11-19, listed in
"Changes in round 15c" at the end, with the earlier rounds' lists below it). It states what macOS
did, not why, and not what is
needed for sleep to work; the candidates of 8.2 are differences, not causes.
Nothing here comes from any Linux sleep driver's code. Section 12 records what was **read on the
machine under Linux** (the state a driver starts from); every such statement is marked
**[LINUX]** and is an observation of Linux, not of macOS.

## 0. Terms used in this document

- **The machine**: MacBook Air (M1, 2020), Apple model J313, chip t8103. Eight cores: cores 0-3
  are the efficiency cluster, cores 4-7 the performance cluster.
- **Deep sleep / suspend-to-RAM**: the chip is powered down, memory keeps its contents, and the
  machine continues later where it stopped.
- **Device register / word**: a memory-mapped hardware register, named by its physical address
  (`0x2........`). "W addr=value" is a write, "R addr=value" a read.
- **Device tree (ADT)**: Apple's description of the hardware, handed to macOS at boot. Device
  names in this document (`pmgr`, `mcc`, `aic`, `smc`, ...) are its node names; a name with
  `.regN` means "the N-th address range that node lists". Several nodes often list the same
  range, so every statement also gives the address. The naming rule is in `var/spec/lib.py`.
- **Power manager (`pmgr`)**: the block at `0x23b700000` (and `0x23d280000`) holding one
  **control word per power domain**. Domain names (`SIO`, `DISP0_FE`, ...) are from the power
  manager's own table in the device tree (`var/map-20261117/adt/pmgr-devices.json`). In a control
  word the low four bits are the state macOS asks for and bits 4-7 the state the hardware reports
  (`0xf` = on, `0x0` = off, `0x4` = clock-gated, as far as the values seen here show).
  *Reference, not an observation* (gap T7): Aurora Silicon's Linux driver
  (`aurora-silicon/linux`, branch `integration/aurora`, commit `dcce0e751c71`,
  `drivers/pmdomain/apple/pmgr-pwrstate.c`) names the other bits: 31 reset, 28 "auto enable",
  27-24 "auto" state, 19-16 minimum state, 12 "PS reset", 11 busy, 10 device disable, 9 "was
  clock-gated", 8 "was power-gated", 7-4 actual, 3-0 target; states `0xf` active, `0x4`
  clock-gated, `0x0` power-gated. Those names are that driver's; none of them is established by
  the captures. In the captures bits 8 and 9 are set by the hardware when a domain goes down
  (`0x3f0` is read back as `0x200`), bit 28 is set by macOS's third write of a turn-on, and bits
  24-27 read `0xf` after a coprocessor in the domain has been stopped (`PMP` `0x1f0f03ff`).
  *(Added this round, gaps Q13, Q15.)* Which of bits 8 and 9 a word shows after a turn-off
  depends on the domain and, for some, on the capture (section 4.3: `0x200` for the bus and PWM
  domains; `0x2100`, later `0x2300` for DISP0_FE; `..300` for RMX, DISP0_CPU0, GFX; APCIE_ST
  `0x0f000200` in E, F, H and `0x0f000300` in D, G, I). Bit 11 is read set in five reads in all
  eight captures, each while macOS waits for a turn-on to complete (DISP0_FE `0xb4f`,
  DISPEXT_FE `0xb4f` / `0x2b4f`; E, F, I), never at rest and never written. PMP's
  `0x1f0f03ff` is also read once with macOS awake, before any sleep entry (I's "pre-full"
  snapshot, section 4.1b), so it is not tied to the sleep.
  *(Added round 7, gaps W2, W14; `r7_bits24.py`.)* **Bits 24-27 against bits 4-7**, over every
  read and snapshot value of a domain word in D-I (101,361 values): with bit 28 set, bits 24-27
  equal bits 4-7 in 1,004 of 1,012 values (`0x1000030f`, `0x1400024f`, `0x1f0003ff` ...); the
  eight others are DCS words reading `0x1f00030f` and `0x1f00034f` (bits 24-27 `0xf`, state 0 or
  4). With bit 28 clear, bits 24-27 read 0, 4 or `0xf` independently of the state (`0x0f000200`,
  `0x4000244`, `0x244`). In every read after a write that cleared bit 28 (section 4.3, form 2;
  66 instances with a read, `r7_bit28.py`) bits 24-27 read `0xf`, also where the write put 0 there (RMX written `0xf`, read
  `0x0f0003ff`): bits 24-27 are not read back as written.
  *Reference, not an observation* (round 7): in the same Aurora Silicon file (commit
  `dcce0e751c71`), bit 28 enables the hardware's automatic power management: a domain
  "active" there is one whose actual state is `0xf`, **or** whose target is `0xf` with bit 28
  set (`apple_pmgr_ps_is_active`); the driver sets bit 28 after a turn-on unless told not to,
  and on a turn-off "as macOS lowers a domain" it first writes the word with bits 28, 9, 8 and
  11 cleared and waits for the actual state `0xf`, then writes the target with bits 8 and 9 set
  ("writing the history bits clears them"), the actual bits left as read. Its comment, written
  for another chip (T8140), says that taking both at once "from an auto-gated state can leave
  BUSY latched", and states that "macOS waits for (word & 0x8ff) == 0" after a turn-off. Its
  comment for the M4 DCP (J713) says the DCP CPU domain under automatic power management "reads
  level 0 while its CPU idles, and is fully on again once the CPU has been stopped". Aurora's
  device tree (`arch/arm64/boot/dts/apple/t8103-pmgr.dtsi`, same commit) gives DISP0_CPU0 and
  DISPEXT_CPU0 `apple,min-state = <4>`, which that driver writes into bits 16-19. None of this
  is established for t8103 by the captures; it is how the reference code reads these bits. The
  Asahi Linux documentation has no power-manager page (asahilinux.org/docs/hw/soc/pmgr/ returns
  404, round 7).
- **Memory controller (`mcc`)**: the block at `0x200000000`-`0x2003fffff`: four identical planes
  at `0x200000000`, `0x200040000`, `0x200080000`, `0x2000c0000`, common words at `0x200100000` and
  `0x200150000`, and eight DRAM channel controllers `DCS0`-`DCS7` at `0x200200000` + n x `0x40000`.
- **Coprocessor**: a small processor inside the chip running Apple firmware. macOS talks to each
  through a **mailbox**: it writes a message into two words at +`0x8800`/+`0x8808` of the
  coprocessor's block and reads replies from +`0x8830`/+`0x8838`. The low byte of the second word
  is the **endpoint** (channel); endpoint 0 carries power management messages. Two status words
  are read around each message: +`0x8110` (towards the coprocessor) and +`0x8114` (towards the
  main processor). Forms read (`mbox_status.py`, `gaps_gh.py`, gaps S4, F3): `0x2XY01` (bit 17
  set, bits 20-23 zero) and `0xNXY01` with N in bits 20-23 non-zero (`0x100101`, `0x101201`,
  `0x202401`, `0x402601`, `0x608e01`, `0x818001` ...), where X and Y are hexadecimal digits that
  step by one per message. In all seven captures, over every mailbox: no read of +`0x8830`
  follows a read of +`0x8114` in the bit-17 form (29 to 49 such reads per capture, each followed
  by no reply read), and every read of +`0x8830` follows a +`0x8114` read with bits 20-23
  non-zero (bit 20 alone in 14,974 to 64,086 cases per capture; bits 21-23 at some mailboxes),
  apart from one to three reads per capture at blocks whose +`0x8114` reads `0x0`-`0xa` and a
  few reads at the very start of E's and F's logs. Whether bits 20-23 count waiting messages is
  not established. *Documentation, not an observation:* the Asahi Linux page "ASC"
  (asahilinux.org/docs/hw/soc/asc/) says these status registers show "empty" in bit 17 and
  "not empty" in bit 16; in the captures the reply follows bits 20-23 being non-zero. The
  same page names +`0x44` CPU_CTRL (bit 4 "CPU_START") and +`0x48` CPU_STATUS (bit 5 mailboxes to
  the main processor empty, bit 3 FIQ not pending, bit 2 IRQ not pending, bit 1 CPU stopped,
  bit 0 CPU idle). macOS reads +`0x48` = `0x2e` before writing +`0x44` = 0 in all seven captures
  (gap F9); by that page's names `0x2e` has bits 1, 2, 3 and 5 set. *(Added this round, gap
  Q11.)* The same read of `0x2e` precedes the write of +`0x44` = 0 for `dcp`, `dcpext`,
  `gfx-asc` and `ans` too, in D-I (section 3, E2a). *Reference, not an observation:*
  Aurora Silicon's `aura` (`aurora-silicon/aura`, branch `main`, commit `5d3219cf`,
  `src/asc.c`) names +`0x48` bit 1 "STOPPED" and bit 5 "IDLE" and treats a coprocessor with
  both set as stopped in its idle loop; the Asahi page names bit 5 differently (above).
  *(Added round 7, gaps W1, W7; observation.)* **Widths** (`r7_mbox_seq.py`, all eight
  captures): the four mailbox words +`0x8800`, +`0x8808`, +`0x8830`, +`0x8838` are accessed as
  64 bits, and +`0x44`, +`0x48`, +`0x8110`, +`0x8114` as 32 bits, for every coprocessor of R4.
  The low byte of +`0x8808` (sent) and +`0x8838` (received) is the endpoint; its upper bytes in
  the received word carry a counter (`0x10670000000020` ...). **+`0x48` is read only straight
  before a write of +`0x44` = 0, and reads `0x2e` in all 76 such reads of all eight captures**
  (`r7_coproc_words.py`); no capture reads it at another moment. `aop`, `smc` and `sep` have no
  access to +`0x44` or +`0x48` in any capture.
  *Reference, not an observation* (round 7; Aurora Silicon `aurora-silicon/linux`, branch
  `integration/aurora`, commit `dcce0e751c71`): `drivers/soc/apple/mailbox.c` names +`0x8110`
  the AP-to-coprocessor control word and +`0x8114` the coprocessor-to-AP control word, bit 16
  "full", bit 17 "empty", and bit 0 of +`0x8114` "receive enable"; +`0x44` bit 4 "CPU run".
  `drivers/soc/apple/rtkit.c` names the management message types by bits 52-59: 6 "set IOP
  power state" (`0x0060..`), 7 its acknowledgement (`0x0070..`), `0xb` "set AP power state"
  (`0x00b0..`, acknowledged with the same type), 1 hello, 5 start endpoint, 8 endpoint map;
  the power states `0x20` "on", `0x10` "quiesced", `0x201` "idle: sleeping, retain state",
  `0x220` "init"; the system endpoints 1 crash log, 2 syslog, 3 debug, 4 I/O report, 8 OS log;
  and +`0x48` bit 1 "stopped", bit 5 "idle", both together "down": its own sleep path, after
  the "idle" power state, polls +`0x48` for both bits for 5 ms. `drivers/gpu/drm/apple/afk.c`
  names the endpoint-level types of `dcp`'s endpoints by bits 48-63: `0xa3` "start", `0x86`
  "start acknowledged", `0xa2` "send", `0x85` "receive", `0xc0` / `0xc1` "shutdown" /
  acknowledged; it has no name for `0xa4` and `0x87` (the pair macOS uses in R5a).
  `drivers/gpu/drm/apple/dcp-internal.h` names `dcp`'s endpoint `0x37` "IOMFB" and lists
  `0x20`-`0x2d` as service endpoints. `drivers/gpu/drm/apple/iomfb_m4.c` (M4, not t8103) stops
  its display coprocessor by waiting up to 100 ms for +`0x48` bit 5 and then clearing +`0x44`
  bit 4.
  Coprocessors seen:
  `smc` (system management: battery, sensors, lid, keys), `pmp` (power metering), `sio` (serial
  I/O helper), `aop` (always-on sensors, audio), `ans` (storage), `dcp` and `dcpext` (internal
  and external display), `gfx-asc` (graphics), `sep` (secure enclave).
- **Power chip (PMU)**: the separate power-management chip. macOS reaches it over the **SPMI** bus
  through a controller at `0x23d0d9000` (`nub-spmi`): a command word written to +`0x304`, a reply
  read from +`0x308`.
- **Interrupt controller (`aic`)**: block at `0x23b100000`.
- **Hypervisor**: the m1n1 program (version v2.0.0-131 with local changes) that ran underneath
  macOS during the captures and recorded its hardware accesses. Anything the hypervisor did, or
  changed, is called a **hypervisor artefact** and is marked `[ARTEFACT]`.
- **Capture A** = run `135full3`: asleep 900 s, woken by the power chip's alarm, which the
  hypervisor had set. **Capture B** = run `135full4`: asleep 320 s, woken by a key press.
- **Capture D** = run `det2`: asleep 119 s, woken by a key press, recorded on the machine itself
  with no host attached (section 1.4). Statements say which captures they rest on: "A/B/D" gives
  three values in that order; "(D)" means capture D only; "(A, B)" means D cannot show it.
- **Capture E** = run `det5` and **capture F** = run `det4`: like D, but with the cable to the
  other computer physically out during the sleep entry, the sleep and the wake. E slept 415.5 s;
  F slept 1.6 s. "D/E/F" gives three values in that order; "the detached captures" means D, E
  and F. Five values are given as A/B/D/E/F.
- **Capture G** = run `det8`: detached like D (cable in), but nobody clicked Sleep: macOS went
  to sleep by itself after idling; woken after 90 s by the alarm the hypervisor set. It adds a
  snapshot of 792 registers at the commit and the system-register accesses of every core before
  the sleep. "The detached captures" now means D, E, F and G.
- **Capture H** = run `det9`: G's recipe and hypervisor build repeated unattended (idle sleep,
  alarm after 90 s), with the commit snapshot extended by the 66 power-domain words G's list
  lacked (858 words). "G, H" means both; "the detached captures" means D-H. **"All seven"**
  means A, B, D, E, F, G, H.
- **Capture I** = run `det10`: H's recipe again (idle sleep, alarm after 90 s), with the commit
  list extended by the four sub-block status words (862 words), the same list read once more
  with macOS awake just before the detach ("awake-extra" snapshot), and the address-translator
  pages of `pmp` and `sio` logged in full from macOS's boot (section 1.7b). From this round
  "the detached captures" means D-I, **"all eight"** means A, B, D-I, and "G-I" means G, H and I.
- **Capture J** = run `det11` (round 8, section 1.7c): I's recipe (idle sleep, the instrument's
  alarm after 90 s) with one change: at the commit the hypervisor also arms watchdog 1 to bite
  150 s later. Statements made before round 8 keep their meaning ("all eight" is A, B, D-I);
  where J was checked, the text says so ("D-J", "G-J", **"all nine"**).
- **Capture K** = run `det12` (round 9, section 1.7d): J's recipe with the instrument recording,
  on each core at its final `CYC_OVRD_EL1` write and before changing anything, that core's own
  timers, pending interrupts and interrupt-controller words, and with 17 always-on and watchdog
  words added to the commit list. It slept and woke at the alarm. Where K was checked the text
  says so ("D-K", "G-K", **"all ten"**).
- **The round-9 runs** `det13`, `det14`, `det16`, `det17` (section 1.7d): K's recipe with one
  further change of the instrument's each (`det13`, `det17`: each core's timers and pending
  interrupts left as macOS left them; `det14`, `det16`: the last core kept running after the
  commit, sampling). **None of them powered down and woke; each ended in a reset.** Their
  in-memory logs were lost with the reset; what is known of them is the power chip's bytes
  after the reset and the times. They are not captures of macOS alone: **[HV-CHANGED]** marks a
  statement that rests on a run in which the instrument's change altered the outcome, so that
  the statement is about the instrument's influence on the machine, not about what macOS does.
- **Capture L** = run `det18` (round 10, section 1.7e): K's recipe with two additions, both
  reads: inside each of macOS's three writes of `0x23d2c4000` the instrument reads that word,
  watchdog 2 and `0x23d2b8028`, `0x23d2b8040` just before and just after the write (10-20
  microseconds of the instrument's reads in each write); and the commit list extended to the CPU
  start/stop block `0x23b754000`-`0x23b75401c` and the whole power-gate page
  `0x23b71c000`-`0x23b71c704` (1,328 words). It slept and woke at the alarm. Where L was checked
  the text says so ("D-L", "G-L", **"all eleven"**).
- **The round-10 runs** (section 1.7e): L's recipe with one more change of the instrument's
  each. `det19b`, `det21`: each core's guest timers and timer FIQ enable left as macOS left them,
  the pending virtual interrupts cleared as in every earlier power-down; **both powered down and
  woke at the alarm**, and their logs were read, so with L they are three captures of the probe,
  the commit list and each core's state ("L, det19b, det21"). `det20b`, `det22c`: the pending
  virtual interrupts left, the guest timers written off as in every earlier power-down; **both
  ended in a reset, as det13 and det17 did**. *(Round 10.)* **[HV-CHANGED]** also marks a
  statement about what the machine did after the commit in `det19b` or `det21`: the outcome
  there was the same as without the change, but it was reached with the change in place. Their
  readings taken before the instrument's change (macOS's writes, each core's state at its final
  write, the commit snapshot) are macOS's, as in K.
- **The round-11 runs** `det23`, `det24` (section 1.7f; evidence "Hypervisor round 8"): L's
  recipe with one change of the instrument's: on the first core to reach the instrument's
  handling of its final write, after macOS's last write to the power-gate page and before that
  core's own final write, the instrument writes **`0x23b71c000` = 0** (`det23`: after that
  core's state record, 6-14 microseconds before T; `det24`: before it, 281-288 microseconds
  before T and before every core's final write). **Both powered down and woke at the alarm.**
  Their readings of macOS's writes and of each core's state at its final write are macOS's, as
  in L; their commit snapshot was read after the instrument's write: `0x23b71c000` there (0) is
  **[HV-CHANGED]**, and every other word is a reading taken after that write. Their power-down and
  wake are **[HV-CHANGED]** (the outcome the same as without the change). Where they were
  checked with L the text says "L-`det24`" or names the five: L, `det19b`, `det21`, `det23`,
  `det24`. **"All fifteen"** (power-downs, or captures with a wake) means A, B, D-L, `det19b`,
  `det21`, `det23`, `det24`.
- **Reference** (round 9): `docs/reference/asahi-aurora-sleep-deep-dive.md`, a compilation of
  what the Asahi Linux documentation and the Aurora Silicon repositories say about deep sleep on
  other Apple chips (T8140, T8132, T6040, T6050) and about t8103. Statements taken from it are
  marked *Reference, not an observation* and name the chip; none is a requirement.
- **[LINUX]** marks a reading taken with Linux running on the same machine (section 12). It is
  not an observation of macOS and not a requirement.
- **T** = the time of the last recorded access before the sleep; **W** = the time of the first
  recorded access after the wake. In A and B the log stops early (artefact A11), so their T is
  some milliseconds before the real power-down; in D, T is the real last access. `T-2.6` means 2.6 s before T, `W+0.09` means 0.09 s after W.
- **Access number** `i`: position of an access record in a capture, counted from 0.
- **Kernel console**: macOS's own log text. It was written to a serial device during the captures
  and names the driver about to run at each step ("IOPlatformSleepAction -> AppleSMC").

## 1. Scope and method

### 1.1 What was captured

Both captures follow one procedure on 2026-11-17: macOS 13.5 (kernel xnu-8796.141.3~6, release
build for T8103) booted under the hypervisor, left idle at the login window, "Sleep" clicked by
the operator, a real suspend-to-RAM, a wake, macOS running again.

| | Capture A (`135full3`) | Capture B (`135full4`) |
|---|---|---|
| Access records in the file | 7,081,306 | 6,228,527 |
| Page-touch map only until | 212.19 s (i < 1,130,009) | 227.19 s (i < 1,209,271) |
| Every access logged from | i = 1,130,009 | i = 1,209,271 |
| Last access before the sleep (T) | 320.8015 s, i = 3,602,037 | 270.7994 s, i = 2,232,588 |
| Accesses logged in full before T | 2,472,029 in 108.6 s | 1,023,318 in 43.6 s |
| Wake marker | 1220.9832 s | 590.5710 s |
| First access after the wake (W) | 1221.1058 s, i = 3,602,038 | 590.6801 s, i = 2,232,589 |
| Accesses after the wake | 3,479,268 in 163.4 s | 3,995,938 in 172.2 s |
| Kernel text slide | reference | capture A's addresses minus `0x288000` |

Sources per capture: the access log (`touch-135fullN.jsonl`), the hypervisor's log
(`run-135fullN.out`), macOS's console as received by the host (`vuart-135fullN.log`), and two
register snapshots taken by the hypervisor: "pre-full" just before full logging began and "wake"
after the wake, before macOS ran. All are in `tools/hv-trace-kit/runs/20261116-mac135/` (private).
Scripts: `var/spec/*.py`; `build_db.py` loads a capture into `var/spec/db/capN.db`, every other
script reads those. Each claim below names its script and output file (all under `var/spec/`).

Until full logging began the hypervisor recorded only the first access to each 16 KiB page per
5 s (2,539 and 2,633 such records) plus every access to two ranges (`0x200000000`-`0x2003fffff`
and the page `0x23bc34000`). Everything in sections 2-6 uses the full log only.

### 1.2 What this method cannot see

1. **CPU system registers.** Only the ones the hypervisor traps and prints are known
   (section 6.3). The final per-core power-down writes are not printed.
2. **Coprocessor-internal state.** Only mailbox words and the registers macOS touches.
3. **The hypervisor's own accesses** to hardware (its USB, its console, its power-chip commands).
4. **Zones the hypervisor keeps** (`run-135full3.out`, lines "PT[..] -> RESERVED/HOOK"):
   - its virtual serial port `0x235200000`-`0x235203fff`: not logged at all;
   - nine guarded power words: `0x23b7001c0` (domain SIO_BUSIF), `0x23b7001c8` (SIO),
     `0x23b700220` (UART_P), `0x23b700270` (UART0), `0x23b700420` (ATC0_COMMON), `0x23d280088`
     (ATC0_USB_AON), `0x23d280098` (ATC0_USB), `0x23d29c044`, `0x23d29c05c`;
   - the core start/stop words `0x23b754000`-`0x23b75401f` and one word per core at
     `0x210050100`, `0x210150100`, `0x210250100`, `0x210350100`, `0x211050100`, `0x211150100`,
     `0x211250100`, `0x211350100`.
   Accesses to these are absent from the access log (0 records, both captures). Those to the
   guarded power words and the core start/stop words appear in the hypervisor's log in order but
   without a time.
5. **The last moments before power-down.** See artefact A11: the access log ends early.
6. **Anything while asleep**, and anything not memory mapped.
7. **Time precision.** A record's time is when the host received it. Order is exact; times are
   good to the link's buffering.

### 1.3 Where the hypervisor changes what macOS sees or does: the known artefacts

- **A1 Boot arguments.** macOS was started with `debug=0x14e serial=3 apcie=0xfffffffe
  -enable-kprintf-spam wdt=-1 clpc=0` (`run-135full3.out`, "Setting boot arguments"). So: a
  serial console is on and synchronous (every console byte is a write to `0x23d12c004`, 3,726 of
  the 9,649 writes in the last 2.6 s of capture A); macOS's watchdog handling is altered (`wdt=-1`); the
  performance controller is off (`clpc=0`), which may change the idle patterns of section 2; a
  PCIe port mask is set.
- **A2 Devices removed from the device tree** before boot: `dart-usb0`, `atc-phy0`, `usb-drd0`,
  `acio0`, `acio-cpu0`, `dart-acio0`, `apciec0`, `dart-apciec0`, `apciec0-piodma`, three `hpm0`
  USB-C port controllers, `atc0-dpxbar`, `atc0-dpphy`, `atc0-dpin0`, `atc0-dpin1`, and the `atc0`
  display endpoint. macOS therefore never drives the first USB-C/Thunderbolt port; the hypervisor
  uses it. What macOS does to those devices at sleep is not in the captures.
- **A3 Guarded power words** (list in 1.2): macOS's reads return a value composed by the
  hypervisor (for example hardware `0x20ff`, reported `0x2000`); its writes are held back
  ("Dangerous write") and the last held value is written by the hypervisor at the commit.
- **A4 Core start and stop.** macOS's writes to `0x23b754000`.. are handled by the hypervisor,
  which starts or stops the core itself. *(Round 10; the instrument's code, `~/m1n1-next`
  `ff8caba0`, `src/hv/hv_detached.c` `det_cpustart`, and `proxyclient/m1n1/hv/__init__.py`
  `cpustart_wh`, cited as the record of what the instrument did.)* In a real-sleep run a write to
  `0x23b754000` (+`0x0`, the stop bits of R11) is passed to the hardware and logged; a write to
  +`0x8` or +`0xc` makes the instrument start the named cores itself; every other write,
  +`0x4` included, is logged and **not** passed on. The instrument writes nothing to the block
  of its own. So macOS's stop bits reach the hardware; its writes of +`0x4` at the wake (W2) do
  not. (Read in the round-10 build only; that the builds of A-K did the same is not checked
  here.)
- **A5 Memory-protection lock.** The words `0x200000680`-`0x20000068c` (and the same in the other
  three planes) are emulated; the system registers `CTRR_A_LWR_EL1`, `CTRR_A_UPR_EL1`,
  `CTRR_CTL_EL1`, `CTRR_LOCK_EL1` are shadowed (macOS's writes do not reach the hardware) and
  writes to `ACC_CFG_EL1` are dropped.
- **A6 The commit.** When the last core goes down the hypervisor stops its own timers, detaches
  its USB device, writes its markers and a wake-handler address into the power chip's scratch
  registers (`0x9f0a` onward), in capture A sets the power chip's alarm register (`0xd008`) to
  now + 900 s, writes 1 to the SPMI controller's status word `0x23d0d9378`, and applies the held
  power-word writes. None of this is in the access log. (`/home/naeem/m1n1/src/hv/hv_cpu_power.c`,
  `harness/real_s2r.py`, `harness/spmi_ack_patch.py`.)
  *(Round 8: the instrument's commit path written out in full, from its own code, the build that
  made G-J: `~/m1n1-next`, branch `m1power/hv-detached`, `bb8873c0`, `src/hv/hv_cpu_power.c`,
  `hv_real_s2r_cyc_ovrd`; the lines below date from 2026-11-06/07, before capture A, except the
  snapshot (G-J) and watchdog 1 (J). This is the lab's own instrument, cited as a record of what
  the instrument did, not as a reference for the hardware.)* On **every core**, at that core's
  `CYC_OVRD_EL1` write with bit 0 set (E7), before the write reaches the hardware: the core's
  four timer controls are written 0 (`CNTP_CTL_EL0`, `CNTV_CTL_EL0` as seen from EL2, and the
  guest's `CNTP_CTL_EL02`, `CNTV_CTL_EL02`), the guest timer FIQ enable
  `VM_TMR_FIQ_ENA_EL2` is written 0, and the pending virtual IRQ and FIQ bits of `HCR_EL2` are
  cleared. On the **last** core only, in this order: the commit snapshot (G-J); its UART and USB
  device stopped (one register write); the held power-word writes (A3); its stage marks and the
  wake note written into the power chip's scratch `0x9f04`-`0x9f0c` over SPMI (one-byte and
  six-byte writes); with an alarm requested, the clock read (`0xd002`, six bytes) and `0xd008`
  written to now + N s; **`0x23d0d9378` written 1**; in J only, watchdog 1's four writes. Then,
  on each core, its `CYC_OVRD_EL1` write is carried out and the guest's own wait loop runs. The
  instrument does not write the AP wake-source masks at `0x23d004008`-`0x23d004018` in any of
  A-J (`harness/real_s2r.py`: `mask=()` in every run), and does not write power-chip `0xd000` or
  `0xd00e`.
  *(Round 9: the build of K and the round-9 runs, `~/m1n1-next` `m1power/hv-detached`
  `2ced1fab` and `2cb8a180` on `bb8873c0`, same file; each option off unless named.)* With
  `hv_s2r_core_state` (K and every round-9 run) each core, at its `CYC_OVRD_EL1` write and before
  any write of the instrument's, reads its own timer, interrupt and performance-counter
  registers and 107 interrupt-controller words into the log; this made the eight cores' way down
  last about 0.3 ms (J: 31 microseconds). The last core also writes two per-core bitmaps over
  SPMI to power-chip scratch `0x9f0b`, `0x9f0c` after the alarm, before its write of
  `0x23d0d9378` = 1. The instrument writes **no** word of the watchdog page other than
  watchdog 1's four (J) at the commit, in any of these builds. With `hv_s2r_keep_state` (`det13`,
  `det17`) the per-core acts above shrink to stopping the instrument's own two EL2 timers:
  `CNTP_CTL_EL02`, `CNTV_CTL_EL02`, `VM_TMR_FIQ_ENA_EL2` and the pending virtual IRQ and FIQ of
  `HCR_EL2` are left as they were. With `hv_s2r_sample_ms` (`det14`, `det16`) the last core,
  after the whole commit, stays running and reads `0x23d2b8028`, `0x23d2b8040`, watchdog 2's
  three words, `0x23d2c4000`, `0x23b71c090`, `0x23b71c360` every 10 ms and power-chip `0x0201`
  every 100 ms (SPMI reads), and writes power-chip scratch every 100 ms (SPMI writes): **SPMI
  traffic after the commit**, which no other capture has; `det14` then goes down (bound 3 s, or
  watchdog 2 within 1.5 s of its bite), `det16` (`hv_s2r_sample_hold`) never does and would set
  watchdog 1 to bite at once at a 20 s bound (not reached).
  *(Round 10: the build of L and the round-10 runs, `~/m1n1-next` `m1power/hv-detached`
  `ff8caba0` on `2cb8a180`, same file, `hv_real_s2r_cyc_ovrd`; host side lab `546e9e4`.)*
  `hv_s2r_core_state` on in every run. `hv_s2r_keep_timers` (`det19b`, `det21`): the guest's
  `CNTP_CTL_EL02`, `CNTV_CTL_EL02` and `VM_TMR_FIQ_ENA_EL2` are left as they were; the pending
  virtual IRQ and FIQ of `HCR_EL2` are cleared as in A-L. `hv_s2r_keep_vfiq` (`det20b`,
  `det22c`): the pending virtual IRQ and FIQ are left; the three timer registers are written 0
  as in A-L. (`hv_s2r_keep_state` of `det13`, `det17` is both at once.) In every one of them the
  instrument's own two EL2 timers are stopped. `hv_s2r_c4_probe` (L and every round-10 run): on
  each guest write of `0x23d2c4000`, a trapped page, the writing core reads `0x23d2c4000`,
  watchdog 2's count, bite and control, `0x23d2b8028`, `0x23d2b8040`, then carries out the
  write, then reads the same words again; reads only, about 10-20 microseconds inside each of
  the three writes. The commit snapshot table holds up to 2,048 words. The instrument's comment
  at the clearing of the pending virtual interrupts reads "a pending vFIQ is a WFI wake-up
  event"; it is the instrument author's statement, not an observation.
  *(Round 11: the build of `det23`, `det24`, `~/m1n1-next` `m1power/hv-detached` local commit
  `9ec6b9c7` on `ff8caba0`, not pushed; host side `harness/real_s2r.py` `real_s2r_on(pg_clear=)`,
  lab `fea08ef`; as recorded in the evidence.)* The round-10 build with one option,
  `hv_s2r_pg_clear`, off by default: bit 0, the instrument writes `0x23b71c000` = 0; bit 1, also
  `0x23b71c040` = 0 (not run); once per sleep, on the first core to take the instrument's
  `CYC_OVRD_EL1` path, before that core's own final write; bit 2 clear (`det23`, value 1) after
  that core's state record, bit 2 set (`det24`, value 5) before it. The writing core reads both
  header words just before and just after the write (log kind 28, probe sequence 100) and the
  commit note puts `0xc0` with the two words' bit 31 into scratch `0x9f0a` (not needed: both
  runs woke). `keep_timers` and `keep_vfiq` off: every other per-core act as in A-L (timers
  written off, pending virtual interrupts cleared). `hv_s2r_core_state` and the probe of
  `0x23d2c4000` on, as in L.
- **A7 The wake.** The chip's reset vector points into the hypervisor. It runs first, reads the
  wake status, brings its USB back (which powers that port's domains), takes the "wake"
  snapshot, then enters macOS at macOS's reset entry on core 0. The snapshot therefore shows the
  chip after the hypervisor's own early work, and the delay between reset and macOS's first
  access is not macOS's.
- **A8 Slowed execution.** Every access is trapped. Sustained throughput is about 21,000 accesses
  a second; the 49,152-word save in phase E3 takes 2.0 s (41 microseconds a word). All durations
  below are upper bounds for a machine without the hypervisor.
- **A9 Hypervisor watchdog.** The hypervisor armed the chip's watchdog at `0x23d2b0000` for
  150 s at boot and turned it off before the sleep ("WDT off"). Values macOS reads there may
  reflect that. *(Round 8.)* In J the instrument also arms watchdog 1 at the commit (A6, 1.7c).
  *(Round 9.)* So in K and the round-9 runs. Watchdog 2 is not written by the instrument (A6).
  *(Round 10.)* So in L and the round-10 runs; the probe of A6 only reads watchdog 2.
  *(Round 11.)* So in `det23` and `det24`.
- **A10 Power-chip scratch bytes.** After the wake macOS reads scratch `0x9f08`-`0x9f0b` as
  `ff ff 51 01`; before the sleep it read `00 00 00 00`. The change is the hypervisor's (A6).
- **A11 The access log ends before the power-down (captures A and B only).** The log's last records are a sweep of reads
  through the interrupt controller that stops mid-way at different points: 408 reads up to
  `0x23b10365c` in capture A, 372 reads up to `0x23b1035cc` in capture B (`view.py N pre -0.0245
  0 -n`). The console, delivered after the wake, shows macOS went on (section 3, phase E6). The
  records still in the hypervisor's buffer when it shut its USB down were lost.
- **A12 Console.** Access to `0x23d12c000`-`0x23d12c018` (console output) and, at the wake, to
  `0x23d10c000` and `0x23d128008` (console set-up) exists because of A1.
- **A13 Snapshots** are read by the hypervisor while macOS is paused; a read with a side effect
  would be an artefact. None is known.

### 1.4 Capture D (`det2`): the same procedure with no host

**What it is.** 2026-11-17 05:53-05:59, same machine, macOS, boot arguments and removed devices
(A1, A2). The hypervisor (a newer build, v2.0.0-137) was switched into a mode in which the host
computer plays no part: the exits the host used to handle are handled on the machine, and every
record goes into a log in the machine's own memory, read out after the run. Files:
`detached-det2.jsonl` (the log), `touch-det2.jsonl`, `run-det2.out`, `vuart-det2.log` (the part
of the run before detaching). Loaded by `build_db_det.py` into `db/capd.db`.

| | Capture D |
|---|---|
| Lines in the log file | 917,535 (the read-out's own summary says 917,798 entries, none dropped; the difference of 263 is not explained by the file, see open question 12) |
| Access records | 917,081, access numbers 0 - 917,080 |
| Idle after detaching, before the operator's first input | 210.78 s |
| Last access before the sleep (T) | 220.913181 s, i = 585,818 |
| Last core enters its sleep path | 220.913197 s |
| Wake record | 340.307082 s; asleep 119.394 s |
| First access after the wake (W) | 340.307587 s, i = 585,819 |
| Host takes control back | 412.854 s |
| Kernel text slide | capture A's addresses minus `0x16d0000` |

**What it adds.**
1. **The last accesses before power-down** (phase E6). The log does not depend on a link, and it
   runs on past the two points where A and B stop, through the rest of the interrupt-controller
   action and both power-chip actions, to the last core going down.
2. **Real times.** Every record carries the machine's own timer (24 MHz), to a microsecond, and
   the timer runs through the sleep.
3. **The exits the hypervisor handles, as records with times** (`det_events.py`,
   `det-events.tsv`, `det-sysreg.tsv`): 31 reads and writes of the guarded power words (with the
   value given to macOS and the value the hardware held), 28 writes of the core start/stop
   words, 7 + 1 "core enters its sleep path" records, the wake record with the three status
   words, 6 registers read at the wake, the "wake" snapshot (264 words), the resume, 368
   system-register accesses, 7 core starts.
4. **Less stretching.** A trapped access costs about 6.4 microseconds here against about 41 in
   A and B (the 49,152-word read of E3: 0.315 s against 2.04 s). The kernel sleep path takes
   0.484 s against 2.60 s, the wake up to "IOCPUSleepKernel exit" 0.407 s against 3.70 s
   (`det_misc.py`, `phase-times.tsv`).

**Limits of capture D.**
- **Four pages were not trapped and are absent**: `0x23b738000`, `0x23bc34000`, `0x210e20000`,
  `0x211e20000` (16 KiB each). So D shows nothing of the per-core cycle I1, and nothing of the
  cluster words `0x210e20400`-`0x210e20660` and `0x211e20400`-`0x211e20660` that the power
  manager saves, clears and restores (E5-8d, W1-2f). For these, A and B remain the only source.
  In three-way comparisons these pages are removed from A and B as well.
- **Stretching remains**: every logged access is still trapped. 6.4 microseconds a word is far
  above an untrapped register access, so D's durations are still upper bounds; phases with
  few accesses (waits on user space, on coprocessors) are probably close to real.
- The logged rate is not comparable with A and B: 2,046 accesses a second at idle (the four
  busiest pages are missing), 105,569 in the busiest second (the wake).
- One capture of this kind. Its console after detaching exists only as the bytes macOS wrote to
  `0x23d12c004`, re-assembled from the access log (`console.py`, `console-d-*.txt`).
- Artefacts A1-A7, A9, A10, A12, A13 apply unchanged (same boot arguments, same removed
  devices, same guarded words, same code at the commit and the wake). A8 applies with the
  smaller cost above. A11 does not apply. In D the hypervisor did not set the power chip's
  alarm ("left as macOS set it").
- System registers are recorded only after the wake (0 of 368 records before it): the
  registers a core writes as it powers down are still not visible.
- The "pre-full" snapshot (793 words logged, 792 distinct) was taken 28 s before detaching and
  a second one, "pre-detach", 11 s later (791 of 792 equal): about 238 s and 227 s before T.

### 1.5 Capture E (`det5`): no host and no cable, 415 s asleep

Same method, build (v2.0.0-137), boot arguments, removed devices, untrapped pages and record
format as D. Files `detached-det5.jsonl`, `touch-det5.jsonl`, `run-det5.out`, `vuart-det5.log`;
loaded with `build_db_det.py det5 e` into `db/cape.db`.

| | Capture E | Capture F (1.6) |
|---|---|---|
| Lines in the log file / entries reported by the read-out | 576,013 / 576,276 | 1,066,905 / 1,067,168 |
| Access records | 575,556 | 1,066,447 |
| Cable out: host's clock / first sign in the machine's log | about 39 s / 40.025 s | about 187 s / 187.707 s |
| Operator's first input | 51.8 s | 192.8 s |
| Last access before the sleep (T) | 62.156041 s | 215.247815 s |
| Last core enters its sleep path | 62.156059 s | 215.247830 s |
| Wake record; asleep | 477.694508 s; 415.538 s | 216.839031 s; 1.591 s |
| First access after the wake (W) | 477.695001 s | 216.839523 s |
| Cable in: host's clock / first sign in the machine's log | about 488 s / 487.967 s | about 233 s / 232.943 s |
| Host takes control back | 507.863 s | 337.394 s |
| Kernel text slide (A minus) | `0xe0c000` | `0x131c000` |

**What E adds.** A complete sleep and wake with nothing plugged in, comparable with D access for
access (section 10); a second and third instance of the last steps before power-down (E6); a
sleep of 415 s.
**Limits.** As D (four untrapped pages, trapping cost, no system registers before the wake, one
run). Only 38 s of idle before the cable was pulled and 10 s between the wake and the cable
going back in. macOS never drives this port (A2), so it has no controller for it to log; what
it shows of the cable is in section 10. In all three detached captures the file has 263 fewer
lines than the read-out reports entries: the 264-word snapshot is one line (closes the count
question for the logs, open question 12).

### 1.6 Capture F (`det4`): no host and no cable, 1.6 s asleep, and a cancelled entry

Same method as E; `build_db_det.py det4 f`, `db/capf.db`. Numbers in the table above.
**What F adds.** (1) A sleep entry that was started and given up 0.2 s later (section 11.1);
(2) a complete entry 7.7 s after that; (3) a sleep of only 1.591 s (section 11.2); (4) 120 s
of macOS after that wake, including the cable going back in.
**Limits.** As E. The cause of the early wake is not identifiable from the log (section 11.2).
The log shows one committed sleep only and no sleep entry after the wake (section 11.3).

### 1.7 Capture G (`det8`): an idle sleep, with a snapshot at the commit and the cores' registers

2026-11-17 08:31-08:44. No host, cable in, nobody at the machine. Hypervisor build v2.0.0-138;
same boot arguments, removed devices and untrapped pages as D. Files `detached-det8.jsonl`,
`touch-det8.jsonl`, `run-det8.out`, `vuart-det8.log`; `build_db_det.py det8 g` -> `db/capg.db`.

| | Capture G |
|---|---|
| Lines in the file / entries reported | 1,220,324 / 1,221,379 (difference 1,055 = the two snapshots stored word by word) |
| Access records | 1,219,548 |
| Idle after detaching, to the first sign of the entry | 430.5 s |
| Last device access before the sleep (T) | 438.067188 s |
| Last core enters its sleep path | 438.067204 s |
| "commit" snapshot, 792 words | 438.067205 s to 438.068119 s (0.914 ms) |
| Hypervisor's own writes of the guarded words (7 "commit-write" records) | 438.068242 s to 438.068251 s |
| Wake record; asleep | 528.393519 s; 90.326 s |
| First access after the wake (W) | 528.394064 s |
| Read-out | 549.231 s (20.84 s of macOS after the wake) |
| Kernel text slide (A minus) | `0x13b0000` |

**What it adds.**
1. **A register snapshot at the commit** (section 4): 792 words read on core 0 between its own
   sleep-path entry and the first of the hypervisor's own commit actions. The values are the
   hardware's, also for the guarded words (`commit_snap.py`, `commit-snapshot-g.tsv`).
2. **System-register accesses before the wake**: 315 records from the first core's stop-bit
   write to the last core's sleep-path entry, each with its time, the core, the value and how
   the hypervisor dealt with it (section 3, E7; `det_down.py`, `det-down-g.tsv`).
3. **The hypervisor's own power-word writes at the commit**, as records (A3, A6 made visible).
4. **An idle sleep**: an entry macOS started by itself (section 3, "idle sleep").
5. **A second alarm wake** (A's was the first), section 6 W4.
**Limits.** As D. In addition: the snapshot list is the 792-word list of the earlier snapshots
(memory controller 80, DRAM controllers 448, clock generator 96, power-domain words 74, other
power-manager words 32, always-on block 46 + 16); **only 16 of its words are among the roughly
630 the entry writes**, so most last-written values of section 4 are still unconfirmed by a
read-back. The log's snapshot record has one start and one end time, not a time per word.
Not trapped and so in no log (the builder's list): the standard EL1 registers (SCTLR, TTBR,
TCR, VBAR, CPACR, DAIF), the timers, SPRR/GXF, pointer-authentication keys, cache and TLB
maintenance, the final wait instruction; the hypervisor zeroes the guest timer controls on
each core before the snapshot `[ARTEFACT]`. The alarm that woke it is the hypervisor's (A6).
Only 20.8 s after the wake were recorded.

### 1.7a Capture H (`det9`): G repeated, with all 137 domain words at the commit

2026-11-17 17:38-17:54. G's recipe, build (v2.0.0-138), boot arguments, removed devices and
untrapped pages unchanged; nobody at the machine; the hypervisor's alarm at the commit + 90 s.
The one difference: the commit list is G's 793 entries (792 addresses) read first, then the 66
power-domain words G's list lacked (858 addresses). Files `detached-det9.jsonl`,
`touch-det9.jsonl`, `run-det9.out`, `vuart-det9.log`; `build_db_det.py det9 h` -> `db/caph.db`
(kernel text slide, A minus: `0x1a4c000`).

| | Capture H |
|---|---|
| Lines in the file / entries reported | 1,229,124 / 1,230,245, 0 dropped (difference 1,121: the two snapshots stored word by word, as in G) |
| Access records | 1,228,347 |
| First sign of the entry (audio "Set PowerStage (4 -> 6)") | T-7.558 (426.8 s after the detach) |
| Last device access before the sleep (T) | 434.399456 s |
| Last core enters its sleep path | 434.399473 s |
| "commit" snapshot, 858 words | 434.399473 s to 434.400534 s (1.061 ms), 0 errors |
| Hypervisor's writes of the guarded words (7 "commit-write" records) | from 434.400636 s, the same seven words and values as G |
| Wake record; asleep | 524.682696 s; 90.283 s |
| First access after the wake (W) | 524.683235 s |
| Read-out | 545.45 s (20.8 s of macOS after the wake) |

**What it adds.** (1) A second commit snapshot of G's 792 words: 774 equal to G's, 18 different
(section 4.1). (2) The commit values of all 137 power-domain control words (section 4.2a).
(3) A third alarm wake, dark like A's and G's (section 6, W4). (4) A seventh capture of every
statement checked by `reqcheck.py`: 69 checks pass in H, 2 are on untrapped pages, no failure.
**Limits.** As G. The 66 added words have no snapshot value with macOS awake (they are not in
the "pre-full"/"pre-detach" list), so for them only the commit value and the few reads in the
log are known.

**H against D and G, by console-marker segment** (`phases.py` with `CAPS=d,h`, `g,h`, `3,h`;
`seven_h.py`): E3 sleep actions, ordered writes identical in 39 of 42 against D and 37 against G
(the three that differ against D are `smc`'s, `sio`'s and `pmp`'s, which carry message counters);
E5 and E6, all 36 quiesce actions: 34 against D (the two power-chip actions, which in H run in
F's and G's order) and 35 against G (the alarm bytes); W1 active actions: 54 of 57 against D and
against G; W3 wake actions: 24 (D) and 26 (G) of 30. Phase times (console markers, seconds from
T or W): display request -7.488, "PM response" -0.877, "IOCPUSleepKernel enter" -0.478, PMP sleep
action -0.432, first address-translator action -0.125, first quiesce action -0.090,
memory-controller quiesce -0.030, power-manager quiesce -0.022, interrupt-controller quiesce
-0.016; power-manager active +0.005, memory-controller active +0.018, first wake action +0.127,
PMP wake action +0.142, power-manager wake action +0.349, "IOCPUSleepKernel exit" +0.414,
"system wake events" +0.671: within 15 ms of G throughout.

### 1.7b Capture I (`det10`): H repeated, with the commit list read awake, and the translator pages from boot

2026-11-17 18:26-18:41. H's recipe, build (v2.0.0-138 chainloaded, `m1n1-next` `ed07f5bb`), boot
arguments, removed devices and untrapped pages; nobody at the machine; the hypervisor's alarm at
the commit + 90 s. Differences from H: (1) the commit list is H's 858 words plus the four
sub-block status words `0x23b7483e0`, `7e0`, `be0`, `fe0` (`var/recfg/commit-snap-list-r3.json`,
862 addresses); (2) the same list was read once with macOS awake, in the hypervisor shell about
a second before the detach, as snapshot "awake-extra" (863 entries, 0 errors); (3) the pages
`0x23b300000` (`pmp`'s address translator) and `0x235004000` (`sio`'s) were logged in full from
macOS's boot. Files `detached-det10.jsonl`, `touch-det10.jsonl`, `run-det10.out`,
`vuart-det10.log`; `build_db_det.py det10 i` -> `db/capi.db` (kernel text slide, A minus:
`0x86c000`). Observation stage's own tables: `var/commit-state/macos135-det10-*`.

| | Capture I |
|---|---|
| Entries reported / dropped; access records | 995,348 / 0; 993,447 |
| "pre-full" snapshot | 198.2 s after the run start, macOS awake (18 s before the detach) |
| "awake-extra", "pre-detach" snapshots | 216.36 s, 216.54 s after the run start (macOS awake) |
| First sign of the entry (audio "Set PowerStage (4 -> 6)") | T-7.548 |
| Last device access before the sleep (T) | 431.378205 s after the detach |
| Last core enters its sleep path | T+0.000016 (431.378221 s) |
| "commit" snapshot, 862 words | T+0.000017 to T+0.000983, 0 errors |
| Hypervisor's writes of the guarded words (7 "commit-write" records) | from T+0.001113, the same seven words and values as G and H |
| Wake record; asleep | 521.562497 s; 90.184 s |
| First access after the wake (W) | 521.563011 s |
| Wake snapshot | 264 words |

**Phase times** (console, seconds from T or W): audio "(4 -> 6)" -7.548, display request
-7.484, "awdl0 disable" -7.476, "PM response took 1580 ms" -0.876, "IOCPUSleepKernel enter"
-0.481, PMP sleep action -0.433, first address-translator action -0.126, first stop bit
-0.0911, first quiesce action -0.0905, memory-controller quiesce -0.030, power-manager quiesce
-0.022, interrupt-controller quiesce -0.016; power-manager active +0.005, memory-controller
active +0.018, first wake action +0.129, PMP wake action +0.144, power-manager wake action
+0.351, "IOCPUSleepKernel exit" +0.419, "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0x02
nub-spmi.0xC0 rtc" +0.711 (a dark alarm wake as A, G, H). Within 15 ms of H throughout.
**Against H, by console segment** (`phases.py` with `CAPS=h,i`): before the sleep 75 of 79
segments with identical ordered writes (the four that differ: `smc`'s key action, `sio`'s and
`pmp`'s sleep actions, which carry message counters and the +`0x8114` value, and the power-chip
action with the alarm bytes); after the wake 82 of 89. `reqcheck.py`: 69 checks pass in I, 2
not visible (untrapped pages), none fails. Core stop order 4, 1, 5, 2, 3, 6, 7 (T-0.091118 to
T-0.090622); all eight cores in their sleep path within 19 microseconds, core 0 last; start
order at the wake 7, 6, 3, 2, 5, 1, 4 (W+0.1212 to W+0.1281); the 315 system-register records
before the wake carry R43's values exactly as in H. Alarm bytes macOS wrote: `f0 4c 09 00`.
**What it adds:** the awake value of every word of the commit list, including the 66 domain
words and the four sub-block status words (4.1b); a third commit snapshot to compare with G and
H (4.1b); where the translator values of R55 come from (W3); the width of `0x690000004`'s
write (1.8). **Limits:** as H. The awake snapshot is one reading per word at one moment;
periodic readings during the entry were not taken (the detached hypervisor reads extra words
only at the commit and the wake).

### 1.7c Capture J (`det11`): I repeated, with watchdog 1 armed at the commit (round 8)

2026-11-17 22:57-23:11 (evidence "Hypervisor round 5"). I's recipe (idle sleep, nobody at the
machine, the instrument's alarm at the commit + 90 s, I's 862-word commit list) with the build
`m1n1-next` `bb8873c0` (I's `ed07f5bb` plus the watchdog option). The one change: after its alarm
and its write of `0x23d0d9378` (A6), the last core writes watchdog 1 with `0x23d2b001c` = 0,
`0x23d2b0010` = 0, `0x23d2b0014` = `0xd693a400` (150 s at 24 MHz), `0x23d2b001c` = 4, then
carries out its own `CYC_OVRD_EL1` write; and the instrument's wake path reads watchdog 1's
count, bite and control and watchdog 0's count first. The detach came about 17 s before the
entry began (G-I: about 430 s), and no "awake-extra" snapshot was taken. Files
`detached-det11.jsonl`, `run-det11.out`, `vuart-det11.log`; no database was built: every number
here is from `r8_det11.py` (output `r8-det11.txt`), which reads the log directly.

| | Capture J |
|---|---|
| Entries reported / dropped; access records | 332,701 / 0; 330,792 |
| First sign of the entry (audio "Set PowerStage (4 -> 6)") | T-7.528 |
| Last device access before the sleep (T) | 24.438210 s after the detach: the console-port read of E6-4 |
| Cores' sleep-path records | cores 4, 7, 1, 5, 6, 2, 3 at T-0.000005 to T-0.000002; core 0 last, T+0.000014 |
| "commit" snapshot, 862 words | T+0.000014 to T+0.001114, 0 errors |
| The instrument's writes ("commit-write" records) | the seven held words, T+0.001241 to T+0.001250, as in G-I; watchdog 1's four writes logged at T+0.001285 to T+0.001291 (carried out after the alarm and `0x23d0d9378`, A6) |
| Wake record; asleep | 113.951187 s; **89.513 s** (G 90.326, H 90.283, I 90.184) |
| First access after the wake (W) | 113.951711 s (0.524 ms after the wake record) |
| Wake status `0x23d00401c` / `020` / `024` | 0 / `0x400000` / 0, as in all eight |

**Phase times** (s from T): audio "(4 -> 6)" -7.528, "PM response took 1588 ms" -0.849,
"IOCPUSleepKernel enter" -0.483, first stop bit -0.0907, first quiesce action -0.0902,
interrupt-controller quiesce -0.0152 (I: -7.548, -0.876, -0.481, -0.0911, -0.0905, -0.016).
Core stop order 4, 1, 5, 2, 3, 6, 7; start order at the wake 7, 6, 3, 2, 5, 1, 4 (W+0.1216 to
W+0.1284). The 315 system-register records before the wake have G's distribution (77, 77, 37,
26, 24, 24, 16, 16, 9, 9 on the ten registers of E7) and R43's and R45's values: cores 4, 5, 1,
7, 6, 2, 3 read `ACC_OVRD_EL1` = `0x180010102001c207` before any core wrote it, core 0 reads
`0x1800101526076207`; every core writes `ACC_OVRD_EL1` = `0x1800101526076207` and
`CYC_OVRD_EL1` = `0x3000001`. The last steps before T are F's and G's order (R38): the four
power-chip commands at T-0.00477 to T-0.00435, the second `0x23d2c4000` = 1 at T-0.003727, the
third at T-0.000698; alarm bytes written `3a 8a 09 00`. macOS's writes to the watchdog page are
those of R15 (counts of watchdogs 0 and 1 written 0 at T-0.4658; `0x23d2b8008`, `0x23d2b800c`,
`0x23d2b000c` at T-0.0352 to T-0.0350); none after the wake in the 20.8 s logged.

**Commit snapshot against I** (862 words): **842 equal, 20 differ**, all in groups that vary
between the earlier captures: `MCC.plane0-3+0x680`/`684` (`0xdef`/`0xe1b`; emulated, A5),
`DCS1-7+0x500` (`0x2440004`; I `0x1440004`), DCS0 `0x1400034f`, DCS1 `0x1f00034f` (I both
`0x1000030f`), power-gate words `0x23b71c0d8`, `0f0`, `108`, `120` `0x80040307` (I
`0xc0040307`). Against H 844 of 858, against G 776 of 792 equal; **767 of G's 792 words are
equal in G, H, I and J**, the same 767 as in G-I (4.1b). So every word R52 lists changed in J
as in I, the cores' and clusters' words read R53's values, and the four sub-block status words
read R22a's commit values. Wake snapshot: 259 of 264 equal to I's (DCS0, DCS1, DCS3, DCS4, DCS5
differ, words that vary at every wake).

**The watchdogs at the wake entry** (the instrument's first reads; `wake-reg` records):

| Word | At the wake entry | Last written before the sleep |
|---|---|---|
| Watchdog 1 count `0x23d2b0010` | `0x51ae8` (13.94 ms at 24 MHz) | 0 by macOS at T-0.466 and by the instrument after T+0.0013 |
| Watchdog 1 bite `0x23d2b0014` | `0xd693a400` (150 s), as written | `0xd693a400` (instrument) |
| Watchdog 1 control `0x23d2b001c` | 4, as written | 4 (instrument) |
| Watchdog 0 count `0x23d2b0000` | `0x51b57` (13.94 ms) | 0 by macOS at T-0.466 |
| Watchdog 2 count / bite / control `0x23d2b0020` / `24` / `2c` | `0x76f11b` (0.325 s) / `0x7270e00` (5 s) / 0 | not written by macOS in the log |
| `0x23d2b8028`, `0x23d2b8040`, `0x23d2c001c` | `0x8000000`, `0x22`, `0xff0` | not written by macOS in the log |

The two counts differ by 111 ticks (4.6 microseconds) although their last writes before the
sleep were 0.466 s apart, and neither is near the 89.5 s asleep: neither count was carried
through the sleep. Whether they stopped and were reset at the power-up, or at the power-down, is
not separated. (Watchdog 0 counts with its control at 0: the instrument's arm-time lines in
`run-135full3.out`, `run-det2.out`, `run-det4.out`, `run-det5.out` and `run-det8.out` to
`run-det11.out` read watchdog 0's count 33 to 36 ms below the system counter read just after it,
with control 0, eight runs. The same lines read `0x23d2c4000` = 1 with macOS awake before every
entry.) Watchdog 2 and the three other words read as at every earlier wake
(section 5).

**What it adds:** an armed watchdog 1 (control 4, bite 150 s) at the power-down did not prevent
the power-down or the alarm wake, and the bite and control words survive the sleep while the
count does not (R61). **Limits:** as I; one capture; the watchdog writes are the instrument's,
made later than any write of macOS's.

### 1.7d Capture K (`det12`) and the round-9 runs (`det13`, `det14`, `det16`, `det17`) (round 9)

2026-11-17 23:52 to 2026-11-18 01:00 (evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/
README.md`, "Hypervisor round 6"). Every run used J's recipe (idle sleep, nobody at the machine,
the instrument's alarm at the commit + 90 s, watchdog 1 armed at the commit for 150 s) with the
build of A6's round-9 note and `hv_s2r_core_state` on, and the commit list
`var/recfg/commit-snap-list-r6.json` (880 entries: I's 862 words plus the AP wake-source masks
`0x23d004008`-`0x23d004018`, `0x23d2b8028`, `0x23d2b8040`, watchdog 0's count, watchdog 1's
count, bite and control, watchdog 2's count, bite and control, `0x23d2c4000`, `0x23b71c360`,
`0x23d0d9378`). The same list was read with macOS awake ("awake-extra") before K's detach.
Files: `tools/hv-trace-kit/runs/20261116-mac135/*-det1[2-7].*`; the observation stage's
`var/commit-state/r6_core_state.py` (output `r6-det12.txt`) and `r6_snapdiff.py` (output
`macos135-det12-vs-det11.txt`); the power-chip dumps after each run
`var/m1-state/pmu-20261118-*-after-det1*.txt`; this round's `var/spec/r9_det12.py` (output
`r9-det12.txt`), which reads K's log directly (no database).

| Run | The instrument's change besides recording the cores' state | Outcome | Whose observation |
|---|---|---|---|
| K (`det12`) | none | **asleep 89.47 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out | macOS's, under the instrument as in G-J (the recording lengthened the cores' way down to about 0.3 ms) |
| `det13` | each core's timers and pending interrupts left as macOS left them (A6, `keep_state`) | **no wake; a reset about 5-6 s after the commit** (USB gone 00:18:50.2 for a commit at about 00:18:44; next kernel 00:19:02) | **[HV-CHANGED]** |
| `det14` | the last core samples for 3 s after the commit, then goes down | **no wake; a reset about 7 s after the commit** (±2 s; USB gone 00:31:34.3, kernel 00:31:47) | **[HV-CHANGED]** |
| `det15` | as `det16` | not run: macOS panicked while booting under the instrument (`i2c0::_runInterruptMode RxFIFO doesn't have enough bytes ... hpmBusManager`, `vuart-det15.log`) | none |
| `det16` | the last core never goes down; samples for 4.9 s | **a reset about 6 s after the commit** (±2 s; USB gone 00:47:20.4, commit about 00:47:14; kernel 00:47:33) | **[HV-CHANGED]** |
| `det17` | as `det13` | **no wake; a reset about 6 s after the commit** (USB gone 00:59:37.0, commit about 00:59:31; kernel 00:59:49) | **[HV-CHANGED]** |

**How the commit time of the runs that reset is known.** Their in-memory logs were lost with the
reset. The instrument set the alarm at the commit to the power chip's clock + 90 s; the dump
after the reset reads the alarm `0xd008` and the clock, so the commit = dump time + (alarm -
clock) - 90 s, to about ±2 s (evidence). The reset time is the moment the other computer saw the
M1's USB device go (`wake-readout-det1N.log`, "USB device gone"). That every round-9 run had
reached the commit is shown by the scratch bytes the instrument writes there: `det13`, `det14`,
`det17` hold its wake note `'W'` at `0x9f04` unconsumed (the next start was a boot, not a wake),
`det13` and `det17` hold `0x9f0a` = `'P'` (the commit's stage mark) and the bitmaps written after
the alarm; `det16` holds the sampler's own record `'E'` (A6). Whether the last core's real
`CYC_OVRD_EL1` write followed in `det13` and `det17` is not read. **What reset the SoC in any of
them is not read.**

**The power chip after each run** (`pmu-20261118-*`): `0x0201` = `00` after all five (and after
J); `0x9f03` = `0x50` after the four resets, `0x00` after K's wake (and after the wakes of H, I,
J: `pmu-20261117-175256-after-det9.txt`, `-184042-after-det10.txt`, `-231124-after-det11.txt`);
`0xd000` = `0x41` after the four resets (the alarm still armed: each reset came before the
alarm's time) and `0x01` after K's wake; fault shadow `0xa47b`-`0xa47d` = `00 08 00` after all
five, **K's alarm wake included**, so here it does not separate a reset from a wake.
*Reference, not an observation:* Aurora's `t8103.dtsi` names `0x9f01` "boot_stage" and `0x9f03`
"boot_error_stage" (reference, section 3.1); macOS writes `0x9f01` = `0x50` before every sleep
(R9). Under Linux `0x9f03` read `0x50` after ds16 and ds16c and after ds17-1 to -3 (L16, L17)
and `0x00` after ds14, which did not reach its commit: **after every run in either system that
reached a commit and did not wake, `0x9f03` read `0x50`.**

**The bitmaps of `det13` and `det17`** (scratch, written at the commit, read after the reset;
bit n = core n): `0x9f0c` (the guest's timer enabled and unmasked) `0xff` in both, every core;
`0x9f0b` (a virtual IRQ or FIQ, or an interrupt the instrument held for the guest, pending)
`0x03` (cores 0 and 1) in `det13`, `0x09` (cores 0 and 3) in `det17`. In K the same two facts per
core were cores 0-7 and cores 0, 1, 2 (E7, round-9 part).

**The scratch summaries of the sampling runs.** `det14`: `0x9f0a` `'q'` (the sampler stopped at
its 3 s bound and core 0 went on to its `CYC_OVRD_EL1` write), last update at 2.9 s, the low byte
of `0x23d2b8040` `0x20`. `det16`: `'E'`; 4.9 s sampled; last `0x23d2b8040` low byte `0x20`; last
`0x23d2b8028` >> 24 `0x01`; last `0x0201` `00`; flags `0x19` (watchdog 2 control bit 2 set,
watchdog 2 counting, `0x23b71c360` bit 30 set; `0x23d2c4000` bit 0 clear, `0x23b71c090` bit 30
clear; no read failed); first change, last change, number of changes **0, 0, 0**. So for the
4.9 s that core 0 kept sampling with the seven other cores down, none of the sampled words
changed (the progress words, `0x23d2c4000` and the two power-gate words every 10 ms, `0x0201`
every 100 ms), while watchdog 2 counted with its control bit 2 set; the scratch stops at 4.9-5.0
s, below the sampler's 20 s bound, which is when watchdog 2's 5 s bite, started about 15 ms
before T (4.1c), falls due. Whether watchdog 2 reset the SoC is not read.

**K's numbers** (`r9_det12.py`): 1,257,494 records, 0 dropped. T (last device access, a write to
SMC shared memory `0x23fe5f118` by core 0) = 431.639042 s after the detach. The three writes of
`0x23d2c4000` = 1 at T-0.015375, T-0.003898, T-0.000660 (R24, R37, R38; F's order). macOS's
writes to the watchdog page: `0x23d2b0000`, `0x23d2b0010` = 0 at T-0.4542; `0x23d2b8008` = 0,
`0x23d2b800c` read 0 and written 0, `0x23d2b000c` = 0 at T-0.0357 to T-0.0356 (R15); none after.
The first core-state record at T+0.000023; cores down (the instrument's records) 4, 5, 7, 1, 6, 2,
3 at T+0.000299 to T+0.000307, core 0 at T+0.000318. Commit snapshot T+0.000319 to T+0.001367,
879 words, 0 errors. Asleep 89.47 s; wake status 0 / `0x400000` / 0, **the same in all ten
captures**. **Commit snapshot against J** (862 common words, `r6_snapdiff.py`): 850 equal, 12
differ, all in groups that vary between earlier captures (`MCC.plane0-3+0x680`/`684`, `0xb48` /
`0xb74`; the domain words of DCS0, DCS2, DCS6; the power-gate word `0x23b71c120` `0xc0040307`,
J `0x80040307`). Wake snapshot 259 of 264 equal to J's (five DCS domain words, which vary at
every wake).

**What it adds:** each core's own state at its final write (E7, round-9 part); watchdog 2 armed
by the time of the commit and the always-on words at the commit (4.1c); the AP wake-source masks
awake and at the commit (4.1c); and, from the round-9 runs, two changes of the instrument's that
each turned a power-down and wake into a reset 5-7 s after the commit (`[HV-CHANGED]`, R59, R64).
**Limits:** K is one capture; the round-9 runs have no log; the two items `det13`/`det17` left in
place (the timers, the pending virtual interrupts) were not separated; nothing after the last
core goes down is observed in any run.

### 1.7e Capture L (`det18`) and the round-10 runs (`det19b`, `det20b`, `det21`, `det22c`) (round 10)

2026-11-18 02:08-03:35 (evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`,
"Hypervisor round 7", commit `bdb9f12`). Every run used K's recipe (idle sleep, nobody at the
machine, the instrument's alarm at the commit + 90 s, watchdog 1 armed at the commit for 150 s,
each core's state recorded at its final write) with the build of A6's round-10 note, the probe
of `0x23d2c4000` on, and the commit list `var/recfg/commit-snap-list-r7.json` (1,329 entries:
K's 880, the eight words of the CPU start/stop block `0x23b754000`-`0x23b75401c`, and every word
of the power-gate page `0x23b71c000`-`0x23b71c704` not already listed; 1,328 distinct). The same
list was read with macOS awake ("awake-extra", the guest paused) at each detach, about 7 min
before the commit. Files: `tools/hv-trace-kit/runs/20261116-mac135/*-det18.*`, `*-det19*`,
`*-det20*`, `*-det21.*`, `*-det22*`; the observation stage's `var/commit-state/r7_probe.py`
(outputs `r7-det18.txt`, `r7-det19b.txt`, `r7-det21.txt`), `r7_wd2start.py`
(`r7-wd2start-det*.txt`), `r7-det*-core-state.txt`, `r7-pwrgate-records.md`; the power-chip dumps
`var/m1-state/pmu-20261118-*-after-det1[89]*`, `-det2*`; this round's `var/spec/r10_checks.py`
(output `r10-checks.txt`), which re-reads all of these and the capture databases.

| Run | The instrument's change besides recording | Outcome | Whose observation |
|---|---|---|---|
| L (`det18`) | none (the probe's reads only) | **asleep 89.58 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out | macOS's, under the instrument as in K |
| `det19` | `keep_timers` | not run: macOS panicked while booting under the instrument (`i2c0::_runInterruptMode RxFIFO doesn't have enough bytes ... hpmBusManager`, as `det15`), before the instrument's options were set | none |
| `det19b` | `keep_timers` | **asleep 89.74 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out | macOS's up to each core's final write; after it **[HV-CHANGED]** |
| `det20` | `keep_vfiq` | not run: the same boot panic | none |
| `det20b` | `keep_vfiq` | **no wake; a reset about 6 s after the commit** (commit about 02:59:12 ±2 s; USB device gone 02:59:18.1; next kernel 02:59:30) | **[HV-CHANGED]** |
| `det21` | `keep_timers` (`det19b` repeated) | **asleep 89.62 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out | macOS's up to each core's final write; after it **[HV-CHANGED]** |
| `det22`, `det22b` | `keep_vfiq` | not run: the same boot panic, twice | none |
| `det22c` | `keep_vfiq` (`det20b` repeated) | **no wake; a reset about 5-7 s after the commit** (commit about 03:34:02 ±2 s; USB device gone 03:34:08.8; next kernel 03:34:21) | **[HV-CHANGED]** |

The commit times of `det20b` and `det22c` are found as in 1.7d (dump time + alarm − clock − 90
s); this round's re-computation from the dumps' bytes gives the same times within the ±2 s. Of
nine bring-ups four ended in the boot panic, each before the options were written.

**Numbers of the three captures** (`r7-det*.txt`, `r10-checks.txt`). T = the instrument's
"last core down" record: L 445.323736 s after the detach, `det19b` 433.068187, `det21` 433.659305.
macOS's three writes of `0x23d2c4000` = 1, all by core 0 from one guest instruction per run, at
T-15.6 / -4.1 / -0.97 ms (L), T-16.1 / -4.6 / -0.97 ms (`det19b`), T-16.0 / -4.2 / -0.96 ms
(`det21`); no other access to the word in the logs. The commit snapshot: 1,328 words, 0 errors,
from T+1 microsecond to T+1.9 ms (L), +1.8 ms, +2.6 ms. In `det21` the instrument's last-core
path ran on core 4 (counted eighth at 433.659305), while core 0's own state record was the last
of the eight (433.659058); in L and `det19b` both are core 0's. At the wake entry, in all three:
`0x23d2b8028` `0x8000000`, `0x23d2b8040` `0x22`, `0x23d2c001c` `0xff0`, watchdog 2 bite
`0x7270e00`, control 0, count 0.325-0.326 s; watchdog 1 bite `0xd693a400`, control 4, count
13.7-13.9 ms; as in J and K.

**The power chip after each run** (`pmu-20261118-*`; `r10-checks.txt` does not re-read these, the
values below are read from the dump files): `0x0201` `00` after all five; `0x9f03` `0x00` after
the three wakes and `0x50` after `det20b` and `det22c` (1.7d: `0x50` after every run of either
system that reached a commit and did not wake; still so); `0xd000` `0x01` after the wakes and
`0x41` after the two resets (the alarm still armed: each reset came before the alarm's time);
`0xa47b`-`0xa47d` `00 08 00` after all five. After `det20b` and `det22c` `0x9f04` holds the
instrument's wake note `'W'` unconsumed and `0x9f0a` its commit mark `'P'`; its per-core bitmaps
of macOS's own state at each core's final write: `0x9f0c` (guest timer enabled and unmasked)
`0xff` in both; `0x9f0b` (a virtual interrupt or one the instrument held pending) `0x0f` (cores
0-3, `det20b`) and `0x07` (cores 0-2, `det22c`). Whether the last core's real `CYC_OVRD_EL1`
write followed the commit in `det20b` and `det22c` is not read; **what reset the SoC in either is
not read**; whether it powered down before the reset is not read.

**What it adds:** watchdog 2 armed and `0x23d2b8028` bit 24 set **before** macOS's first write
of `0x23d2c4000` reaches the hardware, and `0x23d2c4000` reading 0 from that write on (4.1c,
R62, R24); the CPU start/stop block and the whole power-gate page awake and at the commit (4.1d,
R66, R67); the two items `det13` and `det17` left in place, separated (E7, R59, R68).
**Limits:** the probe is itself a change (reads inside each write; L powered down and woke as J
and K did without it); the two runs that reset left no log; each half of the split was run twice;
nothing after the last core goes down is observed in any run.

### 1.7f The round-11 runs (`det23`, `det24`) and Linux awake of 2026-11-18 03:54 (round 11)

2026-11-18 03:58-04:32 (evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`,
"Hypervisor round 8", commit `fea08ef`). Both runs used L's recipe (idle sleep, nobody at the
machine, the instrument's alarm at the commit + 90 s, watchdog 1 armed at the commit for 150 s,
each core's state recorded at its final write, the probe of `0x23d2c4000`, the commit list
`var/recfg/commit-snap-list-r7.json` read awake at the detach and at the commit) with the build
of A6's round-11 note. No same-session control with the option off was run; L (`det18`) is the
control. Files: `tools/hv-trace-kit/runs/20261116-mac135/*-det23.*`, `*-det24.*`, `*-det25.*`;
the observation stage's `var/commit-state/r8-det2[34].txt` (`r7_probe.py`),
`r8-det2[34]-core-state.txt` (`r6_core_state.py`), `r8-det2[34]-vs-det18.txt`
(`r6_snapdiff.py`); the power-chip dumps `var/m1-state/pmu-20261118-041248-after-det23.txt`,
`-042720-after-det24.txt`, `-043229-after-det25-bringup.txt`; this round's `var/spec/r11_checks.py`
(output `r11-checks.txt`), which re-reads `det18`, `det23` and `det24` from their logs, the
probe's sequence-100 records included (the observation stage's `r7_probe.py` prints them without
values).

| Run | The instrument's change | Outcome | Whose observation |
|---|---|---|---|
| `det23` | `0x23b71c000` = 0, written by core 2 after its state record, 6-14 microseconds before T | **asleep 89.998 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out, 0 dropped | macOS's up to each core's final write; `0x23b71c000` at the commit and the outcome **[HV-CHANGED]** |
| `det24` | `0x23b71c000` = 0, written by core 4 before its state record, 281-288 microseconds before T, 261 microseconds before the first core-down record | **asleep 89.649 s, woke at the alarm**, wake status 0 / `0x400000` / 0, log read out, 0 dropped | as `det23` |
| `det25` | both header words = 0 | not run: macOS came up (no boot panic); Naeem stopped the round before the detach; rebooted out of the instrument without a sleep | none |

**The write and the word at the commit** (`r11-checks.txt` parts 1-3):

| | `det23` | `det24` |
|---|---|---|
| The writing core; read just before (t) | core 2; 425.210853: `0x23b71c000` `0x80000000`, `0x23b71c040` `0x80000000` | core 4; 433.976488: the same |
| Read just after (t) | 425.210861: `0x23b71c000` **0**, `0x23b71c040` `0x80000000` | 433.976495: `0x23b71c000` **0**, `0x23b71c040` `0x80000000` |
| Core-down records (each logged just before that core's own `CYC_OVRD_EL1` write) | core 1 T-14, core 3 T-12, cores 4, 6, 5, 7 T-7 to T-6, core 2 T-3 microseconds, core 0 T (425.210867) | cores 7, 5, 1, 6, 2, 4, 3 T-20 to T-7 microseconds, core 0 T (433.976776) |
| The write against the cores' final writes | after the down records of cores 1 and 3 began (their real writes follow their records; at this resolution before or after the clear is not separated), before those of the other six | **before every core's final write** |
| Commit snapshot (T+1 microsecond to T+2.0 / +1.8 ms), `0x23b71c000` / `0x23b71c040` | **0** / `0x80000000` | **0** / `0x80000000` |
| Awake (at the detach) | `0x80000000` / `0x80000000` | the same |
| macOS's accesses to the header words | entry: `0x23b71c080`, `088` read and written `0x80000000` at T-15.8 ms, nothing else on the page; none between the clear and the wake; wake: R `0x23b71c000` 0, W `0x80000000`, R/W `0x23b71c040` `0x80000000` at wake + 7.68 ms, then `080`, `088` 10 ms later | the same; wake + 7.77 ms |

L (`det18`) for the same table: no clear; `0x23b71c000` `0x80000000` awake and at the commit; the
same entry writes; the wake's read of 0 and write of `0x80000000` at wake + 7.51 ms.

**Everything else, against L** (`r11-checks.txt` parts 4-6; `r8-det2[34]-vs-det18.txt`):
- macOS's three writes of `0x23d2c4000` = 1 by core 0 at T-15.8 / -4.1 / -0.98 ms (`det23`),
  T-15.8 / -4.1 / -0.95 ms (`det24`); inside each, as in L: 1 just before the first and 0 just
  after it, 0 around the second and third; watchdog 2 bite `0x7270e00`, control 4,
  `0x23d2b8028` `0x1000000`, `0x23d2b8040` `0x20` at all six reads; watchdog 2's count before the
  first write 37.8 / 57.2 microseconds; its computed start 7.5 / 3.2 microseconds after the
  record of `W 0x23b718004` = 0 (L 1.3, `det19b` 5.5, `det21` 7.1), 25.5 / 44.8 microseconds
  before the record of the first `0x23d2c4000` write.
- CPU start/stop block at the commit: `0x23b754000` = `0x23b754004` = `0xfe`, the other six 0;
  awake all 0. As L.
- Commit snapshot, 1,328 words, 0 errors, against L: 18 (`det23`) and 23 (`det24`) differ;
  besides `0x23b71c000` and the watchdog counts, all in groups that varied before
  (`MCC.planeN+0x680`/`684`, the DCS domain words `0x23b700300`-`338`, the power-gate group
  `0x23b71c0d8`-`134`, and in `det24` `0x2002c0500` `0x1440004`, L `0x2440004`). In `det24` the
  four group words `0x23b71c0d8`, `0f0`, `108`, `120` read `0xc0040307` at the commit (L
  `0x80040307`); they are among the 23 words of 4.1d that vary between runs.
- At the wake entry: `0x23d2b8028` `0x8000000`, `0x23d2b8040` `0x22`, `0x23d2c001c` `0xff0`,
  watchdog 2 count 0.325 s, bite `0x7270e00`, control 0; watchdog 1 count 13.8 / 13.9 ms, bite
  `0xd693a400`, control 4. As in J-L.
- Each core's own state at its final write: E7's round-11 part.
- The power chip after each run (dumps read after `hv-reboot.sh`): `0x0201` `00`, `0x9f03` `00`,
  `0x9f04`-`0x9f0c` `48 00 01 3f ff ff 47 50 00`, `0xa47b`-`0xa47d` `00 08 00`, `0xd000` `01`,
  `0xd00c` `00`: as after L, `det19b`, `det21`. After `det25`'s bring-up (no sleep) `0x9f03`
  reads `ff` and `0x9f04`-`0x9f0c` 0.

**Linux awake, stock kernel, 2026-11-18 03:54** (evidence "Linux awake, stock kernel (2026-11-18
03:54)", commit `cbeff4a`; one 32-bit read each over `/dev/mem`, kernel 7.3.0-0test5, nothing
suspended; the evidence gives the values only, no data file): `0x23b71c000` = **0**,
`0x23b71c040` = `0x80000000`, `0x23b754000` = 0, `0x23b754004` = 0. The same as the register
scans of L19 (snapshot 12, 2026-11-16; snapshot 16, 2026-11-18 02:12): a second reading, on
another boot, of the one header word that differs from macOS awake. **[LINUX]**

**What it adds:** `0x23b71c000` clear at the commit, from before every core's final write
(`det24`), was followed by the power-down and alarm wake, twice (**[HV-CHANGED]**; R67, R69); five
captures of macOS's own state at the final writes, the CPU block and watchdog 2 (L, `det19b`,
`det21`, `det23`, `det24`); a core reaching its final write with an IPI pending for it in the
instrument's view (`det23` core 3, E7). **Limits:** the word was cleared only at the end, after
macOS's whole entry had run with it set (from about 0.28 ms before T in `det24`); a word clear
through the whole entry, as under Linux awake, is not in any run; `0x23b71c040` was never
cleared (`det25` not run); the control is from another session (L); nothing after the last
core goes down is observed in any run.

### 1.7g The candidates carried into macOS (`det26`-`det32r`, hypervisor round 9; added round 13) **[HV-CHANGED]**

Source: evidence "Hypervisor round 9: candidates injected into macOS (det26-det32r, 2026-11-18
19:09-21:11)" (`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `8775601`);
private files `tools/hv-trace-kit/runs/20261116-mac135/*-det26*` to `*-det32r*`,
`var/commit-state/r9-det2[678].txt`, `r9-det3[01].txt`. Every run is a change by the instrument,
taken for open question 68.

**The recipe.** det18's (1.7e) with the instrument's option `hv_s2r_cand = N`: once, at macOS's
first write of I2C3's domain word `0x23b700208` after the detach (the start of E1; in the runs
that woke 7.45-7.59 s before T), the instrument wrote one candidate's words (8.2) to the values
Linux reads before its entry, on the trapping core, then passed macOS's write on. No restore; the
wake's own I2C3 writes do not inject again. Watchdog 1 was armed there (bite 150 s) and re-armed
at the commit (R61). Ways out without hands, named before the runs: the alarm at commit + 90 s,
watchdog 1 at the injection and at the commit; every run ended without hands.

| Run | Candidate | Written by the instrument | Read just after / at the commit | Outcome |
|---|---|---|---|---|
| `det26` | C2 | the four sub-blocks 0 (R22a's order), each status word read until its low byte is 0 (at most 10 ms) | control words 0; status `0x494900`, 0, `0x494900`, `0x515100`; the same at the commit (R22a's own accesses read 0 and wrote 0) | power-down, alarm wake (asleep 89.46 s) |
| `det27` | C6 | `0x23b71c000` = 0 | 0; 0 at the commit; the wake read 0 and set it `0x80000000` (R67) | power-down, alarm wake |
| `det28` | C4 | DCSn+`0x7b0` = 3, n = 0-7 | **0 one microsecond after the write**, 0 at the commit: not taken; **not a test of C4** | power-down, alarm wake |
| `det29`, `det29r` | C3 | `0x23b058000` = `0x444`, `0x23b05c000` = `0x666`, `0x23b060000` = `0x333` | not read (the log in RAM is lost with the restart) | **no commit** (the instrument's commit note never written); display dark; a restart about 144-153 s after the injection, when watchdog 1's 150 s from the injection falls due (within the timing's error); twice |
| `det30` | C5 | the twelve domains request 4 ((v & ~`0x3ff`) \| 4), each read until state 4 (at most 10 ms) | request 4 (`0x0f000244`, `0x244`) just after and at the commit | power-down, alarm wake; the wake lowered them by form 3 as at every wake |
| `det31` | C7 | `0x23d24003c` = `0x01101100`, `0x23d240048` = `0x00101100` | the same at the commit; at the wake entry `0x23d24003c` read `0x81100100` again with no write logged, `0x23d240048` still `0x00101100` | power-down, alarm wake |
| `det32`, `det32r` | C17 | the 28 words' bits 24-27 = 6 (`0x23b0400b0`: 2) | not read | **no commit**; a restart about 5-19 s after the injection (about when T comes in the runs that woke), before any armed watchdog could bite; twice |

In the five runs that woke no core accessed an injected word between the injection and T, apart
from R22a's own accesses in `det26`; the wake-entry words, watchdog values and power-chip bytes
were det18's. After the four restarts the power chip read `0x9f04`-`0x9f0c` as the arm left them
and the alarm register the previous run's value (the commit note was never written), `0xd000`
`01`, `0x9f03` `ff` after both C3 runs and `00` after both C17 runs, fault shadow `00 08 00` as
after every run of the round. What reset the SoC: not read. Camera: `det29r` dark from about 30 s
after the login window until the restart; `det32r` dark about 10 s after the login window, the
USB device gone 3 s later. Not run: C9, C14, C16 (the coordinator's stop). Not carried: C1, C8,
C10-C13, C15.

**What it adds:** under macOS, Linux's state of C2, C5, C6 and C7, put in at the start of E1 and
left to the commit, did not stop the power-down and wake (one run each): none of the four alone
holds the SoC up when the rest of the state is macOS's. With Linux's values written into C3's
three words, or into C17's clock words, macOS's entry did not reach its commit (two runs each).
**Limits:** each injection is a write by an application processor (the instrument at EL2), so a
run that fails cannot tell Linux's values from the act of writing these words at that moment
(this matters for C3: 8.2 C3, round 13); how far macOS's entry got in the four failed runs is not
read; one session, controls det18 and the five runs that woke; C4 not tested.

### 1.7h `pmp`'s start, its endpoint-`0x20` messages and the C3 words (proxy `c3idle1`; `det33`, `det34b`, `det35`-`det37`; with `det10`, `135map4`, `det18`, `det23`; hypervisor rounds 10 and 11; added round 15)

Source: evidence sections "Hypervisor round 10: what lowers the performance-state words" (lab
`c32ee1a`), "macOS's pmp start-up and endpoint-0x20 exchange (from round-10 captures)" (`4bf6072`)
and "Hypervisor round 11: macOS without the endpoint-0x20 0x55 message" (`bad8454`), all in
`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`; private files `var/commit-state/r10-*.txt`,
`r10-pmpstart-det33-boot.txt`, `-det34b-boot.txt`, `-det33-entry.txt`, `-det33-wake.txt`
(`r10_pmp_startup.py`), `r11-*.txt`; runs `tools/hv-trace-kit/runs/20261116-mac135/*-det33.*` to
`*-det37.*`, `touch-det10.jsonl`, `touch-135map4.jsonl`, `detached-det18.jsonl`,
`detached-det23.jsonl`. Taken for open question 70.

**The recipe.** det18's (1.7e), with the instrument's clock reading nine words every 250 ms: the
three C3 words (written `058000/05c000/060000` below), `pmp`'s +`0x44` and +`0x48` (each only while
PMP `0x23b7003d8` reports state `0xf`), PMP, PMS_SRAM `0x23b7003e0`, PMS `0x23b700140` and DCS0
`0x23b700300`; at boot from the instrument's start (times "t" on the M3's clock at receipt, so the
samples and the logged accesses are ordered only to the USB link's buffering), and while detached
(the M1's timer, exact order). `pmp`'s control page `0x23bc00000` and mailbox page `0x23bc08000` and
both CPU clusters' pages are logged in full from the start; the rest of device space at boot as the
5 s touch map (first access per 16 KiB page per 5 s). The clock stops the guest about four times a
second at boot: `det34`'s boot stalled before macOS ran (cause not read) and was repeated as
`det34b`; det33's sleep and wake came as det18's. det35-det37 add the instrument's drop of one
mailbox message (below, **[HV-CHANGED]**). Ways out without hands, named before each run: the
alarm at commit + 90 s, watchdog 1 at commit + 150 s, the instrument's proxy for a hang before the
commit, the attached host for a boot hang; every run ended without hands. Mailbox field names
(HELLO, EPMAP, STARTEP, ...) are the reference's (aurora-silicon/linux `integration/aurora`
`1f38ff8f4`, `drivers/soc/apple/rtkit.c`; Asahi `hw/soc/asc.md`): *documentation, names for
fields, not readings of what the firmware does*. A meaning marked *(guess)* is inferred from values
only. Messages are written as the 64-bit word; "SEND" is macOS to `pmp`, "RECV" `pmp` to macOS.

**Before any operating system** (`c3idle1`: the installed m1n1 proxy, no OS, 301 samples at 1 s).
The words `0x444/0x666/0x333`, +`0x44` 0, +`0x48` `0x2a`, PMP, PMS_SRAM, PMS `0x0f0000ff`; no change
in 300 s.

**Boot, up to the start** (det33, det34b; the SRAM block in full only in `135map4`, the address
translator in full only in `det10`). In this order:
1. `pmp`'s SRAM header (`0x23b500000`, ADT `/arm-io/pmp` reg 2, `0x80000` bytes): R +`0x20`-`0x5c`,
   +`0xc0`-`0xfc` (all 0), +`0x204`-`0x240`: +`0x204` `0x64697575` ("uuid"), +`0x208` 5, +`0x20c`
   `0x2a384`, +`0x210` `0x2f3a8`, four words, 0, 0, **+`0x22c` `0x3a800`, +`0x230` `0x2d0`**,
   +`0x234` `0x2c000`, 0, +`0x23c` `0x3b52c000`, +`0x240` 2 (all 32-bit, one pc).
2. The `0x2d0`-byte block at +`0x3a800` read (180 words), the header twice more, two strings
   (`RTKit-2062.141.1.release`, ...), then **the 180 words written back, every one the value read**
   (`135map4`; 54 tagged records, `STKG` ... `IOSZ`, listed in the evidence). Nothing else in
   `0x23b500000`-`0x23b53ffff` is written before the start (`135map4`); `0x23b540000` on (the end of
   `__DATA`) is logged in full in no boot.
3. The address translator `0x23b300000` (ADT `/arm-io/dart-pmp`: `sids` `0x8001`, `bypass`
   `0x8000`; `det10`): R +`0x0` `0x0ed01020`, +`0x4` `0x11037`, +`0x60` `0x80016100`; W +`0xfc` = 0;
   R +`0x80`-`0x8c`; W +`0xfc` = 0, W +`0x200` = 0, W +`0x2f0` = 0, W +`0x34` = `0xffffffff`, W +`0x20`
   = `0x100000`; R +`0x60`, +`0x68` `0xf0f0f`, +`0x6c` `0x80808` (the ADT's tunables already); W
   +`0x100` = `0x80`, W +`0x13c` = `0x100`; then W +`0x200` = `0x808217dc`, R +`0xfc` 0, W +`0xfc` = 1.
   Whether these last three come before or after the CPU start is not established (they arrive by
   another path than the start's record).
4. Mailbox I2A control +`0x8114`: R `0x20001`, W `0x20001`.
5. **+`0x44`: R 0, W `0x10`** (det33 t 2.6748, det34b 2.6018).
PMP, PMS_SRAM, PMS read `0x0f0000ff` at t 0.755 and `0x1f0f00ff`, `0x1f0000ff`, `0x1f0000ff` at the
first sample after the start (2.76); macOS's writes to them at boot are not logged (their page was
first touched at 0.43 s).

**RTKit start-up** (det33 = det34b word for word and in the same order; det10, `135map4` the same by
their first touches). Endpoint 0 unless said:

| Dir | Word | Decoded (reference names) |
|---|---|---|
| RECV | `0x00100000000c000c` | HELLO, version 12 |
| SEND | `0x00200000000c000c` | HELLO_REPLY 12 |
| RECV | `0x008000000000001f` | EPMAP base 0: endpoints 0-4, not last |
| SEND | `0x0050000100000002`, `0x0050000200000002`, `0x0050000300000002` | STARTEP 1, 2, 3 |
| SEND (ep 3) | `0x0008000000000000` | kdebug START; RECV (ep 3) `0x00010000000003e9` (GET_BUFFER, count `0x3e9`) |
| SEND | `0x0050000400000002`, `0x0080000000000001` | STARTEP 4; EPMAP reply, base 0, "more" |
| RECV | `0x0088000100000001` | EPMAP base 1: endpoint `0x20`, last |
| SEND (ep 3) | `0x0001000000004000`, `0x0002000000010000` | kdebug buffers at IOVA `0x4000`, `0x10000` |
| SEND | `0x0088000100000000` | EPMAP reply, base 1, last |
| RECV / SEND (ep 1) | `0x0010100000000000` / `0x0010400000018000` | crashlog request (1) / 4 at IOVA `0x18000` |
| RECV / SEND (ep 4) | `0x0011000000000000` / `0x0011000000020000` | ioreport request `0x10` / at IOVA `0x20000`; RECV `0x00c0000000000000`; type 8 (`0x0080000000000000`) echoed |
| RECV | `0x0070000000000020` | IOP power state `0x20`, **with no request sent** |
| SEND / RECV | `0x00b0000000000020` | AP power state `0x20`, echoed |
| RECV (ep 2) | `0x0080000050000010`, `0x0010100000000000` | syslog INIT (16 × `0x50`); request (1) |
| SEND (ep 2) | `0x0010100000034000` | syslog buffer at IOVA `0x34000` |
| SEND | `0x0050002000000002` | **STARTEP `0x20`** |

Endpoints started: 1, 2, 3, 4, `0x20` (the map lists 0-4 and `0x20` only). What the IOVAs map to,
and the buffers' contents, are in DRAM, which is not logged.

**Endpoint `0x20`** (det33, det34b; the same through the opening word for word):
- **Opening:** RECV `0x0`; SEND **`0x000100000003c000`** *(guess: a buffer at IOVA `0x3c000`)*;
  0.27 s (det33) / 0.59 s (det34b) later RECV **`0x000200000023b549`**, and macOS reads byte
  `0x23b549400` 1.4 ms later (`0x42`; that page of `pmp`'s `__DATA` holds 16-byte name slots `BAT`,
  `DRAM`, `ECPU`, `PCPU`, `ECORE0`-`3`, ..., `GPU SRAM` at +`0x400`-`0x55f` and 64-bit words at
  +`0x0`-`0xa0`, +`0x200`-`0x2a0`); SEND `0x0020000000010003` / RECV `0x0020100000010003`; SEND
  `0x0020200000010000` / RECV `0x0020300000010000`.
- **After it**, every word has bit 53 set and a code in bits 44-47. macOS sends even codes 0, 2, 4,
  8, `0xa`, `0xc`, `0xe`; `pmp` answers 0, 2, 4, 8, `0xa`, `0xc` with code + 1 and **never answers
  code `0xe`**. For codes 8, `0xa`, `0xc`, `0xe` bits 16-31 are always the id of a power-manager
  device the ADT flags `notify_pmp` (`0x54` DISP0_FE, `0x55` DISPEXT_FE, `0x5c` JPG, `0x63` GFX,
  `0x64` ISP_SYS, `0x65` VENC_SYS, `0x66` AVD_SYS, `0x68` ANE_SYS, `0xe3` ATC1_PCIE, `0x15c`
  ATC1_PCIE-V) *(guess: the device id; a match of numbers)*; for code `0xe` bits 0-15 are 0 or 1
  *(guess: off/on)*. The reference's power command (`pmp_power.rs`: device id at bit 40, enable at
  bit 32, ids 0-15) has another layout and cannot make these words (*documentation*).
- **At boot**, from t 3.06: code-`0xe` words for GFX, ANE_SYS, AVD_SYS, JPG, ISP_SYS, ATC1_PCIE,
  ATC1_PCIE-V, VENC_SYS, pairs 8/9, `0xa`/`0xb`, `0xc`/`0xd` (among them `0x0020a00000550023` /
  `0x0020b00000550023` at t 3.55), 36 code-4 pairs at t 24.7, then nothing on endpoint `0x20` from
  t 50.1 (det34b 49.16) to **`0x0020e00000550000` at t 69.38 (det34b 69.23)**, sent by core 0 with
  one 128-bit store of the word and its endpoint (round 11). No `…550001` precedes it at boot. After
  it **no `pmp` mailbox traffic at all** for the rest of both boot captures (to 207.9 s and 395.3 s).
- While running macOS echoes `pmp`'s endpoint-2 LOG (`0x0050000000000000`) and endpoint-4 type-8
  words.

**The words at boot** (det33, det34b, det35, det37; det36 below):
- Up to and including the first sample after the start (n 4): `0x444/0x666/0x333`, as the proxy.
- **The next sample** (n 5, 0.24-0.50 s later): **`0x444/0x444/0x444`** (05c000 `0x666` -> `0x444`,
  060000 `0x333` -> `0x444`; det36, det37: 05c000 by way of `0x555`); PMP `0x1f0f03ff`, PMS_SRAM
  `0x1f0003ff`. By receipt time everything of the start-up table and the opening's first two words
  came before n 4; the earliest `pmp` event common to both n 4 -> n 5 windows is RECV
  `0x000200000023b549`. Which event comes first in time is not resolved.
- To about 69 s: `0x444/0x444/0x444` with one-sample rises of the first two.
- **The first sample after `0x0020e00000550000`** (22-250 ms after it): **`0x333/0x444/0x222`**, and
  **PMP and PMS_SRAM read `0x1000030f` for the first time** (bit 28, actual state 0, bits 8-9 set:
  *(guess)* the domain gating itself under automatic control). No other endpoint-`0x20` message lies
  between that sample and the one before. Afterwards 060000 `0x222` in every sample; PMP alternates
  between `0x1f0f03ff` and `0x1000030f`.

**Idle and entry** (det33, detached; det18, det23 the same steps; det35, det37 the same messages):
- Idle: `0x333/0x444/0x222`; one endpoint-`0x20` word, `0x0020e00000540000` (det33 t 440.9; this is
  E1 item 5's message at the display's turn-off; 7.3-7.4 s before T in det33, det35-det37).
- The entry (det33, T = 448.2775): SEND `…550001`, `…540001` (T-0.816; the two in either order in
  the other captures); SEND `0x0020800000630000` / RECV `0x0020900000630000`; SEND **`…550000`**,
  `…540000` (T-0.799; either order). Round 10's evidence listed only the `…0001` pair. Then, 0.37 s
  later (T-0.432), R4's four management words (AP `0x201` echoed, IOP `0x201` acknowledged) and
  R5's stop: +`0x8114` `0x22201` -> `0x22200`, +`0x48` `0x2e`, +`0x44` `0x10` -> 0; the translator:
  R +`0x40`, +`0xfc` 1, +`0x100` `0x80`, W +`0xfc` = 0, R +`0x13c` `0x100`, R +`0xfc` 0, W +`0xfc` = 0,
  R +`0x40`, +`0x100c`; then **R6's 49,152 reads of `0x23b52c000`-`0x23b55bffc`** in order (pc
  `…ceac4`, the boot's SRAM-read pc), T-0.43 to T-0.13; then E5 item d's 12 64-bit reads at
  `0x23b549000`, `200`, `008`, `208`, `010`, `210`, `018`, `218`, `090`, `290`, `0a0`, `2a0` (T-0.017).
- No access to PMP, PMS_SRAM, PMS or the three words in idle or entry (full log). The words stay
  `0x333/0x444/0x222` through `pmp`'s stop and at the commit; after the stop +`0x44` 0, +`0x48`
  `0x2e`, PMP `0x1f0f03ff`.

**Wake** (det33; det18, det23 the same steps; det35 the same messages):

| W + | Access or reading |
|---|---|
| 0.0014 | first sample: **`0x333/0x555/0x333`**, +`0x44` 0, +`0x48` `0x2a`, PMP `0x0f0003ff`, PMS_SRAM `0x0f000300` (state 0), PMS `0x0f0002ff` (as the wake snapshot) |
| 0.0125-0.0138 | core 0's active actions (W1-2): PMP R `0x0f0003ff`, W `0x0f0000ff`, R, W `0x0f0000ff`, R, W `0x1f0000ff`; PMS_SRAM R `0x0f000300`, W `0x0f000000`, R ×3, W `0x0f00000f`, R `0x0f00030f`, R `0x0f0003ff`, W `0x1f00000f`; PMS R `0x0f0002ff`, W `0x0f0000ff` ×2 (with reads), W `0x1f0000ff` |
| 0.018 | the 12 64-bit words at `0x23b549000`+ written (W1-2h), the values E5 read |
| 0.146-0.355 | `pmp`'s wake action: **R6w's 49,152 writes, every byte the byte read at the entry** (196,608 of 196,608; pc `…cea64`); this replaces round 10's "24,576 writes", which counted the part after one sample |
| 0.355 | the translator: R +`0x0`, +`0x4`, +`0x60` `0x10000`, +`0xf0` 0; then R55's ten writes (+`0xfc` = 1, +`0x200` = `0x80822544`, ..., +`0x60` `0x80016100` (read `0x10000`), +`0x68` `0xf0f0f` (read `0x20202`), +`0x6c` `0x80808` (read 0), +`0x100` `0x80`, +`0x13c` `0x100`); +`0x8114` W `0x20001`; **+`0x44` R 0, W `0x10`** (the boot's pc) |
| 0.355-0.356 | RECV `0x00100000000c000c` / SEND `0x00200000000c000c`; RECV `0x008000000000001f` / **SEND `0x008000000000001f`**; RECV `0x0088000100000001` / **SEND `0x0088000100000001`** (the replies echo the map, unlike the boot's); RECV `0x0070000000000020` (unrequested, as at boot); SEND / RECV `0x00b0000000000020`. **No STARTEP, no buffer request on any endpoint, no endpoint-`0x20` opening** |
| 0.446-0.470 | endpoint `0x20`: SEND `…630001`, `…550001`, `…540001`, **`…550000`**, `…540000` |
| 0.502 | **`0x333/0x444/0x222`**, +`0x44` `0x10`, +`0x48` `0x2c`, PMP `0x1f0f03ff`; the same in every sample to the read-out (W+35.8) |

The order of the five wake words differs between captures (det18: `…630001`, `…540001`, `…550001`,
`…550000`, `…540000`; det23: `…630001`, `…550001`, `…540001`, `…540000`, `…550000`; det35-det37: `…540001`,
`…550001`, `…540000`, `…550000`): in all, `…630001` first and both `…0001` words before both
`…0000` words. In I the translator word written at the wake equals the one written at boot (W3); in
det33 the boot's value is not logged (det10's, another boot, is `0x808217dc`).

**Round 11: the message `0x0020e00000550000` dropped (det35, det36, det37) [HV-CHANGED].** The
instrument's option `hv_hold_msg` (m1n1 `~/m1n1-next` local commits `be2bd182`, `c2d99a4e`, not
pushed; off by default): a guest write of that value to the mailbox's send word `0x23bc08800`, and
the endpoint word at +8, is not made, so the message never enters `pmp`'s mailbox (not delayed:
dropped); the trace still records the store; each drop is counted, timed and logged (kind 30).
`hv_hold_where` = 1 drops only after a detached wake. det35's build matched only two separate
64-bit writes and dropped nothing (macOS's store is one 128-bit store), so det35 is a run with the
message sent. That the drops happened: the count (det36: 1 at the detach), a `hold` record per drop,
and the A2I control word `0x23bc08110` reading the same before and after each dropped send
(`0x28801`; `0x24401`) while it changed after every message sent.

| | det35 (sent) | det36 (dropped at boot, entry and wake) | det37 (dropped after the wake only) |
|---|---|---|---|
| boot: sample after the 0x55 send | `0x333/0x444/0x222`, PMP/PMS_SRAM `0x1000030f` (214 ms after) | **`0x444/0x444/0x444` to the end of the boot (481 samples, t 70-192)**; PMP `0x1f0f03ff`, PMS_SRAM `0x1f0003ff` in every sample; +`0x44` `0x10` | `0x333/0x444/0x222`, `0x1000030f` (72 ms after) |
| idle and entry | `0x333/0x444/0x222`; `0x1000030f` in 1336 of 1821 | 058000 `0x444` -> **`0x333` in the first sample after `0x0020e00000540000`** (t 447.65, the only endpoint-`0x20` word in that window; DISP0_FE's id); 060000 `0x444` -> **`0x222` in the first sample after `pmp`'s stop** (W +`0x44` = 0 at 454.512; the 0x55 word dropped at 454.220, before the sample before); PMP/PMS_SRAM never `0x1000030f` (1815 samples) | as det35 |
| commit snapshot (1328 words) | `0x333/0x444/0x222`, PMP `0x1f0f03ff` | **the same** (23 words differ from det35's, none of the three, PMP, PMS_SRAM or `pmp`'s) | the same |
| sleep | **powered down**, 89.62 s, alarm wake, status `0 / 0x400000 / 0` | **powered down**, 89.66 s, the same | **powered down**, 90.17 s, the same |
| wake: first sample | `0x333/0x555/0x333` | the same | the same |
| wake: sample after the 0x55 send or drop (22-42 ms) | **`0x333/0x444/0x222`**; 060000 `0x222` in 141 of 143 to the read-out; `0x1000030f` in 112 | **`0x333/0x444/0x444`** to the read-out (141 samples); PMP `0x1f0f03ff`, PMS_SRAM `0x1f0003ff`, never `0x1000030f` | **`0x333/0x444/0x444`**, the same |

The power chip after each run read det18's values; macOS reached the login window in all three.
Whether macOS waited for anything after the dropped word, its console, a delayed send and a drop at
the entry alone were not read.

**What it adds.**
- macOS's application processors still make no access to the three words (R70 holds in det33-det37).
- The words take one of four triples, and in these captures each change comes in the first sample
  after a `pmp` event: `0x444/0x666/0x333` with `pmp` never started (proxy; Linux, L27, L29);
  `0x444/0x444/0x444` after `pmp`'s start and opening (five boots); **`0x333/0x444/0x222` after
  `0x0020e00000550000` with `pmp` running** (four boots, two wakes), and in det36 also by two steps
  without it (058000 after `…540000`, 060000 after the stop); `0x333/0x555/0x333` across the sleep
  (`pmp` stopped, its SRAM's domain at state 0), and `0x333/0x444/0x444` after the restart without
  the 0x55 word (two wakes).
- **With the word dropped and `pmp` running, 060000 never reached `0x222` and PMP and PMS_SRAM never
  read `0x1000030f`** (one boot, two wakes); with it sent both came in the first sample after it
  (four boots, two wakes).
- **macOS's commit had `0x333/0x444/0x222` and the chip powered down with the 0x55 word dropped at
  boot and at the entry** (det36, one run).
**Limits.** Order of events, not cause: whether `pmp` itself, the always-on side on its behalf or
the hardware writes the words is not read, nor what the word means (*guess*: DISPEXT_FE's state to
`pmp`). 250 ms samples, so anything within one sample of the event goes with it. One run with the
drop at boot, two with it at the wake; one session; the drops are the instrument's act.

### 1.8 Access widths (all six captures)

Every logged access carries its width: macOS read or wrote the word as 8, 16, 32 or 64 bits.
`widths.py` collects, for every device address and direction, the widths seen in all six
captures (`widths.tsv`: address, direction, bits, the captures it was seen in, the count;
`widths-blocks.tsv`: the widths seen per 16 KiB page).

- 106,235 address-and-direction pairs were accessed: 105,344 only ever as 32 bits, 828 only as
  64 bits, 25 only as 16 bits, and 38 with two widths.
- **The width of a word is the same in every capture it appears in.** 38 pairs were accessed
  with two widths, the same two in every capture but for `0x23b549400`: thirteen words of the block at `0x23b549000`
  (`+0x000`, `008`, `010`, `018`, `090`, `0a0`, `200`, `208`, `210`, `218`, `290`, `2a0`:
  32 and 64 bits; and `+0x400`, read as 8 and as 32 bits, the 8-bit read in captures A and B
  only) and ten words of the PCIe blocks at `0x690000000` and `0x690100000`
  (16 and 32 bits). No other word was accessed with more than one width in any capture.
- 64-bit words are found in 175 of the 591 pages touched; 165 of those pages hold only 64-bit
  words. Among the blocks this document deals with: the memory controller's
  `0x200024000`, `0x200064000`, `0x2000a4000` pages (which hold `0x200024000`, `0x200024008`,
  `0x200027000`, `0x200067000`, `0x2000a7000`), `0x200158000`, a page of `DCS0`
  (`0x200204000`), each core's blocks at `0x21n054000`/`0x21n058000`, the cluster blocks at
  `0x210e20000`, `0x210e40000`-`0x210e48000`, `0x210e70000` and the same at `0x211e.....`,
  and the power-manager table blocks `0x23200c000`, `0x23400c000`. The full list is the file.
- `widths.tsv` has no line for a word the access log does not contain (the core start/stop
  words at `0x23b754000` and the guarded power-domain words): their width is not observed.
- What the machine does when a word is accessed with another width is not observed in the
  captures: macOS never did it. `[UNKNOWN]`
- *(Added this round, gap S6, open question 39.)* **`0x690000004`** (PCIe, E5-3): in all eight
  captures it is read as 32 bits (`0x100007`, T-0.49) and **written as 16 bits** (value 0) in
  E5-3; at the wake read as 32 bits (`0x100000`) and written as 32 bits (`0x100007`). The other
  E5-3 write of that block, `0x690000018` = 0, is 32 bits. **The guarded power words and the
  core start/stop words:** every access the hypervisor's hooks logged during macOS's boot and
  secondary-core start in I (46 guarded-word and 21 start-word records in `run-det10.out`) is
  32 bits. Their width during the entry and the wake is not recorded (the detached hypervisor
  writes a fixed width into those records).
- *(Added round 7, gap W9; `r7_pcie_widths.py`, `r7-pcie-widths.txt`.)* **The ten PCIe words with
  two widths, access by access** (D-I; the same in each of the six captures; value as read or
  written; times from T or W):

  | Word | Before the sleep (reads T-0.49 to T-0.48; the write T-0.041, E5-3) | After the wake (W+0.43 to W+0.66) |
  |---|---|---|
  | `0x690000000` | R32 `0x100c106b` (twice) | R16 `0x106b` |
  | `0x690000004` | R32 `0x100007`; **W16 `0x0`** (T-0.041) | R32 `0x100000`; W32 `0x100007` |
  | `0x690000044` | R32 `0x8` | R16 `0x8`; W32 `0x8` |
  | `0x690000058` | R32 `0x0` | W32 `0x0`; W16 `0x0` |
  | `0x690000078` | R32 `0x10081f`; R16 `0x81f` | R32 `0x102810`; W32 `0x100810`; W32 `0x10081f`; W16 `0x81f` |
  | `0x690000080` | R16 `0xc02` | R32 `0x10110000`; W32 `0x10110400`; W16 `0xc02` (twice); R32 `0xb0120c02`; R16 `0xc02` |
  | `0x690000098` | R16 `0x400` | W16 `0x400` (twice); R16 `0x0`; R32 `0x400`; W32 `0x400` |
  | `0x6900000a0` | R16 `0x42` | R16 `0x44`; W16 `0x42` (twice); R32 `0x2010042` |
  | `0x690000130` | (none) | W32 `0xff` (twice); R32 `0x0`; W16 `0x0` |
  | `0x6901000d4` | (none) | R32 `0x0`; W32 `0x400`; W16 `0x400` |

  So these words are read and written with both widths at fixed places of the sequence; a
  16-bit access touches the low half (the 16-bit values are the low halves of the 32-bit ones
  where both are read, e.g. `0x81f` / `0x10081f`). Every other word of the entry and the wake
  has one width (above). R49's "the width of a word never changed between reads and writes" is
  therefore stated for every word except these ten and the thirteen of `0x23b549000`; for these
  the width is the one in this table, per access.

### 1.9 The power domains when the platform sleep actions begin (captures D, E, F, G)

`ps_at_e3.py` gives, for each of the 137 power-domain control words of the power manager's
table, the value macOS has it at when phase E3 begins ("IOCPUSleepKernel enter"): the last value
read or written before that moment, else the idle snapshot taken before the entry
(`ps-at-e3.tsv`: address, name, the value in D, E, F, G, whether the requested state is the
same in all four, the source).

- 78 words are observed, 59 are not (never accessed and in no snapshot). For 77 of the 78 the
  requested state (low four bits) is the same in all four captures; `FPWM1` is on in D, E, G
  and off in F.
- Requested on (`0xf`) at E3 start, among others: `GPIO`, `SIO_BUSIF`, `SIO`, `SIO_CPU`
  (`0x1400024f`), `SPI_P`, `UART_P`, `UART_N`, `UART0`-`UART8`, `AUDIO_P`, `PMS_SRAM`
  (`0x1000030f`), `PMP` (`0x1000030f`), `ANS2` (`0x1f0023ff`), `DCS0`-`DCS7` (`0x1000030f`),
  `SEP` (`0x1000230f`). Requested off: `RMX`, `DISP0_FE`, `DISP0_CPU0`, `DISPEXT_FE`,
  `DISPEXT_CPU0`, `ATC1_COMMON`, `SIO_ADMA`, `FPWM0`, `FPWM2` and the others the file lists
  with request 0 (the display and second-port domains were set off in E1 and E2, R1, R7).
- The words the hypervisor guards for its own link (`SIO`, `SIO_BUSIF`, `UART_P`, `UART0`,
  artefacts A3, A4) are in this list with the values the snapshot read; what macOS itself asks
  for there is not observed.
- The platform sleep actions of E3 and E5 touch blocks in several of these domains (`sio`'s
  mailbox and translator, the pin controller, the temperature sensors, the `pmp` block).
- **Which block is in which domain** (gaps T2, T3). macOS's device tree names domains for a
  device in its `clock-gates` / `power-gates` properties, as numbers of the power manager's own
  table (`adt_domains.py`, `adt-domains.tsv`; 60 nodes carry them). For the blocks of sections
  3-6 it names: PCIe `apcie` (`0x690000000`, `0x680000000`, `0x681000000`.., `0x68c000000`, ...):
  APCIE, APCIE_GP, PCIE_REF; `dwi` (`0x23b200000`): DWI; `pmp` (`0x23bc00000`): PMP, PMS_SRAM;
  `sio` (`0x236400000`): a virtual domain `SIO-CPU-V`; `dart-sio` (`0x235004000`):
  `SIO-CPU-DART`; `ans`: APCIE_ST; `mca-switch` (the audio switch, `0x238400000`,
  `0x238300000`, `0x238500000`, and the clock word `0x23b0400d4` as its third register range):
  MCA0-MCA5; `admac-sio`: SIO_ADMA; `i2c0`, `i2c1`, `i2c3`, `spi1`-`spi4`, `uart0`, `uart2`,
  `fpwm` (FPWM1), `pwm` (FPWM0), `aes`: their own domains. `aop`, `sep`, `smc`, `dart-pmp`
  (`0x23b300000`) and `dispext0` carry the property with no value. **No domain is named** for the
  watchdogs, the SPMI controllers, the temperature sensors, the pin controllers, the NCO, the
  interrupt controller, the memory controller or the power manager's own blocks. That a block
  stops answering when its domain is off is not observed for macOS (macOS never accessed a block
  whose domain it had off); for Linux see section 12, L5.
- The device tree's power-manager table also lists four "perf-reg" ranges (`pmgr-devices.json`):
  `0x23b734000` and `0x23d2b4000` (0x100 bytes each), `0x23b77c000` and `0x23b778000` (0xa bytes
  each): the first words of the blocks R19 writes 0 and E5-8c reads out. It lists "pwrgate-reg"
  ranges at `0x23b71c010`, `0x23b71c310`, `0x23b71c610` (the words at `0x23b71c0d8`.. of section
  4 lie in the first). The blocks at `0x23b720000` and `0x23b748000` are in none of its tables.
- *(Added this round, gaps Q1, Q12; device-tree readings, `adt_domains.py`, `pmgr-devices.json`;
  what the device tree macOS was given says, not what macOS did.)* **Parents.** The power
  manager's table gives each domain its parents. For the domains this document deals with:
  DISP0_CPU0 <- DISP0_FE <- RMX; DISPEXT_CPU0 <- DISPEXT_FE <- RMX; DISPDFR_BE <- DISPDFR_FE <-
  RMX; MIPI_DSI <- DISPDFR_BE; ISP_SYS <- RMX; JPG, MSR, VENC_SYS, AVD_SYS <- MMX; SIO <-
  SIO_BUSIF; SIO_CPU <- SIO; I2C0-4, SPI_P, UART_P, AUDIO_P, AES <- SIO; SPI0-4 <- SIO, SPI_P;
  SIO_ADMA <- SIO, PMS; UART_N, UART0-8 <- UART_P; MCA0-5 <- AUDIO_P, SIO_ADMA; DPA0, DPA1 <-
  AUDIO_P; PMS_FPWM0-4 <- PMS; APCIE <- IMX; APCIE_GP <- APCIE; APCIE_ST <- ANS2, APCIE;
  ATC0_PCIE, ATC0_CIO <- ATC0_COMMON; ATC0_CIO_PCIE, ATC0_CIO_USB <- ATC0_CIO; ATC0_USB <-
  ATC0_USB_AON, ATC0_COMMON; the same for ATC1; DEBUG_USB, DEBUG_AUTH <- DEBUG; VENC_DMA <-
  VENC_SYS and below it VENC_PIPE4/5, VENC_ME0/1; ANE_SYS_CPU <- ANE_SYS. No parent: RMX, MMX,
  GFX, ANS2, PMP, PMS_SRAM, the DCS words, MCC, SBR, SMX, IMX, AIC, GPIO, DWI, MSG, SOC_SPMI0-2,
  the NUB words, ATC0_COMMON, ATC1_COMMON, ATC0/1_USB_AON. Every turn-off macOS made went child
  first (DISP0_CPU0, DISP0_FE, RMX; DISPEXT_CPU0, DISPEXT_FE; section 4.3) and the turn-ons of
  E2 parent first (RMX, DISP0_FE, DISP0_CPU0); the order of the wake's 138 writes against the
  table was not checked. The table's flags mark as "on" or "critical" (among others) SBR, PMS, PMS_BUSIF,
  IMX, MCC, SMX, the DCS words, PMP, PMS_SRAM, SEP, the NUB words, DEBUG and MSG.
  **Virtual domains** (no control word): `sio`'s `SIO-CPU-V` and `dart-sio`'s `SIO-CPU-DART`
  have parent SIO_CPU; `dcp`'s `DISP0_CPU0-V` parent DISP0_CPU0; `dcpext`'s `DISPEXT0_CPU0-V`
  parent DISPEXT_CPU0; `gfx-asc`'s `GFX-ASC` and `sgx`'s `GFX-SGX` parent GFX; `ANE-SYS-V`
  parent ANE_SYS. **Block sizes** (the node's register range): `dcp`, `dcpext`, `gfx-asc`,
  `ans`, `sio` coprocessor blocks `0x6c000` each (at `0x231c00000`, `0x271c00000`,
  `0x206400000`, `0x277400000`, `0x236400000`); `pmp` `0x60000` at `0x23bc00000`, and `pmp`'s
  register list also covers `0x23b500000` (+`0x80000`, which holds R6's `0x23b52c000`.. and
  `0x23b549000`), naming PMP and PMS_SRAM; `apcie` `0x690000000` (+`0x10000000`),
  `0x680000000` (+`0x4000`), `0x681000000` (+`0x8000`): APCIE, APCIE_GP, PCIE_REF;
  `dart-apcie0` `0x681008000` (+`0x4000`) carries no domain property; `dart-pmp` `0x23b300000`
  (+`0x4000`) carries the property with no value; `dart-sio` `0x235004000` (+`0x4000`):
  SIO-CPU-DART. R20's blocks `0x68c008000`, `0x234008000`, `0x279008000` lie in the power
  manager's own register ranges 41, 46, 47 (`0x68c000000`, `0x234000000`, `0x279000000`, each
  `0x1000000`), which name no domain; `0x279000000` is also `ans`'s fourth range (APCIE_ST).
  `mca-switch` `0x238400000` (+`0x18000`): MCA0-5. The temperature sensors, pin controllers,
  watchdog, SPMI controllers, NCO and interrupt controller carry no domain property. Which
  domain the blocks without one depend on is not observed.
- *Reference, not an observation* (round 7, gaps W6, W13): Aurora Silicon's Linux device tree
  for this chip (`aurora-silicon/linux`, `integration/aurora`, commit `dcce0e751c71`,
  `arch/arm64/boot/dts/apple/t8103.dtsi`) gives these blocks power domains: the display
  translators `dart-disp0` `0x231304000` and `dart-dcp` `0x23130c000`, `dcp` and its mailbox:
  DISP0_CPU0; `dart-dispext0` `0x271304000`, `dart-dcpext` `0x27130c000`, `dcpext`:
  DISPEXT_CPU0; `dart-sio` `0x235004000` and `sio`: SIO_CPU (`sio`'s mailbox: SIO);
  `dart-apcie0` `0x681008000` (and `0x682008000`, `0x683008000`) and PCIe: APCIE_GP; the
  interrupt controller: AIC; the pin controller `0x23c100000`: GPIO; the pin controller
  `0x23d1f0000` (R13's `0x23d1f0900`): NUB_GPIO; `gpu` `0x206400000`: GFX; NVMe/`ans`: ANS2 and
  APCIE_ST; `ans`'s mailbox: ANS2. It gives **none** to the watchdog `0x23d2b0000`, the SPMI
  controller `0x23d0d9300`, the NCO `0x23b044000`, the pin controllers `0x24a820000` (R13's
  `0x24a820900`) and `0x23e820000`, `aop`, `smc`, `sep` and their translators; it has no node
  for the temperature sensors, `dart-pmp` `0x23b300000` or R20's blocks. That a block of these
  is unreachable with its domain off is observed only under Linux, for `dart-sio` (section 12,
  L5).
- *(Added this round, gap Q14.)* **The 13 words on at the commit that are not observed at E3:**
  DWI, PMS_BUSIF, PCIE_REF, APCIE, DEBUG, NUB_SPMI0, NUB_SPMI1, NUB_AON, NUB_GPIO, NUB_FABRIC,
  NUB_SRAM, DEBUG_USB, DEBUG_AUTH. I's "awake-extra" snapshot (macOS awake, 431 s before T) has
  each at its commit value (DWI, APCIE, NUB_GPIO `0xff`; PMS_BUSIF, NUB_AON `0x1f0002ff`;
  PCIE_REF, NUB_SPMI0, NUB_SPMI1 `0x1400024f`; DEBUG `0x2ff`; NUB_FABRIC `0x1f0003ff`; NUB_SRAM,
  DEBUG_USB, DEBUG_AUTH `0x1000030f`), and no capture logs a write to any of them between the
  detach and T. So they are on with macOS awake and are not touched by the entry. macOS turning
  one of them on from off is seen only at the wake (section 4.3, W1-2c).

## 2. Idle

Windows used (`idle.py`, `idle_seq.py`; tables `idle-<A=3|B=4>-<pre|post>.tsv`): before the
sleep, A 215-295 s (80 s) and B 230-248 s (18 s); after the wake, A 1260-1380 s and B 630-760 s.
Total rate 22,448 /s (A) and 22,591 /s (B) before the sleep, 168 and 117 distinct (address,
direction) pairs. Rates below are per second, A / B, before the sleep.

**I1. Per-core cycle (about 80 % of all idle accesses).** Every core repeats:
`W 0x23bc34000` = 1 (cores 0-3) or 2 (cores 4-7); `W` its cluster word = 0; `W 0x23bc34000`
again; `R` cluster block +`0x588` (reads 0); `R` cluster block +`0x020` twice (reads
`0x40000101101`); `W` its cluster word = 1. The cluster word is `0x23b738004` for cores 0-3 and
`0x23b738008` for cores 4-7; the cluster block is `0x210e20000` for cores 0-3 and `0x211e20000`
for cores 4-7. A short form, `W 0x23bc34000` then `W` cluster word = 1, is the most common on
core 0 (63,802 of 77,347 cycles in A). Rates: `0x23bc34000` 5,925 / 5,974 writes;
`0x23b738004` 2,815 / 2,839; `0x23b738008` 3,110 / 3,135; `0x210e20020` 2,815 / 2,839;
`0x211e20020` 3,110 / 3,135; +`0x588` half of those. What the cycle means (entering or leaving
a core idle state) is not established.

**I2. Timer block.** Cores 0-3 read `0x23b734004` 136 / 136 times a second (a changing value)
and `0x23b734008` 272 / 272 (reads 1).

**I3. Interrupt controller.** `R 0x23b102004` 163 / 158 on all cores; writes to mask words
`0x23b1041a4`..`0x23b1041d8` that follow the coprocessor traffic below.

**I4. Coprocessor mailboxes.** Messages sent per second: graphics `0x206408800` 135.6 / 131.5;
`smc` `0x23e408800` 33.6 / 32.4 (sensor and battery key reads; value buffer at `0x23fe5e000`,
an address with no device-tree entry, labelled SMC shared memory by `s2r_decode.py`); internal
display `0x231c08800` 25.2 / 26.3; `aop` replies read 2.6 / 2.6.

**I5. Memory-controller burst.** 1.80 / 1.78 times a second, from any of cores 0-3 (A: 43, 42,
32, 27 bursts on cores 0, 1, 2, 3), always these five writes: `0x20010000c`=1, `0x200100014`=1,
`0x200014050`=2, `0x20010000c`=0, `0x200100014`=0. Median gap 0.565 / 0.567 s.

**I6. Graphics pair.** 7.2 / 7.1 times a second: `R` then `W 0x204d14000` = `0x70001`, and `R`
then `W 0x23d2dc100` = `0x100`.

**I7. Slow polls** (0.3-9 /s): temperature sensors (`0x23b280000`.., `0x23b298000`,
`0x23b2a0000`, `0x23b2c4000`.., `0x23b2e0000`, and `0x210000000`, `0x211000000`); `0x23d2a8000`
and `0x23d2a8004` (1 and 2 /s); storage (`0x27bcc0000`.., `0x27bce4910`, `0x27bce8118`);
the PCIe port (`0x681000004`..`0x681000108`) and a PCIe device's own registers at `0x6c0c02140`;
the power chip's clock (SPMI read of register `0xd002`, 0.35 /s).

**I8. Console** `[ARTEFACT A1]`: `0x23d12c004` writes, `0x23d12c014`/`018` reads.

**After the wake the idle is not the same in the two captures** (`idle.py`, `backtoidle.py`).
Capture B (key press) returns to all of I1-I8 and adds polling of a second SPMI controller
`0x24a829300`.. (about 13 reads a second). Capture A (alarm) never shows I5, I6, or any
graphics, internal-display or `aop` mailbox traffic in the 163 s recorded; instead it reads
`0x23d2b9040`-`0x23d2b9070` once a second. I1-I3 continue in both. In capture A the display
was not seen to come back (no "ON" console line; B has "FB0 ... OFF to ON" at W+4.50).

**Capture D** (`det_misc.py`; idle 20-200 s after detaching): I1 cannot be seen (untrapped
pages). I2: 136.0 and 272.0 a second, as in A and B. I4: graphics 146.1, `smc` 34.2, display
25.9 messages a second. I5: the same five writes 1.81 times a second on cores 0-3, median gap
0.561 s. I6: 7.21 a second. I7 as before. So I2 and I4-I7 are the same in all three captures.
One difference: in A and B every core reads `0x23b102004` (I3); in D core 0 does (36,900 of
36,938 reads in 200 s) and cores 4-7 make **no** logged access at all in 210 s of idle. Whether
the reads on the other cores in A and B were caused by the host being attached is not known.
After the wake D behaves like B (key press): display on at W+0.52, I5 back from W+0.66 at
1.92 a second, no access outside the idle set from W+6.

**Captures E and F** (`DET=e IDLE=2,38 det_misc.py`, `DET=f IDLE=20,180 det_misc.py`): F's idle
(160 s, cable in) equals D's: I2 136.0 / 272.0, I5 1.80 a second with median gap 0.561 s, I6
7.18 a second. E's idle window is the first 38 s after detaching and busier (display mailbox
104, graphics 64 messages a second, I6 12.4 a second); I2 and I5 (1.89 a second, gap 0.559 s)
are the same. In both, cores 4-7 make no logged access during idle, as in D. With the cable
out (E from 40 s, F from 188 s) the idle patterns I2-I7 continue unchanged; what the cable
events themselves cause is in section 10.

**Capture G** (430 s of idle; `DET=g IDLE=20,400 det_misc.py`): I2 136.0 a second; I5 the same
five writes 2.09 times a second (median gap 0.552 s); cores 4-7 silent as in D, E, F; core 0
makes 115,377 of the 115,402 reads of `0x23b102004`. macOS then goes to sleep by itself.

## 3. Sleep entry

Phases are named E0-E6. Times are A / B relative to T. "Console" means the line appears in
macOS's console at that point (`console.py`, `console-N-pre.txt`). Phase extracts:
`entry-early-N.tsv` (E1, E2), `phases-pre-N.tsv` (E3-E5), `ps-pre-N.tsv` (power-domain writes),
`mbox-pre-N.txt` and `spmi-pre-N.txt` (decoded messages), `devtable-pre.tsv`.

**Times in the three captures** (`det_misc.py`, `phase-times.tsv`; seconds before each
capture's own T; A's and B's T is early by an unknown few milliseconds, D's times are the
machine's own clock):

| Console marker | A | B | D | E | F |
|---|---|---|---|---|---|
| display "ON to OFF" request (E1) | -10.397 | -10.383 | -7.409 | -7.309 | -7.376 |
| "PM response took ... powerd" (E2 starts) | -3.683 | -3.590 | -0.909 | -0.809 | -0.878 |
| "IOCPUSleepKernel enter" (E3 starts) | -2.603 | -2.590 | -0.484 | -0.486 | -0.485 |
| PMP sleep action | -2.433 | -2.430 | -0.438 | -0.439 | -0.439 |
| first address-translator sleep action | -0.386 | -0.389 | -0.123 | -0.126 | -0.125 |
| first quiesce action (E5 starts) | -0.257 | -0.258 | -0.089 | -0.091 | -0.090 |
| memory-controller quiesce | -0.102 | -0.102 | -0.031 | -0.030 | -0.030 |
| power-manager quiesce | -0.068 | -0.069 | -0.022 | -0.022 | -0.022 |
| interrupt-controller quiesce | -0.024 | -0.024 | -0.016 | -0.016 | -0.016 |

The three detached captures agree with each other to about 2 ms from "IOCPUSleepKernel enter"
on, cable in or out. E1 starts 0.09 s before the display request ("awdl0 disable": -10.498,
-10.505, -7.501, -7.397, -7.471; F has an earlier one at -15.219, section 11.1).
E1 lasts 6.8 / 6.9 / 6.6 / 6.6 / 6.6 s: it is waiting, not register work. Everything after
it is 3 to 6 times shorter in D. In D the operator's first input (E0) is at T-10.134, the last
memory-controller burst at T-7.439, the display domains go off at T-7.255.

**Capture G's times** (same markers, seconds before T): display request -7.478; "PM response"
-0.865; "IOCPUSleepKernel enter" -0.474; PMP sleep action -0.427; first address-translator
action -0.127; first quiesce action -0.091; memory-controller quiesce -0.030; power-manager
quiesce -0.022; interrupt-controller quiesce -0.016: within 10 ms of D, E, F throughout.

**Idle sleep (G) against clicked sleep (A, B, D, E, F).** What differs:
- there is no E0: no trackpad traffic (283 writes to the SPI3 block in the last 30 s against
  11,179 in D);
- the first sign is the audio path, 60 ms before the display request: console "Set PowerStage
  (4 -> 6)", "(6 -> 7)", "(7 -> 1)" for both audio devices at T-7.554 to T-7.514, with the 621
  writes to `i2c3` that the clicked captures make in E2 (T-0.7 in D); in E2 only "(1 -> 0)"
  remains (T-0.697). In the clicked captures the stages go 4 -> 5 -> 0, all in E2;
- the display request (T-7.478) comes before "awdl0 disable" (T-7.470); in the clicked captures
  the other way round;
- the last memory-controller burst is at T-7.504, 26 ms **before** the display request (after
  it by up to 30 ms in the others).
What does not differ: E1 lasts the same 6.6 s ("PM response took 1585 ms"); the 33 non-bus
domain writes and their values (display pairs turned on again in A's order); the `smc` keys
(`MBSE`=`0x736c7077` T-0.846, `WKTP`=2 T-0.758, `MBSE`=`0x736c7061` T-0.464); the coprocessor
shutdown exchanges; E3 (36 of 42 actions with ordered writes identical to A's, 38 to D's); the
33 quiesce actions before the interrupt controller (ordered writes identical to all other
captures); the last steps E6 (identical to D access for access in the interrupt-controller
action; power-chip actions in F's order; alarm bytes `85 c1 08 00`, about 975 s after T by the
inference of E6); the core stop order. `reqcheck.py`: all 71 values hold in G.
**Capture H** (the second idle sleep) repeats every point of this list: audio "Set PowerStage
(4 -> 6)" at T-7.558 to "(7 -> 1)" at T-7.517, display request T-7.488, "awdl0 disable"
T-7.480, last memory-controller burst T-7.508 (20 ms before the display request), "PM response
took 1578 ms" T-0.877, "(1 -> 0)" T-0.710; E1 starts with the audio path in both idle sleeps
and with "awdl0 disable" or the display request in the four clicked ones. Alarm bytes in H:
`d8 41 09 00`. Idle before it (20-400 s after the detach): I5 1.82 a second, cores 4-7 make
no logged access.

### E0. Operator input (T-16.6 / T-18.1 to about T-10.5): not part of the sleep

The first access that differs from idle (`firstdiff.py`) is in both captures `R 0x23d1f0980`
(`nub-gpio`), `W 0x23d1f0034`=`0x66a01`, `W 0x23d1f0980`=`0x2000`, then the SPI3 domain
`0x23b700258` cycled on and off around bursts on `spi3` (`0x23510c000`) and `sio` mailbox
traffic (A: i = 3,191,921; B: i = 1,780,143). This is the trackpad being used to click Sleep:
8,052 / 11,476 SPI3 domain writes in the last 20 s, a count that follows the operator, not
macOS's sleep. During
it `0x200021004`=`0x4000000` is written about every 0.6 s (A from T-15.8, B from T-17.4, to
T-10.3). The interval from the click to phase E1 is not determinable from the captures.
*(Added this round, gap Q10.)* Every write of `0x4000000` to a plane's P+`0x21004`
(`0x200021004`, `0x200061004`, `0x2000a1004`, `0x2000e1004`), in all eight captures, before the
sleep and after the wake (60 to 171 per capture), follows a read of that word returning
`0x4000000`, is the value read, and is followed by a read returning 0 (in A and B four times
`0x4000000` again): the bit is set by the hardware and macOS clears it by writing it back, at
no fixed point of the entry or the wake (after the wake in H and I: W+0.66 to W+11.7, core 0).

### E1. Display off and user-space notification (T-10.50 / T-10.51 to T-3.68 / T-3.59)

Console: "interface awdl0 disable" (T-10.498 / T-10.505), "FB0 Api power state transition
request from ON to OFF" (T-10.397 / T-10.383), display coprocessor messages to T-9.96, then
nothing sleep-related until "PM response took 1581 ms (85, powerd)" (T-3.683; B: 1587 ms,
T-3.590). Several cores run at once; order between devices varies (`compare.py pre -10.6 -3.7`:
45 pages written, 15 with identical ordered writes).

In order of first appearance (A):
1. T-10.50: PWM block `fpwm` `0x235044018`/`01c` ramped (75 / 90 writes to T-9.86); power
   chip clock reads; `aop` endpoint `0x24` messages `0xa2..`/`0x85..`.
2. T-10.42: **last memory-controller burst (I5)** at T-10.417 / T-10.407. It does not occur
   again before the sleep.
3. T-10.3 to T-9.95: internal display coprocessor shut down over its mailbox (167 / 177 words
   written to `0x231c08000`), its address translator `0x231304000`, `0x23130c000`.
4. T-9.946 / T-9.944: power domains off, in this order (identical in both): DISP0_CPU0
   `0x23b710018` `0x0f0400ff` then `0x0f0403f0` (reads settle at `0x0f040300`); DISP0_FE
   `0x23b700360`=`0x23f0` (reads `0x2100` then `0x2300`); RMX `0x23b700350`=`0xf` then `0x300`.
5. T-9.95: `pmp` endpoint `0x20` message `0x0020e00000540000` (sent without waiting for a reply).
6. T-9.86 to T-9.84: SPMI: clock read (`0xd002`), two 6-byte writes to power-chip register
   `0xd100`, clock read again. `smc` key `tGAM` written (4 bytes).
7. T-9.8 to T-3.7: idle patterns I1-I4, I7 continue; graphics mailbox traffic continues to
   T-3.3. Storage coprocessor receives one endpoint-2 message at T-5.77 (A only, with 10 writes
   to `0x27bc50030`/`070`); `sep` exchanges 4 management words at T-5.29 (A) / T-5.2 (B).
The `0x23bc34000` write rate drops to about a quarter between T-14 and T-10 and again in the
last 4 s (`leadcheck.py`: writes per second in 2 s bins from T-24, A: 5952, 5736, 5979, 5076, 4187,
1885, 1337, 5864, 5814, 5660, 2465, 519).

### E2. Drivers power down (T-3.68 / T-3.59 to T-2.60 / T-2.59)

Console in order: USB-C port "set PowerModeOff", "DK: allowPowerChange", secure-enclave
endpoints disabled, `smc` "going to sleep -> writing WKTP=2", audio amplifiers and codec to
power stage 0, Wi-Fi "Link Down on ap1", `aop` "sleep notification", "AppleSEPManager power
state 2 -> 0", "NVMe shutdown start". Several cores; 51 pages written, 29 with identical ordered
writes, 34 with the same write addresses in order (`compare.py pre -3.7 -2.605`).

Per coprocessor, messages in order (identical sequences in both captures unless noted;
`mbox-pre-N.txt`):
- **`smc`** (`0x23e400000`): key writes `MBSE` = `0x736c7077` (the characters "slpw"; stored
  low byte first) at T-3.619 / T-3.522; `WKTP` = `02` at T-3.297 / T-3.249; `MBSE` =
  `0x736c7061` ("slpa") at T-2.570 / T-2.557 (this one is in E3). Key reads continue in between (`smcw.py`). Same 13 messages in
  both from T-3.7; order of concurrent reads differs.
- **`aop`** (`0x24a400000`): `0x00a4000000000000` to endpoints `0x22`, `0x21`, `0x26`, `0x20`,
  `0x28`, `0x25`, `0x24`, `0x27`, each answered `0x0087000000000000` (T-3.37 to T-3.08); two
  endpoint-2 words echoed; then management "AP power state `0x201`", echoed (T-3.071). Same
  messages in both; order of the endpoint messages differs.
- **`gfx-asc`** (`0x206400000`): "AP power `0x201`" echoed, "coprocessor power `0x201`"
  acknowledged (T-3.310 to T-3.298); then domain GFX `0x23b7003f8`: `0x0f0020ff`, `0x0f0023f0`
  (settles `0x0f002300`) at T-3.279 / T-3.218.
- **`dcp`** and **`dcpext`** (`0x231c00000`, `0x271c00000`): at T-3.33 their domains are turned
  **on** again (RMX `0x0f000000`, `0x0f00000f`, `0x1f00000f`; DISP0_FE `0x2000`, `0x200f`,
  `0x1000200f`; DISP0_CPU0 `0x0f040000`, `0x0f04000f`, `0x1f04000f`; DISPEXT_FE and
  DISPEXT_CPU0 `0x23b700368`, `0x23b700378` likewise), each coprocessor boots (hello, endpoint
  map, power acknowledgements), 13 endpoints are started (`0x00a3..` / `0x0086..`), three
  endpoint-`0x37` exchanges, then "AP power `0x201`", 13 endpoint stops (`0x00a4..` /
  `0x0087..`), "coprocessor power `0x201`" acknowledged; then the domains go off: DISPEXT_CPU0
  `0x0f0400ff`, `0x0f0403f0`; DISPEXT_FE `0x23f0`; DISP0_CPU0 same; DISP0_FE `0x23f0`; RMX `0xf`,
  `0x300` (T-3.141 to T-3.130 / T-3.079 to T-3.072). `dcpext`: 36 sent and 37 received words,
  identical in both. `dcp`: 37 / 38, identical in both.
- **`pmp`** (`0x23bc00000`): endpoint-`0x20` words `0x0020e00000540001`, `..550001`,
  `0x0020800000630000` (answered `0x0020900000630000`), `0x0020e00000550000`, `..540000`.
- **`sep`** (`0x242400000`): one word each way at T-2.85 / T-2.72 (`0x020c0800` sent in A,
  `0x020c0700` in B).
- **`ans`** (`0x277400000`): two endpoint-2 words echoed, "AP power `0x201`" echoed,
  "coprocessor power `0x201`" acknowledged (T-2.786 to T-2.763); then domain APCIE_ST
  `0x23b700418`: `0x0f0000ff`, `0x0f0003f0` (settles `0x0f000200`) at T-2.762 / T-2.661.
Buses: `i2c0` 96 writes, `i2c3` 621 writes, `spi2` 15 writes (identical ordered writes in both),
each inside on/off cycles of its domain word (I2C0 `0x23b7001f0`, I2C3 `0x23b700208`, SPI2
`0x23b700250`: `0x0`, `0xf`, `0x1000000f` ... `0x3f0`). Blocks `0x225000000`/`4000`/`8000`
(14, 11, 6 writes), `0x232000000`/`8000` and `0x272000000`/`8000` (25 + 40 writes each),
`0x205008000`: identical in both.

### E2a. How a coprocessor is stopped before its domain goes off (D-I; added this round, gaps Q1, Q11)

Re-read from the access logs of D-I (`coproc_stop.py`, `mbox-pre-h.txt`, `mbox-pre-i.txt`).
Every coprocessor whose domain macOS turns off in E1 or E2 is stopped the same
way, and the same as `sio` and `pmp` in E3 (R5):
1. **Management and endpoint messages** (mailbox +`0x8800`/+`0x8808`, replies +`0x8830`/
   +`0x8838`, section 0): "AP power `0x201`" (`0x00b0000000000201`, endpoint 0) sent and echoed;
   for `dcp` and `dcpext` an "endpoint stop" `0x00a4000000000000` to each of endpoints `0x20`
   to `0x2c` in turn, each answered `0x0087000000000000`; then "coprocessor power `0x201`"
   (`0x0060000000000201`) sent and acknowledged (`0x0070000000000201`, round 7). `gfx-asc` and `ans`
   get only the two power messages (H: `mbox-pre-h.txt`).
2. **Register stop**, immediately after the acknowledgement: +`0x8114` read (in the bit-17
   form with bit 0 set) and written that value with bit 0 cleared (*corrected round 7, gap W7:
   the values given here are those written*; I: `dcp` read `0x24401`, written `0x24400`; E2
   read `0x26601`, written `0x26600`; `dcpext` read `0x25501`, written `0x25500`; `gfx-asc` read
   `0x21101`, written `0x21100`; `ans` read `0x24401`, written `0x24400`; written in other
   captures: `dcp` `0x2ff00` D, G, `0x27700` H),
   +`0x48` read (`0x2e` in every instance), +`0x44` read (`0x10`), **+`0x44` written 0**. For
   `dcp` (base `0x231c00000`), `dcpext` (`0x271c00000`), `gfx-asc` (`0x206400000`), `ans`
   (`0x277400000`), in each of D-I; 30 instances, no exception (the rule on +`0x8114` checked on
   every write: value read with bit 0 cleared).
3. **Address translators** of the display. *(Corrected and completed round 7, gap W6;
   `r7_dart_disp.py`, `r7_dart_rule.py`, `r7-dart-rule.txt`.)* Every write of +`0xfc` on the
   four display translators in D-I (105 writes) is either `0x7fff` (at each restart, below) or
   **the value of the last read of +`0xfc` with one bit s cleared, where s is the stream whose
   word +`0x100`+4s was read just before** (no exception):
   - `dart-disp0` `0x2313040fc`, E1 only, before step 1 (T-7.37 in I, between `dcp`'s
     endpoint-`0x37` exchanges and its "AP power `0x201`"): R +`0x40` (`0xa040000`), then for
     s = 0, 4, 15: R +`0x100`+4s (`0x80`, `0x80`, `0x100`), R +`0xfc`, W +`0xfc` with bit s
     cleared: `0x7fff` -> `0x7ffe` -> `0x7fee` -> `0x7fee` (bit 15 already clear); then R +`0x40`,
     +`0x100c`. Not written again before T: it is written `0x7fff` only after the key wakes (D,
     E, F, W+0.51), and not at all after the alarm wakes.
   - `dart-dcp` `0x23130c0fc`, straight after **every** stop of `dcp` (E1, E2 and the wake's,
     below): R +`0x40`, then for s = 0, 15: R +`0x100`+4s (`0x80`, `0x100`), R +`0xfc`, W:
     `0x7fff` -> `0x7ffe` -> `0x7ffe`; then R +`0x40`, +`0x100c`. **The E2 stop has them too**
     (T-0.739 in I; the earlier text said E2 had neither: withdrawn).
   - `dart-dcpext` `0x27130c0fc`: the same after every stop of `dcpext` (E2, wake).
   - At each restart of `dcp` and `dcpext` (E2 and the wake), before +`0x44` = `0x10`: their
     translator's +`0x0`, +`0x4`, +`0x60`, +`0xf0`, +`0x80`-`0x8c` read, **+`0xfc` = `0x7fff`**,
     +`0x200` and +`0x2f0` read, **+`0x34` = `0xffffffff`, +`0x20` = `0x100000`**, +`0x20` read
     back `0x100000`, +`0x100`, +`0x13c` read.
   The values read before these writes are the same in every capture (`0x7fff` before the first
   clear; +`0x100` `0x80`; +`0x13c` `0x100`). What `dart-disp0`, `dart-dcp`, `dart-dcpext` hold
   under Linux is not read. *Reference, not an observation:* Aurora Silicon's
   `drivers/iommu/apple-dart.c` (`integration/aurora`, `dcce0e751c71`) names, for this kind of
   translator, +`0xfc` "streams enable" (one bit per stream), +`0x100`+4s the stream's control
   word (bit 7 "translate enable", bit 8 "bypass"), +`0x200`+4s its table base (bit 31 valid,
   address >> 12), +`0x34` "stream select", +`0x20` "stream command" (bit 20 "invalidate"),
   +`0x40` error status, +`0x60` config.
4. **Then the domains** (section 4.3): `dcp`'s DISP0_CPU0, DISP0_FE, RMX at T-7.33 (H, I),
   0.4 ms after +`0x44` = 0; in E2, after each coprocessor's step 2: DISPEXT_CPU0, DISPEXT_FE;
   DISP0_CPU0, DISP0_FE, RMX; GFX; APCIE_ST.
**Restart in E2** (`dcp` and `dcpext`, before their second stop): after their domains are
turned on, +`0x8114` written `0x20001`, +`0x44` read **0** and written `0x10`, then the
coprocessor's hello is read: the same as `sio`'s and `pmp`'s start after the wake (R5w).
*(Round 7: the translator writes of item 3 come before +`0x8114` = `0x20001` at every restart,
in D-I; 18 restarts of `dcp`, 12 of `dcpext`, before and after the wake.)*
**The exchange of step 1, message by message** *(added round 7, gap W7; `r7_stops.py`,
`r7-stops.txt`, `r7_mbox_seq.py`).* Over all 76 stops of the six coprocessors in all eight
captures (each write of +`0x44` = 0: 28 of `dcp`, 16 of `dcpext`, 8 each of `gfx-asc`, `ans`,
`sio`, `pmp`, before the sleep and after the wake), from the last "AP power `0x201`" to +`0x44`
= 0, the sequence is, without exception:
- sent `0x00b0000000000201` on endpoint 0; received `0x00b0000000000201` on endpoint 0;
- for `dcp` and `dcpext` only: sent `0x00a4000000000000` on endpoint `0x20`, then `0x21`, ...,
  `0x2c` (ascending, 13 endpoints), **each answered `0x0087000000000000` received on the same
  endpoint before the next is sent** (44 of 44 stops strictly alternating);
- sent `0x0060000000000201` on endpoint 0; received **`0x0070000000000201`** on endpoint 0;
- +`0x8114` read, written with bit 0 cleared; +`0x48` read `0x2e`; +`0x44` read `0x10`; +`0x44`
  written 0.
The only other message inside this span: in E and F (cable out) `dcp`'s E1 stop also has
`0x0040000000000000` sent and echoed on endpoint 4 between the two "AP power" words (open
question 20). Between messages macOS reads +`0x8114` (before each reply it reads with bit 20 set,
section 0). How long macOS waits for a reply before giving up is not observed (open question 38).
**The endpoints being stopped were all started by macOS**: in E1, `dcp` has been running since
before the log begins (+`0x44` `0x10`) and receives `0x0085..` words on endpoints among
`0x20`-`0x2c` just before the stop (I: `0x24`, `0x27`-`0x29`, `0x2b`), their starts lying before
the log; in E2 and at the wake the 13 stops follow 13 starts
`0x00a3000000000000` on endpoints `0x20`-`0x2c` (each answered `0x0086..`) made after the
coprocessor's boot (I: W+0.4590 to W+0.4608 starts, W+0.4629 to W+0.4660 stops). A stop sent to
an endpoint that was not started, and a stop of a coprocessor that macOS did not boot, are in no
capture.
**`dcpext` with macOS awake is stopped, with its domains off** *(added round 7; snapshots of
all eight captures, `r7_coproc_words.py`)*: DISPEXT_CPU0 reads `0x0f040300` and DISPEXT_FE
`0x2300` in every awake snapshot (15), and the first access to `dcpext`'s +`0x44` in each
capture is the read of **0** before its E2 restart. So macOS boots `dcpext` in E2 only to stop
it again (E2 above); it has no external display at the login window. **`dcp` with macOS awake
runs**: its first +`0x44` read in each capture is `0x10`, in E1.
**What the messages carry.** Before step 1, `dcp`'s E1 traffic (T-8.5 to T-7.33) is endpoint
`0x37` and `0x02` words (`0x0000003c00000202`, `0x0000189c00000202`, `0x342`, `0x42`,
`0x005000000000002c`..`3a`, ...) whose payloads are in shared memory that the log does not
contain; what they ask the coprocessor to do cannot be read from the captures. The same holds
for `gfx-asc`'s endpoint `0x20`/`0x21` traffic. What a coprocessor does if step 1 is skipped,
or if it is stopped by step 2 alone, is **not observed**.
**DISP0_CPU0 (`0x23b710018`) through this** (gap Q1(b); also run ds14, section 12 L13). Its
value with macOS awake, in the 15 awake snapshots of all eight captures: `0x1404024f` in 10,
`0x1404034f` in E's two, `0x1f0402ff` in D's, G's and I's "pre-full": the state bits 4-7 read
4 or `0xf` and bits 24-27 `0x4` or `0xf` with macOS awake, varying, with no write by macOS to
the word in any log. macOS's first access to it in the entry is the read just after `dcp`'s
step 2 (T-7.33): `0x1f0402ff` in seven captures, `0x1f0403ff` in E. So macOS's turn-off of
this word was always made from state `0xf` with bit 28 set; it was never seen to write the word
while it read state 4, and what the word does when it is asked for 0 from state 4 is not
observed under macOS.
*(Added round 7, gaps W2, W14; `r7_bit28.py`, `r7-bit28.txt`.)* **What clearing bit 28 does,
as observed.** Every write in D-I that clears bit 28 of a word read with bit 28 set and request
`0xf`, keeping the request (72 writes): the first read after it (3 to 491 microseconds later)
reports state `0xf` and bits 24-27 `0xf` in every instance that has a read (66). The state read
**before** such a write was `0xf` for DISP0_CPU0 (21), DISPEXT_CPU0 (12), GFX (6), APCIE_ST (6),
and **0 for RMX** (21 instances, R `0x1000030f` W `0xf` R `0x0f0003ff`, before the sleep and at
the wake). From state 4 the write is seen only for SIO_CPU (R23, R `0x1400024f` W
`0x0400024f`, 6 instances), and no read follows it before the commit, where SIO_CPU reads
`0x0f0002ff`. So a bit-28 clear taking a word to state `0xf` is observed from state `0xf` and
from state 0; **from state 4 the word's next value is not observed** (open question 43). That
`dcp`'s stop is what brings DISP0_CPU0 from state 4 to `0xf` is not shown either: in the three
awake snapshots where the word reads `0x1f0402ff`, `dcp` runs (its +`0x44` reads `0x10` at its
first access, in E1, minutes later; the word reads `0x1404024f` in the other awake snapshots
of the same runs with `dcp` equally running). Under Linux the word reads `0x1404024f` with `dcp`
running (+`0x44` = `0x10`) both with the display on and in the suspend path (section 12, L14,
L15). *Reference, not an observation:* section 0, the Aurora driver's reading of bit 28 as
automatic power management and its comment on the M4 DCP CPU domain.

### E3. Kernel sleep path, part 1: "sleep actions" (T-2.603 / T-2.590 to T-0.27)

Console "IOCPUSleepKernel enter", then 42 lines "IOPlatformSleepAction -> driver". All cores
still run; the idle patterns continue around it. The order of the actions is not identical in
the two captures (the three SPMI controllers come before the I2C controllers in B, after in A).
Segments by console marker (`phases.py pre`, `phases-pre-compare.tsv`): 42 segments, 34
identical access for access, 36 with identical ordered writes. What each does to hardware:

| Action | Observed (A / B identical unless said) |
|---|---|
| AppleDialogSPMIPMURTC, AppleAVD | nothing attributable |
| AppleSMCPMU | `smc`: key `MBSE`="slpa" written; reply result 0 |
| AppleSMC | `smc` management: "AP power `0x201`" sent, echoed. No further `smc` message before T |
| AppleARMWatchdogTimer | `W 0x23d2b0000`=0, `W 0x23d2b0010`=0. In the same interval, SPMI: write power-chip register `0x9f01`=`0x50`, then reads of `0x9f01` (`50`), `0x9f08` (`00000000`), `0x9f02` (`00`), `0x9f18` (`00`), `0x9f19` (`00 04`), `0x9f00` (`00`), `0x9f1f` (`00`). Each SPMI command is followed by a read of the controller's status words +`0x320`..+`0x380` and `W 0x23d0d9378`=1. Which driver issues the SPMI commands is not certain: 3 cores are active |
| AppleDialogSPMIPMU (2), AppleS5L8940XI2CController (3), AppleSPIMCController (4), AppleStockholmSPMI, AppleT8103PMGR, AppleT8103MemCacheController, AppleThunderboltHALType5 | nothing attributable (accesses falling in these intervals differ between captures and belong to other threads) |
| AppleGen1SPMIController (3) | per controller: read +`0x338` twice, then **`W` +`0x338` = 1**: `0x23d0d9338` (was `0x3f003ff1`), `0x23d0e1338` (was `0x3f003ff1`), `0x24a829338` (was `0x3d003ff1`) |
| AppleSmartIO | `sio`: "AP power `0x201`" echoed; "coprocessor power `0x201`" acknowledged; `R 0x236408114`, `W 0x236408114` with bit 0 cleared (`0x24401`->`0x24400` A, `0x28801`->`0x28800` B and D, `0x20001`->`0x20000` H: the value read, in the bit-17 form, with bit 0 cleared, in all seven); `R 0x236400048` (`0x2e` in all seven), `R 0x236400044`=`0x10`, **`W 0x236400044`=0** |
| ApplePMP | `pmp`: same four management words; `W 0x23bc08114` bit 0 cleared (`0x22201`->`0x22200`, all seven); `R 0x23bc00048`=`0x2e`; **`W 0x23bc00044`=0** (was `0x10`); address translator `0x23b3000fc`: `W`=0 twice; then **49,152 reads, one per 32-bit word, of `0x23b52c000`-`0x23b55bffc`** in address order (T-2.426 to T-0.39; 2.04 s under the hypervisor) |
| AppleT8020DART (19) | three do something: `dart-apcie0` `0x6810080fc`: 15 writes stepping `0x6`->`0x4`->`0x0`, each after reading one of +`0x104`..+`0x13c`; `dart-sio` `0x2350040fc`: `0x3`->`0x2`->`0x0` (4 writes); `dart-aop` `0x24a8080fc`.. read only. Each ends `R` +`0x40`, `R` +`0x100c` |

Also in E3, not tied to an action: T-2.51 `R 0x200155004`, `R 0x200155000`=`0xff000000`, plane
status reads, `W 0x200021004`=`0x4000000` (A; in B the same at another moment).

### E4. Secondary cores stop (T-0.27 to T-0.26)

Cores 1-7 make their last access between T-0.269 and T-0.259 in A, T-0.267 and T-0.259 in B
(core 2 of B at T-0.721). From T-0.257 only core 0 appears. The hypervisor's log shows each of
cores 1-7 writing its own bit to `0x23b754000` (`0x2`, `0x4`, ... `0x80`), passed to the
hardware; order 4, 1, 5, 2, 3, 6, 7 in both. `[ARTEFACT A4]` for how the stop is carried
out. The system registers written by a core as it stops are not visible.

Capture D gives the times: cores 4, 1, 5, 2, 3, 6, 7 write their bit to `0x23b754000` between
T-0.089302 and T-0.088866 (75 microseconds apart), just before the first quiesce action
(T-0.0888). They do **not** power down then: the hypervisor's record of each core entering its
sleep path comes at the very end (E6).
E and F: the same order 4, 1, 5, 2, 3, 6, 7, at T-0.0915 to T-0.0911 and T-0.0903 to
T-0.0899.

### E5. Kernel sleep path, part 2: "quiesce actions", core 0 only (T-0.257 to T-0.024)

34 console lines "IOPlatformQuiesceAction -> driver". 2,019 / 1,980 accesses, **255 writes in
each capture, the ordered writes identical in all 34 segments**; 30 segments identical access
for access (`phases-pre-compare.tsv`). The four that are not: memory controller (160 counter
values read), PCIe (2 read values), power manager (number of polls), interrupt controller
(log cut, A11). The order of the 19 temperature-sensor actions differs between captures.

**Capture D**: 36 quiesce lines (the 34 above and the two power-chip actions of E6), 2,599
accesses and 313 writes with the four untrapped pages left out. On the same basis A and B have
253 writes in the 33 actions before the interrupt controller, and **D's ordered writes are
identical to A's and B's in all 33** (`three.py`). The whole of E5 up to the interrupt
controller takes 73 ms in D (233 ms in A and B). Waits: `0x200001c04` is polled 64 times in D
against 39 in A and B, and `0x23b7487e0` 9 times: the number of polls follows the speed of the
loop, the wait ends on the value. Item 8j in D, from the hypervisor's own records: SIO
`0x23b7001c8` read (macOS is given `0x1f0000ff`; the hardware word holds `0x1400024f`) and
written `0x0f0000ff` at T-0.015833; SIO_BUSIF `0x23b7001c0` the same at T-0.015824; then SIO_CPU
read and written `0x0400024f` at T-0.015818; then `0x23d2c4000`=1 at T-0.015811.
**Captures E and F**: ordered writes identical to D's in all 33 actions before the interrupt
controller (`five.py`); the guarded SIO words handled in the same order with the same values
(hardware word `0x1400024f`, T-0.0158 in E, T-0.0156 in F); first `0x23d2c4000`=1 at T-0.015844
(E), T-0.015616 (F).

1. **Temperature sensors** (T-0.257 to T-0.150; 17 + 2 actions, 3 writes each). Per sensor at
   base S: read +`0x0`, +`0x15c`, +`0x164`, +`0x14`, +`0x18` (or +`0x8`, +`0xc`, +`0x98`,
   +`0xa0`, +`0x5c`, +`0x60`), then `W` +`0x4`=`0xffffffff`, then the control word C (read,
   written with bit 24 set, read, written with bit 25 set instead of 24). **Correction (gap
   S7):** C is +`0x8` for fourteen sensors and +`0x10` for three (`0x23b2c4000`, `0x23b2c8000`,
   `0x23b2cc000`); checked in D and H (`sensor writes`, `gaps_gh.py` session): at +`0x8` the
   writes are `0x1013c00` then `0x2003c00` (twelve sensors) or `0x1010000` then `0x2000000`
   (`0x23b2a1000`, `0x23b299200`); at +`0x10` `0x1013c00` then `0x2013c00`. The second write is
   the value read back after the first with bit 24 replaced by bit 25 (at +`0x8` bit 16 reads
   back clear: `0x13c00` -> `0x3c00`). The 17 bases: `0x23b281000`,
   `0x23b281200`, `0x23b281400`, `0x23b299200`, `0x23b2a1000`, `0x23b2c4000`, `0x23b2c8000`,
   `0x23b2cc000`, `0x210ee1000`, `0x210ee1600`, `0x211ee1400`, `0x211ee1600`, `0x211ee1800`,
   `0x211ee9000`, `0x211ef1200`, `0x211ef1400`, `0x211ef1600` (segments
   "Quiesce:AppleT8015TempSensor" in `phases-pre-N.tsv`). The two
   "MTRTempSensor" actions: `0x23b2e0000`: four reads, `W`=`0xffffffff`, `W`=`0x1000000`,
   `W`=`0x2000000`.
2. **Pin controllers** (T-0.148 to T-0.134): `R 0x23c100c48`; `W 0x24a820900`=`0xffffffff`,
   `W 0x24a820904`=`0xffffffff`; `W 0x23d1f0900`=`0xffffffff`.
3. **PCIe** (T-0.130): 17 writes: `0x681000108`=`0xf0`, `0x681000100`=`0xf0`,
   `0x681000810`=`0x101`, `0x690000004`=0, `0x690000018`=0, `0x681000800`=`0x100101`,
   `0x68100008c`=`0x11`, `0x23c100260`=`0x76a02` (was `0x76a03`), `0x681000810`=`0x101`,
   `0x68100013c`=`0x110`, `0x681000814`=0, `0x68100013c`=`0x10`, `0x681000810`=`0x100`,
   `0x680084004`=`0x8035` (was `0x35`), `0x680084000`=`0x60c` (was `0x60f`),
   `0x681000800`=`0x100100`, `0x681000100`=`0x4600`.
4. **Watchdog** (T-0.112): `W 0x23d2b8008`=0, `R` then `W 0x23d2b800c`=0, `W 0x23d2b000c`=0.
   `[A1, A9 may affect this]`
5. **Memory controller** ("AppleT8103MemCacheController", T-0.097 to T-0.079; 118 writes; all
   135 writes of items 5 and 6 are in `memory-controller-shutdown-writes.tsv`):
   a. `W 0x20010000c`=1, `W 0x200100014`=1, **`W 0x200001c00`=0**, `W 0x20010000c`=0,
      `W 0x200100014`=0;
   b. **wait**: `R 0x200001c04` repeated until it reads 0: 39 reads in both captures, values
      falling `0x41e0`, `0x41c0`, ... `0x4020`, `0x1800`, `0`, in 1.5 ms; then two reads each of
      `0x200041c04`, `0x200081c04`, `0x2000c1c04` (all 0). **In all seven** (gap V8;
      `gaps_gh.py`): the first read after the pulse is `0x41e0` (A, B) or `0x4200` (D-H); the
      reads then fall by `0x20` to `0x4020`, each value read 1 to 4 times; the last one to three
      non-zero values vary (`0x1800` A, B; `0x3800`, `0x1800` D; `0x3800`, `0x2000`, `0x800` E;
      `0x4000`, `0x2800`, `0x800` F; `0x3800`, `0x1c00` G; `0x3800`, `0x2000` H); the wait ends
      on 0, read twice, in every capture. Before the entry (A, B) and at the wake before
      `0x200001c00` = `0x10` (D-H) the word reads `0x200`; after that write, `0x4200`. A wait
      that starts from another value was never seen. The first read of the wait comes after the
      pulse is released in every capture, so whether the value starts to fall at the write of
      `0x200001c00` or at the release is not observed (first-round gap 13);
   c. `0x200158000` cleared one bit at a time from `0x3fcffffffff` to 0 (40 writes), interleaved
      with `0x200024000` and `0x200024008` cleared one bit at a time from `0x1ffff` to 0 (17
      writes each); before each step the matching counters at `0x200159000`+ and
      `0x200025000`+ are read (these are the 160 values that differ between captures);
   d. `0x200200584` cleared one bit at a time from `0x1ff` to 0 (9 writes), with 18 reads of
      `0x200204000`.. in between;
   e. 14 writes of 0 to `0x200027000`, 14 to `0x200067000`, 2 to `0x2000a7000`, each between
      reads of the counters at +`0x20`..
6. **Error handler** ("AppleT8101PlatformErrorHandler", T-0.074; 17 writes, no reads):
   `W 0x200155000`=0; then for each plane P in order `0x200000000`, `0x200040000`,
   `0x200080000`, `0x2000c0000`: `W` P+`0x21008`=0, `W` P+`0x21000`=0; then
   **`W` DCSn+`0x7a0`=0 for n = 0..7** (`0x2002007a0`, `0x2002407a0`, ... `0x2003c07a0`).
7. Secure enclave manager (T-0.069): one read, `R 0x23b700c00`=`0x1000230f`.
8. **Power manager** ("AppleT8103PMGR", T-0.065 to T-0.024; 40 writes, 837-840 reads):
   a. clock muxes `0x23b040140`, `0x23b040144`, `0x23b040148`, `0x23b04014c`, `0x23b040154`:
      each read, written **`0x80100000`**, read back (before: `0x85100000` x3, `0x87100000` x2
      in A; the read-back straight after each write still shows the old value, and the "wake"
      snapshot shows `0x85100000` / `0x87100000` again);
   b. `W 0x23b734000`=0, `W 0x23b77c000`=0, `W 0x23b778000`=0 (each was 1);
   c. about 610 reads saving timer state: triples +`0xNNc`, +`0xNN8`, +`0xNNc` across
      `0x23b734120`-`0x23b734e6c`, `0x23d2b4108`-`0x23d2b416c`, `0x23b778108`..,
      `0x23b77c108`..;
   d. per cluster: `R` then **`W 0x210e20660`=0** (was `0x1000000015`), 21 reads of
      `0x210e20400`-`0x210e204b8` and 9 of `0x210e20580`-`0x210e20648`; `W 0x210e48080`=0 (was
      `0xa000000000000000`); `R 0x210059000`, `0x210159000`, `0x210259000`, `0x210359000`,
      `0x210e48000`; the same for the other cluster with `0x211e20660`, `0x211e48080`,
      `0x211059000`.., `0x211e48000`; then 12 reads at `0x23b549000`+, 6 at `0x23b2040b0`/`b4`;
   e. reads of 14 power-domain words (`0x23b7003c8`, `3c0`, `408`, `410`, `470`, `400`, `360`,
      `3f8`, `3e8`, `448`, `368`, `3a8`, `100`, `3f0`), no writes;
   f. three blocks in turn, B = `0x68c008000`, `0x234008000`, `0x279008000`: `R` B+`0x4000`,
      `W` B+`0x14`=1, 9 reads at B+`0x4200`.., `W` B+`0x2bc`=1, 9 reads, `W` B+`0x2bc`=2,
      1 read, `W` B+`0x2bc`=4;
   g. `0x210e40250` and `0x211e40250`: written with bit 63 cleared (`0x8001b20026f02400` ->
      `0x0001b20026f02400`; `0x8001b2005df05200` -> `0x0001b2005df05200`); `0x210e40240`,
      `0x211e40240` rewritten unchanged; `0x210e48400`, `0x211e48400` written with bit 63
      cleared;
   h. the four sub-blocks `0x23b748400`, `0x23b748800`, `0x23b748c00`, `0x23b748000`, in that
      order: each read (1), written 0, then its status word +`0x3e0` (`0x23b7487e0`,
      `0x23b748be0`, `0x23b748fe0`, `0x23b7483e0`) read until its low byte is 0 (values in R22a;
      9 polls of `0x23b7487e0` in A, 6 in B);
   i. `W 0x23b71c080`=`0x80000000`, `W 0x23b71c088`=`0x80000000` (unchanged values);
      `W 0x23b718000`=0, `W 0x23b718004`=0 (each was `0xf`);
   j. the three SIO domains have bit 28 cleared: SIO_CPU `0x23b7001d0` `0x1400024f` ->
      **`0x0400024f`** (access log, T-0.0244); SIO `0x23b7001c8` and SIO_BUSIF `0x23b7001c0`
      written `0x0f0000ff` (hypervisor's log, held, `[ARTEFACT A3]`; position relative to the
      SIO_CPU write not known); *(round 10: in L, `det19b`, `det21` the instrument's records put
      SIO, then SIO_BUSIF, each read and written, between the write `0x23b718004` = 0 of step i
      and the SIO_CPU write, 4-39 microseconds after the former; `r7-wd2start-det*.txt`)*;
   k. **`W 0x23d2c4000`=1** (T-0.0243), with console text "Starting S2R timer".
9. T-0.023 to T-0.017: 22 writes to `0x23fe5f098`.. (SMC shared memory; values include kernel
   text addresses and differ between captures).
10. **Interrupt controller** ("AppleInterruptController", from T-0.017): reads of consecutive
    words from `0x23b103000`. The log ends inside this sweep (A11).

### E6. The last steps before power-down (T-0.016 to T; capture D; A and B stop inside step 1)

In A and B the access log stops inside step 1 (A11) and only the console shows what follows
(`vuart-135full3.log` lines 2339-2344, `vuart-135full4.log` lines 2364-2369, identical):
```
Starting S2R timerIOPlatformQuiesceAction -> AppleInterruptController
IOPlatformQuiesceAction -> AppleDialogSPMIPMU
pmu go hib (0x7)
Starting S2R timerIOPlatformQuiesceAction -> AppleDialogSPMIPMU
pmu go hib (0x7)
Starting S2R timerIOPlatformActiveAction -> AppleInterruptController
```
Capture D has the same console text and every access behind it (`phases-pre-d.tsv`, segments
"Quiesce:AppleInterruptController#1", "Quiesce:AppleDialogSPMIPMU#1" and "#2"; `view.py d pre
-0.0062 0 -raw`; `spmi-pre-d.txt`). Core 0 only.

1. **Interrupt controller** (T-0.0158 to T-0.0066; 963 reads, 39 writes):
   a. 896 reads, `0x23b103000` to `0x23b103dfc` in address order (A and B have the first 408 and
      372 of these; A's 408 are equal to D's first 408 in address and value);
   b. 28 times, k = 0..27: `R 0x23b104180`+4k, then **`W 0x23b104100`+4k = `0xffffffff`**;
   c. 11 times, k = 0..10: `R 0x23b105028`+`0x80`k (reads `0x80000001`), **`W 0x23b105024`+
      `0x80`k = `0x80000001`**, `R 0x23b105004`+`0x80`k (reads 0);
   d. 16 reads `0x23b106000`+`0x10`k (first reads `0x800000c0`, the rest 0); `R 0x23b100010` =
      `0xe0777971`.
   At the wake all 991 words written back in W1-1 were seen here. **Corrected (gaps V3, 11):**
   the earlier count "913 / 18 / 38" did not add up. Checked word by word in D, E, F, G and H
   (`gaps_gh.py`, block V3; no exception in any of the five): 913 words are written the value
   read from that same word here (the 896 of a., the 16 of d., and `0x23b100010`); the 28 words
   `0x23b104100`+4k are written the value read here from `0x23b104180`+4k; the 28 words
   `0x23b104180`+4k (k = 0..27, up to `0x23b1041ec`) are written the bitwise inverse of the
   value read from that same word; the 11 words `0x23b105028`+`0x80`k are written the inverse of
   the value read from that same word (`0x80000001` read, `0x7ffffffe` written); the 11 words
   `0x23b105024`+`0x80`k are written `0x80000001`. 913 + 28 + 28 + 11 + 11 = 991. A and B cannot
   show it (their read sweep was cut, A11). What the words are, and why a value is written
   inverted, is not established.
2. **First power-chip action** (T-0.0060): console "pmu go hib (0x7)"; one register access:
   **`W 0x23d2c4000`=1** at T-0.004355 (the second such write; console "Starting S2R timer").
   No SPMI traffic.
3. **Second power-chip action** (T-0.0044 to T-0.0007): four SPMI commands to the power chip,
   each as: `W 0x23d0d9338`=0, command word(s) to `0x23d0d9304`, two reads of the status word
   `0x23d0d9378` (reads 1), `W 0x23d0d9378`=1, reply read from `0x23d0d9308`,
   `W 0x23d0d9338`=1:
   a. read register `0xd00c`, 1 byte: `00` (T-0.0017);
   b. **write register `0xd008`, 4 bytes: `9f 9a 08 00`** (T-0.0016);
   c. **write register `0xd00e` = `00`** (T-0.0015);
   d. **write register `0xd000` = `41`** (T-0.0014);
   then console "pmu go hib (0x7)" and **`W 0x23d2c4000`=1** at T-0.000705 (the third).
   The decoding tool labels `0xd008` the clock alarm, `0xd00e` the clock interrupt mask, `0xd000`
   the alarm control (enable bit `0x40`), `0xd002` the clock. The clock read at T-7.06 was
   `7a 23 e4 96 08 00`; if the alarm holds the clock's upper four bytes (an inference from the
   byte layout, not established), the alarm is about 948 s after T.
4. **Nothing else.** After the third write of `0x23d2c4000` there are 48 more records: 18
   console bytes (each a status read of `0x23d12c014` and a write of `0x23d12c004`), 11 writes to
   SMC shared memory `0x23fe5f1f8`-`0x23fe5f220` (a record like the one of E5-9), and a last
   read of the console port `0x23d10c000` at T. macOS sends the power chip **no command other than step 3**
   and writes no power-domain word.
5. **The cores go down** (hypervisor's records): cores 5, 6, 7, 4 enter their sleep path at
   T-0.000015, cores 1, 2, 3 at T-0.000011, core 0 last at T+0.000016. All eight within 31
   microseconds, although cores 1-7 had written their stop bit 89 ms earlier (E4). What each
   core writes to its system registers there is not recorded. After the last core the
   hypervisor does its own commit work (A6), not logged.

**Captures E and F (cable out)** have the same last steps (`phases-pre-e.tsv`,
`phases-pre-f.tsv`, `spmi-pre-e.txt`, `spmi-pre-f.txt`, `phases-pre-compare-de.tsv`, `-df.tsv`):
- Step 1 is identical to D access for access in both: 963 reads and 39 writes, same addresses,
  order and values.
- Steps 2 and 3: the same accesses. In E in D's order. **In F the two power-chip actions run in
  the other order**: the four SPMI commands and the second `0x23d2c4000`=1 come first
  (T-0.0049 to T-0.003931), the action with the single write last (T-0.000690). So the
  third write of `0x23d2c4000` is the last device write in all three, and the alarm commands
  come before the second or before the third.
- The alarm value differs: `9f 9a 08 00` (D), `e4 a6 08 00` (E), `60 a5 08 00` (F). With the
  inference of step 3 that is about 948 s, 972 s and 1,069 s after T: not a fixed interval.
  `0xd00e`=`00` and `0xd000`=`41` are the same in all three; `0xd00c` reads `00` in all three.
- Step 4: 48 trailing records in each, ending with the read of `0x23d10c000`.
- Step 5: all eight cores enter the sleep path within 33 microseconds in each (E: cores 1-7 at
  T+0.000006 to T+0.000008, core 0 at T+0.000018; F: T-0.000017 to T-0.000007, core 0 at
  T+0.000015).

**Capture J** *(round 8, `r8_det11.py`)*: F's order (commands and the second write first, the
third write alone at T-0.000698); every one of the four commands ends, as in D-I, with
`0x23d0d9378` read 1 twice and written 1 and `0x23d0d9338` written 1 (R38); after the fourth the
only SPMI access before T is a read of `0x23d0d9300` (`0x1000100`, T-0.004345). All eight cores
in their sleep path within 19 microseconds, core 0 last.

### E7. Each core's way down: system registers (capture G; `det_down.py`, `det-down-g.tsv`)

Register names are the hypervisor's (its register tables); an encoding is given where it has
no name. 315 records, 182 reads and 133 writes, on ten registers: `PMC0_EL1`, `PMC1_EL1`
(77 each), `PMCR0_EL1` (37), `s3_5_c15_c10_1` (26), `PMCR1_EL1` (24), `IPI_SR_EL1` (24),
`ACC_OVRD_EL1` (16), `CYC_OVRD_EL1` (16), `IPI_RR_LOCAL_EL1` (9), `IPI_RR_GLOBAL_EL1` (9).
Only registers the hypervisor traps appear (limits in 1.7). Two bursts, with **no record on
any core in the 91 ms between them**:

**Burst 1, T-0.091694 to T-0.0912: the cores are told to stop** (the stop-bit writes of E4).
For each core in the order 4, 1, 5, 2, 3, 6, 7, about 80 microseconds per core:
- core 0: reads `PMC0_EL1`, `PMC1_EL1`; writes `s3_5_c15_c10_1` = 0 (twice, each after a pair of
  counter reads); writes `IPI_RR_LOCAL_EL1` = 1, 2, 3 for cores 1, 2, 3 or `IPI_RR_GLOBAL_EL1` =
  `0x10000`, `0x10001`, `0x10002`, `0x10003` for cores 4-7 (the hypervisor carries these out
  itself, "c-locked"); writes `PMCR0_EL1` = `0x7003400`; later writes `PMC0_EL1`, `PMC1_EL1`
  back, `PMCR1_EL1` = `0x3030303` (read `0x30300`), `PMCR0_EL1` = `0x7003403`, and reads then
  writes `IPI_SR_EL1` = 1;
- the addressed core (27 records each; core 4's begin before the first stop bit and only its
  last 4 are logged): writes `PMC0_EL1`, `PMC1_EL1`; `PMCR1_EL1` read `0x30300`, written
  `0x3030303`; `PMCR0_EL1` read `0x7003400`, written `0x7003403`; `IPI_SR_EL1` read 1, written
  1; counter reads; `s3_5_c15_c10_1` = 0 and `IPI_RR_LOCAL_EL1` = 0, twice; `PMCR0_EL1` =
  `0x7003400`; counter reads; then, 50-60 microseconds after its first record, **its stop bit
  to `0x23b754000`** (core 4 T-0.091694, 1 T-0.091611, 5 T-0.091535, 2 T-0.091447, 3 T-0.091373,
  6 T-0.091296, 7 T-0.091211).
Then core 0 runs the quiesce actions (E5: first console line T-0.091) and the last steps (E6:
`0x23d2c4000` written at T-0.015607, T-0.003840, T-0.000696; interrupt-controller action
T-0.0129 to T-0.0067), with no trapped system-register access of its own and none on the
stopped cores.

**Burst 2, T-0.000017 to T+0.000016: every core makes the same four accesses**:
1. read `ACC_OVRD_EL1` (cores 1, 2, 4, 5, 6, 7 read `0x180010102001c207`; cores 3 and 0, which
   come later, read `0x1800101526076207`);
2. **write `ACC_OVRD_EL1` = `0x1800101526076207`**;
3. read `CYC_OVRD_EL1` = `0x2000000`;
4. **write `CYC_OVRD_EL1` = `0x3000001`**: the write the hypervisor marks as taking the core down
   ("s2r"; logged before it acts) and the moment of its "core enters its sleep path" record.
Cores 2, 4, 5, 1, 6, 7 do this between T-0.000017 and T-0.000002, core 3 between T-0.000007
and T+0.000002, **core 0 last, T+0.000011 to T+0.000016**, 16 microseconds after its last
device access (the console-port read of E6-4). Nothing trapped follows on any core. What a
core executes after the `CYC_OVRD_EL1` write (the wait instruction) is not in the log.

**After macOS** `[ARTEFACT A6]`, on core 0, still running: the commit snapshot (T+0.000017 to
T+0.000931), then the hypervisor's writes of the held guarded words at T+0.001054 to
T+0.001063: UART0 and UART_P = `0x100000ff`, SIO and SIO_BUSIF = `0x0f0000ff`, ATC0_USB and
ATC0_USB_AON = `0x3f0`, ATC0_COMMON = `0x23f0`; then its power-chip commands and USB detach,
which are not logged; then the real `CYC_OVRD_EL1` write.

**What this does and does not say about what powers the chip down** (open question 14):
- It is not any device-register write of macOS. After the last one that could matter
  (`0x23d2c4000` = 1, T-0.7 ms) and after macOS's last access of any kind (T), the chip is
  demonstrably still running for more than 1.06 ms: 792 registers are read and seven written.
- Every core's last act is the pair `ACC_OVRD_EL1`, `CYC_OVRD_EL1`, all eight within 33
  microseconds, core 0 last. The chip goes down only after the last core has done it. This
  fits "the chip powers down once all cores have set these two registers and wait", but the
  captures cannot separate that from the alternatives: the hypervisor's own acts come between
  core 0's logged write and its real one, the wait instruction is not seen, and no capture has
  a core set the registers without the chip going down.
- The stop bits of E4 do not power a core down: each core is alive and executes burst 2
  91 ms later.
- Which of the earlier steps are preconditions (`0x23d2c4000`, the alarm, the memory-controller
  shutdown, the masked interrupt controller) cannot be told from captures in which all of them
  always happen.
- *(Round 8.)* Between each core's logged `CYC_OVRD_EL1` write and its real one the instrument
  writes that core's four timer controls and its guest timer FIQ enable 0 and clears the pending
  virtual IRQ and FIQ (A6), on every core, in A-J. So **every observed power-down had every core
  in its final wait with its timers disabled and no virtual interrupt pending** *(round 10: the
  timers not in `det19b`, `det21`, which also powered down; R59)*; what macOS itself
  leaves in these registers is not in any log (the timers are not trapped, 1.7). Before that, in
  burst 1, each core's last trapped writes are `PMCR0_EL1` = `0x7003400` and `IPI_SR_EL1` = 1
  (core 0 included, at T-0.0902 in J; R45). J repeats burst 2 with the values of G and H
  (1.7c).

**Each core's own state at its final write (capture K, round 9; `r6-det12.txt`).** Read by each
core at the start of the instrument's handling of its `CYC_OVRD_EL1` write, before any write of
the instrument's (A6). Order of the writes: cores 4, 5, 1, 3, 7, 6, 2, then core 0 about 30
microseconds later; every core wrote `0x3000001` from the same guest instruction
(`0xfffffe0014a05f1c`). Two kinds of value are mixed here and are kept apart: **macOS's own**
(registers macOS writes and the instrument does not change: the guest's timers, the performance
counters, `ACC_OVRD_EL1`, `CYC_OVRD_EL1`, the interrupt controller's words) and **the
instrument's** (state it keeps for macOS: the pending virtual IRQ/FIQ bits of `HCR_EL2`, the
guest timer FIQ enable `VM_TMR_FIQ_ENA_EL2`, its own EL2 timers, its view of the IPI and
counter interrupts). `ISR_EL1` read at EL2 shows the interrupt lines at the core, which the
instrument's settings shape.

Equal on all eight cores:

| Register | Value | Whose |
|---|---|---|
| `CNTP_CTL_EL02` (the guest's physical timer) | `0x6` (disabled, masked, status set); `CNTP_CVAL_EL02` 0 | macOS's |
| `CNTKCTL_EL12` | `0x4f` | macOS's |
| `CNTVOFF_EL2` / `CNTHCTL_EL2` | `0x1286d8f3` / `0xc00` | the instrument's |
| `ISR_EL1` (read at EL2) | 0: no IRQ, FIQ or SError line asserted at any core | the hardware's, under the instrument's settings |
| `IPI_SR_EL1` | 0 (hardware); the instrument's "IPI pending" and "IPI queued" for the guest 0 | macOS's (it wrote 1 in burst 1, R45) |
| `IPI_CR_EL1` | `0x600` | macOS's |
| `PMCR0_EL1` | `0x7003400`, hardware and the guest's view; counter interrupt pending 0; `PMSR_EL1`, `UPMCR0_EL1`, `UPMSR_EL1` 0 | macOS's |
| `ACC_OVRD_EL1` | `0x1800101526076207` | macOS's (R43) |
| `CYC_OVRD_EL1` before the write | `0x2000000` | macOS's (R43) |
| the instrument's EL2 timers | physical `CTL` 1 (enabled), compare 0.4-0.7 ms ahead; virtual `CTL` 7 | the instrument's (it stops both, A6) |
| guest `PSTATE` (`SPSR_EL2`) | D, A, I, F all masked, EL1 with SP_EL0 | macOS's |

Differing between cores (columns in the order of the writes):

| Core | 4 | 5 | 1 | 3 | 7 | 6 | 2 | 0 |
|---|---|---|---|---|---|---|---|---|
| `CNTV_CTL_EL02` (the guest's virtual timer; macOS's) | `0x1` | `0x1` | `0x5` | `0x1` | `0x1` | `0x1` | `0x5` | `0x5` |
| its compare minus the guest's count then | +89.387 s | +89.387 s | -0.034 s | +0.877 s | +89.387 s | +89.387 s | -0.083 s | -0.083 s |
| `VM_TMR_FIQ_ENA_EL2` (the instrument's) | 3 | 3 | 2 | 3 | 3 | 3 | 2 | 2 |
| `HCR_EL2` (the instrument's) | `0x80032480200029` | `..029` | `..069` | `..029` | `..029` | `..029` | `..069` | `..069` |

`0x1` = enabled, not masked, not fired; `0x5` = enabled, not masked, fired. The guest's count is
`CNTPCT_EL0` - `CNTVOFF_EL2`. Bit 6 of `HCR_EL2` is the pending virtual FIQ. So **macOS leaves
its virtual timer enabled and unmasked on all eight cores at its final write; on cores 1, 2 and
0 it has already fired**, on core 3 it is due 0.88 s later, on cores 4, 5, 6, 7 89.39 s later.
On the three cores where it had fired, the instrument held a virtual FIQ pending for macOS and
had turned that timer's FIQ to the core off (`VM_TMR_FIQ_ENA_EL2` bit 0 clear); no core had a
virtual IRQ pending; `ISR_EL1` read 0 on every core, those three included. So under the
instrument a fired guest timer was presented to macOS as the instrument's pending virtual FIQ
with the timer's own FIQ turned off; what the same timer state presents to a core **without**
the instrument is not observed. `[UNKNOWN]` In every power-down captured the instrument then
wrote all of this off (A6, R59).

**The interrupt controller as each core read it** (`0x23b100000` +; every core read the same
values): `+0x2024` `0x80000001`; the 28 words `+0x4180`-`+0x41ec` `0xffffffff`; the 28 words
`+0x4000`.. 0; the 11 words `+0x5004`+`0x80`k 0 and `+0x5028`+`0x80`k `0x80000001`; of the words
from `+0x4200`, 13 non-zero: `+0x4214` `0x8000000`, `4218` `0x1020`, `421c` `0xa0155000`, `4220`
`0xa0000000`, `4230` `0x1550000`, `4234` `0x2800`, `4238` `0x140000`, `423c` `0x80000000`,
`4240` `0x2`, `4244` `0x80000a00`, `4248` `0x2282`, `4250` `0x5`, the rest 0 (107 words read per
core). The 28 words `+0x4180`+4k and the 11 words `+0x5028`+`0x80`k are words R36 reads before
it writes `+0x4100`+4k = `0xffffffff` and `+0x5024`+`0x80`k = `0x80000001`; here they are read
again at each core's final write, about 6 ms after R36 ends. *Documentation, not an
observation:* the Asahi Linux page "AIC" (asahilinux.org/docs/hw/soc/aic/) says Apple's SET/CLR
register pairs both read the current state, and names `+0x4000` SW_GEN_SET (bits ORed with the
hardware lines), `+0x4100` IRQ_MASK_SET, `+0x4180` IRQ_MASK_CLR (writing a bit there unmasks),
`+0x4200` HW_IRQ_MON ("current interrupt line state?"), `+0x2024` IPI_MASK_SET (bit 0 the
"other" IPI, bit 31 the "self" IPI), and `+0x2004` IRQ_REASON, whose read masks the interrupt it
reports (it was not read); it does not describe the words from `+0x5000`. It also says the cores' timers
bypass the controller and are "wired straight to FIQ". By those names **at every core's final
write every interrupt of the controller is masked, both IPI kinds are masked, none is
software-generated, and 13 words show input lines asserted**; this is the documentation's
reading of the values, not tested here, and it does not cover the cores' timers.

Each core's last logged writes before T in K: `PMCR0_EL1` `0x7003400` and `IPI_SR_EL1` 1 on
cores 0, 1, 2, 3, 5, 6, 7 at T-0.092 to T-0.091 (core 4's are before the logged window), as in
J (R45).

**Leaving that state in place** (`det13`, `det17`; **[HV-CHANGED]**, 1.7d). The instrument
stopped only its own EL2 timers and did the rest of its commit as in K. Both runs: no alarm
wake; a reset about 5-6 s after the commit. Their bitmaps: every core's guest timer enabled and
unmasked; a virtual interrupt or held interrupt pending on cores 0 and 1 (`det13`), 0 and 3
(`det17`). This is an observation of the machine with the instrument's way of presenting
macOS's timer to the core (a held virtual FIQ, with the timer's own FIQ to the core off on the
cores where it had fired), not of macOS's timer state on a machine without the instrument.
Which of the two left items made the difference is not separated (one configuration, run twice).
*Reference, not an observation:* by the Arm architecture a pending virtual FIQ is a wake-up
event for a wait-for-interrupt instruction, and the instrument's code says so in its comment
(A6); Aurora's notes on T8140 say a timer left running ends the final wait and that "the sleep
engine waits for" a raised interrupt line, so its driver masks every line and the timers after
its commit (reference, section 2.2).

**Each core's own state at its final write in L, `det19b`, `det21` (round 10;
`r7-det*-core-state.txt`, `r10-checks.txt` part 2).** Read as in K, before any write of the
instrument's; so these are macOS's values (and the instrument's held state) in all three, the
two `keep_timers` runs included. Every value of K's "equal on all eight cores" table is the same
in all three runs (`CNTP_CTL_EL02` `0x6`, `ISR_EL1` 0, `IPI_SR_EL1` 0, `IPI_CR_EL1` `0x600`,
`PMCR0_EL1` `0x7003400`, `ACC_OVRD_EL1` `0x1800101526076207`, `CYC_OVRD_EL1` `0x2000000` before
the write, `0x3000001` written; the interrupt-controller words as in K), except `CNTVOFF_EL2`,
the instrument's, which differs per boot. The guest virtual timer, per core (due = its compare
minus the guest's count at the read):

| Capture | Enabled, unmasked, **fired** (`0x5`); the instrument: virtual FIQ pending, timer FIQ enable 2 | Enabled, unmasked, not fired (`0x1`); virtual FIQ clear, timer FIQ enable 3 |
|---|---|---|
| K (`det12`) | cores 1, 2, 0 (due -0.034 to -0.083 s) | core 3 +0.877 s; cores 4, 5, 6, 7 +89.39 s |
| L (`det18`) | cores 1, 3, 2, 0 (due -0.010 to -0.088 s) | cores 4, 5, 6, 7 +89.39 s |
| `det19b` | cores 1, 3, 0 (-0.077 to -0.088 s) | **core 2 +0.063 s**; cores 4, 5, 6, 7 +89.39 s |
| `det21` | cores 1, 2, 0 (-0.051 to -0.073 s) | **core 3 +0.062 s**; cores 4, 5, 6, 7 +89.39 s |

So in four captures: macOS leaves its virtual timer enabled and unmasked on all eight cores; it
has fired on three or four of the efficiency cores, **core 0 and core 1 every time**; on the
performance cores it is due about 89.39 s after the final write (the instrument's alarm is at
commit + 90 s); on the remaining efficiency core it is due 0.06 to 0.88 s after. No core had a
virtual IRQ pending; `ISR_EL1` read 0 on every core. Where the timer had fired, the instrument
held a virtual FIQ pending and had the timer's FIQ to the core off (bit 0 of
`VM_TMR_FIQ_ENA_EL2` clear); where it had not, no virtual FIQ and the FIQ to the core on. The
bitmaps of `det20b` and `det22c` (1.7e) show the same kind of state on cores 0-3 and 0-2.

**The two items separated (round 10; [HV-CHANGED]).** Every power-down before this round had,
by the instrument's acts on every core between its logged `CYC_OVRD_EL1` write and its real one,
(a) the guest timers and the timer FIQ enable written 0 and (b) the pending virtual IRQ and FIQ
cleared (A6, R59). `det13` and `det17` kept both and did not power down. This round:

| What the instrument left as macOS left it | Runs | What followed |
|---|---|---|
| neither (A-L) | 11 captures | power-down, wake at the alarm or a key |
| (a) the timers: guest virtual timer enabled and unmasked on all eight cores, fired on three, and the timer FIQ enable as found (fired cores 2, others 3); (b) done: no virtual interrupt pending | `det19b`, `det21` | **power-down and wake at the alarm, 89.74 s and 89.62 s**, wake status 0 / `0x400000` / 0: as without the change |
| (b) the pending virtual FIQ on cores 0-3 (`det20b`) / 0-2 (`det22c`); (a) done: timers and timer FIQ enable 0 | `det20b`, `det22c` | **no wake; a reset about 6 s after the commit**, `0x9f03` `0x50` |
| both | `det13`, `det17` (round 9) | no wake; a reset about 5-6 s after the commit |

So, under the instrument: **with a virtual FIQ pending at two to four cores when they made their
final write, the chip did not power down and wake, four runs of four (two configurations); with
no virtual interrupt pending and every core gone down, it did, thirteen of thirteen, two of them
with every core's guest virtual timer left enabled and unmasked.** (The two runs with no virtual
interrupt pending that did not power down, `det14` and `det16`, kept a core running, R64.) The enabled timer is not what stopped `det13` and
`det17`; the pending virtual FIQ is the item whose presence went with every failure. What happened
at the cores after their final write in the failed runs is not read: whether a core left its wait
is not observed, and nothing in the record says what reset the SoC. *Reference, not an
observation:* by the Arm architecture a pending virtual FIQ (with `HCR_EL2`.FMO set, as here)
ends a wait for interrupt even with `PSTATE`.F masked; the instrument's code says the same in its
comment (A6). On that reading a core with a virtual FIQ pending would not stay in its final wait,
which would make these runs like `det14` and `det16` (a core kept running after the commit: a
reset 6-7 s after, R64), whose timing they match; this is an inference.

Two details of `det19b` and `det21` bound the timer side further, as far as they go. In each, one
core (core 2, core 3) went down with its timer enabled, unmasked, **not fired, due 62-63 ms after
its final write, and its FIQ to the core on** (enable 3); the chip powered down and woke at the
alarm. What happened when that timer fell due is not in any log (the instrument's handling of
such an FIQ after a core's final write is not recorded). Either the chip had passed the point at
which a core's timer matters within about 62 ms of that core's final write, or a timer falling
due after the final write does not stop the power-down; the two are not separated. And on the
cores where the timer had already fired, the instrument had turned the timer's FIQ to the core
off; so **no run has a core reach its final wait with a fired timer whose interrupt reaches the
core other than as the instrument's virtual FIQ**. What macOS's own timer state does on a machine
without the instrument is still not observed `[UNKNOWN]`.

**Each core's own state at its final write in `det23`, `det24` (round 11; `r8-det2[34]-core-state.txt`,
`r11-checks.txt` part 5).** Read as in K, before any per-core write of the instrument's (the
header clear of A6's round-11 note is a device write and came before some of these records in
`det24`). Every value of K's "equal on all eight cores" table is the same in both runs
(`CNTP_CTL_EL02` `0x6`, `CNTKCTL_EL12` `0x4f`, `ISR_EL1` 0, `IPI_SR_EL1` 0, `IPI_CR_EL1`
`0x600`, `PMCR0_EL1` `0x7003400`, `PMSR_EL1`, `UPMCR0_EL1`, `UPMSR_EL1` 0, `ACC_OVRD_EL1`
`0x1800101526076207`, `CYC_OVRD_EL1` `0x2000000` before the write and `0x3000001` written,
`PSTATE` D, A, I, F masked; the 107 interrupt-controller words as in K), except `CNTVOFF_EL2`
(the instrument's, per boot) and **one core's IPI word in `det23`** (below).

| Capture | Guest virtual timer fired (`0x5`); virtual FIQ pending, timer FIQ enable 2 | Not fired (`0x1`), timer FIQ enable 3 | Other |
|---|---|---|---|
| `det23` | cores 2, 1, 0 (due -0.046 to -0.073 s) | core 3 +89.389 s; cores 4-7 +89.389 s | **core 3: the instrument's "IPI pending (guest view)" 1 and its virtual FIQ pending** (`HCR_EL2` bit 6), with its timer not fired and `IPI_SR_EL1` (hardware) 0 |
| `det24` | cores 1, 0 (-0.083 s) | core 3 +0.135 s, core 2 +0.503 s; cores 4-7 +89.388 s | none |

So with K, L, `det19b` and `det21`, six captures: macOS leaves its virtual timer enabled and
unmasked on all eight cores, fired on two to four efficiency cores, core 0 and core 1 every
time. **New in `det23`:** a core (core 3) made its final write with a virtual FIQ pending that
does not come from its timer but from an IPI the instrument held for it: in K-`det21` and `det24`
the instrument's "IPI pending" and "IPI queued" words read 0 on every core. The instrument carries
out macOS's IPI writes itself (E7, burst 1; R45); an IPI sent to a core is presented to that
core's macOS as the instrument's pending flag and a virtual FIQ, so the hardware's `IPI_SR_EL1`
does not show it. Which core sent it, and when, is not in the log (the IPI writes of the last
91 ms are not trapped as accesses). In `det23` the instrument then cleared the pending virtual
interrupts on every core as in A-L, and the chip powered down. On a machine without the
instrument the same IPI would be held by the hardware's own IPI registers of that core
(`IPI_SR_EL1`, which macOS acknowledges by writing 1, R45) at its final write; what it then
presents to the core is not observed. `ISR_EL1` read 0 on all eight cores in both runs.

**What a core leaves at its final write, as far as the observations carry it (round 10).** For
a driver's cores, kept apart by how firmly each rests:
1. *Nothing pending at the core.* Every captured power-down (A-L, `det19b`, `det21`) had no
   virtual IRQ or FIQ pending at any core at its final wait (the instrument's act, [ARTEFACT, in
   every power-down]), and where it was read (K, L, `det19b`, `det21`) `ISR_EL1` read 0 at every
   core's final write. With a virtual FIQ left pending: no power-down, four of four
   [HV-CHANGED]. A physical interrupt pending at a core at its final wait (a fired timer whose
   FIQ is on, an IPI, a performance-counter interrupt, a controller line) is in no run on either
   system. This is R59's requirement (round 10 wording) and R68. *(Round 11.)* `det23` and
   `det24` add two power-downs with nothing pending at the cores' final waits (the
   instrument's clearing) and `ISR_EL1` 0 at every final write: fifteen and six. In `det23` the
   virtual FIQ the instrument cleared on core 3 came from an IPI, not a timer: macOS's own entry
   can leave an IPI not yet taken at a core when it makes its final write.
2. *The timers need not be off.* Every guest virtual timer enabled and unmasked, with nothing
   pending at the core, was followed by a power-down twice (`det19b`, `det21`, [HV-CHANGED]);
   every other power-down had them off (the instrument's act). macOS's own values: virtual timer
   enabled and unmasked on all eight cores, physical timer disabled (four captures).
3. *The rest of the core's state is macOS's own and the same in all four captures* (R65): the
   interrupt controller's lines and both IPI kinds masked, nothing software-generated,
   `IPI_SR_EL1` 0, `PMCR0_EL1` `0x7003400` with no counter interrupt pending, `PSTATE` with D, A,
   I, F masked, `ACC_OVRD_EL1` and `CYC_OVRD_EL1` as R43; core 0 last (R44); no core kept running
   (R64).
4. *Open* (open questions 57, 65, 66): the same per-core reading under Linux at its final
   instruction; whether a fired timer whose interrupt reaches the core, with no instrument in
   between, stops the power-down; and whether the cores with a pending virtual FIQ left their
   wait.

### Power-domain writes in the whole entry, by domain (`ps.py pre -20 0`)

Excluding E0's SPI3 cycles the access log holds these domain writes, the same count in both:
DISP0_CPU0 7, DISP0_FE 5, RMX 7, DISPEXT_CPU0 5, DISPEXT_FE 4, GFX 2, APCIE_ST 2, SPI2 4,
I2C0 20, I2C3 140, SIO_CPU 1. The full ordered sequence of (domain, value) differs between
captures only in where the I2C0, I2C3, SPI2 and SPI3 bus cycles interleave (8,220 of 8,249
writes of A match B in order). **No other domain is written.** In particular the domains of the
memory controller, DRAM controllers, interrupt controller, pin controller, PMP, SMC, storage and
secure enclave are not written during the entry in what was logged; those of the guarded words
(A3) are in the hypervisor's log: SIO and SIO_BUSIF as in 8j, ATC0_COMMON `0x23f0`, ATC0_USB
`0x3f0`, ATC0_USB_AON `0x3f0`, UART_P and UART0 last `0x100000ff` (all written at boot time,
before the entry, and held).

**Capture D** (`ps.py pre '@awdl0 disable' @END`, `CAPS=3,d` and `4,d`): the same per-domain
counts (DISP0_CPU0 7, DISP0_FE 5, RMX 7, DISPEXT_CPU0 5, DISPEXT_FE 4, GFX 2, APCIE_ST 2, SPI2 4,
I2C0 20, I2C3 140, SIO_CPU 1) and the same 33 non-bus writes with the same values; one order
difference: when the display domains are turned on again in E2, D does DISPEXT_FE and
DISPEXT_CPU0 before DISP0_FE and DISP0_CPU0, A and B the other way round. With the log complete
to the end, the statement "no other domain is written" now holds to the power-down (D).
**Captures E and F**: the same per-domain counts, with two run-to-run variations that do not
follow the cable: E turns the display pairs on again in A's and B's order (DISP0 first), so D's
order is not a property of the detached mode; F writes one more domain, FPWM1 = `0x3f0`,
before the sleep (34 non-bus writes), and at the wake restores FPWM1 to `0x340`
instead of on (section 6, W1). No domain is written after the first `0x23d2c4000` write in
either.

## 4. The state at the commit

### 4.1 The snapshot at the commit (capture G; `commit_snap.py`, `commit-snapshot-g.tsv`)

792 words read from the hardware on core 0, starting 1 microsecond after core 0's own
sleep-path record and ending 0.914 ms later, before any of the hypervisor's own commit actions.
All other cores had entered their sleep path. The list is the 792-word list of the earlier
snapshots, so it answers for these words and not for the others. Capture H repeats it and adds
the 66 domain words G lacked; the two are compared in 4.1a, which supersedes the single-capture
counts below wherever they differ.

**Against idle.** 764 of the 792 words have the value of G's "pre-detach" snapshot taken about
440 s earlier at idle (761 of "pre-full"); against the idle snapshots of the other captures 752 to
756. All 80 memory-controller words and all 448 DRAM-controller words (56 per controller,
including +`0x500`) are unchanged from idle: **in what the list covers, the memory and DRAM
controllers look at the commit as they do at idle.** The 28 that changed: 11 power-domain words
(below), 10 clock-generator words at `0x23b040020`-`0x23b04011c` (bit 8 differs),
and `0x23b71c0f0`, `0x23b720030`, `0x23b720034`, `0x23b720044`, `0x23d240000`, `0x23d240040`,
`0x23d240314`; 22 of the 28 were never written by macOS in the log.

**Against what macOS last wrote.** Only 16 snapshot words were written by macOS in the log
(15 during the entry):
- 10 power-domain words read in the snapshot exactly what macOS itself last read after its last
  write (the written request plus status bits): I2C0, I2C3, SPI2, SPI3 wrote `0x3f0`, read and
  snapshot `0x200`; DISP0_FE, DISPEXT_FE wrote `0x23f0`, `0x2300`; DISP0_CPU0, DISPEXT_CPU0 wrote
  `0x0f0403f0`, `0x0f040300`; GFX wrote `0x0f0023f0`, `0x0f002300`; RMX wrote `0x300`,
  `0x0f000300`. **Confirmed.**
- the 5 clock muxes `0x23b040140`-`0x23b040154`: macOS wrote `0x80100000` (E5-8a); the snapshot
  holds `0x85100000` (three) and `0x87100000` (two), which is also what macOS read back at once.
  **The written value is not what the word holds at the commit.** Not guarded.
- SIO_CPU `0x23b7001d0`: macOS wrote `0x0400024f` (bit 28 cleared, E5-8j) and did not read it
  again; the snapshot holds **`0x0f0002ff`** (idle: `0x1400024f`). Not guarded. The domain is
  fully on at the commit, not in the state it idles in.
- Guarded words `[A3]`: SIO `0x23b7001c8`: macOS wrote `0x0f0000ff` (held back); snapshot
  `0x1f0002ff` (idle `0x1400024f`): the hardware word changed although macOS's write never
  reached it. SIO_BUSIF `0x23b7001c0`: macOS wrote `0x0f0000ff` (held); snapshot `0x1400024f`,
  unchanged. UART_P, UART0 `0xff` and ATC0_COMMON `0x20ff`: unchanged from idle, not written by
  macOS in the log. A machine without the hypervisor would hold other values in these five.
  The emulated lock words `0x2000x0680`.. (A5) are unchanged from idle.

**The 74 power-domain words at the commit** (was at idle, where different):

| Value | Domains |
|---|---|
| `0xff` | AIC, GPIO, SOC_DPE, SPI_P, UART_P, UART_N, UART0-UART8 |
| `0x200` | FPWM0, FPWM2, I2C0-I2C4, SIO_ADMA, SPI0-SPI4, MCA0-MCA5, DPA0, DPA1 |
| `0x2ff` | FPWM1, AUDIO_P |
| `0x1f0000ff` | SBR, IMX, MCC, SMX |
| `0x1f0002ff` | PMS, SIO (was `0x1400024f`) |
| `0x0f0002ff` | SIO_CPU (was `0x1400024f`) |
| `0x1400024f` | SIO_BUSIF |
| `0x1000030f` | DCS0, DCS1, DCS4, DCS5, DCS6, DCS7 |
| `0x1f0003ff` | DCS2, DCS3, PMS_SRAM (each was `0x1000030f`) |
| `0x1f0f03ff` | PMP (was `0x1000030f`) |
| `0x1f0023ff` | ANS2 (was `0x1000230f`) |
| `0x1000230f` | SEP |
| `0x0f000300` | RMX (was `0x1000030f`), MMX, ISP_SET1, ISP_SET2 |
| `0x2300` | DISP0_FE (was `0x20ff`), DISPEXT_FE, ISP_SYS |
| `0x0f002300` | GFX (was `0x1000230f`), VENC_SYS, ANE_SYS |
| `0x0f040300` | DISP0_CPU0 (was `0x1404024f`), DISPEXT_CPU0 |
| `0x300` | AES, ISP_SET0, ANE_SYS_CPU |
| `0x20ff` | ATC0_COMMON `[A3]` |

So at the commit the display and graphics domains are off; **everything else that is on at
idle is still on** (interrupt controller, pin controller, UARTs, memory controller, PMS, SBR);
PMP, ANS2, PMS_SRAM, SIO, SIO_CPU and two of the eight DRAM-controller domains read as more
on than at idle (their coprocessors were stopped, and the words read `..3ff` / `..2ff` instead
of `..30f` / `..24f`); six DRAM-controller domains read `0x1000030f` as at idle. This agrees
with R25: macOS turns no domain off for the sleep apart from the display path.

**After the snapshot** the hypervisor writes the seven held words (E7, last part); the state
the chip actually goes down with differs from the snapshot in those: UART0, UART_P
`0x100000ff`; SIO, SIO_BUSIF `0x0f0000ff`; ATC0_USB, ATC0_USB_AON `0x3f0`; ATC0_COMMON `0x23f0`
`[ARTEFACT]`.

**Not in the snapshot list**, so still known only as last written values (4.2): the memory
controller's shutdown words (`0x200001c00`, `0x200158000`, `0x200024000`, P+`0x21000`,
DCSn+`0x7a0`, ...), `0x23d2c4000`, the timer and cluster words, the interrupt controller, the
SPMI controllers, the watchdog words, the pin controllers.

### 4.1a The commit in G and H, word by word (858 words)

Scripts `commit_gh.py`, `snapvar_gh.py`, `ps_commit_gh.py`; tables (all in `var/spec/`):
`commit-state-gh.tsv` (one row per word: address, name, G and H values in the "pre-detach"
snapshot taken with macOS awake at the detach, G and H commit values, whether G and H agree, how
the word got from the one to the other in each capture, the reads of it in the log, and the
Linux readings of section 12), `snapvar-gh.tsv` (the words that changed or vary, with their
value in every snapshot of all seven captures), `ps-commit-gh.tsv` (the 137 domain words).
**Method.** "Written" means a logged write between the detach and T, or a write of a guarded
word handled by the hypervisor ("pmgr" record, the value macOS wrote). Each write is placed in a
phase by the console line before it, re-derived for G and H (E1 starts at the first of the audio
"Set PowerStage (4 -> 6)", the display request, "awdl0 disable"; E2 at "PM response took"; E3 at
"IOCPUSleepKernel enter"; E4 at the first stop-bit record; E5 at the first quiesce action; E6 at
the interrupt-controller quiesce action). (The phase column of
`var/commit-state/macos135-det9-125words-writes.tsv` was not derived this way: it puts the
display-domain writes of T-0.73 in E3 and SIO_CPU's write of T-0.016 in E6. By the console lines
they are in E2 and E5. This section uses the re-derived phases.) The awake value is the
"pre-detach" snapshot, 434 s (H) and 438 s (G) before T.

**G against H at the commit** (792 words): **774 equal, 18 vary** (`[VARIES]`, values G / H):
- `MCC.plane0-3+0x680` `0x800` / `0xe59` and `+0x684` `0x82c` / `0xe85` (8 words; emulated by the
  hypervisor, A5; seven values seen in the 12 idle snapshots, so they vary at idle too);
- `DCS3+0x500` (`0x2002c0500`) `0x2440004` / `0x1440004` (both values seen at idle);
- clock word `0x23b040020` `0x85100000` / `0xc5100000`;
- domain words DCS0, DCS1, DCS5 `0x1000030f` / `0x1f0003ff`; DCS2, DCS3 `0x1f0003ff` /
  `0x1400034f`;
- power-gate words `0x23b71c0d8`, `0x23b71c108`, `0x23b71c120` `0xc0040307` / `0x80040307`.

**How each word got to its commit value** (counts of G's 792 words; H in brackets):
1. **Unchanged from awake and not written: 752 [746].** Among them all 80 memory-controller
   words and all 448 DRAM-controller words in both captures (`DCS3+0x500` and the plane words
   +`0x680`/`684` differ between G and H, but each equals its own awake value): **the memory and
   DRAM controllers, in what the list covers, look at the commit as they did awake, in both.**
2. **Written by macOS, 18 words in both (19 in H's 858)**, the same words, phases, counts and
   values in G and H (I2C3: 140 writes in both; SPI3: 100 in G, 116 in H):
   - E1/E2 bus cycles: I2C3 (E1, the audio path), I2C0, SPI2, SPI3 (E2): last write `0x3f0`;
     commit `0x200`, which is what macOS read after its last write.
   - display and graphics (E1 and E2): RMX last write `0x300`, commit `0x0f000300`; DISP0_FE and
     DISPEXT_FE `0x23f0` -> `0x2300`; DISP0_CPU0 and DISPEXT_CPU0 `0x0f0403f0` -> `0x0f040300`;
     GFX `0x0f0023f0` -> `0x0f002300`. Each commit value is what macOS read after its last write.
   - storage, H only (not in G's list): APCIE_ST written `0x0f0000ff` then `0x0f0003f0` (E2,
     T-0.642), read back `0x0f000200` three times; **commit `0x0f000300`**: bit 8 is set at the
     commit and was not in the last read, with no logged write in between.
   - E5 power-manager quiesce, clock muxes `0x23b040140`, `144`, `148` (`0x85100000`), `14c`,
     `154` (`0x87100000`): one write each of `0x80100000` (T-0.0204 G, T-0.0208 H), read back at
     once as the old value; commit = the old value = awake value.
   - E5-8j, SIO_CPU `0x23b7001d0`: read `0x1400024f`, written `0x0400024f` (T-0.0156 G, T-0.0160
     H), not read again; **commit `0x0f0002ff`** in both. SIO `0x23b7001c8` and SIO_BUSIF
     `0x23b7001c0`: macOS's writes of `0x0f0000ff` held by the hypervisor (A3), the hardware read
     `0x1400024f` just before; commit SIO **`0x1f0002ff`**, SIO_BUSIF `0x1400024f` (unchanged)
     in both. So SIO and SIO_CPU went from `0x1400024f` to their commit values although the
     write that reached SIO_CPU was `0x0400024f` and none reached SIO.
3. **Changed with no logged write: 22 [28]; 21 in both.** No core's write to these words is in
   the log (none lies on an untrapped page). Of these, only ANS2 is read by macOS between the
   detach and T, so for the others the change happened somewhere between the detach and the
   commit, not located further.
   - **The same change in G and H, from a value that is the same in all 12 idle snapshots of
     the seven captures** (so a change that comes with the sleep):
     - clock words, bit 8 cleared: `0x23b04003c`, `0x23b040040` (`0x87100100` -> `0x87100000`),
       `0x23b040114`, `0x23b040118`, `0x23b04011c` (`0x85100100` -> `0x85100000`); bit 8 set:
       `0x23b040088` (`0x88100000` -> `0x88100100`), `0x23b040094` (`0x87100000` ->
       `0x87100100`), `0x23b04009c`, `0x23b0400a0` (`0x85100000` -> `0x85100100`). In the wake
       snapshot of all seven, `03c`, `040`, `088`, `09c`, `0a0` keep the commit value, `114`-`11c`
       read the awake value again and `094` reads `0x86100000`;
     - PMP `0x1000030f` -> `0x1f0f03ff`; PMS_SRAM `0x1000030f` -> `0x1f0003ff`; ANS2
       `0x1000230f` -> `0x1f0023ff`. ANS2 reads `0x1000230f` at T-7.36 and `0x1f0023ff` at
       T-2.39 (G: T-7.36, T-2.40), in E1, before the storage coprocessor's shutdown exchange
       (T-0.65 in H). Wake snapshot: PMP `0x0f0003ff`, PMS_SRAM `0x0f000300`, ANS2 `0x0f002300`;
     - power-gate word `0x23b71c0f0` `0xc0040307` -> `0x80040307` (bit 30 cleared);
     - `0x23b720030` `0x014d514d` -> `0x01515151`, `0x23b720034` `0x01404940` -> `0x01494949`,
       `0x23b720044` `0x01404940` -> `0x01494949`. Wake snapshot (all seven): `0x01515151`,
       `0x01676767`, `0x016c6c6c`. (Values only: the bytes `0x49` and `0x51` are also the second
       and third bytes of the final status values of R22a, `0x494900` and `0x515100`; for Linux
       see section 12, L3.)
     - always-on clock words `0x23d240040` `0x02100100` -> `0x01101100` and `0x23d240314` 0 ->
       `0x01000000`; the wake snapshot keeps both.
   - **Changed in both, to different values** `[VARIES]`: `0x23b040020` (`0x85100100` -> G
     `0x85100000`, H `0xc5100000`); DCS2 (G `0x1000030f` -> `0x1f0003ff`; H `0x1f0003ff` ->
     `0x1400034f`); DCS3 (G `0x1000030f` -> `0x1f0003ff`; H `0x1000030f` -> `0x1400034f`).
     These three also vary between idle snapshots. (With the 18 above: the 21 changed in both.)
   - **Changed in one capture only, in words that also vary between idle snapshots**
     `[VARIES]`: DCS0, DCS1, DCS5 (H, `0x1000030f` -> `0x1f0003ff`); power-gate words
     `0x23b71c0d8`, `108`, `120` (H, bit 30 cleared); always-on clock words `0x23d240000` (G,
     `0x91100010` -> `0x80100010`) and `0x23d240024` (H, `0x81100000` -> `0x81100100`).
4. **The 66 domain words added in H** have no awake snapshot value. Eight are read in H's log:
   DISPDFR_FE `0x2300`, JPG `0x0f000300`, MSR and AVD_SYS `0x0f002300`, ATC1_COMMON `0x2300`
   (each read from T-7.43 to T-0.017 with the commit value); APCIE_GP read `0x1400234f` at
   T-7.43 and `0x1000230f` at T-0.017 (= commit); APCIE_ST (item 2). The other 58 are not
   accessed in the log; their values with macOS awake are not observed.
5. **The cores' domains** (H): ECPU1-3 and PCPU0-3 read `0x100` (requested 0, reported 0), ECPU0
   `0x1f0` (requested 0, reported `0xf`), ECPM `0x21f0`, PCPM `0x2100`. At the commit every core
   but core 0 has made its `CYC_OVRD_EL1` write (E7) and been taken down; the performance
   cluster's PCPM reports 0, the efficiency cluster's ECPM `0xf`. `[ARTEFACT in part]`: under
   the hypervisor each core's final register write is carried out by the hypervisor (A4, E7).

**After the snapshot** (H as G): the hypervisor's seven held writes, UART0 and UART_P
`0x100000ff`, SIO and SIO_BUSIF `0x0f0000ff`, ATC0_USB and ATC0_USB_AON `0x3f0`, ATC0_COMMON
`0x23f0` `[ARTEFACT]`.

### 4.1b The commit in G, H and I, and every commit word with macOS awake (capture I; added this round)

Scripts `commit_ghi.py`, `snapvar_ghi.py`, `commit_list.py`; tables `commit-state-ghi.tsv` (one
row per word of I's 862: the awake values of G, H, I and I's "awake-extra", the commit values of
G, H, I, whether they agree, how the word got to its commit value in I, the wake values),
`snapvar-ghi.tsv` (changed or varying words in every snapshot of all eight captures). The values
of all 725 non-domain words are written out in appendix B; the 137 domain words in 4.2a.

**G, H and I at the commit.** Of G's 792 words, **767 are equal in all three, 25 vary**. H and I
agree in 834 of H's 858; the 24 that differ are all in G's 792 list, so **the 66 domain words H
added read the same at H's and I's commit**. The varying words (values G / H / I) `[VARIES]`:
- `MCC.plane0-3+0x680` `0x800` / `0xe59` / `0xad1`, +`0x684` `0x82c` / `0xe85` / `0xafd`
  (8 words, emulated, A5; each equal to its own capture's awake value);
- `DCSn+0x500` for n = 1..7: G `0x2440004` in all seven, H `0x2440004` except DCS3
  `0x1440004`, I `0x1440004` in all seven; `DCS0+0x500` reads `0x10480004` in all three. Each
  value equals the capture's own awake value; both values occur awake (`snapvar-ghi.tsv`);
- clock word `0x23b040020` `0x85100000` / `0xc5100000` / `0x85100000`;
- domain words DCS0 `0x1000030f` / `0x1f0003ff` / `0x1000030f`; DCS1 the same as DCS0; DCS2
  `0x1f0003ff` / `0x1400034f` / `0x1000030f`; DCS3 the same as DCS2; DCS5 the same as DCS0;
- power-gate words `0x23b71c0d8`, `108`, `120` `0xc0040307` / `0x80040307` / `0xc0040307`, and
  **`0x23b71c0f0` `0x80040307` / `0x80040307` / `0xc0040307`**: the bit-30 change that G and H
  showed for `0x23b71c0f0` (R52) did not happen in I.
**Wake snapshot**: 259 of 264 words equal in G, H, I; DCS2, DCS3, DCS4, DCS5 and `0x23d240000`
vary (`0x80100010` / `0x91100010` / `0x80100010`).

**How each word got to its commit value in I** (method of 4.1a; the awake value is "pre-detach"
for its 792 words and "awake-extra" for the other 70):
1. **Unchanged and not written: 808** (751 + 57 of the 70). Among them all 528 memory- and
   DRAM-controller words (also `DCSn+0x7b0` = 0 on all eight, section 12 L2), and **all 13 words
   of 1.9's last item and the nine never-written domains of 4.3** (ATC1_COMMON `0x2300`, ATC0_PCIE,
   ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE `0x300`, MSG `0x200`, ATC1_USB_AON,
   ATC1_USB `0x300`): with macOS awake they already hold their commit value.
2. **Written by macOS: 19**, the same words, phases and values as H's 19 (4.1a item 2); APCIE_ST
   reads `0x0f000300` after its last write in I (as in D, G; `0x0f000200` in E, F, H).
3. **Changed with no logged write: 35.** 23 against "pre-detach": the nine clock words of R52
   (same direction and values as G and H), `0x23b040020`, PMP, PMS_SRAM, ANS2 (first read
   with the commit value at T-2.40 in E1, as in G and H), `0x23b720030`, `034`, `044`,
   `0x23d240040`, `0x23d240314` (all as in G and H), and, as words that vary at idle,
   DCS2 (`0x1f0003ff` -> `0x1000030f`), `0x23b71c0d8`, `108` (bit 30 set), `0x23b71c330`
   (`0xc0040317` -> `0x80040317`; it already read `0x80040317` in "awake-extra" a second
   later), `0x23d240000`. 12 against "awake-extra": the seven cores' words ECPU1-3, PCPU0-3
   `0x1f0` -> `0x100`, PCPM `0x21f0` -> `0x2100` (cores taken down, R53), and the four
   sub-block status words (R22a).
**Awake values that change the reading of R52** (`snapvar-ghi.tsv`): I's "pre-full" (macOS
awake, 18 s before the detach, no entry under way) has **PMP `0x1f0f03ff` and PMS_SRAM
`0x1f0003ff`**, their commit values; "pre-detach" and "awake-extra" 18 s later have
`0x1000030f` again. So these two words take their commit value with macOS awake too; that they
hold it at every commit is still the observation. ANS2 reads `0x1000230f` in all 15 awake
snapshots.

**The 66 domain words of 4.1a item 4 with macOS awake** (I's "awake-extra", 0 errors;
`macos135-det10-awake-vs-commit-new.tsv`): 57 equal to the commit value, 9 different: ECPU1-3
and PCPU0-3 `0x1f0`, PCPM `0x21f0` (taken down for the sleep, R53) and APCIE_ST `0x1000030f`
(written in E2). ECPU0 `0x1f0` and ECPM `0x21f0` are the same awake and at the commit.

**The four sub-block status words** (R22a, gap V4), first readings with the sub-blocks on:

| Word | Awake ("awake-extra") | Waiting, after the control word is written 0 (E5) | Commit |
|---|---|---|---|
| `0x23b7483e0` | `0x4d4d01` | `0x514d02` x2, then `0x515100` | `0x515100` |
| `0x23b7487e0` | `0x404001` | `0x494002` x9, then `0x494900` | `0x494900` |
| `0x23b748be0` | `0x1` | `0x0` at the first read | `0x0` |
| `0x23b748fe0` | `0x404001` | `0x494002` x3, then `0x494900` | `0x494900` |

With the sub-block on the low byte reads 1 and the second and third bytes are equal (`0x4d`,
`0x40`); while waiting the low byte reads 2 and the third byte has the new value (`0x51`,
`0x49`) while the second still has the old one; when done the low byte is 0 and both bytes have
the new value. The awake bytes `0x4d` and `0x40` are bytes of `0x23b720030` (`0x014d514d`) and
`0x23b720034`/`044` (`0x01404940`) awake, and the done bytes `0x51` and `0x49` bytes of their
commit values (`0x01515151`, `0x01494949`) (values only; section 12 L3). The burst in I:
`0x23b748400`, `800`, `c00`, `000`, each read 1 and written 0, from T-0.015895 to T-0.015801;
macOS accesses none of `0x23b720030`-`048` between the detach and T.

### 4.1c The always-on block, the watchdogs and the wake masks at the commit (capture K; round 9)

The 17 words added to K's commit list, read with macOS awake (the "awake-extra" snapshot, about
7 min before the entry), at the commit (on core 0 after its own final write and the seven other
cores' real ones, before any write of the instrument's: A6), and by the instrument at its wake
entry (`r6-det12.txt`, `r9-det12.txt`):

| Word | Awake | At the commit (K) | At the wake entry (K) |
|---|---|---|---|
| `0x23d2b8028` | `0x0` | **`0x1000000`** | `0x8000000` (as in D-J) |
| `0x23d2b8040` | `0x20` | `0x20` | `0x22` (as in D-J) |
| watchdog 2 count / bite / control `0x23d2b0020` / `24` / `2c` | `0x4ee0c17e` / `0x80befc00` / 0 | **`0x62189` (16.74 ms) / `0x7270e00` (5 s) / 4** | `0x770474` (0.326 s) / `0x7270e00` / 0 (as in D-J) |
| watchdog 0 count `0x23d2b0000` | running | `0xa6bae6` (455.3 ms) | `0x5299c` (14.1 ms) |
| watchdog 1 count / bite / control `0x23d2b0010` / `14` / `1c` | running | `0xa6ba2f` (455.3 ms) / `0x55d4a800` (60 s) / 0 | `0x5292d` (14.1 ms) / `0xd693a400` / 4 (the instrument's, J) |
| `0x23d2c4000` | `0x1` | **`0x0`** | not read |
| `0x23d0d9378` | `0x0` | `0x0` | not read |
| `0x23b71c090` | `0x8004030c` | `0x8004030c` (as in G-J) | not read |
| `0x23b71c360` | `0xc004030b` | `0xc004030b` | not read |
| AP wake-source masks `0x23d004008` / `00c` / `010` / `014` / `018` | `0xf3ffafff` / `0xffb97eff` / `0xfffdeffe` / `0xffffffff` / `0x03ffff87` | the same five values | not read |
| always-on clock words `0x23d240024` / `03c` / `048` | `0x81100100` / `0x81100100` / `0x82100100` | the same (and as at G-J's commits, appendix B) | not read |

What these readings say:
1. **Watchdog 2 is armed before the cores go down, by no logged access.** Its count, 16.74 ms
   when read, puts its start at about T-0.01538 (`r9_det12.py`, with the read time interpolated
   from the word's place in the snapshot); macOS's first write of `0x23d2c4000` = 1 (R24) is at
   T-0.015375. The same method puts the restart of watchdogs 0 and 1 0.29 ms after macOS's logged
   writes of 0 to their counts (T-0.4542), so the method is good to about 0.3 ms: **watchdog 2
   started counting within about 0.3 ms of R24's write**, with bite 5 s and control 4. The log
   has no write to the watchdog page after T-0.0356 (R15's), the watchdog page is trapped (R15's
   writes are logged), and the instrument does not write watchdog 2 (A6). Who armed it is not
   observed. Awake it held a different bite (`0x80befc00`) with control 0; at the wake entry its
   bite is again 5 s with control 0 and a count of 0.326 s (section 5). One capture.
   *(Round 10, L, `det19b`, `det21`; superseded in its timing by the table after this list.)*
   Watchdog 2 is already armed **before** macOS's first write of `0x23d2c4000` reaches the
   hardware, its count started 31-45 microseconds before that write's record.
2. `0x23d2b8028` is 0 awake, `0x1000000` (bit 24 alone) at the commit and `0x8000000` (bit 27
   alone) at every wake entry; `0x23d2b8040` is `0x20` awake and at the commit, `0x22` at every
   wake entry. When bit 24 was set between the awake reading and the commit is not observed.
   *(Round 10.)* It is already set at the first reading inside macOS's first write of
   `0x23d2c4000` (L, `det19b`, `det21`); when, relative to watchdog 2's start, is not read.
3. **`0x23d2c4000` reads 0 at the commit** after macOS wrote it 1 three times (the last at
   T-0.00066) and read 1 awake (R24); no write of 0 to it is logged. *(Round 10.)* It reads 1
   just before macOS's first write of 1 and **0 just after it**, and 0 before and after the
   second and third (L, `det19b`, `det21`): the first write of 1 is followed by a read of 0.
4. `0x23d0d9378` reads 0 at the commit, before the instrument's own SPMI commands: no reply
   status of the power chip's controller is left from macOS's commands (R60).
5. The AP wake-source masks, never written by macOS in any log, hold their awake values at the
   commit. Which sources they leave enabled is not established for t8103. *Reference, not an
   observation:* on T8140 and T8132 Aurora's driver treats a set bit in these mask words as
   "masked" and its wake-block layout puts 8 mask words from +`0x08` and the status words
   after them (reference, section 3.2). On the M1 the words from +`0x08` to +`0x18` are five,
   followed by the status words macOS reads from +`0x1c` (R33); four of the five have clear
   bits. By the reference's reading some sources are enabled; which, on t8103, is not known.
6. Watchdogs 0 and 1 at the commit count 455 ms from macOS's zeroing in E3 (R15); watchdog 1's
   bite reads 60 s with control 0 before the instrument writes it.

**Inside macOS's three writes of `0x23d2c4000` (round 10; L, `det19b`, `det21`; the probe of A6;
`r7-det*.txt`, `r10-checks.txt` part 1).** Read by core 0 just before the write reaches the
hardware and again just after it; counts L / `det19b` / `det21`; every other value the same in
the three runs:

| Write (time in L) | Read | `0x23d2c4000` | Watchdog 2 count | bite | control | `0x23d2b8028` | `0x23d2b8040` |
|---|---|---|---|---|---|---|---|
| 1 (T-15.6 ms) | before | **1** | 42.6 / 52.7 / 56.4 microseconds | `0x7270e00` | **4** | **`0x1000000`** | `0x20` |
| 1 | after | **0** | 52.1 / 64.4 / 65.8 microseconds | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 2 (T-4.1 ms) | before / after | 0 / 0 | 11.575 / 11.562 / 11.776 ms; +9 microseconds | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 3 (T-0.97 ms) | before / after | 0 / 0 | 14.712 / 15.180 / 15.040 ms; +9 microseconds | `0x7270e00` | 4 | `0x1000000` | `0x20` |

Awake (the same list at each detach) watchdog 2 read bite `0x80befc00`, control 0, and
`0x23d2b8028` 0, `0x23d2b8040` `0x20`. So **before the first write of `0x23d2c4000` reaches the
hardware, watchdog 2 is armed (5 s, control 4) and `0x23d2b8028` has bit 24 set**; nothing of
these six words changes at any of the three writes except the count and, at the first,
`0x23d2c4000` itself.

**When watchdog 2 started** (`r7_wd2start.py`: each count subtracted from the core's timer read
just after it, assuming the count starts at 0 when the watchdog is armed): L t = 445.3080573,
`det19b` 433.0520395, `det21` 433.6433051, from the first set; the later sets put it 7-10
microseconds later, so the start is good to about ±10 microseconds. Against the access log (a
write's record is put before the write reaches the hardware):

| Core 0's records, time from watchdog 2's computed start (microseconds) | L | `det19b` | `det21` |
|---|---|---|---|
| `W 0x23b71c080` = `0x80000000`, `W 0x23b71c088` = `0x80000000` (E5-8i) | -29, -25 | -32, -29 | -29, -25 |
| `R 0x23b718000` = `0xf`, `W 0x23b718000` = 0 (E5-8i) | -18, -14 | -16, -12 | -19, -15 |
| `R 0x23b718004` = `0xf`, **`W 0x23b718004` = 0** (E5-8i) | -9, **-1.3** | -9, **-5.5** | -11, **-7.1** |
| SIO, SIO_BUSIF read and written (held by the instrument, A3; E5-8j) | +4 to +19 | -1.5 to +14 | +9 to +32 |
| `R`/`W 0x23b7001d0` SIO_CPU `0x1400024f` -> `0x0400024f` (E5-8j) | +22, +25 | +16, +19 | +34, +38 |
| the first `W 0x23d2c4000` = 1 (E5-8k) | +31 | +32 | +45 |

In each run the start falls 1.3-7.1 microseconds after the record of macOS's write
`0x23b718004` = 0; within the ±10 microseconds the nearest earlier write that reaches the
hardware is that one (the SIO and SIO_BUSIF writes are held by the instrument and do not reach
it), and the nearest later one the SIO_CPU write at +16 to +38. That the times coincide is a
reading; **what arms watchdog 2 and sets `0x23d2b8028` bit 24 is not observed**. Round 9's "within
about 0.3 ms of the first write" (from the count at the commit) is replaced by this.
*(Round 11, `det23`, `det24`; `r11-checks.txt` part 4.)* The same in both: the six probe reads
as in the table above (`0x23d2c4000` 1 before the first write, 0 after it and around the
second and third; bite `0x7270e00`, control 4, `0x23d2b8028` `0x1000000`, `0x23d2b8040` `0x20`
throughout), watchdog 2's count before the first write 37.8 / 57.2 microseconds, its start
7.5 / 3.2 microseconds after the record of `W 0x23b718004` = 0 and 25.5 / 44.8 microseconds
before the first `0x23d2c4000` write. Over five captures: start 1.3-7.5 microseconds after
`W 0x23b718004` = 0; count at the first write 38-57 microseconds. At the commit both read
`0x23d2c4000` 0, `0x23d0d9378` 0, `0x23d2b8028` `0x1000000`, `0x23d2b8040` `0x20`, watchdog 2
bite `0x7270e00` and control 4 (`r8-det2[34].txt`), as L, `det19b`, `det21` (`r7-det*.txt`).

**After the commit with one core kept running** (`det16`, **[HV-CHANGED]**, 1.7d): for 4.9 s
none of `0x23d2b8028` (bit 24), `0x23d2b8040` (`0x20`), `0x23d2c4000` (bit 0 clear),
`0x23b71c090` (bit 30 clear), `0x23b71c360` (bit 30 set) or power-chip `0x0201` (`00`) changed;
watchdog 2 counted with control bit 2 set; then a reset. With all eight cores down (K) the
chip powered down and woke. What these words do after the last core goes down is not observed
in any run.

### 4.1d The CPU start/stop block and the power-gate page at the commit (L, `det19b`, `det21`; round 10)

Read awake (the "awake-extra" list at each detach) and at the commit (`r7-det*.txt`,
`r7-pwrgate-records.md`, `r10-checks.txt` parts 3-5). Linux readings are marked **[LINUX]**: the
lab's register scans of Linux awake on the stock kernel (`var/hwdb/m1-hw.db`, snapshot 12 of
2026-11-16 for the power-gate page, `var/regmap/scan-pmgr-1c000/reads.txt`; snapshot 16 of
2026-11-18 02:12 for the CPU block), not the driver's entry or commit.

**The CPU start/stop block `0x23b754000`-`0x23b75401c`** (eight words):

| Word | Awake (three runs) | At the commit (three runs) | Written by macOS in the entry | [LINUX] awake |
|---|---|---|---|---|
| `0x23b754000` | 0 | **`0xfe`** | cores 4, 1, 5, 2, 3, 6, 7 each their own bit (`0x10`, `0x2`, `0x20`, `0x4`, `0x8`, `0x40`, `0x80`) at T-0.090 s (R11), passed to the hardware (A4) | 0 |
| `0x23b754004` | 0 | **`0xfe`** | none (no write to it in any logged entry; the instrument writes none, A4) | 0 |
| `0x23b754008`-`0x23b75401c` | 0 | 0 | none | 0 |

So at the commit both words hold bits 1-7 (cores 1-7) and not bit 0 (core 0, which writes no
stop bit). +`0x0` holds the seven stop bits written 90 ms earlier; +`0x4` reads the same bits
with no logged write, so something other than a logged access set them between the awake reading
and the commit; when is not read. At the wake core 0 writes +`0x4`, +`0x8`, +`0xc` once per core
(W2); under the instrument those writes of +`0x4` do not reach the hardware (A4).
*Documentation, not an observation:* the Asahi page "SMP" (asahilinux.org/docs/hw/cpu/smp/)
names +`0x4` the "system-wide CPU core startup/active bitmask" (bit = core) and +`0x8`, +`0xc`
the core-start words of clusters 0 and 1, and says that without a core's bit in +`0x4` "AIC
interrupts won't work"; it does not describe +`0x0` or what +`0x4` reads.

**The power-gate page `0x23b71c000`-`0x23b71c704`** (450 words). Its non-zero words are a header,
`0x80000000` at +`0x000`, +`0x010`, ... +`0x080` and +`0x088`, and from +`0x090` 69 groups of six
words at a stride of `0x18` (the grouping is the observation stage's reading of the values'
stride, not a documented layout; the device tree lists "pwrgate-reg" ranges at +`0x010`,
+`0x310`, +`0x610`, section 1.9). macOS's only writes to the page in any logged entry are
`0x23b71c080` and `0x23b71c088` = `0x80000000`, each read `0x80000000` first (E5-8i).
- **Changes between awake and the commit with no write:** 22 / 21 / 20 words in L / `det19b` /
  `det21`; 23 words in all change or differ between runs (`r10-checks.txt` part 3): the first
  words of groups +`0x0d8`, `0f0`, `108`, `120`, `330`, `348`, `5a0` go from bit 30 set to clear
  (`0xc004....` -> `0x8004....`; `0f0` and `120` not in every run), those of +`0x198` and
  `1b0` from clear to set; the sixth word of several groups between `0xc000000` (or
  `0x6000000`) and 0 (+`0x0ec`, `104`, `11c`, `134`, `1ac`, `1c4`, `344`, `35c`, `5b4`); the
  fifth word of the five groups +`0x1c8`-`0x228` from 0 to `0x30000000`. Every other word (427)
  has one value in all six readings. The words of the earlier captures' list agree: `0x23b71c090`
  `0x8004030c` and `0x23b71c360` `0xc004030b` at the commit, as in K; `0x23b71c0d8`, `0f0`,
  `108`, `120` `[VARIES]` as in G-K (appendix B).
- **The header** reads `0x80000000` at all ten words awake and at the commit in all three runs.
  **At every wake** (A, B, D-L, `det19b`, `det21`: all thirteen captures with a wake;
  `r10-checks.txt` part 4) macOS's core 0 reads **`0x23b71c000` = 0** and writes it
  `0x80000000`, then reads `0x23b71c040` = `0x80000000` and writes it `0x80000000` (W1-2a,
  right after the poll of `0x23b718004`); 10 ms later it reads and rewrites `0x23b71c080`,
  `0x23b71c088` (`0x80000000`). It writes neither `0x23b71c000` nor `0x23b71c040` in any logged
  entry. So of the four header words macOS reads at the wake, `0x23b71c000` is the one that
  comes back from the sleep cleared, and macOS sets it again before it starts the other cores
  (W2). (The other six header words are not read at the wake.)
- **[LINUX] awake (snapshot 12):** `0x23b71c000` reads **0**, the other nine header words
  `0x80000000`. Of the 450 words, 32 differ from macOS's value at the commit in every run:
  `0x23b71c000`, and 31 words of 16 groups, mostly the bit-30 / sixth-word pattern above
  (`0x23b71c360` reads `0x8004030b`, macOS `0xc004030b` awake and at the commit; the five fifth
  words `0x30000000` at macOS's commit read 0, as macOS awake). Linux was awake with its own
  devices on, so the group words are not expected to match; the header word is the one difference
  that macOS's entry does not produce (no change of it is seen between macOS awake and its commit).
  *Reference, not an observation* (reference section 2.2, item "Boot core power-gate enable"): on
  T8140 the per-cluster power-manager words at the power-gate block's +`0x0` (efficiency cluster)
  and +`0x40` (performance cluster) have a top bit (bit 31) that lets the cluster's cores power
  down in their wait; cores the power manager started come up allowed, the boot core "only
  follows the word", which the loader leaves clear for its cluster, and with it clear "the
  watchdog reset the machine 5 s into every sleep" (J700); on T8132 "iBoot sets E's only". On t8103 the
  correspondence of `0x23b71c000` / `0x23b71c040` to those words is by offset only; no source
  names them, and no M1 run has had `0x23b71c000` clear at a commit, so its effect here is not
  observed.
- *(Round 11; 1.7f.)* **`0x23b71c000` cleared at the end of macOS's entry** (`det23`,
  `det24`, **[HV-CHANGED]**): written 0 by the instrument after macOS's last write to the page
  and before the cores' final writes (in `det24` before every one of them, 0.28 ms before T); it
  read 0 just after the write and 0 at the commit, `0x23b71c040` `0x80000000`; macOS did not
  access it again before the wake; **the chip powered down and woke at the alarm both times**
  (asleep 90.00 s, 89.65 s), with the wake status and the wake-entry words of every earlier
  wake. At the wake macOS read it 0 and wrote `0x80000000` as in every capture (all fifteen).
  So on the M1, under the instrument, bit 31 of `0x23b71c000` at the commit is not needed for
  the power-down and wake: the reference's T8140 account (a reset 5 s after the commit) did not
  occur. What these runs do not cover: the word clear through the whole entry (under macOS it
  was set from the wake or boot until 0.28 ms before T); `0x23b71c040` clear.
  The CPU block in both: +`0x0` = +`0x4` = `0xfe` at the commit, all 0 awake (five captures).
- *(Round 11.)* **[LINUX]** awake, 2026-11-18 03:54 (1.7f): `0x23b71c000` 0, `0x23b71c040`
  `0x80000000`, `0x23b754000` and `0x23b754004` 0: as snapshots 12 and 16, on another boot.

### 4.2a All 137 power-domain words at the commit (H; G for its 71)

From `ps-commit-gh.tsv`. Grouped by H's commit value. "[G x]" gives G's value where it differs;
the last column gives Linux's value **[LINUX]** read on bare metal in the suspend path just
before the driver's entry (run ds13, section 12, L1) where it differs from H.

| H at commit | Domains | Linux ds13 before the entry, where different |
|---|---|---|
| `0x200` | PMS_FPWM0-4, PMGR_SOC_OCLA, AFT0, DEVC0_IVDMC, FPWM0, FPWM2, I2C0-I2C4, SIO_ADMA, SPI0-SPI4, MCA0-MCA5, DPA0, DPA1, MSG | `0x244`: PMS_FPWM0-4, AFT0, DEVC0_IVDMC, FPWM0, FPWM2; `0x2ff`: MSG |
| `0xff` | AIC, DWI, GPIO, SOC_DPE, SPI_P, UART_P, UART_N, UART0-UART8, APCIE, NUB_GPIO, ATC0_USB_AON, ATC0_USB | `0x200`: GPIO, SPI_P, UART_P, UART_N, UART0-UART8; `0x2ff`: ATC0_USB_AON, ATC0_USB |
| `0x300` | AES, DISPDFR_BE, MIPI_DSI, MSR_ASE_CORE, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE, ATC1_CIO, ATC1_CIO_PCIE, ATC1_CIO_USB, VENC_DMA, VENC_PIPE4, VENC_PIPE5, VENC_ME0, VENC_ME1, ANE_SYS_CPU, ATC1_USB_AON, ATC1_USB | `0x3ff`: ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE; `0x2ff`: ATC1_USB_AON, ATC1_USB |
| `0x100` | ECPU1-3, PCPU0-3 | `0x1f0`: ECPU3 (which core ran the read under Linux is not in the log) |
| `0x1f0` | ECPU0 | `0x100` |
| `0x21f0` | ECPM | |
| `0x2100` | PCPM | `0x21f0` |
| `0x1000030f` | DCS4, DCS6, DCS7, NUB_SRAM, DEBUG_USB, DEBUG_AUTH | `0x1f0002ff`: DCS4, DCS6, DCS7 |
| `0x1f0003ff` | DCS0, DCS1, DCS5 [G `0x1000030f`], PMS_SRAM, NUB_FABRIC | `0x1f0002ff`: DCS0, DCS1, DCS5; `0x0f000300`: PMS_SRAM |
| `0x1400034f` | DCS2, DCS3 [G `0x1f0003ff`] | `0x1f0002ff` |
| `0x2300` | DISP0_FE, DISPEXT_FE, DISPDFR_FE, ISP_SYS, ATC1_COMMON | `0x20ff`: DISP0_FE; `0x23ff`: DISPEXT_FE, ATC1_COMMON |
| `0x0f002300` | MSR, GFX, VENC_SYS, AVD_SYS, ANE_SYS | `0x0f002b00`: GFX |
| `0x1f0000ff` | SBR, IMX, MCC, SMX | |
| `0x1f0002ff` | PMS_BUSIF, PMS, SIO, NUB_AON | `0x1f0000ff`: PMS; `0x0f000200`: SIO |
| `0x4000200` | ISPSENS0-3 | |
| `0x1400024f` | PCIE_REF, SIO_BUSIF, NUB_SPMI0, NUB_SPMI1 | `0x1f0000ff`: PCIE_REF; `0x0f000200`: SIO_BUSIF |
| `0x0f000300` | RMX, MMX, JPG, APCIE_ST | `0x1f0000ff`: RMX; `0x0f000200`: APCIE_ST |
| `0x0f000200` | SOC_SPMI0-2 | `0x0f000244` |
| `0x2ff` | FPWM1, AUDIO_P, DEBUG | `0xa00`: FPWM1; `0x200`: AUDIO_P |
| `0x0f040300` | DISP0_CPU0, DISPEXT_CPU0 | `0x1404024f` |
| `0x1000230f` | APCIE_GP, SEP | `0x1f0020ff` |
| `0x0f0002ff` | SIO_CPU | `0x0f000200` |
| `0x1f0f03ff` | PMP | `0x1f0000ff` |
| `0x1f0023ff` | ANS2 | `0x0f002300` |
| `0x20ff` | ATC0_COMMON `[A3]` | `0x22ff` |

**Requested state** (low four bits) at macOS's commit: on (`0xf`) for SBR, IMX, MCC, SMX, PMS,
PMS_BUSIF, PMS_SRAM, NUB_AON, NUB_FABRIC, NUB_SRAM, NUB_SPMI0/1, PCIE_REF, SIO, SIO_BUSIF,
SIO_CPU, DCS0-7, PMP, ANS2, SEP, APCIE_GP, DEBUG_USB, DEBUG_AUTH, AIC, DWI, GPIO, SOC_DPE, SPI_P,
UART_P, UART_N, UART0-8, APCIE, NUB_GPIO, ATC0_USB, ATC0_USB_AON, FPWM1, AUDIO_P, DEBUG,
ATC0_COMMON (`0x20ff`, hypervisor-held, A3): 54 words; the other 83 request 0. **[LINUX]**
Linux before its entry (ds13) requests on where macOS's commit requests 0: RMX, DISP0_FE,
DISP0_CPU0, DISPEXT_FE, DISPEXT_CPU0, ATC1_COMMON, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE,
ATC0_CIO_USB, ATC1_PCIE, MSG, ATC1_USB_AON, ATC1_USB (14); requests 0 where macOS requests on:
GPIO, SIO_BUSIF, SIO, SIO_CPU, FPWM1, SPI_P, UART_P, AUDIO_P, UART_N, UART0-UART8, PMS_SRAM,
ANS2 (20); requests 4 where macOS requests 0: SOC_SPMI0-2, PMS_FPWM0-4, AFT0, DEVC0_IVDMC,
FPWM0, FPWM2 (12). The other 91 words request the same state; of those, the reported bits
differ for the DCS words, PMS, PMP, SEP, APCIE_GP, GFX, the cores' and clusters' words,
APCIE_ST, ATC0_COMMON and the ATC0 USB words (table).

*(Added this round.)* **Capture I** has every one of the 137 words at H's value except the DCS
words (4.1b: DCS0-3, DCS5 `[VARIES]`), so the requested state of all 137 is the same at the
three commits G (for its 71), H and I.

**The first port's words and the guarded words: what macOS asked for, against what the
snapshot shows** (corrected this round, gap Q4). The snapshot reads the hardware. For the
guarded words (A3) the hardware held the hypervisor's state, and macOS's own requests were held
back and written by the hypervisor after the snapshot (E7, last part). macOS's own last
requests, from the hypervisor's log (`run-det10.out`, boot; the same values in the commit-write
records of G, H, I):
- **ATC0_COMMON** `0x23b700420`: at boot macOS read `0x22ff`, wrote **`0x23f0`** (request 0)
  and then read `0x2000` (the hypervisor's composed value; hardware `0x20ff`); **ATC0_USB**
  `0x23d280098` and **ATC0_USB_AON** `0x23d280088`: read `0x2ff`, wrote **`0x3f0`**, then read
  `0x0` (hardware `0xff`). No later write by macOS. So **macOS requests these three off**, from
  boot on; the snapshot's `0x20ff` / `0xff` / `0xff` are the hypervisor's use of the port
  `[ARTEFACT A3]`, and the chip went down with macOS's `0x23f0`, `0x3f0`, `0x3f0` written by the
  hypervisor after the snapshot `[ARTEFACT A6]`.
- **UART_P**, **UART0**: macOS's last write `0x100000ff` (request on, boot); **SIO**,
  **SIO_BUSIF**: `0x0f0000ff` (request on, E5-8j). These four are on in macOS's request as in
  the snapshot.
- **ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB** (not guarded) read `0x300` at the
  commit of H and I and with macOS awake in I, and are never written in any log. macOS had no
  driver for the first USB-C/Thunderbolt port in any capture (A2): their state at the commit is
  that of a machine on which macOS did not use the port `[A2]`. What macOS does with the first
  port's domains when it drives that port is **not observed**; *settles it:* a capture without
  A2 (the port's devices left in the device tree, the hypervisor reached over the second port
  or a serial console).
So by macOS's own requests the requested state at the commit is on for 51 words (R54's list
without ATC0_COMMON, ATC0_USB, ATC0_USB_AON) and 0 for 86.

### 4.2 Last values written (all captures)

In A and B "commit" is T, the end of the log, not the true power-down (A11); in D, E, F, G it
is the real last access.

- **Last value written to each word written in the entry** (T-10.6 to T): 602 words; 600 written
  in both captures; **534 with the same last value**, 538 with the same number of writes
  (`commit_state.py`, `commit-last-writes.tsv`). Of the 66 that differ, 55 are in SMC shared
  memory `0x23fe5f0xx`-`0x23fe5f3xx`, 7 in storage (`0x27bcc1004`, `0x27bcc100c`, `0x27bce490c`,
  `0x27bce4910`, `0x27bce8118`, and `0x27bc50030`/`070` written only in A), 2 in the PWM
  (`0x235044018`/`01c`), and `0x236408114`, `0x242408800`, `0x6c0c02140`, `0x6c0c10174`.
- Selected last-written values, identical in both: clock muxes `0x23b040140`-`154` =
  `0x80100000` (not what reads back, E5-8a);
  `0x23b734000`, `0x23b778000`, `0x23b77c000` = 0; `0x23b748000`/`400`/`800`/`c00` = 0;
  `0x23b718000`/`004` = 0; `0x210e20660`, `0x211e20660` = 0; `0x210e48080`, `0x211e48080` = 0;
  `0x23d2c4000` = 1; `0x23d0d9338`, `0x23d0e1338`, `0x24a829338` = 1; `0x236400044`,
  `0x23bc00044` = 0; `0x200001c00` = 0; `0x200158000`, `0x200024000`, `0x200024008`,
  `0x200200584` = 0; `0x200155000` = 0; P+`0x21000`, P+`0x21008` = 0 on the four planes;
  DCSn+`0x7a0` = 0 on the eight controllers; `0x23d2b8008`, `0x23d2b800c`, `0x23d2b000c` = 0;
  `0x24a820900`, `0x24a820904`, `0x23d1f0900` = `0xffffffff`; domain words DISP0_CPU0
  `0x0f0403f0`, DISP0_FE `0x23f0`, DISPEXT_CPU0 `0x0f0403f0`, DISPEXT_FE `0x23f0`, RMX `0x300`,
  GFX `0x0f0023f0`, APCIE_ST `0x0f0003f0`, SIO_CPU `0x0400024f`, I2C0/I2C3/SPI2/SPI3 `0x3f0`.
- **Everything else: the "pre-full" snapshot** (`snap-pre-full.tsv`): taken 108.6 s (A) and
  43.6 s (B) before T. The log says 793 words; 792 distinct addresses are present in each
  capture (the count does not add up; one address is listed twice). **777 of 792 have the same
  value in both captures.** The 15 that differ: `0x200000680`/`684` and the same in the other
  three planes (8 words, emulated, A5), DCS1/DCS3/DCS4/DCS7 +`0x500` (`0x2440004` in A,
  `0x1440004` in B), `0x23b040020`, `0x23b71c120`, `0x23d240000`. Only 16 snapshot words are
  among those written during the entry, so for the other 776 the snapshot is the best available
  statement, with the caveat that hardware-updated words can have changed.
- No snapshot exists at the commit itself.
- **Capture D** (`ENTRY='@awdl0 disable' CAPS=3,d commit_state.py`, `commit-last-writes-3d.tsv`,
  `-4d.tsv`; four untrapped pages left out everywhere). D's list is the list at the real
  power-down. Words written from the E1 marker to T: 595 in A or B, 634 in A or D, 632 in B or
  D; 593 are written in each pair; the last value written is equal in 527 (A, B), 505 (A, D),
  504 (B, D). All the values of the list above are the same in D, except that D cannot show
  `0x210e20660` and `0x211e20660` (`reqcheck.py`: 71 checks on each capture, no failure). D adds, as last
  written values: `0x23b104100`-`0x23b10416c` = `0xffffffff` (28 words), `0x23b105024`+`0x80`k
  = `0x80000001` (11 words), `0x23d0d9338` = 1, `0x23d0d9378` = 1, `0x23d2c4000` = 1 (written
  three times), and in the power chip: `0xd008` = `9f 9a 08 00`, `0xd00e` = `00`, `0xd000` =
  `41`, `0x9f01` = `50`.
- **Snapshots, three captures** (`three.py`; files `snap-pre-full-3d.tsv`, `snap-wake-3d.tsv`):
  "pre-full": 792 words in all three, **775 equal in all three**; besides
  the 15 above, D differs in `0x23b040098` and `0x23b710018`. Still no snapshot at the commit.
- **Captures E and F** (`ENTRY='@FB0 Api.*ON to OFF' CAPS=d,e commit_state.py` and `d,f`,
  `e,f`): from the display request to T, 631 words are written in each of D, E, F (F one more);
  the last value written is equal in 541 (D, E), 555 (D, F), 543 (E, F) of them. The words that
  differ are of the same kinds as between A and B (SMC shared memory, storage and mailbox
  counters, PWM, the alarm bytes). Every value of the list above holds in E and F
  (`reqcheck.py`: 71 checks on each of five captures, no failure). "pre-full" snapshot: 792
  words, **772 equal in all five**, 777 equal among D, E, F.
- **Capture G**: from the display request to T, 619 words are written in both D and G; the
  last value is equal in 537. All 71 values of `reqcheck.py` hold in G. "pre-full" snapshot:
  **768 of 792 words equal in all six captures**.

### 4.3 Every power-domain write seen, with the reads around it (D-I; added this round, gaps Q1, Q6, Q13, Q15)

`ps_off.py`, `ps-forms.tsv` (one line per run: capture, side, time, domain, the sequence),
`ps-forms.txt` (the forms with the captures they occur in). A **run** is the consecutive
accesses to one control word with no 5 ms pause; "R x" a read returning x, "W x" a write of x.
The guarded words' boot accesses are from `run-det10.out` (4.2a). 94 of the 137 words are
written in the detached logs; the 43 never written in D-I (and, for the nine of R56, not in A
or B either) are the cores' and clusters'
words, AES, DPA0, DPA1, JPG, MSR, MSR_ASE_CORE, ISP_SYS, VENC_SYS, AVD_SYS, the VENC_* words,
ANE_SYS_CPU, DISPDFR_FE, DISPDFR_BE, MIPI_DSI, MSG, ATC1_COMMON and every ATC0_*/ATC1_* word
(ATC0_COMMON, ATC0_USB, ATC0_USB_AON only at boot, 4.2a).

**Turn-off (request 0)**, three forms. In every instance the value written is a function of the
value read just before, as stated; no instance departs from it except where named.
1. **One write**, when the word reads bit 28 clear: write = the read value with bits 0-9
   replaced by `0x3f0`. Seen: DISP0_FE R `0x20ff` W `0x23f0` R `0x2100` (E1, D-I) and R
   `0x23ff` W `0x23f0` R `0x2100` / `0x2300` (E2); DISPEXT_FE R `0x23ff` W `0x23f0` R `0x2300`
   (E2); I2C0, I2C3, SPI2, SPI3 R `0x2ff` W `0x3f0` R `0x200` (every bus cycle); FPWM1 the same
   (F, E1); at the wake: DISP0_FE, DISPEXT_FE R `0x3ff` W `0x3f0` R `0x100` / `0x300`; MCA0-5,
   SIO_ADMA R `0x3ff` or `0x2ff` W `0x3f0` R `0x200`; DISP0_CPU0, DISPEXT_CPU0, RMX, MMX R
   `0x0f0003ff` W `0x0f0003f0` R `0x0f000300`; GFX, ANE_SYS R `0x0f0023ff` W `0x0f0023f0` R
   `0x0f002300`; PMGR_SOC_OCLA R `0xff` W `0x3f0` R `0x200` (a word on after the reset, turned
   off); at boot ATC0_COMMON R `0x22ff` W `0x23f0`, ATC0_USB and ATC0_USB_AON R `0x2ff` W `0x3f0`.
2. **Two writes**, when the word reads bit 28 set: first write = the read value with bits 28, 9
   and 8 cleared (low byte as read, so the request stays `0xf`); the word then reads with bits
   24-27 = `0xf`, state `0xf`, bit 28 clear; second write = that read with bits 0-9 replaced
   by `0x3f0`. Seen: DISP0_CPU0 R `0x1f0402ff` (E: `0x1f0403ff`) W `0x0f0400ff` R
   `0x0f0402ff` / `0x0f0403ff` W `0x0f0403f0` R `0x0f040300` (E1, E2, wake; D-I);
   DISPEXT_CPU0 the same (E2, wake); GFX R `0x1f0023ff` W `0x0f0020ff` R `0x0f0023ff` W
   `0x0f0023f0` R `0x0f002300`; APCIE_ST R `0x1f0003ff` W `0x0f0000ff` R `0x0f0003ff` W
   `0x0f0003f0` R `0x0f000300` (D, G, I) / `0x0f000200` (E, F, H). **RMX departs in the second
   write**: R `0x1000030f` W `0xf` (the rule) R `0x0f0003ff` **W `0x300`** R `0x0f000300` (E1,
   E2, wake; D-I, 12 + 6 instances).
   *(Added round 7, gap W5a; `r7_rmx.py`.)* RMX's read before that second write is
   `0x0f0003ff` in all 18 instances, so "the read value with bits 0-9 replaced by `0x3f0`"
   (`0x0f0003f0`), "the same with bits 24-27 cleared too" (`0x3f0`) and the constant `0x300`
   differ, and only `0x300` was written: bits 4-7 are written 0 as well, unlike every other
   turn-off. The **same read value `0x0f0003ff`** is followed by **W `0x0f0003f0`** (form 1) in
   RMX's first write at the wake (W+0.0138, D-I, 6 instances, before its turn-on), by the same
   instruction as every other RMX write (one pc for all 102 RMX writes in D-I). So RMX's second
   write is not a function of the value read alone; what the captures give is: after form 2's
   first write, `0x300`; at the wake's first write, form 1. RMX reads `0x0f000300` after either.
   With another read value before the second write (Linux's RMX reads `0x1f0000ff`, section 12)
   the value macOS would write is not observed.
3. **Request 4 to 0** (only at the wake, from the values the chip comes back with): write = the
   read value with bits 0-9 replaced by `0x340`. PMS_FPWM0-4, AFT0, DEVC0_IVDMC R `0x244` W
   `0x340` R `0x200`; I2C0-4, SPI0-4, FPWM0, FPWM2 (and FPWM1 in F) R `0x344` W `0x340` R
   `0x200`; SOC_SPMI0-2 R `0x0f000244` W `0x0f000340` R `0x0f000200`; ISPSENS0-3 R `0x4000244`
   W `0x4000340` R `0x4000200`. D-I, every wake. This is the only place request 4 is seen
   written over or read before a write; no capture shows request 4 before the sleep.
   *(Round 7, gap W5c, W5d.)* Under Linux twelve words read request 4 at the driver's entry
   (SOC_SPMI0-2 `0x0f000244`, PMS_FPWM0-4, AFT0, DEVC0_IVDMC, FPWM0, FPWM2 `0x244`; section 12,
   L15): ten of them are among the words this form was seen on at the wake, from the same
   values (`0x244`, `0x0f000244`); FPWM0 and FPWM2 were seen at the wake from `0x344`. A turn-off
   of a request-4 word **before** a sleep, and a word with request 4 and bit 28 set, are in no
   capture. A word that does not read bits 24-27 `0xf` after form 2's first write is in no
   capture either (above, 66 of 66).
**After a turn-off write** macOS reads the word one to three times within about 40
microseconds. In every instance (all three forms, all captures) the first read already reports
state 0 (bits 4-7 = 0). macOS never met a word that still reported another state after an off
request, so whether it waits, on which bits, and for how long is **not observed**. Bits 8 and 9
after the write: `0x200` (bus, PWM, request-4 words), `0x100` then `0x300` (DISP0_FE at the
wake), `0x2100` then `0x2300` (DISP0_FE before the sleep), `0x300` (CPU0 words, RMX, GFX, MMX).
**Order**: child before parent (DISP0_CPU0, DISP0_FE, RMX; DISPEXT_CPU0, DISPEXT_FE; 1.9).
**Before** each display, graphics and storage domain goes off, its coprocessor was stopped
(E2a); for the bus domains, the turn-off ends each transfer cycle.

**Turn-on**, forms (for Q6's decision; values as read):
4. **From request 0**: first write = the read value with bits 0-11 cleared, except that DISP0_CPU0
   and DISPEXT_CPU0 are written `0x0f040000` also when they read `0x0f000300` (wake); second
   write = first + `0xf`; then the word is read until bits 4-7 read `0xf` (reads seen while
   waiting: `0x30f`, `0x230f`, `0xb4f`, `0x2b4f`); third write = second + bit 28. E.g. bus
   cycles R `0x200` W `0` R `0x200` W `0xf` R `0x2ff` W `0x1000000f`; DISP0_FE R `0x2300` W
   `0x2000` R `0x2300` W `0x200f` R `0x230f` R `0x23ff` W `0x1000200f`; RMX R `0x0f000300` W
   `0x0f000000` R `0x0f000300` W `0x0f00000f` R `0x0f0003ff` W `0x1f00000f`; ANS2, APCIE_GP,
   GFX R `0x0f002300` W `0x0f002000` ... W `0x1f00200f`.
5. **From request 4** (wake): R `0x344` W `0x44` R `0x344` W `0x4f` R `0x3ff` W `0x1000004f`
   (UART1-8, UART_N, SPI_P, FPWM1 in D, E, G, H, I); R `0x244` W `0x44` R `0x244` W `0x4f` R
   `0x2ff` W `0x1000004f` (APCIE, DWI); PCIE_REF R `0x0f000244` W `0x0f000044` R `0x0f000244`
   W `0x0f00004f` R `0x0f00024f` R `0x0f0002ff` W `0x1f00004f`.
6. **Words already on at the wake**: AIC, GPIO, SOC_DPE, DEBUG R `0x2ff` W `0xff` R `0x2ff` W
   `0xff` R `0x2ff` W `0x100000ff`; NUB_GPIO the same from `0xff`; PMP, PMS, PMS_BUSIF, SIO,
   SIO_BUSIF, SIO_CPU, IMX R `0x0f0003ff` (PMS `0x0f0002ff`, PMS_BUSIF `0x0f0000ff`) W
   `0x0f0000ff` twice, W `0x1f0000ff`; MCC, SMX, SBR, NUB_AON, NUB_FABRIC, the DCS words,
   NUB_SRAM, DEBUG_USB, DEBUG_AUTH, SEP, NUB_SPMI0/1: one write = the read value with bits 8 and
   9 cleared (R `0x1f0003ff` W `0x1f0000ff`; R `0x1000030f` W `0x1000000f`; R `0x1400034f` W
   `0x1400004f`; R `0x1000230f` W `0x1000200f`; R `0x1400024f` W `0x1400004f`).
**Request 4 written over request 0** (Q6a): never seen. The only writes with request 4 are the
first two of form 5, made over request 4.
**Turning a display or second-port domain on with nothing behind it started** (Q6b): the
turn-ons of RMX, DISP0_FE, DISP0_CPU0, DISPEXT_FE, DISPEXT_CPU0 in E2 are followed within a
millisecond by their coprocessors' start (E2a, restart), those of W4 by `dcp`'s and `dcpext`'s
boot; in the alarm wakes DISP0_FE is turned on and off again within 30 ms around `dcp`'s "AP
power" messages (W4). A display domain turned on and left on with its coprocessor not started
is not observed. ATC1_* is never written.

### 4.4 At and after the commit: macOS's captures set against Linux's commit (round 8)

Linux's driver now runs its entry to the commit point on bare metal, and the SoC does not power
down (section 12, L16, L17). This section goes through what the captures show of macOS's last
steps and of what follows its commit, and sets each item against what the Linux readings show.
"Linux" here means the readings of section 12 and the evidence they come from, not the driver's
code, which the spec stage does not read. Each row ends with what the comparison is:
**differs** (observed on both sides, different), **same**, or **not read** (one side has no
reading). Scripts: `r8_det11.py` (J), the tables of 4.1a/4.1b, `linux-diff-list.md`.

| # | Item | macOS (captures) | Linux (readings) | Comparison |
|---|---|---|---|---|
| 1 | The last device accesses of the last core | R38's four power-chip commands, the third `0x23d2c4000` = 1, 11 writes to SMC shared memory, console bytes, a console-port read at T (D-J, E6-4) | the driver's last access before the glue's commit mark is a 32-bit write of `0x23d2c4000` by core 0 (ds17 and ds17-1 to -3, L17); what follows it from the driver is not in the record | same as far as read |
| 2 | SPMI traffic after macOS's last command | the instrument's own commands at the commit (stage marks, the wake note, in A, G-K the alarm), **then `0x23d0d9378` = 1** (A6); macOS's own commands each end with `0x23d0d9378` written 1 (R38, R60); *(round 9)* at the commit, before the instrument's commands, `0x23d0d9378` reads 0 (K, 4.1c) | the glue writes its ten-byte record as three SPMI commands to `0x9f04`-`0x9f0d` after the commit point (evidence ds16b) and, with `wdt=N`, watchdog 1 (ds17); whether `0x23d0d9378` is written after those commands is in no Linux record | not read |
| 3 | Each core's last register writes | burst 1: `PMCR0_EL1` last `0x7003400`, `IPI_SR_EL1` = 1 (R45); burst 2: `ACC_OVRD_EL1` = `0x1800101526076207`, `CYC_OVRD_EL1` = `0x3000001`, every core, core 0 last (R43; G-K); *(round 9)* read back by each core at its final write: `ACC_OVRD_EL1` `0x1800101526076207`, `CYC_OVRD_EL1` `0x2000000` before the write, `PMCR0_EL1` `0x7003400`, `IPI_SR_EL1` 0, `IPI_CR_EL1` `0x600` (K, E7) | ds9's record says every core made its `CYC_OVRD_EL1` write (L7); the values written to these registers under Linux are in no record | not read |
| 4 | Each core's timers and pending interrupts at its final wait | written off by the instrument on every core, after macOS's last write and before the real `CYC_OVRD_EL1` write, in every power-down (A6, E7, R59) `[ARTEFACT]`. *(Round 9.)* **macOS's own values** (K, E7): the guest's virtual timer enabled and unmasked on all eight cores, already fired on three (cores 1, 2, 0), its physical timer disabled; every interrupt of the controller and both IPI kinds masked, nothing software-generated, `ISR_EL1` 0 on every core under the instrument. Left in place (`det13`, `det17`): no power-down and wake, a reset 5-6 s after the commit **[HV-CHANGED]**. *(Round 10.)* The same macOS values in L, `det19b`, `det21` (fired on three or four efficiency cores, core 0 and 1 every time; E7). Split **[HV-CHANGED]**: timers left, no virtual interrupt pending (`det19b`, `det21`): power-down and wake, 2 of 2; a virtual FIQ left pending at cores 0-3 / 0-2, timers off (`det20b`, `det22c`): a reset about 6 s after the commit, 2 of 2 | not read | **not read on the Linux side.** On the macOS side every observed power-down had no virtual interrupt pending at any core (the instrument's doing) and `ISR_EL1` 0 where read; a pending virtual FIQ was followed by no power-down four times of four; enabled timers with nothing pending were followed by a power-down twice |
| 5 | The S2R timer word `0x23d2c4000` | written 1 three times (R24, R37, R38), never read by macOS in a log; reads 1 with macOS awake before every entry (the instrument's arm-time line, eight runs, 1.7c). *(Round 9.)* **Reads 0 at the commit** (K); bit 0 stays clear for 4.9 s after the commit with a core kept up (`det16`); watchdog 2 started within about 0.3 ms of the first write (4.1c). *(Round 10.)* Reads 1 just before the first write and 0 just after it, 0 around the second and third (L, `det19b`, `det21`) | written by the driver (row 1); its value before the entry and after the write not read (it is not in the commit list) | not read |
| 6 | The commit list's words at the commit | 4.1a, 4.1b, R51, R52: G-J equal in 767 of 792; 21-35 words change between awake and the commit with no write by any core, among them `0x23b04003c`, `040` (bit 8 cleared) | at Linux's commit 63 (ds16) and 64 (ds16b) words of the list hold a value that is neither the driver's last write nor the reading before the entry; identified: `0x23b04003c`, `0x23b040040`, `0x23b040048`, `0x23b04004c`, and `0x23b040044` or index 41 (L16); their values not recorded | in both systems words of the list change by themselves before the commit, the same clock words among them; whether to the same values: not read |
| 7 | Clock words | at the commit: appendix B; R18's muxes hold `0x85100000` / `0x87100000`; always-on clock words `0x23d240040` -> `0x01101100`, `0x23d240314` -> `0x01000000` between awake and the commit with no write (R52); *(round 9)* `0x23d240024`, `03c`, `048` read `0x81100100`, `0x81100100`, `0x82100100` both awake and at K's commit (4.1c) | before the entry: 50 SoC clock words, the NCO, five always-on clock words differ from macOS's commit (L2); `0x23d240040` and `0x23d240314` hold macOS's **awake** values; `0x23d24003c` `0x01101100` (macOS `0x81100100`), `0x23d240048` `0x00101100` (`0x82100100`), `0x23d240024` `0x81100000` (`0x81100100`); at Linux's commit: row 6 only | differs before the entry; at the commit not read |
| 8 | Power-gate words and the always-on block | `0x23b71c090` `0x8004030c`, `0x23b71c0a8` `0xc0040301` (G-J); `0x23d2c0000`-`03c` appendix B values; `0x23b71c0d8`, `0f0`, `108`, `120` `[VARIES]` | before the entry (ds13, ds15): every one of these words equals its value at H's commit | same |
| 9 | AP wake-source masks `0x23d004008`-`0x23d004018` | never written by macOS in any logged window (D-K; boot is not logged), not written by the instrument (A6); *(round 9)* at K's commit `0xf3ffafff`, `0xffb97eff`, `0xfffdeffe`, `0xffffffff`, `0x03ffff87`, equal to their awake values (4.1c) | not read | not read |
| 10 | Power domains at the commit | 4.2a, R54 | before the entry: 4.2a's last column, L15; at the commit not read (L11) | not read |
| 11 | Watchdog 1 armed at the commit | J: control 4, bite 150 s, armed by the instrument after every other write; the chip powered down and woke at the alarm after 89.5 s (1.7c, R61) | ds17, ds17-1 to -3: armed by the glue at the commit point with the same four writes, `wdt=120`; reset about 120 s later (L17) | the armed watchdog is not the difference (J) |
| 12 | What follows the commit | a sleep and a wake every time (A-K); at the instrument's wake entry `0x23d2b8028` = `0x8000000`, `0x23d2b8040` = `0x22`, watchdog 2 count about 0.325 s with bite 5 s and control 0 (D-J, section 5), watchdogs 0 and 1 counts about 13.9 ms (J); power chip `0x0201` = `00` after the next boot (H, I, J, K). *(Round 9.)* In the four runs in which the instrument left the cores' timer state in place or kept a core running (`det13`, `det14`, `det16`, `det17`, **[HV-CHANGED]**): **no wake and a reset 5-7 s after the commit**, `0x0201` `00`, `0x9f03` `0x50`, `0xd000` `0x41` after it (1.7d). *(Round 10.)* L, `det19b`, `det21`: sleep and wake as before; `det20b`, `det22c` (a virtual FIQ left pending, **[HV-CHANGED]**): the same reset about 6 s after the commit and the same power-chip bytes (1.7e) | no wake by the alarm, a key, a power-button tap or the lid; without the watchdog dark for 10 to 85 min until the power button is held (ds16, ds16b, ds16c); with it a reset about 120 s after the commit; `0x0201` `04` before and after ds17 (L16, L17); *(round 9)* `0x9f03` `0x50` after ds16, ds16c and ds17-1 to -3 (as after macOS's four failed runs), `0xd000` `0x01` (the alarm's time had passed) | **differs**, also from macOS's failed runs: no Linux run reset 5-7 s after its commit |
| 13 | *(Round 9.)* The always-on side's first step, before the cores go down | **watchdog 2 armed (bite 5 s, control 4) within about 0.3 ms of R24's first write of `0x23d2c4000`**, about 15 ms before T, by no logged access and not by the instrument; `0x23d2b8028` bit 24 at the commit (awake 0) (K, 4.1c). *(Round 10.)* **Already armed, and bit 24 already set, before that first write reaches the hardware**; the count starts 1.3-7.1 microseconds (±10) after the record of macOS's write `0x23b718004` = 0 (E5-8i), 31-45 microseconds before the first `0x23d2c4000` write (L, `det19b`, `det21`; 4.1c) | earlier driver (L18, run 26): with a core kept up after its end of entry, watchdog 2 read armed for 5 s from the first sample; round-7 driver (ds16 to ds17-3): not read; no reset about 5 s after the commit in any of its runs | not read for the round-7 driver |
| 14 | *(Round 9.)* One core still running after the commit | `det16` **[HV-CHANGED]**: for 4.9 s `0x23d2b8028` bit 24, `0x23d2b8040` `0x20`, `0x23d2c4000` bit 0 clear, `0x23b71c090` bit 30 clear, `0x23b71c360` bit 30 set, `0x0201` `00`, watchdog 2 counting with control bit 2; nothing changed; a reset about 6 s after the commit. `det14` (the core went down after 3 s): no wake, a reset about 7 s after (1.7d) | earlier driver (L18, run 26): the evidence's "engine progress" byte `0x01` (which of `0x23d2b8028`, `0x23d2b8040` it is, the evidence does not say), watchdog 2 control 4 bite 5 s, no change in 2.5 s, `0x0201` stayed `04`; the next start came "5 s" after the end of the entry by the chip's clock (evidence `2026-11-16-run26-watch`) | **same, as far as read**: with one core up after the commit both systems show watchdog 2 armed for 5 s, no change in the sampled words, and a reset about 5-6 s after; whether the progress values are the same is not established |
| 15 | *(Round 10.)* The power-gate header word `0x23b71c000` | `0x80000000` awake and at the commit (L, `det19b`, `det21`); reads 0 at every wake and is written `0x80000000` by macOS there, with `0x23b71c040` (thirteen captures, W1-2a); never written in a logged entry (4.1d). *(Round 11.)* Cleared by the instrument before the cores' final writes, read 0 at the commit: power-down and alarm wake, `det23`, `det24` **[HV-CHANGED]** (1.7f) | **0** with Linux awake on the stock kernel (snapshot 12, 2026-11-16), the other nine header words `0x80000000`; *(round 11)* 0 again on 2026-11-18 03:54, `0x23b71c040` `0x80000000` (1.7f); before the driver's entry and at its commit not read | **differs** awake; at the commit not read; *(round 11)* under macOS the word read 0 at two commits that powered down, so the difference, if it reaches Linux's commit, is not one that stopped macOS's power-down when made at the end of the entry |
| 16 | *(Round 10.)* The CPU start/stop block `0x23b754000`.. | awake all 0; at the commit +`0x0` = +`0x4` = `0xfe` (cores 1-7), the rest 0 (L, `det19b`, `det21`; 4.1d) | awake all 0 (snapshot 16); the secondaries' stop bits at the driver's entry and the block at its commit not read | not read at the commit |

**What row 12 does and does not establish.** By the lab's decode of the always-on sleep program
(evidence `2026-11-16-run36-38-restart`, `2026-11-16-hv-macos135-wake`, `2026-11-16-run26-watch`;
the lab's documentation of the always-on block's program memory, not a capture) the program's
sequence 0 arms watchdog 2 for 5 s when it starts and polls power-gate words (among them
`0x23b71c090` and `0x23b71c360`, bit 30), sequence 1 writes power-chip `0x0201` = `01`, and the
wake sequence 10 arms watchdog 2 for 5 s, writes `0x0201` = `00` and reaches progress `0x22`.
macOS's wakes fit it (progress `0x22`, a 5 s bite in watchdog 2 read 0.325 s after it was armed,
`0x0201` = `00` afterwards). After Linux's commit **no reading shows any step of that program**:
no reset about 5 s after the commit in ds16, ds16b, ds16c (with nothing else armed), and in ds17
`0x0201` was written neither `01` nor `00` (it read `04` before and after). Under an earlier Linux
driver on the same firmware the same readings did move: `0x0201` read `01` after the run and the
chip reset about 5 s after the end of the entry (L18); in one of those runs (run 26) a core kept
running after the entry read the program's first step already taken (progress `0x01`, watchdog 2
armed for 5 s), so on this firmware that step does not wait for every core to go down. Not
established: that the program did not start at all after the round-7 driver's commit (its
progress word there was not read); one run (ds17) is the only one whose
`0x0201` reading separates "neither written" from "`01` then `00`" (ds17-1 to -3 started from
`00`). The watchdog reset of L17 alone does not show that the SoC stayed powered: J shows that
watchdog 1's bite and control survive a sleep and its count is not carried, so a power-down
followed at once by a wake that stalls is also consistent with a reset about 120 s after the
commit; ds17's `0x0201` (no wake sequence wrote `00`) is the reading against that.

*(Round 9.)* **What rows 13 and 14 add.** Under macOS the first step the lab's decode gives the
always-on program (watchdog 2 armed for 5 s) is taken within about 0.3 ms of macOS's first write
of `0x23d2c4000` = 1, some 15 ms before the cores go down, and not after the last core (K). When
the instrument then kept a core running, or left the cores' timer state in place, macOS's sleep
did not complete and the machine reset 5-7 s after the commit, four runs out of four
(**[HV-CHANGED]**): the reading the earlier Linux driver's runs gave (L18), and the one the
reference records for a stalled sleep on other chips (4.4a). The round-7 Linux driver's runs
never gave it: dark for minutes, or reset at watchdog 1's 120 s. The captures do not say why.
Read against row 13, the alternatives the readings leave are: under Linux watchdog 2 was not
armed at the driver's `0x23d2c4000` write (the program did not start); or it was armed and later
disarmed or moved; or the program went past its first step to a power-down that did not wake.
Watchdog 2 and `0x23d2b8028` read after the driver's first `0x23d2c4000` write separate the
first from the other two (open question 56). The power chip's bytes do not: `0x9f03` reads
`0x50` after every run of either system that reached a commit and did not wake (1.7d).

**What the captures cannot show.** No capture has a trace between the last core's final write
and the power-down: under macOS the instrument acts in between (A6) and the log ends there. So the
captures show what the application processors had done and left when the last core went down,
and not what the always-on side then checks or waits for. Of the items above, the ones that
differ or are not read on the Linux side are rows 2-7, 9, 10, 12, 13, 15 and 16; rows 1, 8 and 11
are the same or ruled out, and row 14 is the same as far as read. The readings that would show
what happens after the last core goes down are open questions 53-55 and 66-67 (macOS, under the
hypervisor) and 56-58, 62, 64 and 65 (Linux); 59-61 were answered in round 10.

*(Round 10.)* **What rows 4, 13, 15 and 16 add.** Row 4: under the instrument the item whose
presence went with every failure to power down at a core's final wait is a pending (virtual)
interrupt, not an enabled timer. Row 13: the always-on side's first observed step follows macOS's
write `0x23b718004` = 0 by microseconds and comes before the first write of `0x23d2c4000`; for a
Linux reading of open question 56 the place to read watchdog 2 and `0x23d2b8028` is right after
the driver's write of `0x23b718004` = 0. Row 15 is a word that macOS's entry never writes, that
holds one value with macOS awake and at its commit, that Linux awake holds differently, and that
the reference ties to the cores' power-down (4.4a C3); whether Linux's entry changes it is not
read.

*(Round 11.)* **What `det23` and `det24` add to rows 4, 13, 15 and 16.** Row 15: the word cleared
after macOS's entry and before the cores' final writes did not stop the power-down (2 of 2,
[HV-CHANGED]); it stays a difference between the systems awake, and what a word clear through
the whole entry does is not read on either. Row 4: two more power-downs with nothing pending at
the cores (the instrument's clearing), one of them with an IPI-borne virtual FIQ cleared on core
3 (E7). Rows 13 and 16: the same values in five captures.

*(Round 12.)* **The Linux side of rows 4, 6 and 12 with the round-8 driver** (L21-L24). Row 4: at
each core's final write nothing is pending at any of the eight cores (`ISR_EL1` F, I, A and
`IPI_SR_EL1` clear, L22), the state every macOS power-down had; the timers of cores 0, 1 and 7
are not on and unmasked, but `CNTP_CTL_EL02` is enabled (masked, condition met) on all three and
core 0's EL2 physical timer likewise (L23), where macOS's guest physical timer is disabled and
the instrument's EL2 timers stopped at every power-down: **differs**, in enables only (8.2
C13). Row 12: ds19 has L17's outcome (no wake, the watchdog-1 reset, `0x0201` `00`, `0x9f03`
`50`). Row 6: the commit walk reads the 118 words of L1 at Linux's commit; at the time of writing
12, among them `DCS0-3+0x7b0` = 3 (macOS 0): that difference reaches the commit (L24). The
observed differences a driver could act on are written out as candidates in 8.2.

### 4.4a The conditions the reference names for the power-down, against the M1 readings (round 9)

*Reference, not an observation.* The reference (`docs/reference/asahi-aurora-sleep-deep-dive.md`,
section 2) describes, for Aurora Silicon's sleep driver on other Apple chips (T8140, T8132,
T6040, T6050; none is t8103), a hardware "sleep engine" that starts after the last core stops,
waits without a timeout on a list of conditions, and powers the chip down; a condition left
unmet ends, on those chips, in a watchdog reset 5 s (5.5 s, a configured 13 s) after the commit.
No source in the reference has t8103 data for that engine, and no source observed the time
between the last core's final write and the power-down on any chip. In the table, the first
column is the reference's (with its chip and section); the other columns are this document's
observations and section 12's Linux readings only; nothing in the first column is a requirement.

"Met" means the M1 reading shows the state the reference's condition names; "not observed" that
no M1 reading covers it. The last column names the reading that would settle the open side.

| # | Condition (reference; chip; section) | macOS at its commit (M1 observation) | Linux at its commit (readings) | Settled by |
|---|---|---|---|---|
| C1 | Every core reaches its final wait and powers down after the commit; one core left awake holds the engine until the watchdog (T8140, measured; 2.2) | every core makes its final write within 33 microseconds (0.3 ms in K), core 0 last, after macOS's last device access (R43, R44; A-K); **with core 0 kept running after the commit the chip did not power down and reset 5-7 s later** (`det14`, `det16`, **[HV-CHANGED]**, 1.7d) | ds9: every core made its `CYC_OVRD_EL1` write (L7); the values and order against the driver's `0x23d2c4000` writes not read | Linux: each core's final values and time against the driver's last device access (open question 57) |
| C2 | Secondaries take their deep wait only after the commit; earlier stops it (T8140, measured; 2.2) | the stop bits (R11, T-0.091) do not take a core down; each core makes its final write at the commit, after the three writes of `0x23d2c4000` (E7) | not read (the order of the cores' final writes against the driver's writes) | Linux: as C1 |
| C3 | A per-cluster (or per-core) power-manager word lets the cores, the boot core included, power down in their wait; the loader leaves the boot core's clear (T8140, T8132, T6050, measured; 2.2) | **not observed**: no such word identified on t8103. What the captures have: `CYC_OVRD_EL1` = `0x3000001` on every core (bits 24-25 = 3; the Asahi page names them "OK To Power Down", 3 "force down": documentation, reference 3.7); the core and cluster domain words at the commit (R53: cores 1-7 `0x100`, core 0 `0x1f0`, ECPM `0x21f0`, PCPM `0x2100`) | the cores' domain words before the entry (L12: one core `0x1f0`, the rest `0x100`); `CYC_OVRD_EL1` value not read | macOS: the power manager's CPU block (`0x23b754000`.., held by the instrument, A4) and the power-gate records of `0x23b71c000`.. read awake and at the commit; Linux: the same words before the entry and at the commit |
| C3 *(round 10)* | as above | **candidate words observed** (4.1d): the power-gate header `0x23b71c000` and `0x23b71c040` (the reference's T8140 offsets +`0x0`, +`0x40` of its power-gate block; correspondence by offset only) read `0x80000000` (bit 31 set) awake and at the commit (L, `det19b`, `det21`); at every wake `0x23b71c000` reads 0 and macOS writes both `0x80000000` (thirteen captures); never written in an entry. The CPU block at the commit: +`0x0` = +`0x4` = `0xfe` | **[LINUX]** awake: `0x23b71c000` = **0**, `0x23b71c040` = `0x80000000` (snapshot 12); CPU block all 0 (snapshot 16); before the entry and at the commit not read | Linux: `0x23b71c000`, `0x23b71c040` and the CPU block before the driver's entry and at its commit (open question 64). macOS: whether `0x23b71c000` clear at the commit stops the power-down (open question 67) |
| C3 *(round 11)* | as above | **`0x23b71c000` clear at the commit did not stop the power-down** **[HV-CHANGED]**: cleared by the instrument after macOS's last write to the page and before the cores' final writes (before all of them in `det24`, 0.28 ms before T), read 0 at the commit; power-down and alarm wake 2 of 2 (`det23`, `det24`, 1.7f). Not run: `0x23b71c040` clear; the word clear through the whole entry | **[LINUX]** awake `0x23b71c000` 0, `0x23b71c040` `0x80000000` (2026-11-18 03:54, a second boot) | Linux: as above (open question 64). macOS: the word clear from before the entry, and `0x23b71c040` clear (open question 67) |
| C4 | No interrupt pending at a core's final wait: every interrupt-controller line masked, the cores' timers masked or off (T8140, implemented; 2.2) | the controller: every line and both IPI kinds masked, nothing software-generated (K, E7, by the Asahi page's names); the timers: **macOS leaves its virtual timer enabled and unmasked, fired on three cores** (K); every observed power-down had them written off by the instrument (R59); kept, twice no power-down (**[HV-CHANGED]**) | not read (L11) | Linux: open question 57; macOS: which kept item matters (open question 59) |
| C4 *(round 10)* | as above | **the pending interrupt, not the timer** **[HV-CHANGED]**: timers left enabled and unmasked with no virtual interrupt pending, power-down 2 of 2 (`det19b`, `det21`); a virtual FIQ left pending, timers off, no power-down 2 of 2 (`det20b`, `det22c`); every power-down (thirteen) had none pending and `ISR_EL1` 0 where read (E7). The controller part as above, the same in L, `det19b`, `det21` | not read | Linux: each core's `ISR_EL1` and timer controls at its final instruction (open questions 57, 65); macOS: a fired timer whose interrupt reaches the core (open question 66) |
| C5 | PMP and SIO stopped (run bit +`0x44` bit 4 clear) or their domains off; a commit with them running reset the chip 5.5 s later (T8140, measured; 2.2) | **met**: +`0x44` written 0 after R4's messages (R5); PMP `0x1f0f03ff`, SIO_CPU `0x0f0002ff` at the commit (R46) | before the entry SIO's domains off, PMP's on (`0x1f0000ff`), `pmp`'s words not read (L15); at the commit not read | Linux: `pmp`'s and `sio`'s +`0x44`, +`0x48` and domain words at the commit |
| C6 | The secure enclave gated itself after a control message (T8140, measured; 2.2) | SEP word `0x1000230f` at the commit (R46: state bits 4-7 read 0, bit 28 set); macOS sends `sep` no power message in R4 and never touches its +`0x44`/+`0x48` (section 0) | not read | Linux: the SEP domain word before the entry and at the commit |
| C7 | Display coprocessors stopped and their domains lowered; "the sleep engine waits on DISP_CPU with no timeout" (T8140, measured/comment; 2.2) | **met**: `dcp`, `dcpext` stopped (R5a) and the display domains off at the commit (R1, R7, R46) | `dcp`, `dcpext` running with their domains on before the entry (L15); at the commit not read | Linux: their +`0x44`, +`0x48` and the display domain words at the commit |
| C8 | Storage (ANS) stopped with its PCIe block and domains lowered (T8140, T6040, measured; 2.2) | `ans` stopped (R5a); APCIE_ST off (R7); ANS2 `0x1f0023ff` at the commit (R46; it changes in E1 with no write, R52) | ANS2 `0x0f002300`, APCIE `0xff`, APCIE_ST `0x0f000200` before the entry (L15); at the commit not read | Linux: those words at the commit |
| C9 | Graphics stopped (a first-pass stop on T8140; 2.2) | `gfx-asc` stopped (R5a), GFX off at the commit (R46) | GFX `0x0f002b00` before the entry (bit 11 set, L15) | Linux: GFX at the commit |
| C10 | DRAM controllers at their sleep state, the PMC voters at 0, the SoC performance word at its sleep state (T8140, T8132, T6040; implemented/measured; 2.2) | **not observed** as such: no voter or performance word identified on t8103. The 80 memory-controller and 448 DRAM-controller words of the list hold their awake values at the commit (R47, K as G-J); the DCS domain words vary (R46); macOS's memory-controller shutdown writes R16-R17 | before the entry the same words but `DCSn+0x7b0` = 3 (macOS 0) and the emulated `MCC+0x680`/`684` (L2); at the commit not read | macOS: candidate words would first have to be named (no t8103 source does); Linux: the 528 words at the commit (open question 58) |
| C11 | Memory-controller error enables cleared, or a pending error turns the sleep round within 20 ms (T8140, measured; 2.2) | not observed (no t8103 word named) | not read | on the reference's account a bounce, not a stall; no reading proposed |
| C12 | No domain left on that macOS has off, none latched busy, the right ones under automatic power (T8140, T6040, T6050, measured; 2.2) | requested states at the commit: on 51, 0 86 (R54); bit 11 never read set at rest (section 0) | before the entry: the nine never-written domains and the first port's seven on, FPWM1 `0x0a00` and GFX `0x0f002b00` with bit 11 at rest (L15); at the commit not read (L11) | Linux: the 137 domain words at the commit |
| C13 | USB/ATC/AUSS domains: a port domain on at the commit (T6050: AUSS) resets 5 s after; ATC commons must be on (T6040) (measured; 2.2) | the first port's words off by the instrument's acts (A2, A3; D4); ATC1 words 0 at the commit (R54, R56) | ATC0 and ATC1 words on before the entry (L15) | Linux: as C12 |
| C14 | No wake source both unmasked and pending (a bounce at once, not a stall; T8140, T8132; 2.2) | masks hold their awake values at the commit (K, 4.1c); wake status at every wake `0x400000` in +`0x20` (section 5) | not read | Linux: the five mask words before the entry and at the commit (open question 58) |
| C15 | No SPMI reply status left latched; a latched one wakes the chip after the commit (T6050, implemented/measured; 2.2) | **met**: `0x23d0d9378` reads 0 at the commit (K); every command is acknowledged (R60) | not read after the glue's own commands (L11) | Linux: `0x23d0d9378` after the glue's last SPMI command (open question 57) |
| C16 | The system management controller told "slpw", "slpa", then AP idle last, with no queued event (T8140, measured; 3.5) | **met** for the messages: R3, in that order; the outbox state at the commit not observed | not read | Linux: the `smc` messages of the entry and its outbox state at the commit |
| C17 | The watchdog a stall ends in: watchdog 2 armed for about 5 s around the commit (Aurora writes it itself at T8140's commit; AU's notes say macOS arms a ~5 s watchdog 2 in the entry; 2.1, 3.10) | **armed for 5 s, control 4, within about 0.3 ms of R24, by no logged access** (K, 4.1c) | not read for the round-7 driver; armed in the earlier driver's runs (L18) | Linux: open question 56 |
| C17 *(round 10)* | as above | **armed before macOS's first write of `0x23d2c4000` reaches the hardware**, its count starting 1.3-7.1 microseconds after the record of macOS's write `0x23b718004` = 0; `0x23d2b8028` bit 24 already set then (L, `det19b`, `det21`; 4.1c) | as above | Linux: watchdog 2 and `0x23d2b8028` right after the driver's `0x23b718004` = 0 (open question 56) |

**What the table says, kept to the observations.** Of the conditions the M1 readings cover,
macOS meets each at its commit (C1, C2, C4's controller part, C5-C9, C12, C14, C15, C16's
messages, C17; C13 only through the instrument's acts), with two
exceptions: the cores' timers (C4), which macOS leaves running and which the instrument turned
off in every power-down, and the always-on words, of which nothing after the last core is
observed. The two runs that left the timer state in place and the two that kept a core running
are the only M1 observations in which one such condition was not met, and each ended as the
reference describes a stall ending (a reset some 5 s after the commit). On the Linux side every
condition is **not read at the commit**: the readings stop before the driver's entry (L1, L15)
or at its record (L16, L17). The conditions with no M1 word at all (C3, C10, C11) would first
need the word named.

*(Round 10.)* Three rows change. **C4**: of the two parts the instrument used to write off, the
one that went with every failure is the pending interrupt at the core, not the enabled timer;
macOS's own timer state is no longer an exception to the condition as the observations now
state it (nothing pending at the core), except that what macOS's fired timers present to a core
without the instrument is not observed. **C3**: candidate words are now read on the M1: the
power-gate header words `0x23b71c000` and `0x23b71c040` hold bit 31 at macOS's commit, and with
Linux awake `0x23b71c000` does not. Unlike the Linux differences of C5, C7-C9 (states macOS's
own entry changes before its commit), macOS's entry never writes this word: it holds bit 31
from macOS's wake (or boot) on. The reference's account of a clear word on T8140 is the 5 s
reset; on the M1 nothing yet shows the word matters. **C17**: the
first step is earlier than R24's write, at R22's `0x23b718004` = 0. The other rows stand.

*(Round 11.)* **C3** changes again: the candidate word `0x23b71c000` was cleared before the
cores' final writes and the M1 still powered down and woke (2 of 2, [HV-CHANGED]); the
reference's T8140 outcome for a clear word (a 5 s reset) did not occur. On the M1 the word's
bit 31 at the commit is therefore not shown to matter; only the word clear through the whole
entry, and `0x23b71c040`, remain untried. C4 and C17: two more captures with the same values.

*(Round 12.)* **C4** is now read on the Linux side (L22, L23): nothing pending at any core's final
write, so C4's condition as the M1 observations state it is met by Linux; what still differs is
that some timers are enabled (masked) under Linux. **C3**: macOS's kernel sets `0x23b71c000` at
boot as well as at every wake (A's and B's page-touch map reads it 0 at boot; 8.2 C6); under
Linux nothing sets it. **C6**: SEP is power-gated by its automatic power at every macOS reading,
awake included, and on under Linux (8.2 C1). **C10**: three words whose value pattern matches the
reference's "SoC perf word" and DCS state (`0x23b058000`, `0x23b05c000`, `0x23b060000`: `0x333`,
`0x444`, `0x222` under macOS, `0x444`, `0x666`, `0x333` under Linux) and the one DRAM-controller
word that differs (`DCSn+0x7b0`, 0 / 3, still 3 at Linux's commit) are now named as candidates
(8.2 C3, C4); the correspondence with the reference's words is by value only. **C12, C13**: the
request-4 domains, the second port's domains, MSG and the two words latched busy are candidates
C5, C9, C11. Every reference condition with an M1 word now has either a reading on both sides or
a candidate in 8.2.

## 5. Asleep

- **Duration**, from T to the wake marker: 900.18 s (A), 319.77 s (B).
- **Cause of the wake.** A: the power chip's alarm, set by the hypervisor to now + 900 s
  `[ARTEFACT A6]`; after the wake macOS reads power-chip register `0xd00c` = `01`. B: the operator
  pressed the space bar, no alarm was set by the hypervisor, `0xd00c` reads `00`.
- **Wake status words**, read by the hypervisor at its wake entry and again by macOS at W+3.5:
  `0x23d00401c` = 0, **`0x23d004020` = `0x400000`**, `0x23d004024` = 0 (and +`0x28`, +`0x2c` = 0
  as read by macOS), the same in both captures.
- macOS's own console line: A "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0x02 nub-spmi.0xC0
  rtc smc..."; B "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0xC0 smc.70070000 ... trackp..."
  (both truncated in the log). Both name the power chip's interrupt first.
- **Capture D**: asleep 119.394 s by the machine's own clock (last core down 220.913197 s,
  wake record 340.307082 s); woken by the space bar; no alarm set by the hypervisor. Wake status
  `0x23d00401c` = 0, `0x23d004020` = `0x400000`, `0x23d004024` = 0: **the same in all three
  captures**. macOS reads power-chip register `0xd00c` = `00`. Console: "system wake events:
  NUB.SPMI0Sw3IRQ nub-spmi.0xC0 smc.70070000 trackpadkeyboard".
- **macOS arms the power chip's alarm itself before every sleep seen in full** (E6 step 3, D).
  In A the hypervisor then overwrote it with now + 900 s (A6), which is what woke the machine at
  900.18 s; whether A's own alarm would have been near 948 s is not known.
- Other registers the hypervisor read at the wake in D, equal to its log lines in A and B:
  `0x23d2b8028` = `0x8000000`, `0x23d2b8040` = `0x22`, `0x23d2b0024` = `0x7270e00`,
  `0x23d2b002c` = 0, `0x23d2c001c` = `0xff0`; `0x23d2b0020` = `0x771238` (A: `0x19c8f98`,
  B: `0x19c87ee`; a running count).
- **Capture E**: asleep 415.538 s with nothing attached, woken by the space bar. **Capture F**:
  asleep 1.591 s (section 11.2). Wake status in both: `0x23d00401c` = 0, `0x23d004020` =
  `0x400000`, `0x23d004024` = 0: **the same in all five captures**, whatever the cause (alarm,
  key, 1.6 s) and with or without the cable. `0xd00c` reads `00` after the wake in E and F.
  Console in E and F, as in D: "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0xC0 smc.70070000
  trackpadkeyboard". (A and B, the captures with a host, also list `smc.71060000`,
  `smc.71010100`, `smc.71010101`; these are the notification words the `smc` coprocessor sends
  when the cable is pulled or inserted, section 10.)
- The count at `0x23d2b0020` read by the hypervisor at its wake entry is `0x771238`, `0x7707ad`,
  `0x770765` in D, E, F: about 7.80 million in each, after sleeps of 119 s, 415 s and 1.6 s.
  It does not follow the sleep length; if it counts at the timer's 24 MHz from the wake event
  (not established), 0.325 s pass between that event and the hypervisor's wake entry.
- **Capture G**: asleep 90.326 s; woken by the alarm the hypervisor set at the commit to now +
  90 s `[ARTEFACT A6]`, which replaced the alarm macOS had set 4.8 ms earlier (about 975 s
  ahead). Wake status `0x23d004020` = `0x400000` again: **the same in all six captures**.
  After the wake `0xd00c` reads `01` (as in A; `00` after the key wakes). Console: "system wake
  events: NUB.SPMI0Sw3IRQ nub-spmi.0x02 nub-spmi.0xC0 rtc", the same sources as A. The count at
  `0x23d2b0020` is `0x76e68f` (7.79 million).
- **Capture H**: asleep 90.283 s (last core down 434.399473 s, wake record 524.682696 s); woken
  by the hypervisor's alarm (commit + 90 s) `[ARTEFACT A6]`, which replaced macOS's own
  (`d8 41 09 00`, written 4.8 ms before T). Wake status `0x23d00401c` / `020` / `024` = 0 /
  `0x400000` / 0: **the same in all seven captures**. The hypervisor read at its wake entry
  `0x23d2b8028` = `0x8000000`, `0x23d2b8040` = `0x22`, `0x23d2c001c` = `0xff0`, watchdog 2's
  count `0x23d2b0020` = `0x76e28b`, alarm `0x23d2b0024` = `0x7270e00`, control 0 (G: count
  `0x76e68f`). After the wake `0xd00c` reads `01`.
- **Capture I**: asleep 90.184 s (last core down 431.378221 s, wake record 521.562497 s);
  woken by the hypervisor's alarm (commit + 90 s) `[ARTEFACT A6]`, which replaced macOS's own
  (`f0 4c 09 00`, written 4.6 ms before T). Wake status `0x23d00401c` / `020` / `024` = 0 /
  `0x400000` / 0: **the same in all eight captures**. After the wake `0xd00c` reads `01`.
- **Capture J** *(round 8)*: asleep 89.513 s (last core down 24.438224 s, wake record
  113.951187 s); woken by the instrument's alarm (commit + 90 s) `[ARTEFACT A6]`, which replaced
  macOS's own (`3a 8a 09 00`), **with watchdog 1 armed at the commit** (control 4, bite 150 s,
  1.7c). Wake status 0 / `0x400000` / 0: **the same in all nine captures**. At the wake entry:
  `0x23d2b8028` = `0x8000000`, `0x23d2b8040` = `0x22`, `0x23d2c001c` = `0xff0`, watchdog 2 count
  `0x76f11b` (0.325 s), bite `0x7270e00`, control 0, as at every detached wake; watchdog 1 count
  `0x51ae8`, watchdog 0 count `0x51b57` (both 13.9 ms), watchdog 1 bite and control as written.
  So the watchdog 1 counter, armed, did not keep the chip up, and did not count through the
  sleep.
- **Capture K** *(round 9)*: asleep 89.47 s; woken by the instrument's alarm `[ARTEFACT A6]`,
  with watchdog 1 armed at the commit as in J. Wake status 0 / `0x400000` / 0: **the same in all
  ten captures**. At the wake entry `0x23d2b8028` = `0x8000000`, `0x23d2b8040` = `0x22`,
  `0x23d2c001c` = `0xff0`, watchdog 2 count `0x770474` (0.326 s), bite `0x7270e00`, control 0;
  watchdogs 0 and 1 counts 14.1 ms; watchdog 1 bite and control as the instrument wrote them.
  Watchdog 2 was armed at the commit (control 4, 5 s, started about 15 ms before T, 4.1c) and
  reads disarmed with a 0.326 s count at the wake entry: between the two it was written again,
  not by macOS (no write in K's log, and macOS has not run yet at the wake entry) and not by the
  instrument (no write to it in its code, A6). By what is not observed.
- **The round-9 runs** `det13`, `det14`, `det16`, `det17` **[HV-CHANGED]**: not asleep as far
  as can be told; each ended in a reset 5-7 s after the commit, with no wake at the alarm
  (1.7d). Whether the chip powered down at all before the reset is not read.
- **Capture L and the round-10 runs** *(round 10; 1.7e)*: L asleep 89.58 s, `det19b` 89.74 s
  and `det21` 89.62 s **[HV-CHANGED: each core's guest timer left enabled]**, each woken by the
  instrument's alarm `[ARTEFACT A6]`; wake status 0 / `0x400000` / 0 in all three, **the same in
  all thirteen captures with a wake**; at the wake entry the always-on and watchdog words as in J
  and K. In `det19b` and `det21` every performance core's guest virtual timer was due about
  89.39 s after its final write (about 0.6 s before the alarm) and one efficiency core's 62-63 ms
  after it; their times asleep and wake status are those of the runs with the timers written off
  (J 89.51 s, K 89.47 s, L 89.58 s), and nothing in the record marks a wake by a core's timer. `det20b`, `det22c` **[HV-CHANGED]**: not asleep as far as can be
  told; a reset about 6 s after the commit, no wake at the alarm.
- **The round-11 runs** *(round 11; 1.7f)*: `det23` asleep 89.998 s, `det24` 89.649 s
  **[HV-CHANGED: `0x23b71c000` cleared before the cores' final writes]**, each woken by the
  instrument's alarm `[ARTEFACT A6]`; wake status 0 / `0x400000` / 0, **the same in all fifteen
  captures with a wake**; the wake-entry words as in J-L.
- **Watchdogs before the sleep (G, H):** macOS writes watchdog 0's count `0x23d2b0000` = 0 and
  watchdog 1's count `0x23d2b0010` = 0 in E3 (T-0.462 in H), and watchdog 0's control
  `0x23d2b000c` = 0 in E5 (T-0.035 in H); no other write to that page between the detach and
  T. Whether a watchdog counts while the chip is asleep is not observed: the count read at the
  wake is 7.7 to 7.8 million (0.32 s at 24 MHz) after sleeps of 1.6 s to 415 s. *(Round 8, J.)*
  Watchdogs 0 and 1 do not carry their count through the sleep: both read 13.9 ms at the wake
  entry after 89.5 s asleep, though last zeroed 0.466 s apart (1.7c).
- **Not known**: anything the chip or the power chip did while asleep; whether any register
  changed during the sleep other than as seen in the wake snapshot; the power drawn.

## 6. Wake

Phases W0-W5. Times are A / B relative to W. Extracts: `phases-post-N.tsv` (W1-W3),
`wake-late-N.tsv` (W4), `ps-post-N.tsv`, `mbox-post-N.txt`, `spmi-post-N.txt`,
`hvlog-wake-N.txt`, `saverestore-N.tsv`.

**Times in the three captures** (seconds after each capture's first access; `phase-times.tsv`):

| Console marker | A | B | D | E | F |
|---|---|---|---|---|---|
| first active action (interrupt controller) | +0.004 | +0.003 | +0.0003 | +0.0003 | +0.0003 |
| power-manager active action | +0.087 | +0.086 | +0.005 | +0.005 | +0.005 |
| memory-controller active action | +0.227 | +0.230 | +0.018 | +0.018 | +0.018 |
| first wake action | +1.006 | +1.008 | +0.122 | +0.120 | +0.119 |
| PMP wake action | +1.412 | +1.517 | +0.134 | +0.133 | +0.132 |
| power-manager wake action | +3.497 | +3.559 | +0.343 | +0.340 | +0.339 |
| "IOCPUSleepKernel exit" | +3.696 | +3.780 | +0.407 | +0.403 | +0.401 |
| "system wake events" | +4.957 | +5.706 | +0.858 | +0.677 | +0.748 |

In D the first access is 0.505 ms after the hypervisor's wake record and 0.211 ms after it
re-entered macOS (E: 0.493 ms, F: 0.492 ms after the wake record); the time from the chip's reset to the wake record is not recorded.

**Capture G's times** (seconds after its first access): power-manager active action +0.005;
memory-controller active +0.018; first wake action +0.130; PMP wake action +0.145;
power-manager wake action +0.354; "IOCPUSleepKernel exit" +0.420; "system wake events" +0.697.
First access 0.545 ms after the wake record. Cores started W+0.1226 to W+0.1292 in the order
7, 6, 3, 2, 5, 1, 4; the 368 system-register records after the wake carry the same writes as
D's. Ordered writes identical to D's in 54 of 57 active actions and 24 of 30 wake actions.

### W0. Before macOS runs `[ARTEFACT A7]`, and the "wake" snapshot

The hypervisor's wake entry runs, re-creates its USB device, and takes the snapshot: 265 words
by its log, 264 distinct addresses in the file. **261 have the same value in both captures**;
the 3 that differ are DCS3's domain word `0x23b700318` (`0x1000030f` / `0x1f0003ff`) and
`0x23b71c0f0`, `0x23b71c120` (bit 30 differs). Compared with "pre-full" (`snap-wake.tsv`):
169 (A) / 167 (B) words are unchanged and 95 / 97 differ. The pattern of the changes:
- most domain words come back in a default state, not the state before the sleep: e.g. AIC,
  GPIO, SOC_DPE `0xff` -> `0x2ff`; I2C0-4, SPI0-4, FPWM0-2 `0x200` -> `0x344`; UART1-8, UART_N
  `0xff` -> `0x344`; MCA0-5, DPA0-1, SIO_ADMA `0x200` -> `0x300`; MCC `0x1f0000ff` ->
  `0x0f0003ff`; SIO, SIO_CPU, SIO_BUSIF `0x1400024f` -> `0x0f0003ff`; PMP, RMX `0x1000030f` ->
  `0x0f0003ff`; ANS2 `0x1000230f` -> `0x0f002300`; GFX `0x1000230f` -> `0x0f0023ff`;
- unchanged: DCS0-5 and DCS7 (`0x1000030f`), SEP (`0x1000230f`), AES, ISP and video-encoder
  domains;
- 25 of 95 clock-generator words at `0x23b040000`+ differ; the five muxes of E5-8a read the
  same as in "pre-full" (`0x85100000`, `0x87100000`), not the `0x80100000` macOS wrote;
- UART_P, UART0 read `0x3ff` and ATC0_COMMON `0x23ff`: the hypervisor's own use `[A7]`.
- **Capture D**: 264 words; **255 equal in all three captures** (256 equal to A, 257 to B). The
  9 that differ are six DRAM-controller domain words (`0x23b700308`, `318`, `320`, `328`, `330`,
  `338`; values `0x1000030f`, `0x1f0003ff` or `0x1400034f`) and `0x23b71c0d8`, `0x23b71c0f0`,
  `0x23b71c120` (bit 30). The clock muxes read `0x85100000` / `0x87100000` in D too.
- **Captures E and F**: 264 words; **253 equal in all five**, 259 equal among D, E, F (D-E 262,
  D-F 259, E-F 260). The five that differ among the detached captures are DRAM-controller
  domain words (`0x23b700300`, `308`, `310`, `318`, `328`). After 1.6 s asleep (F) the chip
  shows the same default domain states as after 415 s (E): the power manager's words do not
  keep their pre-sleep values even across the shortest sleep seen.

### W1. Core 0: first accesses and the "active actions" (W to W+0.56)

Console: 57 lines "IOPlatformActiveAction -> driver". Only core 0. 57 segments, 41 identical
access for access, 53 with identical ordered writes; 6,019 accesses and 3,163 writes in A.

0. **Before the first console line** (W to W+0.003; 18 accesses, identical): console set-up
   `0x23d10c000`..`00c` = 0, 3, 0, 3 and `0x23d128008`=`0x83d600` `[A12]`; then
   `W 0x210055008`=`0xffbfffffffffffff`, `W 0x210055000`=1; `W 0x210e49008`=
   `0xff5fffffffffffff`, `W 0x210e49000`=1.
1. **Interrupt controller** (W+0.004 to W+0.087): **991 writes, no reads, identical in both**:
   `0x23b100010`=`0xe0777971`; 896 words `0x23b103000`-`0x23b103dfc`; 56 words
   `0x23b104100`-`0x23b1041ec`; 22 words `0x23b105024`+`0x80`k and `0x23b105028`+`0x80`k
   (k = 0..10, the last `0x23b105524`, `0x23b105528`); 16 words `0x23b106000`-`0x23b1060f0` (stride `0x10`). (Corrected count, gap
   11: 1 + 896 + 56 + 22 + 16 = 991.) The rule tying each written value to the entry's reads is
   in E6-1. The first 408 / 372 written values equal what the cut sweep of E5-10 had read.
2. **Power manager** (W+0.087 to W+0.227; 1,175 writes in each capture, 2,737 / 2,728 accesses;
   address order of writes identical, 175 written values differ: they are the values saved in
   E5-8). In order:
   a. `W 0x23b718000`=`0xf`, `W 0x23b718004`=`0xf` (poll of `0x23b718004`: 9 more reads in A).
      **In all seven** (gap V7; `gaps_gh.py`): before its write `0x23b718000` reads `0xf` (it
      already holds the value written; it reads `0xf` again after) and `0x23b718004` reads 0;
      after `0x23b718004` is written `0xf` it is read until it changes: `0x1f` 154 to 243 times
      (A 163, B 154, D 237, E 228, F 243, G 242, H 235), then `0x2f` once, and the poll ends on
      `0x2f`;
      `W 0x23b71c000`=`0x80000000`, `W 0x23b71c040`=`0x80000000`; *(round 10, all thirteen
      captures with a wake, `r10-checks.txt` part 4: each is read just before its write,
      **`0x23b71c000` reading 0** and `0x23b71c040` `0x80000000`; both read `0x80000000` with
      macOS awake and at the commit, 4.1d; *round 11:* the same in `det23` and `det24`, all
      fifteen, also after the instrument had cleared `0x23b71c000` before the commit, 1.7f)*;
   b. tables written to both cluster blocks (`0x210e48c10`.., `0x210e480c0`.., `0x210e48480`..;
      `0x211e48c10`.., 16 and 22 writes) between reads of `0x210e70000`-`0x210e70160` and
      `0x211e70000`-`0x211e70160`; 28 + 12 + 4 + 93 + 18 + 12 byte-sized values written to
      `0x23b204004`-`0x23b207300`;
   c. **power domains restored** (`ps-post-N.tsv`): 138 writes in both captures, each domain
      brought to its target in up to three steps (state, then state with low bits `0xf`, then
      bit 28 set), e.g. UART1 `0x44`, `0x4f`, `0x1000004f`; AIC `0xff`, `0xff`, `0x100000ff`;
      MCC `0x1f0000ff`; DCS0-7 `0x1f0000ff` or `0x1000000f` (DCS2, DCS3, DCS5 differ between
      captures: `0x1f0000ff` in A, `0x1000000f` in B; DCS4 and DCS7 `0x1000000f` in both); PMP,
      PMS, SIO_CPU, IMX `0x0f0000ff`, `0x0f0000ff`, `0x1f0000ff`; ANS2, APCIE_GP `0x0f002000`,
      `0x0f00200f`, `0x1f00200f`; SEP `0x1000200f`; then domains set to off or gated: ANE_SYS,
      DISP0_CPU0, DISPEXT_CPU0, GFX, MMX, RMX `..3f0`; I2C0-4, SPI0-4, FPWM0, FPWM2 and others
      `0x340`;
   d. the three blocks of E5-8f set up again (`0x68c000000`/`0x68c008000`, `0x279001000`/
      `0x279008000`, `0x234001000`/`0x234008000`: 40 to 50 writes each);
   e. timer state written back: 441 + about 100 writes to `0x23b734120`.., `0x23b778100`..,
      `0x23b77c100`..; then `W 0x23b77c000`=1, `W 0x23b778000`=1;
   f. cluster state written back: `0x210e20400`.., `0x210e20580`.., `0x210e20660`=
      `0x1000000015`, `0x210059000`.. (4 cores), `0x210e48000`, `0x210e48080`=
      `0xa000000000000000`; same for `0x211e..`;
   g. `W` DCSn+`0xdc4`=`0x0813057f`, `W` DCSn+`0xdbc`=`0x01800180` for n = 0..7;
   h. 12 writes to `0x23b549000`+; `W 0x23b748000`, `c00`, `800`, `400` = 1. **In all seven**
      (gap V1): each of the four reads **0** just before this write (after the sleep; at the
      entry they read 1 and were written 0), and none of the four status words +`0x3e0` is read
      at the wake;
      `0x210e48400`, `0x211e48400`, `0x210e40240`/`250`, `0x211e40240`/`250` written back with
      bit 63 set again.
   Guarded words in this action, from the hypervisor's log `[A3]`: UART_P, UART0 `0x100000ff`;
   SIO_BUSIF, SIO `0x0f0000ff` twice then `0x1f0000ff`.
3. **Memory controller** (W+0.227 / W+0.230; 290 writes, identical): `R 0x200001c00`=0;
   `0x20010000c`/`014` pulse around `W 0x200010010`=0; pulse around **`W 0x200001c00`=`0x10`**;
   `R 0x200001c04` = `0x200`, `0x4200`, `0x4200` and two reads on each other plane; then
   `0x200158050`.., `0x200158000` and `0x200024000`.. set up word by word (138 distinct words).
4. **Error handler** (W+0.255 / W+0.260; 33 writes, identical): `W 0x200155000`=`0xff000000`;
   per plane P: `W` P+`0x72c`=`0xffffffff`, `W` P+`0x730`=`0x30000`, `W` P+`0x21008`=`0x700`,
   `W` P+`0x21000`=`0xfffffc3f`, read and write back P+`0x21004` and P+`0x2100c`; then
   **`W` DCSn+`0x7a0`=`0xc0000` for n = 0..7**.
5. "AppleT8020SOCTuner" (W+0.264): DCSn+`0xc` read and written back (`0x070a1100`), n = 0..7.
6. "AppleS5L8960XNCO" (W+0.274): `0x23b044000`, `0x23b048000`, `0x23b04c000`, `0x23b050000`,
   `0x23b054000`: each read (`0x80000000`), written 0, written `0x80000000`.
7. "AppleS8000DWI" (W+0.285): `W 0x23b200000`=1, +`0xd0`=`0x2ee00`, +`0x4`=`0x78`, +`0x84`=0,
   +`0x80`=`0x41`.
8. Address translators: 19 actions, one does something: `dart-sio` `0x235004000` (30 writes).
9. **Pin controller** (W+0.380): 474 writes to `0x23c100000`+ (262 distinct words), identical.
10. **PCIe** (W+0.433): 110 writes, identical.
11. Temperature sensors (W+0.454 to W+0.56): reads; two sensors written (6-30 writes); the
    order and the split between actions differ between captures.

**Capture D** (`three.py`; untrapped pages left out): the same 57 actions in 0.12 s. Ordered
writes identical in all three captures in 52 of 57 (A-B 53, A-D 53); for items 0, 1, 3, 5, 6,
7, 9, 10 the ordered writes are identical in all three. Item 1: 991 writes, identical to A and B. Item 2: 1,091 writes on
this basis in each capture, same addresses in order, values differ where they are saved state;
the poll of `0x23b718004` runs 239 reads in D. Guarded words with times (hypervisor's records,
`[A3]`): UART_P W+0.01202, UART0 W+0.01208 (`0x100000ff`); SIO_BUSIF W+0.01375, SIO W+0.01377
(`0x0f0000ff` twice, then `0x1f0000ff`); the hardware held `0x3ff` (UART) and `0x0f0003ff`
(SIO) before. Item 4: one written value differs from A and B: plane 3's `0x2000e1004` (the
read-and-write-back word P+`0x21004` of plane `0x2000c0000`) is first written `0x8000000` in
A and B and `0` in D, E, F, G and H, then `0x4000000` in all seven (gap 9; `gaps_gh.py`). The
value it read before the sleep is not compared here. DCS domain values at item 2c:
DCS2 `0x1400004f`, DCS3, DCS4, DCS5 `0x1f0000ff` in D: a third combination.

**Captures E and F**: ordered writes identical to D's in 53 (E) and 54 (F) of 57 actions;
identical in all five captures in 52. The guarded words are handled as in D, at W+0.0122 to
W+0.0139 in both. Item 2c: again other DCS combinations (E: DCS0 `0x1000000f`, DCS2
`0x1f0000ff`, DCS7 `0x1400004f`; F: DCS0, DCS2 `0x1000000f`, DCS5 `0x1400004f`), and in F FPWM1
is written `0x340` once instead of `0x44`, `0x4f`, `0x1000004f`: it had been turned off before
that sleep (section 3, last part). So item 2c writes each domain back to **the state it was in
before the sleep**, not to a fixed table (1,089 writes in F against 1,091).

### W2. Secondary cores start (W+0.56 to about W+1.35)

Hypervisor's log (`hvlog-wake-N.txt`), identical in both apart from load addresses: core 0
writes to the start words for cores 7, 6, 3, 2, 5, 1, 4 in that order: for core 7
`0x23b754004`=`0x80`, `0x23b754008`=0, `0x23b75400c`=`0x8`; the hypervisor then starts the
core at macOS's reset entry `[A4]`. *(Round 10.)* In the round-10 build the writes of +`0x4` do
not reach the hardware (A4); what +`0x4` reads after the wake is not read. First device access per core: core 7 W+0.796 / W+0.799,
core 6 W+0.799 / W+0.809, core 3 W+0.904 / W+0.883, cores 1 and 2 W+1.006 / W+1.007-1.009,
cores 5 and 4 W+1.338, W+1.351 / W+1.415, W+1.424. Each core's first device writes are
`W 0x21N155008`=`0xffbfffffffffffff`, `W 0x21N155000`=1 on its own block (for example
`0x210155008` for core 1, `0x211055008` for core 4). **Core 7**, the first core of the
performance cluster to start, then also writes `0x211e49008`=`0xff5fffffffffffff`,
`0x211e49000`=1 (the cluster pair, as core 0 does for `0x210e49...`); cores 4 and 6 do not
(D, G, H checked; gap 4).
**Before each core's start words** core 0 writes `0xc5acce55` to `0x21N30fb0` of that core
(`0x211330fb0` for core 7, then `0x211230fb0`, `0x210330fb0`, `0x210230fb0`, `0x211130fb0`,
`0x210130fb0`, `0x211030fb0`, in start order), 11 microseconds before the first start word of
the same core in D, G and H (gap S1). What the word is, is not established.

**Capture D, timed** (`det_events.py`): the start-word writes and the hypervisor's start of
each core: core 7 at W+0.113746, 6 at W+0.114855, 3 at W+0.115973, 2 at W+0.117166, 5 at
W+0.118261, 1 at W+0.119343, 4 at W+0.120679: **the same order 7, 6, 3, 2, 5, 1, 4 in all three
captures**, about 1.1 ms apart, 2.6 ms after the last active action's console line (W+0.1111)
and before the first wake action (W+0.122). First device access of each core 2 to 7 ms after its start (W+0.1206 to W+0.1225),
with the same two first writes as above. In A and B this phase took 0.8 s.
E: starts W+0.112426 to W+0.119372; F: W+0.111709 to W+0.118573; same order.

### 6.3 System registers macOS writes on each core at the wake (hypervisor's log)

Identical in both captures except the two address-dependent values marked *.
- Every core, first: `CTRR_A_LWR_EL1`*, `CTRR_A_UPR_EL1`*, `CTRR_CTL_EL1`=`0x12`,
  `CTRR_LOCK_EL1`=1 (shadowed, A5); `ACC_CFG_EL1`=`0xd` (dropped, A5).
- Cores 0-3 (13 writes each): `HID5_EL1`=`0x2082df50e700df14`; `EHID10_EL1`=`0x3000528002788`
  (twice); `EHID20_EL1`=`0x618100` (four times; the value read before the first write was `0x618000`);
  `EHID9_EL1`=`0x600000811`.
- Cores 4-7 (34 writes each): `HID13_EL1`=`0xc332200211010205`, `HID14_EL1`=`0x500000bb8`,
  `HID5_EL1`=`0x2082df205700ff12`, `HID0_EL1`=`0x10002990120e0e00`,
  `HID3_EL1`=`0x4180000cf8001fe0`, `HID1_EL1`=`0x1440000002000000`,
  `HID16_EL1`=`0x6900000440000000`, `HID9_EL1`=`0x8100086c000000`,
  `HID11_EL1`=`0x804000010008000`, `HID6_EL1`=`0x7dc8031f007c0e`, `HID7_EL1`=`0x3110000`,
  `HID18_EL1`=`0x2000040004000`, `HID21_EL1`=`0x1040000`, several of them more than once.
Only registers the hypervisor traps are listed; others macOS sets are not visible.

**Capture D** records the same writes with times and by register encoding (`det-sysreg.tsv`;
368 records, 188 of them writes; names matched to A's log by value and order): the same values
in the same order on every core, except the two CTRR bounds (`0x818540000`, `0x81c9a3fff` in
D). **Identical in all three captures.** Core 0: 25 records between W+0.000385 and W+0.000445,
that is 0.09 ms after the resume and before its first device access. Cores 7, 6, 3, 2, 1, 5, 4:
each within 0.4 to 6 ms after its start (W+0.1148 to W+0.1225). No record before the wake.
E and F: 368 records each, the same writes with the same values in the same order on every
core (CTRR bounds aside): **identical in all five captures**. Core 0 from W+0.000372 in both.

### W3. "Wake actions" (W+1.006 / W+1.008 to W+3.696 / W+3.780)

Console: 30 lines "IOPlatformWakeAction -> driver", then "IOCPUSleepKernel exit". Several cores.
30 segments, 22 identical, 25 with identical ordered writes.
- AppleT8103MemCacheController (W+1.356 / W+1.435): 70 writes, identical: 14 words at
  `0x20000a004`-`0x20000a034` (values such as `0x20040`, `0x30040`, `0x10040`, `0x2b0020`),
  each inside a `0x20010000c`/`0x200100014` pulse.
- AppleMCA2Switch (W+1.381 / W+1.479): 106 writes, identical; before it the domains SIO_ADMA,
  MCA0-5 are turned on (`0x0`, `0xf`, `0x1000000f`) and after it set to `0x3f0`.
- **ApplePMP** (W+1.412 / W+1.517 to W+3.49): **49,152 words written to
  `0x23b52c000`-`0x23b55bffc`, each with the value read from it in E3** (corrected wording, gap
  S8: checked word by word in D, G and H, 49,152 of 49,152; the earlier "49,143 of 49,154" counted
  first writes of the whole action, which includes the translator words). This write-back comes
  first in the action. Then `pmp`'s address translator `0x23b300000` gets ten writes, the same in
  D and H in this order (gap S2): +`0xfc`=1, +`0x200`=V, +`0x2f0`=0, +`0x34`=`0xffffffff`,
  +`0x20`=`0x100000`, +`0x60`=`0x80016100`, +`0x68`=`0xf0f0f`, +`0x6c`=`0x80808`,
  +`0x100`=`0x80`, +`0x13c`=`0x100`. V differs in every capture (`0x80822788` D,
  `0x80821240` G, `0x80822b80` H) and the word is not read or written in the log before the
  sleep in any capture; the same holds for `sio`'s translator words `0x235004200`,
  `0x235004210` of W1-8 (D `0x80822760`, `0x808225fc`; G `0x80820990`, `0x808209a0`; H
  `0x80822764`, `0x808225c8`). Where macOS takes these values from is not observed (its own
  memory is not in the log). *(Added this round, capture I, open question 36.)* With the two
  translator pages logged from boot (1,178 accesses before the detach), every write to the
  three words comes from one instruction (pc `0xfffffe0015022d8c` in I), 32 bits, 2.2 to 2.9 s
  after the start of logging at boot: `0x23b300200` <- 0 then `0x808217dc`; `0x235004210` <- 0
  then `0x80821a38`; `0x235004200` <- 0 then `0x80822854`. After the wake the same instruction
  writes **the same three values** (`sio`'s two at W+0.042, `pmp`'s at W+0.350), without a
  read. So in I each value written at the wake is the value macOS wrote there at boot; it
  differs from boot to boot. What the value points at is not read. Then, in both `sio`'s and `pmp`'s wake action, in all seven:
  +`0x8114` read `0x20001` and written `0x20001`, +`0x44` read 0 and written `0x10`, and the
  coprocessor's first message is read (+`0x8114` reads `0x100101`);
  then the coprocessor is started and boots: hello `0x00100000000c000c` / acknowledgement
  `0x00200000000c000c`, two endpoint-map exchanges, "power acknowledged `0x20`", "AP power
  `0x20`" echoed (W+3.493 to W+3.496).
- AppleT8103PMGR (W+3.497 / W+3.559): reads the wake status words `0x23d00401c`-`0x23d00402c`.
- AppleSmartIO (W+3.506): `W 0x236408114`, **`W 0x236400044`=`0x10`**, then `sio` boots (same
  message pattern as `pmp`).
- AppleGen1SPMIController (3): **`W` +`0x338` restored** (`0x23d0d9338`=`0x3f003ff1`, and the
  other two controllers).
- AppleDialogSPMIPMU: SPMI read of power-chip register `0xd00c` (`01` in A, `00` in B). After
  the three alarm wakes (A, G, H) and after none of the four key wakes, the SPMI controller word
  `0x23d0d9320` is also written, `0` then `4` (gap S11; `gaps_gh.py`). *(Added this round, gap
  Q9; I is a fourth alarm wake and does the same.)* What differs before those writes: the first
  reads of the controller's words +`0x320` and +`0x360` after the wake (W+0.11 to W+0.12 in
  D-I, W+0.56 in A, B; the same reads follow every SPMI command, E3) return +`0x320` = 4 in all
  eight, and **+`0x360` = 4 after the four alarm wakes, `0x20000000` (B, D, F) or `0x20010000`
  (E) after the key wakes**. After an alarm wake macOS then writes +`0x360` = 4 (the value
  read) and +`0x320` = 0, and both read 0; after a key wake it writes neither. Later, in this
  action, the SPMI read of `0xd00c` returns `01` and is followed by +`0x320` = 4 (W+0.394 in
  I). So the writes follow a read of +`0x360` with bit 2 set and `0xd00c` = `01`; which of the
  two macOS tests is not observed (they occur together in every capture). What +`0x320` and
  +`0x360` are is not established.
- AppleARMWatchdogTimer: SPMI write `0x9f01`=`0x00` and the same seven scratch reads as in E3
  (`0x9f08` now `ff ff 51 01`, A10).
- AppleSMC, AppleSMCPMU: `smc` "AP power `0x20`" echoed (W+3.643); key `MBSE` = `0x77616b61`
  ("waka") written (W+3.675 / W+3.771).
- The other actions (pin controllers, I2C, SPI, Thunderbolt, NVRAM, key store, AVD) show
  nothing attributable or a handful of accesses that differ between captures.

**Capture D**: the same 30 actions between W+0.122 and W+0.407. The PMP write-back takes 0.21 s
(W+0.134 to W+0.343; 2.08 s in A): 49,152 words, 49,143 with the value read in E3, as in A and
B. Ordered writes identical in all three captures in 21 of 30 actions; none is identical access
for access between A and D, because in D the other cores are already running and their accesses
fall into every interval. `sio` and `pmp` boot messages identical in all three. `smc`: "AP power
`0x20`", key `MBSE`=`0x77616b61` at W+0.404. SPMI controllers' +`0x338` restored to
`0x3f003ff1` / `0x3d003ff1`. Power-chip `0xd00c` read `00`, `0x9f01` written `00`; scratch
`0x9f08`-`0x9f0b` read `ff ff 47 50` (A10).
**Captures E and F**: the same 30 actions, W+0.120 to W+0.403 and W+0.119 to W+0.401. Ordered
writes identical to D's in 26 of 30 in each; in all five captures in 20. PMP write-back as in
D. `smc` key `MBSE`=`0x77616b61` at W+0.400 / W+0.398.

### W4. Drivers power up (W+3.70 / W+3.78 to about W+6 in A, W+12 in B)

Console: "IOCPUSleepKernel exit", USB "system wake", "AppleSEPManager power state 0 -> 2", audio
power stages 0 -> 3 -> 4, `aop` "wake notification", storage ("Enabling LSQ", queue set-up),
Wi-Fi "Link Up", "SEP EP .. enabled", "system wake events: ...". Coprocessors, in order of
first message (A): `aop` "AP power `0x20`" (W+3.807) and its endpoints restarted (`0x00a3..` /
`0x0086..`); `sep` (W+3.810); `gfx-asc` boots (W+3.826); `ans` boots (W+3.843; storage domain
APCIE_ST on at W+3.83); `dcp` boots (W+3.914) and `dcpext` (W+3.930), with their domains on at
W+3.90; in A `dcp` is sent "AP power `0x20`" (W+3.92) then "`0x201`" (W+3.93) and no more; in
B it is sent `0x20`, `0x201`, `0x20`, `0x201`, `0x20` (W+4.00 to W+4.33) and stays up ("FB0 ...
OFF to ON", W+4.50) and graphics traffic resumes (352 graphics messages in the first 6 s against 4 in A). Key writes:
B only, `WKTP`=`00` (W+4.195). This phase differs between the captures in content and length
(`compare.py post 3.7 12`: 71 pages written, 18 with identical ordered writes).

**Capture D** (key press, like B): `dcp` is sent "AP power" `0x20`, `0x201`, `0x20`, `0x201`,
`0x20` (W+0.450 to W+0.511), the same five as B; "FB0 ... OFF to ON" at W+0.519; keys `WKTP`=`00`
(W+0.523, W+0.930) and `gP0f`; "system wake events" at W+0.858. Pages written from kernel exit
to that line: ordered writes identical in 29 of 66 between B and D, 19 of 66 between A and D.
**Captures E and F** (key or trackpad, cable out): "full wake promotion (reason 1)" and "FB0 ...
OFF to ON" at W+0.567 (E) and W+0.512 (F); `WKTP`=`00` at W+0.484, W+0.671 (E) and W+0.491,
W+0.759 (F). Pages written from kernel exit to "system wake events": ordered writes identical
in 26 of 65 (D, E), 24 of 65 (D, F).

**Capture G (alarm wake) against A (alarm) and the key wakes.** In the 20.8 s recorded G
behaves as A did for 163 s: `dcp` is sent "AP power `0x20`" (W+0.464) and then "`0x201`"
(W+0.477) and nothing more; DISP0_FE is turned on (W+0.458) and off again (`0x3f0`, W+0.487);
there is no "OFF to ON" console line and no "full wake promotion"; no `WKTP` key is written;
4 graphics messages in all; the memory-controller burst I5 does not return; the once-a-second
read of `0x23d2b9040`.. that A showed starts (first at W+4.4). The key wakes (B, D, E, F) all
turn the display on within 0.6 s, write `WKTP`=`00` and resume I5 within 0.7 s. So **both
alarm wakes stay dark and all four key wakes light the display**; two captures against four.
G was read out before macOS could go back to sleep, so what a dark wake does next is not
captured. **Capture H** (alarm) is dark too: no "OFF to ON" line, no `WKTP` key in the 20.8 s
recorded, "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0x02 nub-spmi.0xC0 rtc" at W+0.671,
`0xd00c` reads `01`. Three alarm wakes (A, G, H) against four key wakes.

**`dcp` and `dcpext` at every wake** *(added round 7, gap W3; `r7_wake_display_sum.py`,
`r7-wake-display.txt`, `r7_wake_display.py`).* In all eight captures macOS turns the display
domains on (RMX, DISP0_FE, DISP0_CPU0, DISPEXT_FE, DISPEXT_CPU0 by form 4 of section 4.3; I:
W+0.4553 to W+0.4584), restarts **both** coprocessors (translator, +`0x8114` = `0x20001`, +`0x44`
0 -> `0x10`, E2a), boots them (`0x00200000000c000c` sent, endpoint-map words, "AP power `0x20`"),
starts their endpoints `0x20`-`0x2c` and sends three endpoint-`0x37` words, and then **stops
both again** by the whole of E2a (power messages, 13 endpoint stops, register stop, translator
streams 0 and 15 cleared) and turns their domains off (child first, forms 2 and 1), 9 to 169
ms after the restart (I: `dcp` +`0x44` `0x10` at W+0.4575, 0 at W+0.4668). After the four
alarm wakes (A, G, H, I) nothing more happens to either before the end of the log (163 s in
A, 20.8 s in G-I): the display domains end at their commit values (RMX `0x0f000300`, DISP0_FE
`0x300`, DISP0_CPU0 and DISPEXT_CPU0 `0x0f040300`, DISPEXT_FE `0x300`) and both coprocessors
are stopped. After the four key wakes (B, D, E, F) `dcp` is restarted and stopped once more
and restarted a third time (+`0x44` `0x10`, 0, `0x10`, 0, `0x10` from W+0.44 to W+0.51 in D,
E, F; W+3.98 to W+4.32 in B) and stays running with RMX `0x1f00000f`, DISP0_CPU0 `0x1f04000f`;
`dcpext` is stopped once and stays stopped with its domains off, as with macOS awake (E2a).
In every case (E1, E2, every wake; D-I, 63 starts and stops, `r7_stop_domain.py`) each stop
of `dcp` or `dcpext` is followed by the off writes of its CPU0 word (the first `0x0f0400ff`,
at most 2.4 ms later), and each start is preceded by that word's turn-on to `0x1f04000f` (D:
RMX, DISP0_FE, DISP0_CPU0 turned on, `dcp` started, stopped, the three turned off, twice; then
on and started a third time, W+0.44 to W+0.51): no capture leaves a display coprocessor
stopped with its domains on, or running with them off.

### W5. Back at idle

Distinct (address, direction) pairs not seen in the idle before the sleep, per second after W
(`backtoidle.py`): A 4,009, 14,069, 23,602, 12,682, 551, 924, 42, 0, then a steady 15 (the
`0x23d2b9040`.. poll of section 2); B 4,007, 12,031, 24,257, 13,999, 804, 282, 914, 113, 50,
47, 56, 23, then 0 from W+12. See section 2 for how A's idle after the wake differs.
D: 54,639 in the first second, 796, 147, 26, 56, 23, then 0 from W+6 (`det_misc.py`).
E: 54,707, 223, 179, 0, 33, 3, then 0 until the cable goes in at W+10.3. F: 54,681, 244, 205,
23, 56, 23, then 0 from W+6 until the cable goes in at W+16.1 (section 10).

### 6.4 What the wake reads that the entry did not leave (D-I; added this round, gap Q7)

`reset_reads.py`, `reset-reads.tsv`: for every word whose first access after the wake, in the
active actions (W to the first wake action), is a read, the value read against the value the
word held at the entry (its last value written or read before T). 196 words differ in at least
one capture. Apart from the domain words (all of W0's default states, e.g. SIO_CPU `0x0400024f`
-> `0x0f0003ff`, I2C0 `0x200` -> `0x344`, MCA0-5 `0x200` -> `0x300`, PMP `0x1f0f03ff` ->
`0x0f0003ff`) and running counters (the memory controller's `0x200025000`.., `0x200027000`..,
`0x200159000`.., `0x200204000`.., the timer block `0x23b734300`.., `0x23b2040b0`/`b4`), the words
read at the wake with a value the entry did not leave are, in D-I:
- `0x23b718000`: written 0 at the entry, reads **`0xf`** before its wake write (R30);
- `0x23b734000`: written 0 at the entry (R19), reads **1** before its wake write;
- `0x200001c04`: read 0 at the end of the entry's wait (R16), reads **`0x200`** before the
  wake's pulse;
- pin controllers `0x24a820900`, `0x24a820904`, `0x23d1f0900`: written `0xffffffff` at the
  entry (R13), read **0**;
- PCIe `0x680084004`: written `0x8035` at the entry (E5-3), reads **`0x35`**;
- interrupt controller `0x23b102004`: read 0 at the entry, **`0x100be`** at the wake;
- `0x23d0d9360`: 0 at the entry, 4 or `0x20000000`/`0x20010000` at the wake (W3, Q9).
Words that read at the wake what the entry left: the sub-block control words (written 0, read
0), `sio`'s and `pmp`'s +`0x44` (written 0, read 0, R5w), `0x23b718004` (written 0, read 0), the
six cluster words of R21 (bit 63 as written). In all eight captures the chip had been through a
power-down; **what these words read after an entry that did not power the chip down is not
observed under macOS** (no capture has one; section 11.1's cancelled entry stopped before the
display request). Which of the wake's steps would behave differently on such a chip is not
observable from these captures; the list above names the reads whose values come from the
power-down. Under Linux see section 12, L7, L8.

## 7. Invariant or not

### 7.1 Method

1. Kernel text addresses were normalised (capture B + `0x288000`) and the same instructions
   found at the same normalised address in both (`firstdiff.py`: the first 22 new accesses of
   the entry match in address, direction, value and instruction).
2. **By phase marker** (`phases.py`): the kernel paths E3, E5, W1, W3 are cut at macOS's own
   console lines; each segment of A is paired with the segment of B of the same driver name and
   the same set of addresses; the two access sequences are compared exactly (address, direction,
   value), then ignoring values, then writes only. The idle words of I1-I2, the console page and
   the SMC shared-memory page are removed first.
3. **By page** (`compare.py`): for a time window, the ordered accesses to each 16 KiB page are
   compared between captures. Used where several cores run (E1, E2, W4).
4. **By message** (`buses.py`): decoded SPMI frames and mailbox words per coprocessor.
5. **By final value** (`commit_state.py`) and by snapshot.
"Invariant" below means: identical in both captures under the stated comparison. Two captures
cannot show that something is invariant in general.

### 7.2 Numbers

| Comparison | Result |
|---|---|
| E5 quiesce actions, 34 segments | ordered writes identical in 34 (255 writes); all accesses identical in 30 |
| E3 sleep actions, 42 segments | all accesses identical in 34; ordered writes identical in 36 (81 writes in A) |
| E3+E5 console marker sequence (77 lines) | same drivers and counts; order differs (temperature sensors; SPMI vs I2C controllers) |
| W1 active actions, 57 segments | all accesses identical in 41; ordered writes identical in 53 (3,163 writes in A) |
| W3 wake actions, 30 segments | all accesses identical in 22; ordered writes identical in 25 |
| Wake console marker sequence (89 lines) | same drivers and counts; order differs in places |
| Window T-0.4..T by page | 83 pages; 62 written; ordered writes identical in 54, same write addresses in 56 |
| Window T-2.62..T by page | 115 pages (103 in both); 72 written; ordered writes identical in 57 |
| Window T-10.6..T by page | 162 pages (161 in both); 110 written; ordered writes identical in 73, same write addresses in 78 |
| Window W..W+0.56 by page | 96 pages; 84 written; ordered writes identical in 65, same write addresses in 82 |
| Window W..W+3.7 by page | 163 pages (140 in both); 128 written; ordered writes identical in 93, same addresses in 119 |
| Window W+3.7..W+12 by page | 125 pages (118 in both); 71 written; ordered writes identical in 18 |
| Memory-controller shutdown (E5-5, E5-6) | 135 writes, identical in address, order and value |
| Last value of words written in the entry | 602 words, 600 in both, 534 equal |
| "pre-full" snapshot | 792 words, 777 equal |
| "wake" snapshot | 264 words, 261 equal |
| Power-domain writes in the entry | same per-domain counts except SPI3 (E0); 8,220 of 8,249 in common order |
| Mailboxes T-3.7..T: `dcp`, `dcpext`, `gfx-asc`, `pmp` | identical sequences both directions |
| Mailboxes T-3.7..T: `aop`, `smc` | same messages, order differs |
| Mailboxes T-3.7..T: `ans`, `sep`, `sio` | differ (counters in payload; `sio` 15 / 13 sent) |
| Hypervisor-handled words (its log, whole run) | same lines except the order of core starts at boot and one extra ATC0_COMMON read in B |
| System registers at the wake, per core | identical except the two address-dependent CTRR bounds |

### 7.3 Classification of the statements of sections 3-6

- **Identical in both (invariant in these two captures):** E5 items 1-9 as writes (order of
  the sensor actions aside); the 135 memory-controller writes and the 39-read wait; E3's
  per-driver effects in the table (SMC, watchdog words, the three SPMI controller words, SIO and
  PMP stop sequences, the 49,152-word read range and order, the address-translator steps); the
  display, graphics and `pmp` mailbox sequences of E2; the domain writes of E1-4 and E2; the
  three `smc` key writes and their values; W1 items 0, 1, 3, 4, 5, 6, 7, 9, 10; W1-2's write
  addresses and order; 6.3; the wake status words; the 49,152-word write-back range.
- **Same shape, values differ:** counters read in E5-5 (run time dependent); saved and restored
  timer and cluster values (E5-8c/d, W1-2e/f; they are whatever was read before the sleep); the
  PMP block contents; the DCS domain words (which of DCS0-7 read `0x1000030f` or `0x1f0003ff`
  varies with the moment); the poll counts of the two waits on `0x23b7487e0` and `0x23b718004`;
  `sio`'s mailbox control word; storage and secure-enclave message counters; SMC shared memory;
  the PWM ramp; the CTRR bounds (kernel load address).
- **Differ:** E0 entirely; the order of same-priority actions (E3, E5-1, W1-11, W3); what runs
  concurrently in E1, E2, E3 and W3; whether `0x27bc50030`/`070` are written (A only); W4 and W5
  (A stays dark after the alarm wake, B lights the display); the idle after the wake; the wake
  cause; the sleep duration; where the log ends (A11).

### 7.4 Three captures

Method as in 7.1, with three changes (`three.py`, and `phases.py`, `compare.py`, `ps.py`,
`buses.py`, `commit_state.py` run per pair with `CAPS=3,d` and `CAPS=4,d`): (1) the four pages D
did not trap are removed from A and B too (`DROP4=1` for the pair A, B); (2) windows are cut at
console lines, not at times, because the three captures run at different speeds; (3) a segment
counts as identical in all three when A's segment is identical to its partner in B and to its
partner in D. "Invariant" now means identical in every capture that contains the thing: three
for most statements, A and B only for what lies on the four untrapped pages, D only for E6.

| Comparison | In all three | A-B | A-D | B-D |
|---|---|---|---|---|
| E5 quiesce, 33 actions before the interrupt controller: ordered writes identical | **33 (253 writes)** | 33 | 33 | 33 |
| the same, identical access for access | 30 | 30 | 30 | - |
| E3 sleep actions, 42: ordered writes identical | 36 | 36 | 38 | 38 |
| E3 sleep actions: identical access for access | 33 | 34 | 35 | - |
| W1 active actions, 57: ordered writes identical | 52 (1,894 of A's 3,079 writes) | 53 | 53 | 52 |
| W1 active actions: identical access for access | 39 | 41 | 44 | - |
| W3 wake actions, 30: ordered writes identical | 21 | 25 | 21 | 20 |
| W3 wake actions: identical access for access | 0 | 22 | 0 | - |
| Memory-controller shutdown, 135 writes | identical | | | |
| Pages written, E1 (console "awdl0 disable" to "_sleeping=1"): ordered writes identical / pages written | - | 18 / 42 | 15 / 43 | 14 / 41 |
| Pages written, E2 (to "IOCPUSleepKernel enter") | - | 30 / 49 | 32 / 49 | 31 / 47 |
| Pages written, E3-E5 (to the interrupt-controller action) | - | 56 / 68 | 56 / 68 | 60 / 68 |
| Pages written, W1 (to the first wake action) | - | 76 / 94 | 74 / 94 | 75 / 95 |
| Pages written, W3 (to "IOCPUSleepKernel exit") | - | 21 / 41 | 21 / 41 | 21 / 40 |
| Pages written, W4 (to "system wake events") | - | 23 / 65 | 19 / 66 | 29 / 66 |
| Domain writes in the entry without bus cycles (33) | same set and values; order differs in D (display pairs) | identical | | |
| Domain writes, wake to kernel exit, without bus cycles (159) | identical except DCS2-DCS5 values | | | |
| Last value of words written in the entry (words in both / equal) | - | 593 / 527 | 593 / 505 | 593 / 504 |
| "pre-full" snapshot, 792 words | 775 equal | 777 | 780 | 777 |
| "wake" snapshot, 264 words | 255 equal | 261 | 256 | 257 |
| Mailboxes E2 to T: `dcp`, `dcpext`, `gfx-asc` | identical sequences in all three | | | |
| Mailboxes E2 to T: `pmp` | received identical; sent: A = B; D has the same seven words with two (`..540001`, `..550001`) in the other order | | | |
| Mailboxes W to kernel exit: `pmp`, `sio` | identical sequences in all three | | | |
| System registers at the wake, per core | identical in all three (CTRR bounds aside) | | | |
| Order of core starts at the wake | 7, 6, 3, 2, 5, 1, 4 in all three | | | |
| Wake status words | identical in all three | | | |
| Requirement values (`reqcheck.py`, 71 checks x 3 captures) | no failure; 2 words not visible in D, 2 not in A and B | | | |

Changes to the classification of 7.3:
- **Now resting on three captures and identical in all:** everything listed there as identical
  for E5 (items 1-9), E3's table, the display and graphics mailbox sequences, the three `smc`
  key writes, W1 items 0, 1, 3, 5, 6, 7, 9, 10, section 6.3, the wake status, the PMP
  save and write-back, the 135 memory-controller writes, the core start order.
- **Resting on A and B only (D cannot see):** I1; the cluster words on `0x210e20000` and
  `0x211e20000` in E5-8d and W1-2f.
- **Resting on D only:** E6 steps 1b-5; all absolute times; the timing of guarded words and of
  core stops and starts.
- **No longer "identical":** the number of polls of `0x200001c04` (39, 39, 64) and of
  `0x23b718004`; the order in which the two display pairs are turned on again in E2 (D
  differs); one value written in W1-4; W3 access for access (D has other cores running).
- **Wake kind:** B and D (key press) agree with each other in W4 and W5 and differ from A
  (alarm).

### 7.5 Five captures

Method as in 7.4, extended (`five.py`; `phases.py` and the pairwise scripts run with `CAPS=3,e`,
`3,f`, `d,e`, `d,f`, `e,f`): a segment is identical in all five when A's segment is identical to
its partner in each of B, D, E, F; for what only the detached captures contain (the last steps)
D is the reference and E, F are compared with it. A statement is invariant only if every capture
that contains it agrees.

| Comparison (ordered writes identical unless said) | All five | A-B | A-D | A-E | A-F |
|---|---|---|---|---|---|
| E5 quiesce, 33 actions before the interrupt controller | **33 (253 writes)** | 33 | 33 | 33 | 33 |
| the same, identical access for access | 30 | 30 | 30 | 30 | 30 |
| E3 sleep actions, 42 | 35 | 36 | 38 | 38 | 36 |
| W1 active actions, 57 | 52 (1,894 of A's 3,079 writes) | 53 | 53 | 52 | 53 |
| W3 wake actions, 30 | 20 | 25 | 21 | 22 | 20 |

| Detached captures only (reference D) | D, E, F | D-E | D-F | E-F |
|---|---|---|---|---|
| E5 and E6 quiesce, all 36 actions | 34 (292 of D's 313 writes); the 2 others are the power-chip actions (alarm value in E, order in F) | 35 | 34 | - |
| Interrupt-controller action of E6 (963 reads, 39 writes) | identical access for access | yes | yes | - |
| E3 sleep actions, 42 | 35 | 39 | 35 | - |
| W1 active actions, 57 | 53 | 53 | 54 | - |
| W3 wake actions, 30 | 26 | 26 | 26 | - |
| Pages written, display request to "_sleeping=1" (identical / written) | - | 10 / 36 | 15 / 36 | 11 / 36 |
| Pages written, E2 | - | 26 / 47 | 31 / 49 | 27 / 48 |
| Pages written, E3 to the power-down | - | 56 / 68 | 56 / 68 | 59 / 68 |
| Pages written, W1 | - | 76 / 93 | 74 / 93 | 74 / 92 |
| Pages written, W3 | - | 24 / 39 | 23 / 42 | 24 / 42 |
| Pages written, W4 | - | 26 / 65 | 24 / 65 | 27 / 64 |
| Last value of words written, display request to T (in both / equal) | - | 631 / 541 | 631 / 555 | 631 / 543 |
| "pre-full" snapshot, 792 words | 777 (all five: 772) | 779 | 780 | 778 |
| "wake" snapshot, 264 words | 259 (all five: 253) | 262 | 259 | 260 |

Identical in all five captures: the 135 memory-controller writes; the wake status words; the
order of core stops (4, 1, 5, 2, 3, 6, 7) and of core starts at the wake (7, 6, 3, 2, 5, 1, 4); the system-register writes
of 6.3; the `dcpext` and `gfx-asc` mailbox sequences of E2; the three `smc` key writes of the
entry and `MBSE`="waka" at the wake; the requirement values (`reqcheck.py`: 71 checks on each
capture, no failure; 2 words not visible in D, E, F and 2 not in A, B).
Changes to the classification:
- **E6 now rests on three captures (D, E, F)** and is identical in them except the alarm value
  and the order of the two power-chip actions (F).
- **Not invariant after all:** the order of the two power-chip quiesce actions; the order in
  which the display pairs are turned on again in E2 (A, B, E one way, D the other); the set of
  domains written (F adds FPWM1) and the values the power manager writes back at the wake (they
  follow the state before the sleep); the place of `dcp`'s single endpoint-4 exchange (section
  10).
- The cluster words on the untrapped pages and I1 still rest on A and B only.

### 7.6 Six captures

`five.py` now takes G as well (pairs `3,g` and `d,g`). Ordered writes identical unless said:

| Comparison | All six | A-B | A-D | A-E | A-F | A-G |
|---|---|---|---|---|---|---|
| E5 quiesce, 33 actions before the interrupt controller | **33 (253 writes)** | 33 | 33 | 33 | 33 | 33 |
| the same, identical access for access | 30 | 30 | 30 | 30 | 30 | 30 |
| E3 sleep actions, 42 | 34 | 36 | 38 | 38 | 36 | 36 |
| W1 active actions, 57 | 52 | 53 | 53 | 52 | 53 | 53 |
| W3 wake actions, 30 | 20 | 25 | 21 | 22 | 20 | 21 |

| Detached captures (reference D) | D, E, F, G | D-E | D-F | D-G |
|---|---|---|---|---|
| E5 and E6, all 36 quiesce actions | 34 (292 of D's 313 writes) | 35 | 34 | 34 |
| interrupt-controller action of E6 | identical access for access | yes | yes | yes |
| E3 sleep actions, 42 | 34 | 39 | 35 | 38 |
| W1 active actions, 57 | 53 | 53 | 54 | 54 |
| W3 wake actions, 30 | 24 | 26 | 26 | 24 |
| Pages written E1 / E2 / E3-to-power-down (identical of written), D-G | - | | | 8 of 37 / 27 of 49 / 59 of 68 |
| Pages written W1 / W3 / W4, D-G | - | | | 72 of 93 / 22 of 42 / 18 of 66 |
| Last value of words written, display request to T, D-G | - | | | 619 in both, 537 equal |
| "pre-full" snapshot, 792 words | 772 (all six: 768) | | | 776 |
| "wake" snapshot, 264 words | 258 (all six: 252) | | | 258 |

Identical in all six: the 135 memory-controller writes; the wake status; core stop order and
core start order; the system-register writes after the wake; the `smc` key writes; all 71
requirement values (`reqcheck.py`; 2 words invisible in D-G, 2 in A, B).
Resting on G alone: section 4.1 and E7. Resting on two alarm wakes (A, G) against four key
wakes: W4/W5. The order of the two power-chip actions is now 2 (D, E) against 2 (F, G).

### 7.7 Seven captures (H added this round)

`phases.py` with `CAPS=d,h`, `g,h`, `3,h`; `seven_h.py`; `reqcheck.py` (now over A-H);
`commit_gh.py`. Ordered writes identical unless said:

| Comparison | H-D | H-G | H-A |
|---|---|---|---|
| E3 sleep actions, 42 | 39 | 37 | 38 |
| E5 and E6 quiesce actions (36; 34 against A, whose log ends early) | 34 (the two power-chip actions) | 35 (the alarm bytes) | 33 |
| W1 active actions, 57 | 54 | 54 | 53 |
| W3 wake actions, 30 | 24 | 26 | 20 |
| Requirement values (`reqcheck.py`, 71) | 69 pass in H, 2 not visible (untrapped pages), 0 fail | | |
| Commit snapshot, 792 words | | 774 equal | |
| Wake snapshot, 264 words | | 259 equal (`ps_dcs2`-`5`, `0x23d240000` differ) | |

Identical in all seven: the 135 memory-controller writes; the wake status words; the core stop
order 4, 1, 5, 2, 3, 6, 7 and start order 7, 6, 3, 2, 5, 1, 4; the `smc` key writes; the four
sub-blocks of R22a with their status values; the six words of R21; the read-before-write values
of R19; the wait of R30 ending on `0x2f`; the start of the `sio` and `pmp` wake actions (R5w);
the system-register writes after the wake (6.3; H not re-checked register by register, its
684 records have the same count as G's). The order of the two power-chip quiesce actions is
now 2 (D, E) against 3 (F, G, H). Resting on G and H: section 4.1a, 4.2a, E7.

### 7.8 Eight captures (I added this round)

`phases.py` with `CAPS=h,i`; `reqcheck.py` (A-I); `gaps_gh.py` (A-I, output `gaps-ghi.txt`);
`commit_ghi.py`. I against H: before the sleep 75 of 79 console segments with identical ordered
writes, after the wake 82 of 89 (1.7b); `reqcheck.py` 69 pass, 2 not visible, 0 fail; commit
snapshot 768 of 792 equal to H's (834 of 858), 774 of 792 to G's; wake snapshot 262 of 264
equal to G's. Identical in all eight, as far as each shows: everything listed in 7.7, with these
ranges now: the poll of `0x23b718004` at the wake reads `0x1f` 154 to 246 times (I: 246) and
ends on `0x2f`; the memory-controller wait `0x200001c04` takes 65 reads in I, starting
`0x4200`, ending `0x4000`, `0x2400`, `0x800`, 0, 0; the sub-block status values of R22a (I: 9,
1, 3, 2 reads); R21's six words; R36w's rule for all 991 words; the read-before-write values of
R19; R43's four system-register accesses on every core with the same values (315 records before
the wake); the +`0x8114`/+`0x44` start of `sio`'s and `pmp`'s wake actions; `0x2000e1004`
written 0 then `0x4000000` at the wake (D-I). The order of the two power-chip quiesce actions:
2 (D, E) against 4 (F, G, H, I). Alarm bytes macOS wrote in I: `f0 4c 09 00`.

## 8. Requirements

Form: what macOS was observed to have done before the SoC went down, or after it came up.
Marks: **[BOTH]** observed as stated in every capture that can show it: all three (A, B, D)
unless the entry says otherwise, and since section 7.5 all five (A, B, D, E, F); **[D]** observed
in the detached captures only, because only they reach that point: D, E, F and G agree unless
the entry says otherwise (since the round of capture H D-H, and since this round D-I);
**[G]** observed in the captures with a commit snapshot and the system registers before the
wake: G, and H and I where the entry says so; **[VARIES]** the captures that show it disagree, and the values seen are given; **[UNKNOWN]** observed, cause or necessity not known, or observed incompletely;
**[ARTEFACT]** hypervisor artefact, not a requirement; *(round 8)* **[ARTEFACT, in every
power-down]** an act of the instrument, not of macOS, that was present in every power-down
captured, so that no capture shows the power-down without it; **[J]** observed in capture J
only; *(round 9)* **[K]** observed in capture K only; **[HV-CHANGED]** resting on a run in which
a change of the instrument's altered the outcome (section 0): a record of the machine under the
instrument's influence, not of macOS, and never a step macOS takes; *(round 10)* **[L]**
observed in the three round-10 captures L, `det19b` and `det21` (what macOS did up to each core's
final write; in `det19b` and `det21` the instrument's change acts only after it); *(round 11)*
where an [L] entry says "L-`det24`" or "five captures" it holds in `det23` and `det24` too, for
what macOS did up to each core's final write (their commit value of `0x23b71c000` and their
outcome are [HV-CHANGED]). Section 8.1 restates the requirements since round 6 as statements a
test can check, each with how firmly it rests. Every [BOTH] entry with a register value
was re-checked against all three captures by `reqcheck.py` (no failure). No requirement is claimed to be necessary for sleep to work: each records only
that macOS does it. Evidence gives the section and the output file.

Before the SoC goes down:

- **R1 [BOTH]** The internal display coprocessor has been shut down and domains DISP0_CPU0,
  DISP0_FE, RMX set off, in that order, about 10 s before T, ahead of every step below (E1-3,
  E1-4;
  `ps-pre-N.tsv`, `mbox-pre-N.txt`).
- **R2 [BOTH]** The memory-controller burst of I5 has stopped: none occurs after the display
  goes off (E1-2; last `0x200014050` write at T-10.417 / T-10.407 / T-7.439, each within 0.1 s
  of the "ON to OFF" console line; `idle_seq.py`, `det_misc.py`).
- **R3 [BOTH]** `smc` has been told, in this order: key `MBSE`=`0x736c7077` ("slpw"), key `WKTP`=2, key
  `MBSE`="slpa" (reply result 0), then management "AP power `0x201`", echoed; no `smc` message
  follows (E2, E3; `smcw.py`, `mbox-pre-N.txt`).
- **R4 [BOTH]** Each of `gfx-asc`, `dcpext`, `dcp`, `ans`, `sio`, `pmp` has received "AP power
  `0x201`" (echoed) then "coprocessor power `0x201`" (acknowledged) as its last management
  exchange; `aop` and `smc` have received "AP power `0x201`" only (E2, E3; `mbox-pre-N.txt`).
- **R5 [BOTH]** For `sio` and `pmp`, after R4: bit 0 of the mailbox control word +`0x8114` is
  cleared and the coprocessor's word +`0x44` is written 0 (was `0x10`) (E3). *(Changed this
  round.)* In all seven captures, in this order: +`0x8114` read (it reads in the bit-17 form,
  section 0: `0x22201` for `pmp` in all seven; `0x24401`, `0x28801`, `0x20001` for `sio`,
  varying), +`0x8114` written with **the value read, bit 0 cleared**; +`0x48` read (`0x2e` in
  all seven); +`0x44` read (`0x10`); +`0x44` written 0. The written +`0x8114` value is a rule
  on the value read, not a constant. What +`0x8114`, +`0x48`, +`0x44` read for a coprocessor
  that is not running or does not answer is **not observed** (macOS never met one; gaps F3, F6).
  *(This round, gap Q11.)* +`0x48` is read once, `0x2e` in every instance of all eight
  captures, and +`0x44` is written 0 straight after; whether macOS would wait for, or act on,
  another value is not observed (one value only was ever read).
  **R5a [D]** *(new, gaps Q1, Q11)* `dcp`, `dcpext`, `gfx-asc` and `ans` are stopped the same
  way, each straight after its "coprocessor power `0x201`" acknowledgement and before its
  domains are written off: +`0x8114` written with the value read, bit 0 cleared; +`0x48` read
  (`0x2e`); +`0x44` read (`0x10`); +`0x44` written 0 (E2a; D-I, 30 instances, no exception).
  For `dcp` and `dcpext` the "AP power `0x201`" exchange is followed by an endpoint stop
  (`0x00a4..`, answered `0x0087..`) on each of endpoints `0x20`-`0x2c` before "coprocessor
  power `0x201`". `dcp`'s E1 stop is preceded by endpoint-`0x37`/`0x02` traffic whose payloads
  are not in the log `[UNKNOWN]`; `dart-dcp` +`0xfc` is written `0x7ffe` twice after the
  stop. When `dcp` and `dcpext` are restarted in E2 (after their domains are on): +`0x8114`
  written `0x20001`, +`0x44` read 0, written `0x10`.
  *(Changed round 7, gaps W6, W7; E2a; all eight captures, 76 stops.)* The exchange is exactly:
  sent `0x00b0000000000201` / received `0x00b0000000000201` (endpoint 0); for `dcp` and
  `dcpext` sent `0x00a4000000000000` on endpoint `0x20`, `0x21`, ..., `0x2c` in ascending order,
  each answered `0x0087000000000000` on that endpoint before the next is sent; sent
  `0x0060000000000201` / received `0x0070000000000201` (endpoint 0); then the register stop.
  Mailbox words 64 bits, +`0x44`/+`0x48`/+`0x8114` 32 bits. The +`0x8114` read has bit 0 set
  and the write is that value with bit 0 cleared (E2a gives both). In every instance the
  endpoints stopped had been started by macOS (E2a). **Translators**: after **every** stop of
  `dcp` (E1, E2, wake) `dart-dcp` +`0xfc`, and after every stop of `dcpext` `dart-dcpext` +`0xfc`,
  are written for s = 0 then 15 the last value read from +`0xfc` with bit s cleared, each after
  a read of +`0x100`+4s and of +`0xfc` (`0x7fff` -> `0x7ffe`, `0x7ffe`); in E1 only, before
  `dcp`'s "AP power `0x201`", `dart-disp0` +`0xfc` the same for s = 0, 4, 15 (`0x7ffe`, `0x7fee`,
  `0x7fee`); at every restart, before +`0x8114` = `0x20001`: the translator's +`0xfc` =
  `0x7fff`, +`0x34` = `0xffffffff`, +`0x20` = `0x100000` (E2a item 3; 105 +`0xfc` writes, no
  exception). (The previous wording, "`dcp`'s second stop in E2 has neither", is withdrawn.)
  **R5w [BOTH]** *(new)* At the wake, in each of `sio`'s and `pmp`'s wake actions, in all seven:
  +`0x8114` reads `0x20001` and is written `0x20001`; +`0x44` reads **0** and is written `0x10`;
  the next read of +`0x8114` is `0x100101` and the coprocessor's first message (`0x00100000000c000c`)
  is read (W3). So after a sleep both coprocessors read +`0x44` = 0 before macOS starts them.
- **R6 [BOTH]** The 196,608 bytes at `0x23b52c000`-`0x23b55bffc` have been read word by word in
  address order after `pmp` was stopped (E3). **R6w [BOTH]** After the wake the same range is
  written back before `pmp` is started (W3): *(changed this round, gap S8)* every one of the
  49,152 words is written once with the value read from it in E3 (D, G, H checked word by
  word), as the first writes of `pmp`'s wake action, followed by the ten translator writes of
  R55.
  *(Round 15; 1.7h, R74.)* In det33 (det18, det23 the same steps) they follow core 0's
  active-action writes of PMP, PMS_SRAM, PMS and of the twelve words at `0x23b549000`+ (W1-2h),
  and every byte written equals the byte R6 read (196,608 of 196,608).
  *(Round 15c, gap G26; D3 (b).)* For Linux, R5, the translator writes of R73, R6, and at the wake
  R6w, R55 and R5w are made for a `pmp` (and R5, R5w for a `sio`) **that the same entry stopped**:
  macOS made them only after its own stop of a coprocessor it found running (every capture), and a
  coprocessor found already stopped is D3 (b)'s. Which of the logic and the `pmp` client makes them
  is D9 (b).
- **R7 [BOTH]** Domains GFX, DISPEXT_CPU0, DISPEXT_FE, DISP0_CPU0, DISP0_FE, RMX, APCIE_ST have
  been written to their off values of section 4, each after its coprocessor's R4 exchange (E2).
  *(This round.)* Each after its coprocessor's R5a stop, by the forms of R56.
- **R8 [BOTH]** `W` +`0x338` = 1 on each SPMI controller (`0x23d0d9338`, `0x23d0e1338`,
  `0x24a829338`) (E3). **R8w [BOTH]** restored to the earlier value at the wake (W3).
- **R9 [UNKNOWN]** Power-chip register `0x9f01` has been written `0x50` (E3); at the wake it is
  written `0x00` (W3). Meaning not known; label "boot stage" is the decoding tool's. *(Place
  added this round, gap S5.)* The write falls between the console lines of the watchdog's sleep
  action and the first power-chip sleep action, after the watchdog's two words (D: T-0.468, G:
  T-0.458, H: T-0.462), before the SPMI controllers' R8 and before any write of `0x23d0d9338`.
  Which driver issues it is not established.
- **R10 [BOTH]** The address translators of PCIe port 0 and of `sio` have had +`0xfc` stepped to
  0 (E3).
- **R11 [BOTH]** Cores 1-7 have written their stop bit to `0x23b754000` before any quiesce action
  runs; from then on only core 0 touches devices (E4, E5). In D the stop bits are written
  T-0.0893 to T-0.0889 and the cores enter their final sleep path only at the end (R39).
- **R12 [BOTH]** Each temperature sensor has had +`0x4` written `0xffffffff` and its control word
  written with bit 24 then bit 25 set (E5-1). Order among sensors not fixed. *(Changed this
  round, gap S7.)* The control word is +`0x8` for fourteen sensors and +`0x10` for
  `0x23b2c4000`, `0x23b2c8000`, `0x23b2cc000`; each write is the value just read with bit 24
  set, then the value read back after it with bit 24 replaced by bit 25 (E5-1).
  *(This round, gap Q15.)* The two "MTRTempSensor" actions touch only `0x23b2e0000`: four reads
  (0), `W` `0xffffffff`, read (0), `W` `0x1000000`, read (0), `W` `0x2000000`; at the wake
  `W` 0 twice, read, `W` `0x1000000`, read, `W` `0x2000000`, `W` 0 twice. The word reads 0 at
  every read in D-I, so "the value read with bit 24 set" and the constant `0x1000000` cannot
  be told apart there.
- **R13 [BOTH]** `0x24a820900`, `0x24a820904`, `0x23d1f0900` have been written `0xffffffff`
  (E5-2).
- **R14 [BOTH]** The 17 PCIe writes of E5-3 have been made in that order.
- **R15 [UNKNOWN]** `0x23d2b8008`, `0x23d2b800c`, `0x23d2b000c` have been written 0, and earlier
  `0x23d2b0000`, `0x23d2b0010` (E3, E5-4). Both captures agree, but the boot argument `wdt=-1`
  and the hypervisor's own use of this watchdog (A1, A9) may have changed what macOS does here.
  *(Round 9, K.)* The same writes (`0x23d2b0000`, `0x23d2b0010` at T-0.4542; the three others
  at T-0.0357 to T-0.0356, with `0x23d2b800c` read 0 before its write) and no other write to the
  page before T; macOS writes nothing to watchdog 2, which is nonetheless armed at the commit
  (R62).
- **R16 [BOTH]** Memory controller, in this order: pulse (`0x20010000c`=1, `0x200100014`=1)
  around `W 0x200001c00`=0, pulse released; `0x200001c04` polled until it reads 0 (39, 39, 64
  polls; *changed this round, gap V8:* in all seven it starts at `0x41e0` or `0x4200`, falls
  and ends on 0, the last non-zero values varying, E5-5b; it reads `0x200` before the pulse;
  I: 65 reads, `0x4200` first, `0x4000`, `0x2400`, `0x800` last before 0);
  then
  `0x200158000`, `0x200024000`, `0x200024008` cleared bit by bit to 0; `0x200200584` cleared bit
  by bit to 0; zeros to `0x200027000`, `0x200067000`, `0x2000a7000` (E5-5).
- **R17 [BOTH]** After R16: `0x200155000`=0; P+`0x21008`=0 then P+`0x21000`=0 for the four
  planes in ascending order; DCSn+`0x7a0`=0 for n = 0..7 in ascending order (E5-6).
- **R18 [BOTH]** After R17: clock muxes `0x23b040140`, `144`, `148`, `14c`, `154` written
  `0x80100000` (E5-8a). The written value is not what reads back, then or after the wake.
- **R19 [BOTH]** `0x23b734000`, `0x23b77c000`, `0x23b778000` written 0, then the timer and
  cluster state read out (E5-8b/c/d); `0x210e20660`, `0x211e20660`, `0x210e48080`,
  `0x211e48080` written 0. **R19w [BOTH]** all written back at the wake (W1-2e/f). The words
  `0x210e20660`, `0x211e20660` and the cluster reads at `0x210e20400`.., `0x211e20400`.. rest on
  A and B only (untrapped in D-H). *(Changed this round, gap V11.)* Each of these words, and
  `0x23b718000`/`004` of R22 and the four sub-block words of R22a, is read before it is written
  0, and the value written at the wake equals the value that read returned, in every capture
  that logs the word (`gaps_gh.py`, block V11): `0x23b718000`, `004`: read `0xf`, written back
  `0xf` (all seven); `0x23b734000`, `0x23b77c000`, `0x23b778000`: 1, 1 (all seven);
  `0x210e48080`, `0x211e48080`: `0xa000000000000000` (all seven); `0x210e20660`, `0x211e20660`:
  `0x1000000015` (A, B); `0x23b748000`/`400`/`800`/`c00`: 1, 1 (all seven). No capture shows
  any of them read with another value, so a capture cannot tell "written back what was read"
  from "written a fixed value".
- **R20 [BOTH]** On `0x68c008000`, `0x234008000`, `0x279008000`: +`0x14`=1, then +`0x2bc`=1, 2,
  4 (E5-8f).
- **R21 [BOTH]** Bit 63 cleared in `0x210e40250`, `0x211e40250`, `0x210e48400`, `0x211e48400`
  (E5-8g); set again at the wake (W1-2h). *(Changed this round, gap V10.)* In all seven: each of
  the four is read (`0x8001b20026f02400`, `0x8001b2005df05200`, `0x8003b20026f02400`,
  `0x8001b2005df05200`), written with bit 63 cleared; **after the wake its first read returns
  the value last written before the sleep** (bit 63 clear), and it is then written that value
  with bit 63 set, which equals the value read before the sleep. `0x210e40240` (`0x2000026f00000`)
  and `0x211e40240` (`0x100005df00000`) are read and rewritten unchanged before the sleep, and
  after the wake read and rewritten with the same value. So these six words kept their value
  through every sleep captured (1.6 s to 900 s).
- **R22 [BOTH]** The four sub-blocks of R22a are stopped as R22a states; then `0x23b718000`,
  `0x23b718004` = 0 (E5-8h/i). *(Round 10, [L].)* Watchdog 2's count starts 1.3-7.1
  microseconds (±10) after the record of the write `0x23b718004` = 0, and before the first
  write of `0x23d2c4000` (R62). *(Round 11: 7.5 and 3.2 microseconds in `det23`, `det24`; five
  captures, 1.3-7.5.)* *(Changed this round, gap V6: the literal "`0x23b7487e0` polled
  until it reads `0x494900`" is withdrawn; the wait ends on the low byte, R22a.)*
  **R22a [BOTH]** The four sub-blocks, in the order `0x23b748400`, `0x23b748800`, `0x23b748c00`,
  `0x23b748000`: the control word is read (`1` in every capture), written 0, and then the
  sub-block's status word `0x3e0` above it (`0x23b7487e0`, `0x23b748be0`, `0x23b748fe0`,
  `0x23b7483e0`) is read until its low byte is 0. Values in all seven captures (`gaps_gh.py`,
  block V4/V5; source also `phases-pre-<cap>.tsv`): `0x23b7487e0` `0x494002` 6 to 9 times, then
  `0x494900`; `0x23b748be0` `0` at the first read; `0x23b748fe0` `0x494002` 2 or 3 times, then
  `0x494900`; `0x23b7483e0` `0x514d02` 1 or 2 times, then `0x515100`. *(Changed this round,
  gaps V1, V4, V5, V12.)* What is and is not observed:
  - the low byte was only ever seen as `0x02` (while waiting) or `0x00` (done);
  - in each value the second and third bytes are equal when done and differ while waiting
    (`0x40`/`0x49`, `0x4d`/`0x51`); `0x23b748be0` reads 0 in all bytes;
  - **a status word is never read while its sub-block is on**: in every capture the first read
    of each status word comes after the write of 0 to its control word, no snapshot contains the
    status words, and they are not read at the wake (gap V4: not observed);
  - **at the wake the four control words read 0** before macOS writes them 1 (all seven; W1-2h):
    so "written 1 at the wake" is not "written back what was read at the wake";
  - what a write of 0 does to a sub-block that is already 0, and what the entry does when a
    control word reads 0, are **not observed** (macOS always found 1). Under Linux the four read
    0 (section 12, L3);
  - what the sub-blocks are is not established (no device-tree table names `0x23b748000`,
    section 1.9).
  - *(This round, capture I; supersedes the third point.)* **With the sub-blocks on** (macOS
    awake) the status words read `0x23b7483e0` `0x4d4d01`, `0x23b7487e0` `0x404001`,
    `0x23b748be0` `0x1`, `0x23b748fe0` `0x404001` (one reading, I's "awake-extra"); at the
    commit `0x515100`, `0x494900`, `0`, `0x494900` (I). Low byte 1 on, 2 waiting, 0 done (4.1b).

- **R23 [BOTH]** SIO_CPU `0x23b7001d0` written with bit 28 cleared (E5-8j). **R23a [ARTEFACT]**
  The same for SIO and SIO_BUSIF is seen only through the hypervisor's guard (A3); D gives the
  order and times: SIO, SIO_BUSIF, SIO_CPU, within 15 microseconds, immediately before R24.
- **R24 [BOTH]** `0x23d2c4000` written 1 as the last write of the power manager's quiesce
  action; macOS's console calls it "Starting S2R timer" (E5-8k). It is written twice more
  (R37, R38). *(Round 8.)* macOS never reads the word in any log; with macOS awake, before the
  entry, it reads 1 (the instrument's arm-time line, eight runs: A, D, E, F, G, H, I, J; 1.7c).
  Its value under Linux before the entry is not read (open question 56).
  *(Round 9, K.)* **It reads 0 at the commit** (after the three writes of 1, the last at
  T-0.00066; no write of 0 logged), and its bit 0 stays clear for 4.9 s after the commit with a
  core kept running (`det16`, [HV-CHANGED]). Watchdog 2 starts counting within about 0.3 ms of
  the first of the three writes (R62).
  *(Round 10, [L].)* Read inside each write: 1 just before the first write of 1, **0 just after
  it**, and 0 before and after the second and third (4.1c). Watchdog 2 is armed before the first
  write (R62). *(Round 11.)* The same in `det23`, `det24` (five captures); 0 at all five commits.
- **R25 [BOTH]** Apart from R1, R7, R23 and the per-transfer cycles of I2C0, I2C3, SPI2, SPI3,
  macOS writes no power-domain control word during the entry (section 3, last part): to the
  end of the log in A and B, to the real power-down in D.
- **R26 [BOTH] (was UNKNOWN; superseded by R36-R39)** After R24 macOS reads the interrupt
  controller's words from `0x23b103000` upward. A and B show the first 408 and 372 reads and
  then stop (A11); D shows the rest.
- **R36 [D]** Interrupt controller, in this order: 896 words `0x23b103000`-`0x23b103dfc` read;
  for k = 0..27 `0x23b104180`+4k read and `0x23b104100`+4k written `0xffffffff`; for k = 0..10
  `0x23b105028`+`0x80`k read, `0x23b105024`+`0x80`k written `0x80000001`, `0x23b105004`+`0x80`k
  read; 16 words `0x23b106000`+`0x10`k read; `0x23b100010` read (E6-1). The first 408 / 372
  reads are also in A / B. **R36w [BOTH]** At the wake 991 words are written back (R29).
  *(Changed this round, gap V3.)* The value of each is given by the entry's reads, in D-H
  without exception (E6-1): 913 words the value read from the same word; `0x23b104100`+4k the
  value read from `0x23b104180`+4k; `0x23b104180`+4k and `0x23b105028`+`0x80`k the bitwise
  inverse of the value read from the same word; `0x23b105024`+`0x80`k `0x80000001`.
  *(Round 9, K.)* At each core's final write, every core reads the 28 words `0x23b104180`+4k
  `0xffffffff`, `0x23b102024` `0x80000001`, the 28 words `0x23b104000`+4k 0, the 11 words
  `0x23b105028`+`0x80`k `0x80000001` and `0x23b105004`+`0x80`k 0 (E7, round-9 part); by the
  Asahi page's names every interrupt of the controller and both IPI kinds are masked and none is
  software-generated (documentation).
- **R37 [D]** Then `0x23d2c4000` is written 1 a second time, with no other register access, in
  the first power-chip quiesce action (E6-2). The console text of this step is in all three.
- **R38 [D]** Then, in the second power-chip quiesce action, four SPMI commands to the power
  chip in this order: read `0xd00c` (1 byte); write `0xd008` (4 bytes); write `0xd00e` = `00`;
  write `0xd000` = `41`; each with `0x23d0d9338` written 0 before and 1 after and
  `0x23d0d9378` written 1 after the command; then `0x23d2c4000` written 1 a third time (E6-3).
  The meaning of the registers is the decoding tool's label. The console text is in all five.
  D and E as stated; in F the commands and the second write of `0x23d2c4000` (R37) come in the
  first action and the third write alone in the second; G is like F. The four alarm bytes
  differ each time. *(Round 8.)* J is like F and G (E6; alarm `3a 8a 09 00`).
- **R39 [D]** After R38 macOS makes no further device-register write (11 writes to SMC shared
  memory, console bytes and one console-port read are all that follow), sends the power chip
  nothing else, and all eight cores enter their final sleep path within 31 microseconds, cores
  1-7 first, core 0 last (E6-4, E6-5). How a core enters it is the hypervisor's record `[A4]`;
  the registers it writes are not visible.
- **R27 [ARTEFACT]** The power chip's alarm at now + 900 s (capture A; it replaced the alarm
  macOS had just set itself, R38), the scratch bytes
  `0x9f0a`.., the write of 1 to `0x23d0d9378` after macOS's last SPMI access, and the final
  values of the guarded words are the hypervisor's (A3, A6). Not requirements. *(Changed round
  8.)* The instrument's whole commit path is now written out in A6 from its code: per core, the
  timers and pending virtual interrupts (R59); on the last core, its USB and UART stop, the held
  words, its SPMI notes and alarm, the write of `0x23d0d9378` = 1 (R60) and, in J, watchdog 1
  (R61). Each is an artefact; each was present in every observed power-down, so none of them is
  known to be unnecessary.

After the SoC comes up, before macOS is back at idle:

- **R28 [BOTH]** Core 0's first device writes: `0x210055008`=`0xffbfffffffffffff`,
  `0x210055000`=1, `0x210e49008`=`0xff5fffffffffffff`, `0x210e49000`=1; every other core
  writes the first pair on its own block when it starts (W1-0, W2). *(Changed this round, gap
  4.)* Core 7, the first performance core started, then also writes `0x211e49008` =
  `0xff5fffffffffffff`, `0x211e49000` = 1.
  **R28a [BOTH]** *(new, gap S1)* Before the start words of each core (R32), core 0 writes
  `0xc5acce55` to `0x21N30fb0` of that core, about 11 microseconds earlier (W2).
- **R29 [BOTH]** Then 991 interrupt-controller words are written before anything else (W1-1).
- **R30 [BOTH]** Then the power manager: `0x23b718000`/`004`=`0xf`; cluster tables; every
  domain of the table written to a target state; timer and cluster state back; DCSn+`0xdc4`,
  +`0xdbc`; `0x23b748000`/`400`/`800`/`c00`=1 (W1-2). Values of DCS2, DCS3, DCS5 differ.
  *(Changed this round, gaps V1, V7.)* Before its write `0x23b718000` reads `0xf` and
  `0x23b718004` reads 0; after `0x23b718004` = `0xf` it is read `0x1f` (154 to 243 times) until
  it reads `0x2f`, in all seven (W1-2a). The four sub-block words read 0 before they are
  written 1 (W1-2h). *(This round, gap Q8.)* I: `0x1f` 246 times, then `0x2f`; range now 154
  to 246. The word is read 0 before the write of `0xf`, then `0x1f` (bits 0-4), then `0x2f`
  (bits 0-3 and 5): bits 0-3 read back as written throughout, bit 4 is set while waiting and
  clear at the end, bit 5 set only at the end. **Which bits macOS tests to end the poll is not
  observed**: every poll ended on the same value, after the same one intermediate value. What
  the word reads on a chip that was not powered down (L8) is not observed under macOS
  (section 6.4).
  *(Round 10; all thirteen captures with a wake.)* After the poll, `0x23b71c000` is read (0)
  and written `0x80000000`, then `0x23b71c040` read (`0x80000000`) and written `0x80000000`
  (W1-2a), before any core is started (R32). R67. *(Round 11: all fifteen, `r11-checks.txt`
  part 3.)*
- **R31 [BOTH]** Then the memory controller is re-enabled: `W 0x200001c00`=`0x10` inside a
  pulse, `0x200001c04` read (`0x4200`), enables rebuilt (W1-3); then `0x200155000`=
  `0xff000000`, P+`0x21008`=`0x700`, P+`0x21000`=`0xfffffc3f`, DCSn+`0x7a0`=`0xc0000` (W1-4).
  *(Added this round, gap 9.)* Plane 3's `0x2000e1004` is first written `0x8000000` (A, B) or 0
  (D-H) `[VARIES]`, then `0x4000000`. *(Changed this round, gap Q10.)* In W1-4 each
  P+`0x21004` is read and **written the value just read** (A, B: plane 3 reads `0x8000000`;
  D-I: every plane reads 0). The later `0x4000000` is not part of W1-4: it is the clear of
  section 3 E0 (a read of `0x4000000` written back, then a read of 0), made whenever the bit is
  found set, before the sleep and after the wake, on any plane (all eight captures).
- **R32 [BOTH]** Cores are started only after all active actions, in the order 7, 6, 3, 2, 5,
  1, 4; the "wake actions" run after that (in D the first wake action follows the last core
  start by 1.5 ms); `pmp`, `sio` are booted inside their wake actions, `smc` receives "AP power `0x20`" and
  key `MBSE`="waka" (W2, W3).
- **R33 [BOTH]** macOS reads `0x23d00401c`-`0x23d00402c`; `0x23d004020` reads `0x400000` (section 5).
- **R34 [ARTEFACT]** The system-register values of 6.3 for CTRR and `ACC_CFG_EL1` did not reach
  the hardware (A5); the HID/EHID values are what macOS wrote. **R34a [D]** Each core
  writes the HID/EHID values of 6.3 before its first device access (core 0 within 0.45 ms of
  the wake record); A and B have the same values in the same order but no times.
- **R40 [UNKNOWN]** At the wake the power manager writes each domain back to the state it had
  before the sleep, not to a fixed table: in F, where FPWM1 had been set off (`0x3f0`) before
  the sleep, it is written `0x340` at the wake; in the other four it is turned on (`0x44`,
  `0x4f`, `0x1000004f`). One capture shows the off case (W1, section 3 last part; `ps-pre-f.tsv`,
  `ps-post-f.tsv`). *(This round, gap Q6e.)* Still one domain in one capture; I is a fifth
  capture with FPWM1 on before the sleep and turned on at the wake. Every other domain had the
  same state before the sleep in every capture (or varies by itself, the DCS words), so the
  captures cannot tell "back to the state before the sleep" from "a fixed table" for them.
- **R41 [BOTH] (D, E, F)** The alarm commands of R38, the stop of the cores and the whole of
  R1-R39 are the same with the cable out as with it in (section 10).
- **R42 [BOTH] (G against A, B, D, E, F)** R2-R39 hold unchanged when macOS goes to sleep by
  itself instead of on a click; only the first steps differ (audio path first, no input; R1's
  display shutdown follows 60 ms later) (section 3, "idle sleep"; `reqcheck.py`, `five.py`).
- **R43 [G]** Each core, immediately before it goes down, reads `ACC_OVRD_EL1`, writes
  `ACC_OVRD_EL1` = `0x1800101526076207` (it read `0x180010102001c207` before the first write),
  reads `CYC_OVRD_EL1` = `0x2000000` and writes `CYC_OVRD_EL1` = `0x3000001`; no other trapped
  system register is touched on any core in the 91 ms before (E7, burst 2). *(Changed this
  round: G and H, gap 12.)* H repeats it with the same values (316 records; no trapped access
  on any core between T-0.0897 and T-0.000026). Which value a core reads from `ACC_OVRD_EL1`
  follows the time of its read: a core whose read comes after another core's write reads
  `0x1800101526076207` (G: cores 3 and 0; H: core 0 only, all seven others having read before
  the first write); a core whose read comes before every write reads `0x180010102001c207`. No
  core read the old value after any core had written. Whether the register is shared between
  cores is not established. *(Round 8.)* J repeats it with the same values (315 records; cores 4,
  5, 1, 7, 6, 2, 3 read the old value, core 0 the new; 1.7c). Under Linux the values written to
  these two registers are in no record (4.4 row 3). *(Round 9.)* K repeats the values; read by
  each core at its final write, `ACC_OVRD_EL1` is `0x1800101526076207` and `CYC_OVRD_EL1`
  `0x2000000` on all eight, and the write is `0x3000001` from the same guest instruction on all
  eight (E7).
- **R44 [G]** All eight cores do R43 within 33 microseconds, after core 0's last device access
  of R39 for cores 3 and 0, core 0 last (E7). With D, E, F this timing is seen four times
  (their "sleep path" records), the registers once.
- **R45 [G]** When a core is told to stop (R11) it writes `PMC0_EL1`, `PMC1_EL1`, `PMCR1_EL1` =
  `0x3030303`, `PMCR0_EL1` = `0x7003403` then `0x7003400`, acknowledges `IPI_SR_EL1` = 1, writes
  `s3_5_c15_c10_1` = 0 and `IPI_RR_LOCAL_EL1` = 0, and then writes its stop bit; core 0 has sent
  it `IPI_RR_LOCAL_EL1` or `IPI_RR_GLOBAL_EL1` (E7, burst 1). `[ARTEFACT in part: the hypervisor
  carries out the IPI writes itself.]`
- **R46 [G]** At the commit the hardware holds, for the power-domain words: display and graphics
  domains off (`0x2300`, `0x0f040300`, `0x0f002300`, RMX `0x0f000300`); AIC, GPIO, SOC_DPE, the
  UART domains `0xff`; MCC, SBR, IMX, SMX `0x1f0000ff`; SIO_CPU `0x0f0002ff`; PMP `0x1f0f03ff`;
  ANS2 `0x1f0023ff`; SEP `0x1000230f`; the I2C, SPI, MCA domains `0x200`; DCS domains
  `0x1000030f` (six) or `0x1f0003ff` (two) (section 4.1 table). Which DCS domains read which
  value varies between captures at the wake, so the split six/two is not claimed as fixed.
  *(Changed this round: G and H.)* H agrees for every word named here except the DCS words
  `[VARIES]`: H has DCS4, DCS6, DCS7 `0x1000030f`, DCS0, DCS1, DCS5 `0x1f0003ff`, DCS2, DCS3
  `0x1400034f`. All 137 words at H's commit: section 4.2a. *(This round.)* I agrees with H for
  every word named here except DCS0, DCS1, DCS2, DCS3, DCS5 (all `0x1000030f` in I) `[VARIES]`.
- **R47 [G]** At the commit the 80 memory-controller and 448 DRAM-controller words of the
  snapshot list hold their idle values (section 4.1). *(Changed this round: G and H.)* In H as
  in G each of the 528 words equals its own awake ("pre-detach") value; between G and H nine of
  them differ (`MCC.plane0-3+0x680`/`684`, `DCS3+0x500`), in values that also vary at idle
  (4.1a). *(This round.)* I the same: each of the 528 equals its own awake value; against G and
  H they differ in `MCC.plane0-3+0x680`/`684` and `DCS1-7+0x500` (4.1b) `[VARIES]`; their values
  are written out in appendix B.
  *(Round 8.)* J the same: its 528 words equal I's except `MCC.plane0-3+0x680`/`684` and
  `DCS1-7+0x500`, words that vary (1.7c).
- **R51 [G] (G, H, I)** At the commit the words of the commit list read: for the 137 domain
  words the values of section 4.2a, for the other 725 the values of **appendix B** *(changed
  this round, gap Q5: the values are now in this document; `commit-state-ghi.tsv` has them per
  capture)*. G, H and I agree in 767 of G's 792 and vary in 25 (4.1b), H and I in 834 of 858;
  each varying word also takes those values with macOS awake, except `0x23b71c0f0` (R52).
  *(Round 8.)* J: 842 of its 862 words equal I's; the 767 of G's 792 that agree in G-I agree in J
  too; the 20 that differ from I are in the varying groups (1.7c). Every word of R52 and R53 has
  I's commit value in J.
  *(Previous wording:)* G's 792 agree with H's in 774 and vary in 18 (listed in 4.1a,
  `[VARIES]`). Of G's 792 words, 752 (H: 746) hold the value they had with macOS awake and were
  not written; the 18 macOS writes (19 in H's list) are those of R1, R7, R18, R23, R23a and the
  bus cycles of R25, and each reads at the commit what macOS last read from it, except SIO_CPU
  (written `0x0400024f`, commit `0x0f0002ff`), SIO (write held, commit `0x1f0002ff`) and
  APCIE_ST (read `0x0f000200`, commit `0x0f000300`) (4.1a item 2).
- **R52 [G] (G, H)** *(new)* Changed between macOS awake and the commit **with no logged write
  by any core**, identically in G and H: nine SoC clock words in bit 8, PMP (`0x1f0f03ff`),
  PMS_SRAM (`0x1f0003ff`), ANS2 (`0x1f0023ff`, already in E1), the power-gate word
  `0x23b71c0f0` (bit 30 cleared), `0x23b720030`, `034`, `044` (`0x01515151`, `0x01494949`,
  `0x01494949`), and the always-on clock words `0x23d240040`, `0x23d240314` (4.1a item 3).
  Further changes of this kind occur in one capture only, in words that vary at idle. What
  changes these words is not observed. `[UNKNOWN]` *(Changed this round, capture I, gap Q3.)*
  I repeats every change named here **except `0x23b71c0f0`**, which keeps `0xc0040307` at I's
  commit: it is withdrawn from this list and is `[VARIES]` (G, H `0x80040307`, I
  `0xc0040307`). **PMP and PMS_SRAM** read their commit values `0x1f0f03ff` / `0x1f0003ff` also
  with macOS awake, 18 s before I's detach, and `0x1000030f` again at the next two awake
  readings: they change with macOS awake too, not only on the way to the sleep. ANS2 reads
  `0x1000230f` in all 15 awake snapshots and changes in E1 (T-2.40) in G, H, I. When the clock
  words, `0x23b720030`.., `0x23d240040`, `0x23d240314` change between the detach and the
  commit is still not located (I's log has no access to them; periodic readings were not
  taken).
- **R53 [G] (H)** *(new)* At the commit the domain words of cores 1-7 read `0x100`, core 0's
  `0x1f0`, the efficiency cluster's ECPM `0x21f0`, the performance cluster's PCPM `0x2100`
  (4.1a item 5). `[ARTEFACT in part, A4]` *(This round.)* The same in I. With macOS awake (I,
  all eight cores running) ECPU0-3 and PCPU0-3 read `0x1f0` and ECPM, PCPM `0x21f0`.
- **R54 [G] (H, I)** At the commit the requested state of the 137 domain words is as in
  section 4.2a. *(Changed this round, gap Q4.)* **By macOS's own requests: on for 51 words, 0
  for 86**: the 54 of 4.2a's list less ATC0_COMMON, ATC0_USB and ATC0_USB_AON, which macOS
  requested off at boot (`0x23f0`, `0x3f0`, `0x3f0`; its writes held by the hypervisor and
  written by it after the snapshot, so the chip went down with them off). The snapshot's on
  values for those three are `[ARTEFACT A3]`. ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB
  are 0 at the commit and awake, never written, on a machine where macOS had no driver for the
  first port `[A2]`; their state with that port driven by macOS is **not observed**.
  *(Round 7, gap W4.)* So for the first port's seven words (ATC0_COMMON, ATC0_USB_AON,
  ATC0_USB, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB) the off request at the commit
  rests on the hypervisor's artefacts A2/A3, not on macOS with the port in use; what these words
  read after macOS's own writes reach the hardware, and what the chip comes back with for them
  after a sleep without the hypervisor, are in no capture (the wake snapshot's values are taken
  after the hypervisor has brought its own USB back, A7). Under Linux they read ATC0_COMMON
  `0x22ff`, ATC0_USB_AON and ATC0_USB `0x2ff`, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB
  `0x3ff` (all on; section 12, L15), and the Thunderbolt link to the other computer runs behind
  them. Holding the driver to these seven being requested off at the commit is decision **D4**
  (below), not an observation. *Reference, not an observation:* Aurora's device tree marks
  ATC0_USB_AON and ATC1_USB_AON `apple,always-on` ("Needs to stay on for dwc3 to work",
  `t8103-pmgr.dtsi`, `dcce0e751c71`).
- **R48 [G] / [ARTEFACT]** The clock muxes written `0x80100000` in R18 hold `0x85100000` /
  `0x87100000` at the commit: the write of R18 is observed (all six captures), its effect on
  the word is not. The values of SIO, SIO_BUSIF, UART_P, UART0, ATC0_COMMON at the commit are
  the hypervisor's doing (A3) and are not requirements.
- **R35 [BOTH] (was UNKNOWN)** After an alarm wake macOS does not turn the display, graphics
  or the I5 burst back on (A for 163 s, G for the 20.8 s recorded); after a key wake it does,
  within 5 s in B and 0.7 s in D, E, F (W4, W5, section 2). *(Changed this round.)* Three
  alarm wakes (A, G, H), four key wakes. All three alarms were the hypervisor's. After each alarm
  wake (and no key wake) the SPMI word `0x23d0d9320` is written 0 then 4 in the power chip's
  wake action (gap S11, W3). *(Changed this round, gap Q9; I is a fourth alarm wake.)* The
  first of these writes comes with `W 0x23d0d9360` = 4 (the value read) at the controller's
  first status reads after the wake, where +`0x360` reads 4 after every alarm wake and
  `0x20000000` / `0x20010000` after every key wake; the second follows the SPMI read of
  `0xd00c` = `01`. Which reading macOS acts on is not observed (W3). *(Round 8.)* J is a fifth
  alarm wake (the instrument's alarm), dark as A, G, H, I.
- **R55 [BOTH]** *(new, gap S2)* In `pmp`'s wake action, after R6w: ten writes to `pmp`'s
  address translator in this order: +`0xfc`=1, +`0x200`=V, +`0x2f0`=0, +`0x34`=`0xffffffff`,
  +`0x20`=`0x100000`, +`0x60`=`0x80016100`, +`0x68`=`0xf0f0f`, +`0x6c`=`0x80808`,
  +`0x100`=`0x80`, +`0x13c`=`0x100` (base `0x23b300000`; D, H). V, and `sio`'s translator
  values at `0x235004200`, `0x235004210` (W1-8), differ in every capture, are never 0, and are
  not read or written before the sleep in any log. Their source is not observed `[UNKNOWN]`.
  *(Changed this round, capture I.)* In I each of the three words is written at boot, 0 then V,
  and at the wake the same V again, by the same instruction, without a read (W3): **the value
  written at the wake is the value written at boot** (one capture). What V points at, and
  whether 0 would do, is not observed.
  *Reference, not an observation (round 7):* in Aurora Silicon's `drivers/iommu/apple-dart.c`
  (`integration/aurora`, `dcce0e751c71`) +`0x200` of such a translator is stream 0's table base
  register (bit 31 "valid", the table's address shifted right by 12) and +`0xfc` the streams
  enable; read that way, V names a translation table in memory (I's `0x808217dc`: valid, table
  at `0x8217dc000`), which the captures do not contain.

- **R49 [BOTH]** Every access was made with the width that word has in `widths.tsv`: 32 bits
  unless listed there as 64 (or 16, or 8) bits; the width of a word never changed between
  captures or between reads and writes of the same word, apart from the 23 words named in
  section 1.8 (all six captures; `widths.py`). *(This round.)* `0x690000004` is read as 32 bits
  and written as 16 bits (value 0) in E5-3, read and written as 32 bits at the wake (all eight).
  *(Changed round 7, gap W9.)* For the ten PCIe words with two widths the width is per access,
  as in the table of section 1.8 (D-I, the same in all six): there a word's width does change
  between reads and writes, and between one access and the next. The guarded power words and
  the core start/stop words: 32 bits at boot; during the entry and the wake not recorded (open
  question 39). The coprocessors' mailbox words are 64 bits, their +`0x44`, +`0x48`, +`0x8110`,
  +`0x8114` 32 bits (section 0).

- **R50 [D]** When the platform sleep actions begin, each power-domain control word has the
  requested state of `ps-at-e3.tsv` (section 1.9): the same in D, E, F and G for 77 of the 78
  observed words. *(This round, gap Q14.)* With I's awake snapshot, the 13 words of 1.9's last
  item are on with macOS awake and at the commit and are not written in between; the nine
  domains macOS never writes (4.3) are 0 awake and at the commit.

- **R56 [D]** *(new, gaps Q1, Q15)* Every power-domain write that requests 0, in D-I, takes one
  of the forms of section 4.3, with the value written fixed by the value read just before:
  (1) word read with bit 28 clear: one write, the read value with bits 0-9 replaced by `0x3f0`;
  (2) word read with bit 28 set: first the read value with bits 28, 9, 8 cleared, then (the
  word now reading bits 24-27 and state `0xf`) that read value with bits 0-9 replaced by
  `0x3f0`; RMX's second write is `0x300` instead; (3) word read with request 4 (wake only): one
  write, the read value with bits 0-9 replaced by `0x340`. Children before parents (1.9). The
  first read after the write reports state 0 in every instance; a wait for it is not observed.
  The nine domains Linux has on and macOS never writes (ATC1_COMMON, ATC0_PCIE, ATC0_CIO,
  ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE, MSG, ATC1_USB_AON, ATC1_USB) have **no observed
  turn-off**: they are 0 with macOS awake (I) and at the commit, and are not written in any log
  (boot is not logged in full).
  *(Round 7, gaps W2, W5.)* (a) RMX: its second write is `0x300` after a read of `0x0f0003ff`
  in all 18 instances, while the same read at the wake's first RMX write is followed by form
  (1)'s `0x0f0003f0` (4.3): the captures give the value per place, not a rule on the read.
  (b) The nine never-written domains read on under Linux (ATC1_COMMON `0x23ff`, ATC0_PCIE,
  ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE `0x3ff`, MSG, ATC1_USB_AON, ATC1_USB
  `0x2ff`; L15); which form macOS would use on them is not observed: by the value alone (bit 28
  clear) the general statement (1) is the only form the captures have for such a word.
  (c) Form (3) is seen at the wake only; a request-4 word turned off before a sleep is not
  observed. (d) A word with bit 28 set and request 4, and a word that does not read state `0xf`
  after form (2)'s first write, are not observed; from state 4, form (2)'s first write is seen
  only in R23 (SIO_CPU), with no read after it (E2a, open question 43). After a turn-off write,
  the first read reported state 0 in every instance, so how long a word may take to report
  state 0, and what macOS does if it does not, are not observed. *Reference, not an
  observation:* Aurora's driver comment says macOS waits for (word & `0x8ff`) == 0 (section 0).
- **R57 [D]** *(new, gaps Q1c, Q6)* At the wake (W1-2c), the words that come back with request
  4 are written request 0 by form (3) of R56 (PMS_FPWM0-4, AFT0, DEVC0_IVDMC, SOC_SPMI0-2,
  I2C0-4, SPI0-4, FPWM0, FPWM2, ISPSENS0-3) and read `..200` after; turn-ons take the forms 4-6
  of section 4.3 (three writes, the third with bit 28, after a read showing state `0xf`; one
  write for words already on). Request 4 is never written over request 0 in any capture.
- **R58 [BOTH]** *(new round 7, gap W3; section 6 W4; all eight captures)* At every wake macOS
  turns the display domains on, restarts and boots `dcp` and `dcpext` (E2a's restart), starts
  their endpoints `0x20`-`0x2c`, and stops both again by R5a's whole stop, turning their domains
  off after each stop, 9 to 169 ms after the restart. After the four alarm (dark) wakes both
  stay stopped with their domains at the commit values to the end of each log (A 163 s; G, H, I
  20.8 s). After the four key wakes `dcp` is started again and stays running; `dcpext` stays
  stopped. In no capture is a display coprocessor left stopped with its domains on, or running
  with them off.
- **R59 [ARTEFACT, in every power-down]** *(new round 8; A6, E7, 4.4 row 4)* Each core enters its
  final wait with its four timer controls (`CNTP_CTL_EL0` and `CNTV_CTL_EL0` as seen from EL2,
  `CNTP_CTL_EL02`, `CNTV_CTL_EL02`) and its guest timer FIQ enable (`VM_TMR_FIQ_ENA_EL2`) at 0,
  and with no virtual IRQ or FIQ pending: the instrument writes these on every core between that
  core's `CYC_OVRD_EL1` write of R43 and the moment the write reaches the hardware, in A-J. Before
  that each core's last `PMCR0_EL1` write is `0x7003400` and its `IPI_SR_EL1` has been written 1
  (R45; core 0 included, J). What macOS itself leaves in the timer registers is **not observed**
  (they are not trapped). No capture has a power-down with a core's timer enabled or an
  interrupt pending at a core; whether either keeps the chip up is not observed.
  *(Changed round 9: K, `det13`, `det17`.)* **What macOS itself leaves is now observed (K, one
  capture):** at its final write each core's guest physical timer is disabled (`0x6`) and its
  guest virtual timer **enabled and unmasked on all eight cores**, already fired on cores 1, 2
  and 0 (`0x5`), due 0.88 s later on core 3 and 89.39 s later on cores 4-7 (E7). The instrument
  had, on the three fired cores, a virtual FIQ pending for macOS and that timer's FIQ to the core
  off. The statement above stands as the state of **every observed power-down** (A-K: the
  instrument's writes). **[HV-CHANGED]** In the two runs in which the instrument left macOS's
  timer state and its own pending virtual interrupts in place (`det13`, `det17`), the chip did
  not power down and wake: no alarm wake, a reset about 5-6 s after the commit, both times. Which
  of the two (the enabled timers, the pending virtual FIQs) made the difference is not separated,
  and what macOS's timer state does on a machine without the instrument is not observed
  (open question 59). So the requirement on a Linux driver's cores that rests on the
  observations is the state of every observed power-down: timers off and no interrupt pending
  at each core's final wait; macOS's own state is not that state, and was twice followed by no
  power-down when kept under the instrument.
  *(Changed round 10: L, `det19b`, `det20b`, `det21`, `det22c`; E7.)* **The two items are now
  separated [HV-CHANGED]**: with the guest timers and timer FIQ enable left as macOS left them
  and no virtual interrupt pending, the chip powered down and woke at the alarm (`det19b`,
  `det21`, 2 of 2); with a virtual FIQ left pending at cores 0-3 / 0-2 and the timers written
  off, it did not, and reset about 6 s after the commit (`det20b`, `det22c`, 2 of 2). So "timers
  off" is no longer the state of every observed power-down (two had every core's guest virtual
  timer enabled and unmasked), and the statement that holds in all thirteen captured power-downs
  (A-L, `det19b`, `det21`) is: **at each core's final wait no virtual IRQ or FIQ was pending at
  the core** (the instrument's act, [ARTEFACT, in every power-down]), **and, where read (K, L,
  `det19b`, `det21`), `ISR_EL1` read 0 at each core's final write** (macOS's state under the
  instrument's settings). macOS's own timer values are the same kind in K, L, `det19b`, `det21`
  (E7). **The requirement on a driver's cores that rests on the observations is therefore: at
  each core's final write nothing is pending at the core: `ISR_EL1` reads 0, and no virtual IRQ or
  FIQ is pending if the kernel uses `HCR_EL2`'s.** Its basis: every observed power-down had it,
  and its absence (a pending virtual FIQ) was followed by no power-down four times of four, both
  under the instrument. **Not required by the observations: that the timers be disabled**; a
  core's timer may be left enabled, as long as nothing is pending at the core (`det19b`,
  `det21`, [HV-CHANGED]; one core each went down with an unfired timer due 62-63 ms later and
  its FIQ to the core on). Not observed on either system: a physical interrupt (a fired timer
  whose FIQ is on, an IPI, a counter interrupt, a controller line) pending at a core at its
  final wait; what macOS's fired timers present to a core without the instrument (open questions
  65, 66).
  *(Round 11: `det23`, `det24`; E7.)* The requirement stands as worded in round 10, now on
  **fifteen** captured power-downs (A-L, `det19b`, `det21`, `det23`, `det24`; the virtual part the
  instrument's act) and `ISR_EL1` 0 at every core's final write in **six** (K, L, `det19b`,
  `det21`, `det23`, `det24`). New: in `det23` core 3's pending virtual FIQ came from an IPI the
  instrument held for it, not from its timer (E7); so "nothing pending" covers IPIs as well as
  timers, and macOS's own entry does reach a core's final write with an IPI not yet taken at
  that core. The test statement is in 8.1.
- **R60 [D] and [ARTEFACT, in every power-down]** *(new round 8; R38, A6, 4.4 row 2)* When the
  cores go down, the power chip's SPMI controller `0x23d0d9300` has no reply status left
  unacknowledged: every command macOS sends ends with `0x23d0d9378` read 1 and written 1 and
  `0x23d0d9338` written 1 (D-J), and after its own commands at the commit the instrument writes
  `0x23d0d9378` = 1 (every capture of this document; in A and B through
  `harness/spmi_ack_patch.py`, A6). Two earlier runs under the instrument without that last write
  (2026-11-16, evidence `2026-11-16-hv-macos135-s2r`; 2026-11-17 `135full1`, evidence
  `2026-11-16-dram-controller-state`) powered down and were woken after about 0.65 s and 1 s,
  wake status `+0x20` = `0x400000`; with it (`135full3` = A, and every capture since) the chip
  slept until the alarm or an input (F's 1.6 s wake is "trackpadkeyboard", section 11.2). So any SPMI command sent after R38's (a record, an alarm) is
  followed by `0x23d0d9378` = 1 before the cores go down. Those two runs show an early wake, not a
  chip that stays up. *(Round 9, K.)* At the commit, after macOS's last command and before the
  instrument's own, `0x23d0d9378` reads 0 (awake also 0; 4.1c). *(Round 11.)* 0 at the commit
  and awake also in L, `det19b`, `det21`, `det23`, `det24` (`r7-det*.txt`, `r8-det2[34].txt`): six
  captures.
- **R61 [J]** *(new round 8; 1.7c, 4.4 row 11)* Watchdog 1 armed at the commit, with
  `0x23d2b001c` = 0, `0x23d2b0010` = 0, `0x23d2b0014` = N x 24,000,000 (N = 150), `0x23d2b001c` =
  4, written after every other write of the commit (the instrument's), did not prevent the
  power-down or the alarm wake (asleep 89.5 s). At the wake entry its bite and control read as
  written and its count, like watchdog 0's, about 13.9 ms. Not a step macOS takes; recorded
  because Linux's runs arm the same watchdog with the same four writes (L17). One capture.
  *(Round 9.)* K repeats it (asleep 89.47 s; at the wake entry its count 14.1 ms, its bite and
  control as written).
- **R62 [K]** *(new round 9; 4.1c, 4.4 rows 5 and 13, 4.4a C17)* **Watchdog 2 is armed before the
  cores go down, with no write of macOS's to it.** At the commit watchdog 2 reads bite
  `0x7270e00` (5 s at 24 MHz) and control 4, its count 16.74 ms: started within about 0.3 ms of
  macOS's first write of `0x23d2c4000` = 1 (R24, T-0.0154). macOS's writes to the watchdog page
  in the entry are R15's only (none to watchdog 2), the instrument writes no word of watchdog 2
  (A6), and awake it read bite `0x80befc00`, control 0. Also at the commit: `0x23d2b8028` =
  `0x1000000` (awake 0), `0x23d2b8040` = `0x20` (awake `0x20`), `0x23d2c4000` = 0 (R24),
  watchdogs 0 and 1 counting from macOS's zeroing (R15) with watchdog 1's bite 60 s and control
  0. At the wake entry watchdog 2 reads bite 5 s, control 0, count 0.326 s; `0x23d2b8028` =
  `0x8000000`, `0x23d2b8040` = `0x22` (section 5, as in D-J). What arms watchdog 2 is not
  observed. So, for a driver: before the cores go down macOS writes nothing to watchdog 2 and
  watchdog 2 reads armed for 5 s with control 4, within about 0.3 ms of the first write of
  `0x23d2c4000`. One capture; the time is from a count, good to about 0.3 ms.
  *(Changed round 10, [L]; 4.1c.)* Read inside macOS's three writes of `0x23d2c4000` in L,
  `det19b`, `det21`: **watchdog 2 is already armed (bite `0x7270e00`, control 4) and
  `0x23d2b8028` already `0x1000000` just before the first write reaches the hardware**, with a
  count of 43-56 microseconds; nothing of watchdog 2, `0x23d2b8028` (`0x1000000`) or
  `0x23d2b8040` (`0x20`) changes at any of the three writes but the count. Its count started 1.3
  to 7.1 microseconds (±10) after the record of macOS's write `0x23b718004` = 0 (R22), 31-45
  microseconds before the record of the first `0x23d2c4000` write. What arms it is still not
  observed. So, for a driver: before the cores go down macOS writes nothing to watchdog 2, and
  watchdog 2 reads armed for 5 s with control 4, and `0x23d2b8028` bit 24 set, by the time of
  the first write of `0x23d2c4000`, watchdog 2's count having started just after the write
  `0x23b718004` = 0 of R22 (three captures; this replaces "within about 0.3 ms of the first
  write").
  *(Round 11.)* The same in `det23` and `det24`: five captures; count at the first write 38-57
  microseconds, start 1.3-7.5 microseconds after the record of `W 0x23b718004` = 0 (4.1c).
- **R63 [K]** *(new round 9; 4.1c, 4.4 rows 7 and 9)* At the commit the AP wake-source masks
  `0x23d004008`, `00c`, `010`, `014`, `018` read `0xf3ffafff`, `0xffb97eff`, `0xfffdeffe`,
  `0xffffffff`, `0x03ffff87`, the values they hold with macOS awake; macOS writes none of them in
  any logged window (D-K) and the instrument writes none (A6). The always-on clock words
  `0x23d240024`, `03c`, `048` read `0x81100100`, `0x81100100`, `0x82100100` awake and at the
  commit (no change, unlike `0x23d240040` and `0x23d240314`, R52). One capture for the awake
  values; the commit values of the clock words are also those of G-J (appendix B).
- **R64 [HV-CHANGED]** *(new round 9; 1.7d, 4.1c, 4.4 row 14, 4.4a C1)* Not a step macOS takes:
  what the machine did when, after macOS's whole entry and the instrument's whole commit, one
  core (core 0) was **kept running** while the seven others had gone down. `det16` (never goes
  down): for 4.9 s `0x23d2b8028` (bit 24), `0x23d2b8040` (`0x20`), `0x23d2c4000` (bit 0 clear),
  `0x23b71c090` (bit 30 clear), `0x23b71c360` (bit 30 set) and power-chip `0x0201` (`00`) did
  not change while watchdog 2 counted with its control bit 2 set; then a reset about 6 s after
  the commit. `det14` (core 0 went down after 3 s): no wake, a reset about 7 s after the commit
  (±2 s). Both sampled with SPMI reads and writes after the commit (A6). Recorded because it is
  the only M1 observation of the chip after macOS's commit with a core still running, and its
  readings match those of an earlier Linux driver's run with a core kept up (L18, 4.4 row 14).
  With every core down (A-K, with the instrument's per-core writes, R59) the chip powered down
  every time. So, for a driver: every core, core 0 included, makes its final write and goes down
  (R43, R44); none is kept running after the commit.
- **R65 [K]** *(new round 9; E7)* At each core's final write: `CNTP_CTL_EL02` `0x6` (disabled),
  `CNTKCTL_EL12` `0x4f`, `IPI_SR_EL1` 0 (after R45's acknowledgement), `IPI_CR_EL1` `0x600`,
  `PMCR0_EL1` `0x7003400` with no counter interrupt pending (`PMSR_EL1` 0), `UPMCR0_EL1` and
  `UPMSR_EL1` 0, the guest's `PSTATE` with D, A, I and F all masked; the interrupt controller as
  in R36's round-9 note. These are macOS's own values (the instrument does not change them).
  The guest virtual timer is R59's round-9 note. One capture.
  *(Round 10.)* The same values in L, `det19b` and `det21` (E7): four captures.
  *(Round 11.)* The same in `det23` and `det24` (six captures), with one exception that is the
  instrument's word, not a register of macOS's: in `det23` the instrument's "IPI pending" for
  core 3's guest read 1 (an IPI to core 3 not yet taken; E7); the hardware `IPI_SR_EL1` read 0 on
  every core in all six.
- **R66 [L]** *(new round 10; 4.1d, 4.4 row 16)* At the commit the CPU start/stop block reads
  `0x23b754000` = `0xfe` and `0x23b754004` = `0xfe` (bits 1-7: cores 1-7), `0x23b754008`-`01c`
  = 0; with macOS awake all eight read 0. +`0x0` holds the stop bits cores 1-7 wrote at
  T-0.090 s (R11; passed to the hardware, A4); core 0 writes no stop bit. +`0x4` is written by
  no logged access in the entry and by no act of the instrument's (A4). For a driver: at its
  commit the block holds the stop bits of cores 1-7 and not core 0's, in +`0x0` by R11's writes;
  +`0x4` = `0xfe` is a reading of the hardware's, not a write to make. [LINUX] awake all eight
  read 0 (snapshot 16). Three captures. *(Round 11.)* The same in `det23`, `det24`: five
  captures; [LINUX] awake again all 0 for +`0x0` and +`0x4` (2026-11-18 03:54).
- **R67 [L] and [BOTH] for the wake** *(new round 10; 4.1d, 4.4 row 15, 4.4a C3)* At the commit
  the power-gate header words `0x23b71c000`, `0x23b71c010`, ... `0x23b71c080` (stride `0x10`)
  and `0x23b71c088` read `0x80000000`, as with macOS awake (L, `det19b`, `det21`). macOS writes
  `0x23b71c080` and `0x23b71c088` = `0x80000000` in the entry (E5-8i, each read `0x80000000`
  first), and **no other header word in any logged entry**. At **every wake** (thirteen
  captures) it reads `0x23b71c000` = **0** and writes it `0x80000000`, and reads and writes
  `0x23b71c040` = `0x80000000`, before it starts any other core (W1-2a, R30). [LINUX] awake
  `0x23b71c000` reads **0**, the other nine `0x80000000` (snapshot 12). For a driver: at its
  commit `0x23b71c000` and `0x23b71c040` hold `0x80000000` (bit 31 set), the value macOS has at
  every commit read; the only write macOS is seen to make to either is `0x80000000`, at the wake,
  over a read of 0 (for `0x23b71c000`). Whether bit 31 of `0x23b71c000` is needed for the
  power-down is **not observed** (no M1 run has had it clear at a commit); *reference, not an
  observation*: on T8140 the word at the same offset of the power-gate block lets the boot
  cluster's cores power down in their wait, and left clear it ends every sleep in a watchdog
  reset 5 s after the commit (4.1d). Three captures for the commit values, thirteen for the wake
  writes. The other power-gate words: 22, 21, 20 of 450 change between awake and the commit with
  no write of macOS's, 23 in all (4.1d); not a step macOS takes.
  *(Changed round 11: `det23`, `det24`, 1.7f, R69; the Linux reading of 2026-11-18 03:54.)*
  **The sentence "For a driver: at its commit `0x23b71c000` and `0x23b71c040` hold
  `0x80000000`" is withdrawn as a requirement.** With `0x23b71c000` cleared by the instrument
  before every core's final write (`det24`) or before most of them (`det23`), and reading 0 at
  the commit, the chip powered down and woke at the alarm, 2 of 2 **[HV-CHANGED]**: no
  observation now supports requiring bit 31 of `0x23b71c000` at the commit. What R67 now says, by
  how firmly each part rests:
  (a) **Entry [BOTH], all fifteen** (`r10-checks.txt` part 4, `r11-checks.txt` part 3)**:** of the header words macOS writes only
  `0x23b71c080` and `0x23b71c088`, each `0x80000000`, in the order R `080`, R `088`, W `080`,
  W `088` (both read `0x80000000`), by core 0, about 15.7-15.9 ms before T, just before R22's
  `0x23b718000` (E5-8i); it writes neither `0x23b71c000` nor `0x23b71c040`.
  (b) **Commit [L], five captures for macOS's own value:** all ten header words read
  `0x80000000` with macOS's entry left alone (L, `det19b`, `det21`; and in `det23`, `det24` up to
  the instrument's write, read just before it). The value of `0x23b71c000` at a driver's commit
  is **not constrained** by the observations: set (macOS, three) or clear ([HV-CHANGED], two)
  were both followed by a power-down. `0x23b71c040` clear at a commit is in no run.
  (c) **Wake [BOTH], all fifteen captures with a wake:** after the poll of `0x23b718004` ends
  (R30), core 0 reads `0x23b71c000` (0 every time), writes it `0x80000000`, reads
  `0x23b71c040` (`0x80000000`), writes it `0x80000000`, before any other core is started (R32);
  about 10 ms later it reads `080`, `088` and writes each `0x80000000`. Since `0x23b71c000` read
  0 and `0x23b71c040` `0x80000000` every time, the captures cannot tell "set bit 31" from "write
  the constant `0x80000000`" (the written values are the same either way).
  [LINUX] awake `0x23b71c000` reads 0 on two boots (snapshot 12; 2026-11-18 03:54) and
  `0x23b71c040` `0x80000000`. Under D1 the driver's wake keeps macOS's sequence, so it writes
  `0x23b71c000` = `0x80000000` where stock Linux awake has 0; what Linux does with the word set
  is not observed. Whether the word clear **through the whole entry** (as Linux awake has it)
  stops the power-down is not observed (open question 67).
- **R68 [HV-CHANGED]** *(new round 10; 1.7e, E7, 4.4 row 4, 4.4a C4)* Not a step macOS takes:
  what the machine did when the instrument left part of each core's state as macOS left it at
  its final write. (a) Guest timers and timer FIQ enable left (every core's guest virtual timer
  enabled and unmasked, fired on three cores whose timer FIQ to the core the instrument had
  turned off, due 62-63 ms later on one core with its FIQ to the core on, 89.39 s later on four),
  no virtual interrupt pending: **power-down and alarm wake, `det19b` and `det21`**. (b) A
  virtual FIQ left pending at cores 0-3 (`det20b`) or 0-2 (`det22c`), timers written off: **no
  wake, a reset about 6 s after the commit**, as `det13` and `det17` with both left (round 9).
  Recorded because it is the only M1 observation that separates the two items; it supports R59's
  round-10 requirement (nothing pending at a core at its final write) and withdraws "timers
  off" as a requirement. Two runs of each.
- **R69 [HV-CHANGED]** *(new round 11; 1.7f, 4.1d, 4.4 row 15, 4.4a C3)* Not a step macOS
  takes: what the machine did when the instrument wrote `0x23b71c000` = 0 after macOS's last
  write to the power-gate page and before the cores' final writes (`det23`: 6-14 microseconds
  before T, after the first core-down records of cores 1 and 3; `det24`: 281-288 microseconds
  before T, before every core's final write), the word then reading 0 at the commit and
  `0x23b71c040` `0x80000000`: **power-down and wake at the alarm, 2 of 2** (asleep 89.998 s and
  89.649 s, wake status 0 / `0x400000` / 0, wake-entry words and power-chip bytes as in L).
  Recorded because it is the only M1 observation with that word clear at a commit; it withdraws
  R67's commit clause and answers open question 67 for the word cleared at the end of the entry.
  Two runs; control L from another session.
- **R70 [BOTH]** *(new round 13, observed in every capture, 48 boots; 8.2 C3, `r13_c3_boot.py`, `r13_c3_words.py`)* **No write to
  `0x23b058000`, `0x23b05c000`, `0x23b060000`.** macOS's application processors never access the
  pages `0x23b05c000` and `0x23b060000` (no record in the page-touch maps of 48 boots, every touch map
  from `135chain1` to `det32r`, each from the instrument's start; none in any full or detached log)
  and never access the word `0x23b058000` in any full or detached log. Their only accesses to the
  page `0x23b058000` are 32-bit reads of `0x23b058068`, `080`, `098` (`0x51100000`, `0x61210000`,
  `0x9a420000`): the page's first access at boot (`0x23b058068`, 0.74-1.10 s after the
  instrument's start, all 48), and 89 reads by core 0 within 25 ms after each wake (A, B,
  `135full1`, `135chain2`, every detached capture). What follows the boot's first access in the
  same 5 s epoch is below the touch map's resolution. The three words change with no access by
  any core (8.2 C3). In test form: the driver makes no write to the three words, with or without
  any switch, and no access to the pages `0x23b05c000` and `0x23b060000` other than 32-bit reads
  of their first word. **[LINUX]** The one Linux run that wrote them (ds20 with `cand_c3`) did not
  reach its commit and stayed dark (L25); the two macOS runs in which the instrument wrote Linux's
  values into them did not reach a commit (1.7g, [HV-CHANGED]).
  *(Round 15; 1.7h.)* It holds in det33-det37 (no access to the three words in any full or
  detached log); each change of the words there comes in the first 250 ms sample after a `pmp`
  event (R75).
- **R71 [boot: det33, det34b; `det10`, `135map4` for what those do not log in full]** *(new round
  15; 1.7h)* **macOS starts `pmp` at boot, 2.2-2.7 s after the instrument's start, in this order:**
  (a) R the SRAM header (`0x23b500000` +`0x20`-`0x5c`, +`0xc0`-`0xfc`, +`0x204`-`0x240`; +`0x204`
  "uuid", +`0x208` 5, +`0x22c` the block's offset `0x3a800`, +`0x230` its size `0x2d0`); (b) R the
  block, then W every word of it with the value read (`135map4`, one boot); no other SRAM write below
  `0x23b540000`; (c) the address translator `0x23b300000` set up: streams off (+`0xfc` = 0), TTBR of
  stream 0 = 0, +`0x2f0` = 0, +`0x34` = `0xffffffff`, +`0x20` = `0x100000` (invalidate), TCR of stream 0
  (+`0x100`) = `0x80`, of stream 15 (+`0x13c`) = `0x100`, TTBR of stream 0 = a table address with
  bit 31 set, +`0xfc` = 1 (`det10`, one boot); (d) mailbox +`0x8114` R `0x20001`, W `0x20001`; (e)
  +`0x44` R 0, W `0x10`. PMP, PMS_SRAM and PMS read `0x1f0f00ff`, `0x1f0000ff`, `0x1f0000ff` (on, bit
  28) at the first sample after (e); how macOS turned them on at boot is not logged (at the wake: R74).
  In test form (with D9): the kernel side's start makes (a)-(e) in this order, with PMP and PMS_SRAM
  reading state `0xf` before (e). Not testable as written: the translator's table address (DRAM).
  *(Round 15c, gaps G2, G3; 1.7h item 3, evidence "macOS's pmp start-up", det10.)* (c) in full, as
  det10 logged it (the translator's page in full, one boot), the writes in this order: +`0xfc` = 0;
  +`0xfc` = 0 again; +`0x200` = 0; +`0x2f0` = 0; +`0x34` = `0xffffffff`; +`0x20` = `0x100000`;
  +`0x100` = `0x80`; +`0x13c` = `0x100`; +`0x200` = the table address with bit 31; +`0xfc` = 1. The
  reads between them (+`0x0` `0x0ed01020`, +`0x4` `0x11037`, +`0x60`, +`0x80`-`0x8c`, +`0xf0`, +`0x68`,
  +`0x6c`, +`0x20`, and +`0xfc` 0 before the last write) are macOS's and allowed, not required. So
  **+`0xfc` = 0 is written twice** at boot, with reads between (R +`0x80`-`0x8c`, +`0x0`, +`0x4`,
  +`0x60`, +`0xf0`); a test that counts one write or two holds the client to det10's sequence of
  writes, both included. Whether the last three accesses come before or after (d)-(e) is not
  established (1.7h item 3); the client makes them before (d). (b)'s "no other SRAM write below
  `0x23b540000`" is all that is logged; `0x23b540000`-`0x23b57ffff` is logged in full in no boot, so
  **the client writes no SRAM word at boot but the block's 180** (a decision on what is not read; open
  question 79 would show whether macOS writes there).
- **R72 [boot: det33 = det34b word for word]** *(new round 15; 1.7h)* **The RTKit start-up and
  endpoint `0x20`'s opening**, as 1.7h's table and list: after (e), every word macOS sends answers
  the word before it or follows macOS's own order there: HELLO_REPLY `0x00200000000c000c`; STARTEP 1,
  2, 3; kdebug START and its two buffers (endpoint 3); STARTEP 4; the two EPMAP replies
  (`0x0080000000000001`, `0x0088000100000000`); buffer replies of size 4 (endpoint 1), `0x10`
  (endpoint 4) and 1 (endpoint 2); AP power `0x20` after `pmp`'s unrequested IOP power `0x20`;
  STARTEP `0x20`; on endpoint `0x20`, after RECV `0x0`: `0x000100000003c000`; after RECV
  `0x000200000023b549`: an 8-bit read of `0x23b549400`, then `0x0020000000010003` (answered
  `0x0020100000010003`), then `0x0020200000010000` (answered `0x0020300000010000`). macOS sends no
  SET_IOP_PWR_STATE at boot. Then, at boot, code-`0xe`/8/`0xa`/`0xc`/4 words and, once,
  **`0x0020e00000550000`** at 69 s, with no `…550001` before it; after it no mailbox word either way
  for the rest of the capture. IOVAs in the words: macOS's own (`0x4000`-`0x3c000`); what they map
  to is not logged.
- **R73 [det33 detached; det18, det23 the same steps; det35-det37 the same messages]** *(new round
  15; 1.7h; R4, R5, R6 unchanged)* **Before R4's exchange for `pmp`, in the entry, on endpoint
  `0x20`:** `…550001` and `…540001` (either order), `0x0020800000630000` answered
  `0x0020900000630000`, then `…550000` and `…540000` (either order), none of the code-`0xe` words
  answered; R4's exchange follows (0.37 s later in det33). After R5's stop, before R6's reads:
  translator +`0xfc` = 0 twice, each after a read of +`0xfc`, as R5a's translator rule (stream 0's TCR
  `0x80`, then stream 15's `0x100` read). After R6: E5 item d's twelve 64-bit reads at
  `0x23b549000`+ (already section 8's). The words' values do not change at any of these steps in a
  capture with the message sent.
  *(Round 15c, gap G9; evidence "macOS's pmp start-up", section 4, det33 detached, the translator's
  page in full.)* The translator's accesses after R5's stop, in det33's order: R +`0x40`, R +`0xfc`
  (1), R +`0x100` (`0x80`), R +`0xfc` (1), **W +`0xfc` = 0**, R +`0x13c` (`0x100`), R +`0xfc` (0),
  **W +`0xfc` = 0**, R +`0x40`, R +`0x100c`. In test form: each of the two writes is the value last
  read from +`0xfc` with bit s cleared (s = 0, then 15), **the read of +`0xfc` immediately before it**
  (no translator access between that read and the write), and a read of that stream's TCR (+`0x100`,
  then +`0x13c`) since the previous write; the first +`0xfc` read and the +`0x40`, +`0x100c` reads are
  macOS's and allowed, not required. det18 and det23 were compared for the management words, the
  mailbox word, +`0x44` and the SRAM reads, not for these.
- **R74 [det33; det18, det23 the same steps; det35-det37 the same messages]** *(new round 15; 1.7h;
  amends R6w and R55's place)* **At the wake:** PMP, PMS_SRAM and PMS turned on in core 0's active
  actions (W1-2), in these forms (PMP and PMS: W `0x0f0000ff` twice, W `0x1f0000ff`; PMS_SRAM:
  W `0x0f000000`, W `0x0f00000f`, read until state `0xf`, W `0x1f00000f`), PMS_SRAM having read state
  0 (`0x0f000300`) at the wake; the twelve words written (W1-2h); then `pmp`'s wake action: R6w, R55
  (the translator read first as reset: +`0x60` `0x10000`, +`0x68` `0x20202`, +`0x6c` 0), R5w
  (+`0x8114` = `0x20001`, +`0x44` R 0, W `0x10`); then the short handshake: HELLO_REPLY
  `0x00200000000c000c`, **each EPMAP word echoed** (`0x008000000000001f`, `0x0088000100000001`), AP
  power `0x20` after `pmp`'s unrequested IOP power `0x20`; **no STARTEP, no buffer reply, no
  endpoint-`0x20` opening**; then on endpoint `0x20` `…630001` first, `…550001` and `…540001`, then
  `…550000` and `…540000` (each pair either order), none answered. In det33 every byte R6w writes
  equals the byte R6 read (196,608 of 196,608).
- **R75 [HV-CHANGED] and [det33, det34b, det35-det37]** *(new round 15; 1.7h; 8.2 C3, C18)* Not a
  step macOS takes: **the C3 words and PMP/PMS_SRAM against `pmp`'s events, with the message
  `0x0020e00000550000` sent and dropped.** (a) In every boot (five) the words went from
  `0x444/0x666/0x333` to `0x444/0x444/0x444` in the sample after `pmp`'s start and opening, with or
  without the message. (b) With `pmp` running, 060000 reached `0x222`, 058000 `0x333`, and PMP and
  PMS_SRAM `0x1000030f`, **in the first sample after the message** in every case it was sent (four
  boots, two wakes), and **never while it was dropped** (one boot, two wakes: 060000 stayed `0x444`,
  PMP and PMS_SRAM never `0x1000030f`, for 123 s at boot and 35 s after each wake). (c) In the one
  entry with it dropped (det36), 058000 reached `0x333` after `…540000` and 060000 `0x222` after
  `pmp`'s stop, so the commit had `0x333/0x444/0x222` as in every capture, and **the chip powered down
  and woke**. **Established:** under macOS, with `pmp` running, the 0x55 word is followed by the
  change and its absence by none, in these runs. **Not established:** that the word causes the change
  (a delayed send is not run), what writes the words, whether the other words of 1.7h are needed
  for it, and whether the words' values at the commit matter to the power-down (det36 reached macOS's
  commit values by another way; no commit with other values was observed except the [HV-CHANGED]
  writes of 1.7g, which cannot tell the values from the act of writing). In test form: none for a
  driver of its own; the basis of C18.
- **D1 — a decision about Linux, not an observation of macOS** (recorded here at the gap
  file's request; the orchestrator's decision, round 6, gap Q6): *the wake keeps macOS's
  sequence, and after it puts each power domain that the Linux entry changed back to the
  request the entry found.* Nothing in the captures supports or contradicts it: macOS's entry
  never changes a domain that Linux would need back (R25), R40 rests on one domain in one
  capture, and request 4 is never written over request 0 (R57). Where in the wake this happens
  is not given by any observation.
  *(Round 7, gap W8.)* Under D1 the wake writes request `0xf` (or 4) back over words the entry
  set to 0. For DISP0_CPU0 and DISPEXT_CPU0 the only turn-on macOS was seen to make is form 4
  of section 4.3: R `0x0f000300` (or `0x0f040300`) W `0x0f040000` (bits 16-19 = 4), W
  `0x0f04000f`, read until state `0xf`, W `0x1f04000f`; Linux's value for both before the entry,
  `0x1404024f`, also has bits 16-19 = 4. Request 4 written over request 0 is in no capture (R57);
  sixth-round Q6 (a)-(e) stand as stated there.
- **D2 — a decision about Linux, not an observation of macOS** (the orchestrator's default to
  the round-7 gap W3, reported to Naeem, who may change it): *the wake leaves the coprocessors
  the entry stopped (`dcp`, `dcpext`, and any other it stopped by R5a) as they are: it does not
  restart or boot them. Bringing a device's coprocessor back after a sleep is left to that
  device's own Linux driver. (D1 still puts the power domains back.)* What the captures say
  next to it: macOS's dark wakes end with `dcp` and `dcpext` stopped, but with their domains
  off (R58); a display domain left on with its coprocessor stopped, which D1 with D2 produces
  for DISP0_CPU0 and DISPEXT_CPU0, is in no capture (4.3, R58). What Linux's display driver does
  with a coprocessor it finds stopped (+`0x44` = 0) is not observed.
- **D3 — a decision about Linux, not an observation of macOS** (the orchestrator's default to
  gap W1): *for `dcp`, `dcpext`, `gfx-asc` and `ans` the rule decided earlier for `sio` and `pmp`
  holds: found running, the driver does what macOS does, its messages included; found stopped,
  it sends nothing; silent, a bounded wait and then the register stop. A coprocessor whose power
  domain is found off is not touched at all.* What the captures and readings say next to it:
  macOS found each of them running and answering in every stop (R5a); under Linux at the
  driver's entry `dcp` and `dcpext` read +`0x44` `0x10` (running), +`0x48` `0x2d`, and the
  domains of `gfx-asc`, `ans`, `sio` and PMS_SRAM read state 0 (L15). What a coprocessor answers
  under Linux, and a bound for its reply, are not observed (open questions 38, 50).
  **(b) "Found stopped", made exact for `sio` and `pmp`** *(new round 15c, gap G26)*: a `sio` or
  `pmp` whose domain is on and whose +`0x44` reads bit 4 clear at the driver's R4/R5 place gets
  **no message, no write to its control page, mailbox page or translator, no R6** (for `pmp`), and
  **at the wake no R6w, R55 or R5w**: the wake restarts only a coprocessor the same entry stopped
  (C8's "R5w, R6w for `pmp` if the entry stopped it"; D2's rule for R5a's four). Reads of its domain
  words, +`0x48` and +`0x44` (the reads that tell its state) stay allowed. This is 8.1's test form of
  D3 ("found stopped (+`0x44` 0), no message and no write") applied to `sio` and `pmp`, which section 8
  had left to R5, R6, R6w, R55 and R5w as unconditional [BOTH] statements. Reasons: (1) macOS made
  R5's stop, R6 and the wake's restore only for a coprocessor it had found running and stopped
  itself (every capture; open question 37: macOS never met a stopped one); (2) the wake's R5w writes
  +`0x44` = `0x10`, which starts the coprocessor's firmware: done to a `pmp` that was not running
  before the entry, it would start one Linux never started (L29) from SRAM no start had prepared,
  which no capture or reading shows; (3) with C18 on, the `pmp` client stops `pmp` and saves its SRAM
  before `enter` (D10 (b)), so a logic that stopped and saved it again would make R5, the translator
  writes and R6 twice, and its R5w at the wake would restart `pmp` before the client's R6w writes the
  same SRAM under a running CPU. This changes the logic as it stands at kernel `HEAD` `d441389d4`
  (gap G26: there the logic makes R5's register stop, the two +`0xfc` writes and R6 at the entry and
  R6w, R55, R5w at the wake for a `pmp` found stopped); the change goes through the logic's own cycle
  (its test author: D9 (b)'s test; `docs/agents/cleanroom-cycle.md`). Until the logic passes that
  test, a run with `cand_c18` on would make those steps twice; such runs wait for it.
- **D4 — a decision about Linux, not an observation of macOS** (the orchestrator's default to
  gap W4): *the driver is held to all seven first-port domains (ATC0_COMMON, ATC0_USB_AON,
  ATC0_USB, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB) being requested off at the commit,
  as R54 has it, although that rests on the hypervisor's artefacts A2/A3; D1 puts them back at
  the wake.* What the captures say next to it: R54's round-7 note; the forms macOS would use on
  these words from Linux's values (`0x22ff`, `0x2ff`, `0x3ff`) are those of a bit-28-clear word
  (form 1, 4.3; seen for the first three at boot, through the hypervisor's guard, A3); the four
  never-written ones have no observed turn-off (R56).
- **D5 — a decision about Linux, not an observation of macOS** (Naeem's decision of 2026-11-18,
  "Faster cycles", `docs/agents/cleanroom-cycle.md`; recorded round 12): *each candidate
  requirement of section 8.2 (C1-C17) is implemented behind its own module switch, off by
  default, so that one kernel can try them on the machine one by one or in combination.* In test
  form: (a) with a candidate's switch off the driver makes none of that candidate's accesses and
  behaves as section 8 alone asks; (b) with it on, the driver makes the candidate's accesses at
  the place 8.2 gives, in addition to everything section 8 asks, and section 8's requirements
  still hold; (c) any combination of switches may be on; candidates whose places coincide run
  in ascending number; (d) every write a candidate makes follows a 32-bit read of the same word
  by the same core, and is not made when that read already shows the candidate's target; (e) a
  candidate's wait is bounded and the entry goes on when it ends, whatever the word then reads
  (no bound is observed; a test checks that the wait ends); (f) at the wake, a word or domain a
  candidate changed is put back to the value (for a domain word, the request) the candidate's
  read found, by D1's rule for domains and by a write of the value read for other words, after
  R30's power-manager step (R31's memory-controller step for DRAM-controller words), **unless
  macOS's own wake writes that word** (R30, W1-2, W1-6), in which case the wake's write as
  section 8 has it governs and nothing is put back. Nothing in the captures supports or
  contradicts D5; it is how the candidates are to be tried, not a statement about the machine.
- **D6 — a decision about Linux, not an observation of macOS** (round 13; the orchestrator's
  brief of 2026-11-19, after ds20, L25; *revised round 14, gaps Z2-Z7: which waits, which words
  are put back and how, in what order, and what "cores given back" is*): *a wait that runs out in
  the entry ends the entry in a clean return to Linux: no hang, and what the entry changed and
  can put back from its own reads is put back.* In test form:
  (a) every wait of the entry is bounded (as before). *(Round 14, gap Z6.)* **The D6 waits are
  exactly two:** R16's poll of `0x200001c04` and R22a's four status-word waits. No other wait is
  a D6 wait: a domain turn-off has none (R56: the first read after the write reported state 0 in
  every instance; a wait for it is not observed); a coprocessor's reply that does not come is
  D3's case (a bounded wait, then the register stop, R5a; the entry goes on); a candidate's own
  wait is D5 (e) (the entry goes on); a wait the driver makes that section 8 does not state as one
  (on the SPMI controller's reply status, for example, R60) ends and the entry goes on. Reason:
  R16 and R22a are the only places in the captures where macOS reads one word repeatedly until it
  changes (R16: 39 to 65 polls; R22a: 1 to 9 reads per status word), so they are the only places
  where "the value did not come" is defined by an observation; every other wait is the spec
  stage's or the driver's, and each already has a way on.
  (b) when a D6 wait ends without the value it waits for, the driver takes no further step of
  the entry: no write of `0x23b718004` (R22), of `0x23d2c4000` (R24, R37, R38), of the commit's
  power-chip commands (R38, R60), no core's final writes (R43, R64), and no access of a candidate
  placed after that wait. *(Round 14.)* Both D6 waits come before R22, so R23's SIO writes, R36's
  interrupt-controller writes and R38's commands are never made before a D6 return.
  *(Round 14b, gap Z12.)* "No write of `0x23b718004`" holds for the put-back too, with no
  exception: after a D6 wait the driver writes neither `0x23b718004` nor `0x23b718000`, whatever
  C15 read and wrote before the wait ((c) rule 1). The suite's allowance of one put-back write of
  `0x23b718004` to the value C15 read is withdrawn.
  (c) the put-back. *(Round 14, gaps Z2, Z3, Z5, Z7; replaces "every word the entry wrote ... to
  the value the driver read before its first write of it".)* **D6 adds no read to the entry**:
  up to the wait, the entry's accesses are section 8's and the switched-on candidates', as
  without D6 (no capture has a read at the places where macOS writes a word without reading it).
  After the wait the driver puts back each word the entry wrote, **once**, by the first of these
  rules that applies:
  1. *Not put back, whatever was read:* the blocks of the coprocessors the entry stopped
     (mailbox, +`0x44`, +`0x8114`; a stopped coprocessor stays stopped, D2, and a message sent
     is not unsent); the SPMI controllers' words and the power chip's registers (R8, R9: a
     command sent is not undone; R9's `0x9f01` = `0x50` is written before any read of it, E3);
     the CPU start/stop block `0x23b754000`-`0x23b75401c` (e); and **the watchdog block
     `0x23d2b0000`-`0x23d2b8fff`** (gap Z3): its words are counts, controls and the glue's
     watchdog 1 (D7), and writing an earlier value back would move watchdog 1's count back while
     it is armed. R15's writes there stay as made (of them only `0x23d2b800c` is read first, 0,
     and written 0); the failure path's only write to that block is the glue's disarm, (f).
     *(Round 14b, gap Z12.)* And **the pair `0x23b718000`, `0x23b718004`** (R22's two words, which
     C15 writes immediately before R22a's wait): left as C15 left them (written `0xf`, the
     second polled for `0x2f`); neither is written on the failure path, whatever C15 read. So the
     case the suite reached (C15 reads 0, writes `0xf`, R22a's wait runs out, rule 3 would write
     0 back) makes no write. Reasons: (i) a write of 0 to `0x23b718004` is R22's trigger, the
     write the always-on side's first step follows (R62: watchdog 2's count starts 1.3-7.5
     microseconds after it in five captures, 4.1c), which (b) forbids after a D6 wait; (ii) under
     Linux, after an earlier driver's entries, the always-on program took that first step with
     one core still running (watchdog 2 armed, bite 5 s, progress word `0x01`), and without a core
     kept up the machine reset about 5 s later (L18): once that step is taken, no clean return to
     Linux has been seen; (iii) `0xf`, the value left, is what macOS's pair reads with the
     machine running (`0x23b718000` at boot, both before R22 in every entry: R19, V11, C15) and
     what macOS's wake writes into it (R30), so the pair is left as macOS has it awake; (iv)
     macOS writes the two only together
     (R22: `000` then `004` = 0; R30: both `0xf`), and what a write of 0 to `0x23b718000` alone
     does is not observed (the nearest hardware write before watchdog 2's start is `004`'s,
     4.1c), so the pair is kept as one. **[LINUX]** The only reading of the pair under Linux
     before a trigger is `0xf` and `0xf` (an earlier driver's dry run, C15's round-14b note), in
     which C15 makes reads only and this case does not arise. What the pair at `0xf` does to a
     Linux that read another value there and runs on after a D6 return is not observed.
  2. *A power-domain word:* back to the request the entry read before its first write of it
     (every domain write of the entry follows a read of the word: R56's forms, D5 (d)), by D1's
     forms. **A word read at request 4** (C5's twelve; gap Z7) is put back by **form (4r)**: one
     write of v with bits 0-9 replaced by `0x244`, v the value read just before that write, then
     reads until bits 4-7 read 4, bounded. Form (4r) is the always-on program's: its wake
     sequence 10 writes FPWM0 and FPWM2 the word `0x244` and polls each until (v & `0xf0`) =
     `0x40` (`var/recfg/seq10-11.txt`, the decode, as in 8.2 C5), after its sleep sequence 0 has
     written them 0; an application processor's write of request 4 over request 0 is in no
     capture (R57), so this is the program's form taken for the driver, not macOS's kernel's.
     For Linux's values of the twelve (`0x0f000244`, `0x244`, L15) it writes back the value read.
  3. *Any other word that the same core read with a 32-bit read after entry start and before
     the entry's first write of it:* to the value of that read (the latest such read).
  4. *Any other word:* **not put back** (gap Z2): left as the entry wrote it, and no read is
     added to learn its earlier value. Examples among section 8's writes before R16: R13's
     `0x24a820900`, `0x24a820904`, `0x23d1f0900` (`0xffffffff`; E5-2 reads `0x23c100c48`, not
     them). A test decides rules 3 and 4 from the driver's own trace.
  5. *The interrupt controller* (gap Z3): R36's writes come after R24 and are never made before
     a D6 return ((b)). Should a later round add a D6 wait after them, `0x23b104100`+4k (a word
     whose written ones set bits, so a write of the value read cannot clear what the entry set)
     is put back by R36w's rule as macOS's wake does it (E6-1): `0x23b104180`+4k written the
     bitwise inverse of the value read from it, `0x23b104100`+4k the value read from
     `0x23b104180`+4k.
  **Order** (gap Z5): the words are put back in the reverse order of the entry's **first** write
  of each (the word first written last goes first); a word written at several places (a domain
  turned on by a candidate and off later, a sub-block's control word) is put back once, at the
  position of its first write, to its value before that write. Domain words also keep 1.9's
  order (a parent on before its children, a child off before its parent); where the two orders
  would differ, 1.9's governs. Reason: each word put back once to its value before the entry
  gives the state at entry start whatever the order; reverse first writes is the order of an
  undo of single changes, and parents first is the only turn-on order seen (W1-2c; 1.9).
  (d) every wait of the put-back is bounded, and one that runs out does not stop the put-back of
  the remaining words.
  (e) cores 1-7 (*round 14, gap Z4; replaces "are given back to Linux" as a step of the
  logic's*): the logic asks no core for anything further (no final write; (b)), and the put-back
  writes nothing to the CPU start/stop block: no stop bit cleared, no start word written. macOS
  never writes a stop bit back (at every wake +`0x0` reads 0 with no write of macOS's, 4.1d,
  R66); each core's R11 write sets its own bit only, so a write of a value read could not clear
  it; and W2's start words follow a power-down, which a D6 return has not had. Returning each
  parked core to Linux is the glue's (D8 (c)). What a stop bit left set does to a core that goes
  on running Linux is not observed (open question 73).
  (f) watchdog 1, if the glue armed it (D7), is disarmed by the glue (`0x23d2b001c` = 0) after
  `enter` returns the failure and before the glue returns to Linux's suspend path (D7 (c), D8
  (c)); the logic makes no write to the watchdog block on this path.
  (g) the entry returns a failure to Linux's suspend path, which resumes, and the record names
  the wait that ran out (word, width, core: what ds20's 'T' record already gives).
  *(Round 14c, gap GL8.)* **Every field of that record is the wait's own**: the word is the word
  the wait read, the kind is the kind of the wait's last read, the core is the core that made it.
  For both D6 waits that is a 32-bit read (kind 1 in the glue's layout) by core 0 (R16's poll of
  `0x200001c04` and R22a's status words are E5's, core 0's only); the address is the status word
  or `0x200001c04`. The put-back's accesses come after the wait ((c)) and are **not** what the
  record names: where the glue's record rule says "the kind and core of the last access", for
  D6's failure record it reads "of the wait's last read". Reason: the record is there to say which
  wait ran out (ds20's C5 'T' record `44 54 c0 01 70 3b 02 10 80 00`, L25: `0x23b7001c0`, byte 7
  `0x10`, a 32-bit read by core 0, written before any put-back existed); a put-back write's kind
  and core next to the wait's word would describe an access that did not fail. Where the glue
  writes this record in its failure return: D8 (c).
  What the readings say next to it: in ds20 with `cand_c5` a wait ran out, the record says so, and
  the M1 then hung instead of returning (L25), so on the machine the failure path did not return.
  macOS gives no failure path to copy: no wait of macOS's ran out in any capture; its one
  abandoned entry (F, section 11.1) stopped 0.14 s into E1, before any power-manager write, and
  left the hardware back at idle as far as logged.
- **D7 — a decision about Linux, not an observation of macOS** (round 13; the orchestrator's
  brief of 2026-11-19; `AGENTS.md`, "A bare-metal sleep run must end without hands even when it
  hangs before the commit"; L16, L17, L25; *places revised round 14, gap Z10*): *with `wdt` = N
  set, the glue arms watchdog 1 before the entry starts, so that a hang before the commit ends by
  itself.* In test form (the glue):
  (a) *(round 15b, review point 2; replaces round 14's "immediately before it calls `enter`, with
  no access of its own in between")* **R61's four writes are the glue's first device accesses of
  its sleep step** (the step in Linux's suspend path in which the glue parks cores 1-7 and calls
  `enter`): `0x23d2b001c` = 0, `0x23d2b0010` = 0, `0x23d2b0014` = N x 24,000,000, `0x23d2b001c` = 4.
  In that step no device access of the glue's precedes them: no read of any word (the pre-entry
  snapshot of `snap` 1, 2 or 4, the probe's reads with `probe=1`, any other diagnostic read), no
  record or trace mark (each an SPMI command), and they come before the glue parks any core and
  before it calls `enter`. Only (e)'s check, which makes no device access, comes before them.
  Between them and `enter` the glue may make its diagnostics' accesses and park the cores; all of
  these are then under the watchdog. The four writes themselves are the step's only accesses a
  hang in which watchdog 1 does not end. Reasons: (i) round 14's place left the glue's own
  pre-entry accesses uncovered, and they are many: with `snap=4` the glue read the 792 words of
  macOS's commit list, and in ds15 six coprocessors' words besides, with cores 1-7 parked and
  before the logic's first access (evidence "Run ds13", "Run ds15", L15), and a read that does
  not answer hangs core 0 with nothing armed, as ds20's C3 and C5 runs stayed dark until the power
  button (L25); (ii) the count restarts at R15's write of `0x23d2b0010` inside the entry and again
  at (b), so moving the first arming earlier lengthens only the first stretch N must exceed (from
  (a) to R15: the glue's pre-entry diagnostics, the parking and the entry's first steps), not the
  entry's (d); (iii) the round-13 and round-14 places also covered D3's reads (each coprocessor's
  domain word and +`0x44`, read before any write of the entry), and this one still does, with no
  hook inside `enter`. *(Withdrawn round 15c: "What Linux's suspend path does before the glue's
  sleep step (device suspend, the other platform steps) is outside the glue and not covered by
  watchdog 1".)*
  *(Round 15c, gap GL11.)* **The sleep step is every callback of the glue's in one pass of Linux's
  suspend path, from its `begin` to its `end`** (Linux's platform suspend callbacks, in Linux's order:
  `begin`, then the devices' suspend, `prepare`, the devices' late (and noirq) suspend,
  `prepare_late`, the other cores taken offline, `enter`, `wake`, `finish`, the devices' resume,
  `end`; *documentation of Linux*: the comments on `struct platform_suspend_ops`,
  `include/linux/suspend.h`, aurora-silicon/linux `integration/aurora` `1f38ff8f4`: `begin` "is
  executed right prior to suspending devices", `end` is called "right after resuming devices ... or
  [when] the transition to the sleep state has been aborted"). So **D7 (e)'s check and then R61's four
  writes come first in `begin`**, before `begin`'s record ('Da'), its read of the power chip's clock,
  any core's going offline (in `prepare` or wherever the glue or Linux takes them offline), `dump`'s
  reads in `prepare_late`, the parking check and `enter`. N's first stretch is then from `begin` to
  R15 and **covers Linux's device suspend** (the `pmp` client's entry part among it, D10 (b)) and the
  platform steps between; open question 82 is widened to that stretch. Reasons: (i) the run must end
  without hands wherever it hangs (`AGENTS.md`), and a device's suspend that hangs is as dark as the
  glue's read that hangs (L25); arming in `enter` would leave `begin`'s SPMI record and clock read,
  the offlining and `dump`'s reads uncovered, against (a)'s own rule; (ii) with (e) met Linux's
  watchdog driver makes no access to watchdog 1 in its suspend or resume step (*reference, not the
  test kernel's code*: aurora-silicon/linux `1f38ff8f4` `drivers/watchdog/apple_wdt.c`,
  `apple_wdt_suspend` and `apple_wdt_resume` write the watchdog only when it is active or marked
  running in hardware), so the arming made in `begin` is not undone by the device suspend between;
  (iii) every way back to Linux after `begin` passes through the glue again (`enter`'s return, or
  `end` when Linux aborts before `enter`), so a disarm point exists for each ((c));
  (b) at the commit point, in the glue's commit-point step (D8 (b)), it makes them again after
  every other write of its own, as R61 and L17 have it (the count restarts there);
  *(round 14c, gap GL1)* so R61's four are the last device writes before the **first** core's
  final write; the only device writes allowed after them are the glue's probe record and its
  acknowledgement with `probe=1` (D8 (e)), which they then cover;
  (c) on D6's failure return, after `enter` returns and before the glue returns to Linux's
  suspend path, it writes `0x23d2b001c` = 0;
  *(round 14c, gap GL7; (c) widened from D6's failure return to every return)* **on every way
  back to Linux's suspend path after (a)**, whatever brought it there: D6's failure, a `run_on`
  the glue made that was not answered (its -ETIMEDOUT), `snap=1`'s stop at the commit point,
  *(round 15b)* `snap=4`'s return without calling `enter`, an error while parking the cores,
  any other error `enter` or the glue returns, and the return after a wake. On each of them the
  disarm `0x23d2b001c` = 0 is **the glue's last device write before it returns**, after its
  record (D8 (c)) and after every parked core is back with Linux. **One exception:** when a core
  the glue parked cannot be given back (its `run_on` not answered, or not answered when it is to
  be released), *(round 15b, review point 1; replaces "returns the failure without the disarm, and
  watchdog 1 resets the machine N s later; if that happens before (a) ..., the glue makes R61's
  four writes then")* the glue writes its record and then **panics** (Linux's `panic()`), with
  watchdog 1 still armed: no disarm, no other device write after the record, and **no return to
  the suspend path**. Since (a) is now the glue's first device access and precedes the parking,
  watchdog 1 is armed whenever a core can fail to answer, so the round-14c clause for a core lost
  before (a) is gone. Reasons for the panic: (1) a return to the suspend path does not end in a
  reset when Linux's own driver of watchdog 1 is active: on the M1's stock kernel systemd holds
  `/dev/watchdog0`, which is watchdog 1, with a 30 s runtime timeout (L31), and by the glue
  reviewer's report of Linux's code (not read for this spec) `apple_wdt`'s resume step restarts the
  watchdog when it is active and systemd then keeps pinging it, so the machine would run on with a
  core missing; (2) a panic does not resume: no device's resume step runs and no user process runs
  again, so nothing of Linux's pings or rearms watchdog 1, whatever (e) found, and the bite comes at
  most N s after the last restart of the count ((a), R15, (b) or the wake), unless the panic's own
  restart comes first; (3) a panic in the glue's sleep step has ended in a reset in both recorded
  runs in which one was taken: ds10 and ds11 ('P' records, on `snap=1`'s way back; the reset about
  2 s after the panic, not after `panic=10`'s 10 s, cause of the speed unknown) (evidence "Run
  ds10", "Run ds11"); the lab's command lines carry `panic=10` (`var/deepsleep/ds20.cmdline`);
  (4) the record is made before the panic, so the reset leaves it standing in the power chip. Not
  read: a panic with a parked core that does not answer (Linux stops the other cores at a panic and
  waits a bounded time for them; that a core which does not answer then delays the reset by more
  than that is not observed), open question 81. Reasons for the rest of (c): (i) with (a) the watchdog counts from before
  `enter`, so any way back that leaves it armed resets a Linux that has resumed, N s later (with
  (e) met, nothing of Linux's touches it after the return); (ii) J read watchdog 1's bite and
  control at the wake entry **as written** (1.7c; K the same), so a return after a wake also
  finds it armed, with its count restarted from about 0 at the power-up, and needs the same
  disarm; (iii) the disarm last means every step of the glue's way back (its record, the cores'
  release) is still under the watchdog, so a hang there ends by itself, the property D7 is for
  (`AGENTS.md`; ds20's C5 run wrote its 'T' record and then hung with nothing armed, L25);
  (iv) a Linux missing a core it had parked is not a clean return, and a reset is the one way
  out of it that needs no hands. What Linux's own resume does after the disarm is outside the
  glue and not covered by watchdog 1;
  *(round 15c, gap GL10)* **A `run_on` not answered goes the disarm way or the panic way by the
  core's release, not by the job.** When a `run_on` for a job of the entry (the Stop or PowerDown job
  of a parked core) is not answered (-ETIMEDOUT), the glue goes on to its way back and tries that
  core's release as it does every parked core's (bounded, as its other waits); if **every** parked
  core is then given back, the way back is the plain one (record, cores, disarm last, return:
  "a `run_on` not answered" in the list above means this case); if any core's release is not
  answered, it is the exception (record, panic). "Cannot be given back" means only the release not
  answered. Reasons: whether Linux has all its cores, which is what the exception is for (reason
  (iv)), is decided by the release, and a job that did not answer says nothing of it; the release is
  tried with watchdog 1 armed, so a hang in it still ends by itself; the record of D8 (c) (1) is
  written before the release in both cases, so it names the job's wait either way;
  *(round 15c, gap GL11)* **Linux's abort before `enter`** is a way back too: when Linux abandons the
  suspend after `begin` and before `enter` (a device's suspend failing, a wakeup pending, `prepare`
  or `prepare_late` failing), it resumes the devices and calls the glue's `end` without `enter`; the
  glue then disarms watchdog 1 in `end`, as its last device write of that sleep (its record first,
  if it makes one; no core is parked before `enter`, so none to give back). After an `enter` that
  returned, `end` makes no watchdog write (the disarm was made before `enter` returned). So the
  devices' resume after an abort is covered and after an `enter` is not;
  *(round 15c, gap GL13)* **the exception's panic leaves the exception's record standing**: the
  glue's own panic notifier (which writes a 'P' record into `0x9f04`-`0x9f0d` on a panic) **writes
  nothing on this panic**; the glue marks the panic as the exception's before it calls `panic()`, and
  the notifier, finding the mark, makes no device access. On every other panic it writes its 'P'
  record as before (ds10, ds11). Reasons: "no other device write after the record" and reason (4)
  above; the exception's record names the job's wait and the core (D6 (g)), which the 'P' record
  would replace with "a panic", the one fact the reset itself already gives;
  (d) with `wdt` unset it makes none of these writes. The logic writes nothing to watchdog 1's
  bite or control in any case; R15's write of watchdog 1's count (`0x23d2b0010` = 0) inside the
  entry restarts the count and does not disarm it. N must exceed the entry's duration (ds20 used
  30) *(round 15b)* and each of the stretches (a) to R15, R15 to (b), (b) to the power-down; the
  first now holds the glue's pre-entry diagnostics, whose duration is not read (open question
  82); *(round 15c)* with (a) in `begin` it also holds Linux's device suspend and the
  platform steps up to `enter`, the `pmp` client's entry part among them (its waits bounded by D11
  (d)). What the readings say next to it: in five macOS runs the
  instrument armed watchdog 1 (150 s) at the start of E1, 7.5 s before T, and again at the
  commit, and each powered down and woke at the alarm (`det26`, `det27`, `det28`, `det30`, `det31`;
  1.7g, [HV-CHANGED]); in the two C3 runs of the same recipe, which did not reach a commit, the
  machine restarted about 150 s after that first arming (1.7g); ds20's C3 and C5 runs, with
  watchdog 1 armed only at the commit, stayed dark until the power button (L25).
  (e) **Linux's own driver of watchdog 1** *(new round 15b, review point 1)*. A `wdt` run has a
  precondition: when the glue's sleep step starts, **Linux's watchdog core is not driving watchdog
  1**: the device `23d2b0000.watchdog` (`apple_wdt`, `/dev/watchdog0`) is neither active (opened
  and started by a user such as systemd) nor marked as running in hardware. The glue checks this
  from Linux's own watchdog state, before (a), with no device access. If it does not hold, the glue
  makes no device access at all in that sleep, logs the reason, and returns a failure (-EBUSY) to
  the suspend path: nothing armed, nothing to disarm, and no entry. With `wdt` unset there is no
  check. Reasons: (1) one watchdog with two owners: the glue's disarm on every way back ((c))
  would stop a watchdog that Linux's driver and systemd hold as running, and by the reviewer's
  report `apple_wdt`'s resume restarts the count and the reset with the bite the glue left, N x
  24,000,000 (R61's `0x23d2b0014`), not the driver's own timeout, so after a wake the machine's
  reset time would be the glue's N; (2) the panic of (c) ends in a reset without this
  precondition, but the precondition makes every other way back plain: the glue's arming and
  disarm are then the only writes to watchdog 1 between the sleep step and Linux's resume; (3) a
  refusal ends the run at once with the M1 awake and answering, which is the safe failure (the
  lab's runner already refuses a sleep without `wdt`, `AGENTS.md`). The lab's command lines carry
  `systemd.watchdog_sec=0` (ds20's, `var/deepsleep/ds20.cmdline`, and ds2-ds3's, evidence "What
  was run"); whether that leaves `apple_wdt` inactive on the test kernels, and whether
  anything marks it running in hardware at boot, is **not read** (L31, open question 81). If
  the reading finds it active with that command line, every `wdt` run is refused until the
  command line or the system's watchdog setting is changed; that change is the lab's, not the
  glue's.
  *(Round 15c, gap GL11.)* The check is the first thing the glue does in `begin` ((a)), so "no
  device access at all in that sleep" covers `begin`'s record and clock read too: on a refusal
  `begin` returns -EBUSY with no device access, Linux then calls none of `prepare`, `enter` and
  `finish` (`include/linux/suspend.h`), and any glue callback it still calls for that sleep (`end`)
  makes no device access either.
  *(Round 15c, gap GL12; L32.)* **What the check reads, and what it gives.** "Active" is Linux's
  `WDOG_ACTIVE` flag of the watchdog device bound to `/soc/watchdog@23d2b0000` (`watchdog_active()`),
  "marked as running in hardware" is that device's `WDOG_HW_RUNNING` flag (`watchdog_hw_running()`):
  **Linux's flags only**, read from the watchdog device's own state in memory, never the control
  word `0x23d2b001c` (no device access is allowed before (a)). *Reference, not the test kernel's code*
  (aurora-silicon/linux `1f38ff8f4`, `drivers/watchdog/apple_wdt.c`): `apple_wdt`'s probe sets
  `WDOG_HW_RUNNING` when it reads watchdog 1's control with the reset enable (bit 2) set, so the flag
  says that watchdog 1 was armed when Linux found it; its suspend and resume steps write watchdog 1
  when either flag is set (resume: count 0, control = reset enable). **No driver bound** to that node
  (module not loaded, node disabled or absent): the check gives **"not driving"** and the sleep goes
  on: with no watchdog device for watchdog 1 nothing of Linux's watchdog core can ping, stop or
  restart it, which is all (e) guards against. **A driver bound whose watchdog device the glue
  cannot find or read**: the check gives a **refusal** (-EBUSY, no device access), since the glue
  cannot then tell. How the glue finds the device is the C half's; on ds21's kernel the class device
  `watchdog0` had **no `device` link** to `23d2b0000.watchdog` although `apple_wdt` was bound to it
  (L32), so a lookup through that sysfs link would not find it there. On ds21's command line no
  process held `/dev/watchdog0` and systemd reported no runtime or reboot watchdog (L32), so
  "active" is not set there unless something in the kernel opened it; `WDOG_HW_RUNNING` was not read
  (open question 81).
- **D8 — a decision about Linux, not an observation of macOS** (new round 14, gaps Z1, Z4, Z10):
  *the tested logic and the kernel glue meet at three points inside one call of `enter`; the
  logic exposes these, the glue does the rest.*
  (a) **C3's nine values** (gap Z1). The logic exposes them through an accessor,
  `c3_readings(&self) -> [Option<u32>; 9]` (the test author's `[u32; 9]` with "not read" made
  explicit): slots 0-2 hold the reads at C3's place (i), in C3's order (`0x23b058000`,
  `0x23b05c000`, `0x23b060000`), slots 3-5 those at (ii), slots 6-8 those at (iii). Every slot is
  `None` from the start of each `enter`; a slot holds `Some(v)` from the moment the logic has made
  that read until the next `enter` starts, whatever `enter` returns (success, D6's failure). With
  `cand_c3` off all nine stay `None`; after a D6 return the places the entry did not reach stay
  `None`. *(Round 14b, gap Z13; replaces "The accessor is valid inside the glue's commit-point
  step".)* **Inside the commit-point step the glue gets the nine as the
  step's argument**, not through the accessor: the logic passes `&[Option<u32>; 9]` holding the
  same values in the same slots as `c3_readings` would return at that moment (the suite's
  `Hw::commit_point(&mut self, c3: &[Option<u32>; 9])`; the name is the test author's). On an
  entry with the switch on all nine are `Some` there, so the glue can record them before the
  cores go down; with it off all nine are `None`. The accessor serves after `enter` has returned
  (a success that comes back from the wake, or D6's failure, where it says which places were
  reached). Reason: `enter` holds the driver mutably for the whole call, so the glue's step,
  called from inside it, cannot call `c3_readings(&self)` on the same driver (Rust's borrow
  rules; the same for a `no_std` driver kept in a static, short of `unsafe`); passing the values
  gives the glue what (b) asks of it with no second path into the driver.
  Reason for `None`: in ds20's C3 run the record could not say where the entry stopped ('a'
  only, L25); a
  `None` says a place was not reached, and 0 cannot stand for "not read" because 0 is a value
  these words can hold (the always-on program's wake sequence 4 writes all three 0; decode, 8.2
  C3). What the glue does with them (its record's format, the power chip's bytes, a log) is the
  glue's. *(Round 14c, gap GL2: the record's layout is no longer the glue's; it is (f).)*
  (b) **The commit point** (gap Z10). The logic calls one step of the glue's (named here the
  *commit-point step*; its name in code is the test author's) after the entry's third and last
  write of `0x23d2c4000` (R38) and C3's place (iii) reads, and before any core's final write
  (R43, R44): between R38's third write and that call the logic makes no access but C3 (iii)'s
  reads. The glue makes its record there and, with `wdt`, D7 (b); the logic does not see what.
  *(Round 14b, gap Z13.)* The call carries C3's nine values as its argument ((a)).
  After the step returns, the cores' final writes follow with no device write between (R39,
  R61). This is the place where the glue already writes its 'W' record and arms watchdog 1 (L17:
  "the last access before it a 32-bit write to `0x23d2c4000` by core 0"; L25, L26).
  *(Round 14c, gap GL5.)* **"No device write between" includes the glue's diagnostics**: after
  the step returns, no trace mark, record, SPMI command or other device access of the glue's
  comes before the first core's final write (the one exception is (e)'s probe record, after it).
  A trace mark the glue makes for the final writes (its rule "a mark before every `run_on`")
  goes inside the step, before the step's record, or is not made. Reasons: macOS makes no device
  write and sends the power chip nothing after R38 (R39); R61's arming is to be the last write
  (D7 (b)) and R60's acknowledgement the last SPMI step before the cores go down, and a mark
  after them would be an SPMI command with neither after it; a mark in the record's bytes there
  would also replace the step's record (GL3).
  *(Round 14c, gaps GL3, GL4.)* **One record per commit-point step.** The step writes at most
  one record into `0x9f04`-`0x9f0d`, chosen in this order, the first that applies: the record
  of a diagnostic option the run set that names its own commit-point record (`snap=2`'s 'C',
  the commit walk's 'c', L16, L24); else, with `cand_c3` on, **the C3 record** ((f)); else the
  glue's own mark ('W', L17). With `cand_c3` off no C3 record is made (nine `None` would say no
  more than the 'W' mark: that the commit point was reached), and with every option off the
  glue writes what it wrote before this round. The step's record is followed by R60's
  `0x23d0d9378` = 1 and then D7 (b)'s four writes; with `probe=1` the probe record (e) comes
  later and stands in its place. So, with `cand_c3` on and neither `snap=2`, the walk nor
  `probe=1`, the C3 record is the one standing when the cores go down, with or without `wdt`
  and the trace. Reasons: the ten bytes hold one record, so a second record made in the same
  step would only replace the first after three more SPMI commands between R38 and the cores'
  final writes, where macOS sends nothing (R39); a run that sets `snap=2`, the walk or `probe=1`
  is set up for that reading, and C3's values are one switch among the candidates, each tried
  in its own run (D5); a run that wants C3's record sets none of the three. The C3 record, like
  'W', is made only at the commit point, so finding it after a reset says the commit point was
  reached; whether watchdog 1 was armed is the run's command line (`wdt`).
  (c) **The failure return** (gaps Z4, Z10). When `enter` returns D6's failure, the logic has
  finished the put-back ((c)-(d) of D6) and asks no core for anything further. The glue then, in
  this order: returns cores 1-7 from where it parked them to Linux by its own means, disarms
  watchdog 1 (D7 (c)), and returns the failure to the suspend path (watchdog 1 last, so that a
  hang while the cores are returned still ends by itself). Neither is a device access the
  logic makes or a test of the logic sees.
  *(Round 14c, gap GL6: the failure record's place; replaces the order above.)* The glue's
  failure return, in this order: **(1)** the failure record (D6 (g): 'T', the wait's word, kind
  and core) into `0x9f04`-`0x9f0d`, each SPMI command bracketed as R60's and followed by
  `0x23d0d9378` = 1; **(2)** cores 1-7 returned to Linux; **(3)** watchdog 1 disarmed
  (`0x23d2b001c` = 0), the glue's last device write; **(4)** the failure returned to the
  suspend path. The same order on every other way back of D7 (c) (its record, the cores, the
  disarm last), and on its exception (a core not given back) *(round 15b; replaces "(1) and (4)
  only")* (1) and then the panic of D7 (c): no (2), (3) or (4). *(Round 15c, gap GL13.)* On
  that panic the glue's panic notifier writes no record (D7 (c)), so (1) is the record standing
  after the reset. Reasons: the
  record is raw polled SPMI commands, and a controller that does not answer would hang the glue
  there; before the disarm that hang is ended by watchdog 1, after it by nothing; and with the
  record first, a hang in (2) still leaves a record that names the wait that ran out (ds20's C5
  run: 'T' written, then a hang, L25). The host tests cannot see this order (the C half's); it
  is the glue's reviewer's to check.
  (d) Entry start (8.2's definition) stays the place of the candidates' first accesses; D7 no
  longer uses it.
  (e) **The probe record after the first final write** *(new round 14c, gap GL1)*. The glue's
  decision G1 (its interface view: with `probe=1`, on core 0, after cores 1-7 have made their
  final writes and before core 0's own, the probe record 'Q'/'q', three SPMI commands) **stands
  beside (b)**, as the one exception to (b)'s "no device write between" and to R61's "last".
  With `probe=1`: the step's record, R60's acknowledgement and D7 (b)'s four writes in the step;
  then cores 1-7's final writes; then on core 0 the probe record, its commands bracketed as
  R60's and followed by `0x23d0d9378` = 1; then core 0's final write. No other device access
  of the glue's comes after the step. Reasons: the probe reads each core's own state at its
  final write (L22, L23), which exists only once that core has made it, so the record cannot be
  made earlier; watchdog 1 armed before it covers its SPMI commands, so a hang there ends by
  itself (every probe run so far ended in watchdog 1's reset, L22, L23: the 'q' reason is
  "probe, watchdog armed"); R60's acknowledgement after it keeps no reply status latched when
  core 0 goes down. Cost: commands to the power chip after a core's final write, which macOS
  never sends (R39); whether that changes the power-down is not observed, so a `probe=1` run is
  a reading, and its outcome is not counted as evidence on the power-down. R61's test line in
  8.1 is changed to "before the first core's final write" with this exception.
  (f) **The C3 record** *(new round 14c, gap GL2)*. Ten bytes at `0x9f04`-`0x9f0d`, the
  only power-chip registers the glue writes besides the alarm; bytes 0 and 1 keep the glue's
  layout ('D', `0x44`, then the record's letter, the glue's, distinct from its other letters).
  Bytes 2-9 hold the nine values, by this rule of what is kept:
  - **A 4-bit code per slot** s = 0..8 (D8 (a)'s slots): `0xf` = `None`; d (0..`0xd`) = the value
    read is exactly d x `0x111` (bits 0-3, 4-7 and 8-11 each d, bits 12-31 zero); `0xe` = any
    other value. The code of slot s is in byte 2 + s/2 (integer division), the low nibble for an
    even s, the high nibble for an odd s (slot 8 in byte 6's low nibble).
  - **Byte 6's high nibble**: the highest slot whose code is `0xe` (the latest such reading),
    or `0xf` if none.
  - **Bytes 7-9: that slot's value v, in part**: byte 7 = v bits 0-7, byte 8 = v bits 8-15,
    byte 9 bits 0-5 = v bits 16-21, bit 6 = 1 if any of v bits 22-30 is set, bit 7 = v bit 31.
    With no slot coded `0xe`, bytes 7-9 are 0.
  Example: Linux's values at all three places (`0x444`, `0x666`, `0x333`, L27) give bytes 2-9
  `64 43 36 64 f3 00 00 00`; macOS's (`0x333`, `0x444`, `0x222`) `43 32 24 43 f2 00 00 00`.
  **One record, made once, at the commit-point step** ((b)); no record at places (i) or (ii),
  and not several records over time (only the last survives a reset, and a record at (ii) would
  put three SPMI commands between R22's `0x23b718004` = 0 and R24's first `0x23d2c4000` = 1,
  where R62 (b) allows only R23's accesses). At the step all nine are `Some` with the switch on,
  so code `0xf` does not occur there; it is defined so that the rule covers any nine. **The
  failure record does not carry C3's places**: on D6's failure both D6 waits precede R22 (D6
  (b)), so with the switch on exactly place (i) was reached and (ii), (iii) were not, whatever
  wait ran out; the record would add nothing, and after the return Linux runs and the glue can
  log all nine in full from `c3_readings` (D8 (a)). Where a hang stopped (ds20's C3 run, 'a'
  only, L25) is for watchdog 1 to end (D7 (a)) and for the glue's trace to place; the C3 record
  does not try. Reasons for the rule: every reading of the three words in either system has the
  form d x `0x111` (C3, round 13: `0x222`-`0x666` at boot, awake, at the commit and at the wake;
  0 written by the always-on program's wake sequence 4), so one digit per slot keeps every
  value seen exactly and tells apart Linux's values from macOS's and each slot changed alone;
  a value not of that form is what C3's open question 71 asks about (the always-on program
  writes a target into bits 0-3 and waits on busy bit 31 and a state field in bits 8-11, decode),
  so the latest such value keeps its target, state, bits 12-21 and busy bit, and bits 22-30 are
  folded to one flag (no reading has any of them set). Nine full 32-bit values need 36 bytes;
  eight are free.

- **D9 — a decision about Linux, not an observation of macOS** (new round 15; C18): *`pmp` is run
  under Linux by the kernel side, not by the tested logic. The logic cannot run RTKit (an
  interrupt-driven exchange over the mailbox, with buffers mapped through the address translator), so
  everything of C18 that is a message, a buffer or a mapping, and the steps tied to them, is the
  kernel side's: a device-tree description of `pmp` and an RTKit client in the kernel, named here
  the **`pmp` client**.* In test form:
  (a) **The `pmp` client's** (kernel side; with `cand_c18` on): the device-tree nodes (C18 (a));
  the start at boot, R71 and R72 (C18 (b)); the endpoint-`0x20` words at boot, entry and wake
  (C18 (b), (d), (f)); at the entry, R73's words, R4's exchange and R5's stop for `pmp`, the
  translator's +`0xfc` writes and R6's reads (C18 (d)); at the wake, R6w, R55, R5w and the short
  handshake (C18 (f)); keeping PMP and PMS_SRAM on (C18 (c)); the buffers and the translator's
  mappings.
  (b) **The logic's** (no `cand_c18` behaviour of its own): what section 8 already gives it and
  does not change: E5 item d's twelve reads and W1-2h's twelve writes at `0x23b549000`+; the
  domain table at the wake (R30), which turns PMP, PMS_SRAM and PMS on as R74 has it; C8 and D3
  for `pmp` as it finds it; C3's reads and D8. With the client having stopped `pmp` before `enter`
  (D10 (b)), the logic finds PMP on, +`0x44` bit 4 clear and +`0x48` `0x2e`, and by C8/D3 makes
  no message, no stop and no R6 for `pmp`, and at the wake no R5w, R6w or R55 for `pmp` (the entry
  did not stop it). A logic test: with the simulated `pmp` stopped at entry start (+`0x44` 0,
  +`0x48` `0x2e`, PMP `0x1f0f03ff`, PMS_SRAM `0x1f0003ff`), no access by the logic to `pmp`'s
  mailbox page, control page beyond C8's reads, SRAM (`0x23b500000`-`0x23b57ffff`, except the twelve
  words) or translator, in the entry or the wake.
  *(Round 15c, gap G26; replaces "what section 8 already gives it and does not change" for `pmp`
  found stopped.)* Section 8 as written did not give this: R5, R6, R6w, R55 and R5w are [BOTH]
  statements with no condition, D3 said only that a stopped coprocessor is sent nothing, and the
  logic at kernel `HEAD` `d441389d4` makes R5's register stop, the two +`0xfc` writes and R6 at the
  entry and R6w, R55, R5w at the wake for a `pmp` in the test's state (gap G26). **Decided: D3 (b)**
  (no write, no R6 and no restore for a `sio` or `pmp` found stopped), a change of the logic through
  its own cycle; the client keeps all of C18's steps. **Who makes each of `pmp`'s steps:**

  | Step | `cand_c18` off | `cand_c18` on (client's part made) |
  |---|---|---|
  | start at boot (R71, R72), `…550000` after the opening | nobody (`pmp` not started, L29) | client (D10 (a)) |
  | entry: R73's endpoint-`0x20` words | nobody | client, before `enter` |
  | entry: R4's exchange, R5's stop, R73's two +`0xfc` writes, R6 | the logic, **only for a `pmp` it finds running** (domain on, +`0x44` bit 4 set; C8 decides "domain on" when `cand_c8` is on); nobody for one found stopped (D3 (b)) or with its domain off (D3) | client, before `enter`; the logic then finds it stopped and makes none (D3 (b)) |
  | entry: E5 item d's twelve 64-bit reads at `0x23b549000`+ | the logic, at its place (section 8) | the logic, at its place |
  | wake: PMP, PMS_SRAM, PMS on (R30's table, R74's forms) | the logic | the logic; the client only if one still reads off (C18 (f), D10 (c)) |
  | wake: the twelve writes (W1-2h) | the logic | the logic |
  | wake: R6w, R55, R5w | the logic, **only if its entry stopped `pmp`** (D3 (b)) | client, **only if its entry part made R6 in this suspend** (D10 (e)); the logic makes none (its entry stopped nothing) |
  | wake: short handshake, the five words | nobody | client |
  | `pmp` running at the commit | never: found running, the logic stops it; found stopped, it stays stopped | never: the client stopped it (C18 (d); each of D11 (d)'s ways out at the entry ends in R5's stop); an entry part the switch skipped leaves `pmp` to the logic's rule, as in the other column (D10 (e)) |

  So no step is made by both, and each step macOS makes is made by one of them whenever `pmp` was
  running at entry start. **Test form, the logic** (no `cand_c18` behaviour; it does not read the
  switch): (i) the simulated `pmp` stopped at the logic's R4/R5 place (+`0x44` 0, +`0x48` `0x2e`, PMP
  `0x1f0f03ff`, PMS_SRAM `0x1f0003ff`): in the entry, no access to `pmp`'s mailbox page, no write to
  its control page (reads of +`0x48`, +`0x44` allowed), no access to its translator, no access to its
  SRAM but the twelve 64-bit reads; at the wake, the domain table and the twelve writes only, no
  access to `pmp`'s mailbox page, control page, translator or SRAM otherwise; the same with
  PMS_SRAM reading `0x1000030f` (macOS's self-gating value after the 0x55 word, R75); (ii) the
  simulated `pmp` running (+`0x44` `0x10`, domains on): section 8's R4, R5, R73's two +`0xfc` writes
  and R6 in the entry, R6w, R55, R5w at the wake, as before; (iii) its domain off: no access to its
  blocks (D3). **Test form, the client**: C18 (b), (d), (f) with D10 (e)'s rule per part; it never
  relies on the logic for any of `pmp`'s steps. Reasons: D3 (b)'s; and the client cannot leave R4-R6
  to the logic (an entry part of R73's words only, `pmp` left running): the logic decides "domain
  off" on PMS_SRAM's reported state (L15), which reads 0 in macOS's self-gating value `0x1000030f`
  (in 1336 of det35's 1821 idle and entry samples, 1.7h), so whether the logic stopped `pmp` would
  depend on one read, and its R5w at the wake would restart `pmp` with no one to answer its HELLO
  until the client's resume step (macOS answers within 0.2 ms, 1.7h; what `pmp` does when the
  answer is late is not read).
  (c) **Neither** writes the C3 words (R70).
  (d) The client goes through the clean-room cycle as the glue does (an independent test author on
  its interface view; its C half reviewed against this spec; `docs/agents/cleanroom-cycle.md`).
  What the captures say next to it: macOS's `pmp` driver action is separate from core 0's quiesce
  and active actions (E3 and W3 against E5 and W1, 1.7h); the twelve words are core 0's, the rest
  the driver action's, which is the split above.
  (e) **The translator is the client's alone** *(new round 15c; the gap list's note outside the
  tests)*. With `cand_c18` on, `0x23b300000` is programmed only by the client (R71 (c), R73's two
  writes, R55) with its own table (D11 (a)); C18 (a)'s nodes do not bind it to Linux's translator
  (IOMMU) driver (no `iommus` link from `pmp`'s node to it, and no compatible of that driver on the
  translator's node), and the client maps its buffers itself. Reasons: R71 (c), R73 and R55 are
  macOS's exact sequences and the client's test holds them; a second owner would write the same
  registers at its own times (*reference*: aurora-silicon/linux `1f38ff8f4`
  `drivers/iommu/apple-dart.c` has its own suspend, resume and tunable steps for a translator), and
  the reference tree's `iommus = <&pmp_dart 0>` (L29) is not used for this node.
- **D10 — a decision about Linux, not an observation of macOS** (new round 15; C18): *when the
  client acts in Linux's boot, suspend and resume.*
  (a) **Boot:** at the client's probe, once PMP, PMS_SRAM and PMS are on, at whatever point of
  Linux's boot that falls (macOS: 2.2-2.7 s after the instrument's start); the start-up and the
  opening run to their end, then `0x0020e00000550000` is sent at once (macOS sent it 66 s after the
  opening; the readings do not say that the gap matters, open question 76).
  (b) **Entry:** the client's entry part (C18 (d)) runs in Linux's suspend path after the other
  devices' own suspend and **before the logic's `enter`**, at a point where the client still gets
  `pmp`'s replies (with Linux's power-management phases, *documentation of Linux*: not in the phase
  in which device interrupts are off, unless the client polls). Cost: macOS stops `sio` before
  `pmp` (E3); under D10 `pmp` is stopped before the logic stops `sio`. The order of the two is not
  observed to matter.
  (c) **Wake and failure return:** the client's wake part (C18 (f)) runs in Linux's resume path
  after the logic's wake has returned (so after W1's domain table and twelve writes, as macOS's
  action comes after them) and before the other devices resume, at the first point where the client
  gets `pmp`'s replies. **The same part runs when the entry fails** (D6's failure return, or any
  other way back of D7 (c)): Linux's resume path follows a failed suspend, and `pmp` is then stopped
  with its CPU halted, as after a sleep. Reason: an earlier Linux that sent only SET_IOP_POWER
  `0x220` to a `pmp` stopped by an entry got no answer (L30); macOS restarts `pmp` only by R74.
  (d) With `cand_c18` off the client makes none of this (D5 (a)).
  *(Round 15c, gaps G1, G16, G12, G22: (a) completed.)* **The domains at boot are Linux's
  power-domain driver's**, through C18 (a)'s `power-domains` (the earlier module's start found PMP
  and PMS_SRAM `0x1f0000ff`, held on by Linux, L30; the stock kernel turns PMP and PMS on with bit 28,
  L29); the client writes no domain word at boot. **Before any access to `pmp`** the client allocates
  and maps all its buffers (D11 (a), (c)); then it reads PMP, PMS_SRAM and PMS. If a buffer cannot be
  had, or any of the three does not read state `0xf` (bits 4-7) with bit 28, the client makes **no
  other access** (no SRAM, translator, mailbox or control-page access, no word), logs which, and its
  probe returns an error: Linux runs as without C18 for that boot (L29) and the later parts make no
  access ((e)). Reasons: R71 has the three on with bit 28 before macOS's start; with the buffers had
  first, a buffer that cannot be had stops the start before `pmp` runs, so nothing is left running
  (G16); a domain the client finds off is D3's "domain found off". **A boot wait that runs out**
  (D11 (d)): **R5's register stop alone**, its five accesses (R +`0x8114`, W the value read with bit
  0 cleared, R +`0x48`, R +`0x44`, W +`0x44` = 0), no R4 words (no exchange was finished, and they
  would go to a firmware that has not answered), no translator write, no R6; then `pmp` counts as not
  started for that boot ((e)).
  *(Round 15c, gaps G10, G13, G14: (b) completed.)* **The entry part's accesses** are C18 (d)'s, in
  that order, and nothing else on `pmp`'s blocks and the power-manager words: reads of PMP, PMS_SRAM
  and PMS before its first word are allowed, nothing interleaves R6's 49,152 reads; the kernel
  mailbox driver's own status and FIFO accesses on the mailbox page are the driver's. **An entry wait
  that runs out:** no further word; R5's register stop (its five accesses; R4's words already sent
  stay sent, none is sent after the wait), then R73's two +`0xfc` writes and R6, as after a normal
  stop; the part reports the timeout to the C half, which logs it and **lets the suspend go on**
  (D3's "silent": the register stop, then the entry continues). The wake part after it is the normal
  one (R6w, R55, R5w, the short handshake, the five words). Reason: after the register stop `pmp`'s
  CPU is stopped and its SRAM saved, the state a normal entry leaves, so the wake can restore it as
  R74 has it; without R6 the wake would have nothing to write back. **The entry after a wake whose
  wait ran out** (R5w made, the handshake or the words not finished; D11 (d)): the entry part sends
  no word and makes R5's register stop (five accesses), R73's two +`0xfc` writes and R6; the wake
  after it is the normal one. Reasons: that `pmp` did not finish the wake's handshake, so words to it
  would end in waits that run out; its CPU runs (R5w wrote +`0x44` = `0x10`) and must be stopped
  before the commit (C8's reason, *Reference* T8140); the next wake then gets the whole handshake
  again. The client knows this from its own record of the wake part, not from a read.
  *(Round 15c, gaps G11, G15: (c) completed.)* **Domains at the start of the wake part:** if PMS
  does not read state `0xf`, the client writes no domain and goes as below (a domain that does not
  come on); otherwise PMP, then PMS_SRAM (R74's order), each only if it does not read state `0xf`
  with bit 28, by R74's form for that word; PMS is not written by the client (the logic's domain
  table writes it, R30). **A domain that does not reach state `0xf`** within the wait's bound
  (PMS_SRAM's "read until state `0xf`", R74): the client reports and makes nothing more in that wake
  (no R6w, R55 or R5w); `pmp` stays stopped and the later parts make no access until the next boot
  ((e)). Reason: R6w writes SRAM in PMS_SRAM's domain, and a `pmp` restarted without its SRAM written
  back is in no capture.
  (e) **The switch and the chain of parts** *(new round 15c, gaps G12, G15, G17, G18)*. Each part
  reads `cand_c18` at its own start (the boot part at the probe, the entry part and the wake part at
  theirs). With the switch off at a part's start, that part makes **no call of any kind** on the
  client's machine interface: no device access, no wait, no buffer, no translator value (G17). A part
  acts only if the part before it acted to its end: the entry part only if the boot part of this
  boot sent the 0x55 word and no later part has given `pmp` up (a boot that found a domain off or no
  buffer, (a); a wake whose domain did not come on, (c)); the wake part only if this suspend's entry
  part made R6. So: **on at boot, off at an entry**: that entry part and the wake part after it make
  nothing; `pmp`, still running, falls to the logic's own rule (D9 (b)'s table, `cand_c18` off: the
  logic stops it if it finds its domain on, and with PMS_SRAM self-gating at `0x1000030f` it may find
  it off and leave `pmp` running; that is the run's set-up, not the client's), and the client counts
  `pmp` as not its own until the next boot; **on at an entry, off at the wake after it**: that wake
  part makes nothing, `pmp` stays stopped, and the later parts make nothing until the next boot; **off
  at boot, on later**: the client never acts in that boot (`pmp` never started). Reasons: each part
  rests on the state the part before it left (the entry's stop on a started `pmp`, the wake's R6w on
  the entry's R6), and a part that acts on a state it did not make is in no capture; the switch is
  read per part as D5 has the logic's switches read per entry.
  (f) **Words outside the client's waits** *(new round 15c, gaps G24, G25, G27)*. While `pmp` runs in
  the client's view (from R71 (e) at boot to the entry part's R5 stop, and from R5w at a wake whose
  handshake got through to the next entry part's stop), the client answers what `pmp` sends outside
  its waits, also while it waits for another word (that word stays awaited): endpoint-2 LOG words
  echoed; endpoint-4 type-8 and type-4 words (`0x0080…`, `0x0040…`) echoed; buffer requests answered
  (D11 (a)); any other word (endpoint-4 type `0xc`, which macOS received at boot and did not answer,
  1.7h; a kdebug GET_BUFFER; a word of no known kind) logged and not answered. **This includes the
  wake's short handshake** (G25): macOS answered such words in the middle of its boot start-up (ten
  endpoint-4 type-8 words each way between the crashlog reply and IOP power `0x20`; a syslog LOG
  between `0x000200000023b549` and its first request, evidence "macOS's pmp start-up", section 2), and
  no recorded wake had one. Before R71 (e), from the entry part's stop to the wake's R5w, after a part
  that gave `pmp` up ((e)) and with the switch off, the client sends nothing (D3: found stopped, it
  sends nothing). The rule is "echo the word received", so payloads and EPMAP bitmaps no capture
  shows (G27) are covered by it; macOS's own echoes carried LOG index 0 and no type-8 or type-4
  payload. Of G27's other values: a word arriving ahead of an awaited answer is seen (the LOG above);
  +`0x8114` reading `0x24401` for `pmp` is seen under Linux after the earlier module's stop (I2A,
  L30), `0x28801` for `pmp`'s +`0x8114` is not (it is in the A2I word's polls at macOS's boot); +`0xfc`
  reading `0x8001` at the entry is not (macOS read 1). Section 8's rules on read values (R5's "the
  value read, bit 0 cleared", R5a's "bit s cleared") are rules, so a test may use such values.
- **D11 — a decision about Linux, not an observation of macOS** (new round 15; C18): *which words
  the client sends.* (a) **Endpoint `0x20`: macOS's words exactly** (R72-R74), except the IOVA in
  the opening's `0x0001…` word, which is an address the client has mapped (macOS: `0x3c000`; an
  earlier Linux start used `0xffff0000` and `pmp` went on to `0x000200000023b549`, L30); and the
  8-bit read of `0x23b549400` after `0x000200000023b549`, as macOS. Every request of code 0, 2, 8 is
  answered by code + 1 before the next word is sent (bounded wait, (d)); code-`0xe` words are not
  answered (none ever was). (b) **At boot, after the opening, only `0x0020e00000550000`** of the
  words macOS sends there: it is the one the round-11 drop ties to the change (R75); the others (1.7h)
  are not observed to matter, and what states they would carry under Linux is not read. (c) **Management and
  system endpoints at boot:** macOS's words where the client can make them; buffer sizes as macOS's
  replies (4, `0x10`, 1), IOVAs the client's; **kdebug (endpoint 3) is started but given no START
  and no buffers** (its sizes are not read; the earlier Linux start reached the opening without it,
  L30). The kernel's RTKit library may be used where its words are those of L30's start, which `pmp`
  answered (SET_IOP_POWER `0x220` before HELLO_REPLY included). **At the wake, macOS's short
  handshake** (R74: each EPMAP word echoed, no STARTEP, no buffer, no opening): how `pmp` answers
  the boot form there is not observed. (d) Every wait of the client is bounded and the bound is the
  client's, no shorter than ten times the longest gap observed for that word in the captures (0.59 s
  for `0x000200000023b549`, det34b). A wait that runs out:
  at boot the client stops `pmp` by R5's register stop and leaves it stopped (Linux then runs as
  without C18, L29); at the entry it goes on to R5's register stop (D3's "silent"); at the wake it
  leaves `pmp` as it is and reports. (e) The mailbox's store width is the kernel mailbox driver's
  (macOS sends the word and its endpoint in one 128-bit store; the earlier Linux start's width is
  not read, its words were answered, L30).
  *(Round 15c, gaps G5, G6, G7: (a) completed.)* **Fields.** *Documentation*
  (aurora-silicon/linux `1f38ff8f4` `drivers/soc/apple/rtkit.c`, the buffer request and reply): the
  size in bits 44-51 in units of 4 KiB, the IOVA in bits 0-43 in bytes; every value seen agrees:
  macOS's replies (4 at `0x18000`, `0x10` at `0x20000`, 1 at `0x34000`) do not overlap, and L30's
  (1 at `0xfffec000`, `0xfffd0000`, `0xfffcc000`) were answered. The translator's page is 16 KiB
  (PARAMS1 `0x0ed01020` read at boot, bits 24-27 = `0xe`; the reference's `DART_PARAMS1_PAGE_SHIFT`),
  and every IOVA macOS gave is 16 KiB aligned. **Decided:** a buffer of size field s is at least s x
  4 KiB, in whole 16 KiB translator pages, at a 16 KiB-aligned IOVA; no two of the client's buffers
  overlap. The opening's word `0x0001…` carries the IOVA in bits 0-31 (both words seen, `0x3c000` and
  `0xffff0000`, have bits 32-47 zero; bits 48-55 = 1) and no size; the size `pmp` uses there is not
  read, and the client maps **one 16 KiB page** for it (decision; open question 83). The client sends
  each buffer's start. **"At once"** (D10 (a)): the 0x55 word is the client's next word after it has
  received `0x0020300000010000`, with no wait for any word and no delay of its own between (answers
  to words arriving meanwhile, D10 (f), allowed). **"Not answered"**: the client makes no wait for a
  reply to a code-`0xe` word or to the wake's five; it goes on to its next step; a delay of its own is
  allowed (macOS's entry had 0.37 s before R4, R73). **A buffer request after the boot's** (none in
  any capture: none after the start in macOS's boot captures, none in any wake, 1.7h): for an endpoint
  whose boot buffer is at least the size asked, the client re-sends that buffer's reply word (the same
  IOVA and size field); otherwise it maps a new buffer of the size asked and replies with it, keeping
  the old one mapped. **Every buffer stays mapped until the client unbinds**, across sleeps: the
  wake's handshake gives no buffer (R74) and R55 writes the boot's table again, so `pmp` keeps the
  boot's addresses. Reason: the firmware may still write into a buffer it was given (the reference's
  comment on a repeated request, rtkit.c, says the same).
  *(Round 15c, gaps G4, G20, G21, G23: (c) revised; replaces "The kernel's RTKit library may be used
  where its words are those of L30's start, which `pmp` answered (SET_IOP_POWER `0x220` before
  HELLO_REPLY included)".)* **The client sends every word itself through the mailbox; the kernel's
  RTKit library is not used for `pmp`.** So the library's own words (SET_IOP_POWER `0x220` before
  HELLO_REPLY, L30) and its own waits do not occur (G21), and every word is visible to the client's
  test (G23). **The start-up, in this order** (macOS's, R72, without kdebug's START and buffers):
  (1) after HELLO: HELLO_REPLY `0x00200000000c000c`, the first word the client sends; (2) after EPMAP
  base 0 (`0x008000000000001f`): STARTEP 1, 2, 3, 4 ascending, then the EPMAP reply
  `0x0080000000000001`; (3) after EPMAP base 1 (`0x0088000100000001`): `0x0088000100000000`; (4) each
  buffer request (endpoints 1, 4, 2) answered as it comes, before the client's next word of its own;
  (5) after the unrequested IOP power `0x0070000000000020`: AP power `0x00b0000000000020`, its echo
  awaited; (6) once the echo has come and the three buffer requests are answered: STARTEP
  `0x0050002000000002`; (7) after `0x0` on endpoint `0x20`: the opening; after `0x000200000023b549`:
  the 8-bit read of `0x23b549400`, the two request pairs; then the 0x55 word. The client waits
  (bounded, (d)) for each word named after "after" and for the three buffer requests. **No
  SET_IOP_PWR_STATE at boot** (macOS sends none, R72), so G20's word is not sent; in the reference's
  layout it would be `0x0060000000000220` (type 6 in bits 52-59, rtkit.c; documentation only).
  Reasons: macOS's order is the one recorded twice word for word (det33 = det34b) and its opening was
  followed by the change (R75); L30's order also reached the opening, but with a word macOS never
  sends at boot; a client that sends every word itself is tested word by word.
  *(Round 15c, gaps G19, G22: (d) completed.)* **The longest gaps seen** (from
  `var/commit-state/r10-pmpstart-det33-boot.txt`, `-det34b-boot.txt` (receipt times on the M3, to
  0.1 ms), `-det33-entry.txt`, `-det33-wake.txt` (the M1's timer); each from the word the awaited
  one follows):

  | Awaited word | From | Longest gap |
  |---|---|---|
  | HELLO `0x00100000000c000c` | +`0x44` = `0x10` (R71 (e); R5w) | 1.1 ms (det34b); wake 0.1 ms |
  | EPMAP base 0 `0x008000000000001f` | HELLO_REPLY | 0.6 ms; wake 0.1 ms |
  | EPMAP base 1 `0x0088000100000001` | EPMAP reply base 0 | 0.7 ms (det34b); wake < 0.1 ms |
  | buffer request, endpoint 1 | EPMAP reply base 1 | 0.3 ms |
  | buffer request, endpoint 4 | endpoint 1's reply | 0.3 ms (det33, the first endpoint-4 record) |
  | IOP power `0x0070000000000020` | +`0x44` = `0x10` | 18.0 ms (det33; det34b 17.5); wake 0.6 ms |
  | buffer request, endpoint 2 | AP power `0x20` | 0.4 ms |
  | AP power echo `0x00b0000000000020` | AP power `0x20` | 1.0 ms (det33); wake 0.1 ms |
  | `0x0` on endpoint `0x20` | STARTEP `0x20` | 0.5 ms |
  | `0x000200000023b549` | the opening | 589 ms (det34b); L30 63-65 ms |
  | `0x0020100000010003` | `0x0020000000010003` | 0.3 ms |
  | `0x0020300000010000` | `0x0020200000010000` | 0.6 ms |
  | `0x0020900000630000` | `0x0020800000630000` | 0.3 ms (boot); entry < 0.1 ms |
  | AP `0x201` echo | AP `0x201` | 0.1 ms (entry) |
  | `0x0070000000000201` | IOP `0x201` | 0.3 ms (entry) |

  **Decided: every wait's bound is 1 s, except `0x000200000023b549`'s, 6 s** (ten times 0.59 s,
  rounded up); the client may make a bound longer, up to twice these. Reasons: ten times every other
  gap is under 0.2 s, and these are macOS's gaps under the hypervisor, not Linux's (Linux's mailbox
  interrupt and scheduling are not timed); a bound that ends early costs a run, a longer one costs
  seconds only when `pmp` does not answer; the entry part's three waits (R73's one and R4's two)
  then take at most 6 s, within N = 30 with the rest of D7's first stretch (D7 (a), (d)). In test
  form: no wait ends before its bound unless its word has come, and every wait ends. **A boot wait that runs out: R5's
  register stop alone**, five accesses, no R4 words (D10 (a)).
  (f) **`pmp`'s control page** *(new round 15c, gap G8)*: the client's only accesses to
  `0x23bc00000` are R71 (e)'s two at boot, R5's three (R +`0x48`, R +`0x44`, W +`0x44` = 0) at each
  register stop (the entry's, and those of D10 (a), (b)), and R5w's two at the wake; no other read
  (no +`0x48` at boot, no +`0x44` before the entry's words): each part is decided by the client's own
  record of the parts before it (D10 (e)), not by a read. On the mailbox page: R71 (d), R5's and
  R5w's +`0x8114` accesses and the words; the kernel mailbox driver's own status and FIFO accesses
  are the driver's.

### 8.1 The requirements since round 6, as statements a test can check (round 11)

Each requirement added or changed since round 6 (R5a, R56-R69) is restated here so that a test
can check it against a simulated machine, with how firmly it rests and, where it cannot be made
testable as written, why. Nothing here is a new observation: the entries of section 8 govern, and
where the restatement had to choose a reading it says so. D1-D4 are kept as worded in section 8
and only given their test form. R1-R55 are referred to, not restated.

**The simulated machine these statements assume** (the least a test needs; how it is built is
the test author's):
- device words as address -> value, with the read values the captures give where a word is read
  (a sequence where macOS polls); every access in one trace with its order, core, direction,
  address, width (R49) and value;
- per core, the system registers named in R59 and R65, as they stand at that core's final write;
- **a core's final write** = its write `CYC_OVRD_EL1` = `0x3000001` (R43); **the commit** = core
  0's final write, the last of the eight (R44, R64);
- **a reading of the hardware**: a value the machine takes by itself, with no write of macOS's.
  A test may model it; a test must not require the driver to write it.

**How firmly each rests** (section 8's marks, with counts): *all N* = observed as stated in every
capture that can show it, N of them; **[HV-CHANGED]** = rests on runs whose outcome the
instrument's change altered, or that reached their outcome with it in place; **[ARTEFACT, in every
power-down]** = the instrument's act, present in every power-down captured, so no power-down is
observed without it; *Reference* / *Documentation* / *Arm architecture* = used only to give a test
a model of hardware behaviour, never as the basis of a requirement; *Decision* = D1-D4.

**R5a. Stopping `dcp`, `dcpext`, `gfx-asc`, `ans`.** *All eight captures, 76 stops, no
exception.*
- Test: for each of the four, in the entry, in this order, on that coprocessor's block (section
  0): (1) send `0x00b0000000000201` on endpoint 0 (64-bit writes +`0x8800` = message, +`0x8808`
  = endpoint) and receive `0x00b0000000000201` on endpoint 0 (64-bit reads +`0x8830`,
  +`0x8838`), each receive after a 32-bit read of +`0x8114` with bits 20-23 non-zero; (2) for
  `dcp` and `dcpext` only, for e = `0x20`, `0x21`, ... `0x2c` ascending: send
  `0x00a4000000000000` on e, receive `0x0087000000000000` on e before the next send; (3) send
  `0x0060000000000201`, receive `0x0070000000000201` (endpoint 0); (4) 32-bit: R +`0x8114` = v,
  W +`0x8114` = v with bit 0 cleared, R +`0x48` (`0x2e`), R +`0x44` (`0x10`), W +`0x44` = 0; (5)
  after every `dcp` / `dcpext` stop, the translator writes of R5a (`dart-dcp` / `dart-dcpext`
  +`0xfc`, s = 0 then 15); (6) only then the coprocessor's domain words off (R7, by R56).
- Not testable as written: a coprocessor that does not answer, answers otherwise or reads
  +`0x48` other than `0x2e` (macOS never met one). D3 decides it (found stopped: send nothing;
  silent: a bounded wait, then step 4); the bound is not observed, so a test can check that the
  wait ends, not its length. `dcp`'s endpoint-`0x37`/`0x02` traffic before its E1 stop: payloads
  not in the log.

**R56. Turn-off of a power-domain word.** *D-I, every instance; the exceptions named.*
- Test: for every write that requests 0 (bits 0-3 written 0), with v = the value the same core
  read from that word just before: if v bit 28 is clear, one write (v & ~`0x3ff`) | `0x3f0`; if
  set, first v & ~((1<<28) | (1<<9) | (1<<8)), then a read v2 (the simulated word now reads bits
  24-27 `0xf`, bits 4-7 `0xf`, bit 28 clear), then (v2 & ~`0x3ff`) | `0x3f0`, except **RMX,
  whose second write is the constant `0x300`**. After each turn-off write, a read of the word
  (the simulated word reports state 0 at once). Children before parents: DISP0_CPU0, DISP0_FE,
  RMX; DISPEXT_CPU0, DISPEXT_FE (1.9).
- Not testable as written: a wait for state 0 (the first read always reported 0; *Reference:*
  Aurora's comment that macOS waits for (word & `0x8ff`) == 0); a word reading state 4 with bit
  28 set (open question 43); RMX's second write after any read but `0x0f0003ff` (Linux's RMX
  reads `0x1f0000ff`; not observed); a turn-off of the nine never-written domains (none observed;
  D4 decides the first port's seven).

**R57. The wake's domain writes.** *D-I.*
- Test: (i) each word that reads request 4 at the wake (R57's list) is written once
  (v & ~`0x3ff`) | `0x340`, and the next read ends in `0x200` (state 0, bit 9 set); (ii) each
  turn-on takes a form of 4.3 by the value read: from request 0, v with bits 0-11 cleared
  (DISP0_CPU0, DISPEXT_CPU0: `0x0f040000`), that + `0xf`, reads until bits 4-7 read `0xf`, that
  + bit 28; from request 4, v with bits 8 and 9 cleared, that with bits 0-3 = `0xf`, reads until
  on, that + bit 28 (form 5); words already on: 4.3 form 6; (iii) no write puts request 4 over a
  word whose request is 0.
- Not testable as written: which state each word goes back to (R40 rests on one domain in one
  capture); D1 decides it (the request the entry found).

**R58. `dcp` and `dcpext` at the wake.** *All eight.*
- Test: none for a driver. macOS restarts, boots and stops both at every wake; D2 decides the
  driver does not restart them. R58's invariant (never a display coprocessor stopped with its
  domains on) cannot hold together with D1 and D2 for DISP0_CPU0 and DISPEXT_CPU0 (D2 says so);
  tests follow D2: no message to either and no write of their +`0x44` at the wake.

**R59. Nothing pending at a core at its final write.** *All fifteen power-downs had no virtual
IRQ or FIQ pending at any core's final wait ([ARTEFACT, in every power-down]: the instrument's
clearing); `ISR_EL1` read 0 at every core's final write in six (K, L, `det19b`, `det21`,
`det23`, `det24`; macOS's state under the instrument's settings); a virtual FIQ left pending: no
power-down, four of four [HV-CHANGED]; every guest timer left enabled with nothing pending:
power-down, two of two [HV-CHANGED].*
- Test: at each core's final write, the simulated core's `ISR_EL1` is 0; and, if the kernel uses
  `HCR_EL2`'s virtual interrupts, `HCR_EL2` bits 7 (VI) and 6 (VF) are 0. `ISR_EL1` is the
  simulated machine's model; the sources it must model are (*Arm architecture* and
  *Documentation*, not observations): (1) any timer of that core with ENABLE 1, IMASK 0 and
  ISTATUS 1 (the condition met) asserts its interrupt, which on these cores goes straight to FIQ
  (Asahi page "AIC"); (2) an IPI pending at the core (`IPI_SR_EL1` bit 0; macOS acknowledges by
  writing 1, R45); (3) a performance-counter interrupt (macOS's values R65: `PMCR0_EL1`
  `0x7003400`, `PMSR_EL1` 0); (4) an interrupt-controller line unmasked and asserted (macOS
  masks all, R36, R65). The test passes when, for every core at its final write, none of (1)-(4)
  holds. A test must not require the timers to be disabled.
- Not testable as written: a timer that is enabled, unmasked and not yet fired at the final
  write and falls due after it (allowed by the above; observed only for one core each in
  `det19b`, `det21`, due 62-63 ms later, followed by a power-down [HV-CHANGED]; nothing to model
  its later effect on); a physical pending interrupt at a final wait (in no run on either
  system: "pending, so no power-down" is carried over from the virtual FIQ, an inference). The
  IPI case is real for macOS: in `det23` an IPI to core 3 was not yet taken at its final write
  (E7, the instrument cleared it).

**R60. SPMI status acknowledged before the cores go down.** *macOS's commands: D-J, every
command (R38, R60); the acknowledgement after the last command of all: [ARTEFACT, in every power-down];
`0x23d0d9378` 0 at the commit: six (K-`det24`).*
- Test: every SPMI command to the power chip's controller `0x23d0d9000` is, in this order: W
  +`0x338` = 0; the command word(s) to +`0x304`; R +`0x378` (the simulated word reads 1 once the
  command is done; macOS reads it twice); W +`0x378` = 1; the reply read from +`0x308`; W +`0x338`
  = 1. After the last SPMI command of the entry and the commit (the driver's and any record the
  glue writes), a W +`0x378` = 1 comes before the first core's final write, and the simulated
  +`0x378` reads 0 at the commit. *(Round 14c, gap GL1.)* With `probe=1` the probe record comes
  after the first core's final write (D8 (e)); its own W +`0x378` = 1 then comes after it and
  before core 0's final write.
- Firmness of the last part: no power-down was captured without it; the two runs without the
  instrument's last write woke early (0.65 s, 1 s), they did not stay up. Not testable: whether
  the order of +`0x378`'s write against +`0x308`'s read matters (one order seen).

**R61. Watchdog 1 armed at the commit.** *Not a step macOS takes; the instrument's, in seven
power-downs (J, K, L, `det19b`, `det21`, `det23`, `det24`), none prevented.*
- Test (only if the driver or glue arms it): W `0x23d2b001c` = 0, W `0x23d2b0010` = 0, W
  `0x23d2b0014` = N x 24,000,000, W `0x23d2b001c` = 4, after every other device write of the
  commit and before **the first core's** final write *(round 14c, gap GL1; was "before core 0's
  final write")*: no device access between them and it (D8 (b)). The one write after them: with
  `probe=1`, the glue's probe record on core 0 after cores 1-7's final writes and before core
  0's (D8 (e)).

**R62. Watchdog 2 and the always-on words.** *Writes: every detached capture (D-K, and L,
`det19b`, `det21`, `det23`, `det24` by `r11-checks.txt` part 7); the hardware's state: five
([L], L-`det24`).*
- Test: (a) in the entry the driver writes no word of watchdog 2 (`0x23d2b0020`, `0x23d2b0024`,
  `0x23d2b002c`) and neither `0x23d2b8028` nor `0x23d2b8040`; its only writes to the watchdog
  page are R15's five, by core 0, in this order: `0x23d2b0000` = 0, `0x23d2b0010` = 0 (E3, about
  T-0.44 to -0.47 s); `0x23d2b8008` = 0, `0x23d2b800c` read (0) and written 0, `0x23d2b000c` = 0
  (E5, about T-34 to -37 ms); (b) R22's W
  `0x23b718004` = 0 comes before the first W `0x23d2c4000` = 1 (R24), with only R23's SIO,
  SIO_BUSIF, SIO_CPU accesses between; (c) a reading of the hardware: by the first W
  `0x23d2c4000` = 1 watchdog 2 reads bite `0x7270e00`, control 4, its count started 1.3-7.5
  microseconds after W `0x23b718004` = 0; `0x23d2b8028` `0x1000000`, `0x23d2b8040` `0x20`; and
  `0x23d2c4000` reads 0 after that first write. A simulated machine may make (c) follow W
  `0x23b718004` = 0; a test must not require the driver to write any of it.
- Not testable as written: R15 is [UNKNOWN] (the instrument's own use of watchdog 0 may shape
  those writes, A9); what arms watchdog 2 and sets bit 24 is not observed, so no test can check
  that a driver causes (c); the glue may read it (open question 56).

**R63. Wake-source masks and always-on clock words.** *No write: every detached capture's
logged window (D-K; L, `det19b`, `det21`, `det23`, `det24` by `r11-checks.txt` part 7); the
values at the commit equal the awake ones: K, and the same five values at the commits of L,
`det19b`, `det21`, `det23`, `det24` (`r7-det*-core-state.txt`, `r8-det2[34]-core-state.txt`).*
- Test: no write by the driver to `0x23d004008`-`0x23d004018` in the entry or at the commit.
- Not testable as written: their values (Linux's are not read, open question 58); the clock
  words `0x23d240024`, `03c`, `048` (Linux's differ before the entry, 4.4 row 7, and no write of
  macOS's to them is observed to copy).

**R64. Every core goes down; none is kept running.** *All fifteen power-downs; a core kept
running after the commit: no power-down, two of two [HV-CHANGED].*
- Test: each of the eight cores makes its final write once; core 0's is the last and follows
  core 0's last device access (R39, R44); after a core's final write that core makes no access.
- Not testable as written: the time window (all eight within 33 microseconds in D-J, about 0.3
  ms in K-`det24` under the recording; time in a simulated machine is not the machine's).

**R65. Each core's own registers at its final write.** *macOS's own values, six captures (K, L,
`det19b`, `det21`, `det23`, `det24`), the same in all; never varied, so which are needed is not
observed.*
- Test: at each core's final write: `ACC_OVRD_EL1` written `0x1800101526076207` by that core,
  then `CYC_OVRD_EL1` read (`0x2000000`) and written `0x3000001` (R43); `IPI_SR_EL1` 0 after its
  write of 1 (R45); `PMCR0_EL1` `0x7003400`, `PMSR_EL1`, `UPMCR0_EL1`, `UPMSR_EL1` 0; `PSTATE`
  D, A, I, F set; `IPI_CR_EL1` `0x600`; and the interrupt controller, read once: `0x23b104180` +
  4k (k = 0..27) `0xffffffff`, `0x23b104000` + 4k 0, `0x23b102024` `0x80000001`, `0x23b105028` +
  `0x80`k (k = 0..10) `0x80000001`, `0x23b105004` + `0x80`k 0 (R36's round-9 note).
- Not testable as written: macOS's timer values (`CNTP_CTL_EL02` `0x6`, the virtual timer
  enabled, `CNTKCTL_EL12` `0x4f`) are a kernel at EL1's; for a kernel at EL2 the timer
  requirement is R59's rule, not these values. `IPI_CR_EL1` `0x600`: a value to compare, its
  meaning not established.

**R66. The CPU start/stop block.** *R11's writes: all fifteen; the commit values: five ([L],
L-`det24`).*
- Test: in the entry each of cores 1-7 writes its own bit (1 << n) to `0x23b754000` (32 bits)
  once, before core 0's first quiesce action (R11; the order 4, 1, 5, 2, 3, 6, 7 in G and L, not
  claimed fixed); core 0 writes none; no write to `0x23b754004`-`0x23b75401c` in the entry;
  at the commit the simulated +`0x0` holds `0xfe` from those writes. +`0x4` = `0xfe` at the
  commit is a reading of the hardware.
- Not testable as written: what sets +`0x4` (no write observed; open question 61).

**R67. The power-gate header.** *Entry: all fifteen; macOS's commit value: five; the wake: all
fifteen.*
- Test: entry: core 0 R `0x23b71c080`, R `0x23b71c088`, W `0x23b71c080` = `0x80000000`, W
  `0x23b71c088` = `0x80000000`, immediately before R22's W `0x23b718000` = 0; no write to any
  other word of `0x23b71c000`-`0x23b71c08c`. Commit: **no test on `0x23b71c000`** (R69). Wake:
  after the poll of `0x23b718004` ends (R30), core 0 R `0x23b71c000`, W `0x23b71c000` =
  `0x80000000`, R `0x23b71c040`, W `0x23b71c040` = `0x80000000`, before any other core is
  started (R32); later R `080`, R `088`, W `080`, W `088` = `0x80000000`.
- Not testable as written: whether the wake writes are "set bit 31" or the constant (the reads
  never differed); what Linux does with the word set after its wake (Linux awake has 0).

**R68 and R69.** *[HV-CHANGED].* No test of their own. R68 is the basis of R59's test (and of not
requiring the timers off); R69 the basis of not testing `0x23b71c000` at the commit.

**D1-D4, as tests** (*Decision*; wording in section 8 unchanged): D1, at the end of the wake each
power-domain word the entry changed has the request it had when the driver's entry read it; D2,
no message to and no +`0x44` write of a coprocessor the entry stopped, at the wake; D3, per
coprocessor of R5a: found running, R5a's sequence; found stopped (+`0x44` 0), no message and no
write; silent, a bounded wait and then R5a step 4; domain found off, no access to its block;
D4, the seven first-port domain words read request 0 at the commit.

**Summary** (the full statements above):

| Req. | What a test checks | Rests on |
|---|---|---|
| R5a | the four coprocessors stopped by the exact message and register sequence | all eight, 76 stops |
| R56 | each turn-off write a function of the value read (three forms; RMX `0x300`) | D-I, every instance |
| R57 | wake: request-4 words by form 3; turn-ons by forms 4-6; never 4 over 0 | D-I |
| R58 | none for a driver (D2 governs) | all eight; conflicts with D1+D2 |
| R59 | at each final write: no timer fired-and-unmasked, no IPI, no counter or controller interrupt; VI/VF 0 | fifteen ([ARTEFACT, in every power-down]); six for `ISR_EL1` 0; [HV-CHANGED] 4/4 and 2/2 |
| R60 | every SPMI command bracketed; status written 1 after the last command, 0 at the commit | D-J; [ARTEFACT, in every power-down]; six |
| R61 | if armed: watchdog 1's four writes last | seven, the instrument's |
| R62 | no write to watchdog 2 or the two always-on words; `0x23b718004` = 0 before `0x23d2c4000` = 1; watchdog 2 armed is the hardware's | every detached capture; five |
| R63 | no write to the wake-source masks | every detached capture; six for values |
| R64 | eight final writes, core 0 last, no access after | fifteen; [HV-CHANGED] 2/2 |
| R65 | the per-core register values and the interrupt controller masked | six, macOS's own |
| R66 | cores 1-7 write their stop bits; nothing to +`0x4` | fifteen; five for the commit |
| R67 | entry: `080`, `088` only; wake: `000`, `040` set; commit: no test | fifteen; five |
| R68, R69 | none (bases of R59 and R67) | [HV-CHANGED] |
| D1-D4 | as stated | Decision |
| D5 | each candidate of 8.2 behind its own switch, off by default; (a)-(f) of D5 | Decision |
| D6 | *(revised round 14; round 14b; round 14c)* R16's or R22a's wait runs out (no other wait): no further entry step; no read added; each written word put back once, in reverse order of first writes (1.9's order for domains): domains by D1 (request 4 by form (4r)), other words read first to the value read, words never read first left as written; nothing put back in coprocessor blocks, SPMI, the CPU start/stop block, the watchdog block or the pair `0x23b718000`/`004` (no write of either after the wait, whatever C15 read); bounded put-back waits; failure returned, record names the wait: its word, and the kind and core of the wait's last read (32-bit read, core 0), not a put-back access's | Decision (round 13; ds20 C5 hung, L25); form (4r) from the always-on program's decode |
| D7 | *(revised round 14; round 14c; round 15b; round 15c)* glue, `wdt` = N: precondition, Linux's watchdog core not driving watchdog 1 (its `WDOG_ACTIVE` and `WDOG_HW_RUNNING` flags, read without device access; no driver bound: not driving; a driver whose state cannot be read: refusal; else -EBUSY, no device access in any callback of that sleep); R61's four writes as the glue's first device accesses of its sleep step, first in `begin` (before `begin`'s record and clock read, the offlining, any diagnostic read, record, trace mark, parking or `enter`) and again in the commit-point step, last before the first core's final write (the probe record after them with `probe=1`); disarmed as the glue's last device write on every way back to Linux (D6's failure, a `run_on` not answered whose core's release is answered, `snap=1`'s stop, `snap=4`'s return, any error, the wake; in `end` after Linux's abort before `enter`), except when a parked core's release is not answered (record, then panic, left armed, no return; the glue's panic notifier writes nothing on that panic); none without `wdt` | Decision (round 13); macOS [HV-CHANGED] 5/5 power-downs with the early arm (1.7g); L31; panics in the sleep step reset (ds10, ds11) |
| D8 | *(new round 14; round 14b; round 14c)* logic and glue: `c3_readings() -> [Option<u32>; 9]`, `None` until read in this `enter`, for after `enter` returns; the commit-point step called after R38's third write and C3 (iii), before the final writes, with the same nine as its argument; one record per step (`snap=2`/walk, else C3 with `cand_c3`, else 'W'), no glue access after the step but `probe=1`'s record after the first final write; C3 record: a 4-bit code per slot plus the latest odd value in part (f); on D6's return the glue writes the failure record, gives the cores back, then disarms watchdog 1 | Decision (round 14) |
| R70 | no write to `0x23b058000`, `0x23b05c000`, `0x23b060000`; only 32-bit reads of the first word of the last two pages | all captures, 48 boots (touch maps) |
| R71 | *(new round 15)* `pmp`'s start at boot: SRAM header, boot-argument block written back as read, translator, +`0x8114` = `0x20001`, +`0x44` = `0x10` | det33, det34b; the block `135map4`, the translator `det10` (one boot each) |
| R72 | *(new round 15)* RTKit start-up and endpoint `0x20`'s opening, word for word; `0x0020e00000550000` once at boot | det33 = det34b; det10, `135map4` by first touch |
| R73 | *(new round 15)* entry: `…550001`/`…540001`, `0x208` `0x63` answered, `…550000`/`…540000` before R4 for `pmp`; translator +`0xfc` after R5 | det33; det18, det23; det35-det37 |
| R74 | *(new round 15)* wake: PMP, PMS_SRAM, PMS on; twelve words; R6w; R55; R5w; short handshake (EPMAP echoed, no STARTEP, no buffers, no opening); `…630001`, both `…0001`, both `…0000` | det33; det18, det23; det35-det37 |
| R75 | *(new round 15)* none (basis of C18): the words change after `pmp`'s start and after the 0x55 word, not while it is dropped | [HV-CHANGED] 1 boot, 2 wakes dropped; 4 boots, 2 wakes sent |
| D3 (b) | *(new round 15c)* `sio`/`pmp` found stopped (domain on, +`0x44` bit 4 clear): no message, no write to its blocks or translator, no R6; at the wake no R6w, R55, R5w | Decision (changes the logic at `HEAD`, G26) |
| D9 | *(new round 15; (b) restated, (e) new, round 15c)* C18 is the kernel side's (`pmp` client); the logic has no C18 behaviour: with `pmp` found stopped no access to its mailbox, SRAM (but the twelve words) or translator, in entry or wake, also with PMS_SRAM `0x1000030f`; found running, section 8's R4-R6, R6w, R55, R5w; the translator the client's alone | Decision |
| D10 | *(new round 15; completed round 15c)* client: boot at probe, the word right after the opening; entry part before `enter`; wake part after `enter` returns, also on failure; no domain write at boot, buffers before any access, domain off or no buffer: no access, error; boot timeout: R5's register stop alone; entry timeout: register stop, translator, R6, sleep goes on; after a wake timeout: next entry stops without words; switch read per part, a part acts only after the part before it; LOG, type-8, type-4 words echoed while running, also in the wake's handshake | Decision |
| D11 | *(new round 15; completed round 15c)* endpoint `0x20` macOS's words (own IOVA, bits 0-31; one 16 KiB page); at boot only `…550000` after the opening, at once; no kdebug; every word sent by the client in macOS's start-up order, no RTKit library, no SET_IOP_PWR_STATE at boot; buffers: size x 4 KiB in 16 KiB pages, distinct, kept mapped; short handshake at the wake; bounds 1 s (6 s for `0x000200000023b549`); control page only R71 (e), R5, R5w | Decision |

### 8.2 Candidate requirements C1-C17 (round 12) and C18 (round 15)

**What these are.** The Linux driver now reaches its commit with every core clean at its final
write (L22, L23: no interrupt pending, no timer on and unmasked; R59 met as far as read) and the
SoC still stays up until an armed watchdog resets it (L21). Each entry below is an **observed
difference** between what macOS does or leaves at and before its commit and what the Linux
readings (section 12) show, which a driver could act on, written so that a test can hold a
driver to it behind its own switch (D5). **A candidate is not a requirement of section 8 and is
not claimed to be needed for the power-down**: none has been tried on the machine. The order is
the spec stage's judgment of how likely each is to keep the SoC up after Linux's commit; the
reasons cite the reference (*Reference*, `docs/reference/asahi-aurora-sleep-deep-dive.md`, other
chips) only to explain that judgment. Every requirement text rests on M1 observations of macOS,
and where a candidate's act is one macOS was never seen to make on that word, the entry says so.
*(Round 13.)* Several have since been tried on both systems; the table after the summary gives
the outcomes, and C3 and C5 are revised in their light.

**How the list was made.** Every word of L1's 118 (Linux ds13 before its entry against H's
commit), 4.2a's domain table, L15, L19, L20 and the new readings L21-L24, set against the
captures; for each candidate word, every logged access in A-I, including the page-touch map of
A's and B's boot (section 1.1), by this round's `r12_candidates.py` (`r12-candidates.txt`). Left
out, with the reason:
- differences an existing requirement already removes when a driver meets it: the display
  domains and coprocessors (R1, R5a, R7), the first port's seven domains (D4), the five clock
  muxes of R18; whether they are removed at Linux's commit is what the commit walk (L24) reads;
- words that vary under macOS or carry the instrument's values: `MCC.planeN+0x680`/`+0x684`
  (emulated, A5), `DCSn+0x500`, the guarded words' hardware values (A3), the cores' and clusters'
  domain words (which core reports on, L12);
- differences in the history bits 8 and 9 alone (PMS `0x1f0000ff` / `0x1f0002ff`, ATC0_COMMON),
  and the twelve SoC clock words and `0x23d240024` that differ in bit 8 alone (under macOS bit 8
  of such words changes with no write, R52: a reading of the hardware, not a value to write);
- words that macOS's own machine changes between awake and the commit with no write and that
  Linux holds at macOS's awake value (`0x23d240040`, `0x23d240314`): no write to copy; they are
  readings for the glue (open question 69);
- ANS2 (on at macOS's commit, off under Linux): a domain Linux has lower than macOS, with its
  coprocessor stopped in both; no reason found that it would hold the SoC up.

**The commit walk (L24).** 12 of the 118 words had arrived when this section was written
(indices 0, 1, 20, 21, 40, 41, 60, 61, 81, 137, 193, 249): the eight
`MCC.planeN+0x680`/`+0x684` words (varying, left out above) and **`DCS0-3+0x7b0` = 3 at Linux's commit** (C4). A candidate whose word reads
macOS's value at Linux's commit when the walk completes is moot; by D5 (d) its switch then makes
reads only.

**Where the Linux outcome points (judgment, not observation).** No Linux run since ds16 ended in
the reset 5-7 s after the commit with which every failed macOS run under the instrument ended
(4.4 row 12), and an earlier Linux driver did reach the always-on program's first step (L18; its
boot state was not read). The reading that would most narrow this list is open question 56:
watchdog 2 and `0x23d2b8028` just after the driver's write `0x23b718004` = 0. Armed there, the
always-on side started and something later holds it (C1, C3-C5, C8-C14, C16, C17 stay in
question); not armed, the step that starts it is not taken (C2, C6, C7, C15 first).

**Common to every candidate (test form, with D5).** Switch: a boolean module parameter
`cand_cN` (N = 1..17), default off. "Entry start": after D3's decisions on the coprocessors and
before the driver's first device write of the entry. Every access is 32 bits (R49). Domain
writes take the forms of section 4.3, R56 and R57 by the value read: turn-off of a bit-28-clear
word R56 form 1, of a bit-28-set word R56 form 2; turn-on from request 0 R57 (ii) (W v with bits
0-11 cleared, W that | `0xf`, read until bits 4-7 read `0xf`, then, where the entry says "with
bit 28", W that | bit 28); parents before children for a turn-on (1.9; W1-2c), children before
parents for a turn-off. "*Reading*" marks a state at the commit that the hardware, not the
driver's write, sets: a simulated machine may model it, a test must not require the driver to
produce it.

**C1. The secure enclave's power domain gated at the commit.** Switch `cand_c1`.
- *Observed.* SEP `0x23b700c00` reads **`0x1000230f`** (request `0xf`, bit 28 set, bits 4-7 and
  24-27 0, bits 8, 9, 13 set) with macOS awake (G, H, I, before the detach and I's awake-extra)
  and at every commit read (G, H, I; 4.2a); macOS reads it once in the entry (T-0.0225, the same
  value) and writes it only at the wake, `0x1000200f` (W1-2c, all eight; `r12-candidates.txt`).
  macOS sends `sep` no power message and never touches its +`0x44`/+`0x48` (R4, section 0). **[LINUX]** `0x1f0020ff`
  (bits 4-7 and 24-27 `0xf`, bits 8, 9 clear) before the entry (ds13, ds14, ds15; 4.2a).
- *Why a candidate.* Under macOS the enclave's domain is power-gated by its automatic power at
  every reading, awake included; under Linux it is fully on. *Reference* (2.2, T8140, measured):
  "a commit with it running never returned" (the enclave self-gates after a control message); of
  the reference's stall causes this is the one whose outcome, no return and no reset at 5 s,
  matches Linux's (L16, L21).
- *Requirement.* Place: after the last coprocessor stop of R4/R5/R5a and before R16. R SEP's
  word; if bits 4-7 are not 0: R56 form 2 (W v with bits 28, 9, 8 cleared; R until bits 4-7
  read `0xf`, bounded; W (v2 with bits 0-9 replaced by `0x3f0`); R until bits 4-7 read 0,
  bounded). At the commit: SEP bits 0-3 = 0 (the driver's write) and bits 4-7 = 0 (*reading*).
  Wake: D5 (f), by D1 the request `0xf` with bit 28, the value of macOS's W1-2c write
  `0x1000200f`.
- *Not observed.* macOS never lowers SEP's request: its state 0 comes with request `0xf`. A
  request-0 write to this word, and what the enclave does then, are in no capture; the form is
  the one macOS uses on other bit-28 words (R56). The device tree flags SEP "critical", "on"
  (`pmgr-devices.json`); *Reference*: Aurora's t8103 tree marks it "Locked on". So the target
  state is macOS's, the act is the spec stage's choice.

**C2. The power manager's four sub-blocks on before R22a.** Switch `cand_c2`.
- *Observed.* `0x23b748000`, `400`, `800`, `c00` read **1** before every entry and are stopped
  in R22a (all eight); at every wake they read 0 and macOS writes them 1 in the order `000`,
  `c00`, `800`, `400` (W1-2h, all eight). **At boot (A, B: the first access to the page in the
  page-touch map, t 1.048 / 1.131 s) `0x23b748000` reads 0**: macOS's kernel turns them on
  during boot as at the wake (the boot write itself is below the map's resolution). With them on
  the status words read low byte 1 (I's awake-extra: `0x4d4d01`, `0x404001`, `0x1`,
  `0x404001`), at the commit `0x515100`, `0x494900`, 0, `0x494900` (R22a). `0x23b720030`,
  `034`, `044`, whose repeated byte equals the status words' bytes (L3), read `0x014d514d`,
  `0x01404940`, `0x01404940` awake and `0x01515151`, `0x01494949`, `0x01494949` at the commit
  (R52); macOS never accesses that page (no touch-map record, no access in A-I).
  **[LINUX]** the four control words read 0 (L3), the status words `0x616100`, `0x7f7f00`, 0,
  `0x6c6c00`, and `0x23b720030`/`034`/`044` `0x01616161`, `0x017f7f7f`, `0x016c6c6c` before the
  entry (L2; ds13, ds15). An earlier driver's entry timed out in R22a's wait on `0x23b7487e0`
  (evidence ds8).
- *Why a candidate.* R22a is the step straight before R22's write `0x23b718004` = 0, after which
  the always-on side's first observed step follows within 1.3-7.5 microseconds (R62). Under
  Linux R22a meets four sub-blocks in the state macOS's kernel leaves only before it has
  finished booting, and the words tied to their status hold higher values. *Reference* (2.1,
  T8140): the commit parks "DVFM" and brings "the SoC perf word" to its sleep state before the
  commit word; correspondence not established.
- *Requirement.* At entry start, for `0x23b748000`, `c00`, `800`, `400` in this order: R; if 0:
  W 1. Then for their status words in the same order (`0x23b7483e0`, `fe0`, `be0`, `7e0`): R
  until the low byte reads 1, bounded. Then the entry as section 8 has it: at R22a each control word reads
  1 and R22a stops it (W 0, R its status until low byte 0). At the commit: the four control words
  0 (R22a's writes); the status words' low bytes 0 and `0x23b720030`/`034`/`044` are *readings*
  (macOS's commit values above, for the glue to record). Wake: macOS's own (W1-2h); nothing put
  back.
- *Not observed.* What the sub-blocks do under Linux once on; whether their status reaches low
  byte 1 after a write of 1 (macOS reads no status word at the wake): the wait is the spec
  stage's choice.

**C3. The SoC and memory performance words: no write, read at three places (revised round 13).**
Switch `cand_c3`.
- *Observed (round 12).* `0x23b058000` = **`0x333`**, `0x23b05c000` = **`0x444`**, `0x23b060000` =
  **`0x222`** with macOS awake and at every commit read (G, H, I; appendix B). macOS never
  accesses `0x23b05c000` or `0x23b060000` (no record in A's and B's boot touch map, no access in
  any full log A-I), nor `0x23b058000` in any full log (its page's first access at boot is a read
  of `0x23b058068`). **[LINUX]** `0x444`, `0x666`, `0x333` (ds13, ds15; L2).
- *Observed (round 13; `r13_c3_boot.py`, `r13_c3_words.py`, `r13_recfg.py` and their `.txt`).*
  - **Values over time.** Every reading of either system shows three equal hexadecimal digits in
    bits 0-11 and 0 above. **Before any operating system** (the m1n1 proxy,
    `var/commit-state/m1n1-proxy-wide.json`, 2026-11-16 23:48, one reading): `0x444`, `0x666`,
    `0x333`, Linux's values. **macOS awake** at the login window, 192-227 s after the
    instrument's start: `0x333`, `0x444`, `0x222` in every awake snapshot (85: 35 "pre-full", 30
    "pre-detach", 20 "awake-extra"). **At every commit read** (15 detached captures: G-L, `det19b`, `det21`,
    `det23`, `det24`, `det26`-`det28`, `det30`, `det31`; and 3 "last-cpu" snapshots): the same. **At every wake, before macOS
    runs** (the instrument's wake snapshot, 22 wakes: A, B, `135full1`, `135chain2`, D, E, F, G-L,
    `det19b`, `det21`, `det23`, `det24`, `det26`-`det28`, `det30`, `det31`): `0x333`, **`0x555`**, **`0x333`**. No reading later in the
    same boot (the snapshots stop there and macOS does not read the words).
  - **Accesses:** none by any core (R70). So the change from the boot values to macOS's during
    the first 192 s of macOS's boot (`0x444` -> `0x333`, `0x666` -> `0x444`, `0x333` -> `0x222`),
    and the change from the commit values to the wake values across each sleep, are made by
    something other than the application processors: a coprocessor, the always-on side or the
    hardware. Which, and when within those 192 s, is not observed.
  - **macOS's state around them** (the agents the *Reference* names as voters). `pmp`: macOS's
    kernel reads its +`0x44` = **0** (not running) 2.0-2.9 s after the instrument's start (the
    page's first access; `det18`, `det29`, A, `135map4`), and writes its mailbox
    (`0x23bc08800`/`808`, endpoint `0x20`, messages such as `0x20e00000640000`) from 5.2 s (A) or
    24.2 s (`det18`) on (the touch map's first access per 5 s epoch, so the earliest is not
    resolved); `pmp` runs with macOS awake and is stopped in every entry (R4, R5). The words keep
    macOS's values through the entry's stops of `pmp` (R4, R5) and of the GPU's coprocessor
    (R5a) and the cores' power-down: equal awake and at the commit in every capture. The CPU
    clusters' performance pages (`0x210e20000`, `0x211e20000`) are left out of the full log from
    G on (A and B log them, from 192 s on only), so macOS's cluster requests at boot are not
    logged.
    **[LINUX]** The words did not move when Linux moved both clusters between their lowest and
    highest states (L27).
  - **The always-on program** (the lab's decode of its program memory:
    `var/recfg/t8103-recfg-decoded.txt`, `var/recfg/seq10-11.txt`, as in 4.4; documentation of
    the always-on block, not a capture; `r13-recfg.txt`). Its sleep sequence 0 ("AWAKE->AOP_DDR
    PRE"), straight after arming watchdog 2 for 5 s (the step R62 observes 1.3-7.5 microseconds
    after macOS's `W 0x23b718004` = 0), writes **`0x23b058000` = 3** and reads it until bit 31 is
    clear, then **`0x23b05c000` = 4** and reads it until bit 31 is clear, then parks clock words
    from `0x23b040154` down with `0x80100000`; later in the same sequence, after its wait on
    `0x23d2c001c` (`& 0xaa0` = `0xa0`), it writes `0x23b058000` = 2 and reads until
    (v & `0x80000f00`) = `0x200`, and `0x23b05c000` = 2, until (v & `0x80000700`) = `0x200`. Its
    wake sequence 4 ("S2R_AOP->AOP_DDR PRE") writes all three 0 and waits for bits 8-11 (8-10
    for the other two) = 0; sequence 7 ("AOP_DDR->AWAKE POST") writes tables at
    `0x23b058010`-`0x23b05818c`, `0x23b05c008`-`044`, `0x23b060008`-`044`, then `0x23b058000` =
    2 and `0x23b05c000` = 2, each with a bit-31 wait; sequence 10, the wake 4.4 relies on, has
    none of them (sequence 11's decode ends in an unreadable command and is not used). Every
    such wait is a retried read with a retry count of 255; what the program does when the count
    runs out is not decoded. By the decode, then, the program writes a target state into bits
    0-3 and waits on a busy bit 31 and a state field in bits 8-11 (8-10), and **macOS's awake
    values are already sequence 0's first targets** (3 and 4) while Linux's (4 and 6) are not.
    The words `0x23b058068`, `080`, `098` that macOS reads at boot and at every wake hold the
    values sequence 7 writes there (`0x51100000`, `0x61210000`, `0x9a420000`).
  - *Reference* (2.1 steps 5-6, 2.2, 3.8; other chips): "SoC perf word (clk-perf word 0) to
    state 3. State is bits [11:8], busy is bit 31"; "DCS to state 4 via state 6"; T8140's DCS
    block lies at its power manager's base + `0x5c000` (section 3 of the reference, AON block
    map), the offset of `0x23b05c000` in the M1's `pmgr reg[2]`; on T8132 "macOS's firmware
    reaches DCS 4 and perf state 3 with no CPU write"; T8112: with the PMP running "DRAM and
    fabric stay at idle unless votes raise them". Correspondence by offset, layout and values
    only.
  - **[LINUX]** Before the entry `0x444`, `0x666`, `0x333` (L1, L2, L27). **At an earlier
    driver's commit, under the instrument, `0x333`, `0x444`, `0x222`** (L28: runs lx12, lx13,
    lx14, lx17, in runs of that driver whose bare-metal counterparts took the always-on
    program's first step, L18). At the round-8 driver's commit: not yet read (the commit walk
    reaches the three at positions 67-69, L24). **ds20 with `cand_c3`** (the round-12
    requirement: at entry start W `0x333`, `0x444`, `0x222`, each followed by a bounded wait for
    that value): the entry did not reach its commit and the M1 stayed dark; the record holds
    'a' only (armed; no failure recorded), so where among C3's accesses it stopped is not known
    (L25). **[HV-CHANGED]** macOS with Linux's values written in by the instrument at the start
    of E1: no commit, twice (1.7g).
- *Who sets them, as far as observed.* **Observed:** macOS's application processors never write
  them (R70); they change with no logged access during macOS's boot and across each sleep; the
  always-on program writes them in its sleep and wake sequences (decode); under an earlier Linux
  driver they had reached macOS's values by Linux's commit. **Not observed:** what lowers them
  during macOS's boot (a coprocessor such as `pmp`, the always-on side, or the hardware on a
  vote), when, and what leaves `0x555` and `0x333` at the wake. The reading that would settle it
  is open question 70.
  *(Round 15; 1.7h, R75, L29, L30.)* **Observed:** each change comes in the first 250 ms sample
  after a `pmp` event: `0x444/0x444/0x444` after `pmp`'s start and opening (five boots);
  `0x333/0x444/0x222` after `0x0020e00000550000` with `pmp` running (four boots, two wakes), never
  while that word was dropped ([HV-CHANGED]: one boot, two wakes, 060000 left at `0x444`); in the one
  entry without it, 058000 after `…540000` and 060000 after `pmp`'s stop, so the commit had macOS's
  values and the chip powered down; `0x333/0x555/0x333` at every wake with `pmp` stopped. The earlier
  Linux of L28 had started `pmp` and sent `…550000` 0.25-0.37 s before those commit snapshots (L30);
  the stock kernel never starts it (L29). **Still not observed:** what writes them (`pmp`, the
  always-on side on its behalf, or the hardware) and whether their values at the commit matter. The
  way to macOS's values that the readings show is `pmp`'s: candidate C18. C3's requirement (no
  write; the nine reads) is unchanged; with C18 on its reads say whether the words follow.
- *Why still a candidate.* The always-on program's sleep sequence begins by moving the first two
  words to 3 and 4 and waiting on their busy bit, a wait with no observed way out. Under macOS
  that is no change; under Linux it is a change of one and two steps (4 -> 3, 6 -> 4), made by
  the program after the trigger. Whether that step completes under the round-8 driver is not
  read (open question 71). Every write of these words by an application processor so far, in
  either system, was followed by an entry that did not reach its commit (three runs).
- *Requirement (revised round 13; replaces the round-12 write, which is withdrawn).* **No
  write** (R70). With the switch on, the driver reads the three words, 32 bits each, in the order
  `0x23b058000`, `0x23b05c000`, `0x23b060000`, at three places: (i) entry start; (ii)
  immediately after R22's write `0x23b718004` = 0 and before R24's first write of `0x23d2c4000`;
  (iii) at the commit point, before the cores' final writes. It hands the nine values, in that
  order, to the glue for its record. No wait, and nothing else changes. With the switch off,
  none of these reads. Wake: nothing (nothing was written).
  *(Round 14, gaps Z9, Z1.)* The places, exactly: (i) as 8.2's "entry start", with D5 (c)'s
  ascending order among candidates there; (ii) **core 0's first three device accesses after its
  write `0x23b718004` = 0**, before any other access (R23's SIO accesses follow them; no other
  candidate has a place there); (iii) **after the entry's third and last write of `0x23d2c4000`
  (R38) and before the logic calls the glue's commit-point step (D8 (b))**, so before every core's
  final write, with no other access of the logic's between that write and the call (R39: macOS
  makes no device write after R38; reads are not excluded there). The test author's reading of
  (ii) stands; that of (iii) ("after the entry's last write of `0x23d2c4000` and before the first
  core's final write") stands and is narrowed to before the commit-point step. "Hands to the
  glue" is D8 (a): `c3_readings`, slots in the order (i), (ii), (iii), `None` for a read not made
  in this `enter`; *(round 14b, gap Z13)* inside the commit-point step the same nine come as the
  step's argument. *(Round 14c, gaps GL2-GL4.)* The record the glue makes of them is D8 (f) (a
  4-bit code per value, the latest value of another form in part), made once, in the
  commit-point step, only with the switch on, and standing unless `snap=2`, the commit walk or
  `probe=1` is also set (D8 (b), (e)).
- *Not observed.* Whether bits 0-3 are the only field a write sets; what a write by an
  application processor does to the hardware (the three runs that made one did not reach a
  commit, and none was read afterwards); what the program does when its wait runs out; who sets
  the words under macOS (open question 70).

**C4. The DRAM controllers' `+0x7b0` at 0.** Switch `cand_c4`.
- *Observed.* DCSn+`0x7b0` (`0x2002007b0` + n x `0x40000`, n = 0..7) read **0** in every
  snapshot of every capture, awake and at the commit; **macOS never accesses them**, not even at
  boot in A and B, where the memory-controller range is logged access by access from the start
  (1.1). The DCS domain words read state 0, 4 or `0xf` with bits 8 and 9 set at macOS's commit
  and awake (`0x1000030f`, `0x1400034f`, `0x1f0003ff`, [VARIES]; 4.2a, R46). **[LINUX]** **3** on
  all eight before the entry (ds13, ds15) and **at Linux's commit for DCS0-3** (L24; the walk
  had not reached DCS4-7); the eight DCS domain words `0x1f0002ff` before the entry (state `0xf`,
  bit 8 clear).
- *Why a candidate.* The only one of the 448 DRAM-controller words read that differs between the
  systems (same on all eight channels and two boots, and still there at the commit); and the DCS
  domain words show the channels gating under macOS and not under Linux. *Reference* (2.2,
  T6040, measured): the engine expects each DCS to gate itself after self-refresh, which needs a
  DCS dynamic power-gate setting macOS makes at boot and after every wake; Linux did not make it
  and "the engine waited for good on the first DCS pair power gate". Which M1 word is that
  setting is not known; `+0x7b0` is the only one the readings offer.
- *Requirement.* At entry start, for n = 0..7 ascending: R DCSn+`0x7b0`; if not 0: W 0. At R16's
  first write and at the commit each reads 0. The DCS domain words at the commit are *readings*
  (macOS's values above). Wake: D5 (f), the value read written back after R31.
- *Not observed.* Any write to the word; what 3 means (no t8103 source names it). Whether the
  DCS domain words then gate under Linux.

**C5. The clock-gated (request 4) domains at request 0, only with PMS and the SIO family on
(revised round 13).** Switch `cand_c5`.
- *Observed (round 12).* SOC_SPMI0, SOC_SPMI1, SOC_SPMI2 (`0x23b700118`, `120`, `128`),
  PMS_FPWM0-4 (`0x23b700148`-`0x23b700168`, stride 8), AFT0 (`0x23b7001a8`), DEVC0_IVDMC
  (`0x23b7001b0`), FPWM0 (`0x23b7001d8`), FPWM2 (`0x23b7001e8`): at **every wake** each reads
  request 4 (`0x0f000244`, `0x244` or `0x344`) and macOS writes it by R56 form 3 ((v with bits
  0-9 replaced by `0x340`): `0x0f000340`, `0x340`), reading `..200` after (R57, all eight); with
  macOS awake and at every commit read they request 0 (`0x0f000200`, `0x200`; 4.2a).
  **[LINUX]** request 4 before the entry: `0x0f000244`, `0x244` (ds13-ds15; L15).
- *Observed (round 13; `r13_c5_domains.py`, `r13-c5-domains.txt`: the 18 detached captures D-L,
  `det19b`, `det21`, `det23`, `det24`, `det26`-`det28`, `det30`, `det31`).* macOS's application processors never access the twelve in
  any entry. They are lowered at every wake only, by core 0, at W+0.0138 to W+0.0141, in one
  order, descending address: FPWM2, FPWM0, DEVC0_IVDMC, AFT0, PMS_FPWM4, 3, 2, 1, 0, SOC_SPMI2,
  1, 0; each R `..244` (FPWM0, FPWM2: `0x344`), W (v & ~`0x3ff`) | `0x340`, then three reads of
  `..200` (state 0 at the first read, 3 microseconds after the write). **What comes before it,
  in all 18:** the wake snapshot (before macOS runs) has SIO_BUSIF, SIO, SIO_CPU `0x0f0003ff`
  (request and state `0xf`) and PMS `0x0f0002ff`; macOS then turns PMS on with bit 28 (R
  `0x0f0002ff`, W `0x0f0000ff`, R, W `0x0f0000ff`, R, W `0x1f0000ff`; W+0.0135) and SIO_CPU the
  same way (W+0.0137), and only then lowers the twelve. So the only lowering observed is made
  with PMS (the parent of PMS_FPWM0-4, 1.9) and SIO_BUSIF, SIO and SIO_CPU on.
  The always-on program (decode, as in C3): its wake sequence 10 turns SIO_BUSIF and SIO on
  (request `0xf`, waits for state `0xf`) and writes FPWM0 and FPWM2 `0x244` (request 4, waits for
  state 4); its sleep sequence 0 writes FPWM0 and FPWM2 0, SIO_CPU `0x80000000`, SIO 0 and
  SIO_BUSIF 0, each followed by a wait for bit 11 clear; it writes none of the other ten. So
  FPWM0's and FPWM2's request 4 at the wake is the program's; the other ten's is written by
  nothing logged or decoded. **[HV-CHANGED]** With the twelve put at request 4 7.55 s before T
  and left there to the commit, macOS powered down and woke (`det30`, 1.7g).
  **[LINUX]** PMS `0x1f0000ff` (on, as macOS awake); SIO_BUSIF, SIO, SIO_CPU `0x0f000200`
  (request 0) before the entry (L15). **ds20 with `cand_c5`** (the round-12 requirement, at entry
  start): a wait ran out on a 32-bit read of SIO_BUSIF `0x23b7001c0` by core 0, and the M1 then
  hung instead of returning to Linux (L25); which of the driver's steps made that wait is not in
  the record.
- *Why still a candidate (weaker).* The twelve at request 4 did not stop macOS's power-down
  (`det30`). Kept because macOS's commit has them at request 0 and, once the SIO family is on, the
  change is the one macOS makes at every wake.
- *Requirement (revised round 13; replaces the round-12 one).* Place: immediately after C12's
  turn-ons when `cand_c12` is on; otherwise at entry start. First R PMS, SIO_BUSIF, SIO,
  SIO_CPU; **if any of them is not *on* by the round-14b gate below, the candidate makes reads
  only** (each of the twelve read once, no write) and the entry goes on. *(Round 14b, gap Z11;
  replaces "does not read bits 4-7 = `0xf`".)* Otherwise, for each of the twelve in
  macOS's wake order (FPWM2 `0x23b7001e8`, FPWM0 `0x23b7001d8`, DEVC0_IVDMC `0x23b7001b0`, AFT0
  `0x23b7001a8`, PMS_FPWM4-0 `0x23b700168` down to `0x23b700148`, SOC_SPMI2-0 `0x23b700128` down
  to `0x23b700118`): R; if bits 0-3 = 4: W (v & ~`0x3ff`) | `0x340`; R until bits 0-7 read 0,
  bounded (macOS: at the first read); a wait that ends without it is D5 (e): the entry goes on.
  At the commit each that was written requests 0 (state 0, bit 9: *reading*). Wake: D5 (f), by
  D1 back to request 4.
  *(Round 14, gap Z8.)* **The four reads are C5's own**: 32 bits each, by core 0, in the order
  PMS `0x23b700140`, SIO_BUSIF `0x23b7001c0`, SIO `0x23b7001c8`, SIO_CPU
  `0x23b7001d0`, as C5's first four accesses at its place, immediately before its first access to
  the twelve; C5 decides on these four alone, and no other read of the same words (section 8's,
  D3's, C12's, an earlier candidate's) stands for them. Reasons: C12's turn-ons, the step just
  before, change the SIO family, so only a read after them shows the state C5 acts on; and the
  record of a C5 run must show the state where C5 decided (in ds20 the step that read SIO_BUSIF
  is not known, open question 72). The order is a decision: parents first as the observed
  turn-ons have them (macOS's wake turns PMS on before SIO_CPU, W+0.0135 and W+0.0137; the
  always-on program's sequence 10 turns SIO_BUSIF on before SIO, `seq10-11.txt`; C12's
  parents-first turn-on is SIO_BUSIF, SIO, SIO_CPU). **C5's own
  wait, for a test:** no later step of the entry accesses the twelve (macOS's application
  processors never access them in any entry, 18 captures; none is among R25's domain writes), so
  a test may hold one of them at a non-zero state through C5's wait and the rest of the entry:
  its request at the commit is 0 (the write) and its state is a *reading*. Under D6 a word C5
  wrote is put back by form (4r) (D6 (c) 2).
  *(Round 14b, gap Z11.)* **C5's gate is on the request and the state together.** Each of the
  four is *on* when it reads bits 0-3 = `0xf` **and** either bits 4-7 = `0xf`, or bits 4-7 = 4
  with bit 28 set (`0x1400024f` is on, as are `0x0f0003ff`, `0x0f0002ff`, `0x1f0002ff`,
  `0x1f0000ff`). Anything else is not on: a request other than `0xf` (Linux's `0x0f000200`),
  state 0, or state 4 with bit 28 clear (seen only part-way through a turn-on, PCIE_REF
  `0x0f00024f` in 4.3 form 5). What the readings say:
  - *macOS, the four at its lowering:* at every wake in D-I PMS, SIO_BUSIF, SIO and SIO_CPU are
    each turned on by 4.3 form 6 (R `0x0f0003ff`, PMS `0x0f0002ff`; W `0x0f0000ff` twice; W
    `0x1f0000ff`) just before the twelve are lowered (`ps-forms.tsv`, G: W+0.0130 to +0.0132,
    the twelve from +0.0133); in the 18 detached captures PMS and SIO_CPU the same way at
    W+0.0135 and +0.0137. **No read of any of the four follows its bit-28 write** (each run in D-I
    ends with that write; for PMS and SIO_CPU none anywhere in the 18 detached logs,
    `r13-c5-domains.txt`, although in `det10` the power manager's pages are logged to W+20.7 s).
    So the state they had when macOS lowered the twelve is **not observed**; their last reads
    before it were state `0xf` with bit 28 clear.
  - *At rest with bit 28 set:* SIO_BUSIF, SIO, SIO_CPU read `0x1400024f` (state 4) with macOS
    awake (4.2a, idle), while the twelve request 0; at the commit SIO_BUSIF `0x1400024f`, SIO and
    PMS `0x1f0002ff` (SIO from 4 to `0xf` with no write of macOS's reaching it, 4.1, A3): with
    bit 28 set the state moves between 4 and `0xf` by itself. **[LINUX]** SIO_CPU `0x1400024f`
    awake (L14); after ds14's failed entry and its way back all three `0x1400024f` (evidence "Run
    ds14", `linux-ds14-bare-ps-words.json`; what wrote them is not in the record); PMS
    `0x1f0000ff` and the family `0x0f000200` before the entry (L15).
  - *Right after a turn-on with bit 28, on the M1 under Linux (C12's):* **not read** (C12 never
    ran alone; with the others, L26, the record has no domain word). Other words show both
    outcomes under macOS (`ps-forms.tsv`, D-I, every read between a write with bit 28 and the
    next write): the first read after the write already reports **state 4** on NUB_SPMI0 and
    NUB_SPMI1 (W `0x1400004f`, R `0x1400024f`, six wakes each) and on DCS words (W `0x1f0000ff`,
    R `0x1400034f`), and state 0 on DEBUG_AUTH, DEBUG_USB, NUB_SRAM, SEP, once NUB_FABRIC and
    some DCS reads (`0x1000030f`, `0x1000230f`, `0x1f00030f`); the I2C, SPI and UART words read state `0xf` in every read
    after their bit-28 write up to their turn-off. So with bit 28 a word can report 4 within
    microseconds of the write; which the SIO family does is not read for either system. The read
    that settles it: open question 74.
  Every reading of the four with request `0xf`, under either system, has state `0xf` or state 4
  with bit 28; the only reading with the family off has request 0 and state 0. Reasons for the
  gate (a decision): it keeps the round-13 purpose (no lowering with the parents off, ds20's C5,
  L25); macOS's own lowering followed a bit-28 write whose result it did not read, so "state
  `0xf` at the lowering" is not what the captures show; state 4 with bit 28 is the state the
  family rests in under macOS while the twelve are at request 0, which is the state C5 aims at;
  and C5 then acts with C12 on whether the hardware stays at `0xf` or drops to 4 after C12's
  bit-28 write (the suite's two machines both act; a family at `0x0f000200` reads only), so the
  unread value no longer decides whether C5 is tried. *Reference, not an observation* (section
  0): Aurora's driver counts a domain active when its state is `0xf` or its target is `0xf` with
  bit 28 set; the gate here is narrower (state 0 is not on) because no reading of these four with
  request `0xf` has state 0 (other words with bit 28 do, above: should the family read so after
  C12, C5 reads only, and its four reads in the record show it).
- *Not observed.* Request 4 lowered with the SIO family off (the one run that did, on Linux,
  timed out on SIO_BUSIF); request 4 lowered during an entry (only at the wake, R56 (c)); which
  of the twelve, if any, needs the SIO family or PMS on; *(round 14b)* the four's state right
  after a bit-28 write, and whether a lowering with the parents at state 4 differs from one at
  `0xf` (open question 74).

**C6. The power-gate header word `0x23b71c000` set before the always-on side's first step.**
Switch `cand_c6`.
- *Observed.* `0x80000000` with macOS awake and at every commit left alone (R67 (b), five); at
  every wake read 0 and written `0x80000000`, with `0x23b71c040` read and written `0x80000000`,
  before any other core starts (R67 (c), fifteen); **at boot (A, B: first access to the page in
  the touch map, t 0.934 / 1.063 s) it reads 0**, so macOS's kernel sets it during boot as well
  (the write itself below the map's resolution). **[LINUX]** 0 awake on two boots (L19, L20); not
  read before the entry or at the commit. [HV-CHANGED] cleared 0.28 ms before T, after R22 and
  after the always-on side's first step: power-down and wake (R69).
- *Why a candidate.* Linux never sets the word macOS sets at boot and at every wake. R69 cleared
  it only after the always-on side's first step had been taken (R62: that step follows R22 by
  microseconds, about 15.6 ms before the clear), so a word clear when that step starts, as under
  Linux, is untried (open question 67 (b)). *Reference* (2.2, T8140, T8132, T6050, measured): the
  per-cluster word whose bit 31 lets the boot cluster's cores power down; left clear by the
  loader; "the sleep never gets past its first sequence".
- *Requirement.* At entry start: R `0x23b71c000`; if bit 31 is clear: W `0x80000000`; R
  `0x23b71c040`; if bit 31 is clear: W `0x80000000` (W1-2a's form). At R22's W `0x23b718004` = 0
  and at the commit `0x23b71c000` reads `0x80000000`. Wake: macOS's own (R67 (c)); nothing put
  back.
- *Not observed.* What the word does on the M1; the boot write's place.

**C7. The always-on clock words `0x23d24003c` and `0x23d240048` enabled.** Switch `cand_c7`.
- *Observed.* **`0x81100100`** and **`0x82100100`** with macOS awake and at every commit read
  (G-I, K; R63). macOS never accesses the page `0x23d240000` (no touch-map record at boot, no
  access in A-I). **[LINUX]** `0x01101100` and `0x00101100` before the entry: bit 31 clear, bit
  12 set, bits 24-27 1 and 0 (L2; ds13, ds15).
- *Why a candidate.* Two always-on clock words that macOS has with bit 31 set have it clear under
  Linux, and the always-on side runs the program that, by the lab's decode, powers the chip down
  (4.4). Bit 31 as an enable is a reading of macOS's own clock writes (R18's `0x80100000`; the
  audio path's `0x86101000`, then `0x00101000` when audio stops), not a documented name. Under
  macOS `0x23d240040` goes from `0x02100100` to `0x01101100` (bit 31 clear, bit 12 set) between
  awake and the commit with no write (R52), so bit 12 set goes with bit 31 clear there too.
- *Requirement.* At entry start, each: R; if bit 31 is clear: W macOS's value (`0x81100100`,
  `0x82100100`). At the commit each has bit 31 set and bits 24-27 1 and 2 (bits 8 and 12:
  *reading*). Wake: D5 (f).
- *Not observed.* Any write to these words; which clocks they are.

**C8. `pmp` stopped at the commit whatever PMS_SRAM reads.** Switch `cand_c8`.
- *Observed.* macOS stops `pmp` in every entry (R4, R5; +`0x44` `0x10` -> 0) and then reads the
  196,608 bytes of R6; at the commit PMP `0x1f0f03ff` and PMS_SRAM `0x1f0003ff` (both on; R52),
  PMS_SRAM `0x1000030f` awake (request `0xf` with automatic power). **[LINUX]** PMP `0x1f0000ff`
  (on) and PMS_SRAM `0x0f000300` (request 0) before the entry; `pmp`'s +`0x44`, +`0x48` not read
  (skipped because PMS_SRAM reported state 0; L15); with the stock kernel `pmp` was running in
  ds4 (L4).
- *Why a candidate.* If PMS_SRAM's state decides that `pmp` is "found with its domain off"
  (D3), a running `pmp` is left running at the commit, where macOS's is always stopped.
  *Reference* (2.2, T8140, measured): "a commit with the PMP and SIO still running reset the SoC
  5.5 s later".
- *Requirement.* At R4/R5's place for `pmp`: whatever PMS_SRAM reads, if PMP (`0x23b7003d8`)
  reads bits 4-7 = `0xf`: R `pmp`'s +`0x48`, +`0x44`. If +`0x44` bit 4 is set: turn PMS_SRAM on
  with bit 28 (macOS's awake request) if it reads request 0; then `pmp` as D3 has it for a
  coprocessor found running (R4's exchange, R5's stop; silent: bounded wait, then R5's register
  stop), then R6. If bit 4 is clear: no message. At the commit `pmp`'s +`0x44` bit 4 is clear.
  Wake: R5w, R6w for `pmp` if the entry stopped it (section 8); PMS_SRAM by D1.
  *(Round 15; C18, D9.)* With `cand_c18` on, the `pmp` client has stopped `pmp` and made R6 before
  `enter` (D10 (b)): C8 then reads PMP on, +`0x48` `0x2e`, +`0x44` bit 4 clear, and makes no
  message, no stop and no R6; the wake makes no R5w, R6w or R55 for `pmp`; PMS_SRAM is found on
  (C18 (c)), so C8 turns nothing on. *(Round 15c, G26.)* That is D3 (b), now stated for `pmp` found
  stopped with or without `cand_c8`.
- *Not observed.* What `pmp` reads or answers under Linux (open question 38; partly, L30); which
  domain R6's block is in.

**C9. The second port's domains and MSG off.** Switch `cand_c9`.
- *Observed.* ATC1_COMMON `0x23b700448` `0x2300`, ATC1_PCIE `0x23b700450` `0x300`, ATC1_USB_AON
  `0x23d280090` `0x300`, ATC1_USB `0x23d2800a0` `0x300`, MSG `0x23d280078` `0x200` with macOS awake
  (I) and at the commit (H, I); read, never written, in every capture (R56). **[LINUX]**
  `0x23ff`, `0x3ff`, `0x2ff`, `0x2ff`, `0x2ff` (on) before the entry (L15).
- *Why a candidate.* Five domains on under Linux that are off at every macOS reading, which no
  requirement turns off (R56 has no observed turn-off for them; D4 covers the first port only).
  *Reference* (2.2): a USB-side domain on at the commit, "the machine resets five seconds after
  the commit; macOS never sleeps with AUSS on" (T6050); ATC conditions on T6040.
- *Requirement.* With R7's domain turn-offs (after R5a): by R56 form 1, children before parents:
  ATC1_USB, ATC1_PCIE (and ATC1_CIO_PCIE, ATC1_CIO_USB, ATC1_CIO if found on), ATC1_USB_AON,
  ATC1_COMMON, then MSG: each R; if bits 0-3 are not 0: W (v & ~`0x3ff`) | `0x3f0`; R. At the
  commit each requests 0 (state: *reading*). Wake: D5 (f), by D1.
- *Not observed.* macOS's turn-off of any of them (never on under macOS); the form is R56's
  general one for a bit-28-clear word (R56 (b)). MSG carries the device tree flag "critical".

**C10. APCIE_GP gated at the commit.** Switch `cand_c10`.
- *Observed.* APCIE_GP `0x23b7003e8`: `0x1000230f` with macOS awake (I) and at the commit (H, I);
  in the entry it goes down by itself, with no write: G `0x1f0023ff` at T-7.4 s, `0x1400234f`,
  `0x1000230f` from T-0.017 s (`r12-candidates.txt`); the wake writes `0x0f002000`,
  `0x0f00200f`, `0x1f00200f` (W1-2c). **[LINUX]** `0x1f0020ff` (on, bits 8 and 9 clear) before
  the entry (ds13).
- *Why a candidate.* As C1, for the general PCIe block's domain: power-gated by its automatic
  power under macOS, on under Linux.
- *Requirement.* After R14 (the PCIe writes): R; if bits 4-7 are not 0, R until they are,
  bounded (macOS's word comes down by itself within the entry); if still not 0: R56 form 2 as C1.
  At the commit bits 4-7 = 0 (*reading*). Wake: D5 (f), by D1 (macOS's W1-2c turn-on).
- *Not observed.* A write lowering APCIE_GP's request; *Reference*: Aurora's tree comments the
  domain "Breaks things if shut down".

**C11. No domain word with bit 11 set at the commit.** Switch `cand_c11`.
- *Observed.* Bit 11 is read set only while macOS waits for a turn-on, never at rest and never
  at a commit (section 0; 4.2a). FPWM1 `0x23b7001e0` reads `0x2ff` (on) awake and at every commit;
  in F it was turned off and back on (W `0x0`, `0xf`, ..., `0x1000000f`; R40). GFX `0x23b7003f8`
  `0x0f002300` at the commit. **[LINUX]** FPWM1 **`0x0a00`** (request 0, state 0, bits 9 and 11)
  and GFX **`0x0f002b00`** (bits 8, 9, 11) before the entry (L15).
- *Why a candidate.* Two words latched busy at rest under Linux. *Reference* (2.2, 3.3, T8140): a
  domain off with BUSY latched holds the power manager's poll until a watchdog (seen there at the
  wake); the T8140 driver clears it with a pulse of bit 12, which no M1 capture shows.
- *Requirement.* At entry start: FPWM1: R; if bit 11 is set: turn on with bit 28 (R57 (ii); F's
  writes); left on, as at macOS's commit. GFX: R; if bit 11 is set: turn on without bit 28, then
  R56 form 1. At the commit FPWM1 requests `0xf`, GFX 0; bit 11 clear in both (*reading*). Wake:
  D5 (f), by D1.
- *Not observed.* Whether a turn-on clears a latched bit 11.

**C12. SIO and its children on, with automatic power off at R23.** Switch `cand_c12`.
- *Observed.* With macOS awake SIO_BUSIF `0x23b7001c0`, SIO `0x23b7001c8`, SIO_CPU `0x23b7001d0`
  read `0x1400024f` (request `0xf`, bit 28); in E5-8j, after R22 and 15 microseconds before R24,
  macOS's last power-domain writes clear their bit 28 with the request kept (SIO, SIO_BUSIF
  `0x0f0000ff`, held by the instrument, A3; SIO_CPU `0x0400024f`, commit `0x0f0002ff`; R23,
  R23a). At the commit their children request on: SPI_P, UART_N `0xff`, AUDIO_P `0x2ff`, UART_P
  and UART0-8 `0xff` (UART_P and UART0 the instrument's held values, macOS's own request on; 4.2a).
  **[LINUX]** SIO_BUSIF, SIO, SIO_CPU `0x0f000200` and SPI_P, UART_P, AUDIO_P, UART_N, UART0-8
  `0x200` (all request 0) before the entry (L15, 4.2a).
- *Why a candidate.* macOS's last domain writes before R24 are on these three, and they leave
  them on with automatic power off; under Linux the same step meets domains that are off.
  *Reference* (2.1 step 9, T8140): "SIO_CPU AUTO_ENABLE cleared" in the commit body.
- *Requirement.* At entry start (D3's decision for `sio` taken on the state found before; `sio`
  is not messaged or started by this candidate): turn on with bit 28, parents first: SIO_BUSIF,
  SIO, SIO_CPU; then SPI_P, UART_P, AUDIO_P; then UART_N, UART0-UART8 (`0x23b700268`,
  `0x23b700270`-`0x23b7002b0`). The entry then runs as section 8 has it, R10's `sio` translator
  step and R23 now meeting the domains on. At R23 the three read request `0xf` with bit 28; at the
  commit they request `0xf` with bit 28 clear, the children request `0xf`, and `sio`'s +`0x44`
  bit 4 is clear. Wake: D5 (f), by D1.
- *Not observed.* What Linux's `sio` does when its domains come on (L6: it did not answer once
  started by Linux's own driver). *(Round 14b, gap Z11.)* What the three read right after this
  turn-on, state `0xf` or 4 (C5's round-14b note; open question 74); C5's gate takes either.

**C13. Each core's timers disabled at its final write.** Switch `cand_c13`.
- *Observed.* In every captured power-down (fifteen) each core went down with the instrument's
  own EL2 timers stopped (A6, [ARTEFACT, in every power-down]) and its guest physical timer
  `CNTP_CTL_EL02` with ENABLE 0: macOS's own `0x6` where read (six, R65), the instrument's 0 in
  A-J (R59). The guest virtual timer was left enabled in two power-downs (`det19b`, `det21`,
  R68). **[LINUX]** at the final write (L23): core 0 EL2 physical `0x7` (enabled, masked,
  condition met), EL2 virtual `0x4`, `CNTV_CTL_EL02` `0x7`, `CNTP_CTL_EL02` `0x7`; cores 1 and 7
  `CNTP_CTL_EL02` `0x7`, their other three 0; cores 2-6 not read; `ISR_EL1` 0 on every core
  (L22).
- *Why a candidate.* Nothing is pending at Linux's cores, but two kinds of timer that every macOS
  power-down had disabled are enabled (masked, condition met) under Linux. *Reference* (2.2,
  T8140): "a timer left running also ends WFI". The cheapest candidate to try.
- *Requirement.* In each core's last job, before R43's accesses: `CNTP_CTL_EL02` written with
  ENABLE 0 and IMASK 1 (reads `0x6` or `0x2`); the physical and virtual timer controls the kernel
  uses at EL2 (`CNTP_CTL_EL0`, `CNTV_CTL_EL0` as accessed at EL2) written with ENABLE 0. No
  requirement on `CNTV_CTL_EL02`. At the final write those three have bit 0 = 0; R59 holds as
  before. Wake: nothing put back by the driver (the kernel's own timer code programs its timers
  after the resume).
- *Not observed.* Whether a masked, enabled timer matters to a core's power-down on the M1.

**C14. The audio clocks as macOS leaves them.** Switch `cand_c14`.
- *Observed.* `0x23b0400d4`-`0x23b0400e8` (six words) read **`0x100`** awake and at every commit
  (G-I); **macOS's boot writes `0x23b0400d4` = 0** (A, B: the first access to the page, core 1,
  t 2.962 / 1.221 s); in E and F the audio path writes `0x23b0400d8` = `0x86101000` when playback
  starts and `0x00101000` when it stops (L2 note). The NCO words `0x23b044000`, `048000`,
  `04c000`, `050000`, `054000` read `0x80000000` and are written 0 then `0x80000000` at every wake
  (W1-6, all eight); `0x23b048000` reads `0x80000000` at every commit. **[LINUX]** the six words
  `0x85100100`, `0x86100100`, `0x87100100`, `0x88100100`, `0x89100100`, `0x89100100` (bit 31 and
  bits 24-27 set); `0x23b048000` = 0 (ds13, ds15; the other four NCO words not read).
- *Why a candidate.* The audio switch's clocks are left enabled under Linux while their domains
  (SIO_ADMA, MCA0-5, AUDIO_P) are off; under macOS they are cleared when audio stops.
  *Reference* (2.1, 3.9): the T8140 and T6050 commits park clock muxes and clear clock words
  before the commit word.
- *Requirement.* At entry start: each of the six, ascending: R; if bits 24-31 are not 0: W 0. Then
  each NCO word, ascending: R; if not `0x80000000`: W 0, W `0x80000000` (W1-6's form). At the
  commit the six read bits 24-31 = 0 (the rest: *reading*, macOS `0x100`) and the five NCO words
  `0x80000000`. Wake: the six by D5 (f); the NCO words by macOS's own W1-6, nothing put back.
- *Not observed.* Which clock each word drives; a write of 0 to the five words other than
  `0x23b0400d4`.

**C15. `0x23b718000` and `0x23b718004` at `0xf` before R22 (conditional).** Switch `cand_c15`.
- *Observed.* `0x23b718000` reads `0xf` at macOS's boot (A, B touch map) and before its R22
  write in every entry; `0x23b718004` reads `0xf` before R22's write (all eight; R19, V11); at
  every wake macOS writes both `0xf` and polls `0x23b718004` (`0x1f` ... `0x2f`; R30). **[LINUX]**
  not read before the entry; after an entry that did not power down the wake's poll of
  `0x23b718004` timed out (L8, ds12). *(Round 14b, gap Z12.)* **[LINUX]** One reading, by an
  earlier driver (readings only, as L18 and L28, not a description of that driver): its dry run
  of 2026-11-16 06:51 on bare metal (kernel `7.2.11-run26`, `apple_s2r_rs.dry=1`; its trace
  states that from the cores' parking on no write was made, so each read there shows what the
  word held) read **`0x23b718000` = `0xf` and `0x23b718004` = `0xf`** at the place of its R22
  writes, after the cores were parked (private file
  `var/m1-state/20261116-122032-run35b/m1power-s2r/run22-20261116-065142.txt`, trace records
  924309-924310). One boot, another kernel; under the clean-room driver the pair is still unread
  (open question 69). With these values C15 makes reads only.
- *Why a candidate.* R22's write `0x23b718004` = 0 is the write the always-on side's first step
  follows (R62); what the word holds under Linux before it is not known. A difference only if it
  does not read `0xf`.
- *Requirement.* Immediately before R22a: R `0x23b718000`, R `0x23b718004`; if either is not
  `0xf`: W `0x23b718000` = `0xf`, W `0x23b718004` = `0xf`, R `0x23b718004` until it reads `0x2f`,
  bounded (R30's form). At R22's writes both read `0xf` (*reading* if the hardware does not take
  the writes). Wake: macOS's own (R30).
  *(Round 14b, gap Z12.)* **On D6's failure path the pair is not put back** (D6 (c) rule 1): when
  R22a's wait runs out after C15 has written, neither word is written again, whatever C15 read;
  the pair stays as C15 left it. A test: after a D6 wait no write of `0x23b718000` or
  `0x23b718004`, also when C15 read 0 (the case where D6 (c) rule 3 would have written R22's
  trigger value back).
- *Not observed.* The words under the clean-room driver (open question 69); what the pair at
  `0xf` does to a Linux that had another value there and runs on after a D6 return.

**C16. The GPIO domain on.** Switch `cand_c16`.
- *Observed.* GPIO `0x23b700130` reads `0xff` awake and at every commit (G-I); at every wake read
  `0x2ff` and written `0xff`, `0xff`, `0x100000ff` (all eight). **[LINUX]** `0x200` (request 0)
  before the entry (4.2a).
- *Why a candidate.* A domain on at every macOS reading and off under Linux. *Reference* (3.3,
  Aurora `dd2a90a2`): "SEP needs the GPIO state on". Weak; listed because a driver can act on it.
- *Requirement.* At entry start: R; if request 0: turn on with bit 28. At the commit request
  `0xf`. Wake: D5 (f), by D1.

**C17. The SoC clock words' bits 24-27 at macOS's value.** Switch `cand_c17`.
- *Observed.* 28 words read bits 24-27 = 7 at every macOS commit and awake (G-I; appendix B) and
  6 under Linux (`0x23b0400b0`: 2) before the entry (L2; ds13, ds15): `0x23b040000`, `004`,
  `00c`, `010`, `024`, `03c`, `040`, `050`-`06c` (eight), `080`, `084`, `094`, `098`, `0b0`,
  `0b4`, `0c0`, `0c4`, `0c8`, `0cc`, `0d0`, `134`, `138`. No macOS write to any of them in any full
  log (A-I); whether its boot writes them is below the touch map's resolution. (R18's
  `0x23b04014c` and `0x23b040154` also read 6 under Linux; they are left to R18.)
- *Why a candidate.* The largest group of differing words; their bits 24-27 differ between the
  systems and never between macOS's awake and commit; by the pattern of R18 and the audio path a
  source field (a reading of the bit pattern, not a name).
- *Requirement.* Immediately before R18, each word ascending: R; if bits 24-27 are not 7: W v
  with bits 24-27 = 7, the other bits as read. At the commit bits 24-27 read 7 (*reading* if not
  taken). Wake: D5 (f), after R30.
- *Not observed.* What the field selects; whether a write is taken; what changing it does to a
  running block (the devices are suspended by then).

**C18. `pmp` started, messaged and stopped as macOS does (new round 15).** Switch `cand_c18`
(bit 18, `0x40000`, of `cand`); **the kernel side's, not the logic's** (D9).
- *Observed.* macOS starts `pmp` at boot (R71, R72), tells it on endpoint `0x20`
  `0x0020e00000550000` (R72), stops it in every entry after `…550001`/`…540001`, `0x208` `0x63` and
  `…550000`/`…540000` (R73, R4, R5, R6), and restarts it at every wake (R74) followed by the same
  words. The C3 words reach macOS's `0x333/0x444/0x222` with no access by any core (R70), each step
  in the first 250 ms sample after a `pmp` event; with `pmp` running, 060000 reaches `0x222` and PMP
  and PMS_SRAM `0x1000030f` only after the 0x55 word, never while it is dropped (R75 [HV-CHANGED]).
  **[LINUX]** No `pmp` node, nothing bound, +`0x44` 0, the words `0x444/0x666/0x333`, PMS_SRAM
  `0x0f000300` (L27, L29). An earlier Linux that started `pmp` (opening answered) and sent
  `…550000` at its entry read macOS's three values at its commit, 0.25-0.37 s after (L28, L30);
  none of its runs powered down.
- *Why a candidate.* C3's words differ between Linux and macOS before the entry, every write of them
  by an application processor in either system was followed by no commit (C3), and the only way
  they are seen to reach macOS's values is through `pmp`'s start, its words and its stop (R75, L30).
  Weak on the power-down: macOS powered down with the 0x55 word dropped (det36), reaching the commit
  values by another way, and the earlier Linux with `pmp` started and macOS's commit values did not
  power down (L30). Also the only way seen to get PMP and PMS_SRAM gating themselves
  (`0x1000030f`) as macOS awake has them (C8).
- *Requirement* (all the client's; D9-D11; the words exactly as R71-R74 give them):
  (a) **Device tree.** Nodes for `pmp` (control page `0x23bc00000`; its SRAM `0x23b500000`,
  `0x80000` bytes; power domains PMP and PMS_SRAM, PMS their parent), its mailbox `0x23bc08000`
  (interrupts per the ADT `/arm-io/pmp`: 512, 511, 514, 513) and its translator `0x23b300000`
  (stream 0 translated, stream 15 bypass: ADT `sids` `0x8001`, `bypass` `0x8000`; tunables +`0x60`
  `0x80016100`, +`0x68` `0xf0f0f`, +`0x6c` `0x80808`). *Documentation, not an observation:* the
  reference tree (aurora-silicon/linux `integration/aurora` `1f38ff8f4`, `t8103-peripherals.dtsi`)
  has these three nodes, `status = "disabled"`, with no driver matching them (L29).
  (b) **Boot** (D10 (a)): PMP, PMS_SRAM, PMS on, each read with state `0xf` and bit 28 set
  (macOS's first readings after the start, R71); R71 (a)-(e); R72 by D11 (management words,
  buffers, endpoint `0x20`'s opening and its two request pairs); then `0x0020e00000550000` once.
  While running: endpoint-2 LOG words and endpoint-4 type-8 words echoed, buffer requests answered
  (D11 (c)).
  (c) **PMP and PMS_SRAM stay on** from the start to the commit and are not turned off by Linux's
  suspend of the client (macOS's commit: `0x1f0f03ff`, `0x1f0003ff`, R52; the logic's C8 then finds
  PMS_SRAM on). What they read while `pmp` runs is the hardware's (`0x1000030f` or `0x1f0f03ff`
  under macOS).
  (d) **Entry** (D10 (b)), in this order: `0x0020e00000550001`, `0x0020e00000540001`,
  `0x0020800000630000` (wait for `0x0020900000630000`), `0x0020e00000550000`,
  `0x0020e00000540000`; R4's exchange for `pmp` (AP `0x201` echoed, IOP `0x201` acknowledged);
  R5's stop (+`0x8114` the value read with bit 0 cleared, R +`0x48`, R +`0x44`, W +`0x44` = 0); the
  translator's two +`0xfc` writes (R73); R6's 49,152 reads in address order, kept for the wake. No
  write to SRAM, PMP, PMS_SRAM or PMS. At `enter` +`0x44` reads 0.
  (e) **Asleep:** nothing (the client's entry part has ended before `enter`).
  (f) **Wake and failure return** (D10 (c)), after the logic's wake: if PMP or PMS_SRAM does not
  read state `0xf` with bit 28, turn it on as R74's forms (otherwise no domain write); R6w (every
  word the value R6 read, in address order); R55 with the same table address as the boot's
  (macOS's wake value in I equals its boot value, W3); R5w (+`0x8114` R, W `0x20001`; +`0x44` R 0,
  W `0x10`); R74's short handshake; then `0x0020e00000630001`, `0x0020e00000550001`,
  `0x0020e00000540001`, `0x0020e00000550000`, `0x0020e00000540000` (det33's order).
  (g) With the switch off: no access to `pmp`'s control page, mailbox, SRAM or translator, and
  PMP, PMS_SRAM, PMS as Linux has them now (L29).
  *(Round 15c, gaps G1-G27.)* Completed by D9 (b) (the logic makes none of (d)'s or (f)'s steps for
  the `pmp` the client stopped; D3 (b)), D9 (e) (the translator the client's alone), D10 (a)-(c)
  (domains at boot are Linux's, buffers before the first access, every way out), D10 (e) (the switch
  read per part; a part acts only after the part before it), D10 (f) (words outside the waits,
  echoed also in the wake's handshake), D11 (a) (fields, sizes, "at once", later buffer requests),
  D11 (c) (the start-up's order; no kernel RTKit library, no SET_IOP_PWR_STATE at boot), D11 (d)
  (bounds: 1 s, 6 s for `0x000200000023b549`), D11 (f) (control-page accesses), R71 (c) (det10's
  writes in full, both +`0xfc` = 0) and R73 (the translator's reads before each +`0xfc` write).
  **Test lines** (the client's test author): the words and accesses of (b), (d), (f) in order, each
  wait bounded (D11 (d)); (d) complete before the logic's `enter` is called; (f) after `enter`
  returns, on success and on failure; no endpoint-`0x20` word sent before the reply to the request
  before it has come; no access with the switch off. For the logic: D9 (b)'s test.
- *Not observed.* Whether the 0x55 word sent at the end of the opening (not 66 s later) is followed
  by the change; whether the change comes under Linux at all, at boot, at the entry or after the
  wake; whether the other boot words (1.7h) are needed; what `pmp` does with the short handshake if
  its `__DATA` was not restored or the translator not set back; whether `pmp`'s start changes anything
  else under Linux (the always-on side, the DRAM controllers, PMS_SRAM's gating) or whether any of it
  matters to the power-down (open questions 75-80).

**Summary** (ranked; each behind its switch `cand_cN`, D5):

| # | What | Why it is a candidate | Evidence (macOS / Linux) |
|---|---|---|---|
| C1 | SEP domain to state 0 before R16 (R56 form 2) | gated under macOS at every reading, on under Linux; Reference T8140: running enclave "never returned" | G-I awake and commit `0x1000230f` / `0x1f0020ff` (ds13-15) |
| C2 | four power-manager sub-blocks on at entry start, so R22a stops running blocks | R22a is the step before the write that the always-on side's first step follows; macOS turns them on at boot and every wake | 1 awake, 0 at boot (A, B), wake writes 1 (all eight) / 0 (L3), ds8 timed out in R22a |
| C3 | *(revised round 13; places exact and the values' interface, round 14)* no write (R70); `0x23b058000`/`05c000`/`060000` read at entry start, as core 0's first three accesses after R22's trigger, after R38's third write before the commit-point step; nine values through D8 (a) | macOS never writes them; the always-on program's sleep sequence starts by moving them to 3 and 4 (decode); every application-processor write so far was followed by no commit | awake and commit `0x333`/`0x444`/`0x222`, wake `0x333`/`0x555`/`0x333`, no access; earlier Linux driver's commit macOS's values (L28) / `0x444`/`0x666`/`0x333`; ds20 C3 dark (L25) |
| C4 | DCSn+`0x7b0` = 0 | only differing DRAM-controller word; DCS domains gate under macOS only; Reference T6040: DCS dynamic gate | 0 always, never accessed / 3 on all eight, 3 at Linux's commit (DCS0-3) |
| C5 | *(revised round 13; its four reads exact, round 14; its gate, round 14b)* twelve request-4 domains to request 0 (form 3, macOS's wake order), only with PMS, SIO_BUSIF, SIO, SIO_CPU on (request `0xf` with state `0xf`, or state 4 with bit 28; else reads only), decided on C5's own four reads in that order right before the twelve | macOS lowers exactly these at every wake, after PMS and the SIO family are on | R57, all eight; 18 wakes / request 4 (L15), SIO family off; ds20 C5 timed out on SIO_BUSIF and hung (L25); macOS with request 4 powered down (`det30`) |
| C6 | `0x23b71c000` (and `040`) set at entry start | set by macOS at boot and every wake, never by Linux; R69 cleared it only after the first step; Reference: boot-cluster power-gate enable | 0 at boot then `0x80000000` / 0 (L19, L20) |
| C7 | `0x23d24003c`, `0x23d240048` with bit 31 | always-on clocks enabled under macOS, disabled under Linux | G-I, K / bit 31 clear (L2) |
| C8 | `pmp` stopped whatever PMS_SRAM reads | a running `pmp` may be skipped under D3; Reference T8140: running PMP resets | R4, R5 / PMP on, PMS_SRAM off, +`0x44` unread |
| C9 | ATC1_COMMON, ATC1_PCIE, ATC1_USB_AON, ATC1_USB, MSG off (form 1) | on under Linux, off at every macOS reading, no requirement lowers them | H, I / L15 |
| C10 | APCIE_GP to state 0 after R14 | gated by itself in macOS's entry, on under Linux | G's entry, H, I / `0x1f0020ff` |
| C11 | FPWM1, GFX without bit 11 (turn-on clears the latch) | busy latched at rest under Linux only | section 0 / `0x0a00`, `0x0f002b00` |
| C12 | SIO family on at entry start, R23 then clears bit 28 | macOS's last domain writes before R24 act on on-domains | R23, R23a / all off |
| C13 | timers disabled at each final write | enabled (masked, met) under Linux where every power-down had them off | fifteen power-downs / L23 |
| C14 | audio-switch clock words 0, NCO words `0x80000000` | audio clocks left enabled with their domains off | boot write, W1-6 / L2 |
| C15 | `0x23b718000`/`004` at `0xf` before R22 (only if not); *(round 14b)* never put back on D6's failure path | the trigger word's state under this driver is unread | `0xf` at boot and every entry / `0xf` once, an earlier driver's dry run (round 14b) |
| C16 | GPIO domain on | on under macOS, off under Linux | G-I / 4.2a |
| C17 | 28 SoC clock words' bits 24-27 = 7 | largest group of differing words | G-I / L2 |
| C18 | *(new round 15; the kernel side's, D9-D11)* `pmp` started at boot as macOS (R71, R72) with `…550000` after the opening; at the entry before `enter` macOS's endpoint-`0x20` words, R4, R5, R6; at the wake and on failure R6w, R55, R5w, short handshake, macOS's words | C3's words reach macOS's values only through `pmp`'s events, never by an application processor's write (R75, R70); PMP/PMS_SRAM gate themselves only after the 0x55 word | 1.7h, R75 [HV-CHANGED] / not started (L29); an earlier start: macOS's C3 values at the commit, no power-down (L30) |

*(Round 13.)* **What the runs have shown so far, per candidate** (1.7g for macOS with Linux's
state put in, [HV-CHANGED]; L25, L26 for Linux with the switch on). "Down" = powered down and
woke; "commit, up" = Linux's commit reached and the SoC stayed up until watchdog 1.

| # | macOS with Linux's state (1.7g) | Linux, switch alone (L25) | Linux, with the others (L26: all but C3, C5) |
|---|---|---|---|
| C1 | not carried | commit, up | commit, up |
| C2 | down | not run | commit, up |
| C3 | **no commit** (2/2) | **dark before the commit**, record 'a' | not on |
| C4 | write not taken: no test | commit, up | commit, up |
| C5 | down | **dark: a wait ran out (SIO_BUSIF), no return** | not on |
| C6 | down | not run | commit, up |
| C7 | down | not run | commit, up |
| C8 | not carried | commit, up | commit, up |
| C9 | not run | commit, up | commit, up |
| C10 | not carried | commit, up | commit, up |
| C11, C12 | not carried | not run | commit, up |
| C13 | not carried | commit, up | commit, up |
| C14 | not run | not run | commit, up |
| C15 | not carried | commit, up | commit, up |
| C16 | not run | not run | commit, up |
| C17 | **no commit** (2/2) | commit, up | commit, up |
| C18 | macOS without the 0x55 word: down (`det36`, 1.7h) | not run (an earlier module's start: no power-down, L30) | not run |

So no candidate, alone or with all the others but C3 and C5, has let Linux's SoC power down; the
two that hung Linux's entry are the two revised in this round. These outcomes rest on the
round-12 requirement texts (the ds20 kernel); C3's and C5's revised texts have not run.

## 9. Open questions

Closed by capture D:

1. **CLOSED.** *What macOS does after "Starting S2R timer".* Section 3, E6: the rest of the
   interrupt-controller action (896 reads, 39 writes), a second write of `0x23d2c4000`, four
   SPMI commands (`0xd00c` read; `0xd008`, `0xd00e`, `0xd000` written), a third write of
   `0x23d2c4000`, then the cores go down. Evidence: `phases-pre-d.tsv`, `spmi-pre-d.txt`.
8. **CLOSED.** *The three "Starting S2R timer" lines.* `0x23d2c4000` is written 1 three times:
   T-0.015811, T-0.004355, T-0.000705 (`det_misc.py`, `view.py d pre -0.02 0 -raw`).
10. **PARTLY CLOSED.** *Durations and the timing of hypervisor-handled events.* D gives the
    machine's own times for every phase, the guarded words, core stops and starts (sections 3,
    6, `phase-times.tsv`, `det-events.tsv`). Still open: durations with no trapping at all (D
    still costs about 6.4 microseconds an access), and the time from reset to the wake record.
13. **CLOSED as far as the hypervisor can tell.** *The value the hardware held for SIO and
    SIO_BUSIF.* D's on-machine handler records the hardware word as `0x1400024f` for both at
    E5-8j, as the host's log did in A and B (`det-events.tsv`).

Still open (numbers kept):

2. **PARTLY CLOSED by G.** *The state at the true commit as a snapshot.* Section 4.1: 792
   words read at the commit (`commit-snapshot-g.tsv`). Still open: the words the entry writes
   that are not in that list (about 615 of 630: the memory-controller shutdown words,
   `0x23d2c4000`, the timer and cluster words, the interrupt controller, ...). Needs a snapshot
   list built from `commit-last-writes.tsv`. *This round:* H repeats the 792 and adds all 137
   domain words (4.1a, 4.2a); the written words outside the list are still unread at the commit.
3. **Whether the guarded words and removed devices change the sequence** (A2, A3). Unchanged.
4. **Whether the boot arguments change the sequence** (A1). Unchanged; all three captures use
   the same arguments.
5. **What the per-core idle cycle I1 and the memory-controller burst I5 are.** I1 now rests on
   A and B only.
6. **Meaning of the words** written in R16-R24 and R36-R38.
7. **PARTLY CLOSED by G.** *Each core's power-down registers.* E7: `ACC_OVRD_EL1` and
   `CYC_OVRD_EL1` on every core, and the performance-counter and IPI registers at the stop
   (`det-down-g.tsv`). Still open: the registers the hypervisor does not trap (standard EL1
   registers, timers, SPRR/GXF, pointer-authentication keys, cache and TLB maintenance) and the
   final wait instruction; and the meaning of the two values.
9. **Which thread issues the SPMI commands of E3** (R9) and the two `0xd100` writes of E1.
11. **Invariance beyond three runs**, and wakes from other sources (lid, power button,
    network). There are now three alarm wakes (A, G, H), all with the hypervisor's alarm.
12. **Counts that do not add up.** Snapshots: logs say 793 and 265 words, the files hold 792
    and 264 distinct addresses (D's table says 265, its snapshot record 264). **Closed for the
    detached logs:** the read-out reports 263 more entries than the file has lines in each of
    D, E, F (917,798 / 917,535; 576,276 / 576,013; 1,067,168 / 1,066,905): the 264-word snapshot
    is one line.

New:

14. **What actually powers the chip down. NARROWED by G (E7, last part).** Established: no
    device-register write of macOS does it (the chip runs on for more than 1 ms after macOS's
    last access); the stop bits do not take a core down; every core's last trapped act is
    `ACC_OVRD_EL1` then `CYC_OVRD_EL1` = `0x3000001`, all within 33 microseconds, core 0 last,
    and the chip goes down only after that. Not established: that these writes plus the wait
    are sufficient (the hypervisor's own power-chip commands, USB detach and power-word writes
    come between core 0's logged write and its real one; the wait is not logged); which earlier
    steps are preconditions. Needs a run in which the hypervisor does nothing of its own at the
    commit, or one in which a single step of macOS's is withheld.
    *(Narrowed round 8.)* An armed watchdog 1 does not stop the power-down (J, R61). The
    instrument's acts at the commit are now listed from its code (A6): on every core the timers
    off and pending virtual interrupts cleared (R59), on the last core its SPMI commands followed
    by `0x23d0d9378` = 1 (R60), present in every power-down. Linux's commit (L16, L17) is a
    commit after which the chip does not go down; section 4.4 sets the two side by side. The
    readings that would settle it are 53-55.
    *(Narrowed round 9.)* Watchdog 2 is armed for 5 s within about 0.3 ms of R24's first write,
    about 15 ms before the cores go down, by no logged write (R62). With one core kept running
    after the commit, or with macOS's own timer state and the instrument's pending virtual
    interrupts left at the cores, the chip did not power down and reset 5-7 s after the commit
    (R59, R64; [HV-CHANGED]). So in every observed power-down all eight cores had gone down with
    their timers off and nothing pending; in the four runs without that, none powered down. The
    reference's account for other chips (4.4a) is of this kind (a hardware sequence that waits on
    every core and other conditions); for t8103 that remains reference.
15. **What "(0x7)" in "pmu go hib (0x7)" is**, and why the first power-chip action sends
    nothing.
16. **The alarm macOS sets** (R38). **Partly answered by E and F:** it is set before every
    sleep, with or without the cable, and is not the same interval each time (about 948, 972
    and 1,069 s after T if the inference in E6 holds; 975 s in G, the idle sleep). Still open:
    what determines it, and whether it explains the alarm wake of A. No capture has slept long
    enough to see it fire: both alarm wakes are the hypervisor's.
17. **Why cores 4-7 touch no logged device during idle in D, E and F** while every core reads
    the interrupt controller in A and B (section 2): an effect of the host being attached, or
    of what was trapped? E and F show it does not depend on the cable.
18. **The four untrapped pages at the real power-down**: D cannot show whether the cluster words
    of E5-8d are touched again after the point where A and B stop. Needs a detached capture
    that traps `0x210e20000` and `0x211e20000` during the last 100 ms only.
19. **Why the cores wait.** Cores 1-7 write their stop bit 89 ms before they enter the sleep
    path (E4, E6-5); what they do in between is not visible (no device access).

20. **The place of `dcp`'s endpoint-4 exchange** (section 10): in E2 with the cable in (A, B, D),
    at the display request with it out (E, F). Two against three captures; cause unknown.
    Needs more runs of each kind.
21. **What woke F after 1.6 s.** macOS reports "trackpadkeyboard" for it, the same text as for
    the space-bar wakes of D and E; the log cannot tell a trackpad touch from a key.
22. **The second, cancelled entry the operator reports after F's wake is not in the log**
    (section 11.3). Either it happened after the read-out, or what he did is the short
    cancelled start found before the committed sleep.
23. **What the count at `0x23d2b0020` measures** (section 5): about 7.80 million at every
    detached wake.
24. **What the power manager's read sweep is for** (E5-8c): the same reads are made, with no
    sleep, a second after the cable is pulled or inserted (section 10), and yet the values are
    written back at the wake. A sample of running counters, a save, or both?
25. **A cancelled entry later than 0.2 s**: F's stopped before the display request. What macOS
    undoes when an entry is cancelled after the coprocessors have been shut down, or inside
    the kernel path, has not been captured.

26. **Why the written clock-mux value does not hold** (R18, R48): `0x80100000` is written, the
    word reads `0x85100000` / `0x87100000` at once, at the commit and after the wake. Are the
    differing bits status, or is the write refused?
27. **What `s3_5_c15_c10_1` is** (written 0 by every core as it stops, E7), and what the two
    override values mean.
28. **What a dark wake does next.** A was recorded 163 s, G 20.8 s; neither shows macOS going
    back to sleep or the display coming on. And whether macOS's own alarm produces the same
    dark wake as the hypervisor's.
29. **The record of the snapshot has no time per word** (one start, one end): the order of
    reading within the 0.914 ms is the list's order, not checked.
30. **Whether an idle sleep differs on a machine in use** (apps open, lid, power source): G is
    one idle sleep at the login window. (H is a second, identical in kind.)

Added this round (from the test authors' gap list and from G against H). Each says which reading
would settle it.

31. **macOS's sequence from another starting state** (gaps V1, V2, V4, F1, F2, F6, T1, T5, S3,
    first-round 1 and 5). Every capture is the same macOS on the same machine at the login
    window: the sub-blocks of R22a read 1, `sio` and `pmp` run and answer, the domains are as in
    1.9, the pin controller, PCIe and audio switch hold macOS's configuration. So no capture
    shows a write that depends on the state differing from what macOS found, and none shows
    what macOS does when a step's precondition is missing (a coprocessor that does not answer,
    a sub-block already off, a domain off). Values written that equal values read cannot be
    told from constants. *Settles it:* a capture of macOS entering sleep from a changed state
    (for example a domain or sub-block set off by the hypervisor before the entry), or reading
    the words in question under macOS just before the entry in a capture with another
    configuration (another display, a USB device on the second port).
32. **What the sub-blocks of R22a and the words at `0x23b720030`-`0x23b720048` are**, and
    whether the equal bytes of section 12 L3 mean anything. *Settles it:* documentation of the
    block; or a capture that reads `0x23b720000`.. and the four status words together at several
    moments of macOS's entry (a snapshot list with them in it, read at each sub-block write).
33. **CLOSED by I.** *What a sub-block's status word reads while it is on* (gap V4): `0x4d4d01`,
    `0x404001`, `0x1`, `0x404001` (R22a, 4.1b; one reading with macOS awake).
34. **NARROWED by I.** *What changes the words of R52, and when.* I repeats the changes except
    `0x23b71c0f0` (now `[VARIES]`); PMP and PMS_SRAM take their commit values with macOS awake
    too (4.1b). Still open: when, between the detach and the commit, the clock words,
    `0x23b720030`.., `0x23d240040`, `0x23d240314` change, and what changes them. I's log has
    no access to them. *Settles it:* periodic readings of these words during the entry (every
    100 ms from E1, and at each console marker of E3-E6), which needs a sampler in the detached
    hypervisor (evidence, round 3, reading 3), or a capture whose end is not the alarm wake.
35. **CLOSED by I.** *The 58 domain words of 4.1a item 4 with macOS awake:* equal to their
    commit values (4.1b).
36. **PARTLY CLOSED by I.** *Where the translator values V of R55 come from:* written at boot,
    0 then V, by the instruction that writes them again at the wake with the same V (W3). Still
    open: what V points at, and whether 0 would do. *Settles it:* macOS memory at the address V
    names, read under the hypervisor. *(Round 7, reference only: V is in the place of a
    translation table base, R55.)*
37. **What macOS's mailbox, `+0x44` and `+0x48` read for a coprocessor that is stopped, not
    started, or not answering** (gaps F3, F6, F8, Q11). Seen only: after a sleep, before macOS
    starts them, `sio` and `pmp` read +`0x44` = 0 and +`0x8114` = `0x20001` (R5w); in E2,
    before their restart, `dcp` and `dcpext` read +`0x44` = 0 (R5a). +`0x48` was read only as
    `0x2e`. *Settles it:* a capture in which the hypervisor withholds one coprocessor's boot,
    or a Linux reading of these words with the coprocessor stopped (section 12, L6, L11).
    *(Round 7.)* For a coprocessor **running** under Linux: `dcp` and `dcpext` read +`0x44`
    `0x10`, +`0x48` **`0x2d`** (macOS only ever read `0x2e`, after the power messages), +`0x8110`
    and +`0x8114` in the bit-17 form (L15). Still not read: a stopped or silent one.
38. **How long a reply may take** (gap F7). In D-H every "coprocessor power `0x201`" reply of
    `sio` and `pmp` came 0.1 to 0.4 ms after the message (`mbox-pre-<cap>.txt`), with the
    hypervisor trapping every access; no reply ever failed. A bound for a missing reply is not
    observed.
39. **PARTLY CLOSED by I.** *The widths of accesses not in the log:* `0x690000004` is written
    as 16 bits in E5-3 (all eight); the guarded words and core start/stop words are accessed as
    32 bits at boot (1.8). Still open: their widths during the entry and the wake. *Settles
    it:* a detached hypervisor that records the guest's width in its `pmgr` and `cpustart`
    records.
40. **The alarm wake against the key wake** (R35): four alarm wakes, all the hypervisor's;
    whether macOS's own alarm (R38) gives the same dark wake. *Settles it:* a capture with the
    hypervisor's alarm left off and a sleep longer than macOS's own alarm interval (about
    950-1,070 s).

Added this round (from the sixth-round gap list Q1-Q15 and capture I). Each says which reading
would settle it.

41. **How macOS turns off the nine domains it never writes in the logs** (Q1a): ATC1_COMMON,
    ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB, ATC1_PCIE, MSG, ATC1_USB_AON, ATC1_USB.
    They are 0 with macOS awake. *Settles it:* the power manager's pages `0x23b700000` and
    `0x23d280000` logged in full from macOS's boot (as I did for the translator pages), and for
    the first port a capture without A2.
42. **PARTLY CLOSED by ds15 (round 7).** *What `dcp`'s endpoint-`0x37`/`0x02` messages before
    its stop ask for* (Q1b), and what `dcp`, `dcpext`, `gfx-asc`, `ans` read under Linux at the
    driver's entry. Read in ds15 (L15): `dcp` and `dcpext` running (+`0x44` `0x10`, +`0x48`
    `0x2d`); `gfx-asc` and `ans` not read because their domains report state 0. Still open: the
    messages' payloads. *Settles it:* the shared-memory buffers those messages name, read by
    the hypervisor at each message.
43. **A domain asked for 0 while it reads state 4 with bit 28 set** (Q1, run ds14, L13). macOS
    never did it: DISP0_CPU0 always read state `0xf` when macOS turned it off (E2a), and no
    write by macOS was seen to take it from 4 to `0xf`. *Settles it:* readings of `0x23b710018`
    at short intervals with macOS awake and through E1 (when state 4 becomes `0xf`), and under
    Linux the same word read before and after the display coprocessor is stopped.
    *(Narrowed round 7.)* A bit-28 clear is seen to bring a word to state `0xf` from state `0xf`
    and from state 0 (RMX, 21 instances), never from state 4 with a read after it (E2a). Under
    Linux DISP0_CPU0 reads `0x1404024f` with the display on (L14) and before the entry with
    `dcp` running (L15), the same before and after `dcp`'s four words are read. What the
    round-6 driver wrote to the word in ds14 is not in its log (L13). *Settles it (Linux):*
    DISP0_CPU0 read after each write of form 2 on it, with and without `dcp` stopped first by
    R5a's stop, the replies logged (open question 51).
44. **Who writes the non-domain words Linux has differently** (Q2): DCSn+`0x7b0`, the clock
    words of L2 other than `0x23b0400d4`-`e8`, the NCO, `0x23b058000`.., the always-on clock
    words. No capture writes any of them (the audio path's `0x23b0400d8` and NCO writes of
    section 12 L2 aside). *Settles it:* the pages `0x23b040000`, `0x23b044000`-`0x23b060000`,
    `0x23d240000` and one DRAM controller's page logged in full from boot; and Linux read after
    its audio driver has stopped (an observation of Linux).
45. **What a wake does on a chip that did not power down, and what macOS does when the chip
    does not go down after its last core's `CYC_OVRD_EL1` write** (Q7; open questions 14, 25).
    No capture. *Settles it:* a capture in which the hypervisor, at the commit, does not take
    the chip down and resumes core 0 (an aborted commit), logged. *(Round 8.)* Linux's commit is
    such a case on bare metal (L16, L17): no wake from any source, dark until the power button or
    watchdog 1. What the always-on block does there is not read (56). *(Round 9.)* macOS's
    commits that did not complete under the instrument (`det13`, `det14`, `det16`, `det17`) ended
    in a reset 5-7 s later and a normal boot; what macOS would do if the chip stayed up with all
    cores down is still not observed.
46. **Which bits end the poll of `0x23b718004`** (Q8, R30): only `0x1f` then `0x2f` ever read.
    *Settles it:* reading from a capture in which the poll meets another value (not producible
    under macOS without changing the hardware's state), or the code at the poll's pc, which is
    not read here.
47. **Which reading macOS acts on after an alarm wake** (Q9): +`0x360` bit 2 and `0xd00c` =
    `01` occur together in every capture. *Settles it:* a wake by macOS's own alarm (open
    question 40), and a key wake with an alarm set but not fired.
48. **The domain behind the blocks with no domain property** (Q12; temperature sensors, pin
    controllers, watchdog, SPMI, NCO, interrupt controller, R20's blocks, `dart-apcie0`). Not
    observable from macOS's captures, which never accessed a block whose domain it had off.
    *(Round 7, reference only.)* Aurora's Linux device tree gives domains to some of them
    (`dart-apcie0` APCIE_GP, interrupt controller AIC, pin controllers GPIO / NUB_GPIO, the
    display translators DISP0_CPU0 / DISPEXT_CPU0) and none to the watchdog, SPMI controller,
    NCO, two pin controllers; temperature sensors, `dart-pmp` and R20's blocks have no node
    (section 1.9). *Settles it (Linux):* a read of each block with the named domain off, as L5
    did for `dart-sio` (a fault means the block depends on it).
49. **Bit 11 at rest** (Q13: FPWM1 `0xa00`, GFX `0x0f002b00` under Linux): macOS reads bit 11
    only while waiting for a turn-on (section 0). What a word at rest with bit 11 set means
    is not observed.

Added round 7 (from the seventh-round gap list W1-W14, run ds15 and "Linux awake"). Each says
which reading would settle it.

50. **What `dcp` and `dcpext` answer under Linux to macOS's stop** (W1): "AP power `0x201`",
    the endpoint stops `0x00a4..` to `0x20`-`0x2c` (some of which Linux's own display driver
    may not have started: which endpoints are started under Linux is not read), "coprocessor
    power `0x201`", with Linux's display driver suspended. Under macOS each stopped endpoint
    had been started by macOS and every message was answered (R5a). *Settles it:* one run of
    R5a's stop under Linux on bare metal with every received word and +`0x8114`, +`0x48`
    logged; and the endpoints Linux's driver started, read from it or from the mailbox traffic
    at boot.
51. **DISP0_CPU0 and DISPEXT_CPU0 under form 2 from Linux's state** (W2): from `0x1404024f`,
    whether the first write (`0x0404004f`: bits 28, 9, 8 cleared, request kept) brings the state to
    `0xf`, with and without the coprocessor stopped first; and whether the second write then
    reads state 0 at once. *Settles it:* that run under Linux, reading the word after each write
    (open question 43).
52. **What Linux's display driver does with a coprocessor it finds stopped with its domains on
    after the wake** (D2): no capture, no reading. *Settles it:* a Linux run of the wake under D1
    and D2 with the display driver's log and `dcp`'s +`0x44`, +`0x48` read after its resume.

Added round 8 (from capture J, runs ds16 to ds17-3 and section 4.4). Each says which reading would
settle it; 53-55 are readings of macOS under the hypervisor, 56-58 readings of Linux.

53. **What the always-on block does after macOS's commit, before the power-down** (4.4 row 12,
    open question 14). No capture has a trace there. *Settles it:* the instrument's existing
    spin mode (`hv_s2r_spin_test`, A6: everything of the commit done, the last core spins
    instead of going down) with that core sampling, every 10 ms for some seconds, `0x23d2b8028`,
    `0x23d2b8040`, watchdog 2 (`0x23d2b0020`, `24`, `2c`), `0x23d2c4000`, `0x23b71c090`,
    `0x23b71c360` and power-chip `0x0201`; once with seven cores down and one spinning (the
    state of Linux's run 26, L18), giving macOS's progress where Linux's earlier driver read
    `0x01`. *(Narrowed round 9 by `det16`, [HV-CHANGED]; R64.)* With seven cores down and core 0
    sampling those words (and `0x0201` every 100 ms) for 4.9 s, nothing changed and the machine
    reset about 6 s after the commit: macOS's always-on words with a core up are those of 4.1c's
    commit column, and stay there. Still open, and not reachable from a running core by
    construction: what these words do **after the last core goes down**. What would come nearest:
    the always-on words read by the instrument at its wake entry after a normal power-down (they
    hold the last values written, R62), and the Linux readings of 56 for a side-by-side with
    `det16`.
54. **What macOS itself leaves in each core's timers and interrupt state at its final write**
    (R59). The instrument writes them off; macOS's values are not logged. *Settles it:* the
    instrument recording on each core, at its `CYC_OVRD_EL1` write and before changing anything,
    the guest's `CNTP_CTL_EL02`, `CNTV_CTL_EL02` and their compare values, `ISR_EL1`, the pending
    bits of `HCR_EL2`, `IPI_SR_EL1`, `PMCR0_EL1` and the guest's interrupt mask (from
    `SPSR_EL2`); then one run in which the instrument leaves them as macOS left them.
    *(Closed round 9 for the values: K, E7, R59, R65. The run that leaves them in place was made
    twice, `det13`, `det17`: no power-down, a reset 5-6 s after the commit, [HV-CHANGED]. What it
    left in place was two things at once; open question 59.)*
55. **Whether macOS's own commit powers the chip down without the instrument's last-core acts**
    (R27, R60; open question 14). *Settles it:* a run in which the instrument, at the commit,
    does only the real `CYC_OVRD_EL1` writes and watchdog 1 as the exit (no snapshot, no USB
    stop, no SPMI command of its own after macOS's last one, macOS's own alarm left in place; the
    wake note its wake path reads would have to be placed before macOS's entry); the held words
    of A3 are the one act that cannot be dropped without changing what macOS asked for.
    *(Round 9: not run.)* The observation stage left it out because with macOS's own alarm (about
    16 min ahead, time not read) and watchdog 1 not counting through a sleep (R61), a run that
    powered down properly would have no wake without hands; and placing the wake note before the
    entry changes what macOS reads at `0x9f08` during the entry (evidence, "Left out, and why").
    Still open. The round-9 runs bear on one part of it: of the instrument's per-core acts, the
    timer and pending-interrupt writes (R59) were needed for a power-down under the instrument
    in two runs out of two. *(Round 10.)* Of those two acts only the clearing of the pending
    virtual interrupts was needed (R68); the timers can be left.
56. **The always-on block after Linux's commit** (4.4 row 12, L17, L18). *Settles it:* a core
    kept running after the commit point, as in run 26 (L18), sampling the words of 53 every
    10 ms into the power chip's scratch or memory, under the round-7 driver; and `0x23d2c4000`
    read before the entry and after each of the driver's three writes.
    *(Sharpened round 9, R62, 4.4 rows 13-14.)* The first reading to take: watchdog 2's count,
    bite and control and `0x23d2b8028` read right after the driver's **first** `0x23d2c4000`
    write, and again just before the commit point. Under macOS the first reads a count started
    at that write with bite 5 s and control 4, and the second bit 24 set (K). Then, with a core
    kept up after the commit as in `det16`, the same words for some seconds, to set against R64.
    *(Sharpened round 10, R62, 4.1c.)* Under macOS watchdog 2 is armed and bit 24 set already
    before the first `0x23d2c4000` write, its count starting just after `0x23b718004` = 0. The
    reading to take under Linux: watchdog 2's count, bite, control and `0x23d2b8028`,
    `0x23d2b8040` right after the driver's write of `0x23b718004` = 0 and again right before its
    first write of `0x23d2c4000`, and `0x23d2c4000` before and after that first write (under
    macOS 1, then 0).
57. **Each core's final state under Linux** (4.4 rows 2-4). *Settles it:* per core, recorded at
    its last instruction before the wait: `ACC_OVRD_EL1`, `CYC_OVRD_EL1`, the timer controls in
    use, `ISR_EL1`, `IPI_SR_EL1`, `PMCR0_EL1`; and `0x23d0d9378` read after the glue's last SPMI
    command. *(Round 9.)* Also, per core, the timer controls `CNTP_CTL`/`CNTV_CTL` of every
    exception level Linux runs a timer at, and the interrupt controller words of R65 / R36's
    round-9 note, to set against K's (E7) and against every observed power-down (R59).
    *(Round 10: the item that matters most is now open question 65.)*
58. **The commit-list words that change by themselves at Linux's commit, with values** (L16, 4.4
    rows 6-7); and the AP wake-source masks `0x23d004008`-`0x23d004018` and the always-on clock
    words `0x23d240024`, `03c`, `048` in both systems (under macOS: added to the commit list and
    read awake; under Linux: read before the entry and at the commit). *(Round 9: the macOS side
    is closed by K, R63; the Linux side is open.)*

Added round 9 (from capture K, the round-9 runs and section 4.4a). 59-61 are readings of macOS
under the hypervisor, 62-63 of Linux. Each names what it would need and its way out without
hands.

59. **Which of the two items `det13` and `det17` left in place stops the power-down** (R59,
    4.4a C4). *Settles it:* two runs on K's recipe: (a) the instrument zeroes the guest timers and
    the timer FIQ enable but leaves the pending virtual FIQ; (b) it clears the pending virtual
    interrupts but leaves the guest timers enabled with the timer's FIQ to the core on. Needs a
    split of `hv_s2r_keep_state` into two options (the instrument's code, A6). Way out without
    hands: the alarm at commit + 90 s, watchdog 1 at commit + 150 s, and, as in `det13`/`det17`,
    a reset 5-7 s after the commit if the power-down does not come.
    *(Closed round 10, [HV-CHANGED], R68, E7.)* (b) timers left, no virtual interrupt pending
    (`det19b`, `det21`): power-down and alarm wake, 2 of 2. (a) the pending virtual FIQ left,
    timers off (`det20b`, `det22c`): a reset about 6 s after the commit, 2 of 2. The pending
    virtual FIQ is the item. What it does at the core (whether the core leaves its wait) is open
    question 66.
60. **When the always-on side's first step is taken, against macOS's three writes of
    `0x23d2c4000`** (R62). *Settles it:* the instrument, which traps that page, reads watchdog 2's
    count, bite and control and `0x23d2b8028`, `0x23d2b8040` immediately before and after each of
    macOS's three writes (no write of its own). Way out without hands: K's (the alarm, watchdog 1).
    *(Closed round 10, [L], R62, 4.1c.)* Before the first write: watchdog 2 armed (5 s, control
    4) with a count of 43-56 microseconds, `0x23d2b8028` `0x1000000`; its count started 1.3-7.1
    microseconds (±10) after the record of macOS's write `0x23b718004` = 0. Still open: what arms
    it, and when bit 24 is set relative to it.
61. **The power manager's CPU block and power-gate records at the commit** (4.4a C3). The words
    `0x23b754000`-`0x23b75401f` (held by the instrument, A4) and the power-gate records of the
    page `0x23b71c000` (K's commit list has nine: appendix B's eight and `0x23b71c360`) are not
    read at the commit in full.
    *Settles it:* add those words to the commit list and to the awake snapshot. Way out without
    hands: K's.
    *(Closed round 10, [L], R66, R67, 4.1d.)* CPU block at the commit: +`0x0` = +`0x4` =
    `0xfe`, awake all 0. Power-gate page: 22/21/20 words of 450 change between awake and the
    commit (23 in all), the ten header words `0x80000000` throughout; `0x23b71c000` reads 0 at
    every wake and is set by macOS there; with Linux awake it reads 0 (4.4a C3, open questions
    64, 67). Still open: when +`0x4` takes `0xfe`.
62. **Linux at its commit, against K** (4.4 rows 4, 13; 4.4a C1-C17). *Settles it:* under the
    round-7 driver, the readings of 56 and 57 with the 880 words of K's commit list read at the
    commit point (into memory, written to the power chip's scratch or kept across the watchdog
    reset). Way out without hands: watchdog 1 armed at the commit (L17).
    *(Round 10.)* The list to read is now L's (1,328 words: K's, the CPU block and the whole
    power-gate page; `var/recfg/commit-snap-list-r7.json`).
63. **What `0x9f03` = `0x50` records** (1.7d). It reads `0x50` after every run of either system
    that reached a commit and did not wake, `0x00` after every wake. *Settles it:* `0x9f03` read
    awake before an entry and after a run that was ended by the power button with no commit (not
    yet read). *(Round 10: `det20b` and `det22c` add two more of the first kind, L, `det19b`,
    `det21` three of the second.)*

Added round 10 (from capture L, the round-10 runs and the Linux register scans). 64-65 are
readings of Linux, 66-67 of macOS under the hypervisor.

64. **The power-gate header and the CPU block under Linux at its commit** (R66, R67, 4.4 rows 15
    and 16, 4.4a C3). With Linux awake `0x23b71c000` reads 0 where macOS has `0x80000000` at
    every commit. *Settles it:* under the driver, `0x23b71c000`, `0x23b71c040` (and the other
    eight header words) and `0x23b754000`, `0x23b754004` read before the driver's first access,
    and again at the commit point after its last write; one 32-bit read each, into the record.
    If `0x23b71c000` reads 0 at Linux's commit, Linux's commit differs from every macOS commit
    read in this word; if `0x80000000`, the difference seen awake does not reach the commit. Way
    out without hands: watchdog 1 at the commit (L17).
    *(Round 11.)* Read again with Linux awake on another boot (2026-11-18 03:54): `0x23b71c000` 0,
    `0x23b71c040` `0x80000000`, CPU block +`0x0`, +`0x4` 0 (1.7f). Under macOS the word cleared
    at the end of the entry did not stop the power-down (R69), so a 0 at Linux's commit would no
    longer by itself be a difference from every macOS commit that powered down; the reading at
    Linux's commit is still not taken, and it would also say whether the word stays clear
    through Linux's whole entry (open question 67 (b)).
65. **Whether anything is pending at a core at Linux's final instruction** (R59 round 10, R68, E7;
    sharpens 57). *Settles it:* on each core, as the last thing before its final write and wait,
    record `ISR_EL1`, the control registers of every timer the kernel runs on that core
    (`CNTP_CTL`, `CNTV_CTL` at the exception levels in use, and their compare values against the
    count), `IPI_SR_EL1`, `PMCR0_EL1` and `PMSR_EL1`, and, if the kernel runs at EL2, the
    pending-virtual-interrupt bits of `HCR_EL2`; plus the interrupt controller words of R65 once.
    Under macOS, at every captured power-down, `ISR_EL1` read 0 and no virtual interrupt was
    pending; the failures had a virtual FIQ pending. Way out without hands: watchdog 1 at the
    commit.
66. **What a pending interrupt does at a core after its final write, under macOS** (R68). Two
    readings, each a change of the instrument's ([HV-CHANGED]): (a) `keep_vfiq` again with each
    core counting, into power-chip scratch, the times its guest leaves the wait after its final
    write (whether the cores with a virtual FIQ pending leave their wait, and how often); (b)
    `keep_timers` with, on the cores whose timer has fired, the timer's FIQ to the core turned on
    (`VM_TMR_FIQ_ENA_EL2` bit 0 set) and no virtual FIQ: the nearest the instrument can come to a
    fired timer whose interrupt reaches the core, as it would on a machine without it (what the
    instrument then does with that FIQ is its own and must be recorded too). Way out without
    hands: the alarm, watchdog 1, and the reset of `det20b`/`det22c`.
    *(Round 11: not run; the round was stopped before it.)* Two points from the observation
    stage's notes (evidence "Hypervisor round 8", "Left out, and why"): for (a), every core's
    guest `PSTATE` has D, A, I, F masked at its final write (E7), so a pending virtual FIQ is not
    taken as an exception, and a core leaving its wait need not enter the instrument; counting
    those exits would need the instrument to trap the wait instruction, which changes the wait
    being measured. A draft of (b) exists outside the repositories and was not built or run.
    `det23` adds a case to the question: an IPI to core 3 not yet taken at its final write (E7),
    which the instrument cleared; what such an IPI does at a core with no instrument between is
    not observed either.
67. **Whether `0x23b71c000` bit 31 matters for the M1's power-down** (R67, 4.4a C3). *Settles
    it:* K's recipe with one change: the instrument writes `0x23b71c000` = 0 after macOS's last
    write and before the cores' final writes (at the first core's `CYC_OVRD_EL1` write), and reads
    it back at the commit; once also with `0x23b71c040` = 0. A power-down and alarm wake would
    set the word aside; a reset some 5 s after the commit would match the reference's T8140
    account. [HV-CHANGED] by construction. Way out without hands: the alarm, watchdog 1, and the
    5-7 s reset seen in every failed run.
    *(Partly closed round 11, [HV-CHANGED], R69, 1.7f.)* Run as asked for `0x23b71c000` alone
    (`det23`: written 0 after the first core's state record, 6-14 microseconds before T; `det24`:
    before it, 0.28 ms before T and before every core's final write): it read 0 at the commit
    and **the chip powered down and woke at the alarm both times**. So bit 31 of `0x23b71c000` at
    the commit, cleared at the end of macOS's entry, is not needed for the M1's power-down under
    the instrument; the reference's T8140 outcome did not occur. **Still open:** (a) the same with
    `0x23b71c040` cleared too (`det25`, brought up, not run); (b) the word clear through the
    whole entry, as Linux awake has it: the instrument would write `0x23b71c000` = 0 before
    macOS's entry (at the detach, after macOS's own wake or boot set it) and read it at the
    first `0x23d2c4000` write and at the commit (whether macOS's entry sets it back is itself
    part of the reading: no logged entry writes it). Way out without hands: as above.
68. **Each candidate of 8.2 carried into macOS** (round 12). *Settles it, per candidate:* a run
    of det18's recipe in which the instrument, at the detach (before macOS's entry), puts one
    word or domain into Linux's state and holds it there: C2 the four sub-blocks written 0 and
    macOS's R22a writes passed through; C3 `0x23b058000`/`05c000`/`060000` written
    `0x444`/`0x666`/`0x333`; C4 DCSn+`0x7b0` written 3; C5 the twelve domains written request 4;
    C6 `0x23b71c000` written 0 (open question 67 (b)); C7 `0x23d24003c`/`048` written
    `0x01101100`/`0x00101100`; C9 the five domains turned on; C14 the six audio words and the
    NCO written Linux's values; C16 GPIO turned off; C17 bits 24-27 written 6. Not carried: C1
    and C10 (SEP's and APCIE_GP's state is their own automatic power's; see (c)), C11 (a latch
    the instrument cannot set), C12 (SIO and UART0 carry the instrument's console, A3), C13 (the
    EL2 timers are the instrument's, R59), C8 and C15 (no Linux value read). A run that then does not power down
    marks its candidate as one that holds the SoC up on the M1; one that powers down and wakes
    sets it aside. All [HV-CHANGED] by construction. Way out without hands: the alarm, watchdog
    1, and the 5-7 s reset of every failed run. (c) For C1 and C10: whether macOS sends `sep`
    anything at all in the logged windows (none in R4) and what the SEP word reads at boot in
    A's and B's touch map; a full log of macOS's boot for the pages `0x23b700000`
    (SEP's word), `0x23b748000`, `0x23b71c000`, `0x23b058000`-`0x23b060000`, `0x23d240000` and
    DCS0 (+`0x20`, +`0xc`, +`0x7b0`) would also give the boot writes of C2 and C6 and say whether
    anything writes C3's and C7's words.
    *(Round 13.)* Run for C2-C7 and C17 (1.7g); C9, C14, C16 not run; for C3's words see 70.
69. **The candidates' words under Linux, before the entry and at the commit** (round 12). The
    commit walk (L24) covers C3, C4, C5's, C9's, C11's, C12's, C16's domain words, SEP, the clock
    words of C7, C14 (`0x23b048000` only) and C17. Not covered: the sub-blocks' control and status
    words (C2), APCIE_GP (C10), `0x23b71c000`/`040` (C6), `0x23b718000`/`004` (C15; *round 14b:*
    read once before an earlier driver's trigger, `0xf`/`0xf`, 8.2 C15), the four
    other NCO words (C14), `pmp`'s +`0x44`/+`0x48` (C8), cores 2-6's timer controls and
    `VM_TMR_FIQ_ENA_EL2` (C13), and `0x23d240040`, `0x23d240314` (which macOS's own machine
    changes between awake and the commit). *Settles it:* the glue's probe reading each of these
    before the driver's entry and at the commit point, one per run as the walk does. Together
    with open question 56 (watchdog 2 and `0x23d2b8028` right after the driver's `0x23b718004` =
    0) this would say which candidates' words still differ when the always-on side would start.
70. **Who sets the C3 words under macOS, and when** (round 13; 8.2 C3, R70). The words change
    with no access by any core: from `0x444`/`0x666`/`0x333` (before any operating system) to
    `0x333`/`0x444`/`0x222` within the first 192 s of macOS's boot, and to
    `0x333`/`0x555`/`0x333` across each sleep. *Settles it (under the hypervisor, macOS):* det18's
    recipe with the instrument's clock (`hv_tick.py`, a sample every 250 ms) reading the three
    words from the instrument's start through macOS's boot to the login window, and from the wake
    until macOS is idle again; in the same windows `pmp`'s +`0x44`, +`0x48` and its mailbox
    (`0x23bc08000` page) logged in full, and the CPU clusters' pages (`0x210e20000`,
    `0x211e20000`, skipped since G) logged during the boot. The first sample at which each word
    has changed, set against the accesses just before it, says whether the change follows
    `pmp`'s start or one of its messages, another agent's, or nothing an application processor
    does; the wake series says whether `0x555`/`0x333` go back to `0x444`/`0x222` and after what
    (R5w, R6w restart `pmp`). Way out without hands: as det18 (the alarm; watchdog 1 at the
    commit); the boot part needs none. A cheaper partial reading, not under the hypervisor: the
    m1n1 proxy left idle for some minutes with the three words read every second (do they move
    with no operating system at all?).
    *(Round 15: PARTLY ANSWERED, 1.7h, R75.)* Both readings were made: the proxy's words do not move
    in 300 s; under macOS each change follows a `pmp` event (its start; with `pmp` running the word
    `0x0020e00000550000`, without which 060000 stays `0x444`; `…540000`; its stop). What writes the
    words stays open (75).
71. **The C3 words around Linux's trigger** (round 13, Linux; 8.2 C3, L28). With C3 as revised:
    the nine reads (entry start, right after `W 0x23b718004` = 0, the commit point) under the
    round-8 driver. Under an earlier driver they read macOS's values at the commit (L28); whether
    they move after the round-8 driver's trigger says whether the always-on program's sequence 0
    gets past its first two waits (with open question 56). The commit walk reads the last of the
    three places at its positions 67-69 (L24).
72. **C5's wait that ran out** (round 13, Linux; L25). Which entry step made the 32-bit read of
    SIO_BUSIF that timed out, what SIO_BUSIF, SIO and SIO_CPU read then, and where the M1 hung
    after the record (the failure path, D6). *Settles it:* the glue's trace for that run's step,
    and one run of the revised C5 with `cand_c12` off (reads only by its precondition) and one
    with it on.

73. **A CPU stop bit left set under Linux** (round 14, Linux; D6 (e)). After a D6 return the
    stop bits cores 1-7 wrote to `0x23b754000` (R11) stay set: macOS never clears them by a write
    (at every wake +`0x0` reads 0, 4.1d), and no capture has a core run on after its stop bit
    with no power-down following. What a set bit does to a core that goes on running Linux (its
    next idle, a power-down of its own, nothing), and what clears the bit short of a power-down,
    are not observed. *Settles it (Linux, bare metal):* one core of cores 1-7 writes its bit
    with Linux otherwise running, then idles and is woken by an interrupt; `0x23b754000`,
    `0x23b754004` and that core's domain word read before, after the write and after the wake-up,
    with the core's progress counted (a per-core heartbeat). Way out without hands: watchdog 1
    armed before the write (D7's four writes, N = 30).

74. **The SIO family right after C12's turn-on** (round 14b, Linux; 8.2 C5, C12; gap Z11).
    Whether SIO_BUSIF, SIO and SIO_CPU report state `0xf`, 4 or 0 just after C12 has turned them
    on with bit 28. Under macOS no read follows the family's bit-28 write in any capture, and
    other words report 4 (NUB_SPMI0/1, DCS) or 0 at the first read after such a write (8.2 C5,
    round-14b note). With C5's round-14b gate C5 acts at `0xf` and at 4 alike, so the reading says
    in which state of its parents C5's lowering is tried (macOS's last reads before its own
    lowering were `0xf`), and whether C5 acts at all (it does not at state 0). *Settles it
    (Linux, bare
    metal):* one entry with `cand_c12` and `cand_c5` on, its record carrying C5's own four reads
    (8.2 C5, round 14: PMS, then the three, 32 bits by core 0, immediately after C12's last
    turn-on write and before C5's first access to the twelve). Way out without hands: watchdog
    1 armed before `enter` (D7 (a), N = 30).

75. **A delayed 0x55 word** (round 15; R75, 1.7h). Is the change (060000 to `0x222`, PMP and
    PMS_SRAM to `0x1000030f`) tied to the word whenever it arrives, or to something else in macOS's
    69 s that the word only marks? *Settles it (macOS, under the hypervisor):* det36's recipe with
    the word held and sent by the instrument some seconds later (at boot, and once after a wake),
    sampled as 1.7h; and one run with the word dropped at the entry only (does the commit still read
    `0x333/0x444/0x222` with it present at boot?). Way out without hands: as det33.
76. **The fewest words that bring the change** (round 15, both; C18, D11 (b)). Under macOS, whether
    the change follows `0x0020e00000550000` sent right after the opening; under Linux with C18,
    whether start, opening and that one word are followed by `0x444/0x444/0x444` and then
    `0x333/0x444/0x222` and PMP/PMS_SRAM `0x1000030f`, or whether other words of 1.7h (the code-`0xa`
    word for `0x55`, the device words macOS sends from 3 s) are needed. *Settles it (Linux, bare
    metal):* a boot with `cand_c18` on, the three words, +`0x44`, +`0x48`, PMP, PMS_SRAM, PMS read
    every 250 ms from before the start to 60 s after the word, the mailbox words logged by the
    client. No sleep, so no way out is needed beyond the client's bounded waits.
77. **The C3 words and PMP/PMS_SRAM under Linux with `pmp` run, at the entry and after the wake**
    (round 15, Linux; C18, C3). With `cand_c18` and `cand_c3` on: C3's nine reads, PMP and PMS_SRAM at
    entry start and at the commit, and the outcome (power-down or not). Then the same with the other
    candidates (L26's set). Way out without hands: watchdog 1 armed before `enter` (D7 (a)).
78. **`pmp`'s restart under Linux** (round 15, Linux; C18 (f), D10 (c), D11 (c)). Whether `pmp`
    answers R74's short handshake after the client's R6w, R55, R5w, after a failed entry and after a
    real sleep, and what it does with the boot form of the handshake instead. *Settles it:* first a
    failed entry on purpose (D6's path) with the client's wake part logged; then a sleep.
79. **What macOS's boot leaves that the captures do not log** (round 15; 1.7h). SRAM
    `0x23b540000`-`0x23b57ffff` before the start (including the `0x23b549000` page), macOS's writes of
    PMP, PMS_SRAM and PMS at boot, the boot-argument block in det33/det34b (one boot read in full),
    the translator's set-up and the start in one boot, the IOVA buffers' contents. *Settles it
    (macOS, under the hypervisor):* one boot with `0x23b500000`+`0x80000`, `0x23b300000` and
    `0x23b700000` logged in full from the start.
80. **A second sleep after a wake without the 0x55 word** (round 15, macOS; R75). After det36's and
    det37's wakes the words stayed `0x333/0x444/0x444` with `pmp` running; whether the next entry
    reaches `0x333/0x444/0x222` (by the stop, as det36's first) and the chip powers down again is
    not read. *Settles it:* det37's recipe with a second idle sleep after the wake. Way out without
    hands: the alarm and watchdog 1 as det33.
81. **Linux's own driver of watchdog 1 on the test kernels** (round 15b, Linux; D7 (c), (e), L31).
    Whether `apple_wdt` is active, or marked running in hardware, on a test kernel booted with the
    lab's command line (`systemd.watchdog_sec=0`, as `var/deepsleep/ds20.cmdline`), and so whether
    D7 (e)'s check lets `wdt` runs through. *Settles it (Linux, bare metal, read-only, awake):* on
    such a boot and, for comparison, on the stock kernel: `/sys/class/watchdog/watchdog0/` `state`,
    `timeout`, `bootstatus`, `identity` (and `hw_running` if present); `systemctl show -p
    RuntimeWatchdogUSec -p RebootWatchdogUSec`; the journal's "Watchdog" lines since boot; which
    processes hold `/dev/watchdog` and `/dev/watchdog0` open; and `0x23d2b0014`, `0x23d2b001c` read
    32-bit over `/dev/mem` (the bite and control as Linux left them; whether m1n1 or Linux armed it
    at boot). Second, for D7 (c)'s panic: one `wdt` run in which the glue takes the exception path
    on purpose (a parked core held from answering its release), with the time from the record to
    the reset read on the M3 (the M1's port dropping) and the fault shadow and record read after;
    it says whether the panic's restart or watchdog 1's bite ends it, and how long a core that does
    not answer delays it. Way out without hands: watchdog 1, armed by D7 (a).
    *(Round 15c; L32.)* **Partly answered.** On ds21's kernel and command line no process holds
    `/dev/watchdog0` and systemd reports no runtime or reboot watchdog, so nothing in user space makes
    it active; on the stock kernel systemd holds it (30 s). `state`, `timeout`, `bootstatus`,
    `hw_running` do not exist (`CONFIG_WATCHDOG_SYSFS` not set). **Still open:** whether
    `WDOG_HW_RUNNING` is set on the test kernels (by the reference's `apple_wdt`, when watchdog 1's
    control reads the reset enable at its probe). *Settles it:* `0x23d2b001c` and `0x23d2b0014` read
    32-bit over `/dev/mem` on a ds21-like boot with nothing holding `/dev/watchdog0` (with nothing
    holding it, Linux's core keeps a watchdog it found running pinged and armed, so bit 2 set says
    `WDOG_HW_RUNNING`, clear says neither flag); and the second part above.
82. **The duration of the glue's pre-entry work** (round 15b, Linux; D7 (a), (d)). From D7 (a)'s
    arming to R15's restart of the count, with each diagnostic option (`snap` 1, 2, 4 and
    `probe=1`) and with none: the glue's trace marks' times or the kernel log's timestamps around
    the sleep step. It says whether N = 30 covers the first stretch with the 792-word snapshot (ds13
    and ds15 suggest seconds at most: `echo mem` returned 4 s after the start in ds13, including
    the suspend and resume, but the stretch itself was not timed).
    *(Round 15c, GL11.)* With (a) in `begin`, the stretch runs from `begin` to R15 and includes
    Linux's device suspend (the `pmp` client's entry part with `cand_c18`); to be timed the same way,
    from `begin`'s first mark.
83. **The size of `pmp`'s endpoint-`0x20` buffer** (round 15c; D11 (a), gap G5). The opening's word
    carries an IOVA and no size; macOS gave `0x3c000` (the last of its IOVAs), the earlier Linux start
    `0xffff0000`. *Settles it (macOS, under the hypervisor):* one boot with the translator's table at
    its TTBR (det10: `0x8217dc000`) read from DRAM after the opening, giving the mapping macOS made at
    `0x3c000` and its length. Until then D11 (a)'s one 16 KiB page.

## 10. With and without the cable

Compared: D (cable in throughout) against E and F (cable out from before the entry until after
the wake); same method, build and untrapped pages. Scripts: `five.py`, `cable.py`, `compare.py`,
`ps.py`, `buses.py`, `commit_state.py` with `CAPS=d,e` and `d,f`; numbers in 7.5.

**What macOS can see of the cable.** It has no driver on this port (A2). It learns of the cable
from the `smc` coprocessor. The machine's own log agrees with the host's clock to within 1.1 s:

| Event | Host's clock | Machine's log (`cable.py`) |
|---|---|---|
| E, cable out | about 39 s | 40.025 s: `smc` notifications `0x71010100`, `0x71060000`, `0x70200000` |
| E, cable in | about 488 s | 487.967 s: `0x70200000`, then `0x71010101`, `0x71060000` (several) |
| F, cable out | about 187 s | 187.707 s: `0x71010100`, `0x71060000`, `0x70200000` |
| F, cable in | about 233 s | 232.943 s: `0x70200000`, then `0x71010101`, `0x71060000` (several) |

(Notification = a word read from the `smc` mailbox with type byte `0x18`; the value shown is
its upper half. The low byte of the `0x7101..` word is `00` on removal and `01` on insertion.)
What follows each event:
- within 0.1 s, some tens of `smc` key reads (keys beginning `B`, and `PDTR`, `PSTR`, `D0VR`,
  `AY-N`);
- about 1.2 s later (E: 41.27 s; F: 188.95 s) a read sweep of the power manager: 549 reads in
  `0x23b734000`, 135 in `0x23d2b4000`, 24 in each of `0x68c00c000`, `0x23400c000`,
  `0x27900c000` and two more blocks, 14 power-domain words, and one read of the guarded word
  ATC0_COMMON: the same reads as E5-8c/e/f, with no sleep involved;
- on insertion only: the audio path runs for about 15 s (E: 489-503 s; F: 234-248 s; 144
  accesses a second to `admac-sio`, with `mca`, `i2c1`, `i2c3` and their domains; console
  "Speaker: Hardware timestamp ..." in F).
**The port's power words** (guarded, recorded by the hypervisor): ATC0_COMMON reads `0x20ff` on
the hardware before the sleep and `0x23ff` after the wake; ATC0_USB and ATC0_USB_AON read
`0x3ff` after the wake: **the same values in D, E and F**, cable in or out. They reflect the
hypervisor's use of the port (A7), not the cable. The port's USB controller is not in any log
(the hypervisor's own accesses are not recorded), so the cable times cannot be checked there.

**Differences found between D and the cable-out captures:**
1. The cable events themselves and macOS's reaction to them (above). None of it is part of the
   sleep entry or the wake.
2. One mailbox exchange changes place: the internal display coprocessor's single endpoint-4
   exchange (`0x0040000000000000` sent and echoed) falls inside its brief restart in E2 in A,
   B and D (T-3.28, T-3.22, T-0.81) and at the display request in E and F (T-7.35, T-7.23), so
   `dcp` exchanges 37 / 38 words in E2 with the cable in and 36 / 37 with it out. Whether the
   cable causes this is not established (open question 20).
3. Nothing else that follows the cable. The differences that exist are run-to-run variations
   that do not split by cable: the order of the display pairs in E2 (D alone differs), the
   order of the two power-chip actions (F alone), FPWM1 (F alone), the DCS domain values, the
   alarm value, counters and message payloads.

**What did not differ** (D against E and against F):
- idle patterns I2, I4-I7 before the entry, and that cores 4-7 are silent;
- every phase time from "IOCPUSleepKernel enter" to the power-down, to about 2 ms (table in
  section 3), and from the wake to "IOCPUSleepKernel exit", to about 6 ms (section 6);
- the power-domain writes of the entry (same counts and values; F's extra FPWM1 aside);
- the `smc` key writes (`MBSE` "slpw", `WKTP`=2, `MBSE` "slpa"; "waka" at the wake) and the
  shutdown exchanges of `gfx-asc`, `dcpext`, `ans`, `sio`, `pmp`, `aop`, `smc`;
- the 33 quiesce actions before the interrupt controller: ordered writes identical;
- the handling and hardware values of the guarded SIO words;
- the interrupt-controller action: identical access for access;
- the alarm commands, the three writes of `0x23d2c4000`, the 48 trailing records, and all
  cores entering the sleep path within 33 microseconds;
- the wake status words; the "wake" snapshot apart from DRAM-controller domain words;
- each core's system-register writes and the order and spacing of core starts;
- the active actions (53 and 54 of 57 with identical ordered writes) and wake actions (26 of
  30), the PMP save and write-back, the save/restore of the interrupt controller;
- the wake kind (display on within 0.6 s) and the "system wake events" line;
- every requirement value (`reqcheck.py`).
So, as far as five captures show, **macOS does nothing different around sleep when nothing is
plugged in.** With the limits: macOS does not own this port in any capture (A2), and in every
capture the hypervisor still brings the port up again at the wake (A7).

## 11. The cancelled entry and the 1.6 s sleep (capture F)

### 11.1 The cancelled entry (T-15.22 to about T-14.77; `cancelled.py`, `console-f-pre.txt`)

7.7 s before the entry that led to the sleep, the console shows "interface awdl0 disable"
(T-15.219), which is the first line of E1 in every capture, then "writing WKTP=0" (T-15.082) and
"interface awdl0 enable" (T-15.019). The operator had been using the trackpad since T-22.5.
- **How far it got:** only the first 0.14 s of E1. What it did is what E1-1 does: the three
  `aop` endpoint-`0x24` exchanges (`0x00a2..` / `0x0085..`) twice, the PWM block written
  (`0x23504401c`, `0x235044018`, `0x235044000`), power-chip clock reads. It did **not** reach
  the display request: no "ON to OFF" line, no display-coprocessor shutdown, no write to
  DISP0_CPU0, DISP0_FE or RMX, no `MBSE` or `WKTP`=2 key, no coprocessor power message.
- **What macOS did to undo it:** `smc` key `WKTP` written `00` (T-15.081; the same key write as
  after a key wake, W4); "awdl0 enable"; four `sep` management exchanges (T-15.02 to T-15.00);
  one `pmp` endpoint-4 exchange; a 6-byte write to power-chip register `0xd100` (T-14.77),
  the register written in E1-6.
- **Where it left the hardware:** of the 74 words written in the window (leaving out the
  console and SMC shared memory), 62 end at the value last written before it, and of the other
  12 only five are outside the idle set: the PWM values (`0x6a` -> `0x65`, `0x356` -> `0x35b`) and
  mailbox words (`sio`, `aop`). The memory-controller burst I5 never stopped (23 bursts between
  T-17 and T-7.4, at the idle spacing). The seven seconds until the next entry show only
  trackpad traffic (SPI3, `sio`) and the status writes to `0x200021004` that accompany it.
  **As far as logged, the hardware was back at idle.**

### 11.2 The 1.6 s sleep

The entry from T-7.47 is a complete one: every phase time from "IOCPUSleepKernel enter" on
within 3 ms of D and E (section 3),
ordered writes identical to D's in 33 quiesce actions, the last steps as in E6 (with the two
power-chip actions in the other order), last core down at 215.247830 s. The wake record is at
216.839031 s: **1.591 s asleep**. What the log shows of it:
- wake status `0x23d004020` = `0x400000`, the same word as for every other wake;
- the "wake" snapshot equals E's (415 s) in 260 of 264 words and D's in 259; the domain words
  are in the default state, not the pre-sleep state: the chip went fully down;
- the count at `0x23d2b0020` is `0x770765`, as after the long sleeps (section 5);
- the wake path is the normal one: the same 57 active and 30 wake actions at the same times
  (kernel exit at W+0.401), 991 interrupt-controller words written back, the PMP block written
  back (49,152 words), all seven cores started W+0.1117 to W+0.1186 in the usual order, the
  same system-register writes; display on at W+0.512;
- macOS's line: "system wake events: NUB.SPMI0Sw3IRQ nub-spmi.0xC0 smc.70070000
  trackpadkeyboard", identical to D's and E's (space bar). Power-chip `0xd00c` reads `00`.
So a wake 1.6 s after the commit is, to macOS and in every register logged, the same as a wake
after minutes. Nothing shows an "aborted" or shortened path.

### 11.3 What the log does not contain

After that wake the log runs 120.5 s to the read-out. In it there is **no further sleep entry**:
no "awdl0 disable", no display "ON to OFF", no `WKTP`=2, no write to a display domain to off;
only the wake, the return to idle (W+6), the cable going in (W+16.1), and idle. The only
cancelled entry in the capture is the one of 11.1, **before** the committed sleep. This differs
from the account given with the capture (a second Sleep click after the wake, cancelled by a
key): see open question 22.

## 12. Readings under Linux: the state a driver starts from **[LINUX]**

Everything in this section was read on the same machine with Linux running (Omarchy, the lab's
kernels), recorded in `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` and its private
files. It is **not** an observation of macOS and **not** a requirement. It is here so that the
reader knows in which respects the machine a Linux driver meets differs from the one macOS was
captured on. The numbers L1-L15 are for reference from tests and from section 4.

- **L1 (run ds13, bare metal, 17:59).** In Linux's suspend path, after its devices were
  suspended and cores 1-7 parked and before the deep-sleep driver's first access, the 792 words
  of the commit list were read (`var/commit-state/linux-ds13-bare-preentry.json`, 0 unread, no
  fault). Against macOS H at its commit (`commit-state-gh.tsv`, column
  `linux_ds13_vs_H_commit`): **674 equal, 118 different**: 54 SoC clock words, 40 power-domain
  words, 8 memory-controller words, 8 DRAM-controller words, 5 always-on clock words, 3 other
  power-manager words. The 137 domain words were logged in the same run just before the cores
  were parked ("ps prepare") and after the return ("ps wake")
  (`var/commit-state/linux-ds13-bare-ps-words.json`); their values are in the table of 4.2a.
  Between the two dumps only the cores' domain words and NUB_SPMI0 differ.
- **L2 (ds13): the non-domain words that differ from macOS's commit.** Linux / macOS H:
  - `MCC.plane0-3+0x680` / `+0x684`: `0x9e5` / `0xa11` (macOS awake and at the commit: one of
    seven values between `0x800` and `0xf62`; under the hypervisor these words are emulated, A5);
  - `DCSn+0x7b0`, n = 0..7: **3** (macOS: 0 in every snapshot of all seven captures, awake and
    at the commit; macOS never accesses these words in any log);
  - SoC clock words at `0x23b040000`-`0x23b040154` (50 words). Most often Linux has byte 3
    `0x86` where macOS has `0x87` (`0x86100100` / `0x87100100` in 18 words, `0x86100000` /
    `0x87100000` in 7, `0x86100100` / `0x87100000` in 2, `0x86100000` / `0x87100100` and
    `0x86200100` / `0x87200100` in one each); bit 8 differs alone in 12 (`0x85100100` /
    `0x85100000` in 5, the reverse in 4, `0x80100100` / `0x80100000` in 3); `0x23b0400b0`
    `0x82100000` / `0x87100100`; `0x23b04001c` `0x85100000` / `0x85120000`; `0x23b040020`
    `0x85100100` / `0xc5100000` (G: `0x85100000`); and **`0x23b0400d4`-`0x23b0400e8`, six words
    that read `0x100` under macOS awake and at the commit, read `0x85100100`, `0x86100100`,
    `0x87100100`, `0x88100100`, `0x89100100`, `0x89100100` under Linux.** (`0x23b0400d4` is the
    third register range of the audio switch `mca-switch` in the device tree, section 1.9.)
  - `0x23b048000` (the NCO block's first word): 0 / `0x80000000`; `0x23b058000`, `0x23b05c000`,
    `0x23b060000`: `0x444`, `0x666`, `0x333` / `0x333`, `0x444`, `0x222`;
  - `0x23b720030`, `0x23b720034`, `0x23b720044`: `0x01616161`, `0x017f7f7f`, `0x016c6c6c` /
    `0x01515151`, `0x01494949`, `0x01494949` (macOS awake: `0x014d514d`, `0x01404940`,
    `0x01404940`);
  - always-on clock words `0x23d240024` `0x81100000` / `0x81100100`, `0x23d24003c` `0x01101100` /
    `0x81100100`, `0x23d240040` `0x02100100` / `0x01101100` (= macOS awake), `0x23d240048`
    `0x00101100` / `0x82100100`, `0x23d240314` 0 / `0x01000000` (= macOS awake).
  - *(Added this round, gap Q2: every differing non-domain word with its address, Linux ds13 /
    macOS H commit; `linux_diff_list.py`, `linux-diff-list.md`.)* Clock block `0x23b040000`..
    and the NCO's first word (51): `0x23b040000` `0x86100100`/`0x87100100`; `0x23b040004` `0x86100100`/`0x87100100`; `0x23b04000c` `0x86100100`/`0x87100100`; `0x23b040010` `0x86100100`/`0x87100100`; `0x23b04001c` `0x85100000`/`0x85120000`; `0x23b040020` `0x85100100`/`0xc5100000`; `0x23b040024` `0x86100000`/`0x87100000`; `0x23b04003c` `0x86100100`/`0x87100000`; `0x23b040040` `0x86100100`/`0x87100000`; `0x23b040044` `0x80100100`/`0x80100000`; `0x23b040048` `0x80100100`/`0x80100000`; `0x23b04004c` `0x80100100`/`0x80100000`; `0x23b040050` `0x86100100`/`0x87100100`; `0x23b040054` `0x86100100`/`0x87100100`; `0x23b040058` `0x86100100`/`0x87100100`; `0x23b04005c` `0x86100100`/`0x87100100`; `0x23b040060` `0x86100100`/`0x87100100`; `0x23b040064` `0x86100100`/`0x87100100`; `0x23b040068` `0x86100100`/`0x87100100`; `0x23b04006c` `0x86100100`/`0x87100100`; `0x23b040080` `0x86100100`/`0x87100100`; `0x23b040084` `0x86200100`/`0x87200100`; `0x23b040094` `0x86100000`/`0x87100100`; `0x23b040098` `0x86100100`/`0x87100100`; `0x23b0400b0` `0x82100000`/`0x87100100`; `0x23b0400b4` `0x86100100`/`0x87100100`; `0x23b0400c0` `0x86100100`/`0x87100100`; `0x23b0400c4` `0x86100100`/`0x87100100`; `0x23b0400c8` `0x86100100`/`0x87100100`; `0x23b0400cc` `0x86100000`/`0x87100000`; `0x23b0400d0` `0x86100000`/`0x87100000`; `0x23b0400d4` `0x85100100`/`0x100`; `0x23b0400d8` `0x86100100`/`0x100`; `0x23b0400dc` `0x87100100`/`0x100`; `0x23b0400e0` `0x88100100`/`0x100`; `0x23b0400e4` `0x89100100`/`0x100`; `0x23b0400e8` `0x89100100`/`0x100`; `0x23b0400ec` `0x85100000`/`0x85100100`; `0x23b0400f0` `0x85100100`/`0x85100000`; `0x23b040108` `0x85100000`/`0x85100100`; `0x23b040114` `0x85100100`/`0x85100000`; `0x23b040118` `0x85100100`/`0x85100000`; `0x23b04011c` `0x85100100`/`0x85100000`; `0x23b040128` `0x85100100`/`0x85100000`; `0x23b040134` `0x86100000`/`0x87100000`; `0x23b040138` `0x86100000`/`0x87100000`; `0x23b04013c` `0x85100000`/`0x85100100`; `0x23b04014c` `0x86100000`/`0x87100000`; `0x23b040150` `0x85100000`/`0x85100100`; `0x23b040154` `0x86100000`/`0x87100000`; `0x23b048000` `0x0`/`0x80000000`.
  - *(Added this round, gap Q2: who writes these under macOS.)* In no capture does macOS write
    any of these words in the entry or the wake except the five muxes of R18. **The audio path
    of E and F** (cable insertion, section 10) writes two of them: at the start of playback
    (W+11.38 in E, W+17.21 in F) the NCO `0x23b048000` is read (`0x80308000`), written 0,
    `0x23b048004` = `0x45e`, `0x23b048008` = `0x5ad200`, `0x23b04800c` = `0xff9f5200`,
    `0x23b048010` = `0x7f9f5200` (each between reads of `0x23b048000` = 0), then `0x23b048000` =
    `0x80001000`; 3 ms later **`0x23b0400d8` = `0x86101000`** (read back the same). At the end
    of playback (W+26.06, W+31.54) **`0x23b0400d8` = `0x00101000`**, read back `0x00101100`,
    then the NCO read (`0x80301000`), written 0, written `0x80000000`. At the wake (W1-6) each of
    the five NCO words is read `0x80000000`, written 0, written `0x80000000`. So under macOS the
    word `0x23b0400d8` holds bit 31 and a source in bits 24-27 only while audio plays, and is
    written with them clear when it stops; Linux's `0x86100100` for the same word has them set.
    The other five words `0x23b0400d4`, `0dc`-`0e8` and DCSn+`0x7b0` are never accessed by macOS
    in any log; the clock words with byte 3 `0x86` / `0x87` and the always-on clock words are
    never written by macOS in any log (open question 44).
- **L3 (run ds8, read under the stock kernel after the run).** The four sub-blocks of R22a:
  control words `0x23b748000`, `400`, `800`, `c00` all read **0** (macOS awake: 1 in every
  capture). Status words: `0x23b7483e0` = `0x616100`, `0x23b7487e0` = `0x7f7f00`,
  `0x23b748be0` = 0, `0x23b748fe0` = `0x6c6c00`. In both systems the second and third bytes of
  each non-zero status word equal the byte repeated in one of the words of L2: `0x61` in
  `0x23b720030` (Linux) and `0x51` (macOS's final `0x515100`, its commit `0x01515151`) for
  `0x3e0`; `0x7f` in `0x23b720034` (Linux) and `0x49` (macOS `0x494900`, `0x01494949`) for
  `0x7e0`; `0x6c` in `0x23b720044` (Linux) and `0x49` for `0xfe0`. While macOS waits, the status
  words read `0x494002` and `0x514d02`, whose bytes are those of macOS's awake values
  `0x01404940` and `0x014d514d`. These are coincidences of values in two systems; what ties the
  words together is not established.
- **L4 (ds2-ds4): widths and order.** A 32-bit read of `0x200024000`, which macOS accesses only
  as 64 bits, raised an SError (ds3). A 32-bit read of `0x23b549000` (the R6 block) through
  `/dev/mem` under the stock kernel, with Linux's `pmp` driver loaded and `pmp` running, reset
  the machine at once (ds4); macOS reads this block only after it has stopped `pmp` (R4, R5),
  and the same read did not fault in ds8 after `pmp` had been stopped.
- **L5 (ds5): a block whose domain Linux had off.** With `sio`'s domains off, a 32-bit read of
  `0x235004200` (`sio`'s address translator) raised an SError (panic record, count 1).
- **L6 (ds6, ds13): `sio` and `pmp` under Linux.** ds6's and ds13's domain dumps have SIO_BUSIF,
  SIO, SIO_CPU at `0x0f000200` (off). In ds7, with the domains turned on by the driver, `sio`
  did not answer the first mailbox message ("wait on 0x236408114 did not end"); on that boot
  Linux's own `sio` driver had failed to start it ("error -ETIME"). What `sio`'s +`0x44`,
  +`0x48`, +`0x8110`, +`0x8114` read in that state was not logged. In ds13 the driver logged
  `pmp`'s translator word `0x23b300200` as read **0**, and gave 0 for `sio`'s `0x235004200`,
  `0x235004210` (domains not on). Under macOS these words are only written, at the wake, with a
  non-zero value (W3, W1-8).
- **L7 (ds9): an entry that ran to its end on Linux.** The driver's entry completed (its record
  'R'), including every core's `CYC_OVRD_EL1` write; the chip did **not** power down (the
  Thunderbolt link stayed up for 7 minutes), did not reset, and did not wake at the alarm the
  driver had written (`0xd008` held it). The state at that commit was not read.
- **L8 (ds10, ds11, ds12): the way back without a power-down.** After an entry that did not power
  down, the driver's wake writes ran: a 32-bit write to `0x238408204` (the audio switch, block 2
  of six, third write of that block) was followed by an SError panic (ds10, ds11); in ds12 the
  run got past that action and timed out in the poll of `0x23b718004` (R30; under macOS this poll
  reads `0x1f` and ends on `0x2f`); what Linux read there was not logged. Under macOS the audio
  switch's wake action comes after SIO_ADMA and MCA0-5 have been turned on (W3); at Linux's
  entry those domains read `0x200` (off), as at macOS's commit.
- **L9 (ds8): power chip.** After that run byte `0x9f03` read `0x50` (`0x30` before) and `0x9f01`
  read `0x30`. Under macOS `0x9f01` is written `0x50` before the sleep and `0x00` at the wake
  (R9). Not explained. *(This round, gap Q15.)* After run ds14 `0x9f03` reads `0x00`
  (evidence, ds14). macOS reads and writes no power-chip register `0x9f03` in any capture (the
  scratch registers it accesses are `0x9f00`, `0x9f01`, `0x9f02`, `0x9f08`, `0x9f18`, `0x9f19`,
  `0x9f1f`; `spmi-*-N.txt`), so nothing in the captures relates to L9.
- **L10 (dsh1, dsh2): Linux as the hypervisor's guest.** dsh1's entry stopped before the commit
  (the hypervisor took one core out of the guest at its `CYC_OVRD_EL1` write and the driver
  waited for it); dsh2 reached a real commit and did not wake. The 792 words read with Linux
  awake under the hypervisor 46 s before dsh2's entry: 667 equal to G's commit
  (`linux-ds12-hv-vs-macos-det8.tsv`). L1 is the better reading of what a driver finds; dsh2 is
  kept in `commit-state-gh.tsv` (column `linux_awake_dsh2`) only for comparison.
- **L11: what has not been read under Linux.** The 858 words at Linux's own commit; the
  status words of R22a while a sub-block is on; `sio`'s and `pmp`'s mailbox and control words
  when they do not answer; SIO_CPU's control word after a driver has turned the domain on
  (gap V9); the 66 domain words' values after the entry's writes; any register while asleep. *(This
  round.)* Also not read: `dcp`'s, `dcpext`'s, `gfx-asc`'s and `ans`'s +`0x44`, +`0x48`,
  +`0x8114` at the driver's entry (R5a; whether these coprocessors run then); which domain a
  read of a core's domain word reflects (L12). *(Round 7: `dcp`'s and `dcpext`'s four words are
  now read, L15; `gfx-asc`'s, `ans`'s, `sio`'s and `pmp`'s were not, their domains reporting
  state 0. Still not read: what any coprocessor answers to a message under Linux; which of
  `dcp`'s endpoints Linux has started; the display translators' words; DISP0_CPU0 after a
  write; Linux's state at its own commit.)* *(Round 8: at Linux's commit only the count and four
  or five indices of the commit-list words that changed by themselves are read (L16). Still not
  read: their values; the domain words at the commit; `0x23d2c4000`; the AP wake-source masks;
  each core's `ACC_OVRD_EL1`, `CYC_OVRD_EL1`, timers and pending interrupts at its final wait;
  `0x23d0d9378` after the glue's own SPMI commands; the always-on block's progress word, watchdog
  2 and `0x0201` after the commit while the SoC is still up (4.4).)* *(Round 9: no new Linux
  reading. K's commit list (880 words) and each core's state at its final write (E7) are the
  macOS side of every comparison above; on the Linux side all of them are still unread at the
  commit, 4.4a.)* *(Round 10: no new reading at the commit; L19 adds two register scans of Linux
  awake.)* *(Round 11: no new reading at the commit; L20 adds four words read with Linux awake.)*
  *(Round 12: read at the cores' final writes: nothing pending at any core and the timer
  controls of cores 0, 1, 7 (L22, L23); the commit walk has begun to read the 118 differing words
  at the commit (L24). Still not read at the commit: the domain words outside the 118, watchdog 2
  and `0x23d2b8028` after the driver's `0x23b718004` = 0, `0x23d2c4000`, the AP wake-source masks,
  `0x23d0d9378` after the glue's commands, the CPU block, the power-gate page, the sub-blocks'
  control and status words, `VM_TMR_FIQ_ENA_EL2`, cores 2-6's timers.)*
- **L12: the domain dumps of ds6 and ds13 ("ps prepare", two boots) are equal** in 135 of 137
  words; they differ only in which core's domain reports on (ds6: PCPU1 `0x1f0`, ECPU3 `0x100`;
  ds13 the other way round). *(This round, gap Q15.)* ds13's dump was taken after Linux had parked
  cores 1-7 and runs on one core; macOS awake (I, all cores running) reads `0x1f0` for every
  core and `0x21f0` for both clusters, and at its commit R53's values. Which core made each
  Linux reading is not in the log.
- **L13 (run ds14, bare metal, 19:12; evidence "Run ds14").** The driver of round 6 ran its
  entry and stopped before the commit: "wait on 0x23b710018 did not end" (-110). `0x23b710018`
  is **DISP0_CPU0** in the power manager's table (`pmgr-devices.json`; the evidence file calls
  it DISP0_FE, whose word is `0x23b700360`). Read before the entry (`ps prepare`):
  **`0x1404024f`** (bit 28 set, bits 24-27 `0x4`, state 4, request `0xf`); after the failed
  entry and the driver's way back (`ps wake`): **`0x14040240`** (request 0, state still 4, bit
  28 and bits 24-27 unchanged). DISP0_FE read `0x20ff` and RMX `0x1f0000ff` in both dumps. 41 of
  the 137 words differ between the two dumps (`linux-ds14-bare-ps-words.json`). What the driver
  wrote to the word is not in this record. **Under macOS for the same word** (E2a, 4.3):
  awake `0x1404024f` in 10 of 15 awake snapshots (also `0x1404034f`, `0x1f0402ff`); macOS
  never wrote it while it read state 4; before its first write in the entry `dcp` has had its
  power messages and +`0x44` = 0 (R5a) and `dart-disp0` / `dart-dcp` +`0xfc` written, and the
  word then reads `0x1f0402ff` (state `0xf`); macOS writes `0x0f0400ff` (bit 28 cleared, request
  still `0xf`), reads `0x0f0402ff`, writes `0x0f0403f0`, and reads `0x0f040300` at once.
  After this run power-chip byte `0x9f03` read `0x00` (L9).
- **L14 (Linux awake, stock kernel, 19:35; evidence "Linux awake, stock kernel"; added round
  7).** Read over `/dev/mem` in stock Omarchy (kernel 7.3.0-0test5, display on, nothing
  suspended), one 32-bit read each. The evidence file's text is the only record (no log file
  holds these reads): DISP0_CPU0 `0x23b710018` **`0x1404024f`**; DISP0_FE `0x23b700360`
  `0x20ff`; DISPEXT_FE `0x23b700368` `0x23ff`; DISPEXT_CPU0 `0x23b700378` `0x1404024f`; GFX
  `0x23b7003f8` `0x1000230f`; ANS2 `0x23b7003f0` `0x1000230f`; PMS_SRAM `0x23b7003e0`
  `0x0f000300`; SIO_CPU `0x23b7001d0` `0x1400024f`; NUB_SPMI0 `0x23d280060` `0x1400024f` (names
  from the power manager's table; the evidence names only four). Against macOS awake (the 15
  awake snapshots, `r7_coproc_words.py` and the snapshot tables): DISP0_CPU0 `0x1404024f`,
  DISP0_FE `0x20ff`, GFX `0x1000230f`, ANS2 `0x1000230f`, SIO_CPU `0x1400024f`, NUB_SPMI0
  `0x1400024f` are **the values macOS has awake** (DISP0_CPU0 and DISP0_FE in most snapshots,
  section E2a); **DISPEXT_FE and DISPEXT_CPU0 differ**: on under Linux, off under macOS awake
  (`0x2300`, `0x0f040300` in all 15); PMS_SRAM differs (macOS awake `0x1000030f`, I's pre-full
  `0x1f0003ff`). So DISP0_CPU0 reads state 4 with bit 28 set with the display on and Linux
  awake, as under macOS awake.
- **L15 (run ds15, bare metal, 19:35; evidence "Run ds15"; `var/deepsleep/ds15-snap4-dmesg.txt`,
  parsed by `r7_linux_ds15.py` into `linux-ds15.json`; added round 7).** In Linux's suspend
  path, cores 1-7 parked, before the driver's first access (the driver is not called): the 137
  domain words ("ps prepare"), the 792 words of the commit list, then for six coprocessors
  +`0x44`, +`0x48`, +`0x8110`, +`0x8114` (each coprocessor's four skipped if one of its domain
  words reports state 0), with those domain words read before and after; then the 137 again
  ("ps wake"). Checked against the log lines:

  | Coprocessor | +`0x44` | +`0x48` | +`0x8110` | +`0x8114` | Its domain words (same before and after) |
  |---|---|---|---|---|---|
  | `dcp` | `0x10` | `0x2d` | `0x2ff01` | `0x2aa01` | RMX `0x1f0000ff`, DISP0_FE `0x20ff`, DISP0_CPU0 `0x1404024f` |
  | `dcpext` | `0x10` | `0x2d` | `0x27701` | `0x2ee01` | RMX `0x1f0000ff`, DISPEXT_FE `0x23ff`, DISPEXT_CPU0 `0x1404024f` |
  | `gfx-asc` | skipped | | | | GFX `0x0f002b00` |
  | `ans` | skipped | | | | ANS2 `0x0f002300`, APCIE `0xff`, APCIE_ST `0x0f000200` |
  | `sio` | skipped | | | | SIO_BUSIF, SIO, SIO_CPU `0x0f000200` |
  | `pmp` | skipped | | | | PMP `0x1f0000ff`, PMS_SRAM `0x0f000300` |

  What this says against the captures:
  - **`dcp` and `dcpext` run** at the driver's entry (+`0x44` `0x10`, bit 4; their blocks answer).
    +`0x48` reads **`0x2d`** (bits 0, 2, 3, 5) for both, where macOS read `0x2e` (bits 1, 2, 3,
    5) in every instance, each time after the two power messages and just before writing +`0x44`
    = 0 (section 0). The mailbox words read in the bit-17 form ("empty", no message waiting).
    Which of `dcp`'s endpoints are started, and what either answers, was not read.
  - **`dcpext` runs under Linux with its domains on; under macOS awake it is stopped with its
    domains off** (E2a), and macOS boots it in E2 only to stop it.
  - **`gfx-asc`, `ans`, `sio`** have their domains at state 0 with request 0 at the driver's
    entry; with Linux awake GFX, ANS2 and SIO_CPU read on (L14), so they go off between the two
    (by what is not in these readings). PMP reads on (`0x1f0000ff`) and PMS_SRAM off; `pmp`'s words were not read.
  - **The 137 domain words before the entry are the same in ds13, ds14 and ds15** (three boots)
    except the cores' words (which core reports on: L12): ds15 against ds13 2 differ (ECPU0,
    ECPU3), against ds14 2 (ECPU0, PCPU3). Between ds15's "ps prepare" and "ps wake" (the cores
    started again, no driver) eight differ: ECPU1-3, PCPU0-3 `0x100` -> `0x1f0`, and NUB_SPMI0
    `0x1400024f` -> `0x1f0002ff` (as in ds13, L1).
  - **Request 4 at the entry**, twelve words: SOC_SPMI0-2 `0x0f000244`; PMS_FPWM0-4, AFT0,
    DEVC0_IVDMC, FPWM0, FPWM2 `0x244` (section 4.3, form 3, seen under macOS at the wake only).
    FPWM1 reads `0x0a00` (request 0, state 0, bits 9 and 11).
  - **The first port's words** (R54, D4): ATC0_COMMON `0x22ff`, ATC0_USB_AON `0x2ff`, ATC0_USB
    `0x2ff`, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB `0x3ff`. **The nine never written
    by macOS** (R56): ATC1_COMMON `0x23ff`; ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB,
    ATC1_PCIE `0x3ff`; MSG, ATC1_USB_AON, ATC1_USB `0x2ff`: all on, bit 28 clear. ATC1_CIO,
    ATC1_CIO_PCIE, ATC1_CIO_USB `0x300` (off).
  - **The 792 words**: 783 equal to ds13's (L1); the nine that differ are `MCC.plane0-3+0x680` /
    `+0x684` (`0xb67` / `0xb93`; ds13 `0x9e5` / `0xa11`) and `DCS3+0x500` (`0x2440004`; ds13
    `0x1440004`), words that also vary between macOS's captures (R47). Against macOS H's commit
    673 equal, 119 different (ds13: 674, 118). So the non-domain differences of L2 (DCSn+`0x7b0`
    = 3, the clock words, the NCO, the always-on clock words) are the same on a second boot.
  - No SError was recorded; the machine stayed up (`echo mem` returned with eight cores online).
- **L16 (runs ds16, ds16b, ds16c, bare metal, 20:26-22:30; evidence "Run ds16", "Observation
  round 4", "Run ds16b", "Run ds16c"; added round 8).** The round-7 driver (logic `2695243`, kernel
  `5e1aadaa2`), command line `var/deepsleep/ds16c.cmdline` (ds16c; ds16 and ds16b add the glue's
  `snap=2` comparison), `apple_deepsleep.alarm_secs=60`.
  - **The entry reaches the commit point.** ds16 and ds16b: the glue's record at the commit is
    'C' (its comparison of the commit list at the commit, written at the commit point). ds16c
    (no diagnostics): 'a' (armed, no failure recorded).
  - **At the commit, words of the commit list changed by themselves**: M = 63 (ds16), 64 (ds16b)
    words whose value at the commit is neither the driver's last write to it nor its reading just
    before the entry. By list index: ds16 551 (`0x23b04003c`), 552 (`0x23b040040`) and a third
    that is 553 (`0x23b040044`) or 41 (`0x200080684`), depending on whether the record's last
    byte was written; ds16b (third and fourth): 554 (`0x23b040048`), 555 (`0x23b04004c`). The
    values are not in the record, and the other words are not identified. Under macOS
    `0x23b04003c` and `040` also change between awake and the commit with no write (bit 8
    cleared, R52); `0x23b040044`-`04c` read `0x80100000` awake and at macOS's commit and
    `0x80100100` before Linux's entry (L2). In both runs the record's third SPMI command did not
    land (its last two bytes are not an index).
  - **After the commit: dark, no reset, no wake.** No answer on Thunderbolt, USB or the network
    (ds16), no wake at the alarm (+60 s) in all three; ds16b: a space-bar press about 11 min in,
    no answer; ds16c: a key press, a short power-button press, the lid closed and opened, about
    20 s apart, no reaction (Naeem at the M1). No reset in 85 min (ds16), about 13 min (ds16b),
    about 4 min (ds16c); each ended with the power button held (ds16's restart has the power
    chip's button-reset record, evidence "Observation round 4", section 4; the evidence of ds17
    states that all three ended with the power button).
  - **Power chip after each** (`var/m1-state/pmu-20261117-215301-after-ds16.txt`,
    `pmu-20261117-223028-after-ds16c.txt`; ds16b from the evidence text): `0x0201` = `04` (the value a power-button start leaves, `docs/hardware/
    m1-air-j313.md`), fault shadow `0x040c00` (button bits 10 and 18 with bit 11), `0xd000` = `01`,
    `0xd00c` = `00` with the clock past the alarm the driver had written (`0xd008`; ds16: alarm
    615,186 s, clock at the dump 620,301 s). *(Round 9.)* `0x9f03` = `0x50` after ds16 and
    ds16c (and before ds16b, `pmu-20261117-220602-before-ds16b.txt`), as after macOS's four
    round-9 runs that reset (1.7d); `0x00` after ds14 (no commit) and after H's, I's, J's and
    K's wakes.
  - With the M3's cable in (ds16, ds16c) the M3 logged its partner's sideband not answering for
    the whole dark period (ds16: about 0.1 s apart for 85 min); this log has not been taken with
    the M1 in a known power-down, so it does not tell powered from not powered.
  - ds16b, on battery: the gauge read full before and after, so the charge does not tell how
    much the dark period drew.
- **L17 (runs ds17, ds17-1, ds17-2, ds17-3, bare metal, 22:36-23:23; evidence "Run ds17", "Runs
  ds17-1, ds17-2, ds17-3"; added round 8).** ds16's logic; the glue arms watchdog 1 at the
  commit point (`apple_deepsleep.wdt=120`, the four writes of R61) after writing 'W' into its
  record; command line `var/deepsleep/ds17.cmdline` (`alarm_secs=60`, snapshot and trace off).
  ds17 on battery with nothing plugged into the M1; ds17-1 to -3 with the M3's cable and the
  charger in; nobody touched the M1.
  - Record in each: `44 57 00 40 2c 3d 02 30 xx 00` = 'W': the commit point reached and the
    watchdog armed there; **the last access before it a 32-bit write to `0x23d2c4000` by core 0**.
  - No wake at the alarm (+60 s); the next kernel start about 133-135 s after the run's start in
    each (the 120 s watchdog plus the entry and the boot); four of four.
  - Power chip after (evidence text; no dump file after these runs): ds17 `0x0201` = `04` (`04`
    before, after ds16c), fault shadow `0x040c00` (as before), `0xd000` = `01`, `0xd00c` = `00`,
    fault log `0xd200` all 0; ds17-1 to -3 `0x0201` = `00` (as det11's wake left it before),
    `0x9f03` = `50`, fault shadow `0x000800` (bit 11 `wdog,reset_in_1` only), `0xd000` = `01`,
    `0xd00c` = `00`.
  - **What this establishes** (with J, 4.4 row 12): watchdog 1, armed at the commit point,
    reset the machine about 120 s later; the same armed watchdog does not prevent macOS's
    power-down (R61). It does not by itself show that the SoC stayed powered (J: the bite and
    control survive a sleep, the count restarts). In ds17 `0x0201` was not written: by the lab's
    decode (4.4) neither the sleep program's sequence 1 (`01`) nor its wake sequence (`00`) ran.
    ds17-1 to -3 started from `00`, which cannot separate "not written" from "`01` then `00`".
- **L18 (earlier Linux runs, another driver, firmware 13.5, 2026-11-16; evidence
  `2026-11-16-run26-watch`, `2026-11-16-run36-38-restart`, `2026-11-16-run40-mac-order`; added
  round 8).** Readings only, recorded as a calibration of the readings of L16 and L17, not as a
  description of any driver. After those runs' entries (the evidence calls their end "the
  release"): in run 26 the boot core was kept up for 2.5 s after the release and sampled every
  10 ms: the always-on block's progress word read `0x01` and watchdog 2 read armed (control 4,
  bite 5 s) from the first sample, no wake source was set, and `0x0201` stayed `04` (with that
  core up, the program did not pass its first step); in the runs without a core kept up the
  machine was reset about 5 s after the release, by something that evidence shows is not
  watchdog 2 (runs 36-38: its deadline moved to 100 s, the reset still came about 5 s after),
  and `0x0201` read `01` after the restart (runs 27b, 32, 36-38, 40). So on this firmware the
  always-on program's first step (watchdog 2 armed, progress `0x01`) was reached with one core
  still running, and the readings `0x0201` and "a reset about 5 s after the end of the entry"
  have moved under Linux before; under the round-7 driver (L16, L17) neither moved, and the
  progress word was not sampled.
- **L19 (Linux awake, stock kernel 7.3.0-0test5, two register scans; added round 10).** The
  lab's register scans (`tools/regmap`, database `var/hwdb/m1-hw.db`): snapshot
  12 (2026-11-16 05:28, on battery, no cable; raw reads `var/regmap/scan-pmgr-1c000/reads.txt`)
  read the whole power-gate page `0x23b71c000`-`0x23b71c704`, 450 words, no fault; snapshot 16
  (2026-11-18 02:12, before hypervisor round 7) read the CPU start/stop block
  `0x23b754000`-`0x23b75401c`, no fault. No driver ran in either. Against macOS (4.1d,
  `r10-checks.txt` part 5):
  - CPU block: all eight words 0, as with macOS awake (at macOS's commit +`0x0` and +`0x4` read
    `0xfe`).
  - Power-gate header: **`0x23b71c000` = 0**; `0x23b71c010`-`0x23b71c080` (stride `0x10`) and
    `0x23b71c088` `0x80000000`. macOS awake and at the commit: all ten `0x80000000`; at every
    wake macOS reads `0x23b71c000` = 0 and sets it (R67).
  - The rest of the page: 31 words of 16 groups differ from macOS's commit value in every run,
    mostly first words with bit 30 clear where macOS has it set (`0x23b71c168`, `198`, `1b0`,
    `1c8`, `1f8`, `240`, `258`, `360`, `390`, `5d0`, `600`, `618`) with the sixth word 0 where
    macOS has `0xc000000`; `0x23b71c348` `0xc0040302` and `35c` `0xc000000` where macOS's commit
    has `0x80040302` and 0; the fifth words of the groups +`0x1c8`-`0x228` 0 where macOS's commit
    has `0x30000000`. Linux had its own devices on, so these group words are not compared as
    requirements; they are listed for a reading at Linux's commit (open question 64).
- **L20 (Linux awake, stock kernel 7.3.0-0test5, 2026-11-18 03:54; evidence "Linux awake, stock
  kernel (2026-11-18 03:54)"; added round 11).** One 32-bit read each over `/dev/mem`, nothing
  suspended, no driver run: `0x23b71c000` = 0, `0x23b71c040` = `0x80000000`, `0x23b754000` = 0,
  `0x23b754004` = 0. The evidence records the values only (no data file). The same as L19 on
  another boot. Under macOS `0x23b71c000` reads `0x80000000` awake and at every commit left
  alone; it read 0 at every wake before macOS set it, and at the commits of `det23`, `det24` after
  the instrument cleared it (R69); boot is not logged. At Linux's commit: not read.
  *(Round 12.)* "Boot is not logged" holds for the full log; the page-touch map of A and B (1.1)
  does reach macOS's boot, and there the first access to the page is a read of `0x23b71c000` =
  **0** (A t 0.934 s, B t 1.063 s; `r12-candidates.txt`): at boot macOS finds the word as Linux
  has it, and has it at `0x80000000` by the time it is idle (8.2 C6).
- **L21 (run ds19, bare metal, 2026-11-18 07:00; evidence "Run ds19"; added round 12).** Kernel
  ds19 (the clean-room logic at `deepsleep-clean` `46dfa94`, passing its tests at `202e351`; the
  glue after its own independent tests and review), command line `var/deepsleep/ds19.cmdline`
  (`wdt=120`, `alarm_secs=60`, no snapshot, trace or probe), cable and charger in. Sleep started
  07:00:47; the M3 saw the host disconnect at 07:00:50.41; **no wake at the alarm**; the M1 came
  back in stock Omarchy with a kernel start of 07:03:02, about 135 s after the start (watchdog 1's
  120 s plus the entry and the boot, as ds17-1 to -3). Record `44 57 00 40 2c 3d 02 30 9b 00` =
  'W' (commit point reached, watchdog armed), the last access a 32-bit write to `0x23d2c4000` by
  core 0. Power chip after: `0x0201` `00`, `0x9f03` `50`, fault shadow `0x000800` (watchdog
  reset only), `0xd000` `01`, `0xd00c` `00`. So the outcome of L17 again, with the round-8 driver.
- **L22 (runs ds19p-74, ds19p-75, 07:05-07:11; evidence "Runs ds19p-74, ds19p-75"; added round
  12).** Kernel ds19 with the glue's probe on (`probe=1`, `probe_k` set per run; command line
  `var/deepsleep/ds19p.cmdline`), cable and charger in; each run: no wake at the alarm, a reset
  about 150 s after the start, `0x0201` `00`. Record byte 1 `'q'` (probe, watchdog armed), bytes
  2-3 k with bit 15 = captured, bytes 4-7 the value; four bits per core c at bits 4c..4c+3:
  - k = 74, `0x00000000`: at each core's final write `ISR_EL1` F, I, A clear and `IPI_SR_EL1`
    bit 0 clear, **cores 0-7**: nothing pending at any core (the state R59 asks for);
  - k = 75, `0xfeeeeeef`: the ISTATUS bit (condition met) of the four timer controls (bit 0 EL2
    virtual, 1 EL2 physical, 2 `CNTV_CTL_EL02`, 3 `CNTP_CTL_EL02`): cores 0 and 7 all four set,
    cores 1-6 all but the EL2 virtual.
- **L23 (runs ds19p, k 20-28 and 67-70, 17:31-18:16; evidence "Runs ds19p, k 20-28 and 67-70";
  added round 12).** Twelve probe runs of ds19 (`probe=1`, `wdt=120`, cable and charger in), one
  value each: the timer controls at the core's final write (k = 18 + 7c + r; r 2 EL2 virtual
  `CNTV_CTL_EL0`, 3 EL2 physical `CNTP_CTL_EL0`, 4 `CNTV_CTL_EL02`, 5 `CNTP_CTL_EL02`; bit 0
  ENABLE, 1 IMASK, 2 ISTATUS). Every run ended in the watchdog reset.

  | Core | EL2 virtual | EL2 physical | `CNTV_CTL_EL02` | `CNTP_CTL_EL02` |
  |---|---|---|---|---|
  | 0 | `0x4` (off, met) | `0x7` (on, masked, met) | `0x7` | `0x7` |
  | 1 | `0x0` | `0x0` | `0x0` | `0x7` |
  | 7 | `0x0` | `0x0` | `0x0` | `0x7` |

  No timer is on and unmasked at these cores' final write; several are on and masked with their
  condition met. Each value is from a separate run. Core 7's ISTATUS bits read 0 here for three
  controls and 1 in L22's run: run-to-run variation or a misreading in one of the two modes, not
  settled (evidence). Cores 2-6 not read. Against macOS (R59, R65): `CNTP_CTL_EL02` is `0x6`
  (ENABLE 0) at every core's final write in the six captures that read it and 0 in A-J (the
  instrument's), so ENABLE 1 there is a difference (8.2 C13); the EL2 timers at macOS's
  power-downs are the instrument's own and were stopped by it in all fifteen (A6).
- **L24 (the commit walk, ds19, running 2026-11-18 from 18:41; `var/commit-walk/ds19-commit-118.tsv`,
  the observation stage's file, not yet in the evidence file; added round 12).** The 118 words of
  L1 (the indices of `var/commit-walk/differing-118.k`, in the key order of
  `macos135-det8-real-commit.json`), read at Linux's commit point, one per run. Record: byte 1
  `'c'`, bytes 2-3 the index with bit 15 = changed by itself, bytes 4-7 the value at Linux's
  commit (little-endian); bytes 8-9 are not interpreted here. **12 of 118 had arrived when this
  round was written** (at 19:00), none flagged changed by itself:
  - indices 0, 1, 20, 21, 40, 41, 60, 61 (`MCC.plane0-3+0x680`/`+0x684`): `0xb51`, `0xcfa`,
    `0xc85`, `0xc30`, `0xdef`, `0xb51`, `0xf56`, `0xb9b` (words that vary under macOS and are
    emulated under the instrument, A5);
  - indices 81, 137, 193, 249 (**`DCS0+0x7b0` to `DCS3+0x7b0`**): **3** each, as before the
    entry (L2); macOS: 0 at every reading (8.2 C4).
  *(Round 13.)* The file as read for this round (unchanged since 19:01:21 on 2026-11-18): 13 of
  118; the thirteenth, index 305 (`DCS4+0x7b0`), also **3**. The three C3 words are indices
  621-623, the walk's positions 67-69 (8.2 C3).
- **L25 (runs ds20, one candidate switch at a time, bare metal, 2026-11-18 21:17-22:48; evidence
  "Runs ds20, candidate switches one at a time", commit `a166e89`; `var/commit-walk/ds20-cand.tsv`;
  added round 13).** Kernel ds20 (`7cec0b40b`: the clean-room logic `713a453`, passing 308/308 of
  the tests at `2808844`; the glue with `apple_deepsleep.cand`, 132/132 glue tests at `ecd2ef8`),
  command line `var/deepsleep/ds20.cmdline` (`wdt=30`, alarm +60 s, no diagnostics), cable and
  charger in; each run one boot with one switch set and a real sleep (`tools/tb/m1-cand-runs`).
  The candidates are the round-12 texts of 8.2.

  | Switch (`cand`) | Outcome | Record (`0x9f04`-) |
  |---|---|---|
  | C3 (`0x8`) | **dark**: no answer, the Thunderbolt link still up, screen dark, 246 s until the power button | `44 61 00 ...`: 'a' (armed) only: the commit not reached, **no failure recorded** |
  | C5 (`0x20`) | **dark**: the same, 247 s until the power button | `44 54 c0 01 70 3b 02 10 80 00`: 'T', **a wait ran out, on a 32-bit read of `0x23b7001c0` (SIO_BUSIF) by core 0**; the M1 then hung instead of returning to Linux |
  | C17, C1, C4, C8, C9, C10, C13, C15 (`0x20000`, `0x2`, `0x10`, `0x100`, `0x200`, `0x400`, `0x2000`, `0x8000`) | reset 62-63 s after the start: the commit reached, watchdog 1's reset | `44 57 00 40 2c 3d 02 30 xx 00`: 'W', each |

  After every reset: `0x0201` = `04`, fault shadow `0x000c00`. Not run alone: C2, C6, C7, C11,
  C12, C14, C16. **No switch alone let the SoC power down.** In the two dark runs watchdog 1 was
  not armed (the glue arms it at the commit point only, L17), so nothing ended the run (D7).
- **L26 (run ds20, every switch but C3 and C5, 2026-11-19 00:05-00:08; evidence "Run ds20, all
  candidate switches but C3 and C5 together", commit `10db7c8`; added round 13).** `cand` =
  `0x3ffd6` (C1, C2, C4, C6-C17), otherwise as L25: reset 63 s after the start, record `44 57 00
  40 2c 3d 02 30 a0 00` ('W': the commit reached, watchdog armed), `0x0201` = `04`, fault shadow
  `0x001c00` (bit 12 set since the USB-C restart test at 23:57, evidence). **With every candidate
  but C3 and C5 on together the SoC still stays up after the commit.**
- **L27 (Linux awake, stock kernel, 2026-11-18 21:15; evidence "Linux awake (2026-11-18 21:15):
  the C3 words against the CPU clusters' state", commit `d6f08a1`; added round 13).** Stock
  Omarchy 7.3.0-0test5, read over `/dev/mem`; found with `cpufreq/boost` = 1 and both policies
  on the `performance` governor at their maximum while idle. `0x23b058000`, `0x23b05c000`,
  `0x23b060000` read **`0x444`, `0x666`, `0x333` in all four settings** — as found (cluster
  command words `0x210e20020` `0x105105`, `0x211e20020` `0x10f10f`), maximum = minimum frequency
  with boost 0 (both `0x101101`), maximum with cpu0 and cpu4 busy (`0x105105`, `0x10f10f`),
  restored. The words do not follow the CPU clusters' state.
- **L28 (earlier Linux runs under the hypervisor, another driver, 2026-11-16; private files
  `tools/hv-trace-kit/runs/20261116-linux/s2r-trace-lx12.jsonl`, `-lx13`, `-lx14`, `-lx17`,
  `touch-dsh2.jsonl`, `var/commit-state/linux-live-wide.json`; evidence
  `2026-11-16-run41-mac-state`, `2026-11-16-dram-controller-state`; added round 13).** Readings
  only, as L18, not a description of any driver. The instrument's snapshot when the last core
  reached Linux's commit read **`0x23b058000` = `0x333`, `0x23b05c000` = `0x444`,
  `0x23b060000` = `0x222`** (macOS's values) in all four runs: lx12 (run 40's kernel), lx13,
  lx14, lx17 (run 41's). The evidence names no write of these three words by run 40's kernel
  (the 54 words run 41 set as macOS has them were those that differed at lx12's commit, and these
  three did not). The bare-metal runs of that driver took the always-on program's first step
  (L18). Linux awake read `0x444`, `0x666`, `0x333` on the same day (`linux-live-wide.json`,
  2026-11-17 00:24) and under the instrument 46 s before dsh2's entry (`touch-dsh2.jsonl`,
  L10); under the m1n1 proxy, before any operating system, the same
  (`m1n1-proxy-wide.json`, 2026-11-16 23:48). Also from that day (evidence
  `2026-11-16-dram-controller-state`, lx20): with the hypervisor's shell writing the proxy's
  values back into the clock block after an earlier driver's commit, the M1 stopped answering
  during that block, the last error at `0x23b05c000`, in the same second as watchdog 2's 100 s
  deadline: cause not separated.
  *(Round 15; L30.)* In lx12-lx14 and lx17 that kernel had started `pmp` and sent
  `0x0020e00000550000` at its entry, 0.25-0.37 s before each snapshot; so these four commits are
  not "Linux without `pmp`".
- **L29 (Linux awake, stock kernel 7.3.0-0test5, 2026-11-19 01:10-01:15; evidence "Linux round:
  pmp and the endpoint-0x20 message", commit `e4a3951`; `var/commit-state/linux-pmp-series-20261119.txt`;
  added round 15).** Read over `/dev/mem`, 32-bit, read-only; the mailbox FIFOs not read; no message
  sent. **`pmp` is not started and nothing in this kernel reaches it:** the live device tree
  (root `apple,j313 apple,t8103`) has no node at `0x23bc00000`, `0x23bc08000` or `0x23b300000`; the
  power-manager children for PMP (`power-controller@3d8`) and PMS_SRAM (`@3e0`) are present. The
  module `apple_pmp` is loaded (used by `appledrm`, `aurora`), its aliases name other chips only
  (`t8132`, `t8140`, `t8142`, `t6041`, `t6050`, `t6000`), and no device is bound to it or to any
  `pmp`/`rtkit` driver; `dmesg` has no `pmp` line. genpd: `pmp` on, `pms` on, `pms_sram` off.
  Words: +`0x44` **`0x0`**, +`0x48` `0x2a` (as the bare proxy, 1.7h), A2I and I2A control `0x20001`
  (empty), PMP `0x1f0000ff`, PMS_SRAM `0x0f000300`, PMS `0x1f0000ff`, DCS0 `0x1f0002ff`, cluster
  commands `0x105105` / `0x10f10f`; the C3 words **`0x444/0x666/0x333`, unchanged in 60 samples at 1
  s**. Present in that kernel (its config and `Module.symvers`): `CONFIG_OF_OVERLAY`,
  `CONFIG_APPLE_MAILBOX`, `CONFIG_APPLE_RTKIT`, `CONFIG_APPLE_DART` built in; `apple_rtkit_init`,
  `_wake`, `_start_ep`, `_send_message`, `apple_mbox_get` exported. *Documentation, not an
  observation* (aurora-silicon/linux `integration/aurora` `1f38ff8f4`): the reference tree's
  `t8103-peripherals.dtsi` has `pmp: coprocessor@23bc00000` (`apple,t8103-pmp`, `apple,pmp`;
  power domains `ps_pmp`, `ps_pms_sram`; `iommus = <&pmp_dart 0>`), the mailbox node
  (`apple,t8103-asc-mailbox`, `apple,asc-mailbox-v4`) and `pmp_dart`, all disabled, and no driver
  in that tree matches them; its `pmp_power.rs` power command cannot make `0x0020e00000550000`
  (1.7h). That `pmp` "has never run under Linux here" holds for this kernel only (L30).
- **L30 (earlier Linux runs with `pmp` started, another module, 2026-11-05 to 11-17; evidence
  "Earlier Linux runs with pmp started", commit `c3443a6`, and the run files it cites; added round
  15).** Readings only, as L18 and L28, not a description of any driver; the module is named in the
  evidence only to identify the runs. Firmware 13.5 from 2026-11-14 on. **`pmp` was started under
  Linux, its handshake and endpoint `0x20`'s opening answered:** bare metal on 11-05, 11-08 (by its
  README), 11-14 and in runs 37 and 39 (11-16), and by command line in runs 40-43 (no log of their
  start kept); under the hypervisor
  lx3, lx4, lx9, lx11-lx14, lx16-lx24. In every logged start (bring-up of 11-14 17:49; lx12): PMP and
  PMS_SRAM `0x1f0000ff` (held on) and +`0x44` 0, +`0x48` `0x2a` before; nodes added by overlay at
  the load; then RECV HELLO, **SEND SET_IOP_POWER `0x220`**, SEND HELLO_ACK, the EPMAP words as
  macOS's boot, STARTEP 1-4, IOP power ack `0x20`, AP `0x20` echoed, STARTEP `0x20`; buffer replies
  `0x00101000fffec000` (ep 1), `0x00110000fffd0000` (ep 4), `0x00101000fffcc000` (ep 2); no kdebug
  words; endpoint 4's `0x00c…` once and type 8 125 times each way; on endpoint `0x20` RECV `0x0`,
  **SEND `0x00010000ffff0000`**, RECV `0x000200000023b549` 63-65 ms later, then the 0/1 and 2/3
  pairs exactly as macOS's (R72); `pmp`'s syslog "PMP started". With "reports" on, 13 code-`0xe`
  words at the start (among them `…550001`), none answered. After the start PMP `0x1f0f03ff`,
  PMS_SRAM `0x1f0003ff`; **no Linux reading in these files shows `0x1000030f`.** At the entry
  (kernels run40/run41, lx9, lx11-lx14, lx16-lx21): within 3 ms `…550001`, `…540001`, **`…550000`**,
  `…540000`, `0x0020800000630000` (answered `0x0020900000630000`), then AP and IOP `0x201`, both
  answered; `…550000` 0.12-0.19 s after the `slpw` key; no code-`0xe` word answered. Run 39's
  kernel (lx3, lx4) sent no `0x20e` word at the entry. **The C3 words** were read only at the four
  commit snapshots of L28 (lx12-lx14, lx17): `0x333/0x444/0x222`, PMP `0x1f0f03ff`, PMS_SRAM
  `0x1f0003ff`, 0.25-0.37 s after `…550000`; not before the start, between the start and the entry,
  or in a run without `…550000` (lx4's 30-word snapshot did not include them): these runs do not
  separate the start, the word and the entry. After an entry that did not reach its commit Linux sent
  SET_IOP_POWER `0x220` and **`pmp` did not answer** (lx3, lx9). **None of these runs powered down
  and woke** (bare metal: a restart 5-30 s after the entry or its end, or no wake; hypervisor: the
  CPUs exited to the instrument, a restart, or no wake). Not started: every other bare-metal run of
  11-14 to 11-16, the clean-room runs ds2-ds20, lx1, lx2, lx5-lx8, lx10, lx15, dsh1, dsh2.
- **L31 (Linux awake, stock kernel 7.3.0-0test5, 2026-11-19; read-only; from the orchestrator's
  brief of round 15b, not yet in the evidence file; added round 15b).** **systemd (pid 1) holds
  `/dev/watchdog0`**, which is `23d2b0000.watchdog`, Linux's `apple_wdt` on watchdog 1 (the
  watchdog of R61 and D7), with `RuntimeWatchdogUSec=30s`; the journal has "Watchdog running with a
  hardware timeout of 30s". This boot had the stock command line, not the lab's test command line
  (which carries `systemd.watchdog_sec=0`); the state of `apple_wdt` under the test command line,
  `/sys/class/watchdog/watchdog0/state`, and the bite and control words were not read (open
  question 81). *Not an observation:* the glue's reviewer reports from Linux's code that
  `apple_wdt`'s resume step restarts watchdog 1 (count 0, reset enabled) when it is active, after
  the platform's wake step; this spec has not read that code and uses the report only as the
  reason for D7 (c) and (e).
  *(Round 15c.)* The reference's code (aurora-silicon/linux `1f38ff8f4`,
  `drivers/watchdog/apple_wdt.c`) has been read as reference since: its resume step starts watchdog
  1 (count 0, control = reset enable) when the device is active **or** marked running in hardware,
  its suspend step stops it (control 0) on the same condition, and its probe marks it running in
  hardware when it reads the control's reset enable; the test kernels' own code is not read.
- **L32 (Linux awake, stock kernel `7.3.0-0test5-1-ARCH` and ds21 `7.2.11-ds21`, 2026-11-19
  02:59-03:05; read-only, no sleep started, no `/dev/mem`; evidence "ds21", section "Watchdog reads",
  commit `33ef97f`; added round 15c).** On **ds21's command line** (`panic=10
  systemd.watchdog_sec=0 apple_deepsleep.enable=1 apple_deepsleep.alarm_secs=60 no_console_suspend
  apple_deepsleep.wdt=30`): **no process holds `/dev/watchdog` or `/dev/watchdog0`** (every
  `/proc/*/fd`); `systemctl show`: `WatchdogDevice=` empty, `RuntimeWatchdogUSec=0`,
  `RebootWatchdogUSec=0`; no systemd hardware-watchdog line in the journal; `apple-watchdog`
  (`apple_wdt`, built in) bound to `/soc/watchdog@23d2b0000`, but `/sys/class/watchdog/watchdog0`
  is under `/sys/devices/virtual/watchdog/` with **no `device` link** (cause not read). On the
  **stock** command line: systemd (pid 1) holds `/dev/watchdog0` (fd 15), `RuntimeWatchdogUSec=30s`,
  `RebootWatchdogUSec=2min`, from `/etc/systemd/system.conf.d/90-maclab-watchdog.conf` (present on
  both boots; `systemd.watchdog_sec=0` makes it read 0); `watchdog0` -> the platform device, with a
  `device` link. On both: `CONFIG_WATCHDOG_SYSFS` not set (no `state`, `timeout`, `bootstatus`,
  `identity`, `hw_running`, `timeleft`, `nowayout`), `WATCHDOG_HANDLE_BOOT_ENABLED=y`,
  `WATCHDOG_NOWAYOUT` not set, `watchdog.handle_boot_enabled=Y`. Not read: whether watchdog 1 was
  running in hardware (`WDOG_HW_RUNNING`), `0x23d2b0014` and `0x23d2b001c` (open question 81). The
  same evidence's two `wdt=30` runs of ds21 (`cand` `0x3fffe` and `0x1020`) each reached the commit
  point (the C3 record, D8 (f)'s own example bytes `64 43 36 64 f3 00 00 00` after 'D' 'V'; and 'W')
  and ended in a reset, first answer 62-63 s after the start, fault shadow bit 11 only; whether the
  chip powered down first, and whether the reset was watchdog 1's, are not read.

## Appendix: scripts and extracts (all in `var/spec/`)

Run with `tools/hv-trace-kit/venv/bin/python`, from `var/spec/`, after `build_db.py 3` and
`build_db.py 4`.

| Script | Produces |
|---|---|
| `build_db.py` | `db/cap3.db`, `db/cap4.db` |
| `rate.py` | access rate per 5 s |
| `idle.py`, `idle_seq.py` | `idle-N-pre.tsv`, `idle-N-post.tsv`; cycle and burst statistics |
| `firstdiff.py` | first accesses that differ from idle |
| `devtable.py` | `devtable-pre.tsv`, `devtable-post.tsv` |
| `console.py` | `console-N-pre.txt`, `console-N-post.txt` |
| `phases.py`, `seg.py` | `phases-<pre|post>-N.tsv`, `phases-<pre|post>-compare.tsv` |
| `compare.py` | `compare-<pre|post>-<tag>.tsv` |
| `ps.py` | `ps-<pre|post>-N.tsv` |
| `buses.py`, `smcw.py` | `spmi-<pre|post>-N.txt`, `mbox-<pre|post>-N.txt`; SMC key writes |
| `commit_state.py` | `commit-last-writes.tsv`, `snap-pre-full.tsv`, `snap-wake.tsv` |
| `saverestore.py` | `saverestore-N.tsv` |
| `hvlog.py` | `hvlog-wake-N.txt` |
| `extract.py`, `view.py` | `entry-early-N.tsv`, `wake-late-N.tsv`; ad-hoc views |
| `backtoidle.py` | return to idle after the wake |
| `leadcheck.py` | `memory-controller-shutdown-writes.tsv`; checks of earlier notes against the captures |
| `build_db_det.py` | `db/capd.db` (capture D) |
| `det_events.py` | `det-events.tsv`, `det-sysreg.tsv`: the hypervisor-handled records of D with times |
| `det_misc.py` | D's idle rates, first non-idle access, return to idle; `phase-times.tsv` for all three |
| `three.py` | three-way segment comparison (needs `phases.py` run with `DROP4=1`, `CAPS=3,d`, `CAPS=4,d`) |
| `reqcheck.py` | the register values behind section 8 checked in all five captures |
| `build_db_det.py RUN KEY` | also `det5 e` -> `db/cape.db`, `det4 f` -> `db/capf.db` |
| `five.py` | five-way segment comparison, and D against E and F |
| `cable.py` | what the machine's log shows around the cable events (`DET=e` or `f`) |
| `cancelled.py` | the cancelled entry of capture F |
| `build_db_det.py det8 g` | `db/capg.db` (capture G) |
| `commit_snap.py` | `commit-snapshot-g.tsv`: the commit snapshot against idle, the wake and macOS's last writes |
| `det_down.py` | `det-down-g.tsv`: each core's system-register accesses on the way down, named |
| `det_events.py`, `det_misc.py` with `DET=e` / `DET=f` | `det-events-e.tsv`, `det-sysreg-e.tsv`, `-f`; idle and phase times |
| `build_db_det.py det9 h` | `db/caph.db` (capture H; `lib.py` now lists `h` in `ALLCAPS`, `DET`, `SLIDE`) |
| `commit_gh.py` | `commit-state-gh.tsv`: the 858 commit words of G and H, awake value, path, reads, Linux readings |
| `snapvar_gh.py` | `snapvar-gh.tsv`: the changed or varying commit words in every snapshot of all seven captures |
| `ps_commit_gh.py` | `ps-commit-gh.tsv`: the 137 domain words, macOS G and H at the commit, at E3, at the wake, Linux ds6, dsh1, ds13 |
| `gaps_gh.py` | `gaps-gh.txt`: readings for the gap list (sub-blocks, waits, R21 words, R19 words, R36w rule, mailboxes, S1, S11, gap 9, core order) in all seven captures |
| `mbox_status.py` | the +`0x8114` forms before reply reads, every mailbox, all seven captures |
| `adt_domains.py` | `adt-domains.tsv`: the domains each device-tree node names |
| `seven_h.py` | H against D, G, A by console segment (needs `phases.py` with `CAPS=d,h`, `g,h`, `3,h`) |
| `buses.py` with `CAPS=h,h` | `spmi-pre-h.txt`, `spmi-post-h.txt`, `mbox-pre-h.txt`, `mbox-post-h.txt` |
| `build_db_det.py det10 i` | `db/capi.db` (capture I; `lib.py` lists `i` in `ALLCAPS`, `DET`, `SLIDE` = `0x86c000`) |
| `buses.py pre -40 0` / `post 0 40` with `CAPS=i,i` | `spmi-pre-i.txt`, `spmi-post-i.txt`, `mbox-pre-i.txt`, `mbox-post-i.txt` |
| `phases.py pre` / `post` with `CAPS=h,i` | `phases-pre-compare-hi.tsv`, `phases-post-compare-hi.tsv` |
| `gaps_gh.py` (now over A-I) | `gaps-ghi.txt` |
| `commit_ghi.py` | `commit-state-ghi.tsv`: I's 862 commit words, awake values of G, H, I and I's "awake-extra", commit values G/H/I, I's path, wake values |
| `snapvar_ghi.py` | `snapvar-ghi.tsv`: changed or varying commit words in every snapshot of all eight captures |
| `commit_list.py` | `commit-list.md`: the 725 non-domain commit words with values (appendix B) |
| `ps_off.py` | `ps-forms.tsv`, `ps-forms.txt`: every run of accesses to a domain word that contains a write, D-I (section 4.3) |
| `coproc_stop.py` | the stop of `dcp`, `dcpext`, `gfx-asc`, `ans`, `sio`, `pmp` and DISP0_CPU0's values (E2a) |
| `reset_reads.py` | `reset-reads.tsv`: words the wake reads with a value the entry did not leave (6.4) |
| `linux_diff_list.py` | `linux-diff-list.md`: the non-domain words where Linux ds13 differs from macOS H, with addresses (L2) |
| `r7_coproc_words.py` | `r7-coproc-words.txt`: every access to +`0x44`, +`0x48`, +`0x8110` of each coprocessor, all eight captures (section 0, E2a) |
| `r7_stops.py` | `r7-stops.txt`: the 76 stops message by message; endpoint-stop order and alternation (E2a, R5a) |
| `r7_mbox_seq.py CAP SIDE COPROC T0 T1` | one coprocessor's sent and received words and control-word accesses in a window, with widths |
| `r7_dart_disp.py CAP`, `r7_dart_rule.py` | the display translators' accesses; `r7-dart-rule.txt`: the rule of every +`0xfc` write (E2a item 3) |
| `r7_wake_display.py CAP [t]`, `r7_wake_display_sum.py` | display domains and `dcp`/`dcpext` after the wake; `r7-wake-display.txt` (W4, R58) |
| `r7_stop_domain.py` | each `dcp`/`dcpext` start and stop in D-I against its CPU0 domain word's writes (W4, R58) |
| `r7_rmx.py` | every RMX write in D-I with the read before and after and the pc (4.3) |
| `r7_bit28.py` | `r7-bit28.txt`: every bit-28 clear with request kept, and the reads after (E2a) |
| `r7_bits24.py` | bits 24-27 against bits 4-7 over every domain-word read (section 0) |
| `r7_pcie_widths.py` | `r7-pcie-widths.txt`: the ten PCIe words with two widths, access by access (1.8) |
| `r7_linux_ds15.py` | `linux-ds15.json`: run ds15's log lines parsed; comparisons with ds13, ds14 (L15) |
| `r8_det11.py` | `r8-det11.txt`: capture J read from its log (no database): T, the cores' records, the instrument's commit writes and wake reads, the watchdog page, the last 40 ms of power-manager and SPMI accesses, phase starts, burst 2, the commit and wake snapshots against G, H, I (1.7c) |
| `r9_det12.py` | `r9-det12.txt`: capture K read from its log (no database): T, the three writes of `0x23d2c4000`, the watchdog page in the last second, the cores going down, the commit snapshot's always-on, watchdog and wake-mask words with each count's start time (1.7d, 4.1c, R62) |
| (observation stage) `var/commit-state/r6_core_state.py`, `r6_snapdiff.py` | `r6-det12.txt` (each core's state at its final write, E7), `macos135-det12-vs-det11.txt` (K's commit and wake snapshots against J, 1.7d) |
| (observation stage) `var/commit-state/r7_probe.py`, `r7_wd2start.py`; `r6_core_state.py` on the round-10 logs | `r7-det18.txt`, `r7-det19b.txt`, `r7-det21.txt` (the probe sets, the CPU block and the power-gate page awake and at the commit), `r7-wd2start-det*.txt` (watchdog 2's start against the log), `r7-det*-core-state.txt` (E7), `r7-pwrgate-records.md` (1.7e, 4.1c, 4.1d) |
| `r11_checks.py` | `r11-checks.txt` (round 11): `det18`, `det23`, `det24` from their detached logs: the instrument's write of `0x23b71c000` (probe sequence 100, with values) against the core-state and core-down records; the header words and CPU block awake and at the commit; every access to `0x23b71c000`, `040`, `080`, `088`; the probe sets and watchdog 2's start against `W 0x23b718004` = 0; each core's guest timer and due time, `HCR_EL2` VI/VF, the instrument's IPI words, `ISR_EL1`, `IPI_SR_EL1`, `PMCR0_EL1`, `PMSR_EL1`, `PSTATE` DAIF; the wake status, wake-entry words and the time of the header write; every write before T to the watchdog page and the wake-source masks (also `det19b`, `det21`) (1.7f, E7, 4.1c, 4.1d, R62, R63, R67, R69) |
| `r12_candidates.py` | `r12-candidates.txt` (round 12): every logged access in A-I (full logs and A's and B's boot page-touch map) to the words of the candidates C1-C17, per word and capture the values read and written and the times (8.2) |
| `r13_c3_words.py` | `r13-c3-words.txt` (round 13): in every detached capture, the C3 words and their stride-`0x4000` row in the commit and wake snapshots, and every access to `0x23b050000`-`0x23b07ffff` before and after the wake (8.2 C3, R70) |
| `r13_c3_boot.py` | `r13-c3-boot.txt` (round 13): in all 48 touch maps (each from the instrument's start), every snapshot value of the C3 words by tag, and every record in their three pages (8.2 C3, R70) |
| `r13_c5_domains.py` | `r13-c5-domains.txt` (round 13): in every detached capture, every access to C5's twelve domain words and to PMS, SIO_BUSIF, SIO, SIO_CPU, and their commit and wake snapshot values, with times from the wake (8.2 C5) |
| `r13_recfg.py` | `r13-recfg.txt` (round 13): from the lab's decode of the always-on program (`var/map-20261117/recfg/things*.json`), every operation on the C3 words, C5's twelve domains and PMS, SIO_BUSIF, SIO, SIO_CPU, by sequence (8.2 C3, C5) |
| `r10_checks.py` | `r10-checks.txt`: the probe sets and the start of watchdog 2 against `0x23b718004` = 0; each core's guest timer, due time, virtual FIQ and timer FIQ enable in L, `det19b`, `det21`; the CPU block and the 23 power-gate words that change; every access to the four header words in all thirteen captures with a wake (databases and detached logs); Linux's register scans (snapshots 12 and 16) against macOS (1.7e, E7, 4.1c, 4.1d, L19) |

Capture selection: the pairwise scripts compare the two captures named in the environment
variable `CAPS` (default `3,4`; `3` = A, `4` = B, `d` = D); outputs of other pairs carry the
pair in the file name (`phases-pre-compare-3d.tsv`, `commit-last-writes-4d.tsv`, ...). Files
ending `-no4` are A or B with the four pages D did not trap removed. Window arguments may be
seconds or console anchors (`'@awdl0 disable'`, `@START`, `@END`). Per-capture extracts of D:
`phases-pre-d.tsv`, `phases-post-d.tsv`, `console-d-pre.txt`, `console-d-post.txt`,
`ps-pre-d.tsv`, `ps-post-d.tsv`, `mbox-*-d.txt`, `spmi-*-d.txt`, `saverestore-d.tsv`.


## Appendix B: the non-domain words of the commit list, with their values at the commit (G, H, I)

*(Added this round, gap Q5.)* From `commit_list.py` over `commit-state-ghi.tsv`. 725 words: G's
792 less the 71 domain words it holds, plus I's four sub-block status words (I only). A value
written `x` / `y` / `z` is G / H / I and varies (4.1b); one value means the same in every capture
that read the word. Every word here holds its own capture's awake value except the non-domain
words of 4.1a item 3 and 4.1b item 3 (clock words, `0x23b720030`/`034`/`044`, power-gate and
always-on clock words that change, the four status words); the five clock muxes of R18 are
written but hold their awake value. The 137 domain words are in 4.2a.

- **MCC plane P (P = `0x200000000`, `0x200040000`, `0x200080000`, `0x2000c0000`)**: +`0x680` `0x800/0xe59/0xad1`; +`0x684` `0x82c/0xe85/0xafd`; +`0x68c` `0x1`; +`0x690` `0x0`; +`0x694` `0x51d`; +`0x698` `0x1`; +`0x69c` `0x1`; +`0x6a0` `0x1df024`; +`0x6a4` `0x1e0ddb`; +`0x6a8` `0x1`; +`0x6ac` `0x1`; +`0x6b0` `0x1df01c`; +`0x6b4` `0x1df023`; +`0x6b8` `0x1`; +`0x6bc` `0x1`; +`0x6d0` `0x1e6e24`; +`0x6d4` `0x1ffe23`; +`0x6d8` `0x1`; +`0x6dc` `0x1`; +`0x1c28` `0x1`.
- **DCSn (`0x200200000` + n x `0x40000`, n = 0..7)**: +`0x500` `0x10480004` `0x2440004/0x2440004/0x1440004` `0x2440004/0x2440004/0x1440004` `0x2440004/0x1440004/0x1440004` `0x2440004/0x2440004/0x1440004` `0x2440004/0x2440004/0x1440004` `0x2440004/0x2440004/0x1440004` `0x2440004/0x2440004/0x1440004`; +`0x7b0` `0x0`; +`0xc090` `0x0`; +`0xc504` `0x0`; +`0xc510` `0x0`; +`0xc51c` `0x0`; +`0xc528` `0x0`; +`0xc534` `0x0`; +`0xc540` `0x0`; +`0xc54c` `0x0`; +`0xc708` `0x0`; +`0xc718` `0x0`; +`0xc728` `0x0`; +`0xc750` `0x0`; +`0x10404` `0x0`; +`0x10410` `0x0`; +`0x1041c` `0x0`; +`0x10428` `0x0`; +`0x10434` `0x0`; +`0x10440` `0x0`; +`0x1044c` `0x0`; +`0x10458` `0x0`; +`0x10470` `0x0`; +`0x1047c` `0x0`; +`0x10488` `0x0`; +`0x10494` `0x0`; +`0x104a0` `0x0`; +`0x104ac` `0x0`; +`0x104b8` `0x0`; +`0x104c4` `0x0`; +`0x104d0` `0x0`; +`0x104e8` `0x0`; +`0x10638` `0x0`; +`0x10654` `0x0`; +`0x1065c` `0x0`; +`0x14404` `0x0`; +`0x14410` `0x0`; +`0x1441c` `0x0`; +`0x14428` `0x0`; +`0x14434` `0x0`; +`0x14440` `0x0`; +`0x1444c` `0x0`; +`0x14458` `0x0`; +`0x14470` `0x0`; +`0x1447c` `0x0`; +`0x14488` `0x0`; +`0x14494` `0x0`; +`0x144a0` `0x0`; +`0x144ac` `0x0`; +`0x144b8` `0x0`; +`0x144c4` `0x0`; +`0x144d0` `0x0`; +`0x144e8` `0x0`; +`0x14638` `0x0`; +`0x14654` `0x0`; +`0x1465c` `0x0`.
- `0x23b000000`..: `0x23b000000` `0x1`; `0x23b004000` `0x1`; `0x23b008000` `0x1`; `0x23b00c000` `0x1`.
- `0x23b010000`..: `0x23b010000` `0x1`; `0x23b014000` `0x1`; `0x23b018000` `0x1`; `0x23b01c000` `0x1`.
- `0x23b040000`..: `0x23b040000`-`0x23b040004` `0x87100100`; `0x23b040008` `0x86100100`; `0x23b04000c`-`0x23b040010` `0x87100100`; `0x23b040014` `0x85100100`; `0x23b040018` `0x85100000`; `0x23b04001c` `0x85120000`; `0x23b040020` `0x85100000` / `0xc5100000` / `0x85100000`; `0x23b040024` `0x87100000`; `0x23b040028` `0x85100100`; `0x23b04002c`-`0x23b040030` `0x86100100`; `0x23b040034`-`0x23b040038` `0x85100100`; `0x23b04003c`-`0x23b040040` `0x87100000`; `0x23b040044`-`0x23b04004c` `0x80100000`; `0x23b040050`-`0x23b04006c` `0x87100100`; `0x23b040070` `0x81100100`; `0x23b040074` `0x82100100`; `0x23b040078` `0x83100100`; `0x23b04007c` `0x84100100`; `0x23b040080` `0x87100100`; `0x23b040084` `0x87200100`; `0x23b040088` `0x88100100`; `0x23b04008c` `0xa0000002`; `0x23b040094`-`0x23b040098` `0x87100100`; `0x23b04009c`-`0x23b0400a0` `0x85100100`; `0x23b0400a4` `0x80100100`; `0x23b0400b0`-`0x23b0400b4` `0x87100100`; `0x23b0400b8` `0x80100100`; `0x23b0400bc` `0x85100100`; `0x23b0400c0`-`0x23b0400c8` `0x87100100`; `0x23b0400cc`-`0x23b0400d0` `0x87100000`; `0x23b0400d4`-`0x23b0400e8` `0x100`; `0x23b0400ec` `0x85100100`; `0x23b0400f0` `0x85100000`; `0x23b0400f4`-`0x23b040110` `0x85100100`; `0x23b040114`-`0x23b04011c` `0x85100000`; `0x23b040120` `0x85100100`; `0x23b040124`-`0x23b040128` `0x85100000`; `0x23b04012c`-`0x23b040130` `0x85100100`; `0x23b040134`-`0x23b040138` `0x87100000`; `0x23b04013c` `0x85100100`; `0x23b040140`-`0x23b040148` `0x85100000`; `0x23b04014c` `0x87100000`; `0x23b040150` `0x85100100`; `0x23b040154` `0x87100000`; `0x23b040200` `0x80000104`; `0x23b048000` `0x80000000`.
- `0x23b050000`..: `0x23b058000` `0x333`; `0x23b05c000` `0x444`.
- `0x23b060000`..: `0x23b060000` `0x222`.
- `0x23b700000`..: `0x23b704000` `0x300`; `0x23b704008` `0xf000300`; `0x23b704010` `0xf000300`.
- `0x23b710000`..: `0x23b719000` `0x47be36e`; `0x23b719004` `0x1`; `0x23b719008` `0x20003`; `0x23b71900c` `0x1`; `0x23b719010` `0x0`; `0x23b719014` `0x1`; `0x23b71c090` `0x8004030c`; `0x23b71c0a8` `0xc0040301`; `0x23b71c0d8` `0xc0040307` / `0x80040307` / `0xc0040307`; `0x23b71c0f0` `0x80040307` / `0x80040307` / `0xc0040307`; `0x23b71c108` `0xc0040307` / `0x80040307` / `0xc0040307`; `0x23b71c120` `0xc0040307` / `0x80040307` / `0xc0040307`; `0x23b71c330` `0x80040317`; `0x23b71c5b8` `0x80040302`.
- `0x23b720000`..: `0x23b720030` `0x1515151`; `0x23b720034` `0x1494949`; `0x23b720038` `0x1313131`; `0x23b72003c` `0x1262626`; `0x23b720040` `0x1000000`; `0x23b720044` `0x1494949`; `0x23b720048` `0x17a7a7a`; `0x23b72004c` `0xd4d4`.
- `0x23b740000`..: `0x23b7483e0` `0x515100`; `0x23b7487e0` `0x494900`; `0x23b748be0` `0x0`; `0x23b748fe0` `0x494900`.
- `0x23b780000`..: `0x23b781000` `0x47be3b6`; `0x23b781004` `0x20`; `0x23b781008` `0x1`; `0x23b78100c` `0x0`; `0x23b783ff8` `0xf`; `0x23b783ffc` `0x1`; `0x23b787ff8` `0x0`; `0x23b787ffc` `0x1`; `0x23b78bff8` `0x0`; `0x23b78bffc` `0x1`.
- `0x23d0d0000`..: `0x23d0da100` `0x1000100`; `0x23d0da160` `0xb870300`.
- `0x23d0e0000`..: `0x23d0e2100` `0x1000100`.
- `0x23d240000`..: `0x23d240000` `0x80100010`; `0x23d240004`-`0x23d24001c` `0x81100100`; `0x23d240020` `0x81100000`; `0x23d240024`-`0x23d240034` `0x81100100`; `0x23d240038` `0x81100000`; `0x23d24003c` `0x81100100`; `0x23d240040` `0x1101100`; `0x23d240044`-`0x23d24004c` `0x82100100`; `0x23d240050` `0x80100100`; `0x23d240054` `0x81100000`; `0x23d240304` `0x10000000`; `0x23d240308` `0x1000000`; `0x23d240314` `0x1000000`; `0x23d240320` `0x0`; `0x23d240330`-`0x23d240370` `0x0`.
- `0x23d2c0000`..: `0x23d2c0000`-`0x23d2c000c` `0x0`; `0x23d2c0010` `0x880ff04`; `0x23d2c0014` `0x7`; `0x23d2c0018` `0x1`; `0x23d2c001c` `0xff0`; `0x23d2c0020`-`0x23d2c003c` `0x0`.

## Changes in round 15c (2026-11-19: the glue test author's gaps GL10-GL13 and the `pmp` client's test author's gaps G1-G27; the sleep step, the panic's record, D7 (e)'s check; who makes each of `pmp`'s steps, and the client's order, buffers, bounds and ways out)

Inputs: the spec at `f411b43` (round 15b); the gap lists `docs/spec/gaps-reported-by-glue-tests-r3b.md`
(lab `f15960c`) and `docs/spec/gaps-reported-by-glue-tests-r4.md` (lab `4e4b50a`, with its fill and
review: G1-G27, G19 amended); the coordinator's message on G26; evidence
`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md` sections "ds21" (`33ef97f`), "macOS's pmp
start-up and endpoint-0x20 exchange", "Hypervisor round 11" and "Earlier Linux runs with pmp started",
with the decoder outputs `var/commit-state/r10-pmpstart-det33-boot.txt`, `-det34b-boot.txt`,
`-det33-entry.txt`, `-det33-wake.txt` for the gaps of D11 (d); *reference, read as data*:
aurora-silicon/linux `integration/aurora` `1f38ff8f4` (`include/linux/suspend.h`,
`drivers/watchdog/apple_wdt.c`, `drivers/soc/apple/rtkit.c`, `drivers/iommu/apple-dart.c`). No
test, glue, driver `src/` or old driver branch was read. No new capture or run. The evidence file is
not changed. Inline marks "round 15c" are this round's. All answers are decisions about Linux except
where a reading is named.

**The glue (GL10-GL13):**
- **GL10** (a `run_on` not answered: disarm or panic?): decided by the core's **release**: the glue
  tries the release as for every parked core; all given back: the plain way back with the disarm; a
  release not answered: the exception (record, panic). D7 (c).
- **GL11** (which callback is the sleep step): **the glue's callbacks from `begin` to `end`**; D7 (e)'s
  check and then R61's four writes first in `begin`, before its record, its clock read, the offlining,
  `dump`'s reads and `enter`; so N also covers Linux's device suspend; "no device access at all in
  that sleep" covers `begin`'s record and read; Linux's abort before `enter` is a way back, disarmed in
  `end`. D7 (a), (c), (d), (e); open question 82 widened.
- **GL12** (no driver bound; which flag): no driver bound to `/soc/watchdog@23d2b0000` gives **"not
  driving"** (the sleep goes on); a bound driver whose state cannot be read gives a refusal; "active"
  and "marked running in hardware" are Linux's `WDOG_ACTIVE` and `WDOG_HW_RUNNING` only, never the
  control word. D7 (e); L32 (ds21: no holder, no `device` link); open question 81 partly answered.
- **GL13** (the panic notifier's 'P'): **the notifier writes nothing on the exception's panic** (the
  glue marks it before `panic()`), so the exception's record stands; on any other panic it writes 'P'
  as before. D7 (c), D8 (c).

**The `pmp` client (G1-G27):**
- **G1** (a domain not on at boot): the client writes no domain at boot (Linux's power-domain driver's,
  through C18 (a)); finding any of the three not at state `0xf` with bit 28: no other access, an error
  from its probe, later parts nothing. D10 (a), (e). **G16** (no buffer) has the same answer: buffers
  are had before any access to `pmp`. D10 (a).
- **G2** (SRAM writes above `0x23b540000`): none but the block's 180 (not logged in any boot; open
  question 79). R71 note.
- **G3** (+`0xfc` = 0 once or twice): **twice**, det10's sequence of writes in full. R71 note.
- **G4, G20, G21, G23** (one answer): **the kernel's RTKit library is not used**; the client sends every
  word itself in macOS's start-up order (written out step by step); no SET_IOP_PWR_STATE at boot, so
  G20's word is not sent (its reference form noted); the library's waits do not occur. D11 (c).
- **G5** (fields and sizes): size bits 44-51 in 4 KiB units, IOVA bits 0-43 (reference fields, every
  value seen agrees); buffers in whole 16 KiB translator pages (PARAMS1 read), 16 KiB aligned, not
  overlapping; the opening's IOVA in bits 0-31; its size not read, one 16 KiB page (open question 83).
  D11 (a).
- **G6** ("at once", "not waited for"): the 0x55 word is the client's next word after
  `0x0020300000010000`, no wait or delay between; "not answered" means no wait for a reply, a delay
  allowed. D11 (a).
- **G7** (buffer requests after boot): re-send the boot's reply for that endpoint if large enough, else
  a new buffer, the old kept; all buffers mapped until unbind, across sleeps. D11 (a).
- **G8** (control-page accesses): exactly R71 (e), R5's and R5w's; parts decided by the client's own
  record, not by reads. D11 (f).
- **G9** (the reads before each +`0xfc` write): det33's ten accesses written out; required: a read of
  +`0xfc` immediately before each write and of that stream's TCR since the previous one. R73 note.
- **G10** (other accesses in the entry part): C18 (d)'s only, reads of the three domains before the
  first word allowed, nothing interleaved with R6. D10 (b).
- **G11** (both domains off at the wake): PMS must read state `0xf`, then PMP, then PMS_SRAM, R74's
  order and forms; PMS not written by the client. D10 (c).
- **G12** (after a boot wait ran out): R5's register stop alone; later parts nothing. D10 (a), (e).
  **G22** (R5's stop without R4): the same answer, five accesses, no R4 words. D10 (a), D11 (d).
- **G13** (after an entry wait ran out): R5's register stop, then the translator's two writes and R6;
  the sleep goes on; the wake part is the normal one. D10 (b).
- **G14** (after a wake wait ran out): the next entry part sends no word and makes the register stop,
  the translator's writes and R6; the wake after it is the normal one. D10 (b).
- **G15** (PMS_SRAM never at state `0xf`): report, no R6w, R55 or R5w, `pmp` stays stopped, later
  parts nothing. D10 (c), (e).
- **G17, G18** (the switch; one answer): each part reads `cand_c18` at its start; off: no call of any
  kind; a part acts only after the part before it acted; the three mixed cases written out. D10 (e).
- **G19** (bounds of the other waits): the longest gap for every awaited word, from the decoder
  outputs (table); **1 s for every wait, 6 s for `0x000200000023b549`**, up to twice allowed.
  D11 (d).
- **G24, G25** (words outside the waits; LOG during the wake's handshake): echoed whenever `pmp` runs
  in the client's view, **also inside the wake's handshake** (macOS answered such words inside its
  boot start-up); nothing from the entry's stop to the wake's R5w or after a part gave `pmp` up.
  D10 (f).
- **G26** (D9 (b) against the logic at `HEAD`): section 8 did not give D9 (b); **decided D3 (b)**: a
  `sio` or `pmp` found stopped gets no message, no write, no R6 and no restore at the wake; the logic
  changes through its own cycle; the client keeps all of C18's steps; a table of who makes each step
  with `cand_c18` off and on, and the test form for each side. D3 (b), D9 (b), R6 note, C8 note.
- **G27** (values no capture shows): which are seen (a word ahead of an awaited answer; `0x24401` on
  `pmp`'s +`0x8114` under Linux, L30) and which are not; the echo and section 8's rules on read values
  cover the rest. D10 (f).
- **The translator's owner** (the gap list's note outside the tests): the client alone; C18 (a)'s
  nodes do not bind it to Linux's translator driver. D9 (e).

**Observations added:** L32 (the watchdog under ds21's command line and the stock one; ds21's two
`wdt` runs reached the commit point and reset). **Notes added:** R6 (the restore only for a
coprocessor the entry stopped), R71 (det10's writes in full; no SRAM write but the block), R73 (the
translator's reads), C8, C18, L31 (the reference's `apple_wdt` read). **Decisions changed:** D3 (b)
new; D7 (a) (the sleep step, `begin`), (c) (GL10, the abort in `end`, GL13), (d), (e) (GL11, GL12);
D8 (c) (GL13); D9 (b) restated, (e) new; D10 (a)-(c) completed, (e), (f) new; D11 (a), (d) completed,
(c) revised (no RTKit library), (f) new. **Open questions:** 81 partly answered, 82 widened, 83 new.

**Sections changed:** status; 8 (R6 note, R71 note, R73 note, D3, D7, D8 (c), D9, D10, D11); 8.1 (rows
D3 (b), D7, D9, D10, D11); 8.2 (C8 note, C18 note); 9 (81, 82, 83); 12 (L31 note, L32 new).

**Corrections:** D9 (b)'s round-15 statement that section 8 "already gives" the logic's behaviour for
a `pmp` found stopped was wrong (gap G26): section 8's R5, R6, R6w, R55 and R5w had no condition; it is
now D3 (b). D7 (a)'s round-15b sentence that Linux's device suspend is outside the glue and not
covered is withdrawn (GL11). D11 (c)'s permission of the kernel's RTKit library is withdrawn (G4).

## Changes in round 15b (2026-11-19: two points of the glue's C and arm64 review; watchdog 1's first arming and the "left armed" exception)

Inputs: the spec at `715053b` (round 15, gap answers G1-G24 of the `pmp` client); the
orchestrator's brief of round 15b with the two points of the independent C and arm64 review of the
glue (the review itself, the glue, the driver's `src/` and the tests not read) and the reading on
the M1 it carries (L31); evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`
sections "Run ds10", "Run ds11", "Run ds13", "Run ds15" and ds20's command line `var/deepsleep/ds20.cmdline`. No new capture or run. The evidence
file is not changed. Both answers are decisions about Linux, not observations of macOS. Inline
marks "round 15b" are this round's.

**Review point 1 (D7 (c)'s "left armed" exception and Linux's own watchdog driver):** decided in
D7 (c) and the new D7 (e). (c): when a parked core cannot be given back, the glue writes its record
and **panics**, watchdog 1 still armed, with no disarm and no return to the suspend path (was:
return the failure without the disarm). A panic does not resume, so `apple_wdt`'s resume step and
systemd's pings never run, and both recorded panics in the glue's sleep step ended in a reset (ds10,
ds11); if the panic's restart does not come, watchdog 1 bites. (e): a `wdt` run
requires that Linux's watchdog core is not driving watchdog 1 (not active, not marked running in
hardware), checked by the glue without a device access before (a); otherwise the glue refuses the
entry (-EBUSY) with no device access. Reason: the glue's disarm and `apple_wdt`'s resume would
otherwise fight over one watchdog, and the resume would carry the glue's bite N. To read on the M1:
open question 81 (the watchdog's state under the lab's command line with `systemd.watchdog_sec=0`,
the bite and control words, and one run that takes the exception on purpose). D8 (c)'s exception
order follows ((1), then the panic).

**Review point 2 (accesses before the first arming):** decided in D7 (a): the first arming moves.
R61's four writes are now **the glue's first device accesses of its sleep step**, before any
diagnostic read (`snap` 1, 2, 4's pre-entry snapshot, `probe=1`'s reads), record, trace mark,
the parking of cores 1-7 and `enter` (was: immediately before `enter`, with no access between).
Only D7 (e)'s check, which is not a device access, precedes them; the four writes themselves are
the step's only accesses not covered. Reason: the pre-entry snapshot is hundreds of reads (792 in
ds13, more in ds15) made before round 14's place, and a hang in a read is what left ds20's runs
dark (L25); the count restarts at R15 and at (b), so N grows only by the pre-entry work (open
question 82). With (a) before the parking, the round-14c clause "if that happens before (a), the
glue makes R61's four writes then" is removed, and `snap=4`'s return without `enter` and an error
while parking join (c)'s list of ways back that end in the disarm.

**Observations added:** L31 (systemd holds watchdog 1 on the stock kernel, 30 s). **Decisions
changed:** D7 (a), (c), (d) (N's stretches), (e) new; D8 (c) (the exception's order). **Open
questions added:** 81, 82; 74's way out reworded ("before `enter`").

**Sections changed:** status; 8 (D7, D8 (c)); 8.1 (row D7); 9 (74, 81, 82 new); 12 (L31 new).

**Corrections:** none to this spec's own statements.

## Changes in round 15 (2026-11-19: `pmp`'s start and its endpoint-`0x20` words under macOS, the round-11 runs that dropped `0x0020e00000550000`, `pmp` under Linux; R71-R75, L29-L30, candidate C18, decisions D9-D11)

Inputs: the spec at `6bd7a9d` (round 14c); evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`
sections "Hypervisor round 10: what lowers the performance-state words" (`c32ee1a`), "Linux round:
pmp and the endpoint-0x20 message" (`e4a3951`), "macOS's pmp start-up and endpoint-0x20 exchange
(from round-10 captures)" (`4bf6072`), "Earlier Linux runs with pmp started" (`c3443a6`) and
"Hypervisor round 11: macOS without the endpoint-0x20 0x55 message" (`bad8454`), with the private
files they cite; *documentation*: aurora-silicon/linux `integration/aurora` `1f38ff8f4` and Asahi
`hw/soc/asc.md` as those sections cite them. No driver, glue or test was read. The evidence file is
not changed. Inline marks "round 15" are this round's.

**What is established, and what is not.** Under macOS (hypervisor captures) the three C3 words
change only in the first 250 ms sample after a `pmp` event: `pmp`'s start and opening
(`0x444/0x666/0x333` -> `0x444/0x444/0x444`, five boots) and, with `pmp` running, the endpoint-`0x20`
word `0x0020e00000550000` (-> `0x333/0x444/0x222`, with PMP and PMS_SRAM reading `0x1000030f`; four
boots and two wakes). With that word dropped by the instrument the change did not come while `pmp`
ran (one boot, two wakes); in the one entry without it, the words reached macOS's commit values by
two other `pmp` events (`…540000`, `pmp`'s stop), and macOS still powered down and woke. **Not
established:** that the word causes the change (no delayed send), what writes the words, which
other words are needed, and whether the words' values matter to the power-down. Under Linux, `pmp`
is not started by the stock kernel (L29); an earlier module started it and sent the word at its
entry, and the words read macOS's values at that commit, with no run powering down (L30).

**What Linux must now do (as a candidate, C18, behind `cand_c18`; the kernel side's, D9):** a
device tree for `pmp`, its mailbox and its translator; at boot the start as macOS's (domains on,
SRAM header and boot-argument block read and written back unchanged, translator, +`0x8114`,
+`0x44` = `0x10`), RTKit's start-up and endpoint `0x20`'s opening, then `0x0020e00000550000`; at the
entry, before the logic's `enter`, `…550001`/`…540001`, `0x208` `0x63`, `…550000`/`…540000`, then
R4/R5's stop, the translator, R6's save; at the wake (and on a failed entry), after the logic's
wake, R6w, R55, R5w, macOS's short handshake, then `…630001`, `…550001`, `…540001`, `…550000`,
`…540000`. The logic gains no behaviour: it keeps the twelve `0x23b549000` words (E5 d, W1-2h) and
the domain table (R30), and by C8/D3 leaves a `pmp` it finds stopped alone.

**Observations added:** 1.7h (proxy `c3idle1`; det33, det34b, det35-det37; det10, `135map4`,
det18, det23 for the start-up, entry and wake); R71 (the start at boot), R72 (RTKit and endpoint
`0x20` at boot), R73 (the entry's endpoint-`0x20` words and the translator after the stop), R74 (the
wake: domains, twelve words, R6w, R55, R5w, short handshake, words), R75 ([HV-CHANGED] the C3 words
and PMP/PMS_SRAM against the word sent and dropped); L29 (the stock kernel: no `pmp`), L30 (the
earlier runs with `pmp` started). **Notes added:** R6w (its place after the active actions; byte for
byte in det33), R70 (holds in det33-det37), L28 (read with L30), 8.2 C3 (who sets them, round 15),
C8 (with C18), open question 70 (partly answered). **Candidate added:** C18. **Decisions added:**
D9 (the split between the client and the logic), D10 (when, including the failure return), D11
(which words, bounded waits). **Open questions added:** 75-80.

**Sections changed:** status; 1.7h (new); 8 (R6w note, R70 note, R71-R75 new, D9-D11 new); 8.1
(rows R71-R75, D9-D11); 8.2 (title, C3 note, C8 note, C18 new, both tables); 9 (70 note, 75-80
new); 12 (L28 note, L29, L30 new).

**Corrections:** none to this spec's own statements (R6w already had all 49,152 words). The evidence's
corrections are taken as its later sections give them: round 10's "24,576 writes" at the wake was
the part after one sample; round 10's entry listed only the `…0001` pair; the Linux round's "never
run under Linux here" holds for the stock kernel only (L29, L30).

## Changes in round 14c (2026-11-19: the glue test author's gaps GL1-GL8; the probe record, the C3 record's layout, one record per commit point, the failure record before the disarm, watchdog 1 disarmed on every return)

Inputs: the spec at `749b6ed` (round 14b); the gap list `docs/spec/gaps-reported-by-glue-tests-r3.md`
(lab `2e17416`, from the glue's test author of round 3; the tests themselves not read); the
readings already cited by R39, R60, R61, R62, 1.7c (J: watchdog 1's bite and control at the wake
entry as written), 8.2 C3 (every reading of the three words of the form d x `0x111`), L16, L17,
L22-L25. No new capture or run. The evidence file is not changed. Every answer is a decision
about Linux (the glue's record, its order, its watchdog), not an observation of macOS. Inline
marks "round 14c" are this round's.

**Decisions changed:** D6 (g) the failure record's fields are the wait's; D7 (b) the arming last
before the first core's final write, the probe record after it; D7 (c) the disarm on every way
back to Linux, last, with one exception (a core not given back); D8 (a) the record's layout no
longer the glue's; D8 (b) no glue access after the step, one record per step; D8 (c) the failure
record first, the disarm last. **Decisions added:** D8 (e) the probe record after the first
final write; D8 (f) the C3 record's layout. **Requirements' test lines changed:** R60 and R61 in
8.1 (the first core's final write; the probe's exception).

**Sections changed:** status; 8 (D6 (g); D7 (b), (c); D8 (a), (b), (c), (e) new, (f) new); 8.1
(R60, R61, rows D6, D7, D8); 8.2 (C3's requirement, one note).

**The glue test author's gaps, how each was answered**
- **GL1** (G1's probe record against D7 (b), D8 (b) and R61's "before core 0's final write"):
  **G1 stands beside D8 (b)** as its one exception, D8 (e): with `probe=1` the probe record is
  made on core 0 after cores 1-7's final writes and before core 0's, after D7 (b)'s arming
  (which then covers its SPMI commands) and followed by R60's `0x23d0d9378` = 1. R61's line in
  8.1 now reads "before the first core's final write", with that exception; R60's line says
  where its acknowledgement goes with `probe=1`. A `probe=1` run is a reading, not evidence on
  the power-down (commands after a final write, which macOS never sends, R39).
- **GL2** (nine 32-bit values in a 10-byte record): D8 (f), an exact layout. Bytes 0-1 the glue's
  ('D', the letter); bytes 2-6 a 4-bit code per slot (`0xf` = `None`, d = exactly d x `0x111`,
  `0xe` = another value) and the highest slot coded `0xe`; bytes 7-9 that value's bits 0-21 and
  31, with bits 22-30 folded to a flag. Every reading so far keeps its value exactly; Linux's
  and macOS's values and each slot changed alone to `0x222`-`0x666` are told apart. One record,
  at the commit-point step only; not several over time (only the last survives) and none at
  place (ii) (R62 (b)). The failure record does not carry C3's places: on D6's failure only
  place (i) can have been reached (both D6 waits precede R22), and Linux, back, can log all nine
  from `c3_readings`.
- **GL3** (several records at the commit point): D8 (b), one record per step: `snap=2`'s 'C' or
  the commit walk's 'c' if set, else the C3 record with `cand_c3`, else 'W'; then R60's
  acknowledgement and D7 (b). With `probe=1` the probe record (D8 (e)) replaces it later. So
  the tests' reading stands: the C3 record stands with no option, `wdt`, the trace or both.
- **GL4** (a record at every commit point, or only with `cand_c3`): only with `cand_c3` on (D8
  (b)); with it off the glue writes what it wrote before. The tests' reading stands, and round
  1's test (no record with every option off) is untouched by this round.
- **GL5** (trace marks after the step): D8 (b): "no device write between" covers the glue's
  diagnostics; a mark for the final writes goes inside the step before its record, or is not
  made. The tests' reading stands.
- **GL6** (the failure record against the disarm): D8 (c), revised: record, cores, disarm,
  return; the record **before** the disarm, so a controller that does not answer during the
  record's raw SPMI commands is still ended by watchdog 1, and a hang in the cores' return
  leaves a record naming the wait. The order is the C half's, for the glue's reviewer.
- **GL7** (the disarm on other returns): D7 (c), widened: the disarm is the glue's last device
  write on every way back to Linux after the first arming (D6's failure, `run_on` -ETIMEDOUT,
  `snap=1`'s stop, any error, and the return after a wake, since J read the bite and control as
  written at the wake entry). Exception: a parked core not given back leaves watchdog 1 armed (and
  arms it if that happens before the first arming), so the machine resets N s later instead of
  running on without a core.
- **GL8** (the 'T' record's kind and core): D6 (g): every field is the wait's own (its word, a
  32-bit read, core 0, for both D6 waits), not the last access's (a put-back access). The tests'
  reading stands.

## Changes in round 14b (2026-11-19: the round-10 test author's gaps Z11-Z13; C15's words never put back, C5's gate, C3's values as the commit-point step's argument)

Inputs: the spec at `377cbd2`; the gap list `docs/spec/gaps-reported-by-tests-r10.md` (lab
`f316d05`: Z11-Z13 and the reviewer's note on Z12) and, for Z13's full text only, the test
author's `TESTS.md` section 16 (its gap text, not the tests); `var/spec/ps-forms.tsv` (every
read after a write with bit 28, D-I), `var/spec/r13-c5-domains.txt` and `det10`'s detached log
(no access to PMS or SIO_CPU after their bit-28 writes at the wake; the power manager's pages
logged to W+20.7 s); an earlier driver's dry-run trace
`var/m1-state/20261116-122032-run35b/m1power-s2r/run22-20261116-065142.txt` (private); the
readings already cited by R22, R30, R62, 4.1, 4.1c, 4.2a, L14, L15, L18, L25, L26 and the
evidence's "Run ds14". No new capture or run. The evidence file is not changed. Inline marks
"round 14b" are this round's.

**Decisions changed:** D6 (b) no write of `0x23b718004` or `0x23b718000` after a D6 wait, the
put-back included; D6 (c) rule 1 adds the pair; D8 (a) and (b) the nine C3 values reach the
commit-point step as its argument, the accessor serves after `enter` returns. **Candidates
changed:** C5 (its gate: request `0xf` with state `0xf`, or state 4 with bit 28); C15 (a Linux
reading added; the pair never put back on D6's failure path). C12: one line under "Not observed".
**Open question added:** 74 (the SIO family right after C12's turn-on).

**Sections changed:** status; 8 (D6 (b), (c) 1; D8 (a), (b)); 8.1 (rows D6, D8); 8.2 (C3's
round-14 note, C5, C12, C15, summary rows C5 and C15); 9 (69 note, 74 new).

**The test author's gaps, how each was answered**
- **Z11** (what the SIO family reads after C12's turn-on with bit 28): **not recorded** for
  either system. Under macOS PMS, SIO_BUSIF, SIO and SIO_CPU are each turned on with bit 28 just
  before the twelve are lowered at every wake, and no read of any of them follows that write;
  other words with bit 28 read state 4 (NUB_SPMI0/1, DCS) or 0 at the first read after it;
  under Linux C12 has not been read. Answered by a decision in 8.2 C5's round-14b note: the gate
  is **on the request and the state together**, *on* = request `0xf` with state `0xf`, or state 4
  with bit 28 set; anything else reads only. So C5 acts after C12's turn-on whether the family
  stays at `0xf` or drops to 4 (both of the suite's machines act), and not with Linux's
  `0x0f000200`. The read that would settle the state itself: open question 74 (one entry with
  `cand_c12` and `cand_c5` on, its record carrying C5's own four reads).
- **Z12** (D6 (b) against C15's put-back of `0x23b718004`): D6 (b) holds with no exception and
  D6 (c) rule 1 adds **the pair `0x23b718000`/`004`: never put back**, whatever C15 read; after a
  D6 wait neither is written, and the pair stays at C15's `0xf`. Reasons in D6 (c) rule 1: a
  write of 0 to `0x23b718004` is R22's trigger, the write the always-on side's first step follows
  (R62), and under an earlier Linux driver that step was taken with a core still running, or the
  machine reset about 5 s after the entry (L18); `0xf` is the pair's value with macOS running
  and the value its wake writes (R30);
  macOS writes the two only together. The suite's allowance of one put-back write is withdrawn.
  The suite's machine value 0 for the pair under Linux is not a reading: the only Linux reading
  is `0xf`/`0xf`, an earlier driver's dry run at its R22 place (8.2 C15), in which C15 makes
  reads only and the case does not arise.
- **Z13** (D8 (a)'s accessor inside the commit-point step): D8 (a), (b). Inside the step the
  glue receives the nine as the step's argument, the same values in the same slots as
  `c3_readings` (the suite's `Hw::commit_point(&mut self, c3: &[Option<u32>; 9])` stands, name
  and signature the test author's); `c3_readings` is for after `enter` returns. Reason: `enter`
  holds the driver mutably for the whole call, so the step cannot call back into it.

## Changes in round 14 (2026-11-19: the round-10 test author's gaps Z1-Z10; D6 and D7 revised, D8 new, C3's places and C5's four reads exact)

Inputs: the spec at `c8b735c`; the gap list `docs/spec/gaps-reported-by-tests-r10.md` (lab
`d47c906`; the test author's `TESTS.md` section 16 at tests commit `eb9f9a0`, not read here: the
gap file is the only channel); the readings already cited by D6, D7, C3 and C5 (L17, L25, L26,
4.1d, R11, R15, R16, R22a, R36, R56, R57, R66, E5-2); the always-on program's decode
`var/recfg/seq10-11.txt` (sequence 10's writes of FPWM0 and FPWM2 `0x244` and their polls for
state 4; SIO_BUSIF before SIO) and `var/recfg/t8103-recfg-decoded.txt` (PMS's word
`0x23b700140`); the evidence file's runs ds10, ds17 and ds20 (the glue's commit point and its
record), read only. No new capture or run. Inline marks "round 14" are this round's.

**Decisions changed:** D6 (a) the D6 waits are exactly R16's and R22a's; (b) both precede R22, so
R23, R36 and R38 never precede a D6 return; (c) rewritten: no read added, each word put back once
by five rules (not put back: coprocessor blocks, SPMI and the power chip, the CPU start/stop block,
the watchdog block; domains by D1 with the new form (4r) for request 4; other words read first to
the value read; words never read first left as written; the interrupt controller by R36w's rule
should it ever be reached), in reverse order of first writes with 1.9's order for domains; (e) the
logic writes nothing to the CPU start/stop block, giving the cores back is the glue's; (f) the
disarm is the glue's after `enter` returns. D7 (a) the first arming moves to just before `enter`;
(b) the second is made in the glue's commit-point step; (c) the disarm after `enter` returns.
**Decision added:** D8 (the logic's interface to the glue: `c3_readings`, the commit-point step,
the failure return). **Candidates changed:** C3 (the places (ii) and (iii) exact; the values
through D8 (a)); C5 (its four reads exact, in order, its own; its wait testable by holding a word).
**Open question added:** 73 (a stop bit left set under Linux).

**Sections changed or added:** status; 8 (D6, D7, D8); 8.1 (rows D6, D7, D8); 8.2 (C3, C5,
summary rows C3 and C5); 9 (73). The evidence file is not changed.

**The test author's gaps, how each was answered**
- **Z1** (C3's nine values: no interface): D8 (a). `c3_readings(&self) -> [Option<u32>; 9]`,
  slots (i), (ii), (iii) in C3's word order; all `None` at the start of each `enter`; `Some` once
  read, kept until the next `enter`, whatever `enter` returns; with `cand_c3` off or a place not
  reached, `None`; readable in the glue's commit-point step. `None` rather than 0 because the
  always-on program writes these words 0 (decode). The record's format is the glue's.
- **Z2** (D6 (c) and words written without a read): D6 (c) rules 3 and 4. D6 adds no read; a word
  the same core read after entry start and before its first write goes back to the value read; a
  word never read first is not put back (the suite's choice stands).
- **Z3** (the watchdog block and the interrupt controller's "set" words): D6 (c) rules 1 and 5.
  The watchdog block `0x23d2b0000`-`0x23d2b8fff` is never put back (its words are counts and the
  glue's watchdog 1; the glue's disarm is the only failure-path write there). R36's writes come
  after R24 and are never made before a D6 return; should that change, R36w's rule, not the value
  read.
- **Z4** (D6 (e), cores "given back"): D6 (e) and D8 (c). The logic asks no core for anything
  further and writes nothing to `0x23b754000`-`0x23b75401c` (no stop bit cleared, no start word:
  macOS never clears a stop bit, W2's start words follow a power-down); the glue returns the
  parked cores to Linux. The suite's allowance of start words after the wait is withdrawn. What a
  stop bit left set does under Linux: open question 73.
- **Z5** (D6 (c), the order for a word changed at several places): D6 (c), "Order". Each word put
  back once, to its value before the entry's first write of it, in the reverse order of first
  writes; for domain words 1.9's parent/child order governs where the two differ.
- **Z6** (D6, which waits): D6 (a). Only R16's poll and R22a's status waits; a coprocessor's
  bounded wait stays D3's "go on" (the suite's choice stands), as do candidates' waits (D5 (e))
  and any wait section 8 does not state as one.
- **Z7** (D6 (c) for a domain found at request 4): D6 (c) rule 2, form (4r): W v with bits 0-9
  replaced by `0x244`, then reads until bits 4-7 read 4, bounded; the always-on program's form
  in its wake sequence 10 (decode); no application processor's write of request 4 over request 0
  is in any capture (R57), which D6 states.
- **Z8** (C5's four reads): 8.2 C5, round-14 note. C5's own four 32-bit reads by core 0, in the
  order PMS, SIO_BUSIF, SIO, SIO_CPU, immediately before its first access to the twelve; no other
  read stands for them; the decision rests on them alone. C5's own wait can be tested by holding
  a word's state: no later entry step accesses the twelve.
- **Z9** (C3's places (ii) and (iii)): 8.2 C3, round-14 note. (ii) as the suite has it (core 0's
  first three accesses after `W 0x23b718004` = 0); (iii) after R38's third write of `0x23d2c4000`
  and before the glue's commit-point step, hence before the first core's final write.
- **Z10** (D7's places inside `enter`): D7 (a)-(c) and D8 (b). The first arming moves to just
  before the glue calls `enter` (it differs from entry start by D3's reads only and also covers
  them); the second is made in the glue's commit-point step, which the logic calls after R38's
  third write and C3 (iii), before the final writes (where the glue already arms it, L17); the
  disarm after `enter` returns D6's failure.

## Changes in round 13 (2026-11-19: the candidates carried into macOS, the ds20 switch runs, who writes C3's words, C3 and C5 revised, decisions D6 and D7)

Inputs: the spec at `99aee86` (repository at `10db7c8`); the evidence file's "Hypervisor round 9:
candidates injected into macOS (det26-det32r)", "Linux awake (2026-11-18 21:15)", "Runs ds20,
candidate switches one at a time" and "Run ds20, all candidate switches but C3 and C5 together"
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commits `8775601`, `d6f08a1`,
`a166e89`, `10db7c8`); `var/commit-walk/ds20-cand.tsv` and `ds19-commit-118.tsv`; every touch map
and detached log in `tools/hv-trace-kit/runs/20261116-mac135/` (48 boots, 22 wakes); the Linux
and proxy readings `var/commit-state/m1n1-proxy-wide.json`, `linux-live-wide.json`,
`macos135-135snap1.json`, `linux-run40-lx12.json`, `tools/hv-trace-kit/runs/20261116-linux/s2r-trace-lx1{2,3,4,7}.jsonl`,
`touch-dsh2.jsonl`, `run-lx20.out`; the lab's decode of the always-on program
(`var/recfg/t8103-recfg-decoded.txt`, `seq10-11.txt`, `var/map-20261117/recfg/things*.json`);
the reference `docs/reference/asahi-aurora-sleep-deep-dive.md` (2.1, 2.2, 3.4, 3.8, the AON block
map), marked as reference where used; the orchestrator's brief for D6 and D7. Inline marks
"round 13" are this round's.

**Checked against the data**
- Every value and access of the C3 words: `r13_c3_boot.py` (48 touch maps), `r13_c3_words.py`
  (every detached log); new: the wake value `0x333`/`0x555`/`0x333` in all 22 wakes, no access by
  any core to the two pages `0x23b05c000`, `0x23b060000` in any capture, and on `0x23b058000`'s
  page only reads of `+0x68`, `+0x80`, `+0x98`; the proxy's values (`0x444`/`0x666`/`0x333`)
  equal Linux's.
- The always-on program's operations on those words and on C5's domains: `r13_recfg.py` over the
  decode.
- C5's wake order and what precedes it: `r13_c5_domains.py` over the 18 detached captures.
- The ds20 runs, the macOS injections and Linux awake 21:15: from the evidence text and
  `ds20-cand.tsv` (no other data file holds them; the failed macOS runs' logs are lost).

**Requirements added:** R70 (no write to the C3 words; reads of the two pages' first words only).
**Decisions added:** D6 (a wait that runs out ends the entry in a clean, bounded put-back and
return to Linux), D7 (with `wdt`, the glue arms watchdog 1 at entry start too and disarms it on
D6's return); their rows and R70's in 8.1.

**Candidate requirements changed:** C3 — the round-12 write of macOS's values and its wait are
**withdrawn** (it hung Linux's entry; no macOS write of these words exists); C3 is now reads only,
at entry start, after R22's trigger and at the commit point. C5 — acts only with PMS, SIO_BUSIF,
SIO and SIO_CPU on (otherwise reads only), placed after C12's turn-ons, in macOS's wake order,
waiting for low byte 0. Summary table rows C3 and C5 replaced; a table of the runs' outcomes per
candidate added. C1, C2, C4, C6-C17 unchanged.

**Sections changed or added:** status; 1.7g (new); 8 (R70, D6, D7); 8.1 (three rows); 8.2 (C3, C5,
summary rows, outcomes table); 9 (68 note; 70-72 new); 12 (L24 note; L25-L28 new); appendix
(four scripts).

**The orchestrator's questions, how each was dealt with**
1. The ds20 runs as [LINUX] statements: L25 (one switch at a time), L26 (all but C3 and C5); with
   Linux awake 21:15 (L27) and the earlier driver's commit readings of the C3 words (L28).
2. C3: who writes the words and when — **observed:** macOS's application processors never write
   them (R70); they change with no logged access during macOS's boot (proxy/Linux
   `0x444`/`0x666`/`0x333` -> macOS awake `0x333`/`0x444`/`0x222` by 192 s) and across each sleep
   (`0x333`/`0x555`/`0x333` at every wake before macOS runs); they are unchanged by macOS's
   entry, its stops of `pmp` and the GPU, and the cores' power-down; the always-on program's
   sleep sequence 0 writes them (3, 4, later 2, 2) with waits on a busy bit, and its wake
   sequences 4 and 7 write them too (decode); under an earlier Linux driver they read macOS's
   values at Linux's commit. **Not observed:** what lowers them during macOS's boot (`pmp`,
   another coprocessor, the always-on side, or the hardware on a vote), when, and what sets the
   wake values. C3 revised into reads only (no write: R70); the hypervisor reading that would
   settle who sets them is open question 70. C5: macOS lowers the twelve only at the wake, in a
   fixed order, after PMS and SIO_CPU are turned on and with SIO_BUSIF and SIO on; C5 revised to
   that precondition and order.
3. D6 and D7 recorded as decisions about Linux (section 8, after D5), with what the readings
   say next to each.
4. "Changes in this round" replaced by this list; round 12's kept below as "Changes in round 12".

## Changes in round 12 (2026-11-18: run ds19 and its probe runs, the commit walk's first words, every observed difference written as a candidate requirement C1-C17, decision D5)

Inputs: the spec at `7216e7b` (repository at `cdead1f`); the evidence file's "Run ds19", "Runs
ds19p-74, ds19p-75" and "Runs ds19p, k 20-28 and 67-70"
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commits `0726bd0`, `153780c`,
`aa1a977`); the commit walk's file `var/commit-walk/ds19-commit-118.tsv` as it stood at 19:00
(running), with `var/commit-walk/differing-118.k`; the earlier Linux readings of section 12
(`var/commit-state/linux-ds13-bare-preentry-vs-macos-commit.tsv`, `linux-ds13-bare-ps-words.json`);
the capture databases `var/spec/db/cap{3,4,d,e,f,g,h,i}.db` and `commit-state-ghi.tsv`; the
power manager's table `var/map-20261117/adt/pmgr-devices.json`; the rules
`docs/agents/cleanroom-cycle.md` ("Faster cycles") and `AGENTS.md`; the reference
`docs/reference/asahi-aurora-sleep-deep-dive.md` (sections 2.1-2.3, 3.3, 3.4, 3.8, 3.9), marked
as reference where used. Inline marks "round 12" are this round's.

**Checked against the data**
- ds19 and the probe runs: taken from the evidence text (no data file holds the probe values
  beyond the evidence's tables).
- The commit walk: 12 of 118 at 19:00; read from the file, decoded by the brief's record layout.
- Every "macOS never accesses" and "macOS writes" statement of 8.2: `r12_candidates.py` over all
  eight capture databases, including A's and B's boot page-touch map. New from it: at boot
  `0x23b71c000` reads 0 and `0x23b748000` reads 0 (A, B), macOS's boot writes `0x23b0400d4` = 0
  (A, B), DCSn+`0x7b0` is never accessed even at boot (A, B log that range in full),
  `0x23b05c000`, `0x23b060000`, `0x23b720000`'s page and `0x23d240000`'s page are never accessed,
  APCIE_GP goes down by itself during G's entry, SEP is written `0x1000200f` at every wake.

**Requirements added:** none to section 8. **Candidate requirements added** (section 8.2, new):
C1-C17, each with the difference observed, why it is a candidate, its requirement in test form
(place, order, reads, writes, the state at the commit, the wake) and what is not observed; a
ranked summary table. **Decision added:** D5 (each candidate behind its own switch `cand_cN`, off
by default; reads before writes, bounded waits, the wake rule), with its test-table row in 8.1.

**Requirements changed or withdrawn:** none. D1-D4 unchanged.

**Sections changed or added:** status; 4.4 (round-12 note: rows 4, 6, 12); 4.4a (round-12
note: C3, C4, C6, C10, C12, C13); 8 (D5); 8.1 (D5 row); 8.2 (new); 9 (68, 69 new); 12 (L11, L20's
boot note; L21-L24 new); appendix (`r12_candidates.py`).

**The orchestrator's questions, how each was dealt with**
1. Every observed difference between macOS at and before its commit and Linux's readings that a
   driver could act on: C1-C17 in 8.2, ranked by judgment; the differences left out are listed
   there with the reason.
2. Each written so that a test author can hold a driver to it behind its own switch: the
   "Requirement" bullet of each, with the common rules and D5 (a)-(f).
3. D5 recorded as a decision (section 8, after D4).
4. The new Linux readings as [LINUX] statements: L21-L24, L11, 4.4's round-12 note.
5. The commit walk: 12 of 118 had arrived (eight varying memory-controller words and
   DCS0-3+`0x7b0` = 3 at Linux's commit); no candidate rests on the walk alone (C4 is the one it
   confirms reaches the commit).
6. The macOS readings under the hypervisor that would sharpen the candidates: open question 68
   (each candidate's Linux state carried into macOS, [HV-CHANGED]; macOS's boot logged in full
   for the candidates' pages); the Linux readings: open questions 56 and 69.

## Changes in round 11 (2026-11-18: the round-11 runs det23 and det24, the power-gate header word cleared at the commit, Linux awake again, the requirements since round 6 as test statements)

Inputs: the spec at `cda3fe5` (repository at `fea08ef`); the evidence file's "Linux awake, stock
kernel (2026-11-18 03:54)" (commit `cbeff4a`) and "Hypervisor round 8" (commit `fea08ef`)
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`); the runs
`tools/hv-trace-kit/runs/20261116-mac135/*-det23.*`, `*-det24.*`, `*-det25.*` and, as the
control, `*-det18.*`; the observation stage's `var/commit-state/r8-det2[34].txt`,
`r8-det2[34]-core-state.txt`, `r8-det2[34]-vs-det18.txt`, and for comparison `r7-det*.txt`,
`r7-det*-core-state.txt`, `r6-det12.txt`; the power-chip dumps
`var/m1-state/pmu-20261118-041248-after-det23.txt`, `-042720-after-det24.txt`,
`-043229-after-det25-bringup.txt`; `var/spec/r10-checks.txt` (the header accesses of the earlier
captures); the reference `docs/reference/asahi-aurora-sleep-deep-dive.md` (section 2.2, the boot
core power-gate enable), marked as reference where used. Every reading the observation stage
reported was re-read from the detached logs by this round's `r11_checks.py` (`r11-checks.txt`).
Inline marks "round 11" are this round's.

**Checked against the data, and where the data say more than the evidence summary**
- `0x23b71c000` read `0x80000000` just before and 0 just after the instrument's write (core 2 in
  `det23`, core 4 in `det24`), 0 at the commit, `0x23b71c040` `0x80000000` throughout; power-down
  and alarm wake in both (89.998 s, 89.649 s); wake status, wake-entry words and power-chip bytes
  as L: all confirmed. The before/after values are in the logs' sequence-100 probe records; the
  observation stage's `r8-det2[34].txt` prints those records without values.
- macOS's header accesses: the entry's `080`, `088` and the wake's read of 0 and write of
  `0x80000000` (wake + 7.68 / 7.77 ms; L 7.51 ms): confirmed; none between the clear and the wake.
- Watchdog 2 in the three writes and its start (7.5 / 3.2 microseconds after `W 0x23b718004` =
  0): computed this round (the observation stage's `r7_wd2start.py` stops at the sequence-100
  set); five captures now.
- Each core's state: as the evidence says, with one thing it does not mention: in `det23` core
  3's pending virtual FIQ comes with the instrument's "IPI pending" = 1 and an unfired timer (due
  89.389 s), i.e. from an IPI, not a timer (E7). In `det24` the unfired timers of cores 3 and 2
  are due 0.135 s and 0.503 s.
- The Linux reading of 03:54 has no data file; its values are taken from the evidence text.

**Requirements added**
- R69 [HV-CHANGED]: `0x23b71c000` cleared by the instrument before the cores' final writes,
  read 0 at the commit: power-down and alarm wake, 2 of 2.
- Section 8.1: R5a and R56-R69 restated as statements a test can check against a simulated
  machine, each with how firmly it rests and, where not testable as written, why; D1-D4 given
  their test form (their wording unchanged).

**Requirements changed**
- R67: **its commit clause "for a driver, `0x23b71c000` and `0x23b71c040` hold `0x80000000` at
  its commit" withdrawn**; R67 now (a) the entry writes only `080`, `088` of the header (all
  fifteen), (b) macOS's own commit value `0x80000000` (five), not constrained for a driver, (c)
  the wake's read and set of `0x23b71c000`, `0x23b71c040` (all fifteen); the second Linux
  reading.
- R59: the same requirement on fifteen power-downs and six `ISR_EL1` readings; an IPI-borne
  pending virtual FIQ at a core's final write seen under macOS (`det23`).
- R60, R62, R65, R66: `det23`, `det24` added (six / five / six / five captures); R65 notes the
  instrument's IPI word on `det23` core 3. R22, R24, R30: round-11 counts.

**Requirements withdrawn:** none as an entry; within R67 its commit clause, above. D1-D4
unchanged.

**Sections changed or added:** status; 0 (the round-11 runs, "all fifteen"); 1.3 A6 (the
round-11 option), A9; 1.7f (new); E7 (the per-core state in `det23`, `det24`; item 1 of "what a
core leaves"); 4.1c (watchdog 2 in five captures); 4.1d (the header cleared; Linux awake again);
4.4 (row 15; what round 11 adds); 4.4a (C3 round-11 row; what changes); 5; 6 W1-2a; 8 (marks;
R22, R24, R30, R59, R60, R62, R65, R66, R67; R69 new; 8.1 new); 9 (64, 66 updated; 67 partly
closed); 12 (L11; L20 new); appendix (`r11_checks.py`).

**What the spec now says a driver's cores must leave at their final write, and the rest of the
commit** (8.1)
1. Nothing pending at the core (R59): no timer enabled, unmasked and fired; no IPI; no counter
   or controller interrupt; no virtual interrupt. Fifteen power-downs; failures 4 of 4 with a
   virtual FIQ pending [HV-CHANGED]. Timers may stay enabled.
2. macOS's own register values (R65, six captures) and every core down, core 0 last (R64).
3. The CPU block: cores 1-7 write their stop bits, nothing writes +`0x4` (R66).
4. Watchdog 2 and `0x23d2b8028`: not written; their armed state is the hardware's (R62).
5. SPMI: every command bracketed and acknowledged, the status 0 at the commit (R60).
6. The power-gate header: no requirement on `0x23b71c000` at the commit (R67, R69).

**The orchestrator's questions, how each was dealt with**
1. Round 8 and the Linux reading recorded (1.7f, E7, 4.1c, 4.1d, L20), checked against the data
   (above); R67 and open question 67 updated (R67's commit clause withdrawn; 67 partly closed,
   (a) and (b) still open).
2. Every requirement since round 6 restated for testing with its firmness (8.1); where not
   testable as written, the reason is given there (R5a's silent coprocessor, R56's wait, R57's
   target state, R58 against D1/D2, R59's later-falling timer and physical interrupts, R62's
   cause, R63's values, R64's timing, R65's EL1 timer values, R66's +`0x4`, R67's constant).
3. D1-D4 kept; given their test form only.
4. This list; the earlier rounds' lists kept below.

## Changes in round 10 (2026-11-18: capture L, the round-10 runs det19b to det22c, the power-gate page and the CPU block, pending interrupts at the cores' last step)

Inputs: the spec at `fca5a6f` (repository at `bdb9f12`); the evidence file's "Hypervisor round 7"
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `bdb9f12`); the runs
`tools/hv-trace-kit/runs/20261116-mac135/*-det18*` to `*-det22c*`; the observation stage's
`var/commit-state/r7_probe.py`, `r7_wd2start.py` and their outputs, `r7-det*-core-state.txt`,
`r7-pwrgate-records.md`; `var/recfg/commit-snap-list-r7.json`; the power-chip dumps
`var/m1-state/pmu-20261118-*-after-det1[89]*`, `-det2*`; the capture databases `var/spec/db/` and
the detached logs of J and K (for the wake writes of the power-gate header); the lab's Linux
register scans `var/hwdb/m1-hw.db` (snapshots 12, 16) and `var/regmap/scan-pmgr-1c000/`; the
instrument's code (`~/m1n1-next` `ff8caba0`: `src/hv/hv_cpu_power.c`, `src/hv/hv_detached.c`;
`proxyclient/m1n1/hv/__init__.py`), cited as the record of what the instrument did; the reference
`docs/reference/asahi-aurora-sleep-deep-dive.md` and the Asahi documentation page "SMP" (local
clone `docs/hw/cpu/smp.md`, commit `e8bcfea`), marked as reference or documentation where used.
Every reading the observation stage reported was re-read from its output files and, for the
wake writes, the Linux scans and the per-core due times, from the logs and databases by this
round's `r10_checks.py` (`r10-checks.txt`). Inline marks "round 10" are this round's.

**Checked against the data, and where the data say otherwise than the summary handed over**
- Watchdog 2 armed before the first write of `0x23d2c4000` reaches the hardware (bite 5 s,
  control 4, count 43-56 microseconds), its start 1.3-7.1 microseconds after the record of
  `W 0x23b718004` = 0: confirmed in all three captures. `0x23d2c4000` reads 1 **only** before the
  first write; it reads 0 after it and 0 both before and after the second and third (not "1 before
  each of the three writes").
- The keep-state split: confirmed (`keep_timers` power-down and wake 2 of 2; `keep_vfiq` reset
  2 of 2); the per-core states of L, `det19b`, `det21` re-read (fired on cores 1, 3, 2, 0 / 1, 3,
  0 / 1, 2, 0).
- CPU block `0xfe` / `0xfe` at the commit: confirmed. Power-gate page: **23** of 450 words change
  between awake and the commit or between runs (22, 21, 20 per run), not 25; with the CPU
  block's two the round's changed words number 25.
- Added from earlier captures and Linux scans, not in the summary: `0x23b71c000` reads 0 and is
  written `0x80000000` by macOS at every wake (thirteen captures), and reads 0 with Linux awake.

**Requirements added**
- R66 [L]: the CPU start/stop block at the commit (+`0x0` = +`0x4` = `0xfe`, the rest 0).
- R67 [L] and [BOTH] for the wake: the power-gate header words `0x80000000` at the commit;
  `0x23b71c000` read 0 and set at every wake; for a driver, `0x23b71c000` and `0x23b71c040` hold
  `0x80000000` at its commit (whether bit 31 is needed is not observed).
- R68 [HV-CHANGED]: the two items separated: timers left, nothing pending: power-down; a virtual
  FIQ pending: reset.

**Requirements changed**
- R59: the requirement on a driver's cores is now "nothing pending at the core at its final
  write" (`ISR_EL1` 0; no virtual IRQ/FIQ pending), resting on all thirteen captured
  power-downs and on four of four failures with a virtual FIQ pending; **"timers off" withdrawn
  as a requirement** (two power-downs with every guest virtual timer enabled and unmasked).
- R62: watchdog 2 armed and `0x23d2b8028` bit 24 set before the first write of `0x23d2c4000`, the
  count starting just after `0x23b718004` = 0 (replaces "within about 0.3 ms of the first write").
- R22, R24, R30, R65: round-10 readings added (watchdog 2 after `0x23b718004` = 0; `0x23d2c4000`
  0 after the first write; the header writes at the wake; R65's values in four captures).

**Requirements withdrawn:** none as an entry; within R59 "timers off" as stated above. D1-D4
unchanged.

**Sections changed or added:** status; 0 (capture L, the round-10 runs, [HV-CHANGED] for a run
whose outcome was unchanged); 1.3 A4 (what the instrument does with the CPU block), A6 (the
round-10 options), A9; 1.7e (new); E5-8j (where SIO and SIO_BUSIF fall); E7 (the per-core state
in three more captures, the split, what a core leaves at its final write and how firmly); 4.1c
(inside the three writes; watchdog 2's start against the log); 4.1d (new: the CPU block and the
power-gate page, with Linux awake); 4.4 (rows 4, 5, 12, 13 updated, 15 and 16 new; what they add);
4.4a (C3, C4, C17 round-10 rows; what changes); 5; 6 W1-2a, W2; 8 (marks: [L]; above); 9 (55, 56,
57, 62, 63 updated; 59, 60, 61 closed; 64-67 new); 12 (L11, L19 new); appendix.

**What the spec now says a driver's cores must leave at their final write** (E7, R59, R65, R68)
1. Nothing pending at the core: `ISR_EL1` 0 and no virtual interrupt pending. Observed in every
   captured power-down (the instrument's act for the virtual part) and its absence followed by
   no power-down four of four, both under the instrument **[HV-CHANGED]**; not observed for a
   physical interrupt on either system.
2. Timers may be left enabled (two power-downs, [HV-CHANGED]); not required off.
3. macOS's own values, four captures: the interrupt controller's lines and both IPI kinds masked,
   `IPI_SR_EL1` 0, `PMCR0_EL1` `0x7003400`, no counter interrupt pending, `PSTATE` D, A, I, F
   masked, `ACC_OVRD_EL1` / `CYC_OVRD_EL1` as R43, core 0 last, no core kept running.
4. Open: the same reading under Linux at its final instruction (65); a physical pending interrupt
   under macOS (66).

**The orchestrator's questions, how each was dealt with**
1. Round 7's readings, checked, each marked: 1.7e's table (macOS's / [HV-CHANGED] per run and
   per part of a run), 4.1c (the probe, macOS's under the probe's reads), 4.1d (macOS's commit and
   awake values; Linux awake marked [LINUX]), E7 (macOS's per-core values; the split
   [HV-CHANGED]). Two corrections to the summary handed over (above).
2. Pending interrupts at the cores' last step: E7's round-10 parts keep apart what macOS leaves
   (four captures), what the instrument changes (A6: the virtual FIQ it holds for a fired timer,
   the timer's FIQ to the core turned off, and in every power-down the clearing), what followed
   with and without that clearing, and the inference (marked, with its reference). The
   requirement goes as far as R59's round-10 wording; the rest is open questions 65 and 66.
3. 4.4a: C3, C4, C17 answered for Q59-Q61 as far as read; open questions 64-67.
4. D1-D4 kept unchanged.

## Changes in round 9 (2026-11-18: capture K, the round-9 runs det13 to det17, the reference's conditions)

Inputs: the spec at `9450b3d` (repository at `a3b8280`); the evidence file's "Hypervisor round 6"
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `0e6bd8d`); capture K and the
round-9 runs (`tools/hv-trace-kit/runs/20261116-mac135/*-det1[2-7].*`), K re-read by
`r9_det12.py`; the observation stage's `r6-det12.txt` and `macos135-det12-vs-det11.txt`; the
power-chip dumps `var/m1-state/pmu-20261118-*` and, for `0x9f03`, `pmu-20261117-*`; the
instrument's code (`~/m1n1-next`, `m1power/hv-detached`, `2ced1fab`, `2cb8a180`,
`src/hv/hv_cpu_power.c`, `src/wdt.c`), cited as the record of what the instrument did; the
reference `docs/reference/asahi-aurora-sleep-deep-dive.md` (commit `a3b8280`) and the Asahi
documentation page "AIC" (local clone of the Asahi docs, `docs/hw/soc/aic.md`), both marked as
reference or documentation where used. Inline marks "round 9" are this round's.

**Requirements added**
- R62 [K]: watchdog 2 armed (5 s, control 4) before the cores go down, within about 0.3 ms of
  R24's first write, with no write of macOS's to it; the always-on words at the commit
  (`0x23d2b8028` bit 24, `0x23d2b8040` `0x20`, `0x23d2c4000` 0) and at the wake.
- R63 [K]: the AP wake-source masks and three always-on clock words hold their awake values at
  the commit.
- R64 [HV-CHANGED]: with a core kept running after the commit, nothing sampled changes for 4.9 s
  and the machine resets 6-7 s after the commit; not a step macOS takes.
- R65 [K]: each core's own registers at its final write (physical timer off, `IPI_SR_EL1` 0,
  `PMCR0_EL1` `0x7003400`, interrupts masked in `PSTATE`).

**Requirements changed**
- R59: macOS's own timer state is now observed (its virtual timer enabled and unmasked on all
  eight cores, fired on three); the statement stays the state of every observed power-down; kept
  in place under the instrument (det13, det17), no power-down twice [HV-CHANGED].
- R15, R24, R36, R43, R60, R61: K's readings added (watchdog page writes as before; `0x23d2c4000`
  reads 0 at the commit; the interrupt controller as read at each core's final write; the
  `ACC_OVRD_EL1` / `CYC_OVRD_EL1` values; `0x23d0d9378` 0 at the commit; watchdog 1 as in J).

**Requirements withdrawn:** none. D1-D4 unchanged.

**Sections changed or added:** status; 0 (capture K, the round-9 runs, the mark [HV-CHANGED], the
reference); 1.3 A6 (the round-9 build's options) and A9; 1.7d (new: K and the round-9 runs, with
whose observation each is); E7 (each core's own state at its final write; leaving it in place);
4.1c (new: the always-on block, the watchdogs and the wake masks at the commit); 4.4 (rows 2-5,
7, 9, 12 updated; rows 13 and 14 new; what they add); 4.4a (new: the reference's seventeen
conditions against the M1 readings); 5 (K; the round-9 runs); 8 (marks; above); 9 (14, 45,
53-58 updated; 59-63 new); 12 (L11, L16); appendix (`r9_det12.py`, the observation stage's
scripts).

**The orchestrator's questions, how each was dealt with**
1. Round 6's readings, each marked macOS's own or shaped by the instrument: each core's state at
   its final write (E7: macOS's own registers and the instrument's held state in separate
   columns; R65, R59), watchdog 2 armed before the commit (4.1c, R62: armed by no logged access,
   so not "armed by macOS" as a write), the always-on words at the commit (4.1c, R62, R63), and
   each run's outcome with what the instrument changed (1.7d's table). Which runs changed the
   outcome: `det13`, `det17` (timer state left in place) and `det14`, `det16` (a core kept
   running): each turned K's power-down and wake into a reset 5-7 s after the commit; they are
   marked [HV-CHANGED] wherever used. K itself changed only the cores' way down (0.3 ms instead
   of 31 microseconds), outcome unchanged.
2. Section 4.4 updated (rows 13, 14 new) and 4.4a added: for each of seventeen conditions the
   reference names, macOS at its commit, Linux at its commit, and the reading that settles the
   open side; observation and reference in separate columns.
3. Requirements: only what the observations support (R62-R65, R59 changed); the rest to open
   questions 59-63.
4. D1-D4 kept.

## Changes in round 8 (2026-11-17 near midnight: capture J, runs ds16 to ds17-3, macOS's commit against Linux's)

Inputs: the spec at `f99247c` (repository at `07ed602`); the evidence file's sections after "Run
ds15" (`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `07ed602`: ds16,
Observation round 4, ds16b, ds16c, ds17, Hypervisor round 5, ds17-1 to -3); capture J
(`tools/hv-trace-kit/runs/20261116-mac135/*-det11.*`), re-read by `r8_det11.py`; the power-chip
dumps `var/m1-state/pmu-*.txt`; the instrument's arm-time lines in `run-*.out`; the instrument's
own code (`~/m1n1-next`, `m1power/hv-detached`, `bb8873c0`, `src/hv/hv_cpu_power.c`;
`tools/hv-trace-kit/harness/real_s2r.py`), cited as the record of what the instrument did; the
earlier evidence `2026-11-16-hv-macos135-s2r`, `2026-11-16-dram-controller-state`,
`2026-11-16-hv-macos135-wake`, `2026-11-16-run26-watch`, `2026-11-16-run36-38-restart`,
`2026-11-16-run40-mac-order` (readings, and the lab's decode of the always-on program, marked as
such where used). No new reference material. Inline marks "round 8" are this round's.

**Requirements added**
- R59 [ARTEFACT, in every power-down]: each core's timers off and no virtual interrupt pending at
  its final wait (the instrument's doing); `PMCR0_EL1` `0x7003400` and `IPI_SR_EL1` acknowledged
  before; macOS's own timer values not observed.
- R60 [D] + [ARTEFACT, in every power-down]: no SPMI reply status left unacknowledged when the
  cores go down (`0x23d0d9378` = 1 after every command, macOS's and the instrument's); without
  it, two earlier runs woke within about a second.
- R61 [J]: watchdog 1 armed at the commit does not prevent the power-down or the alarm wake; its
  bite and control survive, its count does not.

**Requirements changed**
- R24: `0x23d2c4000` is never read by macOS and reads 1 awake before every entry (eight runs).
- R27: the instrument's whole commit path, from its code (A6).
- R35: J a fifth alarm wake. R38: J ordered like F and G. R43: J repeats the values.
- R47, R51: J's commit snapshot (842 of 862 equal to I; 767 of G's 792 equal in G-J).

**Requirements withdrawn:** none. D1-D4 unchanged.

**Sections changed or added:** status; 0 (capture J); 1.3 A6 (the instrument's commit path in
full) and A9; 1.7c (capture J, new); E6 (J); E7 (the instrument's per-core acts, PMCR0 and
IPI_SR last writes); 4.4 (new: macOS's commit against Linux's, twelve items); 5 (J asleep; the
watchdog counts); 8 (above); 9 (14, 45 updated; 53-58 new); 12 (L11 updated; L16, L17, L18 new);
appendix (`r8_det11.py`).

**The orchestrator's questions, how each was dealt with**
1. The new Linux readings: L16 (ds16, ds16b, ds16c: commit reached, 63/64 commit-list words
   changed by themselves at the commit, dark, no wake from any source), L17 (ds17 and ds17-1 to
   -3: commit reached, watchdog 1 reset about 120 s later, `0x0201` unchanged in ds17), L18
   (earlier Linux runs as a calibration of those readings). Two corrections against the evidence
   file's summary: the watchdog reset alone does not show that the SoC stayed powered (J), and
   only ds17's `0x0201` reading separates "not written" from "`01` then `00`" (4.4, L17). J is
   recorded as a macOS observation (1.7c, section 5, R61).
2. The central question: section 4.4, row by row. Observed differences: after the commit (row
   12) and in the clock words before the entry (row 7). Same: the last device access, the
   power-gate and always-on block words, and the armed watchdog (rows 1, 8, 11). Not read on the
   Linux side: SPMI acknowledgement after the glue's commands, each core's last registers and
   timers, `0x23d2c4000`, the commit-list values at Linux's commit, the wake masks, the domains at
   the commit (rows 2-7, 9, 10). After the last core goes down no capture has a trace (the
   instrument acts in between): open questions 53-58 name the readings. New requirements only
   where an observation supports them (R59, R60, R61).
3. D1-D4 unchanged.

## Changes in round 7 (2026-11-17 late night: run ds15, Linux awake, the seventh-round gaps W1-W14, decisions D2-D4)

Inputs: the spec at `b794596`; `docs/spec/gaps-reported-by-tests-round7.md` (W1-W14, D2-D4);
the evidence file's "Linux awake, stock kernel (19:35)" and "Run ds15"
(`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `c88cf2c`) and the log
`var/deepsleep/ds15-snap4-dmesg.txt`; the eight captures re-queried (scripts `r7_*.py`, appendix);
Aurora Silicon `aurora-silicon/linux`, `integration/aurora`, commit `dcce0e751c71`
(`pmgr-pwrstate.c`, `mailbox.c`, `rtkit.c`, `afk.c`, `dcp-internal.h`, `iomfb_m4.c`,
`apple-dart.c`, `t8103.dtsi`, `t8103-pmgr.dtsi`) and the Asahi page "ASC", as reference only,
marked so where used. Inline marks "round 7" in the text are this round's; older inline marks
("this round", "added this round") belong to the round that wrote them (lists below). Every ds15 number was checked against the log lines
by `r7_linux_ds15.py`; the "Linux awake" values have no log file and rest on the evidence text.

**Requirements added**
- R58 [BOTH]: at every wake macOS restarts, boots and stops `dcp` and `dcpext` again, domains
  off after each stop; after alarm wakes both stay stopped with their domains at the commit
  values, after key wakes `dcp` runs; never a display coprocessor stopped with its domains on.
- D2, D3, D4: the orchestrator's decisions about Linux (wake leaves stopped coprocessors as
  they are; the stop rule for `dcp`, `dcpext`, `gfx-asc`, `ans`; the first port's seven words
  off at the commit), recorded beside D1 as **decisions, not observations**, each with what the
  captures say next to it.

**Requirements changed**
- R5a: the exchange message by message (ascending endpoint stops, each answered on its own
  endpoint before the next; the acknowledgement `0x0070000000000201`; widths); +`0x8114` read
  and written values distinguished; translator writes after every `dcp`/`dcpext` stop, with
  their rule, and at every restart; "E2 has neither" withdrawn.
- R49: the ten PCIe words' width is per access (table in 1.8); coprocessor word widths.
- R54: the first port's seven words: what rests on A2/A3, Linux's values, D4.
- R55: reference reading of V as a translation-table base.
- R56: RMX's `0x300` is per place, not a rule on the read; Linux's values for the nine
  never-written words; form 3 before a sleep, request 4 with bit 28, and a missing state `0xf`
  not observed; no observed wait (reference comment cited).
- D1: Linux's DISP0_CPU0 bits 16-19 and macOS's only turn-on form for it (W8).

**Requirements withdrawn:** none. (Inside R5a and E2a: "`dcp`'s second stop in E2 has neither
[translator write]" is withdrawn.)

**Sections changed or added:** 0 (bits 24-27 counts; reference reading of bits 28, 24-27,
16-19 and of the turn-off; mailbox and coprocessor word widths, +`0x48` read only before the
stop; reference names of the control words, message types, power states, endpoint types);
1.8 (the ten PCIe words access by access); 1.9 (reference: Aurora's device-tree domains for the
blocks without one); E2a (item 2 values corrected; item 3 rewritten: every +`0xfc` write and its
rule, E2 and wake included, restarts; step 1 message by message; endpoints stopped were started
by macOS; `dcpext` stopped and off with macOS awake; what a bit-28 clear does from states 0,
`0xf`, 4); 4.3 (RMX's second write against its first wake write; request 4 under Linux);
6 W4 (`dcp` and `dcpext` at every wake); 8 (above); 9 (36, 37, 42, 43, 48 updated; 50-52 new);
12 (L11 updated; L14, L15 new); appendix (scripts).

**Gap list W1-W14, how each was dealt with**
- W1: ds15 read `dcp`, `dcpext` running (+`0x44` `0x10`, +`0x48` `0x2d`, bit-17 mailbox words);
  `gfx-asc`, `ans` not readable (domains at state 0) (L15). macOS's exchange given message by
  message and shown to stop only endpoints macOS started (E2a, R5a). D3 recorded. What `dcp`
  answers under Linux, and which endpoints Linux started: not observed (50).
- W2: a bit-28 clear observed to give state `0xf` from `0xf` and from 0 (RMX), never from 4 with
  a read after (E2a, 4.3); bits 24-27 counts (section 0); Linux DISP0_CPU0 `0x1404024f` awake and
  at the entry with `dcp` running (L14, L15); ds14's written value not in its log (L13);
  reference reading of bit 28 as automatic power management (section 0). Not observed: 43, 51.
- W3: R58 (macOS's own wakes end with both display coprocessors stopped and their domains off
  after a dark wake); D2 recorded with the note that D1 + D2 give a state in no capture (52).
- W4: R54 note; Linux's values (L15); D4 recorded. Not observed: 41.
- W5: (a) RMX `0x300` against `0x0f0003f0` from the same read (4.3, R56); (b) Linux's values of the
  nine, no observed form (R56); (c) form 3 seen at the wake only, the twelve Linux words named
  (4.3, L15); (d) not observed (R56).
- W6: every display-translator write with the read before it and its rule, E1, E2, wake and
  restarts (E2a item 3, R5a); E2's stop has them; `dart-disp0` not rewritten before T; reference
  register names and domains (E2a, 1.9). Not read under Linux (L11).
- W7: order compared (ascending, all 44 `dcp`/`dcpext` stops); reply on the stopped endpoint;
  acknowledgement `0x0070000000000201` for all six; +`0x8114` read/written values; widths in the
  text (section 0, E2a, R5a).
- W8: D1 note (only form 4 seen for DISP0_CPU0/DISPEXT_CPU0; bits 16-19); request 4 over 0
  still in no capture.
- W9: the ten PCIe words access by access (1.8), R49 changed; guarded and start words still not
  recorded during entry and wake (39).
- W10: ds15 repeats ds13's non-domain differences on a second boot (L15); who writes them under
  macOS still not observed (44).
- W11: unchanged: no capture of a commit without power-down (45).
- W12: unchanged: 46, 47 (no reference found for either).
- W13: reference domains from Aurora's device tree for some blocks, none for the rest (1.9, 48);
  not observed.
- W14: each choice against the readings: stop -> state `0xf` not shown (E2a); state 4 kept
  under request 0 seen once (L13); GFX, ANS2 awake under Linux equal macOS awake but off at the
  entry (L14, L15); first port (R54, D4); `dcp`/`dcpext` running under Linux, their answers not
  read (L15, 50).

## Changes in round 6 (2026-11-17 night: capture I, run ds14, the sixth-round gaps Q1-Q15)

Inputs: capture I (`det10`, section 1.7b) and the evidence file's "Hypervisor round 3" and "Run
ds14" (`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, commit `d7085e2`);
`var/commit-state/macos135-det10-*`, `linux-ds14-bare-ps-words.json`; the sixth-round gap list
`docs/spec/gaps-reported-by-tests-round6.md`; the device tree's power-manager table; Aurora
Silicon `aura` (`main` `5d3219cf`, `src/asc.c`) as reference only. Every number re-derived from
the logs by the scripts named (appendix), not taken from the evidence file's prose; where they
differ, the logs were used (the evidence calls `0x23b710018` DISP0_FE; it is DISP0_CPU0).

**Requirements added**
- R5a: `dcp`, `dcpext`, `gfx-asc`, `ans` stopped as `sio` and `pmp` (+`0x8114` read value with
  bit 0 cleared, +`0x48` `0x2e`, +`0x44` `0x10` -> 0), with their endpoint stops; their E2
  restart (+`0x8114` `0x20001`, +`0x44` 0 -> `0x10`).
- R56: the three turn-off forms, each written value a function of the value read; RMX's second
  write; child first; no observed wait; no observed turn-off for the nine never-written domains.
- R57: the wake's request-4 -> 0 writes and the turn-on forms; request 4 never written over 0.
- D1: the orchestrator's decision on the wake putting back what the entry changed, recorded as a
  decision about Linux, **not an observation**.

**Requirements changed**
- R5: one read of +`0x48`, always `0x2e`; a wait on it not observed.
- R7: each domain off after its coprocessor's R5a stop, by R56's forms.
- R12: the MTR word reads 0 at every read; rule and constant not distinguishable.
- R16: I's values (65 reads).
- R22a: the status words with the sub-blocks on (I): `0x4d4d01`, `0x404001`, `1`, `0x404001`.
- R30: poll range 154-246; which bits end it is not observed.
- R31: P+`0x21004` written the value read; the later `0x4000000` is the clear seen anywhere.
- R35: the alarm-wake writes come with `0x23d0d9360` reading 4 (key wakes: `0x20000000` /
  `0x20010000`) and `0xd00c` = `01`; four alarm wakes.
- R40: still one domain in one capture.
- R46, R47: I added; DCS words and `DCSn+0x500` `[VARIES]`.
- R49: `0x690000004` written as 16 bits in E5-3.
- R50: the 13 words on awake and at the commit, never written.
- R51: values now in the document (4.2a, appendix B); G-H-I 767 equal / 25 vary.
- R52: `0x23b71c0f0` withdrawn from it (`[VARIES]`); PMP and PMS_SRAM also take their commit
  values with macOS awake.
- R53: I added; awake values of the cores' and clusters' words.
- R54: by macOS's own requests 51 on / 86 off (ATC0_COMMON, ATC0_USB, ATC0_USB_AON requested off
  at boot; the snapshot's values are the hypervisor's); first port's domains `[A2]`.
- R55: V is the value macOS wrote at boot (I).

**Requirements withdrawn:** none. (`0x23b71c0f0` is withdrawn from R52's list.)

**Sections changed or added:** 0 (control-word bits 8, 9, 11; +`0x48` reference); 1.7b
(capture I, new); 1.8 (widths of `0x690000004`, guarded and start words at boot); 1.9 (device-tree
parents, virtual domains, block sizes; the 13 words of Q14); 3 E0 (P+`0x21004` clears), E2a
(coprocessor stops and DISP0_CPU0, new); 4.1b (G, H, I at the commit; every word awake; status
words, new); 4.2a (I; guarded and first-port words corrected); 4.3 (every domain write form,
new); 5 (I asleep); 6 W3 (`0x23d0d9360`, translator values from boot); 6.4 (what the wake reads
that the entry did not leave, new); 7.8 (eight captures, new); 8 (above); 9 (33, 35 closed; 34,
36, 39 narrowed; 37, 40 updated; 41-49 new); 12 (L2 addresses and the audio path's writes, L9,
L11, L12, L13 ds14 new); appendix (scripts) and appendix B (commit values, new).

**Gap list Q1-Q15, how each was dealt with**
- Q1: forms of every turn-off and turn-on with reads (4.3, R56, R57); the coprocessor stops at
  register level (E2a, R5a), their message payloads not in the log (open question 42); the nine
  never-written domains not observed (41); request 4 seen only at the wake (R57); DISP0_CPU0's
  values awake and in the entry against ds14 (E2a, L13, open question 43).
- Q2: addresses of all differing words (L2); macOS's audio path writes `0x23b0400d8` and the NCO
  (L2); the rest never written by macOS (open question 44).
- Q3: I repeats R52 except `0x23b71c0f0`; PMP, PMS_SRAM awake; periodic readings and Linux at its
  commit still not taken (34, L11).
- Q4: corrected (4.2a, R54).
- Q5: values written out (4.2a, appendix B, R51).
- Q6: decision recorded (D1); (a) request 4 over 0 never seen, (b) not observed, (c) no
  observation gives a place, (d) bits above the request given per form (4.3), (e) R40 unchanged.
- Q7: what the wake reads from the power-down (6.4); a wake without one not observed (45).
- Q8: not observed (R30, 46).
- Q9: the reading that differs (+`0x360`, `0xd00c`) given; which one macOS uses not observed (47).
- Q10: answered (E0, R31).
- Q11: one read, one value in every instance; reference names; not observed beyond (R5, 37).
- Q12: parents, virtual domains, sizes from the device tree (1.9); blocks without a property not
  observable (48).
- Q13: bit 11 seen only while waiting for a turn-on (section 0); FPWM1 on in D, E, G, H, I, off
  in F; at rest not observed (49).
- Q14: answered with I's awake readings (1.9, R50).
- Q15: L9 (macOS never accesses `0x9f03`; ds14 reads `0x00`); R12 (MTR word always 0); L12
  (cores' words); bits 8 and 9 per domain (section 0, 4.3).

## Changes in the round before round 6 (2026-11-17 evening: capture H, the Linux readings, the test authors' gaps V1-V12, F1-F10, S1-S13, T1-T12, 1-15)

Inputs: capture H (`det9`, section 1.7a); `var/commit-state/` (G and H at the commit, the Linux
readings of runs ds6, ds13, dsh2); `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`;
`docs/spec/gaps-reported-by-tests.md`. Every number below was re-derived from the logs by the
scripts named (appendix), not taken from the evidence file's prose.

**Requirements added**
- R5w: the start of `sio`'s and `pmp`'s wake actions (+`0x8114` `0x20001`, +`0x44` 0 -> `0x10`).
- R28a: `0xc5acce55` to `0x21N30fb0` before each core's start words.
- R51: the 858 commit words of G and H (`commit-state-gh.tsv`), 774 / 18 `[VARIES]`.
- R52: words changed between awake and commit with no logged write `[UNKNOWN]`.
- R53: the cores' and clusters' domain words at the commit.
- R54: the requested state of all 137 domain words at the commit (4.2a).
- R55: `pmp`'s translator writes at the wake; the translator values' source not observed.

**Requirements changed**
- R5: the +`0x8114` write is the value read with bit 0 cleared (a rule, not a constant);
  +`0x48` = `0x2e`; states what is not observed for a coprocessor that does not run.
- R6w: all 49,152 words written back with the value read in E3 (was "49,143 of 49,154").
- R9: its place among the sleep actions.
- R12: control word +`0x8` for fourteen sensors, +`0x10` for three; the written values' rule.
- R16: the values of the wait in all seven captures; the value before the pulse.
- R19 / R19w: the values read before each write of 0 and written back, in all seven; no capture
  tells "written back" from "fixed".
- R21: the six words keep their value through the sleep (first read after the wake = last
  write before it).
- R22: the literal `0x494900` withdrawn; refers to R22a.
- R22a: source files; low-byte values; status words never read while a sub-block is on; the
  control words read 0 at the wake; behaviour from another start state not observed.
- R28: core 7 also writes the performance cluster's pair.
- R30: `0x23b718000` reads `0xf` and `0x23b718004` 0 before the wake writes; the poll reads
  `0x1f` 154-243 times and ends on `0x2f`; the sub-block words read 0 before being written 1.
- R31: plane 3's `0x2000e1004` first value `[VARIES]` (`0x8000000` A, B; 0 D-H).
- R35: three alarm wakes; `0x23d0d9320` written 0, 4 after alarm wakes only.
- R36w: the rule for each of the 991 words (913 as read; 28 from the neighbour word; 39
  inverted or constant).
- R43: G and H; which `ACC_OVRD_EL1` value a core reads follows the order of reads and writes.
- R46, R47: H added; the DCS domain words `[VARIES]`.

**Requirements withdrawn:** none. (R22's literal value is withdrawn inside R22.)

**Sections changed or added:** 0 (control-word bits and mailbox status words, as documentation
and reference; the `+0x8114` forms as observation); 1.7a (capture H); 1.9 (device-tree domains
of each block; the "perf-reg" and "pwrgate-reg" tables); 3 (idle sleep H; E3 `sio`/`pmp` rows;
E5-1 sensors; E5-5b wait values; E5-8h; E6-1 rule and counts); 4.1a and 4.2a (the commit in G and
H, word by word; all 137 domain words, with Linux's values); 5 (H asleep; watchdog writes);
6 (W1-1 counts, W1-2a, W1-2h, W1-4 item 4, W2 core 7 and `0xc5acce55`, W3 `pmp` write-back,
translator writes, `sio`/`pmp` start, `0x23d0d9320`, W4 H dark); 7.7 (seven captures); 9 (open
questions 31-40, 2 and 11 updated); 12 (readings under Linux, L1-L12, all `[LINUX]`).
