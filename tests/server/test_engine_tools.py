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
async def test_assess_strength_goal(client):
    result = await client.call_tool(
        "assess_strength_goal",
        {
            "current_one_rm_kg": 100.0,
            "target_one_rm_kg": 110.0,
            "weeks": 20,
            "training_age": "intermediate",
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["improvement_needed"] == pytest.approx(0.10)
    assert verdict["required_weekly_rate"] == pytest.approx(0.005)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.0035)
    assert verdict["probability"] == pytest.approx(0.2166, abs=0.001)


@pytest.mark.anyio
async def test_assess_hypertrophy_goal(client):
    result = await client.call_tool(
        "assess_hypertrophy_goal",
        {"target_lean_gain_kg": 5.0, "weeks": 26, "training_age": "beginner"},
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["required_weekly_rate"] == pytest.approx(5 / 26)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.23)
    assert verdict["probability"] == pytest.approx(0.6205, abs=0.001)


@pytest.mark.anyio
async def test_assess_bodycomp_goal(client):
    result = await client.call_tool(
        "assess_bodycomp_goal",
        {
            "current_weight_kg": 80.0,
            "current_body_fat_pct": 20.0,
            "target_body_fat_pct": 12.0,
            "weeks": 16,
            "sex": "male",
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["fat_mass_to_lose_kg"] == pytest.approx(7.2727, abs=0.001)
    assert verdict["probability"] == pytest.approx(0.6742, abs=0.001)
    assert verdict["exceeds_safe_rate"] is False


@pytest.mark.anyio
async def test_assess_bodycomp_goal_refuses_sub_healthy_target(client):
    result = await client.call_tool(
        "assess_bodycomp_goal",
        {
            "current_weight_kg": 80.0,
            "current_body_fat_pct": 15.0,
            "target_body_fat_pct": 4.0,
            "weeks": 16,
            "sex": "male",
        },
    )
    assert result.isError
    assert "healthy minimum" in result.content[0].text


@pytest.mark.anyio
async def test_prescribe_reps_load(client):
    result = await client.call_tool(
        "prescribe_reps_load", {"one_rm_kg": 100.0, "reps": 5, "rir": 2}
    )
    assert not result.isError
    prescription = result.structuredContent
    assert prescription["percentage"] == pytest.approx(30 / 37)
    assert prescription["load_kg"] == pytest.approx(100 * 30 / 37)


@pytest.mark.anyio
async def test_weekly_set_targets_for(client):
    result = await client.call_tool("weekly_set_targets_for", {"training_age": "intermediate"})
    assert not result.isError
    targets = result.structuredContent
    assert targets["minimum_effective_sets"] == 8
    assert targets["optimal_low_sets"] == 10
    assert targets["optimal_high_sets"] == 16
    assert targets["maximum_adaptive_sets"] == 20


@pytest.mark.anyio
async def test_progress_double_progression(client):
    result = await client.call_tool(
        "progress_double_progression",
        {
            "reps_achieved": [12, 12, 12],
            "load_kg": 60.0,
            "rep_range_low": 8,
            "rep_range_high": 12,
            "increment_kg": 2.5,
        },
    )
    assert not result.isError
    decision = result.structuredContent
    assert decision["next_load_kg"] == pytest.approx(62.5)
    assert decision["next_target_reps"] == 8
    assert decision["load_increased"] is True


@pytest.mark.anyio
async def test_build_block_cycle(client):
    result = await client.call_tool("build_block_cycle", {"total_weeks": 12})
    assert not result.isError
    weeks = result.structuredContent["weeks"]
    assert len(weeks) == 12
    assert [w["phase"] for w in weeks[:7]] == ["accumulation"] * 6 + ["intensification"]
    assert weeks[0]["volume_factor"] == pytest.approx(1.10)
    assert weeks[0]["intensity_factor"] == pytest.approx(0.85)
    assert weeks[11]["phase"] == "realization"
    assert weeks[11]["intensity_factor"] == pytest.approx(1.10)


@pytest.mark.anyio
async def test_build_undulating_sessions(client):
    result = await client.call_tool("build_undulating_sessions", {"sessions_per_week": 3})
    assert not result.isError
    sessions = result.structuredContent["sessions"]
    assert [s["emphasis"] for s in sessions] == ["heavy", "light", "moderate"]
    assert sessions[0]["intensity_low"] == pytest.approx(0.85)
    assert sessions[0]["intensity_high"] == pytest.approx(0.925)


@pytest.mark.anyio
async def test_build_inseason_maintenance(client):
    result = await client.call_tool("build_inseason_maintenance", {"matches_this_week": 1})
    assert not result.isError
    week = result.structuredContent
    assert week["strength_sessions"] == 2
    assert week["volume_factor"] == pytest.approx(0.50)
    assert week["min_intensity_factor"] == pytest.approx(0.80)


@pytest.mark.anyio
async def test_build_inseason_maintenance_refuses_congested_week(client):
    result = await client.call_tool("build_inseason_maintenance", {"matches_this_week": 3})
    assert result.isError
    assert "rest is the prescription" in result.content[0].text


@pytest.mark.anyio
async def test_build_peaking_block(client):
    result = await client.call_tool("build_peaking_block", {"weeks": 2})
    assert not result.isError
    weeks = result.structuredContent["weeks"]
    assert weeks[0]["volume_factor"] == pytest.approx(0.55)
    assert weeks[0]["is_test_week"] is False
    assert weeks[1]["intensity_factor"] == pytest.approx(1.025)
    assert weeks[1]["is_test_week"] is True


@pytest.mark.anyio
async def test_compute_bmr_tdee(client):
    result = await client.call_tool(
        "compute_bmr_tdee",
        {
            "sex": "male",
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "age_years": 30,
            "activity_factor": 1.55,
        },
    )
    assert not result.isError
    energy = result.structuredContent
    assert energy["bmr_kcal"] == pytest.approx(1780.0)
    assert energy["tdee_kcal"] == pytest.approx(2759.0)


@pytest.mark.anyio
async def test_prescribe_nutrition_targets(client):
    result = await client.call_tool(
        "prescribe_nutrition_targets",
        {
            "tdee_kcal": 2600.0,
            "goal": "cut",
            "weekly_change_pct_bw": 0.0075,
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "sex": "male",
        },
    )
    assert not result.isError
    target = result.structuredContent
    assert target["daily_kcal"] == pytest.approx(1940.0)
    assert target["protein_g_per_day"] == pytest.approx(176.0)
    assert target["weekly_weight_change_kg"] == pytest.approx(-0.6)
    assert target["clamped_to_floor"] is False


@pytest.mark.anyio
async def test_prescribe_nutrition_targets_refuses_underweight_cut(client):
    result = await client.call_tool(
        "prescribe_nutrition_targets",
        {
            "tdee_kcal": 2200.0,
            "goal": "cut",
            "weekly_change_pct_bw": 0.005,
            "weight_kg": 50.0,
            "height_cm": 175.0,
            "sex": "male",
        },
    )
    assert result.isError
    assert "below the healthy minimum" in result.content[0].text


@pytest.mark.anyio
async def test_prescribe_top_set_backoff(client):
    result = await client.call_tool(
        "prescribe_top_set_backoff",
        {"one_rm_kg": 200.0, "top_percentage": 0.9, "backoff_drop": 0.10, "backoff_sets": 3},
    )
    assert not result.isError
    prescription = result.structuredContent
    assert prescription["top_set_load_kg"] == pytest.approx(180.0)
    assert prescription["backoff_load_kg"] == pytest.approx(160.0)
    assert prescription["backoff_sets"] == 3


@pytest.mark.anyio
async def test_prescribe_wave_loading(client):
    result = await client.call_tool(
        "prescribe_wave_loading",
        {
            "one_rm_kg": 100.0,
            "base_percentage": 0.70,
            "step_increment": 0.05,
            "steps_per_wave": 3,
            "waves": 2,
            "inter_wave_increment": 0.025,
        },
    )
    assert not result.isError
    steps = result.structuredContent["steps"]
    assert len(steps) == 6
    assert [s["load_kg"] for s in steps] == pytest.approx([70.0, 75.0, 80.0, 72.5, 77.5, 82.5])
    assert steps[3]["wave"] == 2
    assert steps[3]["step"] == 1


@pytest.mark.anyio
async def test_prescribe_wave_loading_refuses_peak_over_cap(client):
    result = await client.call_tool(
        "prescribe_wave_loading",
        {
            "one_rm_kg": 100.0,
            "base_percentage": 1.0,
            "step_increment": 0.1,
            "steps_per_wave": 5,
            "waves": 4,
            "inter_wave_increment": 0.05,
        },
    )
    assert result.isError
    assert "peak" in result.content[0].text


@pytest.mark.anyio
async def test_convert_rpe_to_rir(client):
    result = await client.call_tool("convert_rpe_to_rir", {"rpe": 8.5})
    assert not result.isError
    assert result.structuredContent["rir"] == pytest.approx(1.5)


@pytest.mark.anyio
async def test_all_engine_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {
        "assess_endurance_goal",
        "assess_strength_goal",
        "assess_hypertrophy_goal",
        "assess_bodycomp_goal",
        "predict_race_time",
        "compute_pace",
        "estimate_1rm",
        "prescribe_load",
        "prescribe_reps_load",
        "weekly_set_targets_for",
        "progress_double_progression",
        "compute_session_load",
        "compute_weekly_loads",
        "compute_acwr",
        "build_periodization_waves",
        "build_block_cycle",
        "build_undulating_sessions",
        "build_inseason_maintenance",
        "build_peaking_block",
        "compute_bmr_tdee",
        "prescribe_nutrition_targets",
        "prescribe_top_set_backoff",
        "prescribe_wave_loading",
        "convert_rpe_to_rir",
        "recommend_taper",
    } <= names


@pytest.mark.anyio
async def test_recommend_taper_tool(client):
    result = await client.call_tool(
        "recommend_taper",
        {"buildup_weeks": 12, "modality": "endurance", "event_priority": "A"},
    )
    assert not result.isError
    assert 4 <= result.structuredContent["taper_days"] <= 14
