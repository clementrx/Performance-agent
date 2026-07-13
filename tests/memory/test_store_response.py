"""Store tests for the versioned, immutable response-profile YAML documents."""

from datetime import date

import pytest

from performance_agent.memory.schemas import LiftRate, MeasuredRate, ResponseProfile
from performance_agent.memory.store import (
    latest_response_profile_version,
    read_response_profile,
    save_response_profile,
)

TODAY = date(2026, 7, 12)


def _profile() -> ResponseProfile:
    return ResponseProfile(
        as_of=TODAY,
        goal_id="squat-160",
        per_lift_rates=[
            LiftRate(lift="Back Squat", pct_per_week=0.005, r2=0.9, n=8, window_weeks=8)
        ],
        per_goal_measured_rate=MeasuredRate(value=0.005, n=8, window_weeks=8, r2=0.9),
        caveats=["measured rate from only 8 points: treat as provisional"],
    )


def test_no_profile_yet(tmp_path):
    assert latest_response_profile_version(tmp_path) is None
    assert read_response_profile(tmp_path) is None


def test_first_profile_writes_yaml(tmp_path):
    path, version = save_response_profile(tmp_path, _profile(), today=TODAY)
    assert version == 1
    assert path == tmp_path / "response" / "response-profile-v1.yaml"
    stored = read_response_profile(tmp_path)
    assert stored is not None
    assert stored.version == 1
    assert stored.as_of == TODAY
    assert stored.per_goal_measured_rate is not None
    assert stored.per_goal_measured_rate.value == pytest.approx(0.005)


def test_second_version_requires_reason(tmp_path):
    save_response_profile(tmp_path, _profile(), today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        save_response_profile(tmp_path, _profile(), today=TODAY)


def test_second_version_with_reason_stamps_it(tmp_path):
    save_response_profile(tmp_path, _profile(), today=TODAY)
    _, version = save_response_profile(
        tmp_path, _profile(), reason="mesocycle 1 end: measured 0.5%/week", today=TODAY
    )
    assert version == 2
    assert latest_response_profile_version(tmp_path) == 2
    stored = read_response_profile(tmp_path)
    assert stored is not None
    assert stored.reason == "mesocycle 1 end: measured 0.5%/week"


def test_versions_are_immutable_old_stays_readable(tmp_path):
    save_response_profile(tmp_path, _profile(), today=TODAY)
    save_response_profile(tmp_path, _profile(), reason="update", today=TODAY)
    v1 = read_response_profile(tmp_path, version=1)
    assert v1 is not None
    assert v1.version == 1
    assert v1.reason is None


def test_reading_missing_version_errors(tmp_path):
    save_response_profile(tmp_path, _profile(), today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read_response_profile(tmp_path, version=7)
