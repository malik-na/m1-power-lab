# macOS 13.5 on the M1 MacBook Air: what it is observed to do around deep sleep

Status: observation record, written 2026-11-17 from two captures (A, B) and brought up to date
the same day with a third (D, section 1.4), which has the last accesses before power-down, and
with two more taken with the cable out (E, F, sections 1.5, 1.6, 10, 11), and with one that
adds a register snapshot at the commit and each core's system registers on the way down (G,
sections 1.7, 3 E7, 4). It states what macOS did, not
why, and not what is needed for sleep to work. Nothing here comes from any Linux sleep driver.

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
- **Memory controller (`mcc`)**: the block at `0x200000000`-`0x2003fffff`: four identical planes
  at `0x200000000`, `0x200040000`, `0x200080000`, `0x2000c0000`, common words at `0x200100000` and
  `0x200150000`, and eight DRAM channel controllers `DCS0`-`DCS7` at `0x200200000` + n x `0x40000`.
- **Coprocessor**: a small processor inside the chip running Apple firmware. macOS talks to each
  through a **mailbox**: it writes a message into two words at +`0x8800`/+`0x8808` of the
  coprocessor's block and reads replies from +`0x8830`/+`0x8838`. The low byte of the second word
  is the **endpoint** (channel); endpoint 0 carries power management messages. Coprocessors seen:
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
  which starts or stops the core itself.
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
  reflect that.
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

### E0. Operator input (T-16.6 / T-18.1 to about T-10.5): not part of the sleep

The first access that differs from idle (`firstdiff.py`) is in both captures `R 0x23d1f0980`
(`nub-gpio`), `W 0x23d1f0034`=`0x66a01`, `W 0x23d1f0980`=`0x2000`, then the SPI3 domain
`0x23b700258` cycled on and off around bursts on `spi3` (`0x23510c000`) and `sio` mailbox
traffic (A: i = 3,191,921; B: i = 1,780,143). This is the trackpad being used to click Sleep:
8,052 / 11,476 SPI3 domain writes in the last 20 s, a count that follows the operator, not
macOS's sleep. During
it `0x200021004`=`0x4000000` is written about every 0.6 s (A from T-15.8, B from T-17.4, to
T-10.3). The interval from the click to phase E1 is not determinable from the captures.

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
| AppleSmartIO | `sio`: "AP power `0x201`" echoed; "coprocessor power `0x201`" acknowledged; `R 0x236408114`, `W 0x236408114` with bit 0 cleared (`0x24401`->`0x24400` A, `0x28801`->`0x28800` B); `R 0x236400048`, `R 0x236400044`=`0x10`, **`W 0x236400044`=0** |
| ApplePMP | `pmp`: same four management words; `W 0x23bc08114` bit 0 cleared (`0x22201`->`0x22200`); **`W 0x23bc00044`=0** (was `0x10`); address translator `0x23b3000fc`: `W`=0 twice; then **49,152 reads, one per 32-bit word, of `0x23b52c000`-`0x23b55bffc`** in address order (T-2.426 to T-0.39; 2.04 s under the hypervisor) |
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
   +`0xa0`, +`0x5c`, +`0x60`), then `W` +`0x4`=`0xffffffff`, `R` +`0x10`, `W` +`0x10` with bit
   24 set, `R`, `W` +`0x10` with bit 25 set instead. The 17 bases: `0x23b281000`,
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
      `0x200041c04`, `0x200081c04`, `0x2000c1c04` (all 0);
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
   h. `W 0x23b748400`=0, then **wait**: `R 0x23b7487e0` repeated until it changes from
      `0x494002` to `0x494900` (9 polls in A, 6 in B); `W 0x23b748800`=0, `W 0x23b748c00`=0,
      `W 0x23b748000`=0, each followed by reads of +`0x7e0`;
   i. `W 0x23b71c080`=`0x80000000`, `W 0x23b71c088`=`0x80000000` (unchanged values);
      `W 0x23b718000`=0, `W 0x23b718004`=0 (each was `0xf`);
   j. the three SIO domains have bit 28 cleared: SIO_CPU `0x23b7001d0` `0x1400024f` ->
      **`0x0400024f`** (access log, T-0.0244); SIO `0x23b7001c8` and SIO_BUSIF `0x23b7001c0`
      written `0x0f0000ff` (hypervisor's log, held, `[ARTEFACT A3]`; position relative to the
      SIO_CPU write not known);
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
   At the wake all 991 words written back in W1-1 were seen here: 913 carry the value last read
   here, 18 the value last written, 38 another value (`saverestore.py` with `CAPS=d`).
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
All other cores had entered their sleep path. One capture; the list is the 792-word list of the
earlier snapshots, so it answers for these words and not for the others.

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
   `0x23b100010`=`0xe0777971`; 896 words `0x23b103000`-`0x23b103dfc`; 48 words
   `0x23b104100`-`0x23b1041dc`; 22 words `0x23b105024`-`0x23b105528`; the first 408 / 372
   written values equal what the cut sweep of E5-10 had read.
