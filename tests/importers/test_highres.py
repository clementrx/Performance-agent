"""Tests for high-resolution ingestion: power/cadence/splits and VBT CSV."""

import pytest

from performance_agent.importers.activity import (
    ActivityImportError,
    _fit_power,
    _fit_splits,
    _normalized_power,
    _power_summary,
    parse_activity_file,
)
from performance_agent.importers.vbt_csv import looks_like_vbt_csv, parse_vbt_csv


def test_normalized_power_short_stream_is_none():
    assert _normalized_power([200.0] * 10) is None


def test_normalized_power_constant_stream_equals_mean():
    powers = [200.0] * 120
    assert _normalized_power(powers) == pytest.approx(200.0)


def test_normalized_power_variable_exceeds_mean():
    # A spiky stream has NP above its arithmetic mean (4th-power weighting).
    powers = ([100.0] * 30 + [300.0] * 30) * 4
    mean = sum(powers) / len(powers)
    np = _normalized_power(powers)
    assert np is not None and np > mean


def test_power_summary_none_when_empty():
    assert _power_summary(None, [], []) is None


def test_fit_power_from_records():
    records: list[dict[str, object]] = [{"power": 200.0, "cadence": 90.0} for _ in range(60)]
    summary = _fit_power({}, records)
    assert summary is not None
    assert summary.avg_watts == pytest.approx(200.0)
    assert summary.avg_cadence == pytest.approx(90.0)


def test_fit_power_prefers_session_np():
    records: list[dict[str, object]] = [{"power": 200.0} for _ in range(60)]
    session: dict[str, object] = {"normalized_power": 250.0}
    summary = _fit_power(session, records)
    assert summary is not None
    assert summary.normalized_watts == pytest.approx(250.0)


def test_fit_splits():
    laps: list[dict[str, object]] = [
        {"total_distance": 5000.0, "total_elapsed_time": 600.0},
        {"total_distance": 5200.0, "total_elapsed_time": 605.0},
    ]
    splits = _fit_splits(laps)
    assert len(splits) == 2
    assert splits[0].distance_m == pytest.approx(5000.0)
    assert splits[1].duration_s == pytest.approx(605.0)


def test_tcx_ride_extracts_splits_and_power(fixtures):
    activity = parse_activity_file(fixtures / "ride.tcx")
    assert len(activity.splits) == 2
    assert activity.splits[0].distance_m == pytest.approx(5000.0)
    assert activity.power is not None
    assert activity.power.avg_watts == pytest.approx(220.0)  # mean of 210, 230
    assert activity.power.avg_cadence == pytest.approx(90.0)  # mean of 88, 92


def test_run_tcx_has_no_power(fixtures):
    activity = parse_activity_file(fixtures / "run.tcx")
    assert activity.power is None


def test_vbt_csv_parses(fixtures):
    sets = parse_vbt_csv(fixtures / "vbt.csv")
    assert len(sets) == 3
    assert sets[0].exercise == "Back Squat"
    assert sets[0].load_kg == pytest.approx(100.0)
    assert sets[0].mean_velocity == pytest.approx(0.75)
    assert sets[0].top_velocity == pytest.approx(0.82)


def test_vbt_csv_variant_columns(fixtures):
    sets = parse_vbt_csv(fixtures / "vbt_variant.csv")
    assert len(sets) == 2
    assert sets[0].exercise == "Bench Press"
    assert sets[0].top_velocity is None


def test_vbt_csv_missing_columns_raises(fixtures):
    with pytest.raises(ActivityImportError, match="not a VBT export"):
        parse_vbt_csv(fixtures / "vbt_bad.csv")


def test_looks_like_vbt_csv(fixtures):
    assert looks_like_vbt_csv(fixtures / "vbt.csv") is True
    assert looks_like_vbt_csv(fixtures / "vbt_bad.csv") is False
    assert looks_like_vbt_csv(fixtures / "hrv.csv") is False
