"""MCP tools for the athlete data directory (file-based long-term memory).

These tools own every stored fact. The coach reads the athlete at conversation
start, quotes get_time_context instead of computing dates, and records every
adaptation through the versioned program store.
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import (
    CheckinEntry,
    Goal,
    Profile,
    ProgramPlan,
    SessionEntry,
)
from performance_agent.memory.time_context import TimeContext, build_time_context


class AthleteSnapshot(TypedDict):
    """Everything stored about the athlete, in one read.

    The four version fields tell you where the athlete is in the pipeline:
    analysis but no dossier means the deep research has not run yet;
    nutrition_frame_version is null unless the Nutritionist has run.
    """

    athlete_dir: str
    profile: Profile
    goals: list[Goal]
    program_version: int | None
    analysis_version: int | None
    dossier_version: int | None
    nutrition_frame_version: int | None


class WrittenFile(TypedDict):
    """Path of the file the tool just wrote."""

    path: str


class GoalCount(TypedDict):
    """Number of stored goals after the operation."""

    total_goals: int


class SessionCount(TypedDict):
    """Number of logged sessions after the operation."""

    total_sessions: int


class SessionHistory(TypedDict):
    """Logged sessions, oldest first."""

    sessions: list[SessionEntry]


class CheckinHistory(TypedDict):
    """Logged check-ins, oldest first."""

    checkins: list[CheckinEntry]


class VersionedDocSaved(TypedDict):
    """Result of writing a new version of a versioned athlete document."""

    path: str
    version: int


class VersionedDocView(TypedDict):
    """A stored document version with its audit metadata."""

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    body: str


class ProgramView(TypedDict):
    """A stored program version: rendered markdown plus its structured plan.

    plan is null for legacy prose-only versions saved before the structured
    format landed (still readable and adaptable).
    """

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    plan: ProgramPlan | None


def read_athlete() -> AthleteSnapshot:
    """Return the athlete snapshot: profile, goals, latest artifact versions.

    Call this at the start of every coaching conversation — no conversation
    starts from zero. The analysis/dossier/program versions locate the
    athlete in the pipeline (analysis without dossier = research not run).
    """
    base = resolve_athlete_dir()
    return AthleteSnapshot(
        athlete_dir=str(base),
        profile=store.read_profile(base),
        goals=store.read_goals(base),
        program_version=store.latest_program_version(base),
        analysis_version=store.latest_analysis_version(base),
        dossier_version=store.latest_research_dossier_version(base),
        nutrition_frame_version=store.latest_nutrition_frame_version(base),
    )


def write_profile(profile: Profile) -> WrittenFile:
    """Replace the athlete profile.

    Read the athlete first, then write the FULL updated profile — this is a
    whole-document replace, not a merge: omitted fields are DROPPED
    (injuries, equipment, availability, notes, lift_inventory, body_fat_pct,
    calendar_type, split_preferences).
    """
    return WrittenFile(path=str(store.write_profile(resolve_athlete_dir(), profile)))


def upsert_goal(goal: Goal) -> GoalCount:
    """Add a goal, or replace the goal that has the same id."""
    return GoalCount(total_goals=len(store.upsert_goal(resolve_athlete_dir(), goal)))


def log_session(entry: SessionEntry) -> SessionCount:
    """Append one completed training session to the athlete's history.

    Strength sessions should carry structured exercises → sets
    {reps, load_kg, rir}; endurance sessions may omit exercises entirely.
    Timestamps are naive local wall-clock time (no timezone offset).
    """
    base = resolve_athlete_dir()
    store.append_session(base, entry)
    return SessionCount(total_sessions=len(store.read_sessions(base)))


def log_checkin(entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; days_since_last is auto-filled from the previous one.

    Record bodyweight_kg at every check-in when the goal involves body
    composition — the series across check-ins IS the trend the coach reads.
    days_since_last may be negative for backdated entries.
    """
    return store.append_checkin(resolve_athlete_dir(), entry)


def read_sessions(last_n: Annotated[int, Field(ge=1)] | None = None) -> SessionHistory:
    """Return logged training sessions, oldest first.

    Use these to build daily-load series for compute_weekly_loads/compute_acwr
    and to diagnose adherence. last_n limits to the most recent N entries.
    """
    sessions = store.read_sessions(resolve_athlete_dir())
    if last_n is not None:
        sessions = sessions[-last_n:]
    return SessionHistory(sessions=sessions)


def read_checkins(last_n: Annotated[int, Field(ge=1)] | None = None) -> CheckinHistory:
    """Return logged check-ins, oldest first (last_n limits to the most recent N)."""
    checkins = store.read_checkins(resolve_athlete_dir())
    if last_n is not None:
        checkins = checkins[-last_n:]
    return CheckinHistory(checkins=checkins)


def _doc_view(result: tuple[dict[str, object], str] | None, missing_msg: str) -> VersionedDocView:
    if result is None:
        raise ValueError(missing_msg)
    frontmatter, body = result
    reason = frontmatter.get("reason")
    return VersionedDocView(
        version=int(str(frontmatter["version"])),
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(reason) if reason is not None else None,
        body=body,
    )


