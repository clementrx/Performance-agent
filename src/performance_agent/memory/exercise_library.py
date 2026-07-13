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