2. **Power manager** (W+0.087 to W+0.227; 1,175 writes in each capture, 2,737 / 2,728 accesses;
   address order of writes identical, 175 written values differ: they are the values saved in
   E5-8). In order:
   a. `W 0x23b718000`=`0xf`, `W 0x23b718004`=`0xf` (poll of `0x23b718004`: 9 more reads in A);
      `W 0x23b71c000`=`0x80000000`, `W 0x23b71c040`=`0x80000000`;
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
   h. 12 writes to `0x23b549000`+; `W 0x23b748000`, `c00`, `800`, `400` = 1;
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
(SIO) before. Item 4: one written value differs from A and B. DCS domain values at item 2c:
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
core at macOS's reset entry `[A4]`. First device access per core: core 7 W+0.796 / W+0.799,
core 6 W+0.799 / W+0.809, core 3 W+0.904 / W+0.883, cores 1 and 2 W+1.006 / W+1.007-1.009,
cores 5 and 4 W+1.338, W+1.351 / W+1.415, W+1.424. Each core's first device writes are
`W 0x21N155008`=`0xffbfffffffffffff`, `W 0x21N155000`=1 on its own block (for example
`0x210155008` for core 1, `0x211055008` for core 4).

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
  `0x23b52c000`-`0x23b55bffc`; of the 49,154 words first written in this action 49,143 carry the
  value last read in E3** (`saverestore.py`);
  then the coprocessor is started and boots: hello `0x00100000000c000c` / acknowledgement
  `0x00200000000c000c`, two endpoint-map exchanges, "power acknowledged `0x20`", "AP power
  `0x20`" echoed (W+3.493 to W+3.496).
- AppleT8103PMGR (W+3.497 / W+3.559): reads the wake status words `0x23d00401c`-`0x23d00402c`.
- AppleSmartIO (W+3.506): `W 0x236408114`, **`W 0x236400044`=`0x10`**, then `sio` boots (same
  message pattern as `pmp`).
- AppleGen1SPMIController (3): **`W` +`0x338` restored** (`0x23d0d9338`=`0x3f003ff1`, and the
  other two controllers).
- AppleDialogSPMIPMU: SPMI read of power-chip register `0xd00c` (`01` in A, `00` in B).
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
captured.

### W5. Back at idle

Distinct (address, direction) pairs not seen in the idle before the sleep, per second after W
(`backtoidle.py`): A 4,009, 14,069, 23,602, 12,682, 551, 924, 42, 0, then a steady 15 (the
`0x23d2b9040`.. poll of section 2); B 4,007, 12,031, 24,257, 13,999, 804, 282, 914, 113, 50,
47, 56, 23, then 0 from W+12. See section 2 for how A's idle after the wake differs.
D: 54,639 in the first second, 796, 147, 26, 56, 23, then 0 from W+6 (`det_misc.py`).
E: 54,707, 223, 179, 0, 33, 3, then 0 until the cable goes in at W+10.3. F: 54,681, 244, 205,
23, 56, 23, then 0 from W+6 until the cable goes in at W+16.1 (section 10).

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

## 8. Requirements

Form: what macOS was observed to have done before the SoC went down, or after it came up.
Marks: **[BOTH]** observed as stated in every capture that can show it: all three (A, B, D)
unless the entry says otherwise, and since section 7.5 all five (A, B, D, E, F); **[D]** observed
in the detached captures only, because only they reach that point: D, E, F and G agree unless
the entry says otherwise; **[G]** observed in capture G only (the commit snapshot and the
system registers before the wake exist nowhere else); **[UNKNOWN]** observed, cause or necessity not known, or observed incompletely;
**[ARTEFACT]** hypervisor artefact, not a requirement. Every [BOTH] entry with a register value
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
  cleared and the coprocessor's word +`0x44` is written 0 (was `0x10`) (E3).
- **R6 [BOTH]** The 196,608 bytes at `0x23b52c000`-`0x23b55bffc` have been read word by word in
  address order after `pmp` was stopped (E3). **R6w [BOTH]** After the wake the same range is
  written back before `pmp` is started (W3).
