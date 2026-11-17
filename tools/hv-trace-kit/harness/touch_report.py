#!/usr/bin/env python3
# Read touch maps taken with hv_touch_map.py and name the devices.
#   harness/touch_report.py <touch.jsonl>                    one run: devices per epoch
#   harness/touch_report.py <macos.jsonl> <linux.jsonl>      two runs: what each touches that the
#                                                            other does not, whole run and at the end
# Devices are the Apple device tree's nodes (var/map-20261117/adt/things.json, reg ranges); a page
# in no node's range is listed by address. "At the end" is the last TAIL epochs before the log's
# last record (env TAIL, default 2): for a run that ends in a sleep commit, the sleep entry.
# A device a run never touched may still have been held by the hypervisor: those zones are listed.
import bisect, json, os, sys
REPO = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + "/../../..")
ADT = os.environ.get("ADT_THINGS", REPO + "/var/map-20261117/adt/things.json")
TAIL = int(os.environ.get("TAIL", "2"))


def ranges():
    out = []
    for n in json.load(open(ADT)):
        for i, r in enumerate(n.get("reg", [])):
            if r.get("translated") is False or "addr" not in r: continue
            a, s = int(r["addr"], 16), int(r["size"], 16)
            if s and a >= 0x200000000: out.append((a, a + s, n["path"].replace("/arm-io/", ""), i))
    out.sort(key=lambda x: (x[0], x[1] - x[0]))
    return out


def namer(rs):
    """Address -> device. A node's first reg entry is its own registers; later entries are often
    words of other blocks it uses (its power-state word in the power manager, the memory
    controller's planes), so the first-entry match wins, then the smallest range."""
    def name(addr):
        best = None
        for a, b, p, i in rs:
            if a > addr: break
            if a <= addr < b:
                key = (0 if i == 0 else 1, b - a)
                if best is None or key < best[0]: best = (key, p if i == 0 else "%s.reg%d" % (p, i))
        return best[1] if best else "unnamed %#x" % (addr & ~0xfffff)
    return name


def load(path, name):
    ep, held, last = {}, [], 0
    for l in open(path, errors="replace"):
        try: e = json.loads(l)
        except Exception: continue
        if e["ev"] == "touch":
            d = ep.setdefault(e["epoch"], {}).setdefault(name(int(e["addr"], 16)), [0, 0, e["t"]])
            d[1 if e["w"] else 0] += 1; last = max(last, e["epoch"])
        elif e["ev"] == "zone" and e.get("held"):
            held.append("%s+%s (%s)" % (e["start"], e["size"], ",".join(e["held"])))
    return ep, held, last


def devs(ep, epochs): return {d for k in epochs for d in ep.get(k, {})}


def main(argv):
    name = namer(ranges())
    runs = [(os.path.basename(p),) + load(p, name) for p in argv]
    for tag, ep, held, last in runs:
        print("%s: %d epochs, %d devices touched in all, %d in the last %d; hypervisor-held zones: %d" % (
            tag, last + 1, len(devs(ep, ep)), len(devs(ep, range(last - TAIL + 1, last + 1))), TAIL, len(held)))
    if len(runs) == 1:
        tag, ep, held, last = runs[0]
        seen = set()
        for k in sorted(ep):
            new = sorted(set(ep[k]) - seen); seen |= set(ep[k])
            print("epoch %d: %d devices (%d pages); first seen here: %s" % (k, len(ep[k]), sum(a + b for a, b, _ in ep[k].values()), " ".join(new) or "-"))
        return
    (ta, ea, _, la), (tb, eb, _, lb) = runs
    for label, da, db in (("whole run", devs(ea, ea), devs(eb, eb)),
                          ("last %d epochs" % TAIL, devs(ea, range(la - TAIL + 1, la + 1)), devs(eb, range(lb - TAIL + 1, lb + 1)))):
        print("\n%s: both %d" % (label, len(da & db)))
        print("  only %s (%d): %s" % (ta, len(da - db), " ".join(sorted(da - db)) or "-"))
        print("  only %s (%d): %s" % (tb, len(db - da), " ".join(sorted(db - da)) or "-"))


if __name__ == "__main__":
    main(sys.argv[1:])
