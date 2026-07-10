"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import (
    FeasibilityResult,
    TrainingAge,
    WeekLoad,
    acute_chronic_ratio,
    build_weekly_waves,
    endurance_feasibility,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    pace_s_per_km,
    riegel_predict,
    session_rpe_load,
    weekly_loads,
)

_ONE_RM_FORMULAS = {"brzycki": one_rm_brzycki, "epley": one_rm_epley}


class RacePrediction(TypedDict):
    """Predicted race time with its implied pace."""

    predicted_time_s: float
    pace_s_per_km: float


class Pace(TypedDict):
    """Running pace."""

    pace_s_per_km: float


class OneRmEstimate(TypedDict):
    """Estimated one-rep max and the formula that produced it."""

    one_rm_kg: float
    formula: Literal["epley", "brzycki"]


class LoadPrescription(TypedDict):
    """Absolute load for a percentage of 1RM."""

    load_kg: float


class SessionLoad(TypedDict):
    """Session-RPE training load."""

    session_load: float


class WeeklyLoads(TypedDict):
    """Daily loads summed into consecutive 7-day blocks."""

    weekly_totals: list[float]


class AcwrResult(TypedDict):
    """Acute:chronic workload ratio (null when history is insufficient)."""

    acute_chronic_ratio: float | None


class PeriodizationWaves(TypedDict):
    """Week-by-week volume/intensity multipliers."""

    weeks: list[WeekLoad]


def assess_endurance_goal(
    current_time_s: float, target_time_s: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of an endurance time goal (honest-coach verdict).

    Both times are in seconds over the same distance; training_age is one of
    beginner, intermediate, advanced. Returns the success probability (0-1)
    with the drivers behind it (improvement_needed, required vs achievable
    weekly rates, their ratio). Always present the drivers alongside the
    probability, never the bare number.
    """
    return endurance_feasibility(current_time_s, target_time_s, weeks, training_age)


def predict_race_time(
    known_distance_m: float, known_time_s: float, target_distance_m: float
) -> RacePrediction:
    """Predict a race time at a new distance from a known performance (Riegel).

    Distances must be within 1500-42195 m (enforced model validity band).
    Returns the predicted time in seconds and the implied pace in s/km.
    """
    predicted = riegel_predict(known_distance_m, known_time_s, target_distance_m)
    return RacePrediction(
        predicted_time_s=predicted,
        pace_s_per_km=pace_s_per_km(target_distance_m, predicted),
    )


def compute_pace(distance_m: float, time_s: float) -> Pace:
    """Return running pace in seconds per kilometre for a distance and time.

    distance_m and time_s must be positive.
    """
    return Pace(pace_s_per_km=pace_s_per_km(distance_m, time_s))


def estimate_1rm(
    load_kg: float, reps: int, formula: Literal["epley", "brzycki"] = "epley"
) -> OneRmEstimate:
    """Estimate a one-rep max in kg from a submaximal set (1-12 reps).

    Pick one formula per athlete and lift and stay consistent; do not average
    the two.
    """
    return OneRmEstimate(one_rm_kg=_ONE_RM_FORMULAS[formula](load_kg, reps), formula=formula)


def prescribe_load(one_rm_kg: float, percentage: float) -> LoadPrescription:
    """Return the absolute load in kg for a fraction of 1RM (e.g. 0.8 = 80%).

    percentage must be in (0, 1.3]; values above 1.0 are for supra-maximal
    work (eccentrics, partials).
    """
    return LoadPrescription(load_kg=load_for_percentage(one_rm_kg, percentage))


def compute_session_load(rpe: int, duration_min: int) -> SessionLoad:
    """Return Foster's session-RPE training load (CR-10 RPE x whole minutes).

    rpe must be 1-10; duration_min must be positive whole minutes.
    """
    return SessionLoad(session_load=session_rpe_load(rpe, duration_min))


def compute_weekly_loads(daily_loads: list[float]) -> WeeklyLoads:
    """Sum daily session loads into consecutive 7-day blocks.

    Loads must be finite and non-negative. Blocks are anchored at the first
    element (oldest day); a short final block contains the most recent days.
    """
    return WeeklyLoads(weekly_totals=weekly_loads(daily_loads))


def compute_acwr(daily_loads: list[float]) -> AcwrResult:
    """Acute:chronic workload ratio over the most recent 28 days (coupled variant).

    Returns null when history is shorter than 28 days or the chronic load is
    zero. Descriptive trend only — its injury-prediction validity is contested;
    never present it as an injury probability.
    """
    return AcwrResult(acute_chronic_ratio=acute_chronic_ratio(daily_loads))


def build_periodization_waves(
    total_weeks: int, deload_every: int = 4, taper_weeks: int = 1
) -> PeriodizationWaves:
    """Generate week-by-week volume/intensity multipliers for a training block.

    Building weeks ramp volume (+5%/wk) and intensity (+2.5%/wk) within each
    mesocycle; every deload_every-th building week is a deload (0.6 volume,
    0.9 intensity); the final taper_weeks weeks halve volume at baseline
    intensity. Factors are multipliers against a baseline week (1.0).
    """
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=taper_weeks)
    return PeriodizationWaves(weeks=waves)


def register(mcp: FastMCP) -> None:
    """Register every engine tool on the server."""
    for tool in (
        assess_endurance_goal,
        predict_race_time,
        compute_pace,
        estimate_1rm,
        prescribe_load,
        compute_session_load,
        compute_weekly_loads,
        compute_acwr,
        build_periodization_waves,
    ):
        mcp.tool()(tool)
