"""Training residuals: how long a trained quality is retained (pure, deterministic).

Each quality has a residual training effect duration — how many days it holds
before decaying without a refresh stimulus (Issurin block-periodization reviews).
check_residuals scans a plan's per-quality stimulus days and warns when a
maintained quality would go longer than its residual without a refresh. Durations
are labeled cited/prior; the corpus study lands in the Phase 10 evidence pass.
"""

from dataclasses import dataclass

# Residual training-effect durations in days (Issurin 2010; team-chosen priors for
# qualities the review does not name directly). Longer = holds longer without work.
RESIDUAL_DAYS: dict[str, int] = {
    "aerobic_capacity": 30,
    "max_strength": 30,
    "hypertrophy": 30,
    "mobility": 20,
    "anaerobic_capacity": 18,
    "muscular_endurance": 15,
    "balance_stability": 15,
    "change_of_direction": 8,
    "explosive_strength": 8,
    "reactive_strength": 8,
    "acceleration": 5,
    "speed": 5,
}
_DEFAULT_RESIDUAL_DAYS = 15


def residual_days(quality: str) -> int:
    """Return the retention duration in days for a quality (team-chosen prior default)."""
    return RESIDUAL_DAYS.get(quality, _DEFAULT_RESIDUAL_DAYS)


@dataclass(frozen=True)
class QualityStimulus:
    """One planned training stimulus: the day it lands and the qualities it trains."""

    day_index: int
    qualities: tuple[str, ...]


@dataclass(frozen=True)
class ResidualWarning:
    """A quality that would decay past its residual before the next refresh."""

    quality: str
    gap_days: int
    residual_days: int
    after_day: int
    message: str


def _stimulus_days(stimuli: list[QualityStimulus], quality: str) -> list[int]:
    return sorted(s.day_index for s in stimuli if quality in s.qualities)


def check_residuals(stimuli: list[QualityStimulus], horizon_days: int) -> list[ResidualWarning]:
    """Warn where a trained quality's gap between stimuli exceeds its residual.

    For each quality trained at least once, checks every gap between consecutive
    stimulus days (and the tail from the last stimulus to horizon_days) against the
    quality's residual. Deterministic; sorted by (quality, after_day). Extending a
    gap never removes a warning.
    """
    if horizon_days < 0:
        msg = f"horizon_days must be non-negative, got {horizon_days}"
        raise ValueError(msg)
    warnings: list[ResidualWarning] = []
    qualities = sorted({quality for s in stimuli for quality in s.qualities})
    for quality in qualities:
        days = _stimulus_days(stimuli, quality)
        residual = residual_days(quality)
        boundaries = [*days, horizon_days]
        for previous, nxt in zip(days, boundaries[1:], strict=True):
            gap = nxt - previous
            if gap > residual:
                warnings.append(
                    ResidualWarning(
                        quality=quality,
                        gap_days=gap,
                        residual_days=residual,
                        after_day=previous,
                        message=(
                            f"{quality}: {gap} days between stimuli (day {previous} -> {nxt}) "
                            f"exceeds its {residual}-day residual; add a refresh stimulus"
                        ),
                    )
                )
    return warnings
