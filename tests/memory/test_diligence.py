"""Memory-layer tests for list_due_actions: files in, correct facts out."""

from datetime import date, datetime, timedelta

from performance_agent.memory.diligence import list_due_actions
from performance_agent.memory.schemas import (
    CalendarEvent,
    CheckinEntry,
    Goal,
    Mesocycle,
    ProgramPlan,
    ReadinessEntry,
    ResponseProfile,
    SessionEntry,
    WeekPlan,
)
from performance_agent.memory.store import (
    append_checkin,
    append_readiness,
    append_session,
    save_program,
    save_response_profile,
    upsert_calendar_event,
    upsert_goal,
)
from performance_agent.memory.weekly_review import LOADS_REVIEW_STATE_FILE
from tests.program_plans import a_session, minimal_plan

TODAY = date(2026, 7, 13)


def _kinds(base_dir) -> list[str]:
    return [a["kind"] for a in list_due_actions(base_dir, today=TODAY)]


def _action(base_dir, kind: str):
    return next(a for a in list_due_actions(base_dir, today=TODAY) if a["kind"] == kind)


def _three_weekday_plan() -> ProgramPlan:
    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            a_session("w01-s1", weekday=0),
            a_session("w01-s2", weekday=2),
            a_session("w01-s3", weekday=4),
        ],
    )
    return minimal_plan(mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=[week])])


def test_empty_directory_is_all_green(tmp_path):
    assert list_due_actions(tmp_path, today=TODAY) == []


def test_fully_tended_athlete_is_all_green(tmp_path):
    # One-weekday plan, a session + green readiness two days ago, a recent check-in
    # and loads review, no dated deadline, no profile: nothing is due.
    save_program(tmp_path, minimal_plan())
    two_days_ago = datetime.combine(TODAY - timedelta(days=2), datetime.min.time().replace(hour=18))
    append_session(tmp_path, SessionEntry(performed_at=two_days_ago))
    append_readiness(
        tmp_path,
        ReadinessEntry(at=two_days_ago, sleep=1, fatigue=1, soreness=1, stress=1),
    )
    append_checkin(tmp_path, CheckinEntry(at=two_days_ago))
    (tmp_path / LOADS_REVIEW_STATE_FILE).write_text(
        f"last_run: {(TODAY - timedelta(days=1)).isoformat()}\n", encoding="utf-8"
    )
    assert list_due_actions(tmp_path, today=TODAY) == []


def test_overdue_checkin_is_surfaced(tmp_path):
    save_program(tmp_path, minimal_plan())
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 3, 9, 0)))  # 10 days before TODAY
    action = _action(tmp_path, "checkin")
    assert action["severity"] == "medium"
    assert action["message_key"] == "checkin_overdue"
    assert action["due_since_days"] == 10


def test_imminent_a_event_is_high(tmp_path):
    save_program(tmp_path, minimal_plan())
    append_checkin(tmp_path, CheckinEntry(at=datetime.combine(TODAY, datetime.min.time())))
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nationals",
            date=TODAY + timedelta(days=10),
            kind="competition",
            priority="A",
            label="Nationals",
        ),
    )
    action = _action(tmp_path, "event")
    assert action["severity"] == "high"
    assert action["due_in_days"] == 10
    assert action["ref"] == "nationals"


def test_missed_planned_sessions_go_high(tmp_path):
    # A three-day-a-week plan with nothing logged this week: three sessions missed.
    save_program(tmp_path, _three_weekday_plan())
    action = _action(tmp_path, "missed_sessions")
    assert action["severity"] == "high"
    assert action["due_since_days"] is None  # nothing logged, so no "since" anchor


def test_readiness_gap_on_recent_training_days(tmp_path):
    for offset in (2, 4, 6):
        performed = datetime.combine(
            TODAY - timedelta(days=offset), datetime.min.time().replace(hour=18)
        )
        append_session(tmp_path, SessionEntry(performed_at=performed))
    action = _action(tmp_path, "readiness_gap")
    assert action["severity"] == "medium"


def test_goal_deadline_without_events_flags_calendar(tmp_path):
    upsert_goal(
        tmp_path,
        Goal(id="squat-160", statement="Squat 160kg", deadline=TODAY + timedelta(days=90)),
    )
    action = _action(tmp_path, "calendar_incomplete")
    assert action["severity"] == "medium"


def test_deadline_with_a_dated_event_does_not_flag(tmp_path):
    upsert_goal(
        tmp_path,
        Goal(id="squat-160", statement="Squat 160kg", deadline=TODAY + timedelta(days=90)),
    )
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="meet",
            date=TODAY + timedelta(days=80),
            kind="competition",
            priority="A",
            label="Meet",
        ),
    )
    assert "calendar_incomplete" not in _kinds(tmp_path)


def test_stale_response_profile_is_low(tmp_path):
    save_response_profile(
        tmp_path,
        ResponseProfile(as_of=TODAY),
        today=TODAY - timedelta(days=50),
    )
    action = _action(tmp_path, "response_profile_stale")
    assert action["severity"] == "low"
    assert action["due_since_days"] == 50


def test_fresh_response_profile_is_not_flagged(tmp_path):
    save_response_profile(tmp_path, ResponseProfile(as_of=TODAY), today=TODAY - timedelta(days=20))
    assert "response_profile_stale" not in _kinds(tmp_path)


def test_readiness_red_streak_is_high(tmp_path):
    for offset in (5, 3, 1):
        at = datetime.combine(TODAY - timedelta(days=offset), datetime.min.time().replace(hour=7))
        append_readiness(tmp_path, ReadinessEntry(at=at, sleep=7, fatigue=7, soreness=7, stress=7))
    action = _action(tmp_path, "readiness_red_streak")
    assert action["severity"] == "high"
    assert action["due_since_days"] == 3


def test_actions_sorted_by_severity(tmp_path):
    save_program(tmp_path, minimal_plan())
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 20, 9, 0)))  # long overdue -> high
    save_response_profile(tmp_path, ResponseProfile(as_of=TODAY), today=TODAY - timedelta(days=60))
    severities = [a["severity"] for a in list_due_actions(tmp_path, today=TODAY)]
    assert severities == sorted(severities, key=["high", "medium", "low"].index)


def test_a_event_without_protocol_surfaces_competition_protocol(tmp_path):
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nationals",
            date=TODAY + timedelta(days=6),
            kind="competition",
            priority="A",
            label="Nationals",
        ),
    )
    action = _action(tmp_path, "competition_protocol")
    assert action["ref"] == "nationals"
    assert action["due_in_days"] == 6
