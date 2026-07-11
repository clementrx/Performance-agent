# Memory Foundation (Premium Pipeline Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the athlete memory schemas so the system can represent a strength athlete — structured sessions (exercises → sets with reps/load/RIR), a multi-lift 1RM inventory, body-composition and calendar facts, and check-in bodyweight/PR tracking — without breaking any existing athlete directory.

**Architecture:** Pure additive schema extensions in `memory/schemas.py` (every new field optional with a default, `extra="forbid"` preserved), flowing through the existing store and MCP tools unchanged. No new tools; no new files. Spec: `docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md` §3 & §7-phase-1.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing FastMCP in-process test harness.

**Conventions (this repo):**
- Line length 100, `ruff check` + `ruff format` + `ty check` must stay clean.
- Commits: imperative subject, no type prefix (match `git log`), ≤72 chars.
- The spec's tree sketch says `sessions.yaml`/`checkins.yaml`; the actual store uses
  `sessions.jsonl`/`checkins.jsonl` (append-only JSONL). **Keep JSONL** — the spec
  sketch is illustrative, the append-only log is a design property (plan 03).
- Run tests with `uv run pytest`, lint with `uv run ruff check .`, types with `uv run ty check`.

---

### Task 1: Structured strength sets on SessionEntry

A session can now carry `exercises` — a list of performed exercises, each with ordered
sets of `{reps, load_kg, rir}`. Endurance sessions simply omit it; all existing fields
(`kind`, `rpe`, `duration_min`, `notes`) are unchanged.

**Files:**
- Modify: `src/performance_agent/memory/schemas.py`
- Test: `tests/memory/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/memory/test_schemas.py` (extend the existing import of schemas with
`ExercisePerformed, SetPerformed`):

```python
def test_session_entry_accepts_structured_exercises():
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 11, 18, 0),
        kind="strength",
        exercises=[
            ExercisePerformed(
                name="back squat",
                sets=[
                    SetPerformed(reps=5, load_kg=100, rir=2),
                    SetPerformed(reps=5, load_kg=100, rir=1),
                ],
            )
        ],
    )
    assert entry.exercises[0].sets[1].rir == 1


def test_session_entry_without_exercises_still_valid():
    entry = SessionEntry(performed_at=datetime(2026, 7, 11, 7, 0), kind="easy run", rpe=4)
    assert entry.exercises == []


def test_set_performed_bounds():
    with pytest.raises(ValidationError):
        SetPerformed(reps=0, load_kg=100)
    with pytest.raises(ValidationError):
        SetPerformed(reps=5, load_kg=-1)
    with pytest.raises(ValidationError):
        SetPerformed(reps=5, load_kg=100, rir=11)


def test_exercise_performed_requires_name_and_rejects_extras():
    with pytest.raises(ValidationError):
        ExercisePerformed(name="", sets=[])
    with pytest.raises(ValidationError):
        ExercisePerformed(name="bench press", sets=[], tempo="3010")  # ty: ignore[unknown-argument]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: FAIL — `ImportError: cannot import name 'ExercisePerformed'`

- [ ] **Step 3: Implement the schemas**

In `src/performance_agent/memory/schemas.py`, insert between `Availability` and
`Profile`:

```python
class SetPerformed(BaseModel):
    """One completed set. RIR = reps in reserve; None means not recorded."""

    model_config = ConfigDict(extra="forbid")

    reps: int = Field(ge=1, le=100)
    load_kg: float = Field(ge=0, le=1000)
    rir: int | None = Field(default=None, ge=0, le=10)


