"""Pure next-load math for each ProgressionRule kind."""

import pytest

from performance_agent.engine.progression import (
    SetActual,
    next_load_double,
    next_load_from_pct,
    next_load_linear,
    next_load_rir,
    round_to_increment,
)
from performance_agent.memory.schemas import ProgressionRule

DOUBLE = ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5)
LINEAR = ProgressionRule(kind="linear_load", increment_kg=2.5)
RIR = ProgressionRule(kind="rir_target", target_rir=2)


def sets(*reps, load=80.0, rir=None):
    return [SetActual(reps=r, load_kg=load, rir=rir) for r in reps]


def test_rounding():
    assert round_to_increment(81.4, 2.5) == 82.5
    assert round_to_increment(81.1, 2.5) == 80.0


def test_rounding_rejects_bad_step():
    with pytest.raises(ValueError, match="step"):
        round_to_increment(80.0, 0)


def test_double_top_of_range_increments():
    result = next_load_double(DOUBLE, 80.0, sets(12, 12, 12, 12))
    assert result.next_load_kg == 82.5
    assert result.action == "increment"
    assert result.flags == ()


def test_double_mid_range_holds():
    result = next_load_double(DOUBLE, 80.0, sets(12, 12, 12, 11))
    assert result.next_load_kg == 80.0
    assert result.action == "hold"


def test_double_below_rep_min_holds_with_failed_flag():
    result = next_load_double(DOUBLE, 80.0, sets(8, 7, 6))
    assert result.next_load_kg == 80.0
    assert result.action == "hold"
    assert "failed_sets" in result.flags


def test_double_no_sets_flags_unmatched():
    result = next_load_double(DOUBLE, 80.0, [])
    assert result.next_load_kg is None
    assert "no_logged_sets" in result.flags


def test_linear_all_sets_at_prescribed_reps_increment():
    result = next_load_linear(LINEAR, 100.0, 5, sets(5, 5, 5, load=100.0))
    assert result.next_load_kg == 102.5
    assert result.action == "increment"


def test_linear_missed_reps_holds_with_flag():
    result = next_load_linear(LINEAR, 100.0, 5, sets(5, 4, 3, load=100.0))
    assert result.next_load_kg == 100.0
    assert "failed_sets" in result.flags


def test_rir_above_target_raises_load():
    # mean RIR 4 vs target 2 -> +6% on 100 kg -> 106 -> rounds to 105
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0, rir=4))
    assert result.next_load_kg == 105.0
    assert result.action == "increment"


def test_rir_below_target_lowers_load():
    # mean RIR 0 vs target 2 -> -6% -> 94 -> rounds to 95
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0, rir=0))
    assert result.next_load_kg == 95.0
    assert result.action == "decrement"


def test_rir_clamped_to_ten_percent():
    # mean RIR 8 vs target 2 -> raw +18% -> clamped to +10% -> 110
    result = next_load_rir(RIR, 100.0, sets(5, load=100.0, rir=8))
    assert result.next_load_kg == 110.0
    assert "clamped" in result.flags


def test_rir_without_logged_rir_holds():
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0))
    assert result.next_load_kg == 100.0
    assert "no_rir_logged" in result.flags


def test_from_pct_resolves_next_week_pct():
    result = next_load_from_pct(0.85, 140.0, 2.5)
    assert result.next_load_kg == 120.0
    assert result.action == "per_plan"


def test_from_pct_without_e1rm_flags():
    result = next_load_from_pct(0.85, None, 2.5)
    assert result.next_load_kg is None
    assert "no_e1rm" in result.flags
