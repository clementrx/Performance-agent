"""Graded return-to-load ladder after time off.

build_return_progression turns a layoff length into a week-by-week volume /
intensity ramp back to full load. The starting reduction is banded by how long
the athlete was away; the ramp then climbs at a fixed weekly step until both
factors reach baseline (1.0). Longer layoffs start lower and therefore ramp
longer.

HARD PRECONDITION: this is a return-to-LOAD ladder, not a return-from-injury
protocol. It must only be used after a professional has cleared the athlete to
resume training. The engine takes pain_free (the within-session 24h-rule gate);
clearance is enforced at the tool/skill boundary. The agent never programs
through an active injury and always refers out.

Constants are team-chosen priors. They reflect return-to-sport consensus
(graded progression, the 24h symptom rule) and detraining/retraining reviews in
spirit only -- those sources are not in the evidence corpus and are labelled as
priors here rather than cited unverified.
"""

import math
from dataclasses import dataclass

from performance_agent.engine._validation import validate_whole_number

# Banded starting factors (volume, intensity) vs baseline, by weeks off.
# Team-chosen priors: the longer the layoff, the deeper the initial reduction.
_BANDS: tuple[tuple[int, float, float], ...] = (
    # min_weeks_off (inclusive), volume_start, intensity_start
    (4, 0.40, 0.60),  # > 4 weeks off (matched last, catch-all)
    (2, 0.50, 0.70),  # 2-4 weeks
    (1, 0.70, 0.85),  # 1-2 weeks
    (0, 0.90, 0.95),  # < 1 week
)

# Weekly climb back to baseline. Volume adds 12.5% of baseline per week (the
# midpoint of the 10-15%/week return-to-sport band); intensity climbs slower.
# Team-chosen priors.
_VOLUME_STEP = 0.125
_INTENSITY_STEP = 0.075
_BASELINE = 1.0

_MAX_SESSIONS_PER_WEEK = 14  # plausibility bound (up to two sessions a day)

# The 24h symptom rule, encoded in every progressing week's note (ASCII, this
# text may reach the athlete). Team-chosen prior from return-to-sport consensus.
_TWENTYFOUR_HOUR_RULE = (
    "if post-session pain stays <=3/10 and clears within 24h, advance to the next "
    "week; if it does not, repeat this week (do not progress through pain)"
)


@dataclass(frozen=True)
class WeekFactor:
    """One week of the return ramp (factors vs baseline load)."""

    week_index: int  # 1-based
    volume_factor: float
    intensity_factor: float
    note: str


def _band_start(weeks_off: int) -> tuple[float, float]:
    for min_weeks, volume_start, intensity_start in _BANDS:
        if weeks_off >= min_weeks:
            return volume_start, intensity_start
    # Unreachable: the 0-week band matches every non-negative input.
    msg = f"no return band for weeks_off={weeks_off!r}"
    raise ValueError(msg)


def _steps_to_baseline(start: float, step: float) -> int:
    # Whole `step`-sized climbs to reach baseline from `start`; an epsilon absorbs
    # float drift so an exact multiple does not spuriously add a week.
    distance = _BASELINE - start
    if distance <= 0:
        return 0
    return math.ceil(distance / step - 1e-9)


def _ramp_weeks(volume_start: float, intensity_start: float) -> int:
    volume_weeks = _steps_to_baseline(volume_start, _VOLUME_STEP)
    intensity_weeks = _steps_to_baseline(intensity_start, _INTENSITY_STEP)
    return max(volume_weeks, intensity_weeks) + 1  # +1 to include the starting week


def build_return_progression(
    weeks_off: int, sessions_per_week: int, pain_free: bool
) -> list[WeekFactor]:
    """Build a graded volume/intensity ramp back to full load after time off.

    weeks_off is whole weeks away from training; sessions_per_week is the cadence
    to resume at (1-14). Starting reduction is banded: < 1 week off -> 0.90 vol /
    0.95 int; 1-2 -> 0.70/0.85; 2-4 -> 0.50/0.70; > 4 -> 0.40/0.60. From the start
    the ramp adds 12.5%/week of baseline volume and 7.5%/week intensity, capped at
    1.0, so both factors reach baseline on the final week; a longer layoff starts
    lower and ramps longer.

    pain_free gates progression (the 24h rule): when False the athlete is not
    clear to advance, so a single holding week at the reduced start is returned
    with a step-back note. When True the full climbing ladder is returned, each
    week carrying the 24h rule.

    PRECONDITION: only after professional clearance to resume training -- this is
    return-to-load, never return-from-injury. Clearance is enforced by the caller.
    """
    validate_whole_number("weeks_off", weeks_off)
    validate_whole_number("sessions_per_week", sessions_per_week)
    if weeks_off < 0:
        msg = f"weeks_off must be >= 0, got {weeks_off!r}"
        raise ValueError(msg)
    if not 1 <= sessions_per_week <= _MAX_SESSIONS_PER_WEEK:
        msg = (
            f"sessions_per_week must be within 1-{_MAX_SESSIONS_PER_WEEK}, "
            f"got {sessions_per_week!r}"
        )
        raise ValueError(msg)

    volume_start, intensity_start = _band_start(weeks_off)
    if not pain_free:
        note = (
            f"not pain-free: hold at this reduced load, resume at {sessions_per_week} "
            "sessions/week, and do not progress until sessions are pain-free -- "
            + _TWENTYFOUR_HOUR_RULE
        )
        return [
            WeekFactor(
                week_index=1,
                volume_factor=volume_start,
                intensity_factor=intensity_start,
                note=note,
            )
        ]

    total_weeks = _ramp_weeks(volume_start, intensity_start)
    ramp: list[WeekFactor] = []
    for step in range(total_weeks):
        volume = min(_BASELINE, volume_start + step * _VOLUME_STEP)
        intensity = min(_BASELINE, intensity_start + step * _INTENSITY_STEP)
        if step == 0:
            note = (
                f"restart at {sessions_per_week} sessions/week at reduced load -- "
                + _TWENTYFOUR_HOUR_RULE
            )
        elif volume >= _BASELINE and intensity >= _BASELINE:
            note = "back to baseline load"
        else:
            note = _TWENTYFOUR_HOUR_RULE
        ramp.append(
            WeekFactor(
                week_index=step + 1,
                volume_factor=volume,
                intensity_factor=intensity,
                note=note,
            )
        )
    return ramp
