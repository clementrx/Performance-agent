"""MCP tools for multi-year planning: macro plan and training residuals.

build_macro_plan derives a 1-4 year plan from the gaps and the calendar's major
event; save_macro_plan/read_macro_plan version it immutably; check_residuals warns
where a program's maintained qualities would decay past their retention windows.
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from performance_agent.memory import macro, store
from performance_agent.memory.macro import ResidualWarningView
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import MacroPlan


class VersionedDocSaved(TypedDict):
    """Result of writing a new macro-plan version."""

    path: str
    version: int


def build_macro_plan(
    horizon_years: Annotated[int, Field(ge=1, le=4)],
    major_event_id: str | None = None,
    level: str = "elite",
) -> MacroPlan:
    """Build a multi-year macro plan (computed, not saved) from the gaps and calendar.

    Types each year backward from the major event (last = realization, prior =
    qualification for >= 3-year horizons, earlier = development) and derives each
    year's quality emphases from the performance-gap priorities: development years
    bias general capacities and the biggest weaknesses, the realization year biases
    specific/competition qualities. major_event_id defaults to the latest A-priority
    competition on the calendar. Errors if no performance model exists. Save with
    save_macro_plan; feed a year's emphases into build_season_plan.
    """
    return macro.build_macro_plan(resolve_athlete_dir(), horizon_years, major_event_id, level)


def save_macro_plan(plan: MacroPlan, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT macro-plan version (immutable YAML audit trail).

    Hand the MacroPlan from build_macro_plan (or a hand-edited one). The store
    stamps the authoritative version and reason; version 1 needs no reason, every
    later version (v2+) requires one. Existing versions are never overwritten.
    """
    path, version = store.save_macro_plan(resolve_athlete_dir(), plan, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_macro_plan(version: int | None = None) -> MacroPlan:
    """Return the latest (or a specific) macro-plan version (errors when none saved)."""
    plan = store.read_macro_plan(resolve_athlete_dir(), version)
    if plan is None:
        msg = "no macro plan has been saved yet; build one with build_macro_plan then save it"
        raise ValueError(msg)
    return plan


def check_residuals() -> list[ResidualWarningView]:
    """Warn where the active program's maintained qualities would decay past residuals.

    Resolves each block's exercise_id to its ontology qualities and checks the
    per-quality spacing against Issurin retention windows (aerobic/max-strength hold
    ~30 days, speed ~5). Returns one warning per over-long gap (empty when all
    qualities are refreshed in time); blocks with no exercise_id are skipped. Errors
    if no structured program exists.
    """
    return macro.check_program_residuals(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register the multi-year planning tools on the server."""
    for tool in (build_macro_plan, save_macro_plan, read_macro_plan, check_residuals):
        mcp.tool()(tool)
