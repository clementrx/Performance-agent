# Plan 03 — Athlete Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** File-based long-term athlete memory — schema-validated profile/goals, append-only
session and check-in logs, immutable versioned programs with an adaptation audit trail,
and a time-context tool — exposed as 8 MCP memory tools.

**Architecture:** Per spec v2 §4: a transparent athlete data directory
(`PERFORMANCE_AGENT_HOME` → `./athlete/` if present → `~/.performance-agent/`) of plain
YAML/JSONL/markdown the user can read, diff, and sync. A `memory/` package owns schemas
(Pydantic) and storage (atomic writes, never deletes history); `server/memory_tools.py`
wraps it as MCP tools. The clock is injectable (`today: date | None`) so every date
computation is deterministic under test.

**Tech Stack:** pydantic (exact-pinned), pyyaml (exact-pinned), stdlib json/pathlib.
mcp==1.28.1 FastMCP conventions from Plan 02 (camelCase result attrs, in-process
ClientSession fixture, TypedDict returns, engine enums in signatures).

---

## MVP Plan Sequence (spec v2 §10)

1. ✅ Foundation & sports science engine
2. ✅ MCP server core
3. **Athlete memory** ← this plan
4. Evidence corpus (seed manifest, SQLite FTS5, citation check)
5. Coaching skills + eval harness
6. Typst reports
7. Distribution (PyPI, corpus releases)

---

## File Structure (this plan)

```
src/performance_agent/
├── memory/
│   ├── __init__.py            # docstring only (public API = the modules)
│   ├── paths.py               # athlete-dir resolution (env → ./athlete → ~/.performance-agent)
│   ├── schemas.py             # Pydantic models: Profile, Injury, Availability, Goal,
│   │                          #   SessionEntry, CheckinEntry
│   ├── store.py               # atomic YAML/JSONL/program-version I/O
│   └── time_context.py        # date-delta computation (TimeContext TypedDict)
└── server/
    ├── memory_tools.py        # 8 MCP tools + register(mcp)
    └── app.py                 # + memory_tools.register(mcp)

tests/
├── memory/
│   ├── __init__.py
│   ├── test_paths.py
│   ├── test_schemas.py
│   ├── test_store_profile_goals.py
│   ├── test_store_logs.py
│   ├── test_store_programs.py
│   └── test_time_context.py
└── server/test_memory_tools.py
```

Athlete directory layout produced (spec v2 §4):

```
athlete/
├── profile.yaml        # schema-validated structured facts
├── goals.yaml          # list of goals
├── programs/
│   └── program-v1.md   # YAML frontmatter (version, goal_id, created_on, reason) + body
├── sessions.jsonl      # append-only, one SessionEntry per line
└── checkins.jsonl      # append-only, one CheckinEntry per line
```

All test suite counts below are per-file; after each task run the FULL suite too and
report the total (baseline entering this plan: 116 passed).

---

### Task 1: Dependencies + athlete-dir resolution

**Files:**
- Modify: `pyproject.toml` (+ pydantic, pyyaml)
- Create: `src/performance_agent/memory/__init__.py`, `src/performance_agent/memory/paths.py`
- Test: `tests/memory/__init__.py` (empty), `tests/memory/test_paths.py`

- [ ] **Step 1: Add dependencies (exact pins, current versions)**

```bash
uv add --bounds exact pydantic pyyaml
```
(pydantic is already a transitive dep of mcp — pinning it as a direct dependency is
correct since memory/ imports it directly. If `uv add` leaves a non-`==` specifier,
hand-edit to the resolved version and `uv lock`.)

- [ ] **Step 2: Write the failing tests** — `tests/memory/test_paths.py`:

```python
from pathlib import Path

from performance_agent.memory.paths import resolve_athlete_dir


def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path / "custom"))
    assert resolve_athlete_dir() == tmp_path / "custom"


def test_project_local_athlete_dir_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    (tmp_path / "athlete").mkdir()
    monkeypatch.chdir(tmp_path)
    assert resolve_athlete_dir() == tmp_path / "athlete"


def test_falls_back_to_home_dotdir(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(tmp_path)  # no ./athlete here
    assert resolve_athlete_dir() == Path.home() / ".performance-agent"


def test_env_var_expands_user(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", "~/somewhere")
    assert resolve_athlete_dir() == Path.home() / "somewhere"
```

