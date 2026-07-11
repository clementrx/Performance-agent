"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import (
    BodycompFeasibility,
    FeasibilityResult,
    ProgressionDecision,
    TrainingAge,
    WeekLoad,
    WeeklySetTargets,
    acute_chronic_ratio,
    bodycomp_feasibility,
    build_weekly_waves,
    double_progression,
    endurance_feasibility,
    hypertrophy_feasibility,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    pace_s_per_km,
    percentage_for_reps_rir,
    riegel_predict,
    session_rpe_load,
    strength_feasibility,
    weekly_loads,
)
from performance_agent.engine import weekly_set_targets as engine_weekly_set_targets

_ONE_RM_FORMULAS = {
    "brzycki": one_rm_brzycki,
    "epley": one_rm_epley,
    "lombardi": one_rm_lombardi,
    "wathan": one_rm_wathan,
}


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
    formula: Literal["epley", "brzycki", "lombardi", "wathan"]


class LoadPrescription(TypedDict):
    """Absolute load for a percentage of 1RM."""

    load_kg: float


class RepsLoadPrescription(TypedDict):
    """Percentage of 1RM and absolute load for a reps-at-RIR prescription."""

    percentage: float
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


def assess_strength_goal(
    current_one_rm_kg: float, target_one_rm_kg: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of a strength (1RM) goal (honest-coach verdict).

    Both loads are in kg for the same lift; training_age is one of beginner,
    intermediate, advanced. Sign convention: improvement_needed is positive
    when the target is above the current 1RM. Returns the success
    probability (0-1) with the drivers behind it (improvement_needed,
    required vs achievable weekly rates as fractions of current 1RM, their
    ratio). Always present the drivers alongside the probability, never the
    bare number.
    """
    return strength_feasibility(current_one_rm_kg, target_one_rm_kg, weeks, training_age)


def assess_hypertrophy_goal(
    target_lean_gain_kg: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of a lean-mass gain goal (honest-coach verdict).

    target_lean_gain_kg is lean mass in kg (positive); rates are ABSOLUTE
    kg/week, not fractions — improvement_needed carries the target gain in
    kg. Returns the success probability (0-1) with the drivers behind it
    (required vs achievable kg/week, their ratio). Always present the
    drivers alongside the probability, never the bare number.
    """
    return hypertrophy_feasibility(target_lean_gain_kg, weeks, training_age)


def assess_bodycomp_goal(
    current_weight_kg: float,
    current_body_fat_pct: float,
    target_body_fat_pct: float,
    weeks: int,
    sex: Literal["male", "female"],
) -> BodycompFeasibility:
    """Score the feasibility of a fat-loss goal (honest-coach verdict).

    Weight in kg; body-fat percentages in (3, 60) with target below current.
    REFUSES targets below the healthy minimum for the athlete's sex (5% male,
    12% female) with an error telling you to refer to a health professional —
    relay that refusal, do not work around it. exceeds_safe_rate=True means
    the deadline demands more than 1% bodyweight/week and risks muscle loss;
    say so explicitly. Always present the drivers (fat_mass_to_lose_kg,
    required vs achievable weekly loss as fractions of bodyweight, their
    ratio) alongside the probability, never the bare number.
    """
    return bodycomp_feasibility(
        current_weight_kg, current_body_fat_pct, target_body_fat_pct, weeks, sex
    )


def prescribe_reps_load(one_rm_kg: float, reps: int, rir: int) -> RepsLoadPrescription:
    """Prescribe the %1RM and absolute load for a reps-at-RIR target.

    Epley-based: percentage = 1 / (1 + (reps + rir) / 30). Effective reps
    (reps + rir) are capped at 18, and the model is only validated to ~12 —
    when reps + rir is 13-18, label the prescription as carrying extra
    uncertainty. Returns the fraction of 1RM and the load in kg.
    """
    percentage = percentage_for_reps_rir(reps, rir)
    return RepsLoadPrescription(
        percentage=percentage, load_kg=load_for_percentage(one_rm_kg, percentage)
    )


def weekly_set_targets_for(training_age: TrainingAge) -> WeeklySetTargets:
    """Weekly hard-set targets per muscle group for a training-age bucket.

    Returns minimum_effective_sets, optimal_low_sets-optimal_high_sets (the
    range to program), and maximum_adaptive_sets (do not exceed), all in
    weekly hard sets per muscle group. Anchored on the volume dose-response
    meta-analysis in the corpus; the training-age spread is a team-chosen
    prior.
    """
    return engine_weekly_set_targets(training_age)


def progress_double_progression(
    reps_achieved: list[int],
    load_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    increment_kg: float,
) -> ProgressionDecision:
    """Decide the next session's load and rep target by double progression.

    Fill the rep range first, then add load: when every set reached
    rep_range_high, the load goes up by increment_kg and the target resets
    to rep_range_low; otherwise the load holds and the target is one rep
    above the lowest achieved set, capped at rep_range_high. Loads in kg;
    rep range must satisfy 1 <= low < high <= 18.
    """
    return double_progression(reps_achieved, load_kg, rep_range_low, rep_range_high, increment_kg)


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
    load_kg: float,
    reps: int,
    formula: Literal["epley", "brzycki", "lombardi", "wathan"] = "epley",
) -> OneRmEstimate:
    """Estimate a one-rep max in kg from a submaximal set (1-12 reps).

    Epley is the general default; Brzycki is more conservative near the top
    of the rep range; Lombardi gives the flattest (lowest) estimates at
    moderate reps; Wathan the highest. Pick one formula per athlete and lift
    and stay consistent; do not average them.
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
    These start-anchored blocks are NOT aligned with compute_acwr's
    end-anchored windows unless the history length is a multiple of 7.
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
    total_weeks must be >= 1; deload_every must be >= 2; taper_weeks must be
    >= 0 and < total_weeks.
    """
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=taper_weeks)
    return PeriodizationWaves(weeks=waves)


def register(mcp: FastMCP) -> None:
    """Register every engine tool on the server."""
    for tool in (
        assess_endurance_goal,
        assess_strength_goal,
        assess_hypertrophy_goal,
        assess_bodycomp_goal,
        predict_race_time,
        compute_pace,
        estimate_1rm,
        prescribe_load,
        prescribe_reps_load,
        weekly_set_targets_for,
        progress_double_progression,
        compute_session_load,
        compute_weekly_loads,
        compute_acwr,
        build_periodization_waves,
    ):
        mcp.tool()(tool)
