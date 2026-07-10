"""Pydantic schemas for the athlete data directory.

Structured facts live here with a strict contract (extra="forbid", bounded
values); free-text preferences go in Profile.notes. The schema is what makes
profile.yaml trustworthy for both humans and agents.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from performance_agent.engine import TrainingAge

Locale = Literal["en", "fr", "es"]


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
    notes: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    """A training goal with deadline and status."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
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
    notes: str | None = None


class CheckinEntry(BaseModel):
    """One coaching check-in record."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    days_since_last: int | None = None
    adherence_pct: float | None = Field(default=None, ge=0, le=100)
    fatigue: int | None = Field(default=None, ge=1, le=10)
    pain_flags: list[str] = Field(default_factory=list)
    notes: str | None = None
