"""The athlete-aware import proposal: matching, sRPE, plausibility reuse, HRV."""

from datetime import date, datetime

import pytest

from performance_agent.importers.proposal import propose_import
from performance_agent.memory import store
from performance_agent.memory.schemas import (
    ExerciseBlock,
    Fallbacks,
    Mesocycle,
    Profile,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    WeekPlan,
)


def _endurance_plan() -> ProgramPlan:
    session = SessionPlan(
        id="w01-s2-long-run",
        weekday=None,
        qualities=["endurance_long"],
        patterns=["run"],
        est_minutes=45,
        purpose="Aerobic base",
        blocks=[
            ExerciseBlock(
                exercise="Easy run",
                priority="primary",
                warmup="none",
                sets=1,
                distance_m=8000.0,
                progression_rule="add 5% distance weekly",
            )
        ],
        fallbacks=Fallbacks(
            low_readiness="cut to 30 min easy",
            short_on_time="30 min easy",
            missing_equipment="treadmill ok",
        ),
    )
    week = WeekPlan(week_index=1, volume_factor=1.0, intensity_factor=1.0, sessions=[session])
    return ProgramPlan.model_validate(
        {
            "version": 1,
            "goal_id": "10k-sub45",
            "created_on": date(2026, 6, 1),
            "mesocycles": [Mesocycle(index=1, phase="accumulation", weeks=[week])],
        }
    )


def test_matches_planned_session_on_duration_and_distance(tmp_path, fixtures):
    store.save_program(tmp_path, _endurance_plan())
    proposal = propose_import(tmp_path, fixtures / "activity.csv")
    assert proposal.kind == "activity"
    session = proposal.session
    assert session is not None
    assert session.source == "programmed"
    assert session.session_plan_id == "w01-s2-long-run"
    assert session.entry.session_plan_id == "w01-s2-long-run"
    assert "matched planned session" in session.rationale


def test_falls_back_to_external_without_a_program(tmp_path, fixtures):
    proposal = propose_import(tmp_path, fixtures / "activity.csv")
    assert proposal.session is not None
    assert proposal.session.source == "external"
    assert proposal.session.entry.source == "external"
    assert "no structured program" in proposal.session.rationale


def test_far_off_activity_is_not_matched(tmp_path):
    store.save_program(tmp_path, _endurance_plan())
    # A 4500 s / 20 km ride is nowhere near the 45 min / 8 km planned run.
    ride = tmp_path / "ride.csv"
    ride.write_text("duration_min,distance_km,avg_hr\n75,20.0,130\n", encoding="utf-8")
    proposal = propose_import(tmp_path, ride)
    assert proposal.session is not None
    assert proposal.session.source == "external"


def test_srpe_estimated_from_hr_when_birthdate_known(tmp_path, fixtures):
    store.write_profile(tmp_path, Profile(birth_date=date(1996, 6, 15)))
    proposal = propose_import(tmp_path, fixtures / "activity.csv")
    session = proposal.session
    assert session is not None
    assert session.srpe_estimated is True
    assert session.needs_srpe is False
    # 152 bpm of a ~190 HRmax = 80% -> RPE (80-50)/5 = 6.
    assert session.entry.rpe == 6
    assert session.entry.avg_hr == pytest.approx(152.0)


def test_srpe_needs_athlete_when_no_birthdate(tmp_path, fixtures):
    proposal = propose_import(tmp_path, fixtures / "activity.csv")
    session = proposal.session
    assert session is not None
    assert session.needs_srpe is True
    assert session.srpe_estimated is False
    assert session.entry.rpe is None


def test_srpe_needs_athlete_when_no_hr(tmp_path):
    no_hr = tmp_path / "no_hr.csv"
    no_hr.write_text("duration_min,distance_km\n45,8.0\n", encoding="utf-8")
    store.write_profile(tmp_path, Profile(birth_date=date(1996, 6, 15)))
    proposal = propose_import(tmp_path, no_hr)
    assert proposal.session is not None
    assert proposal.session.needs_srpe is True


def test_imported_entry_runs_through_plausibility_guard(tmp_path):
    for day in range(5):
        store.append_session(
            tmp_path,
            SessionEntry(performed_at=datetime(2026, 6, 1 + day, 7, 0), duration_min=45),
        )
    outlier = tmp_path / "epic.csv"
    outlier.write_text("duration_min,distance_km\n300,50.0\n", encoding="utf-8")
    proposal = propose_import(tmp_path, outlier)
    assert proposal.session is not None
    codes = {flag["code"] for flag in proposal.session.flags}
    assert "duration_outlier" in codes


def test_hrv_csv_becomes_a_readiness_proposal(tmp_path, fixtures):
    proposal = propose_import(tmp_path, fixtures / "hrv.csv")
    assert proposal.kind == "hrv"
    assert proposal.session is None
    assert [r.hrv_ms for r in proposal.hrv_readings] == [62.5, 58.0, 65.2]


def test_performed_at_falls_back_to_today_without_a_timestamp(tmp_path):
    no_time = tmp_path / "no_time.csv"
    no_time.write_text("duration_min,distance_km\n45,8.0\n", encoding="utf-8")
    proposal = propose_import(tmp_path, no_time, today=date(2026, 6, 20))
    assert proposal.session is not None
    assert proposal.session.entry.performed_at.date() == date(2026, 6, 20)
