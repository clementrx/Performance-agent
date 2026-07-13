"""Proactive follow-up at the athlete layer: read the files, call the pure planner.

The engine (engine/diligence.py) is datetime-free and decides/orders due actions
from already-extracted facts; this module does all the reading and date math —
time context, the active program's cadence, the calendar, sessions, readiness and
the response profile — packs them into DiligenceFacts, and maps the engine's
DueAction list into a JSON-friendly view. Mirrors the engine/season.py <->
memory/season.py split. Deterministic given `today`.

Window lengths here (recent-session and readiness lookbacks) are team-chosen priors.
"""

from datetime import date
from pathlib import Path
from typing import TypedDict

from performance_agent.engine.diligence import (
    DiligenceFacts,
    UpcomingEvent,
)
from performance_agent.engine.diligence import list_due_actions as list_due_actions_engine
from performance_agent.engine.load import readiness_score
from performance_agent.memory import store
from performance_agent.memory.schemas import ProgramPlan, ReadinessEntry
from performance_agent.memory.time_context import TimeContext, build_time_context

# Team-chosen priors: how far back "recently missed a session" and "no readiness on
# a training day" look. Seven days is one microcycle; readiness gaps accrue over two.
_MISSED_WINDOW_DAYS = 7
_READINESS_WINDOW_DAYS = 14
_EVENT_HORIZON_DAYS = 21


class DueActionView(TypedDict):
    """One due coaching action as facts (the LLM renders the locale-aware sentence).

    message_key is stable and locale-neutral; exactly one of due_since_days /
    due_in_days is set (overdue vs upcoming); ref names the subject (e.g. an event
    id) when one applies.
    """

    kind: str
    severity: str
    message_key: str
    due_since_days: int | None
    due_in_days: int | None
    ref: str | None


def _weekly_session_frequency(plan: ProgramPlan) -> int:
    """Distinct planned training weekdays across the program (its weekly rhythm)."""
    weekdays = {
        session.weekday
        for meso in plan.mesocycles
        for week in meso.weeks
        for session in week.sessions
        if session.weekday is not None
    }
    return len(weekdays)


def _missed_session_count(base_dir: Path, plan: ProgramPlan | None, current: date) -> int:
    """Expected weekly training days minus sessions actually logged in the last week."""
    if plan is None:
        return 0
    expected = _weekly_session_frequency(plan)
    if expected == 0:
        return 0
    logged = sum(
        1
        for entry in store.read_sessions(base_dir)
        if 0 <= (current - entry.performed_at.date()).days < _MISSED_WINDOW_DAYS
    )
    return max(0, expected - logged)


def _training_days_without_readiness(base_dir: Path, current: date) -> int:
    """Count recent days with a logged session but no readiness read on that date."""
    training_days = {
        entry.performed_at.date()
        for entry in store.read_sessions(base_dir)
        if 0 <= (current - entry.performed_at.date()).days < _READINESS_WINDOW_DAYS
    }
    readiness_days = {
        entry.at.date()
        for entry in store.read_readiness(base_dir)
        if 0 <= (current - entry.at.date()).days < _READINESS_WINDOW_DAYS
    }
    return len(training_days - readiness_days)


def _goal_deadline_without_events(base_dir: Path) -> bool:
    """True when an active goal has a deadline but the calendar has no dated events."""
    has_deadline = any(
        goal.status == "active" and goal.deadline is not None for goal in store.read_goals(base_dir)
    )
    return has_deadline and not store.read_calendar(base_dir).events


def _profile_stale_days(base_dir: Path, current: date) -> int | None:
    """Days since the latest response profile's as_of date, or None when there is none."""
    profile = store.read_response_profile(base_dir)
    if profile is None:
        return None
    return (current - profile.as_of).days


def _readiness_band(entry: ReadinessEntry) -> str:
    return readiness_score(entry.sleep, entry.fatigue, entry.soreness, entry.stress).band


def _readiness_red_streak(base_dir: Path, current: date) -> int:
    """Length of the trailing run of red readiness reads within the recent window."""
    recent = [
        entry
        for entry in store.read_readiness(base_dir)
        if 0 <= (current - entry.at.date()).days < _READINESS_WINDOW_DAYS
    ]
    recent.sort(key=lambda entry: entry.at)
    streak = 0
    for entry in reversed(recent):
        if _readiness_band(entry) != "red":
            break
        streak += 1
    return streak


def _upcoming_events(context: TimeContext) -> tuple[UpcomingEvent, ...]:
    events = [
        UpcomingEvent(
            event_id=event["event_id"],
            priority=event["priority"],
            days_until=event["days_until"],
        )
        for event in context["next_events"]
        if event["priority"] in ("A", "B") and 0 <= event["days_until"] <= _EVENT_HORIZON_DAYS
    ]
    return tuple(events)


def _build_facts(base_dir: Path, current: date) -> DiligenceFacts:
    context = build_time_context(base_dir, today=current)
    program = store.read_program(base_dir)
    plan = program.plan if program is not None else None
    cadence = plan.checkin_cadence_days if plan is not None else 7
    return DiligenceFacts(
        has_program=program is not None,
        checkin_cadence_days=cadence,
        days_since_checkin=context["days_since_last_checkin"],
        upcoming_events=_upcoming_events(context),
        missed_session_count=_missed_session_count(base_dir, plan, current),
        days_since_last_session=context["days_since_last_session"],
        training_days_without_readiness=_training_days_without_readiness(base_dir, current),
        goal_deadline_without_events=_goal_deadline_without_events(base_dir),
        profile_stale_days=_profile_stale_days(base_dir, current),
        readiness_red_streak=_readiness_red_streak(base_dir, current),
    )


def list_due_actions(base_dir: Path, today: date | None = None) -> list[DueActionView]:
    """Read the athlete's files and return every due action, most severe first."""
    current = today or date.today()
    actions = list_due_actions_engine(_build_facts(base_dir, current))
    return [
        DueActionView(
            kind=action.kind,
            severity=action.severity,
            message_key=action.message_key,
            due_since_days=action.due_since_days,
            due_in_days=action.due_in_days,
            ref=action.ref,
        )
        for action in actions
    ]
