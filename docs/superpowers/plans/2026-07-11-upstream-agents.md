# Upstream Agents (Premium Pipeline Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three upstream agents of the premium pipeline as skill protocols exploiting phases 1–3: an enriched Interview (l'Entretien — multi-lift 1RM inventory, calendar type, body composition, split preferences), a new Analyst (l'Analyste — needs analysis + multi-goal honest feasibility verdict, replacing goal-assessment), and a new Researcher (le Chercheur — deep multilingual faceted research with a coverage loop), backed by versioned analysis and research-dossier stores that mirror the program store's immutable audit trail.

**Architecture:** Server side, `memory/store.py` generalizes its private program helpers into one versioned-document family (`athlete/programs/program-vN.md`, `athlete/analysis/needs-analysis-vN.md`, `athlete/research/dossier-vN.md` — same frontmatter, same reason-required-on-v2+ rule) exposed as 4 new MCP tools (41 → 45). Skill side, `athlete-onboarding` is reworked in place, `goal-assessment` is deleted and replaced by `skills/needs-analysis/`, `skills/deep-research/` is new, and `performance-coach`/`program-generation` re-route onto the new pipeline (Entretien → Analyste → Chercheur → program-generation; the Planner/Optimizer split is phase 5). Spec: `docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md` §2 (Interview/Analyst/Researcher), §3 (data flow), §5 (Researcher protocol, agent side).

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing FastMCP in-process test harness, Claude Code skill format (SKILL.md with YAML frontmatter).

**Conventions (this repo):**
- Line length 100; `uv run ruff format . && uv run ruff check . && uv run ty check` must stay clean (zero warnings).
- In a worktree, run tools as `env -u VIRTUAL_ENV uv run pytest -q` etc. — the parent repo's venv must not leak in.
- Commits: imperative subject, no type prefix (match `git log`), ≤72 chars.
- **The skills eval harness (`tests/skills/`) must stay green after every task.** Its rules bind every SKILL.md in this plan:
  - directory name == frontmatter `name` (`test_structure.py`);
  - `tools:` list ⇄ body mentions enforced in BOTH directions: every declared tool must appear in the body, and any server tool name appearing in the body (substring match, even in prose) must be declared (`test_tool_references.py`) — so never namedrop a tool a skill doesn't declare;
  - skills may only declare tools that exist on the server (`test_declared_tools_exist_on_the_server` — 45 after Task 1);
  - skill bodies must pass the anti-fabrication scanner (`test_no_fabricated_refs.py`) — no DOIs/PMIDs/ISBNs or author-year citations in skill prose.
- Skills are written in English (French probe examples are welcome as quoted examples), each under ~150 lines like the existing ones.
- The spec's tree sketch (§3) puts `needs-analysis-v1.md` at the athlete root; this plan uses `athlete/analysis/needs-analysis-vN.md` (a subdirectory per document family, matching `programs/` and `research/`) — a deliberate, maintainer-approved deviation for symmetry.

---

### Task 1: Versioned analysis & research stores + 4 MCP tools (41 → 45)

Mirror the program store pattern exactly: immutable versions, YAML frontmatter
(`version`, `goal_id`, `created_on`, `reason`), reason required from v2+. The three
program helpers (`_program_path`, `latest_program_version`, `save_program`/`read_program`
internals) collapse cleanly into one shared versioned-document family — do that
generalization, but **program behavior must not change**: every existing test in
`tests/memory/test_store_programs.py` and `tests/server/test_memory_tools.py` stays
green untouched (they are the regression net for the refactor).

**Files:**
- Modify: `src/performance_agent/memory/store.py`
- Modify: `src/performance_agent/server/memory_tools.py`
- Create: `tests/memory/test_store_documents.py`
- Modify: `tests/server/test_memory_tools.py`
- Modify: `README.md` (line 109), `docs/installing.md` (line ~205)

- [ ] **Step 1: Write the failing store tests**

Create `tests/memory/test_store_documents.py` (mirrors `test_store_programs.py` style):

