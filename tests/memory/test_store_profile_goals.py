from datetime import date

from performance_agent.memory.schemas import Goal, Injury, Profile
from performance_agent.memory.store import (
    read_goals,
    read_profile,
    upsert_goal,
    write_profile,
)


def test_missing_profile_returns_defaults(tmp_path):
    profile = read_profile(tmp_path)
    assert profile.locale == "en"


def test_profile_round_trips_through_readable_yaml(tmp_path):
    original = Profile(
        locale="fr",
        weight_kg=75.5,
        injuries=[Injury(area="left knee", noted_on=date(2026, 6, 1))],
        notes=["déteste les burpees"],
    )
    path = write_profile(tmp_path, original)
    assert path == tmp_path / "profile.yaml"
    text = path.read_text(encoding="utf-8")
    assert "déteste les burpees" in text  # human-readable, unicode intact
    assert read_profile(tmp_path) == original


def test_write_is_atomic_no_tmp_left_behind(tmp_path):
    write_profile(tmp_path, Profile())
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_goals_empty_when_missing(tmp_path):
    assert read_goals(tmp_path) == []


def test_upsert_goal_adds_then_replaces_by_id(tmp_path):
    first = Goal(id="sub-45-10k", statement="10K under 45:00")
    upsert_goal(tmp_path, first)
    updated = Goal(id="sub-45-10k", statement="10K under 45:00", status="achieved")
    goals = upsert_goal(tmp_path, updated)
    assert len(goals) == 1
    assert read_goals(tmp_path)[0].status == "achieved"


def test_upsert_keeps_other_goals(tmp_path):
    upsert_goal(tmp_path, Goal(id="goal-a", statement="A"))
    goals = upsert_goal(tmp_path, Goal(id="goal-b", statement="B"))
    assert {g.id for g in goals} == {"goal-a", "goal-b"}
