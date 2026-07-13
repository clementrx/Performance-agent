"""Individual response modelling: pure, descriptive, and honest about n.

Every function here distils the athlete's OWN logged history into a trend and
REFUSES to guess when the data is too thin: progression_rate returns None below
six points or a four-week span, volume_tolerance returns None below eight weeks
and reports association direction only (never a causal claim). No fabricated
rate is ever returned in place of missing data.

The module is datetime-free and pydantic-free (engine purity): it works on
engine-local dataclasses of plain numbers. The memory layer converts the
athlete's ProgramPlan / sessions.jsonl / readiness.jsonl into these inputs,
supplies the day indices (days from the series start) and the implausible-entry
exclusion flag, and maps the results back onto dates.
"""

import math
from dataclasses import dataclass, field
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number
from performance_agent.engine.strength import MAX_ESTIMATION_REPS, one_rm_epley

_DAYS_PER_WEEK = 7.0
# Honesty-about-n thresholds (team-chosen priors): a weekly progression rate
# needs at least this many points spanning at least this many weeks before it
# beats the population prior; below either, the rate is None, never guessed.
MIN_PROGRESSION_POINTS = 6
MIN_PROGRESSION_SPAN_WEEKS = 4.0
# Volume-tolerance association needs at least this many weekly observations, and
# calls a direction only when the correlation clears this magnitude (team priors).
MIN_TOLERANCE_WEEKS = 8
TOLERANCE_CORRELATION_THRESHOLD = 0.3
# A logged e1RM more than this fraction above the running best of earlier points
# is treated as data-entry noise and excluded (mirrors load.py's guard).
_MAX_E1RM_JUMP_FRACTION = 0.15

DONE_VOLUME_FRACTION = 0.9  # performed sets >= this share of prescribed = "done"

Compliance = Literal["done", "partial", "modified", "missed"]
MatchedBy = Literal["id", "weekday_quality", "none"]


@dataclass(frozen=True)
class SessionSets:
    """One session's scored sets for a single lift, in day space.

    day_index is whole days from the first session in the series; sets are
    (load_kg, reps) pairs; excluded marks an entry the memory layer flagged as
    implausible and not athlete-confirmed (dropped from the timeline).
    """

    day_index: int
    sets: tuple[tuple[float, int], ...]
    excluded: bool = False


@dataclass(frozen=True)
class TimelinePoint:
    """One dated best-effort estimated 1RM (day_index = days from series start)."""

    day_index: int
    e1rm: float


@dataclass(frozen=True)
class ProgressionRate:
    """A fitted weekly progression, with the sample size that produced it."""

    pct_per_week: float
    r2: float
    n: int
    span_weeks: float


def _best_e1rm(sets: tuple[tuple[float, int], ...]) -> float | None:
    """Best Epley e1RM across an exercise's scorable sets (1-12 reps), or None."""
    estimates = [
        one_rm_epley(load, reps)
        for load, reps in sets
        if load > 0 and 1 <= reps <= MAX_ESTIMATION_REPS
    ]
    return max(estimates) if estimates else None


def e1rm_timeline(sessions: list[SessionSets]) -> list[TimelinePoint]:
    """Best estimated 1RM per session over time, excluding flagged entries.

    One point per session that has a scorable set and is not excluded; the
    best set of the session (highest Epley e1RM) is the day's value. Points are
    returned sorted by day_index. A session with no scorable set contributes no
    point (silence, not a zero).
    """
    points: list[TimelinePoint] = []
    for session in sessions:
        if session.excluded:
            continue
        best = _best_e1rm(session.sets)
        if best is not None:
            points.append(TimelinePoint(session.day_index, best))
    return sorted(points, key=lambda p: p.day_index)


