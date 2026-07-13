"""In-process tests for the day-of autoregulation MCP tools."""

from datetime import datetime

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import SessionEntry, VbtSet
from tests.program_plans import plan_dict


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


async def _save_program(client):
    result = await client.call_tool("save_program", {"plan": plan_dict()})
    assert not result.isError


@pytest.mark.anyio
async def test_adjust_session_amber_reduces(client):
    await _save_program(client)
    result = await client.call_tool(
        "adjust_session", {"session_plan_id": "w01-s1-lower-heavy", "band": "amber"}
    )
    assert not result.isError
    payload = result.structuredContent
    assert payload["kind"] == "reduced"
    assert payload["deltas_summary"]


@pytest.mark.anyio
async def test_adjust_session_red_is_recovery(client):
    await _save_program(client)
    result = await client.call_tool(
        "adjust_session", {"session_plan_id": "w01-s1-lower-heavy", "band": "red"}
    )
    payload = result.structuredContent
    assert payload["kind"] == "recovery"
    assert payload["session"]["qualities"] == ["recovery"]


def _log_squat_vbt(base_dir):
    for i, (load, vel) in enumerate([(60, 1.14), (100, 0.9), (140, 0.66), (180, 0.42)]):
        store.append_session(
            base_dir,
            SessionEntry(
                performed_at=datetime(2026, 7, 1 + i, 10, 0),
                vbt_sets=[VbtSet(exercise="Back Squat", load_kg=load, mean_velocity=vel, reps=1)],
            ),
        )


@pytest.mark.anyio
async def test_fit_load_velocity_tool(client, athlete_home):
    _log_squat_vbt(athlete_home)
    result = await client.call_tool("fit_load_velocity", {"exercise": "Back Squat"})
    assert not result.isError
    profile = result.structuredContent
    assert profile["usable"] is True
    assert profile["e1rm_kg"] == pytest.approx(200.0, abs=2.0)


@pytest.mark.anyio
async def test_fit_load_velocity_too_few_sets_errors(client):
    result = await client.call_tool("fit_load_velocity", {"exercise": "Deadlift"})
    assert result.isError
    assert "at least 2 logged VBT sets" in result.content[0].text


@pytest.mark.anyio
async def test_adjust_session_with_velocity_suggestion(client, athlete_home):
    await _save_program(client)
    _log_squat_vbt(athlete_home)
    result = await client.call_tool(
        "adjust_session",
        {
            "session_plan_id": "w01-s1-lower-heavy",
            "band": "green",
            "velocity_exercise": "Back Squat",
            "velocity_load_kg": 100.0,
            "velocity_mean_velocity": 0.78,
        },
    )
    assert not result.isError
    suggestion = result.structuredContent["velocity_suggestion"]
    assert suggestion is not None
    assert suggestion["pct_change"] < 0  # slow warm-up -> back off


@pytest.mark.anyio
async def test_adjust_session_without_velocity_has_null_suggestion(client):
    await _save_program(client)
    result = await client.call_tool(
        "adjust_session", {"session_plan_id": "w01-s1-lower-heavy", "band": "green"}
    )
    assert result.structuredContent["velocity_suggestion"] is None


@pytest.mark.anyio
async def test_adjust_unknown_session_errors(client):
    await _save_program(client)
    result = await client.call_tool(
        "adjust_session", {"session_plan_id": "does-not-exist", "band": "amber"}
    )
    assert result.isError
    assert "does-not-exist" in result.content[0].text


@pytest.mark.anyio
async def test_compress_session_reports_cost(client):
    await _save_program(client)
    result = await client.call_tool(
        "compress_session", {"session_plan_id": "w01-s1-lower-heavy", "available_minutes": 30}
    )
    payload = result.structuredContent
    assert payload["estimated_minutes"] >= 1
    assert payload["session"]["blocks"]


@pytest.mark.anyio
async def test_substitute_exercise_lists_alternatives(client):
    result = await client.call_tool(
        "substitute_exercise",
        {"exercise": "Back Squat", "pattern": "squat", "available_equipment": ["dumbbell"]},
    )
    names = [a["name"] for a in result.structuredContent["alternatives"]]
    assert "Goblet Squat" in names
    assert "Back Squat" not in names


@pytest.mark.anyio
async def test_log_and_read_adjustments_with_escalation(client):
    for _ in range(3):
        logged = await client.call_tool(
            "log_session_adjustment",
            {
                "entry": {
                    "at": "2026-07-13T18:00:00",
                    "session_plan_id": "w01-s1-lower-heavy",
                    "kind": "readiness",
                    "inputs": {"band": "amber"},
                    "deltas_summary": ["Back Squat: rpe 8->7"],
                }
            },
        )
        assert not logged.isError
    history = await client.call_tool("read_session_adjustments", {})
    payload = history.structuredContent
    assert len(payload["adjustments"]) == 3
    # escalation reflects the real-time 14-day window; assert the block is wired
    # (deterministic escalate=True is covered in tests/memory/test_autoregulation.py).
    assert set(payload["escalation"]) == {
        "downgrades",
        "compressions",
        "escalate",
        "window_days",
        "threshold",
    }
