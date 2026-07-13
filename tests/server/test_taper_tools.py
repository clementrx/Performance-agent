"""In-process tests for the taper-response MCP tools."""

from datetime import date, datetime, timedelta

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    CalendarEvent,
    KpiResult,
    KpiSpec,
    PerformanceModel,
    Provenance,
    QualityRequirement,
    SessionEntry,
)

ORIGIN = date(2026, 1, 1)


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def _seed_two_tapers(base_dir):
    for day in range(120):
        tapering = 33 <= day < 40 or 83 <= day < 90
        at = datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=day)
        store.append_session(
            base_dir,
            SessionEntry(
                performed_at=at, rpe=3 if tapering else 7, duration_min=20 if tapering else 60
            ),
        )
    store.save_performance_model(
        base_dir,
        PerformanceModel(
            discipline="pl",
            event="total",
            qualities=[
                QualityRequirement(
                    quality="max_strength", weight=1.0, provenance=Provenance(kind="prior")
                )
            ],
            kpis=[
                KpiSpec(
                    id="total",
                    name="Total",
                    quality="max_strength",
                    protocol="meet",
                    unit="kg",
                    higher_is_better=True,
                )
            ],
        ),
    )
    for i, day in enumerate((40, 90)):
        store.upsert_calendar_event(
            base_dir,
            CalendarEvent(
                id=f"c{i}",
                date=ORIGIN + timedelta(days=day),
                kind="competition",
                priority="A",
                label=f"Meet{i}",
            ),
        )
        store.append_kpi_result(
            base_dir,
            KpiResult(
                date=ORIGIN + timedelta(days=day),
                kpi_id="total",
                protocol="meet",
                value=500.0 + 20.0 * i,
                unit="kg",
            ),
        )


@pytest.mark.anyio
async def test_recommend_taper_population_without_history(client):
    result = await client.call_tool(
        "recommend_taper",
        {"buildup_weeks": 12, "modality": "endurance", "event_priority": "A"},
    )
    assert not result.isError
    body = result.structuredContent
    assert body["basis"] == "population"
    assert 4 <= body["taper_days"] <= 14


@pytest.mark.anyio
async def test_recommend_taper_individual_with_history(client, athlete_home):
    _seed_two_tapers(athlete_home)
    result = await client.call_tool(
        "recommend_taper",
        {"buildup_weeks": 8, "modality": "strength", "event_priority": "A"},
    )
    assert not result.isError
    body = result.structuredContent
    assert body["basis"] == "individual"
    assert body["taper_days"] == 7


@pytest.mark.anyio
async def test_fit_taper_response_tool(client, athlete_home):
    _seed_two_tapers(athlete_home)
    result = await client.call_tool("fit_taper_response", {})
    assert not result.isError
    body = result.structuredContent
    assert body["n_detected"] == 2
    assert body["n_with_outcome"] == 2
