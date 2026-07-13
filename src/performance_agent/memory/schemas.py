"""Pydantic schemas for the athlete data directory.

Structured facts live here with a strict contract (extra="forbid", bounded
values); free-text preferences go in Profile.notes. The schema is what makes
profile.yaml trustworthy for both humans and agents.

Timestamps are naive local wall-clock time; timezone-aware values are rejected.
"""

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from performance_agent.engine import TrainingAge

Locale = Literal["en", "fr", "es"]

_MONDAY = 0
_SUNDAY = 6


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
    weekdays: list[int] | None = None  # real training weekdays (0=Mon..6=Sun)

    @field_validator("weekdays")
    @classmethod
    def _weekdays_in_range_and_unique(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(day < _MONDAY or day > _SUNDAY for day in value):
            msg = f"weekdays must each be 0-6 (Mon-Sun), got {value}"
            raise ValueError(msg)
        if len(set(value)) != len(value):
            msg = f"weekdays must be unique, got {value}"
            raise ValueError(msg)
        return sorted(value)


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
    """One completed training session (raw facts; loads are computed by engine tools).

    source distinguishes work the coach programmed from external load the coach
    does not (club practice, matches, physical work) — external load still
    counts toward weekly totals. session_plan_id links a logged session back to
    its SessionPlan.id in the active program. avg_hr feeds sRPE estimation for
    sessions logged without a rated RPE. All three are optional for backward
    compatibility with pre-Phase-2 logs.
    """

    model_config = ConfigDict(extra="forbid")

    performed_at: datetime
    kind: str | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)
    duration_min: int | None = Field(default=None, ge=1)
    exercises: list[ExercisePerformed] = Field(default_factory=list)
    source: Literal["programmed", "external"] = "programmed"
    session_plan_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64
    )
    avg_hr: float | None = Field(default=None, gt=0, le=230)
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
    measurements: dict[
        Annotated[str, StringConstraints(min_length=1)],
        Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)],
    ] = Field(default_factory=dict)
    prs: list[RepPR] = Field(default_factory=list)
    notes: str | None = None

    _naive_at = field_validator("at")(staticmethod(_require_naive))


class ReadinessEntry(BaseModel):
    """One pre-session wellness read (Hooper items, optional HRV).

    Each Hooper item is 1 (best) to 7 (worst): sleep quality, fatigue, muscle
    soreness, stress. hrv_ms is an optional raw HRV measurement (e.g. rMSSD);
    the engine interprets HRV as a percent delta from baseline, computed by the
    caller. Appended to readiness.jsonl (schema_version 1).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    at: datetime
    sleep: int = Field(ge=1, le=7)
    fatigue: int = Field(ge=1, le=7)
    soreness: int = Field(ge=1, le=7)
    stress: int = Field(ge=1, le=7)
    hrv_ms: float | None = Field(default=None, gt=0, le=1000)
    notes: str | None = None

    _naive_at = field_validator("at")(staticmethod(_require_naive))


ReadinessBand = Literal["green", "amber", "red"]
AdjustmentKind = Literal["readiness", "time", "equipment", "manual"]


class AdjustmentInputs(BaseModel):
    """The trigger values behind a day-of adjustment (band / minutes / missing kit)."""

    model_config = ConfigDict(extra="forbid")

    band: ReadinessBand | None = None
    available_minutes: int | None = Field(default=None, ge=1, le=480)
    missing_equipment: list[str] = Field(default_factory=list)


class SessionAdjustmentEntry(BaseModel):
    """One day-of session adjustment (never a program version).

    kind records what drove it (readiness/time/equipment/manual); inputs holds
    the trigger values; deltas_summary is the machine-readable list of what
    changed; applied says whether the athlete took the adjusted session.
    Appended to session_adjustments.jsonl (schema_version 1).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    at: datetime
    session_plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    kind: AdjustmentKind
    inputs: AdjustmentInputs = Field(default_factory=AdjustmentInputs)
    deltas_summary: list[str] = Field(default_factory=list)
    applied: bool = True

    _naive_at = field_validator("at")(staticmethod(_require_naive))


# --- Structured programs (machine-readable source of truth) ---------------
#
# A program is a ProgramPlan tree; the markdown is a deterministic render of it
# (programs/render.py). Legacy prose-only program-vN.md files stay readable —
# a ProgramPlan is present only for versions saved after this format landed.

