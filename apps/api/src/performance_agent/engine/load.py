"""Training load quantification: session-RPE and acute:chronic workload ratio.

ACWR is provided as a monitoring signal only. Its injury-prediction validity
is contested in the literature; downstream agents must present it as a
descriptive trend, never as an injury probability.
"""

import math
from collections.abc import Sequence

MIN_RPE = 1
MAX_RPE = 10
DAYS_PER_WEEK = 7
CHRONIC_WINDOW_DAYS = 28


def _validate_whole_number(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{name} must be a whole number, got {value!r}"
        raise ValueError(msg)


def _validate_daily_loads(daily_loads: Sequence[float]) -> None:
    for day, value in enumerate(daily_loads):
        if not math.isfinite(value):
            msg = f"daily loads must be finite, got {value} at index {day}"
            raise ValueError(msg)
        if value < 0:
            msg = f"daily loads must not be negative, got {value} at index {day}"
            raise ValueError(msg)


def session_rpe_load(rpe: int, duration_min: int) -> float:
    """Return Foster's session-RPE load: RPE (CR-10) x duration in minutes.

    Duration is whole minutes by design; sub-minute precision is not
    meaningful for session-RPE quantification.
    """
    _validate_whole_number("rpe", rpe)
    _validate_whole_number("duration_min", duration_min)
    if not MIN_RPE <= rpe <= MAX_RPE:
        msg = f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe}"
        raise ValueError(msg)
    if duration_min <= 0:
        msg = f"duration_min must be positive, got {duration_min}"
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


def acute_chronic_ratio(daily_loads: Sequence[float]) -> float | None:
    """Return acute (7-day mean) over chronic (28-day mean) workload ratio.

    This is the coupled ACWR: the acute 7-day window is contained within the
    28-day chronic window, which inflates self-correlation between the two
    terms. Treat the result as a coarse descriptive trend only.

    Returns None when fewer than 28 days of history exist or when the chronic
    load is zero (an untrained window makes the ratio meaningless). Only the
    most recent 28 days are considered.
    """
    _validate_daily_loads(daily_loads)
    if len(daily_loads) < CHRONIC_WINDOW_DAYS:
        return None
    window = daily_loads[-CHRONIC_WINDOW_DAYS:]
    chronic = sum(window) / CHRONIC_WINDOW_DAYS
    if chronic == 0:
        return None
    acute = sum(window[-DAYS_PER_WEEK:]) / DAYS_PER_WEEK
    return acute / chronic
