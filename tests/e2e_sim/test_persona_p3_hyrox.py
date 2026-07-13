"""Persona P3 — Hyrox hybrid (4 sessions/week, one A race + one B race).

Exercises: a mixed-modality season with a taper before the A race, a calendar
change at week 6 that re-plans and keeps a taper before the NEW date, zero
`block` sequencing violations for the 4-day template, and a return-to-load ramp
engaged after a 2-week sick break — saved as a new program version whose phase is
`return_to_load`. Every program version carries a reason.
"""

from datetime import timedelta
from itertools import pairwise

from performance_agent.engine.return_to_load import build_return_progression
from performance_agent.memory import store
from performance_agent.memory.schemas import Availability as Avail
from performance_agent.memory.schemas import (
    CalendarEvent,
    Mesocycle,
    Profile,
    ProgramPlan,
    WeekPlan,
)
from performance_agent.memory.season import build_season_plan
from performance_agent.memory.sequencing import check_week_for_athlete
from tests.e2e_sim import harness as h

A_RACE_WEEK = 16
B_RACE_WEEK = 8


def _template() -> list:
    """The Hyrox 4-day microcycle: intervals / stations / brick / long easy."""
    return [
        h.run_session("mon-intervals", 0, "hiit", 45, 8),
        h.strength_session("wed-stations", 2, patterns=["squat", "hinge", "push_h"], load_kg=90.0),
        h.run_session("fri-brick", 4, "brick", 75, 6),
        h.run_session("sun-long", 6, "endurance_long", 85, 4),
    ]


def _seed_athlete(base_dir, *, a_race_date=None):
    store.write_profile(
        base_dir,
        Profile(
            sport="hyrox",
            availability=Avail(sessions_per_week=4, minutes_per_session=90, weekdays=[0, 2, 4, 6]),
        ),
    )
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="hyrox-a",
            date=a_race_date or h.ORIGIN + timedelta(weeks=A_RACE_WEEK - 1),
            kind="competition",
            priority="A",
            label="Hyrox A",
        ),
    )
    store.upsert_calendar_event(
        base_dir,
        CalendarEvent(
            id="hyrox-b",
            date=h.ORIGIN + timedelta(weeks=B_RACE_WEEK - 1),
            kind="competition",
            priority="B",
            label="Hyrox B",
        ),
    )


def _assert_taper_before_each_competition(segments):
    comps = [s for s in segments if s["phase_type"] == "competition"]
    tapers = {s["end_week"] for s in segments if s["phase_type"] == "taper"}
    assert comps
    for comp in comps:
        # A taper segment must end on the week immediately before the competition.
        assert comp["start_week"] - 1 in tapers


def test_season_has_taper_before_a_race(tmp_path):
    _seed_athlete(tmp_path)
    plan = build_season_plan(tmp_path, modality="mixed", today=h.ORIGIN)
    segments = plan["segments"]
    assert segments[0]["start_week"] == 1
    for earlier, later in pairwise(segments):
        assert later["start_week"] == earlier["end_week"] + 1
    _assert_taper_before_each_competition(segments)
    # The B race is surfaced separately (mini-taper / train-through), not a full taper.
    assert any(e["event_id"] == "hyrox-b" for e in plan["secondary_events"])


def test_calendar_change_keeps_taper_before_new_date(tmp_path):
    _seed_athlete(tmp_path)
    store.save_program(
        tmp_path,
        h.program_from_weeks("hyrox", [_template()]),
        reason="initial plan",
        today=h.ORIGIN,
    )
    # At week 6 the A race is postponed two weeks; the calendar is updated and re-planned.
    new_date = h.ORIGIN + timedelta(weeks=A_RACE_WEEK + 1)
    store.upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="hyrox-a", date=new_date, kind="competition", priority="A", label="Hyrox A"
        ),
    )
    replan_today = h.ORIGIN + timedelta(weeks=5)
    replanned = build_season_plan(tmp_path, modality="mixed", today=replan_today)
    _assert_taper_before_each_competition(replanned["segments"])
    store.save_program(
        tmp_path,
        h.program_from_weeks("hyrox", [_template()]),
        reason=f"A race moved to {new_date.isoformat()}",
        today=replan_today,
    )
    v2 = store.read_program(tmp_path, version=2)
    assert v2 is not None
    assert v2.reason and new_date.isoformat() in v2.reason


def test_four_day_template_has_zero_block_violations(tmp_path):
    _seed_athlete(tmp_path)
    program = h.program_from_weeks("hyrox", [_template()])
    store.save_program(tmp_path, program, reason="v1", today=h.ORIGIN)
    week = program.mesocycles[0].weeks[0]
    violations = check_week_for_athlete(tmp_path, week)
    assert [v for v in violations if v.severity == "block"] == []


def test_return_to_load_ramp_engaged_after_sick_break(tmp_path):
    _seed_athlete(tmp_path)
    store.save_program(
        tmp_path, h.program_from_weeks("hyrox", [_template()]), reason="v1", today=h.ORIGIN
    )
    ramp = build_return_progression(weeks_off=2, sessions_per_week=4, pain_free=True)
    # A real graded restart: starts below baseline, climbs monotonically to 1.0.
    assert ramp[0].volume_factor < 1.0
    assert ramp[0].intensity_factor < 1.0
    for earlier, later in pairwise(ramp):
        assert later.volume_factor >= earlier.volume_factor
        assert later.intensity_factor >= earlier.intensity_factor
    assert ramp[-1].volume_factor == 1.0
    assert ramp[-1].intensity_factor == 1.0

    # Persist the ramp as a return_to_load program version with a reason.
    return_weeks = [
        WeekPlan(
            week_index=week_factor.week_index,
            volume_factor=week_factor.volume_factor,
            intensity_factor=week_factor.intensity_factor,
            notes=week_factor.note,
            sessions=_template(),
        )
        for week_factor in ramp
    ]
    return_plan = ProgramPlan(
        version=1,
        goal_id="hyrox",
        created_on=h.ORIGIN,
        mesocycles=[Mesocycle(index=1, phase="return_to_load", weeks=return_weeks)],
    )
    store.save_program(
        tmp_path, return_plan, reason="2-week sick break, cleared by physician", today=h.ORIGIN
    )
    v2 = store.read_program(tmp_path, version=2)
    assert v2 is not None
    assert v2.plan is not None
    assert v2.plan.mesocycles[0].phase == "return_to_load"
    assert v2.reason


def test_every_program_version_has_a_reason(tmp_path):
    _seed_athlete(tmp_path)
    for reason in ("initial plan", "post-B-race adjust", "return-to-load after break"):
        store.save_program(
            tmp_path, h.program_from_weeks("hyrox", [_template()]), reason=reason, today=h.ORIGIN
        )
    latest = store.latest_program_version(tmp_path)
    assert latest == 3
    for version in range(1, latest + 1):
        read = store.read_program(tmp_path, version=version)
        assert read is not None and read.reason
