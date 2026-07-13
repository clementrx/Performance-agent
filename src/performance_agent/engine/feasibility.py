"""Goal feasibility: required progression rate vs empirically achievable rates.

Model (documented assumption, revisit with data): improvement demand is spread
linearly over the available weeks and compared against sustainable weekly
improvement rates by training age. The required/achievable ratio maps to a
probability through a logistic curve centred at ratio 1.0. This is a coarse,
honest prior — not a guarantee — and downstream agents must present it with
its drivers (the two rates), never as a bare number. The model assumes a
constant achievable rate over arbitrary horizons and models no asymptotic
performance limit, so long-horizon and already-met verdicts are optimistic.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number


class TrainingAge(StrEnum):
    """Coarse training-experience buckets used for achievable-rate lookup."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Sustainable weekly improvement in endurance performance (fraction of current
# time), by training age. Team-chosen priors, not yet validated against data.
ENDURANCE_ACHIEVABLE_WEEKLY_RATE: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.010,
    TrainingAge.INTERMEDIATE: 0.005,
    TrainingAge.ADVANCED: 0.0025,
}

LOGISTIC_STEEPNESS = 3.0
# Clamp the logistic exponent so extreme ratios neither overflow math.exp nor
# collapse the probability to exactly 0.0 or 1.0 (it must stay in (0, 1)).
MAX_LOGISTIC_EXPONENT = 30.0

# Sustainable weekly 1RM improvement (fraction of current 1RM), by training
# age. Team-chosen priors, not yet validated against data; strength gains
# decay far faster with training age than endurance gains.
STRENGTH_ACHIEVABLE_WEEKLY_RATE: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.010,
    TrainingAge.INTERMEDIATE: 0.0035,
    TrainingAge.ADVANCED: 0.0010,
}

# Sustainable lean-mass gain (kg per week), by training age. Team-chosen
# priors derived from common coaching heuristics (~1%/0.5%/0.25% bodyweight
# per month for 70-90 kg athletes); revisit with data.
HYPERTROPHY_ACHIEVABLE_WEEKLY_KG: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.23,
    TrainingAge.INTERMEDIATE: 0.11,
    TrainingAge.ADVANCED: 0.05,
}

# Safe weekly fat-loss rate as a fraction of bodyweight. 0.5-1.0 %/week is
# the range commonly recommended to preserve lean mass; we score against the
# 0.75% midpoint and flag anything above 1.0% as muscle-risking.
BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW = 0.0075
BODYCOMP_MAX_SAFE_WEEKLY_LOSS_PCT_BW = 0.010
# Essential-fat floors below which we refuse to plan. Team-chosen priors
# aligned with common physiology references.
MIN_HEALTHY_BODY_FAT_PCT: dict[str, float] = {"male": 5.0, "female": 12.0}
# Plausible input range for a body-fat percentage; anything outside it is
# almost certainly a data-entry error rather than a real measurement.
MIN_PLAUSIBLE_BODY_FAT_PCT = 3.0
MAX_PLAUSIBLE_BODY_FAT_PCT = 60.0


@dataclass(frozen=True)
class FeasibilityResult:
    """Feasibility verdict with the rates that produced it (for explainability).

    Units depend on the goal type: endurance and strength express
    improvement_needed and the weekly rates as fractions of current
    performance; hypertrophy expresses them in absolute kg and kg/week.
    """

    improvement_needed: float
    required_weekly_rate: float
    achievable_weekly_rate: float
    ratio: float
    probability: float


def _logistic_probability(ratio: float) -> float:
    """Map a required/achievable ratio to a probability via the shared logistic."""
    exponent = LOGISTIC_STEEPNESS * (ratio - 1)
    exponent = max(min(exponent, MAX_LOGISTIC_EXPONENT), -MAX_LOGISTIC_EXPONENT)
    return 1 / (1 + math.exp(exponent))


# A measured window shorter than this many weeks carries extra uncertainty and
# is flagged so the narrator caveats it (team-chosen prior).
MEASURED_SMALL_N_WEEKS = 8


@dataclass(frozen=True)
class MeasuredFeasibility:
    """A feasibility probability recomputed from the athlete's MEASURED rate.

    Same logistic mapping as the population verdict, but scoring the required
    weekly rate against the athlete's own measured rate instead of the
    training-age prior. small_n flags a short measurement window.
    """

    measured_weekly_rate: float
    required_weekly_rate: float
    ratio: float
    probability: float
    small_n: bool


