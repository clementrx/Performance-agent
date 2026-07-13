"""MCP tools for the exercise ontology (list & propose structured exercises).

The engine owns the attributes; the LLM filters the merged seed+athlete library
and, when a needed exercise is missing, submits a fully attributed definition that
the engine validates (schema + equipment vocabulary) and persists with `judgment`
provenance. Selection scoring lands in Phase 3; here the LLM just browses.
"""

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import exercise_library
from performance_agent.memory.exercise_library import (
    ExerciseView,
    ScoredExerciseView,
    SpecificityWarningView,
)
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import (
    ExerciseDefinition,
    MesocyclePhase,
    MovementPattern,
    PerformanceQuality,
    SpecificityLevel,
)


def list_exercises(
    pattern: MovementPattern | None = None,
    quality: PerformanceQuality | None = None,
    equipment: list[str] | None = None,
    specificity: SpecificityLevel | None = None,
) -> list[ExerciseView]:
    """Browse the merged seed + athlete exercise library, filtered.

    pattern keeps exercises training that movement pattern; quality keeps those
    that train that body quality; specificity matches the general/special/
    specific/competition level. equipment is the athlete's AVAILABLE tokens — an
    exercise qualifies only when every token it needs is available (an exercise
    needing nothing always qualifies). Returns the full attribute set per exercise,
    sorted by id. The athlete's own additions take precedence over a seed with the
    same id.
    """
    return exercise_library.list_exercises(
        resolve_athlete_dir(),
        pattern=pattern,
        quality=quality,
        equipment=equipment,
        specificity=specificity,
    )


def propose_exercise(definition: ExerciseDefinition) -> ExerciseView:
    """Add a fully attributed exercise to the athlete library (provenance judgment).

    Submit an ExerciseDefinition: id (slug), name, patterns, force_vector,
    contraction_regime, chain (open/closed), equipment tokens (from the known
    vocabulary), specificity_level, qualities_trained (quality -> 0-1 weight),
    contraindications, unilateral, skill_complexity (1-3). The engine validates the
    schema and equipment vocabulary and persists it with `judgment` provenance; an
    id already in the athlete library is replaced.
    """
    return exercise_library.propose_exercise(resolve_athlete_dir(), definition)


def score_exercises(  # noqa: PLR0913 -- selection inputs, all optional-with-defaults
    quality_targets: dict[PerformanceQuality, float],
    phase: MesocyclePhase,
    pattern: MovementPattern | None = None,
    available_equipment: list[str] | None = None,
    contraindicated_regions: list[str] | None = None,
    recent_exercise_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[ScoredExerciseView]:
    """Rank exercises for quality targets in a mesocycle phase, with a scored breakdown.

    quality_targets maps each body quality to a priority weight (use the
    per-quality priorities from compute_performance_gaps). Score = quality_match x
    phase-appropriate specificity x novelty, with equipment feasibility and
    contraindication as HARD gates (a candidate failing either scores 0 with an
    excluded_reason). Candidates default to the whole library (filter with pattern);
    available_equipment and contraindicated_regions default to the athlete's profile
    (equipment + active injuries). Pick within the top_k with a stated reason; cite
    or label the choice. Sorted by score, tie-broken by name.
    """
    return exercise_library.score_library_exercises(
        resolve_athlete_dir(),
        {str(quality): weight for quality, weight in quality_targets.items()},
        phase,
        pattern=pattern,
        available_equipment=available_equipment,
        contraindicated_regions=contraindicated_regions,
        recent_exercise_ids=recent_exercise_ids,
        top_k=top_k,
    )


def check_program_specificity() -> list[SpecificityWarningView]:
    """Flag mesocycles whose exercise specificity mix drifts out of the phase band.

    Resolves each block's exercise_id against the ontology and checks the general->
    special->specific->competition mix per mesocycle against phase-appropriate bands
    (general prep is general-leaning, realization/taper specific-leaning). Blocks
    with no exercise_id are skipped — link them to the ontology to be checked.
    Returns one warning per drifting mesocycle (empty when all are in band). Errors
    if no structured program exists.
    """
    return exercise_library.check_program_specificity(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register every exercise-ontology tool on the server."""
    for tool in (list_exercises, propose_exercise, score_exercises, check_program_specificity):
        mcp.tool()(tool)
