# Power domains: the words, the forms, the ones that matter

Each domain is one 32-bit word in the power manager; macOS turns domains off and on by fixed forms that depend on the value read just before.
2026-11-20. The Nov 16 "stuck islands" finding came from an earlier driver; no clean-room run has read those gate records.

## Established

**The word** (power manager `0x23b700000`, also `0x23d280000`): [section 0, "Power manager"]
- Bits 0-3 the request, bits 4-7 the state reported; `0xf` on, `0x4` clock-gated, `0x0` off. [section 0]
- Bit 28 is set by macOS's third write of a turn-on; with it set, bits 24-27 equal bits 4-7 in 1,004 of 1,012 values. [section 0, round 7]
- Bits 8, 9 are set by the hardware when a domain goes down (`0x3f0` reads back `0x200`). [section 0]
- Bit 11 was read set only while macOS waited for a turn-on (DISP0_FE `0xb4f`). [section 0]
- Bits 24-27 read `0xf` after a coprocessor in the domain was stopped (PMP `0x1f0f03ff`). [section 0]
- Aurora's names (not established on t8103): 31 reset, 28 auto enable, 19-16 minimum state, 12 PS reset, 11 busy, 10 device disable. [section 0, reference note]

**Turn-off (request 0), R56 / section 4.3**
- Form 1, bit 28 clear: one write, read value with bits 0-9 = `0x3f0`. [R56 (1)]
- Form 2, bit 28 set: write the read value with bits 28, 9, 8 cleared; then the new read with bits 0-9 = `0x3f0`. RMX's second write is `0x300`. [R56 (2)]
- Form 3, request 4 (wake only): bits 0-9 = `0x340`. [R56 (3)]
- The first read after the write reports state 0 every time; a wait is never seen. [R56]

**Turn-on, section 4.3 forms 4-6 and R57**
- Form 4, from request 0: W bits 0-11 cleared, W +`0xf`, read until state `0xf`, W + bit 28 (RMX `0x0f000000`, `0x0f00000f`, `0x1f00000f`). [4.3 form 4]
- Form 5, from request 4: `0x44`, `0x4f`, then `0x1000004f`. Form 6, already on: PMP, PMS, SIO family `0x0f0000ff` twice, `0x1f0000ff`. [4.3 forms 5, 6]
- Request 4 is never written over request 0 in any capture. [R57]

| Domain | Word | macOS awake / commit | Linux before the entry | Source |
|---|---|---|---|---|
| PMP | `0x23b7003d8` | on; `0x1f0f03ff` at the commit | `0x1f0000ff` | [C8; L15] |
| PMS_SRAM | `0x23b7003e0` | `0x1000030f` awake; `0x1f0003ff` at the commit | `0x0f000300` (off) | [C8] |
| PMS | `0x23b700140` | on | `0x1f0000ff` | [C5; L29] |
| SIO_BUSIF / SIO / SIO_CPU | `0x23b7001c0` / `1c8` / `1d0` | `0x1400024f`; bit 28 cleared just before R24 | `0x0f000200` (off) | [C12] |
| SEP | `0x23b700c00` | `0x1000230f` (auto-gated) | `0x1f0020ff` | [C1] |
| APCIE_GP | `0x23b7003e8` | `0x1000230f` | `0x1f0020ff` | [C10] |
| DISP0_FE / DISP0_CPU0 / RMX | `0x23b700360` / `0x23b710018` / `0x23b700350` | off at the commit | on; DISP0_CPU0 `0x1404024f` | [4.4a C7; L15; ds14 evidence] |
| GFX / ANS2 | `0x23b7003f8` / `0x23b7003f0` | GFX off; ANS2 `0x1f0023ff` at the commit | `0x0f002b00` / `0x0f002300` | [4.4a C8, C9] |

- **C5's twelve** (SOC_SPMI0-2 `0x23b700118`-`128`, PMS_FPWM0-4 `0x23b700148`-`168`, AFT0 `1a8`, DEVC0_IVDMC `1b0`, FPWM0 `1d8`, FPWM2 `1e8`): request 0 with macOS awake and at its commit, request 4 under Linux; macOS lowers them only at the wake, after PMS and SIO_CPU are on. [C5]
- With the twelve held at request 4 to the commit, macOS still powered down and woke. [C5, det30]
- The display: macOS turns DISP0_CPU0 on only by form 4 (`0x0f040000`, `0x0f04000f`, wait, `0x1f04000f`). [D1, round 7]
- ds14: DISP0_CPU0 went to request 0 and kept state 4; the entry stopped there (-110). [evidence, "Run ds14"]

