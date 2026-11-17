#!/usr/bin/env python3
# Read a trace taken with S2R_DCS=3 and say when the DRAM controllers' domains stop idling.
#   harness/dcs_series.py runs/<day>/s2r-trace-<tag>.jsonl [seconds of context, default 0.5]
# Prints one line per second of the run (series taken, share of reads that show a domain fully
# on), then the last series that showed any idling, how much of the time after it has no series
# at all (lx21: 68 s of 77 s, so "never idles again" was not established), and the trace events
# around the last idling series.
import json, sys
f = sys.argv[1]; ctx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
ev = []
for l in open(f, errors="replace"):
    try: ev.append(json.loads(l))
    except Exception: pass
idle = [e for e in ev if e.get("ev") == "dcs-idle"]
if not idle: sys.exit("no dcs-idle records (run with S2R_DCS=3)")
sec = {}
for e in idle:
    b = sec.setdefault(int(e["t"]), [0, 0]); b[0] += 1; b[1] += sum(e["on"])
line = []
for s in range(int(idle[0]["t"]), int(idle[-1]["t"]) + 1):
    n, on = sec.get(s, (0, 0)); line.append("%d:%s" % (s, "-" if not n else "%d%%/%d" % (100 * on // (40 * n), n)))
print("second:fully-on share/series  " + "  ".join(line))
last = None
for e in idle:
    if sum(e["on"]) < 40: last = e
if last is None: sys.exit("the domains never idled in this trace")
after = [e for e in idle if e["t"] > last["t"]]
print("last series with idling: t=%.3f on=%s; %d series after it, all fully on, until t=%.3f" % (last["t"], last["on"], len(after), idle[-1]["t"]))
# What "all fully on" covers: a stretch with no series says nothing about the domains.
ts = [last["t"]] + [e["t"] for e in after]
gaps = sorted(((b - a, a, b) for a, b in zip(ts, ts[1:])), reverse=True)
blind = sum(g for g, _, _ in gaps if g > 1.0)
ticks = sum(1 for e in after if e.get("trigger") == "tick")
print("coverage after it: %d of the series are clocked ticks; %.1f s of the %.1f s lie in gaps over 1 s with no series%s" % (
    ticks, blind, ts[-1] - ts[0], "" if not gaps else "; longest: " + ", ".join("%.1f s (%.2f-%.2f)" % g for g in gaps[:3] if g[0] > 1.0)))
if blind > 0.25 * (ts[-1] - ts[0]):
    print("NOT ESTABLISHED: more than a quarter of that time has no series (run with S2R_DCS=3 and S2R_DCS_TICK > 0)")
def short(e):
    k = {x: e[x] for x in ("addr", "data", "ps", "region", "text", "trigger", "on", "cpu", "pc") if x in e}
    return "  t=%.4f %-9s %s" % (e["t"], e["ev"], " ".join("%s=%s" % (a, str(b)[:70]) for a, b in k.items()))
print("events from %.1f s before it to %.1f s after:" % (ctx, ctx))
# Raw mailbox words are left out: the decoded message lines (…-tx / …-rx) carry them.
for e in ev:
    if last["t"] - ctx <= e["t"] <= last["t"] + ctx and not (e["ev"] == "mmio" and "mbox" in str(e.get("region"))):
        print(short(e))
