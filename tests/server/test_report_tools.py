"""In-process tests for the report MCP tool (isolated athlete dir per test)."""

import shutil

import pytest

from tests.program_plans import plan_dict

HAS_TYPST = shutil.which("typst") is not None


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


async def _seed(client):
    await client.call_tool("write_profile", {"profile": {"locale": "en"}})
    await client.call_tool(
        "upsert_goal", {"goal": {"id": "sub-45-10k", "statement": "10K under 45:00"}}
    )
    await client.call_tool("save_program", {"plan": plan_dict(goal_id="sub-45-10k")})


@pytest.mark.anyio
async def test_fabricated_citation_aborts_render(client):
    await client.call_tool("write_profile", {"profile": {"locale": "en"}})
    await client.call_tool("upsert_goal", {"goal": {"id": "g", "statement": "goal"}})
    await client.call_tool(
        "save_program",
        {"plan": plan_dict(goal_id="g", note="Proven (doi:10.9999/fake).")},
    )
    result = await client.call_tool("render_report", {"mode": "expert"})
    assert result.isError
    assert "10.9999/fake" in result.content[0].text


@pytest.mark.anyio
async def test_render_before_any_program_is_readable_error(client):
    result = await client.call_tool("render_report", {})
    assert result.isError
    assert "save_program" in result.content[0].text


@pytest.mark.anyio
@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
async def test_render_report_produces_pdf(client, athlete_home):
    await _seed(client)
    result = await client.call_tool("render_report", {"mode": "coach"})
    assert not result.isError
    report = result.structuredContent
    assert report["version"] == 1
    assert report["mode"] == "coach"
    assert report["locale"] == "en"
    assert report["pdf_path"].endswith("program-v1-coach-en.pdf")
    assert (athlete_home / "reports" / "program-v1-coach-en.pdf").exists()


@pytest.mark.anyio
async def test_report_tool_is_listed(client):
    listed = await client.list_tools()
    assert "render_report" in {tool.name for tool in listed.tools}
