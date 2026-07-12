"""Intra-week sequencing at the athlete layer: WeekPlan -> engine, then check.

The engine (engine/sequencing.py) is pydantic-free and works on engine-local
dataclasses; this module converts a WeekPlan and the week's recurring constraints
into that shape, supplies the athlete's per-day available minutes, calls the pure
checker, and returns its Violations. All WeekPlan / RecurringConstraint / Profile
handling lives here, never in the engine (purity + no cycle), mirroring the
engine/season.py <-> memory/season.py split.
"""

from pathlib import Path

from performance_agent.engine.sequencing import (
    RecurringInput,
    SessionInput,
    Violation,
)
from performance_agent.engine.sequencing import (
    check_week_sequencing as engine_check_week_sequencing,
)
from performance_agent.memory import store
from performance_agent.memory.schemas import RecurringConstraint, WeekPlan


def _to_engine_sessions(week: WeekPlan) -> list[SessionInput]:
    return [
        SessionInput(
            id=session.id,
            weekday=session.weekday,
            qualities=tuple(session.qualities),
            patterns=tuple(session.patterns),
            est_minutes=session.est_minutes,
        )
        for session in week.sessions
    ]


def _to_engine_recurring(recurring: list[RecurringConstraint]) -> list[RecurringInput]:
    return [
        RecurringInput(weekday=item.weekday, kind=item.kind, est_minutes=item.est_minutes)
        for item in recurring
    ]


def check_week(
    week: WeekPlan,
    recurring: list[RecurringConstraint],
    *,
    available_minutes: int | None = None,
    strength_priority: bool = True,
) -> list[Violation]:
    """Convert a WeekPlan + its recurring constraints to engine inputs and check it.

    available_minutes is the athlete's per-day training window (R7); strength_priority
    says a strength/hypertrophy goal is A-priority (drives the same-day ordering rule
    R3). Returns the pure engine Violations, deterministically sorted.
    """
    return engine_check_week_sequencing(
        _to_engine_sessions(week),
        _to_engine_recurring(recurring),
        volume_factor=week.volume_factor,
        strength_priority=strength_priority,
        available_minutes=available_minutes,
    )


def check_week_for_athlete(
    base_dir: Path, week: WeekPlan, *, strength_priority: bool = True
) -> list[Violation]:
    """Check one week against the athlete's stored calendar and availability.

    Pulls the weekly recurring constraints from calendar.yaml and the per-day
    available minutes from the profile's availability (minutes_per_session; None
    when no availability is recorded, which disables R7).
    """
    calendar = store.read_calendar(base_dir)
    profile = store.read_profile(base_dir)
    available = profile.availability.minutes_per_session if profile.availability else None
    return check_week(
        week,
        calendar.recurring,
        available_minutes=available,
        strength_priority=strength_priority,
    )
