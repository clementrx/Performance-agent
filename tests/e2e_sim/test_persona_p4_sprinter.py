"""Persona P4 — sprinter (100 m, SEEDED model).

Drives the Phase 0-8 pipeline end to end on the packaged sprint-100m model:
seed the model -> log KPI measurements -> compute gaps -> plan the test battery ->
score exercises for a priority quality -> build a 2-year macro -> fit the Banister
model on a qualifying synthetic KPI+load history. No LLM; deterministic.
"""

from datetime import date, timedelta

from performance_agent.engine.banister import PerformancePoint, _decay_trace, fit_banister
from performance_agent.engine.load import session_rpe_load
from performance_agent.memory import store
from performance_agent.memory.banister import fit_kpi_banister
from performance_agent.memory.exercise_library import score_library_exercises
from performance_agent.memory.macro import build_macro_plan
from performance_agent.memory.performance_models import (
    compute_performance_gaps,
    load_seed_models,
    plan_performance_test_battery,
)
from performance_agent.memory.schemas import CalendarEvent, KpiResult, SessionEntry
from tests.e2e_sim import harness as h

TODAY = date(2026, 7, 13)


def _seed_sprinter(base_dir):
    store.save_performance_model(base_dir, load_seed_models()["sprint-100m"])
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="games", date=date(2028, 7, 1), kind="competition", priority="A", label="Games"
        ),
    )
    for kpi_id, value, unit in (
        ("sprint-100m-time", 10.8, "s"),
        ("back-squat-rel", 1.7, "x bodyweight"),
    ):
        store.append_kpi_result(
            base_dir,
            KpiResult(
                date=date(2026, 7, 1), kpi_id=kpi_id, protocol="test", value=value, unit=unit
            ),
        )


def test_sprinter_gaps_and_battery(tmp_path):
    _seed_sprinter(tmp_path)
    gaps = compute_performance_gaps(tmp_path, "elite", TODAY)
    measured = {g["kpi_id"]: g for g in gaps["kpi_gaps"] if g["status"] == "measured"}
    assert "sprint-100m-time" in measured
    # Measured qualities rank ahead of unmeasured ones.
    priorities = gaps["quality_priorities"]
    assert priorities[0]["priority_score"] is not None
    battery = plan_performance_test_battery(tmp_path, TODAY)
    assert battery["tests"]


def test_sprinter_scored_selection_favours_plyometrics(tmp_path):
    _seed_sprinter(tmp_path)
    scored = score_library_exercises(
        tmp_path,
        {"reactive_strength": 1.0},
        "realization",
        pattern="jump",
        available_equipment=["bodyweight", "box"],
        top_k=5,
    )
    assert scored
    assert scored[0]["excluded_reason"] is None
    assert scored[0]["quality_match"] > 0


def test_sprinter_two_year_macro(tmp_path):
    _seed_sprinter(tmp_path)
    plan = build_macro_plan(tmp_path, horizon_years=2)
    assert [y.year_type for y in plan.years] == ["development", "realization"]
    # Development year leans on general capacities (max_strength ranks high there).
    dev = dict(plan.years[0].quality_emphases)
    assert dev.get("max_strength", 0.0) > 0


def test_sprinter_banister_fit_qualifies(tmp_path):
    _seed_sprinter(tmp_path)
    # 84 days of daily sessions + 6 KPI points following a known Banister curve.
    n_days = 84
    rpe, duration = 5, 12
    daily_load = session_rpe_load(rpe, duration)
    loads = [daily_load] * n_days
    p0, k1, k2, tau1, tau2 = 60.0, 0.05, 0.07, 40.0, 8.0
    g1, g2 = _decay_trace(loads, tau1), _decay_trace(loads, tau2)
    origin = date(2026, 1, 1)
    for i in range(n_days):
        store.append_session(
            tmp_path,
            SessionEntry(
                performed_at=h.at((origin - h.ORIGIN).days + i), rpe=rpe, duration_min=duration
            ),
        )
    for day in (10, 25, 40, 55, 70, 82):
        store.append_kpi_result(
            tmp_path,
            KpiResult(
                date=origin + timedelta(days=day),
                kpi_id="cmj-height",
                protocol="cmj",
                value=p0 + k1 * g1[day] - k2 * g2[day],
                unit="cm",
            ),
        )
    params = fit_kpi_banister(tmp_path, "cmj-height")
    assert params.usable is True
    assert params.tau1 > params.tau2
    # Cross-check the pure engine agrees on the same reconstructed series.
    points = [
        PerformancePoint(day_index=day, value=p0 + k1 * g1[day] - k2 * g2[day])
        for day in (10, 25, 40, 55, 70, 82)
    ]
    assert fit_banister(loads, points).usable is True
