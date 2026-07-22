"""Coverage guard: every tool added in Phases 0-8 is registered and exercised.

Seeds a fully-loaded athlete (model, KPIs, VBT sets, program, calendar) and calls
each new MCP tool once, asserting a non-error result. Fails loudly if a new tool is
dropped from the server or breaks on a realistic athlete.
"""

from datetime import date, datetime

import pytest

from performance_agent.memory import store
from performance_agent.memory.performance_models import load_seed_models
from performance_agent.memory.schemas import (
    CalendarEvent,
    ExerciseBlock,
    Fallbacks,
    KpiResult,
    Mesocycle,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    VbtSet,
    WeekPlan,
)

_NEW_TOOLS = {
    "save_performance_model",
    "read_performance_model",
    "log_kpi_result",
    "read_kpi_results",
    "compute_performance_gaps",
    "plan_test_battery",
    "list_exercises",
    "propose_exercise",
    "score_exercises",
    "check_program_specificity",
    "search_exercise_media",
    "fit_load_velocity",
    "fit_banister",
    "recommend_taper",
    "fit_taper_response",
    "build_macro_plan",
    "save_macro_plan",
    "read_macro_plan",
    "check_residuals",
}


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(tmp_path / "no-dataset"))
    return tmp_path


def _seed(base_dir):
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="games", date=date(2028, 7, 1), kind="competition", priority="A", label="Games"
        ),
    )
    store.append_kpi_result(
        base_dir,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="back-squat-rel", protocol="1rm", value=1.7, unit="x bw"
        ),
    )
    for i, (load, vel) in enumerate([(100, 0.9), (140, 0.66), (180, 0.42), (200, 0.3)]):
        store.append_session(
            base_dir,
            SessionEntry(
                performed_at=datetime(2026, 1, 1 + i, 10, 0),
                vbt_sets=[VbtSet(exercise="Back Squat", load_kg=load, mean_velocity=vel, reps=1)],
            ),
        )
    session = SessionPlan(
        id="w01-s1",
        weekday=0,
        qualities=["power"],
        est_minutes=60,
        purpose="test",
        blocks=[
            ExerciseBlock(
                exercise="Back Squat",
                exercise_id="back-squat",
                priority="primary",
                sets=3,
                reps="5",
                rest_s=180,
                progression_rule="x",
            )
        ],
        fallbacks=Fallbacks(low_readiness="a", short_on_time="b", missing_equipment="c"),
    )
    store.save_program(
        base_dir,
        ProgramPlan(
            version=1,
            goal_id="g",
            created_on=date(2026, 1, 1),
            mesocycles=[
                Mesocycle(
                    index=1,
                    phase="general_prep",
                    weeks=[
                        WeekPlan(
                            week_index=1,
                            volume_factor=1.0,
                            intensity_factor=1.0,
                            sessions=[session],
                        )
                    ],
                )
            ],
        ),
    )


def _kpi_entry():
    return {
        "date": "2026-07-02",
        "kpi_id": "cmj-height",
        "protocol": "mat",
        "value": 44.0,
        "unit": "cm",
    }


def _exercise_definition():
    return {
        "id": "cov-drill",
        "name": "Coverage Drill",
        "patterns": ["jump"],
        "force_vector": "axial",
        "contraction_regime": "plyometric",
        "chain": "closed",
        "equipment": [],
        "specificity_level": "special",
        "qualities_trained": {"reactive_strength": 0.8},
        "skill_complexity": 2,
        "provenance": {"kind": "prior"},
    }


@pytest.mark.anyio
async def test_every_new_tool_registered_and_exercised(client, athlete_home):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert names >= _NEW_TOOLS, f"missing tools: {sorted(_NEW_TOOLS - names)}"

    # Exercise save_performance_model via the tool, then seed the rest via the store.
    model_payload = load_seed_models()["sprint-100m"].model_dump(mode="json")
    saved_model = await client.call_tool("save_performance_model", {"model": model_payload})
    assert not saved_model.isError
    _seed(athlete_home)
    macro = await client.call_tool("build_macro_plan", {"horizon_years": 2})
    calls = {
        "read_performance_model": {},
        "log_kpi_result": {"entry": _kpi_entry()},
        "read_kpi_results": {},
        "compute_performance_gaps": {},
        "plan_test_battery": {},
        "list_exercises": {"pattern": "jump"},
        "propose_exercise": {"definition": _exercise_definition()},
        "score_exercises": {"quality_targets": {"reactive_strength": 1.0}, "phase": "realization"},
        "check_program_specificity": {},
        "search_exercise_media": {"query": "squat"},
        "fit_load_velocity": {"exercise": "Back Squat"},
        "fit_banister": {"kpi_id": "back-squat-rel"},
        "recommend_taper": {"buildup_weeks": 8, "modality": "strength", "event_priority": "A"},
        "fit_taper_response": {},
        "save_macro_plan": {"plan": macro.structuredContent},
        "read_macro_plan": {},
        "check_residuals": {},
    }
    assert not macro.isError
    for tool_name, args in calls.items():
        result = await client.call_tool(tool_name, args)
        assert not result.isError, f"{tool_name} errored: {result.content}"