Quality = Literal[
    "strength_heavy",
    "hypertrophy",
    "power",
    "hiit",
    "tempo",
    "endurance_long",
    "endurance_easy",
    "brick",
    "recovery",
    "match",
    "club_practice",
    "test",
]
MesocyclePhase = Literal[
    "general_prep",
    "specific_prep",
    "accumulation",
    "intensification",
    "realization",
    "maintenance",
    "taper",
    "return_to_load",
]
TestProtocol = Literal["amrap_rir1", "timetrial", "one_rm_test"]
BlockPriority = Literal["primary", "secondary", "optional"]

# A block prescribes intensity through exactly one of these channels; setting
# more than one is contradictory (which number does the athlete chase?).
_INTENSITY_FIELDS = ("load_kg", "pct_1rm", "rir", "rpe", "pace_s_per_km")
# Every block must state its volume through at least one of these.
_VOLUME_FIELDS = ("reps", "duration_min", "distance_m")


class ExerciseBlock(BaseModel):
    """One prescribed exercise inside a session, with a single intensity mode."""

    model_config = ConfigDict(extra="forbid")

    exercise: str = Field(min_length=1)
    priority: BlockPriority
    warmup: Literal["auto", "none"] = "auto"
    sets: int = Field(ge=1, le=20)
    reps: str | None = Field(default=None, min_length=1, max_length=16)
    duration_min: float | None = Field(default=None, gt=0, le=600)
    distance_m: float | None = Field(default=None, gt=0, le=100000)
    load_kg: float | None = Field(default=None, ge=0, le=1000)
    pct_1rm: float | None = Field(default=None, gt=0, le=1.3)
    rir: float | None = Field(default=None, ge=0, le=10)
    rpe: float | None = Field(default=None, ge=1, le=10)
    pace_s_per_km: float | None = Field(default=None, gt=0, le=3600)
    rest_s: int | None = Field(default=None, ge=0, le=1800)
    progression_rule: str = Field(min_length=1)
    cite: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_intensity_and_some_volume(self) -> Self:
        set_intensity = [f for f in _INTENSITY_FIELDS if getattr(self, f) is not None]
        if len(set_intensity) > 1:
            msg = (
                "a block prescribes intensity through exactly one channel; "
                f"got {set_intensity} — pick one of {list(_INTENSITY_FIELDS)}"
            )
            raise ValueError(msg)
        if not any(getattr(self, f) is not None for f in _VOLUME_FIELDS):
            msg = f"a block must state its volume via one of {list(_VOLUME_FIELDS)}"
            raise ValueError(msg)
        if self.pace_s_per_km is not None and self.reps is not None:
            msg = "pace_s_per_km is an endurance prescription; it cannot pair with reps"
            raise ValueError(msg)
        return self


class Fallbacks(BaseModel):
    """Self-serve contingencies printed with the session (authored, non-empty)."""

    model_config = ConfigDict(extra="forbid")

    low_readiness: str = Field(min_length=1)
    short_on_time: str = Field(min_length=1)
    missing_equipment: str = Field(min_length=1)


class SessionPlan(BaseModel):
    """One planned session: qualities, movement patterns, blocks, fallbacks."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    weekday: int | None = Field(default=None, ge=0, le=6)
    qualities: list[Quality] = Field(min_length=1)
    patterns: list[str] = Field(default_factory=list)
    est_minutes: int = Field(ge=1, le=480)
    purpose: str = Field(min_length=1)
    blocks: list[ExerciseBlock] = Field(min_length=1)
    fallbacks: Fallbacks


class WeekPlan(BaseModel):
    """One microcycle (7-day week is a documented modeling limit)."""

    model_config = ConfigDict(extra="forbid")

    week_index: int = Field(ge=1)
    is_deload: bool = False
    is_taper: bool = False
    volume_factor: float = Field(gt=0, le=2)
    intensity_factor: float = Field(gt=0, le=2)
    weekly_set_targets: (
        dict[
            Annotated[str, StringConstraints(min_length=1)],
            Annotated[int, Field(ge=0, le=60)],
        ]
        | None
    ) = None
    notes: str | None = None
    sessions: list[SessionPlan] = Field(default_factory=list)


class Mesocycle(BaseModel):
    """A block of weeks sharing one periodization phase."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    phase: MesocyclePhase
    weeks: list[WeekPlan] = Field(min_length=1)


class TestMilestone(BaseModel):
    """A scheduled re-test that feeds the response profile and next version."""

    __test__ = False  # not a pytest test class despite the Test* name

    model_config = ConfigDict(extra="forbid")

    week_index: int = Field(ge=1)
    protocol: TestProtocol
    targets: list[str] = Field(min_length=1)


