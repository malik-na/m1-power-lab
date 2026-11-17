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
round 6 restated as statements a test can check (sections 1.7f, 8.1) (round 11, 2026-11-18,
listed in "Changes in this round" at the end, with the earlier rounds' lists below it). It
states what macOS did, not why, and not what is needed for sleep to work.
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
- **D4 — a decision about Linux, not an observation of macOS** (the orchestrator's default to
  gap W4): *the driver is held to all seven first-port domains (ATC0_COMMON, ATC0_USB_AON,
  ATC0_USB, ATC0_PCIE, ATC0_CIO, ATC0_CIO_PCIE, ATC0_CIO_USB) being requested off at the commit,
  as R54 has it, although that rests on the hypervisor's artefacts A2/A3; D1 puts them back at
  the wake.* What the captures say next to it: R54's round-7 note; the forms macOS would use on
  these words from Linux's values (`0x22ff`, `0x2ff`, `0x3ff`) are those of a bit-28-clear word
  (form 1, 4.3; seen for the first three at boot, through the hypervisor's guard, A3); the four
  never-written ones have no observed turn-off (R56).

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
  +`0x378` reads 0 at the commit.
- Firmness of the last part: no power-down was captured without it; the two runs without the
  instrument's last write woke early (0.65 s, 1 s), they did not stay up. Not testable: whether
  the order of +`0x378`'s write against +`0x308`'s read matters (one order seen).

**R61. Watchdog 1 armed at the commit.** *Not a step macOS takes; the instrument's, in seven
power-downs (J, K, L, `det19b`, `det21`, `det23`, `det24`), none prevented.*
- Test (only if the driver or glue arms it): W `0x23d2b001c` = 0, W `0x23d2b0010` = 0, W
  `0x23d2b0014` = N x 24,000,000, W `0x23d2b001c` = 4, after every other device write of the
  commit and before core 0's final write.

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

## Changes in this round (round 11, 2026-11-18: the round-11 runs det23 and det24, the power-gate header word cleared at the commit, Linux awake again, the requirements since round 6 as test statements)

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
