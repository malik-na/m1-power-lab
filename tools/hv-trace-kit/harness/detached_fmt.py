"""Layout of the hypervisor's detached-mode control block and log, shared by detach.py and
detach_readout.py. The other side is m1n1 src/hv/hv_detached.c (branch m1power/hv-detached):
struct hv_detached_ctl (all 64-bit little-endian words) and struct det_entry (32 bytes).

No m1n1 import and no hardware access here, so tests/core/test_hv_detached.py runs it on any
machine (and compares the layout with the build's debug info when the build is there).
"""
import os
import struct
import subprocess

MAGIC = 0x4445544143480002      # HV_DET_MAGIC, layout version in the low 16 bits
MAGIC_V1 = 0x4445544143480001   # the first layout: the same block without the fields after saved_usage
MAX_SEG, MAX_CPU, MAX_PMGR, MAX_CONST, MAX_AMCC = 4, 32, 32, 8, 32
MAX_SYSREG, MAX_SHADOW, MAX_SNAP, MAX_CSNAP = 64, 32, 320, 1024
MAX_CPUS, USB_IODEV_COUNT = 32, 8

# (name, words per element, elements), in the order of the C struct.
FIELDS = [
    ("magic", 1, 1), ("size", 1, 1), ("state", 1, 1), ("flags", 1, 1),
    ("nseg", 1, 1), ("seg", 2, MAX_SEG),                      # base, cap (entries)
    ("log_cap", 1, 1), ("log_total", 1, 1), ("t_detach", 1, 1), ("cntfrq", 1, 1),
    ("entry_page", 1, 1), ("resume_flags", 1, 1), ("resumed", 1, 1), ("guest_reset_pc", 1, 1),
    ("cpustart_base", 1, 1), ("cpustart_size", 1, 1),
    ("ncpu", 1, 1), ("cpu", 3, MAX_CPU),                      # reg, cpu_id, impl_reg
    ("npmgr", 1, 1), ("pmgr", 5, MAX_PMGR),                   # addr, shadow, shadow_valid, requested, requested_valid
    ("nconst", 1, 1), ("konst", 2, MAX_CONST),                # addr, value
    ("namcc", 1, 1), ("amcc", 6, MAX_AMCC),                   # addr, write_mask, override_mask, override, value, valid
    ("nsysreg", 1, 1), ("sysreg", 3, MAX_SYSREG),             # enc, action, enc2
    ("nshadow", 1, 1), ("shadow_enc", 1, MAX_SHADOW), ("shadow", MAX_SHADOW, MAX_CPUS),
    ("nsnap", 1, 1), ("snap", 1, MAX_SNAP),
    ("stop", 8, 1),                                           # reason, code, esr, elr, far, spsr, cpu, hook_addr
    ("count", 1, 16), ("stray", 1, 1), ("deferred_dropped", 1, 1),
    ("saved_usage", 1, USB_IODEV_COUNT),
    # layout version 2
    ("ncsnap", 1, 1), ("csnap", 1, MAX_CSNAP), ("csnap_delay_us", 1, 1),
]
OFFSET = {}                     # name -> (first word, words per element, elements)
_w = 0
for _name, _per, _n in FIELDS:
    OFFSET[_name] = (_w, _per, _n)
    _w += _per * _n
WORDS = _w
SIZE = WORDS * 8
SIZE_V1 = OFFSET["ncsnap"][0] * 8

STATES = {0: "off", 1: "armed", 2: "stopped", 3: "host"}
FLAG_STOPPED = 1
FLAG_SR_ALL = 2              # log every system register access from the arm on
STOP_FIELDS = ("reason", "code", "esr", "elr", "far", "spsr", "cpu", "hook_addr")
COUNT_NAMES = ("pmgr", "cpustart", "const", "amcc", "sync_hook", "sysreg", "brk", "secondary",
               "irq", "upmc")
SR_PASS, SR_RO, SR_SKIP, SR_XLATE = 0, 1, 2, 3


def sysreg_enc(op0, op1, crn, crm, op2):
    """The key the C side uses: the register's bits in an MRS/MSR instruction."""
    return (op0 << 19) | (op1 << 16) | (crn << 12) | (crm << 8) | (op2 << 5)


