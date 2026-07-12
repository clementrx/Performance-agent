"""Turn a parsed activity file into a session the athlete confirms before logging.

This layer reads the athlete directory (active program, profile, history) to
match the activity against a planned session, estimate session-RPE from heart
rate, and run the data-quality guards. It PROPOSES only — nothing is written
here; the caller logs the confirmed entry through the store.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from performance_agent.engine import estimate_srpe_from_hr
from performance_agent.importers.activity import (
    HrvReading,
    ParsedActivity,
    looks_like_hrv_csv,
    parse_activity_file,
    parse_hrv_csv,
)
from performance_agent.memory import monitoring, store
from performance_agent.memory.monitoring import PlausibilityFlag
from performance_agent.memory.schemas import Profile, ProgramPlan, SessionEntry, SessionPlan

# Team-chosen priors (no cohort tuning):
_MATCH_TOLERANCE = 0.20  # mean relative duration/distance error to accept a plan match
_WEEKDAY_BONUS = 0.5  # multiply the error when the planned weekday matches the activity's
_AGE_PREDICTED_HR_MAX_ANCHOR = 220  # Fox age-predicted HRmax = 220 - age; rough population prior
_HR_MAX_MIN = 100
_HR_MAX_MAX = 230
_MAX_LOGGABLE_HR = 230  # SessionEntry.avg_hr bound
_SECONDS_PER_MINUTE = 60.0
_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class SessionProposal:
    """A proposed SessionEntry plus how it was matched and what to confirm."""

    entry: SessionEntry
    source: Literal["programmed", "external"]
    session_plan_id: str | None
    rationale: str
    srpe_estimated: bool
    needs_srpe: bool
    flags: list[PlausibilityFlag] = field(default_factory=list)


@dataclass(frozen=True)
class ImportProposal:
    """The full import proposal: either a session or a batch of HRV readings."""

    kind: Literal["activity", "hrv"]
    activity: ParsedActivity | None = None
    session: SessionProposal | None = None
    hrv_readings: list[HrvReading] = field(default_factory=list)


def propose_import(base_dir: Path, path: Path, today: date | None = None) -> ImportProposal:
    """Parse a file and build a confirmable proposal (never writes anything).

    A .csv that carries HRV but no activity columns becomes an HRV proposal
    (dated rMSSD readings for readiness.jsonl); everything else becomes a
    session proposal matched against the active program.
    """
    if path.suffix.casefold() == ".csv" and looks_like_hrv_csv(path):
        return ImportProposal(kind="hrv", hrv_readings=parse_hrv_csv(path))
    activity = parse_activity_file(path)
    session = _propose_session(base_dir, activity, today)
    return ImportProposal(kind="activity", activity=activity, session=session)


def _propose_session(
    base_dir: Path, activity: ParsedActivity, today: date | None
) -> SessionProposal:
    profile = store.read_profile(base_dir)
    program = store.read_program(base_dir)
    plan = program.plan if program is not None else None
    duration_min = _duration_min(activity)
    avg_hr = activity.avg_hr if _is_loggable_hr(activity.avg_hr) else None
    srpe, needs_srpe = _propose_srpe(activity, profile, today)
    plan_id, source, rationale = _match(activity, plan, duration_min)
    entry = SessionEntry(
        performed_at=_performed_at(activity, today),
        kind=activity.sport or "imported_activity",
        rpe=srpe,
        duration_min=duration_min,
        source=source,
        session_plan_id=plan_id,
        avg_hr=avg_hr,
        notes=_notes(activity),
    )
    flags = monitoring.session_plausibility_flags(entry, store.read_sessions(base_dir), profile)
    return SessionProposal(
        entry=entry,
        source=source,
        session_plan_id=plan_id,
        rationale=rationale,
        srpe_estimated=srpe is not None and needs_srpe is False and avg_hr is not None,
        needs_srpe=needs_srpe,
        flags=flags,
    )


def _duration_min(activity: ParsedActivity) -> int | None:
    if activity.duration_s is None or activity.duration_s < _SECONDS_PER_MINUTE:
        return None
    return round(activity.duration_s / _SECONDS_PER_MINUTE)


def _is_loggable_hr(avg_hr: float | None) -> bool:
    return avg_hr is not None and 0 < avg_hr <= _MAX_LOGGABLE_HR


def _performed_at(activity: ParsedActivity, today: date | None) -> datetime:
    if activity.start_time is not None:
        return activity.start_time
    return datetime.combine(today or date.today(), time(12, 0))


def _notes(activity: ParsedActivity) -> str:
    parts = ["imported activity"]
    if activity.distance_m is not None:
        parts.append(f"distance {activity.distance_m / 1000:.2f} km")
    return "; ".join(parts)


def _propose_srpe(
    activity: ParsedActivity, profile: Profile, today: date | None
) -> tuple[int | None, bool]:
    """Return (estimated sRPE as int, needs_srpe). needs_srpe means ask the athlete."""
    avg_hr = activity.avg_hr
    if avg_hr is None or not 0 < avg_hr <= _MAX_LOGGABLE_HR:
        return None, True
    hr_max = _age_predicted_hr_max(profile, activity, today)
    if hr_max is None:
        return None, True
    return round(estimate_srpe_from_hr(avg_hr, hr_max)), False


def _age_predicted_hr_max(
    profile: Profile, activity: ParsedActivity, today: date | None
) -> float | None:
    if profile.birth_date is None:
        return None
    reference = (
        activity.start_time.date() if activity.start_time is not None else (today or date.today())
    )
    age_years = (reference - profile.birth_date).days / _DAYS_PER_YEAR
    hr_max = float(_AGE_PREDICTED_HR_MAX_ANCHOR) - age_years
    if not _HR_MAX_MIN <= hr_max <= _HR_MAX_MAX:
        return None
    return hr_max


def _match(
    activity: ParsedActivity, plan: ProgramPlan | None, duration_min: int | None
) -> tuple[str | None, Literal["programmed", "external"], str]:
    if plan is None:
        return None, "external", "no structured program active; logged as external load"
    weekday = activity.start_time.weekday() if activity.start_time is not None else None
    best_id: str | None = None
    best_err = float("inf")
    for session in _all_sessions(plan):
        err = _match_error(activity, duration_min, session, weekday)
        if err is not None and err < best_err:
            best_err = err
            best_id = session.id
    if best_id is not None and best_err <= _MATCH_TOLERANCE:
        return (
            best_id,
            "programmed",
            f"matched planned session '{best_id}' (relative error {best_err:.0%})",
        )
    return None, "external", "no planned session matched on duration/distance; external load"


def _all_sessions(plan: ProgramPlan) -> list[SessionPlan]:
    return [s for meso in plan.mesocycles for week in meso.weeks for s in week.sessions]


def _match_error(
    activity: ParsedActivity,
    duration_min: int | None,
    session: SessionPlan,
    weekday: int | None,
) -> float | None:
    errors: list[float] = []
    if duration_min is not None and session.est_minutes > 0:
        errors.append(abs(duration_min - session.est_minutes) / session.est_minutes)
    planned_distance = _planned_distance_m(session)
    if activity.distance_m is not None and planned_distance:
        errors.append(abs(activity.distance_m - planned_distance) / planned_distance)
    if not errors:
        return None
    error = sum(errors) / len(errors)
    if weekday is not None and session.weekday == weekday:
        error *= _WEEKDAY_BONUS
    return error


def _planned_distance_m(session: SessionPlan) -> float | None:
    distances = [block.distance_m for block in session.blocks if block.distance_m is not None]
    return sum(distances) if distances else None
