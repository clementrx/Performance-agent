from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from performance_agent.engine import TrainingAge
from performance_agent.memory.schemas import (
    CheckinEntry,
    Goal,
    Injury,
    Profile,
    SessionEntry,
)


def test_default_profile_is_valid_and_english():
    profile = Profile()
    assert profile.locale == "en"
    assert profile.injuries == []
    assert profile.equipment == []


def test_profile_accepts_structured_facts():
    profile = Profile(
        locale="fr",
        display_name="Clément",
        birth_date=date(1990, 5, 1),
        sex="male",
        height_cm=180,
        weight_kg=75,
        training_age=TrainingAge.INTERMEDIATE,
        sport="running",
        injuries=[Injury(area="left knee", noted_on=date(2026, 6, 1))],
        equipment=["barbell", "rack"],
        notes=["prefers morning sessions"],
    )
    assert profile.training_age is TrainingAge.INTERMEDIATE
    assert profile.injuries[0].status == "active"


@pytest.mark.parametrize(
    ("field", "value"),
    [("locale", "de"), ("height_cm", 30), ("weight_kg", 500), ("sex", "other")],
)
def test_profile_rejects_out_of_contract_values(field, value):
    with pytest.raises(ValidationError):
        Profile(**{field: value})


def test_profile_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Profile(favourite_color="blue")  # ty: ignore[unknown-argument]


def test_goal_defaults_and_id_pattern():
    goal = Goal(id="sub-45-10k", statement="10K under 45:00")
    assert goal.priority == "A"
    assert goal.status == "active"
    with pytest.raises(ValidationError):
        Goal(id="Bad Id!", statement="x")


def test_session_entry_bounds():
    entry = SessionEntry(performed_at=datetime(2026, 7, 10, 18, 0), rpe=7, duration_min=60)
    assert entry.rpe == 7
    with pytest.raises(ValidationError):
        SessionEntry(performed_at=datetime(2026, 7, 10), rpe=11)


def test_aware_datetimes_are_rejected_with_guidance():
    with pytest.raises(ValidationError, match="naive local"):
        SessionEntry(performed_at=datetime(2026, 7, 10, 18, 0, tzinfo=UTC))
    with pytest.raises(ValidationError, match="naive local"):
        CheckinEntry(at=datetime(2026, 7, 10, 9, 0, tzinfo=UTC))


def test_goal_id_length_is_bounded():
    with pytest.raises(ValidationError):
        Goal(id="a" * 65, statement="x")


def test_checkin_entry_bounds():
    entry = CheckinEntry(at=datetime(2026, 7, 10, 9, 0), adherence_pct=80, fatigue=4)
    assert entry.pain_flags == []
    with pytest.raises(ValidationError):
        CheckinEntry(at=datetime(2026, 7, 10), adherence_pct=140)
