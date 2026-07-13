"""Specificity fit and mesocycle specificity-mix checks (pure, deterministic).

Bondarchuk-style specificity runs general -> special -> specific -> competition.
A mesocycle phase has a target band on that axis: general preparation is
general-dominant, realization and taper are specific/competition-dominant. This
module scores how well one exercise's specificity fits a phase (used by the
selection engine) and warns when a phase's exercise mix drifts out of its band.

Bands are team-chosen priors consistent with engine/periodization.py phase intent.
"""

from dataclasses import dataclass

_SPECIFICITY_ORDINAL: dict[str, int] = {
    "general": 0,
    "special": 1,
    "specific": 2,
    "competition": 3,
}
_MAX_ORDINAL = 3

# Acceptable specificity band (min, max ordinal) per mesocycle phase — team-chosen
# priors: preparation is general-leaning, realization/taper are specific-leaning.
PHASE_SPECIFICITY_BAND: dict[str, tuple[int, int]] = {
    "general_prep": (0, 1),
    "specific_prep": (1, 2),
    "accumulation": (1, 2),
    "intensification": (2, 3),
    "realization": (2, 3),
    "maintenance": (0, 2),
    "taper": (2, 3),
    "return_to_load": (0, 1),
}
_DEFAULT_BAND = (0, 3)
# A phase is flagged when more than this fraction of its exercises fall out of band.
_OUT_OF_BAND_WARN_FRACTION = 0.5


@dataclass(frozen=True)
class SpecificityWarning:
    """One mesocycle whose specificity mix drifts out of its phase band."""

    phase: str
    out_of_band: int
    total: int
    message: str


def _ordinal(level: str) -> int:
    if level not in _SPECIFICITY_ORDINAL:
        msg = f"unknown specificity level {level!r}; known: {sorted(_SPECIFICITY_ORDINAL)}"
        raise ValueError(msg)
    return _SPECIFICITY_ORDINAL[level]


def specificity_fit(level: str, phase: str) -> float:
    """Score how well a specificity level fits a mesocycle phase (1.0 in band).

    Inside the phase band the fit is 1.0; outside it decays linearly with the
    ordinal distance to the nearest band edge (never below 0).
    """
    ordinal = _ordinal(level)
    low, high = PHASE_SPECIFICITY_BAND.get(phase, _DEFAULT_BAND)
    if low <= ordinal <= high:
        return 1.0
    distance = low - ordinal if ordinal < low else ordinal - high
    return max(0.0, 1.0 - distance / _MAX_ORDINAL)


def check_specificity_mix(phase: str, levels: list[str]) -> SpecificityWarning | None:
    """Warn when more than half a phase's exercises fall outside its specificity band.

    Returns None when the mix is acceptable or the phase has no attributed
    exercises. Deterministic.
    """
    if not levels:
        return None
    low, high = PHASE_SPECIFICITY_BAND.get(phase, _DEFAULT_BAND)
    out_of_band = sum(1 for level in levels if not low <= _ordinal(level) <= high)
    if out_of_band <= _OUT_OF_BAND_WARN_FRACTION * len(levels):
        return None
    edge = ", ".join(k for k, v in _SPECIFICITY_ORDINAL.items() if low <= v <= high)
    message = (
        f"{phase}: {out_of_band}/{len(levels)} exercises fall outside the "
        f"phase-appropriate specificity band ({edge})"
    )
    return SpecificityWarning(
        phase=phase, out_of_band=out_of_band, total=len(levels), message=message
    )
