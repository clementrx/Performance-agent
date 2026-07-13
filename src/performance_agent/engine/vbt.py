"""Load-velocity profiling and velocity-based autoregulation (pure, deterministic).

A linear load-velocity profile (mean concentric velocity vs load) yields an
estimated 1RM at the minimal velocity threshold, the theoretical zero-velocity
load, and a minimal detectable change from the fit residuals. A submaximal set's
velocity gives a daily e1RM; comparing it to the profile suggests a bounded load
adjustment. Honest gates: fewer than 4 distinct loads, a load range under 30% of
the estimated 1RM, or a non-negative slope refuse with a reason.

Velocity-at-1RM (minimal velocity threshold) and velocity-loss stop thresholds are
team-chosen priors consistent with González-Badillo & Sánchez-Medina 2010 and
Sánchez-Medina & González-Badillo 2011 (added to the corpus in the Phase 10
evidence pass; labeled priors until then).
"""

from dataclasses import dataclass

from performance_agent.engine._validation import validate_finite

# Minimal velocity threshold: mean concentric velocity at 1RM (m/s). A general
# team-chosen prior; multi-joint barbell lifts sit near here.
DEFAULT_MVT_MPS = 0.30
_MIN_POINTS = 2
_MIN_DISTINCT_LOADS = 4
_MIN_RANGE_FRACTION = 0.30  # load span must cover >= 30% of the estimated 1RM
_MDC_Z = 1.96  # 95% minimal detectable change
_SQRT2 = 1.4142135623730951
_MAX_DAILY_ADJUST = 0.10  # bound day-of load suggestions to +/-10%

# Velocity-loss stop thresholds by training goal (fraction of within-set velocity
# drop at which to end the set) — team-chosen priors.
_VELOCITY_LOSS_THRESHOLD: dict[str, float] = {
    "strength": 0.15,
    "power": 0.10,
    "hypertrophy": 0.30,
    "endurance": 0.40,
}


@dataclass(frozen=True)
class LoadVelocityPoint:
    """One (load, mean concentric velocity) observation."""

    load_kg: float
    mean_velocity: float


@dataclass(frozen=True)
class LoadVelocityProfile:
    """A fitted load-velocity profile with its honesty verdict."""

    slope: float
    intercept: float
    r2: float
    load0_kg: float
    e1rm_kg: float
    velocity_mdc: float
    n_distinct_loads: int
    usable: bool
    reason: str | None


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """Ordinary least squares: return (slope, intercept, r2, residual_sd)."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    syy = sum((y - mean_y) ** 2 for y in ys)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    dof = n - 2
    residual_sd = (sum(r * r for r in residuals) / dof) ** 0.5 if dof > 0 else 0.0
    return slope, intercept, r2, residual_sd


def fit_load_velocity(
    points: list[LoadVelocityPoint], mvt: float = DEFAULT_MVT_MPS
) -> LoadVelocityProfile:
    """Fit a linear load-velocity profile and judge whether it is usable.

    Estimates 1RM at the minimal velocity threshold `mvt`. Gates: at least 4
    distinct loads, a load span of at least 30% of the estimated 1RM, and a
    negative slope. A profile that fails a gate is returned with usable=False and a
    reason (its numbers are still exposed for transparency). Raises on non-finite
    inputs or fewer than 2 points.
    """
    if len(points) < _MIN_POINTS:
        msg = f"need at least {_MIN_POINTS} velocity points to fit a profile, got {len(points)}"
        raise ValueError(msg)
    for point in points:
        validate_finite("load_kg", point.load_kg)
        validate_finite("mean_velocity", point.mean_velocity)
    xs = [p.load_kg for p in points]
    ys = [p.mean_velocity for p in points]
    slope, intercept, r2, residual_sd = _linear_fit(xs, ys)
    distinct = len(set(xs))
    e1rm = (mvt - intercept) / slope if slope != 0 else 0.0
    load0 = -intercept / slope if slope != 0 else 0.0
    velocity_mdc = _MDC_Z * _SQRT2 * residual_sd
    load_span = max(xs) - min(xs)
    usable, reason = _profile_verdict(slope, distinct, load_span, e1rm)
    return LoadVelocityProfile(
        slope=slope,
        intercept=intercept,
        r2=r2,
        load0_kg=load0,
        e1rm_kg=e1rm,
        velocity_mdc=velocity_mdc,
        n_distinct_loads=distinct,
        usable=usable,
        reason=reason,
    )


def _profile_verdict(
    slope: float, distinct_loads: int, load_span: float, e1rm: float
) -> tuple[bool, str | None]:
    if slope >= 0:
        return False, "slope is non-negative; velocity should fall as load rises (bad data)"
    if distinct_loads < _MIN_DISTINCT_LOADS:
        return False, f"need >= {_MIN_DISTINCT_LOADS} distinct loads, got {distinct_loads}"
    if e1rm <= 0 or load_span < _MIN_RANGE_FRACTION * e1rm:
        return False, (
            f"load range {load_span:.0f} kg covers under {_MIN_RANGE_FRACTION:.0%} of the "
            f"estimated 1RM ({e1rm:.0f} kg); spread the loads wider"
        )
    return True, None


def daily_e1rm(
    slope: float, load_kg: float, mean_velocity: float, mvt: float = DEFAULT_MVT_MPS
) -> float:
    """Estimate today's 1RM from one submaximal set, using the profile's slope.

    Anchors a fresh intercept on today's (load, velocity) point and extrapolates to
    the minimal velocity threshold. Raises on a non-negative slope.
    """
    if slope >= 0:
        msg = f"slope must be negative to estimate a daily 1RM, got {slope}"
        raise ValueError(msg)
    intercept_today = mean_velocity - slope * load_kg
    return (mvt - intercept_today) / slope


@dataclass(frozen=True)
class LoadAdjustment:
    """A bounded day-of load-adjustment suggestion from today's velocity."""

    ratio: float
    pct_change: float
    bounded: bool
    rationale: str


def velocity_load_adjustment(profile_e1rm: float, todays_e1rm: float) -> LoadAdjustment:
    """Suggest a bounded working-load scaling from today's e1RM vs the profile's.

    ratio = todays_e1rm / profile_e1rm, clamped to +/-10% (bounded=True when the
    raw ratio was outside the band). A ratio above 1 means today is strong (nudge
    loads up); below 1 means back off. Coaching judgment, not a prescription.
    """
    if profile_e1rm <= 0:
        msg = f"profile_e1rm must be positive, got {profile_e1rm}"
        raise ValueError(msg)
    raw = todays_e1rm / profile_e1rm
    low, high = 1.0 - _MAX_DAILY_ADJUST, 1.0 + _MAX_DAILY_ADJUST
    ratio = max(low, min(high, raw))
    bounded = raw < low or raw > high
    direction = "up" if ratio > 1 else "down" if ratio < 1 else "unchanged"
    rationale = (
        f"today's e1RM is {raw:.0%} of the profile's; nudge working loads {direction} "
        f"by {abs(ratio - 1):.0%}" + (" (bounded to +/-10%)" if bounded else "")
    )
    return LoadAdjustment(ratio=ratio, pct_change=ratio - 1.0, bounded=bounded, rationale=rationale)


def velocity_loss_threshold(goal: str) -> float:
    """Return the within-set velocity-loss stop threshold for a training goal."""
    if goal not in _VELOCITY_LOSS_THRESHOLD:
        msg = f"goal must be one of {sorted(_VELOCITY_LOSS_THRESHOLD)}, got {goal!r}"
        raise ValueError(msg)
    return _VELOCITY_LOSS_THRESHOLD[goal]
