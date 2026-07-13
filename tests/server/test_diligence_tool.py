"""In-process test for the list_due_actions MCP tool."""

from datetime import date, timedelta

import pytest

from performance_agent.memory.schemas import Goal
from performance_agent.memory.store import upsert_goal


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_empty_athlete_has_nothing_due(client):
    result = await client.call_tool("list_due_actions", {})
    assert result.structuredContent["result"] == []


@pytest.mark.anyio
async def test_goal_deadline_without_events_is_surfaced(client, athlete_home):
    upsert_goal(
        athlete_home,
        Goal(id="squat-160", statement="Squat 160kg", deadline=date.today() + timedelta(days=120)),
    )
    result = await client.call_tool("list_due_actions", {})
    actions = result.structuredContent["result"]
    kinds = {a["kind"] for a in actions}
    assert "calendar_incomplete" in kinds
    incomplete = next(a for a in actions if a["kind"] == "calendar_incomplete")
    assert incomplete["severity"] == "medium"
    assert incomplete["message_key"] == "calendar_incomplete"
