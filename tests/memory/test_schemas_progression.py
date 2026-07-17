"""ProgressionRule: per-kind parameter validation and block attachment."""

from datetime import date

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Guidance,
    Mesocycle,
    ProgramPlan,
    ProgressionRule,
    SessionPlan,
    WeekPlan,
)


def test_double_requires_range_and_increment():
    rule = ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5)
    assert rule.rounding_kg == 2.5
    with pytest.raises(ValidationError, match="rep_min"):
        ProgressionRule(kind="double", rep_max=12, increment_kg=2.5)
    with pytest.raises(ValidationError, match="rep_min"):
        ProgressionRule(kind="double", rep_min=12, rep_max=8, increment_kg=2.5)


def test_linear_requires_increment():
    ProgressionRule(kind="linear_load", increment_kg=2.5)
    with pytest.raises(ValidationError, match="increment_kg"):
        ProgressionRule(kind="linear_load")


def test_rir_target_requires_target():
    rule = ProgressionRule(kind="rir_target", target_rir=2)
    assert rule.adjust_pct_per_rir == 0.03
    with pytest.raises(ValidationError, match="target_rir"):
        ProgressionRule(kind="rir_target")


def test_from_pct_and_none_take_no_required_params():
    ProgressionRule(kind="from_pct")
    ProgressionRule(kind="none")


def test_block_accepts_structured_progression_and_stays_optional():
    block = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=4,
        reps="8-12",
        load_kg=80,
        progression_rule="Double progression 8-12, +2.5 kg at the top.",
        progression=ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    )
    assert block.progression is not None
    legacy = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=4,
        reps="8-12",
        load_kg=80,
        progression_rule="text only",
    )
    assert legacy.progression is None


def test_program_plan_carries_optional_guidance():
    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id="a",
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper",
                blocks=[
                    ExerciseBlock(
                        exercise="Bench press",
                        priority="primary",
                        sets=3,
                        reps="8",
                        load_kg=80,
                        progression_rule="hold",
                    )
                ],
                fallbacks=Fallbacks(
                    low_readiness="halve", short_on_time="cut", missing_equipment="dumbbells"
                ),
            )
        ],
    )
    plan = ProgramPlan(
        version=1,
        goal_id="g",
        created_on=date(2026, 7, 17),
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=[week])],
        advice=[Guidance(text="Creatine 5 g/day.", cite="creatine-2017")],
        rationale=[Guidance(text="12-16 hard sets per muscle per week.")],
    )
    assert plan.advice[0].cite == "creatine-2017"
    assert plan.rationale[0].cite is None
    bare = plan.model_copy(update={"advice": [], "rationale": []})
    assert bare.advice == []
