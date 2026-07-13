"""In-process tests for the PerformanceModel MCP tools."""

import pytest


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def _model_payload() -> dict:
    return {
        "discipline": "athletics",
        "event": "100m sprint",
        "qualities": [
            {
                "quality": "reactive_strength",
                "weight": 0.6,
                "provenance": {"kind": "prior"},
            },
            {
                "quality": "max_strength",
                "weight": 0.4,
                "provenance": {"kind": "cited", "cite_ids": ["suchomel-2016"]},
            },
        ],
        "kpis": [
            {
                "id": "squat-1rm",
                "name": "Back squat 1RM",
                "quality": "max_strength",
                "protocol": "one-rep-max after warm-up ramp",
                "test_protocol": "one_rm_test",
                "unit": "kg",
                "benchmarks": [{"level": "elite", "value": 180.0, "provenance": {"kind": "prior"}}],
            }
        ],
    }


@pytest.mark.anyio
async def test_save_then_read_round_trip(client):
    saved = await client.call_tool("save_performance_model", {"model": _model_payload()})
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    read = await client.call_tool("read_performance_model", {})
    assert not read.isError
    body = read.structuredContent
    assert body["event"] == "100m sprint"
    weights = {q["quality"]: q["weight"] for q in body["qualities"]}
    assert weights["reactive_strength"] == pytest.approx(0.6)
    assert weights["max_strength"] == pytest.approx(0.4)


@pytest.mark.anyio
async def test_read_before_save_errors(client):
    result = await client.call_tool("read_performance_model", {})
    assert result.isError
    assert "no performance model" in result.content[0].text


@pytest.mark.anyio
async def test_second_version_without_reason_errors(client):
    await client.call_tool("save_performance_model", {"model": _model_payload()})
    result = await client.call_tool("save_performance_model", {"model": _model_payload()})
    assert result.isError
    assert "reason" in result.content[0].text


@pytest.mark.anyio
async def test_invalid_model_cited_without_ids_errors(client):
    payload = _model_payload()
    payload["qualities"][1]["provenance"] = {"kind": "cited"}
    result = await client.call_tool("save_performance_model", {"model": payload})
    assert result.isError
    assert "cited provenance requires" in result.content[0].text


@pytest.mark.anyio
async def test_invalid_model_unknown_quality_errors(client):
    payload = _model_payload()
    payload["qualities"][0]["quality"] = "explosiveness"
    result = await client.call_tool("save_performance_model", {"model": payload})
    assert result.isError