- **R7 [BOTH]** Domains GFX, DISPEXT_CPU0, DISPEXT_FE, DISP0_CPU0, DISP0_FE, RMX, APCIE_ST have
  been written to their off values of section 4, each after its coprocessor's R4 exchange (E2).
- **R8 [BOTH]** `W` +`0x338` = 1 on each SPMI controller (`0x23d0d9338`, `0x23d0e1338`,
  `0x24a829338`) (E3). **R8w [BOTH]** restored to the earlier value at the wake (W3).
- **R9 [UNKNOWN]** Power-chip register `0x9f01` has been written `0x50` (E3); at the wake it is
  written `0x00` (W3). Meaning not known; label "boot stage" is the decoding tool's.
- **R10 [BOTH]** The address translators of PCIe port 0 and of `sio` have had +`0xfc` stepped to
  0 (E3).
- **R11 [BOTH]** Cores 1-7 have written their stop bit to `0x23b754000` before any quiesce action
  runs; from then on only core 0 touches devices (E4, E5). In D the stop bits are written
  T-0.0893 to T-0.0889 and the cores enter their final sleep path only at the end (R39).
- **R12 [BOTH]** Each temperature sensor has had +`0x4` written `0xffffffff` and +`0x10` written
  with bit 24 then bit 25 set (E5-1). Order among sensors not fixed.
- **R13 [BOTH]** `0x24a820900`, `0x24a820904`, `0x23d1f0900` have been written `0xffffffff`
  (E5-2).
- **R14 [BOTH]** The 17 PCIe writes of E5-3 have been made in that order.
- **R15 [UNKNOWN]** `0x23d2b8008`, `0x23d2b800c`, `0x23d2b000c` have been written 0, and earlier
  `0x23d2b0000`, `0x23d2b0010` (E3, E5-4). Both captures agree, but the boot argument `wdt=-1`
  and the hypervisor's own use of this watchdog (A1, A9) may have changed what macOS does here.
- **R16 [BOTH]** Memory controller, in this order: pulse (`0x20010000c`=1, `0x200100014`=1)
  around `W 0x200001c00`=0, pulse released; `0x200001c04` polled until it reads 0 (39, 39, 64
  polls); then
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
  A and B only (untrapped in D, E, F).
- **R20 [BOTH]** On `0x68c008000`, `0x234008000`, `0x279008000`: +`0x14`=1, then +`0x2bc`=1, 2,
  4 (E5-8f).
- **R21 [BOTH]** Bit 63 cleared in `0x210e40250`, `0x211e40250`, `0x210e48400`, `0x211e48400`
  (E5-8g); set again at the wake (W1-2h).
- **R22 [BOTH]** `0x23b748400`=0, then `0x23b7487e0` polled until it reads `0x494900`, then
  `0x23b748800`, `0x23b748c00`, `0x23b748000` = 0; then `0x23b718000`, `0x23b718004` = 0
  (E5-8h/i). The number of polls varies (9, 6, 9).
- **R23 [BOTH]** SIO_CPU `0x23b7001d0` written with bit 28 cleared (E5-8j). **R23a [ARTEFACT]**
  The same for SIO and SIO_BUSIF is seen only through the hypervisor's guard (A3); D gives the
  order and times: SIO, SIO_BUSIF, SIO_CPU, within 15 microseconds, immediately before R24.
- **R24 [BOTH]** `0x23d2c4000` written 1 as the last write of the power manager's quiesce
  action; macOS's console calls it "Starting S2R timer" (E5-8k). It is written twice more
  (R37, R38).
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
- **R37 [D]** Then `0x23d2c4000` is written 1 a second time, with no other register access, in
  the first power-chip quiesce action (E6-2). The console text of this step is in all three.
- **R38 [D]** Then, in the second power-chip quiesce action, four SPMI commands to the power
  chip in this order: read `0xd00c` (1 byte); write `0xd008` (4 bytes); write `0xd00e` = `00`;
  write `0xd000` = `41`; each with `0x23d0d9338` written 0 before and 1 after and
  `0x23d0d9378` written 1 after the command; then `0x23d2c4000` written 1 a third time (E6-3).
  The meaning of the registers is the decoding tool's label. The console text is in all five.
  D and E as stated; in F the commands and the second write of `0x23d2c4000` (R37) come in the
  first action and the third write alone in the second; G is like F. The four alarm bytes
  differ each time.
