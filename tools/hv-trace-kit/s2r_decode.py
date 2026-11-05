#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Pure-Python decoders for the t8103 (M1, J313) sleep-entry trace.

No m1n1 or third-party imports: the hypervisor module (hv_s2r_trace.py) uses
these at trace time, and the same code summarises a finished log offline.

    python3 s2r_decode.py selftest
    python3 s2r_decode.py summarize s2r-trace.jsonl [--all] [--from-mark NAME]

Formats (all verified against m1n1 @70757dc unless marked):
  SPMI gen-1 command word   proxyclient/m1n1/hw/spmi1.py R_CMD:
      [31:16] EXTRA (register / data), [15] ALERT, [11:8] SLAVE_ID, [7:0] OPCODE
  SPMI reply word           hw/spmi1.py R_REPLY:
      [31:16] FRAME_PARITY, [15] ACK, [14:8] SLAVE_ID, [7:0] OPCODE
  Opcodes and payload rules proxyclient/m1n1/hw/spmi.py (raw_command, *_ext*, *_reg)
  SMC messages              proxyclient/m1n1/fw/smc.py (TYPE [7:0], ID [15:12],
                            SIZE [23:16], KEY [63:32] big-endian ASCII)
  RTKit management (EP 0)   proxyclient/m1n1/fw/asc/mgmt.py (TYPE [59:52], STATE [15:0])
  ASC mailbox offsets       proxyclient/m1n1/hw/asc.py (INBOX0 +0x8800, INBOX1 +0x8808,
                            OUTBOX0 +0x8830, OUTBOX1 +0x8838; EP = INBOX1/OUTBOX1 [7:0])
