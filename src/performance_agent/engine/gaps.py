"""Gap analysis: athlete measurements vs event benchmarks (pure, deterministic).

Given a performance model's KPIs (each linked to a trainable quality with a
normalized weight) and the athlete's latest measurements, compute a per-KPI gap
to a chosen competitive level and a per-quality priority ranking (mean gap x
quality weight). The engine never guesses: a KPI with no measurement is
`unmeasured`, a KPI whose model carries no benchmark for the level is
`no_benchmark`; both are reported, never filled with a number.

Pydantic- and datetime-free: measurement staleness arrives as an integer day
count computed by the memory layer. Gap direction follows each KPI's
`higher_is_better` flag (a sprint time gap grows as the measured time rises above
the benchmark; a 1RM gap grows as the measured load falls below it).
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

GapStatus = Literal["measured", "unmeasured", "no_benchmark"]

# A measurement older than this is flagged stale (team-chosen prior): beyond a
# training block the number no longer reflects current capacity.
STALE_AFTER_DAYS = 180


@dataclass(frozen=True)
class KpiTarget:
    """One model KPI to evaluate: its quality, weight and level benchmarks."""

    kpi_id: str
    quality: str
    weight: float
    higher_is_better: bool
    benchmarks: tuple[tuple[str, float], ...]  # (level, value) pairs


@dataclass(frozen=True)
class Measurement:
    """The athlete's latest value for a KPI plus how old it is (days)."""

    kpi_id: str
    value: float
    staleness_days: int


@dataclass(frozen=True)
class KpiGap:
    """The gap for one KPI at the chosen level (None gap when not measurable)."""

    kpi_id: str
    quality: str
    status: GapStatus
    measured_value: float | None
    benchmark_value: float | None
    gap_fraction: float | None
    staleness_days: int | None
    stale: bool


@dataclass(frozen=True)
class QualityPriority:
    """A quality's training priority: mean measured gap x its weight."""

    quality: str
    weight: float
    mean_gap: float | None
    priority_score: float | None
    measured_kpis: int
    unmeasured_kpis: int


@dataclass(frozen=True)
class GapReport:
    """Per-KPI gaps and per-quality priorities against one competitive level."""

    level: str
    kpi_gaps: tuple[KpiGap, ...]
    quality_priorities: tuple[QualityPriority, ...]


def _benchmark_for(target: KpiTarget, level: str) -> float | None:
    for benchmark_level, value in target.benchmarks:
        if benchmark_level == level:
            return value
    return None


def _gap_fraction(measured: float, benchmark: float, *, higher_is_better: bool) -> float:
    """Non-negative shortfall as a fraction of the benchmark (0 when met/exceeded)."""
    if benchmark == 0:
        return 0.0
    deficit = (benchmark - measured) if higher_is_better else (measured - benchmark)
    return max(0.0, deficit / abs(benchmark))


def _kpi_gap(target: KpiTarget, measurement: Measurement | None, level: str) -> KpiGap:
    benchmark = _benchmark_for(target, level)
    if measurement is None:
        return KpiGap(
            kpi_id=target.kpi_id,
            quality=target.quality,
            status="unmeasured",
            measured_value=None,
            benchmark_value=benchmark,
            gap_fraction=None,
            staleness_days=None,
            stale=False,
        )
    if benchmark is None:
        return KpiGap(
            kpi_id=target.kpi_id,
            quality=target.quality,
            status="no_benchmark",
            measured_value=measurement.value,
            benchmark_value=None,
            gap_fraction=None,
            staleness_days=measurement.staleness_days,
            stale=measurement.staleness_days > STALE_AFTER_DAYS,
        )
    gap = _gap_fraction(measurement.value, benchmark, higher_is_better=target.higher_is_better)
    return KpiGap(
        kpi_id=target.kpi_id,
        quality=target.quality,
        status="measured",
        measured_value=measurement.value,
        benchmark_value=benchmark,
        gap_fraction=gap,
        staleness_days=measurement.staleness_days,
        stale=measurement.staleness_days > STALE_AFTER_DAYS,
    )


def _quality_priorities(targets: list[KpiTarget], gaps: list[KpiGap]) -> list[QualityPriority]:
    weight_by_quality: dict[str, float] = {}
    measured_gaps: dict[str, list[float]] = {}
    unmeasured: dict[str, int] = {}
    for target in targets:
        weight_by_quality[target.quality] = target.weight
        measured_gaps.setdefault(target.quality, [])
        unmeasured.setdefault(target.quality, 0)
    for gap in gaps:
        if gap.status == "measured" and gap.gap_fraction is not None:
            measured_gaps[gap.quality].append(gap.gap_fraction)
        else:
            unmeasured[gap.quality] += 1
    priorities: list[QualityPriority] = []
    for quality, weight in weight_by_quality.items():
        values = measured_gaps[quality]
        mean_gap = sum(values) / len(values) if values else None
        score = mean_gap * weight if mean_gap is not None else None
        priorities.append(
            QualityPriority(
                quality=quality,
                weight=weight,
                mean_gap=mean_gap,
                priority_score=score,
                measured_kpis=len(values),
                unmeasured_kpis=unmeasured[quality],
            )
        )
    # Highest priority first; unmeasured qualities (score None) sink to the end.
    priorities.sort(
        key=lambda p: (p.priority_score is not None, p.priority_score or 0.0), reverse=True
    )
    return priorities


def compute_gaps(
    targets: list[KpiTarget], measurements: list[Measurement], level: str
) -> GapReport:
    """Score each KPI against the level benchmark and rank quality priorities.

    measurements should carry the athlete's latest value per KPI (the memory
    layer resolves "latest"). A KPI with no measurement is `unmeasured`; a KPI
    with no benchmark for the level is `no_benchmark`; neither is given a number.
    Per-quality priority is the mean measured gap times the quality weight, sorted
    high to low with unmeasured qualities last. Deterministic; tie-broken by the
    input order of qualities.
    """
    if level not in ("recreational", "competitive", "national", "elite"):
        msg = f"level must be one of recreational/competitive/national/elite, got {level!r}"
        raise ValueError(msg)
    for target in targets:
        validate_finite(f"weight[{target.kpi_id}]", target.weight)
        for benchmark_level, value in target.benchmarks:
            validate_finite(f"benchmark[{target.kpi_id}:{benchmark_level}]", value)
    latest: dict[str, Measurement] = {}
    for measurement in measurements:
        validate_finite(f"measurement[{measurement.kpi_id}]", measurement.value)
        validate_whole_number(f"staleness_days[{measurement.kpi_id}]", measurement.staleness_days)
        if measurement.staleness_days < 0:
            msg = f"staleness_days must be non-negative, got {measurement.staleness_days!r}"
            raise ValueError(msg)
        latest[measurement.kpi_id] = measurement
    gaps = [_kpi_gap(target, latest.get(target.kpi_id), level) for target in targets]
    priorities = _quality_priorities(targets, gaps)
    return GapReport(level=level, kpi_gaps=tuple(gaps), quality_priorities=tuple(priorities))
