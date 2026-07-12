from datetime import date, datetime

from performance_agent.memory.schemas import (
    CalendarEvent,
    CheckinEntry,
    Goal,
    RecurringConstraint,
    SessionEntry,
)
from performance_agent.memory.store import (
    append_checkin,
    append_session,
    set_recurring_constraints,
    upsert_calendar_event,
    upsert_goal,
)
from performance_agent.memory.time_context import build_time_context

TODAY = date(2026, 7, 10)


def test_empty_directory_yields_null_deltas(tmp_path):
    context = build_time_context(tmp_path, today=TODAY)
    assert context["today"] == "2026-07-10"
    assert context["days_since_last_session"] is None
    assert context["days_since_last_checkin"] is None
    assert context["goals"] == []
    assert context["next_events"] == []
    assert context["recurring_constraints"] == []


def test_next_events_lists_future_ab_events_soonest_first(tmp_path):
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="race-a", date=date(2026, 11, 1), kind="competition", priority="A", label="Marathon"
        ),
    )
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="tuneup", date=date(2026, 9, 1), kind="competition", priority="B", label="10k"
        ),
    )
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="past", date=date(2026, 6, 1), kind="competition", priority="A", label="old"
        ),
    )
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="fun", date=date(2026, 10, 1), kind="other", priority="C", label="parkrun"
        ),
    )
    events = build_time_context(tmp_path, today=TODAY)["next_events"]
    # C events and past events are excluded; soonest first.
    assert [e["event_id"] for e in events] == ["tuneup", "race-a"]
    assert events[0]["days_until"] == (date(2026, 9, 1) - TODAY).days


def test_recurring_constraints_are_surfaced(tmp_path):
    set_recurring_constraints(
        tmp_path,
        [
            RecurringConstraint(
                weekday=2, kind="club_practice", est_minutes=90, est_srpe=6, label="Club run"
            )
        ],
    )
    recurring = build_time_context(tmp_path, today=TODAY)["recurring_constraints"]
    assert len(recurring) == 1
    assert recurring[0]["kind"] == "club_practice"
    assert recurring[0]["est_srpe"] == 6


def test_deltas_come_from_the_most_recent_entries(tmp_path):
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 6, 20, 18, 0)))
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 6, 26, 18, 0)))
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    context = build_time_context(tmp_path, today=TODAY)
    assert context["last_session_on"] == "2026-06-26"
    assert context["days_since_last_session"] == 14
    assert context["days_since_last_checkin"] == 14


def test_goal_countdowns_only_for_active_goals(tmp_path):
    upsert_goal(
        tmp_path,
        Goal(id="sub-45-10k", statement="10K under 45:00", deadline=date(2026, 10, 30)),
    )
    upsert_goal(
        tmp_path,
        Goal(id="done", statement="done", deadline=date(2026, 8, 1), status="achieved"),
    )
    context = build_time_context(tmp_path, today=TODAY)
    assert len(context["goals"]) == 1
    view = context["goals"][0]
    assert view["goal_id"] == "sub-45-10k"
    assert view["days_remaining"] == 112
    assert view["weeks_remaining"] == 16.0


def test_goal_without_deadline_has_null_countdown(tmp_path):
    upsert_goal(tmp_path, Goal(id="open-goal", statement="get stronger"))
    view = build_time_context(tmp_path, today=TODAY)["goals"][0]
    assert view["deadline"] is None
    assert view["days_remaining"] is None
    assert view["weeks_remaining"] is None


def test_overdue_goal_has_negative_days(tmp_path):
    upsert_goal(tmp_path, Goal(id="past", statement="past race", deadline=date(2026, 7, 1)))
    view = build_time_context(tmp_path, today=TODAY)["goals"][0]
    assert view["days_remaining"] == -9
