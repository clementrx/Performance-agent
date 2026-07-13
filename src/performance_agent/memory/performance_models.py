"""PerformanceModel athlete layer: seeds, gap analysis, test-battery scheduling.

The engine (engine/gaps.py, engine/test_battery.py) is pydantic- and
datetime-free; this module reads the stored PerformanceModel, the KPI-results
log and the calendar, converts dates into staleness/week indices, calls the pure
engine, and assembles LLM-facing views. It never fabricates a gap: an unmeasured
KPI stays unmeasured. Seed models are packaged read-only fixtures/few-shot
examples, never a support gate.
"""

from datetime import date, timedelta
from importlib import resources
from pathlib import Path
from typing import TypedDict

import yaml

from performance_agent.engine.gaps import KpiTarget, Measurement, compute_gaps
from performance_agent.engine.test_battery import (
    TestableKpi,
    plan_test_battery,
)
from performance_agent.memory import season as season_layer
from performance_agent.memory import store
from performance_agent.memory.schemas import KpiResult, KpiSpec, PerformanceModel

_SEED_PACKAGE = "performance_agent.models"
_DAYS_PER_WEEK = 7
_BLACKOUT_PHASES = frozenset({"taper", "competition"})


def load_seed_models() -> dict[str, PerformanceModel]:
    """Load the packaged reference PerformanceModels keyed by file slug."""
    seed_dir = resources.files(_SEED_PACKAGE) / "data" / "seed"
    models: dict[str, PerformanceModel] = {}
    for entry in seed_dir.iterdir():
        if entry.name.endswith(".yaml"):
            raw = yaml.safe_load(entry.read_text(encoding="utf-8"))
            slug = entry.name.removesuffix(".yaml")
            models[slug] = PerformanceModel.model_validate(raw)
    return dict(sorted(models.items()))


class QualityPriorityView(TypedDict):
    """A quality's training priority (None score when unmeasured)."""

    quality: str
    weight: float
    mean_gap: float | None
    priority_score: float | None
    measured_kpis: int
    unmeasured_kpis: int


class KpiGapView(TypedDict):
    """One KPI's gap to the chosen level (status says whether it is measurable)."""

    kpi_id: str
    quality: str
    status: str
    measured_value: float | None
    benchmark_value: float | None
    gap_fraction: float | None
    staleness_days: int | None
    stale: bool


class GapReportView(TypedDict):
    """Per-KPI gaps and per-quality priorities for the LLM to narrate."""

    level: str
    kpi_gaps: list[KpiGapView]
    quality_priorities: list[QualityPriorityView]


def _quality_weights(model: PerformanceModel) -> dict[str, float]:
    return {q.quality: q.weight for q in model.qualities}


def _kpi_target(kpi: KpiSpec, weights: dict[str, float]) -> KpiTarget:
    return KpiTarget(
        kpi_id=kpi.id,
        quality=kpi.quality,
        weight=weights.get(kpi.quality, 0.0),
        higher_is_better=kpi.higher_is_better,
        benchmarks=tuple((b.level, b.value) for b in kpi.benchmarks),
    )


def _latest_measurements(results: list[KpiResult], today: date) -> list[Measurement]:
    """Latest value per kpi_id, with staleness in days (results without a kpi_id skipped)."""
    latest: dict[str, KpiResult] = {}
    for result in results:
        if result.kpi_id is None:
            continue
        current = latest.get(result.kpi_id)
        if current is None or result.date >= current.date:
            latest[result.kpi_id] = result
    return [
        Measurement(kpi_id=kid, value=r.value, staleness_days=(today - r.date).days)
        for kid, r in latest.items()
    ]


def compute_performance_gaps(
    base_dir: Path, level: str = "elite", today: date | None = None
) -> GapReportView:
    """Score the athlete's KPI measurements against the model benchmarks for a level.

    Reads the latest performance model and the KPI-results log, resolves the
    latest value per KPI, and calls the pure gap engine. Unmeasured KPIs stay
    unmeasured; per-quality priority is the mean measured gap times the quality
    weight. Raises when no performance model has been saved.
    """
    resolved_today = today or date.today()
    model = store.read_performance_model(base_dir)
    if model is None:
        msg = "no performance model saved; research and save_performance_model first"
        raise ValueError(msg)
    weights = _quality_weights(model)
    targets = [_kpi_target(kpi, weights) for kpi in model.kpis]
    measurements = _latest_measurements(store.read_kpi_results(base_dir), resolved_today)
    report = compute_gaps(targets, measurements, level)
    return GapReportView(
        level=report.level,
        kpi_gaps=[
            KpiGapView(
                kpi_id=g.kpi_id,
                quality=g.quality,
                status=g.status,
                measured_value=g.measured_value,
                benchmark_value=g.benchmark_value,
                gap_fraction=g.gap_fraction,
                staleness_days=g.staleness_days,
                stale=g.stale,
            )
            for g in report.kpi_gaps
        ],
        quality_priorities=[
            QualityPriorityView(
                quality=p.quality,
                weight=p.weight,
                mean_gap=p.mean_gap,
                priority_score=p.priority_score,
                measured_kpis=p.measured_kpis,
                unmeasured_kpis=p.unmeasured_kpis,
            )
            for p in report.quality_priorities
        ],
    )


class ScheduledTestView(TypedDict):
    """A scheduled test with its week index and calendar date."""

    week: int
    date: str
    kpi_id: str
    quality: str
    kind: str


class TestBatteryView(TypedDict):
    """The dated test battery for the LLM to narrate and place on the calendar."""

    start_date: str
    horizon_weeks: int
    tests: list[ScheduledTestView]


def _measured_kpi_ids(base_dir: Path) -> set[str]:
    return {r.kpi_id for r in store.read_kpi_results(base_dir) if r.kpi_id is not None}


def _blackout_weeks(base_dir: Path, today: date) -> tuple[int, frozenset[int]]:
    plan = season_layer.build_season_plan(base_dir, today=today)
    blackout: set[int] = set()
    for segment in plan["segments"]:
        if segment["phase_type"] in _BLACKOUT_PHASES:
            blackout.update(range(segment["start_week"], segment["end_week"] + 1))
    return plan["horizon_weeks"], frozenset(blackout)


def plan_performance_test_battery(base_dir: Path, today: date | None = None) -> TestBatteryView:
    """Schedule baseline + cadence re-tests for the model's KPIs around the calendar.

    KPIs with no logged measurement get a week-1 baseline; all get cadence-based
    re-tests. Tests never land inside a taper or on a competition week (blackouts
    derived from the backward season plan). Raises when no performance model exists.
    """
    resolved_today = today or date.today()
    model = store.read_performance_model(base_dir)
    if model is None:
        msg = "no performance model saved; research and save_performance_model first"
        raise ValueError(msg)
    measured = _measured_kpi_ids(base_dir)
    kpis = [
        TestableKpi(kpi_id=kpi.id, quality=kpi.quality, needs_baseline=kpi.id not in measured)
        for kpi in model.kpis
    ]
    horizon, blackout = _blackout_weeks(base_dir, resolved_today)
    tests = plan_test_battery(kpis, horizon, blackout)
    return TestBatteryView(
        start_date=resolved_today.isoformat(),
        horizon_weeks=horizon,
        tests=[
            ScheduledTestView(
                week=t.week,
                date=(resolved_today + timedelta(days=(t.week - 1) * _DAYS_PER_WEEK)).isoformat(),
                kpi_id=t.kpi_id,
                quality=t.quality,
                kind=t.kind,
            )
            for t in tests
        ],
    )
