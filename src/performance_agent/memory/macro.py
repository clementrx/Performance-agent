"""Multi-year planning at the athlete layer: build the macro plan, check residuals.

build_macro_plan derives the year typing and quality-emphasis budgets from the
PerformanceModel gap priorities and the calendar's major event. check_residuals
resolves a program's blocks to their ontology qualities and warns where a quality
would decay past its retention window without a refresh. The engine owns the math;
this module reads the athlete directory and assembles the schema objects.
"""

from pathlib import Path
from typing import TypedDict

from performance_agent.engine.macro import QualityPriorityInput, build_macro_years
from performance_agent.engine.residuals import QualityStimulus, check_residuals
from performance_agent.memory import exercise_library, performance_models, store
from performance_agent.memory.schemas import MacroPlan, MacroYear

_DAYS_PER_WEEK = 7


def _gap_priorities(base_dir: Path, level: str) -> list[QualityPriorityInput]:
    gaps = performance_models.compute_performance_gaps(base_dir, level)
    priorities: list[QualityPriorityInput] = []
    for entry in gaps["quality_priorities"]:
        # Measured priority when we have it; the model weight for unmeasured qualities.
        score = entry["priority_score"]
        priorities.append(
            QualityPriorityInput(
                quality=entry["quality"],
                priority=score if score is not None else entry["weight"],
            )
        )
    return priorities


def _major_event_id(base_dir: Path, major_event_id: str | None) -> str:
    if major_event_id is not None:
        return major_event_id
    competitions = [
        e
        for e in store.read_calendar(base_dir).events
        if e.kind == "competition" and e.priority == "A"
    ]
    if not competitions:
        msg = "no A-priority competition on the calendar; pass major_event_id explicitly"
        raise ValueError(msg)
    return max(competitions, key=lambda e: e.date).id


def build_macro_plan(
    base_dir: Path,
    horizon_years: int,
    major_event_id: str | None = None,
    level: str = "elite",
) -> MacroPlan:
    """Build a multi-year macro plan (unsaved) from gaps and the calendar's major event.

    Types each year backward from the major event and derives per-year quality
    emphases from the gap priorities (development years bias general capacities and
    weaknesses, the realization year biases specific qualities). Raises when no
    performance model exists (gaps need it) or no major event can be resolved.
    """
    major = _major_event_id(base_dir, major_event_id)
    priorities = _gap_priorities(base_dir, level)
    year_plans = build_macro_years(horizon_years, priorities)
    years = [
        MacroYear.model_validate(
            {
                "index": plan.index,
                "year_type": plan.year_type,
                "primary_event_id": major if plan.year_type == "realization" else None,
                "quality_emphases": dict(plan.quality_emphases),
            }
        )
        for plan in year_plans
    ]
    return MacroPlan(horizon_years=horizon_years, major_event_id=major, years=years)


class ResidualWarningView(TypedDict):
    """One quality that would decay past its residual before a refresh."""

    quality: str
    gap_days: int
    residual_days: int
    after_day: int
    message: str


def _program_stimuli(base_dir: Path) -> tuple[list[QualityStimulus], int]:
    program = store.read_program(base_dir)
    if program is None or program.plan is None:
        msg = "no structured program to check; save a ProgramPlan first"
        raise ValueError(msg)
    library = exercise_library.merged_exercises(base_dir)
    stimuli: list[QualityStimulus] = []
    last_day = 0
    for meso in program.plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                weekday = session.weekday if session.weekday is not None else 0
                day = (week.week_index - 1) * _DAYS_PER_WEEK + weekday
                last_day = max(last_day, day)
                qualities = {
                    quality
                    for block in session.blocks
                    if block.exercise_id is not None and block.exercise_id in library
                    for quality in library[block.exercise_id].qualities_trained
                }
                if qualities:
                    stimuli.append(
                        QualityStimulus(day_index=day, qualities=tuple(sorted(qualities)))
                    )
    return stimuli, last_day


def check_program_residuals(base_dir: Path) -> list[ResidualWarningView]:
    """Warn where a program's maintained qualities would decay past their residuals.

    Resolves each block's exercise_id to its ontology qualities, then checks the
    per-quality stimulus spacing against Issurin retention windows. Blocks without an
    exercise_id are skipped. Raises when no structured program exists.
    """
    stimuli, last_day = _program_stimuli(base_dir)
    warnings = check_residuals(stimuli, last_day)
    return [
        ResidualWarningView(
            quality=w.quality,
            gap_days=w.gap_days,
            residual_days=w.residual_days,
            after_day=w.after_day,
            message=w.message,
        )
        for w in warnings
    ]
