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
ACHIEVABLE_WEEKLY_RATE: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.010,
    TrainingAge.INTERMEDIATE: 0.005,
    TrainingAge.ADVANCED: 0.0025,
}

LOGISTIC_STEEPNESS = 3.0
# Clamp the logistic exponent so extreme ratios neither overflow math.exp nor
# collapse the probability to exactly 0.0 or 1.0 (it must stay in (0, 1)).
MAX_LOGISTIC_EXPONENT = 30.0


@dataclass(frozen=True)
class FeasibilityResult:
    """Feasibility verdict with the rates that produced it (for explainability)."""

    improvement_needed: float
    required_weekly_rate: float
    achievable_weekly_rate: float
    ratio: float
    probability: float


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
    achievable_weekly_rate = ACHIEVABLE_WEEKLY_RATE[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    exponent = LOGISTIC_STEEPNESS * (ratio - 1)
    exponent = max(min(exponent, MAX_LOGISTIC_EXPONENT), -MAX_LOGISTIC_EXPONENT)
    probability = 1 / (1 + math.exp(exponent))
    return FeasibilityResult(
        improvement_needed=improvement_needed,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=probability,
    )
