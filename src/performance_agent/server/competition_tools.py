"""MCP tools for the pre-competition protocol.

Engine numbers are quoted, never renegotiated upward; the athlete may always
choose the more conservative option. The save gate resolves every citation id
against the corpus — an unknown id aborts before anything is written.
"""

from dataclasses import asdict
from typing import Any, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import competition as competition_engine
from performance_agent.evidence.citations import resolve_citations
from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import CompetitionProtocol
from performance_agent.programs.render_protocol import protocol_citation_ids
from performance_agent.programs.render_protocol_html import render_protocol_html


class AttemptView(TypedDict):
    """Meet-day attempts for one lift, engine-computed."""

    lift: str
    e1rm_kg: float
    opener_kg: float
    second_kg: float
    third_kg: float
    flags: list[str]


class ProtocolSaved(TypedDict):
    """Result of writing a protocol version (markdown + phone page)."""

    path: str
    version: int
    html_path: str


class ProtocolView(TypedDict):
    """A stored protocol version: structured plan plus rendered markdown."""

    version: int
    event_id: str
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    protocol: dict[str, Any]


def carb_loading_targets(body_mass_kg: float, event_duration_min: float) -> dict[str, Any]:
    """Carb-loading and in-race fueling ranges for an event (evidence-based).

    Events >= 90 min: 8-12 g/kg/day over the final 48 h; 60-90 min: 6-8 g/kg/day
    over 24 h; shorter: loading_required=false (say so, don't invent a load).
    In-race: none under 60 min, 30-60 g/h up to ~2.5 h, 60-90 g/h beyond. Quote
    the ranges as ranges — food choices and timing are coaching conversation.
    """
    return asdict(competition_engine.carb_loading_targets(body_mass_kg, event_duration_min))


def select_attempts(
    lift: str, e1rm_kg: float, goal_kg: float, rounding_kg: float = 2.5
) -> AttemptView:
    """Three meet-day attempts from the e1RM (get it from estimate_1rm first).

    Opener ~91% (a confident triple), second ~96%, third at the goal when it
    lies within 93-105% of e1RM — else ~101% with flag goal_beyond_e1rm (or
    goal_below_e1rm_range on the low side): name the gap honestly, never
    pretend the goal is on the bar. The athlete may always call lighter
    attempts; never push heavier than the engine's numbers.
    """
    selection = competition_engine.select_attempts(e1rm_kg, goal_kg, rounding_kg)
    return AttemptView(
        lift=lift,
        e1rm_kg=e1rm_kg,
        opener_kg=selection.opener_kg,
        second_kg=selection.second_kg,
        third_kg=selection.third_kg,
        flags=list(selection.flags),
    )


def pacing_plan(
    distance_m: float,
    target_time_s: float,
    segment_m: float = 1000.0,
    strategy: str = "even",
) -> list[dict[str, Any]]:
    """Per-segment target paces and cumulative splits for a race plan.

    target_time_s comes from the athlete's goal or predict_race_time — this
    only distributes it. strategy 'even' or 'negative' (first half ~1% slower,
    second half balanced so the total lands on target).
    """
    return [
        asdict(split)
        for split in competition_engine.pacing_plan(distance_m, target_time_s, segment_m, strategy)
    ]


def save_competition_protocol(
    protocol: CompetitionProtocol, reason: str | None = None
) -> ProtocolSaved:
    """Write the NEXT protocol version for its event (immutable audit trail).

    The event must exist in the calendar with a matching, non-past date.
    Version 1 needs no reason; v2+ requires one naming the trigger. Every cite
    (advice, day lines, fueling, practices) must be a real corpus id — an
    unknown id aborts the save (anti-fabrication). Every documented practice
    carries its warning by schema. Alongside the markdown, a standalone phone
    page is written — hand that file to the athlete for the event.
    MANDATORY: pass the draft through program-review's protocol gate BEFORE
    saving; only an APPROVED verdict saves.
    """
    base = resolve_athlete_dir()
    citations = resolve_citations(protocol_citation_ids(protocol))
    path, version = store.save_competition_protocol(base, protocol, reason, citations=citations)
    stored = store.read_competition_protocol(base, protocol.event_id, version)
    if stored is None:  # pragma: no cover - just written above
        msg = f"protocol v{version} vanished after save"
        raise ValueError(msg)
    locale = store.read_profile(base).locale
    page = render_protocol_html(stored.protocol, locale=locale, citations=citations)
    html_path = path.with_suffix(".html")
    html_path.write_text(page, encoding="utf-8")
    return ProtocolSaved(path=str(path), version=version, html_path=str(html_path))


def read_competition_protocol(event_id: str, version: int | None = None) -> ProtocolView:
    """Return the latest (or a specific) protocol version for an event."""
    stored = store.read_competition_protocol(resolve_athlete_dir(), event_id, version)
    if stored is None:
        msg = f"no protocol saved for event {event_id!r}; save_competition_protocol first"
        raise ValueError(msg)
    return ProtocolView(
        version=stored.version,
        event_id=stored.event_id,
        goal_id=stored.goal_id,
        created_on=stored.created_on,
        reason=stored.reason,
        markdown=stored.markdown,
        protocol=stored.protocol.model_dump(mode="json"),
    )


def register(mcp: FastMCP) -> None:
    """Register the competition tools on the server."""
    for tool in (
        carb_loading_targets,
        select_attempts,
        pacing_plan,
        save_competition_protocol,
        read_competition_protocol,
    ):
        mcp.tool()(tool)
