"""Competition protocols: per-event immutable versions, calendar validation."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    CalendarEvent,
    CompetitionProtocol,
    ProtocolDay,
    ProtocolLine,
)

TODAY = date(2026, 7, 25)
EVENT_DATE = date(2026, 8, 1)


def _seed_event(base, event_id="nationals", event_date=EVENT_DATE):
    store.upsert_calendar_event(
        base,
        CalendarEvent(
            id=event_id, date=event_date, kind="competition", priority="A", label="Nationals"
        ),
    )


def _protocol(event_id="nationals", event_date=EVENT_DATE, **overrides):
    fields = {
        "version": 1,
        "event_id": event_id,
        "event_date": event_date,
        "goal_id": "sub-40-10k",
        "created_on": TODAY,
        "window_days": 7,
        "days": [ProtocolDay(day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up.")])],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_save_and_read_roundtrip(tmp_path):
    _seed_event(tmp_path)
    path, version = store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    assert version == 1
    assert path == tmp_path / "competition" / "protocol-nationals-v1.md"
    assert (tmp_path / "competition" / "protocol-nationals-v1.yaml").exists()
    stored = store.read_competition_protocol(tmp_path, "nationals")
    assert stored is not None
    assert stored.version == 1
    assert stored.protocol.event_id == "nationals"
    assert "# Competition protocol v1" in stored.markdown


def test_v2_requires_reason_and_versions_are_per_event(tmp_path):
    _seed_event(tmp_path)
    _seed_event(tmp_path, event_id="tune-up", event_date=date(2026, 7, 30))
    store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    _, v2 = store.save_competition_protocol(
        tmp_path, _protocol(), reason="taper adjusted", today=TODAY
    )
    assert v2 == 2
    _, other = store.save_competition_protocol(
        tmp_path,
        _protocol(event_id="tune-up", event_date=date(2026, 7, 30)),
        today=TODAY,
    )
    assert other == 1  # independent lineage per event


def test_save_rejects_unknown_event_and_date_drift(tmp_path):
    with pytest.raises(ValueError, match="calendar"):
        store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    _seed_event(tmp_path)
    with pytest.raises(ValueError, match="date"):
        store.save_competition_protocol(
            tmp_path, _protocol(event_date=date(2026, 8, 2)), today=TODAY
        )


def test_save_rejects_past_event(tmp_path):
    _seed_event(tmp_path)
    with pytest.raises(ValueError, match="past"):
        store.save_competition_protocol(tmp_path, _protocol(), today=date(2026, 8, 5))


def test_latest_version_none_when_empty(tmp_path):
    assert store.latest_competition_protocol_version(tmp_path, "nationals") is None
    assert store.read_competition_protocol(tmp_path, "nationals") is None


def test_read_rejects_unknown_version(tmp_path):
    _seed_event(tmp_path)
    store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    with pytest.raises(ValueError, match="does not exist"):
        store.read_competition_protocol(tmp_path, "nationals", version=3)


def test_read_rejects_frontmatter_version_mismatch(tmp_path):
    _seed_event(tmp_path)
    md_path, _ = store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    tampered = md_path.read_text(encoding="utf-8").replace("version: 1", "version: 2", 1)
    md_path.write_text(tampered, encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter declares version"):
        store.read_competition_protocol(tmp_path, "nationals")
