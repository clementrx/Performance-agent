from datetime import date
from typing import Literal

from performance_agent.memory.schemas import CalendarEvent, RecurringConstraint
from performance_agent.memory.store import (
    read_calendar,
    remove_calendar_event,
    set_recurring_constraints,
    upsert_calendar_event,
)


def _event(
    event_id: str, event_date: date, priority: Literal["A", "B", "C"] = "A"
) -> CalendarEvent:
    return CalendarEvent(
        id=event_id, date=event_date, kind="competition", priority=priority, label=event_id
    )


def test_empty_calendar_reads_as_default(tmp_path):
    calendar = read_calendar(tmp_path)
    assert calendar.events == []
    assert calendar.recurring == []
    assert calendar.schema_version == 1


def test_upsert_adds_and_keeps_events_date_sorted(tmp_path):
    upsert_calendar_event(tmp_path, _event("late", date(2026, 11, 1)))
    upsert_calendar_event(tmp_path, _event("early", date(2026, 9, 1)))
    events = read_calendar(tmp_path).events
    assert [e.id for e in events] == ["early", "late"]


def test_upsert_replaces_same_id(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 1)))
    upsert_calendar_event(tmp_path, _event("race", date(2026, 12, 1)))
    events = read_calendar(tmp_path).events
    assert len(events) == 1
    assert events[0].date == date(2026, 12, 1)


def test_remove_event(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 1)))
    remove_calendar_event(tmp_path, "race")
    assert read_calendar(tmp_path).events == []


def test_remove_absent_event_is_a_noop(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 1)))
    remove_calendar_event(tmp_path, "ghost")
    assert len(read_calendar(tmp_path).events) == 1


def test_set_recurring_replaces_whole_list(tmp_path):
    set_recurring_constraints(
        tmp_path, [RecurringConstraint(weekday=2, kind="club_practice", label="club")]
    )
    set_recurring_constraints(
        tmp_path, [RecurringConstraint(weekday=5, kind="match_day", label="match")]
    )
    recurring = read_calendar(tmp_path).recurring
    assert len(recurring) == 1
    assert recurring[0].weekday == 5


def test_events_and_recurring_persist_together(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 1)))
    set_recurring_constraints(
        tmp_path, [RecurringConstraint(weekday=2, kind="club_practice", label="club")]
    )
    calendar = read_calendar(tmp_path)
    assert len(calendar.events) == 1
    assert len(calendar.recurring) == 1
