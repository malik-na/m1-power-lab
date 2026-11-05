# Offline harness: runs hv_s2r_trace.py against a fake HV and feeds synthetic events.
import os, sys, runpy, types, json, tempfile, pathlib
KIT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "work" / "mock"))
from m1n1.hv import TraceMode

class Flags:
    def __init__(s, write, width, cpu=0, multi=0): s.WRITE=write; s.WIDTH=width; s.CPU=cpu; s.MULTI=multi
class Evt:
    def __init__(s, addr, data, write, width=2, cpu=0, pc=0xfffffe0000001234):
        s.addr=addr; s.data=data; s.flags=Flags(write, width, cpu); s.pc=pc

class Reg:
    def __init__(s, regs): s.regs=regs
    def get_reg(s, i): return s.regs[i]
class PS:  # ps_regs entry
    def __init__(s, reg, offset): s.reg=reg; s.offset=offset
class Dev:
    def __init__(s, name, psreg, psidx): s.name=name; s.psreg=psreg; s.psidx=psidx
class Pmgr(Reg):
    pass

pm_regs = [(0x23b700000,0x8c000),(0x23d280000,0x74000),(0x23b000000,0x70000),(0x23d200000,0x80000),(0x23d004000,0x1000),
           (0x210e20000,0x2000),(0x210050000,0xef1000),(0x210e40000,0x9000),(0x210e50000,0xe81000),(0x210e70000,0x1000),
           (0,0),(0,0),(0,0),(0,0),(0x211e20000,0x2000),(0,0),(0x211e40000,0xb000),(0,0),(0x211e70000,0x1000)]
pmgr = Pmgr(pm_regs); pmgr.ps_regs=[PS(0,0x0), PS(1, 0x0)]; pmgr.devices=[Dev("SIO_CPU",0,58), Dev("AOP",1,2)]
ADT = {"/arm-io/pmgr": pmgr, "/arm-io/smc": Reg([(0x23e400000,0x4000)]), "/arm-io/nub-spmi": Reg([(0x23d0d9300,0x100),(0x23d0d8e00,0x100),(0x23d0d8400,0x78)]),
       "/arm-io/nub-spmi1": Reg([(0x23d0e1300,0x100),(0x23d0e0e00,0x100),(0x23d0e0400,0x78)])}
class Adt(dict):
    def __getitem__(s, k): return dict.__getitem__(s, k)

class Ctx: cpu_id = 0; elr = 0xfffffe00deadbeef
class P:
    def __init__(s): s.exited=[]
    def hv_exit_cpu(s, cpu=-1): s.exited.append(cpu)
    def read32(s, a): return a & 0xffff
class U:
    def __init__(s): s.writes=[]; s.mrs_calls=[]
    def write(s, a, v, w): s.writes.append((a,v,w))
    def mrs(s, enc): s.mrs_calls.append(enc); return 0x400000  # pretend IRQ_MODE(1) landed
class FakeHV:
    def __init__(s):
        s.adt=Adt(ADT); s.tracers={}; s.p=P(); s.u=U(); s.ctx=Ctx(); s.started=True; s.started_cpus={0:1,4:1}; s.logs=[]
    def log(s, m, *a, **k): s.logs.append(m)
    def add_tracer(s, zone, ident, mode, read=None, write=None, **kw):
        assert mode in (TraceMode.RESERVED, TraceMode.OFF, TraceMode.BYPASS) or read or write
        s.tracers[(zone.start, zone.stop, ident)] = (mode, read, write, kw)
    def clear_tracers(s, ident):
        for k in [k for k in s.tracers if k[2]==ident]: del s.tracers[k]
    def cont(s): raise SystemExit("cont")
    def run_shell(s, a, b): print("SHELL:", a); return None
    def find(s, addr, write):
        best=None
        for (a,b,i),(m,r,w,kw) in s.tracers.items():
            if a<=addr<b and (w if write else r):
                if best is None or (b-a) < best[0]: best=(b-a,m,r,w,kw)
        return best

hv = FakeHV()
log = str(KIT / "work" / "mock-trace.jsonl"); pathlib.Path(log).unlink(missing_ok=True)
os.environ["S2R_LOG"]=log; os.environ["S2R_STOP"]="1"
g = runpy.run_path(str(KIT/"hv_s2r_trace.py"), init_globals={"hv": hv}, run_name="<hv_script>")
S2R = g["S2R"]
# always zones present
assert any(k[0]==0x23e408800 for k in hv.tracers), hv.tracers.keys()
def fire(addr, data, write, width=2, cpu=0):
    b = hv.find(addr, write)
    assert b, f"no tracer for {addr:#x} write={write}"
    _, m, r, w, kw = b
    (w if write else r)(Evt(addr, data, write, width, cpu), **kw)
    return m
