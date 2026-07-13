"""In-process tests for the response-profile MCP tools and recalibration path."""

from datetime import datetime, timedelta

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import ExercisePerformed, Goal, SessionEntry, SetPerformed
from tests.program_plans import FIXTURE_TODAY, minimal_plan

ORIGIN = FIXTURE_TODAY


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def _seed(tmp_path, weeks: int) -> None:
    store.save_program(tmp_path, minimal_plan(goal_id="squat-160"), today=ORIGIN)
    store.upsert_goal(tmp_path, Goal(id="squat-160", statement="Back Squat 160 kg"))
    for week in range(weeks):
        at = datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=week * 7)
        store.append_session(
            tmp_path,
            SessionEntry(
                performed_at=at,
                kind="strength_heavy",
                session_plan_id="w01-s1-lower-heavy",
                exercises=[
                    ExercisePerformed(
                        name="Back Squat",
                        sets=[SetPerformed(reps=5, load_kg=120.0 * (1 + 0.005 * week))],
                    )
                ],
            ),
        )


@pytest.mark.anyio
async def test_compute_save_read_round_trip(client, athlete_home):
    _seed(athlete_home, weeks=8)
    computed = await client.call_tool("compute_response_profile", {})
    assert not computed.isError
    assert computed.structuredContent["per_goal_measured_rate"]["value"] == pytest.approx(
        0.005, abs=5e-4
    )
    saved = await client.call_tool("save_response_profile", {"profile": computed.structuredContent})
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    read = await client.call_tool("read_response_profile", {})
    assert not read.isError
    assert read.structuredContent["goal_id"] == "squat-160"


@pytest.mark.anyio
async def test_read_before_save_errors(client):
    result = await client.call_tool("read_response_profile", {})
    assert result.isError
    assert "no response profile" in result.content[0].text


@pytest.mark.anyio
async def test_compute_without_program_errors(client):
    result = await client.call_tool("compute_response_profile", {})
    assert result.isError
    assert "no structured program" in result.content[0].text


@pytest.mark.anyio
async def test_compare_prescribed_actual_tool(client, athlete_home):
    _seed(athlete_home, weeks=1)  # one logged session matches the one planned session
    result = await client.call_tool("compare_prescribed_actual", {})
    assert not result.isError
    body = result.structuredContent
    assert body["extra_unplanned"] == 0
    matched = {s["session_id"]: s for s in body["sessions"]}
    # One set logged against a 7-set prescription -> matched by id, partial.
    assert matched["w01-s1-lower-heavy"]["status"] == "partial"
    assert matched["w01-s1-lower-heavy"]["matched_by"] == "id"


@pytest.mark.anyio
async def test_assess_strength_goal_reports_both_probabilities(client):
    result = await client.call_tool(
        "assess_strength_goal",
        {
            "current_one_rm_kg": 100.0,
            "target_one_rm_kg": 110.0,
            "weeks": 20,
            "training_age": "intermediate",
            "measured_weekly_rate": 0.005,
            "measured_n_weeks": 8,
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["probability"] == pytest.approx(0.2166, abs=0.001)  # population prior unchanged
    assert verdict["measured"] is not None
    assert verdict["measured"]["measured_weekly_rate"] == pytest.approx(0.005)
    assert verdict["measured"]["small_n"] is False


@pytest.mark.anyio
async def test_assess_strength_goal_measured_absent_by_default(client):
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
    assert result.structuredContent["measured"] is None


@pytest.mark.anyio
async def test_weekly_set_targets_reduce_adjustment(client):
    result = await client.call_tool(
        "weekly_set_targets_for",
        {"training_age": "intermediate", "tolerance_adjustment": "reduce"},
    )
    assert not result.isError
    targets = result.structuredContent
    assert targets["minimum_effective_sets"] == 8
    assert targets["optimal_low_sets"] == 8
    assert targets["optimal_high_sets"] == 10
