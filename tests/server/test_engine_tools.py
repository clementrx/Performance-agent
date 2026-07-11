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
async def test_estimate_1rm_lombardi(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 8, "formula": "lombardi"}
    )
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(123.11, abs=0.01)
    assert result.structuredContent["formula"] == "lombardi"


@pytest.mark.anyio
async def test_estimate_1rm_wathan(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 8, "formula": "wathan"}
    )
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(127.67, abs=0.01)
    assert result.structuredContent["formula"] == "wathan"


@pytest.mark.anyio
async def test_prescribe_load(client):
    result = await client.call_tool("prescribe_load", {"one_rm_kg": 150, "percentage": 0.8})
    assert not result.isError
    assert result.structuredContent["load_kg"] == pytest.approx(120.0)


@pytest.mark.anyio
async def test_compute_session_load(client):
    result = await client.call_tool("compute_session_load", {"rpe": 7, "duration_min": 60})
    assert not result.isError
    assert result.structuredContent["session_load"] == pytest.approx(420.0)


@pytest.mark.anyio
async def test_compute_weekly_loads(client):
    result = await client.call_tool("compute_weekly_loads", {"daily_loads": [100.0] * 10})
    assert not result.isError
    assert result.structuredContent["weekly_totals"] == [700.0, 300.0]


@pytest.mark.anyio
async def test_compute_acwr_with_history(client):
    history = [100.0] * 21 + [150.0] * 7
    result = await client.call_tool("compute_acwr", {"daily_loads": history})
    assert not result.isError
    assert result.structuredContent["acute_chronic_ratio"] == pytest.approx(1.3333, abs=0.001)


@pytest.mark.anyio
async def test_compute_acwr_short_history_is_null_not_error(client):
    result = await client.call_tool("compute_acwr", {"daily_loads": [100.0] * 10})
    assert not result.isError
    assert result.structuredContent["acute_chronic_ratio"] is None


@pytest.mark.anyio
async def test_build_periodization_waves(client):
    result = await client.call_tool(
        "build_periodization_waves",
        {"total_weeks": 8, "deload_every": 4, "taper_weeks": 1},
    )
    assert not result.isError
    weeks = result.structuredContent["weeks"]
    assert len(weeks) == 8
    assert weeks[3]["is_deload"] is True
    assert weeks[3]["volume_factor"] == pytest.approx(0.6)
    assert weeks[7]["is_taper"] is True
    assert weeks[7]["intensity_factor"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_all_engine_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {
        "assess_endurance_goal",
        "predict_race_time",
        "compute_pace",
        "estimate_1rm",
        "prescribe_load",
        "compute_session_load",
        "compute_weekly_loads",
        "compute_acwr",
        "build_periodization_waves",
    } <= names
