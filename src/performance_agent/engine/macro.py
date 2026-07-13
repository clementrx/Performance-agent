"""Multi-year macrocycle planning: backward year typing + quality budgets (pure).

A macrocycle is planned backward from the major event: the final year is
realization, the year before qualification (for >= 3-year horizons), and the
earliest years development. Each year's quality-emphasis budget is derived from the
PerformanceModel gap priorities, then tilted by year type — development years bias
general capacities and the biggest weaknesses, the realization year biases specific
and competition qualities. Deterministic and datetime-free.
"""

from dataclasses import dataclass

# Specific/competition-expression qualities vs general capacities (team-chosen
# classification). Development years favor general, realization favors specific.
_SPECIFIC_QUALITIES = frozenset(
    {
        "speed",
        "acceleration",
        "reactive_strength",
        "explosive_strength",
        "change_of_direction",
        "anaerobic_capacity",
    }
)
_DEVELOPMENT_GENERAL_TILT = 1.5
_DEVELOPMENT_SPECIFIC_TILT = 0.7
_REALIZATION_SPECIFIC_TILT = 1.5
_REALIZATION_GENERAL_TILT = 0.7
_MIN_HORIZON_YEARS = 1
_MAX_HORIZON_YEARS = 4
_QUALIFICATION_MIN_HORIZON = 3


@dataclass(frozen=True)
class QualityPriorityInput:
    """One quality's gap-driven priority (higher = a bigger training need)."""

    quality: str
    priority: float


@dataclass(frozen=True)
class MacroYearPlan:
    """A planned macro year: its type and normalized quality emphases."""

    index: int
    year_type: str
    quality_emphases: tuple[tuple[str, float], ...]


def _year_types(horizon_years: int) -> list[str]:
    """Backward year typing: last=realization, prior=qualification, rest development."""
    types = ["development"] * horizon_years
    types[-1] = "realization"
    if horizon_years >= _QUALIFICATION_MIN_HORIZON:
        types[-2] = "qualification"
    return types


def _tilt(quality: str, year_type: str) -> float:
    specific = quality in _SPECIFIC_QUALITIES
    if year_type == "development":
        return _DEVELOPMENT_SPECIFIC_TILT if specific else _DEVELOPMENT_GENERAL_TILT
    if year_type == "realization":
        return _REALIZATION_SPECIFIC_TILT if specific else _REALIZATION_GENERAL_TILT
    return 1.0  # qualification: neutral


def _emphases_for(
    priorities: list[QualityPriorityInput], year_type: str
) -> tuple[tuple[str, float], ...]:
    weighted = {p.quality: max(0.0, p.priority) * _tilt(p.quality, year_type) for p in priorities}
    total = sum(weighted.values())
    if total <= 0:
        return ()
    normalized = sorted(
        ((quality, weight / total) for quality, weight in weighted.items()),
        key=lambda item: (-item[1], item[0]),
    )
    return tuple(normalized)


def build_macro_years(
    horizon_years: int, priorities: list[QualityPriorityInput]
) -> list[MacroYearPlan]:
    """Type each macro year backward and derive its gap-tilted quality emphases.

    priorities are the PerformanceModel gap priorities (quality, priority score).
    Development years tilt toward general capacities and weaknesses; the realization
    year tilts toward specific/competition qualities. Emphases are normalized per
    year to sum to 1 (empty when no positive priority). Deterministic.
    """
    if not _MIN_HORIZON_YEARS <= horizon_years <= _MAX_HORIZON_YEARS:
        msg = f"horizon_years must be 1-4, got {horizon_years}"
        raise ValueError(msg)
    return [
        MacroYearPlan(
            index=index,
            year_type=year_type,
            quality_emphases=_emphases_for(priorities, year_type),
        )
        for index, year_type in enumerate(_year_types(horizon_years), start=1)
    ]
