"""Deterministic renderer: golden file plus structural properties."""

from datetime import date
from pathlib import Path

from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Mesocycle,
    ProgramPlan,
    SessionPlan,
    TestMilestone,
    WeekPlan,
)
from performance_agent.programs.render import render_program

GOLDEN = Path(__file__).parent / "golden_program.md"


def _fallbacks() -> Fallbacks:
    return Fallbacks(
        low_readiness="top set at RPE 7, skip block C",
        short_on_time="A + B1 only",
        missing_equipment="goblet squat 3x10 @ RIR 2",
    )


def _golden_plan() -> ProgramPlan:
    """A plan exercising every render branch (intensity modes, flags, warmups)."""
    heavy = SessionPlan(
        id="w01-s1-lower-heavy",
        weekday=0,
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
                cite="resistance-training-volume-hypertrophy-meta-2017",
            ),
            ExerciseBlock(
                exercise="Front Squat",
                priority="primary",
                warmup="auto",
                sets=3,
                reps="3",
                pct_1rm=0.8,
                rest_s=180,
                progression_rule="add load when all sets hit top reps",
            ),
            ExerciseBlock(
                exercise="Romanian Deadlift",
                priority="secondary",
                sets=3,
                reps="8-12",
                rir=2.0,
                rest_s=120,
                progression_rule="double_progression(8-12, +5kg)",
                notes="brace hard",
            ),
        ],
        fallbacks=_fallbacks(),
    )
    easy = SessionPlan(
        id="w02-s1-run-easy",
        weekday=None,
        qualities=["endurance_easy", "recovery"],
        est_minutes=40,
        purpose="Aerobic base",
        blocks=[
            ExerciseBlock(
                exercise="Easy run",
                priority="primary",
                sets=1,
                distance_m=8000.0,
                pace_s_per_km=330.0,
                progression_rule="hold pace, add 1 km/week",
            ),
            ExerciseBlock(
                exercise="Mobility flow",
                priority="optional",
                sets=1,
                duration_min=10.0,
                progression_rule="none",
            ),
        ],
        fallbacks=_fallbacks(),
    )
    return ProgramPlan(
        version=1,
        goal_id="squat-160",
        created_on=date(2026, 7, 12),
        checkin_cadence_days=7,
        season_ref="two races 16 weeks apart",
        test_milestones=[
            TestMilestone(week_index=4, protocol="amrap_rir1", targets=["squat", "bench"]),
        ],
        mesocycles=[
            Mesocycle(
                index=1,
                phase="accumulation",
                weeks=[
                    WeekPlan(
                        week_index=1,
                        volume_factor=1.0,
                        intensity_factor=0.9,
                        weekly_set_targets={"quads": 12, "hamstrings": 8},
                        notes="ramp in gently",
                        sessions=[heavy],
                    ),
                    WeekPlan(
                        week_index=2,
                        is_deload=True,
                        volume_factor=0.6,
                        intensity_factor=0.85,
                        sessions=[easy],
                    ),
                ],
            ),
        ],
    )


def test_render_matches_golden():
    rendered = render_program(_golden_plan())
    assert rendered == GOLDEN.read_text(encoding="utf-8")


def test_every_exercise_appears_in_the_markdown():
    plan = _golden_plan()
    rendered = render_program(plan)
    for meso in plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                for block in session.blocks:
                    assert block.exercise in rendered


def test_render_is_deterministic():
    plan = _golden_plan()
    assert render_program(plan) == render_program(plan)


def test_light_load_gets_no_warmup_ramp():
    session = SessionPlan(
        id="s1",
        weekday=0,
        qualities=["strength_heavy"],
        est_minutes=30,
        purpose="light technique",
        blocks=[
            ExerciseBlock(
                exercise="Empty bar squat",
                priority="primary",
                sets=2,
                reps="5",
                load_kg=20.0,
                progression_rule="technique only",
            )
        ],
        fallbacks=_fallbacks(),
    )
    plan = ProgramPlan(
        version=1,
        goal_id="squat-160",
        created_on=date(2026, 7, 12),
        mesocycles=[
            Mesocycle(
                index=1,
                phase="general_prep",
                weeks=[
                    WeekPlan(
                        week_index=1,
                        volume_factor=1.0,
                        intensity_factor=1.0,
                        sessions=[session],
                    )
                ],
            )
        ],
    )
    # 40% of 20 kg = 8 kg < the 20 kg floor, so every ramp step is dropped.
    assert "Warm-up (auto)" not in render_program(plan)


def test_pct_based_primary_gets_generic_warmup_note():
    plan = _golden_plan()
    rendered = render_program(plan)
    # Front Squat is pct_1rm-based (no absolute load) → generic labeled ramp.
    assert "progressively heavier ramp sets" in rendered
