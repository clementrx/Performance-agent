from datetime import datetime

import pytest

from performance_agent.memory.schemas import CheckinEntry, SessionEntry
from performance_agent.memory.store import (
    append_checkin,
    append_session,
    read_checkins,
    read_sessions,
)


def test_sessions_append_and_read_in_order(tmp_path):
    first = SessionEntry(performed_at=datetime(2026, 7, 1, 18, 0), rpe=7, duration_min=60)
    second = SessionEntry(performed_at=datetime(2026, 7, 3, 18, 0), rpe=5, duration_min=45)
    append_session(tmp_path, first)
    append_session(tmp_path, second)
    sessions = read_sessions(tmp_path)
    assert sessions == [first, second]


def test_sessions_file_is_one_json_per_line(tmp_path):
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 7, 1, 18, 0)))
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 7, 2, 18, 0)))
    lines = (tmp_path / "sessions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("{")


def test_read_sessions_empty_when_missing(tmp_path):
    assert read_sessions(tmp_path) == []


def test_first_checkin_has_no_days_since_last(tmp_path):
    stored = append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0)))
    assert stored.days_since_last is None


def test_checkin_days_since_last_is_auto_filled(tmp_path):
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    stored = append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0)))
    assert stored.days_since_last == 14
    assert read_checkins(tmp_path)[-1].days_since_last == 14


def test_explicit_days_since_last_is_respected(tmp_path):
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    stored = append_checkin(
        tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0), days_since_last=99)
    )
    assert stored.days_since_last == 99


def test_backdated_checkin_yields_negative_days_since_last(tmp_path):
    # backfill/corrections are legitimate; negative deltas are intentional
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0)))
    stored = append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 5, 9, 0)))
    assert stored.days_since_last == -5


def test_schema_invalid_session_line_names_the_file(tmp_path):
    (tmp_path / "sessions.jsonl").write_text(
        '{"performed_at": "2026-07-01T18:00:00", "rpe": 15}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"sessions\.jsonl"):
        read_sessions(tmp_path)
