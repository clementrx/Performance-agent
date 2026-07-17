"""CompetitionProtocol schemas: structure and validator errors."""

from datetime import date

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    AttemptPlan,
    CompetitionProtocol,
    DocumentedPractice,
    FuelingPlan,
    Guidance,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)

EVENT_DATE = date(2026, 8, 1)


def _day(offset, title="Race day"):
    return ProtocolDay(
        day_offset=offset,
        title=title,
        lines=[ProtocolLine(text="Easy 20 min shakeout.", time_hint="07:30")],
    )


def _protocol(**overrides):
    fields = {
        "version": 1,
        "event_id": "nationals",
        "event_date": EVENT_DATE,
        "goal_id": "sub-40-10k",
        "created_on": date(2026, 7, 25),
        "window_days": 7,
        "days": [_day(-2, "Carb load"), _day(-1, "Rest"), _day(0)],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_valid_protocol_with_all_sections():
    protocol = _protocol(
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        attempts=[
            AttemptPlan(
                lift="Squat",
                e1rm_kg=200,
                opener_kg=182.5,
                second_kg=192.5,
                third_kg=205,
                basis="engine",
                flags=[],
            )
        ],
        fueling=FuelingPlan(
            carb_g_per_kg_low=8,
            carb_g_per_kg_high=12,
            window_hours=48,
            race_carb_g_per_h_low=60,
            race_carb_g_per_h_high=90,
        ),
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Described in physique literature; effect sizes small.",
                warning="Dehydration risk — never do this without supervision.",
            )
        ],
        checklist=["Pin race bib", "Bottle in fridge"],
        advice=[Guidance(text="Nothing new on race day.")],
    )
    assert protocol.days[-1].day_offset == 0
    assert protocol.practices[0].warning.startswith("Dehydration")


def test_days_must_be_sorted_unique_and_end_at_zero():
    with pytest.raises(ValidationError, match="day_offset"):
        _protocol(days=[_day(0), _day(-1)])
    with pytest.raises(ValidationError, match="day_offset"):
        _protocol(days=[_day(-1), _day(-1), _day(0)])
    with pytest.raises(ValidationError, match="J0"):
        _protocol(days=[_day(-2), _day(-1)])


def test_window_must_cover_the_days_span():
    with pytest.raises(ValidationError, match="window_days"):
        _protocol(window_days=1, days=[_day(-5), _day(0)])


def test_practice_requires_a_warning():
    with pytest.raises(ValidationError):
        DocumentedPractice(name="X", summary="Y", warning="")


def test_attempts_must_strictly_increase():
    with pytest.raises(ValidationError, match="increasing"):
        AttemptPlan(
            lift="Squat",
            e1rm_kg=200,
            opener_kg=190,
            second_kg=190,
            third_kg=200,
            basis="engine",
        )


def test_fueling_low_cannot_exceed_high():
    with pytest.raises(ValidationError, match="carb_g_per_kg"):
        FuelingPlan(carb_g_per_kg_low=10, carb_g_per_kg_high=8, window_hours=48)
