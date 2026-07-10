import pytest


@pytest.mark.anyio
async def test_assess_endurance_goal_returns_honest_verdict(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {
            "current_time_s": 3300,
            "target_time_s": 2100,
            "weeks": 12,
            "training_age": "beginner",
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["probability"] < 0.05
    assert verdict["improvement_needed"] == pytest.approx(0.3636, abs=0.001)
    assert verdict["required_weekly_rate"] == pytest.approx(0.0303, abs=0.001)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.010)


@pytest.mark.anyio
async def test_predict_race_time_includes_pace(client):
    result = await client.call_tool(
        "predict_race_time",
        {"known_distance_m": 5000, "known_time_s": 1200, "target_distance_m": 10000},
    )
    assert not result.isError
    prediction = result.structuredContent
    assert prediction["predicted_time_s"] == pytest.approx(2502, abs=2)
    assert prediction["pace_s_per_km"] == pytest.approx(250.2, abs=0.5)


@pytest.mark.anyio
async def test_compute_pace(client):
    result = await client.call_tool("compute_pace", {"distance_m": 10000, "time_s": 2700})
    assert not result.isError
    assert result.structuredContent["pace_s_per_km"] == pytest.approx(270.0)


@pytest.mark.anyio
async def test_estimate_1rm_default_epley(client):
    result = await client.call_tool("estimate_1rm", {"load_kg": 100, "reps": 5})
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(116.67, abs=0.01)
    assert result.structuredContent["formula"] == "epley"


@pytest.mark.anyio
async def test_estimate_1rm_brzycki(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 5, "formula": "brzycki"}
    )
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(112.5, abs=0.01)


@pytest.mark.anyio
async def test_prescribe_load(client):
    result = await client.call_tool("prescribe_load", {"one_rm_kg": 150, "percentage": 0.8})
    assert not result.isError
    assert result.structuredContent["load_kg"] == pytest.approx(120.0)
