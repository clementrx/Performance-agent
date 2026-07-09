"""Endurance performance prediction (Riegel model) and pace utilities."""

RIEGEL_EXPONENT = 1.06  # Riegel (1981) empirical fatigue exponent for running
RIEGEL_MIN_DISTANCE_M = 1500  # model validity band: ~1.5 km ...
RIEGEL_MAX_DISTANCE_M = 42195  # ... to the marathon
MAX_RIEGEL_EXPONENT = 1.3


def riegel_predict(
    known_distance_m: float,
    known_time_s: float,
    target_distance_m: float,
    exponent: float = RIEGEL_EXPONENT,
) -> float:
    """Predict a race time at a new distance from a known performance.

    Uses Riegel's power law: t2 = t1 * (d2 / d1) ** exponent. Both distances
    must fall within the model's validity band, RIEGEL_MIN_DISTANCE_M to
    RIEGEL_MAX_DISTANCE_M (1.5 km to the marathon); values outside it are
    rejected with ValueError, as are exponents outside (0, MAX_RIEGEL_EXPONENT].
    """
    if known_distance_m <= 0 or known_time_s <= 0 or target_distance_m <= 0:
        msg = (
            "known_distance_m, known_time_s and target_distance_m must be positive, "
            f"got {known_distance_m}, {known_time_s}, {target_distance_m}"
        )
        raise ValueError(msg)
    for name, distance_m in (
        ("known_distance_m", known_distance_m),
        ("target_distance_m", target_distance_m),
    ):
        if not RIEGEL_MIN_DISTANCE_M <= distance_m <= RIEGEL_MAX_DISTANCE_M:
            msg = (
                f"{name} must be a distance within the Riegel validity band "
                f"[{RIEGEL_MIN_DISTANCE_M}, {RIEGEL_MAX_DISTANCE_M}] m, got {distance_m}"
            )
            raise ValueError(msg)
    if not 0 < exponent <= MAX_RIEGEL_EXPONENT:
        msg = f"exponent must be in (0, {MAX_RIEGEL_EXPONENT}], got {exponent}"
        raise ValueError(msg)
    return known_time_s * (target_distance_m / known_distance_m) ** exponent


def pace_s_per_km(distance_m: float, time_s: float) -> float:
    """Return pace in seconds per kilometre."""
    if distance_m <= 0 or time_s <= 0:
        msg = f"distance_m and time_s must be positive, got {distance_m}, {time_s}"
        raise ValueError(msg)
    return time_s / (distance_m / 1000)
