"""Training load quantification: session-RPE, monotony/strain, fitness-fatigue.

Every number here is a DESCRIPTIVE monitoring trend, never a prediction. ACWR's
injury-prediction validity is contested in the literature; monotony, strain,
CTL/ATL/TSB and readiness are trend indicators the coach reads and narrates, not
probabilities. Downstream agents must present them that way.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

MIN_RPE = 1
MAX_RPE = 10
DAYS_PER_WEEK = 7
CHRONIC_WINDOW_DAYS = 28

AcwrMethod = Literal["rolling", "ewma"]

# EWMA impulse-response time constants (Coggan-style CTL/ATL). These taus are
# modelling conventions, not tuned to any cohort — 42 days for chronic training
# load (fitness), 7 days for acute load (fatigue).
CTL_TAU_DAYS = 42
ATL_TAU_DAYS = 7
# EWMA-variant ACWR (Williams et al. 2017): acute EWMA over chronic EWMA, still
# descriptive-only. Same taus as ATL/CTL by convention.
_ACWR_ACUTE_TAU = 7
_ACWR_CHRONIC_TAU = 28

# Hooper wellness items are each rated 1 (best) to 7 (worst); the mean of the
# inverted items scales to 0-100. Band cut-offs are team-chosen priors.
_HOOPER_MIN = 1
_HOOPER_MAX = 7
_READINESS_GREEN = 75.0  # score >= this is green (fresh)
_READINESS_AMBER = 50.0  # score in [50, 75) is amber; below is red
# Optional HRV modifier: each 1% of HRV above/below the athlete's baseline moves
# the score by this many points, clamped to the cap. Team-chosen prior.
_HRV_POINTS_PER_PCT = 0.5
_HRV_MODIFIER_CAP = 10.0

# %HRmax -> session-RPE (CR-10) linear map, anchored on Foster's HR/RPE table
# (60% HRmax ~ RPE 2, 100% ~ RPE 10). The slope is a team-chosen prior.
_SRPE_HR_ANCHOR_PCT = 50.0
_SRPE_HR_PCT_PER_POINT = 5.0
# Plausible maximum-heart-rate band (bpm); values outside it are input errors.
_HR_MAX_MIN = 100
_HR_MAX_MAX = 230

# Data-quality guards protecting the response-learning loop from noise. All
# thresholds are team-chosen priors.
_MAX_E1RM_JUMP_FRACTION = 0.15  # session e1RM > 15% above recent best = suspect
_MAX_LOAD_OVER_1RM_FRACTION = 1.15  # a working load above 115% of a known 1RM (non-test)
_OUTLIER_HIGH_MULTIPLE = 3.0  # duration/distance > 3x the recent median
_OUTLIER_LOW_MULTIPLE = 1.0 / 3.0  # or below a third of it


def _validate_daily_loads(daily_loads: Sequence[float]) -> None:
    for day, value in enumerate(daily_loads):
        if not math.isfinite(value):
            msg = f"daily loads must be finite, got {value!r} at index {day}"
            raise ValueError(msg)
        if value < 0:
            msg = f"daily loads must not be negative, got {value!r} at index {day}"
            raise ValueError(msg)


def session_rpe_load(rpe: int, duration_min: int) -> float:
    """Return Foster's session-RPE load: RPE (CR-10) x duration in minutes.

    Duration is whole minutes by design; sub-minute precision is not
    meaningful for session-RPE quantification.
    """
    validate_whole_number("rpe", rpe)
    validate_whole_number("duration_min", duration_min)
    if not MIN_RPE <= rpe <= MAX_RPE:
        msg = f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe!r}"
        raise ValueError(msg)
    if duration_min <= 0:
        msg = f"duration_min must be positive, got {duration_min!r}"
        raise ValueError(msg)
    return float(rpe * duration_min)


def weekly_loads(daily_loads: Sequence[float]) -> list[float]:
    """Sum daily loads into consecutive 7-day blocks (last block may be partial).

    Blocks are anchored at the first element (oldest day), so a short final
    block contains the most recent days. This is NOT aligned with
    acute_chronic_ratio's end-anchored windows unless the history length is a
    multiple of 7.
    """
    _validate_daily_loads(daily_loads)
    return [
        sum(daily_loads[start : start + DAYS_PER_WEEK])
        for start in range(0, len(daily_loads), DAYS_PER_WEEK)
    ]


def _ewma(values: Sequence[float], tau: int) -> float:
    """Exponentially weighted moving average, seeded at zero, returned at the end."""
    alpha = 1.0 - math.exp(-1.0 / tau)
    state = 0.0
    for value in values:
        state += alpha * (value - state)
    return state


def acute_chronic_ratio(
    daily_loads: Sequence[float], method: AcwrMethod = "rolling"
) -> float | None:
    """Return the acute:chronic workload ratio (coupled, descriptive only).

    method="rolling" (default) is the classic coupled ACWR: acute 7-day mean
    over chronic 28-day mean, both end-anchored on the most recent 28 days.
    method="ewma" is the Williams et al. exponentially-weighted variant (acute
    EWMA over chronic EWMA), which weights recent days more and needs no hard
    window cut-off. Both self-correlate and both are coarse trends only — never
    an injury probability.

    Returns None when fewer than 28 days of history exist or when the chronic
    term is zero (an untrained window makes the ratio meaningless).
    """
    _validate_daily_loads(daily_loads)
    if method not in ("rolling", "ewma"):
        msg = f"method must be 'rolling' or 'ewma', got {method!r}"
        raise ValueError(msg)
    if len(daily_loads) < CHRONIC_WINDOW_DAYS:
        return None
    if method == "ewma":
        chronic = _ewma(daily_loads, _ACWR_CHRONIC_TAU)
        if chronic == 0:
            return None
        return _ewma(daily_loads, _ACWR_ACUTE_TAU) / chronic
    window = daily_loads[-CHRONIC_WINDOW_DAYS:]
    chronic = sum(window) / CHRONIC_WINDOW_DAYS
    if chronic == 0:
        return None
    acute = sum(window[-DAYS_PER_WEEK:]) / DAYS_PER_WEEK
    return acute / chronic


def _population_std(values: Sequence[float], mean: float) -> float:
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def weekly_monotony(daily_loads_7: Sequence[float]) -> float | None:
    """Return Foster's training monotony: mean daily load / population SD.

    Takes exactly 7 daily loads (rest days count as zeros). Higher monotony
    (a flat week with little day-to-day variation) is Foster's marker of a
    poorly varied load. Returns None when the SD is zero (a perfectly uniform
    week, including an all-rest week) — monotony is undefined there.
    """
    _validate_daily_loads(daily_loads_7)
    if len(daily_loads_7) != DAYS_PER_WEEK:
        msg = f"weekly_monotony needs exactly {DAYS_PER_WEEK} daily loads, got {len(daily_loads_7)}"
        raise ValueError(msg)
    mean = sum(daily_loads_7) / DAYS_PER_WEEK
    std = _population_std(daily_loads_7, mean)
    if std == 0:
        return None
    return mean / std


def weekly_strain(daily_loads_7: Sequence[float]) -> float | None:
    """Return Foster's training strain: weekly load total x monotony.

    Takes exactly 7 daily loads. Strain combines how much and how monotonously
    the week was loaded; Foster linked spikes in strain to illness/injury, but
    treat it as a descriptive trend, not a prediction. Returns None when
    monotony is undefined (uniform week).
    """
    monotony = weekly_monotony(daily_loads_7)
    if monotony is None:
        return None
    return sum(daily_loads_7) * monotony


@dataclass(frozen=True)
class DayState:
    """One day of the fitness-fatigue model (all descriptive trend values)."""

    date_index: int
    ctl: float  # chronic training load = "fitness" trend
    atl: float  # acute training load = "fatigue" trend
    tsb: float  # training stress balance = "freshness" trend (ctl - atl)


def fitness_fatigue_series(
    daily_loads: Sequence[float], ctl_tau: int = CTL_TAU_DAYS, atl_tau: int = ATL_TAU_DAYS
) -> list[DayState]:
    """Return the day-by-day CTL/ATL/TSB fitness-fatigue trend (EWMA impulse-response).

    CTL (chronic, ctl_tau=42d) tracks fitness; ATL (acute, atl_tau=7d) tracks
    fatigue; TSB = CTL - ATL is freshness (positive = fresh, negative = fatigued).
    Both EWMAs are seeded at zero, so the first weeks ramp up from cold. These
    are DESCRIPTIVE trends (a deterministic precursor to a fitted Banister model),
    never performance predictions. Taus are modelling conventions, overridable.
    """
    _validate_daily_loads(daily_loads)
    for name, tau in (("ctl_tau", ctl_tau), ("atl_tau", atl_tau)):
        validate_whole_number(name, tau)
        if tau < 1:
            msg = f"{name} must be >= 1 day, got {tau!r}"
            raise ValueError(msg)
    ctl_alpha = 1.0 - math.exp(-1.0 / ctl_tau)
    atl_alpha = 1.0 - math.exp(-1.0 / atl_tau)
    ctl = 0.0
    atl = 0.0
    series: list[DayState] = []
    for index, load in enumerate(daily_loads):
        ctl += ctl_alpha * (load - ctl)
        atl += atl_alpha * (load - atl)
        series.append(DayState(date_index=index, ctl=ctl, atl=atl, tsb=ctl - atl))
    return series


ReadinessBand = Literal["green", "amber", "red"]


@dataclass(frozen=True)
class ReadinessAssessment:
    """A pre-session readiness read (descriptive; 0-100, higher = fresher)."""

    score_0_100: float
    band: ReadinessBand
    drivers: dict[str, float]  # per-item 0-100 sub-scores + optional hrv modifier


def _hooper_subscore(name: str, value: int) -> float:
    validate_whole_number(name, value)
    if not _HOOPER_MIN <= value <= _HOOPER_MAX:
        msg = f"{name} must be a Hooper rating {_HOOPER_MIN}-{_HOOPER_MAX} (1=best), got {value!r}"
        raise ValueError(msg)
    return (_HOOPER_MAX - value) / (_HOOPER_MAX - _HOOPER_MIN) * 100.0


def readiness_score(
    sleep: int,
    fatigue: int,
    soreness: int,
    stress: int,
    hrv_delta_pct: float | None = None,
) -> ReadinessAssessment:
    """Score pre-session readiness 0-100 from the four Hooper items (+ optional HRV).

    Each item is rated 1 (best) to 7 (worst): sleep quality, fatigue, muscle
    soreness, stress. They are inverted and averaged to 0-100 (higher = fresher).
    hrv_delta_pct, when given, is HRV vs the athlete's own baseline as a percent
    (+10 = 10% above); it nudges the score up/down, capped at +/-10 points. Bands:
    >= 75 green, 50-74 amber, < 50 red. Descriptive only — a readiness read guides
    autoregulation, it is not a diagnosis. drivers holds each item's sub-score.
    """
    subs = {
        "sleep": _hooper_subscore("sleep", sleep),
        "fatigue": _hooper_subscore("fatigue", fatigue),
        "soreness": _hooper_subscore("soreness", soreness),
        "stress": _hooper_subscore("stress", stress),
    }
    score = sum(subs.values()) / len(subs)
    if hrv_delta_pct is not None:
        validate_finite("hrv_delta_pct", hrv_delta_pct)
        modifier = max(
            -_HRV_MODIFIER_CAP, min(_HRV_MODIFIER_CAP, hrv_delta_pct * _HRV_POINTS_PER_PCT)
        )
        score = max(0.0, min(100.0, score + modifier))
        subs["hrv_modifier"] = modifier
    band: ReadinessBand = (
        "green" if score >= _READINESS_GREEN else "amber" if score >= _READINESS_AMBER else "red"
    )
    return ReadinessAssessment(score_0_100=score, band=band, drivers=subs)


def estimate_srpe_from_hr(avg_hr: float, hr_max: float) -> float:
    """Estimate a session-RPE (CR-10, 1-10) from average HR as a %HRmax.

    Linear map anchored on Foster's HR/RPE table (~60% HRmax -> RPE 2,
    100% -> RPE 10), for club sessions and imported files that carry HR but no
    logged RPE. avg_hr must be positive and not exceed hr_max; hr_max must be a
    plausible 100-230 bpm. Returns a float clamped to [1, 10] — confirm it with
    the athlete rather than treating an estimate as a logged fact.
    """
    validate_finite("avg_hr", avg_hr)
    validate_finite("hr_max", hr_max)
    if not _HR_MAX_MIN <= hr_max <= _HR_MAX_MAX:
        msg = f"hr_max must be a plausible {_HR_MAX_MIN}-{_HR_MAX_MAX} bpm, got {hr_max!r}"
        raise ValueError(msg)
    if avg_hr <= 0 or avg_hr > hr_max:
        msg = f"avg_hr must be positive and <= hr_max ({hr_max}), got {avg_hr!r}"
        raise ValueError(msg)
    pct = avg_hr / hr_max * 100.0
    rpe = (pct - _SRPE_HR_ANCHOR_PCT) / _SRPE_HR_PCT_PER_POINT
    return float(max(MIN_RPE, min(MAX_RPE, rpe)))


@dataclass(frozen=True)
class LoadBudget:
    """How much programmable load is left after committed external load."""

    programmable_budget: float
    external_total: float
    conflict: bool
    drivers: dict[str, float]


def budget_weekly_load(
    target_weekly_load: float,
    external_loads: Sequence[float],
    min_programmed_load: float = 0.0,
) -> LoadBudget:
    """Subtract committed external load from a weekly target to size programming.

    target_weekly_load is the intended total session-RPE load for the week;
    external_loads are the session-RPE loads the coach does NOT program (club
    practice, matches, physical work). programmable_budget = target - sum(external).
    conflict is True when the budget falls below min_programmed_load (the week's
    minimum effective programmed dose) — meaning external commitments alone
    already fill the week; surface that honestly. All loads must be non-negative.
    """
    for name, value in (
        ("target_weekly_load", target_weekly_load),
        ("min_programmed_load", min_programmed_load),
    ):
        validate_finite(name, value)
        if value < 0:
            msg = f"{name} must be non-negative, got {value!r}"
            raise ValueError(msg)
    _validate_daily_loads(external_loads)  # same non-negative/finite guard
    external_total = sum(external_loads)
    budget = target_weekly_load - external_total
    share = external_total / target_weekly_load if target_weekly_load > 0 else 0.0
    return LoadBudget(
        programmable_budget=budget,
        external_total=external_total,
        conflict=budget < min_programmed_load,
        drivers={"external_total": external_total, "external_share": share},
    )


ImplausibilityCode = Literal["e1rm_jump", "load_over_1rm", "duration_outlier", "distance_outlier"]


@dataclass(frozen=True)
class ImplausibilityFlag:
    """One data-quality concern about a logged session value."""

    code: ImplausibilityCode
    message: str


def flag_implausible_session(  # noqa: PLR0913 -- independent optional guards, all keyword-only
    *,
    session_e1rm_kg: float | None = None,
    recent_best_e1rm_kg: float | None = None,
    top_load_kg: float | None = None,
    known_1rm_kg: float | None = None,
    is_test: bool = False,
    duration_min: float | None = None,
    median_duration_min: float | None = None,
    distance_m: float | None = None,
    median_distance_m: float | None = None,
) -> list[ImplausibilityFlag]:
    """Flag logged values that look like data-entry noise (never auto-reject them).

    Guards, each a team-chosen prior: a session e1RM more than 15% above the
    recent best (session_e1rm_kg vs recent_best_e1rm_kg); a working load above
    115% of a known 1RM outside a test context (top_load_kg vs known_1rm_kg,
    is_test); a duration or distance more than 3x or below a third of the recent
    median. Every argument is optional — pass only what the session has. Returns
    a (possibly empty) list of flags for the coach to confirm with the athlete
    before the value feeds the response-learning loop; the entry still gets
    logged either way.
    """
    flags: list[ImplausibilityFlag] = []
    _flag_e1rm_jump(flags, session_e1rm_kg, recent_best_e1rm_kg)
    _flag_load_over_1rm(flags, top_load_kg, known_1rm_kg, is_test=is_test)
    _flag_outlier(flags, "duration", "duration_outlier", duration_min, median_duration_min)
    _flag_outlier(flags, "distance", "distance_outlier", distance_m, median_distance_m)
    return flags


def _flag_e1rm_jump(
    flags: list[ImplausibilityFlag], session_e1rm: float | None, recent_best: float | None
) -> None:
    if session_e1rm is None or recent_best is None or recent_best <= 0:
        return
    validate_finite("session_e1rm_kg", session_e1rm)
    validate_finite("recent_best_e1rm_kg", recent_best)
    if session_e1rm > recent_best * (1.0 + _MAX_E1RM_JUMP_FRACTION):
        jump = session_e1rm / recent_best - 1.0
        flags.append(
            ImplausibilityFlag(
                "e1rm_jump",
                f"estimated 1RM {session_e1rm:.1f} kg is {jump * 100:.0f}% above the recent "
                f"best {recent_best:.1f} kg (guard: >{_MAX_E1RM_JUMP_FRACTION * 100:.0f}%)",
            )
        )


def _flag_load_over_1rm(
    flags: list[ImplausibilityFlag],
    top_load: float | None,
    known_1rm: float | None,
    *,
    is_test: bool,
) -> None:
    if top_load is None or known_1rm is None or known_1rm <= 0 or is_test:
        return
    validate_finite("top_load_kg", top_load)
    validate_finite("known_1rm_kg", known_1rm)
    if top_load > known_1rm * _MAX_LOAD_OVER_1RM_FRACTION:
        flags.append(
            ImplausibilityFlag(
                "load_over_1rm",
                f"working load {top_load:.1f} kg exceeds {_MAX_LOAD_OVER_1RM_FRACTION:.2f}x the "
                f"known 1RM {known_1rm:.1f} kg outside a test — confirm the load or log a test",
            )
        )


def _flag_outlier(
    flags: list[ImplausibilityFlag],
    label: str,
    code: ImplausibilityCode,
    value: float | None,
    median: float | None,
) -> None:
    if value is None or median is None or median <= 0:
        return
    validate_finite(f"{label}_value", value)
    validate_finite(f"{label}_median", median)
    if value > median * _OUTLIER_HIGH_MULTIPLE or value < median * _OUTLIER_LOW_MULTIPLE:
        flags.append(
            ImplausibilityFlag(
                code,
                f"{label} {value:.0f} is far from the recent median {median:.0f} "
                f"(guard: {_OUTLIER_LOW_MULTIPLE:.2f}x-{_OUTLIER_HIGH_MULTIPLE:.0f}x)",
            )
        )
