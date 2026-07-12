import itertools

import pytest

from performance_agent.engine.endurance import (
    pace_s_per_km,
    riegel_predict,
    training_zones_from_race,
)


def test_riegel_20min_5k_predicts_about_41_42_10k():
    predicted = riegel_predict(known_distance_m=5000, known_time_s=1200, target_distance_m=10000)
    assert predicted == pytest.approx(2502, abs=2)


def test_riegel_same_distance_returns_same_time():
    assert riegel_predict(
        known_distance_m=5000, known_time_s=1200, target_distance_m=5000
    ) == pytest.approx(1200)


def test_riegel_shorter_distance_predicts_faster_time():
    predicted = riegel_predict(known_distance_m=10000, known_time_s=2700, target_distance_m=5000)
    assert 1290 < predicted < 1350


@pytest.mark.parametrize(
    ("known_d", "known_t", "target_d"),
    [(0, 1200, 5000), (5000, 0, 10000), (5000, 1200, -1)],
)
def test_riegel_validates_inputs(known_d, known_t, target_d):
    with pytest.raises(ValueError, match="positive"):
        riegel_predict(known_distance_m=known_d, known_time_s=known_t, target_distance_m=target_d)


@pytest.mark.parametrize("distance_m", [1499, 42196])
def test_riegel_rejects_distances_outside_validity_band(distance_m):
    with pytest.raises(ValueError, match="distance"):
        riegel_predict(known_distance_m=5000, known_time_s=1200, target_distance_m=distance_m)
    with pytest.raises(ValueError, match="distance"):
        riegel_predict(known_distance_m=distance_m, known_time_s=1200, target_distance_m=10000)


@pytest.mark.parametrize("exponent", [0, -1, 1.31])
def test_riegel_rejects_out_of_band_exponent(exponent):
    with pytest.raises(ValueError, match="exponent"):
        riegel_predict(
            known_distance_m=5000,
            known_time_s=1200,
            target_distance_m=10000,
            exponent=exponent,
        )


def test_riegel_custom_exponent_is_used():
    # exponent 1.0 = pure proportional scaling
    assert riegel_predict(
        known_distance_m=5000, known_time_s=1200, target_distance_m=10000, exponent=1.0
    ) == pytest.approx(2400.0)


def test_pace_s_per_km():
    assert pace_s_per_km(distance_m=10000, time_s=2700) == pytest.approx(270.0)


def test_pace_validates_inputs():
    with pytest.raises(ValueError, match="positive"):
        pace_s_per_km(distance_m=0, time_s=2700)


def test_training_zones_returns_five_named_zones():
    zones = training_zones_from_race(5000, 1200)
    assert [z.name for z in zones] == [
        "Z5 interval",
        "Z4 threshold",
        "Z3 tempo",
        "Z2 endurance",
        "Z1 recovery",
    ]


def test_training_zones_are_contiguous_and_monotonic():
    zones = training_zones_from_race(10000, 2700)
    # each zone's slow edge is the next zone's fast edge (contiguous)
    for faster, slower in itertools.pairwise(zones):
        assert faster.high_pace_s_per_km == pytest.approx(slower.low_pace_s_per_km)
    # paces increase (get slower) from Z5 down to Z1
    edges = [z.low_pace_s_per_km for z in zones]
    assert edges == sorted(edges)


def test_training_zones_bracket_the_threshold_pace():
    # Z4 threshold band should straddle the projected 10k pace
    zones = training_zones_from_race(5000, 1200)
    threshold = next(z for z in zones if z.name == "Z4 threshold")
    projected_10k_pace = pace_s_per_km(10000, riegel_predict(5000, 1200, 10000))
    assert threshold.low_pace_s_per_km < projected_10k_pace < threshold.high_pace_s_per_km


def test_training_zones_reject_distance_outside_band():
    with pytest.raises(ValueError, match="distance"):
        training_zones_from_race(500, 120)
