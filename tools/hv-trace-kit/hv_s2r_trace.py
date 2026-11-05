# SPDX-License-Identifier: MIT
#
# m1n1 hypervisor module: trace macOS's suspend-to-RAM ENTRY on t8103 (M1, J313).
#
# Load it with run_guest.py:
#   python3 $M1N1/proxyclient/tools/run_guest.py -l $RUN/hv.log \
#       -m $KIT/hv_s2r_trace.py $KC -- "<boot args>"
#
# It runs inside run_guest's namespace (HV.run_script -> runpy.run_path with the
# shell locals: hv, p, u, iface, TraceMode, ...; proxyclient/m1n1/hv/__init__.py:2306-2309).
# Every function it defines becomes a hypervisor-shell command.
#
# Design ("go mode", after aura PR #70's measured lesson that trapping whole
# blocks synchronously slowed XNU's quiesce past a ~5 s watchdog):
#   * No Python round trip on the sleep path. All sleep-path zones use
#     TraceMode.ASYNC or TraceMode.UNBUF: m1n1's C code emulates the access and
#     queues an event (src/hv/hv_vm.c:860-883, 996-1001). UNBUF flushes the USB
#     link before the write is performed (emit before hv_pa_write, hv_vm.c:1000-1012),
#     so the write that cuts power is already on the host.
#   * Writes only, except the SPMI REPLY and mailbox OUTBOX registers needed for
#     decoding. Status polling is not logged.
#   * Heavy blocks (PMGR power states, clock generator, cluster blocks) are added
#     only when you arm, right before triggering sleep.
#   * Nothing is changed: every traced write lands as the guest issued it.
#     Optional stop mode (S2R_STOP=1) holds ONE configured write in a shell.
#
# What m1n1 already does on this path (not changed here):
#   * CPU_START block 0x23b754000+0x20 is a RESERVED hook that logs
#     "CPUSTART W ..." and swallows the write (hv/__init__.py:1606-1631).
#   * ACC_OVRD writes are skipped and logged ("Skip: msr ACC_OVRD_EL1 ...",
#     python ro set, hv/__init__.py:716-719, 750-758).
#   * CYC_OVRD writes are split (src/hv/hv_exc.c:360-366):
#       - a value WITHOUT DISABLE_WFI_RET (bit 0) and WITHOUT FIQ_MODE (bits 21:20)
#         is written to the hardware in C and never reaches Python, so it is NOT
#         logged (this covers IRQ_MODE-only and WFI_MODE values);
#       - a value WITH bit 0 or FIQ_MODE goes to Python, is logged as
#         "Skip: msr CYC_OVRD_EL1, xN = ..." and is NOT written; with bit 0 the
#         CPU leaves the guest ("Guest is shutting down CPU", hv/__init__.py:731-738).
#     The exit-cpu hook below reads CYC_OVRD back from the hardware, which gives
#     the last value that did land (the unlogged C-path writes included).
#   So the deep-WFI CYC_OVRD modes do reach the hardware, but the core never
#   executes the sleep WFI with bit 0 set, and the guest cannot complete a real
#   S2R; this kit captures the AP-side entry program, not a wake.

import json
import os
import pathlib
import sys
import time

_KIT = pathlib.Path(__file__).resolve().parent
if str(_KIT) not in sys.path:
    sys.path.insert(0, str(_KIT))

import s2r_decode as _D                      # noqa: E402
from m1n1.hv import TraceMode               # noqa: E402  (hv/types.py:50-61)
from m1n1.utils import irange               # noqa: E402  (utils.py:979)


def _env_int(name, default):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return int(v, 0)


def _env_zones(name, default):
    v = os.environ.get(name)
    if not v:
        return default
    out = []
    for part in v.split(","):
        a, s = part.split(":")
        out.append((int(a, 0), int(s, 0)))
    return out


CYC_OVRD_ENC = (3, 5, 15, 5, 0)   # CYC_OVRD_EL1, src/cpu_regs.h:533

