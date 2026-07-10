"""Read/write operations for the athlete data directory.

All writes are atomic (temp file + os.replace) and schema-validated. The store
never deletes history: logs are append-only and program versions are immutable.
"""

import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from performance_agent.memory.schemas import CheckinEntry, Goal, Profile, SessionEntry

PROFILE_FILE = "profile.yaml"
GOALS_FILE = "goals.yaml"
SESSIONS_FILE = "sessions.jsonl"
CHECKINS_FILE = "checkins.jsonl"
PROGRAMS_DIR = "programs"


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


def _program_path(base_dir: Path, version: int) -> Path:
    return base_dir / PROGRAMS_DIR / f"program-v{version}.md"


def latest_program_version(base_dir: Path) -> int | None:
    """Return the highest existing program version, or None."""
    programs_dir = base_dir / PROGRAMS_DIR
    if not programs_dir.is_dir():
        return None
    versions = [
        int(stem)
        for path in programs_dir.glob("program-v*.md")
        if (stem := path.stem.removeprefix("program-v")).isdigit()
    ]
    return max(versions) if versions else None


def save_program(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next program version; adapting an existing program requires a reason.

    Versions are immutable: this never overwrites, and the required reason on
    v2+ is the coaching-decision audit trail.
    """
    current = latest_program_version(base_dir)
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting program v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    frontmatter = {
        "version": version,
        "goal_id": goal_id,
        "created_on": (today or date.today()).isoformat(),
        "reason": reason,
    }
    content = "---\n" + _to_yaml(frontmatter) + "---\n\n" + markdown_body.strip() + "\n"
    path = _program_path(base_dir, version)
    if path.exists():
        msg = f"{path} already exists; program versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, content)
    return path, version


def read_program(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest version; None when empty."""
    target = version if version is not None else latest_program_version(base_dir)
    if target is None:
        return None
    path = _program_path(base_dir, target)
    if not path.exists():
        msg = f"program version {target} does not exist"
        raise ValueError(msg)
    text = path.read_text(encoding="utf-8")
    _, frontmatter_text, body = text.split("---\n", 2)
    return yaml.safe_load(frontmatter_text), body.strip()
