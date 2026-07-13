"""Athlete-layer tests: exercise scoring, stimulus substitution, program specificity."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.autoregulation import substitute_exercise
from performance_agent.memory.exercise_library import (
    check_program_specificity,
    merged_exercises,
    score_library_exercises,
    stimulus_substitutes,
)
from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Injury,
    Mesocycle,
    MesocyclePhase,
    Profile,
    ProgramPlan,
    SessionPlan,
    WeekPlan,
)


def test_score_uses_profile_equipment_and_injuries(tmp_path):
    store.write_profile(
        tmp_path,
        Profile(
            equipment=["barbell", "rack"], injuries=[Injury(area="knee", noted_on=date(2026, 7, 1))]
        ),
    )
    scored = score_library_exercises(
        tmp_path, {"max_strength": 1.0}, "specific_prep", pattern="squat"
    )
    by_id = {s["exercise_id"]: s for s in scored}
    # Back Squat (barbell+rack, contraindicated by knee) is excluded by the injury.
    assert by_id["back-squat"]["excluded_reason"] == "contraindicated"
    # Safety-bar squat (barbell+rack, no knee contraindication) is scorable.
    assert by_id["safety-bar-squat"]["excluded_reason"] is None


def test_score_respects_explicit_equipment_override(tmp_path):
    scored = score_library_exercises(
        tmp_path,
        {"max_strength": 1.0},
        "specific_prep",
        pattern="squat",
        available_equipment=["bodyweight"],
    )
    for entry in scored:
        if "barbell" in entry["exercise_id"] or entry["exercise_id"] == "back-squat":
            assert entry["excluded_reason"] == "equipment"


def test_score_top_k(tmp_path):
    scored = score_library_exercises(
        tmp_path, {"reactive_strength": 1.0}, "realization", pattern="jump", top_k=3
    )
    assert len(scored) == 3


def test_stimulus_substitutes_none_for_unknown(tmp_path):
    assert stimulus_substitutes(tmp_path, "Totally Made Up Lift", ["barbell"]) is None


def test_stimulus_substitutes_rank_known(tmp_path):
    subs = stimulus_substitutes(tmp_path, "back-squat", ["barbell", "rack"])
    assert subs is not None
    names = [s.name for s in subs]
    assert "Front Squat" in names
    assert all(s.source.startswith("stimulus equivalence") for s in subs)


def test_substitute_excludes_contraindicated(tmp_path):
    store.write_profile(
        tmp_path, Profile(injuries=[Injury(area="knee", noted_on=date(2026, 7, 1))])
    )
    subs = substitute_exercise(
        tmp_path, "Back Squat", "squat", ["barbell", "rack", "box", "machine"]
    )
    # Every returned option must not carry a knee contraindication.
    library = {d.name: d for d in merged_exercises(tmp_path).values()}
    for sub in subs:
        assert "knee" not in library[sub.name].contraindications


def _fallbacks() -> Fallbacks:
    return Fallbacks(low_readiness="ease off", short_on_time="core only", missing_equipment="swap")


def _program_with_blocks(phase: MesocyclePhase, exercise_ids: list[str]) -> ProgramPlan:
    blocks = [
        ExerciseBlock(
            exercise=eid,
            exercise_id=eid,
            priority="primary",
            sets=3,
            reps="5",
            rest_s=120,
            progression_rule="double progression",
        )
        for eid in exercise_ids
    ]
    session = SessionPlan(
        id="w01-s1",
        weekday=0,
        qualities=["power"],
        est_minutes=60,
        purpose="test",
        blocks=blocks,
        fallbacks=_fallbacks(),
    )
    return ProgramPlan(
        version=1,
        goal_id="goal-x",
        created_on=date(2026, 7, 12),
        mesocycles=[
            Mesocycle(
                index=1,
                phase=phase,
                weeks=[
                    WeekPlan(
                        week_index=1, volume_factor=1.0, intensity_factor=1.0, sessions=[session]
                    )
                ],
            )
        ],
    )


def test_program_specificity_flags_out_of_band(tmp_path):
    # general_prep should be general-leaning; competition-level lifts are out of band.
    plan = _program_with_blocks(
        "general_prep", ["clean-and-jerk", "acceleration-sprint", "flying-sprint"]
    )
    store.save_program(tmp_path, plan)
    warnings = check_program_specificity(tmp_path)
    assert warnings
    assert warnings[0]["phase"] == "general_prep"
    assert warnings[0]["out_of_band"] >= 2


def test_program_specificity_ok_in_band(tmp_path):
    plan = _program_with_blocks("general_prep", ["back-squat", "bodyweight-squat", "goblet-squat"])
    store.save_program(tmp_path, plan)
    assert check_program_specificity(tmp_path) == []


def test_program_specificity_requires_program(tmp_path):
    with pytest.raises(ValueError, match="no structured program"):
        check_program_specificity(tmp_path)
