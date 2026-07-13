"""Consolidated cross-cutting property tests (Phase 9).

One place that re-asserts the invariants the fitted/selection/residual engines rely
on, so a regression in any of them fails a single, obvious suite. Each module also
has its own focused property tests; these are the cross-cutting guarantees.
"""

import math

from hypothesis import assume, given
from hypothesis import strategies as st

from performance_agent.engine.banister import PerformancePoint, _decay_trace, fit_banister
from performance_agent.engine.exercise_selection import (
    Candidate,
    QualityTarget,
    score_exercises,
)
from performance_agent.engine.residuals import QualityStimulus, check_residuals
from performance_agent.engine.vbt import LoadVelocityPoint, fit_load_velocity


@given(
    slope=st.floats(min_value=-0.007, max_value=-0.003),
    intercept=st.floats(min_value=1.3, max_value=1.9),
)
def test_load_velocity_recovers_slope(slope, intercept):
    loads = [50, 90, 130, 170, 210]
    velocities = [intercept + slope * x for x in loads]
    assume(min(velocities) > 0.15)
    points = [
        LoadVelocityPoint(load_kg=x, mean_velocity=v)
        for x, v in zip(loads, velocities, strict=True)
    ]
    profile = fit_load_velocity(points)
    if profile.usable:
        assert abs(profile.slope - slope) < 0.005


@given(
    k1=st.floats(min_value=0.05, max_value=0.15),
    k2=st.floats(min_value=0.08, max_value=0.20),
)
def test_banister_reproduces_data(k1, k2):
    loads = [80.0 + 10.0 * math.sin(i / 4.0) for i in range(84)]
    g1, g2 = _decay_trace(loads, 40.0), _decay_trace(loads, 8.0)
    days = [10, 25, 40, 55, 70, 82]
    points = [PerformancePoint(day_index=d, value=100.0 + k1 * g1[d] - k2 * g2[d]) for d in days]
    fit = fit_banister(loads, points)
    if fit.usable:
        assert fit.r2 > 0.9
        assert fit.tau1 > fit.tau2


def _candidate(cid, contra=()):
    return Candidate(
        exercise_id=cid,
        name=cid,
        patterns=("squat",),
        force_vector="axial",
        contraction_regime="concentric_dominant",
        equipment=(),
        specificity_level="special",
        qualities_trained=(("max_strength", 0.8),),
        contraindications=tuple(contra),
        skill_complexity=2,
    )


@given(region=st.sampled_from(["knee", "shoulder", "hip"]))
def test_selection_contraindication_never_raises_score(region):
    candidate = _candidate("c", contra=(region,))
    targets = [QualityTarget("max_strength", 1.0)]
    without = score_exercises([candidate], targets, "specific_prep", [], [])[0].score
    with_contra = score_exercises([candidate], targets, "specific_prep", [], [region])[0].score
    assert with_contra <= without


@given(extra=st.integers(min_value=0, max_value=40))
def test_residual_gap_extension_never_removes_warning(extra):
    base = [QualityStimulus(0, ("speed",)), QualityStimulus(8, ("speed",))]
    widened = [QualityStimulus(0, ("speed",)), QualityStimulus(8 + extra, ("speed",))]
    if check_residuals(base, 8):
        assert check_residuals(widened, 8 + extra)
