"""Watch reports: immutable versioned docs under watch/."""

import pytest

from performance_agent.memory import store


def test_first_report_is_v1_and_readable(tmp_path):
    path, version = store.save_watch_report(tmp_path, "All lifts on track.", "goal-1")
    assert version == 1
    assert path == tmp_path / "watch" / "report-v1.md"
    stored = store.read_watch_report(tmp_path)
    assert stored is not None
    frontmatter, body = stored
    assert frontmatter["version"] == 1
    assert body == "All lifts on track."


def test_v2_requires_reason(tmp_path):
    store.save_watch_report(tmp_path, "v1", "goal-1")
    with pytest.raises(ValueError, match="reason"):
        store.save_watch_report(tmp_path, "v2", "goal-1")
    _, version = store.save_watch_report(tmp_path, "v2", "goal-1", reason="biweekly watch")
    assert version == 2


def test_latest_version_none_when_empty(tmp_path):
    assert store.latest_watch_report_version(tmp_path) is None
