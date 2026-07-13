"""Persona P2 — amateur footballer (3 club practices + 1 match + 2 gym slots).

Exercises: external load present in the weekly totals, zero `block` sequencing
violations for a footballer week (lifting kept away from match +/-1 day), an
injected fixture pile-up week firing a deload within one simulated week, and
`list_due_actions` surfacing the right facts after a silent week.
"""

from datetime import timedelta

from performance_agent.engine.load import (
    fitness_fatigue_series,
    readiness_score,
    weekly_monotony,
    weekly_strain,
)
from performance_agent.engine.regulation import should_deload
from performance_agent.memory import store
from performance_agent.memory.diligence import list_due_actions
from performance_agent.memory.schemas import Availability as Avail
from performance_agent.memory.schemas import (
    Profile,
    RecurringConstraint,
)
from performance_agent.memory.sequencing import check_week_for_athlete
from tests.e2e_sim import harness as h

# Weekly commitments: club practice Mon/Wed/Fri, match Sunday; gym Tue/Thu.
_RECURRING = [
    RecurringConstraint(weekday=0, kind="club_practice", est_minutes=90, est_srpe=6, label="Club"),
    RecurringConstraint(weekday=2, kind="club_practice", est_minutes=90, est_srpe=6, label="Club"),
    RecurringConstraint(weekday=4, kind="club_practice", est_minutes=90, est_srpe=6, label="Club"),
    RecurringConstraint(weekday=6, kind="match_day", est_minutes=90, est_srpe=8, label="Match"),
]


def _gym_week() -> list:
    """Two gym sessions on distinct patterns, both clear of the Sunday match +/-1."""
    return [
        h.strength_session("tue-lower", 1, patterns=["squat", "hinge"], load_kg=110.0),
        h.strength_session("thu-upper", 3, patterns=["push_h", "pull_h"], load_kg=70.0),
    ]


def _seed_athlete(base_dir):
    store.write_profile(
        base_dir,
        Profile(
            sport="football",
            availability=Avail(sessions_per_week=2, minutes_per_session=120, weekdays=[1, 3]),
        ),
    )
    store.set_recurring_constraints(base_dir, _RECURRING)


def test_external_load_present_in_weekly_totals(tmp_path):
    _seed_athlete(tmp_path)
    entries = [
        h.logged_session(0, rpe=6, duration_min=90, source="external", kind="club_practice"),
        h.logged_session(
            1, rpe=8, duration_min=60, source="programmed", session_plan_id="tue-lower"
        ),
        h.logged_session(2, rpe=6, duration_min=90, source="external", kind="club_practice"),
        h.logged_session(
            3, rpe=8, duration_min=60, source="programmed", session_plan_id="thu-upper"
        ),
        h.logged_session(4, rpe=6, duration_min=90, source="external", kind="club_practice"),
        h.logged_session(6, rpe=8, duration_min=90, source="external", kind="match"),
    ]
    for entry in entries:
        store.append_session(tmp_path, entry)
    logged = store.read_sessions(tmp_path)
    total = sum(h.session_load(e) for e in logged)
    assert total > 0
    share = h.external_share(logged)
    # Club + match load is the majority of the week; the coach never programmed it.
    assert share > 0.5


def test_footballer_week_has_zero_block_violations(tmp_path):
    _seed_athlete(tmp_path)
    weeks = [_gym_week()]
    program = h.program_from_weeks("stay-fit", weeks, season_ref="in-season football")
    store.save_program(tmp_path, program, reason="in-season maintenance", today=h.ORIGIN)
    week = program.mesocycles[0].weeks[0]
    violations = check_week_for_athlete(tmp_path, week)
    assert [v for v in violations if v.severity == "block"] == []


def test_fixture_pileup_fires_deload_within_one_week(tmp_path):
    _seed_athlete(tmp_path)
    # Seven calm weeks: three practices + a match, with rest days between them.
    for week in range(7):
        for day, rpe in ((0, 6), (2, 6), (4, 6), (6, 8)):
            store.append_session(
                tmp_path,
                h.logged_session(
                    week * 7 + day, rpe=rpe, duration_min=90, source="external", kind="club"
                ),
            )
    # Week 8 is a fixture pile-up: a match or practice every single day (monotonous, heavy).
    pileup_start = 7 * 7
    for day in range(7):
        store.append_session(
            tmp_path,
            h.logged_session(
                pileup_start + day, rpe=8, duration_min=85, source="external", kind="match"
            ),
        )
    loads = h.daily_loads(store.read_sessions(tmp_path), pileup_start + 7)
    pileup_loads = loads[pileup_start : pileup_start + 7]
    calm_loads = loads[pileup_start - 7 : pileup_start]

    tsb_after = fitness_fatigue_series(loads)[-1].tsb
    tsb_before = fitness_fatigue_series(loads[:pileup_start])[-1].tsb
    strain_trend = (weekly_strain(pileup_loads) or 0.0) - (weekly_strain(calm_loads) or 0.0)
    # Readiness fell over the pile-up (green baseline to a red pile-up week).
    readiness_trend = (
        readiness_score(6, 6, 6, 6).score_0_100 - readiness_score(2, 2, 2, 2).score_0_100
    )

    result = should_deload(
        weeks_since_deload=1,
        monotony_recent=weekly_monotony(pileup_loads),
        strain_trend=strain_trend,
        tsb=tsb_after,
        readiness_trend=min(tsb_after - tsb_before, readiness_trend),
        adherence_pct=95.0,
        planned_interval_weeks=4,
    )
    assert result.recommendation != "none"
    assert result.drivers


def test_list_due_actions_after_silent_week(tmp_path):
    # A 3-weekday plan; three sessions 8-12 days ago logged without readiness, then a
    # fully silent last week: missed sessions AND a readiness gap should both surface.
    _seed_athlete(tmp_path)
    week = [
        h.run_session("mon", 0, "endurance_easy", 40, 4),
        h.strength_session("wed", 2, patterns=["squat"], load_kg=100.0),
        h.run_session("fri", 4, "endurance_easy", 40, 4),
    ]
    store.save_program(
        tmp_path, h.program_from_weeks("stay-fit", [week]), reason="v1", today=h.ORIGIN
    )
    today = h.ORIGIN + timedelta(days=28)
    for days_ago in (8, 10, 12):
        offset = (today - h.ORIGIN).days - days_ago
        store.append_session(tmp_path, h.logged_session(offset, rpe=6, duration_min=60))
    kinds = {a["kind"] for a in list_due_actions(tmp_path, today=today)}
    assert "missed_sessions" in kinds
    assert "readiness_gap" in kinds
