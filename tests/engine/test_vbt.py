"""Tests for load-velocity profiling and velocity-based autoregulation."""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from performance_agent.engine.vbt import (
    LoadVelocityPoint,
    daily_e1rm,
    fit_load_velocity,
    velocity_load_adjustment,
    velocity_loss_threshold,
)


def _synthetic(slope, intercept, loads):
    return [LoadVelocityPoint(load_kg=x, mean_velocity=intercept + slope * x) for x in loads]


def test_recovers_clean_profile():
    # velocity = 1.5 - 0.006*load ; at MVT 0.30 => 1RM = (0.30-1.5)/-0.006 = 200 kg
    points = _synthetic(-0.006, 1.5, [60, 100, 140, 180])
    profile = fit_load_velocity(points)
    assert profile.usable
    assert profile.slope == pytest.approx(-0.006, abs=1e-6)
    assert profile.e1rm_kg == pytest.approx(200.0, abs=1.0)
    assert profile.r2 == pytest.approx(1.0, abs=1e-9)


def test_too_few_distinct_loads_refused():
    points = _synthetic(-0.006, 1.5, [100, 100, 100, 140])
    profile = fit_load_velocity(points)
    assert not profile.usable
    assert "distinct loads" in (profile.reason or "")


def test_narrow_range_refused():
    # Four distinct loads but spanning far less than 30% of the ~200 kg 1RM.
    points = _synthetic(-0.006, 1.5, [100, 105, 110, 115])
    profile = fit_load_velocity(points)
    assert not profile.usable
    assert "load range" in (profile.reason or "")


def test_non_negative_slope_refused():
    points = [LoadVelocityPoint(load_kg=x, mean_velocity=0.5) for x in (60, 100, 140, 180)]
    profile = fit_load_velocity(points)
    assert not profile.usable


def test_daily_e1rm_matches_profile_on_profile_point():
    slope, intercept = -0.006, 1.5
    # A submaximal set on the profile line returns the profile's 1RM.
    e1rm = daily_e1rm(slope, 100, intercept + slope * 100)
    assert e1rm == pytest.approx(200.0, abs=1.0)


def test_daily_e1rm_slow_day_is_lower():
    slope = -0.006
    on_line = daily_e1rm(slope, 100, 1.5 + slope * 100)
    slow = daily_e1rm(slope, 100, (1.5 + slope * 100) - 0.1)  # 0.1 m/s slower
    assert slow < on_line


def test_velocity_load_adjustment_bounded():
    adj = velocity_load_adjustment(profile_e1rm=200.0, todays_e1rm=160.0)  # 80% -> clamp
    assert adj.bounded is True
    assert adj.ratio == pytest.approx(0.90)
    assert adj.pct_change == pytest.approx(-0.10)


def test_velocity_load_adjustment_small_change_unbounded():
    adj = velocity_load_adjustment(profile_e1rm=200.0, todays_e1rm=210.0)  # +5%
    assert adj.bounded is False
    assert adj.ratio == pytest.approx(1.05)


def test_velocity_loss_thresholds():
    assert velocity_loss_threshold("power") < velocity_loss_threshold("hypertrophy")
    with pytest.raises(ValueError, match="goal must be one of"):
        velocity_loss_threshold("mobility")


@given(
    slope=st.floats(min_value=-0.008, max_value=-0.003),
    intercept=st.floats(min_value=1.3, max_value=2.0),
    noise=st.lists(st.floats(min_value=-0.02, max_value=0.02), min_size=6, max_size=6),
)
def test_recovers_noisy_profile_within_tolerance(slope, intercept, noise):
    loads = [50, 80, 110, 140, 170, 200]
    true_velocities = [intercept + slope * x for x in loads]
    # Only realistic profiles: every measured velocity stays clearly positive.
    assume(min(true_velocities) > 0.15)
    points = [
        LoadVelocityPoint(load_kg=x, mean_velocity=v + n)
        for x, v, n in zip(loads, true_velocities, noise, strict=True)
    ]
    profile = fit_load_velocity(points)
    # Slope recovered close to truth despite noise.
    assert profile.slope == pytest.approx(slope, abs=0.005)
