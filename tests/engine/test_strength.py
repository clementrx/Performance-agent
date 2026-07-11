import pytest

from performance_agent.engine.feasibility import TrainingAge
from performance_agent.engine.strength import (
    ProgressionDecision,
    TopSetBackoff,
    WeeklySetTargets,
    double_progression,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    rir_from_rpe,
    top_set_backoff,
    wave_loading,
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


def test_lombardi_known_value():
    # 100 * 8**0.1 ~ 123.11
    assert one_rm_lombardi(load_kg=100, reps=8) == pytest.approx(123.11, abs=0.01)


def test_wathan_known_value():
    # 100 * 100 / (48.8 + 53.8 * e^-0.6) ~ 127.67
    assert one_rm_wathan(load_kg=100, reps=8) == pytest.approx(127.67, abs=0.01)


def test_lombardi_and_wathan_single_rep_is_the_load_itself():
    # Wathan at reps=1 would give ~1.3% above the load; the shortcut clamps it.
    assert one_rm_lombardi(load_kg=100, reps=1) == 100.0
    assert one_rm_wathan(load_kg=100, reps=1) == 100.0


@pytest.mark.parametrize("reps", [0, -1, 13])
def test_lombardi_and_wathan_rep_range_is_validated(reps):
    with pytest.raises(ValueError, match="reps"):
        one_rm_lombardi(load_kg=100, reps=reps)
    with pytest.raises(ValueError, match="reps"):
        one_rm_wathan(load_kg=100, reps=reps)


@pytest.mark.parametrize("load_kg", [0, -20])
def test_lombardi_and_wathan_load_must_be_positive(load_kg):
    with pytest.raises(ValueError, match="load"):
        one_rm_lombardi(load_kg=load_kg, reps=5)
    with pytest.raises(ValueError, match="load"):
        one_rm_wathan(load_kg=load_kg, reps=5)


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
        targets.minimum_effective_sets
        < targets.optimal_low_sets
        < targets.optimal_high_sets
        < targets.maximum_adaptive_sets
    )


def test_weekly_set_targets_beginner_values():
    targets = weekly_set_targets(TrainingAge.BEGINNER)
    assert targets == WeeklySetTargets(
        minimum_effective_sets=6, optimal_low_sets=8, optimal_high_sets=12, maximum_adaptive_sets=16
    )


def test_weekly_set_targets_scale_with_training_age():
    beginner = weekly_set_targets(TrainingAge.BEGINNER)
    intermediate = weekly_set_targets(TrainingAge.INTERMEDIATE)
    advanced = weekly_set_targets(TrainingAge.ADVANCED)
    assert beginner.optimal_low_sets < intermediate.optimal_low_sets < advanced.optimal_low_sets
    assert (
        beginner.maximum_adaptive_sets
        < intermediate.maximum_adaptive_sets
        < advanced.maximum_adaptive_sets
    )


