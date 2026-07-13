"""Band, ramp-property and gating tests for the return-to-load ladder."""

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.return_to_load import build_return_progression


def _ramp(weeks_off, sessions_per_week=3, pain_free=True):
    return build_return_progression(weeks_off, sessions_per_week, pain_free)


# --- starting band, on each side of every boundary ---


@pytest.mark.parametrize(
    ("weeks_off", "volume_start", "intensity_start"),
    [
        (0, 0.90, 0.95),  # < 1 week
        (1, 0.70, 0.85),  # 1-2 weeks
        (2, 0.50, 0.70),  # 2-4 weeks
        (3, 0.50, 0.70),  # still the 2-4 band
        (4, 0.40, 0.60),  # > 4 weeks
        (10, 0.40, 0.60),  # catch-all
    ],
)
def test_starting_band(weeks_off, volume_start, intensity_start):
    first = _ramp(weeks_off)[0]
    assert first.volume_factor == pytest.approx(volume_start)
    assert first.intensity_factor == pytest.approx(intensity_start)


# --- ramp properties ---


@pytest.mark.parametrize("weeks_off", [0, 1, 2, 3, 4, 8])
def test_factors_monotone_non_decreasing_and_capped(weeks_off):
    ramp = _ramp(weeks_off)
    for prev, cur in itertools.pairwise(ramp):
        assert cur.volume_factor >= prev.volume_factor
        assert cur.intensity_factor >= prev.intensity_factor
    for week in ramp:
        assert week.volume_factor <= 1.0
        assert week.intensity_factor <= 1.0


@pytest.mark.parametrize("weeks_off", [0, 1, 2, 4, 8])
def test_ramp_reaches_baseline_on_the_last_week(weeks_off):
    last = _ramp(weeks_off)[-1]
    assert last.volume_factor == pytest.approx(1.0)
    assert last.intensity_factor == pytest.approx(1.0)


def test_week_indices_are_1_based_and_contiguous():
    ramp = _ramp(4)
    assert [w.week_index for w in ramp] == list(range(1, len(ramp) + 1))


def test_longer_layoff_ramps_at_least_as_long():
    lengths = [len(_ramp(w)) for w in (0, 1, 2, 4)]
    assert lengths == sorted(lengths)
    # a > 4 week layoff must ramp strictly longer than a < 1 week one
    assert len(_ramp(8)) > len(_ramp(0))


def test_progressing_weeks_carry_the_24h_rule():
    ramp = _ramp(4)
    assert "24h" in ramp[0].note
    assert "sessions/week" in ramp[0].note


# --- pain_free gating ---


def test_not_pain_free_returns_a_single_holding_week():
    ramp = build_return_progression(4, 3, pain_free=False)
    assert len(ramp) == 1
    week = ramp[0]
    assert week.week_index == 1
    # holds at the band start, does not progress
    assert week.volume_factor == pytest.approx(0.40)
    assert week.intensity_factor == pytest.approx(0.60)
    assert "not pain-free" in week.note
    assert "do not progress" in week.note


def test_pain_free_and_holding_share_the_same_start():
    progressing = build_return_progression(2, 3, pain_free=True)[0]
    holding = build_return_progression(2, 3, pain_free=False)[0]
    assert progressing.volume_factor == holding.volume_factor
    assert progressing.intensity_factor == holding.intensity_factor


# --- validation ---


@pytest.mark.parametrize(
    ("weeks_off", "sessions_per_week"),
    [(-1, 3), (2, 0), (2, 15)],
)
def test_rejects_out_of_range(weeks_off, sessions_per_week):
    with pytest.raises(ValueError):
        build_return_progression(weeks_off, sessions_per_week, True)


def test_rejects_non_integer_inputs():
    with pytest.raises(ValueError, match="whole number"):
        build_return_progression(1.5, 3, True)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="whole number"):
        build_return_progression(2, 3.5, True)  # ty: ignore[invalid-argument-type]


@given(
    weeks_off=st.integers(min_value=0, max_value=52),
    sessions=st.integers(min_value=1, max_value=14),
)
def test_ramp_always_well_formed(weeks_off, sessions):
    ramp = build_return_progression(weeks_off, sessions, pain_free=True)
    assert ramp[-1].volume_factor == pytest.approx(1.0)
    assert ramp[-1].intensity_factor == pytest.approx(1.0)
    for prev, cur in itertools.pairwise(ramp):
        assert cur.volume_factor >= prev.volume_factor
        assert cur.intensity_factor >= prev.intensity_factor
        assert cur.volume_factor <= 1.0
