"""Athlete-layer autoregulation: SessionPlan round-trips, recovery template, escalation."""

from datetime import datetime

from performance_agent.memory.autoregulation import (
    adjust_session,
    compress_session,
    escalation_signals,
    substitute_exercise,
)
from performance_agent.memory.schemas import (
    AdjustmentInputs,
    ExerciseBlock,
    Fallbacks,
    Mesocycle,
    ProgramPlan,
    SessionAdjustmentEntry,
    SessionPlan,
    WeekPlan,
)
from performance_agent.memory.store import append_session_adjustment
from performance_agent.programs.render import render_program


def _session() -> SessionPlan:
    return SessionPlan(
        id="w01-s1-lower",
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
                rpe=8.0,
                rest_s=180,
                progression_rule="add 2.5kg when all reps hit",
            ),
            ExerciseBlock(
                exercise="Romanian Deadlift",
                priority="secondary",
                sets=4,
                reps="8-12",
                rir=2.0,
                rest_s=120,
                progression_rule="double_progression(8-12, +5kg)",
            ),
            ExerciseBlock(
                exercise="Hanging Leg Raise",
                priority="optional",
                sets=3,
                reps="12",
                rpe=7.0,
                rest_s=60,
                progression_rule="add reps",
            ),
        ],
        fallbacks=Fallbacks(
            low_readiness="top set at RPE 7, skip block C",
            short_on_time="A + B1 only",
            missing_equipment="goblet squat 3x10 @ RIR 2",
        ),
    )


def test_amber_returns_a_valid_reduced_session():
    result = adjust_session(_session(), "amber")
    assert result.kind == "reduced"
    exercises = [b.exercise for b in result.session.blocks]
    assert "Hanging Leg Raise" not in exercises  # optional dropped
    squat = result.session.blocks[0]
    assert squat.rpe == 7.0  # top set stepped down
    rdl = result.session.blocks[1]
    assert rdl.sets < 4  # secondary volume cut
    assert any("Back Squat" in line for line in result.deltas_summary)


def test_red_returns_recovery_with_no_strength_or_hiit():
    result = adjust_session(_session(), "red")
    assert result.kind == "recovery"
    assert result.session.qualities == ["recovery"]
    assert "strength_heavy" not in result.session.qualities
    assert "hiit" not in result.session.qualities
    assert len(result.session.blocks) == 1


def test_green_session_is_unchanged():
    original = _session()
    result = adjust_session(original, "green")
    assert result.kind == "unchanged"
    assert result.session == original


def test_compress_keeps_primary_and_updates_est_minutes():
    result = compress_session(_session(), 20)
    assert result.session.blocks[0].exercise == "Back Squat"
    assert result.session.est_minutes == result.estimated_minutes
    if result.cut:
        assert result.cut[0].priority in ("optional", "secondary")


def test_adjusted_session_renders_deterministically():
    result = adjust_session(_session(), "amber")
    plan = ProgramPlan.model_validate(
        {
            "version": 1,
            "goal_id": "squat-160",
            "created_on": "2026-07-12",
            "mesocycles": [
                Mesocycle(
                    index=1,
                    phase="accumulation",
                    weeks=[
                        WeekPlan(
                            week_index=1,
                            volume_factor=1.0,
                            intensity_factor=0.9,
                            sessions=[result.session],
                        )
                    ],
                )
            ],
        }
    )
    rendered = render_program(plan)
    assert "Back Squat [primary]: 4x5 @ RPE 7" in rendered
    assert "Hanging Leg Raise" not in rendered  # dropped optional stays out of the render
    assert render_program(plan) == rendered  # deterministic


def test_substitute_exercise_passthrough():
    alts = substitute_exercise("Back Squat", "squat", ["kettlebell"])
    names = [a.name for a in alts]
    assert "Goblet Squat" in names
    assert "Back Squat" not in names


def _adjustment(
    session_id: str, at: datetime, kind="readiness", band="amber"
) -> SessionAdjustmentEntry:
    return SessionAdjustmentEntry(
        at=at,
        session_plan_id=session_id,
        kind=kind,
        inputs=AdjustmentInputs(band=band),
        deltas_summary=["Back Squat: rpe 8->7"],
    )


def test_escalation_signals_fire_after_three_downgrades(tmp_path):
    now = datetime(2026, 7, 13, 18, 0)
    for day in (1, 6, 11):
        append_session_adjustment(
            tmp_path, _adjustment("w01-s1-lower", datetime(2026, 7, day, 18, 0))
        )
    signals = escalation_signals(tmp_path, now=now)
    assert signals.downgrades == 3
    assert signals.escalate


def test_escalation_quiet_when_spread_out(tmp_path):
    now = datetime(2026, 7, 13, 18, 0)
    append_session_adjustment(tmp_path, _adjustment("w01-s1-lower", datetime(2026, 7, 12, 18, 0)))
    signals = escalation_signals(tmp_path, now=now)
    assert not signals.escalate
