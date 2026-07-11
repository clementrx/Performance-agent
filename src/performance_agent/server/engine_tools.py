"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import (
    BlockWeek,
    BodycompFeasibility,
    EnergyTarget,
    FeasibilityResult,
    InseasonWeek,
    PeakingWeek,
    ProgressionDecision,
    TrainingAge,
    UndulatingSession,
    WeekLoad,
    WeeklySetTargets,
    acute_chronic_ratio,
    bmr_mifflin_st_jeor,
    bodycomp_feasibility,
    build_block_periodization,
    build_inseason_week,
    build_strength_peaking,
    build_undulating_week,
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
    prescribe_energy_target,
    riegel_predict,
    session_rpe_load,
    strength_feasibility,
    tdee_from_bmr,
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


class BlockCycle(TypedDict):
    """Accumulation/intensification/realization weeks of a block cycle."""

    weeks: list[BlockWeek]


class UndulatingWeekPlan(TypedDict):
    """Session-by-session emphases for a daily-undulating week."""

    sessions: list[UndulatingSession]


class PeakingBlock(TypedDict):
    """Week-by-week taper toward a 1RM test."""

    weeks: list[PeakingWeek]


class BmrTdee(TypedDict):
    """Basal and total daily energy expenditure, in kcal/day."""

    bmr_kcal: float
    tdee_kcal: float


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
    (reps + rir) above 18 are REJECTED (enforced validity band), not
    clamped, and the model is only validated to ~12 — when reps + rir is
    13-18, label the prescription as carrying extra uncertainty. One all-out
    rep (reps=1, rir=0) returns exactly 1.0 (100% of 1RM), not the raw
    formula value. Returns the fraction of 1RM and the load in kg.
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
    above the lowest achieved set, capped at rep_range_high. A
    next_target_reps below rep_range_low signals performance below the
    range; load reduction (deload) is out of scope for this rule. Loads in
    kg; rep range must satisfy 1 <= low < high <= 18.
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

    Epley is the general default; Brzycki is more conservative at
    low-to-moderate reps but the most aggressive at 11-12; Lombardi gives
    the lowest estimates at moderate-to-high reps; Wathan the highest
    through ~10 reps. Pick one formula per athlete and lift and stay
    consistent; do not average them.
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


def build_block_cycle(total_weeks: int) -> BlockCycle:
    """Split a training cycle into accumulation/intensification/realization blocks.

    Use this when a single deadline goal is 6+ weeks out and benefits from
    distinct sequential emphases (build_periodization_waves is the generic
    ramp, build_peaking_block covers the final 1-3 weeks before a 1RM test,
    build_inseason_maintenance covers weeks with competitive fixtures).
    Phase split is ~50/35/15% of total_weeks with at least 1 week per phase;
    accumulation is 1.10 volume at 0.85 intensity, intensification 0.90 at
    1.05, realization 0.55 at 1.10 — multipliers against a baseline week.
    total_weeks must be a whole number >= 6.
    """
    return BlockCycle(weeks=build_block_periodization(total_weeks))


def build_undulating_sessions(sessions_per_week: int) -> UndulatingWeekPlan:
    """Assign daily-undulating (DUP) emphases to a week's strength sessions.

    Use this to structure intensity WITHIN a training week (2-7 sessions)
    when all qualities are trained concurrently — the block and peaking
    tools structure across weeks instead. Sessions cycle heavy (0.85-0.925
    of 1RM), light (0.60-0.70), moderate (0.725-0.80); heavy-then-light
    adjacency is deliberate recovery spacing. A single weekly session cannot
    undulate (error).
    """
    return UndulatingWeekPlan(sessions=build_undulating_week(sessions_per_week))


def build_inseason_maintenance(matches_this_week: int) -> InseasonWeek:
    """Prescribe in-season strength maintenance around this week's fixtures.

    Use this when the athlete has 1 or 2 competitive matches this week and
    strength work must shrink to the minimum effective dose. 1 match: 2
    sessions at 0.50 of off-season volume; 2 matches: 1 session at 0.30 —
    both holding intensity at or above 0.80 (intensity, not volume, retains
    strength). REFUSES 0 matches (use a normal building week) and 3+ matches
    (rest is the prescription) — relay those refusals, do not work around
    them.
    """
    return build_inseason_week(matches_this_week)


def build_peaking_block(weeks: int) -> PeakingBlock:
    """Taper the final 1-3 weeks before a 1RM test day.

    Use this only when a maximal strength test is scheduled: volume falls
    week over week while intensity climbs to near-max, and the last week
    (is_test_week=True) carries intensity above 1.0 for openers/heavy
    singles — not a projected new max. Blocks longer than 3 weeks are
    refused (they detrain; schedule a block cycle first).
    """
    return PeakingBlock(weeks=build_strength_peaking(weeks))


def compute_bmr_tdee(
    sex: Literal["male", "female"],
    weight_kg: float,
    height_cm: float,
    age_years: int,
    activity_factor: float,
) -> BmrTdee:
    """Estimate BMR (Mifflin-St Jeor) and TDEE, both in kcal/day.

    weight_kg in (30, 250), height_cm in (100, 250), age_years a whole
    number in (14, 90) — under-15s are refused (youth nutrition is out of
    scope; relay the paediatric referral). activity_factor in [1.2, 2.4],
    sedentary to extreme training loads.
    """
    bmr = bmr_mifflin_st_jeor(sex, weight_kg, height_cm, age_years)
    return BmrTdee(bmr_kcal=bmr, tdee_kcal=tdee_from_bmr(bmr, activity_factor))


def prescribe_nutrition_targets(  # noqa: PLR0913 -- plan-approved signature; all call sites use keywords
    tdee_kcal: float,
    goal: Literal["cut", "maintain", "gain"],
    weekly_change_pct_bw: float,
    weight_kg: float,
    height_cm: float,
    sex: Literal["male", "female"],
) -> EnergyTarget:
    """Prescribe daily kcal and protein for a cut, maintain or gain goal.

    This is not medical advice; the guards are hard-coded and must be
    relayed, never worked around. REFUSES a deficit for an underweight
    athlete (BMI < 18.5) with a referral to a health professional. Caps the
    weekly rate at 1% of bodyweight for a cut and 0.5% for a gain
    (weekly_change_pct_bw is a fraction: 0.0075 = 0.75%/week; must be 0 for
    maintain). Daily kcal for ANY goal (cut, maintain or gain) landing below
    the caloric floor (1500 kcal male, 1200 female) is clamped to the floor
    with clamped_to_floor=True — that flag means "extend the deadline,
    never deepen the deficit". Protein is 2.2 g/kg on a cut, 1.6
    maintaining, 1.8 gaining.
    """
    return prescribe_energy_target(tdee_kcal, goal, weekly_change_pct_bw, weight_kg, height_cm, sex)


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
        build_block_cycle,
        build_undulating_sessions,
        build_inseason_maintenance,
        build_peaking_block,
        compute_bmr_tdee,
        prescribe_nutrition_targets,
    ):
        mcp.tool()(tool)
