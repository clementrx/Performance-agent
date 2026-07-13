"""MCP tools for the sport-agnostic PerformanceModel (event determinants).

The Analyste researches the literature, proposes a PerformanceModel filling the
generic schema (qualities, KPIs with benchmarks, injury risks, energy systems),
and saves it as an immutable version. The engine validates the schema, rejects
invented qualities and uncited "cited" values, and normalizes quality weights.
Every value the LLM fills carries a provenance label the reports render.
"""

from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import performance_models, store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.performance_models import GapReportView, TestBatteryView
from performance_agent.memory.schemas import KpiResult, PerformanceModel

BenchmarkLevel = Literal["recreational", "competitive", "national", "elite"]


class VersionedDocSaved(TypedDict):
    """Result of writing a new performance-model version."""

    path: str
    version: int


class KpiResultLogged(TypedDict):
    """Result of appending one KPI/test measurement."""

    kpi_id: str | None
    count: int


def save_performance_model(model: PerformanceModel, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT performance-model version (immutable YAML audit trail).

    Hand a fully attributed PerformanceModel: discipline, event, a non-empty
    qualities list (each with a weight 0-1 and a provenance label
    cited|prior|judgment — cited requires cite_ids from the corpus), KPIs (each
    with a test protocol, unit and level benchmarks), injury risks and an
    optional energy-system split. The engine normalizes the quality weights to
    sum to 1, rejects invented quality names, KPIs missing a protocol or unit,
    and "cited" provenance without cite_ids. The store stamps the authoritative
    version and reason; version 1 needs no reason, every later version (v2+)
    requires one stating what changed. Existing versions are never overwritten.
    """
    path, version = store.save_performance_model(resolve_athlete_dir(), model, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_performance_model(version: int | None = None) -> PerformanceModel:
    """Return the latest (or a specific) performance-model version.

    Raises a readable error when none has been saved yet. Read this before
    programming: the quality weights drive per-quality priorities and the KPIs
    with their benchmarks are what athlete measurements are scored against.
    """
    model = store.read_performance_model(resolve_athlete_dir(), version)
    if model is None:
        msg = "no performance model has been saved yet; research and save_performance_model first"
        raise ValueError(msg)
    return model


def log_kpi_result(entry: KpiResult) -> KpiResultLogged:
    """Append one dated KPI/test measurement to kpi_results.jsonl.

    Provide date, protocol (how it was measured), value, unit, and kpi_id linking
    to a KpiSpec in the performance model (kpi_id may be omitted for a measurement
    with no model KPI). context carries conditions the value depends on
    (bodyweight, surface, wind), numeric or textual. The log is append-only.
    """
    base = resolve_athlete_dir()
    store.append_kpi_result(base, entry)
    return KpiResultLogged(kpi_id=entry.kpi_id, count=len(store.read_kpi_results(base)))


def read_kpi_results() -> list[KpiResult]:
    """Return all logged KPI/test measurements in insertion order (empty when none)."""
    return store.read_kpi_results(resolve_athlete_dir())


def compute_performance_gaps(level: BenchmarkLevel = "elite") -> GapReportView:
    """Score the athlete's KPI measurements against the model benchmarks for a level.

    Reads the latest performance model and the KPI-results log. Returns per-KPI
    gaps (status measured|unmeasured|no_benchmark — unmeasured KPIs are never
    given a guessed number) and per-quality priorities (mean measured gap x the
    quality weight), highest priority first with unmeasured qualities last. Drives
    which qualities the program attacks first. Errors if no model has been saved.
    """
    return performance_models.compute_performance_gaps(resolve_athlete_dir(), level)


def plan_test_battery() -> TestBatteryView:
    """Schedule baseline + cadence-based re-tests for the model's KPIs around the calendar.

    KPIs with no logged measurement get a week-1 baseline; all get cadence-based
    re-tests (fast-adapting qualities more often). Tests never land inside a taper
    or on a competition week (blackouts derived from the backward season plan).
    Returns dated milestones to place on the calendar. Errors if no model has been
    saved.
    """
    return performance_models.plan_performance_test_battery(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register every performance-model tool on the server."""
    for tool in (
        save_performance_model,
        read_performance_model,
        log_kpi_result,
        read_kpi_results,
        compute_performance_gaps,
        plan_test_battery,
    ):
        mcp.tool()(tool)
