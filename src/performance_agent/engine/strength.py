"""Strength math: 1RM estimation and percentage-based load prescription.

Formulas are only validated for 1-12 repetitions; both Epley and Brzycki
degrade badly beyond ~10 reps, so higher inputs are rejected. The
percentage_for_reps_rir/reps_for_percentage_rir pair extends this to 18
effective reps (reps + RIR), with 13-18 carrying the extra uncertainty
documented on those functions.
"""

import math
from dataclasses import dataclass

from performance_agent.engine._validation import validate_whole_number
from performance_agent.engine.feasibility import TrainingAge

MAX_ESTIMATION_REPS = 12
MAX_PERCENTAGE = 1.3  # supra-maximal work (eccentrics, partials) tops out around 130%
MAX_EFFECTIVE_REPS = 18  # reps + RIR beyond this leaves the formula's validated range


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

    minimum_effective: int
    optimal_low: int
    optimal_high: int
    maximum_adaptive: int


# Weekly hard sets per muscle group by training age. Anchored on the
# dose-response meta-analysis in the corpus (resistance-training-volume-
# hypertrophy-meta-2017: 10+ sets/muscle/week outperform fewer); the spread
# across training ages is a team-chosen prior.
WEEKLY_SET_TARGETS: dict[TrainingAge, WeeklySetTargets] = {
    TrainingAge.BEGINNER: WeeklySetTargets(6, 8, 12, 16),
    TrainingAge.INTERMEDIATE: WeeklySetTargets(8, 10, 16, 20),
    TrainingAge.ADVANCED: WeeklySetTargets(10, 12, 20, 26),
}


def weekly_set_targets(training_age: TrainingAge) -> WeeklySetTargets:
    """Return per-muscle weekly hard-set targets for a training-age bucket."""
    return WEEKLY_SET_TARGETS[training_age]
