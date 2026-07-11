"""Periodization models: weekly waves, block, undulating, in-season and peaking.

Factors are multipliers against a baseline week (1.0 = baseline volume or
intensity). The Periodization agent later maps these onto concrete sessions.
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_whole_number

MIN_DELOAD_EVERY = 2
DEFAULT_VOLUME_RAMP = 0.05
DEFAULT_INTENSITY_RAMP = 0.025
DELOAD_INTENSITY = 0.9
DELOAD_VOLUME = 0.6
TAPER_VOLUME = 0.5
TAPER_INTENSITY = 1.0

BlockPhase = Literal["accumulation", "intensification", "realization"]

# Phase split of a block-periodized cycle (fractions of total weeks).
# Team-chosen priors following classic block schemes (~50/35/15).
BLOCK_PHASE_FRACTIONS: tuple[tuple[BlockPhase, float], ...] = (
    ("accumulation", 0.50),
    ("intensification", 0.35),
    ("realization", 0.15),
)
# Per-phase load multipliers vs baseline. Team-chosen priors: accumulation is
# high-volume/moderate-intensity, intensification inverts that, realization
# sheds volume while intensity peaks.
ACCUMULATION_VOLUME = 1.10
ACCUMULATION_INTENSITY = 0.85
INTENSIFICATION_VOLUME = 0.90
INTENSIFICATION_INTENSITY = 1.05
REALIZATION_VOLUME = 0.55
REALIZATION_INTENSITY = 1.10
# Below 6 weeks the three phases degenerate (a phase would need < 1 full
# week). Team-chosen floor.
MIN_BLOCK_WEEKS = 6

_BLOCK_PHASE_FACTORS: dict[BlockPhase, tuple[float, float]] = {
    "accumulation": (ACCUMULATION_VOLUME, ACCUMULATION_INTENSITY),
    "intensification": (INTENSIFICATION_VOLUME, INTENSIFICATION_INTENSITY),
    "realization": (REALIZATION_VOLUME, REALIZATION_INTENSITY),
}

SessionEmphasis = Literal["heavy", "moderate", "light"]

# Daily-undulating intensity zones as fractions of 1RM (low, high).
# Team-chosen priors consistent with common DUP schemes. The light floor is
# 0.625 because that is the minimum percentage reps_for_percentage_rir accepts
# (MAX_EFFECTIVE_REPS = 18), so every emitted zone bound is a valid input to
# the engine's own RIR primitives.
UNDULATION_ZONES: dict[SessionEmphasis, tuple[float, float]] = {
    "heavy": (0.85, 0.925),
    "moderate": (0.725, 0.80),
    "light": (0.625, 0.70),
}
# Heavy-then-light adjacency is deliberate: the light day buys recovery
# after the heaviest stimulus before quality moderate work.
_UNDULATION_ORDER: tuple[SessionEmphasis, ...] = ("heavy", "light", "moderate")
# A single weekly session cannot undulate; beyond daily training the cycle
# stops meaning anything. Team-chosen bounds.
MIN_UNDULATING_SESSIONS = 2
MAX_UNDULATING_SESSIONS = 7

# In-season maintenance: minimum effective dose around fixtures. Volume
# fractions are of the athlete's off-season baseline; intensity is held high
# because intensity, not volume, retains strength. Team-chosen priors.
INSEASON_VOLUME_ONE_MATCH = 0.50
INSEASON_VOLUME_TWO_MATCHES = 0.30
INSEASON_MIN_INTENSITY = 0.80
INSEASON_SESSIONS_ONE_MATCH = 2
INSEASON_SESSIONS_TWO_MATCHES = 1
MAX_INSEASON_MATCHES = 2


@dataclass(frozen=True)
class WeekLoad:
    """Planned load multipliers for one training week (week is 1-indexed)."""

    week: int
    volume_factor: float
    intensity_factor: float
    is_deload: bool
    is_taper: bool


def _validate(total_weeks: int, deload_every: int, taper_weeks: int) -> None:
    validate_whole_number("total_weeks", total_weeks)
    validate_whole_number("deload_every", deload_every)
    validate_whole_number("taper_weeks", taper_weeks)
    if total_weeks < 1:
        msg = f"total_weeks must be >= 1, got {total_weeks!r}"
        raise ValueError(msg)
    if deload_every < MIN_DELOAD_EVERY:
        msg = f"deload_every must be >= {MIN_DELOAD_EVERY}, got {deload_every!r}"
        raise ValueError(msg)
    if not 0 <= taper_weeks < total_weeks:
        msg = f"taper_weeks must be >= 0 and < total_weeks, got {taper_weeks!r}"
        raise ValueError(msg)


def build_weekly_waves(
    total_weeks: int,
    *,
    deload_every: int = 4,
    taper_weeks: int = 1,
) -> list[WeekLoad]:
    """Generate week-by-week load multipliers for a training block.

    Building weeks ramp volume by 5% and intensity by 2.5% per week within
    each mesocycle; every ``deload_every``-th building week drops to 60%
    volume at 90% intensity; the final ``taper_weeks`` weeks hold intensity
    at baseline (1.0) while halving volume (the preceding building weeks sit
    above 1.0). Baseline escalation across mesocycles is intentionally out of
    scope for v1 (the ramp resets after each deload).
    """
    _validate(total_weeks, deload_every, taper_weeks)

    waves: list[WeekLoad] = []
    week_in_block = 0
    for week in range(1, total_weeks + 1):
        if week > total_weeks - taper_weeks:
            waves.append(
                WeekLoad(week, TAPER_VOLUME, TAPER_INTENSITY, is_deload=False, is_taper=True)
            )
            continue
        week_in_block += 1
        if week_in_block == deload_every:
            waves.append(
                WeekLoad(week, DELOAD_VOLUME, DELOAD_INTENSITY, is_deload=True, is_taper=False)
            )
            week_in_block = 0
            continue
        volume = 1.0 + DEFAULT_VOLUME_RAMP * (week_in_block - 1)
        intensity = 1.0 + DEFAULT_INTENSITY_RAMP * (week_in_block - 1)
        waves.append(WeekLoad(week, volume, intensity, is_deload=False, is_taper=False))
    return waves


@dataclass(frozen=True)
class BlockWeek:
    """One week of a block-periodized cycle (week is 1-indexed)."""

    week: int
    phase: BlockPhase
    volume_factor: float
    intensity_factor: float


def build_block_periodization(total_weeks: int) -> list[BlockWeek]:
    """Split a cycle into accumulation, intensification and realization blocks.

    Phase lengths are round(total * fraction) for accumulation (0.50) and
    intensification (0.35), with realization taking the remainder; every
    phase keeps at least one week (deterministic repair: while any phase is
    below one week, one week moves from the currently largest phase to the
    deficient one). Factors are constant within a phase — per-week ramps
    stay the job of build_weekly_waves; this model sets the phase structure.
    """
    validate_whole_number("total_weeks", total_weeks)
    if total_weeks < MIN_BLOCK_WEEKS:
        msg = (
            f"total_weeks must be >= {MIN_BLOCK_WEEKS}, got {total_weeks!r}: below "
            f"{MIN_BLOCK_WEEKS} weeks the three phases degenerate — use "
            "build_weekly_waves instead"
        )
        raise ValueError(msg)
    counts: dict[BlockPhase, int] = {
        "accumulation": round(total_weeks * BLOCK_PHASE_FRACTIONS[0][1]),
        "intensification": round(total_weeks * BLOCK_PHASE_FRACTIONS[1][1]),
    }
    counts["realization"] = total_weeks - counts["accumulation"] - counts["intensification"]
    while any(count < 1 for count in counts.values()):
        deficient = min(counts, key=lambda phase: counts[phase])
        largest = max(counts, key=lambda phase: counts[phase])
        counts[largest] -= 1
        counts[deficient] += 1
    weeks: list[BlockWeek] = []
    week = 1
    for phase, _fraction in BLOCK_PHASE_FRACTIONS:
        volume, intensity = _BLOCK_PHASE_FACTORS[phase]
        for _ in range(counts[phase]):
            weeks.append(BlockWeek(week, phase, volume, intensity))
            week += 1
    return weeks


@dataclass(frozen=True)
class UndulatingSession:
    """One session slot in a daily-undulating training week."""

    session: int
    emphasis: SessionEmphasis
    intensity_low: float
    intensity_high: float


def build_undulating_week(sessions_per_week: int) -> list[UndulatingSession]:
    """Assign daily-undulating emphases to a week's strength sessions.

    Sessions cycle heavy -> light -> moderate (heavy-then-light adjacency is
    deliberate recovery spacing). Zone bounds are fractions of 1RM from
    UNDULATION_ZONES. The cycle restarts each week, so at frequencies where
    ``sessions_per_week % 3 == 1`` (4, 7) the last and first slots are both
    heavy — spacing those across the week boundary is the scheduler's job.
    """
    validate_whole_number("sessions_per_week", sessions_per_week)
    if not MIN_UNDULATING_SESSIONS <= sessions_per_week <= MAX_UNDULATING_SESSIONS:
        msg = (
            f"sessions_per_week must be between {MIN_UNDULATING_SESSIONS} and "
            f"{MAX_UNDULATING_SESSIONS}, got {sessions_per_week!r}: a single weekly "
            "session cannot undulate, and beyond daily training the cycle is meaningless"
        )
        raise ValueError(msg)
    sessions: list[UndulatingSession] = []
    for index in range(sessions_per_week):
        emphasis = _UNDULATION_ORDER[index % len(_UNDULATION_ORDER)]
        low, high = UNDULATION_ZONES[emphasis]
        sessions.append(UndulatingSession(index + 1, emphasis, low, high))
    return sessions


@dataclass(frozen=True)
class InseasonWeek:
    """Strength maintenance prescription for one in-season week."""

    matches: int
    strength_sessions: int
    volume_factor: float
    min_intensity_factor: float


def build_inseason_week(matches_this_week: int) -> InseasonWeek:
    """Prescribe strength maintenance around this week's fixtures (1 or 2).

    Volume is a fraction of the off-season baseline; min_intensity_factor is
    the floor to hold (intensity, not volume, retains strength). Zero matches
    and congested (3+) weeks are refused with coaching guidance in the error.
    """
    validate_whole_number("matches_this_week", matches_this_week)
    if matches_this_week < 0:
        msg = f"matches_this_week must be non-negative, got {matches_this_week!r}"
        raise ValueError(msg)
    if matches_this_week == 0:
        msg = "no fixture this week: use a normal building week, not the in-season model"
        raise ValueError(msg)
    if matches_this_week > MAX_INSEASON_MATCHES:
        msg = (
            f"got {matches_this_week!r} matches: more than 2 fixtures leaves no recovery "
            "window for strength work — rest is the prescription"
        )
        raise ValueError(msg)
    if matches_this_week == 1:
        return InseasonWeek(
            matches=1,
            strength_sessions=INSEASON_SESSIONS_ONE_MATCH,
            volume_factor=INSEASON_VOLUME_ONE_MATCH,
            min_intensity_factor=INSEASON_MIN_INTENSITY,
        )
    return InseasonWeek(
        matches=2,
        strength_sessions=INSEASON_SESSIONS_TWO_MATCHES,
        volume_factor=INSEASON_VOLUME_TWO_MATCHES,
        min_intensity_factor=INSEASON_MIN_INTENSITY,
    )
