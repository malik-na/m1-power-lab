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
