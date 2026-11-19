# pmp: the power-management coprocessor

macOS starts `pmp` at boot, stops it before the commit and restarts it at the wake; Linux does not start it unless our client does.
2026-11-20. With macOS's translator and opening region (D17) the client runs it (ds27p); no sleep with it has woken yet.

## Established

| Part | Address | Source |
|---|---|---|
| Control page (+`0x44` run bit 4, +`0x48` status) | `0x23bc00000` | [1.7h recipe; section 0] |
| Mailbox page (+`0x8114` I2A control; send +`0x8800`/`8808`, receive +`0x8830`/`8838`) | `0x23bc08000` | [1.7h recipe; section 0] |
| Translator `dart-pmp` (sids `0x8001`, bypass `0x8000`) | `0x23b300000` | [1.7h item 3] |
| SRAM (ADT reg 2), `0x80000` bytes; block at +`0x3a800`, `0x2d0` bytes | `0x23b500000` | [1.7h item 1; R71 (a)] |
| R6's save range (196,608 bytes) | `0x23b52c000`-`0x23b55bffc` | [R6] |
| Domains PMP / PMS_SRAM / PMS | `0x23b7003d8` / `0x23b7003e0` / `0x23b700140` | [1.7h recipe] |

Word names below are fw/pmp.py's (type in bits 44-56; DevPwr: DEV bits 16-31, STATE bits 0-15). [1.7h, the fw/pmp.py note]

**macOS at boot** (R71, R72): SRAM header read; the 180-word block read and written back as read; translator set up (+`0xfc`=0 twice, +`0x34`=`0xffffffff`, +`0x20`=`0x100000`, TCRs +`0x100`=`0x80`, +`0x13c`=`0x100`, TTBR +`0x200`, +`0xfc`=1); +`0x8114` R/W `0x20001`; +`0x44` R 0, W `0x10`. [R71]
- RTKit: HELLO 12, EPMAP, STARTEP 1-4, buffers crashlog `0x18000`, ioreport `0x20000`, syslog `0x34000`, STARTEP `0x20`. [R72; 1.7h table]
- Endpoint `0x20`: RECV Startup `0x0`; SEND Configure `0x000100000003c000`; RECV Configure_Ack `0x000200000023b549`; Init1 `0x0020000000010003` / ack; Init2 `0x0020200000010000` / ack; once, DevPwr `0x0020e00000550000` (dev `0x55`, state 0) at 69 s. [R72]
- The translator maps 13 DRAM pages and 100 MMIO pages (the 34 non-empty `/arm-io/pmp` reg entries 3-43, IOVA `0xc0000000`+). [R76 (a), (b)]
- The opening region is 64 KiB at IOVA `0x3c000`: zero but for +`0x2000`-`0x207f` (`energy-model-dram-configs` bytes `0x80`-`0xff`) and +`0xe000`-`0xe28f` (41 records: IOVA, size). [R76 (c)]

**macOS at the entry**: DevPwr `…550001`, `…540001`; DevPwr_Sync `0x0020800000630000` answered `0x0020900000630000`; DevPwr `…550000`, `…540000`; then R4 (AP `0x201` echoed, IOP `0x201` acked), R5 (+`0x8114` bit 0 cleared, +`0x48` `0x2e`, +`0x44` `0x10`->0), translator +`0xfc` streams 0 and 15 off, R6 read-out. [R73; R4; R5; R6]

**macOS at the wake**: PMP, PMS_SRAM, PMS on (R74 forms); R6w writes the 196,608 bytes back; R55's ten translator writes; R5w (+`0x8114`=`0x20001`, +`0x44` 0->`0x10`); short handshake (no STARTEP, no opening); then DevPwr `…630001`, `…550001`, `…540001`, `…550000`, `…540000`, none answered. [R74; R6w; R55; R5w]

