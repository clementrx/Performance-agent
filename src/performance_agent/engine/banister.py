"""Fitted two-component Banister impulse-response model (pure, deterministic).

p_hat(t) = p0 + k1 * g1(t) - k2 * g2(t), where g_tau(t) = sum_{s<=t} load(s)
e^{-(t-s)/tau} is the exponentially-weighted training-load trace. Fitting is a
coarse grid over (tau1, tau2) with a closed-form linear least squares for
(p0, k1, k2) at each grid point, then a local refinement — no external optimizer,
deterministic seeding. Fitness decays slower than fatigue, so tau1 > tau2 always.

Honesty gates: at least 8 weeks of daily load AND at least 5 performance points
spanning it; k1, k2 must be positive; a fit pinned at a tau bound is rejected as
not converged. A failing fit comes back usable=False with a reason, never a
fabricated parameter. CIs are approximate (OLS standard errors), labeled as such.

Impulse-response modeling follows Banister 1975 / Morton 1990 (added to the corpus
in the Phase 10 evidence pass; tau bounds are team-chosen priors until then).
"""

import math
from dataclasses import dataclass

from performance_agent.engine._validation import validate_finite, validate_whole_number

_MIN_LOAD_DAYS = 56  # 8 weeks of daily load history
_MIN_PERF_POINTS = 5
_MIN_PERF_SPAN_FRACTION = 0.5  # performance points must span >= half the load window
_CI_Z = 1.96
_SINGULAR_EPS = 1e-12
_N_PARAMS = 3  # p0, k1, k2

# tau grids (days). Endpoints double as the "pinned" bounds: a coarse best landing
# on one is treated as non-convergence. Fitness (tau1) decays slower than fatigue.
_TAU1_GRID = (14, 21, 28, 35, 42, 49, 56)
_TAU2_GRID = (2, 4, 6, 8, 10, 12, 14, 16, 18, 20)
_REFINE1 = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
_REFINE2 = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)


@dataclass(frozen=True)
class PerformancePoint:
    """One dated performance observation (day index into the load series, value)."""

    day_index: int
    value: float


@dataclass(frozen=True)
class BanisterFit:
    """A fitted Banister model with approximate CIs and an honesty verdict."""

    p0: float
    k1: float
    k2: float
    tau1: float
    tau2: float
    r2: float
    residual_se: float
    k1_ci_half: float
    k2_ci_half: float
    usable: bool
    reason: str | None


def _decay_trace(loads: list[float], tau: float) -> list[float]:
    """g_tau(t) = sum_{s<=t} load(s) e^{-(t-s)/tau}, via the O(n) EWMA recursion."""
    decay = math.exp(-1.0 / tau)
    trace: list[float] = []
    accumulated = 0.0
    for load in loads:
        accumulated = decay * accumulated + load
        trace.append(accumulated)
    return trace


