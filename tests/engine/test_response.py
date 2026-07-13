"""Engine tests for the individual response model (honest about n)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.response import (
    LoggedSession,
    PlannedSession,
    SessionSets,
    TimelinePoint,
    adherence_stats,
    compare_prescribed_actual,
    e1rm_timeline,
    progression_rate,
    volume_tolerance,
)


def _timeline_at_rate(weeks: int, start_e1rm: float, pct_per_week: float) -> list[TimelinePoint]:
    return [
        TimelinePoint(day_index=w * 7, e1rm=start_e1rm * (1 + pct_per_week * w))
        for w in range(weeks)
    ]


def test_e1rm_timeline_takes_best_set_per_session_and_excludes_flagged():
    sessions = [
        SessionSets(day_index=0, sets=((100.0, 5), (110.0, 3))),  # best = 110*(1+3/30)=121
        SessionSets(day_index=7, sets=((130.0, 1),), excluded=True),  # dropped
    ]
    timeline = e1rm_timeline(sessions)
    assert len(timeline) == 1
    assert timeline[0].day_index == 0
    assert timeline[0].e1rm == pytest.approx(121.0)


def test_e1rm_timeline_skips_sessions_with_no_scorable_set():
    sessions = [SessionSets(day_index=0, sets=((0.0, 5),)), SessionSets(day_index=7, sets=())]
    assert e1rm_timeline(sessions) == []


def test_progression_rate_recovers_a_known_linear_rate():
    timeline = _timeline_at_rate(weeks=8, start_e1rm=100.0, pct_per_week=0.005)
    rate = progression_rate(timeline)
    assert rate is not None
    assert rate.pct_per_week == pytest.approx(0.005, abs=1e-4)
    assert rate.r2 == pytest.approx(1.0, abs=1e-6)
    assert rate.n == 8


def test_progression_rate_none_below_six_points():
    timeline = _timeline_at_rate(weeks=5, start_e1rm=100.0, pct_per_week=0.01)
    assert progression_rate(timeline) is None


def test_progression_rate_none_below_four_week_span():
    # Six points but crammed into 3 weeks (span < 4).
    timeline = [TimelinePoint(day_index=d, e1rm=100.0 + d) for d in (0, 4, 8, 12, 16, 21)]
    assert progression_rate(timeline) is None


def test_progression_rate_none_on_zero_span():
    timeline = [TimelinePoint(day_index=0, e1rm=100.0 + i) for i in range(6)]
    assert progression_rate(timeline) is None


@given(
    rate=st.floats(min_value=0.0, max_value=0.02),
    start=st.floats(min_value=50.0, max_value=250.0),
    weeks=st.integers(min_value=6, max_value=24),
)
def test_progression_rate_property_recovers_synthetic_rate(rate, start, weeks):
    timeline = _timeline_at_rate(weeks=weeks, start_e1rm=start, pct_per_week=rate)
    result = progression_rate(timeline)
    assert result is not None
    assert result.pct_per_week == pytest.approx(rate, abs=1e-3)


def test_volume_tolerance_none_below_eight_weeks():
    assert volume_tolerance([10.0] * 7, [3.0] * 7) is None


def test_volume_tolerance_none_when_flat():
    assert volume_tolerance([10.0] * 10, [3.0] * 10) is None


def test_volume_tolerance_reports_positive_association_direction():
    hard_sets = [8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0]
    fatigue = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5]  # rises with volume
    result = volume_tolerance(hard_sets, fatigue)
    assert result is not None
    assert result.direction == "higher_volume_higher_fatigue"
    assert result.correlation == pytest.approx(1.0, abs=1e-6)
    assert result.n_weeks == 8


def test_volume_tolerance_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        volume_tolerance([1.0] * 8, [1.0] * 9)


def _planned(session_id, week, weekday, quality, sets):
    return PlannedSession(session_id, week, weekday, quality, sets)


def _logged(plan_id, week, weekday, quality, sets):
    return LoggedSession(plan_id, week, weekday, quality, sets)


def test_compliance_done_partial_missed_and_extra():
    planned = [
        _planned("w1-s1", 1, 0, "strength_heavy", 10),
        _planned("w1-s2", 1, 2, "hypertrophy", 12),
        _planned("w2-s1", 2, 0, "strength_heavy", 10),  # never logged -> missed
    ]
    logged = [
        _logged("w1-s1", 1, 0, "strength_heavy", 10),  # done
        _logged("w1-s2", 1, 2, "hypertrophy", 5),  # partial
        _logged(None, 1, 4, None, 6),  # unplanned extra
    ]
    report = compare_prescribed_actual(planned, logged)
    by_id = {s.session_id: s for s in report.sessions}
    assert by_id["w1-s1"].status == "done"
    assert by_id["w1-s1"].matched_by == "id"
    assert by_id["w1-s2"].status == "partial"
    assert by_id["w2-s1"].status == "missed"
    assert report.extra_unplanned == 1


def test_compliance_fallback_match_is_modified():
    planned = [_planned("w1-s1", 1, 0, "strength_heavy", 10)]
    logged = [_logged(None, 1, 0, "strength_heavy", 10)]  # no id, same slot
    report = compare_prescribed_actual(planned, logged)
    assert report.sessions[0].status == "modified"
    assert report.sessions[0].matched_by == "weekday_quality"


def test_compliance_swapped_quality_on_id_match_is_modified():
    planned = [_planned("w1-s1", 1, 0, "strength_heavy", 10)]
    logged = [_logged("w1-s1", 1, 0, "hypertrophy", 12)]  # id matches, quality differs
    report = compare_prescribed_actual(planned, logged)
    assert report.sessions[0].status == "modified"


def test_compliance_weekly_volume_prescribed_vs_performed():
    planned = [_planned("w1-s1", 1, 0, "strength_heavy", 10)]
    logged = [_logged("w1-s1", 1, 0, "strength_heavy", 7)]
    report = compare_prescribed_actual(planned, logged)
    assert report.weekly_volume[0].week_index == 1
    assert report.weekly_volume[0].prescribed_sets == 10
    assert report.weekly_volume[0].performed_sets == 7


def test_adherence_stats_rolls_up_by_quality():
    planned = [
        _planned("a", 1, 0, "strength_heavy", 10),
        _planned("b", 1, 2, "strength_heavy", 10),
    ]
    logged = [_logged("a", 1, 0, "strength_heavy", 10)]  # b missed
    stats = adherence_stats(compare_prescribed_actual(planned, logged))
    assert len(stats) == 1
    assert stats[0].quality == "strength_heavy"
    assert stats[0].done == 1
    assert stats[0].missed == 1
    assert stats[0].adherence_pct == pytest.approx(50.0)


def test_missing_week_is_all_missed():
    planned = [_planned(f"w2-s{i}", 2, i, "strength_heavy", 10) for i in range(3)]
    report = compare_prescribed_actual(planned, [])  # nothing logged
    assert all(s.status == "missed" for s in report.sessions)
    assert report.weekly_volume[0].performed_sets == 0
    assert math.isclose(adherence_stats(report)[0].adherence_pct, 0.0)
