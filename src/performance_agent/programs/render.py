"""Deterministic ProgramPlan -> markdown renderer (the human view of a program).

The markdown is generated, never hand-written: save_program renders it from the
structured plan so the printed program and the source of truth can never drift.
Warm-up ramps for auto strength blocks are emitted here via the engine helper,
so a printed program carries the ramp-up sets a coach writes by hand.
"""

from performance_agent.engine import warmup_scheme
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ProgramPlan,
    SessionPlan,
    WeekPlan,
)

_METERS_PER_KM = 1000

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def num_label(value: float) -> str:
    """Format a number without trailing zeros (48.0 -> '48', 47.5 -> '47.5')."""
    return f"{value:g}"


def pace_label(seconds_per_km: float) -> str:
    """Format a running pace as m:ss/km."""
    minutes, secs = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{secs:02d}/km"


def volume_label(block: ExerciseBlock) -> str:
    """Format a block's volume prescription (sets x reps / minutes / distance)."""
    if block.reps is not None:
        return f"{block.sets}x{block.reps}"
    if block.duration_min is not None:
        return f"{block.sets}x{num_label(block.duration_min)} min"
    distance = block.distance_m or 0.0
    if distance >= _METERS_PER_KM:
        label = f"{num_label(distance / _METERS_PER_KM)} km"
    else:
        label = f"{num_label(distance)} m"
    return f"{block.sets}x{label}"


def intensity_label(block: ExerciseBlock) -> str:
    """Format a block's single-channel intensity prescription."""
    if block.load_kg is not None:
        return f"{num_label(block.load_kg)} kg"
    if block.pct_1rm is not None:
        return f"{block.pct_1rm * 100:.0f}% 1RM"
    if block.rir is not None:
        return f"RIR {num_label(block.rir)}"
    if block.rpe is not None:
        return f"RPE {num_label(block.rpe)}"
    if block.pace_s_per_km is not None:
        return pace_label(block.pace_s_per_km)
    return ""


def _block_line(block: ExerciseBlock) -> str:
    parts = [f"- {block.exercise} [{block.priority}]: {volume_label(block)}"]
    intensity = intensity_label(block)
    if intensity:
        parts.append(f" @ {intensity}")
    if block.rest_s is not None:
        parts.append(f" — rest {block.rest_s}s")
    parts.append(f". {block.progression_rule}")
    if block.cite:
        parts.append(f" [{block.cite}]")
    if block.notes:
        parts.append(f" — {block.notes}")
    return "".join(parts)


def _warmup_line(session: SessionPlan, block: ExerciseBlock) -> str | None:
    if "strength_heavy" not in session.qualities:
        return None
    if block.warmup != "auto" or block.priority != "primary":
        return None
    if block.load_kg is None:
        return (
            "  - Warm-up (auto): 2-3 progressively heavier ramp sets to the "
            "working weight (coaching judgment)"
        )
    ramp = warmup_scheme(block.load_kg)
    if not ramp:
        return None
    steps = ", ".join(
        f"{fraction * 100:.0f}% (~{num_label(block.load_kg * fraction)} kg) x{reps}"
        for fraction, reps in ramp
    )
    return f"  - Warm-up (auto): {steps}"


def _session_lines(session: SessionPlan) -> list[str]:
    day = _WEEKDAYS[session.weekday] if session.weekday is not None else "unscheduled"
    lines = [
        f"**{session.id}** — {day} · {session.est_minutes} min",
        f"Purpose: {session.purpose}",
    ]
    quality_line = f"Qualities: {', '.join(session.qualities)}"
    if session.patterns:
        quality_line += f"; patterns: {', '.join(session.patterns)}"
    lines.append(quality_line)
    for block in session.blocks:
        warmup = _warmup_line(session, block)
        if warmup is not None:
            lines.append(warmup)
        lines.append(_block_line(block))
    fallbacks = session.fallbacks
    lines.append(
        "Fallbacks — low readiness: "
        f"{fallbacks.low_readiness}; short on time: {fallbacks.short_on_time}; "
        f"missing equipment: {fallbacks.missing_equipment}"
    )
    return lines


def _week_lines(week: WeekPlan) -> list[str]:
    flags = [flag for flag, on in (("deload", week.is_deload), ("taper", week.is_taper)) if on]
    heading = f"### Week {week.week_index}"
    if flags:
        heading += f" ({', '.join(flags)})"
    lines = [
        heading,
        f"Volume x{num_label(week.volume_factor)}, intensity x{num_label(week.intensity_factor)}",
    ]
    if week.notes:
        lines.append(week.notes)
    if week.weekly_set_targets:
        targets = ", ".join(f"{k}: {v}" for k, v in sorted(week.weekly_set_targets.items()))
        lines.append(f"Weekly set targets: {targets}")
    for session in week.sessions:
        lines.append("")
        lines.extend(_session_lines(session))
    return lines


def _header_lines(plan: ProgramPlan) -> list[str]:
    lines = [
        f"# Program v{plan.version} — {plan.created_on:%Y%m%d} — {plan.goal_id}",
        "",
        f"- Check-in cadence: every {plan.checkin_cadence_days} days",
    ]
    if plan.season_ref:
        lines.append(f"- Season plan: {plan.season_ref}")
    if plan.reason:
        lines.append(f"- Reason: {plan.reason}")
    if plan.test_milestones:
        lines += ["", "## Test milestones"]
        for milestone in plan.test_milestones:
            lines.append(
                f"- Week {milestone.week_index}: {milestone.protocol} — "
                f"{', '.join(milestone.targets)}"
            )
    return lines


def render_program(plan: ProgramPlan) -> str:
    """Render a ProgramPlan to the human markdown view (deterministic)."""
    lines = _header_lines(plan)
    for meso in plan.mesocycles:
        lines += ["", f"## Mesocycle {meso.index} — {meso.phase}"]
        for week in meso.weeks:
            lines.append("")
            lines.extend(_week_lines(week))
    return "\n".join(lines).strip() + "\n"


def plan_citation_ids(plan: ProgramPlan) -> list[str]:
    """Every corpus id the plan cites, in order of first appearance, deduplicated.

    Order: advice, then rationale, then blocks in program order — this is the
    [n] numbering of the HTML page and the Sources section.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def add(cite: str | None) -> None:
        if cite and cite not in seen:
            seen.add(cite)
            ids.append(cite)

    for guidance in (*plan.advice, *plan.rationale):
        add(guidance.cite)
    for meso in plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                for block in session.blocks:
                    add(block.cite)
    return ids
