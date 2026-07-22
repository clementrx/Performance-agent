"""In-process tests for the exercise-ontology MCP tools."""

import pytest

from tests.exercises.test_dataset import write_fixture_dataset


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_list_exercises_filter(client):
    result = await client.call_tool(
        "list_exercises",
        {"quality": "reactive_strength", "equipment": ["bodyweight"]},
    )
    assert not result.isError
    entries = result.structuredContent["result"]
    assert entries
    assert all("reactive_strength" in e["qualities_trained"] for e in entries)


@pytest.mark.anyio
async def test_propose_and_relist(client):
    definition = {
        "id": "sledge-throw",
        "name": "Sledgehammer Throw",
        "patterns": ["throw"],
        "force_vector": "rotational",
        "contraction_regime": "ballistic",
        "chain": "open",
        "equipment": ["medicine_ball"],
        "specificity_level": "specific",
        "qualities_trained": {"explosive_strength": 0.7},
        "skill_complexity": 2,
        "provenance": {"kind": "prior"},
    }
    proposed = await client.call_tool("propose_exercise", {"definition": definition})
    assert not proposed.isError
    assert proposed.structuredContent["provenance_kind"] == "judgment"
    listed = await client.call_tool("list_exercises", {"pattern": "throw"})
    ids = {e["id"] for e in listed.structuredContent["result"]}
    assert "sledge-throw" in ids


@pytest.mark.anyio
async def test_score_exercises_ranks(client):
    result = await client.call_tool(
        "score_exercises",
        {
            "quality_targets": {"reactive_strength": 1.0},
            "phase": "realization",
            "pattern": "jump",
            "top_k": 5,
        },
    )
    assert not result.isError
    scored = result.structuredContent["result"]
    assert 1 <= len(scored) <= 5
    scores = [s["score"] for s in scored]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_check_program_specificity_needs_program(client):
    result = await client.call_tool("check_program_specificity", {})
    assert result.isError
    assert "no structured program" in result.content[0].text


@pytest.mark.anyio
async def test_propose_rejects_bad_equipment(client):
    definition = {
        "id": "bad-ex",
        "name": "Bad Exercise",
        "patterns": ["squat"],
        "force_vector": "axial",
        "contraction_regime": "concentric_dominant",
        "chain": "closed",
        "equipment": ["jetpack"],
        "specificity_level": "general",
        "qualities_trained": {"max_strength": 0.5},
        "skill_complexity": 1,
        "provenance": {"kind": "prior"},
    }
    result = await client.call_tool("propose_exercise", {"definition": definition})
    assert result.isError


@pytest.mark.anyio
async def test_search_exercise_media_returns_candidates(client, monkeypatch, tmp_path):
    dataset_dir = write_fixture_dataset(tmp_path / "ds")
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(dataset_dir))
    result = await client.call_tool(
        "search_exercise_media", {"query": "squat", "equipment": "barbell"}
    )
    assert not result.isError
    payload = result.structuredContent
    assert payload["dataset_available"] is True
    assert payload["candidates"][0]["media_id"] == "0043"
    assert payload["candidates"][0]["target"] == "glutes"


@pytest.mark.anyio
async def test_search_exercise_media_without_dataset(client, monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(tmp_path / "missing"))
    result = await client.call_tool("search_exercise_media", {"query": "squat"})
    assert not result.isError
    payload = result.structuredContent
    assert payload["dataset_available"] is False
    assert payload["candidates"] == []
    assert payload["hint"]


@pytest.mark.anyio
async def test_search_exercise_media_rejects_blank_query(client, monkeypatch, tmp_path):
    dataset_dir = write_fixture_dataset(tmp_path / "ds")
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(dataset_dir))
    result = await client.call_tool("search_exercise_media", {"query": "   "})
    assert result.isError
    assert "query" in result.content[0].text
