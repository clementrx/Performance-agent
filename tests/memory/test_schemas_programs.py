"""Validators for the structured ProgramPlan family."""

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    ProgramPlan,
    SessionPlan,
)
from tests.program_plans import a_session, minimal_plan


def _block(**overrides: object) -> ExerciseBlock:
    fields: dict[str, object] = {
        "exercise": "Back Squat",
        "priority": "primary",
        "sets": 3,
        "reps": "5",
        "load_kg": 100.0,
        "progression_rule": "double_progression(5-5, +2.5kg)",
    }
    fields.update(overrides)
    return ExerciseBlock.model_validate(fields)


def test_single_intensity_mode_is_enforced():
    with pytest.raises(ValidationError, match="one channel"):
        _block(load_kg=100.0, rpe=8.0)


def test_one_intensity_mode_is_allowed():
    assert _block(load_kg=100.0, rpe=None).load_kg == 100.0


def test_a_block_without_intensity_is_allowed_for_recovery():
    block = _block(load_kg=None, reps=None, duration_min=15.0, progression_rule="none")
    assert block.duration_min == 15.0


def test_a_block_must_state_some_volume():
    with pytest.raises(ValidationError, match="volume"):
        _block(reps=None, load_kg=100.0)


def test_pace_cannot_pair_with_reps():
    with pytest.raises(ValidationError, match="pace"):
        _block(load_kg=None, reps="5", pace_s_per_km=300.0)


def test_pace_with_distance_is_fine():
    block = _block(load_kg=None, reps=None, distance_m=5000.0, pace_s_per_km=300.0)
    assert block.pace_s_per_km == 300.0


def test_fallbacks_must_be_non_empty():
    with pytest.raises(ValidationError):
        Fallbacks(low_readiness="", short_on_time="x", missing_equipment="y")


def test_session_purpose_must_be_non_empty():
    with pytest.raises(ValidationError):
        SessionPlan.model_validate(a_session().model_dump() | {"purpose": ""})


def test_week_indices_must_be_globally_increasing():
    plan = minimal_plan()
    dumped = plan.model_dump()
    # Duplicate the single week so indices are [1, 1] — not strictly increasing.
    dumped["mesocycles"][0]["weeks"].append(dumped["mesocycles"][0]["weeks"][0])
    with pytest.raises(ValidationError, match="increasing"):
        ProgramPlan.model_validate(dumped)


def test_empty_mesocycles_is_rejected():
    with pytest.raises(ValidationError):
        minimal_plan(mesocycles=[])


def test_schema_version_is_pinned_to_one():
    assert minimal_plan().schema_version == 1
    with pytest.raises(ValidationError):
        ProgramPlan.model_validate(minimal_plan().model_dump() | {"schema_version": 2})
