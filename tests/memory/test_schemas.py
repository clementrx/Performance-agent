from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from performance_agent.engine import TrainingAge
from performance_agent.memory.schemas import (
    CheckinEntry,
    ExercisePerformed,
    Goal,
    Injury,
    LiftRecord,
    Profile,
    RepPR,
    SessionEntry,
    SetPerformed,
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


def test_session_entry_accepts_structured_exercises():
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 11, 18, 0),
        kind="strength",
        exercises=[
            ExercisePerformed(
                name="back squat",
                sets=[
                    SetPerformed(reps=5, load_kg=100, rir=2),
                    SetPerformed(reps=5, load_kg=100, rir=1),
                ],
            )
        ],
    )
    assert entry.exercises[0].sets[1].rir == 1


def test_session_entry_without_exercises_still_valid():
    entry = SessionEntry(performed_at=datetime(2026, 7, 11, 7, 0), kind="easy run", rpe=4)
    assert entry.exercises == []


def test_set_performed_bounds():
    with pytest.raises(ValidationError):
        SetPerformed(reps=0, load_kg=100)
    with pytest.raises(ValidationError):
        SetPerformed(reps=5, load_kg=-1)
    with pytest.raises(ValidationError):
        SetPerformed(reps=5, load_kg=100, rir=11)
    with pytest.raises(ValidationError):
        SetPerformed(reps=101, load_kg=100)
    with pytest.raises(ValidationError):
        SetPerformed(reps=5, load_kg=1001)


def test_exercise_performed_requires_name_and_rejects_extras():
    with pytest.raises(ValidationError):
        ExercisePerformed(name="", sets=[])
    with pytest.raises(ValidationError):
        ExercisePerformed(name="bench press", sets=[], tempo="3010")  # ty: ignore[unknown-argument]


def test_profile_accepts_lift_inventory_and_bodycomp():
    profile = Profile(
        body_fat_pct=18.5,
        calendar_type="single_deadline",
        split_preferences=["upper/lower"],
        lift_inventory=[
            LiftRecord(lift="back squat", one_rm_kg=140, recorded_on=date(2026, 7, 1)),
            LiftRecord(
                lift="bench press",
                one_rm_kg=100,
                recorded_on=date(2026, 7, 1),
                source="estimated",
            ),
        ],
    )
    assert profile.lift_inventory[1].source == "estimated"
    assert profile.calendar_type == "single_deadline"


def test_profile_connected_services_optional():
    assert Profile().connected_services == []
    assert Profile(connected_services=["garmin", "strava"]).connected_services == [
        "garmin",
        "strava",
    ]


def test_lift_record_defaults_to_tested_and_bounds():
    record = LiftRecord(lift="deadlift", one_rm_kg=180, recorded_on=date(2026, 7, 1))
    assert record.source == "tested"
    with pytest.raises(ValidationError):
        LiftRecord(lift="deadlift", one_rm_kg=0, recorded_on=date(2026, 7, 1))


@pytest.mark.parametrize(
    ("field", "value"),
    [("body_fat_pct", 1), ("body_fat_pct", 80), ("calendar_type", "seasonal")],
)
def test_profile_rejects_out_of_contract_new_fields(field, value):
    with pytest.raises(ValidationError):
        Profile(**{field: value})


def test_checkin_accepts_bodyweight_measurements_and_prs():
    entry = CheckinEntry(
        at=datetime(2026, 7, 11, 9, 0),
        bodyweight_kg=79.4,
        measurements={"waist": 84.0},
        prs=[RepPR(lift="bench press", reps=5, load_kg=90, achieved_on=date(2026, 7, 9))],
    )
    assert entry.measurements["waist"] == 84.0
    assert entry.prs[0].reps == 5


def test_checkin_new_fields_are_optional():
    entry = CheckinEntry(at=datetime(2026, 7, 11, 9, 0), fatigue=3)
    assert entry.bodyweight_kg is None
    assert entry.measurements == {}
    assert entry.prs == []


def test_checkin_bodyweight_bounds():
    with pytest.raises(ValidationError):
        CheckinEntry(at=datetime(2026, 7, 11, 9, 0), bodyweight_kg=10)


@pytest.mark.parametrize(
    "measurements",
    [{"waist": float("nan")}, {"waist": -5.0}, {"waist": 600.0}, {"": 84.0}],
)
def test_checkin_measurements_are_bounded(measurements):
    with pytest.raises(ValidationError):
        CheckinEntry(at=datetime(2026, 7, 11, 9, 0), measurements=measurements)
