"""In-process tests for the exercise-ontology MCP tools."""

import pytest


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
