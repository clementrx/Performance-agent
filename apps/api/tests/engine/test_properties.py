from hypothesis import assume, given
from hypothesis import strategies as st

from performance_agent.engine import (
    build_weekly_waves,
    endurance_feasibility,
    one_rm_epley,
    riegel_predict,
)
from performance_agent.engine.feasibility import TrainingAge

loads = st.floats(min_value=1, max_value=500, allow_nan=False)
times = st.floats(min_value=60, max_value=36000, allow_nan=False)
riegel_distances = st.floats(min_value=1500, max_value=42195, allow_nan=False)


@given(load_kg=loads, reps=st.integers(min_value=1, max_value=11))
def test_one_rm_never_decreases_with_more_reps(load_kg, reps):
    assert one_rm_epley(load_kg, reps + 1) >= one_rm_epley(load_kg, reps)


@given(load_kg=loads, reps=st.integers(min_value=1, max_value=12))
def test_one_rm_is_at_least_the_lifted_load(load_kg, reps):
    assert one_rm_epley(load_kg, reps) >= load_kg


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
    total_weeks=st.integers(min_value=2, max_value=52),
    deload_every=st.integers(min_value=2, max_value=8),
)
def test_waves_cover_every_week_with_positive_factors(total_weeks, deload_every):
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=1)
    assert len(waves) == total_weeks
    assert all(w.volume_factor > 0 and w.intensity_factor > 0 for w in waves)
