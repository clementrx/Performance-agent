"""Strength math: 1RM estimation and percentage-based load prescription.

Formulas are only validated for 1-12 repetitions; both Epley and Brzycki
degrade badly beyond ~10 reps, so higher inputs are rejected.
"""

from performance_agent.engine._validation import validate_whole_number

MAX_ESTIMATION_REPS = 12
MAX_PERCENTAGE = 1.3  # supra-maximal work (eccentrics, partials) tops out around 130%


def _validate_load_and_reps(load_kg: float, reps: int) -> None:
    validate_whole_number("reps", reps)
    if load_kg <= 0:
        msg = f"load_kg must be positive, got {load_kg!r}"
        raise ValueError(msg)
    if not 1 <= reps <= MAX_ESTIMATION_REPS:
        msg = f"reps must be between 1 and {MAX_ESTIMATION_REPS}, got {reps!r}"
        raise ValueError(msg)


def one_rm_epley(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Epley formula: load * (1 + reps / 30).

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * (1 + reps / 30)


def one_rm_brzycki(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Brzycki formula: load * 36 / (37 - reps).

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged (float rounding in
    ``load * 36 / 36`` would otherwise land one ULP below the lifted load).
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * 36 / (37 - reps)


def load_for_percentage(one_rm_kg: float, percentage: float) -> float:
    """Return the absolute load for a fraction of 1RM (e.g. 0.8 for 80%)."""
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < percentage <= MAX_PERCENTAGE:
        msg = f"percentage must be in (0, {MAX_PERCENTAGE}], got {percentage!r}"
        raise ValueError(msg)
    return one_rm_kg * percentage