**The Nov 16 "stuck islands" finding** (earlier driver, macOS-27-era firmware then 13.5): the chip's sleep program polls bit 30 of power-gate records `0x23b71c090` (SIO island) and `0x23b71c360` (PCIe/NVMe island); in run 22 both stayed open and watchdog 2 reset the M1 5 s after the commit. [memory m1-s2r-stuck-islands]
- Runs 31 and 32 (SIO parents on, FPWM1 released) left both open. [same]
- The records are not writable from the AP. [same, "Awake SIO gate test"]
- At macOS's own commit `0x23b71c090` reads `0x8004030c` (bit 30 clear) and `0x23b71c360` `0xc004030b` (bit 30 set). [4.1c table]
- With one core kept running after macOS's commit, neither record changed in 4.9 s. [4.1c]
- Since then: the clean-room logic turns SIO's family on (C12) and gates APCIE_GP (C10); ds28/ds29 ran them, and no run read the two records after Linux's commit. [C12; C10; evidence "ds28", "ds29"]
- At Linux's commit (core 0 just before its final write) against macOS's commit values: AOP config `0x23d2c0000`-`3c`, `0x23d2c4000`, `0x23d2b8028`/`040`, watchdog 2 bite/control, `0x23d0d9378`, MSG, NUB_GPIO, ATC1_USB_AON, ATC1_USB, NUB_SPMI/AON/FABRIC and `0x23d2800b0`-`c0`, `060`/`068` are equal; ATC0_USB_AON `0x23d280088` and ATC0_USB `0x23d280098` differ from macOS's `0xff` (the entry turns them off in R54) [docs/experiments/2026-11-20-m2-commit-aon-compare.md, milestone-2 run 3].
- `0x23b718004` (P cluster) reads `0x10` at Linux's commit, cores 4-7 down: state 1 in bits 4-7, not 0; macOS's wake reads 0 there after a power-down and polls `0x1f` -> `0x2f` when bringing it up [milestone-2 run 4, k 157; spec 3457-3462, 3749]. macOS's value at its commit: not read. 50 ms later (core 0 held) it reads `0x50`, not 0; the old driver's run 26 recorded "P 0x50" in the same place, and that driver's other runs reached sequence 1, so `0x50` is unlikely to be the gate (inference; its meaning, bit 6, is unknown) [milestone-2 run 8; docs/evidence/2026-11-16-run26-watch/README.md 35].

## Decided

- The wake puts back each domain the entry changed to the request it found. [D1]
- A word read at request 4 is put back by form (4r): bits 0-9 = `0x244`, then read until state 4. [D6]
- A turn-on whose wait runs out makes no bit-28 write. [D5, round 15d]
- C5 writes only if PMS and the SIO family read on; otherwise reads only. [C5 requirement]

## Open

- Do the two gate records reach bit 30 after Linux's commit? Settled by reading them after the clean-room commit (watch off). [4.1c "not observed"; memory note]
- Which turn-off form macOS would use on the nine words Linux has on that macOS never writes (ATC1_COMMON, MSG, ...). No capture holds one. [R56 (b)]
- How long a word may take to report state 0 after a turn-off. Settled by a read loop after a Linux turn-off. [R56 (d)]

## Read more
- Spec `docs/spec/macos-13.5-sleep-wake-observed.md` section 0 "Power manager" (lines 92-140).
- Spec 4.3 "Every power-domain write seen" (lines 3004-3099); R56-R57 (lines 4464-4494).
- Spec 8.2 C1, C5, C8, C10, C12 (lines 6512, 6714, 6864, 6905, 6934).
- Spec 4.1c (lines 2677-2788): the power-gate records at macOS's commit.
- `~/.claude/projects/-home-naeem-Projects-m1-power-lab/memory/m1-s2r-stuck-islands.md`.
