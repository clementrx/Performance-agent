"""Individual taper response at the athlete layer: loads, events, outcomes.

Builds a daily session-RPE load series from the log, competition events from the
calendar, and pairs each competition with an event-linked KPI outcome (normalized
so higher = better via the performance model's higher_is_better). Calls the pure
taper-response engine, and upgrades recommend_taper to return an individual
recommendation when >= 2 tapers carry outcomes, else the labeled population rule.
"""

from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

from performance_agent.engine.load import session_rpe_load
from performance_agent.engine.season import SeasonModality, recommend_taper_length
from performance_agent.engine.taper_response import TaperEvent, fit_taper_response
from performance_agent.memory import store

_OUTCOME_WINDOW_DAYS = 7  # a KPI result within this many days of an event is its outcome


def _loads_and_origin(base_dir: Path) -> tuple[list[float], date | None]:
    sessions = store.read_sessions(base_dir)
    events = store.read_calendar(base_dir).events
    dates = [s.performed_at.date() for s in sessions] + [e.date for e in events]
    if not dates:
        return [], None
    origin = min(dates)
    n_days = (max(dates) - origin).days + 1
    loads = [0.0] * n_days
    for entry in sessions:
        if entry.rpe is not None and entry.duration_min is not None:
            loads[(entry.performed_at.date() - origin).days] += session_rpe_load(
                entry.rpe, entry.duration_min
            )
    return loads, origin


def _higher_is_better(base_dir: Path) -> dict[str, bool]:
    model = store.read_performance_model(base_dir)
    return {kpi.id: kpi.higher_is_better for kpi in model.kpis} if model is not None else {}


def _event_outcome(base_dir: Path, event_date: date, direction: dict[str, bool]) -> float | None:
    """The event-linked KPI outcome (normalized higher = better), or None."""
    best: tuple[int, float] | None = None
    for result in store.read_kpi_results(base_dir):
        if result.kpi_id is None:
            continue
        distance = abs((result.date - event_date).days)
        if distance > _OUTCOME_WINDOW_DAYS:
            continue
        normalized = result.value if direction.get(result.kpi_id, True) else -result.value
        if best is None or distance < best[0]:
            best = (distance, normalized)
    return best[1] if best is not None else None


def _taper_events(base_dir: Path, origin: date) -> list[TaperEvent]:
    direction = _higher_is_better(base_dir)
    events: list[TaperEvent] = []
    for event in store.read_calendar(base_dir).events:
        if event.kind != "competition":
            continue
        events.append(
            TaperEvent(
                day_index=(event.date - origin).days,
                outcome=_event_outcome(base_dir, event.date, direction),
            )
        )
    return events


class TaperWindowView(TypedDict):
    """One detected historical taper with its outcome."""

    event_day: int
    duration_days: int
    reduction: float
    outcome: float | None


class TaperResponseView(TypedDict):
    """The fitted taper response: detected windows + basis + recommendation."""

    n_detected: int
    n_with_outcome: int
    windows: list[TaperWindowView]
    recommended_duration_days: int | None
    recommended_reduction: float | None
    basis: str
    note: str


def fit_taper_response_view(base_dir: Path, generic_duration_days: int) -> TaperResponseView:
    """Detect the athlete's historical tapers and summarize with a recommendation."""
    loads, origin = _loads_and_origin(base_dir)
    events = _taper_events(base_dir, origin) if origin is not None else []
    response = fit_taper_response(loads, events, generic_duration_days)
    return TaperResponseView(
        n_detected=response.n_detected,
        n_with_outcome=response.n_with_outcome,
        windows=[
            TaperWindowView(
                event_day=w.event_day,
                duration_days=w.duration_days,
                reduction=w.reduction,
                outcome=w.outcome,
            )
            for w in response.windows
        ],
        recommended_duration_days=response.recommended_duration_days,
        recommended_reduction=response.recommended_reduction,
        basis=response.basis,
        note=response.note,
    )


class TaperRecommendationView(TypedDict):
    """A taper length recommendation with its basis (individual vs population)."""

    taper_days: int
    basis: str
    population_days: int
    note: str


def recommend_taper(
    base_dir: Path,
    buildup_weeks: int,
    modality: SeasonModality,
    event_priority: Literal["A", "B", "C"],
) -> TaperRecommendationView:
    """Recommend a taper length, consulting the athlete's fitted taper response.

    Computes the generic population taper, then checks the fitted response: with
    >= 2 historical tapers carrying outcomes it returns the individual best-outcome
    duration (basis="individual"); otherwise the population rule (basis="population").
    """
    population_days = recommend_taper_length(buildup_weeks, modality, event_priority)
    response = fit_taper_response_view(base_dir, population_days)
    if response["basis"] == "individual" and response["recommended_duration_days"] is not None:
        return TaperRecommendationView(
            taper_days=response["recommended_duration_days"],
            basis="individual",
            population_days=population_days,
            note=response["note"],
        )
    return TaperRecommendationView(
        taper_days=population_days,
        basis="population",
        population_days=population_days,
        note=response["note"],
    )
