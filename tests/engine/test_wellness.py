"""Wellness-trend analysis: honesty gates, window math, band classification."""

import math

import pytest

from performance_agent.engine.wellness import (
    WellnessSample,
    hrv_trend,
    resting_hr_trend,
    sleep_trend,
    wellness_trend,
)


def _series(values_by_day):
    return [WellnessSample(day_index=d, value=v) for d, v in values_by_day]


def _flat_month(value, days=35):
    return _series((d, value) for d in range(days))


def test_hrv_flat_series_is_normal_with_zero_delta():
    trend = hrv_trend(_flat_month(60.0))
    assert trend.usable
    assert trend.band == "normal"
    assert trend.delta_pct == pytest.approx(0.0)
    assert trend.swc_ln == pytest.approx(0.0)


def test_hrv_suppressed_week_reads_below():
    # 28 baseline days around 60 ms with mild noise, then a week at 45 ms.
    baseline = [(d, 60.0 + (2.0 if d % 2 else -2.0)) for d in range(28)]
    week = [(d, 45.0) for d in range(28, 35)]
    trend = hrv_trend(_series(baseline + week))
    assert trend.usable
    assert trend.band == "below"
    assert trend.delta_pct < -20.0


def test_hrv_elevated_week_reads_above():
    baseline = [(d, 60.0 + (2.0 if d % 2 else -2.0)) for d in range(28)]
    week = [(d, 80.0) for d in range(28, 35)]
    trend = hrv_trend(_series(baseline + week))
    assert trend.band == "above"
    assert trend.delta_pct > 20.0


def test_hrv_delta_pct_matches_hand_computation():
    baseline = [(d, 50.0) for d in range(28)]
    week = [(d, 55.0) for d in range(28, 35)]
    trend = hrv_trend(_series(baseline + week))
    expected = (math.exp(math.log(55.0) - math.log(50.0)) - 1.0) * 100.0
    assert trend.delta_pct == pytest.approx(expected)  # exactly +10%
    assert trend.delta_pct == pytest.approx(10.0)


def test_hrv_thin_rolling_window_is_unusable_with_reason():
    # A lone reading at day 40: the rolling week holds 1 sample, gate fires first.
    trend = hrv_trend(_series([(d, 60.0) for d in range(28)] + [(40, 58.0)]))
    assert not trend.usable
    assert trend.reason is not None and "last 7 days" in trend.reason


def test_hrv_thin_baseline_is_unusable_with_reason():
    trend = hrv_trend(_series([(d, 60.0) for d in range(26, 35)]))
    assert not trend.usable
    assert trend.reason is not None and "baseline" in trend.reason


def test_hrv_empty_and_invalid_inputs():
    assert not hrv_trend([]).usable
    with pytest.raises(ValueError, match="hrv value"):
        hrv_trend([WellnessSample(day_index=0, value=0.0)])
    with pytest.raises(ValueError, match="day_index"):
        hrv_trend([WellnessSample(day_index=-1, value=60.0)])


def test_resting_hr_elevated_and_lowered_bands():
    baseline = [(d, 50.0) for d in range(28)]
    elevated = resting_hr_trend(_series(baseline + [(d, 56.0) for d in range(28, 35)]))
    assert elevated.usable
    assert elevated.band == "elevated"
    assert elevated.delta_bpm == pytest.approx(6.0)
    lowered = resting_hr_trend(_series(baseline + [(d, 44.0) for d in range(28, 35)]))
    assert lowered.band == "lowered"
    within = resting_hr_trend(_series(baseline + [(d, 53.0) for d in range(28, 35)]))
    assert within.band == "normal"


def test_resting_hr_out_of_range_rejected():
    with pytest.raises(ValueError, match="resting_hr value"):
        resting_hr_trend([WellnessSample(day_index=0, value=150.0)])


def test_sleep_short_week_and_debt():
    trend = sleep_trend(_series([(d, 6.0) for d in range(7)]), nightly_target_h=8.0)
    assert trend.usable
    assert trend.band == "short"
    assert trend.rolling_mean_h == pytest.approx(6.0)
    assert trend.weekly_debt_h == pytest.approx(14.0)  # 7 nights x 2 h


def test_sleep_on_target_is_ok_and_surplus_adds_no_negative_debt():
    trend = sleep_trend(_series([(d, 8.5) for d in range(7)]))
    assert trend.band == "ok"
    assert trend.weekly_debt_h == pytest.approx(0.0)


def test_sleep_needs_three_nights_and_valid_target():
    thin = sleep_trend(_series([(0, 7.0), (1, 7.0)]))
    assert not thin.usable
    assert thin.reason is not None and "3 sleep nights" in thin.reason
    with pytest.raises(ValueError, match="nightly_target_h"):
        sleep_trend(_series([(d, 7.0) for d in range(7)]), nightly_target_h=2.0)


def test_wellness_trend_composes_and_skips_missing_signals():
    trend = wellness_trend(hrv=_flat_month(60.0), sleep=_series([(d, 7.5) for d in range(7)]))
    assert trend.hrv is not None and trend.hrv.usable
    assert trend.resting_hr is None
    assert trend.sleep is not None and trend.sleep.band == "ok"


def test_windows_ignore_data_older_than_the_baseline():
    # An ancient outlier far before the 35-day window must not move the baseline.
    old = [(0, 30.0)]
    baseline = [(d, 60.0) for d in range(40, 68)]
    week = [(d, 60.0) for d in range(68, 75)]
    trend = hrv_trend(_series(old + baseline + week))
    assert trend.usable
    assert trend.band == "normal"
    assert trend.baseline_ln_mean == pytest.approx(math.log(60.0))
