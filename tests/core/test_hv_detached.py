"""Detached mode's host tools (tools/hv-trace-kit/harness/detach.py, detach_readout.py,
detached_fmt.py) without a Mac: the control block's layout, the tables built from a fake
hypervisor object, and the log's way back to JSON lines.

What this cannot show: anything the hypervisor does with the tables (src/hv/hv_detached.c runs
only on the M1).
"""
from __future__ import annotations

import enum
import io
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2] / "tools/hv-trace-kit/harness"
sys.path.insert(0, str(HARNESS))
import detached_fmt as F  # noqa: E402
import detach_readout as readout  # noqa: E402


def _fake_m1n1():
    """Stand-ins for the two m1n1 modules detach.py imports (same names, same encodings)."""
    class TraceMode(enum.IntEnum):
        OFF, BYPASS, ASYNC, UNBUF, WSYNC, SYNC, HOOK, RESERVED = range(8)

    hv_mod = types.ModuleType("m1n1.hv")
    hv_mod.TraceMode = TraceMode
    sr = types.ModuleType("m1n1.sysreg")
    sr.VMSA_LOCK_EL1 = (3, 4, 15, 1, 2)
    sr.ACC_CFG_EL1 = (3, 5, 15, 4, 0)
    sr.ACC_OVRD_EL1 = (3, 5, 15, 6, 0)
    sr.DC_CIVAC = (1, 3, 7, 14, 1)
    sr.DBGBVRn_EL1 = lambda n: (2, 0, 0, n, 4)
    sr.DBGBCRn_EL1 = lambda n: (2, 0, 0, n, 5)
    sr.DBGWVRn_EL1 = lambda n: (2, 0, 0, n, 6)
    sr.DBGWCRn_EL1 = lambda n: (2, 0, 0, n, 7)
    sr.sysreg_parse = tuple
    pkg = types.ModuleType("m1n1")
    pkg.hv, pkg.sysreg = hv_mod, sr
    sys.modules.update({"m1n1": pkg, "m1n1.hv": hv_mod, "m1n1.sysreg": sr})
    return TraceMode


def _load_detach(hv):
    ns = {"hv": hv, "p": None, "u": None, "iface": None, "__file__": str(HARNESS / "detach.py"),
          "__name__": "<hv_script>"}
    exec(compile((HARNESS / "detach.py").read_text(), str(HARNESS / "detach.py"), "exec"), ns)
    return ns


class Reg:
    def __init__(self, write_mask, override_mask=0, override=0, value=None):
        self.write_mask, self.override_mask, self.override, self.value = write_mask, override_mask, override, value


class Node:
    def __init__(self, reg, cpu_id, impl):
        self.reg, self.cpu_id, self.cpu_impl_reg = reg, cpu_id, (impl, 0x1000)


