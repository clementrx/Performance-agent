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
        "estimate_1rm", {"load_kg": 100, "reps": 5, "formula": "lombardi"}
    )
    text = error_text(result)
    assert "brzycki" in text
    assert "epley" in text


@pytest.mark.anyio
async def test_out_of_band_distance_is_rejected_with_the_band(client):
    result = await client.call_tool(
        "predict_race_time",
        {"known_distance_m": 5000, "known_time_s": 1200, "target_distance_m": 100},
    )
    assert "distance" in error_text(result)


@pytest.mark.anyio
async def test_negative_load_is_rejected(client):
    result = await client.call_tool("compute_weekly_loads", {"daily_loads": [100.0, -5.0]})
    assert "negative" in error_text(result)
