"""In-process tests for the memory MCP tools (isolated athlete dir per test)."""

import pytest


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_read_athlete_on_fresh_directory(client):
    result = await client.call_tool("read_athlete", {})
    assert not result.isError
    snapshot = result.structuredContent
    assert snapshot["profile"]["locale"] == "en"
    assert snapshot["goals"] == []
    assert snapshot["program_version"] is None


@pytest.mark.anyio
async def test_write_profile_then_read_back(client, athlete_home):
    result = await client.call_tool(
        "write_profile",
        {"profile": {"locale": "fr", "sport": "running", "training_age": "intermediate"}},
    )
    assert not result.isError
    assert (athlete_home / "profile.yaml").exists()

    back = await client.call_tool("read_athlete", {})
    assert back.structuredContent["profile"]["locale"] == "fr"
    assert back.structuredContent["profile"]["training_age"] == "intermediate"


@pytest.mark.anyio
async def test_invalid_profile_is_rejected_readably(client):
    result = await client.call_tool("write_profile", {"profile": {"locale": "de"}})
    assert result.isError
    text = result.content[0].text
    assert "en" in text and "fr" in text and "es" in text


@pytest.mark.anyio
async def test_goal_lifecycle(client):
    added = await client.call_tool(
        "upsert_goal",
        {
            "goal": {
                "id": "sub-45-10k",
                "statement": "10K under 45:00",
                "deadline": "2026-10-30",
            }
        },
    )
    assert not added.isError
    assert added.structuredContent["total_goals"] == 1

    snapshot = await client.call_tool("read_athlete", {})
    assert snapshot.structuredContent["goals"][0]["id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_log_session_and_checkin(client):
    logged = await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-08T18:00:00", "rpe": 7, "duration_min": 60}},
    )
    assert not logged.isError
    assert logged.structuredContent["total_sessions"] == 1

    first = await client.call_tool("log_checkin", {"entry": {"at": "2026-06-26T09:00:00"}})
    assert not first.isError
    second = await client.call_tool("log_checkin", {"entry": {"at": "2026-07-10T09:00:00"}})
    assert second.structuredContent["days_since_last"] == 14


@pytest.mark.anyio
async def test_program_versioning_through_tools(client):
    v1 = await client.call_tool(
        "save_program", {"markdown_body": "# Plan\nWeek 1", "goal_id": "sub-45-10k"}
    )
    assert not v1.isError
    assert v1.structuredContent["version"] == 1

    rejected = await client.call_tool(
        "save_program", {"markdown_body": "# Plan v2", "goal_id": "sub-45-10k"}
    )
    assert rejected.isError
    assert "reason" in rejected.content[0].text

    v2 = await client.call_tool(
        "save_program",
        {
            "markdown_body": "# Plan v2",
            "goal_id": "sub-45-10k",
            "reason": "plateau at week 4",
        },
    )
    assert v2.structuredContent["version"] == 2

    latest = await client.call_tool("read_program", {})
    assert latest.structuredContent["version"] == 2
    assert latest.structuredContent["reason"] == "plateau at week 4"
    first_version = await client.call_tool("read_program", {"version": 1})
    assert first_version.structuredContent["body"] == "# Plan\nWeek 1"


@pytest.mark.anyio
async def test_read_program_before_any_save_is_a_readable_error(client):
    result = await client.call_tool("read_program", {})
    assert result.isError
    assert "save_program" in result.content[0].text


@pytest.mark.anyio
async def test_get_time_context_quotes_deltas(client):
    await client.call_tool("log_session", {"entry": {"performed_at": "2026-07-01T18:00:00"}})
    await client.call_tool(
        "upsert_goal",
        {
            "goal": {
                "id": "sub-45-10k",
                "statement": "10K under 45:00",
                "deadline": "2026-10-30",
            }
        },
    )
    result = await client.call_tool("get_time_context", {})
    assert not result.isError
    context = result.structuredContent
    assert context["last_session_on"] == "2026-07-01"
    assert isinstance(context["days_since_last_session"], int)
    assert context["goals"][0]["goal_id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_memory_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {
        "read_athlete",
        "write_profile",
        "upsert_goal",
        "log_session",
        "log_checkin",
        "save_program",
        "read_program",
        "get_time_context",
    } <= names
