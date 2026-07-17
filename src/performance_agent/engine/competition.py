"""Pre-competition math: carb loading, attempt selection, pacing, trigger window.

Pure and deterministic — no I/O, no memory imports. Thresholds are corpus-cited
priors (IOC/Burke carbohydrate consensus, powerlifting attempt-selection
convention, the taper meta-analysis) recorded as constants with their rationale.
Anything the literature does not quantify (meal timing, water/sodium
manipulation, weight-cut tactics) deliberately has NO function here: it is
sourced advice with warnings in the protocol document, never engine math.
"""

from dataclasses import dataclass

from performance_agent.engine.progression import round_to_increment

_MIN_BODY_MASS_KG = 30.0
_MAX_BODY_MASS_KG = 250.0
_MIN_EVENT_MIN = 5.0
_MAX_EVENT_MIN = 1440.0
# Carb-loading priors (IOC consensus): events >= 90 min load 8-12 g/kg/day over
# the final ~48 h; 60-90 min take 6-8 g/kg/day the day before; shorter events
# need no loading. In-race: none under 60 min, 30-60 g/h up to ~2.5 h, 60-90 g/h
# beyond (multiple transportable carbohydrates).
_LONG_EVENT_MIN = 90.0
_MID_EVENT_MIN = 60.0
_RACE_FUEL_LONG_MIN = 150.0


@dataclass(frozen=True)
class CarbLoadingTargets:
    """Evidence-based carbohydrate targets for the final window and the race."""

    loading_required: bool
    carb_g_per_kg_low: float | None = None
    carb_g_per_kg_high: float | None = None
    carb_g_per_day_low: float | None = None
    carb_g_per_day_high: float | None = None
    window_hours: int | None = None
    race_carb_g_per_h_low: float | None = None
    race_carb_g_per_h_high: float | None = None


def carb_loading_targets(body_mass_kg: float, event_duration_min: float) -> CarbLoadingTargets:
    """Carb-loading and in-race fueling ranges from body mass and event duration."""
    if not _MIN_BODY_MASS_KG <= body_mass_kg <= _MAX_BODY_MASS_KG:
        msg = (
            f"body_mass_kg must be within [{_MIN_BODY_MASS_KG}, {_MAX_BODY_MASS_KG}], "
            f"got {body_mass_kg!r}"
        )
        raise ValueError(msg)
    if not _MIN_EVENT_MIN <= event_duration_min <= _MAX_EVENT_MIN:
        msg = (
            f"event_duration_min must be within [{_MIN_EVENT_MIN}, {_MAX_EVENT_MIN}], "
            f"got {event_duration_min!r}"
        )
        raise ValueError(msg)
    if event_duration_min < _MID_EVENT_MIN:
        return CarbLoadingTargets(loading_required=False)
    if event_duration_min >= _LONG_EVENT_MIN:
        g_low, g_high, window = 8.0, 12.0, 48
    else:
        g_low, g_high, window = 6.0, 8.0, 24
    if event_duration_min > _RACE_FUEL_LONG_MIN:
        race_low, race_high = 60.0, 90.0
    else:
        race_low, race_high = 30.0, 60.0
    return CarbLoadingTargets(
        loading_required=True,
        carb_g_per_kg_low=g_low,
        carb_g_per_kg_high=g_high,
        carb_g_per_day_low=round(g_low * body_mass_kg, 1),
        carb_g_per_day_high=round(g_high * body_mass_kg, 1),
        window_hours=window,
        race_carb_g_per_h_low=race_low,
        race_carb_g_per_h_high=race_high,
    )


_MIN_E1RM_KG = 20.0
_MAX_E1RM_KG = 600.0
# Attempt-selection convention (powerlifting coaching literature): opener ~91%
# of e1RM (a weight you can triple), second ~96%, third at the goal when the
# data supports it — 93-105% of e1RM — else a conservative ~101% PR attempt.
_OPENER_PCT = 0.91
_SECOND_PCT = 0.96
_THIRD_FALLBACK_PCT = 1.01
_GOAL_MIN_PCT = 0.93
_GOAL_MAX_PCT = 1.05


@dataclass(frozen=True)
class AttemptSelection:
    """Opening, second and third attempts for one lift on meet day."""

    opener_kg: float
    second_kg: float
    third_kg: float
    flags: tuple[str, ...] = ()


def select_attempts(e1rm_kg: float, goal_kg: float, rounding_kg: float = 2.5) -> AttemptSelection:
    """Three meet-day attempts from the estimated 1RM and the athlete's goal.

    The honesty gate lives here: a goal outside 93-105% of e1RM is never
    silently endorsed — the third falls back to ~101% and the goal_beyond_e1rm
    flag tells the skill to name the gap.
    """
    if not _MIN_E1RM_KG <= e1rm_kg <= _MAX_E1RM_KG:
        msg = f"e1rm_kg must be within [{_MIN_E1RM_KG}, {_MAX_E1RM_KG}], got {e1rm_kg!r}"
        raise ValueError(msg)
    if goal_kg <= 0:
        msg = f"goal_kg must be positive, got {goal_kg!r}"
        raise ValueError(msg)
    if rounding_kg <= 0:
        msg = f"rounding_kg must be positive, got {rounding_kg!r}"
        raise ValueError(msg)
    opener = round_to_increment(_OPENER_PCT * e1rm_kg, rounding_kg)
    second = round_to_increment(_SECOND_PCT * e1rm_kg, rounding_kg)
    flags: tuple[str, ...] = ()
    if _GOAL_MIN_PCT * e1rm_kg <= goal_kg <= _GOAL_MAX_PCT * e1rm_kg:
        third = round_to_increment(goal_kg, rounding_kg)
    else:
        third = round_to_increment(_THIRD_FALLBACK_PCT * e1rm_kg, rounding_kg)
        flags = ("goal_beyond_e1rm",)
    if second <= opener:
        second = opener + rounding_kg
    if third <= second:
        third = second + rounding_kg
    return AttemptSelection(opener, second, third, flags)
