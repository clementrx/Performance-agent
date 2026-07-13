"""Data-driven deload regulation from accumulated monitoring signals.

should_deload reads the Phase 2 monitoring trends (monotony/strain, TSB, a
readiness trend) plus the planned-deload counter and recent adherence, and
returns a DESCRIPTIVE recommendation (none / light / full) with the drivers
that fired. It never decides for the coach — the LLM reads the drivers, weighs
them against the athlete's context, and narrates. Every threshold below is a
team-chosen prior (deload timing is judgement, not a settled constant).
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

DeloadRecommendation = Literal["none", "light", "full"]

# The planned deload cadence acts as a guardrail: past it, fatigue evidence is
# no longer required to justify a full deload. Team-chosen prior (a common
# mesocycle deload cadence is every 4 weeks); overridable per program.
_DEFAULT_DELOAD_INTERVAL_WEEKS = 4
_INTERVAL_OVERRUN_WEEKS = 1  # weeks_since_deload >= interval + 1 -> full regardless

# Fatigue-evidence thresholds (team-chosen priors, all descriptive):
_TSB_DEEP_FATIGUE = -25.0  # TSB below this = deeply fatigued (Phase 2 freshness trend)
_READINESS_NOT_IMPROVING = 0.0  # readiness trend <= 0 = flat/declining freshness
_MONOTONY_HIGH = 2.0  # Foster monotony above this = poorly varied week
_STRAIN_RISING = 0.0  # strain_trend > 0 = strain climbing week-on-week
_ADHERENCE_FLOOR_PCT = 70.0  # below this, fatigue signals are unreliable (see playbook)
_ADHERENCE_MAX_PCT = 100.0  # adherence is a percentage in [0, 100]

_RANK: dict[DeloadRecommendation, int] = {"none": 0, "light": 1, "full": 2}
_BY_RANK: tuple[DeloadRecommendation, ...] = ("none", "light", "full")


@dataclass(frozen=True)
class DeloadAssessment:
    """A descriptive deload recommendation and the signals behind it."""

    recommendation: DeloadRecommendation
    drivers: list[str]  # plain-language signals that fired, in evaluation order


def _escalate(current: DeloadRecommendation, floor: DeloadRecommendation) -> DeloadRecommendation:
    return _BY_RANK[max(_RANK[current], _RANK[floor])]


def _validate_deload_inputs(  # noqa: PLR0913 -- mirrors should_deload's signal set
    weeks_since_deload: int,
    monotony_recent: float | None,
    strain_trend: float,
    tsb: float,
    readiness_trend: float,
    adherence_pct: float,
    planned_interval_weeks: int,
) -> None:
    validate_whole_number("weeks_since_deload", weeks_since_deload)
    validate_whole_number("planned_interval_weeks", planned_interval_weeks)
    if weeks_since_deload < 0:
        msg = f"weeks_since_deload must be >= 0, got {weeks_since_deload!r}"
        raise ValueError(msg)
    if planned_interval_weeks < 1:
        msg = f"planned_interval_weeks must be >= 1, got {planned_interval_weeks!r}"
        raise ValueError(msg)
    validate_finite("strain_trend", strain_trend)
    validate_finite("tsb", tsb)
    validate_finite("readiness_trend", readiness_trend)
    validate_finite("adherence_pct", adherence_pct)
    if not 0.0 <= adherence_pct <= _ADHERENCE_MAX_PCT:
        msg = f"adherence_pct must be within 0-100, got {adherence_pct!r}"
        raise ValueError(msg)
    if monotony_recent is not None:
        validate_finite("monotony_recent", monotony_recent)
        if monotony_recent < 0:
            msg = f"monotony_recent must be non-negative, got {monotony_recent!r}"
            raise ValueError(msg)


def should_deload(  # noqa: PLR0913 -- plan-mandated monitoring-signal set
    weeks_since_deload: int,
    monotony_recent: float | None,
    strain_trend: float,
    tsb: float,
    readiness_trend: float,
    adherence_pct: float,
    planned_interval_weeks: int = _DEFAULT_DELOAD_INTERVAL_WEEKS,
) -> DeloadAssessment:
    """Recommend a deload (none/light/full) from accumulated monitoring signals.

    Inputs are plain monitoring numbers (Phase 2): monotony_recent is Foster's
    monotony for the recent week (None when the week was uniform); strain_trend
    is the week-on-week change in Foster strain (positive = rising); tsb is the
    latest CTL-ATL freshness (negative = fatigued); readiness_trend is the recent
    change in the readiness score in points (negative = freshness declining);
    adherence_pct is recent adherence 0-100. weeks_since_deload and
    planned_interval_weeks drive the guardrail.

    Rules (team-chosen priors, all descriptive):
    - weeks_since_deload >= planned_interval_weeks + 1 -> full, regardless of the
      other signals (the planned counter is the backstop).
    - tsb < -25 with readiness not improving (trend <= 0) -> full when adherence
      is >= 70%; when adherence is below 70% the fatigue signals are unreliable
      (the athlete is not doing the work), so this downgrades to light and flags
      the adherence playbook instead.
    - monotony > 2.0 with rising strain -> at least light.

    Returns the recommendation and the plain-language drivers that fired; the
    coach narrates and decides, this never acts on its own.
    """
    _validate_deload_inputs(
        weeks_since_deload,
        monotony_recent,
        strain_trend,
        tsb,
        readiness_trend,
        adherence_pct,
        planned_interval_weeks,
    )

    drivers: list[str] = []
    if weeks_since_deload >= planned_interval_weeks + _INTERVAL_OVERRUN_WEEKS:
        drivers.append(
            f"{weeks_since_deload} weeks since the last deload, past the planned "
            f"{planned_interval_weeks}-week cadence: a full deload is due regardless of fatigue"
        )
        return DeloadAssessment(recommendation="full", drivers=drivers)

    recommendation: DeloadRecommendation = "none"
    low_adherence = adherence_pct < _ADHERENCE_FLOOR_PCT
    if tsb < _TSB_DEEP_FATIGUE and readiness_trend <= _READINESS_NOT_IMPROVING:
        drivers.append(
            f"TSB {tsb:.0f} below {_TSB_DEEP_FATIGUE:.0f} with readiness not improving "
            f"(trend {readiness_trend:+.0f})"
        )
        if low_adherence:
            drivers.append(
                f"adherence {adherence_pct:.0f}% below {_ADHERENCE_FLOOR_PCT:.0f}%: fatigue "
                "signals are unreliable under low adherence -- lightening rather than a full "
                "deload; run the adherence playbook to fix the real problem"
            )
            recommendation = _escalate(recommendation, "light")
        else:
            recommendation = _escalate(recommendation, "full")
    if (
        monotony_recent is not None
        and monotony_recent > _MONOTONY_HIGH
        and strain_trend > _STRAIN_RISING
    ):
        drivers.append(
            f"monotony {monotony_recent:.2f} above {_MONOTONY_HIGH:.1f} with rising strain "
            f"(trend {strain_trend:+.0f}): a light deload restores variation"
        )
        recommendation = _escalate(recommendation, "light")
    return DeloadAssessment(recommendation=recommendation, drivers=drivers)
