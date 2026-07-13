"""Tests for the exercise ontology: seed loading, filters, athlete merge, propose."""

import pytest
from pydantic import ValidationError

from performance_agent.memory.exercise_library import (
    list_exercises,
    load_seed_exercises,
    merged_exercises,
    propose_exercise,
)
from performance_agent.memory.schemas import ExerciseDefinition, Provenance

_MIN_SEED_EXERCISES = 120


def _definition(**overrides) -> ExerciseDefinition:
    base = {
        "id": "custom-drill",
        "name": "Custom Drill",
        "patterns": ["jump"],
        "force_vector": "axial",
        "contraction_regime": "plyometric",
        "chain": "closed",
        "equipment": [],
        "specificity_level": "special",
        "qualities_trained": {"reactive_strength": 0.8},
        "skill_complexity": 2,
        "provenance": {"kind": "prior"},
    }
    base.update(overrides)
    return ExerciseDefinition.model_validate(base)


def test_seed_loads_and_validates_entirely():
    seed = load_seed_exercises()
    assert len(seed) >= _MIN_SEED_EXERCISES
    for definition in seed.values():
        assert definition.qualities_trained
        assert all(0.0 <= w <= 1.0 for w in definition.qualities_trained.values())


def test_filter_by_pattern(tmp_path):
    results = list_exercises(tmp_path, pattern="squat")
    assert results
    assert all("squat" in r["patterns"] for r in results)


def test_filter_by_quality_and_equipment_bodyweight(tmp_path):
    # Acceptance: reactive_strength + bodyweight -> plyometric entries from the seed.
    results = list_exercises(tmp_path, quality="reactive_strength", equipment=["bodyweight"])
    assert results
    ids = {r["id"] for r in results}
    assert "pogo-hops" in ids  # a bodyweight plyometric
    for r in results:
        assert "reactive_strength" in r["qualities_trained"]
        assert r["equipment"] == []  # nothing needed -> available under bodyweight-only


def test_equipment_is_a_hard_gate(tmp_path):
    # A barbell exercise must not appear for a bodyweight-only athlete.
    results = list_exercises(tmp_path, pattern="squat", equipment=["bodyweight"])
    assert all("barbell" not in r["equipment"] for r in results)


def test_filter_by_specificity(tmp_path):
    results = list_exercises(tmp_path, specificity="competition")
    assert results
    assert all(r["specificity_level"] == "competition" for r in results)


def test_propose_persists_with_judgment_provenance(tmp_path):
    view = propose_exercise(tmp_path, _definition())
    assert view["provenance_kind"] == "judgment"
    assert view["id"] == "custom-drill"
    # It now appears in the merged library.
    assert "custom-drill" in merged_exercises(tmp_path)


def test_propose_forces_judgment_even_if_cited(tmp_path):
    view = propose_exercise(
        tmp_path, _definition(provenance=Provenance(kind="cited", cite_ids=["x"]))
    )
    assert view["provenance_kind"] == "judgment"


def test_athlete_library_overrides_seed_id(tmp_path):
    override = _definition(id="back-squat", name="My Back Squat", patterns=["squat"])
    propose_exercise(tmp_path, override)
    merged = merged_exercises(tmp_path)
    assert merged["back-squat"].name == "My Back Squat"


def test_unknown_equipment_rejected():
    with pytest.raises(ValidationError, match="unknown equipment"):
        _definition(equipment=["jetpack"])


def test_quality_weight_out_of_range_rejected():
    with pytest.raises(ValidationError, match="within 0-1"):
        _definition(qualities_trained={"reactive_strength": 1.5})
