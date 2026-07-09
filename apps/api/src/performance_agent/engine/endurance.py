"""Endurance performance prediction (Riegel model) and pace utilities."""

RIEGEL_EXPONENT = 1.06  # Riegel (1981) empirical fatigue exponent for running


def riegel_predict(
    known_distance_m: float,
    known_time_s: float,
    target_distance_m: float,
    exponent: float = RIEGEL_EXPONENT,
) -> float:
    """Predict a race time at a new distance from a known performance.

    Uses Riegel's power law: t2 = t1 * (d2 / d1) ** exponent. Reasonable for
    race distances between ~1.5 km and the marathon; accuracy degrades outside
    that range.
    """
    if known_distance_m <= 0 or known_time_s <= 0 or target_distance_m <= 0:
        msg = (
            "known_distance_m, known_time_s and target_distance_m must be positive, "
            f"got {known_distance_m}, {known_time_s}, {target_distance_m}"
        )
        raise ValueError(msg)
    return known_time_s * (target_distance_m / known_distance_m) ** exponent


def pace_s_per_km(distance_m: float, time_s: float) -> float:
    """Return pace in seconds per kilometre."""
    if distance_m <= 0 or time_s <= 0:
        msg = f"distance_m and time_s must be positive, got {distance_m}, {time_s}"
        raise ValueError(msg)
    return time_s / (distance_m / 1000)
