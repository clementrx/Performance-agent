import math

import pytest

from performance_agent.engine.feasibility import (
    FeasibilityResult,
    TrainingAge,
    endurance_feasibility,
    strength_feasibility,
)


def test_unrealistic_goal_gets_near_zero_probability():
    # 10K from 55:00 to 35:00 in 12 weeks (the spec's canonical honest-coach case)
    result = endurance_feasibility(
        current_time_s=3300,
        target_time_s=2100,
        weeks=12,
        training_age=TrainingAge.BEGINNER,
    )
    assert result.probability < 0.05


def test_reasonable_goal_gets_high_probability():
    # 10K from 47:00 to 45:00 in 16 weeks, intermediate athlete
    result = endurance_feasibility(
        current_time_s=2820,
        target_time_s=2700,
        weeks=16,
        training_age=TrainingAge.INTERMEDIATE,
    )
    assert 0.7 < result.probability < 0.9


def test_already_achieved_goal_is_near_certain():
    result = endurance_feasibility(
        current_time_s=2700,
        target_time_s=2820,
        weeks=8,
        training_age=TrainingAge.ADVANCED,
    )
    assert result.probability > 0.9


def test_result_exposes_the_rates_behind_the_probability():
    result = endurance_feasibility(
        current_time_s=3300,
        target_time_s=3000,
        weeks=10,
        training_age=TrainingAge.BEGINNER,
    )
    assert isinstance(result, FeasibilityResult)
    assert result.required_weekly_rate == pytest.approx(0.00909, abs=0.0001)
    assert result.achievable_weekly_rate == pytest.approx(0.010)
    assert result.ratio == pytest.approx(0.909, abs=0.01)


def test_result_exposes_total_improvement_needed():
    result = endurance_feasibility(
        current_time_s=3300,
        target_time_s=2100,
        weeks=12,
        training_age=TrainingAge.BEGINNER,
    )
    assert result.improvement_needed == pytest.approx(0.3636, abs=0.001)


def test_ratio_of_exactly_one_is_a_coin_flip():
    # beginner: 1%/wk achievable; 10% improvement over 10 weeks = exactly 1%/wk required
    result = endurance_feasibility(
        current_time_s=1000.0,
        target_time_s=900.0,
        weeks=10,
        training_age=TrainingAge.BEGINNER,
    )
    assert result.ratio == pytest.approx(1.0)
    assert result.probability == pytest.approx(0.5)


def test_lower_training_age_means_higher_probability_for_same_goal():
    probabilities = [
        endurance_feasibility(
            current_time_s=2820, target_time_s=2700, weeks=16, training_age=age
        ).probability
        for age in (TrainingAge.BEGINNER, TrainingAge.INTERMEDIATE, TrainingAge.ADVANCED)
    ]
    assert probabilities[0] > probabilities[1] > probabilities[2]


def test_target_equal_to_current_is_high_but_hedged():
    result = endurance_feasibility(
        current_time_s=2700,
        target_time_s=2700,
        weeks=8,
        training_age=TrainingAge.INTERMEDIATE,
    )
    assert 0.9 < result.probability < 1.0


def test_more_time_raises_probability_for_improvement_goals():
    p_short = endurance_feasibility(
        current_time_s=3300,
        target_time_s=2820,
        weeks=8,
        training_age=TrainingAge.INTERMEDIATE,
    ).probability
    p_long = endurance_feasibility(
        current_time_s=3300,
        target_time_s=2820,
        weeks=24,
        training_age=TrainingAge.INTERMEDIATE,
    ).probability
    assert p_long > p_short


def test_extreme_ratios_stay_inside_open_interval():
    # pathological demands must neither overflow nor collapse to exactly 0 or 1
    near_impossible = endurance_feasibility(
        current_time_s=36000,
        target_time_s=60,
        weeks=1,
        training_age=TrainingAge.ADVANCED,
    )
    assert 0.0 < near_impossible.probability < 1.0
    trivially_done = endurance_feasibility(
        current_time_s=60,
        target_time_s=36000,
        weeks=1,
        training_age=TrainingAge.BEGINNER,
    )
    assert 0.0 < trivially_done.probability < 1.0


