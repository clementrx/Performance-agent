"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import (
    AcwrMethod,
    BlockWeek,
    BodycompFeasibility,
    EnergyTarget,
    FeasibilityResult,
    InseasonWeek,
    PeakingWeek,
    ProgressionDecision,
    SeasonModality,
    TopSetBackoff,
    TrainingAge,
    UndulatingSession,
    WaveStep,
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
    fitness_fatigue_series,
    hypertrophy_feasibility,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    pace_s_per_km,
    percentage_for_reps_rir,
    prescribe_energy_target,
    readiness_score,
    recommend_taper_length,
    riegel_predict,
    rir_from_rpe,
    session_rpe_load,
    strength_feasibility,
    tdee_from_bmr,
    top_set_backoff,
    training_zones_from_race,
    wave_loading,
    weekly_loads,
    weekly_monotony,
    weekly_strain,
)
from performance_agent.engine import budget_weekly_load as engine_budget_weekly_load
from performance_agent.engine import estimate_srpe_from_hr as engine_estimate_srpe_from_hr
from performance_agent.engine import flag_implausible_session as engine_flag_implausible_session
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


class WaveLoadingPlan(TypedDict):
    """Ordered wave-loading sets (wave and step are 1-indexed)."""

    steps: list[WaveStep]


class RirValue(TypedDict):
    """Reps in reserve equivalent to a session RPE."""

    rir: float


class TaperLength(TypedDict):
    """Recommended taper length in days."""

    taper_days: int


def recommend_taper(
    buildup_weeks: int,
    modality: SeasonModality,
    event_priority: Literal["A", "B", "C"],
) -> TaperLength:
    """Recommend a taper length in days (4-14) before a competition.

    Endurance events taper longest and strength shortest (corpus taper
    meta-analysis, tapering-performance-meta-2007); a short buildup shortens
    it, and a B event gets a mini-taper (never a full one). modality is
    strength, endurance or mixed; buildup_weeks is the weeks of loading before
    the taper (non-negative). Returns days, clamped to [4, 14].
    """
    return TaperLength(taper_days=recommend_taper_length(buildup_weeks, modality, event_priority))


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


