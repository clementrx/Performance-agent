"""MCP tools for the weekly follow-up: loads review and watch reports."""

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import store, weekly_review
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.weekly_review import WeeklyLoadsView
from performance_agent.server.memory_tools import VersionedDocSaved


def suggest_next_week_loads(days_back: int = 7) -> WeeklyLoadsView:
    """Compute next week's load for every block of the logged program week.

    Deterministic engine math, zero guessing: logged sessions from the last
    days_back days are matched to the program (session_plan_id first, exercise
    names as fallback); each block's structured progression rule then yields
    {next_load_kg, rationale_key, flags}. Degraded cases are flags, never
    guesses: no_rule (unstructured block — handle it conversationally),
    no_logged_sets, failed_sets (hold), no_rir_logged, no_e1rm, clamped,
    ambiguous_reps; week-level: no_matched_week, last_week. Quote the numbers
    and the rationale to the athlete; this NEVER modifies the program. A
    successful run is recorded so list_due_actions can see the review happened.
    """
    return weekly_review.suggest_next_week_loads(resolve_athlete_dir(), days_back=days_back)


def save_watch_report(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT program-watch report version (immutable audit trail).

    The report is the program-watch skill's output: per-exercise verdicts
    (keep / watch / substitution candidate) with the data behind each one.
    Version 1 needs no reason; every later report (v2+) requires a reason
    naming its trigger (biweekly watch, mesocycle boundary, athlete request).
    Saving also timestamps the watch for list_due_actions.
    """
    path, version = store.save_watch_report(resolve_athlete_dir(), markdown_body, goal_id, reason)
    return VersionedDocSaved(path=str(path), version=version)


def register(mcp: FastMCP) -> None:
    """Register the follow-up tools on the server."""
    for tool in (suggest_next_week_loads, save_watch_report):
        mcp.tool()(tool)
