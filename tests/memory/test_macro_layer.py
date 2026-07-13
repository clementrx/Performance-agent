"""Athlete-layer tests: macro plan build, versioned store, program residuals."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.macro import build_macro_plan, check_program_residuals
from performance_agent.memory.performance_models import load_seed_models
from performance_agent.memory.schemas import (
    CalendarEvent,
    ExerciseBlock,
    Fallbacks,
    Mesocycle,
    ProgramPlan,
    SessionPlan,
    WeekPlan,
)


def _seed_model_and_event(base_dir):
    store.save_performance_model(base_dir, load_seed_models()["sprint-100m"])
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="games", date=date(2028, 7, 1), kind="competition", priority="A", label="Games"
        ),
    )


def test_build_macro_plan_backward_typing(tmp_path):
    _seed_model_and_event(tmp_path)
    plan = build_macro_plan(tmp_path, horizon_years=2)
    assert plan.horizon_years == 2
    assert plan.major_event_id == "games"
    assert [y.year_type for y in plan.years] == ["development", "realization"]
    assert plan.years[1].primary_event_id == "games"


def test_build_macro_plan_requires_major_event(tmp_path):
    store.save_performance_model(tmp_path, load_seed_models()["sprint-100m"])
    with pytest.raises(ValueError, match="no A-priority competition"):
        build_macro_plan(tmp_path, horizon_years=2)


def test_macro_plan_store_round_trip(tmp_path):
    _seed_model_and_event(tmp_path)
    plan = build_macro_plan(tmp_path, horizon_years=3)
    path, version = store.save_macro_plan(tmp_path, plan)
    assert version == 1
    assert path == tmp_path / "macro" / "macro-plan-v1.yaml"
    stored = store.read_macro_plan(tmp_path)
    assert stored is not None
    assert stored.horizon_years == 3


def test_macro_plan_second_version_needs_reason(tmp_path):
    _seed_model_and_event(tmp_path)
    plan = build_macro_plan(tmp_path, horizon_years=2)
    store.save_macro_plan(tmp_path, plan)
    with pytest.raises(ValueError, match="reason"):
        store.save_macro_plan(tmp_path, plan)


def _program_with_speed_then_gap() -> ProgramPlan:
    def _session(week_index, eid):
        return SessionPlan(
            id=f"w{week_index:02d}-s1",
            weekday=0,
            qualities=["power"],
            est_minutes=60,
            purpose="test",
            blocks=[
                ExerciseBlock(
                    exercise=eid,
                    exercise_id=eid,
                    priority="primary",
                    sets=3,
                    reps="3",
                    rest_s=180,
                    progression_rule="x",
                )
            ],
            fallbacks=Fallbacks(low_readiness="a", short_on_time="b", missing_equipment="c"),
        )

    weeks = [
        WeekPlan(
            week_index=1,
            volume_factor=1.0,
            intensity_factor=1.0,
            sessions=[_session(1, "flying-sprint")],
        ),
        WeekPlan(
            week_index=8,
            volume_factor=1.0,
            intensity_factor=1.0,
            sessions=[_session(8, "back-squat")],
        ),
    ]
    return ProgramPlan(
        version=1,
        goal_id="g",
        created_on=date(2026, 7, 12),
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=weeks)],
    )


def test_check_residuals_flags_dropped_speed(tmp_path):
    store.save_program(tmp_path, _program_with_speed_then_gap())
    warnings = check_program_residuals(tmp_path)
    # flying-sprint trains speed on week 1; nothing refreshes it for ~7 weeks.
    assert any(w["quality"] == "speed" for w in warnings)


def test_check_residuals_requires_program(tmp_path):
    with pytest.raises(ValueError, match="no structured program"):
        check_program_residuals(tmp_path)
