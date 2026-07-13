"""Engine tests for measured-rate recalibration and tolerance-adjusted targets."""

import pytest

from performance_agent.engine import TrainingAge, weekly_set_targets, weekly_set_targets_adjusted
from performance_agent.engine.feasibility import (
    recalibrated_feasibility,
    strength_feasibility,
)


def test_recalibrated_matches_population_when_rates_equal():
    verdict = strength_feasibility(100.0, 110.0, 20, TrainingAge.INTERMEDIATE)
    measured = recalibrated_feasibility(
        verdict.required_weekly_rate, verdict.achievable_weekly_rate, 8
    )
    assert measured.probability == pytest.approx(verdict.probability)
    assert measured.small_n is False


def test_recalibrated_faster_measured_rate_lifts_probability():
    verdict = strength_feasibility(100.0, 110.0, 20, TrainingAge.INTERMEDIATE)
    faster = recalibrated_feasibility(verdict.required_weekly_rate, 0.01, 12)
    assert faster.probability > verdict.probability


def test_recalibrated_small_n_flag():
    result = recalibrated_feasibility(0.005, 0.005, 5)
    assert result.small_n is True


def test_recalibrated_rejects_non_positive_measured_rate():
    with pytest.raises(ValueError, match="measured_weekly_rate must be positive"):
        recalibrated_feasibility(0.005, 0.0, 8)


def test_tolerance_default_returns_base_targets():
    base = weekly_set_targets(TrainingAge.INTERMEDIATE)
    assert weekly_set_targets_adjusted(TrainingAge.INTERMEDIATE, "default") == base


def test_tolerance_reduce_pulls_range_down_within_landmarks():
    base = weekly_set_targets(TrainingAge.INTERMEDIATE)
    reduced = weekly_set_targets_adjusted(TrainingAge.INTERMEDIATE, "reduce")
    assert reduced.minimum_effective_sets == base.minimum_effective_sets
    assert reduced.maximum_adaptive_sets == base.maximum_adaptive_sets
    assert reduced.optimal_low_sets == base.minimum_effective_sets
    assert reduced.optimal_high_sets == base.optimal_low_sets
    assert reduced.optimal_low_sets <= reduced.optimal_high_sets


def test_tolerance_extend_pushes_range_up_within_landmarks():
    base = weekly_set_targets(TrainingAge.ADVANCED)
    extended = weekly_set_targets_adjusted(TrainingAge.ADVANCED, "extend")
    assert extended.optimal_low_sets == base.optimal_high_sets
    assert extended.optimal_high_sets == base.maximum_adaptive_sets
    assert extended.optimal_high_sets <= extended.maximum_adaptive_sets
