"""Phase 2 monitoring math: monotony/strain, fitness-fatigue, readiness, budget, guards."""

import math

import pytest

from performance_agent.engine.load import (
    acute_chronic_ratio,
    budget_weekly_load,
    estimate_srpe_from_hr,
    fitness_fatigue_series,
    flag_implausible_session,
    readiness_score,
    weekly_monotony,
    weekly_strain,
)

# --- monotony / strain (Foster) -------------------------------------------


def test_monotony_is_mean_over_population_sd():
    # loads [100,50,0,80,0,120,0]: mean = 50, population sd ~ 47.5
    week = [100.0, 50.0, 0.0, 80.0, 0.0, 120.0, 0.0]
    mean = sum(week) / 7
    sd = math.sqrt(sum((v - mean) ** 2 for v in week) / 7)
    assert weekly_monotony(week) == pytest.approx(mean / sd)


def test_monotony_none_for_uniform_week():
    assert weekly_monotony([80.0] * 7) is None


def test_monotony_none_for_all_rest_week():
    assert weekly_monotony([0.0] * 7) is None


def test_strain_is_weekly_load_times_monotony():
    week = [100.0, 50.0, 0.0, 80.0, 0.0, 120.0, 0.0]
    monotony = weekly_monotony(week)
    assert monotony is not None
    assert weekly_strain(week) == pytest.approx(sum(week) * monotony)


def test_strain_none_when_monotony_undefined():
    assert weekly_strain([80.0] * 7) is None


@pytest.mark.parametrize("length", [0, 6, 8, 14])
def test_monotony_requires_exactly_seven_days(length):
    with pytest.raises(ValueError, match="exactly 7"):
        weekly_monotony([50.0] * length)


def test_monotony_rejects_negative():
    with pytest.raises(ValueError, match="negative"):
        weekly_monotony([50.0, 50.0, 50.0, 50.0, 50.0, 50.0, -1.0])


# --- fitness-fatigue EWMA (CTL/ATL/TSB) -----------------------------------


def test_fitness_fatigue_converges_to_constant_load():
    series = fitness_fatigue_series([100.0] * 600)
    last = series[-1]
    assert last.ctl == pytest.approx(100.0, abs=0.5)
    assert last.atl == pytest.approx(100.0, abs=0.01)
    assert last.tsb == pytest.approx(0.0, abs=0.5)


def test_fitness_fatigue_tsb_goes_negative_after_a_spike():
    # steady base, then a hard week: fatigue (atl) outruns fitness (ctl)
    series = fitness_fatigue_series([50.0] * 40 + [300.0] * 5)
    assert series[-1].tsb < 0


def test_fitness_fatigue_series_length_and_indices():
    series = fitness_fatigue_series([10.0, 20.0, 30.0])
    assert [d.date_index for d in series] == [0, 1, 2]


def test_fitness_fatigue_empty_series():
    assert fitness_fatigue_series([]) == []


@pytest.mark.parametrize(("ctl_tau", "atl_tau"), [(0, 7), (42, 0), (-1, 7)])
def test_fitness_fatigue_rejects_bad_taus(ctl_tau, atl_tau):
    with pytest.raises(ValueError, match="tau"):
        fitness_fatigue_series([100.0] * 10, ctl_tau=ctl_tau, atl_tau=atl_tau)


# --- readiness score ------------------------------------------------------


def test_readiness_best_case_is_100_green():
    result = readiness_score(1, 1, 1, 1)
    assert result.score_0_100 == pytest.approx(100.0)
    assert result.band == "green"


def test_readiness_worst_case_is_0_red():
    result = readiness_score(7, 7, 7, 7)
    assert result.score_0_100 == pytest.approx(0.0)
    assert result.band == "red"


def test_readiness_band_edges():
    # all items at 4/7 -> subscore 50 -> amber lower edge
    assert readiness_score(4, 4, 4, 4).band == "amber"
    # tune to just below 50 via a worse item -> red
    assert readiness_score(4, 4, 4, 5).band == "red"


def test_readiness_hrv_modifier_moves_score_and_is_capped():
    base = readiness_score(4, 4, 4, 4).score_0_100
    up = readiness_score(4, 4, 4, 4, hrv_delta_pct=40)  # capped at +10
    assert up.score_0_100 == pytest.approx(min(100.0, base + 10.0))
    assert up.drivers["hrv_modifier"] == pytest.approx(10.0)


