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
_CLKGEN = (0x23b040140, 0x23b040144, 0x23b040148, 0x23b04014c, 0x23b040154)  # muxes macOS parks (= 0x80100000) before the commit
def real_s2r_on(spin=0, alarm=0, mask=(), wake="reset"):
    p.write32(_A_CNT, 0); _slots.clear()
    try:
        # wake="proxy": the handler keeps the hypervisor image alive, restores these clkgen words,
        # powers the ATC0 USB path back up and runs the proxy (no guest entry yet)
        a = _base + _sym("hv_s2r_clkgen")
        vals = [p.read32(r) for r in _CLKGEN]
        for i, (r, v) in enumerate(zip(_CLKGEN, vals)):
            p.write64(a + 16 * i, r); p.write64(a + 16 * i + 8, v)
        # try53: macOS panicked at the wake on "Register is locked down! AccessType=Write
        # Address=0x23b040140": the clkgen muxes are lock-protected and the PMGR event log records
        # our restore. USB works with them parked (try49 probes), so in resume mode leave them to
        # macOS's own restoreClockConfig.
        p.write32(_base + _sym("hv_s2r_clkgen_count"), 0 if wake == "resume" else len(_CLKGEN))
        p.write32(_base + _sym("hv_s2r_wake_mode"), {"reset": 0, "proxy": 1, "resume": 1}[wake])
        if wake == "resume":
            # stage two: the host session survives the USB drop and re-enters the guest
            hv.s2r_resume_addr = _base + _sym("hv_s2r_resume_guest")
            hv.s2r_expected = True
            _path, hv.s2r_product = hv._s2r_find_m1n1_tty()
            import secrets as _sec
            hv.s2r_nonce = _sec.randbits(64) | 1
            hv.s2r_nonce_addr = _base + _sym("hv_s2r_nonce")
            p.write64(hv.s2r_nonce_addr, hv.s2r_nonce)
            print(f"[s2r-real] stage two armed: resume via {hv.s2r_resume_addr:#x}, flags {hv.s2r_resume_flags:#x}, device {hv.s2r_product!r}, nonce {hv.s2r_nonce:#x}")
        print(f"[s2r-real] wake mode {wake}; clkgen at arm: " + " ".join(f"{r:#x}={v:#x}" for r, v in zip(_CLKGEN, vals)))
    except KeyError:
        if wake != "reset":
            print("[s2r-real] this m1n1 build has no wake modes")
    try:
        p.write32(_base + _sym("hv_s2r_alarm_secs"), alarm)
        print(f"[s2r-real] RTC alarm at the commit: {'now + %d s' % alarm if alarm else 'left as macOS set it'}")
    except KeyError:
        pass
    try:
        # mask = AP wake-source numbers (ADT order, e.g. 81 = SMC.OutboxNotEmpty) to mask at the commit
        a = _base + _sym("hv_s2r_wake_mask_or")
        words = [0] * 5
        for s in mask:
            words[s // 32] |= 1 << (s % 32)
        for i, w in enumerate(words):
            p.write32(a + 4 * i, w)
        print(f"[s2r-real] wake sources masked at the commit: {list(mask)} -> words {[hex(w) for w in words]}")
    except KeyError:
        if mask:
            print("[s2r-real] this m1n1 build cannot mask wake sources")
    try:
        p.write32(_base + _sym("hv_s2r_spin_test"), 1 if spin else 0)
        print(f"[s2r-real] spin test {'ON: last core spins and counts 100 ms ticks into PMU scratch' if spin else 'off'}")
    except KeyError:
        print("[s2r-real] this m1n1 build has no spin test")
    wdt_state("at arm")
    try:
        import time as _t
        print(f"[s2r-real] CNTPCT at arm {u.mrs((3, 3, 14, 0, 1)):#x} host {_t.time():.3f}")
    except Exception as e:
        print("[s2r-real] CNTPCT read failed:", e)
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
