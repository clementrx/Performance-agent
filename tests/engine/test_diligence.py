"""Pure decision/ordering tests for engine/diligence.list_due_actions."""

from dataclasses import replace

import pytest

from performance_agent.engine.diligence import (
    DiligenceFacts,
    UpcomingEvent,
    list_due_actions,
)

# A green baseline (has a program, checked in recently); each test tweaks one facet.
_GREEN = DiligenceFacts(has_program=True, checkin_cadence_days=7, days_since_checkin=3)


def _facts(**overrides: object) -> DiligenceFacts:
    return replace(_GREEN, **overrides)


def _kinds(facts: DiligenceFacts) -> list[str]:
    return [a.kind for a in list_due_actions(facts)]


def test_all_green_yields_no_actions():
    assert list_due_actions(_facts()) == []


def test_checkin_overdue_is_medium_then_high():
    medium = list_due_actions(_facts(days_since_checkin=10))[0]
    assert medium.kind == "checkin"
    assert medium.severity == "medium"
    assert medium.message_key == "checkin_overdue"
    assert medium.due_since_days == 10
    high = list_due_actions(_facts(days_since_checkin=14))[0]
    assert high.severity == "high"


def test_checkin_exactly_on_cadence_is_not_overdue():
    assert list_due_actions(_facts(days_since_checkin=7)) == []


def test_never_checked_in_with_a_program_is_high():
    action = list_due_actions(_facts(days_since_checkin=None))[0]
    assert action.severity == "high"
    assert action.message_key == "checkin_never"


def test_no_program_means_no_checkin_nag():
    assert list_due_actions(_facts(has_program=False, days_since_checkin=None)) == []


def test_a_event_severity_by_days_out():
    near = list_due_actions(_facts(upcoming_events=(UpcomingEvent("race", "A", 14),)))[0]
    assert near.severity == "high"
    assert near.kind == "event"
    assert near.due_in_days == 14
    assert near.ref == "race"
    mid = list_due_actions(_facts(upcoming_events=(UpcomingEvent("race", "A", 15),)))[0]
    assert mid.severity == "medium"


def test_b_event_severity_by_days_out():
    imminent = list_due_actions(_facts(upcoming_events=(UpcomingEvent("tuneup", "B", 7),)))[0]
    assert imminent.severity == "medium"
    later = list_due_actions(_facts(upcoming_events=(UpcomingEvent("tuneup", "B", 8),)))[0]
    assert later.severity == "low"


def test_event_beyond_horizon_is_ignored():
    assert list_due_actions(_facts(upcoming_events=(UpcomingEvent("race", "A", 22),))) == []


def test_missed_sessions_high_at_three():
    two = list_due_actions(_facts(missed_session_count=2, days_since_last_session=4))[0]
    assert two.severity == "medium"
    assert two.due_since_days == 4
    three = list_due_actions(_facts(missed_session_count=3))[0]
    assert three.severity == "high"


def test_readiness_gap_fires_at_three_training_days():
    assert _kinds(_facts(training_days_without_readiness=2)) == []
    gap = list_due_actions(_facts(training_days_without_readiness=3))[0]
    assert gap.kind == "readiness_gap"
    assert gap.severity == "medium"


def test_calendar_incompleteness_is_flagged():
    action = list_due_actions(_facts(goal_deadline_without_events=True))[0]
    assert action.kind == "calendar_incomplete"
    assert action.severity == "medium"


def test_stale_profile_boundary():
    assert _kinds(_facts(profile_stale_days=42)) == []
    stale = list_due_actions(_facts(profile_stale_days=43))[0]
    assert stale.kind == "response_profile_stale"
    assert stale.severity == "low"
    assert stale.due_since_days == 43


def test_red_streak_medium_then_high():
    assert _kinds(_facts(readiness_red_streak=1)) == []
    medium = list_due_actions(_facts(readiness_red_streak=2))[0]
    assert medium.severity == "medium"
    high = list_due_actions(_facts(readiness_red_streak=3))[0]
    assert high.severity == "high"


def test_actions_are_ordered_by_severity():
    facts = _facts(
        days_since_checkin=14,  # checkin high
        profile_stale_days=60,  # low
        upcoming_events=(UpcomingEvent("tuneup", "B", 20),),  # low
        goal_deadline_without_events=True,  # medium
    )
    severities = [a.severity for a in list_due_actions(facts)]
    assert severities == sorted(severities, key=["high", "medium", "low"].index)
    assert severities[0] == "high"


def test_ties_break_on_urgency_soonest_event_first():
    facts = _facts(
        days_since_checkin=3,
        upcoming_events=(UpcomingEvent("far", "A", 10), UpcomingEvent("near", "A", 4)),
    )
    refs = [a.ref for a in list_due_actions(facts) if a.kind == "event"]
    assert refs == ["near", "far"]


def test_zero_cadence_is_rejected():
    with pytest.raises(ValueError, match="checkin_cadence_days"):
        list_due_actions(_facts(checkin_cadence_days=0))


def test_loads_review_due_when_sessions_logged_and_never_reviewed():
    facts = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=3,
        days_since_loads_review=None,
    )
    kinds = {action.kind for action in list_due_actions(facts)}
    assert "loads_review" in kinds


def test_loads_review_quiet_without_recent_sessions_or_when_fresh():
    quiet = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=0,
        days_since_loads_review=None,
    )
    fresh = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=3,
        days_since_loads_review=2,
    )
    for facts in (quiet, fresh):
        kinds = {action.kind for action in list_due_actions(facts)}
        assert "loads_review" not in kinds


def test_program_watch_due_after_fourteen_days():
    facts = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        days_since_watch_anchor=15,
    )
    kinds = {action.kind for action in list_due_actions(facts)}
    assert "program_watch" in kinds


def test_program_watch_quiet_when_recent_or_no_program():
    recent = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        days_since_watch_anchor=13,
    )
    no_program = DiligenceFacts(
        has_program=False,
        checkin_cadence_days=7,
        days_since_watch_anchor=100,
    )
    for facts in (recent, no_program):
        kinds = {action.kind for action in list_due_actions(facts)}
        assert "program_watch" not in kinds
