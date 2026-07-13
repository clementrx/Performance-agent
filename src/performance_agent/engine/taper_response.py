"""Individual taper-response detection and summary (pure, deterministic).

Detects historical taper windows in a daily-load series — a sustained volume
reduction of at least ~25% over at least 4 days immediately before a competition —
and pairs each with an outcome (higher = better; the memory layer normalizes
lower-is-better KPIs). With at least 2 tapers carrying outcomes it recommends the
best-outcome (duration, reduction) as an individual prior; with fewer it returns
the generic population rule, explicitly labeled. Datetime-free: the memory layer
resolves dates into day indices and reads outcomes.
"""

from dataclasses import dataclass

MIN_TAPER_DAYS = 4
_MAX_TAPER_DAYS = 21
# Baseline = the normal load over a window ending _BASELINE_OFFSET days before the
# event (before any plausible taper), spanning _BASELINE_WINDOW_DAYS.
_BASELINE_OFFSET = 21
_BASELINE_WINDOW_DAYS = 14
_MIN_REDUCTION = 0.25  # a taper day sits >= 25% below baseline; overall drop too
_MIN_INDIVIDUAL_TAPERS = 2


@dataclass(frozen=True)
class TaperEvent:
    """A competition day and its outcome (higher = better), None when unmeasured."""

    day_index: int
    outcome: float | None


@dataclass(frozen=True)
class TaperWindow:
    """A detected taper before one event: its duration, volume reduction and outcome."""

    event_day: int
    duration_days: int
    reduction: float
    outcome: float | None


@dataclass(frozen=True)
class TaperResponse:
    """Summary of detected tapers plus an individual-or-population recommendation."""

    n_detected: int
    n_with_outcome: int
    windows: tuple[TaperWindow, ...]
    recommended_duration_days: int | None
    recommended_reduction: float | None
    basis: str
    note: str


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def detect_taper(loads: list[float], event_day: int) -> tuple[int, float] | None:
    """Return (duration_days, reduction) of the taper before an event, or None.

    Baseline is the mean load over a pre-taper window; the taper is the run of
    consecutive days immediately before the event each sitting >= 25% below
    baseline (capped at 21 days). None when there is not enough history, no
    baseline load, or the run is shorter than 4 days.
    """
    baseline_end = event_day - _BASELINE_OFFSET
    baseline_start = baseline_end - _BASELINE_WINDOW_DAYS
    if baseline_start < 0 or event_day > len(loads) or event_day < 1:
        return None
    baseline = _mean(loads[baseline_start:baseline_end])
    if baseline is None or baseline <= 0:
        return None
    threshold = (1.0 - _MIN_REDUCTION) * baseline
    day = event_day - 1
    taper_days: list[float] = []
    while day >= 0 and len(taper_days) < _MAX_TAPER_DAYS and loads[day] <= threshold:
        taper_days.append(loads[day])
        day -= 1
    if len(taper_days) < MIN_TAPER_DAYS:
        return None
    taper_mean = _mean(taper_days)
    reduction = 1.0 - taper_mean / baseline if taper_mean is not None else 0.0
    return len(taper_days), reduction


def fit_taper_response(
    loads: list[float], events: list[TaperEvent], generic_duration_days: int
) -> TaperResponse:
    """Detect each event's taper, pair with outcomes, and recommend duration/reduction.

    With >= 2 detected tapers carrying outcomes, recommends the best-outcome taper's
    (duration, reduction) with basis="individual". Otherwise returns the generic
    population rule (basis="population"), explicitly labeled. Deterministic.
    """
    windows: list[TaperWindow] = []
    for event in events:
        detected = detect_taper(loads, event.day_index)
        if detected is not None:
            duration, reduction = detected
            windows.append(
                TaperWindow(
                    event_day=event.day_index,
                    duration_days=duration,
                    reduction=reduction,
                    outcome=event.outcome,
                )
            )
    with_outcome = [w for w in windows if w.outcome is not None]
    if len(with_outcome) >= _MIN_INDIVIDUAL_TAPERS:
        best = max(with_outcome, key=lambda w: w.outcome if w.outcome is not None else 0.0)
        note = (
            f"individual taper prior from {len(with_outcome)} tapers with outcomes; "
            f"best was {best.duration_days} days at {best.reduction:.0%} volume reduction"
        )
        return TaperResponse(
            n_detected=len(windows),
            n_with_outcome=len(with_outcome),
            windows=tuple(windows),
            recommended_duration_days=best.duration_days,
            recommended_reduction=best.reduction,
            basis="individual",
            note=note,
        )
    generic = (
        f"the generic {generic_duration_days}-day rule"
        if generic_duration_days > 0
        else "the generic rule"
    )
    note = (
        f"population prior: only {len(with_outcome)} taper(s) with an outcome on file "
        f"(need {_MIN_INDIVIDUAL_TAPERS}); using {generic}"
    )
    return TaperResponse(
        n_detected=len(windows),
        n_with_outcome=len(with_outcome),
        windows=tuple(windows),
        recommended_duration_days=None,
        recommended_reduction=None,
        basis="population",
        note=note,
    )
