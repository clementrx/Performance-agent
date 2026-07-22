# Exercise Media Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the coach (the LLM) bind each program block to its exercise GIF at program-creation time, so programs written in the athlete's language (Spanish, French, …) render with media from the English-named `hasaneyldrm/exercises-dataset`.

**Architecture:** A new optional `media_id` field on `ExerciseBlock` holds a dataset record id chosen by the agent. HTML rendering resolves `media_id` first (direct id lookup), falling back to the existing chain (seed map → exact name → fuzzy). A new MCP tool `search_exercise_media` searches the local dataset clone so the agent can translate the exercise name to English, pick the right record, and stamp its id. The `program-optimization` skill gains the binding step.

**Tech Stack:** Python 3.13, Pydantic v2 schemas, FastMCP server, pytest (in-process MCP client fixture). Dataset clone already auto-syncs at server start (`exercises/dataset.py`) — no sync changes.

**Spec:** `docs/superpowers/specs/2026-07-22-exercise-media-binding-design.md`

**Conventions:** run everything with `uv run` from the repo root. Line length 100. Tests colocated under `tests/` mirroring the package. The working tree has an unrelated `README.md` modification — never `git add README.md` except in Task 6 (which touches only the tool-count lines).

---

### Task 0: Feature branch

**Files:** none

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feat/exercise-media-binding
```

- [ ] **Step 2: Verify clean state (only README.md may appear modified)**

Run: `git status --short`
Expected: ` M README.md` only.

---

### Task 1: `media_id` field on `ExerciseBlock`

The schema change everything else hangs on. Dataset ids are 4-char numeric strings today (`"0043"`), but validation stays loose (length only) because the dataset is external and its id scheme may evolve; a wrong id degrades to "no media" at render, never an error.

**Files:**
- Create: `tests/memory/test_schemas_media.py`
- Modify: `src/performance_agent/memory/schemas.py:394` (just after `exercise_id`)

- [ ] **Step 1: Write the failing tests**

Create `tests/memory/test_schemas_media.py`:

```python
"""media_id on ExerciseBlock: agent-chosen dataset media binding."""

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import ExerciseBlock


def block_fields(**overrides):
    fields = {
        "exercise": "Sentadilla trasera",
        "priority": "primary",
        "sets": 4,
        "reps": "5",
        "load_kg": 60.0,
        "progression_rule": "double_progression(4-6, +2.5kg)",
    }
    fields.update(overrides)
    return fields


def test_media_id_defaults_to_none():
    block = ExerciseBlock.model_validate(block_fields())
    assert block.media_id is None


def test_media_id_accepts_dataset_shaped_id():
    block = ExerciseBlock.model_validate(block_fields(media_id="0043"))
    assert block.media_id == "0043"


@pytest.mark.parametrize("bad", ["", "x" * 17])
def test_media_id_rejects_empty_and_overlong(bad):
    with pytest.raises(ValidationError):
        ExerciseBlock.model_validate(block_fields(media_id=bad))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/memory/test_schemas_media.py -q`
Expected: FAIL — `media_id` is rejected by `extra="forbid"` on the first two tests.

- [ ] **Step 3: Add the field**

In `src/performance_agent/memory/schemas.py`, directly below the `exercise_id` line (line 394):

```python
    exercise_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    media_id: str | None = Field(default=None, min_length=1, max_length=16)
```

(The `exercise_id` line already exists — add only the `media_id` line.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/memory/test_schemas_media.py -q`
Expected: 4 passed.

- [ ] **Step 5: Run the neighbouring schema/store tests (regression)**

Run: `uv run pytest tests/memory tests/programs -q`
Expected: all pass (field is optional, existing plans unaffected).

- [ ] **Step 6: Commit**

```bash
git add tests/memory/test_schemas_media.py src/performance_agent/memory/schemas.py
git commit -m "feat: add media_id binding field to ExerciseBlock"
```

---

### Task 2: id lookup on the index + `media_id` priority in HTML rendering

**Files:**
- Modify: `src/performance_agent/exercises/dataset.py` (class `ExerciseMediaIndex`, after `load`)
- Modify: `src/performance_agent/programs/render_html.py:208-220` (`_MediaCatalog.resolve`)
- Test: `tests/exercises/test_dataset.py`
- Test: `tests/programs/test_render_html.py`

