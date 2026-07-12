"""Season planning at the athlete layer: date <-> week conversion + engine call.

The engine (engine/season.py) is datetime-free and works in integer week space;
this module reads the calendar, converts real dates into weeks from the plan
start, calls the pure planner, and maps the segments back onto dates. B/C events
are surfaced separately for the skill to treat (mini-taper / train-through).
"""

from datetime import date, timedelta
from pathlib import Path
from typing import TypedDict

from performance_agent.engine.season import (
    SeasonEvent,
    SeasonModality,
    plan_season,
)
from performance_agent.memory import store

_DEFAULT_OPEN_HORIZON_WEEKS = 12
_DAYS_PER_WEEK = 7


class SegmentView(TypedDict):
    """One planned segment with both week indices and calendar dates."""

    start_week: int
    end_week: int
    start_date: str
    end_date: str
    phase_type: str
    anchor_event_id: str | None
    rationale: str


class SecondaryEventView(TypedDict):
    """A B/C event surfaced for the skill (no full taper is planned for these)."""

    event_id: str
    date: str
    priority: str
    weeks_out: int
    label: str


class SeasonPlanView(TypedDict):
    """The full backward-planned season, ready for the LLM to narrate."""

    start_date: str
    horizon_weeks: int
    modality: str
    segments: list[SegmentView]
    secondary_events: list[SecondaryEventView]


def _week_of(event_date: date, start: date) -> int:
    return (event_date - start).days // _DAYS_PER_WEEK + 1


def _segment_dates(start: date, start_week: int, end_week: int) -> tuple[str, str]:
    seg_start = start + timedelta(days=(start_week - 1) * _DAYS_PER_WEEK)
    seg_end = start + timedelta(days=end_week * _DAYS_PER_WEEK - 1)
    return seg_start.isoformat(), seg_end.isoformat()


def _horizon_weeks(base_dir: Path, start: date, event_weeks: list[int]) -> int:
    furthest = max(event_weeks, default=0)
    deadlines = [
        _week_of(goal.deadline, start)
        for goal in store.read_goals(base_dir)
        if goal.status == "active" and goal.deadline is not None
    ]
    furthest = max([furthest, *[w for w in deadlines if w >= 1]], default=0)
    return furthest if furthest >= 1 else _DEFAULT_OPEN_HORIZON_WEEKS


def build_season_plan(
    base_dir: Path, modality: SeasonModality = "mixed", today: date | None = None
) -> SeasonPlanView:
    """Read the calendar and plan the season backward from its dated events."""
    start = today or date.today()
    calendar = store.read_calendar(base_dir)
    engine_events = [
        SeasonEvent(
            event_id=event.id,
            week=_week_of(event.date, start),
            priority=event.priority,
            kind=event.kind,
        )
        for event in calendar.events
    ]
    horizon = _horizon_weeks(base_dir, start, [e.week for e in engine_events if e.week >= 1])
    segments = plan_season(engine_events, horizon, modality=modality)
    segment_views: list[SegmentView] = []
    for seg in segments:
        seg_start, seg_end = _segment_dates(start, seg.start_week, seg.end_week)
        segment_views.append(
            SegmentView(
                start_week=seg.start_week,
                end_week=seg.end_week,
                start_date=seg_start,
                end_date=seg_end,
                phase_type=seg.phase_type,
                anchor_event_id=seg.anchor_event_id,
                rationale=seg.rationale,
            )
        )
    secondary = [
        SecondaryEventView(
            event_id=event.id,
            date=event.date.isoformat(),
            priority=event.priority,
            weeks_out=_week_of(event.date, start),
            label=event.label,
        )
        for event in calendar.events
        if event.priority in ("B", "C") and event.date >= start
    ]
    return SeasonPlanView(
        start_date=start.isoformat(),
        horizon_weeks=horizon,
        modality=modality,
        segments=segment_views,
        secondary_events=secondary,
    )
