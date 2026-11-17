#!/usr/bin/env python3
# At the bare m1n1 proxy (no guest): the DRAM controllers' power domains idle part of the time
# after the switch (dram_gate.py). Which step towards the state of a Linux boot changes that?
#   harness/proxy-probe.sh <name> harness/proxy_idle_probe.py [steps...]
# Steps, in this order whatever the order given; none given means "cpus words":
#   nvme    m1n1's own NVMe driver: init, 2 s, shutdown, 2 s. The NVMe domain is already on at the
#           proxy, so this is the coprocessor's start, not a cold power-up of its domain.
#   spi     ps_spi1-3 = 0xf0, as Linux writes them while udev loads drivers
#   smc     the SMC handshake and key traffic as Linux's driver makes it
#   cpus    the other seven CPU cores started (m1n1's idle loop)
#   words   Linux's commit values (var/commit-state/linux-run41-dramgate-lx17-wide.json), one
#           word at a time. Every word written gets a line: the value before, the value read back
#           and a sample of 30 reads. At the end, for each controller, the word at which its
#           fully-on share changes level (changepoint()), and the count of words that differ, were
#           written and were skipped, with the skipped ones named.
#   clocks  with "words": also the NCO word and the three clock-divider words, last. Not written
#           without this: in lx20 the proxy stopped answering in the clock block when these were
#           being put back the other way.
# Never written: watchdog words, the proxy's own USB and UART domains, the +0x680/+0x684 counters,
# +0x7b0 (the controllers' state) and the ps_dcs words (the domains being measured).
#
# pidle1 (2026-11-17), read with a tolerance that hid single words: after the 44 power-state words
# dcs2 and dcs3 read fully on in 95-100 % of reads (76 and 63 before) and the other six in 0 %
# (10-18 before). The word is not known; that is what the per-word lines are for.
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(HERE + "/../../..")
PMGR = 0x23b700000
DCS_PS = [0x300, 0x310, 0x308, 0x318, 0x320, 0x330, 0x328, 0x338]
CLOCKS = (0x23b048000, 0x23b058000, 0x23b05c000, 0x23b060000)
LINK = (0x23b700420, 0x23b700270, 0x23b700220)      # ps_atc0_common, ps_uart0, ps_uart_p
GROUPS = ("AON", "AOP cfg", "PMGR clkgen", "MCC", "DCS", "PMGR PS", "PMGR other")


def skip_reason(a, name, clocks=False):
    """Why a snapshot word is never written, or None when it may be."""
    if ":" not in name:
        return "not a register-group word (watchdog, CPU bounds)"
    if 0x23d2b0000 <= a < 0x23d2c0000:
        return "watchdog"
    if a in LINK:
        return "the proxy's own USB or UART domain"
    if a in [PMGR + o for o in DCS_PS]:
        return "ps_dcs, the domain being measured"
    if 0x200200000 <= a < 0x200400000 and (a & 0x3ffff) == 0x7b0:
        return "the controller's state word"
    if a < 0x200200000 and (a & 0x3ffff) in (0x680, 0x684):
        return "a counter"
    if a in CLOCKS and not clocks:
        return "clock word (only with the clocks step)"
    return None


def plan(snapshot, clocks=False):
    """Split a commit snapshot {"0xADDR group:name": "0xVALUE"} into the words to write, in group
    order with the clock words last, and the words left alone with the reason."""
    write, skipped = [], []
    for k, v in snapshot.items():
        a = int(k.split()[0], 16); name = k.split(" ", 1)[1]; val = int(v, 16)
        why = skip_reason(a, name, clocks)
        if why:
            skipped.append((a, val, name, why)); continue
        blk = name.split(":")[0]
        blk = "DCS" if blk.startswith("DCS") else blk
        rank = len(GROUPS) + 1 if a in CLOCKS else GROUPS.index(blk) if blk in GROUPS else len(GROUPS)
        write.append((rank, a, val, name))
    write.sort(key=lambda w: w[0])
    return [w[1:] for w in write], skipped


def changepoint(series, min_side=3, min_step=12):
    """series: one controller's fully-on shares, one per row. Returns (index, mean before, mean
    after) for the split with the largest difference of means, where index is the first row of the
    new level. None unless the two sides differ by min_step points and by 3.5 standard errors
    (a share from 30 reads scatters by about 6 points around 15 %, 8 around 75 %)."""
    def sd(x):
        m = sum(x) / len(x)
        return max((sum((v - m) ** 2 for v in x) / max(len(x) - 1, 1)) ** 0.5, 1.0)
    best = None
    for i in range(min_side, len(series) - min_side + 1):
        lo, hi = series[:i], series[i:]
        a = sum(lo) / len(lo); b = sum(hi) / len(hi)
        se = (sd(lo) ** 2 / len(lo) + sd(hi) ** 2 / len(hi)) ** 0.5
        if abs(b - a) >= max(min_step, 3.5 * se) and (best is None or abs(b - a) > abs(best[2] - best[1])):
            best = (i, a, b)
    return best


