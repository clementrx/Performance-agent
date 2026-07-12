"""In-process test for the check_week_sequencing MCP tool."""

import pytest


def _block(exercise: str) -> dict:
    return {
        "exercise": exercise,
        "priority": "primary",
        "sets": 3,
        "reps": "5",
        "rir": 2.0,
        "rest_s": 120,
        "progression_rule": "double_progression",
    }


def _session(session_id: str, weekday: int, patterns: list[str]) -> dict:
    return {
        "id": session_id,
        "weekday": weekday,
        "qualities": ["strength_heavy"],
        "patterns": patterns,
        "est_minutes": 60,
        "purpose": "work",
        "blocks": [_block("Back Squat")],
        "fallbacks": {
            "low_readiness": "RPE 7",
            "short_on_time": "A only",
            "missing_equipment": "goblet",
        },
    }


def _week(sessions: list[dict]) -> dict:
    return {
        "week_index": 1,
        "volume_factor": 1.0,
        "intensity_factor": 0.9,
        "sessions": sessions,
    }


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_flags_a_same_pattern_clash(client):
    week = _week([_session("mon", 0, ["squat"]), _session("tue", 1, ["squat"])])
    result = await client.call_tool("check_week_sequencing", {"week": week})
    payload = result.structuredContent
    assert payload["block_count"] == 1
    assert payload["warn_count"] == 0
    assert payload["violations"][0]["rule_id"] == "R1"
    assert payload["violations"][0]["session_ids"] == ["mon", "tue"]


@pytest.mark.anyio
async def test_clean_week_reports_no_violations(client):
    week = _week([_session("mon", 0, ["squat"]), _session("thu", 3, ["push_h"])])
    result = await client.call_tool("check_week_sequencing", {"week": week})
    payload = result.structuredContent
    assert payload["violations"] == []
    assert payload["block_count"] == 0
