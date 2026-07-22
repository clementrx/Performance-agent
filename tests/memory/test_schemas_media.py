"""media_id on ExerciseBlock: agent-chosen dataset media binding."""

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import ExerciseBlock


def block_fields(**overrides):
    fields = {
        "exercise": "Sentadilla trasera",
        "priority": "primary",
        "sets": 4,
        "reps": "5",
        "load_kg": 60.0,
        "progression_rule": "double_progression(4-6, +2.5kg)",
    }
    fields.update(overrides)
    return fields


def test_media_id_defaults_to_none():
    block = ExerciseBlock.model_validate(block_fields())
    assert block.media_id is None


def test_media_id_accepts_dataset_shaped_id():
    block = ExerciseBlock.model_validate(block_fields(media_id="0043"))
    assert block.media_id == "0043"


@pytest.mark.parametrize("bad", ["", "x" * 17])
def test_media_id_rejects_empty_and_overlong(bad):
    with pytest.raises(ValidationError):
        ExerciseBlock.model_validate(block_fields(media_id=bad))
