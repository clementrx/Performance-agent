import pytest

from performance_agent.engine.strength import (
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
)


def test_epley_known_value():
    assert one_rm_epley(load_kg=100, reps=5) == pytest.approx(116.67, abs=0.01)


def test_epley_single_rep_is_the_load_itself():
    assert one_rm_epley(load_kg=100, reps=1) == 100.0


def test_brzycki_known_value():
    assert one_rm_brzycki(load_kg=100, reps=5) == pytest.approx(112.5, abs=0.01)


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
