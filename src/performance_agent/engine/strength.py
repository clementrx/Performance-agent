"""Strength math: 1RM estimation and percentage-based load prescription.

Formulas are only validated for 1-12 repetitions; these estimation formulas
degrade badly beyond ~10 reps, so higher inputs are rejected. The
percentage_for_reps_rir/reps_for_percentage_rir pair extends this to 18
effective reps (reps + RIR), with 13-18 carrying the extra uncertainty
documented on those functions.
"""

import math
from dataclasses import dataclass

from performance_agent.engine._validation import validate_finite, validate_whole_number
from performance_agent.engine.feasibility import TrainingAge

MAX_ESTIMATION_REPS = 12
MAX_PERCENTAGE = 1.3  # supra-maximal work (eccentrics, partials) tops out around 130%
MAX_EFFECTIVE_REPS = 18  # reps + RIR beyond this leaves the formula's validated range
# Back-off drops beyond 50% of 1RM stop being training weight (team-chosen prior).
MAX_BACKOFF_DROP = 0.5
# More than 10 back-off sets is volume programming, not a top-set day (team-chosen prior).
MAX_BACKOFF_SETS = 10
# Wave-loading bounds, all team-chosen priors: per-set jumps above 10% of 1RM
# skip too much of the intensity curve; 2-5 sets per wave and 1-4 waves cover
# every classic scheme.
MAX_WAVE_STEP = 0.1
MIN_STEPS_PER_WAVE = 2
MAX_STEPS_PER_WAVE = 5
MAX_WAVES = 4
# CR-10 session-RPE scale bounds (published scale, not a tunable prior).
MIN_RPE = 1.0
MAX_RPE = 10.0
# Standard ramp-up to a heavy working set, as (fraction of working load, reps).
# The shape a coach writes before a top strength set; all team-chosen priors.
WARMUP_RAMP: tuple[tuple[float, int], ...] = ((0.4, 5), (0.55, 4), (0.7, 3), (0.85, 2))
# Ramp sets whose absolute load falls below an empty Olympic barbell are dropped:
# ramping under the bar is not a warm-up (team-chosen prior).
MIN_WARMUP_LOAD_KG = 20.0


def _validate_load_and_reps(load_kg: float, reps: int) -> None:
    validate_whole_number("reps", reps)
    if load_kg <= 0:
        msg = f"load_kg must be positive, got {load_kg!r}"
        raise ValueError(msg)
    if not 1 <= reps <= MAX_ESTIMATION_REPS:
        msg = f"reps must be between 1 and {MAX_ESTIMATION_REPS}, got {reps!r}"
        raise ValueError(msg)


