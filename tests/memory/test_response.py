"""Memory-layer tests: compute_response_profile from logged history (honest n)."""

from datetime import datetime, timedelta

import pytest

from performance_agent.memory import store
from performance_agent.memory.response import compute_response_profile
from performance_agent.memory.schemas import (
    ExercisePerformed,
    Goal,
    SessionEntry,
    SetPerformed,
)
from tests.program_plans import FIXTURE_TODAY, minimal_plan

ORIGIN = FIXTURE_TODAY


def _squat_session(week: int, load_kg: float, plan_id: str = "w01-s1-lower-heavy") -> SessionEntry:
    at = datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=week * 7)
    return SessionEntry(
        performed_at=at,
        kind="strength_heavy",
        session_plan_id=plan_id,
        exercises=[
            ExercisePerformed(name="Back Squat", sets=[SetPerformed(reps=5, load_kg=load_kg)])
        ],
    )


def _seed_program(tmp_path):
    store.save_program(tmp_path, minimal_plan(goal_id="squat-160"), today=ORIGIN)
    store.upsert_goal(
        tmp_path,
        Goal(id="squat-160", statement="Back Squat 160 kg", metric="squat 1RM"),
    )


def test_measured_rate_recovered_after_eight_weeks(tmp_path):
    _seed_program(tmp_path)
    # ~0.5%/week on the working load -> same fractional e1RM rate.
    for week in range(8):
        store.append_session(tmp_path, _squat_session(week, 120.0 * (1 + 0.005 * week)))
    profile = compute_response_profile(tmp_path, today=ORIGIN + timedelta(weeks=8))
    assert profile.per_goal_measured_rate is not None
    assert profile.per_goal_measured_rate.value == pytest.approx(0.005, abs=5e-4)
    assert profile.per_goal_measured_rate.n == 8
    lifts = {r.lift for r in profile.per_lift_rates}
    assert "Back Squat" in lifts


def test_insufficient_data_returns_none_rate_with_caveat(tmp_path):
    _seed_program(tmp_path)
    for week in range(3):  # only 3 points -> below the 6-point floor
        store.append_session(tmp_path, _squat_session(week, 120.0))
    profile = compute_response_profile(tmp_path, today=ORIGIN + timedelta(weeks=3))
    assert profile.per_goal_measured_rate is None
    assert profile.per_lift_rates == []
    assert any("population prior" in c for c in profile.caveats)


def test_implausible_jump_excluded_from_rate(tmp_path):
    _seed_program(tmp_path)
    for week in range(8):
        store.append_session(tmp_path, _squat_session(week, 120.0 + week))
    # A wild outlier session (way above recent best) must not distort the fit.
    store.append_session(tmp_path, _squat_session(8, 400.0))
    profile = compute_response_profile(tmp_path, today=ORIGIN + timedelta(weeks=9))
    assert profile.per_goal_measured_rate is not None
    # The 400 kg jump is excluded, so the slope stays modest, not explosive.
    assert profile.per_goal_measured_rate.value < 0.05


def test_no_structured_program_errors(tmp_path):
    with pytest.raises(ValueError, match="no structured program"):
        compute_response_profile(tmp_path, today=ORIGIN)


def test_compliance_feeds_adherence(tmp_path):
    _seed_program(tmp_path)
    for week in range(8):
        store.append_session(tmp_path, _squat_session(week, 120.0 + week))
    profile = compute_response_profile(tmp_path, today=ORIGIN + timedelta(weeks=8))
    # The plan has one strength_heavy session; logged sessions match it by id.
    qualities = {a.quality for a in profile.adherence_by_quality}
    assert "strength_heavy" in qualities