# SMC init reply -> SRAM address
fire(0x23e408830, 0x23fe04000, False, 3); fire(0x23e408838, 0x20, False, 3)
g["s2r_arm"]("test")
mode = fire(0x23d0d9304, 0xd0008f30, True); assert mode == TraceMode.UNBUF, mode
fire(0x23d0d9304, 0x41, True)
fire(0x23d0d9304, 0xd00c8f38, True); fire(0x23d0d9308, 0x00018f38, False); fire(0x23d0d9308, 0x1, False)
fire(0x23d0d9304, 0xd0018f30, True); fire(0x23d0d9304, 0x07, True)
assert fire(0x23b7001d0, 0x400024f, True) == TraceMode.ASYNC
assert fire(0x23b780008, 0x0, True) == TraceMode.UNBUF
fire(0x23d2b002c, 0x4, True)
fire(0x23fe04000, 0x736c7077, True)  # SRAM data
msg = (int.from_bytes(b"MBSE","big")<<32)|(4<<16)|(1<<12)|0x11
fire(0x23e408800, msg, True, 3); fire(0x23e408808, 0x20, True, 3)
# defaults: no cluster zones, stop zone narrowed to the candidate words, no wake reads in snapshots
assert not any(str(v[3].get("region","")).startswith("cluster") for v in hv.tracers.values())
stop = [k for k,v in hv.tracers.items() if v[3].get("region")=="stop"]; assert stop == [(0x23d2d4000, 0x23d2d4010, "S2R-ARM")], stop
assert hv.find(0x23d2d4010, True) is None or hv.find(0x23d2d4010, True)[1] != TraceMode.HOOK
assert g["CFG"]["snap_wake"] == 0
# stop zone HOOK
b = hv.find(0x23d2d4000, True); assert b[1] == TraceMode.HOOK
b[3](0x23d2d4000, 1, 32, **b[4]); assert hv.u.writes[-1] == (0x23d2d4000, 1, 32)
# hv log tee + last-cpu snapshot
hv.log("CPUSTART W 23b754000+0:32 = 0x2"); hv.log("Skip: msr ACC_OVRD_EL1, x0 = 400000000")
hv.p.hv_exit_cpu(); hv.started_cpus.pop(0); hv.p.hv_exit_cpu()
g["s2r_status"](); g["s2r_disarm"]()
assert not any(k[2]=="S2R-ARM" for k in hv.tracers)
S2R.f.flush()
recs=[json.loads(l) for l in open(log)]
evs=[r["ev"] for r in recs]
for need in ("arm","spmi-cmd","spmi-reply","smc-tx","stop","hvlog","exit-cpu","snap","disarm"):
    assert need in evs, (need, evs)
ex=[r for r in recs if r["ev"]=="exit-cpu"]; assert ex[0]["cyc_ovrd_hw"]=="0x400000", ex[0]
assert hv.u.mrs_calls and hv.u.mrs_calls[0]==(3,5,15,5,0)
snaps=[r for r in recs if r["ev"]=="snap"]; assert not any("nub-wake" in k for r in snaps for k in r["regs"]), "wake read in guest"
smc=[r for r in recs if r["ev"]=="smc-tx"][0]; assert smc["key"]=="MBSE" and smc["value"]=="77706c73", smc
pm=[r for r in recs if r["ev"]=="spmi-cmd" and r.get("label")=="pm_setting"][0]; assert pm["data"]=="07"
ps=[r for r in recs if r["ev"]=="mmio" and r.get("ps")]; assert ps and ps[0]["ps"]=="SIO_CPU", ps
print("mock test OK:", len(recs), "records ->", log)

# ---- scenario 2: S2R_CLUSTER=1 -> cpm blocks limited to their first page, no SError page traced
def run_scenario(env, regs):
    for k in ("S2R_STOP","S2R_CLUSTER"): os.environ.pop(k, None)
    os.environ.update(env)
    ADT["/arm-io/pmgr"].regs = regs
    h = FakeHV(); h.adt = Adt(ADT)
    lg = str(KIT / "work" / "mock-trace-2.jsonl"); pathlib.Path(lg).unlink(missing_ok=True); os.environ["S2R_LOG"]=lg
    g2 = runpy.run_path(str(KIT/"hv_s2r_trace.py"), init_globals={"hv": h}, run_name="<hv_script>")
    g2["s2r_arm"]("scenario")
    g2["S2R"].f.flush()
    pathlib.Path(lg).unlink(missing_ok=True)
    return h, g2
h2, g2 = run_scenario({"S2R_CLUSTER": "1"}, list(pm_regs))
cl = {k: v for k, v in h2.tracers.items() if str(v[3].get("region","")).startswith("cluster")}
assert (0x210e40000, 0x210e44000, "S2R-ARM") in cl and (0x211e40000, 0x211e44000, "S2R-ARM") in cl, cl.keys()
for (a, b, i) in h2.tracers:
    for pg in g2["FORBIDDEN_PAGES"]:
        assert not (a < pg + 0x4000 and pg < b), f"zone {a:#x}-{b:#x} overlaps SError page {pg:#x}"
assert 0x210e44000 in g2["FORBIDDEN_PAGES"] and 0x210e48000 in g2["FORBIDDEN_PAGES"] and 0x211e48000 in g2["FORBIDDEN_PAGES"]
print("scenario cluster=1 OK:", len(cl), "cluster zones, SError pages untraced")

# ---- scenario 3: a reordered ADT (reg[1] and reg[7] swapped) -> both zones refused, nothing at the wrong address
bad = list(pm_regs); bad[1], bad[7] = bad[7], bad[1]
h3, g3 = run_scenario({"S2R_CLUSTER": "1"}, bad)
names = [n for n, _ in g3["S2R"].refused]
assert "aon-pmgr" in names and "cluster[7]" in names, names
assert not any(a == 0x210e40000 and v[3].get("region") == "aon-pmgr" for (a, b, i), v in h3.tracers.items())
assert not any(b - a > 0x100000 for (a, b, i) in h3.tracers)
print("scenario wrong-ADT OK: refused", names)
ADT["/arm-io/pmgr"].regs = pm_regs
import subprocess; subprocess.run([sys.executable, "-I", str(KIT/"s2r_decode.py"), "summarize", log], check=True)
