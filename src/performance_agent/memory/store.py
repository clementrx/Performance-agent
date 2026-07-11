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
ANALYSIS_DIR = "analysis"
RESEARCH_DIR = "research"
_FRONTMATTER_DELIMITER = "---\n"
_FRONTMATTER_DELIMITER_COUNT = 2


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


def _parse_yaml(text: str, path: Path) -> object:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"{path} contains invalid YAML: {exc}"
        raise ValueError(msg) from exc


def _load_yaml(path: Path) -> object:
    return _parse_yaml(path.read_text(encoding="utf-8"), path)


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


def _doc_path(base_dir: Path, subdir: str, prefix: str, version: int) -> Path:
    return base_dir / subdir / f"{prefix}-v{version}.md"


def _latest_doc_version(base_dir: Path, subdir: str, prefix: str) -> int | None:
    doc_dir = base_dir / subdir
    if not doc_dir.is_dir():
        return None
    marker = f"{prefix}-v"
    versions = [
        int(stem)
        for path in doc_dir.glob(f"{marker}*.md")
        if (stem := path.stem.removeprefix(marker)).isdigit() and str(int(stem)) == stem
    ]
    return max(versions) if versions else None


def _save_versioned_doc(  # noqa: PLR0913 -- shared by 3 doc families, all keyword-only past 3
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    *,
    subdir: str,
    prefix: str,
    label: str,
    reason: str | None,
    today: date | None,
) -> tuple[Path, int]:
    current = _latest_doc_version(base_dir, subdir, prefix)
    version = 1 if current is None else current + 1
    if version > 1 and not reason:
        msg = f"adapting {label} v{current} to v{version} requires a reason (audit trail)"
        raise ValueError(msg)
    frontmatter = {
        "version": version,
        "goal_id": goal_id,
        "created_on": (today or date.today()).isoformat(),
        "reason": reason,
    }
    content = "---\n" + _to_yaml(frontmatter) + "---\n\n" + markdown_body.strip() + "\n"
    path = _doc_path(base_dir, subdir, prefix, version)
    if path.exists():
        msg = f"{path} already exists; {label} versions are immutable"
        raise ValueError(msg)
    _atomic_write(path, content)
    return path, version


def _read_versioned_doc(
    base_dir: Path,
    *,
    subdir: str,
    prefix: str,
    label: str,
    version: int | None,
) -> tuple[dict[str, object], str] | None:
    target = version if version is not None else _latest_doc_version(base_dir, subdir, prefix)
    if target is None:
        return None
    path = _doc_path(base_dir, subdir, prefix, target)
    if not path.exists():
        msg = f"{label} version {target} does not exist"
        raise ValueError(msg)
    text = path.read_text(encoding="utf-8")
    if text.count(_FRONTMATTER_DELIMITER) < _FRONTMATTER_DELIMITER_COUNT:
        msg = f"{path} is missing YAML frontmatter delimited by '---' lines"
        raise ValueError(msg)
    _, frontmatter_text, body = text.split(_FRONTMATTER_DELIMITER, 2)
    raw = _parse_yaml(frontmatter_text, path)
    if not isinstance(raw, dict):
        msg = f"{path} frontmatter must be a YAML mapping"
        raise ValueError(msg)
    frontmatter: dict[str, object] = {str(key): value for key, value in raw.items()}
    if frontmatter.get("version") != target:
        msg = (
            f"{path} frontmatter declares version {frontmatter.get('version')} "
            f"but the filename says {target}"
        )
        raise ValueError(msg)
    return frontmatter, body.strip()


def latest_program_version(base_dir: Path) -> int | None:
    """Return the highest existing program version, or None."""
    return _latest_doc_version(base_dir, PROGRAMS_DIR, "program")


def latest_analysis_version(base_dir: Path) -> int | None:
    """Return the highest existing needs-analysis version, or None."""
    return _latest_doc_version(base_dir, ANALYSIS_DIR, "needs-analysis")


def latest_research_dossier_version(base_dir: Path) -> int | None:
    """Return the highest existing research-dossier version, or None."""
    return _latest_doc_version(base_dir, RESEARCH_DIR, "dossier")


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
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=PROGRAMS_DIR,
        prefix="program",
        label="program",
        reason=reason,
        today=today,
    )


def read_program(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest version; None when empty."""
    return _read_versioned_doc(
        base_dir, subdir=PROGRAMS_DIR, prefix="program", label="program", version=version
    )


def save_analysis(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next needs-analysis version; revising an existing one requires a reason.

    Same immutable-version audit trail as programs; lives in analysis/.
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=ANALYSIS_DIR,
        prefix="needs-analysis",
        label="needs analysis",
        reason=reason,
        today=today,
    )


def read_analysis(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest needs analysis; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=ANALYSIS_DIR,
        prefix="needs-analysis",
        label="needs analysis",
        version=version,
    )


def save_research_dossier(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next research-dossier version; re-research requires a reason.

    Same immutable-version audit trail as programs; lives in research/.
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=RESEARCH_DIR,
        prefix="dossier",
        label="research dossier",
        reason=reason,
        today=today,
    )


def read_research_dossier(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest dossier; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=RESEARCH_DIR,
        prefix="dossier",
        label="research dossier",
        version=version,
    )
