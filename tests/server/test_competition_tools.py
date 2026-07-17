"""MCP wrappers for the pre-competition protocol."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    CalendarEvent,
    CompetitionProtocol,
    Guidance,
    Profile,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.server import competition_tools

TODAY = date.today()


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    store.write_profile(tmp_path, Profile())
    store.upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nationals",
            date=TODAY.replace(year=TODAY.year + 1),
            kind="competition",
            priority="A",
            label="Nationals",
        ),
    )
    return tmp_path


def _protocol(**overrides):
    fields = {
        "version": 1,
        "event_id": "nationals",
        "event_date": TODAY.replace(year=TODAY.year + 1),
        "goal_id": "sub-40-10k",
        "created_on": TODAY,
        "window_days": 7,
        "days": [ProtocolDay(day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up.")])],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_engine_wrappers_quote_engine_numbers(athlete_dir):  # noqa: ARG001 - fixture side effect
    carbs = competition_tools.carb_loading_targets(70.0, 180.0)
    assert carbs["carb_g_per_day_high"] == 840.0
    attempts = competition_tools.select_attempts("Squat", 200.0, 205.0)
    assert attempts["lift"] == "Squat"
    assert attempts["third_kg"] == 205.0
    splits = competition_tools.pacing_plan(10000.0, 2400.0)
    assert len(splits) == 10


def test_save_renders_html_and_read_roundtrips(athlete_dir):  # noqa: ARG001 - fixture side effect
    result = competition_tools.save_competition_protocol(_protocol())
    assert result["version"] == 1
    page = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "<script" not in page
    view = competition_tools.read_competition_protocol("nationals")
    assert view["version"] == 1
    assert view["protocol"]["event_id"] == "nationals"


def test_save_rejects_unknown_citation(athlete_dir):  # noqa: ARG001 - fixture side effect
    protocol = _protocol(advice=[Guidance(text="Fake.", cite="phantom-id")])
    with pytest.raises(ValueError, match="phantom-id"):
        competition_tools.save_competition_protocol(protocol)


def test_read_without_protocol_raises(athlete_dir):  # noqa: ARG001 - fixture side effect
    with pytest.raises(ValueError, match="no protocol"):
        competition_tools.read_competition_protocol("nationals")


def test_save_survives_when_html_write_fails(athlete_dir, monkeypatch):
    def raiser(*_args, **_kwargs):
        raise OSError("disk full")

    # store.save_competition_protocol also calls os.replace internally (its own
    # atomic write of the md/yaml) via the SAME os module object, so patching
    # os.replace globally would fail the store write instead of the html write
    # this test targets. Rebinding the `os` name inside competition_tools'
    # namespace scopes the failure to this module's own os.replace call.
    monkeypatch.setattr(competition_tools, "os", SimpleNamespace(replace=raiser))
    with pytest.raises(ValueError, match=r"protocol v1 was saved"):
        competition_tools.save_competition_protocol(_protocol())
    protocol_dir = athlete_dir / "competition"
    assert (protocol_dir / "protocol-nationals-v1.md").exists()
    assert (protocol_dir / "protocol-nationals-v1.yaml").exists()
    assert not (protocol_dir / "protocol-nationals-v1.html").exists()
