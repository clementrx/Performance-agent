"""MCP tools for day-of session autoregulation.

These adjust or compress TODAY'S session and log the change to
session_adjustments.jsonl -- they NEVER create a program version. The engine
computes the deltas; the coach narrates the one-sentence why and confirms with
the athlete. Escalation (>=3 downward adjustments or compressions in 14 days)
is surfaced by read_session_adjustments so the coach can route to adaptation.
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from performance_agent.memory import autoregulation, store
from performance_agent.memory import vbt as vbt_layer
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import (
    ReadinessBand,
    SessionAdjustmentEntry,
    SessionPlan,
)
from performance_agent.memory.vbt import LoadVelocityProfileView, VelocitySuggestionView


class AdjustedSessionView(TypedDict):
    """A readiness-adjusted session (not a program version).

    kind is unchanged (green), reduced (amber), or recovery (red). session is the
    adjusted SessionPlan to present; deltas_summary lists what changed, one item
    per block, for the athlete-facing why and for logging. velocity_suggestion is
    present only when warm-up velocity evidence was supplied AND a usable
    load-velocity profile exists — a bounded, labeled load nudge, never applied
    automatically.
    """

    kind: str
    band: str
    session: SessionPlan
    deltas_summary: list[str]
    velocity_suggestion: VelocitySuggestionView | None


class CutBlockView(TypedDict):
    """One block dropped to fit the time budget."""

    exercise: str
    priority: str
    reason: str


class CompressedSessionView(TypedDict):
    """A time-compressed session: what survives, what was cut, the new cost.

    fits is False when even the kept primary work overruns the budget (present it
    honestly: the athlete is short on time for the top set too).
    """

    session: SessionPlan
    cut: list[CutBlockView]
    estimated_minutes: int
    fits: bool


class SubstituteView(TypedDict):
    """One alternative exercise and the equipment it needs (source = coaching judgment)."""

    name: str
    equipment: list[str]
    source: str


class SubstitutionResult(TypedDict):
    """Same-pattern alternatives the athlete can do with the equipment on hand."""

    alternatives: list[SubstituteView]


class EscalationView(TypedDict):
    """Rolling-window counts of downward adjustments and whether to escalate.

    escalate True means >=threshold downgrades OR compressions in window_days --
    the plan no longer fits the athlete's life; route to program-adaptation.
    """

    downgrades: int
    compressions: int
    escalate: bool
    window_days: int
    threshold: int


class AdjustmentLogResult(TypedDict):
    """Count after logging one adjustment, plus the refreshed escalation signal."""

    total_adjustments: int
    escalation: EscalationView


class AdjustmentsHistory(TypedDict):
    """Logged adjustments (oldest first) plus the current escalation signal."""

    adjustments: list[SessionAdjustmentEntry]
    escalation: EscalationView


def _require_session(session_plan_id: str) -> SessionPlan:
    session = store.find_session_plan(resolve_athlete_dir(), session_plan_id)
    if session is None:
        msg = (
            f"no session {session_plan_id!r} in the latest structured program; "
            "check read_program (legacy prose programs have no session ids)"
        )
        raise ValueError(msg)
    return session


def _escalation_view(signals: autoregulation.EscalationSignals) -> EscalationView:
    return EscalationView(
        downgrades=signals.downgrades,
        compressions=signals.compressions,
        escalate=signals.escalate,
        window_days=signals.window_days,
        threshold=signals.threshold,
    )


def adjust_session(
    session_plan_id: str,
    band: ReadinessBand,
    velocity_exercise: str | None = None,
    velocity_load_kg: Annotated[float, Field(gt=0, le=1000)] | None = None,
    velocity_mean_velocity: Annotated[float, Field(gt=0, le=10)] | None = None,
) -> AdjustedSessionView:
    """Adjust today's planned session to a readiness band (green/amber/red).

    Looks the session up by id in the latest structured program. green leaves it
    unchanged; amber steps the top block down one intensity step, cuts back-off
    and secondary volume ~25%, and drops optional blocks; red replaces it with an
    easy aerobic/mobility recovery session (never strength_heavy or HIIT). Returns
    the adjusted session and a per-block delta summary. Get the band from
    compute_readiness first. This NEVER creates a program version -- log it with
    log_session_adjustment.

    OPTIONAL velocity evidence: pass velocity_exercise + velocity_load_kg +
    velocity_mean_velocity from today's warm-up set. When a usable load-velocity
    profile exists for that exercise (from logged VBT sets), the result carries a
    bounded (+/-10%) velocity_suggestion comparing today's e1RM to the profile's --
    a labeled coaching nudge, never auto-applied. Without velocity evidence (or a
    usable profile) the suggestion is null and behavior is unchanged.
    """
    session = _require_session(session_plan_id)
    result = autoregulation.adjust_session(session, band)
    suggestion: VelocitySuggestionView | None = None
    if (
        velocity_exercise is not None
        and velocity_load_kg is not None
        and velocity_mean_velocity is not None
    ):
        suggestion = vbt_layer.velocity_suggestion(
            resolve_athlete_dir(), velocity_exercise, velocity_load_kg, velocity_mean_velocity
        )
    return AdjustedSessionView(
        kind=result.kind,
        band=result.band,
        session=result.session,
        deltas_summary=result.deltas_summary,
        velocity_suggestion=suggestion,
    )


def fit_load_velocity(
    exercise: str,
    mvt: Annotated[float, Field(gt=0, le=2)] = 0.30,
) -> LoadVelocityProfileView:
    """Fit an exercise's load-velocity profile from its logged VBT sets.

    Reads every logged vbt_set for the exercise, fits mean velocity vs load, and
    estimates 1RM at the minimal velocity threshold mvt (default 0.30 m/s). The
    result carries usable + reason: it refuses (usable=false) with fewer than 4
    distinct loads, a load span under 30% of the estimated 1RM, or a bad fit --
    never presenting a fabricated 1RM. Errors when fewer than 2 VBT sets exist.
    """
    return vbt_layer.fit_exercise_profile(resolve_athlete_dir(), exercise, mvt)


def compress_session(
    session_plan_id: str, available_minutes: Annotated[int, Field(ge=1, le=480)]
) -> CompressedSessionView:
    """Fit today's session into the minutes actually available.

    Looks the session up by id in the latest structured program. Cuts optional
    blocks first, then secondary work; the primary top set is always kept. Time
    model: sets x (~40s work + rest) plus generated warm-up ramp sets. Returns the
    surviving session (est_minutes updated), what was cut, and whether it fits.
    This NEVER creates a program version -- log it with log_session_adjustment.
    """
    session = _require_session(session_plan_id)
    result = autoregulation.compress_session(session, available_minutes)
    return CompressedSessionView(
        session=result.session,
        cut=[
            CutBlockView(exercise=c.exercise, priority=c.priority, reason=c.reason)
            for c in result.cut
        ],
        estimated_minutes=result.estimated_minutes,
        fits=result.fits,
    )


def substitute_exercise(
    exercise: str, pattern: str, available_equipment: list[str]
) -> SubstitutionResult:
    """List exercise swaps doable with the equipment on hand.

    pattern is a movement pattern (squat, hinge, push_h, push_v, pull_h, pull_v,
    lunge, carry, core, jump, sprint, throw, olympic, run, ride, swim). When the
    original exercise is in the ontology, alternatives rank by STIMULUS EQUIVALENCE
    (qualities/force/regime similarity, filtered by equipment and the athlete's
    active-injury contraindications); otherwise it falls back to the curated
    same-pattern table. Excludes the original and any option whose equipment is not
    available; bodyweight options always remain. Every alternative is coaching
    judgment, not a corpus-cited prescription.
    """
    alternatives = autoregulation.substitute_exercise(
        resolve_athlete_dir(), exercise, pattern, available_equipment
    )
    return SubstitutionResult(
        alternatives=[
            SubstituteView(name=s.name, equipment=list(s.equipment), source=s.source)
            for s in alternatives
        ]
    )


def log_session_adjustment(entry: SessionAdjustmentEntry) -> AdjustmentLogResult:
    """Append one day-of adjustment to session_adjustments.jsonl (never a program version).

    kind is readiness/time/equipment/manual; inputs carries the band, minutes, or
    missing equipment; deltas_summary is what changed; applied says whether the
    athlete took the adjusted session. Returns the total logged plus the refreshed
    escalation signal -- act on escalate=True by routing to program-adaptation.
    Timestamps are naive local wall-clock time.
    """
    base = resolve_athlete_dir()
    store.append_session_adjustment(base, entry)
    return AdjustmentLogResult(
        total_adjustments=len(store.read_session_adjustments(base)),
        escalation=_escalation_view(autoregulation.escalation_signals(base)),
    )


def read_session_adjustments(
    last_n: Annotated[int, Field(ge=1)] | None = None,
) -> AdjustmentsHistory:
    """Return logged day-of adjustments (oldest first) plus the escalation signal.

    Read these as diagnostic signals: repeated time compressions mean a schedule
    mismatch, repeated readiness downgrades mean under-recovery. escalate=True in
    the escalation block means route to program-adaptation. last_n limits to the
    most recent N entries (escalation always reflects the full 14-day window).
    """
    base = resolve_athlete_dir()
    adjustments = store.read_session_adjustments(base)
    escalation = _escalation_view(autoregulation.escalation_signals(base))
    if last_n is not None:
        adjustments = adjustments[-last_n:]
    return AdjustmentsHistory(adjustments=adjustments, escalation=escalation)


def register(mcp: FastMCP) -> None:
    """Register every autoregulation tool on the server."""
    for tool in (
        adjust_session,
        compress_session,
        substitute_exercise,
        fit_load_velocity,
        log_session_adjustment,
        read_session_adjustments,
    ):
        mcp.tool()(tool)