class ProgramPlan(BaseModel):
    """Structured program: the source of truth the markdown is rendered from."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    version: int = Field(ge=1)
    goal_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    created_on: date
    reason: str | None = None
    checkin_cadence_days: int = Field(default=7, ge=1, le=90)
    season_ref: str | None = None
    test_milestones: list[TestMilestone] = Field(default_factory=list)
    mesocycles: list[Mesocycle] = Field(min_length=1)

    @model_validator(mode="after")
    def _week_indices_are_globally_increasing(self) -> Self:
        indices = [week.week_index for meso in self.mesocycles for week in meso.weeks]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            msg = f"week_index must be globally unique and increasing, got {indices}"
            raise ValueError(msg)
        return self


# --- Season calendar (dated events + weekly recurring constraints) --------
#
# calendar.yaml is the scheduling source of truth; the season planner reads it
# to build the program backward from real dates.

CalendarEventKind = Literal["competition", "test", "camp", "travel", "holiday", "other"]
RecurringKind = Literal["club_practice", "match_day", "unavailable"]


class CalendarEvent(BaseModel):
    """One dated event on the athlete's season calendar."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    date: date
    kind: CalendarEventKind
    priority: Literal["A", "B", "C"]
    label: str = Field(min_length=1)
    goal_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    sport: str | None = None
    notes: str | None = None


class RecurringConstraint(BaseModel):
    """A weekly recurring commitment the program must plan around."""

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)  # 0 = Monday
    kind: RecurringKind
    est_minutes: int | None = Field(default=None, ge=1, le=480)
    est_srpe: float | None = Field(default=None, ge=1, le=10)  # CR-10 session RPE
    label: str = Field(min_length=1)


class Calendar(BaseModel):
    """The athlete's dated events and weekly recurring constraints."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    events: list[CalendarEvent] = Field(default_factory=list)
    recurring: list[RecurringConstraint] = Field(default_factory=list)


# --- Individual response profile (versioned, immutable, honest about n) ----
#
# response/response-profile-v{N}.yaml distils the athlete's own logged response
# into measured rates, tolerance flags and adherence. Every measured field
# carries its sample size (n, window_weeks, r2) so a thin number is never
# presented as solid; caveats spell out where population priors still stand in.

ToleranceDirection = Literal[
    "higher_volume_higher_fatigue", "higher_volume_lower_fatigue", "no_clear_direction"
]


class LiftRate(BaseModel):
    """A measured weekly progression rate for one lift, with its sample size."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1)
    pct_per_week: float
    r2: float = Field(ge=0, le=1)
    n: int = Field(ge=1)
    window_weeks: float = Field(gt=0)


class MeasuredRate(BaseModel):
    """The goal's measured weekly rate (fraction/week or kg/week) with its n."""

    model_config = ConfigDict(extra="forbid")

    value: float
    n: int = Field(ge=1)
    window_weeks: float = Field(gt=0)
    r2: float = Field(ge=0, le=1)


class VolumeToleranceFlag(BaseModel):
    """A descriptive association between weekly volume and fatigue (never causal)."""

    model_config = ConfigDict(extra="forbid")

    direction: ToleranceDirection
    correlation: float = Field(ge=-1, le=1)
    n_weeks: int = Field(ge=1)


class AdherenceQuality(BaseModel):
    """Compliance rolled up for one quality tag."""

    model_config = ConfigDict(extra="forbid")

    quality: str = Field(min_length=1)
    done: int = Field(ge=0)
    partial: int = Field(ge=0)
    modified: int = Field(ge=0)
    missed: int = Field(ge=0)
    adherence_pct: float = Field(ge=0, le=100)


