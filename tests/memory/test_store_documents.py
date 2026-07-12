from datetime import date

import pytest

from performance_agent.memory.store import (
    read_analysis,
    read_nutrition_frame,
    read_program,
    read_research_dossier,
    save_analysis,
    save_nutrition_frame,
    save_program,
    save_research_dossier,
)
from tests.program_plans import minimal_plan

TODAY = date(2026, 7, 11)

DOC_KINDS = [
    pytest.param(save_analysis, read_analysis, "analysis", "needs-analysis", id="analysis"),
    pytest.param(
        save_research_dossier, read_research_dossier, "research", "dossier", id="research"
    ),
    pytest.param(save_nutrition_frame, read_nutrition_frame, "nutrition", "frame", id="nutrition"),
]


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_no_documents_yet(tmp_path, save, read, subdir, prefix):  # noqa: ARG001 - parametrize shape
    assert read(tmp_path) is None


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_first_version_is_v1_and_needs_no_reason(tmp_path, save, read, subdir, prefix):
    path, version = save(tmp_path, "# Section\nbody.", "squat-160", today=TODAY)
    assert version == 1
    assert path == tmp_path / subdir / f"{prefix}-v1.md"
    result = read(tmp_path)
    assert result is not None
    frontmatter, body = result
    assert frontmatter["version"] == 1
    assert frontmatter["goal_id"] == "squat-160"
    assert frontmatter["created_on"] == "2026-07-11"
    assert frontmatter["reason"] is None
    assert body == "# Section\nbody."


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_revision_requires_a_reason(tmp_path, save, read, subdir, prefix):  # noqa: ARG001 - parametrize shape
    save(tmp_path, "v1", "squat-160", today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        save(tmp_path, "v2", "squat-160", today=TODAY)
    _, version = save(tmp_path, "v2", "squat-160", reason="goal renegotiated", today=TODAY)
    assert version == 2


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_old_versions_stay_readable(tmp_path, save, read, subdir, prefix):  # noqa: ARG001 - parametrize shape
    save(tmp_path, "first body", "squat-160", today=TODAY)
    save(tmp_path, "second body", "squat-160", reason="re-run", today=TODAY)
    result = read(tmp_path, version=1)
    assert result is not None
    frontmatter, body = result
    assert frontmatter["version"] == 1
    assert body == "first body"


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_reading_a_missing_version_is_an_error(tmp_path, save, read, subdir, prefix):  # noqa: ARG001 - parametrize shape
    save(tmp_path, "v1", "squat-160", today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read(tmp_path, version=7)


def test_document_families_version_independently(tmp_path):
    save_program(tmp_path, minimal_plan(), today=TODAY)
    save_analysis(tmp_path, "analysis", "squat-160", today=TODAY)
    save_research_dossier(tmp_path, "dossier", "squat-160", today=TODAY)
    save_nutrition_frame(tmp_path, "frame", "squat-160", today=TODAY)
    # Each family has its own v1 counter — a program does not bump the analysis.
    path, version = save_analysis(
        tmp_path, "analysis v2", "squat-160", reason="verdict changed", today=TODAY
    )
    assert version == 2
    assert path == tmp_path / "analysis" / "needs-analysis-v2.md"
    program = read_program(tmp_path)
    assert program is not None
    assert program.version == 1
    frame = read_nutrition_frame(tmp_path)
    assert frame is not None
    assert frame[0]["version"] == 1
