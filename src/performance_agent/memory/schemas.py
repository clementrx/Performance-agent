"""Pydantic schemas for the athlete data directory.

Structured facts live here with a strict contract (extra="forbid", bounded
values); free-text preferences go in Profile.notes. The schema is what makes
profile.yaml trustworthy for both humans and agents.

Timestamps are naive local wall-clock time; timezone-aware values are rejected.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from performance_agent.engine import TrainingAge

Locale = Literal["en", "fr", "es"]


def _require_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        msg = (
            "timestamps are naive local wall-clock time by design; "
            f"drop the timezone offset (got {value.isoformat()})"
        )
        raise ValueError(msg)
    return value


class Injury(BaseModel):
    """An injury record; the coach adapts around active injuries, never through them."""

    model_config = ConfigDict(extra="forbid")

    area: str
    description: str = ""
    status: Literal["active", "recovered"] = "active"
    noted_on: date


class Availability(BaseModel):
    """Weekly training availability."""

    model_config = ConfigDict(extra="forbid")

    sessions_per_week: int = Field(ge=1, le=14)
    minutes_per_session: int = Field(ge=10, le=480)


class SetPerformed(BaseModel):
    """One completed set. RIR = reps in reserve; None means not recorded."""

    model_config = ConfigDict(extra="forbid")

    reps: int = Field(ge=1, le=100)
    load_kg: float = Field(ge=0, le=1000)
    rir: int | None = Field(default=None, ge=0, le=10)


class ExercisePerformed(BaseModel):
    """One exercise within a session, with its sets in performed order."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    sets: list[SetPerformed] = Field(default_factory=list)
    notes: str | None = None


CalendarType = Literal["single_deadline", "recurring_fixtures", "open_ended"]


class LiftRecord(BaseModel):
    """A known 1RM for one lift; 'estimated' means derived via estimate_1rm, not tested."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1)
    one_rm_kg: float = Field(gt=0, le=1000)
    recorded_on: date
    source: Literal["tested", "estimated"] = "tested"


class Profile(BaseModel):
    """Athlete profile — structured facts only."""

    model_config = ConfigDict(extra="forbid")

    locale: Locale = "en"
    display_name: str | None = None
    birth_date: date | None = None
    sex: Literal["male", "female"] | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=250)
    training_age: TrainingAge | None = None
    sport: str | None = None
    discipline: str | None = None
    injuries: list[Injury] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    availability: Availability | None = None
    lift_inventory: list[LiftRecord] = Field(default_factory=list)
    body_fat_pct: float | None = Field(default=None, ge=3, le=60)
    calendar_type: CalendarType | None = None
    split_preferences: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    """A training goal with deadline and status."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    statement: str
    metric: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    deadline: date | None = None
    priority: Literal["A", "B", "C"] = "A"
    status: Literal["active", "achieved", "abandoned"] = "active"


class SessionEntry(BaseModel):
    """One completed training session (raw facts; loads are computed by engine tools)."""

    model_config = ConfigDict(extra="forbid")

    performed_at: datetime
    kind: str | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)
    duration_min: int | None = Field(default=None, ge=1)
    exercises: list[ExercisePerformed] = Field(default_factory=list)
    notes: str | None = None

    _naive_performed_at = field_validator("performed_at")(staticmethod(_require_naive))


class RepPR(BaseModel):
    """A rep personal record: best load for a rep count on a lift."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1)
    reps: int = Field(ge=1, le=100)
    load_kg: float = Field(gt=0, le=1000)
    achieved_on: date


class CheckinEntry(BaseModel):
    """One coaching check-in record."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    days_since_last: int | None = None
    adherence_pct: float | None = Field(default=None, ge=0, le=100)
    fatigue: int | None = Field(default=None, ge=1, le=10)
    pain_flags: list[str] = Field(default_factory=list)
    bodyweight_kg: float | None = Field(default=None, ge=30, le=250)
    measurements: dict[str, float] = Field(default_factory=dict)
    prs: list[RepPR] = Field(default_factory=list)
    notes: str | None = None

    _naive_at = field_validator("at")(staticmethod(_require_naive))
