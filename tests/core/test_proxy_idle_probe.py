"""The proxy probe's choice of words and its reading of the result
(tools/hv-trace-kit/harness/proxy_idle_probe.py), without a Mac.

2026-11-17: the first version reported "every differing word written" while four clock words were
skipped, and a tolerance of 34 points hid the word after which two controllers stopped idling.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/hv-trace-kit/harness"))
import proxy_idle_probe as probe  # noqa: E402

SNAPSHOT = {
    "0x23d2b0010 wdt+0x10": "0x1",
    "0x23b700300 PMGR PS:ps_dcs0": "0x1f0003ff",
    "0x2002007b0 DCS0:DCS0+0x7b0": "0x0",
    "0x200000680 MCC:MCC.plane0+0x680": "0xe0b",
    "0x23b700420 PMGR PS:ps_atc0_common": "0x22ff",
    "0x23b05c000 PMGR clkgen:SoC clkgen+0x5c000": "0x444",
    "0x23b7001f0 PMGR PS:ps_i2c0": "0x200",
    "0x23b040000 PMGR clkgen:SoC clkgen+0x40000": "0x87100100",
    "0x23d240024 AON:AON clkgen+0x40024": "0x81100100",
}


def test_plan_writes_in_group_order_and_names_what_it_leaves_alone():
    write, skipped = probe.plan(SNAPSHOT)
    assert [hex(a) for a, _, _ in write] == ["0x23d240024", "0x23b040000", "0x23b7001f0"]
    reasons = {hex(a): why for a, _, _, why in skipped}
    assert set(reasons) == {"0x23d2b0010", "0x23b700300", "0x2002007b0", "0x200000680", "0x23b700420", "0x23b05c000"}
    assert "clock" in reasons["0x23b05c000"] and "measured" in reasons["0x23b700300"]


def test_clock_words_are_written_last_and_only_when_asked():
    write, skipped = probe.plan(SNAPSHOT, clocks=True)
    assert hex(write[-1][0]) == "0x23b05c000"
    assert "0x23b05c000" not in {hex(a) for a, _, _, _ in skipped}


def test_changepoint_finds_the_change_pidle1_hid():
    # dcs2 in pidle1: about 76 % fully on, then 95 % from one word on (19 points, under the old
    # tolerance of 34); dcs0: about 13 %, then 0.
    assert probe.changepoint([76, 80, 73, 75, 81, 78, 95, 98, 96, 95, 97, 95])[0] == 6
    assert probe.changepoint([13, 15, 11, 18, 10, 13, 0, 0, 1, 0, 0, 0])[0] == 6


def test_changepoint_is_silent_on_scatter():
    assert probe.changepoint([13, 8, 15, 10, 16, 11, 12, 9, 14, 10, 18, 7]) is None
    assert probe.changepoint([76, 80, 70, 75, 81, 68, 79, 73, 82, 71, 77, 74]) is None
