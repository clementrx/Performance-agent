"""MCP tools for the exercise ontology (list & propose structured exercises).

The engine owns the attributes; the LLM filters the merged seed+athlete library
and, when a needed exercise is missing, submits a fully attributed definition that
the engine validates (schema + equipment vocabulary) and persists with `judgment`
provenance. Selection scoring lands in Phase 3; here the LLM just browses.
"""

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import exercise_library
from performance_agent.memory.exercise_library import ExerciseView
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import (
    ExerciseDefinition,
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


def register(mcp: FastMCP) -> None:
    """Register every exercise-ontology tool on the server."""
    for tool in (list_exercises, propose_exercise):
        mcp.tool()(tool)
