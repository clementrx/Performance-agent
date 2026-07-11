"""Energy and protein targets with hard safety guards.

The guards live HERE, not in prompts: no agent can prescribe below the
caloric floor, above the safe loss rate, or to an underweight athlete.
Numbers are team-chosen priors from mainstream sports-nutrition consensus;
they parameterize honesty, not medical advice — the tools refuse and refer
out when a request crosses a red line.
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

Sex = Literal["male", "female"]
GoalDirection = Literal["cut", "maintain", "gain"]

# Mifflin-St Jeor sex offsets (kcal/day) — published constants of the source
# equation, not tunable priors.
MALE_BMR_OFFSET = 5.0
FEMALE_BMR_OFFSET = -161.0
# Activity-factor band: 1.2 (sedentary) to 2.4 (extreme training loads).
# Team-chosen bounds on the standard multiplier tables.
MIN_ACTIVITY_FACTOR = 1.2
MAX_ACTIVITY_FACTOR = 2.4
# Absolute daily floors (kcal) below which we refuse to prescribe.
# Team-chosen priors matching mainstream dietetic guidance.
CALORIC_FLOOR_KCAL = {"male": 1500.0, "female": 1200.0}
# Safe weekly bodyweight-change caps as fractions of bodyweight. Team-chosen
# priors: up to 1%/week loss preserves lean mass; above 0.5%/week gain
# mostly adds fat.
MAX_WEEKLY_LOSS_PCT_BW = 0.010
MAX_WEEKLY_GAIN_PCT_BW = 0.005
# Protein targets (g per kg bodyweight per day) by goal direction.
# Team-chosen priors from sports-nutrition consensus ranges.
PROTEIN_G_PER_KG = {"cut": 2.2, "maintain": 1.6, "gain": 1.8}
# Energy density of a kilogram of bodyweight change — the classic 7700
# kcal/kg approximation (team-chosen prior).
KCAL_PER_KG_TISSUE = 7700.0
# WHO underweight threshold; below it we refuse to prescribe a deficit.
MIN_HEALTHY_BMI = 18.5

# Plausible adult athlete measurement bands (exclusive). Team-chosen priors;
# outside them the equations are extrapolating.
_WEIGHT_RANGE_KG = (30.0, 250.0)
_HEIGHT_RANGE_CM = (100.0, 250.0)
_AGE_RANGE_YEARS = (14, 90)


def _validate_sex(sex: str) -> None:
    if sex not in ("male", "female"):
        msg = f'sex must be "male" or "female", got {sex!r}'
        raise ValueError(msg)


def _validate_open_range(name: str, value: float, bounds: tuple[float, float]) -> None:
    validate_finite(name, value)
    low, high = bounds
    if not low < value < high:
        msg = f"{name} must be between {low} and {high} (exclusive), got {value!r}"
        raise ValueError(msg)


def _validate_age(age_years: int) -> None:
    validate_whole_number("age_years", age_years)
    low, high = _AGE_RANGE_YEARS
    if age_years <= low:
        msg = (
            f"age_years must be over {low}, got {age_years!r}: youth nutrition is "
            "out of scope; refer to a paediatric professional"
        )
        raise ValueError(msg)
    if age_years >= high:
        msg = f"age_years must be under {high}, got {age_years!r}"
        raise ValueError(msg)


def bmr_mifflin_st_jeor(sex: Sex, weight_kg: float, height_cm: float, age_years: int) -> float:
    """Basal metabolic rate in kcal/day (Mifflin-St Jeor).

    10*weight_kg + 6.25*height_cm - 5*age_years + offset(sex). weight_kg in
    (30, 250), height_cm in (100, 250), age_years a whole number in
    (14, 90) — under-15s are refused (youth nutrition is out of scope).
    """
    _validate_sex(sex)
    _validate_open_range("weight_kg", weight_kg, _WEIGHT_RANGE_KG)
    _validate_open_range("height_cm", height_cm, _HEIGHT_RANGE_CM)
    _validate_age(age_years)
    offset = MALE_BMR_OFFSET if sex == "male" else FEMALE_BMR_OFFSET
    return 10 * weight_kg + 6.25 * height_cm - 5 * age_years + offset


def tdee_from_bmr(bmr_kcal: float, activity_factor: float) -> float:
    """Total daily energy expenditure: BMR scaled by an activity factor.

    bmr_kcal must be positive and finite; activity_factor must be in
    [1.2, 2.4] (sedentary to extreme training loads).
    """
    validate_finite("bmr_kcal", bmr_kcal)
    validate_finite("activity_factor", activity_factor)
    if bmr_kcal <= 0:
        msg = f"bmr_kcal must be positive, got {bmr_kcal!r}"
        raise ValueError(msg)
    if not MIN_ACTIVITY_FACTOR <= activity_factor <= MAX_ACTIVITY_FACTOR:
        msg = (
            f"activity_factor must be in [{MIN_ACTIVITY_FACTOR}, {MAX_ACTIVITY_FACTOR}], "
            f"got {activity_factor!r}"
        )
        raise ValueError(msg)
    return bmr_kcal * activity_factor


@dataclass(frozen=True)
class EnergyTarget:
    """Daily energy & protein prescription with its guard status."""

    goal: GoalDirection
    daily_kcal: float
    protein_g_per_day: float
    weekly_weight_change_kg: float
    clamped_to_floor: bool


def _validate_target_inputs(
    tdee_kcal: float, goal: str, weight_kg: float, height_cm: float, sex: str
) -> None:
    _validate_sex(sex)
    if goal not in PROTEIN_G_PER_KG:
        msg = f'goal must be "cut", "maintain" or "gain", got {goal!r}'
        raise ValueError(msg)
    validate_finite("tdee_kcal", tdee_kcal)
    if tdee_kcal <= 0:
        msg = f"tdee_kcal must be positive, got {tdee_kcal!r}"
        raise ValueError(msg)
    _validate_open_range("weight_kg", weight_kg, _WEIGHT_RANGE_KG)
    _validate_open_range("height_cm", height_cm, _HEIGHT_RANGE_CM)


def _validate_rate(goal: GoalDirection, weekly_change_pct_bw: float) -> None:
    validate_finite("weekly_change_pct_bw", weekly_change_pct_bw)
    if goal == "maintain" and weekly_change_pct_bw != 0:
        msg = f"weekly_change_pct_bw must be 0 for maintain, got {weekly_change_pct_bw!r}"
        raise ValueError(msg)
    if goal == "cut" and not 0 < weekly_change_pct_bw <= MAX_WEEKLY_LOSS_PCT_BW:
        msg = (
            f"weekly_change_pct_bw for a cut must be in (0, {MAX_WEEKLY_LOSS_PCT_BW}] — "
            f"1%/week is the lean-mass-preserving cap, got {weekly_change_pct_bw!r}"
        )
        raise ValueError(msg)
    if goal == "gain" and not 0 < weekly_change_pct_bw <= MAX_WEEKLY_GAIN_PCT_BW:
        msg = (
            f"weekly_change_pct_bw for a gain must be in (0, {MAX_WEEKLY_GAIN_PCT_BW}] — "
            f"0.5%/week for gains — faster mostly adds fat, got {weekly_change_pct_bw!r}"
        )
        raise ValueError(msg)


def prescribe_energy_target(  # noqa: PLR0913 -- plan-approved signature; all call sites use keywords
    tdee_kcal: float,
    goal: GoalDirection,
    weekly_change_pct_bw: float,
    weight_kg: float,
    height_cm: float,
    sex: Sex,
) -> EnergyTarget:
    """Prescribe daily energy and protein for a cut, maintain or gain goal.

    weekly_change_pct_bw is the weekly bodyweight change as a fraction of
    bodyweight: 0 for maintain, in (0, 0.010] for a cut, in (0, 0.005] for a
    gain. Hard guards, in order: an underweight athlete (BMI < 18.5) is
    refused a deficit outright; the rate caps are enforced; and a cut whose
    daily kcal would land below the sex-specific caloric floor is clamped to
    the floor with clamped_to_floor=True — the coach must then extend the
    deadline instead of deepening the deficit. weekly_weight_change_kg is
    negative for a cut, zero for maintain, positive for a gain.
    """
    _validate_target_inputs(tdee_kcal, goal, weight_kg, height_cm, sex)
    bmi = weight_kg / (height_cm / 100) ** 2
    if bmi < MIN_HEALTHY_BMI and goal == "cut":
        msg = (
            f"BMI {bmi:.1f} is below the healthy minimum ({MIN_HEALTHY_BMI}): refusing "
            "to prescribe a deficit — refer to a health professional"
        )
        raise ValueError(msg)
    _validate_rate(goal, weekly_change_pct_bw)
    weekly_change_kg = weekly_change_pct_bw * weight_kg
    daily_adjustment_kcal = weekly_change_kg * KCAL_PER_KG_TISSUE / 7
    clamped = False
    if goal == "cut":
        daily_kcal = tdee_kcal - daily_adjustment_kcal
        weekly_weight_change_kg = -weekly_change_kg
        if daily_kcal < CALORIC_FLOOR_KCAL[sex]:
            daily_kcal = CALORIC_FLOOR_KCAL[sex]
            clamped = True
    elif goal == "gain":
        daily_kcal = tdee_kcal + daily_adjustment_kcal
        weekly_weight_change_kg = weekly_change_kg
    else:
        daily_kcal = tdee_kcal
        weekly_weight_change_kg = 0.0
    return EnergyTarget(
        goal=goal,
        daily_kcal=daily_kcal,
        protein_g_per_day=PROTEIN_G_PER_KG[goal] * weight_kg,
        weekly_weight_change_kg=weekly_weight_change_kg,
        clamped_to_floor=clamped,
    )
