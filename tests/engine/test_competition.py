"""Pure pre-competition math: carb loading, attempts, pacing, window."""

import pytest

from performance_agent.engine.competition import (
    carb_loading_targets,
    pacing_plan,
    protocol_window_days,
    select_attempts,
)


def test_long_event_loads_8_to_12_g_per_kg_over_48h():
    result = carb_loading_targets(70.0, 180.0)
    assert result.loading_required is True
    assert (result.carb_g_per_kg_low, result.carb_g_per_kg_high) == (8.0, 12.0)
    assert (result.carb_g_per_day_low, result.carb_g_per_day_high) == (560.0, 840.0)
    assert result.window_hours == 48
    assert (result.race_carb_g_per_h_low, result.race_carb_g_per_h_high) == (60.0, 90.0)


def test_mid_event_loads_6_to_8_g_per_kg_over_24h():
    result = carb_loading_targets(60.0, 75.0)
    assert result.loading_required is True
    assert (result.carb_g_per_kg_low, result.carb_g_per_kg_high) == (6.0, 8.0)
    assert (result.carb_g_per_day_low, result.carb_g_per_day_high) == (360.0, 480.0)
    assert result.window_hours == 24
    assert (result.race_carb_g_per_h_low, result.race_carb_g_per_h_high) == (30.0, 60.0)


def test_short_event_needs_no_loading_and_no_race_fuel():
    result = carb_loading_targets(80.0, 45.0)
    assert result.loading_required is False
    assert result.carb_g_per_kg_low is None
    assert result.carb_g_per_day_high is None
    assert result.window_hours is None
    assert result.race_carb_g_per_h_low is None


def test_carb_guards_reject_out_of_range_inputs():
    with pytest.raises(ValueError, match="body_mass_kg"):
        carb_loading_targets(20.0, 180.0)
    with pytest.raises(ValueError, match="event_duration_min"):
        carb_loading_targets(70.0, 2.0)
    with pytest.raises(ValueError, match="event_duration_min"):
        carb_loading_targets(70.0, 2000.0)


def test_attempts_goal_within_range_becomes_third():
    result = select_attempts(200.0, 205.0)
    assert result.opener_kg == 182.5  # 0.91 * 200 = 182 -> 182.5
    assert result.second_kg == 192.5  # 0.96 * 200 = 192 -> 192.5
    assert result.third_kg == 205.0
    assert result.flags == ()


def test_attempts_goal_beyond_e1rm_is_flagged_and_capped():
    result = select_attempts(200.0, 215.0)  # > 105% of e1RM
    assert result.third_kg == 202.5  # 1.01 * 200 = 202 -> 202.5
    assert "goal_beyond_e1rm" in result.flags


def test_attempts_stay_strictly_increasing_after_rounding():
    result = select_attempts(52.0, 50.0)
    assert result.opener_kg < result.second_kg < result.third_kg


def test_attempts_guards():
    with pytest.raises(ValueError, match="e1rm_kg"):
        select_attempts(10.0, 50.0)
    with pytest.raises(ValueError, match="goal_kg"):
        select_attempts(200.0, 0.0)
    with pytest.raises(ValueError, match="rounding_kg"):
        select_attempts(200.0, 205.0, rounding_kg=0.0)


def test_even_pacing_splits_evenly_and_lands_on_target():
    splits = pacing_plan(10000.0, 2400.0, segment_m=1000.0, strategy="even")
    assert len(splits) == 10
    assert all(s.target_pace_s_per_km == 240.0 for s in splits)
    assert splits[-1].cumulative_time_s == pytest.approx(2400.0, abs=1.0)


def test_negative_split_first_half_slower_lands_on_target():
    splits = pacing_plan(10000.0, 2400.0, segment_m=1000.0, strategy="negative")
    assert splits[0].target_pace_s_per_km > splits[-1].target_pace_s_per_km
    assert splits[0].target_pace_s_per_km == pytest.approx(242.4, abs=0.01)
    assert splits[-1].cumulative_time_s == pytest.approx(2400.0, abs=1.0)


def test_pacing_remainder_becomes_last_short_segment():
    splits = pacing_plan(10500.0, 2520.0, segment_m=1000.0, strategy="even")
    assert len(splits) == 11
    assert splits[-1].distance_m == pytest.approx(500.0)


def test_pacing_oversized_segment_yields_single_split():
    splits = pacing_plan(5000.0, 1200.0, segment_m=8000.0, strategy="even")
    assert len(splits) == 1
    assert splits[0].distance_m == pytest.approx(5000.0)


def test_pacing_guards():
    with pytest.raises(ValueError, match="distance_m"):
        pacing_plan(0.0, 2400.0)
    with pytest.raises(ValueError, match="target_time_s"):
        pacing_plan(10000.0, -5.0)
    with pytest.raises(ValueError, match="strategy"):
        pacing_plan(10000.0, 2400.0, strategy="wild")


def test_window_scales_with_priority():
    assert protocol_window_days(10, "A") == 10
    assert protocol_window_days(4, "A") == 7  # floor
    assert protocol_window_days(25, "A") == 21  # ceiling
    assert protocol_window_days(5, "B") == 5
    assert protocol_window_days(2, "B") == 3  # floor
    assert protocol_window_days(12, "B") == 10  # ceiling
    assert protocol_window_days(10, "C") == 0  # never auto-surfaced


def test_window_guards():
    with pytest.raises(ValueError, match="taper_days"):
        protocol_window_days(-1, "A")
    with pytest.raises(ValueError, match="priority"):
        protocol_window_days(10, "X")
