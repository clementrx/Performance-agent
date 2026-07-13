"""Deterministic exercise scoring and stimulus similarity (pure).

score_exercises ranks candidates for a set of quality targets in a mesocycle
phase, with an attribute-by-attribute breakdown: quality match x phase-appropriate
specificity x equipment feasibility (hard gate) x contraindication (hard exclusion)
x a novelty modifier that damps recently over-used exercises. stimulus_similarity
scores how interchangeable two exercises are (for substitution). Pydantic- and
datetime-free; tie-broken by name so the ranking is stable.
"""

import math
from dataclasses import dataclass

from performance_agent.engine._validation import validate_finite
from performance_agent.engine.specificity import specificity_fit

# A recently-used exercise is damped toward this floor, never fully excluded.
NOVELTY_FLOOR = 0.5
_NOVELTY_STEP = 0.15
# Stimulus similarity weights: quality-vector cosine dominates, with small bonuses
# for matching force vector and contraction regime (team-chosen priors).
_COSINE_WEIGHT = 0.7
_FORCE_WEIGHT = 0.15
_REGIME_WEIGHT = 0.15


@dataclass(frozen=True)
class Candidate:
    """Engine-local view of one exercise's scorable attributes."""

    exercise_id: str
    name: str
    patterns: tuple[str, ...]
    force_vector: str
    contraction_regime: str
    equipment: tuple[str, ...]
    specificity_level: str
    qualities_trained: tuple[tuple[str, float], ...]
    contraindications: tuple[str, ...]
    skill_complexity: int


@dataclass(frozen=True)
class QualityTarget:
    """One quality the selection is chasing, with its priority weight."""

    quality: str
    weight: float


@dataclass(frozen=True)
class ScoreBreakdown:
    """The attribute-by-attribute justification behind one score."""

    quality_match: float
    specificity_fit: float
    equipment_ok: bool
    contraindicated: bool
    novelty: float


@dataclass(frozen=True)
class ScoredExercise:
    """One candidate's final score, breakdown, and exclusion reason if any."""

    exercise_id: str
    name: str
    score: float
    breakdown: ScoreBreakdown
    excluded_reason: str | None


def _quality_match(candidate: Candidate, targets: list[QualityTarget]) -> float:
    trained = dict(candidate.qualities_trained)
    return sum(target.weight * trained.get(target.quality, 0.0) for target in targets)


def _novelty(exercise_id: str, recent_exposure: dict[str, int]) -> float:
    count = recent_exposure.get(exercise_id, 0)
    if count <= 0:
        return 1.0
    return max(NOVELTY_FLOOR, 1.0 - _NOVELTY_STEP * count)


def _score_one(  # noqa: PLR0913 -- one scoring axis per parameter, all required
    candidate: Candidate,
    targets: list[QualityTarget],
    phase: str,
    available: set[str],
    contraindicated: set[str],
    recent_exposure: dict[str, int],
) -> ScoredExercise:
    equipment_ok = set(candidate.equipment) <= available
    contraindicated_flag = any(region in contraindicated for region in candidate.contraindications)
    quality_match = _quality_match(candidate, targets)
    fit = specificity_fit(candidate.specificity_level, phase)
    novelty = _novelty(candidate.exercise_id, recent_exposure)
    breakdown = ScoreBreakdown(
        quality_match=quality_match,
        specificity_fit=fit,
        equipment_ok=equipment_ok,
        contraindicated=contraindicated_flag,
        novelty=novelty,
    )
    reason: str | None = None
    if not equipment_ok:
        reason = "equipment"
    elif contraindicated_flag:
        reason = "contraindicated"
    score = 0.0 if reason is not None else quality_match * fit * novelty
    return ScoredExercise(
        exercise_id=candidate.exercise_id,
        name=candidate.name,
        score=score,
        breakdown=breakdown,
        excluded_reason=reason,
    )


def score_exercises(  # noqa: PLR0913 -- selection contract (plan Phase 3): all six inputs required
    candidates: list[Candidate],
    quality_targets: list[QualityTarget],
    phase: str,
    available_equipment: list[str],
    contraindicated_regions: list[str],
    recent_exposure: dict[str, int] | None = None,
) -> list[ScoredExercise]:
    """Rank candidates for the quality targets in a phase, with a scored breakdown.

    Score = quality_match x specificity_fit x novelty, with equipment feasibility
    and contraindication as hard gates (a candidate failing either scores 0 and
    carries an excluded_reason). Sorted by score descending, tie-broken by name.
    recent_exposure maps exercise_id -> recent use count (damps novelty).
    Deterministic.
    """
    for target in quality_targets:
        validate_finite(f"weight[{target.quality}]", target.weight)
    available = set(available_equipment)
    contraindicated = set(contraindicated_regions)
    recent = recent_exposure or {}
    scored = [
        _score_one(candidate, quality_targets, phase, available, contraindicated, recent)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: (-item.score, item.name))
    return scored


def _vector_norm(values: tuple[tuple[str, float], ...]) -> float:
    return math.sqrt(sum(weight * weight for _, weight in values))


def stimulus_similarity(a: Candidate, b: Candidate) -> float:
    """Score how interchangeable two exercises are, in [0, 1].

    Cosine similarity of the qualities-trained vectors dominates, plus small
    bonuses for a matching force vector and contraction regime. 1.0 means an
    identical training stimulus profile; 0.0 means no shared qualities.
    """
    trained_a = dict(a.qualities_trained)
    trained_b = dict(b.qualities_trained)
    keys = set(trained_a) | set(trained_b)
    dot = sum(trained_a.get(k, 0.0) * trained_b.get(k, 0.0) for k in keys)
    norm_a = _vector_norm(a.qualities_trained)
    norm_b = _vector_norm(b.qualities_trained)
    cosine = dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    force_match = 1.0 if a.force_vector == b.force_vector else 0.0
    regime_match = 1.0 if a.contraction_regime == b.contraction_regime else 0.0
    return _COSINE_WEIGHT * cosine + _FORCE_WEIGHT * force_match + _REGIME_WEIGHT * regime_match
