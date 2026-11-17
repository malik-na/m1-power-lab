# hv script (run_guest -m): which device pages does the guest touch, and when?
#
# The S2R tracer watches the register zones it was told to watch. This watches all of them: every
# page of the SoC's device space (the /arm-io ranges the hypervisor maps as hardware) is trapped;
# the first access to a page in an epoch is recorded (time, address, read or write, value, pc,
# cpu) and the page is handed back to the hardware, so each page costs one trap per epoch.
# Every S2R_TOUCH_EPOCH seconds (default 10) the pages touched in the last epoch are trapped
# again: the output is, per epoch, the set of device pages the guest used. Pages the hypervisor
# keeps for itself (its virtual UART, its own hooks) are listed as held and cannot be seen.
#
# Use it INSTEAD of hv_s2r_trace.py (S2R_TRACER=<this file> with harness/golinux.sh or go135.sh):
# two tracers on one page have not been tried. Epochs are advanced by any trap after the epoch's
# end, and by a clock (hv_tick.py) so a quiet guest still gets them.
#   S2R_TOUCH_LOG    output, JSON lines (default touch-<pid>.jsonl in the run directory)
#   S2R_TOUCH_EPOCH  seconds per epoch (default 10; 0 = one epoch, never re-arm)
#   S2R_TOUCH_TICK   ms between clock ticks (default 1000; 0 = no clock)
#   S2R_TOUCH_FULL   ranges logged in full instead: "0xSTART+0xSIZE,..." Every access to them is
#                    recorded with its value ({"ev":"acc",...}), in the hypervisor's asynchronous
#                    mode (m1n1 performs the access itself, the guest does not wait for this Mac).
#   S2R_TOUCH_CTL    a control file read at each clock tick (then removed). One command per line:
#                      snap <tag>   read the snapshot list now
#                      full [0xSTART+0xSIZE,...]   snapshot "pre-full", then log EVERY access to
#                                   the whole device space (the listed ranges excepted: they are
#                                   handed back to the hardware unlogged), and stop the clock: no
#                                   byte goes to the Mac from then on, so a real sleep is safe.
#   S2R_TOUCH_SNAP   the snapshot list, JSON [[address, name], ...]
#                    (default var/recfg/commit-snap-list-wide.json, 793 words)
# Snapshots are also taken by themselves when the last guest CPU goes down for sleep
# ("last-cpu") and, after a real sleep, before the guest is entered again ("wake": power
# manager, always-on and clock words only; other blocks may not be powered yet).
# A full log has the order of accesses exactly; "t" is when this Mac received the record, so
# times are good to the USB link's buffering, not to the access.
# Records: {"ev":"zone",...} what is trapped / held at start; {"ev":"touch","epoch","t","addr",
# "w","data","width","pc","cpu"}; {"ev":"epoch","epoch","t","pages"} at each re-arm.
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hv_tick as _TICK
from m1n1.hv import TraceMode
from m1n1.utils import irange

PAGE = 0x4000
IDENT = "TOUCH"


