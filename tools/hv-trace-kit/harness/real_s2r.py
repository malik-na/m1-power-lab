# hv script: real_s2r_on() lets the guest's final sleep steps reach the hardware (m1n1 C side,
# commit "hv: real S2R pass-through"). Symbol offsets come from the chainloaded build's ELF.
import subprocess
import os
_ELF = os.environ.get("M1N1_ELF", "/home/naeem/m1n1/build/m1n1-raw.elf")
def _sym(name):
    out = subprocess.run(["readelf", "-sW", _ELF], capture_output=True, text=True).stdout
    for l in out.splitlines():
        f = l.split()
        if len(f) >= 8 and f[7] == name:
            return int(f[1], 16)
    raise KeyError(name)
_base = p.get_base()
_A_FLAG = _base + _sym("hv_real_s2r")
_A_CNT = _base + _sym("hv_s2r_deferred_count")
_A_ARR = _base + _sym("hv_s2r_deferred")
_slots = {}     # addr -> slot index in the C array (last value wins)
def _defer(addr, data):
    if addr not in _slots:
        if len(_slots) >= 16:
            print(f"[s2r-real] deferred list full, dropping {addr:#x}={data:#x}")
            return
        _slots[addr] = len(_slots)
        p.write64(_A_ARR + 16 * _slots[addr], addr)
    p.write64(_A_ARR + 16 * _slots[addr] + 8, data)
    p.write32(_A_CNT, len(_slots))
    print(f"[s2r-real] deferred PS write {addr:#x} = {data:#x} (slot {_slots[addr]})")
def wdt_state(tag=""):
    b = 0x23d2b0000
    print(f"[s2r-real] AON WDT {tag}: WD0 cnt/alarm/ctl {p.read32(b):#x}/{p.read32(b+4):#x}/{p.read32(b+0xc):#x}  "
          f"WD1 {p.read32(b+0x10):#x}/{p.read32(b+0x14):#x}/{p.read32(b+0x1c):#x}  WD2 {p.read32(b+0x20):#x}/{p.read32(b+0x24):#x}/{p.read32(b+0x2c):#x}  "
          f"extra 8008/800c/8020 {p.read32(0x23d2b8008):#x}/{p.read32(0x23d2b800c):#x}/{p.read32(0x23d2b8020):#x}  s2r-timer {p.read32(0x23d2c4000):#x}")
def real_s2r_on(spin=0, alarm=0):
    p.write32(_A_CNT, 0); _slots.clear()
    try:
        p.write32(_base + _sym("hv_s2r_alarm_secs"), alarm)
        print(f"[s2r-real] RTC alarm at the commit: {'now + %d s' % alarm if alarm else 'left as macOS set it'}")
    except KeyError:
        pass
    try:
        p.write32(_base + _sym("hv_s2r_spin_test"), 1 if spin else 0)
        print(f"[s2r-real] spin test {'ON: last core spins and counts 100 ms ticks into PMU scratch' if spin else 'off'}")
    except KeyError:
        print("[s2r-real] this m1n1 build has no spin test")
    wdt_state("at arm")
    hv.real_s2r_defer = _defer
    # the guest believes these hooked domains hold its last requested values: apply them at the
    # commit, like aura does (its commit 1820814), so the USB/UART/SIO domains really go down
    for addr in getattr(hv, "_pmgr_hooked", []):
        if addr in hv._pmgr_requested:
            _defer(addr, hv._pmgr_requested[addr])
    p.write32(_A_FLAG, 1)
    rv = p.read64(0x210050000)
    print(f"[s2r-real] cpu0 RVBAR reg {rv:#x} ({'locked' if rv & 1 else 'unlocked'}); this image base {_base:#x}; "
          f"{'wake lands in THIS image' if (rv & 0xffffffffffff & ~0xfff) == _base else 'wake lands ELSEWHERE'}")
    p.call(_base + _sym("hv_s2r_register_wake"))
    print(f"[s2r-real] ON: flag {_A_FLAG:#x} = {p.read32(_A_FLAG)}, base {_base:#x}, {len(_slots)} PS words queued, wake handler registered")
print("[s2r-real] real_s2r_on() defined")
