# hv script: instrumentation for the early-boot freezes of Linux guests (2026-11-16, lx5-lx8).
#   host:  kill -USR2 <run_guest pid> writes every host thread's Python stack to run-<tag>.out
#   M1:    with M1N1_HV_WDT_CPU=<n> (and run_guest -C without that CPU) m1n1's hypervisor
#          watchdog runs on CPU n; when the hypervisor stalls for over 1 s outside a host call it
#          barks, and the handler below prints each CPU's breadcrumbs and the hypervisor's lock and
#          rendezvous words, read over the proxy, before the panic shell.
# Symbols come from the running image's ELF (M1N1_ELF), offsets from p.get_base().
import faulthandler
import os
import signal
import subprocess
import sys

from m1n1.proxy import START
from m1n1.hv.types import HV_EVENT

faulthandler.register(signal.SIGUSR2, all_threads=True, file=sys.stderr)
print(f"[probe] kill -USR2 {os.getpid()} dumps the host's Python stacks")

_ELF = os.environ.get("M1N1_ELF", "/home/naeem/m1n1/build/m1n1-raw.elf")
_SYMTAB = {}
for _l in subprocess.run(["readelf", "-sW", _ELF], capture_output=True, text=True).stdout.splitlines():
    _f = _l.split()
    if len(_f) >= 8:
        try:
            _SYMTAB[_f[7]] = int(_f[1], 16)
        except ValueError:
            pass
_base = p.get_base()


def _addr(name):
    return _base + _SYMTAB[name]


def _crumbs(v):
    return bytes((v >> s) & 0xff for s in range(56, -8, -8)).replace(b"\0", b"").decode(errors="replace")


def probe_state(tag="manual"):
    bc = [p.read64(_addr("hv_wdt_breadcrumbs") + 8 * i) for i in range(8)]
    print(f"[probe] {tag}: breadcrumbs " + "  ".join(f"cpu{i}:{_crumbs(v) or '-'}" for i, v in enumerate(bc)))
    print(f"[probe] {tag}: hv_cpus_in_guest {p.read64(_addr('hv_cpus_in_guest')):#x} "
          f"hv_pinned_cpu {p.read32(_addr('hv_pinned_cpu')):#x} hv_want_cpu {p.read32(_addr('hv_want_cpu')):#x} "
          f"bhl {p.read64(_addr('bhl')):#x}")
    sys.stdout.flush()


_wdt = os.environ.get("M1N1_HV_WDT_CPU")
if _wdt is not None:
    hv.wdt_cpu = int(_wdt)
    _orig_bark = hv.handle_bark

    def _bark(reason, code, info):
        print("[probe] HV WATCHDOG BARK: the hypervisor stalled for over 1 s outside a host call")
        try:
            probe_state("bark")
        except Exception as e:
            print(f"[probe] state read failed: {e}")
        return _orig_bark(reason, code, info)

    hv.iface.set_handler(START.HV, HV_EVENT.WDT_BARK, _bark)
    print(f"[probe] hypervisor watchdog on CPU {hv.wdt_cpu} (1 s); breadcrumbs at {_addr('hv_wdt_breadcrumbs'):#x}")
