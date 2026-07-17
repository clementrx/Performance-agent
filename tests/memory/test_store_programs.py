import pytest

from performance_agent.memory.store import (
    latest_program_version,
    read_program,
    save_program,
)
from tests.program_plans import FIXTURE_TODAY, minimal_plan

TODAY = FIXTURE_TODAY


def _read(tmp_path, version=None):
    result = read_program(tmp_path, version=version)
    assert result is not None
    return result


def test_no_programs_yet(tmp_path):
    assert latest_program_version(tmp_path) is None
    assert read_program(tmp_path) is None


def test_first_program_writes_yaml_and_md_pair(tmp_path):
    md_path, version = save_program(tmp_path, minimal_plan(), today=TODAY)
    assert version == 1
    assert md_path == tmp_path / "programs" / "program-v1.md"
    assert (tmp_path / "programs" / "program-v1.plan.yaml").exists()
    program = _read(tmp_path)
    assert program.version == 1
    assert program.goal_id == "squat-160"
    assert program.created_on == "2026-07-12"
    assert program.reason is None
    assert program.plan is not None
    assert program.plan.mesocycles[0].weeks[0].sessions[0].id == "w01-s1-lower-heavy"
    assert "# Program v1 — 20260712 — squat-160" in program.markdown


def test_store_stamps_authoritative_version_over_the_plan(tmp_path):
    # The plan claims version 9; the store computes and stamps the real one.
    save_program(tmp_path, minimal_plan(), today=TODAY)
    _, version = save_program(
        tmp_path, minimal_plan(version=9), reason="format upgrade", today=TODAY
    )
    assert version == 2
    assert _read(tmp_path).plan.version == 2


def test_adaptation_requires_a_reason(tmp_path):
    save_program(tmp_path, minimal_plan(), today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        save_program(tmp_path, minimal_plan(), today=TODAY)


def test_adaptation_with_reason_creates_next_version(tmp_path):
    save_program(tmp_path, minimal_plan(), today=TODAY)
    _, version = save_program(
        tmp_path, minimal_plan(), reason="missed week 3 with a cold", today=TODAY
    )
    assert version == 2
    assert latest_program_version(tmp_path) == 2
    assert _read(tmp_path).reason == "missed week 3 with a cold"


def test_old_versions_stay_readable(tmp_path):
    save_program(tmp_path, minimal_plan(goal_id="squat-160"), today=TODAY)
    save_program(tmp_path, minimal_plan(goal_id="bench-120"), reason="new goal", today=TODAY)
    program = _read(tmp_path, version=1)
    assert program.version == 1
    assert program.goal_id == "squat-160"


def test_reading_a_missing_version_is_an_error(tmp_path):
    save_program(tmp_path, minimal_plan(), today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read_program(tmp_path, version=7)


def test_legacy_prose_only_program_reads_with_plan_none(tmp_path):
    # A program saved before the structured format: frontmatter + body, no yaml.
    programs = tmp_path / "programs"
    programs.mkdir()
    (programs / "program-v1.md").write_text(
        "---\nversion: 1\ngoal_id: sub-45-10k\ncreated_on: 2026-01-01\nreason: null\n"
        "---\n\n# Week 1\nRun easy.\n",
        encoding="utf-8",
    )
    program = _read(tmp_path)
    assert program.plan is None
    assert program.goal_id == "sub-45-10k"
    assert program.markdown == "# Week 1\nRun easy."


def test_new_version_after_legacy_prose_program(tmp_path):
    # Legacy prose v1 must not block saving a structured v2 (format upgrade).
    programs = tmp_path / "programs"
    programs.mkdir()
    (programs / "program-v1.md").write_text(
        "---\nversion: 1\ngoal_id: squat-160\ncreated_on: 2026-01-01\nreason: null\n"
        "---\n\nprose only\n",
        encoding="utf-8",
    )
    _, version = save_program(tmp_path, minimal_plan(), reason="format upgrade", today=TODAY)
    assert version == 2
    assert _read(tmp_path, version=2).plan is not None
    assert _read(tmp_path, version=1).plan is None
