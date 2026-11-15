#!/usr/bin/env python3
"""M1 hardware database: one SQLite file for everything learned about the M1 Air's hardware.

  hwdb.py DB init
  hwdb.py DB inventory INV_DIR STATE          load one collect-inventory.sh output as a snapshot
  hwdb.py DB dtmap MAP_TSV                    load tools/regmap/dt-map.py output (the address map)
  hwdb.py DB regs SNAPSHOT_ID MRD_OUT [LABELS] load an mrd / mrd-stream output (LABELS: list file
                                              with "# label" comments) as register reads
  hwdb.py DB fault ADDR WIDTH KERNEL NOTE     record a read that took the machine down
  hwdb.py DB note TOPIC TEXT                  add a research note
  hwdb.py DB summary                          counts per table

Tables (see README): snapshot, block, attr, platform_device, power_domain, smc_key, reg_read,
read_fault, note. The DB lives in var/ (gitignored): register values stay private.
"""
import os
import re
import sqlite3
import sys
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY, taken_at TEXT, kernel TEXT, boot_id TEXT,
  state TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS block (start INTEGER, size INTEGER, node TEXT, reg_name TEXT, compatible TEXT,
  status TEXT, power_domains TEXT, driver TEXT, note TEXT, PRIMARY KEY (start, node, reg_name));
CREATE TABLE IF NOT EXISTS attr (snapshot INTEGER, subsystem TEXT, object TEXT, name TEXT, value TEXT);
CREATE INDEX IF NOT EXISTS attr_obj ON attr (subsystem, object, name);
CREATE TABLE IF NOT EXISTS platform_device (snapshot INTEGER, name TEXT, of_node TEXT, driver TEXT,
  runtime_pm TEXT);
CREATE TABLE IF NOT EXISTS power_domain (snapshot INTEGER, name TEXT, raw TEXT, target TEXT, actual TEXT,
  min TEXT, auto INTEGER, busy INTEGER, clkgated INTEGER, pwrgated INTEGER);
CREATE TABLE IF NOT EXISTS smc_key (snapshot INTEGER, key TEXT, type TEXT, size INTEGER, flags TEXT,
  value TEXT);
