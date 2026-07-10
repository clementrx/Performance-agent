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


class TimeContext(TypedDict):
    """Everything date-related the coach needs at conversation start."""

    today: str
    last_session_on: str | None
    days_since_last_session: int | None
    last_checkin_on: str | None
    days_since_last_checkin: int | None
    goals: list[GoalTimeView]


def _goal_view(goal_id: str, statement: str, deadline: date | None, current: date) -> GoalTimeView:
    days = (deadline - current).days if deadline else None
    return GoalTimeView(
        goal_id=goal_id,
        statement=statement,
        deadline=deadline.isoformat() if deadline else None,
        days_remaining=days,
        weeks_remaining=round(days / 7, 1) if days is not None else None,
    )


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
    )
