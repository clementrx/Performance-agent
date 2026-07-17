"""MCP tools for the pre-competition protocol.

Engine numbers are quoted, never renegotiated upward; the athlete may always
choose the more conservative option. The save gate resolves every citation id
against the corpus — an unknown id aborts before anything is written.
"""

import os
from typing import Any, Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import competition as competition_engine
from performance_agent.evidence.citations import resolve_citations
from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import CompetitionProtocol
from performance_agent.programs.render_protocol import protocol_citation_ids
from performance_agent.programs.render_protocol_html import render_protocol_html


class CarbTargetsView(TypedDict):
    """Evidence-based carbohydrate targets for the final window and the race."""

    loading_required: bool
    carb_g_per_kg_low: float | None
    carb_g_per_kg_high: float | None
    carb_g_per_day_low: float | None
    carb_g_per_day_high: float | None
    window_hours: int | None
    race_carb_g_per_h_low: float | None
    race_carb_g_per_h_high: float | None


class AttemptView(TypedDict):
    """Meet-day attempts for one lift, engine-computed."""

    lift: str
    e1rm_kg: float
    opener_kg: float
    second_kg: float
    third_kg: float
    flags: list[str]


class PacingSplitView(TypedDict):
    """One race segment: its target pace and the cumulative time at its end."""

    label: str
    distance_m: float
    target_pace_s_per_km: float
    cumulative_time_s: float


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


def carb_loading_targets(body_mass_kg: float, event_duration_min: float) -> CarbTargetsView:
    """Carb-loading and in-race fueling ranges for an event (evidence-based).

    Events >= 90 min: 8-12 g/kg/day over the final 48 h; 60-90 min: 6-8 g/kg/day
    over 24 h; shorter: loading_required=false (say so, don't invent a load).
    In-race: none under 60 min, 30-60 g/h up to ~2.5 h, 60-90 g/h beyond. Quote
    the ranges as ranges — food choices and timing are coaching conversation.
    """
    targets = competition_engine.carb_loading_targets(body_mass_kg, event_duration_min)
    return CarbTargetsView(
        loading_required=targets.loading_required,
        carb_g_per_kg_low=targets.carb_g_per_kg_low,
        carb_g_per_kg_high=targets.carb_g_per_kg_high,
        carb_g_per_day_low=targets.carb_g_per_day_low,
        carb_g_per_day_high=targets.carb_g_per_day_high,
        window_hours=targets.window_hours,
        race_carb_g_per_h_low=targets.race_carb_g_per_h_low,
        race_carb_g_per_h_high=targets.race_carb_g_per_h_high,
    )


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
    strategy: Literal["even", "negative"] = "even",
) -> list[PacingSplitView]:
    """Per-segment target paces and cumulative splits for a race plan.

    target_time_s comes from the athlete's goal or predict_race_time — this
    only distributes it. strategy 'even' or 'negative' (first half ~1% slower,
    second half balanced so the total lands on target).
    """
    return [
        PacingSplitView(
            label=split.label,
            distance_m=split.distance_m,
            target_pace_s_per_km=split.target_pace_s_per_km,
            cumulative_time_s=split.cumulative_time_s,
        )
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
    html_path = path.with_suffix(".html")
    tmp_path = html_path.with_suffix(".html.tmp")
    try:
        page = render_protocol_html(stored.protocol, locale=locale, citations=citations)
        tmp_path.write_text(page, encoding="utf-8")
        os.replace(tmp_path, html_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        msg = (
            f"protocol v{version} was saved, but writing the phone page failed at "
            f"{html_path}: {exc}; fix the filesystem issue and re-save as v{version + 1} "
            "with a reason"
        )
        raise ValueError(msg) from exc
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
