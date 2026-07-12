"""Day-of autoregulation: readiness adjustment, time compression, substitution, escalation."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.autoregulation import (
    ESCALATION_THRESHOLD,
    AdjustmentRecord,
    Block,
    Session,
    adjust_session_for_readiness,
    compress_session,
    count_escalation_signals,
    substitute_exercise,
)


def _block(  # noqa: PLR0913 -- test builder, all block fields exposed as keywords
    priority="primary",
    sets=4,
    rest_s=180,
    *,
    load_kg=None,
    rir=None,
    rpe=None,
    duration_min=None,
    warmup_auto=True,
):
    return Block(
        priority=priority,
        sets=sets,
        rest_s=rest_s,
        warmup_auto=warmup_auto,
        load_kg=load_kg,
        pct_1rm=None,
        rir=rir,
        rpe=rpe,
        duration_min=duration_min,
    )


def _strength_session():
    return Session(
        qualities=("strength_heavy",),
        blocks=(
            _block("primary", 4, 180, rpe=8.0, load_kg=120.0),
            _block("secondary", 4, 120, rir=2.0),
            _block("optional", 3, 60, rpe=7.0),
        ),
    )


def _total_sets(session: Session) -> int:
    return sum(b.sets for b in session.blocks)


# --- readiness adjustment -------------------------------------------------


def test_green_leaves_the_session_unchanged():
    session = _strength_session()
    result = adjust_session_for_readiness(session, "green")
    assert result.kind == "unchanged"
    assert all(d.action == "kept" and d.new_sets == d.old_sets for d in result.blocks)


def test_amber_steps_primary_intensity_down_one_step():
    result = adjust_session_for_readiness(_strength_session(), "amber")
    primary = result.blocks[0]
    assert primary.action == "intensity_down"
    assert primary.channel == "rpe"
    assert primary.new_value == 7.0  # RPE 8 -> 7
    assert primary.new_sets == primary.old_sets  # intensity down, volume kept


def test_amber_cuts_secondary_volume_and_drops_optional():
    result = adjust_session_for_readiness(_strength_session(), "amber")
    secondary, optional = result.blocks[1], result.blocks[2]
    assert secondary.action == "volume_down"
    assert secondary.new_sets < secondary.old_sets
    assert optional.action == "dropped"


def test_red_is_a_recovery_replacement_with_no_blocks():
    result = adjust_session_for_readiness(_strength_session(), "red")
    assert result.kind == "recovery"
    assert result.blocks == ()
    assert "recovery" in result.deltas_summary[0].casefold()


def test_amber_rir_channel_increases():
    session = Session(qualities=("hypertrophy",), blocks=(_block("primary", 4, 120, rir=2.0),))
    result = adjust_session_for_readiness(session, "amber")
    assert result.blocks[0].channel == "rir"
    assert result.blocks[0].new_value == 3.0  # RIR 2 -> 3


def test_adjust_rejects_bad_band():
    with pytest.raises(ValueError, match="band must be"):
        adjust_session_for_readiness(_strength_session(), "yellow")  # ty: ignore[invalid-argument-type]


def test_adjust_is_deterministic():
    session = _strength_session()
    assert adjust_session_for_readiness(session, "amber") == adjust_session_for_readiness(
        session, "amber"
    )


_priorities = st.sampled_from(["primary", "secondary", "optional"])
_blocks = st.builds(
    _block,
    priority=_priorities,
    sets=st.integers(min_value=1, max_value=8),
    rest_s=st.integers(min_value=0, max_value=300),
    rpe=st.floats(min_value=5, max_value=10),
)
_sessions = st.builds(
    Session,
    qualities=st.just(("strength_heavy",)),
    blocks=st.lists(_blocks, min_size=1, max_size=6).map(tuple),
)


@given(_sessions, st.sampled_from(["green", "amber"]))
def test_adjusted_volume_never_exceeds_original(session, band):
    result = adjust_session_for_readiness(session, band)
    kept = sum(d.new_sets for d in result.blocks if d.action != "dropped")
    assert kept <= _total_sets(session)


# --- time compression -----------------------------------------------------


def test_compression_keeps_everything_when_time_is_ample():
    result = compress_session(_strength_session(), 480)
    assert result.fits
    assert result.cut == ()
    assert result.kept_indices == (0, 1, 2)


def test_compression_drops_optional_first_then_secondary():
    result = compress_session(_strength_session(), 12)
    cut_priorities = [c.priority for c in result.cut]
    assert cut_priorities and cut_priorities[0] == "optional"
    assert 0 in result.kept_indices  # primary always survives


def test_compression_never_drops_primary_even_when_it_overruns():
    session = Session(
        qualities=("strength_heavy",), blocks=(_block("primary", 6, 240, load_kg=140.0),)
    )
    result = compress_session(session, 1)
    assert result.kept_indices == (0,)
    assert not result.fits


@given(_sessions, st.integers(min_value=1, max_value=240))
def test_primary_kept_whenever_budget_covers_its_cost(session, minutes):
    result = compress_session(session, minutes)
    primary_indices = {i for i, b in enumerate(session.blocks) if b.priority == "primary"}
    assert primary_indices <= set(result.kept_indices)


def test_compression_rejects_zero_minutes():
    with pytest.raises(ValueError, match="available_minutes must be"):
        compress_session(_strength_session(), 0)


def test_compression_is_deterministic():
    session = _strength_session()
    assert compress_session(session, 30) == compress_session(session, 30)


# --- substitution ---------------------------------------------------------


def test_substitution_excludes_the_original_and_respects_equipment():
    alts = substitute_exercise("Back Squat", "squat", ["dumbbell"])
    names = [a.name for a in alts]
    assert "Back Squat" not in names
    assert "Goblet Squat" in names  # dumbbell available
    assert "Leg Press" not in names  # machine not available


def test_bodyweight_option_always_available():
    alts = substitute_exercise("Back Squat", "squat", [])
    assert any(a.equipment == () for a in alts)


def test_substitution_rejects_unknown_pattern():
    with pytest.raises(ValueError, match="unknown movement pattern"):
        substitute_exercise("Back Squat", "nonsense", ["barbell"])


# --- escalation counting --------------------------------------------------


def _rec(kind, days_ago, *, band=None, applied=True):
    return AdjustmentRecord(kind=kind, band=band, applied=applied, days_ago=days_ago)


def test_three_readiness_downgrades_in_window_escalate():
    records = [_rec("readiness", d, band="amber") for d in (1, 5, 10)]
    signals = count_escalation_signals(records)
    assert signals.downgrades == ESCALATION_THRESHOLD
    assert signals.escalate


def test_three_compressions_in_window_escalate():
    records = [_rec("time", d) for d in (2, 6, 13)]
    signals = count_escalation_signals(records)
    assert signals.compressions == ESCALATION_THRESHOLD
    assert signals.escalate


def test_old_or_green_or_unapplied_do_not_escalate():
    records = [
        _rec("readiness", 20, band="amber"),  # outside window
        _rec("readiness", 1, band="green"),  # not a downgrade
        _rec("readiness", 2, band="red", applied=False),  # not applied
        _rec("time", 3),  # a single compression
    ]
    signals = count_escalation_signals(records)
    assert signals.downgrades == 0
    assert signals.compressions == 1
    assert not signals.escalate


def test_escalation_rejects_bad_window():
    with pytest.raises(ValueError, match="window_days must be"):
        count_escalation_signals([], window_days=0)
