"""Day-of session autoregulation (pure): readiness adjustment, time compression, substitution.

Deterministic deltas only. The engine works on lightweight engine-local dataclasses
(Session/Block) because engine/ never imports memory.schemas (purity + no cycle);
the memory layer (memory/autoregulation.py) converts SessionPlan <-> these and builds
the recovery template.

Adjustment step sizes (RPE -1 / RIR +1 / pct_1RM -5 pts) follow the RIR/RPE
autoregulation framework (Helms et al.) in spirit, but the exact deltas here are a
team-chosen prior / coaching judgment, not a cited corpus constant. The per-set time
model, the -25% volume cut, and the escalation thresholds are team-chosen priors.
"""

import math
from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number
from performance_agent.engine.load import ReadinessBand
from performance_agent.engine.strength import warmup_scheme
from performance_agent.engine.substitutions import Substitute, substitutes_for

BlockPriority = Literal["primary", "secondary", "optional"]

# --- team-chosen priors (labeled) -----------------------------------------
# Amber back-off/secondary volume cut: -25%, the midpoint of the 20-30% band.
READINESS_VOLUME_FACTOR = 0.75
# One intensity "step" down for an amber top block, per prescription channel.
RPE_STEP = 1.0
RIR_STEP = 1.0
PCT_1RM_STEP = 0.05
LOAD_STEP_FACTOR = 0.95
_MIN_RPE = 1.0
_MAX_RIR = 10.0
_MIN_PCT_1RM = 0.05
# Time model: a working set is ~40s of work; unspecified rest defaults to 90s;
# each generated warm-up set is a short set plus 60s to reset.
WORK_SECONDS_PER_SET = 40
DEFAULT_REST_S = 90
WARMUP_REST_S = 60
_SECONDS_PER_MINUTE = 60
# Escalation: >=3 downward readiness adjustments OR >=3 time compressions inside
# a rolling 14-day window means the plan no longer fits the life.
ESCALATION_WINDOW_DAYS = 14
ESCALATION_THRESHOLD = 3
# A red-readiness session is replaced wholesale by this recovery template.
RECOVERY_QUALITIES: tuple[str, ...] = ("recovery",)
RECOVERY_MINUTES = 30


@dataclass(frozen=True)
class Block:
    """Engine-local view of one program block, enough to cost and adjust it."""

    priority: BlockPriority
    sets: int
    rest_s: int | None
    warmup_auto: bool
    load_kg: float | None
    pct_1rm: float | None
    rir: float | None
    rpe: float | None
    duration_min: float | None


@dataclass(frozen=True)
class Session:
    """Engine-local view of a session: its qualities and ordered blocks."""

    qualities: tuple[str, ...]
    blocks: tuple[Block, ...]

    @property
    def is_strength(self) -> bool:
        """Whether the session carries strength_heavy work (drives warm-up ramps)."""
        return "strength_heavy" in self.qualities


@dataclass(frozen=True)
class BlockDelta:
    """What happened to one block: kept, intensity-stepped, volume-cut, or dropped."""

    index: int
    action: Literal["kept", "intensity_down", "volume_down", "dropped"]
    old_sets: int
    new_sets: int
    channel: Literal["rpe", "rir", "pct_1rm", "load_kg"] | None
    old_value: float | None
    new_value: float | None


@dataclass(frozen=True)
class AdjustedSession:
    """A readiness-adjusted session: per-block deltas plus a machine-readable summary."""

    band: ReadinessBand
    kind: Literal["unchanged", "reduced", "recovery"]
    blocks: tuple[BlockDelta, ...]
    deltas_summary: tuple[str, ...]


@dataclass(frozen=True)
class CutBlock:
    """One block removed during time compression, with the reason."""

    index: int
    priority: BlockPriority
    reason: str


@dataclass(frozen=True)
class CompressedSession:
    """A time-compressed session: which blocks survive, what was cut, the new cost."""

    kept_indices: tuple[int, ...]
    cut: tuple[CutBlock, ...]
    estimated_minutes: int
    fits: bool


@dataclass(frozen=True)
class AdjustmentRecord:
    """One past adjustment, for escalation counting (days_ago from a reference date)."""

    kind: Literal["readiness", "time", "equipment", "manual"]
    band: ReadinessBand | None
    applied: bool
    days_ago: int