class ResponseProfile(BaseModel):
    """The athlete's individual response model, versioned and immutable.

    per_goal_measured_rate is None until enough data exists (honesty about n);
    caveats record every place a population prior still stands in. The store
    stamps version/as_of/reason; a reason is mandatory from v2.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    version: int = Field(default=1, ge=1)
    as_of: date
    goal_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    reason: str | None = None
    per_lift_rates: list[LiftRate] = Field(default_factory=list)
    per_goal_measured_rate: MeasuredRate | None = None
    volume_tolerance_flags: list[VolumeToleranceFlag] = Field(default_factory=list)
    adherence_by_quality: list[AdherenceQuality] = Field(default_factory=list)
    adjustment_patterns: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# --- PerformanceModel (sport-agnostic determinants, researched & versioned) -
#
# models/performance-model-v{N}.yaml is the structured answer to "what
# determines performance in this event". The LLM researches the literature and
# proposes; the engine validates, normalizes weights, and computes gaps against
# it. Every value the LLM fills carries a Provenance label so a report can show
# whether a number is cited, a team-chosen prior, or coaching judgment.

ProvenanceKind = Literal["cited", "prior", "judgment"]

# Generic, trainable body-quality axes. This enum is the contract: the LLM
# cannot invent qualities. Sport-specific expression belongs in KpiSpec
# protocols, not in new quality names. (Named PerformanceQuality to avoid
# collision with the session-tag Quality literal above.)
PerformanceQuality = Literal[
    "max_strength",
    "explosive_strength",
    "reactive_strength",
    "speed",
    "acceleration",
    "change_of_direction",
    "aerobic_capacity",
    "anaerobic_capacity",
    "muscular_endurance",
    "hypertrophy",
    "mobility",
    "balance_stability",
]

BenchmarkLevel = Literal["recreational", "competitive", "national", "elite"]

_ENERGY_SUM_TOLERANCE = 0.02


class Provenance(BaseModel):
    """Where a structured value came from: cited requires ≥1 corpus id."""

    model_config = ConfigDict(extra="forbid")

    kind: ProvenanceKind
    cite_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cited_requires_ids(self) -> Self:
        if self.kind == "cited" and not self.cite_ids:
            msg = "cited provenance requires at least one cite_id (never invent citations)"
            raise ValueError(msg)
        if self.kind != "cited" and self.cite_ids:
            msg = f"{self.kind} provenance must not carry cite_ids (only 'cited' may)"
            raise ValueError(msg)
        return self


class QualityRequirement(BaseModel):
    """One trainable quality's importance to the event (weights normalized at the model)."""

    model_config = ConfigDict(extra="forbid")

    quality: PerformanceQuality
    weight: float = Field(ge=0, le=1)
    provenance: Provenance
    rationale: str = ""


class Benchmark(BaseModel):
    """A performance standard for one competitive level, with its provenance."""

    model_config = ConfigDict(extra="forbid")

    level: BenchmarkLevel
    value: float = Field(allow_inf_nan=False)
    provenance: Provenance


class KpiSpec(BaseModel):
    """A measurable indicator linked to a quality, with a test protocol and benchmarks."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    name: str = Field(min_length=1)
    quality: PerformanceQuality
    protocol: str = Field(min_length=1)
    test_protocol: TestProtocol | None = None
    unit: str = Field(min_length=1)
    benchmarks: list[Benchmark] = Field(default_factory=list)

    @model_validator(mode="after")
    def _benchmark_levels_unique(self) -> Self:
        levels = [b.level for b in self.benchmarks]
        if len(set(levels)) != len(levels):
            msg = f"KPI {self.id} has duplicate benchmark levels: {levels}"
            raise ValueError(msg)
        return self


class InjuryRiskEntry(BaseModel):
    """A region-specific injury risk with its mechanism and a screening cue."""

    model_config = ConfigDict(extra="forbid")

    region: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    screen: str = Field(min_length=1)
    provenance: Provenance


class EnergySystemSplit(BaseModel):
    """Approximate energy-system contributions (fractions summing to ≈1)."""

    model_config = ConfigDict(extra="forbid")

    aerobic: float = Field(ge=0, le=1)
    anaerobic_lactic: float = Field(ge=0, le=1)
    anaerobic_alactic: float = Field(ge=0, le=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _fractions_sum_to_one(self) -> Self:
        total = self.aerobic + self.anaerobic_lactic + self.anaerobic_alactic
        if abs(total - 1.0) > _ENERGY_SUM_TOLERANCE:
            msg = f"energy-system fractions must sum to ≈1 (got {total:.3f})"
            raise ValueError(msg)
        return self


class PerformanceModel(BaseModel):
    """Sport-agnostic determinants of one event, versioned and immutable.

    qualities weights are normalized to sum to 1 at validation (the raw weights
    the LLM proposes need not sum to 1). The store stamps version/reason; a
    reason is mandatory from v2. schema_version guards forward compatibility.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    version: int = Field(default=1, ge=1)
    discipline: str = Field(min_length=1)
    event: str = Field(min_length=1)
    reason: str | None = None
    qualities: list[QualityRequirement] = Field(min_length=1)
    kpis: list[KpiSpec] = Field(default_factory=list)
    injury_risks: list[InjuryRiskEntry] = Field(default_factory=list)
    energy_systems: EnergySystemSplit | None = None
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_quality_weights(self) -> Self:
        total = sum(q.weight for q in self.qualities)
        if total <= 0:
            msg = "quality weights are not normalizable (they sum to 0); give at least one > 0"
            raise ValueError(msg)
        for requirement in self.qualities:
            requirement.weight = requirement.weight / total
        return self

    @model_validator(mode="after")
    def _kpi_ids_unique(self) -> Self:
        ids = [k.id for k in self.kpis]
        if len(set(ids)) != len(ids):
            msg = f"KPI ids must be unique within a model, got {ids}"
            raise ValueError(msg)
        return self
