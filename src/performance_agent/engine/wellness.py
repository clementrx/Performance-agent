"""Deterministic wellness-trend analysis: HRV, resting heart rate, sleep.

HRV follows the rolling-average monitoring framework (Plews & Laursen /
Buchheit): work in ln(rMSSD), compare the last 7 days' rolling mean against
the preceding 28-day baseline, and call a departure only beyond the smallest
worthwhile change (0.5 x the baseline's between-day SD). Departures in BOTH
directions are reported — a rolling mean above baseline + SWC is also worth
narrating, not only suppression. Resting HR compares the same windows with a
plain bpm threshold; sleep reports the last week's mean and debt against a
nightly target. All outputs are DESCRIPTIVE trends, never a diagnosis.

Honesty gates mirror fit_banister: thin data returns usable=False with a
reason, never a fabricated baseline. Thresholds are team-chosen priors until
the monitoring papers land in the corpus (dates never enter the engine: the
caller converts calendar dates to day indexes).
"""

import math
from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

_ROLLING_DAYS = 7
_BASELINE_DAYS = 28
_MIN_ROLLING_SAMPLES = 3
_MIN_BASELINE_SAMPLES = 10
_SWC_SD_FACTOR = 0.5  # smallest worthwhile change = 0.5 x baseline SD (Hopkins convention)
_RHR_BAND_BPM = 5.0  # resting-HR departure worth naming (team-chosen prior)
_SLEEP_SHORT_MARGIN_H = 1.0  # "short" = rolling mean more than 1 h under the nightly target

_HRV_MIN_MS = 1.0
_HRV_MAX_MS = 1000.0  # matches the readiness schema's hrv_ms bound
_RHR_MIN_BPM = 20.0
_RHR_MAX_BPM = 120.0
_SLEEP_MAX_H = 24.0
_SLEEP_TARGET_MIN_H = 4.0
_SLEEP_TARGET_MAX_H = 12.0

HrvBand = Literal["below", "normal", "above"]
RestingHrBand = Literal["lowered", "normal", "elevated"]
SleepBand = Literal["short", "ok"]


@dataclass(frozen=True)
class WellnessSample:
    """One dated measurement: day_index counts days from the series start (0-based)."""

    day_index: int
    value: float


@dataclass(frozen=True)
class HrvTrend:
    """Rolling ln(rMSSD) vs baseline +/- SWC; read usable FIRST."""

    usable: bool
    reason: str | None
    rolling_ln_mean: float
    baseline_ln_mean: float
    baseline_ln_sd: float
    swc_ln: float
    delta_pct: float  # rolling vs baseline in raw-rMSSD percent (readiness hrv_delta_pct)
    band: HrvBand


@dataclass(frozen=True)
class RestingHrTrend:
    """Rolling resting-HR mean vs baseline; elevated/lowered beyond a bpm threshold."""

    usable: bool
    reason: str | None
    rolling_mean_bpm: float
    baseline_mean_bpm: float
    delta_bpm: float
    band: RestingHrBand


@dataclass(frozen=True)
class SleepTrend:
    """Last week's mean sleep and accumulated debt vs the nightly target."""

    usable: bool
    reason: str | None
    rolling_mean_h: float
    nightly_target_h: float
    weekly_debt_h: float  # summed shortfall over the SAMPLED nights (missing nights don't count)
    band: SleepBand


@dataclass(frozen=True)
class WellnessTrend:
    """Per-signal trends; a signal is None when no samples were given for it."""

    hrv: HrvTrend | None
    resting_hr: RestingHrTrend | None
    sleep: SleepTrend | None


def _validate_samples(name: str, samples: list[WellnessSample], low: float, high: float) -> None:
    for sample in samples:
        validate_whole_number(f"{name} day_index", sample.day_index)
        if sample.day_index < 0:
            msg = f"{name} day_index must be >= 0, got {sample.day_index!r}"
            raise ValueError(msg)
        validate_finite(f"{name} value", sample.value)
        if not low <= sample.value <= high:
            msg = f"{name} value must be in [{low}, {high}], got {sample.value!r}"
            raise ValueError(msg)


def _split_windows(
    samples: list[WellnessSample],
) -> tuple[list[float], list[float]]:
    """Return (rolling, baseline) values: last 7 days vs the 28 days before them."""
    latest = max(sample.day_index for sample in samples)
    rolling_start = latest - _ROLLING_DAYS  # exclusive
    baseline_start = rolling_start - _BASELINE_DAYS  # exclusive
    rolling = [s.value for s in samples if s.day_index > rolling_start]
    baseline = [s.value for s in samples if baseline_start < s.day_index <= rolling_start]
    return rolling, baseline


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


_MIN_SD_SAMPLES = 2


def _sample_sd(values: list[float], mean: float) -> float:
    if len(values) < _MIN_SD_SAMPLES:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _window_gate(rolling: list[float], baseline: list[float], unit: str) -> str | None:
    if len(rolling) < _MIN_ROLLING_SAMPLES:
        return (
            f"need >= {_MIN_ROLLING_SAMPLES} {unit} in the last {_ROLLING_DAYS} days, "
            f"got {len(rolling)}"
        )
    if len(baseline) < _MIN_BASELINE_SAMPLES:
        return (
            f"need >= {_MIN_BASELINE_SAMPLES} baseline {unit} in the {_BASELINE_DAYS} days "
            f"before the rolling week, got {len(baseline)}"
        )
    return None


