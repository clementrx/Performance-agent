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
