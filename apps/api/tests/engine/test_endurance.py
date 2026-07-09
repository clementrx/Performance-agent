import pytest

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict


def test_riegel_20min_5k_predicts_about_41_42_10k():
    predicted = riegel_predict(known_distance_m=5000, known_time_s=1200, target_distance_m=10000)
    assert predicted == pytest.approx(2502, abs=2)


def test_riegel_same_distance_returns_same_time():
    assert riegel_predict(
        known_distance_m=5000, known_time_s=1200, target_distance_m=5000
    ) == pytest.approx(1200)


def test_riegel_shorter_distance_predicts_faster_time():
    predicted = riegel_predict(known_distance_m=10000, known_time_s=2700, target_distance_m=5000)
    assert predicted < 1350


@pytest.mark.parametrize(
    ("known_d", "known_t", "target_d"),
    [(0, 1200, 5000), (5000, 0, 10000), (5000, 1200, -1)],
)
def test_riegel_validates_inputs(known_d, known_t, target_d):
    with pytest.raises(ValueError, match="positive"):
        riegel_predict(known_distance_m=known_d, known_time_s=known_t, target_distance_m=target_d)


def test_pace_s_per_km():
    assert pace_s_per_km(distance_m=10000, time_s=2700) == pytest.approx(270.0)


def test_pace_validates_inputs():
    with pytest.raises(ValueError, match="positive"):
        pace_s_per_km(distance_m=0, time_s=2700)
