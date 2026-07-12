"""Per-format parsing and malformed-file error paths."""

import pytest

from performance_agent.importers.activity import (
    ActivityImportError,
    looks_like_hrv_csv,
    parse_activity_file,
    parse_hrv_csv,
)


@pytest.mark.parametrize("name", ["run.fit", "run.tcx", "activity.csv"])
def test_summary_formats_extract_duration_distance_hr(fixtures, name):
    activity = parse_activity_file(fixtures / name)
    assert activity.duration_s == pytest.approx(2730.0)
    assert activity.distance_m == pytest.approx(8000.0)
    assert activity.avg_hr == pytest.approx(152.0)
    assert activity.sport is not None


def test_gpx_derives_duration_and_distance_from_track(fixtures):
    activity = parse_activity_file(fixtures / "run.gpx")
    assert activity.duration_s == pytest.approx(540.0)  # 07:30 -> 07:39
    assert activity.distance_m is not None and activity.distance_m > 1000
    assert activity.avg_hr == pytest.approx((140 + 150 + 158 + 160) / 4)
    assert activity.sport == "running"


@pytest.mark.parametrize("name", ["run.fit", "run.tcx", "run.gpx"])
def test_timezone_aware_files_return_naive_datetimes(fixtures, name):
    activity = parse_activity_file(fixtures / name)
    assert activity.start_time is not None
    assert activity.start_time.tzinfo is None


def test_csv_without_timezone_is_left_naive(fixtures):
    activity = parse_activity_file(fixtures / "activity.csv")
    assert activity.start_time is not None
    assert activity.start_time.tzinfo is None
    assert activity.start_time.hour == 7


@pytest.mark.parametrize(
    ("name", "needle"),
    [
        ("malformed.fit", "not a readable FIT file"),
        ("malformed.tcx", "not valid TCX XML"),
        ("empty.gpx", "no track points"),
        ("empty.csv", "expected a CSV header row"),
    ],
)
def test_malformed_files_raise_actionable_errors(fixtures, name, needle):
    with pytest.raises(ActivityImportError, match=needle):
        parse_activity_file(fixtures / name)


def test_unsupported_extension_is_rejected(tmp_path):
    bogus = tmp_path / "workout.xyz"
    bogus.write_text("nope", encoding="utf-8")
    with pytest.raises(ActivityImportError, match="unsupported activity file"):
        parse_activity_file(bogus)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ActivityImportError, match="not found"):
        parse_activity_file(tmp_path / "ghost.fit")


def test_activity_csv_without_duration_or_distance_is_rejected(tmp_path):
    path = tmp_path / "meta.csv"
    path.write_text("sport,avg_hr\nrunning,150\n", encoding="utf-8")
    with pytest.raises(ActivityImportError, match="no duration or distance column"):
        parse_activity_file(path)


@pytest.mark.parametrize(
    ("clock", "seconds"),
    [("45:30", 2730.0), ("1:15:00", 4500.0)],
)
def test_csv_duration_accepts_clock_notation(tmp_path, clock, seconds):
    path = tmp_path / "clock.csv"
    path.write_text(f"duration,distance_m\n{clock},5000\n", encoding="utf-8")
    activity = parse_activity_file(path)
    assert activity.duration_s == pytest.approx(seconds)


def test_hrv_csv_is_detected_and_parsed(fixtures):
    assert looks_like_hrv_csv(fixtures / "hrv.csv") is True
    readings = parse_hrv_csv(fixtures / "hrv.csv")
    assert [r.hrv_ms for r in readings] == [62.5, 58.0, 65.2]
    assert all(r.at.tzinfo is None for r in readings)


def test_activity_csv_is_not_mistaken_for_hrv(fixtures):
    assert looks_like_hrv_csv(fixtures / "activity.csv") is False


def test_hrv_csv_without_hrv_column_is_rejected(tmp_path):
    path = tmp_path / "bad_hrv.csv"
    path.write_text("date,mood\n2026-06-14,good\n", encoding="utf-8")
    with pytest.raises(ActivityImportError, match="date column and an HRV column"):
        parse_hrv_csv(path)