def recalibrated_feasibility(
    required_weekly_rate: float, measured_weekly_rate: float, measured_n_weeks: int
) -> MeasuredFeasibility:
    """Recompute a feasibility probability from a measured weekly rate.

    required_weekly_rate comes from a population feasibility verdict (already in
    the goal's units — a fraction for endurance/strength/bodycomp, kg/week for
    hypertrophy); measured_weekly_rate must be positive and in the SAME units.
    The ratio and logistic mapping match the population path, so the two
    probabilities are directly comparable. small_n is True below
    MEASURED_SMALL_N_WEEKS weeks of measurement.
    """
    validate_whole_number("measured_n_weeks", measured_n_weeks)
    validate_finite("required_weekly_rate", required_weekly_rate)
    validate_finite("measured_weekly_rate", measured_weekly_rate)
    if measured_weekly_rate <= 0:
        msg = f"measured_weekly_rate must be positive, got {measured_weekly_rate!r}"
        raise ValueError(msg)
    if measured_n_weeks <= 0:
        msg = f"measured_n_weeks must be positive, got {measured_n_weeks!r}"
        raise ValueError(msg)
    ratio = required_weekly_rate / measured_weekly_rate
    return MeasuredFeasibility(
        measured_weekly_rate=measured_weekly_rate,
        required_weekly_rate=required_weekly_rate,
        ratio=ratio,
        probability=_logistic_probability(ratio),
        small_n=measured_n_weeks < MEASURED_SMALL_N_WEEKS,
    )


def _validate_inputs(current_time_s: float, target_time_s: float, weeks: int) -> None:
    validate_whole_number("weeks", weeks)
    for name, value in (("current_time_s", current_time_s), ("target_time_s", target_time_s)):
        validate_finite(name, value)
    if current_time_s <= 0 or target_time_s <= 0 or weeks <= 0:
        msg = (
            "current_time_s, target_time_s and weeks must be positive, "
            f"got {current_time_s!r}, {target_time_s!r}, {weeks!r}"
        )
        raise ValueError(msg)


