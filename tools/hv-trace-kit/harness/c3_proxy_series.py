#!/usr/bin/env python3
# At the bare m1n1 proxy (no guest, no OS): do the SoC/DRAM performance words of spec 8.2 C3 move
# by themselves? Reads only, every PERIOD seconds for SECS seconds (spec open question 70, the
# cheap part).
#   harness/proxy-probe.sh <name> harness/c3_proxy_series.py [secs] [period]
# Prints one "[c3idle]" line per sample in which any word differs from the previous sample (and the
# first and last samples), and a summary. Words read (32-bit, each once per sample):
#   the three C3 words; pmp's +0x44/+0x48; the power-state words of PMP, PMS_SRAM and PMS;
#   the CPU clusters' performance command words.
import sys, time
from m1n1.setup import *      # noqa: F401,F403  (p, u, ...)

WORDS = [
    (0x23b058000, "c3_058000"), (0x23b05c000, "c3_05c000"), (0x23b060000, "c3_060000"),
    (0x23bc00044, "pmp+44"), (0x23bc00048, "pmp+48"),
    (0x23b7003d8, "ps_PMP"), (0x23b7003e0, "ps_PMS_SRAM"), (0x23b700140, "ps_PMS"),
    (0x210e20020, "ecpu_cmd"), (0x211e20020, "pcpu_cmd"),
]
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 300
period = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
t0 = time.time(); prev = None; n = 0; changes = 0
print("[c3idle] start %s, %d words every %g s for %g s" % (time.strftime("%T"), len(WORDS), period, secs), flush=True)
while True:
    t = time.time() - t0
    vals = tuple(p.read32(a) for a, _ in WORDS)
    n += 1
    last = t >= secs
    if vals != prev or last:
        if prev is not None and vals != prev:
            changes += 1
        print("[c3idle] t=%7.2f n=%4d %s" % (t, n, " ".join("%s=%#x" % (nm, v) for (_, nm), v in zip(WORDS, vals))), flush=True)
        prev = vals
    if last:
        break
    time.sleep(max(0, period - ((time.time() - t0) - t)))
print("[c3idle] end %s: %d samples, %d with a change from the sample before" % (time.strftime("%T"), n, changes), flush=True)
