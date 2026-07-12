"""Intra-week sequencing: one week per rule, clean templates, and properties."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.sequencing import (
    RecurringInput,
    SessionInput,
    check_week_sequencing,
)


def _s(
    session_id: str,
    weekday: int | None,
    qualities: tuple[str, ...],
    patterns: tuple[str, ...] = (),
    est_minutes: int = 60,
) -> SessionInput:
    return SessionInput(session_id, weekday, qualities, patterns, est_minutes)


def _rule_ids(violations) -> list[str]:
    return [v.rule_id for v in violations]


# --- one constructed week per rule ---------------------------------------


def test_r1_same_pattern_heavy_within_48h_blocks():
    week = [
        _s("mon", 0, ("strength_heavy",), ("squat", "hinge")),
        _s("tue", 1, ("strength_heavy",), ("squat",)),
    ]
    violations = check_week_sequencing(week, [])
    assert [v.severity for v in violations if v.rule_id == "R1"] == ["block"]
    assert violations[0].session_ids == ("mon", "tue")


def test_r1_uses_72h_in_a_high_volume_week():
    week = [
        _s("mon", 0, ("strength_heavy",), ("squat",)),
        _s("wed", 2, ("strength_heavy",), ("squat",)),  # 2 days apart
    ]
    assert "R1" not in _rule_ids(check_week_sequencing(week, [], volume_factor=1.0))
    assert "R1" in _rule_ids(check_week_sequencing(week, [], volume_factor=1.1))


def test_r1_different_patterns_do_not_trigger():
    week = [
        _s("mon", 0, ("strength_heavy",), ("squat",)),
        _s("tue", 1, ("strength_heavy",), ("push_h",)),
    ]
    assert "R1" not in _rule_ids(check_week_sequencing(week, []))


def test_r2_hiit_day_before_lower_heavy_blocks():
    week = [
        _s("hiit", 0, ("hiit",), ("run",)),
        _s("legs", 1, ("strength_heavy",), ("squat",)),
    ]
    violations = check_week_sequencing(week, [])
    assert [v.severity for v in violations if v.rule_id == "R2"] == ["block"]


def test_r2_hiit_before_upper_heavy_does_not_trigger():
    week = [
        _s("hiit", 0, ("hiit",), ("run",)),
        _s("push", 1, ("strength_heavy",), ("push_h",)),
    ]
    assert "R2" not in _rule_ids(check_week_sequencing(week, []))


def test_r3_same_day_strength_and_endurance_warns_when_strength_is_a_goal():
    week = [
        _s("lift", 0, ("strength_heavy",), ("squat",)),
        _s("run", 0, ("endurance_easy",), ("run",)),
    ]
    warn = check_week_sequencing(week, [], strength_priority=True)
    assert [v.severity for v in warn if v.rule_id == "R3"] == ["warn"]
    assert "R3" not in _rule_ids(check_week_sequencing(week, [], strength_priority=False))


def test_r4_three_consecutive_high_days_block():
    week = [
        _s("mon", 0, ("strength_heavy",), ("squat",)),
        _s("tue", 1, ("hiit",), ("run",)),
        _s("wed", 2, ("strength_heavy",), ("push_h",)),
    ]
    violations = check_week_sequencing(week, [])
    r4 = [v for v in violations if v.rule_id == "R4"]
    assert len(r4) == 1 and r4[0].severity == "block"
    assert r4[0].session_ids == ("mon", "tue", "wed")


def test_r4_match_counts_as_a_high_day():
    week = [
        _s("mon", 0, ("strength_heavy",), ("push_h",)),
        _s("tue", 1, ("hiit",), ("run",)),
    ]
    recurring = [RecurringInput(2, "match_day", 90)]  # Wed match → 3 in a row
    assert "R4" in _rule_ids(check_week_sequencing(week, recurring))


def test_r5_day_before_match_must_be_low():
    week = [_s("legs", 1, ("strength_heavy",), ("squat",))]
    recurring = [RecurringInput(2, "match_day", 90)]
    violations = check_week_sequencing(week, recurring)
    assert [v.rule_id for v in violations if v.rule_id == "R5"] == ["R5"]
    assert "day before" in violations[0].message


def test_r5_day_after_match_must_be_recovery():
    week = [_s("hard", 3, ("hiit",), ("run",))]
    recurring = [RecurringInput(2, "match_day", 90)]
    violations = check_week_sequencing(week, recurring)
    assert any("day after" in v.message for v in violations if v.rule_id == "R5")


def test_r5_priming_the_day_before_a_match_is_allowed():
    week = [_s("prime", 1, ("power",), ("squat",))]
    recurring = [RecurringInput(2, "match_day", 90)]
    assert "R5" not in _rule_ids(check_week_sequencing(week, recurring))


def test_r6_long_endurance_before_a_match_warns():
    week = [_s("long", 1, ("endurance_long",), ("run",))]
    recurring = [RecurringInput(2, "match_day", 90)]
    r6 = [v for v in check_week_sequencing(week, recurring) if v.rule_id == "R6"]
    assert len(r6) == 1 and r6[0].severity == "warn"


def test_r6_long_endurance_before_hiit_warns():
    week = [
        _s("long", 0, ("endurance_long",), ("run",)),
        _s("intervals", 1, ("hiit",), ("run",)),
    ]
    r6 = [v for v in check_week_sequencing(week, []) if v.rule_id == "R6"]
    assert len(r6) == 1
    assert r6[0].session_ids == ("intervals", "long")


def test_r7_day_over_available_minutes_blocks():
    week = [_s("legs", 0, ("strength_heavy",), ("squat",), est_minutes=120)]
    violations = check_week_sequencing(week, [], available_minutes=90)
    assert [v.severity for v in violations if v.rule_id == "R7"] == ["block"]


def test_r7_counts_recurring_load_on_the_day():
    week = [_s("gym", 0, ("strength_heavy",), ("push_h",), est_minutes=60)]
    recurring = [RecurringInput(0, "club_practice", 60)]  # same day, 60 + 60 > 90
    assert "R7" in _rule_ids(check_week_sequencing(week, recurring, available_minutes=90))


def test_r7_disabled_when_no_available_minutes():
    week = [_s("legs", 0, ("strength_heavy",), ("squat",), est_minutes=480)]
    assert "R7" not in _rule_ids(check_week_sequencing(week, []))


# --- clean reference templates (2..6 scheduled sessions) ------------------


def _clean_week(n: int) -> list[SessionInput]:
    """A conflict-free week of n sessions spread across distinct days."""
    templates = [
        _s("s0", 0, ("strength_heavy",), ("squat",)),
        _s("s1", 2, ("strength_heavy",), ("push_h",)),
        _s("s2", 4, ("strength_heavy",), ("pull_h",)),
        _s("s3", 6, ("endurance_easy",), ("run",)),
        _s("s4", 1, ("hypertrophy",), ("lunge",)),
        _s("s5", 5, ("tempo",), ("run",)),
    ]
    return templates[:n]


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_clean_templates_have_no_block_violations(n):
    violations = check_week_sequencing(_clean_week(n), [], strength_priority=True)
    assert [v for v in violations if v.severity == "block"] == []


def test_hyrox_four_day_template_passes():
    week = [
        _s("intervals", 0, ("hiit",), ("run",)),
        _s("stations", 2, ("hypertrophy",), ("carry",)),
        _s("brick", 4, ("brick",), ("run", "ride")),
        _s("long", 6, ("endurance_long",), ("run",)),
    ]
    assert check_week_sequencing(week, []) == []


# --- unscheduled sessions -------------------------------------------------


def test_unscheduled_sessions_are_skipped():
    week = [
        _s("a", None, ("strength_heavy",), ("squat",)),
        _s("b", None, ("strength_heavy",), ("squat",)),
    ]
    assert check_week_sequencing(week, []) == []


# --- determinism and the permutation property -----------------------------


def _week() -> list[SessionInput]:
    return [
        _s("mon", 0, ("strength_heavy",), ("squat",)),
        _s("tue", 1, ("strength_heavy",), ("squat",)),
        _s("thu", 3, ("hiit",), ("run",)),
    ]


def test_is_deterministic():
    assert check_week_sequencing(_week(), []) == check_week_sequencing(_week(), [])


@given(st.permutations(_week()))
def test_session_order_does_not_change_the_result(permuted):
    assert check_week_sequencing(list(permuted), []) == check_week_sequencing(_week(), [])


@given(shift=st.integers(min_value=-2, max_value=2))
def test_translating_all_weekdays_preserves_the_rule_multiset(shift):
    base = [
        _s("a", 2, ("strength_heavy",), ("squat",)),
        _s("b", 3, ("strength_heavy",), ("squat",)),
        _s("c", 4, ("hiit",), ("run",)),
    ]
    shifted = [
        SessionInput(s.id, (s.weekday or 0) + shift, s.qualities, s.patterns, s.est_minutes)
        for s in base
    ]
    before = sorted(_rule_ids(check_week_sequencing(base, [])))
    after = sorted(_rule_ids(check_week_sequencing(shifted, [])))
    assert before == after


# --- validation -----------------------------------------------------------


def test_rejects_out_of_range_weekday():
    with pytest.raises(ValueError, match="0-6"):
        check_week_sequencing([_s("x", 7, ("recovery",), (), 30)], [])


def test_rejects_non_positive_volume_factor():
    with pytest.raises(ValueError, match="volume_factor"):
        check_week_sequencing([], [], volume_factor=0)


def test_rejects_bad_available_minutes():
    with pytest.raises(ValueError, match="available_minutes"):
        check_week_sequencing([], [], available_minutes=0)
