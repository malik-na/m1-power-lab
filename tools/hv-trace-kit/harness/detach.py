# hv script: detach(): let the hypervisor run the guest with NO host, the cable out.
"""Detached mode, host side, step 1 of 2 (step 2 is harness/detach_readout.py).

Needs an m1n1 built from ~/m1n1-next (branch m1power/hv-detached) running on the M1, and
M1N1_ELF pointing at that build's m1n1-raw.elf (the symbols are read from it).

ORDER OF USE
  1. macOS up on that build with the real sleep armed and full logging on, as for any run of a
     chainloaded build (harness/macos-up.sh <tag> does all of it: fresh proxy, chainload.py -r
     ~/m1n1-next/build/m1n1.bin, go135.sh with M1N1_ELF and the touch map, drive135.sh:
     watchdog off, real_s2r_on(wake="resume")). Let macOS reach the state you want.
  2. harness/detach135.sh <tag>
     It puts these two lines into the hypervisor shell's FIFO and interrupts the guest once:
       run_script("<kit>/harness/detach.py")
       detach()
     detach() copies the host's live tables into the hypervisor, gives it a log buffer in the
     M1's RAM, arms detached mode, lets the guest run again and ENDS THIS HOST PROCESS
     (os._exit: nothing more is sent to the Mac). When it prints "DETACHED" the cable can come
     out. go135.sh then ends by itself and stops its console reader.
  3. Unplug. Click Sleep. Wait. Press a key. Watch it wake. Plug the cable back in.
  4. venv/bin/python harness/detach_readout.py -o <file>.jsonl      (see its --help)

detach(leave=True, mb=None, m1n1_mb=0, skip="", force=False, snap=True,
       commit_snap=<var/recfg/commit-snap-list-wide.json>, commit_delay_us=0, sysreg_all=False)
  leave=False  only arm; this process stays. Then end the shell with EOF (the guest runs on,
               detached) and stop the host side with SIGTERM (harness/stop.sh). NEVER Ctrl-C /
               SIGINT / cont-and-interrupt afterwards: the interrupt byte is what ends detached
               mode. (detach() disables this process's own senders of that byte.)
  mb           size of the log in MiB (default: all of the host-side heap that is free, about
               120 MiB = 3.9 million entries of 32 bytes). When full, the first entries are kept
               and the rest are counted.
  m1n1_mb      extra log space taken from m1n1's own heap (untested; default none).
  skip         "0xSTART+0xSIZE,..." handed to the touch map's go_full() when detach() has to
               switch it to full logging: ranges left unlogged (the PMP doorbell page, say).
  force        arm even if a check below fails (each failure means: that exit will stop the
               guest with an "unhandled" marker instead of being handled).
  snap         take the touch map's 793-word snapshot ("pre-detach") first, and have the
               hypervisor read the power-manager/always-on words of that list at the wake.

  commit_snap  JSON [[address, name], ...] (up to 1024 words): read by the last core when it goes
               down for the sleep, before the hypervisor's own commit actions ("snap" record,
               tag "commit"). None: no commit snapshot.
  commit_delay_us  wait this long on the last core before the first read (default 0: the other
               cores have made their last register write but may not have powered off yet).
  sysreg_all   log every system register access the hypervisor sees, from now on. Default: the
               ones the host's rules decide are always logged; the ones the C side handles by
               itself only from the first core's stop bit of a sleep until the wake.

What the hypervisor then does by itself (src/hv/hv_detached.c): the power-manager hooks, the CPU
start/stop word, the system registers, the memory-protection lock words, the constant
power-gate words, BRK lowering, the wake (re-enters the guest), and the log. An exit it has no
handler for stops the guest with a marker until a host connects.
"""
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detached_fmt as _F      # noqa: E402

_WDT = 0x23d2b0000


def _closure(fn):
    if fn is None or not getattr(fn, "__closure__", None):
        return {}
    return dict(zip(fn.__code__.co_freevars, (c.cell_contents for c in fn.__closure__)))


def _hooks(hv):
    """Sort hv.vm_hooks (map_hook) into the kinds the hypervisor handles. Returns
    (pmgr shadow dict, pmgr addresses, constants {addr: value}, cpustart bases, unknown)."""
    shadow, pmgr, consts, cpustart, unknown = None, [], {}, [], []
    for idx, h in enumerate(hv.vm_hooks):
        if h is None:
            continue
        rd, wr, ipa, _kw = h
        cv = {}
        cv.update(_closure(rd))
        cv.update(_closure(wr))
        if rd is not None and wr is not None and "_pmgr" in cv:
            shadow = cv["_pmgr"]
            pmgr.append(ipa)
        elif rd is None and wr is not None and wr.__name__ == "cpustart_wh":
            cpustart.append(ipa)
        elif rd is not None and wr is None and "pg_overrides" in cv and ipa in cv["pg_overrides"]:
            consts[ipa] = cv["pg_overrides"][ipa]
        else:
            unknown.append("vm hook %d at %#x (%s/%s)" % (
                idx, ipa, getattr(rd, "__qualname__", None), getattr(wr, "__qualname__", None)))
    return shadow, pmgr, consts, cpustart, unknown


