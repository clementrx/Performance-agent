"""Descriptive report annexes computed from already-stored athlete data.

Each section is built from what the athlete has saved (calendar, program plan,
session log, response profile) and quotes DESCRIPTIVE numbers straight from the
real engine functions — never a fabricated or predicted value. A section returns
None when its data does not exist, so the report skips it gracefully. Rendering
these dataclasses to Typst lives in reports/source.py; the free-text they carry
is fed back through the citation gate in reports/renderer.py.
"""

from dataclasses import dataclass
from datetime import timedelta

from performance_agent.engine.load import (
    fitness_fatigue_series,
    session_rpe_load,
    weekly_monotony,
    weekly_strain,
)
from performance_agent.memory.schemas import (
    Calendar,
    ProgramPlan,
    ResponseProfile,
    SessionEntry,
)

_LAST_WEEK_DAYS = 7


@dataclass(frozen=True)
class SeasonEventRow:
    """One dated calendar event, ready to print."""

    date: str
    priority: str
    label: str


@dataclass(frozen=True)
class PhaseSpan:
    """One mesocycle phase and the global week range it covers."""

    phase: str
    start_week: int
    end_week: int


@dataclass(frozen=True)
class SeasonOverview:
    """The season snapshot: events, phase timeline, taper and test weeks."""

    season_ref: str | None
    events: list[SeasonEventRow]
    phases: list[PhaseSpan]
    taper_weeks: list[int]
    test_weeks: list[int]


@dataclass(frozen=True)
class LoadTrends:
    """Last-week load, monotony/strain and the CTL/ATL/TSB tail (all descriptive)."""

    last_week_total: float
    external_share: float
    monotony: float | None
    strain: float | None
    ctl: float
    atl: float
    tsb: float
    days_of_history: int


@dataclass(frozen=True)
class RateRow:
    """A measured weekly rate with the sample size that backs it."""

    label: str
    pct_per_week: float
    n: int
    window_weeks: float
    r2: float


@dataclass(frozen=True)
class AdherenceRow:
    """Compliance rolled up for one quality tag."""

    quality: str
    adherence_pct: float
    done: int
    partial: int
    modified: int
    missed: int


@dataclass(frozen=True)
class ToleranceRow:
    """A descriptive volume/fatigue association (never causal)."""

    direction: str
    correlation: float
    n_weeks: int


@dataclass(frozen=True)
class QualityRateRow:
    """A measured per-quality weekly rate, keyed to its KPI, with its sample size."""

    quality: str
    kpi_id: str
    pct_per_week: float
    n: int
    window_weeks: float
    r2: float


@dataclass(frozen=True)
class BanisterRow:
    """The fitted Banister summary: params, fit quality, and usability verdict."""

    usable: bool
    tau1: float
    tau2: float
    k1: float
    k2: float
    r2: float
    k1_ci_half: float
    k2_ci_half: float
    n_load_days: int
    n_performance_points: int


@dataclass(frozen=True)
class ResponseSummary:
    """Measured-vs-prior response, adherence and the profile's caveats verbatim."""

    goal_rate: RateRow | None
    lift_rates: list[RateRow]
    quality_rates: list[QualityRateRow]
    adherence: list[AdherenceRow]
    tolerance: list[ToleranceRow]
    banister: BanisterRow | None
    caveats: list[str]


def _phase_spans(plan: ProgramPlan) -> list[PhaseSpan]:
    spans: list[PhaseSpan] = []
    for meso in plan.mesocycles:
        weeks = [week.week_index for week in meso.weeks]
        spans.append(PhaseSpan(phase=meso.phase, start_week=min(weeks), end_week=max(weeks)))
    return spans


def _taper_weeks(plan: ProgramPlan) -> list[int]:
    weeks: set[int] = set()
    for meso in plan.mesocycles:
        for week in meso.weeks:
            if meso.phase == "taper" or week.is_taper:
                weeks.add(week.week_index)
    return sorted(weeks)


def build_season_overview(calendar: Calendar, plan: ProgramPlan | None) -> SeasonOverview | None:
    """Assemble the season snapshot from the calendar and the saved plan.

    Reads what the program already encodes rather than re-planning a fresh
    season, so the report stays deterministic. Returns None when neither dated
    events nor a season reference nor test milestones exist.
    """
    events = [
        SeasonEventRow(date=event.date.isoformat(), priority=event.priority, label=event.label)
        for event in calendar.events
    ]
    has_plan_season = plan is not None and bool(plan.season_ref or plan.test_milestones)
    if not events and not has_plan_season:
        return None
    return SeasonOverview(
        season_ref=plan.season_ref if plan is not None else None,
        events=events,
        phases=_phase_spans(plan) if plan is not None else [],
        taper_weeks=_taper_weeks(plan) if plan is not None else [],
        test_weeks=sorted({m.week_index for m in plan.test_milestones}) if plan is not None else [],
    )