def _fake_hv(TraceMode, extra_hook=False, hook_tracer=False):
    """vm_hooks as HV.map_essential leaves them: closures with the same free variables."""
    hv = types.SimpleNamespace()
    _pmgr = {0x23b7001c0: 0x1f0000ff}                # only one word read so far
    pg_overrides = {0x23d29c05c: 0xc000000, 0x23d29c044: 0xc000000}

    def wh(base, off, data, width):
        _pmgr[base + off] = data

    def rh(base, off, width):
        return _pmgr.setdefault(base + off, 0)

    def cpustart_wh(base, off, data, width):
        pass

    hv.vm_hooks = [None, (rh, wh, 0x23b7001c0, {}), (rh, wh, 0x23b700420, {})]
    for addr in pg_overrides:
        hv.vm_hooks.append((lambda base, off, width: pg_overrides[base + off], None, addr, {}))
    hv.vm_hooks.append((None, cpustart_wh, 0x23b754000, {}))
    if extra_hook:
        hv.vm_hooks.append((None, lambda base, off, data, width: None, 0x210000000, {}))
    hv._pmgr_hooked = [0x23b7001c0, 0x23b700420]
    hv._pmgr_requested = {0x23b700420: 0x20ff}
    hv.adt = {"cpus": [Node(0, 0, 0x210050000), Node(0x103, 7, 0x211350000)]}
    hv.entry, hv.s2r_guest_reset_pc, hv.s2r_resume_flags = 0x818e08800, 0x818e08000, 1
    hv._bps, hv._wps = [None] * 5, [None] * 4
    hv.MSR_REDIRECTS = {(3, 0, 1, 0, 0): (3, 5, 1, 0, 0)}
    hv.sysreg = {0: {(3, 4, 15, 2, 2): 1, (3, 4, 15, 2, 5): 0x12}, 7: {}}
    hv.xnu_amcc = types.SimpleNamespace(registers={
        0x200000680: Reg(0xffffffff, 0xffffffff, 0x1234, None),
        0x20000068c: Reg(1, 1, 0, 0)})
    maps = {"HW": (TraceMode.OFF, "HW", None, None, {}),
            "XNU AMCC": (TraceMode.HOOK, "XNU AMCC", print, print, {})}
    zones = [(range(0x200000680, 0x200000684), maps)]
    if hook_tracer:
        zones.append((range(0x23d000000, 0x23d000004),
                      {"X": (TraceMode.HOOK, "S2R", print, print, {})}))
    hv.mmio_maps = types.SimpleNamespace(items=lambda: zones)
    return hv


def test_layout_matches_the_build():
    elf = Path(F.DEFAULT_ELF)
    if not elf.exists() or not shutil.which("pahole"):
        return                                      # no build on this machine: nothing to compare
    out = subprocess.run(["pahole", "-C", "hv_detached_ctl", str(elf)], capture_output=True, text=True).stdout
    offs = {m.group(1): (int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"^\t(?:u64\s+|\} )(\w+)(?:\[[\d\]\[]+)?;\s*/\*\s*(\d+)\s+(\d+)", out, re.M)}
    assert offs, "pahole printed no members"
    for name, (word, per, n) in F.OFFSET.items():
        assert offs[name] == (word * 8, per * n * 8), name
    assert F.symbols(str(elf), ("hv_detached_ctl",))["hv_detached_ctl"][1] == F.SIZE
    assert F.image_bytes(str(elf), F.symbols(str(elf), ("hv_detached_info",))["hv_detached_info"][0], 16) == \
        F.ENTRY.pack(F.MAGIC, F.SIZE, 0, 0)[:16]


