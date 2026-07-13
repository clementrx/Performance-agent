from datetime import date, datetime
from typing import Literal

import pytest

from performance_agent.memory.schemas import (
    AdherenceQuality,
    Calendar,
    CalendarEvent,
    LiftRate,
    MeasuredRate,
    Mesocycle,
    ResponseProfile,
    SessionEntry,
    VolumeToleranceFlag,
    WeekPlan,
)
from performance_agent.reports.sections import (
    build_load_trends,
    build_response_summary,
    build_season_overview,
    collect_prose,
)
from tests.program_plans import a_session, minimal_plan


def _event(event_id: str = "nats", priority: Literal["A", "B", "C"] = "A") -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=date(2026, 10, 3),
        kind="competition",
        priority=priority,
        label="National Championship",
    )


def _session(
    day: int, rpe: int, minutes: int, source: Literal["programmed", "external"] = "programmed"
) -> SessionEntry:
    return SessionEntry(
        performed_at=datetime(2026, 7, day, 9, 0),
        rpe=rpe,
        duration_min=minutes,
        source=source,
    )


# --- season overview ------------------------------------------------------


def test_season_overview_lists_events_and_taper():
    calendar = Calendar(events=[_event()])
    taper_week = WeekPlan(
        week_index=2,
        is_taper=True,
        volume_factor=0.6,
        intensity_factor=1.0,
        sessions=[a_session(session_id="w02-s1")],
    )
    plan = minimal_plan(
        mesocycles=[
            Mesocycle(
                index=1,
                phase="accumulation",
                weeks=[
                    WeekPlan(
                        week_index=1,
                        volume_factor=1.0,
                        intensity_factor=0.9,
                        sessions=[a_session()],
                    )
                ],
            ),
            Mesocycle(index=2, phase="taper", weeks=[taper_week]),
        ]
    )
    overview = build_season_overview(calendar, plan)
    assert overview is not None
    assert overview.events[0].label == "National Championship"
    assert overview.taper_weeks == [2]
    assert [p.phase for p in overview.phases] == ["accumulation", "taper"]
    assert overview.test_weeks == [4]  # from minimal_plan's test_milestone


def test_season_overview_skips_when_no_season_data():
    plan = minimal_plan(season_ref=None, test_milestones=[])
    assert build_season_overview(Calendar(), plan) is None


def test_season_overview_renders_from_events_only_without_plan():
    overview = build_season_overview(Calendar(events=[_event()]), None)
    assert overview is not None
    assert overview.phases == []
    assert overview.taper_weeks == []


# --- load trends ----------------------------------------------------------


def test_load_trends_quote_engine_numbers():
    sessions = [
        _session(1, 6, 60),
        _session(3, 7, 50, source="external"),
        _session(5, 8, 40),
    ]
    trends = build_load_trends(sessions)
    assert trends is not None
    assert trends.days_of_history == 5  # day 1..5 inclusive, rest days zero-filled
    assert trends.last_week_total == pytest.approx(360 + 350 + 320)
    assert trends.external_share == pytest.approx(350 / (360 + 350 + 320))
    assert trends.ctl > 0 and trends.atl > 0


def test_load_trends_skip_when_no_scored_sessions():
    assert build_load_trends([]) is None
    # a session missing rpe/duration cannot be scored
    unscored = SessionEntry(performed_at=datetime(2026, 7, 1, 9, 0))
    assert build_load_trends([unscored]) is None


# --- response summary -----------------------------------------------------


def _profile(measured: MeasuredRate | None) -> ResponseProfile:
    return ResponseProfile(
        as_of=date(2026, 7, 12),
        goal_id="squat-160",
        per_lift_rates=[
            LiftRate(lift="Back Squat", pct_per_week=0.015, r2=0.7, n=6, window_weeks=6.0)
        ],
        per_goal_measured_rate=measured,
        volume_tolerance_flags=[
            VolumeToleranceFlag(
                direction="higher_volume_higher_fatigue", correlation=0.6, n_weeks=5
            )
        ],
        adherence_by_quality=[
            AdherenceQuality(
                quality="strength_heavy",
                done=5,
                partial=1,
                modified=0,
                missed=1,
                adherence_pct=71.0,
            )
        ],
        caveats=["measured on n=6 sessions; treat as provisional"],
    )


def test_response_summary_carries_measured_rate_and_caveats():
    summary = build_response_summary(
        _profile(MeasuredRate(value=0.02, n=6, window_weeks=6.0, r2=0.8)), "squat 160 kg"
    )
    assert summary.goal_rate is not None
    assert summary.goal_rate.label == "squat 160 kg"
    assert summary.goal_rate.n == 6
    assert summary.caveats == ["measured on n=6 sessions; treat as provisional"]
    assert summary.tolerance[0].direction == "higher_volume_higher_fatigue"


def test_response_summary_none_goal_rate_when_unmeasured():
    summary = build_response_summary(_profile(None), None)
    assert summary.goal_rate is None
    assert summary.lift_rates[0].label == "Back Squat"


# --- prose collection (citation gate feed) --------------------------------


def test_collect_prose_gathers_free_text_only():
    season = build_season_overview(Calendar(events=[_event()]), None)
    summary = build_response_summary(_profile(None), None)
    prose = collect_prose(season, summary)
    assert "National Championship" in prose
    assert "measured on n=6 sessions; treat as provisional" in prose
    assert "Back Squat" in prose
