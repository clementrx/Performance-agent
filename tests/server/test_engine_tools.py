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