def _tracers(hv):
    """Trace mappings the hypervisor cannot serve alone: a HOOK-mode tracer that is not the
    lock-word emulation runs host code per access."""
    from m1n1.hv import TraceMode
    bad = []
    for zone, maps in hv.mmio_maps.items():
        if not maps:
            continue
        mode, ident = max(((m[0], m[1]) for m in maps.values()), key=lambda m: (int(m[0]), m[1]))
        if mode == TraceMode.HOOK and ident not in ("XNU AMCC", "SPTM AMCC"):
            bad.append("HOOK tracer %s at %#x..%#x" % (ident, zone.start, zone.stop))
    return bad


def _sysregs(hv):
    """The tables of HV.handle_msr: (rows for the action table, shadowed encodings)."""
    import m1n1.sysreg as sr
    enc = lambda reg: _F.sysreg_enc(*sr.sysreg_parse(reg))
    shadow = {sr.VMSA_LOCK_EL1}
    if getattr(hv, "xnu_amcc", None) is not None:
        shadow |= {(3, 4, 15, 2, 2), (3, 4, 15, 2, 3), (3, 4, 15, 2, 4), (3, 4, 15, 2, 5)}
    for i in range(len(hv._bps)):
        shadow |= {sr.DBGBCRn_EL1(i), sr.DBGBVRn_EL1(i)}
    for i in range(len(hv._wps)):
        shadow |= {sr.DBGWCRn_EL1(i), sr.DBGWVRn_EL1(i)}
    shadow = sorted(tuple(sr.sysreg_parse(s)) for s in shadow)
    redirects = {tuple(sr.sysreg_parse(k)): tuple(sr.sysreg_parse(v)) for k, v in hv.MSR_REDIRECTS.items()}
    actions = {tuple(sr.sysreg_parse(r)): _F.SR_RO for r in (sr.ACC_CFG_EL1, sr.ACC_OVRD_EL1)}
    actions[tuple(sr.sysreg_parse(sr.DC_CIVAC))] = _F.SR_XLATE
    rows = []
    for reg in sorted(set(actions) | set(redirects)):
        rows.append((enc(reg), actions.get(reg, _F.SR_PASS), enc(redirects.get(reg, reg))))
    return rows, shadow


_COMMIT_SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "../../../var/recfg/commit-snap-list-wide.json")


def build(hv, u, segs, snap_addrs=(), commit_addrs=(), commit_delay_us=0, sysreg_all=False):
    """The control block from the live host state. Returns (Ctl, problems, notes)."""
    c, problems, notes = _F.Ctl(), [], []
    c.set("magic", _F.MAGIC)
    c.set("size", _F.SIZE)
    c.set_table("nseg", "seg", segs)

    # kind 1: power-manager hooks; plus the constant power-gate words; kind 2: CPU start/stop
    shadow, pmgr, consts, cpustart, unknown = _hooks(hv)
    problems += unknown
    if shadow is None:
        problems.append("no power-manager hook found in hv.vm_hooks")
        shadow = {}
    if sorted(pmgr) != sorted(getattr(hv, "_pmgr_hooked", [])):
        problems.append("power-manager hooks %s differ from hv._pmgr_hooked" % [hex(a) for a in pmgr])
    req = getattr(hv, "_pmgr_requested", {})
    c.set_table("npmgr", "pmgr", [(a, shadow.get(a, 0), int(a in shadow), req.get(a, 0), int(a in req))
                                  for a in pmgr])
    c.set_table("nconst", "konst", sorted(consts.items()))
    if len(cpustart) == 1:
        c.set("cpustart_base", cpustart[0])
        c.set("cpustart_size", 0x20)
    else:
        problems.append("%d CPU start blocks hooked, the hypervisor handles one" % len(cpustart))
    cpus = []
    for node in hv.adt["cpus"]:
        cpus.append((node.reg, node.cpu_id, node.cpu_impl_reg[0]))
    c.set_table("ncpu", "cpu", cpus)

    # the wake: HV.s2r_resume / start_secondary
    reset_pc = getattr(hv, "s2r_guest_reset_pc", None)
    c.set("entry_page", hv.entry & ~0xfff)
    c.set("guest_reset_pc", reset_pc or 0)
    c.set("resume_flags", hv.s2r_resume_flags)
    c.set("resumed", int(bool(getattr(hv, "s2r_resumed", False))))
    if reset_pc is None:
        notes.append("no secondary was started yet: the wake re-enters at hv.entry's page %#x" % (hv.entry & ~0xfff))

    # kind 3: system registers
    rows, shadowed = _sysregs(hv)
    c.set_table("nsysreg", "sysreg", rows)
    if len(shadowed) > _F.MAX_SHADOW:
        raise ValueError("%d shadowed registers, the hypervisor's table holds %d" % (len(shadowed), _F.MAX_SHADOW))
    c.set("nshadow", len(shadowed))
    for i, reg in enumerate(shadowed):
        c.set("shadow_enc", _F.sysreg_enc(*reg), i)
    for cpu, regs in hv.sysreg.items():
        if not 0 <= cpu < _F.MAX_CPUS:
            continue
        row = [0] * _F.MAX_SHADOW
        for reg, val in regs.items():
            reg = tuple(reg)
            if reg in shadowed:
                row[shadowed.index(reg)] = val
        c.set("shadow", row, cpu)

    # kind 4: memory-protection lock words (VirtualAMCC)
    amcc = []
    for name in ("xnu_amcc", "sptm_amcc"):
        obj = getattr(hv, name, None)
        for addr, reg in sorted(obj.registers.items()) if obj is not None else ():
            amcc.append((addr, reg.write_mask, reg.override_mask, reg.override,
                         reg.value or 0, int(reg.value is not None)))
    c.set_table("namcc", "amcc", amcc)

    problems += _tracers(hv)
    c.set_table("nsnap", "snap", list(snap_addrs)[:_F.MAX_SNAP])
    commit_addrs = list(commit_addrs)
    if len(commit_addrs) > _F.MAX_CSNAP:
        notes.append("commit snapshot list cut from %d to %d words" % (len(commit_addrs), _F.MAX_CSNAP))
    c.set_table("ncsnap", "csnap", commit_addrs[:_F.MAX_CSNAP])
    c.set("csnap_delay_us", commit_delay_us)
    c.set("flags", _F.FLAG_SR_ALL if sysreg_all else 0)
    return c, problems, notes


