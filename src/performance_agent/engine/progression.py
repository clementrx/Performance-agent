"""Pure weekly progression math: one function per ProgressionRule kind.

No I/O, no dates. The memory layer (memory/weekly_review.py) matches logs to
blocks and dispatches here. The ±10% weekly cap on autoregulated (RIR) load
moves and the round-half-up-to-increment rounding are team-chosen priors.
"""

from dataclasses import dataclass
from typing import Protocol

# Autoregulated weekly load moves are capped at ±10% (team-chosen prior):
# a single week's mean RIR should nudge the load, not rewrite it.
_MAX_RIR_ADJUST_PCT = 0.10


class ProgressionRuleLike(Protocol):
    """Structural view of memory.schemas.ProgressionRule (engine stays import-pure)."""

    @property
    def kind(self) -> str:
        """Rule kind; read-only so the model's Literal type stays assignable."""
        ...

    rep_min: int | None
    rep_max: int | None
    increment_kg: float | None
    target_rir: float | None
    adjust_pct_per_rir: float
    rounding_kg: float


@dataclass(frozen=True)
class SetActual:
    """One logged set, already matched to the block being progressed."""

    reps: int
    load_kg: float
    rir: float | None = None


@dataclass(frozen=True)
class LoadSuggestion:
    """The engine's verdict for one block's next week."""

    next_load_kg: float | None
    action: str  # increment | hold | decrement | per_plan
    flags: tuple[str, ...] = ()


def round_to_increment(value: float, step: float) -> float:
    """Round to the nearest plate step (2.5 kg default upstream)."""
    if step <= 0:
        msg = f"step must be positive, got {step!r}"
        raise ValueError(msg)
    return round(value / step) * step


def _require(rule: ProgressionRuleLike, field: str) -> float:
    value = getattr(rule, field)
    if value is None:
        msg = f"kind={rule.kind} requires {field}; the schema validator should have caught this"
        raise ValueError(msg)
    return value


def next_load_double(
    rule: ProgressionRuleLike, current_load_kg: float, sets: list[SetActual]
) -> LoadSuggestion:
    """Double progression: all sets at rep_max -> add increment, else hold."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    rep_min = _require(rule, "rep_min")
    rep_max = _require(rule, "rep_max")
    increment_kg = _require(rule, "increment_kg")
    if all(s.reps >= rep_max for s in sets):
        raised = round_to_increment(current_load_kg + increment_kg, rule.rounding_kg)
        return LoadSuggestion(raised, "increment")
    flags = ("failed_sets",) if any(s.reps < rep_min for s in sets) else ()
    return LoadSuggestion(current_load_kg, "hold", flags)


def next_load_linear(
    rule: ProgressionRuleLike,
    current_load_kg: float,
    prescribed_reps: int,
    sets: list[SetActual],
) -> LoadSuggestion:
    """Linear load: every set hit the prescribed reps -> add increment, else hold."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    increment_kg = _require(rule, "increment_kg")
    if all(s.reps >= prescribed_reps for s in sets):
        raised = round_to_increment(current_load_kg + increment_kg, rule.rounding_kg)
        return LoadSuggestion(raised, "increment")
    return LoadSuggestion(current_load_kg, "hold", ("failed_sets",))


def next_load_rir(
    rule: ProgressionRuleLike, current_load_kg: float, sets: list[SetActual]
) -> LoadSuggestion:
    """RIR-target autoregulation: adjust_pct_per_rir per point of mean deviation."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    target_rir = _require(rule, "target_rir")
    rirs = [s.rir for s in sets if s.rir is not None]
    if not rirs:
        return LoadSuggestion(current_load_kg, "hold", ("no_rir_logged",))
    delta = sum(rirs) / len(rirs) - target_rir
    adjust = rule.adjust_pct_per_rir * delta
    flags: tuple[str, ...] = ()
    if abs(adjust) > _MAX_RIR_ADJUST_PCT:
        adjust = _MAX_RIR_ADJUST_PCT if adjust > 0 else -_MAX_RIR_ADJUST_PCT
        flags = ("clamped",)
    raised = round_to_increment(current_load_kg * (1 + adjust), rule.rounding_kg)
    if raised > current_load_kg:
        action = "increment"
    elif raised < current_load_kg:
        action = "decrement"
    else:
        action = "hold"
    return LoadSuggestion(raised, action, flags)


def next_load_from_pct(
    next_pct_1rm: float, e1rm_kg: float | None, rounding_kg: float
) -> LoadSuggestion:
    """Percent-planned blocks: next week's planned pct resolved against e1RM."""
    if e1rm_kg is None:
        return LoadSuggestion(None, "per_plan", ("no_e1rm",))
    return LoadSuggestion(round_to_increment(next_pct_1rm * e1rm_kg, rounding_kg), "per_plan")
