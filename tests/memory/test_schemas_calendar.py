"""Validators for the calendar schemas and the new Availability.weekdays field."""

from datetime import date

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    Availability,
    Calendar,
    CalendarEvent,
    RecurringConstraint,
)


def test_calendar_event_requires_priority_and_label():
    with pytest.raises(ValidationError):
        # priority is required and label must be non-empty.
        CalendarEvent.model_validate(
            {"id": "r", "date": "2026-11-01", "kind": "competition", "label": ""}
        )


def test_calendar_event_id_is_a_slug():
    with pytest.raises(ValidationError):
        CalendarEvent(
            id="Race 1", date=date(2026, 11, 1), kind="competition", priority="A", label="x"
        )


def test_recurring_srpe_is_bounded_cr10():
    with pytest.raises(ValidationError):
        RecurringConstraint(weekday=2, kind="club_practice", est_srpe=11, label="club")


def test_recurring_weekday_is_bounded():
    with pytest.raises(ValidationError):
        RecurringConstraint(weekday=7, kind="match_day", label="match")


def test_calendar_defaults_are_empty():
    calendar = Calendar()
    assert calendar.events == []
    assert calendar.recurring == []
    assert calendar.schema_version == 1


def test_availability_weekdays_rejects_out_of_range():
    with pytest.raises(ValidationError, match="0-6"):
        Availability(sessions_per_week=3, minutes_per_session=60, weekdays=[0, 7])


def test_availability_weekdays_rejects_duplicates():
    with pytest.raises(ValidationError, match="unique"):
        Availability(sessions_per_week=3, minutes_per_session=60, weekdays=[1, 1])


def test_availability_weekdays_are_sorted():
    availability = Availability(sessions_per_week=3, minutes_per_session=60, weekdays=[4, 0, 2])
    assert availability.weekdays == [0, 2, 4]


def test_availability_weekdays_optional():
    assert Availability(sessions_per_week=3, minutes_per_session=60).weekdays is None