def endurance_feasibility(
    current_time_s: float,
    target_time_s: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of an endurance time goal.

    Args:
        current_time_s: Current performance over the goal distance, in seconds.
        target_time_s: Target performance over the same distance, in seconds.
        weeks: Whole weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    _validate_inputs(current_time_s, target_time_s, weeks)
    improvement_needed = (current_time_s - target_time_s) / current_time_s
    required_weekly_rate = improvement_needed / weeks
    achievable_weekly_rate = ENDURANCE_ACHIEVABLE_WEEKLY_RATE[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    probability = _logistic_probability(ratio)
    return FeasibilityResult(
        improvement_needed=improvement_needed,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=probability,
    )


def _validate_load_inputs(current_one_rm_kg: float, target_one_rm_kg: float, weeks: int) -> None:
    validate_whole_number("weeks", weeks)
    for name, value in (
        ("current_one_rm_kg", current_one_rm_kg),
        ("target_one_rm_kg", target_one_rm_kg),
    ):
        validate_finite(name, value)
    if current_one_rm_kg <= 0 or target_one_rm_kg <= 0 or weeks <= 0:
        msg = (
            "current_one_rm_kg, target_one_rm_kg and weeks must be positive, "
            f"got {current_one_rm_kg!r}, {target_one_rm_kg!r}, {weeks!r}"
        )
        raise ValueError(msg)


def strength_feasibility(
    current_one_rm_kg: float,
    target_one_rm_kg: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of a strength (1RM) goal.

    Sign convention is INVERTED versus endurance: a bigger target is better,
    so improvement_needed = (target - current) / current. A target at or
    below the current 1RM yields improvement <= 0, ratio <= 0 and a
    probability above 0.95 — already-met goals are easy by construction.

    Args:
        current_one_rm_kg: Current estimated 1RM for the lift, in kg.
        target_one_rm_kg: Target 1RM for the same lift, in kg.
        weeks: Whole weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    _validate_load_inputs(current_one_rm_kg, target_one_rm_kg, weeks)
    improvement_needed = (target_one_rm_kg - current_one_rm_kg) / current_one_rm_kg
    required_weekly_rate = improvement_needed / weeks
    achievable_weekly_rate = STRENGTH_ACHIEVABLE_WEEKLY_RATE[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    return FeasibilityResult(
        improvement_needed=improvement_needed,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=_logistic_probability(ratio),
    )


def hypertrophy_feasibility(
    target_lean_gain_kg: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of a lean-mass gain goal.

    Unlike the endurance and strength paths, rates are ABSOLUTE kilograms per
    week, not fractions of current performance: improvement_needed carries
    the target gain in kg, and required/achievable_weekly_rate are kg/week.
    The ratio and logistic mapping are shared with the other goal types.

    Args:
        target_lean_gain_kg: Lean mass to gain, in kg (must be positive).
        weeks: Whole weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    validate_whole_number("weeks", weeks)
    validate_finite("target_lean_gain_kg", target_lean_gain_kg)
    if target_lean_gain_kg <= 0 or weeks <= 0:
        msg = (
            "target_lean_gain_kg and weeks must be positive, "
            f"got {target_lean_gain_kg!r}, {weeks!r}"
        )
        raise ValueError(msg)
    required_weekly_rate = target_lean_gain_kg / weeks
    achievable_weekly_rate = HYPERTROPHY_ACHIEVABLE_WEEKLY_KG[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    return FeasibilityResult(
        improvement_needed=target_lean_gain_kg,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=_logistic_probability(ratio),
    )


@dataclass(frozen=True)
class BodycompFeasibility:
    """Body-composition verdict with its drivers (for explainability)."""

    fat_mass_to_lose_kg: float
    required_weekly_loss_pct_bw: float
    achievable_weekly_loss_pct_bw: float
    ratio: float
    probability: float
    exceeds_safe_rate: bool


def bodycomp_feasibility(
    current_weight_kg: float,
    current_body_fat_pct: float,
    target_body_fat_pct: float,
    weeks: int,
    sex: Literal["male", "female"],
) -> BodycompFeasibility:
    """Score the feasibility of a fat-loss body-composition goal.

    Assumes constant lean mass: fat to lose is the weight change needed to
    hit the target body-fat percentage at today's lean mass. The required
    weekly loss (fraction of current bodyweight) is scored against the 0.75%
    midpoint of the commonly recommended 0.5-1.0%/week band; anything above
    1.0%/week additionally sets exceeds_safe_rate (muscle-risking deadline).
    Targets below the healthy minimum for the athlete's sex are refused with
    a ValueError. Body-fat GAIN goals are out of scope and also refused.

    Args:
        current_weight_kg: Current bodyweight, in kg.
        current_body_fat_pct: Current body-fat percentage, in (3, 60).
        target_body_fat_pct: Target body-fat percentage, in (3, 60), below
            current and at or above the healthy floor for `sex`.
        weeks: Whole weeks available until the goal deadline.
        sex: "male" or "female" (selects the healthy body-fat floor).

    Returns:
        A BodycompFeasibility whose probability is in the open interval (0, 1).
    """
    validate_whole_number("weeks", weeks)
    validate_finite("current_weight_kg", current_weight_kg)
    for name, value in (
        ("current_body_fat_pct", current_body_fat_pct),
        ("target_body_fat_pct", target_body_fat_pct),
    ):
        validate_finite(name, value)
    if current_weight_kg <= 0 or weeks <= 0:
        msg = f"current_weight_kg and weeks must be positive, got {current_weight_kg!r}, {weeks!r}"
        raise ValueError(msg)
    for name, value in (
        ("current_body_fat_pct", current_body_fat_pct),
        ("target_body_fat_pct", target_body_fat_pct),
    ):
        if not MIN_PLAUSIBLE_BODY_FAT_PCT < value < MAX_PLAUSIBLE_BODY_FAT_PCT:
            msg = f"{name} must be between 3 and 60 percent (exclusive), got {value!r}"
            raise ValueError(msg)
    if target_body_fat_pct >= current_body_fat_pct:
        msg = (
            "target_body_fat_pct must be below current_body_fat_pct; "
            "body-fat GAIN goals are not modelled; treat as hypertrophy"
        )
        raise ValueError(msg)
    if sex not in MIN_HEALTHY_BODY_FAT_PCT:
        msg = f"sex must be 'male' or 'female', got {sex!r}"
        raise ValueError(msg)
    healthy_floor = MIN_HEALTHY_BODY_FAT_PCT[sex]
    if target_body_fat_pct < healthy_floor:
        msg = (
            f"target_body_fat_pct {target_body_fat_pct!r} is below the healthy minimum "
            f"for {sex} ({healthy_floor}%) — refuse and refer to a health professional"
        )
        raise ValueError(msg)
    lean_mass_kg = current_weight_kg * (1 - current_body_fat_pct / 100)
    target_weight_kg = lean_mass_kg / (1 - target_body_fat_pct / 100)
    fat_mass_to_lose_kg = current_weight_kg - target_weight_kg
    required_weekly_loss_pct_bw = (fat_mass_to_lose_kg / current_weight_kg) / weeks
    ratio = required_weekly_loss_pct_bw / BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW
    return BodycompFeasibility(
        fat_mass_to_lose_kg=fat_mass_to_lose_kg,
        required_weekly_loss_pct_bw=required_weekly_loss_pct_bw,
        achievable_weekly_loss_pct_bw=BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW,
        ratio=ratio,
        probability=_logistic_probability(ratio),
        exceeds_safe_rate=required_weekly_loss_pct_bw > BODYCOMP_MAX_SAFE_WEEKLY_LOSS_PCT_BW,
    )