def compute_acwr(daily_loads: list[float], method: AcwrMethod = "rolling") -> AcwrResult:
    """Acute:chronic workload ratio over the most recent 28 days (coupled variant).

    method "rolling" (default) is the classic 7-day-mean over 28-day-mean ratio;
    "ewma" is the exponentially-weighted variant (weights recent days more).
    Returns null when history is shorter than 28 days or the chronic term is
    zero. Descriptive trend only — its injury-prediction validity is contested;
    never present it as an injury probability.
    """
    return AcwrResult(acute_chronic_ratio=acute_chronic_ratio(daily_loads, method))


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
    of 1RM), light (0.625-0.70), moderate (0.725-0.80); heavy-then-light
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
    with clamped_to_floor=True. On a clamped CUT, that flag means "extend
    the deadline, never deepen the deficit"; on a clamped maintain or gain,
    it means "sanity-check the tdee_kcal input — it is almost certainly an
    upstream estimation error". Protein is 2.2 g/kg on a cut, 1.6
    maintaining, 1.8 gaining.
    """
    return prescribe_energy_target(tdee_kcal, goal, weekly_change_pct_bw, weight_kg, height_cm, sex)


def prescribe_top_set_backoff(
    one_rm_kg: float, top_percentage: float, backoff_drop: float, backoff_sets: int
) -> TopSetBackoff:
    """Prescribe a top-set/back-off strength session from a 1RM.

    One top set at top_percentage of 1RM (in (0, 1.3]), then backoff_sets
    sets (whole number 1-10) at top_percentage - backoff_drop. backoff_drop
    is a fraction of 1RM in (0, 0.5] — drops beyond 50% stop being training
    weight — and must leave a positive back-off percentage. Loads in kg.
    """
    return top_set_backoff(one_rm_kg, top_percentage, backoff_drop, backoff_sets)


def prescribe_wave_loading(  # noqa: PLR0913 -- plan-approved signature; all call sites use keywords
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> WaveLoadingPlan:
    """Generate a wave-loading set sequence for one strength session.

    Each wave climbs from base_percentage (in (0, 1]) in step_increment
    jumps (in (0, 0.1]) for steps_per_wave sets (2-5); the next wave
    restarts inter_wave_increment above the previous wave's base (1-4
    waves). inter_wave_increment must stay strictly below step_increment so
    waves OVERLAP — each wave starts below where the previous one ended;
    that overlap is the defining property of wave loading. The peak
    percentage (base + (steps_per_wave-1)*step_increment +
    (waves-1)*inter_wave_increment) is REFUSED above 1.3, the supra-maximal
    cap — relay that refusal, do not work around it. Loads in kg.
    """
    return WaveLoadingPlan(
        steps=wave_loading(
            one_rm_kg,
            base_percentage,
            step_increment,
            steps_per_wave,
            waves,
            inter_wave_increment,
        )
    )


class MonotonyStrain(TypedDict):
    """Foster monotony and strain for a 7-day block (null when the week is uniform)."""

    weekly_load: float
    monotony: float | None
    strain: float | None


class DayStateView(TypedDict):
    """One day of the fitness-fatigue model."""

    date_index: int
    ctl: float
    atl: float
    tsb: float


class FitnessFatigueSeries(TypedDict):
    """Day-by-day CTL/ATL/TSB fitness-fatigue trend."""

    days: list[DayStateView]


class ReadinessResult(TypedDict):
    """Pre-session readiness score, band, and per-item drivers."""

    score_0_100: float
    band: Literal["green", "amber", "red"]
    drivers: dict[str, float]


class SrpeEstimate(TypedDict):
    """Estimated session-RPE (CR-10) from average heart rate."""

    estimated_srpe: float


class PaceZoneView(TypedDict):
    """One training pace zone in seconds per kilometre."""

    name: str
    low_pace_s_per_km: float
    high_pace_s_per_km: float


class PaceZones(TypedDict):
    """Five race-derived training pace zones, Z5 (fastest) to Z1 (slowest)."""

    zones: list[PaceZoneView]


class LoadBudgetResult(TypedDict):
    """Programmable weekly load left after committed external load."""

    programmable_budget: float
    external_total: float
    conflict: bool
    drivers: dict[str, float]


class FlagView(TypedDict):
    """One data-quality concern to confirm with the athlete."""

    code: str
    message: str


class PlausibilityResult(TypedDict):
    """Data-quality flags for a session value (empty list = looks clean)."""

    flags: list[FlagView]


def compute_monotony_strain(daily_loads_7: list[float]) -> MonotonyStrain:
    """Foster training monotony and strain for one 7-day block (descriptive).

    Pass exactly 7 daily session-RPE loads (rest days as 0). Monotony is
    mean/SD (a flat, samey week scores high); strain is weekly load x monotony.
    Both are null when the week is perfectly uniform (SD 0). Present them as
    trends the coach reads, never as an injury probability.
    """
    return MonotonyStrain(
        weekly_load=sum(daily_loads_7),
        monotony=weekly_monotony(daily_loads_7),
        strain=weekly_strain(daily_loads_7),
    )


def compute_fitness_fatigue(daily_loads: list[float]) -> FitnessFatigueSeries:
    """Day-by-day CTL/ATL/TSB fitness-fatigue trend from a daily-load series.

    CTL (42-day EWMA) is the fitness trend, ATL (7-day EWMA) the fatigue trend,
    TSB = CTL - ATL the freshness trend (positive = fresh, negative = fatigued).
    Both EWMAs start cold at zero, so the first weeks ramp up. Descriptive
    trends only, never a performance prediction; narrate the direction of the
    last few days, not the absolute number.
    """
    return FitnessFatigueSeries(
        days=[
            DayStateView(date_index=d.date_index, ctl=d.ctl, atl=d.atl, tsb=d.tsb)
            for d in fitness_fatigue_series(daily_loads)
        ]
    )


def compute_readiness(
    sleep: int, fatigue: int, soreness: int, stress: int, hrv_delta_pct: float | None = None
) -> ReadinessResult:
    """Score pre-session readiness 0-100 from the four Hooper items (+ optional HRV).

    Each item is rated 1 (best) to 7 (worst): sleep quality, fatigue, muscle
    soreness, stress. hrv_delta_pct is optional HRV vs the athlete's baseline as
    a percent (+10 = 10% above), nudging the score up to +/-10 points. Bands:
    >= 75 green, 50-74 amber, < 50 red. Descriptive read for autoregulation, not
    a diagnosis; quote the drivers (per-item sub-scores) alongside the band.
    """
    result = readiness_score(sleep, fatigue, soreness, stress, hrv_delta_pct)
    return ReadinessResult(score_0_100=result.score_0_100, band=result.band, drivers=result.drivers)


def estimate_srpe_from_hr(avg_hr: float, hr_max: float) -> SrpeEstimate:
    """Estimate a session-RPE (CR-10, 1-10) from average heart rate as %HRmax.

    For club sessions and imported files that carry HR but no rated RPE. avg_hr
    must be positive and <= hr_max; hr_max a plausible 100-230 bpm. This is an
    ESTIMATE from Foster's HR/RPE table — confirm it with the athlete before
    logging it as a fact.
    """
    return SrpeEstimate(estimated_srpe=engine_estimate_srpe_from_hr(avg_hr, hr_max))


def endurance_zones(distance_m: float, time_s: float) -> PaceZones:
    """Derive five running pace zones (s/km) from a recent race performance.

    Estimates threshold pace by Riegel-projecting the race to 10 km, then scales
    it into five contiguous zones from Z5 (interval, fastest) to Z1 (recovery,
    slowest). Race distance must be within the Riegel band (1500-42195 m).
    Population-model guidance, not a physiological test — say so.
    """
    return PaceZones(
        zones=[
            PaceZoneView(
                name=z.name,
                low_pace_s_per_km=z.low_pace_s_per_km,
                high_pace_s_per_km=z.high_pace_s_per_km,
            )
            for z in training_zones_from_race(distance_m, time_s)
        ]
    )


def budget_weekly_load(
    target_weekly_load: float, external_loads: list[float], min_programmed_load: float = 0.0
) -> LoadBudgetResult:
    """Size programmable load after subtracting committed external load.

    target_weekly_load is the intended weekly session-RPE total; external_loads
    are the session-RPE loads the coach does NOT program (club practice, matches,
    physical work). Returns programmable_budget = target - sum(external), the
    external total and its share, and conflict=True when the budget falls below
    min_programmed_load (external commitments already fill the week). Surface a
    conflict honestly: cut the target or accept a higher total with monitoring.
    """
    result = engine_budget_weekly_load(target_weekly_load, external_loads, min_programmed_load)
    return LoadBudgetResult(
        programmable_budget=result.programmable_budget,
        external_total=result.external_total,
        conflict=result.conflict,
        drivers=result.drivers,
    )


def flag_implausible_session(  # noqa: PLR0913 -- optional numeric guards, all keyword at call sites
    session_e1rm_kg: float | None = None,
    recent_best_e1rm_kg: float | None = None,
    top_load_kg: float | None = None,
    known_1rm_kg: float | None = None,
    is_test: bool = False,
    duration_min: float | None = None,
    median_duration_min: float | None = None,
) -> PlausibilityResult:
    """Flag logged values that look like data-entry noise (never auto-rejects them).

    Guards (team-chosen priors): a session estimated 1RM >15% above the recent
    best; a working load above 115% of a known 1RM outside a test; a duration
    more than 3x or below a third of the recent median. Pass only the numbers
    the session has. log_session already runs these automatically — call this
    directly only for ad-hoc checks. Confirm every flag with the athlete before
    trusting the value.
    """
    flags = engine_flag_implausible_session(
        session_e1rm_kg=session_e1rm_kg,
        recent_best_e1rm_kg=recent_best_e1rm_kg,
        top_load_kg=top_load_kg,
        known_1rm_kg=known_1rm_kg,
        is_test=is_test,
        duration_min=duration_min,
        median_duration_min=median_duration_min,
    )
    return PlausibilityResult(flags=[FlagView(code=f.code, message=f.message) for f in flags])


def convert_rpe_to_rir(rpe: float) -> RirValue:
    """Convert a session RPE (1-10, half points allowed) to reps in reserve.

    RIR = 10 - RPE (e.g. RPE 8.5 -> 1.5 RIR). Use this when the athlete or
    a source speaks RPE; the prescription tools (prescribe_reps_load) take
    RIR. Quarter-point RPEs are refused — the scale is half-point.
    """
    return RirValue(rir=rir_from_rpe(rpe))


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
        compute_monotony_strain,
        compute_fitness_fatigue,
        compute_readiness,
        estimate_srpe_from_hr,
        endurance_zones,
        budget_weekly_load,
        flag_implausible_session,
        build_periodization_waves,
        build_block_cycle,
        build_undulating_sessions,
        build_inseason_maintenance,
        build_peaking_block,
        compute_bmr_tdee,
        prescribe_nutrition_targets,
        prescribe_top_set_backoff,
        prescribe_wave_loading,
        convert_rpe_to_rir,
        recommend_taper,
    ):
        mcp.tool()(tool)
