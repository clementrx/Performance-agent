"""Shared input validators for engine modules (internal)."""

import math


def validate_whole_number(name: str, value: int) -> None:
    """Reject bool and non-int values with an actionable ValueError."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{name} must be a whole number, got {value!r}"
        raise ValueError(msg)


def validate_finite(name: str, value: float) -> None:
    """Reject NaN and infinities with an actionable ValueError."""
    if not math.isfinite(value):
        msg = f"{name} must be finite, got {value!r}"
        raise ValueError(msg)
