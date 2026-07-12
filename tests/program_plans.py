"""Shared builders for structured ProgramPlan test fixtures.

Kept out of conftest so every layer (store, reports, server) can import the
same minimal-but-valid plan and vary just what it is testing.
"""

from datetime import date

from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Mesocycle,
    ProgramPlan,
    SessionPlan,
    TestMilestone,
    WeekPlan,
)

FIXTURE_TODAY = date(2026, 7, 12)


def a_fallbacks() -> Fallbacks:
    """A valid non-empty Fallbacks block."""
    return Fallbacks(
        low_readiness="top set at RPE 7, skip block C",
        short_on_time="A + B1 only",
        missing_equipment="goblet squat 3x10 @ RIR 2",
    )


def a_session(
    session_id: str = "w01-s1-lower-heavy",
    *,
    weekday: int | None = 0,
    note: str | None = None,
) -> SessionPlan:
    """A strength session with a primary auto-warmup block; note lands on it."""
    return SessionPlan(
        id=session_id,
        weekday=weekday,
        qualities=["strength_heavy"],
        patterns=["squat", "hinge"],
        est_minutes=75,
        purpose="Build the squat base",
        blocks=[
            ExerciseBlock(
                exercise="Back Squat",
                priority="primary",
                sets=4,
                reps="5",
                load_kg=120.0,
                rest_s=180,
                progression_rule="double_progression(5-5, +2.5kg)",
                notes=note,
            ),
            ExerciseBlock(
                exercise="Romanian Deadlift",
                priority="secondary",
                sets=3,
                reps="8-12",
                rir=2.0,
                rest_s=120,
                progression_rule="double_progression(8-12, +5kg)",
            ),
        ],
        fallbacks=a_fallbacks(),
    )


def minimal_plan(
    goal_id: str = "squat-160",
    *,
    note: str | None = None,
    **overrides: object,
) -> ProgramPlan:
    """A single-mesocycle, single-week, single-session valid plan.

    Pass note to embed arbitrary text in the first block (used by the report
    citation-gate tests). Any ProgramPlan field can be overridden by keyword.
    """
    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=0.9,
        weekly_set_targets={"quads": 12, "hamstrings": 8},
        sessions=[a_session(note=note)],
    )
    fields: dict[str, object] = {
        "version": 1,
        "goal_id": goal_id,
        "created_on": FIXTURE_TODAY,
        "season_ref": "two races 16 weeks apart",
        "test_milestones": [TestMilestone(week_index=4, protocol="amrap_rir1", targets=["squat"])],
        "mesocycles": [Mesocycle(index=1, phase="accumulation", weeks=[week])],
    }
    fields.update(overrides)
    return ProgramPlan.model_validate(fields)


def plan_dict(goal_id: str = "squat-160", *, note: str | None = None, **overrides: object) -> dict:
    """JSON-mode dump of minimal_plan for passing to the save_program MCP tool."""
    return minimal_plan(goal_id, note=note, **overrides).model_dump(mode="json")
