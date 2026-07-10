"""Read/write operations for the athlete data directory.

All writes are atomic (temp file + os.replace) and schema-validated. The store
never deletes history: logs are append-only and program versions are immutable.
"""

import os
from pathlib import Path

import yaml

from performance_agent.memory.schemas import Goal, Profile

PROFILE_FILE = "profile.yaml"
GOALS_FILE = "goals.yaml"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _to_yaml(data: object) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def read_profile(base_dir: Path) -> Profile:
    """Return the stored profile, or a default Profile when none exists."""
    path = base_dir / PROFILE_FILE
    if not path.exists():
        return Profile()
    return Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def write_profile(base_dir: Path, profile: Profile) -> Path:
    """Persist the profile as readable YAML; returns the file path."""
    path = base_dir / PROFILE_FILE
    _atomic_write(path, _to_yaml(profile.model_dump(mode="json")))
    return path


def read_goals(base_dir: Path) -> list[Goal]:
    """Return all stored goals (empty list when the file is missing)."""
    path = base_dir / GOALS_FILE
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Goal.model_validate(item) for item in raw]


def upsert_goal(base_dir: Path, goal: Goal) -> list[Goal]:
    """Add a goal or replace the one with the same id; returns the updated list."""
    goals = [g for g in read_goals(base_dir) if g.id != goal.id]
    goals.append(goal)
    _atomic_write(
        base_dir / GOALS_FILE,
        _to_yaml([g.model_dump(mode="json") for g in goals]),
    )
    return goals