@dataclass(frozen=True)
class EscalationSignals:
    """Rolling-window counts of downward adjustments and whether they cross threshold."""

    downgrades: int
    compressions: int
    escalate: bool
    window_days: int
    threshold: int


def _intensity_channel(
    block: Block,
) -> tuple[Literal["rpe", "rir", "pct_1rm", "load_kg"] | None, float | None]:
    """Return the block's single intensity channel and its current value."""
    if block.rpe is not None:
        return "rpe", block.rpe
    if block.rir is not None:
        return "rir", block.rir
    if block.pct_1rm is not None:
        return "pct_1rm", block.pct_1rm
    if block.load_kg is not None:
        return "load_kg", block.load_kg
    return None, None


def _stepped_value(channel: str, value: float) -> float:
    """Step one intensity channel down by a single autoregulation step."""
    if channel == "rpe":
        return max(_MIN_RPE, value - RPE_STEP)
    if channel == "rir":
        return min(_MAX_RIR, value + RIR_STEP)
    if channel == "pct_1rm":
        return max(_MIN_PCT_1RM, round(value - PCT_1RM_STEP, 4))
    return round(value * LOAD_STEP_FACTOR, 2)  # load_kg


def _reduced_sets(sets: int) -> int:
    """Cut volume by ~25%, always dropping at least one set for multi-set blocks."""
    return max(1, math.floor(sets * READINESS_VOLUME_FACTOR))


def _amber_delta(index: int, block: Block) -> BlockDelta:
    if block.priority == "optional":
        return BlockDelta(index, "dropped", block.sets, 0, None, None, None)
    if block.priority == "primary":
        channel, value = _intensity_channel(block)
        if channel is None or value is None:
            return BlockDelta(index, "kept", block.sets, block.sets, None, None, None)
        return BlockDelta(
            index,
            "intensity_down",
            block.sets,
            block.sets,
            channel,
            value,
            _stepped_value(channel, value),
        )
    new_sets = _reduced_sets(block.sets)
    action = "volume_down" if new_sets < block.sets else "kept"
    return BlockDelta(index, action, block.sets, new_sets, None, None, None)


def adjust_session_for_readiness(session: Session, band: ReadinessBand) -> AdjustedSession:
    """Adjust today's session to the athlete's readiness band (deterministic).

    green: unchanged. amber: the top (primary) block drops one intensity step,
    back-off/secondary volume is cut ~25%, optional blocks are dropped. red: the
    session is replaced wholesale by a recovery template (never strength_heavy,
    never HIIT) -- the memory layer builds that session; the engine only signals
    it. Returns per-block deltas plus a machine-readable summary of what changed.
    """
    if band not in ("green", "amber", "red"):
        msg = f"band must be green, amber or red, got {band!r}"
        raise ValueError(msg)
    if band == "red":
        return AdjustedSession(
            band, "recovery", (), ("replace with recovery: Z1-Z2 aerobic / mobility, or rest",)
        )
    if band == "green":
        blocks = tuple(
            BlockDelta(i, "kept", b.sets, b.sets, None, None, None)
            for i, b in enumerate(session.blocks)
        )
        return AdjustedSession(band, "unchanged", blocks, ("green readiness: session unchanged",))
    deltas = tuple(_amber_delta(i, b) for i, b in enumerate(session.blocks))
    summary = tuple(_delta_line(d) for d in deltas if d.action != "kept")
    return AdjustedSession(
        band, "reduced", deltas, summary or ("amber readiness: no change needed",)
    )


def _delta_line(delta: BlockDelta) -> str:
    if delta.action == "dropped":
        return f"block {delta.index}: dropped (optional, amber readiness)"
    if delta.action == "volume_down":
        return (
            f"block {delta.index}: volume {delta.old_sets}->{delta.new_sets} sets (amber readiness)"
        )
    return (
        f"block {delta.index}: {delta.channel} {_num(delta.old_value)}->"
        f"{_num(delta.new_value)} (amber readiness)"
    )


def _num(value: float | None) -> str:
    return "?" if value is None else f"{value:g}"