S2R_IDENT_ALWAYS = "S2R"
S2R_IDENT_ARMED = "S2R-ARM"

CFG = {
    "log": os.environ.get("S2R_LOG") or f"s2r-trace-{time.strftime('%Y%m%d-%H%M%S')}.jsonl",
    "arm_at_start": _env_int("S2R_ARM_AT_START", 0),
    "console": _env_int("S2R_CONSOLE", 1),     # 0 quiet, 1 decoded/AON/SoC-level, 2 everything
    "pmgr": _env_int("S2R_PMGR", 1),           # PMGR power-state block (reg[0])
    "clkgen": _env_int("S2R_CLKGEN", 1),       # clock generator (reg[2])
    "cluster": _env_int("S2R_CLUSTER", 0),     # E/P cluster blocks: run-2 option (see CPM_SERROR)
    "aic": _env_int("S2R_AIC", 0),             # AIC writes: very noisy, off by default
    "stop": _env_int("S2R_STOP", 0),           # hold the first write to a stop zone
    # Only the candidate words, not the 16 KiB page: every READ inside a HOOK
    # zone becomes a synchronous proxy round trip (hv/__init__.py:552-574).
    "stop_zones": _env_zones("S2R_STOP_ZONES", [(0x23d2d4000, 0x10)]),
    # Wake-block reads are off in the guest: the +0x28..0x44 words may be
    # read-to-clear. pmu_postmortem.py reads them after the reboot instead.
    "snap_wake": _env_int("S2R_SNAP_WAKE", 0),
    "cyc_read": _env_int("S2R_CYC_READ", 1),   # read CYC_OVRD_EL1 back in the exit-cpu hook
}

# Fallback addresses (t8103) used only if the live ADT lacks a node.
FALLBACK = {
    "smc": 0x23e400000,       # t8103.dtsi:1301-1305
    "pmp": 0x23bc00000,       # PMP mailbox 0x23bc08000 = base + 0x8000
}

# Expected /arm-io/pmgr reg[] on t8103 (J313 ADT, fabric/adt.pkl). A zone is
# armed only if the live ADT entry matches exactly; a missing entry falls back
# to this table, a different one is refused with a warning.
T8103_PMGR_REG = {
    0: (0x23b700000, 0x8c000),    # PMGR power states
    1: (0x23d280000, 0x74000),    # AON PMGR (WDT, S2R-timer candidate)
    2: (0x23b000000, 0x70000),    # clock generator
    3: (0x23d200000, 0x80000),
    4: (0x23d004000, 0x1000),     # wake block
    5: (0x210e20000, 0x2000),     # E cluster
    7: (0x210e40000, 0x9000),     # E cluster cpm-impl-reg
    9: (0x210e70000, 0x1000),
    14: (0x211e20000, 0x2000),    # P cluster
    16: (0x211e40000, 0xb000),    # P cluster cpm-impl-reg
    18: (0x211e70000, 0x1000),
}
T8103_SPMI_REG = {
    "nub-spmi": {0: (0x23d0d9300, 0x100), 1: (0x23d0d8e00, 0x100), 2: (0x23d0d8400, 0x78)},
}
MAX_ZONE = 0x100000               # hard guard: never trace anything larger

# cpm-impl-reg offsets that raise an SError when touched
# (src/hv/hv_cpu_power.c:20-29: 0x8000, 0x8008, 0x40f8, and 12 slots at
# 0x4008 + n*0x10 that probably raise delayed SErrors). A traced access is
# emulated from EL2, so such an SError would land in m1n1, not in the guest.
# Sub-page carve-outs do not help (a TraceMode.OFF range that is not 16 KiB
# aligned is still software-mapped, hv/__init__.py:212-234), so the whole
# 16 KiB page holding any of these words is never traced.
CPM_BASES = (0x210e40000, 0x211e40000)
CPM_SERROR = (0x8000, 0x8008, 0x40f8) + tuple(0x4008 + n * 0x10 for n in range(12))
PAGE = 0x4000
FORBIDDEN_PAGES = sorted({(b + o) & ~(PAGE - 1) for b in CPM_BASES for o in CPM_SERROR})


