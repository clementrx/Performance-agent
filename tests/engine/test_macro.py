"""Tests for the multi-year macrocycle engine."""

import pytest

from performance_agent.engine.macro import (
    QualityPriorityInput,
    build_macro_years,
)

_PRIORITIES = [
    QualityPriorityInput("max_strength", 0.5),
    QualityPriorityInput("speed", 0.3),
    QualityPriorityInput("aerobic_capacity", 0.2),
]


def test_year_typing_two_years():
    years = build_macro_years(2, _PRIORITIES)
    assert [y.year_type for y in years] == ["development", "realization"]


def test_year_typing_four_years():
    years = build_macro_years(4, _PRIORITIES)
    assert [y.year_type for y in years] == [
        "development",
        "development",
        "qualification",
        "realization",
    ]


def test_year_typing_one_year_is_realization():
    years = build_macro_years(1, _PRIORITIES)
    assert years[0].year_type == "realization"


def test_development_biases_general():
    years = build_macro_years(2, _PRIORITIES)
    dev = dict(years[0].quality_emphases)
    real = dict(years[1].quality_emphases)
    # max_strength (general) weighs relatively more in development than realization.
    assert dev["max_strength"] > real["max_strength"]
    # speed (specific) weighs relatively more in realization than development.
    assert real["speed"] > dev["speed"]


def test_emphases_normalized():
    years = build_macro_years(3, _PRIORITIES)
    for year in years:
        assert sum(w for _, w in year.quality_emphases) == pytest.approx(1.0)


def test_horizon_out_of_range_rejected():
    with pytest.raises(ValueError, match="horizon_years must be 1-4"):
        build_macro_years(5, _PRIORITIES)


def test_no_positive_priority_gives_empty_emphases():
    years = build_macro_years(1, [QualityPriorityInput("speed", 0.0)])
    assert years[0].quality_emphases == ()
