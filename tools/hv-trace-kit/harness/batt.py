import sys, struct, time; sys.path.insert(0, "/home/naeem/m1n1/proxyclient")
from m1n1.setup import *
from m1n1.fw.smc import SMCClient, SMCError
smc = SMCClient(u, u.adt["arm-io/smc"].get_reg(0)[0]); smc.start(); smc.start_ep(0x20); smc.verbose = 0
ep = smc.epmap[0x20]
def rd(k):
    try:
        n, t, f = ep.get_key_info(k); return ep.read_type(k, n, t), t
    except Exception as e: return None, str(e)[:40]
print("time", time.strftime("%H:%M:%S"))
for k in ("B0RM", "B0FC", "B0AC", "B0AV", "B0CT", "BRSC", "CHLS", "AC-W", "D0VR", "PSTR", "PPBR", "PDTR", "PHPC", "PSBR"):
    v, t = rd(k); print("%s (%s) = %s" % (k, t, v))
smc.stop()
print("smc stopped")
