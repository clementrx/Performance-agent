"""MCP tools for the individual response profile (measured recalibration).

The coach computes the profile at each mesocycle end, saves it as an immutable
version, and reads it before planning. Every measured field carries its sample
size; the tools return None where the data is too thin — the narrator must say
so, never invent a rate.
"""

from datetime import date
from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import response as response_engine
from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import ResponseProfile


class VersionedDocSaved(TypedDict):
    """Result of writing a new response-profile version."""

    path: str
    version: int


class SessionComplianceView(TypedDict):
    """How one planned session fared against the log."""

    session_id: str
    quality: str
    status: str
    matched_by: str


class WeeklyVolumeView(TypedDict):
    """Prescribed vs performed hard sets for one program week."""

    week_index: int
    prescribed_sets: int
    performed_sets: int


class ComplianceView(TypedDict):
    """Prescribed-vs-actual compliance for the active program.

    extra_unplanned counts logged sessions that matched no planned session;
    status per session is done / partial / modified / missed.
    """

    sessions: list[SessionComplianceView]
    weekly_volume: list[WeeklyVolumeView]
    extra_unplanned: int


def compute_response_profile(goal_id: str | None = None) -> ResponseProfile:
    """Distil the athlete's logged response into a profile (computed, not saved).

    Reads the active structured program (its created_on anchors program-week
    alignment), the session/readiness/adjustment logs and the goal, then returns
    per_lift_rates, per_goal_measured_rate {value, n, window_weeks, r2},
    volume_tolerance_flags, adherence_by_quality, adjustment_patterns and
    caveats. per_goal_measured_rate is null when the data is too thin (fewer than
    6 points or under a 4-week span) — recalibrate only when it is present; the
    caveats say where population priors still stand in. Call save_response_profile
    to persist the result. Errors if no structured program exists yet.
    """
    return response_engine.compute_response_profile(resolve_athlete_dir(), goal_id)


def save_response_profile(profile: ResponseProfile, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT response-profile version (immutable YAML audit trail).

    Hand the ResponseProfile from compute_response_profile. The store stamps the
    authoritative version, as_of date and reason. Version 1 needs no reason;
    every later version (v2+) requires a reason stating what changed (new
    measured rate at a mesocycle end). Existing versions are never overwritten.
    """
    path, version = store.save_response_profile(resolve_athlete_dir(), profile, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_response_profile(version: int | None = None) -> ResponseProfile:
    """Return the latest (or a specific) response-profile version.

    Raises a readable error when none has been saved yet. needs-analysis and
    program-planning MUST read this first and pass per_goal_measured_rate.value
    to the assess_* tools as measured_weekly_rate when it is present (state which
    rate the plan uses); map a volume_tolerance flag to weekly_set_targets_for's
    tolerance_adjustment.
    """
    profile = store.read_response_profile(resolve_athlete_dir(), version)
    if profile is None:
        msg = "no response profile has been saved yet; call compute_response_profile then save it"
        raise ValueError(msg)
    return profile


def compare_prescribed_actual() -> ComplianceView:
    """Compare the active program's prescribed sessions against what was logged.

    Matches on session_plan_id first, then same week + weekday + quality. Each
    planned session is done (>=90% of prescribed sets), partial, modified
    (matched only by the fallback or a different quality) or missed; weekly
    volume sums prescribed vs performed sets; extra_unplanned counts logged
    sessions that matched nothing. Program weeks are aligned from the program's
    created_on date. Errors if no structured program exists yet.
    """
    base = resolve_athlete_dir()
    program = store.read_program(base)
    if program is None or program.plan is None:
        msg = "no structured program to compare against; save a ProgramPlan first"
        raise ValueError(msg)
    origin = date.fromisoformat(program.created_on)
    report = response_engine.compare_plan_to_log(program.plan, store.read_sessions(base), origin)
    return ComplianceView(
        sessions=[
            SessionComplianceView(
                session_id=s.session_id,
                quality=s.quality,
                status=s.status,
                matched_by=s.matched_by,
            )
            for s in report.sessions
        ],
        weekly_volume=[
            WeeklyVolumeView(
                week_index=w.week_index,
                prescribed_sets=w.prescribed_sets,
                performed_sets=w.performed_sets,
            )
            for w in report.weekly_volume
        ],
        extra_unplanned=report.extra_unplanned,
    )


def register(mcp: FastMCP) -> None:
    """Register every response-profile tool on the server."""
    for tool in (
        compute_response_profile,
        save_response_profile,
        read_response_profile,
        compare_prescribed_actual,
    ):
        mcp.tool()(tool)