def _wake_snap_addrs(tm):
    """The words the touch map reads at a wake (power manager, always-on, clocks)."""
    if tm is None or not getattr(tm, "snap_list", None):
        return []
    return [a for a, _n in tm.snap_list
            if 0x23b000000 <= a < 0x23b800000 or 0x23d000000 <= a < 0x23d300000]


def detach(leave=True, mb=None, m1n1_mb=0, skip="", force=False, snap=True,
           commit_snap=_COMMIT_SNAP, commit_delay_us=0, sysreg_all=False):
    import json
    commit_addrs = [int(a) for a, _n in json.load(open(commit_snap))] if commit_snap else []
    g = globals()
    hv, p, u, iface = g["hv"], g["p"], g["u"], g["iface"]
    say = lambda s: print("[detach] " + s, flush=True)
    if hv.ctx is None or not hv.started:
        raise RuntimeError("detach() is for the hypervisor shell of a running, paused guest")

    # 1. is the image on the M1 the build whose symbols we have?
    elf = _F.elf_path()
    sym = _F.symbols(elf, ("hv_detached_ctl", "hv_detached_info", "hv_detached_arm", "hv_detached",
                           "hv_real_s2r", "hv_s2r_wake_mode"))
    base = p.get_base()
    info = (p.read64(base + sym["hv_detached_info"][0]), p.read64(base + sym["hv_detached_info"][0] + 8))
    if info != (_F.MAGIC, _F.SIZE) or sym["hv_detached_ctl"][1] != _F.SIZE:
        raise RuntimeError("the running m1n1 is not %s, or its control block is not this tool's layout "
                           "(read %#x/%d, ELF %d, tool %#x/%d). Chainload that build first." % (
                               elf, info[0], info[1], sym["hv_detached_ctl"][1], _F.MAGIC, _F.SIZE))
    a, n = sym["hv_detached_arm"]
    if iface.readmem(base + a, n) != _F.image_bytes(elf, a, n):
        raise RuntimeError("hv_detached_arm on the M1 differs from %s: not the same build" % elf)
    ctl_addr, arm_addr = base + sym["hv_detached_ctl"][0], base + a
    if p.read32(base + sym["hv_detached"][0]):
        raise RuntimeError("detached mode is already armed")

    # 2. can the hypervisor serve everything the host serves now? (before anything is changed)
    tm = g.get("touch_map")
    _c, problems, _notes = build(hv, u, [(0, 0)])
    for s in problems:
        say("NOT HANDLED DETACHED: " + s)
    if problems and not force:
        raise RuntimeError("%d thing(s) the hypervisor cannot handle alone (above); detach(force=True) "
                           "arms anyway" % len(problems))

    # 3. no clock of this process may send the interrupt byte from here on; full logging
    signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    if tm is not None:
        t = getattr(tm, "tick", None)
        if t is not None:
            t.stop()
        if snap:
            try:
                tm.snapshot("pre-detach")
            except Exception as e:
                say("snapshot failed: %r" % (e,))
        if not tm.full:
            tm.go_full(skip)
        elif skip:
            say("the touch map is in full mode already: skip=%r not applied" % skip)
    hv.pt_update()

    # 4. the log buffer: host-side heap (RAM the guest does not have), optionally m1n1's heap
    heap = u.heap
    free = max([nb for nb, used in heap.blocks if not used] or [0]) * heap.block
    size = (free - (2 << 20) if mb is None else mb << 20) & ~0x3fff
    if size < (1 << 20):
        raise RuntimeError("no room for a log: %d bytes free in the host-side heap" % free)
    segs = [(heap.memalign(0x4000, size), size // _F.ENTRY.size)]
    if m1n1_mb:
        extra = p.memalign(0x4000, m1n1_mb << 20)
        if extra:
            segs.append((extra, (m1n1_mb << 20) // _F.ENTRY.size))
        else:
            say("m1n1 could not give %d MiB of its heap: log stays at %d MiB" % (m1n1_mb, size >> 20))

    # 5. the tables
    c, problems, notes = build(hv, u, segs, _wake_snap_addrs(tm) if snap else (), commit_addrs,
                               commit_delay_us, sysreg_all)
    s2r = getattr(hv, "real_s2r_defer", None) is not None and getattr(hv, "s2r_expected", False)
    flag, mode = p.read32(base + sym["hv_real_s2r"][0]), p.read32(base + sym["hv_s2r_wake_mode"][0])
    if not (s2r and flag == 1 and mode == 1):
        notes.append("real sleep is NOT armed for a resume (real_s2r_on(wake=\"resume\") not called: "
                     "host %s, hv_real_s2r %d, wake mode %d): a Sleep while detached stops the guest "
                     "with an 'unhandled' marker" % (s2r, flag, mode))
    wd = p.read32(_WDT + 0x1c)
    if wd & 4:
        notes.append("watchdog 1 is ARMED (ctl %#x, alarm %d s): it will reset the Mac; "
                     "p.write32(%#x, 0) first" % (wd, p.read32(_WDT + 0x14) // 24000000, _WDT + 0x1c))
    for s in notes:
        say("note: " + s)
    if problems and not force:
        raise RuntimeError("after the switch to full logging: " + "; ".join(problems))

    blob = c.pack()
    iface.writemem(ctl_addr, blob)
    if iface.readmem(ctl_addr, len(blob)) != blob:
        raise RuntimeError("control block did not read back as written")
    say("tables: %d power-manager words, %d constants, CPU start block %#x, %d cores, %d lock words, "
        "%d register rules, %d shadowed registers, %d wake-snapshot words, %d commit-snapshot words%s" % (
            c.get("npmgr"), c.get("nconst"), c.get("cpustart_base"), c.get("ncpu"), c.get("namcc"),
            c.get("nsysreg"), c.get("nshadow"), c.get("nsnap"), c.get("ncsnap"),
            "; every register access logged" if sysreg_all else ""))
    say("log: %s = %d entries (%d MiB); wake re-enters at %#x, flags %#x" % (
        " + ".join("%#x" % b for b, _ in segs), sum(n for _, n in segs),
        sum(n for _, n in segs) * _F.ENTRY.size >> 20,
        c.get("guest_reset_pc") or c.get("entry_page"), c.get("resume_flags")))

    # 6. arm. From here the guest's console and this process's Ctrl-C do not reach the Mac.
    if leave:
        hv._commit_context()
    for f in (sys.stdout, getattr(hv.print_tracer, "log_file", None), getattr(tm, "f", None)):
        try:
            f.flush()
        except Exception:
            pass
    old_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    hv.interrupt = lambda: None
    try:
        r = p.call(arm_addr, _F.MAGIC, _F.SIZE)
        if r != 0:
            raise RuntimeError("hv_detached_arm refused (%d): not armed" % r)
    except BaseException:
        del hv.interrupt            # still attached: Ctrl-C works as before
        signal.signal(signal.SIGINT, old_sigint)
        raise
    if not leave:
        say("ARMED. End this shell with EOF (the guest then runs detached), stop the host side "
            "with SIGTERM (harness/stop.sh), never with Ctrl-C. Then the cable can come out.")
        return
    from m1n1.proxy import EXC_RET
    p.exit(EXC_RET.HANDLED)
    try:
        iface.dev.close()
    except Exception:
        pass
    say("DETACHED: the guest runs on with no host. The cable can come out now. "
        "Afterwards: harness/detach_readout.py")
    sys.stdout.flush()
    os._exit(0)


print("[detach] detach() defined (build: %s)" % _F.elf_path())
