"""Deterministic simulation harness for the end-to-end evaluation (Phase 8).

Drives the REAL engine + store against synthetic athletes: build a calendar and
profile, plan the season, author a structured program, simulate weeks of session
and readiness logs with controlled perturbations, then run the check-in math.

Determinism is the whole point (no LLM, green in CI on every run):
- every date is explicit (passed as `today=` into the store/season/diligence
  functions), anchored on ORIGIN below;
- any "athlete noise" comes from a SEEDED `random.Random(seed)` instance, never
  the global `random` module and never wall-clock time.

Only the athlete BEHAVIOUR is synthetic (which sessions get done, readiness
values, injected perturbations); the planning/monitoring/response code under test
is the production engine + store.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Literal

from performance_agent.engine.load import session_rpe_load
from performance_agent.memory.schemas import (
    BlockPriority,
    ExerciseBlock,
    ExercisePerformed,
    Fallbacks,
    Mesocycle,
    MesocyclePhase,
    ProgramPlan,
    Quality,
    ReadinessEntry,
    SessionEntry,
    SessionPlan,
    SetPerformed,
    TestMilestone,
    WeekPlan,
)

SessionSource = Literal["programmed", "external"]

# A Monday, so weekday offsets map cleanly onto SessionPlan.weekday (0 = Mon).
ORIGIN = date(2026, 1, 5)


def rng(seed: int) -> random.Random:
    """A seeded RNG so synthetic noise is identical on every run."""
    return random.Random(seed)


def jitter(generator: random.Random, base: float, pct: float) -> float:
    """base scaled by a seeded +/- pct fraction (pct=0.05 -> +/-5%)."""
    return base * (1.0 + generator.uniform(-pct, pct))


def at(day_offset: int, hour: int = 18) -> datetime:
    """A naive local timestamp `day_offset` days after ORIGIN, at `hour`."""
    return datetime.combine(ORIGIN + timedelta(days=day_offset), datetime.min.time()) + timedelta(
        hours=hour
    )


def week_day_offset(week_index: int, weekday: int) -> int:
    """Day offset from ORIGIN for a 1-based week and a 0=Mon weekday."""
    return (week_index - 1) * 7 + weekday


def a_fallbacks() -> Fallbacks:
    """A valid non-empty Fallbacks block (self-serve contingencies)."""
    return Fallbacks(
        low_readiness="drop the top block, hold RPE 7",
        short_on_time="primary block only",
        missing_equipment="swap to a bodyweight or single-implement variant",
    )


def run_block(minutes: float, rpe: float) -> ExerciseBlock:
    """An endurance block prescribed by duration + RPE (one intensity channel)."""
    return ExerciseBlock(
        exercise="Run",
        priority="primary",
        warmup="none",
        sets=1,
        duration_min=minutes,
        rpe=rpe,
        progression_rule="hold the prescribed effort",
    )


def lift_block(
    exercise: str, load_kg: float, *, priority: BlockPriority = "primary"
) -> ExerciseBlock:
    """A strength block prescribed by load (the key lift the profile tracks)."""
    return ExerciseBlock(
        exercise=exercise,
        priority=priority,
        sets=4,
        reps="5",
        load_kg=load_kg,
        rest_s=180,
        progression_rule="double_progression(5-5, +2.5kg)",
    )


def run_session(
    session_id: str, weekday: int, quality: Quality, minutes: int, rpe: float
) -> SessionPlan:
    """A single-block endurance session (easy / tempo / long / brick)."""
    return SessionPlan(
        id=session_id,
        weekday=weekday,
        qualities=[quality],
        patterns=["run"],
        est_minutes=minutes,
        purpose=f"{quality} aerobic work",
        blocks=[run_block(minutes, rpe)],
        fallbacks=a_fallbacks(),
    )


def strength_session(  # noqa: PLR0913 -- fixture builder, all keyword-only past 2
    session_id: str,
    weekday: int,
    *,
    patterns: list[str],
    load_kg: float,
    minutes: int = 60,
    quality: Quality = "strength_heavy",
) -> SessionPlan:
    """A strength session with a tracked primary lift plus one accessory."""
    return SessionPlan(
        id=session_id,
        weekday=weekday,
        qualities=[quality],
        patterns=patterns,
        est_minutes=minutes,
        purpose="develop the primary strength pattern",
        blocks=[
            lift_block("Back Squat", load_kg),
            ExerciseBlock(
                exercise="Chin-up",
                priority="secondary",
                sets=3,
                reps="6-10",
                rir=2.0,
                rest_s=120,
                progression_rule="double_progression(6-10, +bodyweight)",
            ),
        ],
        fallbacks=a_fallbacks(),
    )


def program_from_weeks(  # noqa: PLR0913 -- fixture builder, all keyword-only past 2
    goal_id: str,
    weeks: list[list[SessionPlan]],
    *,
    phase: MesocyclePhase = "accumulation",
    season_ref: str | None = None,
    test_milestone_week: int | None = None,
    volume_factor: float = 1.0,
    intensity_factor: float = 0.9,
) -> ProgramPlan:
    """Assemble a single-mesocycle ProgramPlan from a per-week list of sessions.

    week_index is global 1-based; the caller supplies already-sequenced weeks.
    The store stamps version/created_on/reason on save, so those are placeholders.
    """
    week_plans = [
        WeekPlan(
            week_index=index + 1,
            volume_factor=volume_factor,
            intensity_factor=intensity_factor,
            sessions=sessions,
        )
        for index, sessions in enumerate(weeks)
    ]
    milestones = []
    if test_milestone_week is not None:
        milestones = [
            TestMilestone(
                week_index=test_milestone_week, protocol="amrap_rir1", targets=["Back Squat"]
            )
        ]
    return ProgramPlan(
        version=1,
        goal_id=goal_id,
        created_on=ORIGIN,
        season_ref=season_ref,
        test_milestones=milestones,
        mesocycles=[Mesocycle(index=1, phase=phase, weeks=week_plans)],
    )


def logged_session(  # noqa: PLR0913 -- fixture builder, all keyword-only past 1
    day_offset: int,
    *,
    rpe: int,
    duration_min: int,
    source: SessionSource = "programmed",
    session_plan_id: str | None = None,
    kind: str | None = None,
    exercises: list[ExercisePerformed] | None = None,
) -> SessionEntry:
    """A completed SessionEntry at a fixed day offset (sRPE = rpe x duration)."""
    return SessionEntry(
        performed_at=at(day_offset),
        kind=kind,
        rpe=rpe,
        duration_min=duration_min,
        source=source,
        session_plan_id=session_plan_id,
        exercises=exercises or [],
    )


def squat_log(day_offset: int, load_kg: float, session_plan_id: str) -> SessionEntry:
    """A logged strength session whose top set drives the e1RM timeline."""
    return SessionEntry(
        performed_at=at(day_offset),
        kind="strength_heavy",
        rpe=8,
        duration_min=60,
        session_plan_id=session_plan_id,
        exercises=[
            ExercisePerformed(name="Back Squat", sets=[SetPerformed(reps=5, load_kg=load_kg)])
        ],
    )


def readiness_log(  # noqa: PLR0913 -- fixture builder, all keyword-only past 1
    day_offset: int, *, sleep: int, fatigue: int, soreness: int, stress: int, hour: int = 7
) -> ReadinessEntry:
    """A pre-session wellness read (Hooper items, 1 = best .. 7 = worst)."""
    return ReadinessEntry(
        at=at(day_offset, hour=hour),
        sleep=sleep,
        fatigue=fatigue,
        soreness=soreness,
        stress=stress,
    )


def session_load(entry: SessionEntry) -> float:
    """Foster sRPE load for a logged entry (0 when RPE/duration missing)."""
    if entry.rpe is None or entry.duration_min is None:
        return 0.0
    return session_rpe_load(entry.rpe, entry.duration_min)


def daily_loads(entries: list[SessionEntry], num_days: int) -> list[float]:
    """Bucket logged sRPE load into a per-day array of length num_days from ORIGIN."""
    loads = [0.0] * num_days
    for entry in entries:
        index = (entry.performed_at.date() - ORIGIN).days
        if 0 <= index < num_days:
            loads[index] += session_load(entry)
    return loads


def external_share(entries: list[SessionEntry]) -> float:
    """Fraction of total weekly sRPE load coming from source='external'."""
    total = sum(session_load(e) for e in entries)
    if total == 0:
        return 0.0
    external = sum(session_load(e) for e in entries if e.source == "external")
    return external / total