The fixture dataset (`tests/exercises/test_dataset.py::write_fixture_dataset`) has two records: `0043` "barbell full squat" (GIF present, en+fr steps) and `0025` "barbell bench press" (GIF intentionally missing, en steps only).

- [ ] **Step 1: Write the failing index test**

Append to `tests/exercises/test_dataset.py`:

```python
def test_get_by_dataset_id(index):
    assert index.get("0043").name == "barbell full squat"
    assert index.get("9999") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/exercises/test_dataset.py::test_get_by_dataset_id -q`
Expected: FAIL — `AttributeError: 'ExerciseMediaIndex' object has no attribute 'get'`.

- [ ] **Step 3: Implement `get`**

In `src/performance_agent/exercises/dataset.py`, inside `ExerciseMediaIndex`, after the `load` classmethod:

```python
    def get(self, dataset_id: str) -> DatasetExercise | None:
        """Return the record with this dataset id, or None when unknown."""
        return self._by_id.get(dataset_id)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/exercises/test_dataset.py::test_get_by_dataset_id -q`
Expected: PASS.

- [ ] **Step 5: Write the failing render tests**

In `tests/programs/test_render_html.py`, replace the existing `linked_plan` helper (lines 31-46) with a block-parameterised version — existing callers stay valid:

```python
def linked_plan(block: ExerciseBlock | None = None, **overrides):
    session = SessionPlan(
        id="w01-s1-lower-heavy",
        weekday=0,
        qualities=["strength_heavy"],
        patterns=["squat"],
        est_minutes=75,
        purpose="Build the squat base",
        blocks=[block if block is not None else squat_block()],
        fallbacks=a_fallbacks(),
    )
    week = WeekPlan(week_index=1, volume_factor=1.0, intensity_factor=0.9, sessions=[session])
    return minimal_plan(
        mesocycles=[{"index": 1, "phase": "accumulation", "weeks": [week.model_dump()]}],
        **overrides,
    )
```

Then append the three tests:

