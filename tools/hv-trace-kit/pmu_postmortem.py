#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Read-only post-mortem of the t8103 Sera PMU and AON registers over the m1n1 proxy.

Run it with the M1 sitting in m1n1 proxy mode (before run_guest.py: run_guest
and m1n1.setup both call PMU(u).reset_panic_counter(), which zeroes the
boot error / panic counts at leg_scrpad+2 -- run_guest.py:161, setup.py:31,
hw/pmu.py:28-32). This script deliberately does NOT import m1n1.setup.

    M1N1DEVICE=/dev/ttyACM0 python3 pmu_postmortem.py --m1n1 ~/m1n1 --tag baseline --out RUN/

Use it only against an m1n1 built from the same commit as --m1n1 (it builds
ProxyUtils, which allocates heap and loads the ADT over the proxy). Do not run
it against the installed Asahi stage 1 (v1.6.1) unless you chainloaded a
matching m1n1 first.

The wake block 0x23d004000 words +0x28..0x44 have unknown read semantics and
may be read-to-clear. Read them once, after the reboot, and treat a second
read as possibly disturbed. --no-wake skips them.

Only SPMI EXT_READL commands (hw/spmi.py read_extl) and 32-bit MMIO reads are
issued. Nothing is written to the PMU.
"""

import argparse
import json
import pathlib
import struct
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--m1n1", required=True, type=pathlib.Path, help="m1n1 checkout (same commit as the target)")
ap.add_argument("--tag", default="pm")
ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("."))
ap.add_argument("--no-mmio", action="store_true", help="skip the AON MMIO reads")
ap.add_argument("--no-wake", action="store_true",
                help="skip the wake-block reads (0x23d004000; possibly read-to-clear)")
args = ap.parse_args()

sys.path.insert(0, str(args.m1n1 / "proxyclient"))
from m1n1.proxy import UartInterface, M1N1Proxy          # noqa: E402
from m1n1.proxyutils import ProxyUtils, bootstrap_port   # noqa: E402
from m1n1.hw.spmi import SPMI                            # noqa: E402

iface = UartInterface()
p = M1N1Proxy(iface, debug=False)
bootstrap_port(iface, p)
u = ProxyUtils(p)

res = {"tag": args.tag, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "pmu": {}, "simetra": {}, "mmio": {}}
lines = []


def out(s):
    print(s)
    lines.append(s)


def prop(node, name, default=None):
    """ADT property, normalised: info-* parsed as u32 lists for *pmu* nodes
    (adt.py:318-322); other nodes (e.g. spmi-simetra) may return raw bytes."""
    try:
        v = node.getprop(name, None)
    except Exception:
        v = None
    if v is None:
        return default
    if isinstance(v, (bytes, bytearray)):
        if "name" in name:
            return v.split(b"\0")[0].decode("ascii", "replace")
        if len(v) % 4 == 0:
            return list(struct.unpack(f"<{len(v) // 4}I", v))
    return v


def first(v, default):
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return v[0] if v else default
    return v


def read_block(spmi, slave, reg, size):
    data = b""
    while size > 0:
        n = min(8, size)
        data += spmi.read_extl(slave, reg + len(data), n)
        size -= n
    return data


def fault_names(node):
    names = {}
    for i in range(64):
        n = prop(node, f"info-fault_name-{i}")
        if n:
            names[i] = n
    return names


def decode_bits(raw, names):
    val = int.from_bytes(raw, "little")
    return [f"bit{i}:{names.get(i, '?')}" for i in range(len(raw) * 8) if val >> i & 1]


chip = u.adt["/chosen"].chip_id
out(f"== {args.tag}  chip-id {chip:#x}  {res['time']}")

# ---------------------------------------------------------------- Sera PMU
try:
    node = u.adt["/arm-io/nub-spmi/spmi-pmu"]
    slave = first(getattr(node, "reg", None), 0xf)
    spmi = SPMI(u, "/arm-io/nub-spmi")
    names = fault_names(node)
    regions = {
        "leg_scrpad": (first(prop(node, "info-leg_scrpad"), 0x9f00), 0x10),
        "fault_log": tuple((prop(node, "info-fault_log") or [0xd200, 4])[:2]),
        "fault_shadow(ADT)": tuple((prop(node, "info-fault_shadow") or [0xa47b, 0x10])[:2]),
        "fault_shadow(DT 0xa67b)": (0xa67b, 0x10),
        "rtc_alarm block 0xd000": (0xd000, 0x10),
        "rtc_scrpad/offset": (first(prop(node, "info-rtc_scrpad"), 0xd100), 0x8),
    }
    out(f"Sera PMU slave {slave:#x} on /arm-io/nub-spmi")
    for name, (reg, size) in regions.items():
        try:
            raw = read_block(spmi, slave, reg, size)
            res["pmu"][name] = {"reg": f"{reg:#06x}", "hex": raw.hex()}
            out(f"  {name:<24} @{reg:#06x}[{size:#x}] = {raw.hex(' ')}")
            if name.startswith("fault"):
                bits = decode_bits(raw[:4], names)
                res["pmu"][name]["bits_first_word"] = bits
                out(f"      first word set bits: {', '.join(bits) or 'none'}")
        except Exception as e:
            res["pmu"][name] = {"error": str(e)}
            out(f"  {name:<24} ERROR {e}")
    ls = bytes.fromhex(res["pmu"].get("leg_scrpad", {}).get("hex", "")) or b""
    if len(ls) >= 4:
        out(f"  boot_stage {ls[1]:#04x}  boot_error_count {ls[2] & 0xf}  panic_count {ls[2] >> 4}"
            f"  boot_error_stage {ls[3]:#04x}  shutdown_flag(bit3 of 0x9f0f) {(ls[15] >> 3) & 1 if len(ls) > 15 else '?'}")
    al = bytes.fromhex(res["pmu"].get("rtc_alarm block 0xd000", {}).get("hex", "")) or b""
    if len(al) >= 16:
        out(f"  alarm_ctrl {al[0]:#04x}  pm_setting {al[1]:#04x}  alarm {struct.unpack('<I', al[8:12])[0]:#x}"
            f"  alarm_event {al[12]:#04x}  irq_mask {al[14]:#04x}")
    res["fault_names"] = names
except Exception as e:
    out(f"Sera PMU read failed: {e}")

# ---------------------------------------------------------------- secondary PMIC
try:
    node = u.adt["/arm-io/nub-spmi1/spmi-simetra"]
    slave = first(getattr(node, "reg", None), 0xf)
    spmi1 = SPMI(u, "/arm-io/nub-spmi1")
    fl = tuple((prop(node, "info-fault_log") or [0x1800, 2])[:2])
    raw = read_block(spmi1, slave, fl[0], fl[1])
    res["simetra"]["fault_log"] = raw.hex()
    bits = decode_bits(raw, fault_names(node))
    out(f"Simetra slave {slave:#x} fault_log @{fl[0]:#06x} = {raw.hex(' ')}  bits: {', '.join(bits) or 'none'}")
except Exception as e:
    out(f"Simetra read failed (non-fatal): {e}")

# ---------------------------------------------------------------- AON MMIO
if not args.no_mmio:
    regs = [(0x23d2b0000 + o, f"wdt+{o:#04x}") for o in (0x10, 0x14, 0x1c, 0x20, 0x24, 0x28, 0x2c)]
    regs += [(0x23d2b8008, "wdt-extra 8008"), (0x23d2b800c, "wdt-extra 800c"), (0x23d2b8020, "wdt-extra 8020")]
    if not args.no_wake:
        out("  (nub-wake words below may be read-to-clear: first read after the reboot is the evidence)")
        regs += [(0x23d004000 + o, f"nub-wake+{o:#04x}") for o in range(0, 0x50, 4)]
    for addr, name in regs:
        try:
            v = p.read32(addr)
            res["mmio"][f"{addr:#x}"] = f"{v:#010x}"
            out(f"  {addr:#x} {name:<16} = {v:#010x}")
        except Exception as e:
            out(f"  {addr:#x} {name:<16} ERROR {e}")

args.out.mkdir(parents=True, exist_ok=True)
stem = args.out / f"postmortem-{args.tag}-{time.strftime('%H%M%S')}"
stem.with_suffix(".json").write_text(json.dumps(res, indent=1))
stem.with_suffix(".txt").write_text("\n".join(lines) + "\n")
print(f"saved {stem}.json and .txt")
