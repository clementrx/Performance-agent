"""Tests for the specificity fit and mesocycle mix check."""

import pytest

from performance_agent.engine.specificity import (
    check_specificity_mix,
    specificity_fit,
)


def test_fit_is_one_inside_band():
    assert specificity_fit("general", "general_prep") == 1.0
    assert specificity_fit("competition", "realization") == 1.0


def test_fit_decays_with_distance():
    # realization band is specific..competition; general is 2 steps below specific.
    far = specificity_fit("general", "realization")
    near = specificity_fit("special", "realization")
    assert 0.0 <= far < near < 1.0


def test_unknown_specificity_rejected():
    with pytest.raises(ValueError, match="unknown specificity"):
        specificity_fit("olympic", "general_prep")


def test_mix_ok_returns_none():
    assert check_specificity_mix("general_prep", ["general", "general", "special"]) is None


def test_mix_out_of_band_warns():
    warning = check_specificity_mix(
        "general_prep", ["competition", "competition", "competition", "general"]
    )
    assert warning is not None
    assert warning.out_of_band == 3
    assert warning.total == 4


def test_empty_mix_is_none():
    assert check_specificity_mix("realization", []) is None


def test_unknown_phase_uses_default_band():
    # An unknown phase accepts the whole 0-3 range, so nothing is out of band.
    assert specificity_fit("general", "made_up_phase") == 1.0
    assert check_specificity_mix("made_up_phase", ["general", "competition"]) is None
