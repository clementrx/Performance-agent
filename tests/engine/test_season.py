"""Season backward-planning: tiling properties and taper placement."""

import pytest

from performance_agent.engine.periodization import MIN_BLOCK_WEEKS as PERIODIZATION_MIN
from performance_agent.engine.season import (
    MIN_BLOCK_WEEKS,
    SeasonEvent,
    plan_season,
    recommend_taper_length,
)


def _a(event_id: str, week: int) -> SeasonEvent:
    return SeasonEvent(event_id=event_id, week=week, priority="A", kind="competition")


def _tiles_horizon(segments, horizon: int) -> bool:
    """Segments cover 1..horizon contiguously with no gaps or overlaps."""
    cursor = 1
    for seg in segments:
        if seg.start_week != cursor or seg.end_week < seg.start_week:
            return False
        cursor = seg.end_week + 1
    return cursor == horizon + 1


def test_no_a_event_is_one_open_ended_segment():
    segments = plan_season([], 12)
    assert len(segments) == 1
    assert segments[0].phase_type == "block"
    assert segments[0].anchor_event_id is None
    assert _tiles_horizon(segments, 12)


def test_short_horizon_with_no_a_event_uses_waves():
    segments = plan_season([], 4)
    assert segments[0].phase_type == "waves"


def test_single_a_event_places_taper_then_competition():
    segments = plan_season([_a("race", 16)], 16, modality="endurance")
    comp = [s for s in segments if s.phase_type == "competition"]
    taper = [s for s in segments if s.phase_type == "taper"]
    assert len(comp) == 1 and comp[0].start_week == comp[0].end_week == 16
    assert len(taper) == 1
    # taper ends immediately before the competition week
    assert taper[0].end_week == 15
    assert _tiles_horizon(segments, 16)


def test_taper_always_immediately_precedes_its_a_event():
    segments = plan_season([_a("r1", 10), _a("r2", 22)], 24, modality="mixed")
    comps = {s.anchor_event_id: s for s in segments if s.phase_type == "competition"}
    tapers = {s.anchor_event_id: s for s in segments if s.phase_type == "taper"}
    for event_id, comp in comps.items():
        assert tapers[event_id].end_week == comp.start_week - 1


def test_two_a_events_close_together_flag_a_compromise():
    # 4 weeks apart (< MIN_BLOCK_WEEKS) → maintenance bridge + compromise note.
    segments = plan_season([_a("r1", 12), _a("r2", 16)], 20)
    assert any(s.phase_type == "maintenance" for s in segments)
    assert any("compromise" in s.rationale for s in segments)
    assert _tiles_horizon(segments, 20)


def test_wide_gap_uses_a_block():
    segments = plan_season([_a("r1", 20)], 20)
    assert any(s.phase_type == "block" for s in segments)


def test_event_in_the_past_is_rejected():
    with pytest.raises(ValueError, match="before the plan start"):
        plan_season([_a("stale", 0)], 12)


def test_event_beyond_horizon_is_rejected():
    with pytest.raises(ValueError, match="beyond"):
        plan_season([_a("far", 30)], 12)


def test_b_events_never_create_a_taper_segment():
    events = [_a("r1", 16), SeasonEvent("tuneup", 8, "B", "competition")]
    segments = plan_season(events, 16)
    tapers = [s for s in segments if s.phase_type == "taper"]
    assert all(s.anchor_event_id == "r1" for s in tapers)


def test_planning_is_deterministic():
    events = [_a("r1", 10), _a("r2", 22)]
    assert plan_season(events, 24) == plan_season(events, 24)


def test_taper_length_endurance_is_longer_than_strength():
    strength = recommend_taper_length(8, "strength", "A")
    endurance = recommend_taper_length(8, "endurance", "A")
    assert strength < endurance
    assert 4 <= strength <= 14
    assert 4 <= endurance <= 14


def test_b_event_gets_a_shorter_taper_than_a():
    assert recommend_taper_length(8, "mixed", "B") < recommend_taper_length(8, "mixed", "A")


def test_taper_length_is_bounded():
    for modality in ("strength", "endurance", "mixed"):
        for priority in ("A", "B", "C"):
            days = recommend_taper_length(10, modality, priority)
            assert 4 <= days <= 14


def test_taper_length_rejects_bad_modality():
    with pytest.raises(ValueError, match="modality"):
        recommend_taper_length(8, "power", "A")  # ty: ignore[invalid-argument-type]


def test_taper_length_rejects_negative_buildup():
    with pytest.raises(ValueError, match="non-negative"):
        recommend_taper_length(-1, "mixed", "A")


def test_min_block_weeks_constant_matches_periodization():
    assert MIN_BLOCK_WEEKS == PERIODIZATION_MIN