def sysreg_name(enc):
    return "s%d_%d_c%d_c%d_%d" % ((enc >> 19) & 3, (enc >> 16) & 7, (enc >> 12) & 15,
                                  (enc >> 8) & 15, (enc >> 5) & 7)


class Ctl:
    """The control block as a list of words."""

    def __init__(self, words=None):
        self.w = list(words) if words is not None else [0] * WORDS
        assert len(self.w) == WORDS

    @classmethod
    def unpack(cls, blob):
        if len(blob) == SIZE_V1:        # a block saved from the first layout
            blob = blob + bytes(SIZE - SIZE_V1)
        if len(blob) != SIZE:
            raise ValueError("control block is %d bytes, expected %d" % (len(blob), SIZE))
        return cls(struct.unpack("<%dQ" % WORDS, blob))

    def pack(self):
        return struct.pack("<%dQ" % WORDS, *[v & 0xffffffffffffffff for v in self.w])

    def get(self, name, i=None):
        first, per, n = OFFSET[name]
        if i is None:
            if per == 1 and n == 1:
                return self.w[first]
            return [self.get(name, k) for k in range(n)]
        assert 0 <= i < n
        v = self.w[first + per * i:first + per * (i + 1)]
        return v[0] if per == 1 else tuple(v)

    def set(self, name, value, i=0):
        first, per, n = OFFSET[name]
        assert 0 <= i < n, "%s[%d]: only %d elements" % (name, i, n)
        value = [value] if per == 1 else list(value)
        assert len(value) == per, "%s takes %d words" % (name, per)
        self.w[first + per * i:first + per * (i + 1)] = [int(v) for v in value]

    def set_table(self, count_name, name, rows):
        rows = list(rows)
        if len(rows) > OFFSET[name][2]:
            raise ValueError("%d %s entries, the hypervisor's table holds %d" % (
                len(rows), name, OFFSET[name][2]))
        self.set(count_name, len(rows))
        for i, row in enumerate(rows):
            self.set(name, row, i)


# ---- the log ----
ENTRY = struct.Struct("<4Q")    # t (CNTPCT), addr, data, pc (low 48 bits) | meta << 48
K_ACC, K_DETACH, K_CORE_DOWN, K_LAST_DOWN, K_WAKE, K_WAKE_REG, K_SNAP, K_SECONDARY = range(8)
K_HOST, K_UNHANDLED, K_UNHANDLED2, K_UNHANDLED_HOOK, K_PMGR, K_CPUSTART = range(8, 14)
K_SYSREG, K_AMCC, K_CONST, K_BRK, K_IRQ, K_PANIC, K_UPMC_FIQ, K_RESUME, K_CPU_UNKNOWN = range(14, 23)
K_CSNAP, K_COMMIT_WRITE = 23, 24
# round 6 (m1n1-next 2ced1fab): a core's own state at its sleep write; the last core's sampler
K_CORE_STATE, K_SAMPLE, K_SAMPLE_END = 25, 26, 27
# how a system register access was handled: by the host's rules run on the M1 (pass, shadow,
# skip), or by the hypervisor's C side itself (c: fast path, c-locked: under its lock, s2r: the
# write that takes the core down for a real sleep, logged before it acts)
HOW = {0: "pass", 1: "shadow", 2: "skip", 3: "c", 4: "c-locked", 5: "s2r"}
START_REASON = {0: "BOOT", 1: "EXCEPTION", 2: "EXCEPTION_LOWER", 3: "HV"}
EXC_CODE = {0: "SYNC", 1: "IRQ", 2: "FIQ", 3: "SERROR"}
HV_CODE = {1: "HOOK_VM", 2: "VTIMER", 3: "USER_INTERRUPT", 4: "WDT_BARK", 5: "CPU_SWITCH",
           6: "VIRTIO", 7: "PANIC"}


def make_entry(t, addr, data, pc, kind, cpu=0, write=False, multi=False, width=0):
    """What det_put() stores (for the tests)."""
    meta = (cpu & 0x1f) | (int(write) << 5) | (int(multi) << 6) | ((width & 3) << 7) | (kind << 9)
    return ENTRY.pack(t, addr, data, (pc & 0xffffffffffff) | (meta << 48))