CREATE TABLE IF NOT EXISTS reg_read (snapshot INTEGER, addr INTEGER, width INTEGER, value TEXT,
  label TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS reg_addr ON reg_read (addr);
CREATE TABLE IF NOT EXISTS read_fault (addr INTEGER, width INTEGER, kernel TEXT, at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS note (at TEXT, topic TEXT, text TEXT);
CREATE VIEW IF NOT EXISTS reg_map AS
  SELECT printf('%#x', r.addr) AS addr, r.width, r.value, r.label,
         (SELECT b.node FROM block b WHERE r.addr >= b.start AND r.addr < b.start + b.size ORDER BY b.size LIMIT 1) AS node,
         (SELECT b.driver FROM block b WHERE r.addr >= b.start AND r.addr < b.start + b.size ORDER BY b.size LIMIT 1) AS driver,
         r.snapshot
  FROM reg_read r;
"""


def db(path):
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    return c


def sections(path):
    """'### name' headed key=value files -> {name: [(k, v)]}"""
    out, cur = {}, None
    if not os.path.exists(path):
        return out
    for line in open(path, errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("### "):
            cur = line[4:].strip()
            out.setdefault(cur, [])
        elif cur is not None and "=" in line:
            k, v = line.split("=", 1)
            out[cur].append((k, v.strip()))
    return out


def inventory(c, d, state):
    ident = open(os.path.join(d, "identity.txt")).read().splitlines()
    kernel = ident[0].split()[2] if ident else "?"
    boot = ident[-1] if ident else "?"
    cur = c.execute("INSERT INTO snapshot (taken_at, kernel, boot_id, state, source) VALUES (?,?,?,?,?)",
                    (time.strftime("%Y-%m-%dT%H:%M:%S"), kernel, boot, state, os.path.abspath(d)))
    sid = cur.lastrowid
    for fn in os.listdir(d):
        if fn.endswith(".txt") and fn not in ("smc_keys.txt", "pmgr_ps.txt"):
            sub = fn[:-4]
            for obj, kvs in sections(os.path.join(d, fn)).items():
                c.executemany("INSERT INTO attr VALUES (?,?,?,?,?)", [(sid, sub, obj, k, v) for k, v in kvs])
    p = os.path.join(d, "platform.tsv")
    if os.path.exists(p):
        rows = [l.rstrip("\n").split("\t") for l in open(p) if l.strip()]
        c.executemany("INSERT INTO platform_device VALUES (?,?,?,?,?)", [(sid, *r[:4]) for r in rows if len(r) >= 4])
    p = os.path.join(d, "pmgr_ps.txt")
    if os.path.exists(p):
        for l in open(p):
            f = l.split()
            if not f:
                continue
            kv = dict(x.split("=", 1) for x in f[1:] if "=" in x)
            c.execute("INSERT INTO power_domain VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (sid, f[0], kv.get("raw"), kv.get("target"), kv.get("actual"), kv.get("min"),
                       int(kv.get("auto", 0)), int(kv.get("busy", 0)), int(kv.get("was_clkgated", 0)),
                       int(kv.get("was_pwrgated", 0))))
    p = os.path.join(d, "smc_keys.txt")
    if os.path.exists(p):
        for l in open(p, errors="replace"):
            f = l.rstrip("\n").split(None, 4)
            if len(f) >= 4:
                c.execute("INSERT INTO smc_key VALUES (?,?,?,?,?,?)",
                          (sid, f[0], f[1], int(f[2]) if f[2].isdigit() else None, f[3], f[4] if len(f) > 4 else ""))
    c.commit()
    print("snapshot", sid)


def dtmap(c, p):
    rows = [l.rstrip("\n").split("\t") for l in open(p)][1:]
    c.executemany("INSERT OR REPLACE INTO block VALUES (?,?,?,?,?,?,?,?,?)",
                  [(min(int(r[0], 16), 2**63 - 1), min(int(r[1], 16), 2**63 - 1), r[3], r[4], r[5], r[6], r[7], r[8], r[9] if len(r) > 9 else "")
                   for r in rows if len(r) >= 9])
    c.commit()
    print(len(rows), "blocks")


def regs(c, sid, out, labels):
    lab = {}
    if labels:
        for l in open(labels):
            m = re.match(r"\s*(0x[0-9a-fA-F]+)\s+\d+\s*#\s*(.*)", l)
            if m:
                lab[int(m.group(1), 16)] = m.group(2).strip()
    n = 0
    for l in open(out, errors="replace"):
        m = re.match(r"(0x[0-9a-f]+) ([48]) ((?:0x)?[0-9a-f]+)\s*$", l.strip())  # mrd prints 0 as 0000000000
        if m:
            a = int(m.group(1), 16)
            c.execute("INSERT INTO reg_read VALUES (?,?,?,?,?,?)",
                      (sid, a, int(m.group(2)), "%#0*x" % (2 + 2 * int(m.group(2)), int(m.group(3), 16)), lab.get(a, ""), os.path.basename(out)))
            n += 1
    c.commit()
    print(n, "reads")


def main():
    c = db(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "init":
        pass
    elif cmd == "inventory":
        inventory(c, sys.argv[3], sys.argv[4])
    elif cmd == "dtmap":
        dtmap(c, sys.argv[3])
    elif cmd == "regs":
        regs(c, int(sys.argv[3]), sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None)
    elif cmd == "fault":
        c.execute("INSERT INTO read_fault VALUES (?,?,?,?,?)",
                  (int(sys.argv[3], 16), int(sys.argv[4]), sys.argv[5], time.strftime("%Y-%m-%dT%H:%M:%S"), sys.argv[6]))
        c.commit()
    elif cmd == "note":
        c.execute("INSERT INTO note VALUES (?,?,?)", (time.strftime("%Y-%m-%dT%H:%M:%S"), sys.argv[3], sys.argv[4]))
        c.commit()
    elif cmd == "summary":
        for t in ("snapshot", "block", "attr", "platform_device", "power_domain", "smc_key", "reg_read", "read_fault", "note"):
            print(f"{t:16} {c.execute(f'SELECT count(*) FROM {t}').fetchone()[0]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