```python
from datetime import date

import pytest

from performance_agent.memory.store import (
    read_analysis,
    read_program,
    read_research_dossier,
    save_analysis,
    save_program,
    save_research_dossier,
)

TODAY = date(2026, 7, 11)

DOC_KINDS = [
    pytest.param(save_analysis, read_analysis, "analysis", "needs-analysis", id="analysis"),
    pytest.param(
        save_research_dossier, read_research_dossier, "research", "dossier", id="research"
    ),
]


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_no_documents_yet(tmp_path, save, read, subdir, prefix):
    assert read(tmp_path) is None


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_first_version_is_v1_and_needs_no_reason(tmp_path, save, read, subdir, prefix):
    path, version = save(tmp_path, "# Section\nbody.", "squat-160", today=TODAY)
    assert version == 1
    assert path == tmp_path / subdir / f"{prefix}-v1.md"
    result = read(tmp_path)
    assert result is not None
    frontmatter, body = result
    assert frontmatter["version"] == 1
    assert frontmatter["goal_id"] == "squat-160"
    assert frontmatter["created_on"] == "2026-07-11"
    assert frontmatter["reason"] is None
    assert body == "# Section\nbody."


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_revision_requires_a_reason(tmp_path, save, read, subdir, prefix):
    save(tmp_path, "v1", "squat-160", today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        save(tmp_path, "v2", "squat-160", today=TODAY)
    _, version = save(
        tmp_path, "v2", "squat-160", reason="goal renegotiated", today=TODAY
    )
    assert version == 2


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_old_versions_stay_readable(tmp_path, save, read, subdir, prefix):
    save(tmp_path, "first body", "squat-160", today=TODAY)
    save(tmp_path, "second body", "squat-160", reason="re-run", today=TODAY)
    result = read(tmp_path, version=1)
    assert result is not None
    frontmatter, body = result
    assert frontmatter["version"] == 1
    assert body == "first body"


@pytest.mark.parametrize(("save", "read", "subdir", "prefix"), DOC_KINDS)
def test_reading_a_missing_version_is_an_error(tmp_path, save, read, subdir, prefix):
    save(tmp_path, "v1", "squat-160", today=TODAY)
    with pytest.raises(ValueError, match="version 7"):
        read(tmp_path, version=7)


def test_document_families_version_independently(tmp_path):
    save_program(tmp_path, "program", "squat-160", today=TODAY)
    save_analysis(tmp_path, "analysis", "squat-160", today=TODAY)
    save_research_dossier(tmp_path, "dossier", "squat-160", today=TODAY)
    # Each family has its own v1 counter — a program does not bump the analysis.
    path, version = save_analysis(
        tmp_path, "analysis v2", "squat-160", reason="verdict changed", today=TODAY
    )
    assert version == 2
    assert path == tmp_path / "analysis" / "needs-analysis-v2.md"
    result = read_program(tmp_path)
    assert result is not None
    assert result[0]["version"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/memory/test_store_documents.py -q`
Expected: FAIL — `ImportError: cannot import name 'save_analysis'`

- [ ] **Step 3: Implement the generalized store**

In `src/performance_agent/memory/store.py`, add the directory constants next to
`PROGRAMS_DIR`:

```python
ANALYSIS_DIR = "analysis"
RESEARCH_DIR = "research"
```

Replace the private program helpers (`_program_path` and the bodies of
`latest_program_version`, `save_program`, `read_program`) with the shared family —
keep the exact error-message shapes the existing tests match (`"requires a reason"`,
`"versions are immutable"`, `"version {N} does not exist"`, filename-naming on corrupt
frontmatter, frontmatter-vs-filename version check):

```python
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


def _save_versioned_doc(
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
```

The public API — programs delegate (docstrings unchanged), analysis and research are new:

```python
def latest_program_version(base_dir: Path) -> int | None:
    """Return the highest existing program version, or None."""
    return _latest_doc_version(base_dir, PROGRAMS_DIR, "program")


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
        base_dir, markdown_body, goal_id,
        subdir=PROGRAMS_DIR, prefix="program", label="program", reason=reason, today=today,
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
        base_dir, markdown_body, goal_id,
        subdir=ANALYSIS_DIR, prefix="needs-analysis", label="needs analysis",
        reason=reason, today=today,
    )


def read_analysis(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest needs analysis; None when empty."""
    return _read_versioned_doc(
        base_dir, subdir=ANALYSIS_DIR, prefix="needs-analysis", label="needs analysis",
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
        base_dir, markdown_body, goal_id,
        subdir=RESEARCH_DIR, prefix="dossier", label="research dossier",
        reason=reason, today=today,
    )


def read_research_dossier(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest dossier; None when empty."""
    return _read_versioned_doc(
        base_dir, subdir=RESEARCH_DIR, prefix="dossier", label="research dossier",
        version=version,
    )
```

- [ ] **Step 4: Run the memory suite (new tests pass, program tests untouched and green)**

Run: `env -u VIRTUAL_ENV uv run pytest tests/memory -q`
Expected: PASS, including all of `test_store_programs.py` unmodified.

- [ ] **Step 5: Write the failing server tests**

Append to `tests/server/test_memory_tools.py` (the file's harness: `client` fixture =
in-process MCP session from `tests/server/conftest.py`, autouse `athlete_home` fixture
isolating `PERFORMANCE_AGENT_HOME`, async tests marked `@pytest.mark.anyio`):

```python
@pytest.mark.anyio
async def test_analysis_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_analysis", {"markdown_body": "# Needs analysis", "goal_id": "squat-160"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "analysis" / "needs-analysis-v1.md").exists()

    read_back = await client.call_tool("read_analysis", {})
    assert read_back.structuredContent["goal_id"] == "squat-160"
    assert read_back.structuredContent["body"] == "# Needs analysis"

    unreasoned = await client.call_tool(
        "save_analysis", {"markdown_body": "v2", "goal_id": "squat-160"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_research_dossier_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_research_dossier", {"markdown_body": "# Dossier", "goal_id": "squat-160"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "research" / "dossier-v1.md").exists()

    read_back = await client.call_tool("read_research_dossier", {})
    assert read_back.structuredContent["body"] == "# Dossier"

    unreasoned = await client.call_tool(
        "save_research_dossier", {"markdown_body": "v2", "goal_id": "squat-160"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_reading_unsaved_documents_errors_readably(client):
    analysis = await client.call_tool("read_analysis", {})
    assert analysis.isError
    assert "save_analysis" in analysis.content[0].text
    dossier = await client.call_tool("read_research_dossier", {})
    assert dossier.isError
    assert "save_research_dossier" in dossier.content[0].text
```