class ExercisePerformed(BaseModel):
    """One exercise within a session, with its sets in performed order."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    sets: list[SetPerformed] = Field(default_factory=list)
    notes: str | None = None
```

Then add the field to `SessionEntry` (after `duration_min`):

```python
    exercises: list[ExercisePerformed] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: PASS (all, including pre-existing tests)

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff format . && uv run ruff check . && uv run ty check`
Expected: clean.

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas.py
git commit -m "Add structured exercises/sets/RIR to SessionEntry"
```

---

### Task 2: Lift inventory, body composition, and calendar type on Profile

The profile gains: `lift_inventory` (per-lift 1RM records — the Interview agent collects
several, not one), `body_fat_pct`, `calendar_type` (single deadline vs weekly fixtures vs
open-ended — drives the Planner's periodization choice), and `split_preferences`.

**Files:**
- Modify: `src/performance_agent/memory/schemas.py`
- Test: `tests/memory/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/memory/test_schemas.py` (add `LiftRecord` to the schema imports):

```python
def test_profile_accepts_lift_inventory_and_bodycomp():
    profile = Profile(
        body_fat_pct=18.5,
        calendar_type="single_deadline",
        split_preferences=["upper/lower"],
        lift_inventory=[
            LiftRecord(lift="back squat", one_rm_kg=140, recorded_on=date(2026, 7, 1)),
            LiftRecord(
                lift="bench press",
                one_rm_kg=100,
                recorded_on=date(2026, 7, 1),
                source="estimated",
            ),
        ],
    )
    assert profile.lift_inventory[1].source == "estimated"
    assert profile.calendar_type == "single_deadline"


def test_lift_record_defaults_to_tested_and_bounds():
    record = LiftRecord(lift="deadlift", one_rm_kg=180, recorded_on=date(2026, 7, 1))
    assert record.source == "tested"
    with pytest.raises(ValidationError):
        LiftRecord(lift="deadlift", one_rm_kg=0, recorded_on=date(2026, 7, 1))


@pytest.mark.parametrize(
    ("field", "value"),
    [("body_fat_pct", 1), ("body_fat_pct", 80), ("calendar_type", "seasonal")],
)
def test_profile_rejects_out_of_contract_new_fields(field, value):
    with pytest.raises(ValidationError):
        Profile(**{field: value})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: FAIL — `ImportError: cannot import name 'LiftRecord'`

- [ ] **Step 3: Implement**

In `src/performance_agent/memory/schemas.py`, add above `Profile`:

```python
CalendarType = Literal["single_deadline", "recurring_fixtures", "open_ended"]


class LiftRecord(BaseModel):
    """A known 1RM for one lift; 'estimated' means derived via estimate_1rm, not tested."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1)
    one_rm_kg: float = Field(gt=0, le=1000)
    recorded_on: date
    source: Literal["tested", "estimated"] = "tested"
```

Add to `Profile` (after `availability`):

```python
    lift_inventory: list[LiftRecord] = Field(default_factory=list)
    body_fat_pct: float | None = Field(default=None, ge=3, le=60)
    calendar_type: CalendarType | None = None
    split_preferences: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: PASS

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff format . && uv run ruff check . && uv run ty check`

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas.py
git commit -m "Add lift inventory, body composition and calendar type to Profile"
```

---

### Task 3: Bodyweight, measurements and PRs on CheckinEntry

Check-ins gain the cut/recomp tracking signals: `bodyweight_kg` (time series when read
across check-ins), `measurements` (site → cm), and `prs` (rep PRs achieved since last
check-in — feeds stall detection and lift-inventory refreshes).

**Files:**
- Modify: `src/performance_agent/memory/schemas.py`
- Test: `tests/memory/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/memory/test_schemas.py` (add `RepPR` to the schema imports):

