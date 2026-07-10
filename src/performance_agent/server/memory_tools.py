"""MCP tools for the athlete data directory (file-based long-term memory).

These tools own every stored fact. The coach reads the athlete at conversation
start, quotes get_time_context instead of computing dates, and records every
adaptation through the versioned program store.
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import CheckinEntry, Goal, Profile, SessionEntry
from performance_agent.memory.time_context import TimeContext, build_time_context


class AthleteSnapshot(TypedDict):
    """Everything stored about the athlete, in one read."""

    athlete_dir: str
    profile: Profile
    goals: list[Goal]
    program_version: int | None


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


class ProgramSaved(TypedDict):
    """Result of writing a new program version."""

    path: str
    version: int


class ProgramView(TypedDict):
    """A stored program version with its audit metadata."""

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    body: str


def read_athlete() -> AthleteSnapshot:
    """Return the athlete snapshot: profile, goals, latest program version.

    Call this at the start of every coaching conversation — no conversation
    starts from zero.
    """
    base = resolve_athlete_dir()
    return AthleteSnapshot(
        athlete_dir=str(base),
        profile=store.read_profile(base),
        goals=store.read_goals(base),
        program_version=store.latest_program_version(base),
    )


def write_profile(profile: Profile) -> WrittenFile:
    """Replace the athlete profile.

    Read the athlete first, then write the FULL updated profile — this is a
    whole-document replace, not a merge: omitted fields are DROPPED
    (injuries, equipment, availability, notes).
    """
    return WrittenFile(path=str(store.write_profile(resolve_athlete_dir(), profile)))


def upsert_goal(goal: Goal) -> GoalCount:
    """Add a goal, or replace the goal that has the same id."""
    return GoalCount(total_goals=len(store.upsert_goal(resolve_athlete_dir(), goal)))


def log_session(entry: SessionEntry) -> SessionCount:
    """Append one completed training session to the athlete's history.

    Timestamps are naive local wall-clock time (no timezone offset).
    """
    base = resolve_athlete_dir()
    store.append_session(base, entry)
    return SessionCount(total_sessions=len(store.read_sessions(base)))


def log_checkin(entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; days_since_last is auto-filled from the previous one.

    days_since_last may be negative for backdated entries.
    """
    return store.append_checkin(resolve_athlete_dir(), entry)


def read_sessions(last_n: int | None = None) -> SessionHistory:
    """Return logged training sessions, oldest first.

    Use these to build daily-load series for compute_weekly_loads/compute_acwr
    and to diagnose adherence. last_n limits to the most recent N entries.
    """
    sessions = store.read_sessions(resolve_athlete_dir())
    if last_n is not None:
        sessions = sessions[-last_n:]
    return SessionHistory(sessions=sessions)


def read_checkins(last_n: int | None = None) -> CheckinHistory:
    """Return logged check-ins, oldest first (last_n limits to the most recent N)."""
    checkins = store.read_checkins(resolve_athlete_dir())
    if last_n is not None:
        checkins = checkins[-last_n:]
    return CheckinHistory(checkins=checkins)


def save_program(markdown_body: str, goal_id: str, reason: str | None = None) -> ProgramSaved:
    """Write the NEXT program version (immutable audit trail).

    Version 1 needs no reason; every adaptation (v2+) requires a reason stating
    the coaching decision. Existing versions are never overwritten.
    """
    path, version = store.save_program(resolve_athlete_dir(), markdown_body, goal_id, reason)
    return ProgramSaved(path=str(path), version=version)


def read_program(version: int | None = None) -> ProgramView:
    """Return the latest (or a specific) program version.

    Raises a readable error if no program has been saved yet — call
    save_program first. Check read_athlete's program_version first: null
    there means nothing to read yet.
    """
    result = store.read_program(resolve_athlete_dir(), version)
    if result is None:
        msg = "no program has been saved yet; call save_program first"
        raise ValueError(msg)
    frontmatter, body = result
    reason = frontmatter.get("reason")
    return ProgramView(
        version=int(str(frontmatter["version"])),
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(reason) if reason is not None else None,
        body=body,
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
        get_time_context,
    ):
        mcp.tool()(tool)