class TouchMap:
    def __init__(self, hv):
        self.hv = hv
        self.t0 = time.time()
        self.epoch_len = float(os.environ.get("S2R_TOUCH_EPOCH", "10"))
        self.f = open(os.environ.get("S2R_TOUCH_LOG", "touch-%d.jsonl" % os.getpid()), "a", buffering=1)
        self.epoch = 0
        self.epoch_t = self.t0
        self.touched = []           # pages touched in this epoch, to trap again
        self.total = 0
        self.zones = []             # what this tracer traps: (start, size)
        self.full = False
        self.ctl = os.environ.get("S2R_TOUCH_CTL", "")
        self.snap_list = None
        self._install()
        self._hooks()
        ms = int(os.environ.get("S2R_TOUCH_TICK", "1000"))
        if ms > 0 and self.epoch_len > 0:
            from m1n1.proxy import START, EXC_RET
            from m1n1.hv.types import HV_EVENT
            self.tick = _TICK.Tick(hv, self._tick, ms / 1000.0, EXC_RET.HANDLED,
                                   lambda fn: hv.iface.set_handler(START.HV, HV_EVENT.USER_INTERRUPT, fn),
                                   on_error=lambda e: self.rec("error", text="tick: %s" % e))
            self.tick.start()

    def rec(self, ev, **kw):
        kw.update(ev=ev, t=round(time.time() - self.t0, 4))
        self.f.write(json.dumps(kw) + "\n")

    def _install(self):
        hv = self.hv
        trapped = held = 0
        for part in filter(None, os.environ.get("S2R_TOUCH_FULL", "").split(",")):
            start, size = (int(x, 16) for x in part.split("+"))
            hv.add_tracer(irange(start, size), "TOUCHFULL", TraceMode.ASYNC, self._full, self._full)
            self.rec("zone", start="%#x" % start, size="%#x" % size, full=True)
        for r in hv.adt["/arm-io"].ranges:
            zone = irange(r.parent_addr, r.size)
            for mzone, maps in list(hv.mmio_maps.overlaps(zone)):
                lo, hi = max(mzone.start, zone.start), min(mzone.stop, zone.stop)
                # /arm-io ranges overlap: a part this loop has trapped already is not "held".
                if IDENT in maps:
                    continue
                others = [i for i, m in maps.items() if m[0] != TraceMode.OFF]
                if others:
                    held += hi - lo
                    self.rec("zone", start="%#x" % lo, size="%#x" % (hi - lo), held=others)
                    continue
                hv.add_tracer(irange(lo, hi - lo), IDENT, TraceMode.SYNC, self._touch, self._touch)
                self.zones.append((lo, hi - lo))
                trapped += hi - lo
                self.rec("zone", start="%#x" % lo, size="%#x" % (hi - lo), held=None)
        print("[touch] trapping %d MiB of device space, %d KiB held by the hypervisor; epoch %g s" % (
            trapped >> 20, held >> 10, self.epoch_len), flush=True)

    def _full(self, evt, **kw):
        # Asynchronous: no proxy calls here, only the record.
        self.rec("acc", addr="%#x" % evt.addr, w=bool(evt.flags.WRITE),
                 data="%#x" % evt.data if isinstance(evt.data, int) else str(evt.data),
                 width=int(evt.flags.WIDTH), pc="%#x" % evt.pc, cpu=int(evt.flags.CPU))

    def _touch(self, evt, **kw):
        page = evt.addr & ~(PAGE - 1)
        self.total += 1
        self.rec("touch", epoch=self.epoch, addr="%#x" % evt.addr, w=bool(evt.flags.WRITE),
                 data="%#x" % evt.data if isinstance(evt.data, int) else str(evt.data),
                 width=int(evt.flags.WIDTH), pc="%#x" % evt.pc, cpu=int(evt.flags.CPU))
        try:
            self.hv.del_tracer(irange(page, PAGE), IDENT)
        except KeyError:
            pass                    # a second CPU trapped on the same page before the remap
        self.touched.append(page)
        self._maybe_rearm()

    def _maybe_rearm(self):
        if self.full or self.epoch_len <= 0 or time.time() - self.epoch_t < self.epoch_len:
            return False
        pages, self.touched = self.touched, []
        self.rec("epoch", epoch=self.epoch, pages=len(pages))
        for page in set(pages):
            self.hv.add_tracer(irange(page, PAGE), IDENT, TraceMode.SYNC, self._touch, self._touch)
        self.epoch += 1
        self.epoch_t = time.time()
        return True

    def _tick(self):
        changed = self._maybe_rearm()
        if self.ctl and os.path.exists(self.ctl):
            lines = open(self.ctl).read().split("\n")
            os.remove(self.ctl)
            for line in lines:
                w = line.split()
                if w[:1] == ["snap"]:
                    self.snapshot(w[1] if len(w) > 1 else "manual")
                elif w[:1] == ["full"]:
                    self.snapshot("pre-full")
                    self.go_full(w[1] if len(w) > 1 else "")
                    changed = True
        if changed:
            self.hv.pt_update()     # the tick's handler returns to the guest itself

    def snapshot(self, tag, wake=False):
        """Read the snapshot list over the proxy. Only from a synchronous context."""
        if self.snap_list is None:
            path = os.environ.get("S2R_TOUCH_SNAP", os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "../../var/recfg/commit-snap-list-wide.json"))
            self.snap_list = [(int(a), n) for a, n in json.load(open(path))]
        regs, errs = {}, 0
        for a, n in self.snap_list:
            if wake and not (0x23b000000 <= a < 0x23b800000 or 0x23d000000 <= a < 0x23d300000):
                continue
            try:
                regs["%#x %s" % (a, n)] = "%#x" % self.hv.p.read32(a)
            except Exception as e:
                errs += 1
                regs["%#x %s" % (a, n)] = "ERR %s" % e
                if errs >= 3:       # a link that is gone: do not hammer it
                    break
        self.rec("snap", tag=tag, words=len(regs), errors=errs, regs=regs)
        print("[touch] snapshot %s: %d words, %d errors" % (tag, len(regs), errs), flush=True)

    def go_full(self, skip=""):
        hv = self.hv
        skips = [tuple(int(x, 16) for x in part.split("+")) for part in filter(None, skip.split(","))]
        hv.clear_tracers(IDENT)
        for start, size in self.zones:
            hv.add_tracer(irange(start, size), "TOUCHFULL", TraceMode.ASYNC, self._full, self._full)
        for start, size in skips:
            hv.del_tracer(irange(start, size), "TOUCHFULL")
            self.rec("zone", start="%#x" % start, size="%#x" % size, skipped=True)
        self.full = True
        self.touched = []
        t = getattr(self, "tick", None)
        if t is not None:
            t.stop()
        self.rec("mode", mode="full", zones=len(self.zones), skipped=len(skips))
        print("[touch] FULL logging of %d zones (%d ranges left out); clock stopped" % (len(self.zones), len(skips)), flush=True)

    def _hooks(self):
        hv = self.hv
        orig_exit = hv.p.hv_exit_cpu

        def exit_cpu(cpu=-1):
            # From HV.handle_msr when a guest CPU takes its sleep path, before started_cpus shrinks.
            try:
                left = len(hv.started_cpus)
                self.rec("exit-cpu", cpu=hv.ctx.cpu_id if hv.ctx else cpu, left=left - 1)
                if left <= 1:
                    self.snapshot("last-cpu")
            except Exception as e:
                print("[touch] exit hook: %s" % e, flush=True)
            return orig_exit(cpu)

        hv.p.hv_exit_cpu = exit_cpu
        orig_resume = getattr(hv, "s2r_resume", None)
        if orig_resume is not None:
            def resume():
                # After a real sleep: this Mac has the proxy again, the guest is not entered yet.
                try:
                    self.rec("wake")
                    self.snapshot("wake", wake=True)
                except Exception as e:
                    print("[touch] wake hook: %s" % e, flush=True)
                return orig_resume()

            hv.s2r_resume = resume

    def stop(self):
        t = getattr(self, "tick", None)
        if t is not None:
            t.stop()
        self.rec("end", epoch=self.epoch, pages=len(self.touched), total=self.total)


touch_map = TouchMap(hv)
