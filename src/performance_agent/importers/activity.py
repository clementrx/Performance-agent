"""Parse activity files (.fit/.tcx/.gpx/CSV) into a normalized summary.

Every parser returns duration, distance and average HR when the file carries
them; missing values come back as None (the athlete fills the gap on
confirmation). Malformed files raise ActivityImportError with an actionable
message — never a bare crash. Timestamps are normalized to naive local time to
match the athlete-data schema convention.
"""

import csv
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path

import fitdecode

_TCX_NS = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"
_GPX_NS = "{http://www.topografix.com/GPX/1/1}"
_GPX_TPX_HR = "hr"  # matched by local tag, namespace-agnostic (TrackPointExtension)
_EARTH_RADIUS_M = 6371000.0
_MIN_SPAN_POINTS = 2  # need two timestamps/coordinates to derive a duration or distance

_DURATION_COLUMNS = (
    "duration_s",
    "duration_min",
    "moving_time",
    "elapsed_time",
    "duration",
    "time",
)
_DISTANCE_COLUMNS = ("distance_m", "distance_km", "distance")
_HR_COLUMNS = ("avg_hr", "average_heart_rate", "avg_heart_rate", "heart_rate", "hr")
_START_COLUMNS = ("start_time", "timestamp", "date", "datetime")
_SPORT_COLUMNS = ("sport", "activity_type", "type")
_HRV_COLUMNS = ("hrv_ms", "rmssd_ms", "rmssd", "hrv")


class ActivityImportError(ValueError):
    """A file could not be parsed into an activity (bad format or missing data)."""


@dataclass(frozen=True)
class ParsedActivity:
    """A normalized activity summary; any field may be None when absent from the file."""

    sport: str | None
    start_time: datetime | None
    duration_s: float | None
    distance_m: float | None
    avg_hr: float | None


@dataclass(frozen=True)
class HrvReading:
    """One dated HRV measurement from an HRV CSV export (raw rMSSD in ms)."""

    at: datetime
    hrv_ms: float


def _naive_local(value: datetime) -> datetime:
    """Drop timezone info (converting to local wall-clock) to match the schema."""
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _parse_iso(text: str) -> datetime | None:
    try:
        return _naive_local(datetime.fromisoformat(text.strip()))
    except ValueError:
        return None


def parse_activity_file(path: Path) -> ParsedActivity:
    """Parse one activity file into a normalized summary by its extension.

    Supports .fit (binary, via fitdecode), .tcx and .gpx (XML, stdlib), and
    activity-summary .csv (Garmin/Strava export). Raises ActivityImportError on
    an unknown extension, an unreadable file, or a CSV that carries no activity
    columns.
    """
    if not path.exists():
        msg = f"activity file not found: {path}"
        raise ActivityImportError(msg)
    suffix = path.suffix.casefold()
    parsers = {
        ".fit": _parse_fit,
        ".tcx": _parse_tcx,
        ".gpx": _parse_gpx,
        ".csv": _parse_activity_csv,
    }
    parser = parsers.get(suffix)
    if parser is None:
        msg = (
            f"unsupported activity file '{path.name}' (extension {suffix or 'none'}); "
            "supported: .fit, .tcx, .gpx, .csv"
        )
        raise ActivityImportError(msg)
    return parser(path)


