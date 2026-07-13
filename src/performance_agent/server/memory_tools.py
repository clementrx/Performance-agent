"""MCP tools for the athlete data directory (file-based long-term memory).

These tools own every stored fact. The coach reads the athlete at conversation
start, quotes get_time_context instead of computing dates, and records every
adaptation through the versioned program store.
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from performance_agent.engine import SeasonModality
from performance_agent.memory import diligence, monitoring, sequencing, store
from performance_agent.memory import season as season_planner
from performance_agent.memory.diligence import DueActionView
from performance_agent.memory.monitoring import PlausibilityFlag
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import (
    Calendar,
    CalendarEvent,
    CheckinEntry,
    Goal,
    Profile,
    ProgramPlan,
    ReadinessEntry,
    RecurringConstraint,
    SessionEntry,
    WeekPlan,
)
from performance_agent.memory.season import SeasonPlanView
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


class SessionLogResult(TypedDict):
    """Sessions logged so far, plus any data-quality flags on this entry.

    flags is empty when the entry looks clean. A non-empty flags list means a
    value (an implausible 1RM jump, a load above a known max, an outlier
    duration) needs confirming with the athlete before it is treated as fact —
    the entry is still logged regardless.
    """

    total_sessions: int
    flags: list[PlausibilityFlag]


class ReadinessCount(TypedDict):
    """Number of logged readiness reads after the operation."""

    total_readiness: int


class ReadinessHistory(TypedDict):
    """Logged readiness reads, oldest first."""

    readiness: list[ReadinessEntry]


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


def log_session(entry: SessionEntry) -> SessionLogResult:
    """Append one completed training session; returns the count and any flags.

    Strength sessions should carry structured exercises → sets
    {reps, load_kg, rir}; endurance sessions may omit exercises entirely. Set
    source="external" for load the coach did not program (club practice, matches,
    physical work) and session_plan_id to link a session back to the program.
    Timestamps are naive local wall-clock time (no timezone offset). The result
    carries data-quality flags (implausible 1RM jumps, loads above a known max,
    outlier durations); confirm any flagged value with the athlete before
    treating it as fact — the entry is logged either way.
    """
    base = resolve_athlete_dir()
    history = store.read_sessions(base)
    profile = store.read_profile(base)
    flags = monitoring.session_plausibility_flags(entry, history, profile)
    store.append_session(base, entry)
    return SessionLogResult(total_sessions=len(history) + 1, flags=flags)


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


def log_readiness(entry: ReadinessEntry) -> ReadinessCount:
    """Append one pre-session readiness read (Hooper items, optional HRV).

    Each Hooper item is 1 (best) to 7 (worst): sleep, fatigue, soreness, stress.
    hrv_ms is an optional raw HRV value. For a serious competitor this is the
    DEFAULT on training days — pass compute_readiness the same four items to get
    the score and green/amber/red band. Timestamps are naive local wall-clock
    time.
    """
    base = resolve_athlete_dir()
    store.append_readiness(base, entry)
    return ReadinessCount(total_readiness=len(store.read_readiness(base)))


def read_readiness(last_n: Annotated[int, Field(ge=1)] | None = None) -> ReadinessHistory:
    """Return logged readiness reads, oldest first (last_n limits to the most recent N).

    Feed these to compute_readiness for the band and to build the daily-load and
    freshness (TSB) picture alongside sessions.
    """
    readiness = store.read_readiness(resolve_athlete_dir())
    if last_n is not None:
        readiness = readiness[-last_n:]
    return ReadinessHistory(readiness=readiness)


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


class CalendarSummary(TypedDict):
    """Event and recurring-constraint counts after a calendar write."""

    total_events: int
    total_recurring: int


def read_calendar() -> Calendar:
    """Return the athlete's season calendar (dated events + recurring constraints).

    Empty when nothing has been recorded. Events are date-sorted. The season
    planner (build_season_plan) reads this as its scheduling source of truth.
    """
    return store.read_calendar(resolve_athlete_dir())


def upsert_calendar_event(event: CalendarEvent) -> CalendarSummary:
    """Add a dated event, or replace the event with the same id.

    Each event carries a slug id, a date, a kind (competition/test/camp/
    travel/holiday/other), an A/B/C priority, a label, and optionally the
    goal_id it serves. A-priority competitions drive the season backward plan.
    """
    calendar = store.upsert_calendar_event(resolve_athlete_dir(), event)
    return CalendarSummary(
        total_events=len(calendar.events), total_recurring=len(calendar.recurring)
    )


def remove_calendar_event(event_id: str) -> CalendarSummary:
    """Remove the dated event with this id (no-op when it is absent)."""
    calendar = store.remove_calendar_event(resolve_athlete_dir(), event_id)
    return CalendarSummary(
        total_events=len(calendar.events), total_recurring=len(calendar.recurring)
    )


def set_recurring_constraints(recurring: list[RecurringConstraint]) -> CalendarSummary:
    """Replace the whole weekly recurring-constraint list (whole-list replace).

    Each constraint is a weekday (0=Monday), a kind (club_practice/match_day/
    unavailable), an optional duration and estimated session-RPE (CR-10), and
    a label. This is a replace, not a merge — pass the FULL current list.
    """
    calendar = store.set_recurring_constraints(resolve_athlete_dir(), recurring)
    return CalendarSummary(
        total_events=len(calendar.events), total_recurring=len(calendar.recurring)
    )


def build_season_plan(modality: SeasonModality = "mixed") -> SeasonPlanView:
    """Plan the season backward from the calendar's dated events.

    Reserves a taper immediately before each A-priority competition and fills
    the gaps with block (>= 6 weeks) or wave development; two A events closer
    than 6 weeks yield a maintenance bridge flagged as a compromise (surface it
    honestly). With no dated event, returns one open-ended development segment.
    modality (strength/endurance/mixed) sets taper lengths. Each segment carries
    week indices, calendar dates, its phase_type, and a rationale to quote;
    B/C events are surfaced separately (B gets a mini-taper, C is trained
    through). Chain the periodization builders per segment's phase_type.
    """
    return season_planner.build_season_plan(resolve_athlete_dir(), modality)


class ViolationView(TypedDict):
    """One broken intra-week sequencing rule.

    severity is block (must be fixed before delivery) or warn (must be
    acknowledged in the program notes). session_ids names the sessions involved;
    rule_id is R1..R7; message states the problem and the fix.
    """

    rule_id: str
    severity: str
    session_ids: list[str]
    message: str


class SequencingReport(TypedDict):
    """The sequencing check for one week: every violation plus block/warn counts.

    block_count is the number to drive to zero; warn_count must be acknowledged
    in the program notes. Empty violations with both counts zero means the week
    is clean.
    """

    violations: list[ViolationView]
    block_count: int
    warn_count: int


def check_week_sequencing(week: WeekPlan, strength_priority: bool = True) -> SequencingReport:
    """Check one week's session order for spacing and interference problems.

    Runs seven intra-week rules on the sessions' weekday field: same-pattern heavy
    spacing >=48h/72h (R1), no HIIT the day before lower-body heavy (R2), same-day
    strength-before-endurance when strength is the A goal (R3), at most two
    consecutive high days (R4), the match day -1/+1 windows (R5), no long endurance
    before a hard day (R6), and per-day minutes within the athlete's available time
    (R7). Match days and available minutes come from the stored calendar and
    profile. strength_priority=True when a strength/hypertrophy goal is A-priority.
    Drive block_count to zero; acknowledge every warn in the program notes.
    Sessions with no weekday are skipped -- assign weekdays first.
    """
    violations = sequencing.check_week_for_athlete(
        resolve_athlete_dir(), week, strength_priority=strength_priority
    )
    views = [
        ViolationView(
            rule_id=v.rule_id,
            severity=v.severity,
            session_ids=list(v.session_ids),
            message=v.message,
        )
        for v in violations
    ]
    return SequencingReport(
        violations=views,
        block_count=sum(1 for v in violations if v.severity == "block"),
        warn_count=sum(1 for v in violations if v.severity == "warn"),
    )


def get_time_context() -> TimeContext:
    """Current date plus days-since deltas and goal countdowns.

    Call this at conversation start and quote its numbers — never compute
    dates yourself. Negative days_remaining means the deadline is overdue;
    null deltas mean nothing has been logged yet (not "today").
    """
    return build_time_context(resolve_athlete_dir())


def list_due_actions() -> list[DueActionView]:
    """What the coach owes the athlete right now, most severe first (facts, not prose).

    Call this immediately after get_time_context and open with the top items. It
    reads the active program cadence, calendar, sessions, readiness and response
    profile to surface: an overdue check-in, an A/B event within three weeks
    (taper/peaking about to start), planned sessions missed this week, three-plus
    training days with no readiness read, an active goal whose deadline has no dated
    events, a response profile older than six weeks, and a streak of red readiness
    days. Each action is {kind, severity, due_since_days|due_in_days, message_key,
    ref}; render the message_key yourself in the athlete's language and quote the
    numbers. An all-green athlete returns []. Severity is high, medium or low.
    """
    return diligence.list_due_actions(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register every memory tool on the server."""
    for tool in (
        read_athlete,
        write_profile,
        upsert_goal,
        log_session,
        log_checkin,
        log_readiness,
        read_sessions,
        read_checkins,
        read_readiness,
        save_program,
        read_program,
        save_analysis,
        read_analysis,
        save_research_dossier,
        read_research_dossier,
        save_nutrition_frame,
        read_nutrition_frame,
        read_calendar,
        upsert_calendar_event,
        remove_calendar_event,
        set_recurring_constraints,
        build_season_plan,
        check_week_sequencing,
        get_time_context,
        list_due_actions,
    ):
        mcp.tool()(tool)