```python
def test_media_id_binds_localized_name_to_gif(index):
    block = squat_block(exercise="Sentadilla trasera", exercise_id=None, media_id="0043")
    page = render_program_html(linked_plan(block), index=index)
    assert '<div class="media m-0043"></div>' in page
    assert "data:image/gif;base64," in page


def test_media_id_wins_over_name_resolution(index):
    # exercise name resolves to the squat record; the explicit binding must win
    page = render_program_html(linked_plan(squat_block(media_id="0025")), index=index)
    assert "Press the bar." in page
    assert "Stand with the bar on your back." not in page


def test_unknown_media_id_falls_back_to_name_chain(index):
    page = render_program_html(linked_plan(squat_block(media_id="9999")), index=index)
    assert '<div class="media m-0043"></div>' in page
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/programs/test_render_html.py -q`
Expected: `test_media_id_binds_localized_name_to_gif` and `test_media_id_wins_over_name_resolution` FAIL (media resolved from the name, not the binding); `test_unknown_media_id_falls_back_to_name_chain` passes already (fallback is today's behaviour); all pre-existing tests still pass.

- [ ] **Step 7: Implement the priority in `_MediaCatalog.resolve`**

In `src/performance_agent/programs/render_html.py`, replace the body of `_MediaCatalog.resolve` (lines 208-220):

```python
    def resolve(self, block: ExerciseBlock) -> tuple[DatasetExercise | None, str | None]:
        """Return the dataset record and the CSS class key of its embedded GIF."""
        if self._index is None:
            return None, None
        record = self._index.get(block.media_id) if block.media_id is not None else None
        if record is None:
            record = self._index.resolve(block.exercise, block.exercise_id)
        if record is None:
            return None, None
        key = _css_key(record.dataset_id)
        if key not in self.uris:
            uri = record.gif_data_uri()
            if uri is not None:
                self.uris[key] = uri
        return record, key if key in self.uris else None
```

- [ ] **Step 8: Run the render and exercise tests**

Run: `uv run pytest tests/programs/test_render_html.py tests/exercises/test_dataset.py -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/performance_agent/exercises/dataset.py src/performance_agent/programs/render_html.py \
  tests/exercises/test_dataset.py tests/programs/test_render_html.py
git commit -m "feat: resolve exercise media by explicit media_id before name chain"
```

---

### Task 3: `search` on `ExerciseMediaIndex`

Pure-Python search the MCP tool will wrap: normalised substring matches ranked first (alphabetical for determinism), then close-name fuzzy completion, optional equality filters on the dataset's `equipment` / `target` vocabulary.

**Files:**
- Modify: `src/performance_agent/exercises/dataset.py` (class `ExerciseMediaIndex`, after `get`)
- Test: `tests/exercises/test_dataset.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/exercises/test_dataset.py`:

```python
def test_search_substring_match(index):
    assert [e.dataset_id for e in index.search("squat")] == ["0043"]


def test_search_filters_by_equipment_and_target(index):
    assert [e.dataset_id for e in index.search("barbell", target="pectorals")] == ["0025"]
    assert index.search("barbell", equipment="cable") == []


def test_search_fuzzy_completes_close_names(index):
    assert "0025" in [e.dataset_id for e in index.search("barbel bench pres")]


def test_search_respects_limit(index):
    assert len(index.search("barbell", limit=1)) == 1


def test_search_rejects_blank_query(index):
    with pytest.raises(ValueError, match="query"):
        index.search("  !! ")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/exercises/test_dataset.py -q -k search`
Expected: 5 FAIL — no attribute `search`.

- [ ] **Step 3: Implement `search`**

In `src/performance_agent/exercises/dataset.py`, inside `ExerciseMediaIndex`, after `get`:

```python
    def search(
        self,
        query: str,
        equipment: str | None = None,
        target: str | None = None,
        limit: int = 10,
    ) -> list[DatasetExercise]:
        """Rank records for an English query: substring matches first, then close names.

        equipment and target filter case-insensitively on the dataset's own
        vocabulary. Raises ValueError on a blank query — nothing to match on.
        """
        normalised = _normalise(query)
        if not normalised:
            msg = f"query must contain letters or digits, got {query!r}"
            raise ValueError(msg)
        candidates = {
            name: exercise
            for name, exercise in self._by_norm_name.items()
            if (equipment is None or exercise.equipment.lower() == equipment.lower())
            and (target is None or exercise.target.lower() == target.lower())
        }
        hits = [name for name in sorted(candidates) if normalised in name]
        if len(hits) < limit:
            remaining = [name for name in candidates if name not in set(hits)]
            hits.extend(
                difflib.get_close_matches(normalised, remaining, n=limit - len(hits), cutoff=0.6)
            )
        return [candidates[name] for name in hits[:limit]]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/exercises/test_dataset.py -q`
Expected: all pass (new and pre-existing).

- [ ] **Step 5: Commit**

```bash
git add src/performance_agent/exercises/dataset.py tests/exercises/test_dataset.py
git commit -m "feat: add filtered name search to ExerciseMediaIndex"
```

---

### Task 4: MCP tool `search_exercise_media`

**Files:**
- Modify: `src/performance_agent/server/exercise_tools.py`
- Test: `tests/server/test_exercise_tools.py`
- Modify: `tests/server/test_new_tool_coverage.py` (tool-coverage guard)

The in-process MCP `client` fixture comes from `tests/server/conftest.py`. The tool resolves the dataset dir through `resolve_dataset_dir()`, which honours the `PERFORMANCE_AGENT_EXERCISES_DATASET` env var — tests point it at the fixture dataset (or at a missing path) so they never touch the developer's real ~420 MB clone.

- [ ] **Step 1: Write the failing server tests**

Append to `tests/server/test_exercise_tools.py`:

```python
@pytest.mark.anyio
async def test_search_exercise_media_returns_candidates(client, monkeypatch, tmp_path):
    from tests.exercises.test_dataset import write_fixture_dataset

    dataset_dir = write_fixture_dataset(tmp_path / "ds")
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(dataset_dir))
    result = await client.call_tool(
        "search_exercise_media", {"query": "squat", "equipment": "barbell"}
    )
    assert not result.isError
    payload = result.structuredContent
    assert payload["dataset_available"] is True
    assert payload["candidates"][0]["media_id"] == "0043"
    assert payload["candidates"][0]["target"] == "glutes"


@pytest.mark.anyio
async def test_search_exercise_media_without_dataset(client, monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(tmp_path / "missing"))
    result = await client.call_tool("search_exercise_media", {"query": "squat"})
    assert not result.isError
    payload = result.structuredContent
    assert payload["dataset_available"] is False
    assert payload["candidates"] == []
    assert payload["hint"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/server/test_exercise_tools.py -q`
Expected: the two new tests FAIL — unknown tool `search_exercise_media`; the four pre-existing tests pass.

- [ ] **Step 3: Implement the tool**

In `src/performance_agent/server/exercise_tools.py`:

Add to the imports (after the existing `from mcp.server.fastmcp import FastMCP`):

```python
from typing import TypedDict

from performance_agent.exercises.dataset import ExerciseMediaIndex
```

Add before `register` (after `check_program_specificity`):

```python
class ExerciseMediaCandidateView(TypedDict):
    """One dataset record a program block can be bound to via media_id."""

    media_id: str
    name: str
    equipment: str
    target: str
    secondary_muscles: list[str]


class ExerciseMediaSearchView(TypedDict):
    """Search outcome: candidates, or a hint when the dataset is not synced yet."""

    dataset_available: bool
    hint: str
    candidates: list[ExerciseMediaCandidateView]


def search_exercise_media(
    query: str,
    equipment: str | None = None,
    target: str | None = None,
    limit: int = 10,
) -> ExerciseMediaSearchView:
    """Find exercise GIF records to bind program blocks to (set the block's media_id).

    Dataset names are ENGLISH only — you are the translation layer: turn the
    athlete-language exercise ("sentadilla trasera") into English gym vocabulary
    ("barbell squat") before searching. Optional equipment/target narrow by the
    dataset's own vocabulary (e.g. equipment "barbell", target "glutes"). Pick the
    candidate matching the prescribed movement and set its media_id on the block;
    when none clearly matches, leave media_id unset — a wrong GIF is worse than no
    GIF. dataset_available false means the local clone is not synced yet (it
    downloads in the background at server start): programs render without media
    until then.
    """
    try:
        index = ExerciseMediaIndex.load()
    except (FileNotFoundError, NotADirectoryError):
        return {
            "dataset_available": False,
            "hint": (
                "exercises-dataset clone not synced yet — it downloads in the background "
                "at server start; retry shortly or check network access to github.com"
            ),
            "candidates": [],
        }
    records = index.search(query, equipment=equipment, target=target, limit=limit)
    return {
        "dataset_available": True,
        "hint": "",
        "candidates": [
            {
                "media_id": record.dataset_id,
                "name": record.name,
                "equipment": record.equipment,
                "target": record.target,
                "secondary_muscles": list(record.secondary_muscles),
            }
            for record in records
        ],
    }
```

Update `register` to include the new tool:

```python
def register(mcp: FastMCP) -> None:
    """Register every exercise-ontology tool on the server."""
    for tool in (
        list_exercises,
        propose_exercise,
        score_exercises,
        check_program_specificity,
        search_exercise_media,
    ):
        mcp.tool()(tool)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/server/test_exercise_tools.py -q`
Expected: 6 passed.

- [ ] **Step 5: Add the tool to the coverage guard**

In `tests/server/test_new_tool_coverage.py`:

1. Add `"search_exercise_media",` to the `_NEW_TOOLS` set (after `"check_program_specificity",`).
2. Add `"search_exercise_media": {"query": "squat"},` to the `calls` dict (after the `"check_program_specificity"` entry).
3. Keep the call hermetic — in the `athlete_home` fixture, point the dataset dir at a non-existent path so the tool takes the `dataset_available: false` branch (non-error) instead of reading a real clone on developer machines:

```python
@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    monkeypatch.setenv("PERFORMANCE_AGENT_EXERCISES_DATASET", str(tmp_path / "no-dataset"))
    return tmp_path
```

- [ ] **Step 6: Run the coverage guard**

Run: `uv run pytest tests/server/test_new_tool_coverage.py -q`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add src/performance_agent/server/exercise_tools.py tests/server/test_exercise_tools.py \
  tests/server/test_new_tool_coverage.py
git commit -m "feat: add search_exercise_media MCP tool"
```

---

### Task 5: Binding step in the `program-optimization` skill

**Files:**
- Modify: `skills/program-optimization/SKILL.md` (section "2b. Choose exercises from the ontology", list ends line ~104)

- [ ] **Step 1: Check the tool list in the frontmatter/header**

Run: `grep -n "search_exercise_media\|allowed-tools\|list_exercises" skills/program-optimization/SKILL.md | head`
If the skill declares a tool list mentioning `list_exercises`/`score_exercises` (line ~16), add `search_exercise_media` to it.

- [ ] **Step 2: Add the binding step**

In section 2b, after numbered step 3 (which ends "…before you reference it.", line ~104), append step 4:

```markdown
4. **Bind the demo media**: for each strength block, call `search_exercise_media`
   with the ENGLISH movement name — you are the translation layer ("sentadilla
   trasera" → "barbell squat") — optionally narrowed by `equipment` / `target`,
   and set the chosen candidate's `media_id` on the block. Best-effort: no clear
   match, or `dataset_available: false` → leave `media_id` unset; a wrong GIF is
   worse than no GIF. Skip conditioning blocks (runs, intervals) — the dataset is
   gym-exercise media. The saved program's HTML page then embeds each bound
   exercise's GIF and technique steps in the athlete's locale.
```

- [ ] **Step 3: Run the skill-integrity tests (if any reference tool names)**

Run: `uv run pytest tests/skills -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add skills/program-optimization/SKILL.md
git commit -m "docs: bind exercise media in program-optimization skill"
```

---

### Task 6: Tool count 103 → 104 in READMEs + changelog

**Files:**
- Modify: `README.md:125` and `README.md:350`
- Modify: `docs/i18n/README.fr.md`, `README.it.md`, `README.es.md`, `README.de.md` (all `103` occurrences; check the others too)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Find every stale count**

Run: `grep -rn "103" README.md docs/i18n/`
Expected: the tool-count sentences ("You should see 103 tools", "103 MCP tools", and their translations).

- [ ] **Step 2: Update each to 104**

Edit each hit from Step 1, replacing `103` with `104` **only in tool-count sentences** (leave any unrelated `103` untouched). README.md has an unrelated pending modification — edit only these lines.

- [ ] **Step 3: Add the changelog entry**

In `CHANGELOG.md`, insert directly under the top `# Changelog` intro (before `## 0.11.0`):

```markdown
## Unreleased

### Added

- **Exercise media binding** — new `media_id` field on program blocks and a
  `search_exercise_media` MCP tool: the coach binds each strength exercise to its
  dataset GIF at program creation, so programs written in the athlete's language
  (Spanish, French, …) render with media despite the dataset's English-only names.
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/i18n/README.fr.md docs/i18n/README.it.md docs/i18n/README.es.md \
  docs/i18n/README.de.md CHANGELOG.md
git commit -m "docs: bump tool count to 104 and add media-binding changelog entry"
```

(If `git status` shows other i18n READMEs with a 103 count — e.g. `README.pt.md` — include them.)

---

### Task 7: Full verification

**Files:** none

- [ ] **Step 1: Full test suite**

Run: `uv run pytest -q`
Expected: all pass (baseline was 1425; now ~1439).

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: no diagnostics. Fix anything reported before continuing.

- [ ] **Step 3: Type check**

Run: `uv run ty check`
Expected: no errors. (If `ty` is not configured in this repo, skip with a note.)

- [ ] **Step 4: Hooks**

Run: `prek run`
Expected: all hooks pass.

- [ ] **Step 5: Manual smoke — real dataset**

Run:

```bash
uv run python - <<'EOF'
from performance_agent.exercises.dataset import ExerciseMediaIndex
index = ExerciseMediaIndex.load()
for record in index.search("barbell squat", limit=5):
    print(record.dataset_id, record.name, "|", record.equipment, "|", record.target)
EOF
```

Expected: five real records including a barbell squat variant, proving the search works against the actual 1,324-record clone in `~/.performance-agent/cache/exercises-dataset`.

---

## Out of scope (from the spec)

- Multilingual alias table (rejected during design).
- `render_report` changes — program pages come from `save_program`, already media-aware.
- Regenerating Maria's program — after merge/release, a v2 `save_program` with reason
  "add exercise media" rebinds it (usage, not code).
- Dataset sync changes — clone/pull automation already exists and works.
