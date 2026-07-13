"""Tests for the training-residuals engine."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from performance_agent.engine.residuals import (
    QualityStimulus,
    check_residuals,
    residual_days,
)


def test_residual_days_known_and_default():
    assert residual_days("max_strength") == 30
    assert residual_days("speed") == 5
    assert residual_days("something_new") == 15


def test_no_warning_when_refreshed_in_time():
    # speed (5-day residual) trained every 4 days -> no decay.
    stimuli = [QualityStimulus(day_index=d, qualities=("speed",)) for d in (0, 4, 8, 12)]
    assert check_residuals(stimuli, horizon_days=12) == []


def test_warning_when_gap_exceeds_residual():
    # speed trained on day 0, then not again until day 20 (> 5-day residual).
    stimuli = [
        QualityStimulus(day_index=0, qualities=("speed",)),
        QualityStimulus(day_index=20, qualities=("speed",)),
    ]
    warnings = check_residuals(stimuli, horizon_days=20)
    assert len(warnings) == 1
    assert warnings[0].quality == "speed"
    assert warnings[0].gap_days == 20


def test_tail_gap_to_horizon_warns():
    # Trained once on day 0, horizon 40 -> the tail exceeds the 5-day residual.
    stimuli = [QualityStimulus(day_index=0, qualities=("speed",))]
    warnings = check_residuals(stimuli, horizon_days=40)
    assert warnings and warnings[0].quality == "speed"


def test_long_residual_quality_tolerates_wide_gaps():
    # max_strength holds 30 days; a 20-day gap is fine.
    stimuli = [
        QualityStimulus(day_index=0, qualities=("max_strength",)),
        QualityStimulus(day_index=20, qualities=("max_strength",)),
    ]
    assert check_residuals(stimuli, horizon_days=20) == []


def test_negative_horizon_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        check_residuals([], horizon_days=-1)


@given(extra=st.integers(min_value=0, max_value=30))
def test_extending_a_gap_never_removes_a_warning(extra):
    base = [
        QualityStimulus(day_index=0, qualities=("speed",)),
        QualityStimulus(day_index=10, qualities=("speed",)),
    ]
    widened = [
        QualityStimulus(day_index=0, qualities=("speed",)),
        QualityStimulus(day_index=10 + extra, qualities=("speed",)),
    ]
    base_warned = bool(check_residuals(base, horizon_days=10))
    widened_warned = bool(check_residuals(widened, horizon_days=10 + extra))
    # A wider gap can only add warnings, never remove the base one.
    if base_warned:
        assert widened_warned