def one_rm_epley(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Epley formula: load * (1 + reps / 30).

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * (1 + reps / 30)


def one_rm_brzycki(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Brzycki formula: load * 36 / (37 - reps).

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged (float rounding in
    ``load * 36 / 36`` would otherwise land one ULP below the lifted load).
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * 36 / (37 - reps)


def one_rm_lombardi(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Lombardi formula: load * reps^0.10.

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * reps**0.10


def one_rm_wathan(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Wathan formula: 100*load / (48.8 + 53.8*e^(-0.075*reps)).

    At ``reps == 1`` the raw formula lands about 1.3% ABOVE the lifted load
    (100 / (48.8 + 53.8*e^-0.075) ~ 1.013), but a single rep at a given load
    is, by definition, at least a 1RM at that load — so ``reps == 1`` returns
    ``load_kg`` unchanged as a deliberate consistency clamp, matching the
    other formulas.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return 100 * load_kg / (48.8 + 53.8 * math.exp(-0.075 * reps))


def load_for_percentage(one_rm_kg: float, percentage: float) -> float:
    """Return the absolute load for a fraction of 1RM (e.g. 0.8 for 80%)."""
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < percentage <= MAX_PERCENTAGE:
        msg = f"percentage must be in (0, {MAX_PERCENTAGE}], got {percentage!r}"
        raise ValueError(msg)
    return one_rm_kg * percentage


def percentage_for_reps_rir(reps: int, rir: int) -> float:
    """Fraction of 1RM at which `reps` clean reps leave `rir` in reserve.

    Epley inverted at effective reps = reps + rir:
    pct = 1 / (1 + (reps + rir) / 30). Effective reps are capped at 18; the
    Epley curve is validated to ~12, so 13-18 carry extra uncertainty the
    caller must label. One all-out rep (reps=1, rir=0) is by definition
    100% of 1RM, so effective reps == 1 returns exactly 1.0.
    """
    validate_whole_number("reps", reps)
    validate_whole_number("rir", rir)
    if reps < 1:
        msg = f"reps must be at least 1, got {reps!r}"
        raise ValueError(msg)
    if rir < 0:
        msg = f"rir must be non-negative, got {rir!r}"
        raise ValueError(msg)
    effective_reps = reps + rir
    if effective_reps > MAX_EFFECTIVE_REPS:
        msg = f"reps + rir must be at most {MAX_EFFECTIVE_REPS}, got {effective_reps!r}"
        raise ValueError(msg)
    if effective_reps == 1:
        return 1.0
    return 1 / (1 + effective_reps / 30)


def reps_for_percentage_rir(percentage: float, rir: int) -> int:
    """Max clean reps at a fraction of 1RM leaving `rir` in reserve (floor).

    Inverts percentage_for_reps_rir: effective reps = floor(30 * (1/pct - 1)),
    with at least one effective rep (a single rep is always possible at or
    below 100% of 1RM), then subtracts `rir`. Raises if the percentage is
    too high to leave `rir` reps in reserve, or if it implies more effective
    reps than the Epley curve is valid for. Effective reps of 13-18 carry
    extra uncertainty, same as the forward percentage_for_reps_rir function.
    """
    validate_whole_number("rir", rir)
    if not 0 < percentage <= 1:
        msg = f"percentage must be in (0, 1], got {percentage!r}"
        raise ValueError(msg)
    if rir < 0:
        msg = f"rir must be non-negative, got {rir!r}"
        raise ValueError(msg)
    # The epsilon absorbs float rounding so exact Epley percentages round-trip.
    effective_reps = max(math.floor(30 * (1 / percentage - 1) + 1e-9), 1)
    if effective_reps > MAX_EFFECTIVE_REPS:
        msg = (
            f"percentage {percentage!r} implies more than {MAX_EFFECTIVE_REPS} "
            "effective reps; the Epley curve is not valid there"
        )
        raise ValueError(msg)
    reps = effective_reps - rir
    if reps < 1:
        msg = (
            f"percentage {percentage!r} is too high to leave {rir!r} reps in reserve; "
            "lower the percentage or the RIR"
        )
        raise ValueError(msg)
    return reps


@dataclass(frozen=True)
class WeeklySetTargets:
    """Weekly hard-set targets for one muscle group."""

    minimum_effective_sets: int
    optimal_low_sets: int
    optimal_high_sets: int
    maximum_adaptive_sets: int


# Weekly hard sets per muscle group by training age. Anchored on the
# dose-response meta-analysis in the corpus
# (resistance-training-volume-hypertrophy-meta-2017); the "10+ sets/muscle/week
# outperform fewer" direction is the paper's headline finding (the corpus
# record itself is kept non-directional), and the spread across training ages
# is a team-chosen prior.
WEEKLY_SET_TARGETS: dict[TrainingAge, WeeklySetTargets] = {
    TrainingAge.BEGINNER: WeeklySetTargets(6, 8, 12, 16),
    TrainingAge.INTERMEDIATE: WeeklySetTargets(8, 10, 16, 20),
    TrainingAge.ADVANCED: WeeklySetTargets(10, 12, 20, 26),
}


def weekly_set_targets(training_age: TrainingAge) -> WeeklySetTargets:
    """Return per-muscle weekly hard-set targets for a training-age bucket."""
    return WEEKLY_SET_TARGETS[training_age]


@dataclass(frozen=True)
class ProgressionDecision:
    """Next-session prescription from a double-progression rule."""

    next_load_kg: float
    next_target_reps: int
    load_increased: bool


def _validate_double_progression_inputs(
    reps_achieved: list[int],
    load_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    increment_kg: float,
) -> None:
    """Raise ValueError if any double_progression input is out of range."""
    for name, value in (("rep_range_low", rep_range_low), ("rep_range_high", rep_range_high)):
        validate_whole_number(name, value)
    if not 1 <= rep_range_low < rep_range_high <= MAX_EFFECTIVE_REPS:
        msg = (
            f"rep range must satisfy 1 <= low < high <= {MAX_EFFECTIVE_REPS}, "
            f"got low={rep_range_low!r}, high={rep_range_high!r}"
        )
        raise ValueError(msg)
    if load_kg <= 0:
        msg = f"load_kg must be positive, got {load_kg!r}"
        raise ValueError(msg)
    if increment_kg <= 0:
        msg = f"increment_kg must be positive, got {increment_kg!r}"
        raise ValueError(msg)
    if not reps_achieved:
        msg = "reps_achieved must not be empty"
        raise ValueError(msg)
    for reps in reps_achieved:
        validate_whole_number("reps_achieved entry", reps)
        if reps < 0:
            msg = f"reps_achieved entries must be non-negative, got {reps!r}"
            raise ValueError(msg)


def double_progression(
    reps_achieved: list[int],
    load_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    increment_kg: float,
) -> ProgressionDecision:
    """Apply the double-progression rule to one exercise's last session.

    Fill the rep range first, then add load: when every set reached
    rep_range_high, add increment_kg and reset the target to rep_range_low;
    otherwise hold the load and target the lowest achieved set + 1 (never
    above rep_range_high by construction). Load REDUCTION (deload/regression)
    is out of scope: when performance falls below the rep range, the hold
    branch's target is unfloored and next_target_reps may fall below
    rep_range_low.

    Args:
        reps_achieved: Reps completed per set last session (non-empty, >= 0).
        load_kg: Load used last session, in kg (positive).
        rep_range_low: Bottom of the working rep range (>= 1).
        rep_range_high: Top of the working rep range (> low, <= 18).
        increment_kg: Load added when the range is filled (positive).

    Returns:
        A ProgressionDecision with the next load, next rep target and
        whether the load increased.
    """
    _validate_double_progression_inputs(
        reps_achieved, load_kg, rep_range_low, rep_range_high, increment_kg
    )
    if all(reps >= rep_range_high for reps in reps_achieved):
        return ProgressionDecision(
            next_load_kg=load_kg + increment_kg,
            next_target_reps=rep_range_low,
            load_increased=True,
        )
    return ProgressionDecision(
        next_load_kg=load_kg,
        next_target_reps=min(min(reps_achieved) + 1, rep_range_high),
        load_increased=False,
    )


@dataclass(frozen=True)
class TopSetBackoff:
    """A top-set/back-off session prescription."""

    top_set_load_kg: float
    backoff_load_kg: float
    backoff_sets: int


def top_set_backoff(
    one_rm_kg: float,
    top_percentage: float,
    backoff_drop: float,
    backoff_sets: int,
) -> TopSetBackoff:
    """Prescribe one top set and its back-off sets from a 1RM.

    Top load is one_rm_kg * top_percentage; back-off load sits backoff_drop
    (a fraction of 1RM, e.g. 0.10 = 10 percentage points) below the top
    percentage, for backoff_sets sets. top_percentage must be in
    (0, MAX_PERCENTAGE], backoff_drop in (0, 0.5], backoff_sets a whole
    number 1-10, and the resulting back-off percentage must stay positive.
    """
    validate_whole_number("backoff_sets", backoff_sets)
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < top_percentage <= MAX_PERCENTAGE:
        msg = f"top_percentage must be in (0, {MAX_PERCENTAGE}], got {top_percentage!r}"
        raise ValueError(msg)
    if not 0 < backoff_drop <= MAX_BACKOFF_DROP:
        msg = (
            f"backoff_drop must be in (0, {MAX_BACKOFF_DROP}], got {backoff_drop!r}: "
            "back-off drops beyond 50% stop being training weight"
        )
        raise ValueError(msg)
    if not 1 <= backoff_sets <= MAX_BACKOFF_SETS:
        msg = f"backoff_sets must be between 1 and {MAX_BACKOFF_SETS}, got {backoff_sets!r}"
        raise ValueError(msg)
    backoff_percentage = top_percentage - backoff_drop
    if backoff_percentage <= 0:
        msg = (
            f"backoff_drop {backoff_drop!r} leaves no back-off load below "
            f"top_percentage {top_percentage!r}"
        )
        raise ValueError(msg)
    return TopSetBackoff(
        top_set_load_kg=one_rm_kg * top_percentage,
        backoff_load_kg=one_rm_kg * backoff_percentage,
        backoff_sets=backoff_sets,
    )


@dataclass(frozen=True)
class WaveStep:
    """One set in a wave-loading scheme (wave and step are 1-indexed)."""

    wave: int
    step: int
    percentage: float
    load_kg: float


def _validate_wave_loading_inputs(  # noqa: PLR0913 -- mirrors wave_loading's plan-approved signature
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> None:
    """Raise ValueError if any wave_loading input is out of range."""
    validate_whole_number("steps_per_wave", steps_per_wave)
    validate_whole_number("waves", waves)
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < base_percentage <= 1:
        msg = f"base_percentage must be in (0, 1], got {base_percentage!r}"
        raise ValueError(msg)
    if not 0 < step_increment <= MAX_WAVE_STEP:
        msg = f"step_increment must be in (0, {MAX_WAVE_STEP}], got {step_increment!r}"
        raise ValueError(msg)
    if not MIN_STEPS_PER_WAVE <= steps_per_wave <= MAX_STEPS_PER_WAVE:
        msg = (
            f"steps_per_wave must be between {MIN_STEPS_PER_WAVE} and "
            f"{MAX_STEPS_PER_WAVE}, got {steps_per_wave!r}"
        )
        raise ValueError(msg)
    if not 1 <= waves <= MAX_WAVES:
        msg = f"waves must be between 1 and {MAX_WAVES}, got {waves!r}"
        raise ValueError(msg)
    if not 0 <= inter_wave_increment < step_increment:
        msg = (
            f"inter_wave_increment must be in [0, step_increment), got "
            f"{inter_wave_increment!r} with step_increment {step_increment!r}: waves must "
            "overlap — each wave starts below where the previous one ended"
        )
        raise ValueError(msg)


def wave_loading(  # noqa: PLR0913 -- plan-approved signature; all call sites use keywords
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> list[WaveStep]:
    """Generate a wave-loading set sequence (waves and steps are 1-indexed).

    Wave w, step s: percentage = base_percentage + (s-1)*step_increment +
    (w-1)*inter_wave_increment; load = one_rm_kg * percentage.
    inter_wave_increment must stay strictly below step_increment so waves
    OVERLAP — the defining property of wave loading: wave 2 starts lower
    than wave 1 ended. The peak percentage (last step of the last wave)
    must not exceed MAX_PERCENTAGE.
    """
    _validate_wave_loading_inputs(
        one_rm_kg, base_percentage, step_increment, steps_per_wave, waves, inter_wave_increment
    )
    peak = (
        base_percentage + (steps_per_wave - 1) * step_increment + (waves - 1) * inter_wave_increment
    )
    if peak > MAX_PERCENTAGE:
        msg = (
            f"wave scheme peaks at {peak!r} of 1RM, above the {MAX_PERCENTAGE} supra-maximal "
            "cap — lower base_percentage, step_increment, waves or inter_wave_increment"
        )
        raise ValueError(msg)
    steps: list[WaveStep] = []
    for wave in range(1, waves + 1):
        for step in range(1, steps_per_wave + 1):
            percentage = (
                base_percentage + (step - 1) * step_increment + (wave - 1) * inter_wave_increment
            )
            steps.append(WaveStep(wave, step, percentage, one_rm_kg * percentage))
    return steps


def warmup_scheme(target_load_kg: float) -> list[tuple[float, int]]:
    """Ramp-up sets leading to a heavy working load, as (fraction, reps) pairs.

    Returns the standard progressively-heavier warm-up a coach writes before a
    top strength set (WARMUP_RAMP), dropping any set whose absolute load would
    fall below an empty barbell (MIN_WARMUP_LOAD_KG) — ramping under the bar is
    not a warm-up. A light target may therefore yield a shorter ramp or none.

    Args:
        target_load_kg: The working load the ramp builds up to (positive).

    Returns:
        (fraction_of_target, reps) pairs in ascending order; each fraction is
        strictly below 1.0 (the working set itself is not a warm-up set).
    """
    validate_finite("target_load_kg", target_load_kg)
    if target_load_kg <= 0:
        msg = f"target_load_kg must be positive, got {target_load_kg!r}"
        raise ValueError(msg)
    return [
        (fraction, reps)
        for fraction, reps in WARMUP_RAMP
        if target_load_kg * fraction >= MIN_WARMUP_LOAD_KG
    ]


def rir_from_rpe(rpe: float) -> float:
    """Convert session RPE (1-10 scale) to reps in reserve: RIR = 10 - RPE.

    Accepts half-point RPEs (e.g. 8.5 -> 1.5 RIR). Prescription work lives
    at RPE 5-10; below 5 the conversion is arithmetic but rarely meaningful.
    """
    validate_finite("rpe", rpe)
    if not MIN_RPE <= rpe <= MAX_RPE:
        msg = f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe!r}"
        raise ValueError(msg)
    # Half points are exactly representable in binary floats, so a valid
    # rpe * 2 is an exact integer and the comparison is safe.
    doubled = rpe * 2
    if doubled != round(doubled):
        msg = f"rpe must be on the half-point scale (1.0, 1.5, ... 10.0), got {rpe!r}"
        raise ValueError(msg)
    return MAX_RPE - rpe
