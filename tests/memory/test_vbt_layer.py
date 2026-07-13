"""Athlete-layer tests: load-velocity profiling from logged VBT sets."""

from datetime import datetime

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import SessionEntry, VbtSet
from performance_agent.memory.vbt import fit_exercise_profile, velocity_suggestion


def _log_vbt(base_dir, loads_velocities, exercise="Back Squat"):
    for i, (load, vel) in enumerate(loads_velocities):
        store.append_session(
            base_dir,
            SessionEntry(
                performed_at=datetime(2026, 7, 1 + i, 10, 0),
                vbt_sets=[VbtSet(exercise=exercise, load_kg=load, mean_velocity=vel, reps=1)],
            ),
        )


def test_fit_requires_two_sets(tmp_path):
    _log_vbt(tmp_path, [(100, 0.9)])
    with pytest.raises(ValueError, match="at least 2 logged VBT sets"):
        fit_exercise_profile(tmp_path, "Back Squat")


def test_fit_usable_profile(tmp_path):
    _log_vbt(tmp_path, [(60, 1.14), (100, 0.9), (140, 0.66), (180, 0.42)])
    view = fit_exercise_profile(tmp_path, "Back Squat")
    assert view["usable"]
    assert view["n_points"] == 4
    assert view["e1rm_kg"] == pytest.approx(200.0, abs=2.0)


def test_fit_under_spread_refused(tmp_path):
    _log_vbt(tmp_path, [(100, 0.9), (105, 0.87), (110, 0.84), (115, 0.81)])
    view = fit_exercise_profile(tmp_path, "Back Squat")
    assert not view["usable"]
    assert view["reason"] is not None


def test_velocity_suggestion_none_without_profile(tmp_path):
    # Only one set -> no usable profile -> no suggestion (degradation invariant).
    _log_vbt(tmp_path, [(100, 0.9)])
    assert velocity_suggestion(tmp_path, "Back Squat", 100, 0.9) is None


def test_velocity_suggestion_slow_day_backs_off(tmp_path):
    _log_vbt(tmp_path, [(60, 1.14), (100, 0.9), (140, 0.66), (180, 0.42)])
    # A warm-up slower than the profile predicts -> back off.
    suggestion = velocity_suggestion(tmp_path, "Back Squat", 100, 0.78)
    assert suggestion is not None
    assert suggestion["pct_change"] < 0
    assert suggestion["ratio"] >= 0.9  # bounded to -10%


def test_velocity_suggestion_strong_day_nudges_up(tmp_path):
    _log_vbt(tmp_path, [(60, 1.14), (100, 0.9), (140, 0.66), (180, 0.42)])
    suggestion = velocity_suggestion(tmp_path, "Back Squat", 100, 0.96)
    assert suggestion is not None
    assert suggestion["pct_change"] > 0
