"""Backward season planning: tile a training horizon around dated A events.

Pure and deterministic, working in integer week space (1 = first planned week);
the date -> week conversion lives in the memory layer because the engine stays
datetime-free. The planner reserves a taper immediately before each A-priority
competition and fills the gaps with development blocks, so the whole season is
built backward from the calendar rather than forward from a start date.

Taper lengths follow the taper meta-analysis in the corpus
(tapering-performance-meta-2007: ~8-14 days endurance, shorter for strength);
the remaining spread and the block-vs-waves threshold are team-chosen priors
consistent with engine/periodization.py (MIN_BLOCK_WEEKS).
"""

import math
from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_whole_number

SeasonModality = Literal["strength", "endurance", "mixed"]
EventPriority = Literal["A", "B", "C"]
SegmentPhase = Literal[
    "block",
    "waves",
    "peaking",
    "in_season",
    "maintenance",
    "taper",
    "competition",
    "transition",
]

# Block vs waves, and the "two A events too close" compromise threshold — mirrors
# periodization.MIN_BLOCK_WEEKS (below 6 weeks the three block phases degenerate).
MIN_BLOCK_WEEKS = 6
TAPER_MIN_DAYS = 4
TAPER_MAX_DAYS = 14
_DAYS_PER_WEEK = 7
# Base taper days by modality — endurance tapers longest (Bosquet meta), strength
# shortest; mixed between. The spread is a team-chosen prior.
_TAPER_BASE_DAYS: dict[SeasonModality, int] = {"strength": 7, "mixed": 10, "endurance": 12}
_SHORT_BUILDUP_WEEKS = 3  # below this, a long taper has nothing to taper from
_SHORT_BUILDUP_PENALTY_DAYS = 3


@dataclass(frozen=True)
class SeasonEvent:
    """A calendar event placed in week space (week 1 = first planned week)."""

    event_id: str
    week: int
    priority: EventPriority
    kind: str


@dataclass(frozen=True)
class SeasonSegment:
    """One contiguous stretch of the season with a chosen phase type."""

    start_week: int
    end_week: int
    phase_type: SegmentPhase
    anchor_event_id: str | None
    rationale: str


def recommend_taper_length(
    buildup_weeks: int, modality: SeasonModality, event_priority: EventPriority
) -> int:
    """Recommend a taper length in days (bounded 4-14) for an event.

    Endurance tapers run longest and strength shortest (corpus taper meta);
    a very short buildup shortens the taper, and a B event gets a mini-taper
    (half), never a full one. Days, clamped to [4, 14].
    """
    validate_whole_number("buildup_weeks", buildup_weeks)
    if buildup_weeks < 0:
        msg = f"buildup_weeks must be non-negative, got {buildup_weeks!r}"
        raise ValueError(msg)
    if modality not in _TAPER_BASE_DAYS:
        msg = f"modality must be one of {sorted(_TAPER_BASE_DAYS)}, got {modality!r}"
        raise ValueError(msg)
    if event_priority not in ("A", "B", "C"):
        msg = f"event_priority must be A, B or C, got {event_priority!r}"
        raise ValueError(msg)
    days = _TAPER_BASE_DAYS[modality]
    if buildup_weeks < _SHORT_BUILDUP_WEEKS:
        days -= _SHORT_BUILDUP_PENALTY_DAYS
    if event_priority == "B":
        days = round(days * 0.5)
    return max(TAPER_MIN_DAYS, min(TAPER_MAX_DAYS, days))


def _taper_weeks(taper_days: int) -> int:
    return max(1, math.ceil(taper_days / _DAYS_PER_WEEK))


def _development_segment(
    start: int, end: int, *, compromise: bool, anchor: str, min_block_weeks: int
) -> SeasonSegment:
    span = end - start + 1
    if compromise:
        return SeasonSegment(
            start,
            end,
            "maintenance",
            anchor,
            f"maintenance bridge: A events <{min_block_weeks} weeks apart (compromise)",
        )
    if span >= MIN_BLOCK_WEEKS:
        return SeasonSegment(start, end, "block", anchor, f"block development ({span} weeks)")
    return SeasonSegment(
        start, end, "waves", anchor, f"wave development ({span} weeks, <{MIN_BLOCK_WEEKS})"
    )


