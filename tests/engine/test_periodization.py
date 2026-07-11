import pytest

from performance_agent.engine.periodization import (
    ACCUMULATION_INTENSITY,
    ACCUMULATION_VOLUME,
    INTENSIFICATION_INTENSITY,
    INTENSIFICATION_VOLUME,
    REALIZATION_INTENSITY,
    REALIZATION_VOLUME,
    BlockWeek,
    WeekLoad,
    build_block_periodization,
    build_undulating_week,
    build_weekly_waves,
)


def test_eight_week_block_shape():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    assert len(waves) == 8
    assert [w.week for w in waves] == list(range(1, 9))


def test_deload_lands_every_fourth_building_week():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    assert waves[3].is_deload
    assert not waves[3].is_taper
    assert waves[3].volume_factor < waves[2].volume_factor
    assert waves[3].intensity_factor < 1.0


def test_volume_ramps_within_a_building_block():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    building = waves[0:3]
    volumes = [w.volume_factor for w in building]
    assert volumes == sorted(volumes)
    assert volumes[0] < volumes[-1]


def test_building_week_factors_are_anchored():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    assert waves[2].volume_factor == pytest.approx(1.10)
    assert waves[2].intensity_factor == pytest.approx(1.05)
    assert waves[3].volume_factor == pytest.approx(0.6)
    assert waves[3].intensity_factor == pytest.approx(0.9)


def test_taper_cuts_volume_but_keeps_intensity():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    taper = waves[-1]
    assert taper.is_taper
    assert taper.volume_factor < 0.7
    assert taper.intensity_factor >= 1.0


def test_deload_count_resets_after_taper_exclusion():
    # 9 weeks, deload every 4, taper 1: deloads at weeks 4 and 8, taper at 9
    waves = build_weekly_waves(total_weeks=9, deload_every=4, taper_weeks=1)
    deload_weeks = [w.week for w in waves if w.is_deload]
    assert deload_weeks == [4, 8]
    assert waves[-1].is_taper


def test_no_taper_when_taper_weeks_is_zero():
    waves = build_weekly_waves(total_weeks=4, deload_every=4, taper_weeks=0)
    assert not any(w.is_taper for w in waves)


def test_a_week_is_never_both_deload_and_taper():
    waves = build_weekly_waves(total_weeks=12, deload_every=4, taper_weeks=2)
    assert not any(w.is_deload and w.is_taper for w in waves)


def test_weeks_are_frozen_value_objects():
    week = WeekLoad(
        week=1, volume_factor=1.0, intensity_factor=1.0, is_deload=False, is_taper=False
    )
    with pytest.raises(AttributeError):
        week.volume_factor = 2.0  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    ("total_weeks", "deload_every", "taper_weeks"),
    [(0, 4, 1), (8, 1, 1), (8, 4, 8), (8, 4, -1)],
)
def test_inputs_are_validated(total_weeks, deload_every, taper_weeks):
    with pytest.raises(ValueError, match=r"weeks|deload"):
        build_weekly_waves(
            total_weeks=total_weeks, deload_every=deload_every, taper_weeks=taper_weeks
        )


@pytest.mark.parametrize(
    ("total_weeks", "deload_every", "taper_weeks"),
    [(8.0, 4, 1), (8, 4.5, 1), (8, 4, True)],
)
def test_non_integer_params_rejected(total_weeks, deload_every, taper_weeks):
    with pytest.raises(ValueError, match="whole number"):
        build_weekly_waves(
            total_weeks=total_weeks, deload_every=deload_every, taper_weeks=taper_weeks
        )


def test_block_twelve_weeks_splits_six_four_two():
    # round(12*0.50)=6, round(12*0.35)=4, 12-10=2
    weeks = build_block_periodization(total_weeks=12)
    phases = [w.phase for w in weeks]
    assert phases == ["accumulation"] * 6 + ["intensification"] * 4 + ["realization"] * 2
    assert [w.week for w in weeks] == list(range(1, 13))


def test_block_factors_match_phase_constants():
    weeks = build_block_periodization(total_weeks=12)
    assert weeks[0].volume_factor == pytest.approx(ACCUMULATION_VOLUME)
    assert weeks[0].intensity_factor == pytest.approx(ACCUMULATION_INTENSITY)
    assert weeks[6].volume_factor == pytest.approx(INTENSIFICATION_VOLUME)
    assert weeks[6].intensity_factor == pytest.approx(INTENSIFICATION_INTENSITY)
    assert weeks[10].volume_factor == pytest.approx(REALIZATION_VOLUME)
    assert weeks[10].intensity_factor == pytest.approx(REALIZATION_INTENSITY)


def test_block_six_weeks_keeps_one_week_per_phase():
    weeks = build_block_periodization(total_weeks=6)
    phases = [w.phase for w in weeks]
    assert phases == ["accumulation"] * 3 + ["intensification"] * 2 + ["realization"]


def test_block_rejects_fewer_than_six_weeks():
    with pytest.raises(ValueError, match="degenerate"):
        build_block_periodization(total_weeks=5)


@pytest.mark.parametrize("total_weeks", [12.0, True])
def test_block_rejects_non_whole_weeks(total_weeks):
    with pytest.raises(ValueError, match="whole number"):
        build_block_periodization(total_weeks=total_weeks)


def test_block_weeks_are_frozen_value_objects():
    week = BlockWeek(week=1, phase="accumulation", volume_factor=1.10, intensity_factor=0.85)
    with pytest.raises(AttributeError):
        week.volume_factor = 2.0  # ty: ignore[invalid-assignment]


def test_undulating_three_sessions_heavy_light_moderate():
    sessions = build_undulating_week(sessions_per_week=3)
    assert [s.session for s in sessions] == [1, 2, 3]
    assert [s.emphasis for s in sessions] == ["heavy", "light", "moderate"]
    assert sessions[0].intensity_low == pytest.approx(0.85)
    assert sessions[0].intensity_high == pytest.approx(0.925)
    assert sessions[1].intensity_low == pytest.approx(0.60)
    assert sessions[1].intensity_high == pytest.approx(0.70)
    assert sessions[2].intensity_low == pytest.approx(0.725)
    assert sessions[2].intensity_high == pytest.approx(0.80)


def test_undulating_five_sessions_wrap_the_cycle():
    sessions = build_undulating_week(sessions_per_week=5)
    assert [s.emphasis for s in sessions] == ["heavy", "light", "moderate", "heavy", "light"]


@pytest.mark.parametrize("sessions_per_week", [1, 8])
def test_undulating_rejects_out_of_range_sessions(sessions_per_week):
    with pytest.raises(ValueError, match="cannot undulate"):
        build_undulating_week(sessions_per_week=sessions_per_week)


def test_undulating_rejects_non_whole_sessions():
    with pytest.raises(ValueError, match="whole number"):
        build_undulating_week(sessions_per_week=3.0)  # ty: ignore[invalid-argument-type]