def _daily_load_maps(
    sessions: list[SessionEntry],
) -> tuple[dict[object, float], dict[object, float]]:
    """Sum session-RPE load per calendar day, splitting out external-source load."""
    total: dict[object, float] = {}
    external: dict[object, float] = {}
    for entry in sessions:
        if entry.rpe is None or entry.duration_min is None:
            continue
        load = session_rpe_load(entry.rpe, entry.duration_min)
        day = entry.performed_at.date()
        total[day] = total.get(day, 0.0) + load
        if entry.source == "external":
            external[day] = external.get(day, 0.0) + load
    return total, external


def build_load_trends(sessions: list[SessionEntry]) -> LoadTrends | None:
    """Quote the descriptive load trend from the session log via the engine.

    Builds the daily session-RPE series (rest days = 0), then reads last-week
    total load with its external share, Foster's monotony/strain over the last 7
    days, and the CTL/ATL/TSB tail from the fitness-fatigue series. Returns None
    when no session carries both an RPE and a duration to score.
    """
    total, external = _daily_load_maps(sessions)
    if not total:
        return None
    first_day = min(total)
    last_day = max(total)
    span_days = (last_day - first_day).days
    full_series = [
        total.get(first_day + timedelta(days=offset), 0.0) for offset in range(span_days + 1)
    ]
    week_start = last_day - timedelta(days=_LAST_WEEK_DAYS - 1)
    last7 = [
        total.get(week_start + timedelta(days=offset), 0.0) for offset in range(_LAST_WEEK_DAYS)
    ]
    last7_external = sum(
        external.get(week_start + timedelta(days=offset), 0.0) for offset in range(_LAST_WEEK_DAYS)
    )
    last_week_total = sum(last7)
    share = last7_external / last_week_total if last_week_total > 0 else 0.0
    tail = fitness_fatigue_series(full_series)[-1]
    return LoadTrends(
        last_week_total=last_week_total,
        external_share=share,
        monotony=weekly_monotony(last7),
        strain=weekly_strain(last7),
        ctl=tail.ctl,
        atl=tail.atl,
        tsb=tail.tsb,
        days_of_history=len(full_series),
    )


def build_response_summary(profile: ResponseProfile, goal_label: str | None) -> ResponseSummary:
    """Fold the latest response profile into printable rows, caveats verbatim."""
    measured = profile.per_goal_measured_rate
    goal_rate = (
        RateRow(
            label=goal_label or profile.goal_id or "goal",
            pct_per_week=measured.value,
            n=measured.n,
            window_weeks=measured.window_weeks,
            r2=measured.r2,
        )
        if measured is not None
        else None
    )
    lift_rates = [
        RateRow(
            label=rate.lift,
            pct_per_week=rate.pct_per_week,
            n=rate.n,
            window_weeks=rate.window_weeks,
            r2=rate.r2,
        )
        for rate in profile.per_lift_rates
    ]
    adherence = [
        AdherenceRow(
            quality=item.quality,
            adherence_pct=item.adherence_pct,
            done=item.done,
            partial=item.partial,
            modified=item.modified,
            missed=item.missed,
        )
        for item in profile.adherence_by_quality
    ]
    tolerance = [
        ToleranceRow(direction=flag.direction, correlation=flag.correlation, n_weeks=flag.n_weeks)
        for flag in profile.volume_tolerance_flags
    ]
    quality_rates = [
        QualityRateRow(
            quality=rate.quality,
            kpi_id=rate.kpi_id,
            pct_per_week=rate.pct_per_week,
            n=rate.n,
            window_weeks=rate.window_weeks,
            r2=rate.r2,
        )
        for rate in profile.per_quality_rates
    ]
    fit = profile.banister
    banister = (
        BanisterRow(
            usable=fit.usable,
            tau1=fit.tau1,
            tau2=fit.tau2,
            k1=fit.k1,
            k2=fit.k2,
            r2=fit.r2,
            k1_ci_half=fit.k1_ci_half,
            k2_ci_half=fit.k2_ci_half,
            n_load_days=fit.n_load_days,
            n_performance_points=fit.n_performance_points,
        )
        if fit is not None
        else None
    )
    return ResponseSummary(
        goal_rate=goal_rate,
        lift_rates=lift_rates,
        quality_rates=quality_rates,
        adherence=adherence,
        tolerance=tolerance,
        banister=banister,
        caveats=list(profile.caveats),
    )


def collect_prose(
    season: SeasonOverview | None,
    response: ResponseSummary | None,
) -> str:
    """Concatenate the free-text a section prints, for the citation gate.

    Only athlete/agent-authored strings can smuggle a reference locator; the
    engine-derived numbers cannot. Season/response prose is gathered so the
    renderer can run find_unknown_references over it alongside the program body.
    """
    prose: list[str] = []
    if season is not None:
        if season.season_ref:
            prose.append(season.season_ref)
        prose.extend(event.label for event in season.events)
    if response is not None:
        if response.goal_rate is not None:
            prose.append(response.goal_rate.label)
        prose.extend(rate.label for rate in response.lift_rates)
        prose.extend(response.caveats)
    return "\n".join(prose)