```python
def test_checkin_accepts_bodyweight_measurements_and_prs():
    entry = CheckinEntry(
        at=datetime(2026, 7, 11, 9, 0),
        bodyweight_kg=79.4,
        measurements={"waist": 84.0},
        prs=[RepPR(lift="bench press", reps=5, load_kg=90, achieved_on=date(2026, 7, 9))],
    )
    assert entry.measurements["waist"] == 84.0
    assert entry.prs[0].reps == 5


def test_checkin_new_fields_are_optional():
    entry = CheckinEntry(at=datetime(2026, 7, 11, 9, 0), fatigue=3)
    assert entry.bodyweight_kg is None
    assert entry.measurements == {}
    assert entry.prs == []


def test_checkin_bodyweight_bounds():
    with pytest.raises(ValidationError):
        CheckinEntry(at=datetime(2026, 7, 11, 9, 0), bodyweight_kg=10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: FAIL — `ImportError: cannot import name 'RepPR'`

- [ ] **Step 3: Implement**

In `src/performance_agent/memory/schemas.py`, add above `CheckinEntry`:

```python
class RepPR(BaseModel):
    """A rep personal record: best load for a rep count on a lift."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1)
    reps: int = Field(ge=1, le=100)
    load_kg: float = Field(gt=0, le=1000)
    achieved_on: date
```

Add to `CheckinEntry` (after `pain_flags`):

```python
    bodyweight_kg: float | None = Field(default=None, ge=30, le=250)
    measurements: dict[str, float] = Field(default_factory=dict)
    prs: list[RepPR] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/memory/test_schemas.py -q`
Expected: PASS

- [ ] **Step 5: Lint, type-check, commit**

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas.py
git commit -m "Add bodyweight, measurements and rep PRs to CheckinEntry"
```

---

### Task 4: Backward compatibility — pre-extension athlete directories still load

Existing athlete directories (written before this change) must keep validating, and new
structured data must round-trip through the store (atomic YAML + JSONL).

**Files:**
- Test: `tests/memory/test_store_logs.py`
- Test: `tests/memory/test_store_profile_goals.py`

- [ ] **Step 1: Write the tests** (they should pass immediately if Tasks 1–3 are truly
additive — a failure here means a default is missing)

Append to `tests/memory/test_store_logs.py` (it already imports `store`; add the schema
imports used below):

```python
def test_pre_extension_session_line_still_loads(tmp_path):
    legacy = '{"performed_at": "2026-07-01T18:00:00", "kind": "run", "rpe": 5}'
    (tmp_path / "sessions.jsonl").write_text(legacy + "\n", encoding="utf-8")
    sessions = store.read_sessions(tmp_path)
    assert sessions[0].exercises == []


def test_structured_session_round_trips(tmp_path):
    entry = SessionEntry(
        performed_at=datetime(2026, 7, 11, 18, 0),
        kind="strength",
        exercises=[
            ExercisePerformed(
                name="back squat", sets=[SetPerformed(reps=5, load_kg=100, rir=2)]
            )
        ],
    )
    store.append_session(tmp_path, entry)
    assert store.read_sessions(tmp_path)[0] == entry


def test_pre_extension_checkin_line_still_loads(tmp_path):
    legacy = '{"at": "2026-07-01T09:00:00", "adherence_pct": 80.0}'
    (tmp_path / "checkins.jsonl").write_text(legacy + "\n", encoding="utf-8")
    checkins = store.read_checkins(tmp_path)
    assert checkins[0].prs == []
```

Append to `tests/memory/test_store_profile_goals.py`:

```python
def test_pre_extension_profile_yaml_still_loads(tmp_path):
    (tmp_path / "profile.yaml").write_text(
        "locale: en\nweight_kg: 75\nsport: running\n", encoding="utf-8"
    )
    profile = store.read_profile(tmp_path)
    assert profile.lift_inventory == []
    assert profile.calendar_type is None


def test_extended_profile_round_trips(tmp_path):
    profile = Profile(
        calendar_type="recurring_fixtures",
        lift_inventory=[
            LiftRecord(lift="back squat", one_rm_kg=140, recorded_on=date(2026, 7, 1))
        ],
    )
    store.write_profile(tmp_path, profile)
    assert store.read_profile(tmp_path) == profile
```

- [ ] **Step 2: Run the memory suite**

Run: `uv run pytest tests/memory -q`
Expected: PASS. If a legacy test fails, a new field is missing its default — fix the
schema, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/memory/test_store_logs.py tests/memory/test_store_profile_goals.py
git commit -m "Prove memory extensions are backward compatible"
```

---

### Task 5: MCP surface — docstrings and an end-to-end structured-session test

No new tools: the extended schemas flow through `log_session`, `write_profile`,
`log_checkin` automatically. Two docstrings must stop under-describing what is stored,
and one server test proves a structured strength session survives the full MCP
round-trip (FastMCP serializes tool arguments — this is where a schema regression
would actually bite).

**Files:**
- Modify: `src/performance_agent/server/memory_tools.py`
- Test: `tests/server/test_memory_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/server/test_memory_tools.py`, following the file's existing in-process
session pattern (reuse its fixtures/helpers for calling tools; the dict below is the
tool argument):

The file's harness: a `client` fixture (in-process MCP session, `tests/server/conftest.py`)
plus an autouse `athlete_home` fixture isolating `PERFORMANCE_AGENT_HOME` per test; async
tests are marked `@pytest.mark.anyio`.

```python
@pytest.mark.anyio
async def test_log_session_round_trips_structured_exercises(client):
    entry = {
        "performed_at": "2026-07-11T18:00:00",
        "kind": "strength",
        "exercises": [
            {
                "name": "back squat",
                "sets": [
                    {"reps": 5, "load_kg": 100.0, "rir": 2},
                    {"reps": 5, "load_kg": 100.0, "rir": 1},
                ],
            }
        ],
    }
    result = await client.call_tool("log_session", {"entry": entry})
    assert not result.isError

    read_back = await client.call_tool("read_sessions", {})
    sessions = read_back.structuredContent["sessions"]
    assert sessions[0]["exercises"][0]["sets"][1]["rir"] == 1
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/server/test_memory_tools.py -q`
Expected: PASS if Tasks 1–4 are correct (FastMCP regenerates schemas from the Pydantic
models). A failure exposes a serialization gap — fix the schema, not the test.

- [ ] **Step 3: Update docstrings**

In `src/performance_agent/server/memory_tools.py`:

`write_profile` — the full-replace warning must list the new droppable fields:

```python
def write_profile(profile: Profile) -> WrittenFile:
    """Replace the athlete profile.

    Read the athlete first, then write the FULL updated profile — this is a
    whole-document replace, not a merge: omitted fields are DROPPED
    (injuries, equipment, availability, notes, lift_inventory, body_fat_pct,
    calendar_type, split_preferences).
    """
```

`log_session` — advertise structured strength logging:

```python
def log_session(entry: SessionEntry) -> SessionCount:
    """Append one completed training session to the athlete's history.

    Strength sessions should carry structured exercises → sets
    {reps, load_kg, rir}; endurance sessions may omit exercises entirely.
    Timestamps are naive local wall-clock time (no timezone offset).
    """
```

`log_checkin` — advertise the new signals:

```python
def log_checkin(entry: CheckinEntry) -> CheckinEntry:
    """Append a check-in; days_since_last is auto-filled from the previous one.

    Record bodyweight_kg at every check-in when the goal involves body
    composition — the series across check-ins IS the trend the coach reads.
    days_since_last may be negative for backdated entries.
    """
```

- [ ] **Step 4: Run the server suite**

Run: `uv run pytest tests/server -q`
Expected: PASS (docstring changes can break tool-description assertions if any exist —
if one fails, update the asserted text to match the new docstring).

- [ ] **Step 5: Lint, type-check, commit**

```bash
git add src/performance_agent/server/memory_tools.py tests/server/test_memory_tools.py
git commit -m "Round-trip structured sessions through MCP and update tool docs"
```

---

### Task 6: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Full test suite**

Run: `uv run pytest -q`
Expected: all tests pass (290 pre-existing + ~14 new).

- [ ] **Step 2: Zero-warning gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run ty check`
Expected: clean output, no warnings.

- [ ] **Step 3: Skills eval harness still green**

Run: `uv run pytest tests/skills -q`
Expected: PASS — this phase must not touch skills; a failure here means a tool
docstring drifted from what a skill declares. Fix the docstring wording, not the skill.

- [ ] **Step 4: Commit any stragglers**

```bash
git status --short
```

Expected: clean tree. If formatting touched files, commit:

```bash
git add -A && git commit -m "Apply formatting"
```
