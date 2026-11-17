#!/usr/bin/env python3
"""Detached mode, host side, step 2 of 2: take the hypervisor back and read its log out.

ORDER OF USE (step 1 is detach() from harness/detach.py; read its docstring first)
  1. The cable is back in and the M1's proxy port is listed again (harness/m1dev.sh: m1dev).
     Nothing else may hold the port (harness/stop.sh, then no run script).
  2. Run this, with the build the M1 is running:
       source harness/m1dev.sh
       M1N1DEVICE=$(m1dev) M1N1_ELF=~/m1n1-next/build/m1n1-raw.elf \\
         venv/bin/python harness/detach_readout.py -o runs/<dir>/detached-<tag>.jsonl
     It opens the port, sends the interrupt byte ("!", what Ctrl-C sends), waits for the
     hypervisor to enter its proxy, reads the control block and the log, and writes JSON lines.
  3. What happens to the Mac afterwards is your choice, stated on the command line:
       (nothing)    the guest stays stopped inside the hypervisor's proxy; macOS is frozen.
                    The log stays in RAM: this tool can be run again.
       --continue   re-arm detached mode and let macOS run on (the log keeps filling; the
                    cable can come out again). Only after a clean interrupt, not when the
                    hypervisor had stopped at an exit it could not handle.
       --reboot     reboot the Mac (the log in RAM is gone after that).

OUTPUT, one JSON object per line
  {"ev":"readout", ...}   first line: counters, state, what stopped the guest (if anything)
  {"addr","w","data","width","pc","cpu","ev":"acc","t"}   every device access, the keys of
                          hv_touch_map.py's records; "width" is log2 of the bytes; "t" is seconds
                          from the first "detached" marker, from the M1's own timer at the access
  markers, each its own "ev": detached, core-down, last-core-down, snap (tag "commit": the
  words read by the last core before the hypervisor's own commit actions; tag "wake"),
  commit-write (a word the hypervisor wrote for the guest at the commit), wake, wake-reg,
  resume, secondary, host, unhandled / unhandled-what / unhandled-hook, and the exits the
  hypervisor handled by itself: pmgr, cpustart, sysreg, amcc, const, brk-lowered.
Whether the M1's timer counts through a sleep is not known: compare "t" of last-core-down and
wake with the wall clock.

This tool never imports m1n1.setup and never builds a ProxyUtils: that would hand out the host
heap again, where the log lives.
"""
import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detached_fmt as F      # noqa: E402

CHUNK = 1 << 20


def read_log(readmem, ctl, progress=None):
    """All stored entries, in order, as raw bytes."""
    left = min(ctl.get("log_total"), ctl.get("log_cap"))
    raw = bytearray()
    for i in range(min(ctl.get("nseg"), F.MAX_SEG)):
        base, cap = ctl.get("seg", i)
        size = min(left, cap) * F.ENTRY.size
        for off in range(0, size, CHUNK):
            raw += readmem(base + off, min(CHUNK, size - off))
            if progress:
                progress(len(raw))
        left -= min(left, cap)
    return bytes(raw)


def header(ctl, start, kept):
    total, cap = ctl.get("log_total"), ctl.get("log_cap")
    stop = dict(zip(F.STOP_FIELDS, ctl.get("stop", 0)))
    stopped = bool(ctl.get("flags") & F.FLAG_STOPPED)
    return {
        "ev": "readout", "host_time": round(time.time(), 3),
        "entries": kept, "offered": total, "dropped": max(0, total - cap), "capacity": cap,
        "cntfrq": ctl.get("cntfrq"), "t_detach_tick": ctl.get("t_detach"),
        "state": F.STATES.get(ctl.get("state"), str(ctl.get("state"))),
        "entered_proxy_as": F.stop_reason(*start) if start else None,
        "stopped_unhandled": stopped,
        "stop": ({"what": F.stop_reason(stop["reason"], stop["code"]),
                  **{k: "%#x" % stop[k] for k in ("esr", "elr", "far", "spsr", "hook_addr")},
                  "cpu": stop["cpu"]} if stopped else None),
        "resumed_after_a_wake": bool(ctl.get("resumed")),
        "handled": dict(zip(F.COUNT_NAMES, ctl.get("count"))),
        "commit_snapshot_words": ctl.get("ncsnap"), "sysreg_all": bool(ctl.get("flags") & F.FLAG_SR_ALL),
        "stray_bytes": ctl.get("stray"), "deferred_dropped": ctl.get("deferred_dropped"),
    }


