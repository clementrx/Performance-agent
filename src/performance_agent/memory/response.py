"""Response profiling at the athlete layer: read logs, extract numbers, call engine.

The engine (engine/response.py) is datetime-free and pydantic-free; this module
reads the athlete's ProgramPlan, sessions.jsonl, readiness.jsonl and
session_adjustments.jsonl, converts dates into day/week indices, marks
implausible entries for exclusion, calls the pure engine, and assembles a
ResponseProfile. It NEVER fabricates a rate: when the engine returns None the
profile carries None and a caveat, never a guessed number.
"""

from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean
from typing import get_args

from performance_agent.engine import (
    AdherenceByQuality,
    ProgressionRate,
    SessionSets,
    VolumeTolerance,
    adherence_stats,
    build_response_profile,
    compare_prescribed_actual,
    e1rm_timeline,
    flag_implausible_session,
    progression_rate,
    volume_tolerance,
)
from performance_agent.engine.response import (
    ComplianceReport,
    LoggedSession,
    PlannedSession,
)
from performance_agent.engine.strength import MAX_ESTIMATION_REPS, one_rm_epley
from performance_agent.memory import banister as banister_layer
from performance_agent.memory import store
from performance_agent.memory.schemas import (
    AdherenceQuality,
    Goal,
    LiftRate,
    MeasuredRate,
    ProgramPlan,
    Quality,
    ReadinessEntry,
    ResponseProfile,
    SessionEntry,
    VolumeToleranceFlag,
)

_DAYS_PER_WEEK = 7
_QUALITIES: frozenset[str] = frozenset(get_args(Quality))


def _normalize(name: str) -> str:
    return name.strip().casefold()


def _best_e1rm_and_sets(
    entry: SessionEntry, lift: str
) -> tuple[float, tuple[tuple[float, int], ...]]:
    """Best Epley e1RM and the (load, reps) pairs for one lift in a session."""
    target = _normalize(lift)
    pairs: list[tuple[float, int]] = []
    for exercise in entry.exercises:
        if _normalize(exercise.name) != target:
            continue
        for performed in exercise.sets:
            if performed.load_kg > 0 and 1 <= performed.reps <= MAX_ESTIMATION_REPS:
                pairs.append((performed.load_kg, performed.reps))
    best = max((one_rm_epley(load, reps) for load, reps in pairs), default=0.0)
    return best, tuple(pairs)


def _lift_names(sessions: list[SessionEntry]) -> list[str]:
    """Distinct lift names (original casing of first sighting) that have scored sets."""
    seen: dict[str, str] = {}
    for entry in sessions:
        for exercise in entry.exercises:
            key = _normalize(exercise.name)
            if key and key not in seen and any(s.load_kg > 0 for s in exercise.sets):
                seen[key] = exercise.name
    return list(seen.values())


def _lift_sessions(sessions: list[SessionEntry], lift: str, origin: date) -> list[SessionSets]:
    """Build engine SessionSets for one lift, excluding implausible e1RM jumps."""
    ordered = sorted(sessions, key=lambda e: e.performed_at)
    running_best = 0.0
    out: list[SessionSets] = []
    for entry in ordered:
        best, pairs = _best_e1rm_and_sets(entry, lift)
        if not pairs:
            continue
        excluded = any(
            flag.code == "e1rm_jump"
            for flag in flag_implausible_session(
                session_e1rm_kg=best, recent_best_e1rm_kg=running_best or None
            )
        )
        if not excluded:
            running_best = max(running_best, best)
        day_index = (entry.performed_at.date() - origin).days
        out.append(SessionSets(day_index=day_index, sets=pairs, excluded=excluded))
    return out


def _lift_rate(sessions: list[SessionEntry], lift: str, origin: date) -> ProgressionRate | None:
    return progression_rate(e1rm_timeline(_lift_sessions(sessions, lift, origin)))


