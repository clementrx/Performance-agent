"""Store tests for the versioned, immutable performance-model YAML documents."""

import pytest

from performance_agent.memory.schemas import (
    PerformanceModel,
    Provenance,
    QualityRequirement,
)
from performance_agent.memory.store import (
    latest_performance_model_version,
    read_performance_model,
    save_performance_model,
)


def _model() -> PerformanceModel:
    return PerformanceModel(
        discipline="athletics",
        event="100m sprint",
        qualities=[
            QualityRequirement(
                quality="reactive_strength", weight=0.6, provenance=Provenance(kind="prior")
            ),
            QualityRequirement(
                quality="max_strength", weight=0.4, provenance=Provenance(kind="prior")
            ),
        ],
    )


def test_no_model_yet(tmp_path):
    assert latest_performance_model_version(tmp_path) is None
    assert read_performance_model(tmp_path) is None


def test_first_model_writes_yaml(tmp_path):
    path, version = save_performance_model(tmp_path, _model())
    assert version == 1
    assert path == tmp_path / "models" / "performance-model-v1.yaml"
    stored = read_performance_model(tmp_path)
    assert stored is not None
    assert stored.version == 1
    assert stored.event == "100m sprint"
    assert sum(q.weight for q in stored.qualities) == pytest.approx(1.0)


def test_second_version_requires_reason(tmp_path):
    save_performance_model(tmp_path, _model())
    with pytest.raises(ValueError, match="reason"):
        save_performance_model(tmp_path, _model())


def test_second_version_with_reason_stamps_it(tmp_path):
    save_performance_model(tmp_path, _model())
    _, version = save_performance_model(
        tmp_path, _model(), reason="added anaerobic-alactic KPI after research"
    )
    assert version == 2
    assert latest_performance_model_version(tmp_path) == 2
    stored = read_performance_model(tmp_path)
    assert stored is not None
    assert stored.reason == "added anaerobic-alactic KPI after research"


def test_versions_are_immutable_old_stays_readable(tmp_path):
    save_performance_model(tmp_path, _model())
    save_performance_model(tmp_path, _model(), reason="update")
    v1 = read_performance_model(tmp_path, version=1)
    assert v1 is not None
    assert v1.version == 1
    assert v1.reason is None


def test_reading_missing_version_errors(tmp_path):
    save_performance_model(tmp_path, _model())
    with pytest.raises(ValueError, match="version 7"):
        read_performance_model(tmp_path, version=7)
