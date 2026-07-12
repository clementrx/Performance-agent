"""MCP tool for importing an activity file into a proposed session.

The tool PARSES and PROPOSES only. It never writes: it returns a proposed
SessionEntry (and, for an HRV CSV, proposed readiness readings) for the LLM to
confirm with the athlete, who then logs it through log_session / log_readiness.
Malformed files raise a readable error instead of crashing.
"""

from pathlib import Path
from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.importers.activity import HrvReading, ParsedActivity
from performance_agent.importers.proposal import SessionProposal, propose_import
from performance_agent.memory.monitoring import PlausibilityFlag
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import SessionEntry

_CONFIRM = (
    "Proposal only — nothing is logged yet. Confirm the values with the athlete "
    "(especially any flags and, when needs_srpe is true, the session RPE), then call "
    "log_session for the session, or log_readiness for each HRV reading once the four "
    "Hooper items are collected."
)


class MatchView(TypedDict):
    """How the imported activity was matched to the program."""

    source: str
    session_plan_id: str | None
    rationale: str


class ActivitySummaryView(TypedDict):
    """The raw values parsed from the file, before matching or estimation."""

    sport: str | None
    start_time: str | None
    duration_min: int | None
    distance_m: float | None
    avg_hr: float | None


class HrvReadingView(TypedDict):
    """One proposed HRV reading; needs the four Hooper items before log_readiness."""

    at: str
    hrv_ms: float


class ActivityImportProposal(TypedDict):
    """A confirmable import proposal (kind='activity' or 'hrv'). Nothing is written.

    For kind='activity', proposed_session is a SessionEntry to confirm and log;
    srpe_estimated tells whether the RPE was estimated from heart rate and
    needs_srpe whether the athlete must supply it. For kind='hrv',
    proposed_readiness lists dated rMSSD values to attach Hooper items to.
    """

    kind: str
    confirm: str
    proposed_session: SessionEntry | None
    match: MatchView | None
    srpe_estimated: bool
    needs_srpe: bool
    flags: list[PlausibilityFlag]
    proposed_readiness: list[HrvReadingView]
    summary: ActivitySummaryView | None


def _summary(activity: ParsedActivity, session: SessionEntry) -> ActivitySummaryView:
    return ActivitySummaryView(
        sport=activity.sport,
        start_time=activity.start_time.isoformat() if activity.start_time else None,
        duration_min=session.duration_min,
        distance_m=activity.distance_m,
        avg_hr=activity.avg_hr,
    )


def _reading_view(reading: HrvReading) -> HrvReadingView:
    return HrvReadingView(at=reading.at.isoformat(), hrv_ms=reading.hrv_ms)


def _activity_proposal(
    activity: ParsedActivity, session: SessionProposal
) -> ActivityImportProposal:
    return ActivityImportProposal(
        kind="activity",
        confirm=_CONFIRM,
        proposed_session=session.entry,
        match=MatchView(
            source=session.source,
            session_plan_id=session.session_plan_id,
            rationale=session.rationale,
        ),
        srpe_estimated=session.srpe_estimated,
        needs_srpe=session.needs_srpe,
        flags=session.flags,
        proposed_readiness=[],
        summary=_summary(activity, session.entry),
    )


def _hrv_proposal(readings: list[HrvReading]) -> ActivityImportProposal:
    return ActivityImportProposal(
        kind="hrv",
        confirm=_CONFIRM,
        proposed_session=None,
        match=None,
        srpe_estimated=False,
        needs_srpe=False,
        flags=[],
        proposed_readiness=[_reading_view(r) for r in readings],
        summary=None,
    )


def import_activity_file(path: str) -> ActivityImportProposal:
    """Parse an activity file and PROPOSE a session to confirm (never logs it).

    Supports .fit (binary), .tcx/.gpx (XML) and .csv (Garmin/Strava summary, or
    an HRV export). Extracts duration, distance and average HR; matches the
    activity to today's planned session by duration/distance proximity
    (source="programmed" + session_plan_id) or falls back to source="external";
    estimates session-RPE from average HR when present (needs_srpe=true means
    ask the athlete). An HRV CSV returns dated readings for readiness instead.
    The athlete MUST confirm before you log anything: call log_session (or
    log_readiness for HRV, after collecting the Hooper items). Malformed files
    return a readable error.
    """
    proposal = propose_import(resolve_athlete_dir(), Path(path).expanduser())
    if proposal.session is None or proposal.activity is None:
        return _hrv_proposal(proposal.hrv_readings)
    return _activity_proposal(proposal.activity, proposal.session)


def register(mcp: FastMCP) -> None:
    """Register the activity-import tool on the server."""
    mcp.tool()(import_activity_file)