@pytest.mark.parametrize("bad", [0, 8, -1])
def test_readiness_rejects_out_of_range_items(bad):
    with pytest.raises(ValueError, match="Hooper"):
        readiness_score(bad, 3, 3, 3)


def test_readiness_rejects_non_finite_hrv():
    with pytest.raises(ValueError, match="finite"):
        readiness_score(3, 3, 3, 3, hrv_delta_pct=float("nan"))


# --- sRPE from heart rate -------------------------------------------------


def test_srpe_from_hr_matches_linear_anchor():
    # 80% HRmax -> (80-50)/5 = 6
    assert estimate_srpe_from_hr(152.0, 190.0) == pytest.approx(6.0)


def test_srpe_from_hr_clamps_to_scale():
    assert estimate_srpe_from_hr(100.0, 190.0) == pytest.approx(1.0)  # low % clamps to 1
    assert estimate_srpe_from_hr(190.0, 190.0) == pytest.approx(10.0)  # 100% clamps to 10


@pytest.mark.parametrize(("avg", "hr_max"), [(200.0, 190.0), (0.0, 190.0), (150.0, 90.0)])
def test_srpe_from_hr_rejects_bad_inputs(avg, hr_max):
    with pytest.raises(ValueError):
        estimate_srpe_from_hr(avg, hr_max)


# --- weekly load budget ---------------------------------------------------


def test_budget_subtracts_external_load():
    result = budget_weekly_load(2000.0, [500.0, 600.0])
    assert result.programmable_budget == pytest.approx(900.0)
    assert result.external_total == pytest.approx(1100.0)
    assert result.drivers["external_share"] == pytest.approx(0.55)


def test_budget_conflict_when_below_minimum():
    result = budget_weekly_load(1000.0, [900.0], min_programmed_load=200.0)
    assert result.conflict is True


def test_budget_no_conflict_by_default():
    result = budget_weekly_load(1000.0, [900.0])
    assert result.conflict is False  # budget 100 >= default floor 0


def test_budget_rejects_negative_target():
    with pytest.raises(ValueError, match="non-negative"):
        budget_weekly_load(-1.0, [100.0])


# --- implausibility guards ------------------------------------------------


def test_flag_e1rm_jump_over_15pct():
    flags = flag_implausible_session(session_e1rm_kg=150.0, recent_best_e1rm_kg=120.0)
    assert [f.code for f in flags] == ["e1rm_jump"]


def test_no_flag_for_modest_e1rm_gain():
    assert flag_implausible_session(session_e1rm_kg=126.0, recent_best_e1rm_kg=120.0) == []


def test_flag_load_over_known_1rm_outside_test():
    flags = flag_implausible_session(top_load_kg=200.0, known_1rm_kg=150.0)
    assert [f.code for f in flags] == ["load_over_1rm"]


def test_no_load_flag_in_test_context():
    assert flag_implausible_session(top_load_kg=200.0, known_1rm_kg=150.0, is_test=True) == []


def test_flag_duration_outlier_high_and_low():
    assert flag_implausible_session(duration_min=200.0, median_duration_min=60.0)[0].code == (
        "duration_outlier"
    )
    assert flag_implausible_session(duration_min=10.0, median_duration_min=60.0)[0].code == (
        "duration_outlier"
    )


def test_no_flags_when_nothing_passed():
    assert flag_implausible_session() == []


# --- acwr method extension ------------------------------------------------


def test_acwr_ewma_converges_to_one_on_long_uniform_history():
    # both EWMAs saturate to the constant load once history is long enough
    assert acute_chronic_ratio([100.0] * 400, "ewma") == pytest.approx(1.0, abs=0.02)


def test_acwr_ewma_rises_after_spike():
    history = [100.0] * 30 + [200.0] * 7
    ratio = acute_chronic_ratio(history, "ewma")
    assert ratio is not None
    assert ratio > 1.0


def test_acwr_rejects_unknown_method():
    with pytest.raises(ValueError, match="method"):
        acute_chronic_ratio([100.0] * 28, "bogus")  # ty: ignore[invalid-argument-type]


def test_acwr_default_is_rolling():
    assert acute_chronic_ratio([100.0] * 28) == acute_chronic_ratio([100.0] * 28, "rolling")
