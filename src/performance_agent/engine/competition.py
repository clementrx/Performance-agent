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
# A goal outside that band is flagged by direction so the skill can say
# whether the athlete is sandbagging or overreaching.
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
    silently endorsed — the third falls back to ~101% and a directional flag
    (goal_beyond_e1rm or goal_below_e1rm_range) tells the skill to name the gap.
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
        if goal_kg > _GOAL_MAX_PCT * e1rm_kg:
            flags = ("goal_beyond_e1rm",)
        else:
            flags = ("goal_below_e1rm_range",)
    if second <= opener:
        second = opener + rounding_kg
    if third <= second:
        third = second + rounding_kg
    return AttemptSelection(opener, second, third, flags)


# Negative-split prior: first half ~1% slower than mean pace, second half
# balanced exactly so the cumulative time lands on the target.
_NEGATIVE_SPLIT_PCT = 0.01
# Protocol windows per priority (spec §4): A events open with the taper but
# never closer than a week nor further than three; B events get a short window;
# C events are never auto-surfaced.
_WINDOW_A_MIN, _WINDOW_A_MAX = 7, 21
_WINDOW_B_MIN, _WINDOW_B_MAX = 3, 10
# sub-metre remainders are float noise, not a real segment
_MIN_REMAINDER_M = 1.0


@dataclass(frozen=True)
class PacingSplit:
    """One race segment: its target pace and the cumulative time at its end."""

    label: str
    distance_m: float
    target_pace_s_per_km: float
    cumulative_time_s: float


def _segment_distances(distance_m: float, segment_m: float) -> list[float]:
    full = int(distance_m // segment_m)
    segments = [segment_m] * full
    remainder = distance_m - full * segment_m
    if remainder > _MIN_REMAINDER_M:
        segments.append(remainder)
    elif not segments:
        segments = [distance_m]
    return segments


def _negative_split_paces(
    distances: list[float], target_time_s: float, mean_pace: float, halfway: float
) -> list[float]:
    """Per-segment paces for the negative-split strategy.

    Falls back to even pacing whenever the second half is degenerate (too
    short, or too fast a first half would force a negative pace on it) — a
    negative pace is physically meaningless and must never reach the athlete.
    """
    start = 0.0
    first_half = []
    for dist in distances:
        first_half.append(start + dist / 2.0 < halfway)
        start += dist
    d1_km = sum(d for d, f in zip(distances, first_half, strict=True) if f) / 1000.0
    d2_km = sum(d for d, f in zip(distances, first_half, strict=True) if not f) / 1000.0
    pace_1 = mean_pace * (1 + _NEGATIVE_SPLIT_PCT)
    pace_2 = (target_time_s - pace_1 * d1_km) / d2_km if d2_km else mean_pace
    if d2_km <= 0 or pace_2 <= 0:
        return [mean_pace] * len(distances)
    return [pace_1 if f else pace_2 for f in first_half]


def pacing_plan(
    distance_m: float,
    target_time_s: float,
    segment_m: float = 1000.0,
    strategy: str = "even",
) -> list[PacingSplit]:
    """Distribute a target time over segments (even or negative split).

    The target comes from the athlete's goal or predict_race_time upstream —
    this function only distributes it; cumulative time always lands on the
    target within a second.
    """
    if distance_m <= 0:
        msg = f"distance_m must be positive, got {distance_m!r}"
        raise ValueError(msg)
    if target_time_s <= 0:
        msg = f"target_time_s must be positive, got {target_time_s!r}"
        raise ValueError(msg)
    if segment_m <= 0:
        msg = f"segment_m must be positive, got {segment_m!r}"
        raise ValueError(msg)
    if strategy not in ("even", "negative"):
        msg = f"strategy must be 'even' or 'negative', got {strategy!r}"
        raise ValueError(msg)
    distances = _segment_distances(distance_m, segment_m)
    mean_pace = target_time_s / (distance_m / 1000.0)
    halfway = distance_m / 2.0
    paces: list[float]
    if strategy == "even" or len(distances) == 1:
        paces = [mean_pace] * len(distances)
    else:
        paces = _negative_split_paces(distances, target_time_s, mean_pace, halfway)
    splits: list[PacingSplit] = []
    cumulative = 0.0
    position = 0.0
    for dist, pace in zip(distances, paces, strict=True):
        cumulative += pace * dist / 1000.0
        position += dist
        splits.append(
            PacingSplit(
                label=f"{position / 1000.0:g} km",
                distance_m=dist,
                target_pace_s_per_km=round(pace, 1),
                cumulative_time_s=round(cumulative, 1),
            )
        )
    return splits


def protocol_window_days(taper_days: int, priority: str) -> int:
    """The adaptive due-action window: taper-driven, clamped per priority."""
    if taper_days < 0:
        msg = f"taper_days must be non-negative, got {taper_days!r}"
        raise ValueError(msg)
    if priority not in ("A", "B", "C"):
        msg = f"priority must be A, B or C, got {priority!r}"
        raise ValueError(msg)
    if priority == "A":
        return min(max(taper_days, _WINDOW_A_MIN), _WINDOW_A_MAX)
    if priority == "B":
        return min(max(taper_days, _WINDOW_B_MIN), _WINDOW_B_MAX)
    return 0
