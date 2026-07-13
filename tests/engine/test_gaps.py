"""Tests for the gap-analysis engine (per-KPI gaps + per-quality priorities)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.gaps import (
    STALE_AFTER_DAYS,
    KpiTarget,
    Measurement,
    compute_gaps,
)


def _target(kpi_id, quality, weight, higher_is_better, elite):
    return KpiTarget(
        kpi_id=kpi_id,
        quality=quality,
        weight=weight,
        higher_is_better=higher_is_better,
        benchmarks=(("elite", elite),),
    )


def test_measured_gap_higher_is_better():
    target = _target("squat-1rm", "max_strength", 0.5, True, 200.0)
    report = compute_gaps([target], [Measurement("squat-1rm", 150.0, 10)], "elite")
    (gap,) = report.kpi_gaps
    assert gap.status == "measured"
    assert gap.gap_fraction == pytest.approx(0.25)  # 50 short of 200
    assert gap.stale is False


def test_measured_gap_lower_is_better_time():
    target = _target("100m", "speed", 0.5, False, 10.0)
    report = compute_gaps([target], [Measurement("100m", 11.0, 5)], "elite")
    (gap,) = report.kpi_gaps
    assert gap.gap_fraction == pytest.approx(0.1)  # 1s slower than the 10s benchmark


def test_meeting_benchmark_is_zero_gap():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    report = compute_gaps([target], [Measurement("squat-1rm", 220.0, 0)], "elite")
    assert report.kpi_gaps[0].gap_fraction == pytest.approx(0.0)


def test_unmeasured_kpi_never_guessed():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    report = compute_gaps([target], [], "elite")
    gap = report.kpi_gaps[0]
    assert gap.status == "unmeasured"
    assert gap.gap_fraction is None
    assert gap.measured_value is None


def test_no_benchmark_for_level_is_flagged():
    target = KpiTarget("row", "muscular_endurance", 1.0, True, benchmarks=(("elite", 100.0),))
    report = compute_gaps([target], [Measurement("row", 80.0, 3)], "recreational")
    gap = report.kpi_gaps[0]
    assert gap.status == "no_benchmark"
    assert gap.gap_fraction is None


def test_staleness_flag():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    report = compute_gaps(
        [target], [Measurement("squat-1rm", 150.0, STALE_AFTER_DAYS + 1)], "elite"
    )
    assert report.kpi_gaps[0].stale is True


def test_latest_measurement_wins():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    report = compute_gaps(
        [target],
        [Measurement("squat-1rm", 150.0, 30), Measurement("squat-1rm", 180.0, 2)],
        "elite",
    )
    assert report.kpi_gaps[0].measured_value == pytest.approx(180.0)


def test_quality_priority_is_gap_times_weight():
    targets = [
        _target("squat-1rm", "max_strength", 0.6, True, 200.0),
        _target("100m", "speed", 0.4, False, 10.0),
    ]
    measurements = [Measurement("squat-1rm", 150.0, 1), Measurement("100m", 10.5, 1)]
    report = compute_gaps(targets, measurements, "elite")
    scores = {p.quality: p.priority_score for p in report.quality_priorities}
    assert scores["max_strength"] == pytest.approx(0.25 * 0.6)
    assert scores["speed"] == pytest.approx(0.05 * 0.4)
    # max_strength has the higher score, so it ranks first.
    assert report.quality_priorities[0].quality == "max_strength"


def test_unmeasured_qualities_rank_last():
    targets = [
        _target("squat-1rm", "max_strength", 0.5, True, 200.0),
        _target("vo2", "aerobic_capacity", 0.5, True, 60.0),
    ]
    report = compute_gaps(targets, [Measurement("squat-1rm", 150.0, 1)], "elite")
    assert report.quality_priorities[-1].quality == "aerobic_capacity"
    assert report.quality_priorities[-1].priority_score is None
    assert report.quality_priorities[-1].unmeasured_kpis == 1


def test_invalid_level_rejected():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    with pytest.raises(ValueError, match="level must be one of"):
        compute_gaps([target], [], "world_record")


def test_negative_staleness_rejected():
    target = _target("squat-1rm", "max_strength", 1.0, True, 200.0)
    with pytest.raises(ValueError, match="non-negative"):
        compute_gaps([target], [Measurement("squat-1rm", 150.0, -1)], "elite")


@given(
    measured=st.floats(min_value=1.0, max_value=500.0),
    benchmark=st.floats(min_value=1.0, max_value=500.0),
    extra=st.floats(min_value=0.0, max_value=200.0),
)
def test_gap_monotone_in_benchmark_distance(measured, benchmark, extra):
    # For higher-is-better, a farther (higher) benchmark never shrinks the gap.
    near = KpiTarget("k", "max_strength", 1.0, True, (("elite", benchmark),))
    far = KpiTarget("k", "max_strength", 1.0, True, (("elite", benchmark + extra),))
    m = [Measurement("k", measured, 1)]
    near_gap = compute_gaps([near], m, "elite").kpi_gaps[0].gap_fraction
    far_gap = compute_gaps([far], m, "elite").kpi_gaps[0].gap_fraction
    assert near_gap is not None and far_gap is not None
    assert far_gap >= near_gap - 1e-9


@given(order=st.permutations([0, 1, 2]))
def test_priority_scores_invariant_under_kpi_order(order):
    targets = [
        _target("a", "max_strength", 0.5, True, 200.0),
        _target("b", "speed", 0.3, False, 10.0),
        _target("c", "aerobic_capacity", 0.2, True, 60.0),
    ]
    measurements = [
        Measurement("a", 150.0, 1),
        Measurement("b", 11.0, 1),
        Measurement("c", 50.0, 1),
    ]
    shuffled_targets = [targets[i] for i in order]
    base = {
        p.quality: p.priority_score
        for p in compute_gaps(targets, measurements, "elite").quality_priorities
    }
    perm = {
        p.quality: p.priority_score
        for p in compute_gaps(shuffled_targets, measurements, "elite").quality_priorities
    }
    assert base.keys() == perm.keys()
    for quality, value in base.items():
        assert value == pytest.approx(perm[quality])