@pytest.mark.parametrize(
    ("current", "target", "weeks"),
    [(0, 2100, 12), (3300, 0, 12), (3300, 2100, 0)],
)
def test_inputs_are_validated(current, target, weeks):
    with pytest.raises(ValueError, match="positive"):
        endurance_feasibility(
            current_time_s=current,
            target_time_s=target,
            weeks=weeks,
            training_age=TrainingAge.BEGINNER,
        )


@pytest.mark.parametrize("weeks", [2.5, True])
def test_non_integer_weeks_rejected(weeks):
    with pytest.raises(ValueError, match="whole number"):
        endurance_feasibility(
            current_time_s=3300,
            target_time_s=2820,
            weeks=weeks,
            training_age=TrainingAge.INTERMEDIATE,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_times_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        endurance_feasibility(
            current_time_s=bad,
            target_time_s=2700,
            weeks=8,
            training_age=TrainingAge.INTERMEDIATE,
        )
    with pytest.raises(ValueError, match="finite"):
        endurance_feasibility(
            current_time_s=2820,
            target_time_s=bad,
            weeks=8,
            training_age=TrainingAge.INTERMEDIATE,
        )


def test_strength_feasibility_exact_values():
    # 100 -> 110 kg in 20 weeks, intermediate: 10% improvement, 0.5%/wk required
    # vs 0.35%/wk achievable -> ratio 10/7, probability 1/(1+exp(3*(10/7-1)))
    result = strength_feasibility(
        current_one_rm_kg=100.0,
        target_one_rm_kg=110.0,
        weeks=20,
        training_age=TrainingAge.INTERMEDIATE,
    )
    assert isinstance(result, FeasibilityResult)
    assert result.improvement_needed == pytest.approx(0.10)
    assert result.required_weekly_rate == pytest.approx(0.005)
    assert result.achievable_weekly_rate == pytest.approx(0.0035)
    assert result.ratio == pytest.approx(10 / 7)
    assert result.probability == pytest.approx(1 / (1 + math.exp(3 * (10 / 7 - 1))))
    assert result.probability == pytest.approx(0.2166, abs=0.001)


def test_strength_already_met_goal_is_easy():
    # Target below current: improvement <= 0, required rate <= 0, ratio <= 0,
    # and the logistic yields near-certainty. Already-met goals are easy.
    result = strength_feasibility(
        current_one_rm_kg=100.0,
        target_one_rm_kg=95.0,
        weeks=8,
        training_age=TrainingAge.ADVANCED,
    )
    assert result.improvement_needed <= 0
    assert result.required_weekly_rate <= 0
    assert result.ratio <= 0
    assert result.probability > 0.95


@pytest.mark.parametrize(
    ("current", "target", "weeks"),
    [(0, 110, 20), (-100, 110, 20), (100, 0, 20), (100, -110, 20), (100, 110, 0)],
)
def test_strength_inputs_are_validated(current, target, weeks):
    with pytest.raises(ValueError, match="positive"):
        strength_feasibility(
            current_one_rm_kg=current,
            target_one_rm_kg=target,
            weeks=weeks,
            training_age=TrainingAge.INTERMEDIATE,
        )


@pytest.mark.parametrize("weeks", [2.5, True])
def test_strength_non_integer_weeks_rejected(weeks):
    with pytest.raises(ValueError, match="whole number"):
        strength_feasibility(
            current_one_rm_kg=100.0,
            target_one_rm_kg=110.0,
            weeks=weeks,
            training_age=TrainingAge.INTERMEDIATE,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_strength_non_finite_loads_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        strength_feasibility(
            current_one_rm_kg=bad,
            target_one_rm_kg=110.0,
            weeks=20,
            training_age=TrainingAge.INTERMEDIATE,
        )
    with pytest.raises(ValueError, match="finite"):
        strength_feasibility(
            current_one_rm_kg=100.0,
            target_one_rm_kg=bad,
            weeks=20,
            training_age=TrainingAge.INTERMEDIATE,
        )
