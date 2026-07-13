"""Proactive follow-up: decide which coaching actions are due, and how urgent.

The MCP server is stdio request/response and cannot push, so "what is due" is
centralised in a tool the ritual calls first. This module holds the PURE decision
and ordering logic: given facts already extracted by the memory layer (days
overdue, days until an event, missing counts, staleness), it produces the ordered
list of due actions with severities. All file reading and date math live in
memory/diligence.py, mirroring the engine/season.py <-> memory/season.py split, so
the engine stays deterministic and datetime-free.

The result is FACTS, never prose: each action carries a stable message_key plus the
numbers; the locale-aware sentence is rendered by the LLM. Every threshold here is a
team-chosen prior (no corpus rule prescribes when a coach should reach out).
"""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["high", "medium", "low"]

# --- Thresholds (all team-chosen priors) ----------------------------------
# A check-in is overdue past its cadence; being a full extra cadence late is high.
# Events within three weeks are worth surfacing (taper/peaking is about to start).
_EVENT_HORIZON_DAYS = 21
_EVENT_IMMINENT_DAYS = 7
_EVENT_NEAR_DAYS = 14
# Missing >=3 planned sessions, or >=3 readiness reads on training days, is serious.
_MISSED_SESSIONS_HIGH = 3
_READINESS_GAP_MIN = 3
# A response profile older than six weeks no longer reflects the current athlete.
_PROFILE_STALE_DAYS = 42
# Two reds in a row is a medium concern; three-plus is high (persistent under-recovery).
_RED_STREAK_MEDIUM = 2
_RED_STREAK_HIGH = 3

_SEVERITY_RANK: dict[Severity, int] = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class UpcomingEvent:
    """A dated A/B event within the follow-up horizon, in whole days from today."""

    event_id: str
    priority: str  # "A" or "B"
    days_until: int


@dataclass(frozen=True)
class DiligenceFacts:
    """Everything the pure planner needs, already extracted from athlete files.

    has_program gates check-in nagging (no program => no cadence expectation).
    days_since_checkin is None when nothing has ever been logged. profile_stale_days
    is None when no response profile exists (staleness only applies once one does).
    """

    has_program: bool
    checkin_cadence_days: int
    days_since_checkin: int | None = None
    upcoming_events: tuple[UpcomingEvent, ...] = ()
    missed_session_count: int = 0
    days_since_last_session: int | None = None
    training_days_without_readiness: int = 0
    goal_deadline_without_events: bool = False
    profile_stale_days: int | None = None
    readiness_red_streak: int = 0


@dataclass(frozen=True)
class DueAction:
    """One action the coach owes the athlete, as facts (the LLM renders the words).

    message_key is a stable, locale-neutral key; exactly one of due_since_days /
    due_in_days is set (overdue vs upcoming). ref names the subject (e.g. an event
    id) when one applies.
    """

    kind: str
    severity: Severity
    message_key: str
    due_since_days: int | None = None
    due_in_days: int | None = None
    ref: str | None = None


def _checkin_action(facts: DiligenceFacts) -> DueAction | None:
    if not facts.has_program:
        return None
    if facts.days_since_checkin is None:
        return DueAction("checkin", "high", "checkin_never", ref=None)
    overdue_by = facts.days_since_checkin - facts.checkin_cadence_days
    if overdue_by <= 0:
        return None
    severity: Severity = "high" if overdue_by >= facts.checkin_cadence_days else "medium"
    return DueAction(
        "checkin", severity, "checkin_overdue", due_since_days=facts.days_since_checkin
    )


def _event_action(event: UpcomingEvent) -> DueAction | None:
    if event.days_until > _EVENT_HORIZON_DAYS:
        return None
    if event.priority == "A":
        severity: Severity = "high" if event.days_until <= _EVENT_NEAR_DAYS else "medium"
    else:
        severity = "medium" if event.days_until <= _EVENT_IMMINENT_DAYS else "low"
    return DueAction(
        "event", severity, "event_approaching", due_in_days=event.days_until, ref=event.event_id
    )


def _missed_sessions_action(facts: DiligenceFacts) -> DueAction | None:
    if facts.missed_session_count <= 0:
        return None
    severity: Severity = "high" if facts.missed_session_count >= _MISSED_SESSIONS_HIGH else "medium"
    return DueAction(
        "missed_sessions",
        severity,
        "missed_sessions",
        due_since_days=facts.days_since_last_session,
    )


def _readiness_gap_action(facts: DiligenceFacts) -> DueAction | None:
    if facts.training_days_without_readiness < _READINESS_GAP_MIN:
        return None
    return DueAction("readiness_gap", "medium", "readiness_gap")


def _calendar_action(facts: DiligenceFacts) -> DueAction | None:
    if not facts.goal_deadline_without_events:
        return None
    return DueAction("calendar_incomplete", "medium", "calendar_incomplete")


def _profile_action(facts: DiligenceFacts) -> DueAction | None:
    if facts.profile_stale_days is None or facts.profile_stale_days <= _PROFILE_STALE_DAYS:
        return None
    return DueAction(
        "response_profile_stale",
        "low",
        "response_profile_stale",
        due_since_days=facts.profile_stale_days,
    )


def _red_streak_action(facts: DiligenceFacts) -> DueAction | None:
    if facts.readiness_red_streak < _RED_STREAK_MEDIUM:
        return None
    severity: Severity = "high" if facts.readiness_red_streak >= _RED_STREAK_HIGH else "medium"
    return DueAction(
        "readiness_red_streak",
        severity,
        "readiness_red_streak",
        due_since_days=facts.readiness_red_streak,
    )


def _sort_key(action: DueAction) -> tuple[int, int, str, str]:
    # Severity first; then most urgent (soonest upcoming, longest overdue); then a
    # stable tiebreak on kind + ref so the order is fully deterministic.
    if action.due_in_days is not None:
        urgency = action.due_in_days
    else:
        urgency = -(action.due_since_days or 0)
    return (_SEVERITY_RANK[action.severity], urgency, action.kind, action.ref or "")


def list_due_actions(facts: DiligenceFacts) -> list[DueAction]:
    """Order every due coaching action by severity, most urgent first.

    Pure and deterministic: the memory layer supplies already-extracted facts and
    this returns the sorted list of DueAction. An all-green athlete yields [].
    """
    if facts.checkin_cadence_days < 1:
        msg = f"checkin_cadence_days must be >= 1, got {facts.checkin_cadence_days!r}"
        raise ValueError(msg)
    candidates: list[DueAction | None] = [
        _checkin_action(facts),
        _missed_sessions_action(facts),
        _readiness_gap_action(facts),
        _calendar_action(facts),
        _profile_action(facts),
        _red_streak_action(facts),
    ]
    candidates.extend(_event_action(event) for event in facts.upcoming_events)
    actions = [action for action in candidates if action is not None]
    return sorted(actions, key=_sort_key)


__all__ = [
    "DiligenceFacts",
    "DueAction",
    "Severity",
    "UpcomingEvent",
    "list_due_actions",
]
