"""MCP wrappers for the weekly follow-up."""

from datetime import date, datetime, timedelta

import pytest

from performance_agent.memory import store
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
from performance_agent.server import followup_tools


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    store.write_profile(tmp_path, Profile())
    return tmp_path


def _seed_program_and_log(base):
    block = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=3,
        reps="8-12",
        load_kg=80.0,
        progression_rule="Double progression 8-12, +2.5 kg at the top.",
        progression=ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    )
    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id="w1-a",
                weekday=0,
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper",
                blocks=[block],
                fallbacks=Fallbacks(
                    low_readiness="halve", short_on_time="cut", missing_equipment="dumbbells"
                ),
            )
        ],
    )
    plan = ProgramPlan(
        version=1,
        goal_id="bench-goal",
        created_on=date(2026, 7, 13),
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=[week])],
    )
    store.save_program(base, plan, today=date(2026, 7, 13))
    # The MCP wrapper reads the real clock: the logged session must stay inside
    # its rolling days_back window, so it is seeded relative to now, not fixed.
    performed = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0) - timedelta(
        days=1
    )
    store.append_session(
        base,
        SessionEntry(
            performed_at=performed,
            session_plan_id="w1-a",
            exercises=[
                ExercisePerformed(
                    name="Bench press",
                    sets=[SetPerformed(reps=12, load_kg=80.0) for _ in range(3)],
                )
            ],
        ),
    )


def test_suggest_returns_block_verdicts(athlete_dir):
    _seed_program_and_log(athlete_dir)
    view = followup_tools.suggest_next_week_loads()
    assert view["week_matched"] == 1
    assert view["blocks"][0]["next_load_kg"] == 82.5


@pytest.mark.usefixtures("athlete_dir")
def test_suggest_rejects_bad_window():
    with pytest.raises(ValueError, match="days_back"):
        followup_tools.suggest_next_week_loads(days_back=0)


@pytest.mark.usefixtures("athlete_dir")
def test_save_watch_report_versions():
    result = followup_tools.save_watch_report("All on track.", "bench-goal")
    assert result["version"] == 1