And extend the existing `test_memory_tools_are_listed` set with the four new names:

```python
        "save_analysis",
        "read_analysis",
        "save_research_dossier",
        "read_research_dossier",
```

- [ ] **Step 6: Run to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/server/test_memory_tools.py -q`
Expected: FAIL — `Unknown tool: save_analysis` (and the listed-tools assertion).

- [ ] **Step 7: Implement the MCP tools**

In `src/performance_agent/server/memory_tools.py`, rename the two program TypedDicts to
the generic family they now serve (replace, don't deprecate — grep first:
`grep -rn "ProgramSaved\|ProgramView" src/ tests/` to confirm they are only used here):

```python
class VersionedDocSaved(TypedDict):
    """Result of writing a new version of a versioned athlete document."""

    path: str
    version: int


class VersionedDocView(TypedDict):
    """A stored document version with its audit metadata."""

    version: int
    goal_id: str
    created_on: str
    reason: str | None
    body: str
```

Update `save_program`/`read_program` annotations to the new names, extract the shared
view builder, and add the four tools with honest docstrings:

```python
def _doc_view(result: tuple[dict[str, object], str] | None, missing_msg: str) -> VersionedDocView:
    if result is None:
        raise ValueError(missing_msg)
    frontmatter, body = result
    reason = frontmatter.get("reason")
    return VersionedDocView(
        version=int(str(frontmatter["version"])),
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(reason) if reason is not None else None,
        body=body,
    )