class S2RTrace:
    def __init__(self, hv):
        self.hv = hv
        self.t0 = time.time()
        self.seq = 0
        path = pathlib.Path(CFG["log"])
        self.path = path.resolve()
        self.f = open(path, "a", buffering=1)
        self.armed = False
        self.armed_zones = []
        self.stopped_once = False
        self.drop_next = False
        self.spmi = {}
        self.mbox = {}
        self.ps_names = {}
        self.zone_names = []
        self.refused = []
        self._build_ps_names()
        self.rec("note", text=f"hv_s2r_trace loaded; cfg={CFG}")
        print(f"[s2r] logging to {self.path}")

    # ------------------------------------------------------------------ output
    def rec(self, ev, **kw):
        self.seq += 1
        r = {"seq": self.seq, "t": round(time.time() - self.t0, 6), "ev": ev}
        r.update(kw)
        try:
            self.f.write(json.dumps(r, default=str) + "\n")
        except Exception as e:  # never let logging break the guest
            print(f"[s2r] log write failed: {e}")
        return r

    def say(self, level, s):
        if CFG["console"] >= level:
            print(f"[s2r] {s}")

    # ------------------------------------------------------------- ADT helpers
    def _adt_reg(self, path, idx):
        try:
            return self.hv.adt[path].get_reg(idx)
        except Exception:
            return None

    def _refuse(self, name, why):
        self.refused.append((name, why))
        self.rec("zone-refused", text=f"{name}: {why}", zone=name)
        print(f"[s2r] WARNING: zone {name} NOT armed: {why}")

    def _checked_reg(self, path, idx, expected, name):
        """ADT reg[idx], or None (with a warning) if it differs from the t8103 table."""
        live = self._adt_reg(path, idx)
        if live is None:
            if expected is None:
                return None
            self.rec("note", text=f"{name}: {path} reg[{idx}] missing in ADT, using t8103 table")
            return expected
        live = (int(live[0]), int(live[1]))
        if expected is not None and live != tuple(expected):
            self._refuse(name, f"{path} reg[{idx}] = {live[0]:#x}+{live[1]:#x}, "
                               f"expected {expected[0]:#x}+{expected[1]:#x} (ADT differs from t8103 table)")
            return None
        return live

    @staticmethod
    def _forbidden(start, size):
        return [pg for pg in FORBIDDEN_PAGES if pg < start + size and start < pg + PAGE]

    def _build_ps_names(self):
        # Same walk as proxyclient/hv/trace_pmgr.py:134-147.
        try:
            pmgr = self.hv.adt["/arm-io/pmgr"]
            for dev in pmgr.devices:
                ps = pmgr.ps_regs[dev.psreg]
                if dev.psidx or dev.psreg:
                    addr = pmgr.get_reg(ps.reg)[0] + ps.offset + dev.psidx * 8
                    self.ps_names[addr] = dev.name
        except Exception as e:
            print(f"[s2r] could not build PMGR device names: {e}")

    # ---------------------------------------------------------------- handlers
    def _mmio(self, evt, region=None, kind=None, base=None):
        try:
            self._mmio_inner(evt, region, kind, base)
        except Exception as e:
            print(f"[s2r] handler error at {evt.addr:#x}: {e}")

    def _mmio_inner(self, evt, region, kind, base):
        write = bool(evt.flags.WRITE)
        nbytes = 1 << evt.flags.WIDTH
        addr = evt.addr
        data = evt.data
        rname, _ = _D.region_of(addr)
        ps = self.ps_names.get(addr & ~0x7)
        r = self.rec("mmio", cpu=evt.flags.CPU, pc=f"{evt.pc:#x}", addr=f"{addr:#x}",
                     w=write, width=nbytes, data=f"{data:#x}", region=rname, zone=region,
                     ps=ps, multi=bool(evt.flags.MULTI))
        if kind == "spmi":
            self._spmi(evt, base, region, write, data)
            return
        if kind in ("smc", "pmp"):
            self._mbox(evt, base, region, kind, write, data)
            return
        if kind == "sram":
            m = self.mbox.get("smc")
            if m is not None and write:
                m.note_sram_write(addr, data, nbytes)
            return
        lvl = 2 if (ps is not None or region in ("pmgr", "clkgen", "aic")
                    or str(region).startswith("cluster")) else 1
        self.say(lvl, f"cpu{evt.flags.CPU} {'W' if write else 'R'}{nbytes * 8} {addr:#x} = {data:#x}"
                      f" [{ps or rname}] pc {evt.pc:#x}")

    def _spmi(self, evt, base, bus, write, data):
        # Sera labels only on nub-spmi; Simetra (nub-spmi1) is also slave 0xf
        dec = self.spmi.setdefault(bus, _D.SPMIDecoder(bus, label_pmu=(bus == "nub-spmi")))
        off = evt.addr - base
        out = []
        if write and off == 0x4:
            out = dec.feed_cmd(data, cpu=evt.flags.CPU, pc=f"{evt.pc:#x}")
        elif (not write) and off == 0x8:
            out = dec.feed_reply(data)
        elif write:
            self.say(1, f"{bus} W {evt.addr:#x} (+{off:#x}) = {data:#x}")
        for o in out:
            o["t"] = round(time.time() - self.t0, 6)
            self.rec(o.pop("ev"), **o)
            hot = o.get("label") or o.get("op") in ("SLEEP", "SHUTDOWN", "WAKEUP", "RESET")
            if o.get("kind") == 'r' or "reply_word" in o:
                self.say(2 if not hot else 1, o["text"])
            else:
                self.say(1, o["text"])

    def _mbox(self, evt, base, name, kind, write, data):
        dec = self.mbox.setdefault(kind, _D.MboxDecoder(name, kind))
        o = dec.feed(evt.addr - base, data, write)
        if o:
            self.rec(o.pop("ev"), **o)
            mgmt_hot = "mgmt" in o and o.get("mgmt") in ("SET_AP_POWER", "SET_IOP_POWER", "IOP_POWER_ACK")
            smc_hot = o.get("smc") in ("WRITE_KEY", "RW_KEY") or "sram_addr" in o
            self.say(1 if (mgmt_hot or smc_hot or kind == "pmp") else 2, o["text"])
            if "sram_addr" in o and self.armed:
                self._add_sram_zone()

    # ------------------------------------------------------------------ zones
    def _add(self, ident, start, size, mode, name, kind=None, read=False, write=True, base=None):
        if size <= 0 or size > MAX_ZONE:
            self._refuse(name, f"size {size:#x} at {start:#x} is outside 1..{MAX_ZONE:#x}")
            return False
        bad = self._forbidden(start, size)
        if bad:
            self._refuse(name, f"{start:#x}+{size:#x} overlaps cpm SError page(s) "
                               + ", ".join(f"{b:#x}" for b in bad))
            return False
        zone = irange(start, size)
        rd = (lambda evt, **kw: self._mmio(evt, **kw)) if read else None
        wr = (lambda evt, **kw: self._mmio(evt, **kw)) if write else None
        self.hv.add_tracer(zone, ident, mode, rd, wr, region=name, kind=kind, base=base)
        self.zone_names.append((ident, start, size, mode.name, name))
        if ident == S2R_IDENT_ARMED:
            self.armed_zones.append(zone)
        return True

    def _asc_base(self, node, fallback):
        r = self._adt_reg(f"/arm-io/{node}", 0)
        return r[0] if r else fallback

    def add_always(self):
        """Mailboxes only: cheap, needed from boot to learn the SMC SRAM address."""
        for kind, node in (("smc", "smc"), ("pmp", "pmp")):
            b = self._asc_base(node, FALLBACK[kind])
            self._add(S2R_IDENT_ALWAYS, b + 0x8800, 0x10, TraceMode.ASYNC, f"{kind}-mbox",
                      kind=kind, write=True, read=False, base=b)
            self._add(S2R_IDENT_ALWAYS, b + 0x8830, 0x10, TraceMode.ASYNC, f"{kind}-mbox",
                      kind=kind, write=False, read=True, base=b)
            self.rec("note", text=f"{kind} mailbox traced at {b + 0x8800:#x}/{b + 0x8830:#x}")

    def _add_sram_zone(self):
        m = self.mbox.get("smc")
        if m is None or m.sram_addr is None:
            self.say(1, "SMC SRAM address not seen yet; SMC key values will not be captured")
            return
        page = m.sram_addr & ~0x3fff
        self._add(S2R_IDENT_ARMED, page, 0x8000, TraceMode.ASYNC, "smc-sram", kind="sram",
                  write=True, read=False)

    def arm(self, note=""):
        if self.armed:
            print("[s2r] already armed")
            return
        self.refused = []
        A = S2R_IDENT_ARMED
        U, AS = TraceMode.UNBUF, TraceMode.ASYNC
        pm = "/arm-io/pmgr"
        # Order matters: a later _add with the same ident replaces an earlier one
        # on the overlapping sub-range (DictRangeMap, utils.py:730-737).
        E = T8103_PMGR_REG
        if CFG["pmgr"]:
            r0 = self._checked_reg(pm, 0, E[0], "pmgr")
            if r0:
                self._add(A, r0[0], r0[1], AS, "pmgr")
                # UNBUF sub-pages: only inside a validated reg[0]
                for start, name in ((0x23b71c000, "pmgr-pwrgate"), (0x23b768000, "pmgr-cllt?"),
                                    (0x23b780000, "pmgr-cluster-ctl?")):
                    self._add(A, start, 0x4000, U, name)
        if CFG["clkgen"]:
            r2 = self._checked_reg(pm, 2, E[2], "clkgen")
            if r2:
                self._add(A, r2[0], r2[1], AS, "clkgen")
                self._add(A, 0x23b040000, 0x4000, U, "clkgen-mux?")
        r3 = self._checked_reg(pm, 3, E[3], "pmgr-reg3")
        if r3:
            self._add(A, r3[0], r3[1], AS, "pmgr-reg3")
        r1 = self._checked_reg(pm, 1, E[1], "aon-pmgr")
        if r1:
            self._add(A, r1[0], r1[1], U, "aon-pmgr")       # includes WDT 0x23d2b0000/0x23d2b8000
        r4 = self._checked_reg(pm, 4, E[4], "nub-wake")
        if r4:
            self._add(A, r4[0], r4[1], U, "nub-wake")
        if CFG["cluster"]:
            for idx in (5, 7, 9, 14, 16, 18):
                r = self._checked_reg(pm, idx, E[idx], f"cluster[{idx}]")
                if not r:
                    continue
                start, size = r
                if start in CPM_BASES:
                    # cpm-impl-reg: trace only the pages free of SError words
                    size = min(size, PAGE)
                    self.rec("note", text=f"cluster[{idx}] cpm block {start:#x}: tracing only "
                                          f"+0..{size:#x}; SError pages left untraced")
                self._add(A, start, size, AS, f"cluster[{idx}]")
        for bus in ("nub-spmi", "nub-spmi1"):
            for idx in (0, 1, 2):
                exp = T8103_SPMI_REG.get(bus, {}).get(idx)
                r = self._checked_reg(f"/arm-io/{bus}", idx, exp, f"{bus}-reg{idx}")
                if not r:
                    continue
                if exp is None and not (0x23d000000 <= r[0] < 0x23e000000 and r[1] <= 0x1000):
                    self._refuse(f"{bus}-reg{idx}", f"{r[0]:#x}+{r[1]:#x} is outside the AON SPMI area")
                    continue
                if idx == 0:
                    self._add(A, r[0], r[1], U, bus, kind="spmi", base=r[0])
                    # REPLY register: read-traced (ASYNC) for reply decoding
                    self._add(A, r[0] + 0x8, 4, AS, bus, kind="spmi", base=r[0],
                              read=True, write=False)
                else:
                    self._add(A, r[0], r[1], U, f"{bus}-reg{idx}")
        if CFG["aic"]:
            r = self._adt_reg("/arm-io/aic", 0)
            if r:
                self._add(A, r[0], r[1], AS, "aic")
        self._add_sram_zone()
        if CFG["stop"]:
            for start, size in CFG["stop_zones"]:
                if size > PAGE or self._forbidden(start, size):
                    self._refuse("stop", f"stop zone {start:#x}+{size:#x} is larger than a page or forbidden")
                    continue
                zone = irange(start, size)
                self.hv.add_tracer(zone, A, TraceMode.HOOK, None, self._stop_w, region="stop")
                self.armed_zones.append(zone)
                self.zone_names.append((A, start, size, "HOOK", "stop"))
        self.armed = True
        self.rec("arm", text=note or "armed", zones=[(i, f"{s:#x}", f"{z:#x}", m, n)
                                                    for i, s, z, m, n in self.zone_names])
        print(f"[s2r] ARMED ({len(self.armed_zones)} zones). Page tables update when the guest resumes.")
        if self.refused:
            print(f"[s2r] {len(self.refused)} zone(s) refused; s2r_status() lists them")

    def disarm(self):
        self.hv.clear_tracers(S2R_IDENT_ARMED)
        self.armed_zones = []
        self.zone_names = [z for z in self.zone_names if z[0] != S2R_IDENT_ARMED]
        self.armed = False
        self.rec("disarm", text="disarmed")
        print("[s2r] disarmed")

    # -------------------------------------------------------------- stop mode
    def _stop_w(self, addr, val, width, **kw):
        # HOOK write handler: called synchronously (hv/__init__.py:620-623),
        # width is in bits. We must perform the write ourselves.
        r = self.rec("stop", text=f"held write {addr:#x} <- {val:#x} (w{width})",
                     addr=f"{addr:#x}", data=f"{val:#x}", width=width // 8,
                     cpu=self.hv.ctx.cpu_id if self.hv.ctx else None,
                     pc=f"{self.hv.ctx.elr:#x}" if self.hv.ctx else None)
        print(f"[s2r] STOP: {r['text']}")
        if not self.stopped_once:
            self.stopped_once = True
            self.snap("stop")
            self.hv.run_shell("[s2r] guest held BEFORE this write. s2r_snap() to read state; "
                              "S2R.drop_next=True to drop it; ^D or cont() to perform it and go on.",
                              "[s2r] continuing")
        if self.drop_next:
            self.drop_next = False
            self.rec("stop", text=f"dropped write {addr:#x} <- {val:#x}")
            print("[s2r] write dropped")
            return
        self.hv.u.write(addr, val, width)

    # --------------------------------------------------------------- snapshot
    SNAP_REGS = [
        # AON watchdog (Linux apple_wdt reads these; t8103.dtsi:1293-1298)
        *[(0x23d2b0000 + o, f"wdt+{o:#04x}") for o in (0x10, 0x14, 0x1c, 0x20, 0x24, 0x28, 0x2c)],
        (0x23d2b8008, "wdt-extra 0x..8008"), (0x23d2b800c, "wdt-extra 0x..800c"),
        (0x23d2b8020, "wdt-extra 0x..8020"),
    ]

    def snap(self, tag="manual"):
        """Read a few registers through the proxy.

        Only call this while the proxy is free: from the hv shell, from a
        synchronous hook, or after "Hypervisor exited". Never from an ASYNC
        event handler (the guest is running then).
        """
        regs = {}
        lst = list(self.SNAP_REGS)
        if CFG["snap_wake"]:
            lst += [(0x23d004000 + o, f"nub-wake+{o:#04x}") for o in range(0, 0x50, 4)]
        t = time.time()
        for addr, name in lst:
            try:
                regs[f"{addr:#x} {name}"] = f"{self.hv.p.read32(addr):#010x}"
            except Exception as e:
                regs[f"{addr:#x} {name}"] = f"ERR {e}"
        self.rec("snap", text=tag, regs=regs, ms=round((time.time() - t) * 1000, 1))
        print(f"[s2r] snapshot '{tag}' ({len(regs)} regs, {(time.time() - t) * 1000:.0f} ms) logged")
        if CFG["console"] >= 1:
            for k, v in regs.items():
                print(f"[s2r]   {k} = {v}")

    # ---------------------------------------------------------- hv log tee
    TEE_TAGS = ("CPUSTART", "msr ", "Guest is shutting down", "Dangerous", "RVBAR",
                "Starting guest secondary", "Guest exception")

    def install_hooks(self):
        hv = self.hv
        orig_log = hv.log

        def tee_log(s, *a, **k):
            orig_log(s, *a, **k)
            try:
                if isinstance(s, str) and any(t in s for t in self.TEE_TAGS):
                    self.rec("hvlog", text=s, cpu=hv.ctx.cpu_id if hv.ctx else None)
            except Exception:
                pass

        hv.log = tee_log

        orig_exit = hv.p.hv_exit_cpu

        def exit_cpu(cpu=-1):
            # Called from HV.handle_msr when the guest writes CYC_OVRD bit 0
            # (hv/__init__.py:731-738), before started_cpus shrinks.
            try:
                left = len(hv.started_cpus)
                me = hv.ctx.cpu_id if hv.ctx else cpu
                cyc = None
                if CFG["cyc_read"]:
                    # We run on the trapping core here (same context as
                    # handle_msr's own u.mrs, hv/__init__.py:762). This is the
                    # last CYC_OVRD value that landed in hardware; the bit-0
                    # value that triggered the exit was not written.
                    try:
                        cyc = f"{hv.u.mrs(CYC_OVRD_ENC):#x}"
                    except Exception as e:
                        cyc = f"ERR {e}"
                self.rec("exit-cpu", text=f"cpu{me} leaves the guest ({left - 1} left); "
                                          f"hw CYC_OVRD_EL1 = {cyc}", cpu=me, cyc_ovrd_hw=cyc)
                print(f"[s2r] cpu{me} entered its sleep WFI path; {left - 1} guest CPUs left")
                if left <= 1:
                    self.snap("last-cpu")
            except Exception as e:
                print(f"[s2r] exit hook error: {e}")
            return orig_exit(cpu)

        hv.p.hv_exit_cpu = exit_cpu

    def status(self):
        print(f"[s2r] log {self.path}  armed={self.armed}  records={self.seq}")
        for i, s, z, m, n in self.zone_names:
            print(f"[s2r]   {i:<8} {s:#011x} +{z:#08x} {m:<6} {n}")
        for n, why in self.refused:
            print(f"[s2r]   REFUSED  {n}: {why}")
        m = self.mbox.get("smc")
        print(f"[s2r]   SMC SRAM buffer: {m.sram_addr:#x}" if m and m.sram_addr else
              "[s2r]   SMC SRAM buffer: not seen")


S2R = S2RTrace(hv)          # noqa: F821  (hv comes from run_guest's namespace)
S2R.install_hooks()
S2R.add_always()
if CFG["arm_at_start"]:
    S2R.arm("armed at start")


# ---------------------------------------------------------- shell commands
def s2r_arm(note=""):
    """Add the sleep-path zones (take effect when the guest resumes)."""
    S2R.arm(note)


def s2r_go(note="sleep"):
    """Arm and resume the guest in one step (use from the ^C hv shell)."""
    S2R.arm(note)
    hv.cont()               # noqa: F821  (raises out of the shell: SIGUSR1 -> ExitConsole)


def s2r_disarm():
    S2R.disarm()


def s2r_snap(tag="manual"):
    S2R.snap(tag)


def s2r_mark(text):
    S2R.rec("mark", text=text)
    print(f"[s2r] mark: {text}")


def s2r_status():
    S2R.status()


print("[s2r] commands: s2r_go('note'), s2r_arm(), s2r_disarm(), s2r_snap(), s2r_mark('x'), "
      "s2r_status(), reboot()")
