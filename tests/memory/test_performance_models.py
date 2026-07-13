"""Athlete-layer tests: seed loading, gap analysis, test-battery scheduling."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.performance_models import (
    compute_performance_gaps,
    load_seed_models,
    plan_performance_test_battery,
)
from performance_agent.memory.schemas import CalendarEvent, KpiResult

TODAY = date(2026, 7, 13)
_EXPECTED_SEEDS = {"sprint-100m", "running-10k", "powerlifting", "football"}


def test_all_seed_models_load_and_validate():
    models = load_seed_models()
    assert set(models) == _EXPECTED_SEEDS
    for model in models.values():
        assert model.qualities
        assert sum(q.weight for q in model.qualities) == pytest.approx(1.0)


def _seed(base_dir, slug="sprint-100m"):
    store.save_performance_model(base_dir, load_seed_models()[slug])


def test_gaps_require_a_saved_model(tmp_path):
    with pytest.raises(ValueError, match="no performance model saved"):
        compute_performance_gaps(tmp_path, "elite", TODAY)


def test_gaps_from_measurements(tmp_path):
    _seed(tmp_path)
    store.append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="sprint-100m-time", protocol="timed", value=10.8, unit="s"
        ),
    )
    report = compute_performance_gaps(tmp_path, "elite", TODAY)
    by_id = {g["kpi_id"]: g for g in report["kpi_gaps"]}
    assert by_id["sprint-100m-time"]["status"] == "measured"
    assert by_id["sprint-100m-time"]["gap_fraction"] == pytest.approx(0.08)
    # A KPI with no measurement stays unmeasured.
    assert by_id["cmj-height"]["status"] == "unmeasured"


def test_gap_priorities_sorted_measured_first(tmp_path):
    _seed(tmp_path)
    store.append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 7, 1),
            kpi_id="back-squat-rel",
            protocol="1rm",
            value=1.7,
            unit="x bodyweight",
        ),
    )
    report = compute_performance_gaps(tmp_path, "elite", TODAY)
    priorities = report["quality_priorities"]
    assert priorities[0]["priority_score"] is not None
    assert priorities[-1]["priority_score"] is None


def test_latest_measurement_used(tmp_path):
    _seed(tmp_path)
    store.append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 6, 1),
            kpi_id="back-squat-rel",
            protocol="1rm",
            value=1.5,
            unit="x bodyweight",
        ),
    )
    store.append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 7, 1),
            kpi_id="back-squat-rel",
            protocol="1rm",
            value=2.0,
            unit="x bodyweight",
        ),
    )
    report = compute_performance_gaps(tmp_path, "elite", TODAY)
    squat = next(g for g in report["kpi_gaps"] if g["kpi_id"] == "back-squat-rel")
    assert squat["measured_value"] == pytest.approx(2.0)


def test_test_battery_requires_model(tmp_path):
    with pytest.raises(ValueError, match="no performance model saved"):
        plan_performance_test_battery(tmp_path, TODAY)


def test_test_battery_baselines_unmeasured_kpis(tmp_path):
    _seed(tmp_path)
    store.append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="sprint-100m-time", protocol="timed", value=10.8, unit="s"
        ),
    )
    battery = plan_performance_test_battery(tmp_path, TODAY)
    baselines = {t["kpi_id"] for t in battery["tests"] if t["kind"] == "baseline"}
    # The measured KPI needs no baseline; unmeasured ones do.
    assert "sprint-100m-time" not in baselines
    assert "cmj-height" in baselines


def test_test_battery_avoids_competition_blackout(tmp_path):
    _seed(tmp_path)
    store.upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="champs", date=date(2026, 10, 1), kind="competition", priority="A", label="Nationals"
        ),
    )
    battery = plan_performance_test_battery(tmp_path, TODAY)
    # The competition week must hold no test.
    comp_week = (date(2026, 10, 1) - TODAY).days // 7 + 1
    assert all(t["week"] != comp_week for t in battery["tests"])
