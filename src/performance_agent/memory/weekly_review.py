"""Weekly loads review: match the logged week to the program, apply each rule.

Deterministic given `today`. Matching: sessions logged in the last `days_back`
days are matched to program sessions by session_plan_id when present, else by
exercise-name overlap; the program week with the most matched sessions is the
current week (tie -> highest week_index). Suggestions target each block's next
occurrence: same-load rules (double/linear/rir_target) progress the current
block; from_pct resolves the SAME exercise's planned pct in the following week
(fallback: the current block's pct). e1RM comes from the best logged set of
that exercise in the last 14 days (Epley), falling back to the profile's
lift_inventory. A successful run records its date so diligence can see it.
"""

from datetime import date
from pathlib import Path
from typing import TypedDict

import yaml

from performance_agent.engine.progression import (
    SetActual,
    next_load_double,
    next_load_from_pct,
    next_load_linear,
    next_load_rir,
)
from performance_agent.engine.strength import MAX_ESTIMATION_REPS, one_rm_epley
from performance_agent.memory import store
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    WeekPlan,
)
from performance_agent.programs.render import intensity_label, volume_label

LOADS_REVIEW_STATE_FILE = "loads-review.yaml"
_DEFAULT_WINDOW_DAYS = 7
_E1RM_WINDOW_DAYS = 14


class ActualSetView(TypedDict):
    """One logged set as facts."""

    reps: int
    load_kg: float
    rir: float | None


class BlockSuggestionView(TypedDict):
    """Next-week verdict for one block (facts; the LLM renders the sentence)."""

    session_id: str
    exercise: str
    rule_kind: str | None
    prescribed_volume: str
    prescribed_intensity: str
    actual_sets: list[ActualSetView]
    next_load_kg: float | None
    rationale_key: str
    flags: list[str]


class WeeklyLoadsView(TypedDict):
    """The whole review: matched week, one verdict per block, run-level flags."""

    week_matched: int | None
    blocks: list[BlockSuggestionView]
    flags: list[str]


def read_last_run(base_dir: Path) -> date | None:
    """Date of the last successful review, or None when never run."""
    path = base_dir / LOADS_REVIEW_STATE_FILE
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "last_run" not in raw:
        return None
    return date.fromisoformat(str(raw["last_run"]))


def _record_run(base_dir: Path, current: date) -> None:
    path = base_dir / LOADS_REVIEW_STATE_FILE
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump({"last_run": current.isoformat()}), encoding="utf-8")
    tmp.replace(path)


def _weeks_in_order(plan: ProgramPlan) -> list[WeekPlan]:
    return [week for meso in plan.mesocycles for week in meso.weeks]


def _window_sessions(base_dir: Path, current: date, days_back: int) -> list[SessionEntry]:
    return [
        entry
        for entry in store.read_sessions(base_dir)
        if entry.source == "programmed"
        and 0 <= (current - entry.performed_at.date()).days < days_back
    ]


def _logged_names(entries: list[SessionEntry]) -> set[str]:
    return {ex.name.casefold() for entry in entries for ex in entry.exercises}


def _match_week(weeks: list[WeekPlan], logged: list[SessionEntry]) -> WeekPlan | None:
    plan_ids = {entry.session_plan_id for entry in logged if entry.session_plan_id}
    names = _logged_names(logged)

    def score(week: WeekPlan) -> int:
        if plan_ids:
            return sum(1 for session in week.sessions if session.id in plan_ids)
        return sum(
            1
            for session in week.sessions
            for block in session.blocks
            if block.exercise.casefold() in names
        )

    best = max(weeks, key=lambda week: (score(week), week.week_index), default=None)
    if best is None or score(best) == 0:
        return None
    return best


def _sets_for_block(block: ExerciseBlock, logged: list[SessionEntry]) -> list[SetActual]:
    wanted = block.exercise.casefold()
    return [
        SetActual(reps=s.reps, load_kg=s.load_kg, rir=s.rir)
        for entry in logged
        for ex in entry.exercises
        if ex.name.casefold() == wanted
        for s in ex.sets
    ]