def hrv_trend(samples: list[WellnessSample]) -> HrvTrend:
    """Rolling 7-day ln(rMSSD) mean vs the 28-day baseline +/- SWC (0.5 x SD).

    delta_pct converts the ln-difference back to raw-rMSSD percent — pass it to
    readiness_score as hrv_delta_pct. usable=False (with the reason) when either
    window is too thin; never act on an unusable trend.
    """
    _validate_samples("hrv", samples, _HRV_MIN_MS, _HRV_MAX_MS)
    if not samples:
        return _unusable_hrv("no HRV samples given")
    rolling, baseline = _split_windows(samples)
    gate = _window_gate(rolling, baseline, "nightly HRV readings")
    if gate is not None:
        return _unusable_hrv(gate)
    rolling_ln = [math.log(v) for v in rolling]
    baseline_ln = [math.log(v) for v in baseline]
    rolling_mean = _mean(rolling_ln)
    baseline_mean = _mean(baseline_ln)
    baseline_sd = _sample_sd(baseline_ln, baseline_mean)
    swc = _SWC_SD_FACTOR * baseline_sd
    band: HrvBand = "normal"
    if rolling_mean < baseline_mean - swc:
        band = "below"
    elif rolling_mean > baseline_mean + swc:
        band = "above"
    return HrvTrend(
        usable=True,
        reason=None,
        rolling_ln_mean=rolling_mean,
        baseline_ln_mean=baseline_mean,
        baseline_ln_sd=baseline_sd,
        swc_ln=swc,
        delta_pct=(math.exp(rolling_mean - baseline_mean) - 1.0) * 100.0,
        band=band,
    )


def resting_hr_trend(samples: list[WellnessSample]) -> RestingHrTrend:
    """Rolling 7-day resting-HR mean vs the 28-day baseline; +/-5 bpm names a departure."""
    _validate_samples("resting_hr", samples, _RHR_MIN_BPM, _RHR_MAX_BPM)
    if not samples:
        return _unusable_rhr("no resting-HR samples given")
    rolling, baseline = _split_windows(samples)
    gate = _window_gate(rolling, baseline, "resting-HR readings")
    if gate is not None:
        return _unusable_rhr(gate)
    rolling_mean = _mean(rolling)
    baseline_mean = _mean(baseline)
    delta = rolling_mean - baseline_mean
    band: RestingHrBand = "normal"
    if delta >= _RHR_BAND_BPM:
        band = "elevated"
    elif delta <= -_RHR_BAND_BPM:
        band = "lowered"
    return RestingHrTrend(
        usable=True,
        reason=None,
        rolling_mean_bpm=rolling_mean,
        baseline_mean_bpm=baseline_mean,
        delta_bpm=delta,
        band=band,
    )


def sleep_trend(samples: list[WellnessSample], nightly_target_h: float = 8.0) -> SleepTrend:
    """Last week's mean sleep hours and summed debt vs the nightly target.

    Debt counts only the SAMPLED nights — missing nights add nothing, so quote
    the sample count honestly. "short" = rolling mean more than 1 h under target.
    """
    validate_finite("nightly_target_h", nightly_target_h)
    if not _SLEEP_TARGET_MIN_H <= nightly_target_h <= _SLEEP_TARGET_MAX_H:
        msg = (
            f"nightly_target_h must be in [{_SLEEP_TARGET_MIN_H}, {_SLEEP_TARGET_MAX_H}], "
            f"got {nightly_target_h!r}"
        )
        raise ValueError(msg)
    _validate_samples("sleep", samples, 0.0, _SLEEP_MAX_H)
    if not samples:
        return _unusable_sleep("no sleep samples given", nightly_target_h)
    latest = max(sample.day_index for sample in samples)
    rolling = [s.value for s in samples if s.day_index > latest - _ROLLING_DAYS]
    if len(rolling) < _MIN_ROLLING_SAMPLES:
        return _unusable_sleep(
            f"need >= {_MIN_ROLLING_SAMPLES} sleep nights in the last {_ROLLING_DAYS} days, "
            f"got {len(rolling)}",
            nightly_target_h,
        )
    rolling_mean = _mean(rolling)
    debt = sum(max(0.0, nightly_target_h - v) for v in rolling)
    band: SleepBand = "short" if rolling_mean < nightly_target_h - _SLEEP_SHORT_MARGIN_H else "ok"
    return SleepTrend(
        usable=True,
        reason=None,
        rolling_mean_h=rolling_mean,
        nightly_target_h=nightly_target_h,
        weekly_debt_h=debt,
        band=band,
    )


def wellness_trend(
    hrv: list[WellnessSample] | None = None,
    resting_hr: list[WellnessSample] | None = None,
    sleep: list[WellnessSample] | None = None,
    nightly_sleep_target_h: float = 8.0,
) -> WellnessTrend:
    """Analyze whichever signals were given; a signal with no samples stays None."""
    return WellnessTrend(
        hrv=hrv_trend(hrv) if hrv else None,
        resting_hr=resting_hr_trend(resting_hr) if resting_hr else None,
        sleep=sleep_trend(sleep, nightly_sleep_target_h) if sleep else None,
    )


def _unusable_hrv(reason: str) -> HrvTrend:
    return HrvTrend(
        usable=False,
        reason=reason,
        rolling_ln_mean=0.0,
        baseline_ln_mean=0.0,
        baseline_ln_sd=0.0,
        swc_ln=0.0,
        delta_pct=0.0,
        band="normal",
    )


def _unusable_rhr(reason: str) -> RestingHrTrend:
    return RestingHrTrend(
        usable=False,
        reason=reason,
        rolling_mean_bpm=0.0,
        baseline_mean_bpm=0.0,
        delta_bpm=0.0,
        band="normal",
    )


def _unusable_sleep(reason: str, nightly_target_h: float) -> SleepTrend:
    return SleepTrend(
        usable=False,
        reason=reason,
        rolling_mean_h=0.0,
        nightly_target_h=nightly_target_h,
        weekly_debt_h=0.0,
        band="ok",
    )