def _solve3(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve a 3x3 linear system by Gaussian elimination (None if singular)."""
    m = [[*row, b[i]] for i, row in enumerate(a)]
    for col in range(3):
        pivot_row = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[pivot_row][col]) < _SINGULAR_EPS:
            return None
        m[col], m[pivot_row] = m[pivot_row], m[col]
        for r in range(3):
            if r != col:
                factor = m[r][col] / m[col][col]
                for c in range(col, 4):
                    m[r][c] -= factor * m[col][c]
    return [m[i][3] / m[i][i] for i in range(3)]


def _normal_matrix(features: list[tuple[float, float, float]]) -> list[list[float]]:
    ata = [[0.0] * 3 for _ in range(3)]
    for row in features:
        for i in range(3):
            for j in range(3):
                ata[i][j] += row[i] * row[j]
    return ata


def _ols(
    features: list[tuple[float, float, float]], ys: list[float]
) -> tuple[list[float], float] | None:
    """Return ([b0, b1, b2], sse) for y ~ b0 + b1*x1 + b2*x2, or None if singular."""
    ata = _normal_matrix(features)
    atb = [sum(row[i] * y for row, y in zip(features, ys, strict=True)) for i in range(3)]
    coeffs = _solve3(ata, atb)
    if coeffs is None:
        return None
    sse = 0.0
    for row, y in zip(features, ys, strict=True):
        prediction = sum(coeffs[i] * row[i] for i in range(3))
        sse += (y - prediction) ** 2
    return coeffs, sse


def _features_at(
    points: list[PerformancePoint], g1: list[float], g2: list[float]
) -> list[tuple[float, float, float]]:
    return [(1.0, g1[p.day_index], g2[p.day_index]) for p in points]


def _fit_at_tau(
    loads: list[float], points: list[PerformancePoint], tau1: float, tau2: float
) -> tuple[list[float], float] | None:
    g1 = _decay_trace(loads, tau1)
    g2 = _decay_trace(loads, tau2)
    return _ols(_features_at(points, g1, g2), [p.value for p in points])


def _best_on_grid(
    loads: list[float],
    points: list[PerformancePoint],
    tau1_values,
    tau2_values,
) -> tuple[float, float, list[float], float] | None:
    best: tuple[float, float, list[float], float] | None = None
    for tau1 in tau1_values:
        for tau2 in tau2_values:
            if tau1 <= tau2:
                continue
            fit = _fit_at_tau(loads, points, tau1, tau2)
            if fit is None:
                continue
            coeffs, sse = fit
            if best is None or sse < best[3]:
                best = (tau1, tau2, coeffs, sse)
    return best


def _refine(
    loads: list[float], points: list[PerformancePoint], tau1: float, tau2: float
) -> tuple[float, float, list[float], float]:
    tau1_values = [tau1 + d for d in _REFINE1 if tau1 + d > 0]
    tau2_values = [tau2 + d for d in _REFINE2 if tau2 + d > 0]
    refined = _best_on_grid(loads, points, tau1_values, tau2_values)
    if refined is not None:
        return refined
    # A refit at the coarse best always succeeds when the coarse fit did.
    fit = _fit_at_tau(loads, points, tau1, tau2)
    if fit is None:
        msg = "coarse fit succeeded but refit failed (unreachable)"
        raise RuntimeError(msg)
    coeffs, sse = fit
    return tau1, tau2, coeffs, sse


def _gate(loads: list[float], points: list[PerformancePoint]) -> str | None:
    if len(loads) < _MIN_LOAD_DAYS:
        weeks = _MIN_LOAD_DAYS // 7
        return f"need >= {_MIN_LOAD_DAYS} days of load history ({weeks} weeks), got {len(loads)}"
    if len(points) < _MIN_PERF_POINTS:
        return f"need >= {_MIN_PERF_POINTS} performance points, got {len(points)}"
    span = max(p.day_index for p in points) - min(p.day_index for p in points)
    if span < _MIN_PERF_SPAN_FRACTION * (len(loads) - 1):
        return "performance points do not span enough of the load history"
    return None


def _ci_halves(
    features: list[tuple[float, float, float]], sse: float, n: int
) -> tuple[float, float]:
    dof = n - _N_PARAMS
    residual_var = sse / dof if dof > 0 else 0.0
    ata = _normal_matrix(features)
    identity = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    cov_diag: list[float] = []
    for i in range(3):
        col = _solve3(ata, identity[i])
        if col is None:
            return 0.0, 0.0
        cov_diag.append(col[i])
    var_k1 = residual_var * cov_diag[1]
    var_k2 = residual_var * cov_diag[2]
    return _CI_Z * math.sqrt(max(0.0, var_k1)), _CI_Z * math.sqrt(max(0.0, var_k2))


def _verdict(tau1: float, tau2: float, k1: float, k2: float) -> tuple[bool, str | None]:
    if tau1 in (_TAU1_GRID[0], _TAU1_GRID[-1]) or tau2 in (_TAU2_GRID[0], _TAU2_GRID[-1]):
        return False, "fit pinned at a tau bound; not converged (treat as unusable)"
    if k1 <= 0 or k2 <= 0:
        return False, "fitted gains are not both positive; impulse-response shape implausible"
    return True, None


def fit_banister(loads: list[float], points: list[PerformancePoint]) -> BanisterFit:
    """Fit the two-component Banister model to daily loads and dated performances.

    Grid-searches (tau1, tau2) with tau1 > tau2, solving (p0, k1, k2) in closed form
    at each node, then refines locally. Returns params, R^2, residual SE, and
    approximate 95% CI half-widths for k1/k2. usable=False (with a reason) when the
    data is too thin, the fit is pinned at a tau bound, or a gain is non-positive.
    Raises on non-finite inputs.
    """
    for load in loads:
        validate_finite("load", load)
    for point in points:
        validate_whole_number("day_index", point.day_index)
        validate_finite("performance", point.value)
        if not 0 <= point.day_index < len(loads):
            msg = f"performance day_index {point.day_index} is outside the load series"
            raise ValueError(msg)
    gate_reason = _gate(loads, points)
    coarse = _best_on_grid(loads, points, _TAU1_GRID, _TAU2_GRID)
    if coarse is None:
        return _degenerate_fit(gate_reason or "could not fit any grid point (degenerate data)")
    tau1_c, tau2_c, _, _ = coarse
    tau1, tau2, coeffs, sse = _refine(loads, points, tau1_c, tau2_c)
    p0, b1, b2 = coeffs
    k1, k2 = b1, -b2
    ys = [p.value for p in points]
    features = _features_at(points, _decay_trace(loads, tau1), _decay_trace(loads, tau2))
    r2 = _r2(ys, sse)
    residual_se = math.sqrt(sse / (len(points) - _N_PARAMS)) if len(points) > _N_PARAMS else 0.0
    k1_ci, k2_ci = _ci_halves(features, sse, len(points))
    verdict_usable, verdict_reason = _verdict(tau1_c, tau2_c, k1, k2)
    reason = gate_reason or verdict_reason
    return BanisterFit(
        p0=p0,
        k1=k1,
        k2=k2,
        tau1=tau1,
        tau2=tau2,
        r2=r2,
        residual_se=residual_se,
        k1_ci_half=k1_ci,
        k2_ci_half=k2_ci,
        usable=verdict_usable and gate_reason is None,
        reason=reason,
    )


def _r2(ys: list[float], sse: float) -> float:
    mean_y = sum(ys) / len(ys)
    sst = sum((y - mean_y) ** 2 for y in ys)
    return 1.0 - sse / sst if sst > 0 else 1.0


def _degenerate_fit(reason: str) -> BanisterFit:
    return BanisterFit(
        p0=0.0,
        k1=0.0,
        k2=0.0,
        tau1=0.0,
        tau2=0.0,
        r2=0.0,
        residual_se=0.0,
        k1_ci_half=0.0,
        k2_ci_half=0.0,
        usable=False,
        reason=reason,
    )
