"""Statistics for live measurements: paired A/B blocks and sleep ledgers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean, median, stdev
from typing import Any, Callable, Sequence

from m1lab.science.power import _T_975, PairedBlock, evaluate_ten_percent_threshold

METRICS = ("sys_w", "dcin_acc_w", "soc_w", "irq_s", "ctxt_s")


@dataclass(frozen=True)
class PairedEffect:
    metric: str
    pairs: int
    mean_a: float
    mean_b: float
    delta: float  # b - a
    ci_low: float | None
    ci_high: float | None
    percent: float | None

    @property
    def significant(self) -> bool:
        return self.ci_low is not None and (self.ci_low > 0 or self.ci_high < 0)


def paired_effect(a: Sequence[float], b: Sequence[float], metric: str) -> PairedEffect:
    if len(a) != len(b) or not a:
        raise ValueError("paired samples must be non-empty and equal length")
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    mean_a, mean_b, delta = mean(a), mean(b), mean(diffs)
    low = high = None
    if len(diffs) >= 2:
        # Past the table (df > 30) use the df = 30 value: slightly wider than
        # the exact interval, so it stays conservative.
        critical = _T_975[min(len(diffs) - 1, len(_T_975) - 1)]
        margin = critical * stdev(diffs) / sqrt(len(diffs))
        low, high = delta - margin, delta + margin
    percent = 100.0 * delta / mean_a if mean_a else None
    return PairedEffect(metric, len(diffs), mean_a, mean_b, delta, low, high, percent)


def analyze_ab(result: dict[str, Any]) -> dict[str, Any]:
    blocks = [b for b in result.get("blocks", []) if "a" in b and "b" in b]
    effects = {}
    for metric in METRICS:
        a = [b["a"].get(metric) for b in blocks]
        b = [b["b"].get(metric) for b in blocks]
        if blocks and all(isinstance(v, (int, float)) for v in a + b):
            effects[metric] = paired_effect(a, b, metric)
    out: dict[str, Any] = {
        "knob": result.get("knob"),
        "a": result.get("a"),
        "b": result.get("b"),
        "pairs": len(blocks),
        "effects": {k: asdict(v) | {"significant": v.significant} for k, v in effects.items()},
    }
    primary = effects.get("sys_w")
    if primary and len(blocks) >= 2 and primary.mean_a > 0:
        try:
            decision = evaluate_ten_percent_threshold(
                [PairedBlock(baseline_watts=b["a"]["sys_w"], changed_watts=b["b"]["sys_w"]) for b in blocks]
            )
            out["ten_percent_rule"] = decision.status
        except ValueError:
            pass
    if primary:
        out["verdict"] = verdict(primary)
    a_last = blocks[-1]["a"] if blocks else {}
    b_last = blocks[-1]["b"] if blocks else {}
    out["idle_a"], out["idle_b"] = a_last.get("idle"), b_last.get("idle")
    out["mhz_a"], out["mhz_b"] = a_last.get("mhz"), b_last.get("mhz")
    return out


def verdict(effect: PairedEffect) -> str:
    mw = effect.delta * 1000
    if effect.ci_low is None:
        return f"{mw:+.0f} mW (too few pairs for an interval)"
    span = f"95% CI {effect.ci_low * 1000:+.0f}..{effect.ci_high * 1000:+.0f} mW"
    if effect.ci_high < 0:
        share = f" ({-effect.percent:.1f}%)" if effect.percent is not None else ""
        return f"saves {-mw:.0f} mW{share}, {span}"
    if effect.ci_low > 0:
        share = f" ({effect.percent:+.1f}%)" if effect.percent is not None else ""
        return f"costs {mw:.0f} mW{share}, {span}"
    return f"no detectable effect ({mw:+.0f} mW, {span})"


def is_sleep(entry: dict[str, Any]) -> bool:
    """A real sleep: not another ledger kind (``standby`` dark-wake decisions),
    and not one of maclab's ``pm_test`` suspend-devices cycles, which freeze
    and suspend devices for a few seconds without ever entering s2idle."""
    return entry.get("kind", "sleep") == "sleep" and entry.get("pm_test", "none") == "none"


def sleep_watts(entry: dict[str, Any]) -> float | None:
    """Best estimate of average power over one sleep bracket.

    Uses the agent's ``sleep_w`` when present. Older entries get the same rule:
    DC-in on AC, otherwise the battery's energy drop (DC-in is ~0 W unplugged).
    """
    if "sleep_w" in entry:
        keys: tuple[str, ...] = ("sleep_w",)
    elif entry.get("on_ac"):
        keys = ("dcin_w",)
    else:
        keys = ("battery_w", "dcin_w")
    for key in keys:
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _weighted(entries: Sequence[dict[str, Any]], value: Callable[[dict[str, Any]], float]) -> float:
    total = sum(e["slept_s"] for e in entries)
    return sum(value(e) * e["slept_s"] for e in entries) / total


def summarize_sleeps(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    usable = [e for e in entries if is_sleep(e) and e.get("slept_s", 0) > 20 and sleep_watts(e) is not None]
    if not usable:
        return {"count": 0}
    total = sum(e["slept_s"] for e in usable)
    out: dict[str, Any] = {
        "count": len(usable),
        "slept_hours": round(total / 3600, 3),
        "sleep_w_weighted": round(_weighted(usable, sleep_watts), 4),
        "sleep_w_median": round(median(sleep_watts(e) for e in usable), 4),
        "s2idle_cpus_pd_median": round(median(e.get("s2idle_cpus_pd", 0) for e in usable), 4),
    }
    dcin = [e for e in usable if isinstance(e.get("dcin_w"), (int, float))]
    if dcin:
        out["dcin_w_weighted"] = round(_weighted(dcin, lambda e: e["dcin_w"]), 4)
        out["dcin_w_median"] = round(median(e["dcin_w"] for e in dcin), 4)
    # On battery, prefer the SMC load accumulator (sleep_w): the gauge moves in
    # coarse steps and read 0.48 W for a sleep the accumulator put at 0.62 W.
    on_battery = [e for e in usable if not e.get("on_ac")]
    if on_battery:
        out["battery_count"] = len(on_battery)
        out["battery_w_weighted"] = round(_weighted(on_battery, sleep_watts), 4)
    battery = [e for e in usable if "battery_pct_per_hour" in e and not e.get("on_ac")]
    if battery:
        out["battery_pct_per_hour_median"] = round(median(e["battery_pct_per_hour"] for e in battery), 3)
    return out


def days_of_standby(watts: float, battery_wh: float) -> float:
    return battery_wh / watts / 24 if watts > 0 else float("inf")


def analyze_sleep_ab(entries: Sequence[dict[str, Any]], knob: str) -> dict[str, Any] | None:
    """Pair consecutive (baseline, changed) sleeps in the order they ran.

    A pair is only formed from two sleeps on the same power source: DC-in on AC
    and battery drain unplugged are different measurements.
    """
    base: list[float] = []
    changed: list[float] = []
    pending: dict[str, tuple[bool, float]] = {}
    for entry in entries:
        watts = sleep_watts(entry)
        if not is_sleep(entry) or watts is None or entry.get("slept_s", 0) < 20:
            continue
        on_ac = bool(entry.get("on_ac"))
        if any(source != on_ac for source, _ in pending.values()):
            pending.clear()
        side = "b" if knob in (entry.get("knobs") or {}) else "a"
        pending[side] = (on_ac, watts)
        if "a" in pending and "b" in pending:
            base.append(pending.pop("a")[1])
            changed.append(pending.pop("b")[1])
    if not base:
        return None
    effect = paired_effect(base, changed, "sleep_w")
    return asdict(effect) | {"significant": effect.significant, "verdict": verdict(effect)}
