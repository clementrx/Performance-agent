import pytest

from performance_agent.engine.feasibility import TrainingAge
from performance_agent.engine.strength import (
    WeeklySetTargets,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    weekly_set_targets,
)


def test_epley_known_value():
    assert one_rm_epley(load_kg=100, reps=5) == pytest.approx(116.67, abs=0.01)


def test_epley_single_rep_is_the_load_itself():
    assert one_rm_epley(load_kg=100, reps=1) == 100.0


def test_brzycki_known_value():
    assert one_rm_brzycki(load_kg=100, reps=5) == pytest.approx(112.5, abs=0.01)


def test_brzycki_single_rep_is_the_load_itself():
    # float rounding regression guard: 1.9 * 36 / 36 != 1.9 exactly
    assert one_rm_brzycki(load_kg=1.9, reps=1) == 1.9


@pytest.mark.parametrize("reps", [0, -1, 13])
def test_rep_range_is_validated(reps):
    with pytest.raises(ValueError, match="reps"):
        one_rm_epley(load_kg=100, reps=reps)
    with pytest.raises(ValueError, match="reps"):
        one_rm_brzycki(load_kg=100, reps=reps)


@pytest.mark.parametrize("load_kg", [0, -20])
def test_load_must_be_positive(load_kg):
    with pytest.raises(ValueError, match="load"):
        one_rm_epley(load_kg=load_kg, reps=5)


def test_accepted_boundaries_compute():
    assert one_rm_epley(load_kg=100, reps=12) == pytest.approx(140.0)
    assert one_rm_brzycki(load_kg=100, reps=1) == pytest.approx(100.0)
    assert load_for_percentage(one_rm_kg=100, percentage=1.3) == pytest.approx(130.0)


@pytest.mark.parametrize("reps", [2.5, 5.0, True])
def test_non_integer_reps_rejected(reps):
    with pytest.raises(ValueError, match="reps"):
        one_rm_epley(load_kg=100, reps=reps)
    with pytest.raises(ValueError, match="reps"):
        one_rm_brzycki(load_kg=100, reps=reps)


def test_load_for_percentage():
    assert load_for_percentage(one_rm_kg=150, percentage=0.8) == pytest.approx(120.0)


@pytest.mark.parametrize("percentage", [0, -0.1, 1.31])
def test_percentage_is_validated(percentage):
    with pytest.raises(ValueError, match="percentage"):
        load_for_percentage(one_rm_kg=150, percentage=percentage)


def test_percentage_for_reps_rir_known_value():
    # 5 reps with 2 in reserve = 7 effective reps -> 1/(1 + 7/30) = 30/37
    assert percentage_for_reps_rir(reps=5, rir=2) == pytest.approx(30 / 37)
    assert percentage_for_reps_rir(reps=5, rir=2) == pytest.approx(0.8108, abs=0.001)


def test_percentage_for_single_all_out_rep_is_full_1rm():
    assert percentage_for_reps_rir(reps=1, rir=0) == 1.0


def test_reps_for_percentage_rir_known_value():
    # 30/37 of 1RM leaves 7 effective reps; 2 in reserve -> 5 clean reps
    assert reps_for_percentage_rir(percentage=30 / 37, rir=2) == 5


def test_reps_for_full_1rm_with_zero_rir_is_one_rep():
    assert reps_for_percentage_rir(percentage=1.0, rir=0) == 1


def test_percentage_too_high_to_leave_reps_in_reserve():
    with pytest.raises(ValueError, match="reserve"):
        reps_for_percentage_rir(percentage=1.0, rir=2)


def test_effective_reps_beyond_cap_rejected():
    with pytest.raises(ValueError, match="18"):
        percentage_for_reps_rir(reps=15, rir=4)


@pytest.mark.parametrize(("reps", "rir"), [(0, 0), (-1, 2), (5, -1)])
def test_reps_and_rir_bounds_rejected(reps, rir):
    with pytest.raises(ValueError):
        percentage_for_reps_rir(reps=reps, rir=rir)


@pytest.mark.parametrize("percentage", [0, -0.5, 1.01])
def test_reps_for_percentage_rir_percentage_validated(percentage):
    with pytest.raises(ValueError, match="percentage"):
        reps_for_percentage_rir(percentage=percentage, rir=1)


@pytest.mark.parametrize(("reps", "rir"), [(2.5, 0), (True, 0), (5, 1.5)])
def test_rir_functions_reject_non_whole_numbers(reps, rir):
    with pytest.raises(ValueError, match="whole number"):
        percentage_for_reps_rir(reps=reps, rir=rir)


@pytest.mark.parametrize(("percentage", "rir"), [(0.30, 2), (0.5, 0)])
def test_reps_for_percentage_rir_rejects_effective_reps_beyond_cap(percentage, rir):
    with pytest.raises(ValueError, match="effective reps"):
        reps_for_percentage_rir(percentage, rir)


@pytest.mark.parametrize("age", list(TrainingAge))
def test_weekly_set_targets_fields_strictly_increase(age):
    targets = weekly_set_targets(age)
    assert isinstance(targets, WeeklySetTargets)
    assert (
        targets.minimum_effective
        < targets.optimal_low
        < targets.optimal_high
        < targets.maximum_adaptive
    )


def test_weekly_set_targets_beginner_values():
    targets = weekly_set_targets(TrainingAge.BEGINNER)
    assert targets == WeeklySetTargets(
        minimum_effective=6, optimal_low=8, optimal_high=12, maximum_adaptive=16
    )


def test_weekly_set_targets_scale_with_training_age():
    beginner = weekly_set_targets(TrainingAge.BEGINNER)
    intermediate = weekly_set_targets(TrainingAge.INTERMEDIATE)
    advanced = weekly_set_targets(TrainingAge.ADVANCED)
    assert beginner.optimal_low < intermediate.optimal_low < advanced.optimal_low
    assert beginner.maximum_adaptive < intermediate.maximum_adaptive < advanced.maximum_adaptive
