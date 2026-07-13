"""In-process tests for the multi-year planning MCP tools."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.performance_models import load_seed_models
from performance_agent.memory.schemas import CalendarEvent


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def _seed(base_dir):
    store.save_performance_model(base_dir, load_seed_models()["sprint-100m"])
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="games", date=date(2028, 7, 1), kind="competition", priority="A", label="Games"
        ),
    )


@pytest.mark.anyio
async def test_build_and_save_macro_plan(client, athlete_home):
    _seed(athlete_home)
    built = await client.call_tool("build_macro_plan", {"horizon_years": 2})
    assert not built.isError
    assert built.structuredContent["horizon_years"] == 2
    saved = await client.call_tool("save_macro_plan", {"plan": built.structuredContent})
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    read = await client.call_tool("read_macro_plan", {})
    assert read.structuredContent["major_event_id"] == "games"


@pytest.mark.anyio
async def test_build_macro_plan_without_model_errors(client):
    result = await client.call_tool("build_macro_plan", {"horizon_years": 2})
    assert result.isError


@pytest.mark.anyio
async def test_read_macro_plan_before_save_errors(client):
    result = await client.call_tool("read_macro_plan", {})
    assert result.isError
    assert "no macro plan" in result.content[0].text


@pytest.mark.anyio
async def test_check_residuals_needs_program(client):
    result = await client.call_tool("check_residuals", {})
    assert result.isError
    assert "no structured program" in result.content[0].text
