"""Pure pre-competition math: carb loading, attempts, pacing, window."""

import pytest

from performance_agent.engine.competition import carb_loading_targets


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
