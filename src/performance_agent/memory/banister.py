"""Fitted Banister model at the athlete layer: build load & performance series.

The engine (engine/banister.py) is pydantic- and datetime-free; this module turns
the athlete's session log into a daily session-RPE load series and the KPI-results
log into dated performance points for one chosen KPI, then calls the pure fitter.
It stores nothing — the fitted params are handed back for the response profile to
persist. Honesty gates live in the engine; a thin history returns usable=False.
"""

from datetime import date
from pathlib import Path

from performance_agent.engine.banister import PerformancePoint, fit_banister
from performance_agent.engine.load import session_rpe_load
from performance_agent.memory import store
from performance_agent.memory.schemas import BanisterParams


def _daily_loads(base_dir: Path, kpi_id: str) -> tuple[list[float], date | None]:
    sessions = store.read_sessions(base_dir)
    kpis = [r for r in store.read_kpi_results(base_dir) if r.kpi_id == kpi_id]
    dates = [s.performed_at.date() for s in sessions] + [r.date for r in kpis]
    if not dates:
        return [], None
    origin = min(dates)
    n_days = (max(dates) - origin).days + 1
    loads = [0.0] * n_days
    for entry in sessions:
        if entry.rpe is not None and entry.duration_min is not None:
            index = (entry.performed_at.date() - origin).days
            loads[index] += session_rpe_load(entry.rpe, entry.duration_min)
    return loads, origin


def fit_kpi_banister(base_dir: Path, kpi_id: str) -> BanisterParams:
    """Fit the Banister model against one KPI's measurements, from logged loads.

    Builds a daily session-RPE load series and the KPI's dated performance points,
    then calls the pure fitter. Returns BanisterParams with usable + the fit
    quality; when the history is too thin or the fit is pinned/implausible, usable
    is False and the params are recorded for transparency, never used for decisions.
    """
    loads, origin = _daily_loads(base_dir, kpi_id)
    kpis = [r for r in store.read_kpi_results(base_dir) if r.kpi_id == kpi_id]
    points = (
        [PerformancePoint(day_index=(r.date - origin).days, value=r.value) for r in kpis]
        if origin is not None
        else []
    )
    fit = fit_banister(loads, points)
    return BanisterParams(
        p0=fit.p0,
        k1=fit.k1,
        k2=fit.k2,
        tau1=max(fit.tau1, 1e-6),
        tau2=max(fit.tau2, 1e-6),
        r2=fit.r2,
        residual_se=fit.residual_se,
        k1_ci_half=fit.k1_ci_half,
        k2_ci_half=fit.k2_ci_half,
        fitted_kpi_id=kpi_id,
        n_load_days=len(loads),
        n_performance_points=len(points),
        usable=fit.usable,
    )
