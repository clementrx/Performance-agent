"""Phase 2 storage: ReadinessEntry schema, readiness.jsonl store, session extensions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import ReadinessEntry, SessionEntry
from performance_agent.memory.store import (
    append_readiness,
    append_session,
    read_readiness,
    read_sessions,
)

# --- ReadinessEntry schema ------------------------------------------------


def test_readiness_entry_defaults_schema_version():
    entry = ReadinessEntry(at=datetime(2026, 7, 12, 7, 0), sleep=2, fatigue=3, soreness=2, stress=1)
    assert entry.schema_version == 1
    assert entry.hrv_ms is None


@pytest.mark.parametrize("field", ["sleep", "fatigue", "soreness", "stress"])
def test_readiness_items_bounded_1_to_7(field):
    good = {"at": datetime(2026, 7, 12, 7, 0), "sleep": 3, "fatigue": 3, "soreness": 3, "stress": 3}
    with pytest.raises(ValidationError):
        ReadinessEntry.model_validate({**good, field: 8})
    with pytest.raises(ValidationError):
        ReadinessEntry.model_validate({**good, field: 0})


def test_readiness_rejects_tz_aware_timestamp():
    with pytest.raises(ValidationError, match="naive"):
        ReadinessEntry(
            at=datetime(2026, 7, 12, 7, 0, tzinfo=UTC), sleep=2, fatigue=2, soreness=2, stress=2
        )


def test_readiness_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ReadinessEntry.model_validate(
            {
                "at": datetime(2026, 7, 12, 7, 0),
                "sleep": 2,
                "fatigue": 2,
                "soreness": 2,
                "stress": 2,
                "mood": 3,
            }
        )


# --- readiness.jsonl store ------------------------------------------------


def test_readiness_append_and_read_in_order(tmp_path):
    first = ReadinessEntry(at=datetime(2026, 7, 11, 7, 0), sleep=2, fatigue=2, soreness=2, stress=2)
    second = ReadinessEntry(
        at=datetime(2026, 7, 12, 7, 0), sleep=4, fatigue=5, soreness=3, stress=4, hrv_ms=45.0
    )
    append_readiness(tmp_path, first)
    append_readiness(tmp_path, second)
    assert read_readiness(tmp_path) == [first, second]


def test_readiness_read_empty_when_missing(tmp_path):
    assert read_readiness(tmp_path) == []


def test_readiness_file_is_one_json_per_line(tmp_path):
    append_readiness(
        tmp_path,
        ReadinessEntry(at=datetime(2026, 7, 11, 7, 0), sleep=2, fatigue=2, soreness=2, stress=2),
    )
    lines = (tmp_path / "readiness.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("{")


# --- SessionEntry backward compatibility + new fields ---------------------


def test_session_new_fields_default_to_programmed():
    entry = SessionEntry(performed_at=datetime(2026, 7, 12, 18, 0))
    assert entry.source == "programmed"
    assert entry.session_plan_id is None
    assert entry.avg_hr is None


def test_legacy_session_line_still_loads_with_defaults(tmp_path):
    legacy = '{"performed_at": "2026-07-01T18:00:00", "kind": "run", "rpe": 5}'
    (tmp_path / "sessions.jsonl").write_text(legacy + "\n", encoding="utf-8")
    session = read_sessions(tmp_path)[0]
    assert session.source == "programmed"
    assert session.session_plan_id is None
    assert session.avg_hr is None


def test_external_session_round_trips(tmp_path):
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 12, 20, 0),
        kind="football match",
        source="external",
        session_plan_id="w03-s2-lower-heavy",
        avg_hr=155.0,
        rpe=8,
        duration_min=90,
    )
    append_session(tmp_path, entry)
    assert read_sessions(tmp_path)[0] == entry


def test_session_plan_id_pattern_is_enforced():
    with pytest.raises(ValidationError):
        SessionEntry(performed_at=datetime(2026, 7, 12, 18, 0), session_plan_id="Not A Slug")
