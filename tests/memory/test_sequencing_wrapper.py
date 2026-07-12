"""The athlete-layer sequencing check: WeekPlan + stored calendar/profile."""

from performance_agent.memory.schemas import (
    Availability,
    ExerciseBlock,
    Fallbacks,
    Profile,
    RecurringConstraint,
    SessionPlan,
    WeekPlan,
)
from performance_agent.memory.sequencing import check_week, check_week_for_athlete
from performance_agent.memory.store import set_recurring_constraints, write_profile


def _fallbacks() -> Fallbacks:
    return Fallbacks(low_readiness="RPE 7", short_on_time="A only", missing_equipment="goblet")


def _session(session_id: str, weekday: int, qualities, patterns, minutes: int = 60) -> SessionPlan:
    return SessionPlan(
        id=session_id,
        weekday=weekday,
        qualities=qualities,
        patterns=patterns,
        est_minutes=minutes,
        purpose="work",
        blocks=[
            ExerciseBlock(
                exercise="Back Squat",
                priority="primary",
                sets=3,
                reps="5",
                rir=2.0,
                rest_s=120,
                progression_rule="double_progression",
            )
        ],
        fallbacks=_fallbacks(),
    )


def _week(sessions) -> WeekPlan:
    return WeekPlan(week_index=1, volume_factor=1.0, intensity_factor=0.9, sessions=sessions)


def test_converts_and_flags_a_same_pattern_clash():
    week = _week(
        [
            _session("mon", 0, ["strength_heavy"], ["squat"]),
            _session("tue", 1, ["strength_heavy"], ["squat"]),
        ]
    )
    violations = check_week(week, [])
    assert [v.rule_id for v in violations] == ["R1"]


def test_clean_week_passes():
    week = _week(
        [
            _session("mon", 0, ["strength_heavy"], ["squat"]),
            _session("thu", 3, ["strength_heavy"], ["push_h"]),
        ]
    )
    assert check_week(week, []) == []


def test_recurring_match_day_drives_r5():
    week = _week([_session("legs", 1, ["strength_heavy"], ["squat"])])
    recurring = [RecurringConstraint(weekday=2, kind="match_day", label="league")]
    assert [v.rule_id for v in check_week(week, recurring)] == ["R5"]


def test_athlete_wrapper_reads_calendar_and_availability(tmp_path):
    write_profile(
        tmp_path,
        Profile(availability=Availability(sessions_per_week=3, minutes_per_session=90)),
    )
    set_recurring_constraints(
        tmp_path, [RecurringConstraint(weekday=2, kind="match_day", label="league")]
    )
    # Heavy day the day before the match (R5) AND 120 min > 90 available (R7).
    week = _week([_session("legs", 1, ["strength_heavy"], ["squat"], minutes=120)])
    rule_ids = {v.rule_id for v in check_week_for_athlete(tmp_path, week)}
    assert rule_ids == {"R5", "R7"}


def test_athlete_wrapper_without_availability_disables_r7(tmp_path):
    week = _week([_session("legs", 0, ["strength_heavy"], ["squat"], minutes=480)])
    assert check_week_for_athlete(tmp_path, week) == []


def test_strength_priority_toggle_controls_r3(tmp_path):
    week = _week(
        [
            _session("lift", 0, ["strength_heavy"], ["squat"]),
            _session("run", 0, ["endurance_easy"], ["run"]),
        ]
    )
    assert [v.rule_id for v in check_week_for_athlete(tmp_path, week)] == ["R3"]
    assert check_week_for_athlete(tmp_path, week, strength_priority=False) == []
