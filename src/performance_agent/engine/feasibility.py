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


@dataclass(frozen=True)
class FeasibilityResult:
    """Feasibility verdict with the rates that produced it (for explainability)."""

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