def test_tables_come_from_the_live_state():
    TraceMode = _fake_m1n1()
    hv = _fake_hv(TraceMode)
    c, problems, notes = _load_detach(hv)["build"](hv, None, [(0x900000000, 1000)], [0x23b700000, 0x23d280088])
    assert problems == [] and notes == []
    c = F.Ctl.unpack(c.pack())                       # what the M1 receives
    assert (c.get("magic"), c.get("size")) == (F.MAGIC, F.SIZE)
    assert c.get("nseg") == 1 and c.get("seg", 0) == (0x900000000, 1000)
    # read once -> cached value, valid; never read -> not valid; the guest's last request kept
    assert c.get("npmgr") == 2
    assert c.get("pmgr", 0) == (0x23b7001c0, 0x1f0000ff, 1, 0, 0)
    assert c.get("pmgr", 1) == (0x23b700420, 0, 0, 0x20ff, 1)
    assert c.get("nconst") == 2 and c.get("konst", 0) == (0x23d29c044, 0xc000000)
    assert (c.get("cpustart_base"), c.get("cpustart_size")) == (0x23b754000, 0x20)
    assert c.get("ncpu") == 2 and c.get("cpu", 1) == (0x103, 7, 0x211350000)
    assert (c.get("entry_page"), c.get("guest_reset_pc"), c.get("resume_flags")) == (0x818e08000, 0x818e08000, 1)
    # lock words: a word never read is fetched by the hypervisor on first use
    assert c.get("namcc") == 2
    assert c.get("amcc", 0) == (0x200000680, 0xffffffff, 0xffffffff, 0x1234, 0, 0)
    assert c.get("amcc", 1) == (0x20000068c, 1, 1, 0, 0, 1)
    # system registers: 1 lock + 4 CTRR + 10 breakpoint + 8 watchpoint shadows, per-CPU values
    encs = [c.get("shadow_enc", i) for i in range(c.get("nshadow"))]
    assert len(encs) == 23 and F.sysreg_enc(3, 4, 15, 2, 2) in encs
    row0 = c.get("shadow", 0)
    assert row0[encs.index(F.sysreg_enc(3, 4, 15, 2, 2))] == 1
    assert row0[encs.index(F.sysreg_enc(3, 4, 15, 2, 5))] == 0x12
    assert not any(c.get("shadow", 7))
    rules = {c.get("sysreg", i)[0]: c.get("sysreg", i)[1:] for i in range(c.get("nsysreg"))}
    assert rules[F.sysreg_enc(3, 5, 15, 4, 0)] == (F.SR_RO, F.sysreg_enc(3, 5, 15, 4, 0))
    assert rules[F.sysreg_enc(1, 3, 7, 14, 1)][0] == F.SR_XLATE
    assert rules[F.sysreg_enc(3, 0, 1, 0, 0)] == (F.SR_PASS, F.sysreg_enc(3, 5, 1, 0, 0))
    assert c.get("nsnap") == 2 and c.get("snap", 1) == 0x23d280088


def test_what_the_hypervisor_cannot_serve_is_named():
    TraceMode = _fake_m1n1()
    hv = _fake_hv(TraceMode, extra_hook=True, hook_tracer=True)
    _c, problems, _notes = _load_detach(hv)["build"](hv, None, [(0x900000000, 10)])
    assert len(problems) == 2
    assert "vm hook 6 at 0x210000000" in problems[0] and "HOOK tracer S2R" in problems[1]
    hv = _fake_hv(TraceMode)
    hv.s2r_guest_reset_pc = None
    c, problems, notes = _load_detach(hv)["build"](hv, None, [(0x900000000, 10)])
    assert problems == [] and c.get("guest_reset_pc") == 0 and "0x818e08000" in notes[0]


def _log(segs_cap, entries):
    """A control block and memory holding `entries` offered to segments of the given sizes."""
    c, mem = F.Ctl(), {}
    c.set("magic", F.MAGIC)
    bases = [0x900000000 + 0x10000000 * i for i in range(len(segs_cap))]
    c.set_table("nseg", "seg", list(zip(bases, segs_cap)))
    c.set("log_cap", sum(segs_cap))
    c.set("log_total", len(entries))
    c.set("cntfrq", 24000000)
    c.set("t_detach", 1000)
    flat = [(b, i) for b, cap in zip(bases, segs_cap) for i in range(cap)]
    for (b, i), raw in zip(flat, entries):
        mem[b + i * F.ENTRY.size] = raw

    def readmem(addr, size):
        return b"".join(mem[a] for a in range(addr, addr + size, F.ENTRY.size))

    return c, readmem


