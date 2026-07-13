"""Tests for the test-battery scheduling engine."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.test_battery import (
    TestableKpi,
    cadence_for,
    plan_test_battery,
)


def test_cadence_known_and_default():
    assert cadence_for("speed") == 4
    assert cadence_for("aerobic_capacity") == 8
    assert cadence_for("something_unlisted") == 6


def test_baseline_scheduled_at_week_one():
    kpis = [TestableKpi("squat-1rm", "max_strength", needs_baseline=True)]
    tests = plan_test_battery(kpis, horizon_weeks=12, blackout_weeks=frozenset())
    assert tests[0].week == 1
    assert tests[0].kind == "baseline"


def test_retests_at_cadence():
    kpis = [TestableKpi("100m", "speed", needs_baseline=False)]  # cadence 4
    tests = plan_test_battery(kpis, horizon_weeks=12, blackout_weeks=frozenset())
    assert [t.week for t in tests] == [4, 8, 12]
    assert all(t.kind == "retest" for t in tests)


def test_no_test_lands_on_a_blackout_week():
    kpis = [TestableKpi("100m", "speed", needs_baseline=True)]
    blackout = frozenset({4, 8})
    tests = plan_test_battery(kpis, horizon_weeks=12, blackout_weeks=blackout)
    assert all(t.week not in blackout for t in tests)


def test_retest_shifts_earlier_out_of_blackout():
    kpis = [TestableKpi("100m", "speed", needs_baseline=False)]
    # cadence 4 -> targets 4, 8, 12; block 4 -> 3, block 8 -> 7.
    tests = plan_test_battery(kpis, horizon_weeks=12, blackout_weeks=frozenset({4, 8}))
    assert {t.week for t in tests} == {3, 7, 12}


def test_baseline_dropped_when_week_one_blacked_out():
    kpis = [TestableKpi("squat-1rm", "max_strength", needs_baseline=True)]
    tests = plan_test_battery(kpis, horizon_weeks=12, blackout_weeks=frozenset({1}))
    assert all(t.kind != "baseline" for t in tests)


def test_output_sorted_by_week_then_kpi():
    kpis = [
        TestableKpi("b-kpi", "speed", needs_baseline=True),
        TestableKpi("a-kpi", "max_strength", needs_baseline=True),
    ]
    tests = plan_test_battery(kpis, horizon_weeks=6, blackout_weeks=frozenset())
    weeks = [(t.week, t.kpi_id) for t in tests]
    assert weeks == sorted(weeks)


def test_horizon_must_be_positive():
    with pytest.raises(ValueError, match="horizon_weeks must be >= 1"):
        plan_test_battery([], horizon_weeks=0, blackout_weeks=frozenset())


@given(
    horizon=st.integers(min_value=1, max_value=52),
    blackout=st.sets(st.integers(min_value=1, max_value=52), max_size=10),
)
def test_never_schedules_on_blackout_property(horizon, blackout):
    kpis = [
        TestableKpi("a", "speed", needs_baseline=True),
        TestableKpi("b", "aerobic_capacity", needs_baseline=False),
    ]
    tests = plan_test_battery(kpis, horizon, frozenset(blackout))
    assert all(t.week not in blackout for t in tests)
    assert all(1 <= t.week <= horizon for t in tests)
