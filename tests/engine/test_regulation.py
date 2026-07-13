"""Threshold and scenario tests for the data-driven deload regulator."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.load import fitness_fatigue_series, weekly_strain
from performance_agent.engine.regulation import should_deload


def _calm(  # noqa: PLR0913 -- keyword-only test helper mirroring the signal set
    *,
    weeks_since_deload: int = 1,
    monotony_recent: float | None = 1.0,
    strain_trend: float = 0.0,
    tsb: float = 0.0,
    readiness_trend: float = 0.0,
    adherence_pct: float = 95.0,
    planned_interval_weeks: int = 4,
):
    """A no-signal baseline call; override the axis under test."""
    return should_deload(
        weeks_since_deload=weeks_since_deload,
        monotony_recent=monotony_recent,
        strain_trend=strain_trend,
        tsb=tsb,
        readiness_trend=readiness_trend,
        adherence_pct=adherence_pct,
        planned_interval_weeks=planned_interval_weeks,
    )


def test_calm_week_recommends_nothing():
    result = _calm()
    assert result.recommendation == "none"
    assert result.drivers == []


# --- planned-counter guardrail, both sides of the interval + 1 boundary ---


def test_at_planned_interval_no_forced_deload():
    # interval 4: weeks_since_deload 4 is NOT yet overdue (needs >= 5)
    assert _calm(weeks_since_deload=4, planned_interval_weeks=4).recommendation == "none"


def test_one_past_planned_interval_forces_full():
    result = _calm(weeks_since_deload=5, planned_interval_weeks=4)
    assert result.recommendation == "full"
    assert any("cadence" in d for d in result.drivers)


def test_overdue_full_ignores_healthy_signals():
    # Fresh, adherent, varied -- but the counter is past due -> still full.
    result = should_deload(
        weeks_since_deload=6,
        monotony_recent=1.0,
        strain_trend=-100.0,
        tsb=20.0,
        readiness_trend=5.0,
        adherence_pct=100.0,
        planned_interval_weeks=4,
    )
    assert result.recommendation == "full"


# --- deep-fatigue rule, both sides of the TSB boundary ---


def test_tsb_just_above_boundary_no_full():
    assert _calm(tsb=-25.0, readiness_trend=-3.0).recommendation == "none"


def test_tsb_just_below_boundary_full():
    result = _calm(tsb=-25.1, readiness_trend=-3.0)
    assert result.recommendation == "full"
    assert any("TSB" in d for d in result.drivers)


def test_deep_fatigue_needs_non_improving_readiness():
    # TSB deep but readiness improving (trend > 0) -> the fatigue rule does not fire.
    assert _calm(tsb=-40.0, readiness_trend=1.0).recommendation == "none"


def test_readiness_trend_zero_counts_as_not_improving():
    assert _calm(tsb=-40.0, readiness_trend=0.0).recommendation == "full"


def test_low_adherence_downgrades_full_to_light():
    result = _calm(tsb=-40.0, readiness_trend=-2.0, adherence_pct=55.0)
    assert result.recommendation == "light"
    assert any("adherence" in d for d in result.drivers)


def test_adherence_floor_boundary():
    # 70% is the floor (inclusive high side): >= 70 keeps full, < 70 downgrades.
    assert _calm(tsb=-40.0, readiness_trend=-2.0, adherence_pct=70.0).recommendation == "full"
    assert _calm(tsb=-40.0, readiness_trend=-2.0, adherence_pct=69.9).recommendation == "light"


# --- monotony / strain rule, both sides of the monotony boundary ---


def test_monotony_at_boundary_no_light():
    assert _calm(monotony_recent=2.0, strain_trend=100.0).recommendation == "none"


def test_monotony_above_boundary_with_rising_strain_light():
    result = _calm(monotony_recent=2.1, strain_trend=100.0)
    assert result.recommendation == "light"
    assert any("monotony" in d for d in result.drivers)


def test_monotony_high_but_strain_flat_no_light():
    assert _calm(monotony_recent=3.0, strain_trend=0.0).recommendation == "none"


def test_none_monotony_never_triggers():
    assert _calm(monotony_recent=None, strain_trend=500.0).recommendation == "none"


def test_full_dominates_light_when_both_fire():
    result = _calm(tsb=-40.0, readiness_trend=-2.0, monotony_recent=3.0, strain_trend=100.0)
    assert result.recommendation == "full"


# --- validation ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"weeks_since_deload": -1},
        {"planned_interval_weeks": 0},
        {"adherence_pct": 120.0},
        {"adherence_pct": -1.0},
        {"tsb": float("nan")},
        {"strain_trend": float("inf")},
        {"monotony_recent": -0.5},
    ],
)
def test_rejects_out_of_range(overrides):
    with pytest.raises(ValueError):
        _calm(**overrides)


def test_rejects_non_integer_weeks():
    with pytest.raises(ValueError, match="whole number"):
        should_deload(1.5, 1.0, 0.0, 0.0, 0.0, 95.0)  # ty: ignore[invalid-argument-type]


# --- scenario: a synthetic overreach series fires full within a week of the spike ---


def test_overreach_scenario_fires_full_after_spike():
    # 6 calm weeks of moderate daily load, then a sharp spike week.
    base_week = [300.0, 0.0, 350.0, 0.0, 320.0, 0.0, 0.0]
    daily = base_week * 6
    spike_week = [700.0, 650.0, 700.0, 680.0, 720.0, 600.0, 400.0]
    daily_with_spike = daily + spike_week

    tsb_before = fitness_fatigue_series(daily)[-1].tsb
    tsb_after = fitness_fatigue_series(daily_with_spike)[-1].tsb
    readiness_trend = tsb_after - tsb_before  # freshness fell hard over the spike week

    strain_before = weekly_strain(base_week) or 0.0
    strain_after = weekly_strain(spike_week) or 0.0

    assert tsb_after < -25.0  # the spike drove freshness deeply negative
    assert readiness_trend < 0  # readiness declining

    result = should_deload(
        weeks_since_deload=1,
        monotony_recent=None,
        strain_trend=strain_after - strain_before,
        tsb=tsb_after,
        readiness_trend=readiness_trend,
        adherence_pct=95.0,
        planned_interval_weeks=4,
    )
    assert result.recommendation == "full"
    assert any("TSB" in d for d in result.drivers)


@given(
    weeks_since=st.integers(min_value=0, max_value=20),
    tsb=st.floats(min_value=-60, max_value=40),
    readiness=st.floats(min_value=-20, max_value=20),
    adherence=st.floats(min_value=0, max_value=100),
)
def test_recommendation_always_valid(weeks_since, tsb, readiness, adherence):
    result = should_deload(
        weeks_since_deload=weeks_since,
        monotony_recent=1.5,
        strain_trend=10.0,
        tsb=tsb,
        readiness_trend=readiness,
        adherence_pct=adherence,
    )
    assert result.recommendation in ("none", "light", "full")
    if result.recommendation != "none":
        assert result.drivers