def test_log_becomes_touch_map_records():
    pc = 0xfffffe0007a1b2c4
    entries = [
        F.make_entry(1000, 100, 24000000, 0, F.K_DETACH),
        F.make_entry(1000 + 24000000, 0x23bc34000, 1, pc, F.K_ACC, cpu=3, write=True, width=2),
        F.make_entry(1000 + 36000000, 0x200100000, 0xdeadbeefcafe, 0x8000, F.K_ACC, cpu=7, width=3),
        F.make_entry(1000 + 48000000, 0x23b7001c0, (0x1f0000ff << 32) | 0xf0000ff, pc, F.K_PMGR, write=True, width=2),
        F.make_entry(1000 + 48000001, 8, 8, 0, F.K_LAST_DOWN),
        F.make_entry(1000 + 60000000, 0, 0x400000, 0, F.K_WAKE),
        F.make_entry(1000 + 60000001, 0x23b700000, 0x3ff, 0, F.K_SNAP),
        F.make_entry(1000 + 60000002, 0x23d280088, 0, 0, F.K_SNAP, write=True),
        F.make_entry(1000 + 60000003, 0x818e08000, 1, 0, F.K_RESUME),
        F.make_entry(1000 + 60000004, (1 << 32) | F.sysreg_enc(3, 4, 15, 2, 2), 1, pc, F.K_SYSREG, write=True),
        F.make_entry(1000 + 60000005, 7, 0x818e08000, 0, F.K_SECONDARY),
        F.make_entry(1000 + 72000000, 0, 2, 0, F.K_HOST),
        F.make_entry(1000 + 72000001, 0, 0, 0, F.K_ACC),     # offered after the log was full
    ]
    c, readmem = _log([5, 7], entries)                # two segments, 12 slots, 13 offered
    raw = readout.read_log(readmem, c)
    assert len(raw) == 12 * F.ENTRY.size
    head = readout.header(c, (3, 3), 12)
    assert (head["entries"], head["offered"], head["dropped"]) == (12, 13, 1)
    assert head["entered_proxy_as"] == "HV/USER_INTERRUPT" and head["stop"] is None
    out = io.StringIO()
    n, first, last, mono = readout.write_jsonl(out, head, raw, c, {0x23b700000: "PMGR PS:x"})
    recs = [json.loads(line) for line in out.getvalue().splitlines()]
    assert recs[0]["ev"] == "readout" and n == len(recs) - 1 and mono and (first, last) == (0.0, 3.0)
    # an access: the touch map's keys, in its order, time from the detach marker
    assert list(recs[2]) == ["addr", "w", "data", "width", "pc", "cpu", "ev", "t"]
    assert recs[2] == {"addr": "0x23bc34000", "w": True, "data": "0x1", "width": 2,
                       "pc": "0xfffffe0007a1b2c4", "cpu": 3, "ev": "acc", "t": 1.0}
    assert recs[3]["pc"] == "0x8000" and recs[3]["width"] == 3 and recs[3]["t"] == 1.5
    evs = [r["ev"] for r in recs[1:]]
    assert evs == ["detached", "acc", "acc", "pmgr", "last-core-down", "wake", "snap", "resume",
                   "sysreg", "secondary", "host"]
    assert recs[4]["data"] == "0xf0000ff" and recs[4]["hw"] == "0x1f0000ff"
    assert recs[6]["status_20"] == "0x400000"
    snap = recs[7]
    assert snap["words"] == 2 and snap["errors"] == 1
    assert snap["regs"] == {"0x23b700000 PMGR PS:x": "0x3ff", "0x23d280088": "ERR"}
    assert recs[9]["reg"] == "s3_4_c15_c2_2" and recs[9]["how"] == "shadow" and recs[9]["w"]
    assert recs[10] == {"ev": "secondary", "cpu": 7, "entry": "0x818e08000", "by": 0, "t": recs[10]["t"]}


