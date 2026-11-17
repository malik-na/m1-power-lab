"""A sampling clock for a hypervisor tracer: a synchronous callback every period, whatever the
guest is doing.

The tracer's hooks only run when the guest writes a hooked register, so a quiet guest is never
sampled (lx21, 2026-11-17: no sample of the DRAM controllers for 42 s before the commit). This
uses the path Ctrl-C already takes: the host writes "!" to the proxy, m1n1's hypervisor stops the
guest and raises USER_INTERRUPT, and the handler runs with the proxy free for reads.

  kick()   from SIGALRM, in the main thread between bytecodes. Sends "!" through hv.interrupt()
           only while the guest runs and no handler is active: a byte in the middle of a proxy
           exchange would corrupt it. m1n1 skips a stray "!" while it looks for a request header.
  event()  the USER_INTERRUPT handler. A real Ctrl-C sets hv._sigint_pending first and goes to
           the hypervisor's own handler (its shell); anything else is a tick: sample, resume.

The clock stops itself when MAX_UNANSWERED kicks in a row bring no event: the guest has exited
(after its sleep commit the proxy is bare again, and a "!" in the middle of a memory write to it
would corrupt the write) or the hypervisor no longer answers.

No m1n1 import here, so tests/core/test_hv_tick.py runs it against a fake hypervisor object.
Not for runs with real suspend pass-through: stop() before the guest's commit.
"""
import signal


MAX_UNANSWERED = 5


class Tick:
    def __init__(self, hv, sample, period_s, handled_ret, set_handler, on_error=None):
        self.hv, self.sample, self.period = hv, sample, period_s
        self.handled_ret, self.set_handler = handled_ret, set_handler
        self.on_error = on_error or (lambda e: None)
        self.on = False
        self.kicks = self.events = self.unanswered = 0

    def start(self):
        self.set_handler(self.event)
        signal.signal(signal.SIGALRM, self.kick)
        signal.setitimer(signal.ITIMER_REAL, self.period, self.period)
        self.on = True

    def stop(self):
        self.on = False
        signal.setitimer(signal.ITIMER_REAL, 0)

    def kick(self, signum=None, frame=None):
        hv = self.hv
        if not self.on or not hv.started or hv._in_handler or hv._sigint_pending:
            return
        if self.unanswered >= MAX_UNANSWERED:
            self.stop()
            self.on_error(RuntimeError("no answer to %d ticks in a row: clock stopped" % self.unanswered))
            return
        try:
            hv.interrupt()
            self.kicks += 1
            self.unanswered += 1
        except Exception as e:      # a dead link must not raise inside whatever the main thread runs
            self.stop()
            self.on_error(e)

    def event(self, reason, code, info):
        hv = self.hv
        if hv._sigint_pending or getattr(hv, "switching_context", False):
            return hv.handle_exception(reason, code, info)
        hv._in_handler = True
        self.unanswered = 0
        try:
            self.sample()
            self.events += 1
        except Exception as e:
            self.on_error(e)
        finally:
            hv.p.exit(self.handled_ret)
            hv._in_handler = False
        if hv._sigint_pending:
            hv._handle_sigint()