- [ ] **Step 3: Run to verify red** — `rtk proxy uv run pytest tests/memory -v` →
ModuleNotFoundError for `performance_agent.memory`.

- [ ] **Step 4: Implement**

`src/performance_agent/memory/__init__.py`:
```python
"""File-based long-term athlete memory (plain YAML/JSONL/markdown, user-owned)."""
```

`src/performance_agent/memory/paths.py`:
```python
"""Athlete data directory resolution.

Precedence: PERFORMANCE_AGENT_HOME env var, then ./athlete/ when it exists
(project-local coaching folder), then ~/.performance-agent/.
"""

import os
from pathlib import Path

ENV_VAR = "PERFORMANCE_AGENT_HOME"
PROJECT_DIR_NAME = "athlete"


def resolve_athlete_dir() -> Path:
    """Return the athlete data directory (never creates it)."""
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    project_dir = Path.cwd() / PROJECT_DIR_NAME
    if project_dir.is_dir():
        return project_dir
    return Path.home() / ".performance-agent"
```

- [ ] **Step 5: Green + full gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 4 passed
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest                      # full suite green; report total
git add pyproject.toml uv.lock src/performance_agent/memory tests/memory
git commit -m "Add memory package with athlete-dir resolution"
```

---

### Task 2: Schemas

**Files:**
- Create: `src/performance_agent/memory/schemas.py`
- Test: `tests/memory/test_schemas.py`

- [ ] **Step 1: Write the failing tests** — `tests/memory/test_schemas.py`:

```python
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from performance_agent.engine import TrainingAge
from performance_agent.memory.schemas import (
    CheckinEntry,
    Goal,
    Injury,
    Profile,
    SessionEntry,
)


def test_default_profile_is_valid_and_english():
    profile = Profile()
    assert profile.locale == "en"
    assert profile.injuries == []
    assert profile.equipment == []


def test_profile_accepts_structured_facts():
    profile = Profile(
        locale="fr",
        display_name="Clément",
        birth_date=date(1990, 5, 1),
        sex="male",
        height_cm=180,
        weight_kg=75,
        training_age=TrainingAge.INTERMEDIATE,
        sport="running",
        injuries=[Injury(area="left knee", noted_on=date(2026, 6, 1))],
        equipment=["barbell", "rack"],
        notes=["prefers morning sessions"],
    )
    assert profile.training_age is TrainingAge.INTERMEDIATE
    assert profile.injuries[0].status == "active"


@pytest.mark.parametrize(
    ("field", "value"),
    [("locale", "de"), ("height_cm", 30), ("weight_kg", 500), ("sex", "other")],
)
def test_profile_rejects_out_of_contract_values(field, value):
    with pytest.raises(ValidationError):
        Profile(**{field: value})


def test_profile_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Profile(favourite_color="blue")


def test_goal_defaults_and_id_pattern():
    goal = Goal(id="sub-45-10k", statement="10K under 45:00")
    assert goal.priority == "A"
    assert goal.status == "active"
    with pytest.raises(ValidationError):
        Goal(id="Bad Id!", statement="x")


def test_session_entry_bounds():
    entry = SessionEntry(performed_at=datetime(2026, 7, 10, 18, 0), rpe=7, duration_min=60)
    assert entry.rpe == 7
    with pytest.raises(ValidationError):
        SessionEntry(performed_at=datetime(2026, 7, 10), rpe=11)


def test_checkin_entry_bounds():
    entry = CheckinEntry(at=datetime(2026, 7, 10, 9, 0), adherence_pct=80, fatigue=4)
    assert entry.pain_flags == []
    with pytest.raises(ValidationError):
        CheckinEntry(at=datetime(2026, 7, 10), adherence_pct=140)