def test_double_progression_all_sets_at_top_increments_load():
    decision = double_progression(
        reps_achieved=[12, 12, 12],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert decision == ProgressionDecision(
        next_load_kg=62.5, next_target_reps=8, load_increased=True
    )


def test_double_progression_partial_achievement_holds_load():
    decision = double_progression(
        reps_achieved=[12, 11, 10],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert decision.next_load_kg == 60.0
    assert decision.load_increased is False
    # lowest set (10) drives the target: 10 + 1 = 11
    assert decision.next_target_reps == 11


def test_double_progression_target_is_capped_at_range_top():
    # lowest achieved already at the top (e.g. logged above range): cap at high
    decision = double_progression(
        reps_achieved=[13, 12, 14],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    # every set reached the top -> load increases instead of rep chasing
    assert decision.load_increased is True

    held = double_progression(
        reps_achieved=[12, 12, 11],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert held.load_increased is False
    assert held.next_target_reps == 12  # min(11 + 1, 12)


def test_double_progression_below_range_target_is_unfloored():
    decision = double_progression(
        reps_achieved=[2],
        load_kg=100,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert decision == ProgressionDecision(
        next_load_kg=100, next_target_reps=3, load_increased=False
    )


def test_double_progression_validation_rejections():
    with pytest.raises(ValueError, match="empty"):
        double_progression(
            reps_achieved=[], load_kg=60.0, rep_range_low=8, rep_range_high=12, increment_kg=2.5
        )
    with pytest.raises(ValueError, match="rep range"):
        double_progression(
            reps_achieved=[10],
            load_kg=60.0,
            rep_range_low=12,
            rep_range_high=8,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="rep range"):
        double_progression(
            reps_achieved=[10],
            load_kg=60.0,
            rep_range_low=8,
            rep_range_high=19,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="non-negative"):
        double_progression(
            reps_achieved=[10, -1],
            load_kg=60.0,
            rep_range_low=8,
            rep_range_high=12,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="load_kg"):
        double_progression(
            reps_achieved=[10], load_kg=0, rep_range_low=8, rep_range_high=12, increment_kg=2.5
        )
    with pytest.raises(ValueError, match="increment_kg"):
        double_progression(
            reps_achieved=[10], load_kg=60.0, rep_range_low=8, rep_range_high=12, increment_kg=0
        )


def test_top_set_backoff_known_values():
    # top = 200 * 0.9 = 180; backoff = 200 * (0.9 - 0.10) = 160
    prescription = top_set_backoff(
        one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.10, backoff_sets=3
    )
    assert isinstance(prescription, TopSetBackoff)
    assert prescription.top_set_load_kg == pytest.approx(180.0)
    assert prescription.backoff_load_kg == pytest.approx(160.0)
    assert prescription.backoff_sets == 3


def test_top_set_backoff_rejects_drop_beyond_half():
    with pytest.raises(ValueError, match="backoff_drop"):
        top_set_backoff(one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.6, backoff_sets=3)


def test_top_set_backoff_rejects_drop_that_leaves_no_load():
    # 0.4 - 0.5 <= 0: both inputs pass their own range checks but combine to nothing
    with pytest.raises(ValueError, match="leaves no back-off load"):
        top_set_backoff(one_rm_kg=200.0, top_percentage=0.4, backoff_drop=0.5, backoff_sets=3)


@pytest.mark.parametrize("backoff_sets", [0, 11])
def test_top_set_backoff_rejects_out_of_range_sets(backoff_sets):
    with pytest.raises(ValueError, match="backoff_sets"):
        top_set_backoff(
            one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.10, backoff_sets=backoff_sets
        )


def test_wave_loading_classic_two_by_three():
    # wave 1: 0.70, 0.75, 0.80; wave 2 restarts 0.025 up: 0.725, 0.775, 0.825
    steps = wave_loading(
        one_rm_kg=100.0,
        base_percentage=0.70,
        step_increment=0.05,
        steps_per_wave=3,
        waves=2,
        inter_wave_increment=0.025,
    )
    assert [(s.wave, s.step) for s in steps] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    assert [s.percentage for s in steps] == pytest.approx([0.70, 0.75, 0.80, 0.725, 0.775, 0.825])
    assert [s.load_kg for s in steps] == pytest.approx([70.0, 75.0, 80.0, 72.5, 77.5, 82.5])


def test_wave_loading_rejects_peak_over_max_percentage():
    # peak = 1.0 + 4*0.1 + 3*0.05 = 1.55 > 1.3
    with pytest.raises(ValueError, match="peak"):
        wave_loading(
            one_rm_kg=100.0,
            base_percentage=1.0,
            step_increment=0.1,
            steps_per_wave=5,
            waves=4,
            inter_wave_increment=0.05,
        )


def test_wave_loading_rejects_non_overlapping_waves():
    # inter_wave_increment == step_increment: wave 2 would start where wave 1 ended
    with pytest.raises(ValueError, match="inter_wave_increment"):
        wave_loading(
            one_rm_kg=100.0,
            base_percentage=0.70,
            step_increment=0.05,
            steps_per_wave=3,
            waves=2,
            inter_wave_increment=0.05,
        )


def test_wave_loading_bounds_rejections():
    with pytest.raises(ValueError, match="base_percentage"):
        wave_loading(100.0, 1.1, 0.05, 3, 2, 0.025)
    with pytest.raises(ValueError, match="step_increment"):
        wave_loading(100.0, 0.70, 0.15, 3, 2, 0.025)
    with pytest.raises(ValueError, match="steps_per_wave"):
        wave_loading(100.0, 0.70, 0.05, 1, 2, 0.025)
    with pytest.raises(ValueError, match="waves must be"):
        wave_loading(100.0, 0.70, 0.05, 3, 5, 0.025)


@pytest.mark.parametrize(("rpe", "expected_rir"), [(8.0, 2.0), (8.5, 1.5), (10.0, 0.0)])
def test_rir_from_rpe_known_values(rpe, expected_rir):
    assert rir_from_rpe(rpe) == pytest.approx(expected_rir)


@pytest.mark.parametrize("rpe", [0.5, 10.5])
def test_rir_from_rpe_rejects_out_of_scale(rpe):
    with pytest.raises(ValueError, match="rpe must be between"):
        rir_from_rpe(rpe)


def test_rir_from_rpe_rejects_quarter_points():
    with pytest.raises(ValueError, match="half-point"):
        rir_from_rpe(8.25)


def test_rir_from_rpe_rejects_nan():
    with pytest.raises(ValueError, match="finite"):
        rir_from_rpe(float("nan"))
