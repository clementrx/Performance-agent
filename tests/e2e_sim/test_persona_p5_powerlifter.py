"""Persona P5 — powerlifter (SEEDED model).

Drives load-velocity profiling and the individual taper response on the packaged
powerlifting model: seed the model -> log VBT sets -> fit the load-velocity profile
-> log two historical tapers with outcomes -> recommend an individual taper. No LLM;
deterministic.
"""

from datetime import date, datetime, timedelta

from performance_agent.memory import store
from performance_agent.memory.performance_models import compute_performance_gaps, load_seed_models
from performance_agent.memory.schemas import (
    CalendarEvent,
    KpiResult,
    SessionEntry,
    VbtSet,
)
from performance_agent.memory.taper_response import recommend_taper
from performance_agent.memory.vbt import fit_exercise_profile, velocity_suggestion

ORIGIN = date(2026, 1, 1)
TODAY = date(2026, 7, 13)


def _seed_powerlifter(base_dir):
    store.save_performance_model(base_dir, load_seed_models()["powerlifting"])
    store.append_kpi_result(
        base_dir,
        KpiResult(
            date=date(2026, 7, 1), kpi_id="squat-rel", protocol="1rm", value=1.8, unit="x bw"
        ),
    )


def _log_squat_vbt(base_dir):
    for i, (load, vel) in enumerate([(100, 0.75), (140, 0.55), (180, 0.35), (200, 0.25)]):
        store.append_session(
            base_dir,
            SessionEntry(
                performed_at=datetime(2026, 1, 1 + i, 10, 0),
                vbt_sets=[VbtSet(exercise="Back Squat", load_kg=load, mean_velocity=vel, reps=1)],
            ),
        )


def test_powerlifter_gaps_flag_strength_priority(tmp_path):
    _seed_powerlifter(tmp_path)
    gaps = compute_performance_gaps(tmp_path, "elite", TODAY)
    top = gaps["quality_priorities"][0]
    # max_strength carries the model's dominant weight, so it leads the priorities.
    assert top["quality"] == "max_strength"


def test_powerlifter_load_velocity_profile(tmp_path):
    _seed_powerlifter(tmp_path)
    _log_squat_vbt(tmp_path)
    profile = fit_exercise_profile(tmp_path, "Back Squat")
    assert profile["usable"] is True
    assert profile["e1rm_kg"] > 150  # a plausible 1RM extrapolated at the velocity threshold
    assert profile["slope"] < 0  # velocity falls as load rises
    # A slow warm-up nudges loads down.
    suggestion = velocity_suggestion(tmp_path, "Back Squat", 140, 0.45)
    assert suggestion is not None
    assert suggestion["pct_change"] < 0


def test_powerlifter_individual_taper(tmp_path):
    _seed_powerlifter(tmp_path)
    # Two historical meets, each preceded by a 7-day taper, with an outcome.
    for day in range(120):
        tapering = 33 <= day < 40 or 83 <= day < 90
        store.append_session(
            tmp_path,
            SessionEntry(
                performed_at=datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=day),
                rpe=3 if tapering else 7,
                duration_min=20 if tapering else 60,
            ),
        )
    for i, day in enumerate((40, 90)):
        store.upsert_calendar_event(
            tmp_path,
            CalendarEvent(
                id=f"meet{i}",
                date=ORIGIN + timedelta(days=day),
                kind="competition",
                priority="A",
                label=f"Meet{i}",
            ),
        )
        store.append_kpi_result(
            tmp_path,
            KpiResult(
                date=ORIGIN + timedelta(days=day),
                kpi_id="squat-rel",
                protocol="meet",
                value=1.8 + 0.05 * i,
                unit="x bw",
            ),
        )
    rec = recommend_taper(tmp_path, 8, "strength", "A")
    assert rec["basis"] == "individual"
    assert rec["taper_days"] == 7
