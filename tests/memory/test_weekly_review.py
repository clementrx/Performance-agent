"""Weekly loads review: week matching, rule dispatch, state file."""

from datetime import date, datetime
from typing import Any

import pytest

from performance_agent.memory import store, weekly_review
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ExercisePerformed,
    Fallbacks,
    Mesocycle,
    Profile,
    ProgramPlan,
    ProgressionRule,
    SessionEntry,
    SessionPlan,
    SetPerformed,
    WeekPlan,
)

TODAY = date(2026, 7, 17)
FALLBACKS = Fallbacks(
    low_readiness="halve", short_on_time="cut accessories", missing_equipment="dumbbells"
)


def _block(exercise="Bench press", **overrides):
    fields: dict[str, Any] = {
        "exercise": exercise,
        "priority": "primary",
        "sets": 3,
        "reps": "8-12",
        "load_kg": 80.0,
        "rest_s": 120,
        "progression_rule": "Double progression 8-12, +2.5 kg at the top.",
        "progression": ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    }
    fields.update(overrides)
    return ExerciseBlock(**fields)


def _week(index, blocks):
    return WeekPlan(
        week_index=index,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id=f"w{index}-a",
                weekday=0,
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper strength",
                blocks=blocks,
                fallbacks=FALLBACKS,
            )
        ],
    )


def _save_program(base, weeks):
    plan = ProgramPlan(
        version=1,
        goal_id="bench-goal",
        created_on=TODAY,
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=weeks)],
    )
    store.save_program(base, plan, today=TODAY)


def _log(  # noqa: PLR0913 -- test helper mirroring the full SessionEntry shape
    base, day, session_plan_id, exercise="Bench press", reps=(12, 12, 12), load=80.0, rir=None
):
    entry = SessionEntry(
        performed_at=datetime(day.year, day.month, day.day, 18, 0),
        session_plan_id=session_plan_id,
        exercises=[
            ExercisePerformed(
                name=exercise,
                sets=[SetPerformed(reps=r, load_kg=load, rir=rir) for r in reps],
            )
        ],
    )
    store.append_session(base, entry)


def test_no_program_raises(tmp_path):
    with pytest.raises(ValueError, match="no program"):
        weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)


def test_double_progression_increment_end_to_end(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert view["week_matched"] == 1
    [block] = view["blocks"]
    assert block["exercise"] == "Bench press"
    assert block["next_load_kg"] == 82.5
    assert block["rationale_key"] == "increment"


def test_unmatched_block_is_flagged_not_guessed(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(
        tmp_path,
        [_week(1, [_block(), _block(exercise="Squat")]), _week(2, [_block()])],
    )
    _log(tmp_path, date(2026, 7, 13), "w1-a")  # only bench logged
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    squat = next(b for b in view["blocks"] if b["exercise"] == "Squat")
    assert squat["next_load_kg"] is None
    assert "no_logged_sets" in squat["flags"]


def test_block_without_structured_rule_flags_no_rule(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block(progression=None)]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    [block] = view["blocks"]
    assert block["rationale_key"] == "no_rule"
    assert block["next_load_kg"] is None


def test_from_pct_uses_next_week_pct_and_logged_e1rm(tmp_path):
    store.write_profile(tmp_path, Profile())
    week1 = _week(
        1,
        [_block(load_kg=None, pct_1rm=0.8, progression=ProgressionRule(kind="from_pct"))],
    )
    week2 = _week(
        2,
        [_block(load_kg=None, pct_1rm=0.85, progression=ProgressionRule(kind="from_pct"))],
    )
    _save_program(tmp_path, [week1, week2])
    # best set 100x5 -> Epley e1RM 116.7 -> 0.85 * 116.7 = 99.2 -> rounds to 100
    _log(tmp_path, date(2026, 7, 13), "w1-a", reps=(5, 5), load=100.0)
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    [block] = view["blocks"]
    assert block["next_load_kg"] == 100.0
    assert block["rationale_key"] == "per_plan"


def test_state_file_records_the_run(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    assert weekly_review.read_last_run(tmp_path) is None
    weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert weekly_review.read_last_run(tmp_path) == TODAY


def test_no_matching_week_returns_empty_with_flag(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert view["week_matched"] is None
    assert view["blocks"] == []
    assert "no_matched_week" in view["flags"]
