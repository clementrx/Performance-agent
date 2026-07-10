"""Read/write operations for the athlete data directory.

All writes are atomic (temp file + os.replace) and schema-validated. The store
never deletes history: logs are append-only and program versions are immutable.
"""

import os
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import ValidationError

from performance_agent.memory.schemas import CheckinEntry, Goal, Profile, SessionEntry

PROFILE_FILE = "profile.yaml"
GOALS_FILE = "goals.yaml"
SESSIONS_FILE = "sessions.jsonl"
CHECKINS_FILE = "checkins.jsonl"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _to_yaml(data: object) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"{path} contains invalid YAML: {exc}"
        raise ValueError(msg) from exc


def _validated[T](path: Path, parse: Callable[[], T]) -> T:
    try:
        return parse()
    except ValidationError as exc:
        msg = f"{path} contains data that violates the schema: {exc}"
        raise ValueError(msg) from exc


def read_profile(base_dir: Path) -> Profile:
    """Return the stored profile, or a default Profile when none exists."""
    path = base_dir / PROFILE_FILE
    if not path.exists():
        return Profile()
    return _validated(path, lambda: Profile.model_validate(_load_yaml(path) or {}))


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
    raw = _load_yaml(path) or []
    if not isinstance(raw, list):
        msg = f"{path} must contain a YAML list of goals (each item starting with '- ')"
        raise ValueError(msg)
    return _validated(path, lambda: [Goal.model_validate(item) for item in raw])


def upsert_goal(base_dir: Path, goal: Goal) -> list[Goal]:
    """Add a goal or replace the one with the same id; returns the updated list."""
    goals = [g for g in read_goals(base_dir) if g.id != goal.id]
    goals.append(goal)
    _atomic_write(
        base_dir / GOALS_FILE,
        _to_yaml([g.model_dump(mode="json") for g in goals]),
    )
    return goals


def _append_jsonl(path: Path, json_line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json_line + "\n")


def append_session(base_dir: Path, entry: SessionEntry) -> None:
    """Append one completed session to the append-only log."""
    _append_jsonl(base_dir / SESSIONS_FILE, entry.model_dump_json())


def read_sessions(base_dir: Path) -> list[SessionEntry]:
    """Return all logged sessions in insertion order."""
    path = base_dir / SESSIONS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [SessionEntry.model_validate_json(line) for line in lines if line.strip()],
    )


def append_checkin(base_dir: Path, entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; fills days_since_last from the previous one when unset.

    days_since_last may be negative for backdated entries.
    """
    previous = read_checkins(base_dir)
    if entry.days_since_last is None and previous:
        entry = entry.model_copy(update={"days_since_last": (entry.at - previous[-1].at).days})
    _append_jsonl(base_dir / CHECKINS_FILE, entry.model_dump_json())
    return entry


def read_checkins(base_dir: Path) -> list[CheckinEntry]:
    """Return all logged check-ins in insertion order."""
    path = base_dir / CHECKINS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return _validated(
        path,
        lambda: [CheckinEntry.model_validate_json(line) for line in lines if line.strip()],
    )
