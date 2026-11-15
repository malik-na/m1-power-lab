#!/usr/bin/env python3
"""Address map of a live Apple-silicon device tree (read from /sys/firmware/devicetree/base).

  dt-map.py DT_DIR [BINDINGS] > map.tsv

DT_DIR is an extracted copy of /sys/firmware/devicetree/base. BINDINGS (optional) is a file
of lines "<of_node path> <driver>" for every bound platform device (see collect in the README).
Prints one row per reg entry: absolute physical start, size, end, node path, compatible,
status, power domains (by PMGR node name), bound driver. Addresses are translated through
every parent's "ranges" (a bus with an empty ranges maps 1:1; a bus without ranges stops
translation, marked "untranslated"). Nothing here touches hardware.
"""
import os
import struct
import sys


def cells(path, name, default):
    p = os.path.join(path, name)
    if not os.path.exists(p):
        return default
    return struct.unpack(">I", open(p, "rb").read()[:4])[0]


def read_cells(data, n):
    v = 0
    for i in range(n):
        v = (v << 32) | struct.unpack(">I", data[4 * i:4 * i + 4])[0]
    return v, data[4 * n:]


def prop(path, name):
    p = os.path.join(path, name)
    return open(p, "rb").read() if os.path.exists(p) else None


def strs(b):
    return [s for s in b.decode(errors="replace").split("\0") if s] if b else []


def main():
    root = sys.argv[1].rstrip("/")
    bound = {}
    if len(sys.argv) > 2:
        for line in open(sys.argv[2]):
            parts = line.split()
            if len(parts) == 2:
                bound[parts[0]] = parts[1]

    # phandle -> node path, for power-domains
    phandles = {}
    for d, _, files in os.walk(root):
        if "phandle" in files:
            phandles[struct.unpack(">I", open(os.path.join(d, "phandle"), "rb").read()[:4])[0]] = d

    def translate(node, addr):
        """Walk up from node's parent bus, applying each ranges; return (addr, ok)."""
        bus = os.path.dirname(node)
        while bus != root and bus.startswith(root):
            parent = os.path.dirname(bus)
            r = prop(bus, "ranges")
            if r is None:
                # A syscon parent (the PMGR): children's reg are offsets into its first reg window.
                if any("syscon" in c for c in strs(prop(bus, "compatible"))) and prop(bus, "reg"):
                    pca = cells(parent, "#address-cells", 2)
                    base, _ = read_cells(prop(bus, "reg"), pca)
                    base, ok = translate(bus, base)
                    return base + addr, ok
                return addr, False
            if len(r) == 0:
                bus = parent
                continue
            ca = cells(bus, "#address-cells", 2)
            pa = cells(parent, "#address-cells", 2)
            cs = cells(bus, "#size-cells", 1)
            hit = False
            while r:
                child, r = read_cells(r, ca)
                par, r = read_cells(r, pa)
                size, r = read_cells(r, cs)
                if child <= addr < child + size:
                    addr = par + (addr - child)
                    hit = True
                    break
            if not hit:
                return addr, False
            bus = parent
        return addr, True

    rows = []
    for d, _, files in os.walk(root):
        if "reg" not in files or d == root:
            continue
        parent = os.path.dirname(d)
        ca = cells(parent, "#address-cells", 2)
        cs = cells(parent, "#size-cells", 1)
        if cs == 0:  # not memory-mapped (i2c, spmi, ...)
            continue
        reg = prop(d, "reg")
        names = strs(prop(d, "reg-names"))
        comp = ",".join(strs(prop(d, "compatible"))) or "-"
        status = (strs(prop(d, "status")) or ["okay"])[0]
        pds = []
        pdb = prop(d, "power-domains")
        if pdb:
            for i in range(0, len(pdb), 4):
                ph = struct.unpack(">I", pdb[i:i + 4])[0]
                if ph in phandles:
                    pds.append(os.path.basename(phandles[ph]))
        rel = d[len(root):] or "/"
        drv = bound.get(rel, "-")
        i = 0
        while reg and len(reg) >= 4 * (ca + cs):
            a, reg = read_cells(reg, ca)
            s, reg = read_cells(reg, cs)
            pa, ok = translate(d, a)
            rows.append((pa, s, rel, names[i] if i < len(names) else "", comp, status,
                         "+".join(pds) or "-", drv, "" if ok else "untranslated"))
            i += 1
    rows.sort()
    print("start\tsize\tend\tnode\treg_name\tcompatible\tstatus\tpower_domains\tdriver\tnote")
    for pa, s, rel, n, comp, st, pd, drv, note in rows:
        print(f"{pa:#012x}\t{s:#x}\t{pa + s:#012x}\t{rel}\t{n}\t{comp}\t{st}\t{pd}\t{drv}\t{note}")


if __name__ == "__main__":
    main()
