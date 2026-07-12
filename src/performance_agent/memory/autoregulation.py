"""Session autoregulation at the athlete layer: SessionPlan <-> engine, then apply.

The engine (engine/autoregulation.py) is pydantic-free and works on engine-local
dataclasses; this module converts a SessionPlan into that shape, calls the pure
adjuster/compressor, rebuilds a valid SessionPlan from the result, and owns the
recovery template and the file I/O for escalation counting. All SessionPlan and
datetime handling lives here, never in the engine.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from performance_agent.engine.autoregulation import (
    RECOVERY_MINUTES,
    AdjustmentRecord,
    Block,
    BlockDelta,
    EscalationSignals,
    Session,
    adjust_session_for_readiness,
    count_escalation_signals,
)
from performance_agent.engine.autoregulation import compress_session as engine_compress_session
from performance_agent.engine.autoregulation import (
    substitute_exercise as engine_substitute_exercise,
)
from performance_agent.engine.substitutions import Substitute
from performance_agent.memory import store
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ReadinessBand,
    SessionPlan,
)

_MAX_EST_MINUTES = 480
_RECOVERY_EXERCISE = "Zone 1-2 aerobic + mobility"


@dataclass(frozen=True)
class AdjustmentResult:
    """A readiness-adjusted session plus a human/machine summary of the change."""

    kind: str  # unchanged | reduced | recovery
    band: ReadinessBand
    session: SessionPlan
    deltas_summary: list[str]


@dataclass(frozen=True)
class CutView:
    """One block dropped during compression."""

    exercise: str
    priority: str
    reason: str


@dataclass(frozen=True)
class CompressionResult:
    """A time-compressed session, what was cut, and whether it fits the budget."""

    session: SessionPlan
    cut: list[CutView]
    estimated_minutes: int
    fits: bool


def _to_engine_block(block: ExerciseBlock) -> Block:
    return Block(
        priority=block.priority,
        sets=block.sets,
        rest_s=block.rest_s,
        warmup_auto=block.warmup == "auto",
        load_kg=block.load_kg,
        pct_1rm=block.pct_1rm,
        rir=block.rir,
        rpe=block.rpe,
        duration_min=block.duration_min,
    )


def _to_engine_session(plan: SessionPlan) -> Session:
    return Session(
        qualities=tuple(plan.qualities), blocks=tuple(_to_engine_block(b) for b in plan.blocks)
    )


def _num(value: float | None) -> str:
    return "?" if value is None else f"{value:g}"


def _recovery_session(plan: SessionPlan) -> SessionPlan:
    """Replace a red-readiness session with an easy aerobic/mobility block or rest."""
    block = ExerciseBlock(
        exercise=_RECOVERY_EXERCISE,
        priority="primary",
        warmup="none",
        sets=1,
        duration_min=float(RECOVERY_MINUTES),
        rest_s=0,
        progression_rule="keep it genuinely easy; this replaces today's load, not adds to it",
    )
    return plan.model_copy(
        update={
            "qualities": ["recovery"],
            "patterns": [],
            "est_minutes": RECOVERY_MINUTES,
            "purpose": "Recovery day (red readiness): protect adaptation, return fresh",
            "blocks": [block],
        }
    )


def _apply_delta(block: ExerciseBlock, delta: BlockDelta) -> ExerciseBlock | None:
    if delta.action == "dropped":
        return None
    if delta.action == "volume_down":
        return block.model_copy(update={"sets": delta.new_sets})
    if delta.action == "intensity_down" and delta.channel is not None:
        return block.model_copy(update={delta.channel: delta.new_value})
    return block


def _delta_summary(block: ExerciseBlock, delta: BlockDelta) -> str | None:
    if delta.action == "dropped":
        return f"{block.exercise}: dropped (optional, amber readiness)"
    if delta.action == "volume_down":
        return f"{block.exercise}: {delta.old_sets}->{delta.new_sets} sets (amber readiness)"
    if delta.action == "intensity_down":
        return (
            f"{block.exercise}: {delta.channel} {_num(delta.old_value)}->"
            f"{_num(delta.new_value)} (amber readiness)"
        )
    return None


def adjust_session(plan: SessionPlan, band: ReadinessBand) -> AdjustmentResult:
    """Adjust a planned session to a readiness band, returning a valid SessionPlan.

    green leaves the session untouched; amber steps the top block down, cuts
    back-off/secondary volume and drops optional blocks; red returns a recovery
    template (never strength_heavy/HIIT). Never versions a program.
    """
    adjusted = adjust_session_for_readiness(_to_engine_session(plan), band)
    if adjusted.kind == "recovery":
        summary = [
            f"red readiness: replaced with {_RECOVERY_EXERCISE} ({RECOVERY_MINUTES} min) or rest"
        ]
        return AdjustmentResult("recovery", band, _recovery_session(plan), summary)
    new_blocks: list[ExerciseBlock] = []
    summary = []
    for block, delta in zip(plan.blocks, adjusted.blocks, strict=True):
        line = _delta_summary(block, delta)
        if line is not None:
            summary.append(line)
        applied = _apply_delta(block, delta)
        if applied is not None:
            new_blocks.append(applied)
    session = plan.model_copy(update={"blocks": new_blocks})
    return AdjustmentResult(adjusted.kind, band, session, summary or list(adjusted.deltas_summary))


def compress_session(plan: SessionPlan, available_minutes: int) -> CompressionResult:
    """Fit a session into available_minutes, cutting optional then secondary work.

    Primary top work is always kept. Returns the surviving SessionPlan (with its
    est_minutes updated to the compressed cost), what was cut, and whether it fits.
    """
    result = engine_compress_session(_to_engine_session(plan), available_minutes)
    kept = [plan.blocks[i] for i in result.kept_indices]
    est = min(_MAX_EST_MINUTES, result.estimated_minutes)
    session = plan.model_copy(update={"blocks": kept, "est_minutes": est})
    cut = [CutView(plan.blocks[c.index].exercise, c.priority, c.reason) for c in result.cut]
    return CompressionResult(session, cut, est, result.fits)


def substitute_exercise(
    exercise: str, pattern: str, available_equipment: list[str]
) -> list[Substitute]:
    """Same-pattern swaps doable with the equipment on hand (pure engine passthrough)."""
    return engine_substitute_exercise(exercise, pattern, available_equipment)


def escalation_signals(base_dir: Path, now: datetime | None = None) -> EscalationSignals:
    """Count recent downward adjustments/compressions from the stored adjustment log."""
    reference = now or datetime.now()
    records = [
        AdjustmentRecord(
            kind=entry.kind,
            band=entry.inputs.band,
            applied=entry.applied,
            days_ago=(reference - entry.at).days,
        )
        for entry in store.read_session_adjustments(base_dir)
    ]
    return count_escalation_signals(records)
