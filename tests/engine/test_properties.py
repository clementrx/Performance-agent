import itertools

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from performance_agent.engine import (
    acute_chronic_ratio,
    bodycomp_feasibility,
    build_weekly_waves,
    endurance_feasibility,
    hypertrophy_feasibility,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    riegel_predict,
    strength_feasibility,
    weekly_loads,
    weekly_set_targets,
)
from performance_agent.engine.feasibility import TrainingAge
from performance_agent.engine.nutrition import CALORIC_FLOOR_KCAL, prescribe_energy_target
from performance_agent.engine.periodization import (
    build_block_periodization,
    build_strength_peaking,
    build_undulating_week,
)

loads = st.floats(min_value=1, max_value=500, allow_nan=False)
times = st.floats(min_value=60, max_value=36000, allow_nan=False)
riegel_distances = st.floats(min_value=1500, max_value=42195, allow_nan=False)
one_rm_formulas = st.sampled_from([one_rm_epley, one_rm_brzycki, one_rm_lombardi, one_rm_wathan])


@given(
    formula=one_rm_formulas,
    load_kg=loads,
    reps=st.integers(min_value=1, max_value=11),
)
def test_one_rm_never_decreases_with_more_reps(formula, load_kg, reps):
    assert formula(load_kg, reps + 1) >= formula(load_kg, reps)


@given(
    formula=one_rm_formulas,
    load_kg=loads,
    reps=st.integers(min_value=1, max_value=12),
)
def test_one_rm_is_at_least_the_lifted_load(formula, load_kg, reps):
    assert formula(load_kg, reps) >= load_kg


@given(d1=riegel_distances, d2=riegel_distances, known_t=times)
def test_riegel_longer_distance_takes_longer(d1, d2, known_t):
    assume(abs(d2 - d1) > 1.0)
    lo, hi = min(d1, d2), max(d1, d2)
    assert riegel_predict(lo, known_t, hi) > known_t


