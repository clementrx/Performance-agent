"""In-process tests for the import_activity_file MCP tool."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "importers" / "fixtures"


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_import_activity_proposes_a_session(client):
    result = await client.call_tool(
        "import_activity_file", {"path": str(FIXTURES / "activity.csv")}
    )
    assert not result.isError
    proposal = result.structuredContent
    assert proposal["kind"] == "activity"
    assert proposal["proposed_session"]["source"] == "external"
    assert proposal["match"]["source"] == "external"
    assert proposal["summary"]["distance_m"] == pytest.approx(8000.0)
    assert "Confirm" in proposal["confirm"]
    assert proposal["proposed_session"] is not None


@pytest.mark.anyio
async def test_import_matches_active_program(client):
    await client.call_tool(
        "save_program",
        {
            "plan": _endurance_plan_dict(),
        },
    )
    result = await client.call_tool(
        "import_activity_file", {"path": str(FIXTURES / "activity.csv")}
    )
    proposal = result.structuredContent
    assert proposal["match"]["source"] == "programmed"
    assert proposal["match"]["session_plan_id"] == "w01-s2-long-run"


@pytest.mark.anyio
async def test_import_hrv_csv_returns_readings(client):
    result = await client.call_tool("import_activity_file", {"path": str(FIXTURES / "hrv.csv")})
    proposal = result.structuredContent
    assert proposal["kind"] == "hrv"
    assert proposal["proposed_session"] is None
    assert len(proposal["proposed_readiness"]) == 3
    assert proposal["proposed_readiness"][0]["hrv_ms"] == pytest.approx(62.5)


@pytest.mark.anyio
async def test_import_ride_surfaces_power_and_splits(client):
    result = await client.call_tool("import_activity_file", {"path": str(FIXTURES / "ride.tcx")})
    proposal = result.structuredContent
    assert proposal["kind"] == "activity"
    assert proposal["summary"]["avg_watts"] == pytest.approx(220.0)
    assert proposal["summary"]["avg_cadence"] == pytest.approx(90.0)
    assert len(proposal["summary"]["splits"]) == 2


@pytest.mark.anyio
async def test_import_vbt_csv_returns_sets(client):
    result = await client.call_tool("import_activity_file", {"path": str(FIXTURES / "vbt.csv")})
    proposal = result.structuredContent
    assert proposal["kind"] == "vbt"
    assert proposal["needs_srpe"] is True
    sets = proposal["proposed_session"]["vbt_sets"]
    assert len(sets) == 3
    assert sets[0]["mean_velocity"] == pytest.approx(0.75)


@pytest.mark.anyio
async def test_malformed_file_returns_a_readable_error(client):
    result = await client.call_tool(
        "import_activity_file", {"path": str(FIXTURES / "malformed.fit")}
    )
    assert result.isError
    assert "not a readable FIT file" in result.content[0].text


def _endurance_plan_dict() -> dict:
    return {
        "version": 1,
        "goal_id": "10k-sub45",
        "created_on": "2026-06-01",
        "mesocycles": [
            {
                "index": 1,
                "phase": "accumulation",
                "weeks": [
                    {
                        "week_index": 1,
                        "volume_factor": 1.0,
                        "intensity_factor": 1.0,
                        "sessions": [
                            {
                                "id": "w01-s2-long-run",
                                "qualities": ["endurance_long"],
                                "patterns": ["run"],
                                "est_minutes": 45,
                                "purpose": "Aerobic base",
                                "blocks": [
                                    {
                                        "exercise": "Easy run",
                                        "priority": "primary",
                                        "warmup": "none",
                                        "sets": 1,
                                        "distance_m": 8000.0,
                                        "progression_rule": "add 5% distance weekly",
                                    }
                                ],
                                "fallbacks": {
                                    "low_readiness": "cut to 30 min easy",
                                    "short_on_time": "30 min easy",
                                    "missing_equipment": "treadmill ok",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
