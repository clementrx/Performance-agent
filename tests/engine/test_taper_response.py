"""Tests for the individual taper-response engine."""

from performance_agent.engine.taper_response import (
    TaperEvent,
    detect_taper,
    fit_taper_response,
)


def _loads_with_tapers(taper_days_before):
    loads = [420.0] * 120
    for event in taper_days_before:
        for day in range(event - 7, event):
            loads[day] = 60.0
    return loads


def test_detect_taper_duration_and_reduction():
    loads = _loads_with_tapers([40])
    detected = detect_taper(loads, 40)
    assert detected is not None
    duration, reduction = detected
    assert duration == 7
    assert reduction > 0.8


def test_detect_none_without_history():
    loads = [420.0] * 120
    assert detect_taper(loads, 10) is None  # not enough pre-event baseline


def test_detect_none_when_no_taper():
    loads = [420.0] * 120
    assert detect_taper(loads, 60) is None


def test_fit_population_when_few_outcomes():
    loads = _loads_with_tapers([40])
    events = [TaperEvent(day_index=40, outcome=500.0)]
    response = fit_taper_response(loads, events, generic_duration_days=10)
    assert response.basis == "population"
    assert response.recommended_duration_days is None
    assert response.n_with_outcome == 1


def test_fit_individual_with_two_outcomes():
    loads = _loads_with_tapers([40, 90])
    events = [
        TaperEvent(day_index=40, outcome=500.0),
        TaperEvent(day_index=90, outcome=520.0),
    ]
    response = fit_taper_response(loads, events, generic_duration_days=10)
    assert response.basis == "individual"
    assert response.recommended_duration_days == 7
    assert response.n_with_outcome == 2


def test_fit_best_outcome_selected():
    # Two tapers of different depths; the better-outcome one drives the recommendation.
    loads = [420.0] * 120
    for day in range(33, 40):
        loads[day] = 60.0  # deep 7-day taper before event 40
    for day in range(84, 90):
        loads[day] = 200.0  # shallower 6-day taper before event 90
    events = [
        TaperEvent(day_index=40, outcome=480.0),
        TaperEvent(day_index=90, outcome=520.0),  # better outcome
    ]
    response = fit_taper_response(loads, events, generic_duration_days=10)
    assert response.basis == "individual"
    assert response.recommended_duration_days == 6  # from the better-outcome taper


def test_fit_no_tapers_detected_is_population():
    loads = [420.0] * 120
    events = [TaperEvent(day_index=40, outcome=500.0), TaperEvent(day_index=90, outcome=520.0)]
    response = fit_taper_response(loads, events, generic_duration_days=10)
    assert response.n_detected == 0
    assert response.basis == "population"