def _least_squares(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Return (slope, intercept, r2) for y ~ slope*x + intercept."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = 1.0 if ss_tot == 0 else max(0.0, 1 - ss_res / ss_tot)
    return slope, intercept, r2


def progression_rate(
    timeline: list[TimelinePoint],
    min_points: int = MIN_PROGRESSION_POINTS,
    min_span_weeks: float = MIN_PROGRESSION_SPAN_WEEKS,
) -> ProgressionRate | None:
    """Fit a weekly progression rate to an e1RM timeline, or None when too thin.

    Returns None (never a fabricated rate) when fewer than min_points points or
    the span is below min_span_weeks. pct_per_week is the least-squares slope
    expressed as a fraction of the fitted value at the first point (so it is
    comparable to the population per-week rates); r2 reports the fit quality and
    n the point count. All points sharing one day (zero span) also yield None.
    """
    validate_whole_number("min_points", min_points)
    if len(timeline) < min_points:
        return None
    xs = [p.day_index / _DAYS_PER_WEEK for p in timeline]
    ys = [p.e1rm for p in timeline]
    span_weeks = max(xs) - min(xs)
    if span_weeks < min_span_weeks:
        return None
    slope, intercept, r2 = _least_squares(xs, ys)
    base = intercept + slope * min(xs)
    if base <= 0:
        return None
    return ProgressionRate(pct_per_week=slope / base, r2=r2, n=len(timeline), span_weeks=span_weeks)


@dataclass(frozen=True)
class PlannedSession:
    """One planned session's compliance-relevant facts (week/day/quality/volume)."""

    session_id: str
    week_index: int
    weekday: int | None
    quality: str
    prescribed_sets: int


@dataclass(frozen=True)
class LoggedSession:
    """One logged session reduced to what compliance matching needs."""

    session_plan_id: str | None
    week_index: int
    weekday: int | None
    quality: str | None
    performed_sets: int


@dataclass(frozen=True)
class SessionCompliance:
    """How one planned session fared against the log."""

    session_id: str
    quality: str
    status: Compliance
    matched_by: MatchedBy


@dataclass(frozen=True)
class WeeklyVolume:
    """Prescribed vs performed hard sets for one program week."""

    week_index: int
    prescribed_sets: int
    performed_sets: int


@dataclass(frozen=True)
class ComplianceReport:
    """Per-session compliance, weekly volume, and count of unplanned sessions."""

    sessions: tuple[SessionCompliance, ...]
    weekly_volume: tuple[WeeklyVolume, ...]
    extra_unplanned: int


def _classify(planned: PlannedSession, logged: LoggedSession, matched_by: MatchedBy) -> Compliance:
    if logged.quality is not None and logged.quality != planned.quality:
        return "modified"
    if matched_by == "weekday_quality":
        return "modified"
    if planned.prescribed_sets > 0 and (
        logged.performed_sets >= planned.prescribed_sets * DONE_VOLUME_FRACTION
    ):
        return "done"
    if logged.performed_sets > 0:
        return "partial"
    return "missed"


def _match(
    planned: PlannedSession, logged: list[LoggedSession], used: set[int]
) -> tuple[int, MatchedBy] | None:
    for index, entry in enumerate(logged):
        if index in used or entry.session_plan_id != planned.session_id:
            continue
        return index, "id"
    for index, entry in enumerate(logged):
        if index in used or entry.session_plan_id is not None:
            continue
        if (
            entry.week_index == planned.week_index
            and entry.weekday == planned.weekday
            and entry.weekday is not None
            and entry.quality == planned.quality
        ):
            return index, "weekday_quality"
    return None


def compare_prescribed_actual(
    planned: list[PlannedSession], logged: list[LoggedSession]
) -> ComplianceReport:
    """Match logged sessions to planned ones and score each for compliance.

    Matches on session_plan_id first, then falls back to same week + weekday +
    quality. Each planned session is done (>=90% of prescribed sets, right
    quality), partial (some but fewer sets), modified (matched only by the
    fallback or a different quality), or missed (no match). Weekly volume sums
    prescribed vs performed sets; extra_unplanned counts logged sessions that
    matched nothing.
    """
    used: set[int] = set()
    results: list[SessionCompliance] = []
    for planned_session in planned:
        matched = _match(planned_session, logged, used)
        if matched is None:
            results.append(
                SessionCompliance(
                    planned_session.session_id, planned_session.quality, "missed", "none"
                )
            )
            continue
        index, matched_by = matched
        used.add(index)
        status = _classify(planned_session, logged[index], matched_by)
        results.append(
            SessionCompliance(
                planned_session.session_id, planned_session.quality, status, matched_by
            )
        )
    weekly = _weekly_volume(planned, logged, used)
    extra = sum(1 for index in range(len(logged)) if index not in used)
    return ComplianceReport(tuple(results), weekly, extra)


def _weekly_volume(
    planned: list[PlannedSession], logged: list[LoggedSession], used: set[int]
) -> tuple[WeeklyVolume, ...]:
    prescribed: dict[int, int] = {}
    performed: dict[int, int] = {}
    for session in planned:
        prescribed[session.week_index] = (
            prescribed.get(session.week_index, 0) + session.prescribed_sets
        )
    for index, entry in enumerate(logged):
        if index in used:
            performed[entry.week_index] = performed.get(entry.week_index, 0) + entry.performed_sets
    weeks = sorted(set(prescribed) | set(performed))
    return tuple(
        WeeklyVolume(week, prescribed.get(week, 0), performed.get(week, 0)) for week in weeks
    )


@dataclass(frozen=True)
class AdherenceByQuality:
    """Compliance rolled up for one quality tag."""

    quality: str
    done: int
    partial: int
    modified: int
    missed: int
    adherence_pct: float


def adherence_stats(report: ComplianceReport) -> list[AdherenceByQuality]:
    """Roll session compliance up by quality tag (done+partial as adherence).

    adherence_pct counts done and partial sessions as adhered, over all planned
    sessions of that quality. Qualities are returned in sorted order.
    """
    buckets: dict[str, dict[str, int]] = {}
    for session in report.sessions:
        bucket = buckets.setdefault(
            session.quality, {"done": 0, "partial": 0, "modified": 0, "missed": 0}
        )
        bucket[session.status] += 1
    stats: list[AdherenceByQuality] = []
    for quality in sorted(buckets):
        counts = buckets[quality]
        total = sum(counts.values())
        adhered = counts["done"] + counts["partial"]
        pct = 100.0 * adhered / total if total else 0.0
        stats.append(
            AdherenceByQuality(
                quality,
                counts["done"],
                counts["partial"],
                counts["modified"],
                counts["missed"],
                pct,
            )
        )
    return stats


ToleranceDirection = Literal[
    "higher_volume_higher_fatigue", "higher_volume_lower_fatigue", "no_clear_direction"
]


@dataclass(frozen=True)
class VolumeTolerance:
    """A DESCRIPTIVE association between weekly volume and a fatigue trend.

    correlation is Pearson's r between weekly hard sets and the weekly fatigue
    metric; direction names its sign only when |r| clears the threshold. This is
    association, never causation, and the memory layer must narrate it that way.
    """

    direction: ToleranceDirection
    correlation: float
    n_weeks: int


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def volume_tolerance(
    weekly_hard_sets: list[float],
    weekly_fatigue: list[float],
    min_weeks: int = MIN_TOLERANCE_WEEKS,
) -> VolumeTolerance | None:
    """Associate weekly hard sets with a weekly fatigue trend (direction only).

    weekly_fatigue is a per-week fatigue-style metric where HIGHER means MORE
    fatigued (e.g. mean Hooper fatigue, or 100 - readiness). Returns None (never
    a guess) below min_weeks aligned observations or when either series is flat.
    Reports Pearson's r and its sign as a direction; the magnitude must clear
    TOLERANCE_CORRELATION_THRESHOLD to be called anything but no_clear_direction.
    Association only — never a causal claim.
    """
    validate_whole_number("min_weeks", min_weeks)
    if len(weekly_hard_sets) != len(weekly_fatigue):
        msg = "weekly_hard_sets and weekly_fatigue must be the same length (one value per week)"
        raise ValueError(msg)
    for value in (*weekly_hard_sets, *weekly_fatigue):
        validate_finite("weekly value", value)
    if len(weekly_hard_sets) < min_weeks:
        return None
    r = _pearson(weekly_hard_sets, weekly_fatigue)
    if r is None:
        return None
    if r >= TOLERANCE_CORRELATION_THRESHOLD:
        direction: ToleranceDirection = "higher_volume_higher_fatigue"
    elif r <= -TOLERANCE_CORRELATION_THRESHOLD:
        direction = "higher_volume_lower_fatigue"
    else:
        direction = "no_clear_direction"
    return VolumeTolerance(direction=direction, correlation=r, n_weeks=len(weekly_hard_sets))


@dataclass(frozen=True)
class ResponseProfileData:
    """Pure numeric assembly of a response profile (memory adds dates + storage)."""

    per_lift_rates: dict[str, ProgressionRate]
    goal_measured_rate: ProgressionRate | None
    volume_tolerance: VolumeTolerance | None
    adherence_by_quality: list[AdherenceByQuality]
    caveats: list[str] = field(default_factory=list)


def build_response_profile(
    per_lift_rates: dict[str, ProgressionRate],
    goal_measured_rate: ProgressionRate | None,
    tolerance: VolumeTolerance | None,
    adherence: list[AdherenceByQuality],
) -> ResponseProfileData:
    """Assemble computed pieces into a ResponseProfileData, recording honesty caveats.

    Caveats are appended for each thin or absent signal (no measured rate, small
    n on the goal rate, no tolerance association) so the narrator can never
    present a thin number as if it were solid.
    """
    caveats: list[str] = []
    if goal_measured_rate is None:
        caveats.append(
            "no measured progression rate yet: insufficient data, using population prior"
        )
    elif goal_measured_rate.n < MIN_PROGRESSION_POINTS + 2:
        caveats.append(
            f"measured rate from only {goal_measured_rate.n} points "
            f"({goal_measured_rate.span_weeks:.0f} weeks): treat as provisional"
        )
    if tolerance is None:
        caveats.append("volume tolerance not yet estimable: needs 8+ weeks of aligned data")
    elif tolerance.direction == "no_clear_direction":
        caveats.append("no clear volume/fatigue association: keep population volume landmarks")
    return ResponseProfileData(
        per_lift_rates=per_lift_rates,
        goal_measured_rate=goal_measured_rate,
        volume_tolerance=tolerance,
        adherence_by_quality=adherence,
        caveats=caveats,
    )
