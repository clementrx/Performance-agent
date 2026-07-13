"""Determinism guard: two runs of the pipeline produce identical outputs.

The whole engine is deterministic (no LLM, no wall-clock, no global randomness), so
running the same seeded athlete through the Phase 0-8 pipeline twice must yield
byte-identical results.
"""

from datetime import date

from performance_agent.memory import store
from performance_agent.memory.exercise_library import score_library_exercises
from performance_agent.memory.macro import build_macro_plan
from performance_agent.memory.performance_models import (
    compute_performance_gaps,
    load_seed_models,
    plan_performance_test_battery,
)
from performance_agent.memory.schemas import CalendarEvent, KpiResult

TODAY = date(2026, 7, 13)


def _seed(base_dir):
    store.save_performance_model(base_dir, load_seed_models()["football"])
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="cup", date=date(2028, 6, 1), kind="competition", priority="A", label="Cup"
        ),
    )
    store.append_kpi_result(
        base_dir,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="sprint-10m", protocol="gates", value=1.8, unit="s"
        ),
    )
    store.append_kpi_result(
        base_dir,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="cmj-height", protocol="mat", value=38.0, unit="cm"
        ),
    )


def _pipeline(base_dir):
    gaps = compute_performance_gaps(base_dir, "elite", TODAY)
    battery = plan_performance_test_battery(base_dir, TODAY)
    scored = score_library_exercises(
        base_dir, {"acceleration": 1.0}, "specific_prep", available_equipment=["bodyweight", "sled"]
    )
    macro = build_macro_plan(base_dir, horizon_years=3)
    return gaps, battery, scored, macro.model_dump(mode="json")


def test_two_runs_are_identical(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _seed(a)
    _seed(b)
    assert _pipeline(a) == _pipeline(b)


def test_repeated_calls_on_one_athlete_are_stable(tmp_path):
    _seed(tmp_path)
    first = _pipeline(tmp_path)
    second = _pipeline(tmp_path)
    assert first == second
