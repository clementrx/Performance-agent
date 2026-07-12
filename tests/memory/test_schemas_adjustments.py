"""Schema contract for session_adjustments.jsonl entries."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import AdjustmentInputs, SessionAdjustmentEntry


def test_entry_round_trips_through_json():
    entry = SessionAdjustmentEntry(
        at=datetime(2026, 7, 13, 18, 0),
        session_plan_id="w01-s1-lower",
        kind="time",
        inputs=AdjustmentInputs(available_minutes=35, missing_equipment=["rack"]),
        deltas_summary=["dropped optional block"],
        applied=True,
    )
    assert SessionAdjustmentEntry.model_validate_json(entry.model_dump_json()) == entry
    assert entry.schema_version == 1


def test_defaults_are_safe():
    entry = SessionAdjustmentEntry(
        at=datetime(2026, 7, 13, 18, 0), session_plan_id="w01-s1", kind="manual"
    )
    assert entry.applied is True
    assert entry.deltas_summary == []
    assert entry.inputs.band is None


def test_timezone_aware_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="naive"):
        SessionAdjustmentEntry(
            at=datetime(2026, 7, 13, 18, 0, tzinfo=UTC),
            session_plan_id="w01-s1",
            kind="readiness",
        )


def test_bad_kind_is_rejected():
    with pytest.raises(ValidationError):
        SessionAdjustmentEntry(
            at=datetime(2026, 7, 13, 18, 0),
            session_plan_id="w01-s1",
            kind="whatever",  # ty: ignore[invalid-argument-type]
        )


def test_bad_session_id_slug_is_rejected():
    with pytest.raises(ValidationError):
        SessionAdjustmentEntry(
            at=datetime(2026, 7, 13, 18, 0),
            session_plan_id="Not A Slug",
            kind="readiness",
        )
