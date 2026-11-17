"""The tracer's sampling clock (tools/hv-trace-kit/hv_tick.py) against a fake hypervisor object.

It interrupts a running guest through the path Ctrl-C takes, so the two things that must hold are:
a kick never writes to the proxy while an exchange may be in progress, and a real Ctrl-C still
reaches the hypervisor's own handler.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/hv-trace-kit"))
import hv_tick  # noqa: E402


class FakeProxy:
    def __init__(self):
        self.exits = []

    def exit(self, ret):
        self.exits.append(ret)


class FakeHV:
    def __init__(self):
        self.started, self._in_handler, self._sigint_pending = True, False, False
        self.p = FakeProxy()
        self.interrupts = self.delegated = self.sigints = 0
        self.fail_interrupt = False

    def interrupt(self):
        if self.fail_interrupt:
            raise OSError("write failed")
        self.interrupts += 1

    def handle_exception(self, reason, code, info):
        self.delegated += 1

    def _handle_sigint(self):
        self.sigints += 1


def make(sample=None):
    hv, samples, errors = FakeHV(), [], []
    t = hv_tick.Tick(hv, sample or (lambda: samples.append(hv._in_handler)), 0.25, "HANDLED",
                     lambda fn: None, on_error=errors.append)
    t.on = True     # start() arms a real timer; the logic is tested without it
    return hv, t, samples, errors


def test_kick_interrupts_only_a_running_guest_with_no_handler_active():
    hv, t, _, _ = make()
    t.kick()
    assert hv.interrupts == 1
    for attr, value in (("started", False), ("_in_handler", True), ("_sigint_pending", True)):
        hv2, t2, _, _ = make()
        setattr(hv2, attr, value)
        t2.kick()
        assert hv2.interrupts == 0, attr


def test_a_dead_link_stops_the_clock_and_does_not_raise():
    hv, t, _, errors = make()
    hv.fail_interrupt = True
    t.kick()
    assert not t.on and len(errors) == 1
    hv.fail_interrupt = False
    t.kick()
    assert hv.interrupts == 0


def test_a_tick_samples_inside_the_handler_and_resumes_the_guest():
    hv, t, samples, _ = make()
    t.event(None, None, None)
    assert samples == [True]            # the sample ran with the handler flag set
    assert hv.p.exits == ["HANDLED"] and hv._in_handler is False and hv.delegated == 0


def test_a_real_interrupt_goes_to_the_hypervisors_own_handler():
    hv, t, samples, _ = make()
    hv._sigint_pending = True
    t.event(None, None, None)
    assert hv.delegated == 1 and samples == [] and hv.p.exits == []


def test_a_failing_sample_still_resumes_the_guest():
    def boom():
        raise RuntimeError("read failed")
    hv, t, _, errors = make(sample=boom)
    t.event(None, None, None)
    assert hv.p.exits == ["HANDLED"] and hv._in_handler is False and len(errors) == 1


def test_the_clock_stops_when_ticks_go_unanswered():
    # After the guest's sleep commit the hypervisor has exited: kicks would reach the bare proxy.
    hv, t, _, errors = make()
    for _ in range(hv_tick.MAX_UNANSWERED):
        t.kick()
    assert t.on and hv.interrupts == hv_tick.MAX_UNANSWERED
    t.kick()
    assert not t.on and hv.interrupts == hv_tick.MAX_UNANSWERED and len(errors) == 1


def test_an_answered_tick_resets_the_count():
    hv, t, _, _ = make()
    for _ in range(hv_tick.MAX_UNANSWERED - 1):
        t.kick()
    t.event(None, None, None)
    for _ in range(hv_tick.MAX_UNANSWERED):
        t.kick()
    assert t.on
