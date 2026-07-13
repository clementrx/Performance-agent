"""Schema tests for the PerformanceModel and its parts (validation is the contract)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    Benchmark,
    EnergySystemSplit,
    InjuryRiskEntry,
    KpiSpec,
    PerformanceModel,
    PerformanceQuality,
    Provenance,
    QualityRequirement,
)


def _prior() -> Provenance:
    return Provenance(kind="prior")


def _quality(name: PerformanceQuality = "max_strength", weight: float = 0.5) -> QualityRequirement:
    return QualityRequirement(quality=name, weight=weight, provenance=_prior())


def _model(**overrides) -> PerformanceModel:
    base = {
        "discipline": "athletics",
        "event": "100m sprint",
        "qualities": [
            _quality("max_strength", 0.4),
            _quality("reactive_strength", 0.6),
        ],
        "kpis": [
            KpiSpec(
                id="squat-1rm",
                name="Back squat 1RM",
                quality="max_strength",
                protocol="one-rep-max test after warm-up ramp",
                test_protocol="one_rm_test",
                unit="kg",
                benchmarks=[Benchmark(level="elite", value=180.0, provenance=_prior())],
            )
        ],
    }
    base.update(overrides)
    return PerformanceModel.model_validate(base)


def test_round_trip_preserves_fields():
    model = _model()
    reloaded = PerformanceModel.model_validate(model.model_dump(mode="json"))
    assert reloaded.discipline == "athletics"
    assert reloaded.event == "100m sprint"
    assert reloaded.schema_version == 1
    assert {q.quality for q in reloaded.qualities} == {"max_strength", "reactive_strength"}


def test_quality_weights_are_normalized_to_sum_one():
    model = _model(qualities=[_quality("speed", 0.8), _quality("acceleration", 0.8)])
    assert sum(q.weight for q in model.qualities) == pytest.approx(1.0)
    assert all(q.weight == pytest.approx(0.5) for q in model.qualities)


def test_empty_qualities_rejected():
    with pytest.raises(ValidationError):
        _model(qualities=[])


def test_zero_weights_not_normalizable_rejected():
    with pytest.raises(ValidationError, match="not normalizable"):
        _model(qualities=[_quality("speed", 0.0), _quality("acceleration", 0.0)])


def test_unknown_quality_name_rejected():
    with pytest.raises(ValidationError):
        _model(
            qualities=[{"quality": "explosiveness", "weight": 0.5, "provenance": {"kind": "prior"}}]
        )


def test_cited_provenance_requires_cite_ids():
    with pytest.raises(ValidationError, match="cited provenance requires"):
        Provenance(kind="cited")


def test_cited_provenance_with_ids_ok():
    prov = Provenance(kind="cited", cite_ids=["suchomel-2016"])
    assert prov.cite_ids == ["suchomel-2016"]


def test_non_cited_provenance_rejects_cite_ids():
    with pytest.raises(ValidationError, match="must not carry cite_ids"):
        Provenance(kind="prior", cite_ids=["x"])


def test_kpi_without_protocol_rejected():
    with pytest.raises(ValidationError):
        KpiSpec(id="k", name="K", quality="speed", protocol="", unit="s")


def test_kpi_without_unit_rejected():
    with pytest.raises(ValidationError):
        KpiSpec(id="k", name="K", quality="speed", protocol="timed run", unit="")


def test_duplicate_kpi_ids_rejected():
    kpi = KpiSpec(id="dup", name="K", quality="speed", protocol="p", unit="s")
    with pytest.raises(ValidationError, match="unique"):
        _model(kpis=[kpi, kpi])


def test_duplicate_benchmark_levels_rejected():
    with pytest.raises(ValidationError, match="duplicate benchmark levels"):
        KpiSpec(
            id="k",
            name="K",
            quality="speed",
            protocol="p",
            unit="s",
            benchmarks=[
                Benchmark(level="elite", value=1.0, provenance=_prior()),
                Benchmark(level="elite", value=2.0, provenance=_prior()),
            ],
        )


def test_energy_split_must_sum_to_one():
    with pytest.raises(ValidationError, match="sum to"):
        EnergySystemSplit(
            aerobic=0.5,
            anaerobic_lactic=0.5,
            anaerobic_alactic=0.5,
            provenance=_prior(),
        )


def test_energy_split_within_tolerance_ok():
    split = EnergySystemSplit(
        aerobic=0.1,
        anaerobic_lactic=0.3,
        anaerobic_alactic=0.6,
        provenance=_prior(),
    )
    assert split.aerobic == pytest.approx(0.1)


def test_injury_risk_requires_all_fields():
    with pytest.raises(ValidationError):
        InjuryRiskEntry(region="hamstring", mechanism="", screen="NHE", provenance=_prior())


_QUALITY_NAMES: list[PerformanceQuality] = [
    "max_strength",
    "speed",
    "acceleration",
    "hypertrophy",
    "aerobic_capacity",
]


@given(
    weights=st.lists(st.floats(min_value=0.01, max_value=1.0), min_size=2, max_size=5),
    seed=st.randoms(use_true_random=False),
)
def test_normalization_invariant_under_permutation(weights, seed):
    names = _QUALITY_NAMES[: len(weights)]
    reqs = [_quality(name, w) for name, w in zip(names, weights, strict=True)]
    forward = _model(qualities=list(reqs))
    shuffled = list(zip(names, weights, strict=True))
    seed.shuffle(shuffled)
    reverse = _model(qualities=[_quality(n, w) for n, w in shuffled])
    forward_map = {q.quality: q.weight for q in forward.qualities}
    reverse_map = {q.quality: q.weight for q in reverse.qualities}
    assert forward_map.keys() == reverse_map.keys()
    for quality, weight in forward_map.items():
        assert weight == pytest.approx(reverse_map[quality])
    assert sum(forward_map.values()) == pytest.approx(1.0)
