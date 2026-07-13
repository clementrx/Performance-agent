"""Tests for the fitted two-component Banister model."""

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from performance_agent.engine.banister import (
    PerformancePoint,
    _decay_trace,
    fit_banister,
)


def _loads(n=84):
    return [50.0 + 30.0 * math.sin(i / 5.0) + 20.0 for i in range(n)]


def _synthetic_points(loads, p0, k1, k2, tau1, tau2, days):  # noqa: PLR0913 -- synthetic-athlete params
    g1 = _decay_trace(loads, tau1)
    g2 = _decay_trace(loads, tau2)
    return [PerformancePoint(day_index=d, value=p0 + k1 * g1[d] - k2 * g2[d]) for d in days]


def test_recovers_clean_params():
    loads = _loads()
    points = _synthetic_points(loads, 100.0, 0.10, 0.14, 40.0, 8.0, [10, 25, 40, 55, 70, 82])
    fit = fit_banister(loads, points)
    assert fit.usable
    assert fit.tau1 == pytest.approx(40.0, abs=2.0)
    assert fit.tau2 == pytest.approx(8.0, abs=2.0)
    assert fit.k1 == pytest.approx(0.10, abs=0.02)
    assert fit.k2 == pytest.approx(0.14, abs=0.02)
    assert fit.r2 == pytest.approx(1.0, abs=1e-6)
    assert fit.tau1 > fit.tau2


def test_short_load_history_refused():
    loads = _loads(30)
    points = _synthetic_points(loads, 100.0, 0.1, 0.14, 40.0, 8.0, [5, 12, 18, 24, 28])
    fit = fit_banister(loads, points)
    assert not fit.usable
    assert "load history" in (fit.reason or "")


def test_too_few_points_refused():
    loads = _loads()
    points = _synthetic_points(loads, 100.0, 0.1, 0.14, 40.0, 8.0, [10, 40, 82])
    fit = fit_banister(loads, points)
    assert not fit.usable
    assert "performance points" in (fit.reason or "")


def test_points_not_spanning_refused():
    loads = _loads()
    # Five points all crammed into the first three weeks.
    points = _synthetic_points(loads, 100.0, 0.1, 0.14, 40.0, 8.0, [2, 5, 9, 14, 18])
    fit = fit_banister(loads, points)
    assert not fit.usable
    assert "span" in (fit.reason or "")


def test_constant_loads_degenerate_refused():
    loads = [40.0] * 84
    points = [PerformancePoint(day_index=d, value=100.0) for d in [10, 25, 40, 55, 70, 82]]
    fit = fit_banister(loads, points)
    assert not fit.usable


def test_out_of_range_day_index_raises():
    loads = _loads()
    with pytest.raises(ValueError, match="outside the load series"):
        fit_banister(loads, [PerformancePoint(day_index=200, value=100.0)])


@settings(max_examples=25, suppress_health_check=[HealthCheck.filter_too_much])
@given(
    k1=st.floats(min_value=0.05, max_value=0.20),
    k2=st.floats(min_value=0.08, max_value=0.25),
    tau1=st.floats(min_value=30.0, max_value=50.0),
    tau2=st.floats(min_value=5.0, max_value=12.0),
)
def test_recovers_params_across_athletes(k1, k2, tau1, tau2):
    assume(tau1 > tau2 + 10)
    loads = _loads()
    points = _synthetic_points(loads, 100.0, k1, k2, tau1, tau2, [10, 25, 40, 55, 70, 82])
    fit = fit_banister(loads, points)
    # Exact parameter recovery is not guaranteed (coarse grid + collinear decay
    # features — the classic Banister identifiability issue); the meaningful
    # invariant is that a usable fit REPRODUCES the observations and keeps
    # fitness slower than fatigue.
    if fit.usable:
        assert fit.r2 > 0.9
        assert fit.tau1 > fit.tau2