def _e1rm_for(base_dir: Path, exercise: str, current: date) -> float | None:
    wanted = exercise.casefold()
    estimates = [
        one_rm_epley(s.load_kg, s.reps)
        for entry in store.read_sessions(base_dir)
        if 0 <= (current - entry.performed_at.date()).days < _E1RM_WINDOW_DAYS
        for ex in entry.exercises
        if ex.name.casefold() == wanted
        for s in ex.sets
        if s.load_kg > 0 and 1 <= s.reps <= MAX_ESTIMATION_REPS
    ]
    if estimates:
        return max(estimates)
    profile = store.read_profile(base_dir)
    for record in profile.lift_inventory:
        if record.lift.casefold() == wanted:
            return record.one_rm_kg
    return None


def _next_pct_for(block: ExerciseBlock, next_week: WeekPlan | None) -> float | None:
    if next_week is not None:
        for session in next_week.sessions:
            for candidate in session.blocks:
                if (
                    candidate.exercise.casefold() == block.exercise.casefold()
                    and candidate.pct_1rm is not None
                ):
                    return candidate.pct_1rm
    return block.pct_1rm


def _suggest_block(  # noqa: PLR0913 -- the six inputs are the review's full context, all distinct
    base_dir: Path,
    session: SessionPlan,
    block: ExerciseBlock,
    logged: list[SessionEntry],
    next_week: WeekPlan | None,
    current: date,
) -> BlockSuggestionView:
    view = BlockSuggestionView(
        session_id=session.id,
        exercise=block.exercise,
        rule_kind=block.progression.kind if block.progression else None,
        prescribed_volume=volume_label(block),
        prescribed_intensity=intensity_label(block),
        actual_sets=[],
        next_load_kg=None,
        rationale_key="no_rule",
        flags=[],
    )
    sets = _sets_for_block(block, logged)
    view["actual_sets"] = [ActualSetView(reps=s.reps, load_kg=s.load_kg, rir=s.rir) for s in sets]
    rule = block.progression
    if rule is None:
        return view
    if rule.kind == "none":
        view["rationale_key"] = "per_plan"
        return view
    if rule.kind == "from_pct":
        pct = _next_pct_for(block, next_week)
        if pct is None:
            view["rationale_key"] = "per_plan"
            view["flags"] = ["no_pct_prescribed"]
            return view
        result = next_load_from_pct(
            pct, _e1rm_for(base_dir, block.exercise, current), rule.rounding_kg
        )
    elif rule.kind == "double":
        result = next_load_double(rule, block.load_kg or 0.0, sets)
    elif rule.kind == "linear_load":
        reps = block.reps or ""
        if not reps.isdigit():
            view["rationale_key"] = "hold"
            view["flags"] = ["ambiguous_reps"]
            return view
        result = next_load_linear(rule, block.load_kg or 0.0, int(reps), sets)
    else:  # rir_target
        result = next_load_rir(rule, block.load_kg or 0.0, sets)
    view["next_load_kg"] = result.next_load_kg
    view["rationale_key"] = result.action
    view["flags"] = list(result.flags)
    return view


def suggest_next_week_loads(
    base_dir: Path, today: date | None = None, days_back: int = _DEFAULT_WINDOW_DAYS
) -> WeeklyLoadsView:
    """Compute every block's next-week load from the logged week (see module doc)."""
    if days_back < 1:
        msg = f"days_back must be >= 1, got {days_back!r}"
        raise ValueError(msg)
    current = today or date.today()
    program = store.read_program(base_dir)
    if program is None:
        msg = "no program has been saved yet; save a program before a loads review"
        raise ValueError(msg)
    if program.plan is None:
        msg = "the active program is legacy prose-only; a structured plan is required"
        raise ValueError(msg)
    weeks = _weeks_in_order(program.plan)
    logged = _window_sessions(base_dir, current, days_back)
    week = _match_week(weeks, logged)
    if week is None:
        return WeeklyLoadsView(week_matched=None, blocks=[], flags=["no_matched_week"])
    position = weeks.index(week)
    next_week = weeks[position + 1] if position + 1 < len(weeks) else None
    flags = [] if next_week is not None else ["last_week"]
    blocks = [
        _suggest_block(base_dir, session, block, logged, next_week, current)
        for session in week.sessions
        for block in session.blocks
    ]
    _record_run(base_dir, current)
    return WeeklyLoadsView(week_matched=week.week_index, blocks=blocks, flags=flags)
