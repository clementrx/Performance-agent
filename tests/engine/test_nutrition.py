import pytest

from performance_agent.engine.nutrition import (
    EnergyTarget,
    bmr_mifflin_st_jeor,
    prescribe_energy_target,
    tdee_from_bmr,
)


def test_bmr_male_known_value():
    # 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert bmr_mifflin_st_jeor("male", 80.0, 180.0, 30) == pytest.approx(1780.0)


def test_bmr_female_known_value():
    # 10*80 + 6.25*180 - 5*30 - 161 = 1614
    assert bmr_mifflin_st_jeor("female", 80.0, 180.0, 30) == pytest.approx(1614.0)


def test_bmr_rejects_unknown_sex():
    with pytest.raises(ValueError, match="sex"):
        bmr_mifflin_st_jeor("other", 80.0, 180.0, 30)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("weight", "height"),
    [(30.0, 180.0), (250.0, 180.0), (80.0, 100.0), (80.0, 250.0)],
)
def test_bmr_rejects_out_of_range_body_measures(weight, height):
    with pytest.raises(ValueError, match=r"weight_kg|height_cm"):
        bmr_mifflin_st_jeor("male", weight, height, 30)


def test_bmr_refuses_youth():
    with pytest.raises(ValueError, match="paediatric"):
        bmr_mifflin_st_jeor("male", 60.0, 170.0, 14)


def test_bmr_rejects_age_ninety_and_up():
    with pytest.raises(ValueError, match="age_years"):
        bmr_mifflin_st_jeor("male", 80.0, 180.0, 90)


def test_bmr_rejects_non_whole_age():
    with pytest.raises(ValueError, match="whole number"):
        bmr_mifflin_st_jeor("male", 80.0, 180.0, 30.5)  # ty: ignore[invalid-argument-type]


def test_tdee_known_value():
    assert tdee_from_bmr(1780.0, 1.55) == pytest.approx(2759.0)


@pytest.mark.parametrize("factor", [1.19, 2.41, 0.0, -1.5])
def test_tdee_rejects_out_of_band_activity_factor(factor):
    with pytest.raises(ValueError, match="activity_factor"):
        tdee_from_bmr(1780.0, factor)


@pytest.mark.parametrize("bmr", [0.0, -100.0, float("nan"), float("inf")])
def test_tdee_rejects_bad_bmr(bmr):
    with pytest.raises(ValueError, match=r"bmr_kcal|finite"):
        tdee_from_bmr(bmr, 1.55)


def test_cut_prescription_exact_values():
    # TDEE 2600, 0.75%/wk on 80 kg -> 0.6 kg/wk -> 0.6*7700/7 = 660 kcal/day deficit
    target = prescribe_energy_target(
        tdee_kcal=2600.0,
        goal="cut",
        weekly_change_pct_bw=0.0075,
        weight_kg=80.0,
        height_cm=180.0,
        sex="male",
    )
    assert isinstance(target, EnergyTarget)
    assert target.goal == "cut"
    assert target.daily_kcal == pytest.approx(1940.0)
    assert target.protein_g_per_day == pytest.approx(176.0)
    assert target.weekly_weight_change_kg == pytest.approx(-0.6)
    assert target.clamped_to_floor is False


def test_cut_clamps_to_caloric_floor():
    # TDEE 1700, 1%/wk on 55 kg -> 605 kcal/day deficit -> raw 1095 < 1200 floor
    target = prescribe_energy_target(
        tdee_kcal=1700.0,
        goal="cut",
        weekly_change_pct_bw=0.010,
        weight_kg=55.0,
        height_cm=165.0,
        sex="female",
    )
    assert target.daily_kcal == pytest.approx(1200.0)
    assert target.clamped_to_floor is True
    assert target.weekly_weight_change_kg == pytest.approx(-0.55)
    assert target.protein_g_per_day == pytest.approx(121.0)


def test_cut_refused_for_underweight_athlete():
    # 50 kg at 175 cm -> BMI 16.3, below the 18.5 healthy minimum
    with pytest.raises(ValueError, match="below the healthy minimum"):
        prescribe_energy_target(
            tdee_kcal=2200.0,
            goal="cut",
            weekly_change_pct_bw=0.005,
            weight_kg=50.0,
            height_cm=175.0,
            sex="male",
        )


def test_cut_rate_above_one_percent_rejected():
    with pytest.raises(ValueError, match="lean-mass"):
        prescribe_energy_target(
            tdee_kcal=2600.0,
            goal="cut",
            weekly_change_pct_bw=0.011,
            weight_kg=80.0,
            height_cm=180.0,
            sex="male",
        )


def test_maintain_requires_zero_rate():
    with pytest.raises(ValueError, match="must be 0 for maintain"):
        prescribe_energy_target(
            tdee_kcal=2500.0,
            goal="maintain",
            weekly_change_pct_bw=0.001,
            weight_kg=75.0,
            height_cm=178.0,
            sex="male",
        )


def test_maintain_prescription():
    target = prescribe_energy_target(
        tdee_kcal=2500.0,
        goal="maintain",
        weekly_change_pct_bw=0.0,
        weight_kg=75.0,
        height_cm=178.0,
        sex="male",
    )
    assert target.daily_kcal == pytest.approx(2500.0)
    assert target.protein_g_per_day == pytest.approx(120.0)
    assert target.weekly_weight_change_kg == 0.0
    assert target.clamped_to_floor is False


def test_gain_prescription_exact_values():
    # 0.4%/wk on 75 kg -> +0.3 kg/wk -> +330 kcal/day surplus
    target = prescribe_energy_target(
        tdee_kcal=2800.0,
        goal="gain",
        weekly_change_pct_bw=0.004,
        weight_kg=75.0,
        height_cm=178.0,
        sex="male",
    )
    assert target.daily_kcal == pytest.approx(3130.0)
    assert target.protein_g_per_day == pytest.approx(135.0)
    assert target.weekly_weight_change_kg == pytest.approx(0.3)
    assert target.clamped_to_floor is False


def test_gain_rate_above_half_percent_rejected():
    with pytest.raises(ValueError, match=r"0\.5%"):
        prescribe_energy_target(
            tdee_kcal=2800.0,
            goal="gain",
            weekly_change_pct_bw=0.006,
            weight_kg=75.0,
            height_cm=178.0,
            sex="male",
        )


def test_maintain_clamps_to_caloric_floor():
    # maintain daily_kcal == tdee_kcal == 900 < 1200 female floor
    target = prescribe_energy_target(
        tdee_kcal=900.0,
        goal="maintain",
        weekly_change_pct_bw=0.0,
        weight_kg=55.0,
        height_cm=165.0,
        sex="female",
    )
    assert target.daily_kcal == pytest.approx(1200.0)
    assert target.clamped_to_floor is True
    assert target.weekly_weight_change_kg == 0.0


def test_gain_clamps_to_caloric_floor():
    # TDEE 100, 0.4%/wk on 75 kg -> +0.3 kg/wk -> +330 kcal/day -> raw 430 < 1500 male floor
    target = prescribe_energy_target(
        tdee_kcal=100.0,
        goal="gain",
        weekly_change_pct_bw=0.004,
        weight_kg=75.0,
        height_cm=178.0,
        sex="male",
    )
    assert target.daily_kcal == pytest.approx(1500.0)
    assert target.clamped_to_floor is True
    assert target.weekly_weight_change_kg == pytest.approx(0.3)