```

- [ ] **Step 2: Run to verify red** — ModuleNotFoundError for schemas.

- [ ] **Step 3: Implement** — `src/performance_agent/memory/schemas.py`:

```python
"""Pydantic schemas for the athlete data directory.

Structured facts live here with a strict contract (extra="forbid", bounded
values); free-text preferences go in Profile.notes. The schema is what makes
profile.yaml trustworthy for both humans and agents.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from performance_agent.engine import TrainingAge

Locale = Literal["en", "fr", "es"]


class Injury(BaseModel):
    """An injury record; the coach adapts around active injuries, never through them."""

    model_config = ConfigDict(extra="forbid")

    area: str
    description: str = ""
    status: Literal["active", "recovered"] = "active"
    noted_on: date


class Availability(BaseModel):
    """Weekly training availability."""

    model_config = ConfigDict(extra="forbid")

    sessions_per_week: int = Field(ge=1, le=14)
    minutes_per_session: int = Field(ge=10, le=480)


class Profile(BaseModel):
    """Athlete profile — structured facts only."""

    model_config = ConfigDict(extra="forbid")

    locale: Locale = "en"
    display_name: str | None = None
    birth_date: date | None = None
    sex: Literal["male", "female"] | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=250)
    training_age: TrainingAge | None = None
    sport: str | None = None
    discipline: str | None = None
    injuries: list[Injury] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    availability: Availability | None = None
    notes: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    """A training goal with deadline and status."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    statement: str
    metric: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    deadline: date | None = None
    priority: Literal["A", "B", "C"] = "A"
    status: Literal["active", "achieved", "abandoned"] = "active"


class SessionEntry(BaseModel):
    """One completed training session (raw facts; loads are computed by engine tools)."""

    model_config = ConfigDict(extra="forbid")

    performed_at: datetime
    kind: str | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)
    duration_min: int | None = Field(default=None, ge=1)
    notes: str | None = None


class CheckinEntry(BaseModel):
    """One coaching check-in record."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    days_since_last: int | None = None
    adherence_pct: float | None = Field(default=None, ge=0, le=100)
    fatigue: int | None = Field(default=None, ge=1, le=10)
    pain_flags: list[str] = Field(default_factory=list)
    notes: str | None = None
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 11 passed (4 + 7)
uv run ruff check . && uv run ruff format --check . && uv run ty check
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas.py
git commit -m "Add athlete memory schemas"
```

---

### Task 3: Store — profile and goals (atomic YAML)

**Files:**
- Create: `src/performance_agent/memory/store.py`
- Test: `tests/memory/test_store_profile_goals.py`

- [ ] **Step 1: Write the failing tests**:

```python
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
```

- [ ] **Step 2: Run to verify red** — ModuleNotFoundError for store.

- [ ] **Step 3: Implement** — `src/performance_agent/memory/store.py`:

```python
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
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 17 passed (11 + 6)
uv run ruff check . && uv run ruff format --check . && uv run ty check
git add src/performance_agent/memory/store.py tests/memory/test_store_profile_goals.py
git commit -m "Add atomic profile and goal storage"
```

---

### Task 4: Store — session and check-in logs (append-only JSONL)

**Files:**
- Modify: `src/performance_agent/memory/store.py`
- Test: `tests/memory/test_store_logs.py`

- [ ] **Step 1: Write the failing tests**:

```python
from datetime import datetime

from performance_agent.memory.schemas import CheckinEntry, SessionEntry
from performance_agent.memory.store import (
    append_checkin,
    append_session,
    read_checkins,
    read_sessions,
)


def test_sessions_append_and_read_in_order(tmp_path):
    first = SessionEntry(performed_at=datetime(2026, 7, 1, 18, 0), rpe=7, duration_min=60)
    second = SessionEntry(performed_at=datetime(2026, 7, 3, 18, 0), rpe=5, duration_min=45)
    append_session(tmp_path, first)
    append_session(tmp_path, second)
    sessions = read_sessions(tmp_path)
    assert sessions == [first, second]


def test_sessions_file_is_one_json_per_line(tmp_path):
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 7, 1, 18, 0)))
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 7, 2, 18, 0)))
    lines = (tmp_path / "sessions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("{")


def test_read_sessions_empty_when_missing(tmp_path):
    assert read_sessions(tmp_path) == []


def test_first_checkin_has_no_days_since_last(tmp_path):
    stored = append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0)))
    assert stored.days_since_last is None


def test_checkin_days_since_last_is_auto_filled(tmp_path):
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    stored = append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0)))
    assert stored.days_since_last == 14
    assert read_checkins(tmp_path)[-1].days_since_last == 14


def test_explicit_days_since_last_is_respected(tmp_path):
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    stored = append_checkin(
        tmp_path, CheckinEntry(at=datetime(2026, 7, 10, 9, 0), days_since_last=99)
    )
    assert stored.days_since_last == 99
```

- [ ] **Step 2: Run to verify red** — ImportError (append_session etc. missing).

- [ ] **Step 3: Implement** — extend `store.py` (imports: add
`from performance_agent.memory.schemas import CheckinEntry, Goal, Profile, SessionEntry`;
constants: add `SESSIONS_FILE = "sessions.jsonl"` and `CHECKINS_FILE = "checkins.jsonl"`):

```python
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
    return [SessionEntry.model_validate_json(line) for line in lines if line.strip()]


def append_checkin(base_dir: Path, entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; fills days_since_last from the previous one when unset."""
    previous = read_checkins(base_dir)
    if entry.days_since_last is None and previous:
        entry = entry.model_copy(
            update={"days_since_last": (entry.at - previous[-1].at).days}
        )
    _append_jsonl(base_dir / CHECKINS_FILE, entry.model_dump_json())
    return entry