def build_lift_rates(sessions: list[SessionEntry], origin: date) -> dict[str, ProgressionRate]:
    """Measured weekly progression rate per lift with enough data (None ones dropped)."""
    rates: dict[str, ProgressionRate] = {}
    for lift in _lift_names(sessions):
        rate = _lift_rate(sessions, lift, origin)
        if rate is not None:
            rates[lift] = rate
    return rates


def _session_quality(qualities: list[Quality]) -> str:
    return qualities[0] if qualities else "recovery"


def _planned_sessions(plan: ProgramPlan) -> list[PlannedSession]:
    planned: list[PlannedSession] = []
    for meso in plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                planned.append(
                    PlannedSession(
                        session_id=session.id,
                        week_index=week.week_index,
                        weekday=session.weekday,
                        quality=_session_quality(session.qualities),
                        prescribed_sets=sum(block.sets for block in session.blocks),
                    )
                )
    return planned


def _logged_quality(entry: SessionEntry) -> str | None:
    if entry.kind is not None and _normalize(entry.kind) in _QUALITIES:
        return _normalize(entry.kind)
    return None


def _week_index_of(entry: SessionEntry, origin: date) -> int:
    return (entry.performed_at.date() - origin).days // _DAYS_PER_WEEK + 1


def _logged_sessions(sessions: list[SessionEntry], origin: date) -> list[LoggedSession]:
    logged: list[LoggedSession] = []
    for entry in sessions:
        logged.append(
            LoggedSession(
                session_plan_id=entry.session_plan_id,
                week_index=_week_index_of(entry, origin),
                weekday=entry.performed_at.weekday(),
                quality=_logged_quality(entry),
                performed_sets=sum(len(ex.sets) for ex in entry.exercises),
            )
        )
    return logged


def compare_plan_to_log(
    plan: ProgramPlan, sessions: list[SessionEntry], origin: date
) -> ComplianceReport:
    """Match logged sessions to the plan (engine), keyed on program week origin."""
    return compare_prescribed_actual(_planned_sessions(plan), _logged_sessions(sessions, origin))


def _weekly_fatigue(readiness: list[ReadinessEntry], origin: date) -> dict[int, float]:
    """Mean Hooper fatigue (1 best..7 worst) per program week."""
    by_week: dict[int, list[int]] = {}
    for entry in readiness:
        week = (entry.at.date() - origin).days // _DAYS_PER_WEEK + 1
        by_week.setdefault(week, []).append(entry.fatigue)
    return {week: mean(values) for week, values in by_week.items()}


def _volume_tolerance(
    report: ComplianceReport, readiness: list[ReadinessEntry], origin: date
) -> VolumeTolerance | None:
    fatigue_by_week = _weekly_fatigue(readiness, origin)
    performed_by_week = {wv.week_index: wv.performed_sets for wv in report.weekly_volume}
    weeks = sorted(set(fatigue_by_week) & set(performed_by_week))
    if not weeks:
        return None
    hard_sets = [float(performed_by_week[w]) for w in weeks]
    fatigue = [fatigue_by_week[w] for w in weeks]
    return volume_tolerance(hard_sets, fatigue)


def _goal_lift(goal: Goal | None, rates: dict[str, ProgressionRate]) -> str | None:
    """Pick the lift whose rate best represents the goal (named match, else most data)."""
    if not rates:
        return None
    if goal is not None:
        haystack = _normalize(f"{goal.statement} {goal.metric or ''}")
        for lift in rates:
            if _normalize(lift) in haystack:
                return lift
    return max(rates, key=lambda lift: rates[lift].n)


def _adjustment_patterns(base_dir: Path) -> list[str]:
    counts = Counter(entry.kind for entry in store.read_session_adjustments(base_dir))
    return [f"{count} {kind} adjustment(s) logged" for kind, count in sorted(counts.items())]


def _to_lift_rate(lift: str, rate: ProgressionRate) -> LiftRate:
    return LiftRate(
        lift=lift,
        pct_per_week=rate.pct_per_week,
        r2=rate.r2,
        n=rate.n,
        window_weeks=rate.span_weeks,
    )


