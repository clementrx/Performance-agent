"""Load-velocity profiling at the athlete layer: read logged VBT sets, call engine.

The engine (engine/vbt.py) is pydantic-free; this module reads the athlete's
logged vbt_sets for one exercise, builds load-velocity points, and calls the pure
fitter. velocity_suggestion refits the profile and compares today's warm-up set to
it, returning a bounded, labeled load-adjustment suggestion — or None when there is
no usable profile (degradation invariant: no VBT data, no suggestion, no change).
"""

from pathlib import Path
from typing import TypedDict

from performance_agent.engine.vbt import (
    DEFAULT_MVT_MPS,
    LoadVelocityPoint,
    daily_e1rm,
    fit_load_velocity,
    velocity_load_adjustment,
)
from performance_agent.memory import store

_MIN_VBT_SETS = 2


class LoadVelocityProfileView(TypedDict):
    """A fitted load-velocity profile for the LLM to narrate (usable says trust it)."""

    exercise: str
    n_points: int
    n_distinct_loads: int
    slope: float
    intercept: float
    r2: float
    load0_kg: float
    e1rm_kg: float
    velocity_mdc: float
    usable: bool
    reason: str | None


class VelocitySuggestionView(TypedDict):
    """A bounded day-of load-adjustment suggestion from today's warm-up velocity."""

    exercise: str
    todays_e1rm_kg: float
    profile_e1rm_kg: float
    ratio: float
    pct_change: float
    bounded: bool
    rationale: str


def _points_for(base_dir: Path, exercise: str) -> list[LoadVelocityPoint]:
    target = exercise.strip().casefold()
    return [
        LoadVelocityPoint(load_kg=vset.load_kg, mean_velocity=vset.mean_velocity)
        for entry in store.read_sessions(base_dir)
        for vset in entry.vbt_sets
        if vset.exercise.strip().casefold() == target
    ]


def fit_exercise_profile(
    base_dir: Path, exercise: str, mvt: float = DEFAULT_MVT_MPS
) -> LoadVelocityProfileView:
    """Fit the load-velocity profile for one exercise from its logged VBT sets.

    Raises when fewer than 2 VBT sets exist for the exercise. The returned view
    carries usable + reason: an under-spread profile comes back usable=False with a
    reason rather than a fabricated number.
    """
    points = _points_for(base_dir, exercise)
    if len(points) < _MIN_VBT_SETS:
        msg = (
            f"need at least {_MIN_VBT_SETS} logged VBT sets for {exercise!r} to fit a "
            f"profile, got {len(points)}"
        )
        raise ValueError(msg)
    profile = fit_load_velocity(points, mvt)
    return LoadVelocityProfileView(
        exercise=exercise,
        n_points=len(points),
        n_distinct_loads=profile.n_distinct_loads,
        slope=profile.slope,
        intercept=profile.intercept,
        r2=profile.r2,
        load0_kg=profile.load0_kg,
        e1rm_kg=profile.e1rm_kg,
        velocity_mdc=profile.velocity_mdc,
        usable=profile.usable,
        reason=profile.reason,
    )


def velocity_suggestion(
    base_dir: Path,
    exercise: str,
    load_kg: float,
    mean_velocity: float,
    mvt: float = DEFAULT_MVT_MPS,
) -> VelocitySuggestionView | None:
    """Suggest a bounded load adjustment from today's warm-up set, or None.

    Returns None when there is no usable load-velocity profile for the exercise
    (fewer than the gated data, or a bad fit) — the caller then leaves loads
    unchanged. Otherwise compares today's e1RM (from the warm-up load+velocity) to
    the profile's and returns a bounded +/-10% suggestion.
    """
    points = _points_for(base_dir, exercise)
    if len(points) < _MIN_VBT_SETS:
        return None
    profile = fit_load_velocity(points, mvt)
    if not profile.usable:
        return None
    todays = daily_e1rm(profile.slope, load_kg, mean_velocity, mvt)
    adjustment = velocity_load_adjustment(profile.e1rm_kg, todays)
    return VelocitySuggestionView(
        exercise=exercise,
        todays_e1rm_kg=todays,
        profile_e1rm_kg=profile.e1rm_kg,
        ratio=adjustment.ratio,
        pct_change=adjustment.pct_change,
        bounded=adjustment.bounded,
        rationale=adjustment.rationale,
    )
