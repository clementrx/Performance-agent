"""Temporal awareness: date deltas the coach quotes instead of trusting its clock."""

from datetime import date
from pathlib import Path
from typing import TypedDict

from performance_agent.memory import store


class GoalTimeView(TypedDict):
    """Countdown view of one active goal."""

    goal_id: str
    statement: str
    deadline: str | None
    days_remaining: int | None
    weeks_remaining: float | None


class CalendarEventView(TypedDict):
    """Countdown view of one upcoming A/B calendar event."""

    event_id: str
    date: str
    priority: str
    kind: str
    days_until: int
    label: str


class RecurringView(TypedDict):
    """One weekly recurring constraint active every week."""

    weekday: int
    kind: str
    est_minutes: int | None
    est_srpe: float | None
    label: str


class TimeContext(TypedDict):
    """Everything date-related the coach needs at conversation start."""

    today: str
    last_session_on: str | None
    days_since_last_session: int | None
    last_checkin_on: str | None
    days_since_last_checkin: int | None
    goals: list[GoalTimeView]
    next_events: list[CalendarEventView]
    recurring_constraints: list[RecurringView]


def _goal_view(goal_id: str, statement: str, deadline: date | None, current: date) -> GoalTimeView:
    days = (deadline - current).days if deadline else None
    return GoalTimeView(
        goal_id=goal_id,
        statement=statement,
        deadline=deadline.isoformat() if deadline else None,
        days_remaining=days,
        weeks_remaining=round(days / 7, 1) if days is not None else None,
    )


def _next_events(base_dir: Path, current: date) -> list[CalendarEventView]:
    """Upcoming A/B events (today or later), soonest first."""
    calendar = store.read_calendar(base_dir)
    upcoming = [
        CalendarEventView(
            event_id=event.id,
            date=event.date.isoformat(),
            priority=event.priority,
            kind=event.kind,
            days_until=(event.date - current).days,
            label=event.label,
        )
        for event in calendar.events
        if event.priority in ("A", "B") and event.date >= current
    ]
    upcoming.sort(key=lambda view: view["date"])
    return upcoming


def _recurring(base_dir: Path) -> list[RecurringView]:
    return [
        RecurringView(
            weekday=constraint.weekday,
            kind=constraint.kind,
            est_minutes=constraint.est_minutes,
            est_srpe=constraint.est_srpe,
            label=constraint.label,
        )
        for constraint in store.read_calendar(base_dir).recurring
    ]


def build_time_context(base_dir: Path, today: date | None = None) -> TimeContext:
    """Compute all date deltas from stored facts (deterministic via `today`)."""
    current = today or date.today()
    last_session = max((s.performed_at.date() for s in store.read_sessions(base_dir)), default=None)
    last_checkin = max((c.at.date() for c in store.read_checkins(base_dir)), default=None)
    goals = [
        _goal_view(goal.id, goal.statement, goal.deadline, current)
        for goal in store.read_goals(base_dir)
        if goal.status == "active"
    ]
    return TimeContext(
        today=current.isoformat(),
        last_session_on=last_session.isoformat() if last_session else None,
        days_since_last_session=(current - last_session).days if last_session else None,
        last_checkin_on=last_checkin.isoformat() if last_checkin else None,
        days_since_last_checkin=(current - last_checkin).days if last_checkin else None,
        goals=goals,
        next_events=_next_events(base_dir, current),
        recurring_constraints=_recurring(base_dir),
    )
