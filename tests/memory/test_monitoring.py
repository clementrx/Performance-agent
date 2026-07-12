"""Session plausibility glue: history + profile -> engine data-quality flags."""

from datetime import date, datetime

from performance_agent.memory.monitoring import session_plausibility_flags
from performance_agent.memory.schemas import (
    ExercisePerformed,
    LiftRecord,
    Profile,
    SessionEntry,
    SetPerformed,
)


def _squat_session(at, load, reps=3, kind=None):
    return SessionEntry(
        performed_at=at,
        kind=kind,
        exercises=[
            ExercisePerformed(name="back squat", sets=[SetPerformed(reps=reps, load_kg=load)])
        ],
    )


def test_clean_session_produces_no_flags():
    history = [_squat_session(datetime(2026, 7, 1, 18, 0), 100)]
    entry = _squat_session(datetime(2026, 7, 8, 18, 0), 102)
    assert session_plausibility_flags(entry, history, Profile()) == []


def test_e1rm_jump_is_flagged_against_history():
    history = [_squat_session(datetime(2026, 7, 1, 18, 0), 100)]
    entry = _squat_session(datetime(2026, 7, 8, 18, 0), 150)
    flags = session_plausibility_flags(entry, history, Profile())
    assert [f["code"] for f in flags] == ["e1rm_jump"]
    assert "back squat" in flags[0]["message"]


def test_load_over_known_1rm_is_flagged_outside_test():
    profile = Profile(
        lift_inventory=[LiftRecord(lift="back squat", one_rm_kg=150, recorded_on=date(2026, 6, 1))]
    )
    entry = _squat_session(datetime(2026, 7, 8, 18, 0), 200, reps=1)
    flags = session_plausibility_flags(entry, [], profile)
    assert any(f["code"] == "load_over_1rm" for f in flags)


def test_load_over_1rm_not_flagged_in_a_test_session():
    profile = Profile(
        lift_inventory=[LiftRecord(lift="back squat", one_rm_kg=150, recorded_on=date(2026, 6, 1))]
    )
    entry = _squat_session(datetime(2026, 7, 8, 18, 0), 200, reps=1, kind="1rm test")
    flags = session_plausibility_flags(entry, [], profile)
    assert all(f["code"] != "load_over_1rm" for f in flags)


def test_duration_outlier_is_flagged():
    history = [
        SessionEntry(performed_at=datetime(2026, 7, d, 18, 0), duration_min=60) for d in range(1, 6)
    ]
    entry = SessionEntry(performed_at=datetime(2026, 7, 8, 18, 0), duration_min=300)
    flags = session_plausibility_flags(entry, history, Profile())
    assert any(f["code"] == "duration_outlier" for f in flags)


def test_lift_name_matching_is_case_insensitive():
    history = [_squat_session(datetime(2026, 7, 1, 18, 0), 100)]
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 8, 18, 0),
        exercises=[ExercisePerformed(name="Back Squat", sets=[SetPerformed(reps=3, load_kg=150)])],
    )
    flags = session_plausibility_flags(entry, history, Profile())
    assert [f["code"] for f in flags] == ["e1rm_jump"]


def test_no_history_means_no_e1rm_flag():
    entry = _squat_session(datetime(2026, 7, 8, 18, 0), 300)
    assert session_plausibility_flags(entry, [], Profile()) == []