def write_jsonl(out, head, raw, ctl, snap_names=None):
    """Returns (records written, t of the first and last record, monotonic?)."""
    entries = (F.decode_entry(raw[i:i + F.ENTRY.size]) for i in range(0, len(raw), F.ENTRY.size))
    t0 = ctl.get("t_detach")
    frq = ctl.get("cntfrq") or 24000000
    out.write(json.dumps(head) + "\n")
    n, first, last, mono = 0, None, None, True
    for rec in F.records(entries, t0, frq, snap_names):
        out.write(json.dumps(rec) + "\n")
        n += 1
        first = rec["t"] if first is None else first
        # entries are numbered before they are stamped: neighbours from two cores may swap
        if last is not None and rec["t"] < last - 0.001:
            mono = False
        last = rec["t"]
    return n, first, last, mono


def wait_for_proxy(iface, seconds):
    """Send the interrupt byte until the hypervisor announces its proxy. Returns
    (reason, code) of the announcement, or None if none came (it may be in the proxy already)."""
    from m1n1.proxy import UartError
    deadline = time.time() + seconds
    iface.dev.timeout = 1
    while time.time() < deadline:
        iface.dev.write(b"!")
        try:
            data = iface.reply(iface.REQ_BOOT)
        except UartError:
            continue
        reason, code, _info = struct.unpack("<IIQ", data[:16])
        return reason, code
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=time.strftime("detached-%Y%m%d-%H%M%S.jsonl"),
                    help="JSON lines output (default: detached-<time>.jsonl here)")
    ap.add_argument("--raw", help="also save the raw control block and log entries to this file")
    ap.add_argument("--from-raw", help="no Mac: decode a file saved with --raw (either layout) to -o")
    ap.add_argument("--device", default=None, help="proxy tty (default: $M1N1DEVICE)")
    ap.add_argument("--elf", default=F.elf_path(), help="m1n1-raw.elf of the build on the M1 ($M1N1_ELF)")
    ap.add_argument("--proxyclient", default=os.environ.get("M1N1_PROXYCLIENT", "/home/naeem/m1n1/proxyclient"),
                    help="m1n1 proxyclient directory to import (default: ~/m1n1/proxyclient)")
    ap.add_argument("--wait", type=float, default=30, help="seconds to wait for the proxy (default 30)")
    ap.add_argument("--snap-list", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "../../../var/recfg/commit-snap-list-wide.json"),
                    help="[[address, name], ...] to name the words of the wake snapshot")
    end = ap.add_mutually_exclusive_group()
    end.add_argument("--continue", dest="cont", action="store_true",
                     help="afterwards: re-arm detached mode and let the guest run on")
    end.add_argument("--reboot", action="store_true", help="afterwards: reboot the Mac")
    ap.add_argument("--force-continue", action="store_true",
                    help="--continue although this run did not see the hypervisor enter its proxy "
                         "(only if an earlier run of this tool reported a user interrupt and "
                         "nothing has talked to the M1 since)")
    args = ap.parse_args(argv)

    names = {}
    try:
        names = {int(addr): name for addr, name in json.load(open(args.snap_list))}
    except (OSError, ValueError):
        pass
    if args.from_raw:
        blob = open(args.from_raw, "rb").read()
        size = struct.unpack_from("<Q", blob, 8)[0]
        if size not in (F.SIZE, F.SIZE_V1):
            sys.exit("%s: control block of %d bytes is neither layout" % (args.from_raw, size))
        ctl, raw = F.Ctl.unpack(blob[:size]), blob[size:]
        head = header(ctl, None, len(raw) // F.ENTRY.size)
        with open(args.out, "w") as out:
            print("%s: %d records" % (args.out, write_jsonl(out, head, raw, ctl, names)[0]))
        return

    sym = F.symbols(args.elf, ("hv_detached_ctl", "hv_detached_info", "hv_detached_arm", "hv_detached"))
    if sym["hv_detached_ctl"][1] != F.SIZE:
        sys.exit("%s: control block is %d bytes, this tool's layout is %d" % (
            args.elf, sym["hv_detached_ctl"][1], F.SIZE))

    sys.path.insert(0, args.proxyclient)
    from m1n1.proxy import UartInterface, M1N1Proxy, EXC_RET

    iface = UartInterface(args.device)
    time.sleep(0.3)
    start = wait_for_proxy(iface, args.wait)
    iface.dev.timeout = 3
    if start is None:
        print("no proxy announcement in %g s; trying the proxy anyway (it may be open already)" % args.wait)
    else:
        print("hypervisor entered its proxy: %s" % F.stop_reason(*start))
    iface.nop()             # also turns data checksums off for the transfers below
    p = M1N1Proxy(iface)
    base = p.get_base()

    info = struct.unpack("<2Q", iface.readmem(base + sym["hv_detached_info"][0], 16))
    a, n = sym["hv_detached_arm"]
    if info != (F.MAGIC, F.SIZE) or iface.readmem(base + a, n) != F.image_bytes(args.elf, a, n):
        sys.exit("the m1n1 answering at base %#x is not the build %s (info words %#x/%d): "
                 "nothing read, nothing changed" % (base, args.elf, info[0], info[1]))

    ctl_blob = iface.readmem(base + sym["hv_detached_ctl"][0], F.SIZE)
    ctl = F.Ctl.unpack(ctl_blob)
    if ctl.get("magic") != F.MAGIC:  # (an image of the first layout is refused above: info words)
        sys.exit("the control block was never set up (magic %#x): detach() did not run on this image"
                 % ctl.get("magic"))
    armed = p.read32(base + sym["hv_detached"][0])
    kept = min(ctl.get("log_total"), ctl.get("log_cap"))
    print("log: %d entries kept of %d offered (%d dropped), %d MiB to read" % (
        kept, ctl.get("log_total"), max(0, ctl.get("log_total") - ctl.get("log_cap")),
        kept * F.ENTRY.size >> 20), flush=True)
    t_read = time.time()
    raw = read_log(iface.readmem, ctl,
                   lambda done: print("\r  %d MiB" % (done >> 20), end="", flush=True))
    print("\r  read in %.1f s" % (time.time() - t_read))
    if args.raw:
        with open(args.raw, "wb") as f:
            f.write(ctl_blob + raw)

    head = header(ctl, start, kept)
    head["detached_flag_at_readout"] = armed
    with open(args.out, "w") as out:
        nrec, first, last, mono = write_jsonl(out, head, raw, ctl, names)
    print("%s: %d records, t %s .. %s s from the detach marker%s" % (
        args.out, nrec, first, last, "" if mono else " (NOT monotonic: the timer restarted?)"))
    print("state %s; handled by the hypervisor alone: %s" % (head["state"], head["handled"]))
    if head["stopped_unhandled"]:
        print("THE GUEST WAS STOPPED at an exit nothing handled: %s" % head["stop"])

    if args.reboot:
        print("rebooting the Mac")
        p.reboot()
    elif args.cont:
        if head["stopped_unhandled"]:
            sys.exit("not continuing: the guest is stopped at an unhandled exit; it would stop there again")
        if armed:
            sys.exit("not continuing: the hypervisor still reads as detached (flag %d)" % armed)
        if start != (3, 3) and not args.force_continue:      # START.HV / HV_EVENT.USER_INTERRUPT
            sys.exit("not continuing: this run did not see the hypervisor enter its proxy for a "
                     "user interrupt (saw %s). See --force-continue." % (start,))
        r = p.call(base + a, F.MAGIC, F.SIZE)
        if r != 0:
            sys.exit("hv_detached_arm refused (%d): the guest stays stopped in the proxy" % r)
        p.exit(EXC_RET.HANDLED)
        print("DETACHED again: the guest runs on with no host; the cable can come out")
    else:
        print("the guest stays stopped in the hypervisor's proxy (macOS frozen). "
              "Run again with --continue or --reboot, or leave it.")
    iface.dev.close()


if __name__ == "__main__":
    main()
