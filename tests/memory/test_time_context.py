from datetime import date, datetime

from performance_agent.memory.schemas import CheckinEntry, Goal, SessionEntry
from performance_agent.memory.store import append_checkin, append_session, upsert_goal
from performance_agent.memory.time_context import build_time_context

TODAY = date(2026, 7, 10)


def test_empty_directory_yields_null_deltas(tmp_path):
    context = build_time_context(tmp_path, today=TODAY)
    assert context["today"] == "2026-07-10"
    assert context["days_since_last_session"] is None
    assert context["days_since_last_checkin"] is None
    assert context["goals"] == []


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
