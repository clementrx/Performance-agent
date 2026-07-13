"""Store tests for the append-only KPI-results log."""

from datetime import date

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import KpiResult
from performance_agent.memory.store import append_kpi_result, read_kpi_results


def test_no_log_yet(tmp_path):
    assert read_kpi_results(tmp_path) == []


def test_append_and_read_in_order(tmp_path):
    append_kpi_result(
        tmp_path,
        KpiResult(date=date(2026, 7, 1), kpi_id="squat", protocol="1rm", value=180.0, unit="kg"),
    )
    append_kpi_result(
        tmp_path,
        KpiResult(
            date=date(2026, 7, 8),
            kpi_id="cmj",
            protocol="jump mat",
            value=52.0,
            unit="cm",
            context={"bodyweight": 78.0, "surface": "hard court"},
        ),
    )
    results = read_kpi_results(tmp_path)
    assert [r.kpi_id for r in results] == ["squat", "cmj"]
    assert results[1].context["bodyweight"] == 78.0
    assert results[1].context["surface"] == "hard court"


def test_kpi_id_optional(tmp_path):
    append_kpi_result(
        tmp_path,
        KpiResult(date=date(2026, 7, 1), protocol="sprint split", value=1.7, unit="s"),
    )
    assert read_kpi_results(tmp_path)[0].kpi_id is None


def test_protocol_required():
    with pytest.raises(ValidationError):
        KpiResult(date=date(2026, 7, 1), protocol="", value=1.0, unit="s")


def test_unit_required():
    with pytest.raises(ValidationError):
        KpiResult(date=date(2026, 7, 1), protocol="test", value=1.0, unit="")