def save_program(plan: ProgramPlan, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT program version from a structured plan (immutable audit trail).

    Hand a full ProgramPlan (mesocycles → weeks → sessions → blocks, with a
    progression rule and non-empty fallbacks per block). The store renders the
    markdown from it and stamps the authoritative version, created_on, and
    reason — the plan's own version/created_on/reason are placeholders. Version
    1 needs no reason; every adaptation (v2+) requires a reason stating the
    coaching decision. Existing versions are never overwritten. goal_id lives
    on the plan.
    """
    path, version = store.save_program(resolve_athlete_dir(), plan, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_program(version: int | None = None) -> ProgramView:
    """Return the latest (or a specific) program version: markdown plus plan.

    plan is null for legacy prose-only versions. Raises a readable error if no
    program has been saved yet — call save_program first. Check read_athlete's
    program_version first: null there means nothing to read yet.
    """
    program = store.read_program(resolve_athlete_dir(), version)
    if program is None:
        msg = "no program has been saved yet; call save_program first"
        raise ValueError(msg)
    return ProgramView(
        version=program.version,
        goal_id=program.goal_id,
        created_on=program.created_on,
        reason=program.reason,
        markdown=program.markdown,
        plan=program.plan,
    )


def save_analysis(markdown_body: str, goal_id: str, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT needs-analysis version (immutable audit trail).

    The needs analysis is the Analyst's output and the brief the Researcher and
    program builder receive: athlete summary, goal & feasibility verdict with
    its drivers, quality hierarchy, muscle/pattern priorities, injury flags,
    and research questions. Version 1 needs no reason; every revision (v2+)
    requires a reason stating what changed (new verdict, renegotiated goal).
    Existing versions are never overwritten.
    """
    path, version = store.save_analysis(resolve_athlete_dir(), markdown_body, goal_id, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_analysis(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) needs-analysis version.

    Raises a readable error when no analysis has been saved yet — run the
    needs-analysis skill (which ends with save_analysis) first.
    """
    return _doc_view(
        store.read_analysis(resolve_athlete_dir(), version),
        "no needs analysis has been saved yet; call save_analysis first",
    )


def save_research_dossier(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT research-dossier version (immutable audit trail).

    The dossier is the Researcher's output: per-facet synthesis with evidence
    grades, contradictions surfaced with both camps cited, confidence levels,
    and honest thin-evidence/degraded-coverage notes. Cite only corpus ids —
    every study it builds on must already be persisted via save_evidence.
    Version 1 needs no reason; re-research (v2+) requires a reason. Existing
    versions are never overwritten.
    """
    path, version = store.save_research_dossier(
        resolve_athlete_dir(), markdown_body, goal_id, reason
    )
    return VersionedDocSaved(path=str(path), version=version)


def read_research_dossier(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) research-dossier version.

    Raises a readable error when no dossier has been saved yet — run the
    deep-research skill (which ends with save_research_dossier) first.
    """
    return _doc_view(
        store.read_research_dossier(resolve_athlete_dir(), version),
        "no research dossier has been saved yet; call save_research_dossier first",
    )


def save_nutrition_frame(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT nutrition-frame version (immutable audit trail).

    The frame is the Nutritionist's output: a fenced yaml block carrying the
    engine-computed numbers (goal, daily_kcal, protein_g_per_day,
    weekly_change_kg, clamped_to_floor, review_trigger) plus prose explaining
    them and the training phase the frame assumes. Version 1 needs no reason;
    every recalculation (v2+ — weight change, phase change) requires a
    reason. Existing versions are never overwritten.
    """
    path, version = store.save_nutrition_frame(
        resolve_athlete_dir(), markdown_body, goal_id, reason
    )
    return VersionedDocSaved(path=str(path), version=version)


def read_nutrition_frame(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) nutrition-frame version.

    Raises a readable error when no frame has been saved yet — run the
    nutrition-planning skill (which ends with save_nutrition_frame) first.
    """
    return _doc_view(
        store.read_nutrition_frame(resolve_athlete_dir(), version),
        "no nutrition frame has been saved yet; call save_nutrition_frame first",
    )


def get_time_context() -> TimeContext:
    """Current date plus days-since deltas and goal countdowns.

    Call this at conversation start and quote its numbers — never compute
    dates yourself. Negative days_remaining means the deadline is overdue;
    null deltas mean nothing has been logged yet (not "today").
    """
    return build_time_context(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register every memory tool on the server."""
    for tool in (
        read_athlete,
        write_profile,
        upsert_goal,
        log_session,
        log_checkin,
        read_sessions,
        read_checkins,
        save_program,
        read_program,
        save_analysis,
        read_analysis,
        save_research_dossier,
        read_research_dossier,
        save_nutrition_frame,
        read_nutrition_frame,
        get_time_context,
    ):
        mcp.tool()(tool)
