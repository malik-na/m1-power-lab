# The DRAM controllers are in a different state under macOS, from early boot (2026-11-16)

## Wide reading at the commit (823 words each)

`S2R_SNAP_LIST=var/recfg/commit-snap-list-wide.json`: the earlier 249 words plus the memory-cache
controller, the eight DRAM controllers (the words the engine's program reads) and the AOP's
configuration words. macOS 13.5 (hv 135snap2) against Linux run41 (hv lx14), no read errors.
54 differ; beyond the flag and status bits already known from the 279-word reading:

| Word | macOS 13.5 | Linux run41 |
|---|---|---|
| DCS0-7 +0x7b0 (low nibble) | **0** on all eight | **3** on all eight |
| ps_dcs0-4, actual state | 4 (idle) | f |
| power gates PMGR+0x1c0d8, +0x1c0f0, bit 30 | set | clear |
| MCC planes +0x680/+0x684 | iBoot's CTRR-A bounds for that boot | (differ per boot; not a system difference) |

AON clock words and the AOP's configuration words: equal.

The engine's program reads these: sequence 7 checks `DCSn+0x7b0 & 0xf == 3` on all eight
controllers; sequence 4 checks bit 30 of power gates +0xd8, +0x108, +0xf0.

## When macOS gets there (hv run 135dcs1, `S2R_DCS=1`)

The tracer now traces the AP's writes to the DRAM controllers and the memory-cache controller, and
samples DCS0/7+0x7b0, ps_dcs0 and gate +0xd8 at every AP->AOP message. At the first sample, 2.37 s
after the guest start, +0x7b0 is already 0 and ps_dcs0 moves between f, 4 and 0 with the gate's bit
30 following: the controllers power-gate themselves when idle. Under Linux (bare metal, 4000
samples; and at the commit under the hypervisor) +0x7b0 stays 3, ps_dcs 0x1f0002ff, gates clear.

XNU's writes before that (t 0.45-1.86 s; `var/commit-state/macos135-dcs-mcc-boot-writes.json`):
a table on DCS0 (+0x580 = 0x71, +0x584 = 0x1ff, nine 5-word entries at +0x58c..+0x640); on every
controller +0xdc4 = 0x0813057f, +0xdbc = 0x01800180, **+0xc = 0x070a1100** (Linux has 0x070a0100),
+0x7a0 = 0xc0000; on every memory-cache plane +0x72c = 0xffffffff, +0x730 = 0x30000 (Linux: 0).
It also writes each ps_dcs word 0x0f0000ff then 0x1f0000ff, and ~500 words in PMGR+0x34000.

## Tried under Linux, live (bare metal, /dev/mem)

All 113 of those controller words written with macOS's values (read back as written): +0x7b0 stayed
3 and the controllers did not start gating, over 2.5 s. The machine kept running. So those writes
alone do not switch the state; what does is not found yet.

## Next

- Sample +0x7b0 from the guest's first instruction on, to find the moment it leaves 3 under macOS
  and the writes just before it (the PMGR+0x34000 block and the PMP's start are candidates).

## The recipe, and the test of it (2026-11-17)

- Per-write sampling under macOS (hv 135dcs3, `S2R_DCS=2`): +0x7b0 leaves 3 during XNU's
  `DCSn+0xc = 0x070a1100` writes (bit 12), with the auto flag already on the ps_dcs words.
- At the m1n1 proxy (no guest): bit 12 on all eight controllers alone changes nothing; adding
  the auto flag (bit 28) on ps_dcs0-7 switches all eight to 0 at once, ps_dcs0 reads 0x1000030f
  (gated) and gate +0xd8 reports. Sixteen writes; XNU's table and MCC words are not needed for it.
- Once Linux runs, the same writes do nothing: live on bare metal (with and without XNU's table,
  with the power-state words as XNU has them), and in the driver's slow part at the commit
  (**run 42**, kernel 7.2.11-run42 = s2r-rs1-135 0008e4871, `dram_gate=1`: record byte 0x9f11 =
  0x80, 0 of 8 switched; restart 29.8 s from release to Omarchy as before). Without XNU's table
  the auto-flag rewrite crashed live Linux once.
- **Switched before the guest starts** (`harness/dram_gate.py`, hv runs lx16/lx17, Linux run41):
  all eight read 0 after the script, Linux boots and runs normally, and at its commit all eight
  still read 0 (lx17 snapshot). **With real S2R (lx16) the M1 still restarted**: commit
  00:35:41.44, Omarchy on Thunderbolt 00:36:11.39 (29.95 s), no wake.

So the +0x7b0 state, though the engine's program reads it and Linux differs from macOS in it, is
not what decides the restart. What still differs at the commit with it equal (lx17 against
135snap2, 42 of 823 words): the DRAM controllers' domains are busy under Linux (ps_dcs actual f,
gates +0xd8/+0xf0 bit 30 clear) and idle under macOS (dcs0-4 actual 4, bit 30 set); the rest is
flag and status bits, iBoot's CTRR bounds and the watchdog words.