def _block_cost_seconds(block: Block, *, is_strength: bool) -> float:
    """Time cost of one block: sets x (work + rest) plus generated warm-up sets."""
    rest = block.rest_s if block.rest_s is not None else DEFAULT_REST_S
    work = (
        block.duration_min * _SECONDS_PER_MINUTE
        if block.duration_min is not None
        else WORK_SECONDS_PER_SET
    )
    cost = block.sets * (work + rest)
    if (
        is_strength
        and block.warmup_auto
        and block.priority == "primary"
        and block.load_kg is not None
    ):
        cost += len(warmup_scheme(block.load_kg)) * (WORK_SECONDS_PER_SET + WARMUP_REST_S)
    return cost


def compress_session(session: Session, available_minutes: int) -> CompressedSession:
    """Fit a session into a time budget by cutting the least essential work first.

    Cut order: optional blocks, then secondary blocks; primary top work is never
    dropped (it survives even when it alone overruns the budget). Returns which
    block indices remain, what was cut and why, the estimated minutes for the kept
    work, and whether it fits. Primary blocks are always kept, so whenever the
    budget covers their cost the compressed session fits.
    """
    validate_whole_number("available_minutes", available_minutes)
    if available_minutes < 1:
        msg = f"available_minutes must be >= 1, got {available_minutes!r}"
        raise ValueError(msg)
    budget = available_minutes * _SECONDS_PER_MINUTE
    costs = [_block_cost_seconds(b, is_strength=session.is_strength) for b in session.blocks]
    kept = [True] * len(session.blocks)
    cut: list[CutBlock] = []
    total = sum(costs)
    for priority in ("optional", "secondary"):
        for i, block in enumerate(session.blocks):
            if total <= budget:
                break
            if kept[i] and block.priority == priority:
                kept[i] = False
                total -= costs[i]
                cut.append(CutBlock(i, block.priority, f"cut to fit {available_minutes} min"))
        if total <= budget:
            break
    kept_indices = tuple(i for i, on in enumerate(kept) if on)
    estimated = max(1, math.ceil(total / _SECONDS_PER_MINUTE))
    return CompressedSession(kept_indices, tuple(cut), estimated, total <= budget)


def substitute_exercise(
    exercise: str, pattern: str, available_equipment: list[str]
) -> list[Substitute]:
    """List same-pattern exercise swaps the athlete can do with the equipment on hand.

    Excludes the original exercise (case-insensitive) and any option whose required
    equipment is not fully available; bodyweight options need nothing so they always
    remain. Raises on an unknown movement pattern. Every entry is coaching judgment
    (a standard same-pattern swap), not a corpus-cited prescription.
    """
    available = {token.strip().casefold() for token in available_equipment}
    target = exercise.strip().casefold()
    return [
        sub
        for sub in substitutes_for(pattern)
        if sub.name.casefold() != target
        and all(item.casefold() in available for item in sub.equipment)
    ]


def count_escalation_signals(
    records: list[AdjustmentRecord],
    window_days: int = ESCALATION_WINDOW_DAYS,
    threshold: int = ESCALATION_THRESHOLD,
) -> EscalationSignals:
    """Count downward readiness adjustments and time compressions in the recent window.

    A downgrade is an applied amber/red readiness adjustment; a compression is an
    applied time cut. Only records with 0 <= days_ago <= window_days count.
    escalate is True when either count reaches the threshold -- the signal to route
    to program-adaptation because the plan no longer fits the athlete's life.
    """
    validate_finite("window_days", window_days)
    if window_days < 1:
        msg = f"window_days must be >= 1, got {window_days!r}"
        raise ValueError(msg)
    if threshold < 1:
        msg = f"threshold must be >= 1, got {threshold!r}"
        raise ValueError(msg)
    in_window = [r for r in records if r.applied and 0 <= r.days_ago <= window_days]
    downgrades = sum(1 for r in in_window if r.kind == "readiness" and r.band in ("amber", "red"))
    compressions = sum(1 for r in in_window if r.kind == "time")
    escalate = downgrades >= threshold or compressions >= threshold
    return EscalationSignals(downgrades, compressions, escalate, window_days, threshold)
