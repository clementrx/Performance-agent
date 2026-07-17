# Living Evidence & Weekly Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four features of `docs/superpowers/specs/2026-07-17-evidence-loop-weekly-followup-design.md`: the athlete `documentation/` folder with two lanes, science in the HTML deliverable, the deterministic weekly loads review, the program-watch audit skill, and the research mini-waves (skills-only).

**Architecture:** Engine stays pure (new `engine/progression.py`), file I/O lives in `memory/` (new `documents.py`, `weekly_review.py`, store additions), MCP wrappers in `server/` (two new modules), rendering in `programs/`. Citation resolution happens server-side so the store keeps zero evidence dependencies. Skills change last, with `tests/skills` invariants updated in the same task.

**Tech Stack:** Python 3.13, uv, pydantic v2, FastMCP, pytest. Run everything with `uv run`.

**Branch:** work continues on `evidence-loop-weekly-followup-spec` (spec already committed). Version bump/release is NOT part of this plan (single release at the end, separately).

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/performance_agent/memory/documents.py` | create | Documentation folder: README, registry schema, scan, mark |
| `src/performance_agent/server/document_tools.py` | create | MCP tools `list_athlete_documents`, `mark_document_processed` |
| `src/performance_agent/engine/progression.py` | create | Pure next-load math for each ProgressionRule kind |
| `src/performance_agent/memory/weekly_review.py` | create | Read program+logs, match week, dispatch rules, state file |
| `src/performance_agent/server/followup_tools.py` | create | MCP tools `suggest_next_week_loads`, `save_watch_report` |
| `src/performance_agent/memory/schemas.py` | modify | `ProgressionRule`, `ExerciseBlock.progression`, `Guidance`, `ProgramPlan.advice/rationale` |
| `src/performance_agent/memory/store.py` | modify | `write_profile` hook, watch report versioned doc, citations param on `save_program` |
| `src/performance_agent/engine/diligence.py` | modify | Facts + `loads_review` / `program_watch` due actions |
| `src/performance_agent/memory/diligence.py` | modify | Extract the new facts from files |
| `src/performance_agent/evidence/citations.py` | modify | `ResolvedCitation`, `resolve_citations` |
| `src/performance_agent/programs/render.py` | modify | `plan_citation_ids`, advice/rationale/Sources sections |
| `src/performance_agent/programs/render_html.py` | modify | Banner, `[n]` markers, bibliography, labels, CSS |
| `src/performance_agent/server/memory_tools.py` | modify | Wire citations into `save_program` + `_write_program_html` |
| `src/performance_agent/server/app.py` | modify | Register the two new tool modules |
| `skills/next-week-loads/SKILL.md` | create | Weekly loads review ritual |
| `skills/program-watch/SKILL.md` | create | Per-exercise program audit |
| 7 existing `skills/*/SKILL.md` | modify | Documents step 0, mini-waves, routing, structured progression |
| `tests/skills/test_structure.py` | modify | EXPECTED_SKILLS + 2 protocol tests |
| `README.md` | modify | Tool count and feature bullets |

---

## Phase 1 — Athlete documentation folder

### Task 1: `memory/documents.py` — registry schema, scan, mark

**Files:**
- Create: `src/performance_agent/memory/documents.py`
- Test: `tests/memory/test_documents.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_documents.py`:

```python
"""Documentation folder: registry, scan states, mark validation."""

from datetime import date

import pytest

from performance_agent.memory.documents import (
    DOCUMENTATION_DIR,
    README_FILE,
    REGISTRY_FILE,
    ensure_documentation_dir,
    load_registry,
    mark_processed,
    scan_documents,
)

TODAY = date(2026, 7, 17)


def _drop(base, name, content=b"pdf-bytes"):
    doc_dir = base / DOCUMENTATION_DIR
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / name).write_bytes(content)


def test_ensure_creates_folder_and_readme(tmp_path):
    path = ensure_documentation_dir(tmp_path)
    assert path == tmp_path / DOCUMENTATION_DIR
    assert path.is_dir()
    readme = path / README_FILE
    assert readme.exists()
    assert "documentation" in readme.read_text(encoding="utf-8").casefold()


def test_ensure_is_idempotent_and_keeps_readme_edits(tmp_path):
    readme = ensure_documentation_dir(tmp_path) / README_FILE
    readme.write_text("custom", encoding="utf-8")
    ensure_documentation_dir(tmp_path)
    assert readme.read_text(encoding="utf-8") == "custom"


def test_scan_reports_new_files_and_excludes_registry_and_readme(tmp_path):
    ensure_documentation_dir(tmp_path)
    _drop(tmp_path, "study.pdf")
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["new"]] == ["study.pdf"]
    assert result["modified"] == []
    assert result["processed"] == []
    assert result["removed"] == []
    assert result["unreadable"] == []


def test_mark_then_scan_reports_processed_with_summary(tmp_path):
    _drop(tmp_path, "study.pdf")
    record = mark_processed(
        tmp_path,
        "study.pdf",
        lane="evidence",
        summary="Creatine meta-analysis.",
        evidence_ids=["creatine-2017"],
        known_evidence_ids={"creatine-2017"},
        today=TODAY,
    )
    assert record.lane == "evidence"
    result = scan_documents(tmp_path)
    assert result["new"] == []
    assert result["processed"][0]["summary"] == "Creatine meta-analysis."


def test_modified_file_is_reported_for_reprocessing(tmp_path):
    _drop(tmp_path, "study.pdf")
    mark_processed(
        tmp_path, "study.pdf", lane="context", summary="v1",
        known_evidence_ids=set(), today=TODAY,
    )
    _drop(tmp_path, "study.pdf", content=b"changed-bytes")
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["modified"]] == ["study.pdf"]


def test_removed_is_derived_not_stored(tmp_path):
    _drop(tmp_path, "study.pdf")
    mark_processed(
        tmp_path, "study.pdf", lane="context", summary="s",
        known_evidence_ids=set(), today=TODAY,
    )
    (tmp_path / DOCUMENTATION_DIR / "study.pdf").unlink()
    result = scan_documents(tmp_path)
    assert result["removed"] == ["study.pdf"]
    stored = load_registry(tmp_path)
    assert [r.filename for r in stored.documents] == ["study.pdf"]


def test_unreadable_lane_needs_no_summary(tmp_path):
    _drop(tmp_path, "corrupt.pdf")
    record = mark_processed(
        tmp_path, "corrupt.pdf", lane="unreadable",
        known_evidence_ids=set(), today=TODAY,
    )
    assert record.summary is None
    assert scan_documents(tmp_path)["unreadable"][0]["filename"] == "corrupt.pdf"


def test_mark_unknown_file_fails(tmp_path):
    ensure_documentation_dir(tmp_path)
    with pytest.raises(ValueError, match="ghost.pdf"):
        mark_processed(
            tmp_path, "ghost.pdf", lane="context", summary="s",
            known_evidence_ids=set(), today=TODAY,
        )


def test_mark_evidence_or_context_requires_summary(tmp_path):
    _drop(tmp_path, "study.pdf")
    with pytest.raises(ValueError, match="summary"):
        mark_processed(
            tmp_path, "study.pdf", lane="evidence",
            known_evidence_ids=set(), today=TODAY,
        )


def test_mark_rejects_unknown_evidence_id(tmp_path):
    _drop(tmp_path, "study.pdf")
    with pytest.raises(ValueError, match="phantom-id"):
        mark_processed(
            tmp_path, "study.pdf", lane="evidence", summary="s",
            evidence_ids=["phantom-id"], known_evidence_ids={"other"}, today=TODAY,
        )


def test_corrupt_registry_is_rebuilt_empty(tmp_path):
    _drop(tmp_path, "study.pdf")
    (tmp_path / DOCUMENTATION_DIR / REGISTRY_FILE).write_text(
        "not: [valid", encoding="utf-8"
    )
    result = scan_documents(tmp_path)
    assert [item["filename"] for item in result["new"]] == ["study.pdf"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memory/test_documents.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'performance_agent.memory.documents'`

- [x] **Step 3: Write the implementation**

Create `src/performance_agent/memory/documents.py`:

```python
"""Athlete-dropped documents: folder bootstrap, registry, scan, mark.

The athlete drops files (studies, physio reports, past programs) into
documentation/; the agent detects new/changed files by content hash and records
what it did with each one. Only `processed` and `unreadable` are stored —
`new`, `modified` and `removed` are derived at scan time. The registry is
reconstructible by design: a deleted or corrupt index.yaml simply makes files
show up as new again (corpus entries are verified independently and survive).
"""

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Literal, Self, TypedDict

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DOCUMENTATION_DIR = "documentation"
REGISTRY_FILE = "index.yaml"
README_FILE = "README.md"
_EXCLUDED_FILES = {REGISTRY_FILE, README_FILE}

_README_CONTENT = """\
# Documentation

EN — Drop documents for your coach here: published studies (PDF), physio or
medical reports you want considered, lab test results, past training programs.
New and changed files are picked up automatically. A study whose DOI/PMID can
be verified joins the evidence corpus; everything else informs your coaching
as context but is never presented as science.

FR — Déposez ici les documents pour votre coach : études publiées (PDF),
bilans kiné/médicaux à partager, résultats de tests, anciens programmes.
Les fichiers nouveaux ou modifiés sont détectés automatiquement. Une étude
dont le DOI/PMID est vérifiable rejoint le corpus scientifique ; tout le
reste nourrit le coaching comme contexte, jamais présenté comme de la science.
"""

Lane = Literal["evidence", "context", "unreadable"]


class DocumentRecord(BaseModel):
    """One processed (or unreadable) dropped file, keyed by filename."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    first_seen: date
    processed_on: date
    lane: Lane
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _summary_required_unless_unreadable(self) -> Self:
        if self.lane != "unreadable" and not self.summary:
            msg = f"{self.filename}: a summary is required for lane {self.lane!r}"
            raise ValueError(msg)
        return self


class DocumentRegistry(BaseModel):
    """The whole documentation/index.yaml file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    documents: list[DocumentRecord] = Field(default_factory=list)


class DocumentView(TypedDict):
    """A file awaiting processing (new or modified)."""

    filename: str
    path: str
    size_bytes: int


class ProcessedView(TypedDict):
    """A file the agent already handled, with what it retained."""

    filename: str
    path: str
    lane: str
    summary: str | None


class ScanResult(TypedDict):
    """Derived folder state: only processed/unreadable are stored on disk."""

    path: str
    new: list[DocumentView]
    modified: list[DocumentView]
    processed: list[ProcessedView]
    removed: list[str]
    unreadable: list[ProcessedView]


def documentation_dir(base_dir: Path) -> Path:
    """Return the documentation folder path (never creates it)."""
    return base_dir / DOCUMENTATION_DIR


def ensure_documentation_dir(base_dir: Path) -> Path:
    """Create the folder and its README when missing; never overwrites."""
    doc_dir = documentation_dir(base_dir)
    doc_dir.mkdir(parents=True, exist_ok=True)
    readme = doc_dir / README_FILE
    if not readme.exists():
        readme.write_text(_README_CONTENT, encoding="utf-8")
    return doc_dir


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry(base_dir: Path) -> DocumentRegistry:
    """Load the registry; a missing or corrupt file yields an empty registry."""
    path = documentation_dir(base_dir) / REGISTRY_FILE
    if not path.exists():
        return DocumentRegistry()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return DocumentRegistry.model_validate(raw or {})
    except (yaml.YAMLError, ValidationError):
        return DocumentRegistry()


def _save_registry(base_dir: Path, registry: DocumentRegistry) -> None:
    path = documentation_dir(base_dir) / REGISTRY_FILE
    _atomic_write(
        path,
        yaml.safe_dump(registry.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
    )


def scan_documents(base_dir: Path) -> ScanResult:
    """Compare the folder against the registry; derives new/modified/removed."""
    doc_dir = ensure_documentation_dir(base_dir)
    registry = load_registry(base_dir)
    records = {record.filename: record for record in registry.documents}
    present = {
        path.name: path
        for path in sorted(doc_dir.iterdir())
        if path.is_file() and path.name not in _EXCLUDED_FILES
    }
    result = ScanResult(
        path=str(doc_dir), new=[], modified=[], processed=[], removed=[], unreadable=[]
    )
    for name, path in present.items():
        view = DocumentView(filename=name, path=str(path), size_bytes=path.stat().st_size)
        record = records.get(name)
        if record is None:
            result["new"].append(view)
        elif record.sha256 != _sha256(path):
            result["modified"].append(view)
        else:
            processed = ProcessedView(
                filename=name, path=str(path), lane=record.lane, summary=record.summary
            )
            if record.lane == "unreadable":
                result["unreadable"].append(processed)
            else:
                result["processed"].append(processed)
    result["removed"] = sorted(set(records) - set(present))
    return result


def mark_processed(  # noqa: PLR0913 -- one keyword per registry field, all named
    base_dir: Path,
    filename: str,
    *,
    lane: Lane,
    summary: str | None = None,
    key_points: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    known_evidence_ids: set[str],
    today: date | None = None,
) -> DocumentRecord:
    """Record the outcome for one file; replaces any previous record.

    known_evidence_ids must cover the whole corpus (packaged + personal); the
    caller builds it so this module never depends on the evidence package.
    """
    path = documentation_dir(base_dir) / filename
    if not path.is_file():
        msg = f"{filename}: no such file in {documentation_dir(base_dir)}"
        raise ValueError(msg)
    unknown = [eid for eid in (evidence_ids or []) if eid not in known_evidence_ids]
    if unknown:
        msg = f"{filename}: evidence_ids not in the corpus: {unknown}"
        raise ValueError(msg)
    registry = load_registry(base_dir)
    previous = {record.filename: record for record in registry.documents}
    current = today or date.today()
    record = DocumentRecord(
        filename=filename,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        first_seen=previous[filename].first_seen if filename in previous else current,
        processed_on=current,
        lane=lane,
        summary=summary,
        key_points=key_points or [],
        evidence_ids=evidence_ids or [],
    )
    kept = [r for r in registry.documents if r.filename != filename]
    _save_registry(base_dir, DocumentRegistry(documents=[*kept, record]))
    return record
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/memory/test_documents.py -q`
Expected: PASS (10 passed)

- [x] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check src/performance_agent/memory/documents.py tests/memory/test_documents.py
uv run ruff format src/performance_agent/memory/documents.py tests/memory/test_documents.py
uv run ty check
git add src/performance_agent/memory/documents.py tests/memory/test_documents.py
git commit -m "Add athlete documentation folder registry and scan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 2: `write_profile` creates the folder (onboarding path)

**Files:**
- Modify: `src/performance_agent/memory/store.py:103-108` (`write_profile`)
- Test: `tests/memory/test_documents.py` (append)

- [x] **Step 1: Write the failing test** (append to `tests/memory/test_documents.py`)

```python
def test_write_profile_bootstraps_documentation_folder(tmp_path):
    from performance_agent.memory import store
    from performance_agent.memory.schemas import Profile

    store.write_profile(tmp_path, Profile())
    assert (tmp_path / DOCUMENTATION_DIR / README_FILE).exists()
```

- [x] **Step 2: Run it** — `uv run pytest tests/memory/test_documents.py::test_write_profile_bootstraps_documentation_folder -q` — Expected: FAIL (no documentation dir)

- [x] **Step 3: Implement** — in `src/performance_agent/memory/store.py`, add to the imports block (after the `from performance_agent.memory.schemas import (...)` import):

```python
from performance_agent.memory.documents import ensure_documentation_dir
```

and change `write_profile` to:

```python
def write_profile(base_dir: Path, profile: Profile) -> Path:
    """Persist the whole profile as readable YAML; returns the file path.

    Also bootstraps the documentation/ drop folder so onboarding creates it.
    """
    path = base_dir / PROFILE_FILE
    _atomic_write(path, _to_yaml(profile.model_dump(mode="json")))
    ensure_documentation_dir(base_dir)
    return path
```

(Keep the original body of `write_profile` otherwise identical to what is in the file — only the docstring line and the `ensure_documentation_dir` call are added.)

- [x] **Step 4: Run** — `uv run pytest tests/memory/test_documents.py tests/memory/ -q` — Expected: PASS, no regressions

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/memory/store.py tests/memory/test_documents.py
git commit -m "Bootstrap documentation folder from write_profile

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: MCP tools `list_athlete_documents` + `mark_document_processed`

**Files:**
- Create: `src/performance_agent/server/document_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_document_tools.py`

- [x] **Step 1: Write the failing tests**

Create `tests/server/test_document_tools.py`:

```python
"""MCP wrappers over the documentation folder."""

import pytest

from performance_agent.server import document_tools


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


def test_list_creates_folder_and_reports_new(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "study.pdf").write_bytes(b"x")
    inventory = document_tools.list_athlete_documents()
    assert [item["filename"] for item in inventory["new"]] == ["study.pdf"]
    assert (athlete_dir / "documentation" / "README.md").exists()


def test_mark_validates_evidence_ids_against_corpus(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "study.pdf").write_bytes(b"x")
    with pytest.raises(ValueError, match="not-a-corpus-id"):
        document_tools.mark_document_processed(
            "study.pdf", lane="evidence", summary="s", evidence_ids=["not-a-corpus-id"]
        )


def test_mark_context_then_list_shows_processed(athlete_dir):
    (athlete_dir / "documentation").mkdir()
    (athlete_dir / "documentation" / "notes.md").write_bytes(b"physio notes")
    result = document_tools.mark_document_processed(
        "notes.md", lane="context", summary="Physio: avoid loaded flexion 2 weeks."
    )
    assert result["lane"] == "context"
    inventory = document_tools.list_athlete_documents()
    assert inventory["processed"][0]["summary"].startswith("Physio")
```

- [x] **Step 2: Run** — `uv run pytest tests/server/test_document_tools.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/server/document_tools.py`:

```python
"""MCP tools for the athlete documentation drop folder.

The server hands out paths and bookkeeping only — reading the files (PDFs
included) is the client's job, and saving a verified study goes through the
regular verify_reference/save_evidence pipeline. Lane rule: `evidence` only
when a locator resolved; everything else is `context` (used to personalize,
never cited as science) or `unreadable`.
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.evidence.corpus import load_corpus
from performance_agent.memory import documents
from performance_agent.memory.documents import Lane, ScanResult
from performance_agent.memory.paths import resolve_athlete_dir


class DocumentMarked(TypedDict):
    """The stored registry record after marking one file."""

    filename: str
    lane: str
    summary: str | None
    evidence_ids: list[str]


def list_athlete_documents() -> ScanResult:
    """Inventory the athlete's documentation/ drop folder (creates it on first call).

    Returns files split into: new (never processed), modified (content changed
    since processing — process again), processed (with the stored summary, so
    you know what you know without re-reading), removed (registry entry whose
    file is gone), unreadable. Each pending item carries its absolute path —
    read the file yourself, then record the outcome with
    mark_document_processed. Never writes the registry.
    """
    return documents.scan_documents(resolve_athlete_dir())


def mark_document_processed(
    filename: str,
    lane: Lane,
    summary: str | None = None,
    key_points: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> DocumentMarked:
    """Record what you did with one dropped file (replaces any earlier record).

    lane must follow the hard rule: `evidence` ONLY when a DOI/PMID/ISBN from
    the document resolved via verify_reference and the study was saved with
    save_evidence (list those corpus ids in evidence_ids — they are validated
    against the corpus). Everything else is `context` (summary + key_points
    persist and inform coaching, never cited as science) or `unreadable`.
    summary is required except for unreadable files.
    """
    record = documents.mark_processed(
        resolve_athlete_dir(),
        filename,
        lane=lane,
        summary=summary,
        key_points=key_points,
        evidence_ids=evidence_ids,
        known_evidence_ids={entry.id for entry in load_corpus()},
    )
    return DocumentMarked(
        filename=record.filename,
        lane=record.lane,
        summary=record.summary,
        evidence_ids=list(record.evidence_ids),
    )


def register(mcp: FastMCP) -> None:
    """Register the document tools on the server."""
    for tool in (list_athlete_documents, mark_document_processed):
        mcp.tool()(tool)
```

In `src/performance_agent/server/app.py`, add `document_tools` to the import tuple and register it (the file lists modules alphabetically):

```python
from performance_agent.server import (
    autoregulation_tools,
    document_tools,
    engine_tools,
    evidence_tools,
    exercise_tools,
    import_tools,
    macro_tools,
    memory_tools,
    performance_tools,
    report_tools,
    response_tools,
    taper_tools,
)
```

and after `engine_tools.register(mcp)` line block add (keep existing order, append at the end of the register calls):

```python
document_tools.register(mcp)
```

- [x] **Step 4: Run** — `uv run pytest tests/server/test_document_tools.py tests/server/ -q` — Expected: PASS

- [x] **Step 5: Lint, commit**

```bash
uv run ruff check src/performance_agent/server/document_tools.py src/performance_agent/server/app.py tests/server/test_document_tools.py && uv run ruff format --check src tests
uv run ty check
git add src/performance_agent/server/document_tools.py src/performance_agent/server/app.py tests/server/test_document_tools.py
git commit -m "Add list_athlete_documents and mark_document_processed tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4: Phase 1 gate

- [x] **Step 1: Full test suite** — Run: `uv run pytest -q` — Expected: all pass (1275+ tests, plus the new ones)
- [x] **Step 2: Zero warnings** — Run: `uv run ruff check src tests && uv run ty check` — Expected: clean. Fix anything before moving on.

---

## Phase 2 — Weekly follow-up (structured progression + engine tool + watch report + diligence)

### Task 5: `ProgressionRule` schema + `ExerciseBlock.progression`

**Files:**
- Modify: `src/performance_agent/memory/schemas.py` (insert `ProgressionRule` right BEFORE `class ExerciseBlock` at line 347; add one field to `ExerciseBlock`)
- Test: `tests/memory/test_schemas_progression.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_schemas_progression.py`:

```python
"""ProgressionRule: per-kind parameter validation and block attachment."""

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import ExerciseBlock, ProgressionRule


def test_double_requires_range_and_increment():
    rule = ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5)
    assert rule.rounding_kg == 2.5
    with pytest.raises(ValidationError, match="rep_min"):
        ProgressionRule(kind="double", rep_max=12, increment_kg=2.5)
    with pytest.raises(ValidationError, match="rep_min"):
        ProgressionRule(kind="double", rep_min=12, rep_max=8, increment_kg=2.5)


def test_linear_requires_increment():
    ProgressionRule(kind="linear_load", increment_kg=2.5)
    with pytest.raises(ValidationError, match="increment_kg"):
        ProgressionRule(kind="linear_load")


def test_rir_target_requires_target():
    rule = ProgressionRule(kind="rir_target", target_rir=2)
    assert rule.adjust_pct_per_rir == 0.03
    with pytest.raises(ValidationError, match="target_rir"):
        ProgressionRule(kind="rir_target")


def test_from_pct_and_none_take_no_required_params():
    ProgressionRule(kind="from_pct")
    ProgressionRule(kind="none")


def test_block_accepts_structured_progression_and_stays_optional():
    block = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=4,
        reps="8-12",
        load_kg=80,
        progression_rule="Double progression 8-12, +2.5 kg at the top.",
        progression=ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    )
    assert block.progression is not None
    legacy = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=4,
        reps="8-12",
        load_kg=80,
        progression_rule="text only",
    )
    assert legacy.progression is None
```

- [x] **Step 2: Run** — `uv run pytest tests/memory/test_schemas_progression.py -q` — Expected: FAIL (`ImportError: ProgressionRule`)

- [x] **Step 3: Implement**

In `src/performance_agent/memory/schemas.py`, insert immediately before `class ExerciseBlock`:

```python
class ProgressionRule(BaseModel):
    """Machine-readable weekly progression; the engine computes next week from it.

    The free-text progression_rule on the block stays the human rendering; when
    this structured rule is present it is the source of computation. Defaults
    (3%/RIR, 2.5 kg rounding, the ±10% weekly clamp in the engine) are
    team-chosen priors.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["double", "linear_load", "rir_target", "from_pct", "none"]
    rep_min: int | None = Field(default=None, ge=1, le=100)
    rep_max: int | None = Field(default=None, ge=1, le=100)
    increment_kg: float | None = Field(default=None, gt=0, le=50)
    target_rir: float | None = Field(default=None, ge=0, le=10)
    adjust_pct_per_rir: float = Field(default=0.03, gt=0, le=0.2)
    rounding_kg: float = Field(default=2.5, gt=0, le=10)

    @model_validator(mode="after")
    def _params_match_kind(self) -> Self:
        if self.kind == "double":
            if self.rep_min is None or self.rep_max is None or self.increment_kg is None:
                msg = "kind=double requires rep_min, rep_max and increment_kg"
                raise ValueError(msg)
            if self.rep_min >= self.rep_max:
                msg = f"rep_min must be < rep_max, got {self.rep_min}..{self.rep_max}"
                raise ValueError(msg)
        if self.kind == "linear_load" and self.increment_kg is None:
            msg = "kind=linear_load requires increment_kg"
            raise ValueError(msg)
        if self.kind == "rir_target" and self.target_rir is None:
            msg = "kind=rir_target requires target_rir"
            raise ValueError(msg)
        return self
```

In `ExerciseBlock`, add after the `progression_rule: str = Field(min_length=1)` line:

```python
    progression: ProgressionRule | None = None
```

- [x] **Step 4: Run** — `uv run pytest tests/memory/test_schemas_progression.py tests/memory/ -q` — Expected: PASS (old program yaml without the field still loads: covered by existing store tests)

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas_progression.py
git commit -m "Add structured ProgressionRule to exercise blocks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 6: `engine/progression.py` — pure next-load math

**Files:**
- Create: `src/performance_agent/engine/progression.py`
- Test: `tests/engine/test_progression.py`

- [x] **Step 1: Write the failing tests**

Create `tests/engine/test_progression.py`:

```python
"""Pure next-load math for each ProgressionRule kind."""

import pytest

from performance_agent.engine.progression import (
    SetActual,
    next_load_double,
    next_load_from_pct,
    next_load_linear,
    next_load_rir,
    round_to_increment,
)
from performance_agent.memory.schemas import ProgressionRule

DOUBLE = ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5)
LINEAR = ProgressionRule(kind="linear_load", increment_kg=2.5)
RIR = ProgressionRule(kind="rir_target", target_rir=2)


def sets(*reps, load=80.0, rir=None):
    return [SetActual(reps=r, load_kg=load, rir=rir) for r in reps]


def test_rounding():
    assert round_to_increment(81.4, 2.5) == 82.5
    assert round_to_increment(81.1, 2.5) == 80.0


def test_double_top_of_range_increments():
    result = next_load_double(DOUBLE, 80.0, sets(12, 12, 12, 12))
    assert result.next_load_kg == 82.5
    assert result.action == "increment"
    assert result.flags == ()


def test_double_mid_range_holds():
    result = next_load_double(DOUBLE, 80.0, sets(12, 12, 12, 11))
    assert result.next_load_kg == 80.0
    assert result.action == "hold"


def test_double_below_rep_min_holds_with_failed_flag():
    result = next_load_double(DOUBLE, 80.0, sets(8, 7, 6))
    assert result.next_load_kg == 80.0
    assert result.action == "hold"
    assert "failed_sets" in result.flags


def test_double_no_sets_flags_unmatched():
    result = next_load_double(DOUBLE, 80.0, [])
    assert result.next_load_kg is None
    assert "no_logged_sets" in result.flags


def test_linear_all_sets_at_prescribed_reps_increment():
    result = next_load_linear(LINEAR, 100.0, 5, sets(5, 5, 5, load=100.0))
    assert result.next_load_kg == 102.5
    assert result.action == "increment"


def test_linear_missed_reps_holds_with_flag():
    result = next_load_linear(LINEAR, 100.0, 5, sets(5, 4, 3, load=100.0))
    assert result.next_load_kg == 100.0
    assert "failed_sets" in result.flags


def test_rir_above_target_raises_load():
    # mean RIR 4 vs target 2 -> +6% on 100 kg -> 106 -> rounds to 105
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0, rir=4))
    assert result.next_load_kg == 105.0
    assert result.action == "increment"


def test_rir_below_target_lowers_load():
    # mean RIR 0 vs target 2 -> -6% -> 94 -> rounds to 95
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0, rir=0))
    assert result.next_load_kg == 95.0
    assert result.action == "decrement"


def test_rir_clamped_to_ten_percent():
    # mean RIR 8 vs target 2 -> raw +18% -> clamped to +10% -> 110
    result = next_load_rir(RIR, 100.0, sets(5, load=100.0, rir=8))
    assert result.next_load_kg == 110.0
    assert "clamped" in result.flags


def test_rir_without_logged_rir_holds():
    result = next_load_rir(RIR, 100.0, sets(5, 5, load=100.0))
    assert result.next_load_kg == 100.0
    assert "no_rir_logged" in result.flags


def test_from_pct_resolves_next_week_pct():
    result = next_load_from_pct(0.85, 140.0, 2.5)
    assert result.next_load_kg == 120.0
    assert result.action == "per_plan"


def test_from_pct_without_e1rm_flags():
    result = next_load_from_pct(0.85, None, 2.5)
    assert result.next_load_kg is None
    assert "no_e1rm" in result.flags
```

- [x] **Step 2: Run** — `uv run pytest tests/engine/test_progression.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/engine/progression.py`:

```python
"""Pure weekly progression math: one function per ProgressionRule kind.

No I/O, no dates. The memory layer (memory/weekly_review.py) matches logs to
blocks and dispatches here. The ±10% weekly cap on autoregulated (RIR) load
moves and the round-half-up-to-increment rounding are team-chosen priors.
"""

from dataclasses import dataclass

from performance_agent.memory.schemas import ProgressionRule

# Autoregulated weekly load moves are capped at ±10% (team-chosen prior):
# a single week's mean RIR should nudge the load, not rewrite it.
_MAX_RIR_ADJUST_PCT = 0.10


@dataclass(frozen=True)
class SetActual:
    """One logged set, already matched to the block being progressed."""

    reps: int
    load_kg: float
    rir: float | None = None


@dataclass(frozen=True)
class LoadSuggestion:
    """The engine's verdict for one block's next week."""

    next_load_kg: float | None
    action: str  # increment | hold | decrement | per_plan
    flags: tuple[str, ...] = ()


def round_to_increment(value: float, step: float) -> float:
    """Round to the nearest plate step (2.5 kg default upstream)."""
    if step <= 0:
        msg = f"step must be positive, got {step!r}"
        raise ValueError(msg)
    return round(value / step) * step


def next_load_double(
    rule: ProgressionRule, current_load_kg: float, sets: list[SetActual]
) -> LoadSuggestion:
    """Double progression: all sets at rep_max -> add increment, else hold."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    assert rule.rep_max is not None and rule.rep_min is not None  # noqa: S101 -- schema-validated
    assert rule.increment_kg is not None  # noqa: S101 -- schema-validated
    if all(s.reps >= rule.rep_max for s in sets):
        raised = round_to_increment(current_load_kg + rule.increment_kg, rule.rounding_kg)
        return LoadSuggestion(raised, "increment")
    flags = ("failed_sets",) if any(s.reps < rule.rep_min for s in sets) else ()
    return LoadSuggestion(current_load_kg, "hold", flags)


def next_load_linear(
    rule: ProgressionRule,
    current_load_kg: float,
    prescribed_reps: int,
    sets: list[SetActual],
) -> LoadSuggestion:
    """Linear load: every set hit the prescribed reps -> add increment, else hold."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    assert rule.increment_kg is not None  # noqa: S101 -- schema-validated
    if all(s.reps >= prescribed_reps for s in sets):
        raised = round_to_increment(current_load_kg + rule.increment_kg, rule.rounding_kg)
        return LoadSuggestion(raised, "increment")
    return LoadSuggestion(current_load_kg, "hold", ("failed_sets",))


def next_load_rir(
    rule: ProgressionRule, current_load_kg: float, sets: list[SetActual]
) -> LoadSuggestion:
    """RIR-target autoregulation: adjust_pct_per_rir per point of mean deviation."""
    if not sets:
        return LoadSuggestion(None, "hold", ("no_logged_sets",))
    assert rule.target_rir is not None  # noqa: S101 -- schema-validated
    rirs = [s.rir for s in sets if s.rir is not None]
    if not rirs:
        return LoadSuggestion(current_load_kg, "hold", ("no_rir_logged",))
    delta = sum(rirs) / len(rirs) - rule.target_rir
    adjust = rule.adjust_pct_per_rir * delta
    flags: tuple[str, ...] = ()
    if abs(adjust) > _MAX_RIR_ADJUST_PCT:
        adjust = _MAX_RIR_ADJUST_PCT if adjust > 0 else -_MAX_RIR_ADJUST_PCT
        flags = ("clamped",)
    raised = round_to_increment(current_load_kg * (1 + adjust), rule.rounding_kg)
    if raised > current_load_kg:
        action = "increment"
    elif raised < current_load_kg:
        action = "decrement"
    else:
        action = "hold"
    return LoadSuggestion(raised, action, flags)


def next_load_from_pct(
    next_pct_1rm: float, e1rm_kg: float | None, rounding_kg: float
) -> LoadSuggestion:
    """Percent-planned blocks: next week's planned pct resolved against e1RM."""
    if e1rm_kg is None:
        return LoadSuggestion(None, "per_plan", ("no_e1rm",))
    return LoadSuggestion(round_to_increment(next_pct_1rm * e1rm_kg, rounding_kg), "per_plan")
```

Note: `assert` here documents schema-guaranteed invariants (the Pydantic validator makes them unreachable); if the repo's ruff config rejects `S101`, replace each assert with an explicit `if x is None: raise ValueError(...)` guard.

- [x] **Step 4: Run** — `uv run pytest tests/engine/test_progression.py tests/engine/test_engine_purity.py -q` — Expected: PASS (purity test must still pass — this module imports only schemas + dataclasses)

- [x] **Step 5: Commit**

```bash
uv run ruff check src/performance_agent/engine/progression.py tests/engine/test_progression.py
git add src/performance_agent/engine/progression.py tests/engine/test_progression.py
git commit -m "Add pure next-load progression engine

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 7: `memory/weekly_review.py` — match the logged week, dispatch rules

**Files:**
- Create: `src/performance_agent/memory/weekly_review.py`
- Test: `tests/memory/test_weekly_review.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_weekly_review.py`. It needs a small program fixture; build it inline:

```python
"""Weekly loads review: week matching, rule dispatch, state file."""

from datetime import date, datetime

import pytest

from performance_agent.memory import store, weekly_review
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ExercisePerformed,
    Fallbacks,
    Mesocycle,
    Profile,
    ProgressionRule,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    SetPerformed,
    WeekPlan,
)

TODAY = date(2026, 7, 17)
FALLBACKS = Fallbacks(low_readiness="halve", short_on_time="cut accessories", missing_equipment="dumbbells")


def _block(exercise="Bench press", **overrides):
    fields = dict(
        exercise=exercise,
        priority="primary",
        sets=3,
        reps="8-12",
        load_kg=80.0,
        rest_s=120,
        progression_rule="Double progression 8-12, +2.5 kg at the top.",
        progression=ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    )
    fields.update(overrides)
    return ExerciseBlock(**fields)


def _week(index, blocks):
    return WeekPlan(
        week_index=index,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id=f"w{index}-a",
                weekday=0,
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper strength",
                blocks=blocks,
                fallbacks=FALLBACKS,
            )
        ],
    )


def _save_program(base, weeks):
    plan = ProgramPlan(
        version=1,
        goal_id="bench-goal",
        created_on=TODAY,
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=weeks)],
    )
    store.save_program(base, plan, today=TODAY)


def _log(base, day, session_plan_id, exercise="Bench press", reps=(12, 12, 12), load=80.0, rir=None):
    entry = SessionEntry(
        performed_at=datetime(day.year, day.month, day.day, 18, 0),
        session_plan_id=session_plan_id,
        exercises=[
            ExercisePerformed(
                name=exercise,
                sets=[SetPerformed(reps=r, load_kg=load, rir=rir) for r in reps],
            )
        ],
    )
    store.append_session(base, entry)


def test_no_program_raises(tmp_path):
    with pytest.raises(ValueError, match="no program"):
        weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)


def test_double_progression_increment_end_to_end(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert view["week_matched"] == 1
    [block] = view["blocks"]
    assert block["exercise"] == "Bench press"
    assert block["next_load_kg"] == 82.5
    assert block["rationale_key"] == "increment"


def test_unmatched_block_is_flagged_not_guessed(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(
        tmp_path,
        [_week(1, [_block(), _block(exercise="Squat")]), _week(2, [_block()])],
    )
    _log(tmp_path, date(2026, 7, 13), "w1-a")  # only bench logged
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    squat = next(b for b in view["blocks"] if b["exercise"] == "Squat")
    assert squat["next_load_kg"] is None
    assert "no_logged_sets" in squat["flags"]


def test_block_without_structured_rule_flags_no_rule(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block(progression=None)]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    [block] = view["blocks"]
    assert block["rationale_key"] == "no_rule"
    assert block["next_load_kg"] is None


def test_from_pct_uses_next_week_pct_and_logged_e1rm(tmp_path):
    store.write_profile(tmp_path, Profile())
    week1 = _week(
        1,
        [_block(load_kg=None, pct_1rm=0.8, progression=ProgressionRule(kind="from_pct"))],
    )
    week2 = _week(
        2,
        [_block(load_kg=None, pct_1rm=0.85, progression=ProgressionRule(kind="from_pct"))],
    )
    _save_program(tmp_path, [week1, week2])
    # best set 100x5 -> Epley e1RM 116.7 -> 0.85 * 116.7 = 99.2 -> rounds to 100
    _log(tmp_path, date(2026, 7, 13), "w1-a", reps=(5, 5), load=100.0)
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    [block] = view["blocks"]
    assert block["next_load_kg"] == 100.0
    assert block["rationale_key"] == "per_plan"


def test_state_file_records_the_run(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    _log(tmp_path, date(2026, 7, 13), "w1-a")
    assert weekly_review.read_last_run(tmp_path) is None
    weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert weekly_review.read_last_run(tmp_path) == TODAY


def test_no_matching_week_returns_empty_with_flag(tmp_path):
    store.write_profile(tmp_path, Profile())
    _save_program(tmp_path, [_week(1, [_block()]), _week(2, [_block()])])
    view = weekly_review.suggest_next_week_loads(tmp_path, today=TODAY)
    assert view["week_matched"] is None
    assert view["blocks"] == []
    assert "no_matched_week" in view["flags"]
```

- [x] **Step 2: Run** — `uv run pytest tests/memory/test_weekly_review.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/memory/weekly_review.py`:

```python
"""Weekly loads review: match the logged week to the program, apply each rule.

Deterministic given `today`. Matching: sessions logged in the last `days_back`
days are matched to program sessions by session_plan_id when present, else by
exercise-name overlap; the program week with the most matched sessions is the
current week (tie -> highest week_index). Suggestions target each block's next
occurrence: same-load rules (double/linear/rir_target) progress the current
block; from_pct resolves the SAME exercise's planned pct in the following week
(fallback: the current block's pct). e1RM comes from the best logged set of
that exercise in the last 14 days (Epley), falling back to the profile's
lift_inventory. A successful run records its date so diligence can see it.
"""

from datetime import date
from pathlib import Path
from typing import TypedDict

import yaml

from performance_agent.engine.progression import (
    SetActual,
    next_load_double,
    next_load_from_pct,
    next_load_linear,
    next_load_rir,
)
from performance_agent.engine.strength import MAX_ESTIMATION_REPS, one_rm_epley
from performance_agent.memory import store
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    WeekPlan,
)
from performance_agent.programs.render import intensity_label, volume_label

LOADS_REVIEW_STATE_FILE = "loads-review.yaml"
_DEFAULT_WINDOW_DAYS = 7
_E1RM_WINDOW_DAYS = 14


class ActualSetView(TypedDict):
    """One logged set as facts."""

    reps: int
    load_kg: float
    rir: float | None


class BlockSuggestionView(TypedDict):
    """Next-week verdict for one block (facts; the LLM renders the sentence)."""

    session_id: str
    exercise: str
    rule_kind: str | None
    prescribed_volume: str
    prescribed_intensity: str
    actual_sets: list[ActualSetView]
    next_load_kg: float | None
    rationale_key: str
    flags: list[str]


class WeeklyLoadsView(TypedDict):
    """The whole review: matched week, one verdict per block, run-level flags."""

    week_matched: int | None
    blocks: list[BlockSuggestionView]
    flags: list[str]


def read_last_run(base_dir: Path) -> date | None:
    """Date of the last successful review, or None when never run."""
    path = base_dir / LOADS_REVIEW_STATE_FILE
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "last_run" not in raw:
        return None
    return date.fromisoformat(str(raw["last_run"]))


def _record_run(base_dir: Path, current: date) -> None:
    path = base_dir / LOADS_REVIEW_STATE_FILE
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump({"last_run": current.isoformat()}), encoding="utf-8")
    tmp.replace(path)


def _weeks_in_order(plan: ProgramPlan) -> list[WeekPlan]:
    return [week for meso in plan.mesocycles for week in meso.weeks]


def _window_sessions(base_dir: Path, current: date, days_back: int) -> list[SessionEntry]:
    return [
        entry
        for entry in store.read_sessions(base_dir)
        if entry.source == "programmed"
        and 0 <= (current - entry.performed_at.date()).days < days_back
    ]


def _logged_names(entries: list[SessionEntry]) -> set[str]:
    return {ex.name.casefold() for entry in entries for ex in entry.exercises}


def _match_week(weeks: list[WeekPlan], logged: list[SessionEntry]) -> WeekPlan | None:
    plan_ids = {entry.session_plan_id for entry in logged if entry.session_plan_id}
    names = _logged_names(logged)

    def score(week: WeekPlan) -> int:
        if plan_ids:
            return sum(1 for session in week.sessions if session.id in plan_ids)
        return sum(
            1
            for session in week.sessions
            for block in session.blocks
            if block.exercise.casefold() in names
        )

    best = max(weeks, key=lambda week: (score(week), week.week_index), default=None)
    if best is None or score(best) == 0:
        return None
    return best


def _sets_for_block(block: ExerciseBlock, logged: list[SessionEntry]) -> list[SetActual]:
    wanted = block.exercise.casefold()
    return [
        SetActual(reps=s.reps, load_kg=s.load_kg, rir=s.rir)
        for entry in logged
        for ex in entry.exercises
        if ex.name.casefold() == wanted
        for s in ex.sets
    ]


def _e1rm_for(base_dir: Path, exercise: str, current: date) -> float | None:
    wanted = exercise.casefold()
    best: float | None = None
    for entry in store.read_sessions(base_dir):
        if not 0 <= (current - entry.performed_at.date()).days < _E1RM_WINDOW_DAYS:
            continue
        for ex in entry.exercises:
            if ex.name.casefold() != wanted:
                continue
            for s in ex.sets:
                if s.load_kg <= 0 or not 1 <= s.reps <= MAX_ESTIMATION_REPS:
                    continue
                estimate = one_rm_epley(s.load_kg, s.reps)
                best = estimate if best is None else max(best, estimate)
    if best is not None:
        return best
    profile = store.read_profile(base_dir)
    for record in profile.lift_inventory:
        if record.lift.casefold() == wanted:
            return record.one_rm_kg
    return None


def _next_pct_for(block: ExerciseBlock, next_week: WeekPlan | None) -> float | None:
    if next_week is not None:
        for session in next_week.sessions:
            for candidate in session.blocks:
                if candidate.exercise.casefold() == block.exercise.casefold():
                    if candidate.pct_1rm is not None:
                        return candidate.pct_1rm
    return block.pct_1rm


def _suggest_block(  # noqa: PLR0911 -- one return per rule kind is the readable shape
    base_dir: Path,
    session: SessionPlan,
    block: ExerciseBlock,
    logged: list[SessionEntry],
    next_week: WeekPlan | None,
    current: date,
) -> BlockSuggestionView:
    view = BlockSuggestionView(
        session_id=session.id,
        exercise=block.exercise,
        rule_kind=block.progression.kind if block.progression else None,
        prescribed_volume=volume_label(block),
        prescribed_intensity=intensity_label(block),
        actual_sets=[],
        next_load_kg=None,
        rationale_key="no_rule",
        flags=[],
    )
    sets = _sets_for_block(block, logged)
    view["actual_sets"] = [
        ActualSetView(reps=s.reps, load_kg=s.load_kg, rir=s.rir) for s in sets
    ]
    rule = block.progression
    if rule is None:
        return view
    if rule.kind == "none":
        view["rationale_key"] = "per_plan"
        return view
    if rule.kind == "from_pct":
        pct = _next_pct_for(block, next_week)
        if pct is None:
            view["rationale_key"] = "per_plan"
            view["flags"] = ["no_pct_prescribed"]
            return view
        result = next_load_from_pct(pct, _e1rm_for(base_dir, block.exercise, current), rule.rounding_kg)
    elif rule.kind == "double":
        result = next_load_double(rule, block.load_kg or 0.0, sets)
    elif rule.kind == "linear_load":
        reps = block.reps or ""
        if not reps.isdigit():
            view["rationale_key"] = "hold"
            view["flags"] = ["ambiguous_reps"]
            return view
        result = next_load_linear(rule, block.load_kg or 0.0, int(reps), sets)
    else:  # rir_target
        result = next_load_rir(rule, block.load_kg or 0.0, sets)
    view["next_load_kg"] = result.next_load_kg
    view["rationale_key"] = result.action
    view["flags"] = list(result.flags)
    return view


def suggest_next_week_loads(
    base_dir: Path, today: date | None = None, days_back: int = _DEFAULT_WINDOW_DAYS
) -> WeeklyLoadsView:
    """Compute every block's next-week load from the logged week (see module doc)."""
    if days_back < 1:
        msg = f"days_back must be >= 1, got {days_back!r}"
        raise ValueError(msg)
    current = today or date.today()
    program = store.read_program(base_dir)
    if program is None:
        msg = "no program has been saved yet; save a program before a loads review"
        raise ValueError(msg)
    if program.plan is None:
        msg = "the active program is legacy prose-only; a structured plan is required"
        raise ValueError(msg)
    weeks = _weeks_in_order(program.plan)
    logged = _window_sessions(base_dir, current, days_back)
    week = _match_week(weeks, logged)
    if week is None:
        return WeeklyLoadsView(week_matched=None, blocks=[], flags=["no_matched_week"])
    position = weeks.index(week)
    next_week = weeks[position + 1] if position + 1 < len(weeks) else None
    flags = [] if next_week is not None else ["last_week"]
    blocks = [
        _suggest_block(base_dir, session, block, logged, next_week, current)
        for session in week.sessions
        for block in session.blocks
    ]
    _record_run(base_dir, current)
    return WeeklyLoadsView(week_matched=week.week_index, blocks=blocks, flags=flags)
```

- [x] **Step 4: Run** — `uv run pytest tests/memory/test_weekly_review.py -q` — Expected: PASS. If the Epley expectation in `test_from_pct_uses_next_week_pct_and_logged_e1rm` is off by one rounding step, recompute by hand (100 × (1 + 5/30) = 116.67; 0.85 × 116.67 = 99.17 → 100.0 at 2.5 rounding) — fix the TEST only if your arithmetic disagrees, never the engine.

- [x] **Step 5: Commit**

```bash
uv run ruff check src/performance_agent/memory/weekly_review.py tests/memory/test_weekly_review.py
git add src/performance_agent/memory/weekly_review.py tests/memory/test_weekly_review.py
git commit -m "Add weekly loads review with week matching and rule dispatch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 8: Watch report versioned doc in the store

**Files:**
- Modify: `src/performance_agent/memory/store.py` (constants + three functions, after the nutrition-frame block at the end of the file)
- Test: `tests/memory/test_store_watch.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_store_watch.py`:

```python
"""Watch reports: immutable versioned docs under watch/."""

import pytest

from performance_agent.memory import store


def test_first_report_is_v1_and_readable(tmp_path):
    path, version = store.save_watch_report(tmp_path, "All lifts on track.", "goal-1")
    assert version == 1
    assert path == tmp_path / "watch" / "report-v1.md"
    frontmatter, body = store.read_watch_report(tmp_path)
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
```

- [x] **Step 2: Run** — `uv run pytest tests/memory/test_store_watch.py -q` — Expected: FAIL (`AttributeError: save_watch_report`)

- [x] **Step 3: Implement** — in `src/performance_agent/memory/store.py`, add to the constants block (after `EXERCISE_LIBRARY_FILE`):

```python
WATCH_DIR = "watch"
```

and append at the end of the file:

```python
def latest_watch_report_version(base_dir: Path) -> int | None:
    """Return the highest existing watch-report version, or None."""
    return _latest_doc_version(base_dir, WATCH_DIR, "report")


def save_watch_report(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next program-watch report version; v2+ requires a reason.

    Same immutable-version audit trail as the other doc families; lives in
    watch/. The latest report's created_on is also the diligence anchor for
    "program watch due".
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=WATCH_DIR,
        prefix="report",
        label="watch report",
        reason=reason,
        today=today,
    )


def read_watch_report(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest watch report; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=WATCH_DIR,
        prefix="report",
        label="watch report",
        version=version,
    )
```

- [x] **Step 4: Run** — `uv run pytest tests/memory/test_store_watch.py tests/memory/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/memory/store.py tests/memory/test_store_watch.py
git commit -m "Add watch report versioned doc family

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 9: MCP tools `suggest_next_week_loads` + `save_watch_report`

**Files:**
- Create: `src/performance_agent/server/followup_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_followup_tools.py`

- [x] **Step 1: Write the failing tests**

Create `tests/server/test_followup_tools.py`:

```python
"""MCP wrappers for the weekly follow-up."""

from datetime import date, datetime

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    ExerciseBlock,
    ExercisePerformed,
    Fallbacks,
    Mesocycle,
    Profile,
    ProgressionRule,
    ProgramPlan,
    SessionEntry,
    SessionPlan,
    SetPerformed,
    WeekPlan,
)
from performance_agent.server import followup_tools


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    store.write_profile(tmp_path, Profile())
    return tmp_path


def _seed_program_and_log(base):
    block = ExerciseBlock(
        exercise="Bench press",
        priority="primary",
        sets=3,
        reps="8-12",
        load_kg=80.0,
        progression_rule="Double progression 8-12, +2.5 kg at the top.",
        progression=ProgressionRule(kind="double", rep_min=8, rep_max=12, increment_kg=2.5),
    )
    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id="w1-a",
                weekday=0,
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper",
                blocks=[block],
                fallbacks=Fallbacks(
                    low_readiness="halve", short_on_time="cut", missing_equipment="dumbbells"
                ),
            )
        ],
    )
    plan = ProgramPlan(
        version=1,
        goal_id="bench-goal",
        created_on=date(2026, 7, 13),
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=[week])],
    )
    store.save_program(base, plan, today=date(2026, 7, 13))
    store.append_session(
        base,
        SessionEntry(
            performed_at=datetime(2026, 7, 15, 18, 0),
            session_plan_id="w1-a",
            exercises=[
                ExercisePerformed(
                    name="Bench press",
                    sets=[SetPerformed(reps=12, load_kg=80.0) for _ in range(3)],
                )
            ],
        ),
    )


def test_suggest_returns_block_verdicts(athlete_dir):
    _seed_program_and_log(athlete_dir)
    view = followup_tools.suggest_next_week_loads()
    assert view["week_matched"] == 1
    assert view["blocks"][0]["next_load_kg"] == 82.5


def test_suggest_rejects_bad_window(athlete_dir):
    with pytest.raises(ValueError, match="days_back"):
        followup_tools.suggest_next_week_loads(days_back=0)


def test_save_watch_report_versions(athlete_dir):
    result = followup_tools.save_watch_report("All on track.", "bench-goal")
    assert result["version"] == 1
```

- [x] **Step 2: Run** — `uv run pytest tests/server/test_followup_tools.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/server/followup_tools.py`:

```python
"""MCP tools for the weekly follow-up: loads review and watch reports."""

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import store, weekly_review
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.weekly_review import WeeklyLoadsView
from performance_agent.server.memory_tools import VersionedDocSaved


def suggest_next_week_loads(days_back: int = 7) -> WeeklyLoadsView:
    """Compute next week's load for every block of the logged program week.

    Deterministic engine math, zero guessing: logged sessions from the last
    days_back days are matched to the program (session_plan_id first, exercise
    names as fallback); each block's structured progression rule then yields
    {next_load_kg, rationale_key, flags}. Degraded cases are flags, never
    guesses: no_rule (unstructured block — handle it conversationally),
    no_logged_sets, failed_sets (hold), no_rir_logged, no_e1rm, clamped,
    ambiguous_reps; week-level: no_matched_week, last_week. Quote the numbers
    and the rationale to the athlete; this NEVER modifies the program. A
    successful run is recorded so list_due_actions can see the review happened.
    """
    return weekly_review.suggest_next_week_loads(resolve_athlete_dir(), days_back=days_back)


def save_watch_report(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT program-watch report version (immutable audit trail).

    The report is the program-watch skill's output: per-exercise verdicts
    (keep / watch / substitution candidate) with the data behind each one.
    Version 1 needs no reason; every later report (v2+) requires a reason
    naming its trigger (biweekly watch, mesocycle boundary, athlete request).
    Saving also timestamps the watch for list_due_actions.
    """
    path, version = store.save_watch_report(
        resolve_athlete_dir(), markdown_body, goal_id, reason
    )
    return VersionedDocSaved(path=str(path), version=version)


def register(mcp: FastMCP) -> None:
    """Register the follow-up tools on the server."""
    for tool in (suggest_next_week_loads, save_watch_report):
        mcp.tool()(tool)
```

In `src/performance_agent/server/app.py`, add `followup_tools` to the import tuple (alphabetical: between `exercise_tools` and `import_tools`) and add `followup_tools.register(mcp)` after `document_tools.register(mcp)`.

- [x] **Step 4: Run** — `uv run pytest tests/server/test_followup_tools.py tests/server/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff check src/performance_agent/server/followup_tools.py src/performance_agent/server/app.py tests/server/test_followup_tools.py
git add src/performance_agent/server/followup_tools.py src/performance_agent/server/app.py tests/server/test_followup_tools.py
git commit -m "Add suggest_next_week_loads and save_watch_report tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 10: Diligence — `loads_review` and `program_watch` due actions

**Files:**
- Modify: `src/performance_agent/engine/diligence.py` (facts + two action builders + thresholds)
- Modify: `src/performance_agent/memory/diligence.py` (fact extraction)
- Test: `tests/engine/test_diligence.py` (append), `tests/memory/` covered via server tests

- [x] **Step 1: Write the failing tests** (append to `tests/engine/test_diligence.py`)

```python
def test_loads_review_due_when_sessions_logged_and_never_reviewed():
    from performance_agent.engine.diligence import DiligenceFacts, list_due_actions

    facts = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=3,
        days_since_loads_review=None,
    )
    kinds = {action.kind for action in list_due_actions(facts)}
    assert "loads_review" in kinds


def test_loads_review_quiet_without_recent_sessions_or_when_fresh():
    from performance_agent.engine.diligence import DiligenceFacts, list_due_actions

    quiet = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=0,
        days_since_loads_review=None,
    )
    fresh = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        sessions_logged_last_week=3,
        days_since_loads_review=2,
    )
    for facts in (quiet, fresh):
        kinds = {action.kind for action in list_due_actions(facts)}
        assert "loads_review" not in kinds


def test_program_watch_due_after_fourteen_days():
    from performance_agent.engine.diligence import DiligenceFacts, list_due_actions

    facts = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        days_since_watch_anchor=15,
    )
    kinds = {action.kind for action in list_due_actions(facts)}
    assert "program_watch" in kinds


def test_program_watch_quiet_when_recent_or_no_program():
    from performance_agent.engine.diligence import DiligenceFacts, list_due_actions

    recent = DiligenceFacts(
        has_program=True,
        checkin_cadence_days=7,
        days_since_checkin=1,
        days_since_watch_anchor=13,
    )
    no_program = DiligenceFacts(
        has_program=False,
        checkin_cadence_days=7,
        days_since_watch_anchor=100,
    )
    for facts in (recent, no_program):
        kinds = {action.kind for action in list_due_actions(facts)}
        assert "program_watch" not in kinds
```

- [x] **Step 2: Run** — `uv run pytest tests/engine/test_diligence.py -q` — Expected: FAIL (`unexpected keyword argument 'sessions_logged_last_week'`)

- [x] **Step 3: Implement**

In `src/performance_agent/engine/diligence.py`:

Add to the thresholds block (after `_RED_STREAK_HIGH = 3`):

```python
# A training week with logged sessions deserves a loads review within six days;
# a running program deserves a watch pass every two weeks (team-chosen priors).
_LOADS_REVIEW_DUE_DAYS = 6
_WATCH_DUE_DAYS = 14
```

Add two fields at the end of `DiligenceFacts`:

```python
    sessions_logged_last_week: int = 0
    days_since_loads_review: int | None = None
    days_since_watch_anchor: int | None = None
```

(and extend the class docstring with: `days_since_loads_review is None when no review was ever recorded; days_since_watch_anchor counts from the newest of program start / last watch report, None without a program.`)

Add two action builders (after `_red_streak_action`):

```python
def _loads_review_action(facts: DiligenceFacts) -> DueAction | None:
    if not facts.has_program or facts.sessions_logged_last_week < 1:
        return None
    never = facts.days_since_loads_review is None
    if not never and (facts.days_since_loads_review or 0) < _LOADS_REVIEW_DUE_DAYS:
        return None
    return DueAction(
        "loads_review",
        "medium",
        "loads_review_due",
        due_since_days=facts.days_since_loads_review,
    )


def _watch_action(facts: DiligenceFacts) -> DueAction | None:
    if not facts.has_program or facts.days_since_watch_anchor is None:
        return None
    if facts.days_since_watch_anchor < _WATCH_DUE_DAYS:
        return None
    return DueAction(
        "program_watch",
        "medium",
        "program_watch_due",
        due_since_days=facts.days_since_watch_anchor,
    )
```

Register both in the `candidates` list inside `list_due_actions` (after `_red_streak_action(facts),`):

```python
        _loads_review_action(facts),
        _watch_action(facts),
```

In `src/performance_agent/memory/diligence.py`:

Add imports: `from performance_agent.memory import weekly_review` (with the existing memory imports).

Add two helpers (after `_readiness_red_streak`):

```python
def _sessions_logged_last_week(base_dir: Path, current: date) -> int:
    return sum(
        1
        for entry in store.read_sessions(base_dir)
        if 0 <= (current - entry.performed_at.date()).days < _MISSED_WINDOW_DAYS
    )


def _days_since_loads_review(base_dir: Path, current: date) -> int | None:
    last_run = weekly_review.read_last_run(base_dir)
    return None if last_run is None else (current - last_run).days


def _days_since_watch_anchor(base_dir: Path, current: date) -> int | None:
    """Days since the newest of program start / latest watch report, or None."""
    program = store.read_program(base_dir)
    if program is None:
        return None
    anchor = date.fromisoformat(program.created_on)
    report = store.read_watch_report(base_dir)
    if report is not None:
        frontmatter, _ = report
        anchor = max(anchor, date.fromisoformat(str(frontmatter["created_on"])))
    return (current - anchor).days
```

And extend `_build_facts`'s returned `DiligenceFacts(...)` with:

```python
        sessions_logged_last_week=_sessions_logged_last_week(base_dir, current),
        days_since_loads_review=_days_since_loads_review(base_dir, current),
        days_since_watch_anchor=_days_since_watch_anchor(base_dir, current),
```

Also update the `list_due_actions` tool docstring in `src/performance_agent/server/memory_tools.py` (lines 564-577): extend the surfaced list with `a finished training week that never got its loads review, and a program unaudited for two weeks (program watch)`.

- [x] **Step 4: Run** — `uv run pytest tests/engine/test_diligence.py tests/memory/ tests/server/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/engine/diligence.py src/performance_agent/memory/diligence.py src/performance_agent/server/memory_tools.py tests/engine/test_diligence.py
git commit -m "Surface loads-review and program-watch due actions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Phase 2 gate

- [x] Run: `uv run pytest -q && uv run ruff check src tests && uv run ty check` — Expected: all green, zero warnings.

---

## Phase 3 — Science in the deliverables

### Task 11: `Guidance` schema + `ProgramPlan.advice` / `rationale`

**Files:**
- Modify: `src/performance_agent/memory/schemas.py` (insert `Guidance` right BEFORE `class ProgramPlan` at line ~456; add two fields to `ProgramPlan`)
- Test: `tests/memory/test_schemas_progression.py` (append)

- [x] **Step 1: Write the failing test** (append to `tests/memory/test_schemas_progression.py`)

```python
def test_program_plan_carries_optional_guidance():
    from datetime import date

    from performance_agent.memory.schemas import (
        Fallbacks,
        Guidance,
        Mesocycle,
        ProgramPlan,
        SessionPlan,
        WeekPlan,
    )

    week = WeekPlan(
        week_index=1,
        volume_factor=1.0,
        intensity_factor=1.0,
        sessions=[
            SessionPlan(
                id="a",
                qualities=["strength_heavy"],
                est_minutes=60,
                purpose="Upper",
                blocks=[
                    ExerciseBlock(
                        exercise="Bench press",
                        priority="primary",
                        sets=3,
                        reps="8",
                        load_kg=80,
                        progression_rule="hold",
                    )
                ],
                fallbacks=Fallbacks(
                    low_readiness="halve", short_on_time="cut", missing_equipment="dumbbells"
                ),
            )
        ],
    )
    plan = ProgramPlan(
        version=1,
        goal_id="g",
        created_on=date(2026, 7, 17),
        mesocycles=[Mesocycle(index=1, phase="accumulation", weeks=[week])],
        advice=[Guidance(text="Creatine 5 g/day.", cite="creatine-2017")],
        rationale=[Guidance(text="12-16 hard sets per muscle per week.")],
    )
    assert plan.advice[0].cite == "creatine-2017"
    assert plan.rationale[0].cite is None
    bare = plan.model_copy(update={"advice": [], "rationale": []})
    assert bare.advice == []
```

- [x] **Step 2: Run** — `uv run pytest tests/memory/test_schemas_progression.py -q` — Expected: FAIL (`ImportError: Guidance`)

- [x] **Step 3: Implement** — in `src/performance_agent/memory/schemas.py`, insert before `class ProgramPlan`:

```python
class Guidance(BaseModel):
    """One header guidance line: advice or program rationale, optionally cited.

    cite is a corpus id (same semantics as ExerciseBlock.cite). Without one the
    line must read as coaching judgment — never a fake citation.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    cite: str | None = None
```

and add to `ProgramPlan` after `test_milestones`:

```python
    advice: list[Guidance] = Field(default_factory=list)
    rationale: list[Guidance] = Field(default_factory=list)
```

- [x] **Step 4: Run** — `uv run pytest tests/memory/ -q` — Expected: PASS (old plan.yaml files load: both fields default)

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas_progression.py
git commit -m "Add Guidance advice/rationale to ProgramPlan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 12: `resolve_citations` + `plan_citation_ids`

**Files:**
- Modify: `src/performance_agent/evidence/citations.py`
- Modify: `src/performance_agent/programs/render.py` (add `plan_citation_ids` only, rendering comes in Task 13)
- Test: `tests/evidence/test_citations_resolution.py`

- [x] **Step 1: Write the failing tests**

Create `tests/evidence/test_citations_resolution.py`:

```python
"""Corpus-id resolution for deliverable bibliographies."""

import pytest

from performance_agent.evidence.citations import resolve_citations
from performance_agent.evidence.corpus import load_corpus


def test_resolves_known_ids_with_stars(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    entry = load_corpus()[0]
    resolved = resolve_citations([entry.id])
    citation = resolved[entry.id]
    assert entry.title in citation.citation
    assert "★" in citation.stars


def test_unknown_id_is_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="phantom-id"):
        resolve_citations(["phantom-id"])


def test_plan_citation_ids_orders_and_dedupes():
    from datetime import date

    from performance_agent.memory.schemas import (
        ExerciseBlock,
        Fallbacks,
        Guidance,
        Mesocycle,
        ProgramPlan,
        SessionPlan,
        WeekPlan,
    )
    from performance_agent.programs.render import plan_citation_ids

    def block(cite):
        return ExerciseBlock(
            exercise="Bench press",
            priority="primary",
            sets=3,
            reps="8",
            load_kg=80,
            progression_rule="hold",
            cite=cite,
        )

    plan = ProgramPlan(
        version=1,
        goal_id="g",
        created_on=date(2026, 7, 17),
        advice=[Guidance(text="Creatine.", cite="id-a")],
        rationale=[Guidance(text="Volume.", cite="id-b"), Guidance(text="Judgment.")],
        mesocycles=[
            Mesocycle(
                index=1,
                phase="accumulation",
                weeks=[
                    WeekPlan(
                        week_index=1,
                        volume_factor=1.0,
                        intensity_factor=1.0,
                        sessions=[
                            SessionPlan(
                                id="a",
                                qualities=["strength_heavy"],
                                est_minutes=60,
                                purpose="Upper",
                                blocks=[block("id-c"), block("id-a")],
                                fallbacks=Fallbacks(
                                    low_readiness="halve",
                                    short_on_time="cut",
                                    missing_equipment="dumbbells",
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )
    assert plan_citation_ids(plan) == ["id-a", "id-b", "id-c"]
```

- [x] **Step 2: Run** — `uv run pytest tests/evidence/test_citations_resolution.py -q` — Expected: FAIL (`ImportError: resolve_citations`)

- [x] **Step 3: Implement**

In `src/performance_agent/evidence/citations.py`, add imports for `dataclass` and the corpus loader, then append:

```python
from dataclasses import dataclass

from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.schemas import STARS
```

(merge with the file's existing imports — `STARS` and `format_citation` may already be imported/defined there; keep one import of each)

```python
@dataclass(frozen=True)
class ResolvedCitation:
    """A corpus id rendered for a deliverable bibliography."""

    citation: str
    stars: str
    doi: str | None
    pmid: str | None


def resolve_citations(ids: "Iterable[str]") -> dict[str, ResolvedCitation]:
    """Resolve corpus ids to formatted citations; unknown ids are a hard error.

    This is the render-side anti-fabrication lock for structured plans: a plan
    whose advice/rationale/blocks cite an id that is not in the corpus refuses
    to save.
    """
    entries = {entry.id: entry for entry in load_corpus()}
    wanted = list(dict.fromkeys(ids))
    unknown = [cid for cid in wanted if cid not in entries]
    if unknown:
        msg = f"citation ids not in the evidence corpus: {unknown}"
        raise ValueError(msg)
    return {
        cid: ResolvedCitation(
            citation=format_citation(entries[cid]),
            stars=STARS[entries[cid].evidence_level],
            doi=entries[cid].doi,
            pmid=entries[cid].pmid,
        )
        for cid in wanted
    }
```

(add `from collections.abc import Iterable` to the imports; adjust the annotation to `Iterable[str]` unquoted)

In `src/performance_agent/programs/render.py`, append:

```python
def plan_citation_ids(plan: ProgramPlan) -> list[str]:
    """Every corpus id the plan cites, in order of first appearance, deduplicated.

    Order: advice, then rationale, then blocks in program order — this is the
    [n] numbering of the HTML page and the Sources section.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def add(cite: str | None) -> None:
        if cite and cite not in seen:
            seen.add(cite)
            ids.append(cite)

    for guidance in (*plan.advice, *plan.rationale):
        add(guidance.cite)
    for meso in plan.mesocycles:
        for week in meso.weeks:
            for session in week.sessions:
                for block in session.blocks:
                    add(block.cite)
    return ids
```

- [x] **Step 4: Run** — `uv run pytest tests/evidence/ tests/programs/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/evidence/citations.py src/performance_agent/programs/render.py tests/evidence/test_citations_resolution.py
git commit -m "Resolve plan citation ids against the corpus

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 13: Render guidance + bibliography (markdown and HTML)

**Files:**
- Modify: `src/performance_agent/programs/render.py`
- Modify: `src/performance_agent/programs/render_html.py`
- Test: `tests/programs/test_render.py`, `tests/programs/test_render_html.py` (append)

- [x] **Step 1: Write the failing tests** (append to `tests/programs/test_render_html.py`; reuse that file's existing plan fixture/helpers if one exists, otherwise build the same minimal plan as in Task 12's test with `advice=[Guidance(text="Creatine 5 g/day.", cite="id-a")]`, one block citing `"id-a"`, and `citations={"id-a": ResolvedCitation(citation="Kreider et al. (2017). ISSN position stand.", stars="★★★★★", doi="10.1186/s12970-017-0173-z", pmid=None)}` — import `ResolvedCitation` from `performance_agent.evidence.citations`):

```python
def test_html_renders_banner_markers_and_bibliography():
    page = render_program_html(_guidance_plan(), locale="en", citations=_CITATIONS)
    assert "Advice" in page and "Creatine 5 g/day." in page
    assert "[1]" in page  # marker on the advice line and the citing block
    assert "Sources" in page and "★★★★★" in page
    assert "https://doi.org/10.1186/s12970-017-0173-z" in page


def test_html_without_guidance_or_citations_is_unchanged_shape():
    page = render_program_html(_bare_plan(), locale="en")
    assert "Sources" not in page and "Advice" not in page


def test_html_localizes_banner_titles_in_french():
    page = render_program_html(_guidance_plan(), locale="fr", citations=_CITATIONS)
    assert "Conseils" in page and "Pourquoi ce programme" in page
```

And append to `tests/programs/test_render.py`:

```python
def test_markdown_renders_guidance_and_sources():
    from performance_agent.evidence.citations import ResolvedCitation
    from performance_agent.programs.render import render_program

    citations = {
        "id-a": ResolvedCitation(
            citation="Kreider et al. (2017). ISSN position stand.",
            stars="★★★★★",
            doi="10.1186/s12970-017-0173-z",
            pmid=None,
        )
    }
    text = render_program(_guidance_plan(), citations=citations)
    assert "## Advice" in text
    assert "Creatine 5 g/day. [id-a]" in text
    assert "## Sources" in text
    assert "DOI: 10.1186/s12970-017-0173-z" in text


def test_markdown_without_citations_matches_legacy_output():
    text = render_program(_bare_plan())
    assert "## Sources" not in text and "## Advice" not in text
```

(define `_guidance_plan()` / `_bare_plan()` helpers once at the bottom of each test file — same construction as Task 12's test plan, with and without advice/rationale/cites)

- [x] **Step 2: Run** — `uv run pytest tests/programs/ -q` — Expected: FAIL (unexpected keyword `citations`)

- [x] **Step 3: Implement**

`src/performance_agent/programs/render.py`:

1. Add import: `from performance_agent.evidence.citations import ResolvedCitation` and `from collections.abc import Mapping`.
2. Add after `_header_lines`:

```python
def _guidance_lines(plan: ProgramPlan) -> list[str]:
    lines: list[str] = []
    for title, items in (("Advice", plan.advice), ("Why this program", plan.rationale)):
        if not items:
            continue
        lines += ["", f"## {title}"]
        for guidance in items:
            suffix = f" [{guidance.cite}]" if guidance.cite else ""
            lines.append(f"- {guidance.text}{suffix}")
    return lines


def _sources_lines(plan: ProgramPlan, citations: Mapping[str, ResolvedCitation]) -> list[str]:
    ids = [cid for cid in plan_citation_ids(plan) if cid in citations]
    if not ids:
        return []
    lines = ["", "## Sources"]
    for number, cid in enumerate(ids, start=1):
        resolved = citations[cid]
        lines.append(f"{number}. {resolved.stars} {resolved.citation}")
    return lines
```

3. Change `render_program` to:

```python
def render_program(
    plan: ProgramPlan, citations: Mapping[str, ResolvedCitation] | None = None
) -> str:
    """Render a ProgramPlan to the human markdown view (deterministic).

    citations maps corpus ids to their resolved rendering; when provided the
    advice/rationale sections and a final Sources section are emitted (the
    Sources DOIs are what the Typst PDF bibliography picks up).
    """
    lines = _header_lines(plan)
    lines += _guidance_lines(plan)
    for meso in plan.mesocycles:
        lines += ["", f"## Mesocycle {meso.index} — {meso.phase}"]
        for week in meso.weeks:
            lines.append("")
            lines.extend(_week_lines(week))
    if citations is not None:
        lines += _sources_lines(plan, citations)
    return "\n".join(lines).strip() + "\n"
```

Note `format_citation` already renders `DOI: <doi>` inside `citation`, which is exactly what the PDF's `_citations_for` scans for.

`src/performance_agent/programs/render_html.py`:

1. Imports: add `from collections.abc import Mapping` and `from performance_agent.evidence.citations import ResolvedCitation` and extend the render import line to `from performance_agent.programs.render import intensity_label, num_label, plan_citation_ids, volume_label`.
2. Add to every `_LABELS` locale dict:
   - en: `"advice": "Advice", "why_program": "Why this program", "sources": "Sources",`
   - fr: `"advice": "Conseils", "why_program": "Pourquoi ce programme", "sources": "Sources",`
   - es: `"advice": "Consejos", "why_program": "Por qué este programa", "sources": "Fuentes",`
3. Add to `_CSS`:

```css
.guidance { margin: 0.75rem 0 0; }
.guidance h2 { margin: 0.75rem 0 0.25rem; font-size: 1rem; }
.guidance ul { margin: 0.25rem 0 0 1.1rem; padding: 0; }
.guidance li { margin: 0.2rem 0; }
sup.cite { color: var(--accent); font-weight: 600; }
section.sources ol { padding-left: 1.2rem; }
section.sources li { margin: 0.35rem 0; font-size: 0.9rem; }
section.sources .stars { color: var(--accent); letter-spacing: 0.05em; }
```

4. New helpers (after `_header_html`):

```python
def _marker(numbers: dict[str, int], cite: str | None) -> str:
    if cite is None or cite not in numbers:
        return ""
    return f'<sup class="cite">[{numbers[cite]}]</sup>'


def _guidance_html(plan: ProgramPlan, numbers: dict[str, int], locale: str) -> str:
    sections = []
    for key, emoji, items in (
        ("advice", "💊", plan.advice),
        ("why_program", "🔬", plan.rationale),
    ):
        if not items:
            continue
        rows = "".join(
            f"<li>{html.escape(g.text)}{_marker(numbers, g.cite)}</li>" for g in items
        )
        sections.append(f"<h2>{emoji} {_t(locale, key)}</h2><ul>{rows}</ul>")
    if not sections:
        return ""
    return f'<div class="guidance">{"".join(sections)}</div>'


def _sources_html(
    plan: ProgramPlan,
    citations: Mapping[str, ResolvedCitation],
    numbers: dict[str, int],
    locale: str,
) -> str:
    ordered = sorted(
        (cid for cid in numbers if cid in citations), key=lambda cid: numbers[cid]
    )
    if not ordered:
        return ""
    rows = []
    for cid in ordered:
        resolved = citations[cid]
        link = (
            f' <a href="https://doi.org/{html.escape(resolved.doi)}">DOI</a>'
            if resolved.doi
            else ""
        )
        rows.append(
            f'<li><span class="stars">{resolved.stars}</span> '
            f"{html.escape(resolved.citation)}{link}</li>"
        )
    return (
        f'<section class="sources"><h2>📚 {_t(locale, "sources")}</h2>'
        f"<ol>{''.join(rows)}</ol></section>"
    )
```

5. In `_block_html`, thread `numbers: dict[str, int]` through (`_block_html(session, block, catalog, locale, numbers)`) and change the `<h4>` line to:

```python
        f'<h4>{name}{_marker(numbers, block.cite)} <span class="prio">[{block.priority}]</span></h4>',
```

Update `_session_html` and `_week_html` signatures to accept and pass `numbers` down (they only forward it).

6. Change `render_program_html`:

```python
def render_program_html(
    plan: ProgramPlan,
    locale: str = "en",
    index: ExerciseMediaIndex | None = None,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str:
```

Inside, before the mesocycle loop compute `numbers = {cid: i for i, cid in enumerate(plan_citation_ids(plan), start=1)} if citations else {}`, pass `numbers` to `_week_html`, insert `_guidance_html(plan, numbers, locale)` right after `_header_html(plan, locale)` in the final f-string, and insert `_sources_html(plan, citations or {}, numbers, locale)` between the sections and `credit`.

- [x] **Step 4: Run** — `uv run pytest tests/programs/ -q` — Expected: PASS, including the pre-existing golden test (bare plans render byte-identically).

- [x] **Step 5: Commit**

```bash
uv run ruff check src/performance_agent/programs tests/programs
git add src/performance_agent/programs/render.py src/performance_agent/programs/render_html.py tests/programs/
git commit -m "Render advice, rationale and starred bibliography in program views

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 14: Wire citations through `save_program`

**Files:**
- Modify: `src/performance_agent/memory/store.py` (`save_program` signature)
- Modify: `src/performance_agent/server/memory_tools.py` (`save_program`, `_write_program_html`)
- Test: `tests/server/test_memory_tools.py` (append)

- [x] **Step 1: Write the failing tests** (append to `tests/server/test_memory_tools.py`, reusing that file's existing athlete-dir fixture pattern — it already tests `save_program`; follow its plan-building helper. New tests):

```python
def test_save_program_rejects_unknown_cite(athlete_dir):
    plan = _minimal_plan()  # the file's existing helper for a valid one-block plan
    plan = plan.model_copy(
        update={"advice": [Guidance(text="Creatine 5 g/day.", cite="phantom-id")]}
    )
    with pytest.raises(ValueError, match="phantom-id"):
        memory_tools.save_program(plan)


def test_save_program_with_corpus_cite_renders_sources(athlete_dir):
    from performance_agent.evidence.corpus import load_corpus

    real_id = load_corpus()[0].id
    plan = _minimal_plan().model_copy(
        update={"advice": [Guidance(text="Backed advice.", cite=real_id)]}
    )
    result = memory_tools.save_program(plan)
    markdown = memory_tools.read_program(result["version"])["markdown"]
    assert "## Sources" in markdown
    html_page = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "Sources" in html_page
```

(adapt helper names to what the file actually defines; import `Guidance` and `Path` at the top with the file's imports)

- [x] **Step 2: Run** — `uv run pytest tests/server/test_memory_tools.py -q` — Expected: FAIL (no Sources section / no rejection)

- [x] **Step 3: Implement**

`src/performance_agent/memory/store.py` — extend `save_program`:

```python
def save_program(
    base_dir: Path,
    plan: ProgramPlan,
    reason: str | None = None,
    today: date | None = None,
    citations: "Mapping[str, ResolvedCitation] | None" = None,
) -> tuple[Path, int]:
```

with imports `from collections.abc import Mapping` and `from performance_agent.evidence.citations import ResolvedCitation`, and the render line becomes:

```python
    content = (
        "---\n"
        + _to_yaml(frontmatter)
        + "---\n\n"
        + render_program(stamped, citations=citations).strip()
        + "\n"
    )
```

(docstring: add `citations maps the plan's corpus ids to their resolved rendering; the server resolves them — None keeps the legacy citation-less rendering for direct store users.`)

`src/performance_agent/server/memory_tools.py`:

1. Imports: `from performance_agent.evidence.citations import ResolvedCitation, resolve_citations` and `from performance_agent.programs.render import plan_citation_ids` and `from collections.abc import Mapping`.
2. `_write_program_html` gains a `citations` parameter:

```python
def _write_program_html(
    base: Path,
    md_path: Path,
    version: int,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str | None:
```

and the render call becomes `render_program_html(program.plan, locale=locale, index=index, citations=citations)`.

3. `save_program` resolves before writing anything:

```python
def save_program(plan: ProgramPlan, reason: str | None = None) -> ProgramSaved:
    base = resolve_athlete_dir()
    citations = resolve_citations(plan_citation_ids(plan))
    path, version = store.save_program(base, plan, reason, citations=citations)
    html_path = _write_program_html(base, path, version, citations)
    return ProgramSaved(path=str(path), version=version, html_path=html_path)
```

and extend its docstring with: `Every cite on advice/rationale/blocks must be a real corpus id — an unknown id aborts the save before anything is written (anti-fabrication).`

- [x] **Step 4: Run** — `uv run pytest tests/server/ tests/memory/ tests/programs/ -q` — Expected: PASS

- [x] **Step 5: Commit + phase gate**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ty check
git add src/performance_agent/memory/store.py src/performance_agent/server/memory_tools.py tests/server/test_memory_tools.py
git commit -m "Resolve and render plan citations at save time

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 4 — Skills

### Task 15: New skill `next-week-loads`

**Files:**
- Create: `skills/next-week-loads/SKILL.md`

- [x] **Step 1: Write the skill**

```markdown
---
name: next-week-loads
description: Use when the athlete has logged their training week (or the loads_review
  due action fires) and wants next week's working weights. Presents the engine's
  deterministic suggestions block by block and never modifies the program.
tools: [read_athlete, get_time_context, read_program, read_sessions,
  suggest_next_week_loads]
---

# Next week's loads

The weekly review ritual: the athlete finished their training week, the logs are
in — hand them next week's numbers. All math is engine math: this skill quotes
`suggest_next_week_loads`, it never invents a load and it NEVER versions the
program (structure changes belong to program-adaptation).

## Ritual

1. Open with `read_athlete` + `get_time_context` (quote its dates, never compute
   your own). `read_program` for the active version.
2. Call `suggest_next_week_loads`. Present the verdicts as a compact per-session
   table in the athlete's locale: exercise, what they did, next load, and the
   engine's rationale_key rendered as a sentence ("all sets at the top of the
   range — +2.5 kg").
3. Flags are conversations, not errors:
   - `no_rule` — the block predates structured progression: agree the next load
     with the athlete conversationally, from their logs (`read_sessions` for
     context), and say plainly it is coaching judgment.
   - `failed_sets` / `no_logged_sets` / `no_rir_logged` / `no_e1rm` /
     `ambiguous_reps` — say what is missing and what would unlock the number.
   - `clamped` — the autoregulated jump was capped at ±10% for safety; say so.
   - `no_matched_week` — the logs don't map to any program week; ask what
     actually happened this week.
4. Repeated `failed_sets` on the same exercise, pain mentions, or a stalled lift
   are NOT solved here: name the signal and route to program-adaptation (and to
   program-watch when the athlete wants the full audit).
5. `last_week` flag: the program just ended — route to training-checkin /
   program-planning for what comes next.

Numbers are quoted, never negotiated upward past the engine's suggestion; the
athlete can always choose LESS than suggested.
```

- [x] **Step 2: Verify structure** — Run: `uv run pytest tests/skills/ -q` — Expected: FAIL on `test_all_expected_skills_exist` (new skill not in EXPECTED_SKILLS — fixed in Task 17; the OTHER skills tests must not fail). If `test_tool_references` fails here, a declared tool name is wrong — fix the frontmatter now.

- [x] **Step 3: Commit**

```bash
git add skills/next-week-loads/SKILL.md
git commit -m "Add next-week-loads skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 16: New skill `program-watch`

**Files:**
- Create: `skills/program-watch/SKILL.md`

- [x] **Step 1: Write the skill**

```markdown
---
name: program-watch
description: Use every two weeks, at each mesocycle boundary, or on demand to audit
  whether the running program is working exercise by exercise. Produces a keep /
  watch / substitution-candidate verdict per exercise and never edits anything.
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
  compare_prescribed_actual, estimate_1rm, compute_weekly_loads,
  compute_monotony_strain, score_exercises, get_citation, save_watch_report]
---

# Program watch

The running program's auditor. Data only, per exercise — the question is never
"is the athlete tired" (training-checkin owns that) but "is THIS exercise doing
its job". Designed to run as a subagent launched by performance-coach or
training-checkin: audit silently, come back with a short report.

## Signals, per exercise

1. Open with `read_athlete` + `get_time_context` (quote its dates), then
   `read_program`, `read_sessions`, `read_checkins` over the current mesocycle.
2. Trajectory — best sets per exercise through `estimate_1rm`: is the estimated
   1RM (or pace at heart rate, via compare_prescribed_actual, for endurance
   blocks) moving the way the block intends?
3. Adherence — an exercise systematically skipped or cut short is a signal about
   THAT exercise (friction, equipment, quiet pain), not laziness.
4. Pain — pain_flags and session notes that recur around one movement.
5. Chronic gap — compare_prescribed_actual: prescribed vs done, week after week.
6. Load shape — compute_weekly_loads + compute_monotony_strain when the pattern
   suggests a structural problem (everything hard, nothing varied).

## Verdict and report

Per audited exercise: **keep** (working — say why in one line), **watch** (name
the signal and the check for next time), or **substitution candidate** (name the
signal, propose 1-2 replacements via score_exercises, cite corpus evidence with
get_citation when one backs the swap — otherwise label it coaching judgment).

Write the report with save_watch_report (goal_id from the program; v2+ reason =
the trigger: "biweekly watch", "mesocycle boundary", "athlete request"). Keep it
short: verdicts first, data behind them after.

## Hard boundary

This skill NEVER edits the program, never prescribes, never substitutes in
place. Substitution candidates route to program-adaptation, which owns the
diagnosis conversation, the versioned save and the program-review gate. At a
mesocycle boundary, pair with deep-research's incremental watch: this report
says what to watch, the research says what the science says.
```

- [x] **Step 2: Verify** — Run: `uv run pytest tests/skills/test_tool_references.py -q` — Expected: only `test_all_expected_skills_exist`-style failures from test_structure (fixed next task); tool references must PASS for this file.

- [x] **Step 3: Commit**

```bash
git add skills/program-watch/SKILL.md
git commit -m "Add program-watch skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 17: Edit the seven existing skills + test invariants

**Files:**
- Modify: `skills/deep-research/SKILL.md`, `skills/program-adaptation/SKILL.md`, `skills/training-checkin/SKILL.md`, `skills/performance-coach/SKILL.md`, `skills/athlete-onboarding/SKILL.md`, `skills/program-optimization/SKILL.md`, `skills/program-review/SKILL.md`
- Modify: `tests/skills/test_structure.py`

- [x] **Step 1: Update `tests/skills/test_structure.py` first (failing invariants drive the edits)**

Add to `EXPECTED_SKILLS`: `"next-week-loads", "program-watch",`

Append two protocol tests:

```python
def test_next_week_loads_skill_protocol(skills):
    loads = next(s for s in skills if s.frontmatter["name"] == "next-week-loads")
    body = loads.body.casefold()
    for needle in (
        "suggest_next_week_loads",
        "read_program",
        "never versions the program",
        "no_rule",
        "failed_sets",
        "clamped",
        "program-adaptation",
        "coaching judgment",
    ):
        assert needle in body, f"next-week-loads skill lost: {needle}"


def test_program_watch_skill_protocol(skills):
    watch = next(s for s in skills if s.frontmatter["name"] == "program-watch")
    body = watch.body.casefold()
    for needle in (
        "save_watch_report",
        "compare_prescribed_actual",
        "estimate_1rm",
        "score_exercises",
        "keep",
        "watch",
        "substitution candidate",
        "never edits the program",
        "program-adaptation",
        "subagent",
    ):
        assert needle in body, f"program-watch skill lost: {needle}"
```

And extend three existing protocol tests with new needles (append to each tuple):
- `test_research_skill_protocol`: `"list_athlete_documents"`, `"mini-wave"`, `"year_from"`
- `test_adaptation_skill_protocol`: `"mini-wave"`, `"read_research_dossier"`, `"adapt first"`
- `test_checkin_skill_protocol`: `"list_athlete_documents"`, `"mesocycle boundary"`

Run: `uv run pytest tests/skills/ -q` — Expected: FAIL on exactly these invariants (that's the worklist).

- [x] **Step 2: `skills/deep-research/SKILL.md`**

Frontmatter: add `list_athlete_documents, mark_document_processed, verify_reference` to `tools` (keep existing entries; `verify_reference` is already declared — do not duplicate).

Insert as the FIRST protocol section (before the current facet-decomposition section):

```markdown
## 0. The athlete's own documents — always first

Before any online search, call `list_athlete_documents`. For every `new` or
`modified` file: read it (the tool hands you the absolute path; paginate large
PDFs). Then route it into exactly one lane and record it with
`mark_document_processed`:

- **evidence** — ONLY when the document carries a DOI/PMID/ISBN that resolves
  via `verify_reference`. Save it with `save_evidence` under the registry's
  canonical title (you read the full text — conclusions may be richer than an
  abstract-only entry), then mark with the corpus ids in `evidence_ids`.
- **context** — everything else (physio reports, lab results, past programs,
  unverifiable PDFs): summarize what matters for coaching into `summary` and
  `key_points`. It informs personalization and the facets below, but it is
  NEVER cited as science in any deliverable.
- **unreadable** — corrupt or unopenable; mark it so you stop retrying.

What the documents claim shapes the facets: a dropped study on a facet joins
that facet's evidence; a physio report adds a constraint facet.
```

Append at the end of the file:

```markdown
## Mini-waves and the incremental watch

A **mini-wave** is this protocol scoped to ONE question: corpus first, then 2-3
live queries in English + the athlete's locale (+1 language if thin), same
verification and save rules, folded into the dossier as v+1 whose reason names
the trigger, with a "what changed vs v{N}" section. Program-adaptation runs
mini-waves for substantive triggers; run one directly when the athlete drops a
document or asks a question that touches one facet.

The **incremental watch** (each mesocycle boundary, routed by training-checkin):
replay the dossier facets' queries with `year_from` set to the current dossier's
year — thin facets first. Something new → dossier v+1; nothing → no new version,
say so in one line.
```

- [x] **Step 3: `skills/program-adaptation/SKILL.md`**

Frontmatter: add `read_research_dossier, save_research_dossier` to `tools`.

Insert a new section after the diagnosis section (before citation repair):

```markdown
## Research refresh — the mini-wave

**Adapt first, research second**: tonight's session never waits for literature.
When the trigger is substantive — a confirmed plateau, recurring pain, a
calendar or method change — run a mini-wave AFTER the immediate fix is agreed:

1. `read_research_dossier` for what the dossier already says on the question.
2. One question, 2-3 live queries (English + locale, +1 language if thin), the
   deep-research verification and save rules unchanged.
3. Fold what you learned into the dossier with `save_research_dossier` (v+1,
   reason = the trigger, with a "what changed" section).
4. If the finding contradicts the ACTIVE program, propose the sourced change to
   the athlete through this skill's normal versioned flow — never edit silently.
```

- [x] **Step 4: `skills/training-checkin/SKILL.md`**

Frontmatter: add `list_athlete_documents` to `tools`.

Add to the opening ritual (where the skill lists its opening calls, right after the due-actions step):

```markdown
- `list_athlete_documents`: new or modified files in the drop folder are part of
  the check-in — acknowledge them, and route to deep-research §0 to process
  them (a physio report may change today's plan).
```

Add a section before the routing/trigger section:

```markdown
## Mesocycle boundary duties

When this check-in crosses into a new mesocycle (compare today against the
program's week boundaries): (1) route to deep-research's incremental watch —
replay the dossier facets with year_from = the dossier's year, thin facets
first; (2) route to program-watch for the per-exercise audit. The
loads_review and program_watch due actions surface both when overdue — treat
them like any other due action: open with them.
```

- [x] **Step 5: `skills/performance-coach/SKILL.md`**

Frontmatter: add `list_athlete_documents` to `tools`.

In the opening ritual (after the `list_due_actions` step), add:

```markdown
- `list_athlete_documents` — dropped files are messages: acknowledge new ones
  and have them processed (deep-research §0) before they go stale.
```

In the routing table/section, add two rows/lines:

```markdown
- Training week logged, athlete wants next week's weights, or the loads_review
  action fires → **next-week-loads**.
- Two weeks since the last audit, a mesocycle boundary, or "is this program
  still right?" → **program-watch** (run it as a subagent; bring back verdicts).
```

- [x] **Step 6: `skills/athlete-onboarding/SKILL.md`**

Add one line to the closing/wrap-up section (no tool changes — write_profile creates the folder):

```markdown
Tell the athlete about their `documentation/` folder (created with the
profile): studies, physio or medical reports, lab results, past programs
dropped there are picked up automatically at the next conversation.
```

- [x] **Step 7: `skills/program-optimization/SKILL.md`**

In the block-construction section (where per-block fields are specified), add:

```markdown
Every load-bearing block (load_kg, pct_1rm or rir intensity) carries a
STRUCTURED `progression` rule alongside the prose `progression_rule`: kind
`double` (rep_min/rep_max/increment_kg), `linear_load` (increment_kg),
`rir_target` (target_rir), `from_pct` (percent-planned weeks), or `none`
(pace/technique blocks). The prose is the human rendering of the structured
rule — write both from the same decision. This is what powers the weekly
loads review; a block left unstructured surfaces as `no_rule` every week.
```

In the section where the program document is assembled (before save_program), add:

```markdown
Fill the plan's `advice` (nutrition, supplements, recovery — the frame's
numbers from read_nutrition_frame become athlete-facing lines here) and
`rationale` ("why this program" — the 3-5 decisions that shaped it). Every
line either carries a corpus `cite` (rendered with stars in the HTML header
and bibliography) or reads as coaching judgment. save_program refuses unknown
cite ids — never invent one.
```

- [x] **Step 8: `skills/program-review/SKILL.md`**

Add to the deterministic compliance checklist:

```markdown
- Structured progression: every block prescribing load_kg, pct_1rm or rir has a
  `progression` rule whose kind matches the prescription (a pct_1rm block with
  kind=double is an objection); the prose progression_rule tells the same story.
- Guidance honesty: every advice/rationale line either cites a corpus id
  (verify each with get_citation) or is phrased as coaching judgment; dosage
  claims without a cite are an objection.
```

- [x] **Step 9: Run the full skills suite** — `uv run pytest tests/skills/ -q` — Expected: PASS (structure, tool references, protocols, no fabricated refs). If `test_bodies_do_not_reference_undeclared_tools` fails, a body mentions a tool missing from its frontmatter — add it to `tools`.

- [x] **Step 10: Commit**

```bash
git add skills/ tests/skills/test_structure.py
git commit -m "Wire documents, mini-waves and weekly follow-up into the skills

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 18: README + final gate

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update README** — locate the tool count (search for `93`) and update to **97**; in the feature list add four bullets in the repo's existing bullet style:

```markdown
- **Athlete document drop folder** — drop studies, physio reports or past
  programs into `documentation/`; verified studies join the evidence corpus
  (full text read), everything else informs coaching as context, never faked
  as science.
- **Research that stays alive** — targeted mini-waves on plateaus, injuries and
  athlete questions; an incremental literature watch at every mesocycle
  boundary (`year_from` delta queries), all folded into the versioned dossier.
- **Weekly loads review** — structured per-block progression rules computed by
  the engine (`suggest_next_week_loads`): next week's exact weights from this
  week's logs, flags instead of guesses.
- **Program watch** — a biweekly per-exercise audit (keep / watch / substitute
  candidate) written as a versioned report; substitutions go through
  program-adaptation, never silently.
- **Science on the gym page** — the offline program HTML opens with sourced
  advice and "why this program" lines, `[n]` markers on blocks, and a starred
  bibliography.
```

- [x] **Step 2: Full suite + linters** — Run: `uv run pytest -q && uv run ruff check src tests && uv run ty check` — Expected: everything green, zero warnings.

- [x] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document the living-evidence and weekly follow-up features

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [x] **Step 4: NOT in this plan** — version bump, CHANGELOG, PyPI release, and the pre-competition spec are separate work.

---

## Plan self-review notes

- Spec coverage: §3 → Tasks 1-4; §4 → Tasks 15-17 (skills only, as specified); §5 → Tasks 5-10; §6 → Tasks 11-14; §7 (errors) → distributed into each module's tests; §8 (testing) → every task is test-first; §9 out-of-scope respected (no PDF extraction, no push, no auto-deload).
- Type consistency: `ScanResult`/`DocumentView`/`ProcessedView` (Tasks 1, 3), `SetActual`/`LoadSuggestion` (Tasks 6, 7), `WeeklyLoadsView`/`BlockSuggestionView` (Tasks 7, 9), `ResolvedCitation` (Tasks 12, 13, 14), `VersionedDocSaved` reused from memory_tools (Task 9) — names match across tasks.
- Known judgment calls an executor may hit: exact insertion anchors inside the seven SKILL.md files are described relationally (the files' section names are stable but not line-numbered here); ruff may reformat long lines — run `uv run ruff format` on touched files before committing.


