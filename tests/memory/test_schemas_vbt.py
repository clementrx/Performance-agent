"""Schema tests for the VBT set, session vbt_sets, and sensor field (optionality)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import Profile, SessionEntry, VbtSet


def test_vbt_set_round_trip():
    s = VbtSet(exercise="Back Squat", load_kg=120.0, mean_velocity=0.55, reps=3, top_velocity=0.6)
    reloaded = VbtSet.model_validate_json(s.model_dump_json())
    assert reloaded.mean_velocity == pytest.approx(0.55)


def test_vbt_set_velocity_must_be_positive():
    with pytest.raises(ValidationError):
        VbtSet(exercise="Squat", load_kg=100.0, mean_velocity=0.0, reps=1)


def test_rep_velocities_bounds():
    with pytest.raises(ValidationError, match="rep_velocities"):
        VbtSet(
            exercise="Squat", load_kg=100.0, mean_velocity=0.5, reps=2, rep_velocities=[0.5, 12.0]
        )


def test_session_without_vbt_sets_defaults_empty():
    entry = SessionEntry(performed_at=datetime(2026, 7, 1, 10, 0))
    assert entry.vbt_sets == []


def test_old_session_json_without_vbt_sets_still_parses():
    # A pre-Phase-4 session log has no vbt_sets key; it must remain readable.
    legacy = '{"performed_at": "2026-07-01T10:00:00", "kind": "strength_heavy"}'
    entry = SessionEntry.model_validate_json(legacy)
    assert entry.vbt_sets == []


def test_session_carries_vbt_sets():
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 1, 10, 0),
        vbt_sets=[VbtSet(exercise="Squat", load_kg=100.0, mean_velocity=0.6, reps=3)],
    )
    assert entry.vbt_sets[0].exercise == "Squat"


def test_profile_equipment_sensors_optional():
    assert Profile().equipment_sensors == []
    assert Profile(equipment_sensors=["vbt", "force_plate"]).equipment_sensors == [
        "vbt",
        "force_plate",
    ]