**Under Linux**
- Stock kernel: no node for `pmp`, its mailbox or translator; `pmp` not started (+`0x44` 0, +`0x48` `0x2a`). [L29]
- An earlier module (11-05 to 11-17) started it with packed IOVAs (opening `0x00010000ffff0000`); answered; no run powered down and woke. [L30]
- Client builds ds22p-ds26p (no windows, own IOVAs): `pmp` took every word through the opening, then crashed within 0.15-0.24 ms. [L33-L36]
- ds27p (D17 set-up): `pmp` answered and ran; words and opening region byte for byte macOS's. [evidence, "Linux round: the pmp client with macOS's opening region (ds27p)"]
- ds28, ds29 (logic + glue + client, `cand` `0xffffe`): commit reached with C3 words `0x333/0x444/0x222`; every run ended at the `wdt` bite. [evidence, "ds28: ...", "ds29: ..."]

**Crash-log decode**: the endpoint-1 page holds `CLHE` with sections `Cver`, `Ctim`, `Crg8`, `Ccst`, `CasC`, `Cmbx`, `Crtk`, `Ccdp`, `Csta`; `Crg8` decoded by `struct apple_rtkit_crashlog_regs` (rtkit-crashlog.c). ds25p/ds26p: pc `0x1027a10`, esr `0xbe000000` (SError), far `0x36140` / `0x210e70000`. [L36]

**Client code** (kernel tree `~/Work/deepsleep-kernel` `52669b5bb`, `drivers/soc/apple/deepsleep/`):
- `pmp.c`: adds the three DT nodes, probe, own page table (L2 = pa|`0x3`), mailbox ring, suspend/resume hooks. [pmp.c lines 1-60]
- `pmp_client.rs`: host-testable core, `PmpClient::boot`, `entry`, `wake`; waits 1 s, 6 s for `…23b549`. [pmp_client.rs lines 1-40, 465, 669, 737]
- `logic/pmp.rs`: the logic's own sleep and wake action for `pmp`. [logic/pmp.rs header]
- Tests: `~/Work/deepsleep-glue-tests-r4` `21cbbe9`, `tests/pmp_*.rs` (round 4d, against spec 15f). [its git log; TESTS.md]

## Decided

- The client (cand bit 18, C18), not the logic, runs `pmp`; it uses the mailbox driver, not the kernel's RTKit library. [D9; D11 (c)]
- Boot at probe; entry part in `prepare_late`, before `enter`; wake part first in the glue's wake. [D10 (a)-(c); pmp.c lines 22-55]
- The logic sends nothing to a `pmp` it finds stopped, and makes no R6w, R55, R5w for it. [D3 (b)]
- Before the opening, the client maps macOS's 13 DRAM pages and 34 ranges and fills the region as macOS's. [D17 (a)-(d)]

## Open

- Does the SoC power down after our commit with `pmp` stopped? Settled by a reading after the commit (power or always-on words). [evidence, "ds29: ...", "What ds29 does not show"]
- What writes the C3 words when DevPwr 0x55 is sent (R75: not established). Settled by a run with D17 and `pmp` stopped. [R75; ds27p "What ds27p does not show"]
- Is the region's place fixed at `0x3c000`? Settled by an opening word at another IOVA. [R76 "Not established"]
- What the translator holds at macOS's wake. Settled by a hypervisor read of the table at the wake. [R76 "Not established"]

**Aurora covers the same ground**: m1n1 `aurora-wip` `proxyclient/m1n1/fw/pmp.py` is the t8103 (v1) protocol: 64 KiB region, energy model at +`0x2000`, table at +`0xe000`, but packed IOVAs and the whole property (lines 89-111). `proxyclient/experiments/pmp_init.py` is the v2 protocol and exits on t8103 ("pmp v1", line 256). aura `docs/pmp-boot-data.md` covers T6000 and T8112 boot data only. [those files]

## Read more
- Spec `docs/spec/macos-13.5-sleep-wake-observed.md` 1.7h (lines 1051-1375) and R71-R76 (lines 4729-4883).
- Spec D9-D11, D17 (lines 5595-5917, 6089-6140); L29-L30, L36 (lines 8449-8527, 8788-8842).
- Evidence `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, "Linux round: the pmp client with macOS's opening region (ds27p)".
- `~/Work/deepsleep-kernel` `52669b5bb:drivers/soc/apple/deepsleep/pmp_client.rs`, lines 1-80.
- `docs/reference/asahi-aurora-sleep-deep-dive.md` section 3.4.