@given(
    current=times,
    target=times,
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_feasibility_probability_is_a_probability(current, target, weeks, age):
    result = endurance_feasibility(current, target, weeks, age)
    assert 0.0 < result.probability < 1.0


@given(
    current=st.floats(min_value=20, max_value=500, allow_nan=False),
    target=st.floats(min_value=20, max_value=500, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_strength_feasibility_probability_is_a_probability(current, target, weeks, age):
    result = strength_feasibility(current, target, weeks, age)
    assert 0.0 < result.probability < 1.0


@given(
    gain=st.floats(min_value=0.1, max_value=30, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_hypertrophy_feasibility_probability_is_a_probability(gain, weeks, age):
    result = hypertrophy_feasibility(gain, weeks, age)
    assert 0.0 < result.probability < 1.0


@given(
    current=st.floats(min_value=40, max_value=300, allow_nan=False),
    delta1=st.floats(min_value=0.01, max_value=200, allow_nan=False),
    delta2=st.floats(min_value=0.01, max_value=200, allow_nan=False),
    weeks=st.integers(min_value=4, max_value=52),
    age=st.sampled_from(list(TrainingAge)),
)
def test_strength_feasibility_probability_non_increasing_in_target(
    current, delta1, delta2, weeks, age
):
    lo, hi = sorted((delta1, delta2))
    assume(hi - lo > 1e-6)
    p_lo = strength_feasibility(current, current + lo, weeks, age).probability
    p_hi = strength_feasibility(current, current + hi, weeks, age).probability
    assert p_lo >= p_hi


@given(daily=st.lists(st.floats(min_value=0, max_value=2000, allow_nan=False), max_size=120))
def test_weekly_loads_conserve_total(daily):
    assert sum(weekly_loads(daily)) == pytest.approx(sum(daily))


@given(
    daily=st.lists(
        st.floats(min_value=0, max_value=2000, allow_nan=False), min_size=28, max_size=120
    )
)
def test_acwr_is_none_or_non_negative(daily):
    ratio = acute_chronic_ratio(daily)
    assert ratio is None or ratio >= 0


@given(
    total_weeks=st.integers(min_value=2, max_value=52),
    deload_every=st.integers(min_value=2, max_value=8),
)
def test_waves_cover_every_week_with_positive_factors(total_weeks, deload_every):
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=1)
    assert len(waves) == total_weeks
    assert all(w.volume_factor > 0 and w.intensity_factor > 0 for w in waves)
    assert [w.week for w in waves] == list(range(1, total_weeks + 1))


@given(
    weight=st.floats(min_value=40, max_value=200, allow_nan=False),
    current_bf=st.floats(min_value=13, max_value=55, allow_nan=False),
    target_bf=st.floats(min_value=12, max_value=50, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    sex=st.sampled_from(["male", "female"]),
)
def test_bodycomp_probability_is_a_probability(weight, current_bf, target_bf, weeks, sex):
    assume(target_bf < current_bf)
    result = bodycomp_feasibility(weight, current_bf, target_bf, weeks, sex)
    assert 0.0 < result.probability < 1.0


@given(
    reps=st.integers(min_value=1, max_value=18),
    rir=st.integers(min_value=0, max_value=17),
)
def test_reps_rir_percentage_round_trips(reps, rir):
    assume(reps + rir <= 18)
    percentage = percentage_for_reps_rir(reps, rir)
    assert reps_for_percentage_rir(percentage, rir) == reps


@given(age=st.sampled_from(list(TrainingAge)))
def test_weekly_set_targets_invariant_ordering(age):
    targets = weekly_set_targets(age)
    assert (
        0
        < targets.minimum_effective_sets
        < targets.optimal_low_sets
        < targets.optimal_high_sets
        < targets.maximum_adaptive_sets
    )


@given(total_weeks=st.integers(min_value=6, max_value=52))
def test_block_periodization_covers_every_week_with_all_three_phases(total_weeks):
    weeks = build_block_periodization(total_weeks)
    assert [w.week for w in weeks] == list(range(1, total_weeks + 1))
    for phase in ("accumulation", "intensification", "realization"):
        assert sum(1 for w in weeks if w.phase == phase) >= 1


@given(sessions_per_week=st.integers(min_value=2, max_value=7))
def test_undulating_sessions_are_contiguous_with_sane_zones(sessions_per_week):
    sessions = build_undulating_week(sessions_per_week)
    assert [s.session for s in sessions] == list(range(1, sessions_per_week + 1))
    for session in sessions:
        assert 0 < session.intensity_low < session.intensity_high < 1


@given(weeks=st.integers(min_value=1, max_value=3))
def test_peaking_volume_falls_while_intensity_climbs(weeks):
    taper = build_strength_peaking(weeks)
    volumes = [w.volume_factor for w in taper]
    intensities = [w.intensity_factor for w in taper]
    # For weeks=1 there are no pairs and both hold trivially.
    assert all(a > b for a, b in itertools.pairwise(volumes))
    assert all(a < b for a, b in itertools.pairwise(intensities))
    assert taper[-1].is_test_week
    assert not any(w.is_test_week for w in taper[:-1])


@given(
    tdee=st.floats(min_value=1300, max_value=5000, allow_nan=False),
    rate=st.floats(min_value=0.001, max_value=0.010, allow_nan=False),
    weight=st.floats(min_value=45, max_value=150, allow_nan=False),
    height=st.floats(min_value=140, max_value=210, allow_nan=False),
    sex=st.sampled_from(["male", "female"]),
)
def test_cut_prescription_never_goes_below_the_floor(tdee, rate, weight, height, sex):
    assume(weight / (height / 100) ** 2 >= 18.5)
    target = prescribe_energy_target(tdee, "cut", rate, weight, height, sex)
    assert target.daily_kcal >= CALORIC_FLOOR_KCAL[sex]
    assert target.protein_g_per_day > 0