def _parse_fit(path: Path) -> ParsedActivity:
    session: dict[str, object] = {}
    records: list[dict[str, object]] = []
    try:
        with fitdecode.FitReader(str(path)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "session" and not session:
                    session = _fit_fields(
                        frame,
                        (
                            "start_time",
                            "total_elapsed_time",
                            "total_distance",
                            "avg_heart_rate",
                            "sport",
                        ),
                    )
                elif frame.name == "record":
                    records.append(_fit_fields(frame, ("timestamp", "distance", "heart_rate")))
    except fitdecode.FitError as exc:
        msg = f"'{path.name}' is not a readable FIT file: {exc}"
        raise ActivityImportError(msg) from exc
    if session:
        return _activity_from_fit_session(session)
    if records:
        return _activity_from_fit_records(records)
    msg = f"'{path.name}' has no session or record data to import"
    raise ActivityImportError(msg)


def _fit_fields(frame: fitdecode.FitDataMessage, names: tuple[str, ...]) -> dict[str, object]:
    return {name: frame.get_value(name, fallback=None) for name in names if frame.has_field(name)}


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _activity_from_fit_session(session: dict[str, object]) -> ParsedActivity:
    start = session.get("start_time")
    sport = session.get("sport")
    return ParsedActivity(
        sport=str(sport) if isinstance(sport, str) else None,
        start_time=_naive_local(start) if isinstance(start, datetime) else None,
        duration_s=_as_float(session.get("total_elapsed_time")),
        distance_m=_as_float(session.get("total_distance")),
        avg_hr=_as_float(session.get("avg_heart_rate")),
    )


def _activity_from_fit_records(records: list[dict[str, object]]) -> ParsedActivity:
    times = [r["timestamp"] for r in records if isinstance(r.get("timestamp"), datetime)]
    distances = [d for r in records if (d := _as_float(r.get("distance"))) is not None]
    hrs = [h for r in records if (h := _as_float(r.get("heart_rate"))) is not None]
    duration = (max(times) - min(times)).total_seconds() if len(times) >= _MIN_SPAN_POINTS else None
    return ParsedActivity(
        sport=None,
        start_time=_naive_local(min(times)) if times else None,
        duration_s=duration,
        distance_m=max(distances) if distances else None,
        avg_hr=sum(hrs) / len(hrs) if hrs else None,
    )


def _xml_root(path: Path, label: str) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        msg = f"'{path.name}' is not valid {label} XML: {exc}"
        raise ActivityImportError(msg) from exc


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _parse_tcx(path: Path) -> ParsedActivity:
    root = _xml_root(path, "TCX")
    activity = root.find(f".//{_TCX_NS}Activity")
    if activity is None:
        msg = f"'{path.name}' has no <Activity> element (not a TCX activity export)"
        raise ActivityImportError(msg)
    laps = activity.findall(f"{_TCX_NS}Lap")
    durations = [_child_float(lap, f"{_TCX_NS}TotalTimeSeconds") for lap in laps]
    distances = [_child_float(lap, f"{_TCX_NS}DistanceMeters") for lap in laps]
    hrs = [
        hr
        for lap in laps
        if (hr := _child_float(lap.find(f"{_TCX_NS}AverageHeartRateBpm"), f"{_TCX_NS}Value"))
        is not None
    ]
    id_node = activity.find(f"{_TCX_NS}Id")
    start = _parse_iso(id_node.text) if id_node is not None and id_node.text else None
    return ParsedActivity(
        sport=activity.get("Sport"),
        start_time=start,
        duration_s=_sum_present(durations),
        distance_m=_sum_present(distances),
        avg_hr=_mean(hrs),
    )


def _child_float(node: ET.Element | None, tag: str) -> float | None:
    if node is None:
        return None
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    try:
        return float(child.text)
    except ValueError:
        return None


def _sum_present(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _parse_gpx(path: Path) -> ParsedActivity:
    root = _xml_root(path, "GPX")
    points = root.findall(f".//{_GPX_NS}trkpt")
    if not points:
        msg = f"'{path.name}' has no track points (<trkpt>) to import"
        raise ActivityImportError(msg)
    times = [t for p in points if (t := _trkpt_time(p)) is not None]
    hrs = [h for p in points if (h := _trkpt_hr(p)) is not None]
    type_node = root.find(f".//{_GPX_NS}trk/{_GPX_NS}type")
    duration = (max(times) - min(times)).total_seconds() if len(times) >= _MIN_SPAN_POINTS else None
    return ParsedActivity(
        sport=type_node.text if type_node is not None else None,
        start_time=min(times) if times else None,
        duration_s=duration,
        distance_m=_gpx_distance(points),
        avg_hr=_mean(hrs),
    )


def _trkpt_time(point: ET.Element) -> datetime | None:
    node = point.find(f"{_GPX_NS}time")
    return _parse_iso(node.text) if node is not None and node.text else None


def _trkpt_hr(point: ET.Element) -> float | None:
    for node in point.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == _GPX_TPX_HR and node.text:
            try:
                return float(node.text)
            except ValueError:
                return None
    return None


def _gpx_distance(points: list[ET.Element]) -> float | None:
    coords = [c for p in points if (c := _trkpt_coords(p)) is not None]
    if len(coords) < _MIN_SPAN_POINTS:
        return None
    total = 0.0
    for (lat1, lon1), (lat2, lon2) in pairwise(coords):
        total += _haversine_m(lat1, lon1, lat2, lon2)
    return total


def _trkpt_coords(point: ET.Element) -> tuple[float, float] | None:
    lat, lon = point.get("lat"), point.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except ValueError:
        return None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        msg = f"could not read '{path.name}': {exc}"
        raise ActivityImportError(msg) from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        msg = f"'{path.name}' is empty; expected a CSV header row"
        raise ActivityImportError(msg)
    normalized = [name.strip().casefold() for name in reader.fieldnames]
    rows = [{k.strip().casefold(): (v or "").strip() for k, v in row.items()} for row in reader]
    return normalized, rows


def _pick(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in columns), None)


def looks_like_hrv_csv(path: Path) -> bool:
    """True when a .csv carries an HRV column but no activity duration/distance."""
    columns, _ = _read_csv_rows(path)
    has_hrv = _pick(columns, _HRV_COLUMNS) is not None
    has_activity = (
        _pick(columns, _DURATION_COLUMNS) is not None
        or _pick(columns, _DISTANCE_COLUMNS) is not None
    )
    return has_hrv and not has_activity


def parse_hrv_csv(path: Path) -> list[HrvReading]:
    """Parse an HRV CSV export into dated rMSSD readings (raw ms).

    Needs a date/timestamp column and one HRV column (hrv_ms/rmssd_ms/rmssd/hrv).
    Rows with an unparseable date or a non-positive HRV are skipped; an empty
    result raises ActivityImportError so the caller can report the bad file.
    """
    columns, rows = _read_csv_rows(path)
    date_col = _pick(columns, _START_COLUMNS)
    hrv_col = _pick(columns, _HRV_COLUMNS)
    if date_col is None or hrv_col is None:
        msg = f"'{path.name}' needs a date column and an HRV column (hrv_ms/rmssd/hrv)"
        raise ActivityImportError(msg)
    readings: list[HrvReading] = []
    for row in rows:
        at = _parse_iso(row.get(date_col, ""))
        hrv = _to_float(row.get(hrv_col, ""))
        if at is not None and hrv is not None and hrv > 0:
            readings.append(HrvReading(at=at, hrv_ms=hrv))
    if not readings:
        msg = f"'{path.name}' had no rows with a valid date and positive HRV value"
        raise ActivityImportError(msg)
    return readings


def _to_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _parse_activity_csv(path: Path) -> ParsedActivity:
    columns, rows = _read_csv_rows(path)
    if not rows:
        msg = f"'{path.name}' has a header but no data rows"
        raise ActivityImportError(msg)
    duration_col = _pick(columns, _DURATION_COLUMNS)
    distance_col = _pick(columns, _DISTANCE_COLUMNS)
    if duration_col is None and distance_col is None:
        msg = (
            f"'{path.name}' has no duration or distance column; expected one of "
            f"{list(_DURATION_COLUMNS)} / {list(_DISTANCE_COLUMNS)}"
        )
        raise ActivityImportError(msg)
    row = rows[0]
    start_col = _pick(columns, _START_COLUMNS)
    sport_col = _pick(columns, _SPORT_COLUMNS)
    hr_col = _pick(columns, _HR_COLUMNS)
    return ParsedActivity(
        sport=row.get(sport_col) or None if sport_col else None,
        start_time=_parse_iso(row.get(start_col, "")) if start_col else None,
        duration_s=_csv_duration_s(row.get(duration_col, ""), duration_col)
        if duration_col
        else None,
        distance_m=_csv_distance_m(row.get(distance_col, ""), distance_col)
        if distance_col
        else None,
        avg_hr=_to_float(row.get(hr_col, "")) if hr_col else None,
    )


def _csv_duration_s(text: str, column: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    if ":" in text:
        return _clock_to_seconds(text)
    value = _to_float(text)
    if value is None:
        return None
    return value * 60.0 if column == "duration_min" else value


def _clock_to_seconds(text: str) -> float | None:
    parts = text.split(":")
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        return None
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def _csv_distance_m(text: str, column: str) -> float | None:
    value = _to_float(text.strip())
    if value is None:
        return None
    return value * 1000.0 if column == "distance_km" else value