def test_a_stop_is_reported_with_what_it_was():
    c, _readmem = _log([4], [F.make_entry(1000, 4, 24000000, 0, F.K_DETACH)])
    c.set("flags", F.FLAG_STOPPED)
    c.set("state", 3)
    c.set("stop", (2, 0, 0x62000000, 0xfffffe0007000000, 0x10, 0x3c5, 4, 0))
    head = readout.header(c, (2, 0), 1)
    assert head["stopped_unhandled"] and head["entered_proxy_as"] == "EXCEPTION_LOWER/SYNC"
    assert head["stop"]["what"] == "EXCEPTION_LOWER/SYNC" and head["stop"]["esr"] == "0x62000000"
    assert head["stop"]["cpu"] == 4
    recs = list(F.records([F.decode_entry(F.make_entry(1000, 0x10, 0x62000000, 0xfffffe0007000000, F.K_UNHANDLED, cpu=4)),
                           F.decode_entry(F.make_entry(1000, (3 << 32) | 1, 0x3c5, 0, F.K_UNHANDLED2)),
                           F.decode_entry(F.make_entry(1000, 0x23b700300, 5, 2, F.K_UNHANDLED_HOOK, write=True, width=2))],
                          1000, 24000000))
    assert recs[0]["ev"] == "unhandled" and recs[0]["pc"] == "0xfffffe0007000000" and recs[0]["far"] == "0x10"
    assert recs[1]["what"] == "HV/HOOK_VM"
    assert recs[2]["addr"] == "0x23b700300" and recs[2]["w"] and recs[2]["hook_id"] == 2


def test_commit_snapshot_and_the_way_down():
    pc = 0xfffffe0007a1b2c4
    cyc = F.sysreg_enc(3, 5, 15, 5, 0)
    entries = [F.decode_entry(r) for r in (
        F.make_entry(1000, 100, 24000000, 0, F.K_DETACH),
        F.make_entry(2000, (3 << 32) | F.sysreg_enc(3, 5, 15, 6, 0), 0x7, pc, F.K_SYSREG, cpu=4, write=True),
        F.make_entry(2100, (5 << 32) | cyc, 0x2000001, pc, F.K_SYSREG, cpu=0, write=True),
        F.make_entry(2200, 8, 8, 0, F.K_LAST_DOWN),
        F.make_entry(2300, 0x23b700000, 0xf, 0, F.K_CSNAP),
        F.make_entry(2400, 0x23d280088, 0, 0, F.K_CSNAP, write=True),
        F.make_entry(2500, 0x23b7001c0, 0xf0000ff, 0, F.K_COMMIT_WRITE, write=True, width=2),
        F.make_entry(9000, 0x23b700000, 0x3ff, 0, F.K_SNAP),
    )]
    recs = list(F.records(entries, 1000, 24000000, {0x23b700000: "x"}))
    assert [r["ev"] for r in recs] == ["detached", "sysreg", "sysreg", "last-core-down", "snap",
                                       "commit-write", "snap"]
    assert recs[1]["how"] == "c" and recs[1]["reg"] == "s3_5_c15_c6_0" and recs[1]["cpu"] == 4
    assert recs[2]["how"] == "s2r" and recs[2]["data"] == "0x2000001" and recs[2]["w"]
    assert recs[4]["tag"] == "commit" and recs[4]["regs"] == {"0x23b700000 x": "0xf", "0x23d280088": "ERR"}
    assert recs[4]["words"] == 2 and recs[4]["errors"] == 1 and recs[4]["t_end"] > recs[4]["t"]
    assert recs[5] == {"ev": "commit-write", "addr": "0x23b7001c0", "data": "0xf0000ff", "cpu": 0, "t": recs[5]["t"]}
    assert recs[6]["tag"] == "wake" and "_kind" not in recs[6]


def test_first_layout_still_decodes_and_the_list_reaches_the_block():
    c = F.Ctl()
    c.set("magic", F.MAGIC_V1)
    c.set("size", F.SIZE_V1)
    c.set("log_cap", 7)
    old = F.Ctl.unpack(c.pack()[:F.SIZE_V1])         # a control block saved by the first build
    assert old.get("log_cap") == 7 and old.get("ncsnap") == 0
    TraceMode = _fake_m1n1()
    hv = _fake_hv(TraceMode)
    c, problems, _n = _load_detach(hv)["build"](hv, None, [(0x900000000, 10)], (), [0x200000000, 0x23b700000], 50, True)
    assert problems == [] and c.get("ncsnap") == 2 and c.get("csnap", 1) == 0x23b700000
    assert c.get("csnap_delay_us") == 50 and c.get("flags") == F.FLAG_SR_ALL


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("ok", _name)