def read_checkins(base_dir: Path) -> list[CheckinEntry]:
    """Return all logged check-ins in insertion order."""
    path = base_dir / CHECKINS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [CheckinEntry.model_validate_json(line) for line in lines if line.strip()]
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 23 passed (17 + 6)
uv run ruff check . && uv run ruff format --check . && uv run ty check
git add src/performance_agent/memory/store.py tests/memory/test_store_logs.py
git commit -m "Add append-only session and check-in logs"
```

---

### Task 5: Store — immutable versioned programs

**Files:**
- Modify: `src/performance_agent/memory/store.py`
- Test: `tests/memory/test_store_programs.py`

- [ ] **Step 1: Write the failing tests**:

```python
from datetime import date

import pytest

from performance_agent.memory.store import (
    latest_program_version,
    read_program,
    save_program,
)

TODAY = date(2026, 7, 10)


def test_no_programs_yet(tmp_path):
    assert latest_program_version(tmp_path) is None
    assert read_program(tmp_path) is None


def test_first_program_is_v1_and_needs_no_reason(tmp_path):
    path, version = save_program(tmp_path, "# Week 1\nRun easy.", "sub-45-10k", today=TODAY)
    assert version == 1
    assert path == tmp_path / "programs" / "program-v1.md"
    frontmatter, body = read_program(tmp_path)
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
    frontmatter, _ = read_program(tmp_path)
    assert frontmatter["reason"] == "missed week 3 with a cold"


def test_old_versions_stay_readable(tmp_path):
    save_program(tmp_path, "first body", "sub-45-10k", today=TODAY)
    save_program(tmp_path, "second body", "sub-45-10k", reason="plateau", today=TODAY)
    frontmatter, body = read_program(tmp_path, version=1)
    assert frontmatter["version"] == 1
    assert body == "first body"