def _to_adherence(stat: AdherenceByQuality) -> AdherenceQuality:
    return AdherenceQuality(
        quality=stat.quality,
        done=stat.done,
        partial=stat.partial,
        modified=stat.modified,
        missed=stat.missed,
        adherence_pct=stat.adherence_pct,
    )


def compute_response_profile(
    base_dir: Path,
    goal_id: str | None = None,
    today: date | None = None,
    banister_kpi_id: str | None = None,
) -> ResponseProfile:
    """Distil the athlete's logged response into a ResponseProfile (unsaved).

    Reads the active program (its created_on anchors program-week alignment),
    the session/readiness/adjustment logs, and the goal, then computes per-lift
    rates, the goal's measured rate, a volume/fatigue association, adherence by
    quality and adjustment patterns. Returns a ResponseProfile with None (and a
    caveat) wherever the data is too thin — never a fabricated number. Raises
    when no structured program exists (the alignment anchor is missing). When
    banister_kpi_id is given, also fits the Banister model against that KPI and
    attaches it (usable=False when the history does not qualify).
    """
    as_of = today or date.today()
    program = store.read_program(base_dir)
    if program is None or program.plan is None:
        msg = "no structured program to align against; save a ProgramPlan first"
        raise ValueError(msg)
    plan = program.plan
    origin = date.fromisoformat(program.created_on)
    sessions = store.read_sessions(base_dir)
    readiness = store.read_readiness(base_dir)
    resolved_goal_id = goal_id or plan.goal_id
    goal = next((g for g in store.read_goals(base_dir) if g.id == resolved_goal_id), None)

    rates = build_lift_rates(sessions, origin)
    goal_lift = _goal_lift(goal, rates)
    goal_rate = rates.get(goal_lift) if goal_lift is not None else None
    report = compare_plan_to_log(plan, sessions, origin)
    tolerance = _volume_tolerance(report, readiness, origin)
    adherence = adherence_stats(report)

    data = build_response_profile(rates, goal_rate, tolerance, adherence)
    measured = (
        MeasuredRate(
            value=goal_rate.pct_per_week,
            n=goal_rate.n,
            window_weeks=goal_rate.span_weeks,
            r2=goal_rate.r2,
        )
        if goal_rate is not None
        else None
    )
    tolerance_flags = (
        [
            VolumeToleranceFlag(
                direction=tolerance.direction,
                correlation=tolerance.correlation,
                n_weeks=tolerance.n_weeks,
            )
        ]
        if tolerance is not None
        else []
    )
    banister = (
        banister_layer.fit_kpi_banister(base_dir, banister_kpi_id)
        if banister_kpi_id is not None
        else None
    )
    return ResponseProfile(
        as_of=as_of,
        goal_id=resolved_goal_id,
        per_lift_rates=[_to_lift_rate(lift, rate) for lift, rate in sorted(rates.items())],
        per_goal_measured_rate=measured,
        volume_tolerance_flags=tolerance_flags,
        adherence_by_quality=[_to_adherence(s) for s in data.adherence_by_quality],
        adjustment_patterns=_adjustment_patterns(base_dir),
        banister=banister,
        caveats=data.caveats,
    )


def tolerance_adjustment_from_profile(profile: ResponseProfile | None) -> str:
    """Map a profile's volume-tolerance flag to a weekly_set_targets adjustment.

    higher_volume_higher_fatigue -> reduce; higher_volume_lower_fatigue -> extend;
    otherwise (no profile, no flag, or no clear direction) -> default.
    """
    if profile is None:
        return "default"
    for flag in profile.volume_tolerance_flags:
        if flag.direction == "higher_volume_higher_fatigue":
            return "reduce"
        if flag.direction == "higher_volume_lower_fatigue":
            return "extend"
    return "default"


__all__ = [
    "compare_plan_to_log",
    "compute_response_profile",
    "tolerance_adjustment_from_profile",
]
