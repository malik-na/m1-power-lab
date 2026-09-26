from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite, sqrt
from statistics import mean, stdev
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class PowerSample:
    monotonic_seconds: float
    watts: float


@dataclass(frozen=True, slots=True)
class PairedBlock:
    baseline_watts: float
    changed_watts: float


@dataclass(frozen=True, slots=True)
class ThresholdDecision:
    status: str
    estimated_reduction_percent: float
    contrast_watts: float
    lower_contrast_watts: float | None
    upper_contrast_watts: float | None
    block_count: int
    explanation: str


# Two-sided 95% Student-t critical values. Confirmation plans with larger or
# unusual designs should use a reviewed statistical implementation instead.
_T_975 = (
    inf,
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def average_power(samples: Iterable[PowerSample]) -> float:
    """Return time-weighted average power using trapezoidal integration."""
    ordered = sorted(samples, key=lambda sample: sample.monotonic_seconds)
    if len(ordered) < 2:
        raise ValueError("at least two power samples are required")
    if any(
        not isfinite(sample.monotonic_seconds)
        or not isfinite(sample.watts)
        or sample.watts < 0
        for sample in ordered
    ):
        raise ValueError("power samples must use a non-negative consumption convention")

    energy_joules = 0.0
    for left, right in zip(ordered, ordered[1:], strict=False):
        duration = right.monotonic_seconds - left.monotonic_seconds
        if duration <= 0:
            raise ValueError("sample timestamps must be unique and increasing")
        energy_joules += duration * (left.watts + right.watts) / 2.0

    elapsed = ordered[-1].monotonic_seconds - ordered[0].monotonic_seconds
    return energy_joules / elapsed


def evaluate_ten_percent_threshold(
    blocks: Sequence[PairedBlock],
    *,
    systematic_allowance_watts: float = 0.0,
) -> ThresholdDecision:
    """Evaluate the frozen paired-block rule from the architecture.

    The contrast is D = 0.90 * baseline - changed. A strictly positive lower
    confidence bound after systematic allowance supports more than 10% lower
    mean power. Callers remain responsible for validating independence,
    protocol adherence, regressions, and the systematic allowance.
    """
    if len(blocks) < 2:
        raise ValueError("at least two independently restarted blocks are required")
    if len(blocks) > 31:
        raise ValueError("the frozen Student-t table supports at most 31 paired blocks")
    if not isfinite(systematic_allowance_watts) or systematic_allowance_watts < 0:
        raise ValueError("systematic allowance must be non-negative")
    if any(
        not isfinite(block.baseline_watts)
        or not isfinite(block.changed_watts)
        or block.baseline_watts <= 0
        or block.changed_watts < 0
        for block in blocks
    ):
        raise ValueError("baseline power must be positive and changed power non-negative")

    baselines = [block.baseline_watts for block in blocks]
    changed = [block.changed_watts for block in blocks]
    contrasts = [0.90 * block.baseline_watts - block.changed_watts for block in blocks]
    estimated_reduction = 100.0 * (1.0 - mean(changed) / mean(baselines))
    contrast = mean(contrasts)
    degrees_freedom = len(contrasts) - 1
    critical = _T_975[degrees_freedom]
    margin = critical * stdev(contrasts) / sqrt(len(contrasts))
    lower = contrast - margin - systematic_allowance_watts
    upper = contrast + margin + systematic_allowance_watts

    if lower > 0:
        status = "threshold_supported"
        explanation = "The frozen 95% paired-block rule supports more than 10% lower power."
    elif estimated_reduction >= 10.0:
        status = "inconclusive"
        explanation = "The point estimate reaches 10%, but uncertainty does not support the full claim."
    else:
        status = "below_threshold_or_inconclusive"
        explanation = "The point estimate is below 10%; the full protocol determines whether this is bounded or inconclusive."

    return ThresholdDecision(
        status=status,
        estimated_reduction_percent=estimated_reduction,
        contrast_watts=contrast,
        lower_contrast_watts=lower,
        upper_contrast_watts=upper,
        block_count=len(blocks),
        explanation=explanation,
    )
