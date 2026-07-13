"""Athlete-layer tests: fit the Banister model from logged sessions + KPI results."""

from datetime import date, datetime, timedelta

from performance_agent.engine.banister import PerformancePoint, _decay_trace, fit_banister
from performance_agent.engine.load import session_rpe_load
from performance_agent.memory import store
from performance_agent.memory.banister import fit_kpi_banister
from performance_agent.memory.schemas import KpiResult, SessionEntry

ORIGIN = date(2026, 1, 1)


def _log_daily_sessions(base_dir, n_days, rpe=5, duration=12):
    for i in range(n_days):
        at = datetime(ORIGIN.year, ORIGIN.month, ORIGIN.day) + timedelta(days=i)
        store.append_session(
            base_dir, SessionEntry(performed_at=at, rpe=rpe, duration_min=duration)
        )


def test_thin_history_refused(tmp_path):
    _log_daily_sessions(tmp_path, 20)
    store.append_kpi_result(
        tmp_path,
        KpiResult(date=ORIGIN, kpi_id="squat-e1rm", protocol="1rm", value=150.0, unit="kg"),
    )
    params = fit_kpi_banister(tmp_path, "squat-e1rm")
    assert params.usable is False
    assert params.n_performance_points == 1


def test_usable_fit_recovers_params(tmp_path):
    n_days = 84
    rpe, duration = 5, 12
    _log_daily_sessions(tmp_path, n_days, rpe=rpe, duration=duration)
    daily_load = session_rpe_load(rpe, duration)
    loads = [daily_load] * n_days
    p0, k1, k2, tau1, tau2 = 100.0, 0.05, 0.07, 40.0, 8.0
    g1 = _decay_trace(loads, tau1)
    g2 = _decay_trace(loads, tau2)
    for day in [10, 25, 40, 55, 70, 82]:
        value = p0 + k1 * g1[day] - k2 * g2[day]
        store.append_kpi_result(
            tmp_path,
            KpiResult(
                date=ORIGIN + timedelta(days=day),
                kpi_id="squat-e1rm",
                protocol="1rm",
                value=value,
                unit="kg",
            ),
        )
    params = fit_kpi_banister(tmp_path, "squat-e1rm")
    assert params.usable is True
    assert params.tau1 > params.tau2
    assert params.fitted_kpi_id == "squat-e1rm"
    assert params.n_load_days == n_days
    # Cross-check against the engine on the same reconstructed series.
    points = [
        PerformancePoint(day_index=day, value=p0 + k1 * g1[day] - k2 * g2[day])
        for day in [10, 25, 40, 55, 70, 82]
    ]
    assert fit_banister(loads, points).usable is True
