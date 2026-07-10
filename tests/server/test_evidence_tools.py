"""In-process tests for the evidence MCP tools (real packaged corpus)."""

import pytest


@pytest.mark.anyio
async def test_search_evidence_returns_graded_hits(client):
    result = await client.call_tool("search_evidence", {"query": "strength training"})
    assert not result.isError
    hits = result.structuredContent["hits"]
    assert hits, "the live-verified starter corpus must match a strength query"
    first = hits[0]
    assert set(first) >= {
        "id",
        "title",
        "year",
        "study_type",
        "evidence_level",
        "stars",
        "conclusions",
        "citation",
    }
    assert first["stars"].count("★") + first["stars"].count("☆") == 5


@pytest.mark.anyio
async def test_search_evidence_empty_result_is_not_an_error(client):
    result = await client.call_tool("search_evidence", {"query": "quantum chromodynamics"})
    assert not result.isError
    assert result.structuredContent["hits"] == []


@pytest.mark.anyio
async def test_get_citation_by_id(client):
    search = await client.call_tool("search_evidence", {"query": "strength training"})
    entry_id = search.structuredContent["hits"][0]["id"]
    result = await client.call_tool("get_citation", {"evidence_id": entry_id})
    assert not result.isError
    assert result.structuredContent["citation"]
    assert result.structuredContent["stars"]


@pytest.mark.anyio
async def test_get_citation_unknown_id_is_readable_error(client):
    result = await client.call_tool("get_citation", {"evidence_id": "no-such-entry"})
    assert result.isError
    assert "search_evidence" in result.content[0].text


@pytest.mark.anyio
async def test_check_citations_flags_fabrications(client):
    result = await client.call_tool(
        "check_citations", {"text": "Proven by science (doi:10.9999/fabricated)."}
    )
    assert not result.isError
    report = result.structuredContent
    assert report["ok"] is False
    assert "10.9999/fabricated" in report["unknown_references"]


@pytest.mark.anyio
async def test_check_citations_passes_clean_text(client):
    result = await client.call_tool("check_citations", {"text": "Squat 5x5 at 80%."})
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["unknown_references"] == []


@pytest.mark.anyio
async def test_evidence_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {"search_evidence", "get_citation", "check_citations"} <= names
