"""Errors must reach the agent as readable tool errors, never as crashes."""

import pytest


def error_text(result) -> str:
    assert result.isError
    return result.content[0].text


@pytest.mark.anyio
async def test_impossible_weeks_surfaces_engine_message(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {"current_time_s": 3300, "target_time_s": 2100, "weeks": 0, "training_age": "beginner"},
    )
    assert "positive" in error_text(result)


@pytest.mark.anyio
async def test_unknown_training_age_lists_valid_values(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {"current_time_s": 3300, "target_time_s": 2100, "weeks": 12, "training_age": "elite"},
    )
    text = error_text(result)
    assert "beginner" in text
    assert "intermediate" in text
    assert "advanced" in text


@pytest.mark.anyio
async def test_unknown_formula_lists_valid_values(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 5, "formula": "mcglothin"}
    )
    text = error_text(result)
    assert "brzycki" in text
    assert "epley" in text
    assert "lombardi" in text
    assert "wathan" in text


@pytest.mark.anyio
async def test_out_of_band_distance_is_rejected_with_the_band(client):
    result = await client.call_tool(
        "predict_race_time",
        {"known_distance_m": 5000, "known_time_s": 1200, "target_distance_m": 100},
    )
    text = error_text(result)
    assert "1500" in text
    assert "42195" in text


@pytest.mark.anyio
async def test_negative_load_is_rejected(client):
    result = await client.call_tool("compute_weekly_loads", {"daily_loads": [100.0, -5.0]})
    assert "negative" in error_text(result)


@pytest.mark.anyio
async def test_out_of_range_rpe_is_rejected(client):
    result = await client.call_tool("compute_session_load", {"rpe": 11, "duration_min": 30})
    text = error_text(result)
    assert "rpe" in text
    assert "10" in text


@pytest.mark.anyio
async def test_taper_longer_than_block_is_rejected(client):
    result = await client.call_tool(
        "build_periodization_waves",
        {"total_weeks": 8, "deload_every": 4, "taper_weeks": 8},
    )
    assert "taper_weeks" in error_text(result)


@pytest.mark.anyio
async def test_out_of_range_reps_is_rejected(client):
    result = await client.call_tool("estimate_1rm", {"load_kg": 100, "reps": 13})
    text = error_text(result)
    assert "reps" in text
    assert "12" in text


@pytest.mark.anyio
async def test_out_of_range_percentage_is_rejected(client):
    result = await client.call_tool("prescribe_load", {"one_rm_kg": 150, "percentage": 1.5})
    text = error_text(result)
    assert "percentage" in text
    assert "1.3" in text


@pytest.mark.anyio
async def test_non_positive_duration_is_rejected(client):
    result = await client.call_tool("compute_session_load", {"rpe": 7, "duration_min": 0})
    text = error_text(result)
    assert "duration" in text
    assert "positive" in text
