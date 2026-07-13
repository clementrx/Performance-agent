"""Exercise ontology at the athlete layer: packaged seed + athlete additions.

The seed library ships read-only in the package; the athlete may add exercises to
exercises/library.yaml, which takes precedence over a seed entry with the same id.
list_exercises filters the merged set; propose_exercise validates a submission and
persists it with `judgment` provenance. Pure data plumbing — no engine math here
(the selection scoring lands in Phase 3).
"""

from importlib import resources
from pathlib import Path
from typing import TypedDict

import yaml

from performance_agent.engine.exercise_selection import (
    Candidate,
    QualityTarget,
    ScoredExercise,
    score_exercises,
    stimulus_similarity,
)
from performance_agent.engine.specificity import check_specificity_mix
from performance_agent.engine.substitutions import Substitute
from performance_agent.memory import store
from performance_agent.memory.schemas import ExerciseDefinition, Provenance

_SEED_PACKAGE = "performance_agent.exercises"


def load_seed_exercises() -> dict[str, ExerciseDefinition]:
    """Load the packaged seed exercises keyed by id (validates every entry)."""
    data = resources.files(_SEED_PACKAGE) / "data" / "seed_exercises.yaml"
    raw = yaml.safe_load(data.read_text(encoding="utf-8")) or []
    exercises: dict[str, ExerciseDefinition] = {}
    for item in raw:
        definition = ExerciseDefinition.model_validate(item)
        if definition.id in exercises:
            msg = f"duplicate exercise id in seed library: {definition.id}"
            raise ValueError(msg)
        exercises[definition.id] = definition
    return exercises


def merged_exercises(base_dir: Path) -> dict[str, ExerciseDefinition]:
    """Seed exercises overlaid with the athlete's additions (athlete id wins)."""
    merged = dict(load_seed_exercises())
    for definition in store.read_exercise_library(base_dir).exercises:
        merged[definition.id] = definition
    return merged


class ExerciseView(TypedDict):
    """One exercise's attributes for the LLM to choose from."""

    id: str
    name: str
    patterns: list[str]
    force_vector: str
    contraction_regime: str
    chain: str
    equipment: list[str]
    specificity_level: str
    qualities_trained: dict[str, float]
    contraindications: list[str]
    unilateral: bool
    skill_complexity: int
    provenance_kind: str


def _to_view(definition: ExerciseDefinition) -> ExerciseView:
    return ExerciseView(
        id=definition.id,
        name=definition.name,
        patterns=list(definition.patterns),
        force_vector=definition.force_vector,
        contraction_regime=definition.contraction_regime,
        chain=definition.chain,
        equipment=list(definition.equipment),
        specificity_level=definition.specificity_level,
        qualities_trained={str(k): v for k, v in definition.qualities_trained.items()},
        contraindications=list(definition.contraindications),
        unilateral=definition.unilateral,
        skill_complexity=definition.skill_complexity,
        provenance_kind=definition.provenance.kind,
    )


def _matches(
    definition: ExerciseDefinition,
    *,
    pattern: str | None,
    quality: str | None,
    equipment: frozenset[str] | None,
    specificity: str | None,
) -> bool:
    if pattern is not None and pattern not in definition.patterns:
        return False
    if quality is not None and quality not in definition.qualities_trained:
        return False
    if specificity is not None and definition.specificity_level != specificity:
        return False
    # Equipment is a hard gate: every token the exercise needs must be available.
    # An exercise that needs nothing (empty list) always passes.
    return not (equipment is not None and not set(definition.equipment) <= equipment)


def list_exercises(
    base_dir: Path,
    pattern: str | None = None,
    quality: str | None = None,
    equipment: list[str] | None = None,
    specificity: str | None = None,
) -> list[ExerciseView]:
    """Filter the merged exercise set by pattern, quality, available equipment, specificity.

    equipment is the athlete's AVAILABLE tokens; an exercise qualifies only when
    all the equipment it needs is available (an exercise needing nothing always
    qualifies). Returns views sorted by id; deterministic.
    """
    available = frozenset(equipment) if equipment is not None else None
    matches = [
        _to_view(definition)
        for definition in merged_exercises(base_dir).values()
        if _matches(
            definition,
            pattern=pattern,
            quality=quality,
            equipment=available,
            specificity=specificity,
        )
    ]
    return sorted(matches, key=lambda view: view["id"])


def propose_exercise(base_dir: Path, definition: ExerciseDefinition) -> ExerciseView:
    """Validate a submitted exercise and persist it to the athlete library.

    The provenance is forced to `judgment` (an athlete/coach-authored addition,
    not a corpus-cited standard). An id already in the athlete library is replaced
    (upsert); the schema and equipment vocabulary are enforced by validation.
    """
    stamped = definition.model_copy(update={"provenance": Provenance(kind="judgment")})
    library = store.read_exercise_library(base_dir)
    kept = [e for e in library.exercises if e.id != stamped.id]
    kept.append(stamped)
    store.write_exercise_library(base_dir, library.model_copy(update={"exercises": kept}))
    return _to_view(stamped)


def _to_candidate(definition: ExerciseDefinition) -> Candidate:
    return Candidate(
        exercise_id=definition.id,
        name=definition.name,
        patterns=tuple(definition.patterns),
        force_vector=definition.force_vector,
        contraction_regime=definition.contraction_regime,
        equipment=tuple(definition.equipment),
        specificity_level=definition.specificity_level,
        qualities_trained=tuple(definition.qualities_trained.items()),
        contraindications=tuple(definition.contraindications),
        skill_complexity=definition.skill_complexity,
    )


