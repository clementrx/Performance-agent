"""Endurance performance prediction (Riegel model) and pace utilities."""

from dataclasses import dataclass

RIEGEL_EXPONENT = 1.06  # Riegel (1981) empirical fatigue exponent for running
RIEGEL_MIN_DISTANCE_M = 1500  # model validity band: ~1.5 km ...
RIEGEL_MAX_DISTANCE_M = 42195  # ... to the marathon
MAX_RIEGEL_EXPONENT = 1.3

# Threshold pace is proxied by the Riegel-projected 10 km pace (a ~30-40 min
# effort approximates lactate threshold for most runners) — team-chosen prior.
_THRESHOLD_REFERENCE_M = 10000
# Pace-zone boundaries as multiples of threshold pace (larger = slower). Five
# contiguous zones from Z5 (fastest, interval) to Z1 (slowest, recovery). The
# spread is a team-chosen prior consistent with common 5-zone running models.
_ZONE_BOUNDS: list[tuple[str, float, float]] = [
    ("Z5 interval", 0.88, 0.99),
    ("Z4 threshold", 0.99, 1.06),
    ("Z3 tempo", 1.06, 1.13),
    ("Z2 endurance", 1.13, 1.25),
    ("Z1 recovery", 1.25, 1.40),
]


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
            f"got {known_distance_m!r}, {known_time_s!r}, {target_distance_m!r}"
        )
        raise ValueError(msg)
    for name, distance_m in (
        ("known_distance_m", known_distance_m),
        ("target_distance_m", target_distance_m),
    ):
        if not RIEGEL_MIN_DISTANCE_M <= distance_m <= RIEGEL_MAX_DISTANCE_M:
            msg = (
                f"{name} must be a distance within the Riegel validity band "
                f"[{RIEGEL_MIN_DISTANCE_M}, {RIEGEL_MAX_DISTANCE_M}] m, got {distance_m!r}"
            )
            raise ValueError(msg)
    if not 0 < exponent <= MAX_RIEGEL_EXPONENT:
        msg = f"exponent must be in (0, {MAX_RIEGEL_EXPONENT}], got {exponent!r}"
        raise ValueError(msg)
    return known_time_s * (target_distance_m / known_distance_m) ** exponent


def pace_s_per_km(distance_m: float, time_s: float) -> float:
    """Return pace in seconds per kilometre."""
    if distance_m <= 0 or time_s <= 0:
        msg = f"distance_m and time_s must be positive, got {distance_m!r}, {time_s!r}"
        raise ValueError(msg)
    return time_s / (distance_m / 1000)


@dataclass(frozen=True)
class PaceZone:
    """One training pace zone (faster pace = smaller s/km; low is the faster edge)."""

    name: str
    low_pace_s_per_km: float  # faster edge
    high_pace_s_per_km: float  # slower edge


def training_zones_from_race(distance_m: float, time_s: float) -> list[PaceZone]:
    """Derive five running pace zones from a recent race performance.

    Estimates threshold pace by Riegel-projecting the race to 10 km (a ~30-40 min
    effort proxies lactate threshold), then scales it into five contiguous zones
    from Z5 (interval, fastest) to Z1 (recovery, slowest). The race distance must
    fall inside the Riegel validity band (1500-42195 m). Zones are descriptive
    training guidance built on a population model, not a physiological test;
    paces are in seconds per kilometre.
    """
    predicted_10k = riegel_predict(distance_m, time_s, _THRESHOLD_REFERENCE_M)
    threshold_pace = pace_s_per_km(_THRESHOLD_REFERENCE_M, predicted_10k)
    return [
        PaceZone(
            name=name,
            low_pace_s_per_km=threshold_pace * low,
            high_pace_s_per_km=threshold_pace * high,
        )
        for name, low, high in _ZONE_BOUNDS
    ]
