"""In-process tests for the day-of autoregulation MCP tools."""

import pytest

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
