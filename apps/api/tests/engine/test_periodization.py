import pytest

from performance_agent.engine.periodization import WeekLoad, build_weekly_waves


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