"""

import json
import sys

# --------------------------------------------------------------------------
# t8103 address map used for labelling. Sources: the generic MacBookAir10,1
# ADT (scratchpad/fabric/adt.pkl), aurora t8103.dtsi, m1n1 smp.c. Entries
# marked "?" are inferred (offset analogy with aura PR #70 on T8140) and are
# labels only: the tracer never writes anything.
# --------------------------------------------------------------------------
T8103_REGIONS = [
    # (start, size, name)
    (0x23b754000, 0x20, "pmgr-cpu-start (stop +0x0, alive +0x4, cluster start +0x8/+0xc)"),
    (0x23b71c000, 0x4000, "pmgr-pwrgate (0x..c010/c310/c610)"),
    (0x23b768000, 0x4000, "pmgr-cllt?"),
    (0x23b780000, 0x4000, "pmgr-cluster-ctl?"),
    (0x23b700000, 0x8c000, "pmgr reg[0]"),
    (0x23b040000, 0x4000, "clkgen-mux?"),
    (0x23b000000, 0x70000, "clkgen reg[2]"),
    (0x23d2b0000, 0x4000, "aon-wdt (WD1 +0x10..0x1c, WD2 +0x20..0x2c)"),
    (0x23d2b8000, 0x4000, "aon-wdt-extra (0x..8008/800c/8020)"),
    (0x23d2d0000, 0x4000, "aes reg[1] (not S2R)"),
    (0x23d2d4000, 0x4000, "aon-s2r-timer?"),
    (0x23d29c000, 0x4000, "aon-pwrgate (0x..c010)"),
    (0x23d280000, 0x74000, "aon-pmgr reg[1]"),
    (0x23d200000, 0x80000, "pmgr reg[3]"),
    (0x23d004000, 0x1000, "nub-wake (enable +0x08..0x24?, status +0x28..0x44?)"),
    (0x23d0d9300, 0x100, "nub-spmi"),
    (0x23d0d8e00, 0x100, "nub-spmi reg[1]"),
    (0x23d0d8400, 0x78, "nub-spmi reg[2]"),
    (0x23d0e1300, 0x100, "nub-spmi1 (secondary PMIC)"),
    (0x23d0e0e00, 0x100, "nub-spmi1 reg[1]"),
    (0x23d0e0400, 0x78, "nub-spmi1 reg[2]"),
    (0x23e408000, 0x4000, "smc-mbox"),
    (0x23fe00000, 0x100000, "smc-sram"),
    (0x23bc08000, 0x4000, "pmp-mbox"),
    (0x210e20000, 0x2000, "ecluster perf"),
    (0x210e40000, 0x9000, "ecluster cpm"),
    (0x210e70000, 0x1000, "ecluster misc"),
    (0x211e20000, 0x2000, "pcluster perf"),
    (0x211e40000, 0xb000, "pcluster cpm"),
    (0x211e70000, 0x1000, "pcluster misc"),
    (0x23b100000, 0x10000, "aic"),
]


def region_of(addr):
    """Most specific (smallest) known region containing addr: (name, start)."""
    best = None
    for start, size, name in T8103_REGIONS:
        if start <= addr < start + size:
            if best is None or size < best[2]:
                best = (name, start, size)
    if best is None:
        return "?", addr
    return best[0], best[1]


# --------------------------------------------------------------------------
# Sera PMU (nub-spmi slave 0xf) register names. ADT /arm-io/nub-spmi/spmi-pmu
# info-* properties and aurora t8103.dtsi nvmem cells.
# --------------------------------------------------------------------------
SERA_REGS = {
    0x9f00: "leg_scrpad",
    0x9f01: "boot_stage",
    0x9f02: "boot_error_count|panic_count",
    0x9f03: "boot_error_stage",
    0x9f0f: "shutdown_flag(bit3)",
    0xa47b: "fault_shadow (ADT)",
    0xa67b: "fault_shadow (DT)",
    0xab00: "socd",
    0xd000: "rtc_alarm_ctrl (enable mask 0x40)",
    0xd001: "pm_setting",
    0xd002: "rtc",
    0xd008: "rtc_alarm",
    0xd00c: "rtc_alarm_event",
    0xd00e: "rtc_irq_mask",
    0xd100: "rtc_offset/scrpad",
    0xd200: "fault_log",
}


def sera_label(reg):
    if reg in SERA_REGS:
        return SERA_REGS[reg]
    if 0x9f00 <= reg < 0x9f10:
        return f"leg_scrpad+{reg - 0x9f00:#x}"
    if 0xa000 <= reg < 0xb000:
        return f"scrpad+{reg - 0xa000:#x}"
    if 0xd002 <= reg < 0xd008:
        return f"rtc+{reg - 0xd002}"
    return ""


SPMI_FIXED = {0x10: "RESET", 0x11: "SLEEP", 0x12: "SHUTDOWN", 0x13: "WAKEUP", 0x1c: "SLAVE_DESC"}


def spmi_classify(op):
    """Return (name, nbytes, kind, payload_words) for an opcode.

    kind: 'w' write with payload words, 'r' read (reply payload), 'c' control,
          'wr' WRITE (value in EXTRA), 'zw' ZERO_WRITE (value in opcode).
    """
    if op in SPMI_FIXED:
        return SPMI_FIXED[op], (10 if op == 0x1c else 0), ('r' if op == 0x1c else 'c'), 0
    if op <= 0x0f:
        n = (op & 0xf) + 1
        return "EXT_WRITE", n, 'w', (n + 3) // 4
    if 0x20 <= op <= 0x2f:
        return "EXT_READ", (op & 0xf) + 1, 'r', 0
    if 0x30 <= op <= 0x37:
        n = (op & 0x7) + 1
        return "EXT_WRITEL", n, 'w', (n + 3) // 4
    if 0x38 <= op <= 0x3f:
        return "EXT_READL", (op & 0x7) + 1, 'r', 0
    if 0x40 <= op <= 0x5f:
        return "WRITE", 1, 'wr', 0
    if 0x60 <= op <= 0x7f:
        return "READ", 1, 'r', 0
    if op >= 0x80:
        return "ZERO_WRITE", 1, 'zw', 0
    return f"OP_{op:#x}?", 0, 'c', 0


class SPMIDecoder:
    """Reassembles SPMI gen-1 commands from CMD writes and replies from REPLY reads.

    Emits dicts. A write command is emitted as soon as its payload is complete
    (before its ACK) so that the last command before a power cut is not lost.
    """

    def __init__(self, bus, pmu_slave=0xf, label_pmu=True):
        self.bus = bus
        self.pmu_slave = pmu_slave
        self.label_pmu = label_pmu
        self.cur = None          # command collecting payload words
        self.pending = []        # commands awaiting a reply header
        self.reply = None        # reply collecting payload words

    def _label(self, slave, reg):
        if reg is None:
            return ""
        if self.label_pmu and slave == self.pmu_slave:
            return sera_label(reg)
        return ""

    def feed_cmd(self, word, cpu=None, pc=None):
        word &= 0xffffffff
        out = []
        if self.cur is not None:
            c = self.cur
            c["_words"].append(word)
            if len(c["_words"]) >= c["_need"]:
                raw = b"".join(w.to_bytes(4, "little") for w in c["_words"])
                c["data"] = raw[:c["nbytes"]].hex()
                self.cur = None
                out.append(self._emit_cmd(c))
            return out
        op = word & 0xff
        slave = (word >> 8) & 0xf
        alert = (word >> 15) & 1
        extra = word >> 16
        name, nbytes, kind, words = spmi_classify(op)
        c = {"bus": self.bus, "op": name, "opcode": op, "slave": slave, "alert": alert,
             "cmd_word": f"{word:#010x}", "cpu": cpu, "pc": pc, "nbytes": nbytes,
             "reg": None, "data": None, "kind": kind}
        if name in ("EXT_WRITE", "EXT_READ"):
            c["reg"] = extra & 0xff
        elif name in ("EXT_WRITEL", "EXT_READL"):
            c["reg"] = extra
        elif name == "WRITE":
            c["reg"] = op & 0x1f
            c["data"] = f"{(extra >> 8) & 0xff:02x}"
        elif name == "READ":
            c["reg"] = op & 0x1f
        elif name == "ZERO_WRITE":
            c["reg"] = 0
            c["data"] = f"{op & 0x7f:02x}"
        self.pending.append(c)
        if kind == 'w' and words:
            c["_words"] = []
            c["_need"] = words
            self.cur = c
            return out
        if kind in ('wr', 'zw', 'c'):
            out.append(self._emit_cmd(c))
        return out

    def _emit_cmd(self, c):
        rec = {k: v for k, v in c.items() if not k.startswith("_")}
        rec["ev"] = "spmi-cmd"
        rec["label"] = self._label(c["slave"], c["reg"])
        rec["text"] = self.fmt(rec)
        return rec

    def feed_reply(self, word):
        word &= 0xffffffff
        out = []
        if self.reply is not None:
            r = self.reply
            r["_words"].append(word)
            if len(r["_words"]) * 4 >= r["_cmd"]["nbytes"]:
                raw = b"".join(w.to_bytes(4, "little") for w in r["_words"])
                r["data"] = raw[:r["_cmd"]["nbytes"]].hex()
                self.reply = None
                out.append(self._emit_reply(r))
            return out
        op = word & 0xff
        slave = (word >> 8) & 0x7f
        ack = (word >> 15) & 1
        parity = word >> 16
        cmd = self.pending.pop(0) if self.pending else None
        r = {"_cmd": cmd or {"nbytes": 0, "op": "?", "reg": None, "slave": slave, "kind": "?"},
             "reply_word": f"{word:#010x}", "ack": ack, "parity": parity,
             "slave": slave, "opcode": op, "data": None}
        notes = []
        if cmd is None:
            notes.append("unexpected reply")
        elif cmd["opcode"] != op:
            notes.append(f"opcode mismatch (cmd {cmd['opcode']:#x})")
        r["notes"] = notes
        if cmd is not None and cmd["kind"] == 'r' and cmd["nbytes"]:
            r["_words"] = []
            self.reply = r
            return out
        out.append(self._emit_reply(r))
        return out

    def _emit_reply(self, r):
        cmd = r["_cmd"]
        rec = {"ev": "spmi-reply", "bus": self.bus, "op": cmd.get("op"), "slave": r["slave"],
               "reg": cmd.get("reg"), "data": r["data"], "ack": r["ack"],
               "parity": r["parity"], "reply_word": r["reply_word"], "notes": r["notes"],
               "label": self._label(r["slave"], cmd.get("reg"))}
        if cmd.get("kind") in ('w', 'wr', 'zw', 'c'):
            rec["data_written"] = cmd.get("data")
        rec["text"] = self.fmt(rec, reply=True)
        return rec

    @staticmethod
    def fmt(rec, reply=False):
        reg = rec.get("reg")
        regs = f" reg {reg:#06x}" if isinstance(reg, int) else ""
        lab = f" [{rec['label']}]" if rec.get("label") else ""
        data = rec.get("data")
        if reply:
            ack = "ACK" if rec.get("ack") else "noACK"
            d = f" = {data}" if data is not None else ""
            notes = (" (" + "; ".join(rec["notes"]) + ")") if rec.get("notes") else ""
            return f"{rec['bus']} <- s{rec['slave']:#x} {rec['op']}{regs}{lab}{d} {ack}{notes}"
        d = f" <- {data}" if data is not None and rec.get("kind") != 'r' else ""
        # ALERT is bit 15 of the command word; its meaning is not known, so print it raw.
        q = f" ALERT={rec.get('alert', '?')}"
        return f"{rec['bus']} -> s{rec['slave']:#x} {rec['op']}{regs}{lab}{d}{q} [{rec['cmd_word']}]"


# --------------------------------------------------------------------------
# ASC mailbox (SMC, PMP)
# --------------------------------------------------------------------------
SMC_TYPES = {0x10: "READ_KEY", 0x11: "WRITE_KEY", 0x12: "GET_KEY_BY_INDEX",
             0x13: "GET_KEY_INFO", 0x17: "INITIALIZE", 0x18: "NOTIFICATION", 0x20: "RW_KEY"}
MGMT_TYPES = {1: "HELLO", 2: "HELLO_ACK", 3: "PING", 4: "PONG", 5: "START_EP",
              6: "SET_IOP_POWER", 7: "IOP_POWER_ACK", 8: "EPMAP", 0xb: "SET_AP_POWER"}


def key_name(k):
    try:
        s = k.to_bytes(4, "big").decode("ascii")
        if all(32 <= ord(ch) < 127 for ch in s):
            return s
    except Exception:
        pass
    return f"{k:#010x}"


class MboxDecoder:
    """Decodes one ASC mailbox from INBOX0/1 writes and OUTBOX0/1 reads.

    kind = 'smc' or 'pmp'. For SMC, key values for WRITE_KEY come from SRAM
    writes the tracer feeds through note_sram_write() (go mode cannot read
    SRAM synchronously).
    """

    def __init__(self, name, kind):
        self.name = name
        self.kind = kind
        self.tx0 = None
        self.rx0 = None
        self.sram_addr = None
        self.sram = {}
        self.ids = {}

    def note_sram_write(self, addr, data, nbytes):
        for i in range(nbytes):
            self.sram[addr + i] = (data >> (8 * i)) & 0xff
        if len(self.sram) > 65536:
            self.sram.clear()

    def sram_bytes(self, size):
        if self.sram_addr is None:
            return None
        out = []
        for i in range(size):
            b = self.sram.get(self.sram_addr + i)
            if b is None:
                return None
            out.append(b)
        return bytes(out).hex()

    def feed(self, off, data, write):
        """off: offset from the ASC base (0x8800/0x8808/0x8830/0x8838)."""
        if write and off == 0x8800:
            self.tx0 = data
        elif write and off == 0x8808:
            return self._msg("tx", self.tx0, data & 0xff)
        elif not write and off == 0x8830:
            self.rx0 = data
        elif not write and off == 0x8838:
            return self._msg("rx", self.rx0, data & 0xff)
        return None

    def _msg(self, d, m, ep):
        if m is None:
            return None
        rec = {"ev": f"{self.kind}-{d}", "mbox": self.name, "ep": ep, "msg": f"{m:#018x}"}
        arrow = ">" if d == "tx" else "<"
        if ep == 0:
            t = (m >> 52) & 0xff
            rec["mgmt"] = MGMT_TYPES.get(t, f"type{t:#x}")
            if t in (6, 7, 0xb):
                rec["state"] = f"{m & 0xffff:#x}"
                rec["text"] = f"{self.name} {arrow} mgmt {rec['mgmt']} state {rec['state']}"
            else:
                rec["text"] = f"{self.name} {arrow} mgmt {rec['mgmt']} {m:#018x}"
            return rec
        if self.kind == "smc" and ep == 0x20:
            if d == "tx":
                t = m & 0xff
                mid = (m >> 12) & 0xf
                name = SMC_TYPES.get(t, f"type{t:#x}")
                rec["smc"] = name
                rec["id"] = mid
                text = f"{self.name} > [{mid:x}] {name}"
                if t in (0x10, 0x11, 0x12, 0x13, 0x20):
                    key = key_name(m >> 32) if t != 0x12 else f"index {m >> 32}"
                    rec["key"] = key
                    text += f" <{key}>"
                if t in (0x10, 0x11):
                    size = (m >> 16) & 0xff
                    rec["size"] = size
                    text += f" size {size}"
                    if t == 0x11:
                        val = self.sram_bytes(size)
                        rec["value"] = val
                        text += f" = {val if val is not None else '(value not captured)'}"
                if t == 0x20:
                    rec["rsize"] = (m >> 16) & 0xff
                    rec["wsize"] = (m >> 24) & 0xff
                    val = self.sram_bytes(rec["wsize"])
                    rec["value"] = val
                    text += f" w{rec['wsize']} r{rec['rsize']} = {val}"
                self.ids[mid] = rec.get("key")
                rec["text"] = text
            else:
                if self.sram_addr is None:
                    # First reply after INITIALIZE carries the SRAM buffer address
                    # (proxyclient/hv/trace_smc.py: first RX sets sram_addr = msg.value).
                    self.sram_addr = m
                    rec["sram_addr"] = f"{m:#x}"
                    rec["text"] = f"{self.name} < SRAM buffer at {m:#x}"
                    return rec
                res = m & 0xff
                mid = (m >> 12) & 0xf
                rec["result"] = res
                rec["id"] = mid
                rec["value"] = f"{(m >> 32) & 0xffffffff:#x}"
                rec["text"] = (f"{self.name} < [{mid:x}] result {res:#x} size {(m >> 16) & 0xffff}"
                               f" value {rec['value']} (for <{self.ids.get(mid)}>)")
            return rec
        if self.kind == "pmp" and ep == 0x20:
            t = (m >> 44) & 0x1fff
            rec["pmp_type"] = f"{t:#x}"
            rec["text"] = f"{self.name} {arrow} ep20 type {t:#x} {m:#018x}"
            return rec
        rec["text"] = f"{self.name} {arrow} ep{ep:#04x} {m:#018x}"
        return rec


# --------------------------------------------------------------------------
# Offline summary
# --------------------------------------------------------------------------
RAW_DECODED_ZONES = ("nub-spmi", "nub-spmi1", "smc-mbox", "pmp-mbox", "smc-sram")
INTERESTING_HVLOG = ("CPUSTART", "msr ", "Guest is shutting down", "Dangerous", "RVBAR")


def load(path):
    recs = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(json.loads(ln))
            except json.JSONDecodeError:
                recs.append({"ev": "corrupt", "text": ln[:200]})
    return recs


def summarize(path, show_all=False, from_mark=None, out=sys.stdout):
    recs = load(path)
    start = 0
    if from_mark:
        for i, r in enumerate(recs):
            if r.get("ev") in ("mark", "arm") and from_mark in (r.get("text") or ""):
                start = i
    else:
        for i, r in enumerate(recs):
            if r.get("ev") == "arm":
                start = i
    recs = recs[start:]
    print(f"# {path}: {len(recs)} records from index {start}", file=out)
    pmgr_ps = 0
    for r in recs:
        ev = r.get("ev")
        if ev == "mmio":
            if not show_all and (not r.get("w") or r.get("zone") in RAW_DECODED_ZONES):
                continue
            reg = r.get("region", "")
            if not show_all and reg.startswith("pmgr reg[0]") and r.get("ps"):
                pmgr_ps += 1
            line = (f"{r.get('t', 0):.6f} cpu{r.get('cpu')} {reg:<34} "
                    f"{'W' if r.get('w') else 'R'}{r.get('width', 4) * 8:<2} {r.get('addr')} = {r.get('data')}"
                    f" pc {r.get('pc')}" + (f" ({r['ps']})" if r.get("ps") else ""))
            print(line, file=out)
        elif ev in ("spmi-cmd", "spmi-reply"):
            if ev == "spmi-reply" and not show_all and r.get("op") not in ("EXT_READL", "EXT_READ", "READ"):
                continue
            print(f"{r.get('t', 0):.6f} {r.get('text')}", file=out)
        elif ev in ("hvlog",):
            if any(tag in (r.get("text") or "") for tag in INTERESTING_HVLOG):
                print(f"{r.get('t', 0):.6f} hv: {r.get('text')}", file=out)
        elif ev in ("mark", "arm", "disarm", "snap", "stop", "note", "exit-cpu", "zone-refused"):
            print(f"{r.get('t', 0):.6f} == {ev}: {r.get('text', '')}", file=out)
            if ev == "snap":
                for k, v in (r.get("regs") or {}).items():
                    print(f"      {k} = {v}", file=out)
        elif ev and ev.startswith(("smc-", "pmp-")):
            if not show_all and ev.endswith("-rx") and r.get("smc") is None and "mgmt" not in r:
                pass
            print(f"{r.get('t', 0):.6f} {r.get('text')}", file=out)
    if pmgr_ps:
        print(f"# {pmgr_ps} PMGR device power-state writes shown (labelled by ADT device)", file=out)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
def selftest():
    ok = 0

    def check(cond, msg):
        nonlocal ok
        if not cond:
            raise AssertionError(msg)
        ok += 1

    # J700 trace words from aura PR #70 (docs/j700-s2r-entry-trace-20261105.txt),
    # PMU slave 0xe there: EXT_READL 0xf80c, EXT_WRITEL 0xf808 <- 4 bytes,
    # 0xf80e <- 0, 0xf800 <- 0x41.
    d = SPMIDecoder("j700", pmu_slave=0xe, label_pmu=False)
    out = d.feed_cmd(0xf80c8e38)
    check(out == [], "EXT_READL emits on reply only")
    check(d.pending[0]["op"] == "EXT_READL" and d.pending[0]["reg"] == 0xf80c, "readl decode")
    out = d.feed_cmd(0xf8088e33)
    check(out == [], "EXT_WRITEL waits for payload")
    out = d.feed_cmd(0x006f86fd)
    check(len(out) == 1 and out[0]["op"] == "EXT_WRITEL" and out[0]["reg"] == 0xf808
          and out[0]["data"] == "fd866f00" and out[0]["slave"] == 0xe, f"writel decode {out}")
    out = d.feed_cmd(0xf80e8e30) + d.feed_cmd(0x0)
    check(out[0]["reg"] == 0xf80e and out[0]["data"] == "00", "writel 1 byte")
    out = d.feed_cmd(0xf8008e30) + d.feed_cmd(0x41)
    check(out[0]["reg"] == 0xf800 and out[0]["data"] == "41", "alarm enable")
    # replies: READL header + payload, then three write ACKs
    check(d.feed_reply(0x00018e38) == [], "readl header waits for payload")
    out = d.feed_reply(0x00000001)
    check(out and out[0]["op"] == "EXT_READL" and out[0]["data"] == "01" and out[0]["reg"] == 0xf80c,
          f"readl reply {out}")
    for _ in range(3):
        out = d.feed_reply(0x00008e30 | 0x3)  # opcode will mismatch for the 0x33 one: fine
    check(len(d.pending) == 0, "pending drained")

    # t8103 Sera (slave 0xf) on nub-spmi: alarm enable as macOS would write it.
    s = SPMIDecoder("nub-spmi")
    out = s.feed_cmd(0xd0008f30) + s.feed_cmd(0x41)
    check(out[0]["label"].startswith("rtc_alarm_ctrl") and out[0]["slave"] == 0xf, "sera label")
    out = s.feed_cmd(0xd0018f30) + s.feed_cmd(0x07)
    check(out[0]["label"] == "pm_setting" and out[0]["data"] == "07", "pm_setting write")
    out = s.feed_cmd(0x00008f11)
    check(out[0]["op"] == "SLEEP", "SLEEP control op")
    out = s.feed_cmd(0x0f0a8f42)
    check(out[0]["op"] == "WRITE" and out[0]["reg"] == 2 and out[0]["data"] == "0f", "WRITE reg")
    out = s.feed_cmd(0x00008f85)
    check(out[0]["op"] == "ZERO_WRITE" and out[0]["data"] == "05", "ZERO_WRITE")
    out = s.feed_cmd(0x00008f37) + s.feed_cmd(0x04030201)
    check(out == [], "8-byte EXT_WRITEL needs two payload words")
    out = s.feed_cmd(0x08070605)
    check(out[0]["data"] == "0102030405060708", "8-byte payload order")

    # SMC: INITIALIZE reply gives SRAM, then WRITE_KEY 'MBSE' size 4 with SRAM bytes.
    m = MboxDecoder("smc", "smc")
    m.feed(0x8830, 0x23fe04000, False)
    r = m.feed(0x8838, 0x20, False)
    check(r and m.sram_addr == 0x23fe04000, "sram addr learned")
    m.note_sram_write(0x23fe04000, 0x736c7077, 4)
    msg = (int.from_bytes(b"MBSE", "big") << 32) | (4 << 16) | (3 << 12) | 0x11
    m.feed(0x8800, msg, True)
    r = m.feed(0x8808, 0x20, True)
    check(r["key"] == "MBSE" and r["size"] == 4 and r["value"] == "77706c73", f"smc write key {r}")
    # RTKit mgmt power state (PMP IDLE request seen on J700 as ...0201)
    pm = MboxDecoder("pmp", "pmp")
    pm.feed(0x8800, (0xb << 52) | 0x201, True)
    r = pm.feed(0x8808, 0x0, True)
    check(r["mgmt"] == "SET_AP_POWER" and r["state"] == "0x201", "mgmt decode")

    # region labels
    check(region_of(0x23b754000)[0].startswith("pmgr-cpu-start"), "cpu start label")
    check(region_of(0x23d2d4000)[0] == "aon-s2r-timer?", "s2r label")
    check(region_of(0x23d2b002c)[0].startswith("aon-wdt"), "wdt label")
    check(region_of(0x23b700100)[0] == "pmgr reg[0]", "pmgr label")
    print(f"selftest: {ok} checks passed")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[1] == "selftest":
        return selftest()
    if argv[1] == "summarize":
        args = argv[2:]
        show_all = "--all" in args
        mark = None
        if "--from-mark" in args:
            mark = args[args.index("--from-mark") + 1]
        paths = [a for a in args if not a.startswith("--") and a != mark]
        for p in paths:
            summarize(p, show_all=show_all, from_mark=mark)
        return 0
    print(f"unknown command {argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