def test_reading_a_missing_version_is_an_error(tmp_path):
    save_program(tmp_path, "v1", "sub-45-10k", today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read_program(tmp_path, version=7)


def test_program_body_may_contain_frontmatter_delimiters(tmp_path):
    body = "intro\n---\ntable section\n---\noutro"
    save_program(tmp_path, body, "sub-45-10k", today=TODAY)
    _, read_body = read_program(tmp_path)
    assert read_body == body
```

- [ ] **Step 2: Run to verify red** — ImportError.

- [ ] **Step 3: Implement** — extend `store.py` (imports: add `from datetime import date`;
constants: add `PROGRAMS_DIR = "programs"`):

```python
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
```

(Note the split: `text.split("---\n", 2)` splits at most twice, so `---` lines inside
the body survive — pinned by `test_program_body_may_contain_frontmatter_delimiters`.)

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 30 passed (23 + 7)
uv run ruff check . && uv run ruff format --check . && uv run ty check
git add src/performance_agent/memory/store.py tests/memory/test_store_programs.py
git commit -m "Add immutable versioned program storage with audit trail"
```

---

### Task 6: Time context

**Files:**
- Create: `src/performance_agent/memory/time_context.py`
- Test: `tests/memory/test_time_context.py`

- [ ] **Step 1: Write the failing tests**:

```python
from datetime import date, datetime

from performance_agent.memory.schemas import CheckinEntry, Goal, SessionEntry
from performance_agent.memory.store import append_checkin, append_session, upsert_goal
from performance_agent.memory.time_context import build_time_context

TODAY = date(2026, 7, 10)


def test_empty_directory_yields_null_deltas(tmp_path):
    context = build_time_context(tmp_path, today=TODAY)
    assert context["today"] == "2026-07-10"
    assert context["days_since_last_session"] is None
    assert context["days_since_last_checkin"] is None
    assert context["goals"] == []


def test_deltas_come_from_the_most_recent_entries(tmp_path):
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 6, 20, 18, 0)))
    append_session(tmp_path, SessionEntry(performed_at=datetime(2026, 6, 26, 18, 0)))
    append_checkin(tmp_path, CheckinEntry(at=datetime(2026, 6, 26, 9, 0)))
    context = build_time_context(tmp_path, today=TODAY)
    assert context["last_session_on"] == "2026-06-26"
    assert context["days_since_last_session"] == 14
    assert context["days_since_last_checkin"] == 14


def test_goal_countdowns_only_for_active_goals(tmp_path):
    upsert_goal(
        tmp_path,
        Goal(id="sub-45-10k", statement="10K under 45:00", deadline=date(2026, 10, 30)),
    )
    upsert_goal(
        tmp_path,
        Goal(id="done", statement="done", deadline=date(2026, 8, 1), status="achieved"),
    )
    context = build_time_context(tmp_path, today=TODAY)
    assert len(context["goals"]) == 1
    view = context["goals"][0]
    assert view["goal_id"] == "sub-45-10k"
    assert view["days_remaining"] == 112
    assert view["weeks_remaining"] == 16.0


def test_goal_without_deadline_has_null_countdown(tmp_path):
    upsert_goal(tmp_path, Goal(id="open-goal", statement="get stronger"))
    view = build_time_context(tmp_path, today=TODAY)["goals"][0]
    assert view["deadline"] is None
    assert view["days_remaining"] is None
    assert view["weeks_remaining"] is None


def test_overdue_goal_has_negative_days(tmp_path):
    upsert_goal(
        tmp_path, Goal(id="past", statement="past race", deadline=date(2026, 7, 1))
    )
    view = build_time_context(tmp_path, today=TODAY)["goals"][0]
    assert view["days_remaining"] == -9
```

- [ ] **Step 2: Run to verify red** — ModuleNotFoundError.

- [ ] **Step 3: Implement** — `src/performance_agent/memory/time_context.py`:

```python
"""Temporal awareness: date deltas the coach quotes instead of trusting its clock."""

from datetime import date
from pathlib import Path
from typing import TypedDict

from performance_agent.memory import store


class GoalTimeView(TypedDict):
    """Countdown view of one active goal."""

    goal_id: str
    statement: str
    deadline: str | None
    days_remaining: int | None
    weeks_remaining: float | None


class TimeContext(TypedDict):
    """Everything date-related the coach needs at conversation start."""

    today: str
    last_session_on: str | None
    days_since_last_session: int | None
    last_checkin_on: str | None
    days_since_last_checkin: int | None
    goals: list[GoalTimeView]


def _goal_view(goal_id: str, statement: str, deadline: date | None, current: date) -> GoalTimeView:
    days = (deadline - current).days if deadline else None
    return GoalTimeView(
        goal_id=goal_id,
        statement=statement,
        deadline=deadline.isoformat() if deadline else None,
        days_remaining=days,
        weeks_remaining=round(days / 7, 1) if days is not None else None,
    )


def build_time_context(base_dir: Path, today: date | None = None) -> TimeContext:
    """Compute all date deltas from stored facts (deterministic via `today`)."""
    current = today or date.today()
    last_session = max(
        (s.performed_at.date() for s in store.read_sessions(base_dir)), default=None
    )
    last_checkin = max((c.at.date() for c in store.read_checkins(base_dir)), default=None)
    goals = [
        _goal_view(goal.id, goal.statement, goal.deadline, current)
        for goal in store.read_goals(base_dir)
        if goal.status == "active"
    ]
    return TimeContext(
        today=current.isoformat(),
        last_session_on=last_session.isoformat() if last_session else None,
        days_since_last_session=(current - last_session).days if last_session else None,
        last_checkin_on=last_checkin.isoformat() if last_checkin else None,
        days_since_last_checkin=(current - last_checkin).days if last_checkin else None,
        goals=goals,
    )
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/memory -v      # 35 passed (30 + 5)
uv run ruff check . && uv run ruff format --check . && uv run ty check
git add src/performance_agent/memory/time_context.py tests/memory/test_time_context.py
git commit -m "Add deterministic time context"
```

---

### Task 7: Memory MCP tools

**Files:**
- Create: `src/performance_agent/server/memory_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_memory_tools.py`

- [ ] **Step 1: Write the failing tests** — `tests/server/test_memory_tools.py`:

```python
"""In-process tests for the memory MCP tools (isolated athlete dir per test)."""

import pytest


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.anyio
async def test_read_athlete_on_fresh_directory(client):
    result = await client.call_tool("read_athlete", {})
    assert not result.isError
    snapshot = result.structuredContent
    assert snapshot["profile"]["locale"] == "en"
    assert snapshot["goals"] == []
    assert snapshot["program_version"] is None


@pytest.mark.anyio
async def test_write_profile_then_read_back(client, athlete_home):
    result = await client.call_tool(
        "write_profile",
        {"profile": {"locale": "fr", "sport": "running", "training_age": "intermediate"}},
    )
    assert not result.isError
    assert (athlete_home / "profile.yaml").exists()

    back = await client.call_tool("read_athlete", {})
    assert back.structuredContent["profile"]["locale"] == "fr"
    assert back.structuredContent["profile"]["training_age"] == "intermediate"


@pytest.mark.anyio
async def test_invalid_profile_is_rejected_readably(client):
    result = await client.call_tool("write_profile", {"profile": {"locale": "de"}})
    assert result.isError
    text = result.content[0].text
    assert "en" in text and "fr" in text and "es" in text


@pytest.mark.anyio
async def test_goal_lifecycle(client):
    added = await client.call_tool(
        "upsert_goal",
        {"goal": {"id": "sub-45-10k", "statement": "10K under 45:00", "deadline": "2026-10-30"}},
    )
    assert not added.isError
    assert added.structuredContent["total_goals"] == 1

    snapshot = await client.call_tool("read_athlete", {})
    assert snapshot.structuredContent["goals"][0]["id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_log_session_and_checkin(client):
    logged = await client.call_tool(
        "log_session",
        {"entry": {"performed_at": "2026-07-08T18:00:00", "rpe": 7, "duration_min": 60}},
    )
    assert not logged.isError
    assert logged.structuredContent["total_sessions"] == 1

    first = await client.call_tool("log_checkin", {"entry": {"at": "2026-06-26T09:00:00"}})
    assert not first.isError
    second = await client.call_tool("log_checkin", {"entry": {"at": "2026-07-10T09:00:00"}})
    assert second.structuredContent["days_since_last"] == 14


@pytest.mark.anyio
async def test_program_versioning_through_tools(client):
    v1 = await client.call_tool(
        "save_program", {"markdown_body": "# Plan\nWeek 1", "goal_id": "sub-45-10k"}
    )
    assert not v1.isError
    assert v1.structuredContent["version"] == 1

    rejected = await client.call_tool(
        "save_program", {"markdown_body": "# Plan v2", "goal_id": "sub-45-10k"}
    )
    assert rejected.isError
    assert "reason" in rejected.content[0].text

    v2 = await client.call_tool(
        "save_program",
        {"markdown_body": "# Plan v2", "goal_id": "sub-45-10k", "reason": "plateau at week 4"},
    )
    assert v2.structuredContent["version"] == 2

    latest = await client.call_tool("read_program", {})
    assert latest.structuredContent["version"] == 2
    assert latest.structuredContent["reason"] == "plateau at week 4"
    first_version = await client.call_tool("read_program", {"version": 1})
    assert first_version.structuredContent["body"] == "# Plan\nWeek 1"


@pytest.mark.anyio
async def test_get_time_context_quotes_deltas(client):
    await client.call_tool(
        "log_session", {"entry": {"performed_at": "2026-07-01T18:00:00"}}
    )
    await client.call_tool(
        "upsert_goal",
        {"goal": {"id": "sub-45-10k", "statement": "10K under 45:00", "deadline": "2026-10-30"}},
    )
    result = await client.call_tool("get_time_context", {})
    assert not result.isError
    context = result.structuredContent
    assert context["last_session_on"] == "2026-07-01"
    assert isinstance(context["days_since_last_session"], int)
    assert context["goals"][0]["goal_id"] == "sub-45-10k"


@pytest.mark.anyio
async def test_memory_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {
        "read_athlete",
        "write_profile",
        "upsert_goal",
        "log_session",
        "log_checkin",
        "save_program",
        "read_program",
        "get_time_context",
    } <= names
```

- [ ] **Step 2: Run to verify red** — unknown tools.

- [ ] **Step 3: Implement** — `src/performance_agent/server/memory_tools.py`:

```python
"""MCP tools for the athlete data directory (file-based long-term memory).

These tools own every stored fact. The coach reads the athlete at conversation
start, quotes get_time_context instead of computing dates, and records every
decision through the versioned program store.
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import CheckinEntry, Goal, Profile, SessionEntry
from performance_agent.memory.time_context import TimeContext, build_time_context


class AthleteSnapshot(TypedDict):
    """Everything stored about the athlete, in one read."""

    athlete_dir: str
    profile: Profile
    goals: list[Goal]
    program_version: int | None


class WrittenFile(TypedDict):
    """Path of a file the tool just wrote."""

    path: str


class GoalCount(TypedDict):
    """Number of stored goals after the operation."""

    total_goals: int


class SessionCount(TypedDict):
    """Number of logged sessions after the operation."""

    total_sessions: int


class ProgramSaved(TypedDict):
    """Result of writing a new program version."""

    path: str
    version: int


class ProgramView(TypedDict):
    """A stored program version with its audit metadata."""

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    body: str


def read_athlete() -> AthleteSnapshot:
    """Return the athlete snapshot: profile, goals, latest program version.

    Call this at the start of every coaching conversation — no conversation
    starts from zero.
    """
    base = resolve_athlete_dir()
    return AthleteSnapshot(
        athlete_dir=str(base),
        profile=store.read_profile(base),
        goals=store.read_goals(base),
        program_version=store.latest_program_version(base),
    )


def write_profile(profile: Profile) -> WrittenFile:
    """Replace the athlete profile.

    Read the athlete first, then write the FULL updated profile — this is a
    whole-document replace, not a merge.
    """
    return WrittenFile(path=str(store.write_profile(resolve_athlete_dir(), profile)))


def upsert_goal(goal: Goal) -> GoalCount:
    """Add a goal, or replace the goal that has the same id."""
    return GoalCount(total_goals=len(store.upsert_goal(resolve_athlete_dir(), goal)))


def log_session(entry: SessionEntry) -> SessionCount:
    """Append one completed training session to the athlete's history."""
    base = resolve_athlete_dir()
    store.append_session(base, entry)
    return SessionCount(total_sessions=len(store.read_sessions(base)))


def log_checkin(entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; days_since_last is auto-filled from the previous one."""
    return store.append_checkin(resolve_athlete_dir(), entry)


def save_program(markdown_body: str, goal_id: str, reason: str | None = None) -> ProgramSaved:
    """Write the NEXT program version (immutable audit trail).

    Version 1 needs no reason; every adaptation (v2+) requires a reason stating
    the coaching decision. Existing versions are never overwritten.
    """
    path, version = store.save_program(resolve_athlete_dir(), markdown_body, goal_id, reason)
    return ProgramSaved(path=str(path), version=version)


def read_program(version: int | None = None) -> ProgramView | None:
    """Return the latest (or a specific) program version, or null when none exists."""
    result = store.read_program(resolve_athlete_dir(), version)
    if result is None:
        return None
    frontmatter, body = result
    return ProgramView(
        version=int(frontmatter["version"]),  # type: ignore[call-overload]
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=frontmatter.get("reason"),  # type: ignore[typeddict-item]
        body=body,
    )


def get_time_context() -> TimeContext:
    """Current date plus days-since deltas and goal countdowns.

    Call this at conversation start and quote its numbers — never compute
    dates yourself.
    """
    return build_time_context(resolve_athlete_dir())


def register(mcp: FastMCP) -> None:
    """Register every memory tool on the server."""
    for tool in (
        read_athlete,
        write_profile,
        upsert_goal,
        log_session,
        log_checkin,
        save_program,
        read_program,
        get_time_context,
    ):
        mcp.tool()(tool)
```

(If ty accepts the frontmatter accesses without the two `# ty: ignore`-style comments
shown, drop them; if it complains differently, use the narrowest suppression it
supports and report. If FastMCP rejects Pydantic-model params (`profile: Profile`)
or the `TimeContext` TypedDict return — the tests will tell you — report BLOCKED
with the exact error; do not switch to untyped dicts silently.)

Modify `src/performance_agent/server/app.py` to:

```python
"""MCP server assembly and stdio entrypoint."""

from mcp.server.fastmcp import FastMCP

from performance_agent.server import engine_tools, memory_tools

mcp = FastMCP("performance-agent")
engine_tools.register(mcp)
memory_tools.register(mcp)


def main() -> None:
    """Run the performance-agent MCP server over stdio."""
    mcp.run()
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/server -v      # all server tests green (23 prior + 8 new)
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest                      # full suite; report total
git add src/performance_agent/server tests/server/test_memory_tools.py
git commit -m "Add athlete memory MCP tools"
```

---

### Task 8: Final sweep

- [ ] **Step 1: Full quality gate**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
prek run --all-files
actionlint .github/workflows/ci.yml && uvx zizmor .github/workflows/ci.yml
```

- [ ] **Step 2: Update `README.md`** — move the memory line from "MVP in progress" to
"Working today". Replace:
```
- 🔜 File-based athlete memory with time awareness ("your last update was 14 days ago")
  and versioned programs with a full adaptation audit trail
```
with (under Working today, after the MCP server line):
```
- ✅ File-based athlete memory: schema-validated profile & goals, append-only session
  and check-in logs, versioned programs with a required-reason adaptation audit trail,
  and time awareness ("your last update was 14 days ago")
```
Also update the 🔜 tools line "Evidence, memory, and report MCP tools" → "Evidence and
report MCP tools". Check exact current wording first; adjust minimally.

- [ ] **Step 3: Update `docs/installing.md`** — the Verify section: "You should see 9
engine tools" → "You should see 17 tools (9 engine + 8 memory: assess_endurance_goal,
read_athlete, get_time_context, …)". Check exact wording first.

- [ ] **Step 4: Record as-built deviations** — add `## As-Built Deviations` to this
plan file (SDK adaptations, ty suppressions actually needed, any test-count drift),
verified against code/git log.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/installing.md docs/superpowers/plans/2026-07-10-plan-03-athlete-memory.md
git commit -m "Record Plan 03 as-built state and update docs"
```

---

## Self-Review Notes

- **Spec coverage (v2 §4 + §10 item 3):** directory resolution (env → ./athlete →
  ~/.performance-agent) ✓ T1; structured schemas with strict contract ✓ T2; atomic
  writes, YAML round-trip ✓ T3; append-only logs + days_since_last auto-fill ✓ T4;
  immutable versioned programs with required reason ✓ T5; get_time_context deltas
  (today, last session/check-in, weeks-to-deadline) ✓ T6; the spec's 6 memory tools
  are delivered as 8 (update_profile split into write_profile+upsert_goal for schema
  clarity; read_program added so agents can retrieve past versions) ✓ T7.
- **Deliberate scope cuts:** reports/ dir handling (Plan 06); semantic memory_facts
  embeddings (spec marks free-text as Profile.notes for MVP); no file locking (single
  local user; atomic replace covers crash safety).
- **Type consistency check:** Profile/Goal/SessionEntry/CheckinEntry names and fields
  identical across T2 schemas, T3-T5 store signatures, T6 time_context, and T7 tools;
  TimeContext keys in T6 match T7's test assertions; store function names
  (read_profile/write_profile/read_goals/upsert_goal/append_session/read_sessions/
  append_checkin/read_checkins/latest_program_version/save_program/read_program)
  consistent everywhere.
- **Known uncertainties, handled in-plan:** FastMCP acceptance of Pydantic-model
  params and TypedDict-with-model fields (BLOCKED instruction if not); exact ty
  behavior on frontmatter dict access (narrowest-suppression instruction).

## As-Built Deviations

1. Athlete-dir deployment guard added after T1 review: `.gitignore` athlete/ entry
   + installing.md "Where your data lives" section with --env examples (commit
   7fce3fb).
2. T2: naive-local-wall-clock timestamp policy enforced by shared _require_naive
   validator; Goal.id max_length=64 (commit 9691f1f); one
   `# ty: ignore[unknown-argument]` on the intentional unknown-field test.
3. T3/T4: uniform file-naming error wrapping — _load_yaml/_parse_yaml for YAML
   errors, PEP 695 `_validated[T]` helper for pydantic ValidationErrors across all
   four readers; isinstance list guard on goals.yaml; _atomic_write tmp cleanup;
   negative days_since_last documented as intentional (commits 04e2332, fa13577).
4. T5: canonical-filename filter (program-v02.md strays ignored); frontmatter
   split guard + version cross-check + mapping guard, all naming the file (commit
   fccf9d3).
5. T7: read_program returns ProgramView and raises on empty store (FastMCP wraps
   Optional returns in {"result":...}); read_sessions/read_checkins history tools
   added post-review (plan had a write-only log oversight) → 10 memory tools, not
   8; last_n ge=1 (commits bd90263, 32033a3, eeedbb6 + this one).
6. Test-count drift: plan estimates vs actuals (final: 179).
