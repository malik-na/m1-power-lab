# hv script, run from the hypervisor's shell after a non-real commit: hv.run_script("<this file>")
# The DRAM controllers' domains idled at the proxy right after the switch (dram_gate.py) and read
# fully on at Linux's commit. This puts the registers back to what they read at the proxy
# (var/commit-state/m1n1-proxy-wide.json), one word at a time, redoing the switch's auto-flag edge
# after each, and samples: the word after which the domains start to idle is what holds them.
# Left alone: watchdog words, the +0x680/+0x684 counters, +0x7b0 (the state itself), and four
# clock words (NCO 0x23b048000, dividers 0x23b058000/0x23b05c000/0x23b060000): in lx20 the proxy
# stopped answering while this script was in the clock block, last seen at 0x23b05c000.
# Every word written gets a line: the value before, the value read back, and a sample.
import json, time
PMGR = 0x23b700000
DCS_PS = [0x300, 0x310, 0x308, 0x318, 0x320, 0x330, 0x328, 0x338]
T0 = time.time()
p.write32(0x23d2b001c, 0); p.write32(0x23d2b002c, 0)   # both watchdogs off (170 s and 100 s nets)
print("[idle2] watchdog control words after writing 0: WD1 %#x WD2 %#x" % (p.read32(0x23d2b001c), p.read32(0x23d2b002c)), flush=True)
def sample(n=12):
    on = [0] * 8; gate = 0
    for _ in range(n):
        for i, o in enumerate(DCS_PS):
            if (p.read32(PMGR + o) >> 4) & 0xf == 0xf: on[i] += 1
        if p.read32(0x23b71c0d8) & 0x40000000: gate += 1
    return tuple(100 * x // n for x in on) + (100 * gate // n,)
def show(tag, s):
    print("[idle2] +%5.1fs %-58s fully-on %% dcs0-7: %s  gate d8 off %%: %d" % (
        time.time() - T0, tag, " ".join("%3d" % x for x in s[:8]), s[8]), flush=True)
def edge():
    for i in range(8): p.write32(0x20020000c + 0x40000 * i, 0x070a0100)
    for i in range(8): p.write32(0x20020000c + 0x40000 * i, 0x070a1100)
    for o in DCS_PS:
        p.write32(PMGR + o, 0x0f0000ff); p.write32(PMGR + o, 0x1f0000ff)
last = sample(40); show("start", last)
edge(); last = sample(40); show("switch redone (bit 12, auto-flag edge)", last)
ref = json.load(open("/home/naeem/Projects/m1-power-lab/var/commit-state/m1n1-proxy-wide.json"))
groups = {}
for k, v in ref.items():
    a = int(k.split()[0], 16); name = k.split(" ", 1)[1]; blk = name.split(":")[0]
    if 0x23d2b0000 <= a < 0x23d2c0000 or a in (0x23b700420, 0x23d280088, 0x23d280098): continue
    if a in (0x23b048000, 0x23b058000, 0x23b05c000, 0x23b060000): continue
    if a < 0x200200000 and (a & 0x3ffff) in (0x680, 0x684): continue
    if (a & 0x3ffff) == 0x7b0 and 0x200200000 <= a < 0x200400000: continue
    if a in [PMGR + o for o in DCS_PS]: continue
    if blk.startswith("DCS"): blk = "DCS"
    groups.setdefault(blk, []).append((a, int(v, 16), name))
for blk in ("AON", "AOP cfg", "PMGR clkgen", "MCC", "DCS", "PMGR PS", "PMGR other"):
    n = 0
    for a, v, name in groups.get(blk, []):
        try:
            was = p.read32(a)
            if was == v: continue
            p.write32(a, v); n += 1; edge(); s = sample(30)
        except Exception as e:
            print("[idle2] +%5.1fs %s %#x: %s" % (time.time() - T0, name, a, e), flush=True); raise
        show("%s %#x -> %#x, reads %#x" % (name.split(":")[-1][-22:], was, v, p.read32(a)), s); last = s
    s = sample(40); show("%s: %d words back to the proxy's values" % (blk, n), s); last = s
print("[idle2] +%5.1fs done" % (time.time() - T0), flush=True)