def _validate_events(events: list[SeasonEvent], horizon_weeks: int) -> None:
    for event in events:
        validate_whole_number("event.week", event.week)
        if event.week < 1:
            msg = f"event {event.event_id!r} falls before the plan start (week {event.week})"
            raise ValueError(msg)
        if event.week > horizon_weeks:
            msg = (
                f"event {event.event_id!r} at week {event.week} is beyond the "
                f"{horizon_weeks}-week horizon"
            )
            raise ValueError(msg)


def plan_season(
    events: list[SeasonEvent],
    horizon_weeks: int,
    modality: SeasonModality = "mixed",
    min_block_weeks: int = MIN_BLOCK_WEEKS,
) -> list[SeasonSegment]:
    """Tile weeks 1..horizon_weeks into phase segments, backward from A events.

    Each A-priority event reserves a taper immediately before it and a
    competition week; the gaps fill with block (>= 6 weeks) or waves (shorter)
    development. Two A events closer than min_block_weeks yield a maintenance
    bridge flagged as a compromise. With no A event, the whole horizon is one
    development segment. Segments tile the horizon with no gaps or overlaps.
    """
    validate_whole_number("horizon_weeks", horizon_weeks)
    validate_whole_number("min_block_weeks", min_block_weeks)
    if horizon_weeks < 1:
        msg = f"horizon_weeks must be >= 1, got {horizon_weeks!r}"
        raise ValueError(msg)
    if min_block_weeks < 1:
        msg = f"min_block_weeks must be >= 1, got {min_block_weeks!r}"
        raise ValueError(msg)
    _validate_events(events, horizon_weeks)
    a_events = sorted((e for e in events if e.priority == "A"), key=lambda e: e.week)
    if not a_events:
        phase: SegmentPhase = "block" if horizon_weeks >= MIN_BLOCK_WEEKS else "waves"
        return [
            SeasonSegment(
                1, horizon_weeks, phase, None, "no A-priority event; open-ended development"
            )
        ]
    segments: list[SeasonSegment] = []
    cursor = 1
    for index, event in enumerate(a_events):
        if event.week < cursor:
            continue  # duplicate/adjacent A already inside the previous arc
        apart = event.week - a_events[index - 1].week if index else None
        compromise = apart is not None and apart < min_block_weeks
        segments.extend(
            _arc_segments(
                event, cursor, modality, compromise=compromise, min_block_weeks=min_block_weeks
            )
        )
        cursor = event.week + 1
    if cursor <= horizon_weeks:
        segments.append(
            SeasonSegment(cursor, horizon_weeks, "transition", None, "post-competition transition")
        )
    return segments


def _arc_segments(
    event: SeasonEvent,
    cursor: int,
    modality: SeasonModality,
    *,
    compromise: bool,
    min_block_weeks: int,
) -> list[SeasonSegment]:
    """Development + taper + competition segments for one A event, from cursor."""
    taper_days = recommend_taper_length(event.week - cursor, modality, "A")
    taper_start = max(cursor, event.week - _taper_weeks(taper_days))
    arc: list[SeasonSegment] = []
    if taper_start - 1 >= cursor:
        arc.append(
            _development_segment(
                cursor,
                taper_start - 1,
                compromise=compromise,
                anchor=event.event_id,
                min_block_weeks=min_block_weeks,
            )
        )
    if taper_start <= event.week - 1:
        arc.append(
            SeasonSegment(
                taper_start,
                event.week - 1,
                "taper",
                event.event_id,
                f"{taper_days}-day taper into A event {event.event_id}",
            )
        )
    comp_note = f"A event {event.event_id}"
    if compromise:
        comp_note += f" (compromise: <{min_block_weeks} weeks since previous A)"
    arc.append(SeasonSegment(event.week, event.week, "competition", event.event_id, comp_note))
    return arc