def main(argv):
    from m1n1.setup import p, u
    steps = set(argv) or {"cpus", "words"}
    T0 = time.time()

    def sample(n=30):
        on = [0] * 8; gate = 0
        for _ in range(n):
            for i, o in enumerate(DCS_PS):
                if (p.read32(PMGR + o) >> 4) & 0xf == 0xf: on[i] += 1
            if p.read32(0x23b71c0d8) & 0x40000000: gate += 1
        return tuple(100 * x // n for x in on) + (100 * gate // n,)

    def show(tag, s=None):
        s = s or sample(60)
        print("[pidle] +%5.1fs %-66s fully-on %% dcs0-7: %s  gate d8 off %%: %d" % (
            time.time() - T0, tag[:66], " ".join("%3d" % x for x in s[:8]), s[8]), flush=True)
        return s

    show("the proxy as it booted")
    exec(open(HERE + "/dram_gate.py").read(), {"p": p, "json": json, "os": os})
    show("after the switch"); show("again")

    if "nvme" in steps:
        print("[pidle] ps_ans2 before %#x (actual state %x: the domain is %s)" % (
            p.read32(PMGR + 0x3f0), (p.read32(PMGR + 0x3f0) >> 4) & 0xf,
            "already on" if (p.read32(PMGR + 0x3f0) >> 4) & 0xf == 0xf else "not on"), flush=True)
        r = p.nvme_init()
        show("straight after m1n1's nvme_init (returned %s)" % r)
        for i in range(4):
            time.sleep(0.5); show("%.1f s after nvme_init" % (0.5 * i + 0.5))
        print("[pidle] ps_ans2 %#x ANS run control %#x" % (p.read32(PMGR + 0x3f0), p.read32(0x277400044)), flush=True)
        p.nvme_shutdown()
        show("straight after m1n1's nvme_shutdown")
        time.sleep(2); show("2 s after nvme_shutdown")
        print("[pidle] ps_ans2 %#x" % p.read32(PMGR + 0x3f0), flush=True)
    if "spi" in steps:
        for name, off in (("ps_spi1", 0x248), ("ps_spi2", 0x250), ("ps_spi3", 0x258)):
            was = p.read32(PMGR + off); p.write32(PMGR + off, 0xf0)
            show("%s %#x -> 0xf0 (off), reads %#x" % (name, was, p.read32(PMGR + off)))
    if "smc" in steps:
        import struct
        from m1n1.fw.smc import SMCClient
        smc = SMCClient(u, u.adt["arm-io/smc"].get_reg(0)[0])
        smc.start()
        show("SMC handshake done (management endpoints)")
        smc.start_ep(0x20); smc.verbose = 0; ep = smc.epmap[0x20]
        show("SMC key endpoint started, %d keys" % ep.read32b("#KEY"))
        try:
            ep.write("NTAP", struct.pack("<B", 1)); show("NTAP = 1 (SMC notifies the AP)")
        except Exception as e:
            print("[pidle] NTAP write: %s" % e, flush=True)
        for i in range(3):
            time.sleep(2); show("%d s later" % (2 * i + 2))
    if "cpus" in steps:
        p.smp_start_secondaries()
        show("the other seven cores started")
    if "words" not in steps:
        print("[pidle] +%5.1fs done" % (time.time() - T0), flush=True); return

    snap = json.load(open(REPO + "/var/commit-state/linux-run41-dramgate-lx17-wide.json"))
    write, skipped = plan(snap, clocks="clocks" in steps)
    rows = [("before the words", show("before the words")), ("before the words (2)", show("before the words (2)")),
            ("before the words (3)", show("before the words (3)"))]
    same = 0
    for a, v, name in write:
        try:
            was = p.read32(a)
            if was == v:
                same += 1; continue
            p.write32(a, v); rb = p.read32(a)
        except Exception as e:
            print("[pidle] +%5.1fs %s %#x: %s" % (time.time() - T0, name, a, e), flush=True); raise
        tag = "%s %#x -> %#x, reads %#x" % (name.split(":")[-1][-24:], was, v, rb)
        rows.append((tag, show(tag, sample(30))))
    for i in range(3):
        rows.append(("after the words (%d)" % (i + 1), show("after the words (%d)" % (i + 1))))
    differing_skipped = []
    for a, v, name, why in skipped:
        if ":" not in name: continue
        try:
            if p.read32(a) != v: differing_skipped.append("%#x %s (%s)" % (a, name.split(":")[-1], why))
        except Exception as e:
            differing_skipped.append("%#x %s (not readable: %s)" % (a, name.split(":")[-1], e))
    print("[pidle] words: %d in the snapshot, %d written, %d already at Linux's value, %d left alone of which %d differ" % (
        len(snap), len(rows) - 6, same, len(skipped), len(differing_skipped)), flush=True)
    for d in differing_skipped:
        print("[pidle] differs, not written: " + d, flush=True)
    for c in range(8):
        cp = changepoint([r[1][c] for r in rows])
        print("[pidle] dcs%d: %s" % (c, "no change of level" if cp is None else
              "%d %% before, %d %% from: %s" % (cp[1], cp[2], rows[cp[0]][0])), flush=True)
    print("[pidle] +%5.1fs done" % (time.time() - T0), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
