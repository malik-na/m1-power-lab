# hv script: before the guest starts, put the eight DRAM controllers into the self-gating state
# macOS 13.5 runs them in (2026-11-16/17). At the m1n1 proxy, with only the boot core running,
# bit 12 of every DCSn+0xc plus a 0 -> 1 edge of the auto flag on the ps_dcs words switches
# DCSn+0x7b0 from 3 to 0; once Linux runs (run 42, and live) the same writes do nothing.
# XNU's own table on controller 0 and its memory-cache words go in first (xnu-dcs-mcc-writes.json,
# traced from XNU's boot, hv run 135dcs1).
import json, os
_W = json.load(open(os.environ.get("DRAM_GATE_WRITES", "/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit/harness/xnu-dcs-mcc-writes.json")))
_st = lambda: tuple(p.read32(0x2002007b0 + 0x40000 * i) & 0xf for i in range(8))
print("[dram] before:", _st())
p.write32(0x23b71c000, 0x80000000)
for _a, _v in _W:
    if (_a & 0x3ffff) != 0xc:
        p.write32(_a, _v)
for _i in range(8):
    p.write32(0x20020000c + 0x40000 * _i, 0x070a1100)
for _a in (0x23b700300, 0x23b700310, 0x23b700308, 0x23b700318, 0x23b700320, 0x23b700330, 0x23b700328, 0x23b700338):
    p.write32(_a, 0x0f0000ff); p.write32(_a, 0x1f0000ff)
print("[dram] after XNU's setup, bit 12 and the auto-flag edge:", _st(),
      "ps_dcs0 %#x gate+0xd8 %#x" % (p.read32(0x23b700300), p.read32(0x23b71c0d8)))
