import pytest

from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)


def test_session_rpe_load():
    assert session_rpe_load(rpe=7, duration_min=60) == 420.0


@pytest.mark.parametrize(("rpe", "duration"), [(0, 60), (11, 60), (7, 0)])
def test_session_rpe_load_validates_inputs(rpe, duration):
    with pytest.raises(ValueError, match=r"rpe|duration"):
        session_rpe_load(rpe=rpe, duration_min=duration)


@pytest.mark.parametrize(("rpe", "duration"), [(7.5, 60), (True, 60), (7, 30.5)])
def test_session_rpe_load_rejects_non_integers(rpe, duration):
    with pytest.raises(ValueError, match="whole number"):
        session_rpe_load(rpe=rpe, duration_min=duration)


def test_weekly_loads_sums_by_seven_day_blocks():
    assert weekly_loads([100.0] * 14) == [700.0, 700.0]


def test_weekly_loads_keeps_partial_final_week():
    assert weekly_loads([100.0] * 10) == [700.0, 300.0]


def test_weekly_loads_empty_input():
    assert weekly_loads([]) == []


def test_acwr_uniform_history_is_one():
    assert acute_chronic_ratio([100.0] * 28) == pytest.approx(1.0)


def test_acwr_spike_in_last_week():
    history = [100.0] * 21 + [150.0] * 7
    assert acute_chronic_ratio(history) == pytest.approx(1.3333, abs=0.001)


def test_acwr_requires_28_days_of_history():
    assert acute_chronic_ratio([100.0] * 27) is None


def test_acwr_zero_chronic_load_returns_none():
    assert acute_chronic_ratio([0.0] * 28) is None


def test_acwr_uses_only_last_28_days():
    # 100 days of huge loads followed by a uniform final 28 days: ratio must be 1.0
    history = [1000.0] * 100 + [50.0] * 28
    assert acute_chronic_ratio(history) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [-1.0, -0.5])
def test_negative_daily_loads_rejected(bad):
    with pytest.raises(ValueError, match="negative"):
        weekly_loads([100.0, bad])
    with pytest.raises(ValueError, match="negative"):
        acute_chronic_ratio([bad] * 28)
