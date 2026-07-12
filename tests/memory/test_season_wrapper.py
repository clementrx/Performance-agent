"""The athlete-layer season planner: date <-> week conversion and horizon."""

from datetime import date

import pytest

from performance_agent.memory.schemas import CalendarEvent, Goal
from performance_agent.memory.season import build_season_plan
from performance_agent.memory.store import upsert_calendar_event, upsert_goal

START = date(2026, 7, 13)  # a Monday


def _event(event_id, event_date, priority="A"):
    return CalendarEvent(
        id=event_id, date=event_date, kind="competition", priority=priority, label=event_id
    )


def test_no_events_falls_back_to_open_ended(tmp_path):
    view = build_season_plan(tmp_path, today=START)
    assert len(view["segments"]) == 1
    assert view["segments"][0]["anchor_event_id"] is None


def test_horizon_extends_to_the_goal_deadline_when_no_events(tmp_path):
    upsert_goal(tmp_path, Goal(id="g", statement="race", deadline=date(2026, 10, 5)))
    view = build_season_plan(tmp_path, today=START)
    # Oct 5 is 84 days (12 full weeks) after Jul 13 → falls in week 13.
    assert view["horizon_weeks"] == 13


def test_a_event_produces_taper_before_competition_with_dates(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 2)))  # a Monday, 16 weeks out
    view = build_season_plan(tmp_path, modality="endurance", today=START)
    phases = [s["phase_type"] for s in view["segments"]]
    assert "taper" in phases
    assert phases[-1] == "competition"
    comp = view["segments"][-1]
    assert comp["start_date"] == "2026-11-02"


def test_secondary_events_are_surfaced(tmp_path):
    upsert_calendar_event(tmp_path, _event("race", date(2026, 11, 2)))
    upsert_calendar_event(tmp_path, _event("tuneup", date(2026, 9, 14), priority="B"))
    view = build_season_plan(tmp_path, today=START)
    ids = [e["event_id"] for e in view["secondary_events"]]
    assert ids == ["tuneup"]


def test_past_event_is_rejected(tmp_path):
    upsert_calendar_event(tmp_path, _event("stale", date(2026, 6, 1)))
    with pytest.raises(ValueError, match="before the plan start"):
        build_season_plan(tmp_path, today=START)