def decode_entry(raw):
    t, addr, data, pm = ENTRY.unpack(raw)
    meta, pc = pm >> 48, pm & 0xffffffffffff
    if pc & (1 << 47):
        pc |= 0xffff << 48
    return {"tick": t, "addr": addr, "data": data, "pc": pc, "cpu": meta & 0x1f,
            "w": bool(meta & 0x20), "multi": bool(meta & 0x40), "width": (meta >> 7) & 3,
            "kind": (meta >> 9) & 0x1f}


def stop_reason(reason, code):
    r = START_REASON.get(reason, str(reason))
    c = (HV_CODE if reason == 3 else EXC_CODE).get(code, str(code))
    return "%s/%s" % (r, c)


def records(entries, t0, frq, snap_names=None):
    """Decoded entries -> the dicts written as JSON lines. Accesses have the keys of
    hv_touch_map.py's "acc" records; "t" is seconds from the detach marker, taken from the M1's
    timer at the access. Markers are their own "ev". The words of a wake snapshot are gathered
    into one "snap" record shaped like the touch map's."""
    snap_names = snap_names or {}
    snap = None

    def t_of(e):
        return round((e["tick"] - t0) / frq, 6)

    def flush():
        nonlocal snap
        if snap is not None:
            out, snap = snap, None
            del out["_kind"]
            out["words"] = len(out["regs"])
            return [out]
        return []

    for e in entries:
        k, h = e["kind"], lambda v: "%#x" % v
        if snap is not None and snap["_kind"] != k:
            yield from flush()
        t = t_of(e)
        if k == K_ACC:
            yield {"addr": h(e["addr"]), "w": e["w"], "data": h(e["data"]), "width": e["width"],
                   "pc": h(e["pc"]), "cpu": e["cpu"], "ev": "acc", "t": t}
        elif k == K_DETACH:
            yield {"ev": "detached", "capacity": e["addr"], "cntfrq": e["data"],
                   "tick": e["tick"], "t": t}
        elif k in (K_CORE_DOWN, K_LAST_DOWN):
            yield {"ev": "last-core-down" if k == K_LAST_DOWN else "core-down", "cpu": e["cpu"],
                   "n": e["addr"], "of": e["data"], "t": t}
        elif k == K_WAKE:
            yield {"ev": "wake", "status_1c": h(e["addr"]), "status_20": h(e["data"] & 0xffffffff),
                   "status_24": h(e["data"] >> 32), "tick": e["tick"], "t": t}
        elif k == K_WAKE_REG:
            yield {"ev": "wake-reg", "addr": h(e["addr"]), "data": h(e["data"]),
                   "error": e["w"], "t": t}
        elif k in (K_SNAP, K_CSNAP):
            if snap is None:
                snap = {"ev": "snap", "tag": "wake" if k == K_SNAP else "commit", "words": 0,
                        "errors": 0, "regs": {}, "t": t, "_kind": k, "cpu": e["cpu"]}
            key = "%#x %s" % (e["addr"], snap_names[e["addr"]]) if e["addr"] in snap_names \
                else h(e["addr"])
            snap["regs"][key] = "ERR" if e["w"] else h(e["data"])
            snap["errors"] += int(e["w"])
            snap["t_end"] = t
        elif k == K_SECONDARY:
            yield {"ev": "secondary", "cpu": e["addr"], "entry": h(e["data"]),
                   "by": e["cpu"], "t": t}
        elif k == K_HOST:
            yield {"ev": "host", "stray_bytes": e["data"], "cpu": e["cpu"], "t": t}
        elif k == K_UNHANDLED:
            yield {"ev": "unhandled", "esr": h(e["data"]), "far": h(e["addr"]), "pc": h(e["pc"]),
                   "cpu": e["cpu"], "t": t}
        elif k == K_UNHANDLED2:
            yield {"ev": "unhandled-what", "what": stop_reason(e["addr"] >> 32, e["addr"] & 0xffffffff),
                   "spsr": h(e["data"]), "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k == K_UNHANDLED_HOOK:
            yield {"ev": "unhandled-hook", "addr": h(e["addr"]), "w": e["w"], "data": h(e["data"]),
                   "width": e["width"], "multi": e["multi"], "hook_id": e["pc"], "cpu": e["cpu"], "t": t}
        elif k == K_PMGR:
            yield {"ev": "pmgr", "addr": h(e["addr"]), "w": e["w"], "data": h(e["data"] & 0xffffffff),
                   "hw": h(e["data"] >> 32), "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k == K_CPUSTART:
            yield {"ev": "cpustart", "addr": h(e["addr"]), "data": h(e["data"]),
                   "passed_through": e["multi"], "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k == K_SYSREG:
            yield {"ev": "sysreg", "reg": sysreg_name(e["addr"] & 0xffffffff), "w": e["w"],
                   "data": h(e["data"]), "how": HOW.get(e["addr"] >> 32, str(e["addr"] >> 32)),
                   "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k in (K_AMCC, K_CONST):
            yield {"ev": "amcc" if k == K_AMCC else "const", "addr": h(e["addr"]), "w": e["w"],
                   "data": h(e["data"]), "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k == K_BRK:
            yield {"ev": "brk-lowered", "vector": h(e["addr"]), "esr": h(e["data"]),
                   "pc": h(e["pc"]), "cpu": e["cpu"], "t": t}
        elif k == K_IRQ:
            yield {"ev": "irq", "num": e["addr"], "type": e["data"], "cpu": e["cpu"], "t": t}
        elif k == K_RESUME:
            yield {"ev": "resume", "pc": h(e["addr"]), "flags": h(e["data"]), "t": t}
        elif k == K_COMMIT_WRITE:
            yield {"ev": "commit-write", "addr": h(e["addr"]), "data": h(e["data"]),
                   "cpu": e["cpu"], "t": t}
        elif k == K_CORE_STATE:
            a = e["addr"]
            what = sysreg_name(a) if a < (1 << 22) else ("pseudo-%#x" % (a & 0xff) if a >> 20 == 0xfff else h(a))
            yield {"ev": "core-state", "cpu": e["cpu"], "reg": what, "data": h(e["data"]),
                   "error": e["w"], "t": t}
        elif k == K_SAMPLE:
            yield {"ev": "sample", "addr": h(e["addr"]), "data": h(e["data"]), "error": e["w"],
                   "cpu": e["cpu"], "t": t}
        elif k == K_SAMPLE_END:
            yield {"ev": "sample-end", "reason": {1: "bound", 2: "wd2-near-bite"}.get(e["addr"], e["addr"]),
                   "samples": e["data"], "cpu": e["cpu"], "t": t}
        elif k == K_CPU_UNKNOWN:
            yield {"ev": "cpu-not-found", "reg": h(e["addr"]), "cpu": e["cpu"], "t": t}
        else:
            name = {K_PANIC: "hv-panic", K_UPMC_FIQ: "upmc-fiq"}.get(k, "kind-%d" % k)
            yield {"ev": name, "addr": h(e["addr"]), "data": h(e["data"]), "pc": h(e["pc"]),
                   "cpu": e["cpu"], "t": t}
    yield from flush()


# ---- the build ----
DEFAULT_ELF = "/home/naeem/m1n1-next/build/m1n1-raw.elf"


def elf_path():
    return os.environ.get("M1N1_ELF", DEFAULT_ELF)


def symbols(elf, names):
    """{name: (address, size)} from the build's ELF (linked at 0: add the running base)."""
    out = subprocess.run(["readelf", "-sW", elf], capture_output=True, text=True, check=True).stdout
    found = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 8 and f[7] in names:
            found[f[7]] = (int(f[1], 16), int(f[2], 0))
    missing = [n for n in names if n not in found]
    if missing:
        raise KeyError("%s has no symbol %s: not a build with detached mode" % (elf, ", ".join(missing)))
    return found


def image_bytes(elf, addr, size):
    """The build's bytes at an image offset, from m1n1.bin beside the ELF (offset = address)."""
    with open(os.path.join(os.path.dirname(elf), "m1n1.bin"), "rb") as f:
        f.seek(addr)
        return f.read(size)
