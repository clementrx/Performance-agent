"""Weekly volume/intensity wave generation with deloads and taper.

Factors are multipliers against a baseline week (1.0 = baseline volume or
intensity). The Periodization agent later maps these onto concrete sessions.
"""

from dataclasses import dataclass

MIN_DELOAD_EVERY = 2
DEFAULT_VOLUME_RAMP = 0.05
DEFAULT_INTENSITY_RAMP = 0.025
DELOAD_INTENSITY = 0.9
TAPER_VOLUME = 0.5
TAPER_INTENSITY = 1.0


@dataclass(frozen=True)
class WeekLoad:
    """Planned load multipliers for one training week (week is 1-indexed)."""

    week: int
    volume_factor: float
    intensity_factor: float
    is_deload: bool
    is_taper: bool


def _validate_whole_number(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{name} must be a whole number, got {value!r}"
        raise ValueError(msg)


def _validate(total_weeks: int, deload_every: int, taper_weeks: int) -> None:
    _validate_whole_number("total_weeks", total_weeks)
    _validate_whole_number("deload_every", deload_every)
    _validate_whole_number("taper_weeks", taper_weeks)
    if total_weeks < 1:
        msg = f"total_weeks must be >= 1, got {total_weeks}"
        raise ValueError(msg)
    if deload_every < MIN_DELOAD_EVERY:
        msg = f"deload_every must be >= {MIN_DELOAD_EVERY}, got {deload_every}"
        raise ValueError(msg)
    if not 0 <= taper_weeks < total_weeks:
        msg = f"taper_weeks must be >= 0 and < total_weeks, got {taper_weeks}"
        raise ValueError(msg)


def build_weekly_waves(
    total_weeks: int,
    *,
    deload_every: int = 4,
    taper_weeks: int = 1,
    volume_ramp: float = DEFAULT_VOLUME_RAMP,
    deload_volume: float = 0.6,
) -> list[WeekLoad]:
    """Generate week-by-week load multipliers for a training block.

    Building weeks ramp volume by ``volume_ramp`` and intensity by 2.5% per
    week within each mesocycle; every ``deload_every``-th building week drops
    to ``deload_volume`` volume at 90% intensity; the final ``taper_weeks``
    weeks halve volume while holding intensity.
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
                WeekLoad(week, deload_volume, DELOAD_INTENSITY, is_deload=True, is_taper=False)
            )
            week_in_block = 0
            continue
        volume = 1.0 + volume_ramp * (week_in_block - 1)
        intensity = 1.0 + DEFAULT_INTENSITY_RAMP * (week_in_block - 1)
        waves.append(WeekLoad(week, volume, intensity, is_deload=False, is_taper=False))
    return waves
