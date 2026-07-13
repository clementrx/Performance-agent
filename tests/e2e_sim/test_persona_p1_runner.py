"""Persona P1 — endurance runner (10K goal, 3 runs + 2 S&C slots per week).

Exercises: season-plan P1 invariants (tile the horizon, taper before the A race),
zero `block` sequencing violations in every generated week, response-profile
recovery of an injected 0.6%/week strength progression within +/-0.2 points, and
that injected implausible log entries are flagged and excluded from the profile.
Every program version is saved with a reason.
"""

from datetime import timedelta
from itertools import pairwise

import pytest

from performance_agent.memory import store
from performance_agent.memory.monitoring import session_plausibility_flags
from performance_agent.memory.response import compute_response_profile
from performance_agent.memory.schemas import Availability as Avail
from performance_agent.memory.schemas import CalendarEvent, Goal, Profile
from performance_agent.memory.season import build_season_plan
from performance_agent.memory.sequencing import check_week_for_athlete
from tests.e2e_sim import harness as h

RACE_WEEK = 14
WEEKS = 14
TRUE_RATE = 0.006  # injected true weekly progression on the tracked lift
BASE_SQUAT = 120.0


def _week_sessions(base_squat: float) -> list:
    """One microcycle: 3 runs (Mon easy, Wed intervals, Sat long) + 2 lifts."""
    return [
        h.run_session("mon-easy", 0, "endurance_easy", 40, 4),
        h.strength_session("tue-lift", 1, patterns=["squat", "hinge"], load_kg=base_squat),
        h.run_session("wed-int", 2, "hiit", 45, 8),
        h.strength_session("fri-lift", 4, patterns=["squat", "hinge"], load_kg=base_squat),
        h.run_session("sat-long", 5, "endurance_long", 80, 5),
    ]


def _seed_athlete(base_dir):
    store.write_profile(
        base_dir,
        Profile(
            training_age="intermediate",
            sport="running",
            availability=Avail(
                sessions_per_week=5, minutes_per_session=90, weekdays=[0, 1, 2, 4, 5]
            ),
        ),
    )
    store.upsert_goal(
        base_dir,
        Goal(
            id="run-10k",
            statement="Run 10K under 45 minutes",
            metric="10k time",
            deadline=h.ORIGIN + timedelta(weeks=RACE_WEEK - 1),
        ),
    )
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="city10k",
            date=h.ORIGIN + timedelta(weeks=RACE_WEEK - 1),
            kind="competition",
            priority="A",
            label="City 10K",
            goal_id="run-10k",
        ),
    )


def test_season_plan_p1_invariants(tmp_path):
    _seed_athlete(tmp_path)
    plan = build_season_plan(tmp_path, modality="endurance", today=h.ORIGIN)
    segments = plan["segments"]
    # Segments tile the horizon with no gap or overlap.
    assert segments[0]["start_week"] == 1
    for earlier, later in pairwise(segments):
        assert later["start_week"] == earlier["end_week"] + 1
    assert segments[-1]["end_week"] == plan["horizon_weeks"]
    # A taper lands immediately before the A race, then the competition week.
    tapers = [s for s in segments if s["phase_type"] == "taper"]
    comps = [s for s in segments if s["phase_type"] == "competition"]
    assert any(s["end_week"] == RACE_WEEK - 1 for s in tapers)
    assert any(s["start_week"] == RACE_WEEK and s["end_week"] == RACE_WEEK for s in comps)


def test_every_generated_week_has_zero_block_violations(tmp_path):
    _seed_athlete(tmp_path)
    weeks = [_week_sessions(BASE_SQUAT * (1 + TRUE_RATE * w)) for w in range(WEEKS)]
    program = h.program_from_weeks(
        "run-10k", weeks, season_ref="City 10K in 14 weeks", test_milestone_week=8
    )
    store.save_program(tmp_path, program, reason="initial season plan", today=h.ORIGIN)
    for meso in program.mesocycles:
        for week in meso.weeks:
            violations = check_week_for_athlete(tmp_path, week)
            assert [v for v in violations if v.severity == "block"] == []


def _simulate_logs(base_dir, generator):
    """Log 14 weeks of clean sessions + green readiness; squat progresses at TRUE_RATE."""
    for week in range(WEEKS):
        squat = h.jitter(generator, BASE_SQUAT * (1 + TRUE_RATE * week), 0.01)
        for weekday, plan_id in ((1, "tue-lift"), (4, "fri-lift")):
            offset = h.week_day_offset(week + 1, weekday)
            store.append_session(base_dir, h.squat_log(offset, squat, plan_id))
            store.append_readiness(
                base_dir, h.readiness_log(offset, sleep=2, fatigue=2, soreness=2, stress=2)
            )


def test_response_profile_recovers_injected_rate(tmp_path):
    _seed_athlete(tmp_path)
    weeks = [_week_sessions(BASE_SQUAT * (1 + TRUE_RATE * w)) for w in range(WEEKS)]
    store.save_program(
        tmp_path, h.program_from_weeks("run-10k", weeks), reason="v1", today=h.ORIGIN
    )
    _simulate_logs(tmp_path, h.rng(101))
    profile = compute_response_profile(tmp_path, today=h.ORIGIN + timedelta(weeks=WEEKS))
    assert profile.per_goal_measured_rate is not None
    # +/-0.2 percentage points on a fractional weekly rate.
    assert profile.per_goal_measured_rate.value == pytest.approx(TRUE_RATE, abs=0.002)


def test_implausible_entry_flagged_and_excluded(tmp_path):
    _seed_athlete(tmp_path)
    weeks = [_week_sessions(BASE_SQUAT * (1 + TRUE_RATE * w)) for w in range(WEEKS)]
    store.save_program(
        tmp_path, h.program_from_weeks("run-10k", weeks), reason="v1", today=h.ORIGIN
    )
    # A physically implausible 400 kg squat injected in the last week.
    outlier = h.squat_log(h.week_day_offset(WEEKS, 1), 400.0, "tue-lift")
    _simulate_logs(tmp_path, h.rng(101))
    history = store.read_sessions(tmp_path)
    flags = session_plausibility_flags(outlier, history, store.read_profile(tmp_path))
    assert any(f["code"] == "e1rm_jump" for f in flags)
    store.append_session(tmp_path, outlier)
    profile = compute_response_profile(tmp_path, today=h.ORIGIN + timedelta(weeks=WEEKS + 1))
    # The 400 kg jump is excluded, so the recovered rate stays near the true rate.
    assert profile.per_goal_measured_rate is not None
    assert profile.per_goal_measured_rate.value == pytest.approx(TRUE_RATE, abs=0.003)


def test_every_program_version_has_a_reason(tmp_path):
    _seed_athlete(tmp_path)
    weeks = [_week_sessions(BASE_SQUAT) for _ in range(WEEKS)]
    store.save_program(
        tmp_path, h.program_from_weeks("run-10k", weeks), reason="v1", today=h.ORIGIN
    )
    store.save_program(
        tmp_path, h.program_from_weeks("run-10k", weeks), reason="mid-block adjust", today=h.ORIGIN
    )
    latest = store.latest_program_version(tmp_path)
    assert latest == 2
    for version in range(1, latest + 1):
        read = store.read_program(tmp_path, version=version)
        assert read is not None
        assert read.reason
