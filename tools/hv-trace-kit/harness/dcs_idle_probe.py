# hv script, run from the hypervisor's shell after a non-real commit ("Hypervisor exited"):
#   hv.run_script("<this file>")
# Question: what keeps the DRAM controllers busy at Linux's commit? Under macOS their domains idle
# (ps_dcs actual 4, power gates +0xd8/+0xf0 bit 30 set); under Linux they read fully on. The
# probe samples them, then stops one candidate at a time (coprocessor cores through their run
# control, the PCIe domains) and samples again after each.
# lx18 (2026-11-17): the M1 restarted about 8 s after this probe began, step not known. So every
# line carries the seconds since the probe began, and each step is followed by a hold of
# S2R_PROBE_HOLD seconds (default 12) with a read every half second: the step after which the
# link dies is the one that restarts the machine.
import json, os, time
T0 = time.time(); HOLD = float(os.environ.get("S2R_PROBE_HOLD", "12"))
def hold(tag):
    end = time.time() + HOLD
    while time.time() < end:
        p.read32(0x23b700300); time.sleep(0.5)
    print("[idle] +%5.1fs still up %g s after: %s" % (time.time() - T0, HOLD, tag), flush=True)
PMGR = 0x23b700000
DCS_PS = [0x300, 0x310, 0x308, 0x318, 0x320, 0x330, 0x328, 0x338]
GATES = [0xd8, 0xf0, 0x108, 0x120]
# Both watchdogs off, read back: the guest leaves watchdog 1 at 170 s and watchdog 2 at 100 s
# (0x23d2b0024 = 0x8f0d1800, 0x23d2b002c = 4). lx19 and lx20 left the bus about 100 s after the
# commit, each in the same second as a probe step, so the two could not be told apart.
p.write32(0x23d2b001c, 0); p.write32(0x23d2b002c, 0)
print("[idle] watchdog control words after writing 0: WD1 %#x WD2 %#x" % (p.read32(0x23d2b001c), p.read32(0x23d2b002c)), flush=True)

def sample(tag, n=60):
    on = [0] * 8; gate = [0] * 4
    for _ in range(n):
        for i, o in enumerate(DCS_PS):
            if (p.read32(PMGR + o) >> 4) & 0xf == 0xf: on[i] += 1
        for i, o in enumerate(GATES):
            if p.read32(0x23b71c000 + o) & 0x40000000: gate[i] += 1
    print("[idle] +%5.1fs %-34s fully-on %% dcs0-7: %s   gate-off %% d8/f0/108/120: %s" % (
        time.time() - T0, tag, " ".join("%3d" % (100 * x // n) for x in on), " ".join("%3d" % (100 * x // n) for x in gate)), flush=True)

def ps(off): return p.read32(PMGR + off)
def stop_asc(name, base, ps_off=None):
    if ps_off is not None and (ps(ps_off) >> 4) & 0xf != 0xf:
        print("[idle] %s: its domain is not on (%#x); left alone" % (name, ps(ps_off)), flush=True); return
    before = p.read32(base + 0x44)
    p.write32(base + 0x44, 0)
    sample("%s core: run control %#x -> 0" % (name, before))
    print("[idle] %s run control reads back %#x%s" % (name, p.read32(base + 0x44), "" if ps_off is None else ", its domain %#x" % ps(ps_off)), flush=True)
    hold(name + " core stopped")

sample("as the guest left it")
hold("nothing (watchdog 1 off only)")
stop_asc("AOP", 0x24a400000)
stop_asc("PMP", 0x23bc00000, 0x3d8)
stop_asc("SIO", 0x236400000, 0x1d0)
stop_asc("NVMe (ANS)", 0x277400000, 0x3f0)
stop_asc("GPU", 0x206400000, 0x3f8)
stop_asc("DCP", 0x231c00000, 0x10018)
stop_asc("DCPEXT", 0x271c00000, 0x378)
for name, off in (("apcie_gp", 0x3e8), ("apcie_st", 0x418), ("ans2", 0x3f0)):
    v = ps(off); p.write32(PMGR + off, v & ~0x1000000f)
    sample("%s target off (was %#x)" % (name, v))
    print("[idle] %s reads back %#x (actual state %x)" % (name, ps(off), (ps(off) >> 4) & 0xf), flush=True)
    hold(name + " target off")
# The SMC's core is left alone. In lx18 the M1 restarted 8 s after the commit and the SMC stop
# (0x23e400044 = 0) was the probe's last step. In lx19 the link went 0.6 s after the SMC stop, but
# that was also 100 s after the commit, where watchdog 2 was set: the two are not separated.
on = []
for a, n in json.load(open("/home/naeem/Projects/m1-power-lab/var/recfg/commit-snap-list.json")):
    if "PMGR PS" in n or n.startswith("AON:ps") or ":ps_" in n:
        v = p.read32(a)
        if (v >> 4) & 0xf == 0xf: on.append("%s=%#x" % (n.split(":")[-1], v))
print("[idle] domains still fully on (%d): %s" % (len(on), " ".join(on)), flush=True)
print("[idle] done", flush=True)
