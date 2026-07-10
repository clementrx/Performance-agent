from datetime import date

import pytest

from performance_agent.memory.store import (
    latest_program_version,
    read_program,
    save_program,
)

TODAY = date(2026, 7, 10)


def _read_program(tmp_path, version=None):
    result = read_program(tmp_path, version=version)
    assert result is not None
    return result


def test_no_programs_yet(tmp_path):
    assert latest_program_version(tmp_path) is None
    assert read_program(tmp_path) is None


def test_first_program_is_v1_and_needs_no_reason(tmp_path):
    path, version = save_program(tmp_path, "# Week 1\nRun easy.", "sub-45-10k", today=TODAY)
    assert version == 1
    assert path == tmp_path / "programs" / "program-v1.md"
    frontmatter, body = _read_program(tmp_path)
    assert frontmatter["version"] == 1
    assert frontmatter["goal_id"] == "sub-45-10k"
    assert frontmatter["created_on"] == "2026-07-10"
    assert frontmatter["reason"] is None
    assert body == "# Week 1\nRun easy."


def test_adaptation_requires_a_reason(tmp_path):
    save_program(tmp_path, "v1", "sub-45-10k", today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        save_program(tmp_path, "v2", "sub-45-10k", today=TODAY)


def test_adaptation_with_reason_creates_next_version(tmp_path):
    save_program(tmp_path, "v1", "sub-45-10k", today=TODAY)
    _, version = save_program(
        tmp_path, "v2", "sub-45-10k", reason="missed week 3 with a cold", today=TODAY
    )
    assert version == 2
    assert latest_program_version(tmp_path) == 2
    frontmatter, _ = _read_program(tmp_path)
    assert frontmatter["reason"] == "missed week 3 with a cold"


def test_old_versions_stay_readable(tmp_path):
    save_program(tmp_path, "first body", "sub-45-10k", today=TODAY)
    save_program(tmp_path, "second body", "sub-45-10k", reason="plateau", today=TODAY)
    frontmatter, body = _read_program(tmp_path, version=1)
    assert frontmatter["version"] == 1
    assert body == "first body"


def test_reading_a_missing_version_is_an_error(tmp_path):
    save_program(tmp_path, "v1", "sub-45-10k", today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read_program(tmp_path, version=7)


def test_program_body_may_contain_frontmatter_delimiters(tmp_path):
    body = "intro\n---\ntable section\n---\noutro"
    save_program(tmp_path, body, "sub-45-10k", today=TODAY)
    _, read_body = _read_program(tmp_path)
    assert read_body == body