- **R39 [D]** After R38 macOS makes no further device-register write (11 writes to SMC shared
  memory, console bytes and one console-port read are all that follow), sends the power chip
  nothing else, and all eight cores enter their final sleep path within 31 microseconds, cores
  1-7 first, core 0 last (E6-4, E6-5). How a core enters it is the hypervisor's record `[A4]`;
  the registers it writes are not visible.
- **R27 [ARTEFACT]** The power chip's alarm at now + 900 s (capture A; it replaced the alarm
  macOS had just set itself, R38), the scratch bytes
  `0x9f0a`.., the write of 1 to `0x23d0d9378` after macOS's last SPMI access, and the final
  values of the guarded words are the hypervisor's (A3, A6). Not requirements.

After the SoC comes up, before macOS is back at idle:

- **R28 [BOTH]** Core 0's first device writes: `0x210055008`=`0xffbfffffffffffff`,
  `0x210055000`=1, `0x210e49008`=`0xff5fffffffffffff`, `0x210e49000`=1; every other core
  writes the first pair on its own block when it starts (W1-0, W2).
- **R29 [BOTH]** Then 991 interrupt-controller words are written before anything else (W1-1).
- **R30 [BOTH]** Then the power manager: `0x23b718000`/`004`=`0xf`; cluster tables; every
  domain of the table written to a target state; timer and cluster state back; DCSn+`0xdc4`,
  +`0xdbc`; `0x23b748000`/`400`/`800`/`c00`=1 (W1-2). Values of DCS2, DCS3, DCS5 differ.
- **R31 [BOTH]** Then the memory controller is re-enabled: `W 0x200001c00`=`0x10` inside a
  pulse, `0x200001c04` read (`0x4200`), enables rebuilt (W1-3); then `0x200155000`=
  `0xff000000`, P+`0x21008`=`0x700`, P+`0x21000`=`0xfffffc3f`, DCSn+`0x7a0`=`0xc0000` (W1-4).
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
  `ps-post-f.tsv`).
- **R41 [BOTH] (D, E, F)** The alarm commands of R38, the stop of the cores and the whole of
  R1-R39 are the same with the cable out as with it in (section 10).
- **R42 [BOTH] (G against A, B, D, E, F)** R2-R39 hold unchanged when macOS goes to sleep by
  itself instead of on a click; only the first steps differ (audio path first, no input; R1's
  display shutdown follows 60 ms later) (section 3, "idle sleep"; `reqcheck.py`, `five.py`).
- **R43 [G]** Each core, immediately before it goes down, reads `ACC_OVRD_EL1`, writes
  `ACC_OVRD_EL1` = `0x1800101526076207` (it read `0x180010102001c207` before the first write),
  reads `CYC_OVRD_EL1` = `0x2000000` and writes `CYC_OVRD_EL1` = `0x3000001`; no other trapped
  system register is touched on any core in the 91 ms before (E7, burst 2).
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
- **R47 [G]** At the commit the 80 memory-controller and 448 DRAM-controller words of the
  snapshot list hold their idle values (section 4.1).
- **R48 [G] / [ARTEFACT]** The clock muxes written `0x80100000` in R18 hold `0x85100000` /
  `0x87100000` at the commit: the write of R18 is observed (all six captures), its effect on
  the word is not. The values of SIO, SIO_BUSIF, UART_P, UART0, ATC0_COMMON at the commit are
  the hypervisor's doing (A3) and are not requirements.
- **R35 [BOTH] (was UNKNOWN)** After an alarm wake macOS does not turn the display, graphics
  or the I5 burst back on (A for 163 s, G for the 20.8 s recorded); after a key wake it does,
  within 5 s in B and 0.7 s in D, E, F (W4, W5, section 2). Two alarm wakes, four key wakes.
  Both alarms were the hypervisor's.

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
   list built from `commit-last-writes.tsv`.
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
    network). There is still only one alarm wake.
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
    one idle sleep at the login window.

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

Capture selection: the pairwise scripts compare the two captures named in the environment
variable `CAPS` (default `3,4`; `3` = A, `4` = B, `d` = D); outputs of other pairs carry the
pair in the file name (`phases-pre-compare-3d.tsv`, `commit-last-writes-4d.tsv`, ...). Files
ending `-no4` are A or B with the four pages D did not trap removed. Window arguments may be
seconds or console anchors (`'@awdl0 disable'`, `@START`, `@END`). Per-capture extracts of D:
`phases-pre-d.tsv`, `phases-post-d.tsv`, `console-d-pre.txt`, `console-d-post.txt`,
`ps-pre-d.tsv`, `ps-post-d.tsv`, `mbox-*-d.txt`, `spmi-*-d.txt`, `saverestore-d.tsv`.