def save_analysis(markdown_body: str, goal_id: str, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT needs-analysis version (immutable audit trail).

    The needs analysis is the Analyst's output and the brief the Researcher and
    program builder receive: athlete summary, goal & feasibility verdict with
    its drivers, quality hierarchy, muscle/pattern priorities, injury flags,
    and research questions. Version 1 needs no reason; every revision (v2+)
    requires a reason stating what changed (new verdict, renegotiated goal).
    Existing versions are never overwritten.
    """
    path, version = store.save_analysis(resolve_athlete_dir(), markdown_body, goal_id, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_analysis(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) needs-analysis version.

    Raises a readable error when no analysis has been saved yet — run the
    needs-analysis skill (which ends with save_analysis) first.
    """
    return _doc_view(
        store.read_analysis(resolve_athlete_dir(), version),
        "no needs analysis has been saved yet; call save_analysis first",
    )


def save_research_dossier(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT research-dossier version (immutable audit trail).

    The dossier is the Researcher's output: per-facet synthesis with evidence
    grades, contradictions surfaced with both camps cited, confidence levels,
    and honest thin-evidence/degraded-coverage notes. Cite only corpus ids —
    every study it builds on must already be persisted via save_evidence.
    Version 1 needs no reason; re-research (v2+) requires a reason. Existing
    versions are never overwritten.
    """
    path, version = store.save_research_dossier(
        resolve_athlete_dir(), markdown_body, goal_id, reason
    )
    return VersionedDocSaved(path=str(path), version=version)


def read_research_dossier(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) research-dossier version.

    Raises a readable error when no dossier has been saved yet — run the
    deep-research skill (which ends with save_research_dossier) first.
    """
    return _doc_view(
        store.read_research_dossier(resolve_athlete_dir(), version),
        "no research dossier has been saved yet; call save_research_dossier first",
    )
```

Simplify `read_program` through the same helper:

```python
def read_program(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) program version.

    Raises a readable error if no program has been saved yet — call
    save_program first. Check read_athlete's program_version first: null
    there means nothing to read yet.
    """
    return _doc_view(
        store.read_program(resolve_athlete_dir(), version),
        "no program has been saved yet; call save_program first",
    )
```

Add the four to the `register()` tuple (after `read_program`): `save_analysis`,
`read_analysis`, `save_research_dossier`, `read_research_dossier`. Memory tools: 10 → 14.

- [ ] **Step 8: Run the server suite**

Run: `env -u VIRTUAL_ENV uv run pytest tests/server -q`
Expected: PASS.

- [ ] **Step 9: Update the documented tool counts**

`README.md` line 109 — current sentence: `You should see 41 tools. Then ask:` →

```
You should see 45 tools. Then ask:
```

`docs/installing.md` line ~205 — current sentence: `Ask your agent: *"List the
performance-agent tools."* You should see 41 tools (24 engine + 10 memory + 6 evidence
+ 1 report: assess_endurance_goal, read_athlete, ...)` →

```
Ask your agent: *"List the performance-agent tools."* You should see 45 tools (24
engine + 14 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).
```

- [ ] **Step 10: Lint, type-check, full-suite, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check && env -u VIRTUAL_ENV uv run pytest -q`
Expected: clean, all green (tests/skills included — no skill changed yet, and the four
new tools are additions, so the drift guard stays green).

```bash
git add src/performance_agent/memory/store.py src/performance_agent/server/memory_tools.py \
        tests/memory/test_store_documents.py tests/server/test_memory_tools.py \
        README.md docs/installing.md
git commit -m "Add versioned needs-analysis and research-dossier stores and tools"
```

---

### Task 2: l'Entretien — rework `skills/athlete-onboarding/SKILL.md`

Keep the one-question-at-a-time discipline and the existing step skeleton; add the
multi-lift 1RM inventory (tested or estimated via `estimate_1rm`), body_fat_pct
(never demanded — sensitive), calendar_type with plain-language probes,
split_preferences, and the `weight_kg` (profile static fact) vs `bodyweight_kg`
(check-in time series) mapping rule flagged in the backlog.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Modify: `skills/athlete-onboarding/SKILL.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`, replace `test_onboarding_skill_protocol` with:

```python
def test_onboarding_skill_protocol(skills):
    onboarding = next(s for s in skills if s.frontmatter["name"] == "athlete-onboarding")
    body = onboarding.body.casefold()
    for needle in (
        "write_profile",
        "upsert_goal",
        "one question",
        "equipment",
        "injur",
        "lift_inventory",
        "estimate_1rm",
        "calendar_type",
        "body_fat_pct",
        "bodyweight_kg",
        "split_preferences",
    ):
        assert needle in body, f"onboarding skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL on `lift_inventory` (and the other new needles).

- [ ] **Step 3: Write the reworked skill**

Replace `skills/athlete-onboarding/SKILL.md` entirely with:

```markdown
---
name: athlete-onboarding
description: Use when the athlete profile is empty or missing key facts. Runs the
  structured intake questionnaire and persists everything through the memory tools.
tools: [read_athlete, write_profile, upsert_goal, log_session, estimate_1rm]
---

# Athlete Onboarding — l'Entretien

Collect the athlete's structured facts conversationally and persist them. Follow the
performance-coach skill's global rules (language, honesty, safety). Start by calling
`read_athlete` — never re-ask for facts already on file; only fill the gaps.

## Protocol

Ask ONE question at a time — this is a conversation, not a form. Adapt follow-ups to
the answers. If they decline a question, note it as unknown and move on — don't
insist more than once. Collect, in this order:

1. **Language** (en/fr/es) — first question, then switch to it immediately.
2. **Mode** — one-shot program (Mode A) or ongoing coaching (Mode B)? Explain the
   difference in one sentence each.
3. **Identity & biometrics** — name (optional), birth date, sex, height, weight.
   Weight goes to profile.weight_kg — the STATIC profile fact. Later weigh-ins are a
   time series recorded as bodyweight_kg on check-ins, never by rewriting the
   profile; downstream skills read the trend from check-ins and the baseline from
   the profile. If they happen to know their body-fat percentage, record
   body_fat_pct — but this is sensitive: never demand it, never suggest measuring
   it, accept "no idea" instantly and move on.
4. **Sport & history** — main sport, discipline, competition level, years of
   structured training (maps to training_age: beginner < 2y structured, intermediate
   2-5y, advanced > 5y — state your mapping when you write it).
5. **Performance inventory** — the benchmarks the needs analysis will require.
   - Strength or mixed-sport athletes: build the multi-lift 1RM inventory
     (profile.lift_inventory), one lift at a time, for the lifts relevant to the
     goal (typically squat, bench, deadlift, plus sport-specific lifts). Per lift:
     a tested 1RM → record with source "tested" and its date; only a recent heavy
     set (e.g. "5 reps at 100 kg with 2 in reserve")? → convert via `estimate_1rm`
     and record with source "estimated" — always tell the athlete you estimated it.
   - Endurance athletes: recent race times over the relevant distances.
6. **Goal** — objective, target metric and value, deadline, priority. Also confirm
   the CURRENT benchmark from step 5 that matches it — the assessment needs it.
7. **Calendar type** — profile.calendar_type, one of single_deadline (one race or
   meet date), recurring_fixtures (weekly matches), open_ended (no fixed date). It
   drives the periodization model later, so probe in plain language — e.g. in
   French: "une compétition précise, des matchs chaque semaine, ou pas
   d'échéance ?"
8. **Environment** — equipment (be concrete: barbell? rack? treadmill? track
   access?), sessions per week, minutes per session, and split_preferences (e.g.
   "upper/lower", "full body", "push/pull/legs" — scheduling quirks go to notes).
9. **Injuries & flags** — current or recent injuries, pain, medical constraints.
   Anything active: call `write_profile` immediately with the flag (don't wait for
   the batch), then continue, applying the red-flag rules from performance-coach.
10. **Preferences** — anything they hate/love, schedule quirks → profile notes.

## Persistence rules

- After steps 3-5, 7-8, and 10: call `write_profile` with the FULL updated profile
  (read first — it is a whole-document replace; omitted fields are dropped,
  including lift_inventory, body_fat_pct, calendar_type, split_preferences).
  Step 9 flags were already written immediately, per the protocol.
- After step 6: `upsert_goal` (id: short kebab slug, e.g. sub-45-10k). If the goal
  is later renegotiated during the needs analysis, that skill REUSES this same goal
  id so the milestone overwrites the raw ask — never leave an unassessed original
  goal active.
- If they mention recent training sessions, offer to `log_session` them — history
  improves everything downstream (strength sessions with structured exercises →
  sets {reps, load_kg, rir} when they can recall them).
- Timestamps are naive local wall-clock time; dates ISO (YYYY-MM-DD).

## Exit

Summarize what you stored (quote the profile back briefly), then route: new goal →
needs-analysis. Never skip the needs analysis on the way to a program.
```

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — the five declared tools all appear in the body, and the body names
no undeclared server tool (watch: write "check-ins", never the tool name for logging
them, which this skill does not declare).

- [ ] **Step 5: Commit**

```bash
git add skills/athlete-onboarding/SKILL.md tests/skills/test_structure.py
git commit -m "Extend onboarding with lift inventory, calendar type and body comp"
```

---

### Task 3: l'Analyste — `skills/needs-analysis/` replaces `skills/goal-assessment/`

Replace, don't deprecate: the old directory is deleted, and every reference to
goal-assessment in other skills is updated (grep first). The new skill keeps
goal-assessment's good patterns (deadline crash-guard, verdict bands, counter-proposal
loop reusing the goal id) and generalizes them across all four feasibility tools, adds
the needs analysis proper, and ends by writing the versioned document via
`save_analysis`.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/needs-analysis/SKILL.md`
- Delete: `skills/goal-assessment/` (git rm)
- Modify: `skills/program-adaptation/SKILL.md` (two routing references)

- [ ] **Step 1: Update the harness first (failing)**

In `tests/skills/test_structure.py`: in `EXPECTED_SKILLS`, replace `"goal-assessment"`
with `"needs-analysis"`. Replace `test_assessment_skill_protocol` with:

```python
def test_needs_analysis_skill_protocol(skills):
    analysis = next(s for s in skills if s.frontmatter["name"] == "needs-analysis")
    body = analysis.body.casefold()
    for needle in (
        "assess_endurance_goal",
        "assess_strength_goal",
        "assess_hypertrophy_goal",
        "assess_bodycomp_goal",
        "estimate_1rm",
        "drivers",
        "counter-proposal",
        "honest",
        "save_analysis",
        "research questions",
    ):
        assert needle in body, f"needs-analysis skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch.

- [ ] **Step 3: Write the new skill, delete the old one**

```bash
git rm -r skills/goal-assessment
mkdir -p skills/needs-analysis
```

Create `skills/needs-analysis/SKILL.md`:

```markdown
---
name: needs-analysis
description: Use whenever a goal is new, changed, or has never been analyzed.
  Translates discipline and goal into a needs analysis (priority muscles and
  patterns, quality hierarchy, energy systems, injury risks), renders the honest
  feasibility verdict with its drivers, negotiates realistic alternatives, and
  saves the versioned analysis document.
tools: [read_athlete, get_time_context, assess_endurance_goal, assess_strength_goal,
        assess_hypertrophy_goal, assess_bodycomp_goal, predict_race_time,
        estimate_1rm, upsert_goal, search_evidence, search_evidence_live,
        save_evidence, verify_reference, check_citations, save_analysis]
---

# Needs Analysis — l'Analyste

The product's signature moment: what this goal actually demands, and whether it is
reachable — honestly. Follow performance-coach global rules. Profile facts
(training_age, lift_inventory, body_fat_pct, calendar_type, benchmarks) come from
`read_athlete`.

## 1. The needs analysis

From the athlete's discipline and goal, work out and write down:

- **Priority muscle groups and movement patterns** — what this sport/goal loads,
  ranked (e.g. a 100 m sprinter: hip extensors, hamstrings, triple extension).
- **Target qualities with hierarchy** — strength, power, explosiveness, endurance,
  hypertrophy, or mixed — ranked: what is trained first and why. Mixed-sport
  profiles get an explicit split ("power primary, aerobic base secondary").
- **Energy-system demands** — which systems the sport taxes and in what proportion.
- **Sport-typical injury risks** — the patterns this population tends to break,
  cross-checked against the athlete's own injury history.

Every claim is either cited (corpus id via `search_evidence`; run
`search_evidence_live` for what the corpus lacks and `save_evidence` the keepers —
any web-found locator passes `verify_reference` first) or explicitly labeled
coaching judgment. Never a memory citation. Exhaustive research is NOT this skill's
job — le Chercheur (deep-research) runs next; here you cite what you assert and
write down the research questions he will chase.

## 2. The feasibility verdict — the honest number

Pick the tool that matches the goal type; numbers come from the tool only:

- Endurance time goal → `assess_endurance_goal` (current time, target time over the
  same distance, whole weeks, training_age).
- 1RM strength goal → `assess_strength_goal` (current and target 1RM for the SAME
  lift, from lift_inventory).
- Lean-mass gain → `assess_hypertrophy_goal` (target kg, weeks, training_age).
- Fat loss / recomposition → `assess_bodycomp_goal` (weight, current & target
  body-fat %, weeks, sex). It REFUSES unsafe targets with a referral — relay the
  refusal, never work around it; exceeds_safe_rate=True must be said out loud.
- Mixed goals: assess each measurable component separately and say which component
  carries which verdict.

Missing inputs come first:
- No deadline on file? Ask for one BEFORE calling any feasibility tool — they
  require whole-number weeks and error without them (quote `get_time_context` for
  the count). No fixed date? Have the athlete pick a working horizon.
- No current benchmark? Get one (a recent race, a test this week) — or derive a
  conservative estimate and say you did: `predict_race_time` from a race at another
  distance, `estimate_1rm` from a recent heavy set.

Present ALL of it, in the athlete's language: probability as a percentage,
improvement_needed, and the drivers — required vs achievable rate. Verdict bands
(state which one applies and why):

- ≥ 70%: realistic — proceed.
- 30% to <70%: ambitious — proceed, but name the risks and the checkpoints.
- < 30%: be honest that it is unrealistic in the timeframe. NEVER let a program be
  built on a goal you believe will fail silently.

**Counter-proposal loop** (< 30%): propose an adjusted target and/or timeline,
re-run the SAME feasibility tool on it, show the new probability, and iterate until
you both accept. Then `upsert_goal` the negotiated milestone REUSING the original
goal's id (it overwrites the raw ask) and note the original ask inline in the
statement (e.g. "sub-45 10k — originally sub-40, renegotiated after a <30%
verdict"). Never upsert the infeasible original as-is.

## 3. Write the needs-analysis document

Once the goal is accepted (and recorded via `upsert_goal`), run `check_citations`
over your draft — fix anything flagged — then call `save_analysis` (markdown body;
goal_id; v1 needs no reason, revisions require one). Structure:

1. **Athlete summary** — the facts the analysis rests on (age, training_age, sport,
   benchmarks, calendar_type, constraints).
2. **Goal & verdict** — probability, band, drivers, and the negotiation trail if any.
3. **Quality hierarchy** — target qualities ranked, with rationale.
4. **Muscle & pattern priorities** — ranked, with rationale.
5. **Injury flags** — sport-typical risks plus the athlete's own history.
6. **Research questions for le Chercheur** — the specific questions deep research
   must answer: periodization for this calendar_type, dose-response for these
   qualities, exercise selection for these priorities, population specifics.

Quote the saved version and path back to the athlete.

## 4. Route onward

Accepted goal + saved analysis → deep-research (le Chercheur reads the document you
just saved). Goal abandoned or postponed → update it via `upsert_goal` (status) and
hand back to performance-coach.
```

- [ ] **Step 4: Sweep the goal-assessment references**

`grep -rn "goal-assessment" skills/ README.md docs/installing.md` — expected hits and
fixes (README's mermaid/changelog are handled in Task 5):

In `skills/program-adaptation/SKILL.md`:
- `weeks); route to goal-assessment to renegotiate the deadline first.` →
  `weeks); route to needs-analysis to renegotiate the deadline first.`
- `(deload), extend the timeline, re-negotiate the goal (route back to goal-assessment` →
  `(deload), extend the timeline, re-negotiate the goal (route back to needs-analysis`

(`athlete-onboarding` was already re-pointed in Task 2; `performance-coach` is Task 5.)

- [ ] **Step 5: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: `test_structure.py` and `test_tool_references.py` pass for needs-analysis.
`performance-coach` still routes to "goal-assessment" until Task 5 — that is prose,
not a tool name, so the harness stays green; the routing is fixed in Task 5.

- [ ] **Step 6: Commit**

```bash
git add -A skills/needs-analysis skills/goal-assessment skills/program-adaptation/SKILL.md \
        tests/skills/test_structure.py
git commit -m "Replace goal-assessment with the needs-analysis skill"
```

---

### Task 4: le Chercheur — new `skills/deep-research/SKILL.md`

The core of the premium promise (spec §5, agent side): read the needs analysis,
decompose into facets, fan out multilingual filtered queries, loop until covered,
persist everything with the registry's canonical title, synthesize
contradiction-aware, save the versioned dossier.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/deep-research/SKILL.md`

- [ ] **Step 1: Update the harness first (failing)**

In `tests/skills/test_structure.py`: add `"deep-research"` to `EXPECTED_SKILLS` and
append:

```python
def test_research_skill_protocol(skills):
    research = next(s for s in skills if s.frontmatter["name"] == "deep-research")
    body = research.body.casefold()
    for needle in (
        "read_analysis",
        "search_evidence_live",
        "save_evidence",
        "save_research_dossier",
        "facet",
        "coverage",
        "canonical",
        "contradiction",
        "thin evidence",
        "failed",
    ):
        assert needle in body, f"deep-research skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch.

- [ ] **Step 3: Write the skill**

Create `skills/deep-research/SKILL.md`:

```markdown
---
name: deep-research
description: Use after a needs analysis has been saved and its goal accepted. Runs
  the deep, multilingual, multi-wave literature search personalized to THIS
  athlete, persists every verified study to the corpus, and writes the
  contradiction-aware research dossier the program will be built on.
tools: [read_athlete, read_analysis, search_evidence, search_evidence_live,
        save_evidence, verify_reference, check_citations, save_research_dossier]
---

# Deep Research — le Chercheur

The core of the premium promise: dozens of queries, several languages, minutes of
work, run live for this athlete — never a single shallow pass. Follow
performance-coach global rules. Narrate progress as you go ("wave 2 — periodization
facet still thin") — the athlete should see the work.

## 1. Read the brief

Call `read_analysis` (latest version) — the needs analysis IS your brief: quality
hierarchy, muscle/pattern priorities, injury flags, and its explicit research
questions. If it errors (nothing saved yet), stop and route back to needs-analysis;
never research without a brief. `read_athlete` for the population facts (age, sex,
training_age, sport) you will condition queries on.

## 2. Facet decomposition

Decompose the brief into a written facet list — the coverage loop scores against
it. At minimum:

- **Periodization × calendar** — the model fitting the athlete's calendar_type
  (block toward a single deadline, undulating, in-season around fixtures).
- **Dose-response per target quality** — volume, intensity, frequency for each
  quality in the hierarchy.
- **Exercise selection per priority muscle/pattern** — under the athlete's
  equipment and injury constraints.
- **Population specifics** — age, sex, training age, sport.

Add one facet per research question the analysis lists.

## 3. Fan-out

Per facet: check the corpus first (`search_evidence`), then run
`search_evidence_live` with 3-5 distinct queries (synonyms, competing
terminologies), each carrying a language_terms dict translated into several
languages (en, fr, es, de, pt, ru, it, zh, … — skip any you cannot translate
confidently). Use the filters: prefer publication_types ["meta_analysis",
"systematic_review"] on a first pass, widen to "rct" or no filter when a facet is
thin; use year_from for fast-moving questions. Candidates arrive evidence-tier
ordered (meta-analyses → reviews → RCTs → the rest, most recent first within a
tier) and PubMed candidates carry full abstracts — read them before grading.

## 4. Coverage loop — never one pass

After each wave, go through the facet list and mark each facet covered (at least
two independent relevant sources, ideally including a meta-analysis or review) or
thin. For every thin facet: reformulate (different terminology, adjacent
population, broader question), drop filters, add languages, relaunch. Repeat until
every facet is covered or reformulations are honestly exhausted. A facet abandoned
while thin is recorded as thin in the dossier — never silently dropped.

## 5. Persist everything you keep

Every retained study is saved via `save_evidence` — the dossier may only cite
corpus ids. Rules:

- Save under the REGISTRY'S CANONICAL TITLE exactly as verification returned it —
  translated or paraphrased titles are rejected by design (title cross-check).
- suggested_study_type set → use it as-is, never upgrade. Null → read the abstract
  and propose a conservative study_type and 1-2 sentence conclusions — never a
  figure absent from the abstract. The grading ceiling is enforced server-side.
- Locators found outside the live search (web results, reference lists) MUST pass
  `verify_reference` before `save_evidence` — never propose an unverified entry.
- Reference books enter by ISBN (`verify_reference` with isbn; study_type
  reference_book) and are capped at expert opinion — good for exercise-technique
  and pedagogy prose. When a book makes a measurable claim, trace it to the primary
  studies and cite those, not the book.

## 6. Contradiction-aware synthesis

Write the dossier, one section per facet:

- **What converges** — the consensus, with corpus ids and stars.
- **What disagrees** — both camps cited; never present one side of a live dispute.
- **Confidence** — high / moderate / low, driven by evidence tier and consistency.
- **Thin facets, said plainly** — "thin evidence — recommendation will be coaching
  judgment", plus what was tried.
- **Degraded coverage** — name every failed source/language pair the live search
  reported; never imply full coverage after partial failures.

## 7. Save and hand off

Run `check_citations` over the full dossier text; fix anything flagged. Then
`save_research_dossier` (markdown body; goal_id; v1 needs no reason, re-research
requires one). Quote the saved version and path, summarize coverage (facets
covered vs thin, studies saved, languages searched), then route onward: dossier
saved → program-generation.
```

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — all eight declared tools appear in the body; no undeclared server
tool is namedropped; no ISBN/DOI digits appear in the prose (anti-fabrication).

- [ ] **Step 5: Commit**

```bash
git add skills/deep-research/SKILL.md tests/skills/test_structure.py
git commit -m "Add the deep-research skill (le Chercheur protocol)"
```

---

### Task 5: le Coach d'accueil — routing + program-generation dossier handoff + README

Route the coach onto the pipeline that now exists (Entretien → Analyste → Chercheur →
program-generation; the Planificateur/Optimiseur split is phase 5 — route names must
only reference skills that EXIST). program-generation now RECEIVES the dossier via
`read_research_dossier` instead of doing its own from-scratch search, keeping its own
search as the explicit fallback when no dossier exists.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Modify: `skills/performance-coach/SKILL.md`
- Modify: `skills/program-generation/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`, add `"read_research_dossier"` to the
`test_generation_skill_protocol` needles, and add `"needs-analysis"` and
`"deep-research"` to the `test_coach_skill_carries_the_global_rules` needles (the
coach must route to skills that exist).

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL on the new needles.

- [ ] **Step 2: Update performance-coach routing**

In `skills/performance-coach/SKILL.md`, replace the `## Routing` section with:

```markdown
## Routing

At session start:

- Empty/incomplete profile → athlete-onboarding
- New or changed goal → needs-analysis (ALWAYS analyze and assess before generating)
- Returning athlete with a program → training-checkin
- Goal analyzed and accepted, but no research dossier → deep-research
- Analysis and dossier done, but no saved program → program-generation

After a skill hands back:

- Accepted goal, no dossier → deep-research
- Dossier saved, no program → program-generation
- Check-in shows poor adherence, plateau, pain, or schedule change → program-adaptation

Re-evaluate routing after each skill completes.
```

And replace the `## Modes` section with:

```markdown
## Modes

- Mode A (one-shot): onboarding → needs analysis → deep research → generation →
  deliver. Still save everything through the memory tools.
- Mode B (ongoing coach): all of Mode A plus check-ins and adaptation over time.
```

(The frontmatter `tools:` list is unchanged — routing names are skill names, not tools.)

- [ ] **Step 3: Update program-generation's evidence-pack section**

In `skills/program-generation/SKILL.md`, add `read_research_dossier` to the
frontmatter `tools:` list (after `check_citations`), and replace the whole
`## 1. Evidence pack` section with:

```markdown
## 1. Evidence pack

le Chercheur (deep-research) normally ran before you: call `read_research_dossier`
and build on its per-facet synthesis. The studies it retained are already in the
corpus — `search_evidence` returns them by id; render the full citation string for
any id you plan to quote with `get_citation`. Respect the dossier's stated
confidence levels and contradictions: a facet it marked "thin evidence — coaching
judgment" stays coaching judgment in the program, and where it shows a live
disagreement, say which camp the program follows and why.

**Fallback — no dossier exists** (`read_research_dossier` errors: legacy athlete,
or the athlete explicitly declined the deep research): build your own evidence
pack. Query `search_evidence` (in ENGLISH, whatever the athlete's language) for the
goal's key training questions — e.g. for a 10K goal: strength training and running
economy, interval vs continuous work, tapering; for barbell strength: volume and
frequency dose-response, progression models. If a question returns nothing, run
`search_evidence_live` with translated `language_terms` (en, fr, es, de, ru, no,
sv, it, zh) before concluding the corpus has no entry. Classify and `save_evidence`
any verified candidate worth citing — `suggested_study_type` if set, otherwise your
own abstract-based proposal (grading ceiling still enforced). Still nothing? Fall
back to a web search per language, `verify_reference` anything with a locator
before proposing `save_evidence`, and if that also comes up empty, label that part
of the plan as coaching judgment rather than force a citation.
```

- [ ] **Step 4: Update README's skill mentions**

In `README.md`:

- Mermaid node (line ~195): replace
  `H -.follows.-> SK[Coaching skills<br/>onboarding · assessment · program generation ·`
  `personalization · check-ins · adaptation]` with
  `H -.follows.-> SK[Coaching skills<br/>onboarding · needs analysis · deep research ·`
  `program generation · check-ins · adaptation]`
- Changelog bullet (line ~233): replace the "Six coaching skills …" bullet with:

```markdown
- ✅ Eight coaching skills (Claude Code plugin format): session rituals, onboarding
  with a multi-lift 1RM inventory, needs analysis with honest multi-goal feasibility
  verdicts and counter-proposals, deep multilingual research dossiers, evidence-cited
  program generation, structured check-ins, versioned adaptation — each eval-guarded
  against tool drift and fabricated references
```

- [ ] **Step 5: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — including `test_bodies_do_not_reference_undeclared_tools` for
program-generation (it now both declares and uses `read_research_dossier`).

- [ ] **Step 6: Commit**

```bash
git add skills/performance-coach/SKILL.md skills/program-generation/SKILL.md \
        README.md tests/skills/test_structure.py
git commit -m "Route the coach through needs-analysis and deep-research"
```

---

### Task 6: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Full test suite**

Run: `env -u VIRTUAL_ENV uv run pytest -q`
Expected: all green — memory, server, skills harness (structure, tool-drift both
directions, anti-fabrication), engine, evidence, reports, packaging.

- [ ] **Step 2: Zero-warning gate**

Run: `env -u VIRTUAL_ENV uv run ruff format --check . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`
Expected: clean output, no warnings.

- [ ] **Step 3: Residual reference check**

Run: `grep -rn "goal-assessment" README.md docs/installing.md skills/ tests/ src/`
Expected: no hits outside `docs/superpowers/` history (specs/plans/backlog are records
and stay as written). Also confirm `docs/installing.md`'s skills install step needs no
change: it copies `skills/*` wholesale (`cp -R Performance-agent/skills/* ~/.claude/skills/`),
so the new directories ride along and the deleted one simply stops shipping — verify
the surrounding prose doesn't enumerate skill names (it doesn't today).

- [ ] **Step 4: Skill line budget**

Run: `wc -l skills/*/SKILL.md`
Expected: every skill under ~150 lines.

- [ ] **Step 5: Commit any stragglers**

```bash
git status --short
```

Expected: clean tree. If formatting touched files:

```bash
git add -A && git commit -m "Apply formatting"
```