def _active_injury_regions(base_dir: Path) -> set[str]:
    return {
        injury.area for injury in store.read_profile(base_dir).injuries if injury.status == "active"
    }


class ScoredExerciseView(TypedDict):
    """One scored candidate with its attribute-by-attribute breakdown."""

    exercise_id: str
    name: str
    score: float
    quality_match: float
    specificity_fit: float
    equipment_ok: bool
    contraindicated: bool
    novelty: float
    excluded_reason: str | None


def _to_scored_view(scored: ScoredExercise) -> ScoredExerciseView:
    return ScoredExerciseView(
        exercise_id=scored.exercise_id,
        name=scored.name,
        score=scored.score,
        quality_match=scored.breakdown.quality_match,
        specificity_fit=scored.breakdown.specificity_fit,
        equipment_ok=scored.breakdown.equipment_ok,
        contraindicated=scored.breakdown.contraindicated,
        novelty=scored.breakdown.novelty,
        excluded_reason=scored.excluded_reason,
    )


def score_library_exercises(  # noqa: PLR0913 -- selection inputs, all optional-with-defaults
    base_dir: Path,
    quality_targets: dict[str, float],
    phase: str,
    pattern: str | None = None,
    available_equipment: list[str] | None = None,
    contraindicated_regions: list[str] | None = None,
    recent_exercise_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[ScoredExerciseView]:
    """Score merged-library exercises for quality targets in a phase (engine call).

    Candidates default to the whole merged library (filter with pattern). Available
    equipment and contraindicated regions default to the athlete's profile
    (equipment + active-injury areas). Returns the scored breakdown sorted by score,
    optionally truncated to top_k.
    """
    library = merged_exercises(base_dir)
    candidates = [
        _to_candidate(definition)
        for definition in library.values()
        if pattern is None or pattern in definition.patterns
    ]
    targets = [QualityTarget(quality=q, weight=w) for q, w in quality_targets.items()]
    if available_equipment is None:
        available_equipment = [*store.read_profile(base_dir).equipment, "bodyweight"]
    if contraindicated_regions is None:
        contraindicated_regions = sorted(_active_injury_regions(base_dir))
    recent = dict.fromkeys(recent_exercise_ids or [], 1)
    scored = score_exercises(
        candidates,
        targets,
        phase,
        available_equipment,
        contraindicated_regions,
        recent,
    )
    views = [_to_scored_view(item) for item in scored]
    return views[:top_k] if top_k is not None else views


def stimulus_substitutes(
    base_dir: Path, exercise: str, available_equipment: list[str]
) -> list[Substitute] | None:
    """Rank ontology substitutes by stimulus equivalence, or None if not in the ontology.

    Returns None when `exercise` matches no ontology entry (the caller falls back to
    the pattern+equipment table). Otherwise ranks same-pattern candidates by
    quality/force/regime similarity, filtered by available equipment and the
    athlete's active-injury contraindications, excluding the original.
    """
    library = merged_exercises(base_dir)
    target = exercise.strip().casefold()
    original = next(
        (d for d in library.values() if d.id == target or d.name.casefold() == target),
        None,
    )
    if original is None:
        return None
    available = {token.strip().casefold() for token in available_equipment} | {"bodyweight"}
    contraindicated = _active_injury_regions(base_dir)
    original_candidate = _to_candidate(original)
    original_patterns = set(original.patterns)
    ranked: list[tuple[float, ExerciseDefinition]] = []
    for definition in library.values():
        if definition.id == original.id:
            continue
        if not original_patterns & set(definition.patterns):
            continue
        if not {e.casefold() for e in definition.equipment} <= available:
            continue
        if any(region in contraindicated for region in definition.contraindications):
            continue
        similarity = stimulus_similarity(original_candidate, _to_candidate(definition))
        ranked.append((similarity, definition))
    ranked.sort(key=lambda item: (-item[0], item[1].name))
    return [
        Substitute(
            name=definition.name,
            equipment=tuple(definition.equipment),
            source=f"stimulus equivalence ({similarity:.0%})",
        )
        for similarity, definition in ranked
    ]


class SpecificityWarningView(TypedDict):
    """One mesocycle flagged for a specificity mix out of its phase band."""

    mesocycle_index: int
    phase: str
    out_of_band: int
    total: int
    message: str


def check_program_specificity(base_dir: Path) -> list[SpecificityWarningView]:
    """Warn where a mesocycle's exercise specificity mix drifts out of its phase band.

    Resolves each block's exercise_id against the merged ontology; blocks without an
    exercise_id (unlinked) are skipped. Raises when no structured program exists.
    """
    program = store.read_program(base_dir)
    if program is None or program.plan is None:
        msg = "no structured program to check; save a ProgramPlan first"
        raise ValueError(msg)
    library = merged_exercises(base_dir)
    warnings: list[SpecificityWarningView] = []
    for meso in program.plan.mesocycles:
        levels: list[str] = [
            str(library[block.exercise_id].specificity_level)
            for week in meso.weeks
            for session in week.sessions
            for block in session.blocks
            if block.exercise_id is not None and block.exercise_id in library
        ]
        warning = check_specificity_mix(meso.phase, levels)
        if warning is not None:
            warnings.append(
                SpecificityWarningView(
                    mesocycle_index=meso.index,
                    phase=warning.phase,
                    out_of_band=warning.out_of_band,
                    total=warning.total,
                    message=warning.message,
                )
            )
    return warnings
