"""Athlete-layer tests: individual taper response and per-quality rates."""

from datetime import date, datetime, timedelta

from performance_agent.memory import store
from performance_agent.memory.response import _per_quality_rates
from performance_agent.memory.schemas import (
    Benchmark,
    CalendarEvent,
    KpiResult,
    KpiSpec,
    PerformanceModel,
    Provenance,
    QualityRequirement,
    SessionEntry,
)
from performance_agent.memory.taper_response import fit_taper_response_view, recommend_taper

ORIGIN = date(2026, 1, 1)


def _log(base_dir, day, rpe, duration):
    at = datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=day)
    store.append_session(base_dir, SessionEntry(performed_at=at, rpe=rpe, duration_min=duration))


def _seed_tapers(base_dir, events_days):
    for day in range(120):
        tapering = any(e - 7 <= day < e for e in events_days)
        _log(base_dir, day, 3 if tapering else 7, 20 if tapering else 60)
    model = PerformanceModel(
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
    )
    store.save_performance_model(base_dir, model)
    for i, day in enumerate(events_days):
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


def test_recommend_taper_population_with_one_taper(tmp_path):
    _seed_tapers(tmp_path, [40])
    rec = recommend_taper(tmp_path, 8, "strength", "A")
    assert rec["basis"] == "population"
    assert rec["taper_days"] == rec["population_days"]


def test_recommend_taper_individual_with_two_tapers(tmp_path):
    _seed_tapers(tmp_path, [40, 90])
    rec = recommend_taper(tmp_path, 8, "strength", "A")
    assert rec["basis"] == "individual"
    assert rec["taper_days"] == 7  # the detected taper duration


def test_fit_view_reports_windows(tmp_path):
    _seed_tapers(tmp_path, [40, 90])
    view = fit_taper_response_view(tmp_path, 10)
    assert view["n_detected"] == 2
    assert view["n_with_outcome"] == 2
    assert all(w["duration_days"] == 7 for w in view["windows"])


def test_per_quality_rates_from_kpi_results(tmp_path):
    model = PerformanceModel(
        discipline="pl",
        event="squat",
        qualities=[
            QualityRequirement(
                quality="max_strength", weight=1.0, provenance=Provenance(kind="prior")
            )
        ],
        kpis=[
            KpiSpec(
                id="squat-1rm",
                name="Squat",
                quality="max_strength",
                protocol="1rm",
                unit="kg",
                higher_is_better=True,
                benchmarks=[
                    Benchmark(level="elite", value=250.0, provenance=Provenance(kind="prior"))
                ],
            )
        ],
    )
    store.save_performance_model(tmp_path, model)
    for week in range(6):
        store.append_kpi_result(
            tmp_path,
            KpiResult(
                date=ORIGIN + timedelta(days=week * 7),
                kpi_id="squat-1rm",
                protocol="1rm",
                value=180.0 + 2.0 * week,
                unit="kg",
            ),
        )
    rates = _per_quality_rates(tmp_path)
    assert len(rates) == 1
    assert rates[0].quality == "max_strength"
    assert rates[0].kpi_id == "squat-1rm"
    assert rates[0].pct_per_week > 0


def test_per_quality_rates_empty_without_model(tmp_path):
    assert _per_quality_rates(tmp_path) == []
