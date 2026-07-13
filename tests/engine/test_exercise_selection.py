"""Tests for the exercise-selection scoring and stimulus similarity."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.exercise_selection import (
    Candidate,
    QualityTarget,
    score_exercises,
    stimulus_similarity,
)


def _candidate(  # noqa: PLR0913 -- test builder with keyword-only attribute overrides
    exercise_id,
    quals,
    *,
    equipment=(),
    contra=(),
    force="axial",
    regime="concentric_dominant",
    specificity="special",
):
    return Candidate(
        exercise_id=exercise_id,
        name=exercise_id,
        patterns=("squat",),
        force_vector=force,
        contraction_regime=regime,
        equipment=tuple(equipment),
        specificity_level=specificity,
        qualities_trained=tuple(quals.items()),
        contraindications=tuple(contra),
        skill_complexity=2,
    )


def test_higher_quality_match_ranks_first():
    strong = _candidate("strong", {"max_strength": 0.9})
    weak = _candidate("weak", {"max_strength": 0.2})
    targets = [QualityTarget("max_strength", 1.0)]
    ranked = score_exercises([weak, strong], targets, "specific_prep", [], [])
    assert ranked[0].exercise_id == "strong"


def test_equipment_is_a_hard_gate():
    barbell = _candidate("barbell-lift", {"max_strength": 0.9}, equipment=("barbell",))
    ranked = score_exercises(
        [barbell], [QualityTarget("max_strength", 1.0)], "specific_prep", [], []
    )
    assert ranked[0].score == 0.0
    assert ranked[0].excluded_reason == "equipment"


def test_equipment_available_scores():
    barbell = _candidate("barbell-lift", {"max_strength": 0.9}, equipment=("barbell",))
    ranked = score_exercises(
        [barbell], [QualityTarget("max_strength", 1.0)], "specific_prep", ["barbell"], []
    )
    assert ranked[0].score > 0.0
    assert ranked[0].excluded_reason is None


def test_contraindication_is_hard_exclusion():
    risky = _candidate("risky", {"max_strength": 0.9}, contra=("knee",))
    ranked = score_exercises(
        [risky], [QualityTarget("max_strength", 1.0)], "specific_prep", [], ["knee"]
    )
    assert ranked[0].score == 0.0
    assert ranked[0].excluded_reason == "contraindicated"


def test_novelty_damps_recently_used():
    fresh = _candidate("fresh", {"max_strength": 0.8})
    stale = _candidate("stale", {"max_strength": 0.8})
    targets = [QualityTarget("max_strength", 1.0)]
    ranked = score_exercises([fresh, stale], targets, "specific_prep", [], [], {"stale": 3})
    assert ranked[0].exercise_id == "fresh"
    assert ranked[0].score > ranked[1].score


def test_ties_broken_by_name():
    a = _candidate("a-lift", {"max_strength": 0.5})
    b = _candidate("b-lift", {"max_strength": 0.5})
    ranked = score_exercises([b, a], [QualityTarget("max_strength", 1.0)], "specific_prep", [], [])
    assert [r.exercise_id for r in ranked] == ["a-lift", "b-lift"]


def test_stimulus_similarity_identical_is_high():
    a = _candidate("a", {"max_strength": 0.9, "hypertrophy": 0.5})
    b = _candidate("b", {"max_strength": 0.9, "hypertrophy": 0.5})
    assert stimulus_similarity(a, b) == pytest.approx(1.0)


def test_stimulus_similarity_disjoint_is_low():
    a = _candidate("a", {"max_strength": 0.9}, force="axial", regime="concentric_dominant")
    b = _candidate("b", {"aerobic_capacity": 0.9}, force="horizontal", regime="plyometric")
    assert stimulus_similarity(a, b) == pytest.approx(0.0)


@given(
    base=st.floats(min_value=0.1, max_value=1.0),
    contra_region=st.sampled_from(["knee", "shoulder", "hamstring"]),
)
def test_adding_a_contraindication_never_raises_score(base, contra_region):
    candidate = _candidate("c", {"max_strength": base}, contra=(contra_region,))
    targets = [QualityTarget("max_strength", 1.0)]
    without = score_exercises([candidate], targets, "specific_prep", [], [])[0].score
    with_contra = score_exercises([candidate], targets, "specific_prep", [], [contra_region])[
        0
    ].score
    assert with_contra <= without


@given(exposure=st.integers(min_value=0, max_value=20))
def test_novelty_monotone_non_increasing_in_exposure(exposure):
    candidate = _candidate("c", {"max_strength": 0.8})
    targets = [QualityTarget("max_strength", 1.0)]
    zero = score_exercises([candidate], targets, "specific_prep", [], [], {"c": 0})[0].score
    used = score_exercises([candidate], targets, "specific_prep", [], [], {"c": exposure})[0].score
    assert used <= zero + 1e-9
