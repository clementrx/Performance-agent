# Live Multilingual Evidence Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an athlete's goal falls outside the packaged evidence corpus, the coach
can search PubMed, Crossref and Semantic Scholar across languages, verify what it
finds the same way the packaged corpus is verified, and add it to a personal corpus —
without weakening the existing anti-fabrication guarantee.

**Architecture:** Two new MCP tools (`search_evidence_live`, `save_evidence`, plus a
small `verify_reference` helper tool) sit alongside the existing evidence tools. A new
`evidence/live_search.py` module does the network fan-out; a new
`evidence/personal_corpus.py` module persists verified entries to a per-athlete YAML
file that `evidence/corpus.py::load_corpus()` merges with the packaged corpus at read
time. Every entry that becomes citable — packaged or live-discovered — passes through
the same DOI/PMID resolution and Pydantic grading-ceiling validation.

**Tech Stack:** Python 3.13, stdlib `urllib` for HTTP (no new dependency), existing
`pydantic`/`pyyaml` deps, `mcp` FastMCP tool registration, `pytest` + `monkeypatch` for
network-free tests (matching the existing `evidence/verify.py` test pattern).

**Spec:** `docs/superpowers/specs/2026-07-10-live-evidence-search-design.md`

---

## Before you start

Read these existing files — the plan assumes you understand their current shape:

- `src/performance_agent/evidence/verify.py` — the DOI/PMID resolution logic you'll
  extract and reuse.
- `src/performance_agent/evidence/corpus.py` — `parse_manifest`/`load_corpus`, which
  you'll split and extend.
- `src/performance_agent/evidence/schemas.py` — `EvidenceEntry`, `StudyType`,
  `GRADING_CEILING`. You will not modify this file; every safeguard here already
  applies to whatever you build.
- `src/performance_agent/server/evidence_tools.py` — the MCP tool registration
  pattern (`lru_cache`-backed `_index()`, `TypedDict` return shapes).
- `src/performance_agent/memory/paths.py` — `resolve_athlete_dir()`, which you'll
  reuse unchanged.
- `tests/evidence/test_verify.py` and `tests/evidence/test_corpus.py` — the
  `monkeypatch` test pattern you'll follow for every new network-touching test.

---

### Task 1: Extract `resolve_reference` from `verify.py`

**Files:**
- Modify: `src/performance_agent/evidence/verify.py`
- Modify: `tests/evidence/test_verify.py`

`evidence/verify.py` currently has a private `_fetch_json` and a `verify_entry(entry)`
that only works against a full `EvidenceEntry`. The live-search path needs to resolve
a bare DOI/PMID (no `EvidenceEntry` yet — the entry doesn't exist until the agent
builds one from a candidate). This task extracts that lower-level capability without
changing `verify_entry`'s existing behavior or its tests' meaning.

- [ ] **Step 1: Update the existing tests to the new (public) function name**

`_fetch_json` is renamed to `fetch_json` (it's about to be imported by another
module, so it can't stay private). Update every monkeypatch target in
`tests/evidence/test_verify.py`:

```python
# tests/evidence/test_verify.py
# Replace every occurrence of "_fetch_json" with "fetch_json", e.g.:

def test_doi_resolution_success(monkeypatch):
    payload = {"message": {"title": ["A sample study"]}}
    monkeypatch.setattr(
        verify_module, "fetch_json", lambda url: payload if "crossref" in url else None
    )
    result = verify_entry(_entry())
    assert result.ok
    assert "A sample study" in (result.retrieved_title or "")


def test_doi_resolution_failure(monkeypatch):
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: None)
    result = verify_entry(_entry())
    assert not result.ok
    assert "10.1000/sample" in result.detail


def test_pmid_resolution_success(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}, "uids": ["123456"]}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    entry = _entry(doi=None, pmid="123456")
    result = verify_entry(entry)
    assert result.ok


def test_disjoint_title_reports_mismatch(monkeypatch):
    payload = {"message": {"title": ["A completely unrelated paper about something else"]}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    result = verify_entry(_entry())
    assert not result.ok
    assert "TITLE MISMATCH" in result.detail


def test_subtitle_split_title_matches(monkeypatch):
    payload = {
        "message": {
            "title": ["Effects of Tapering on Performance"],
            "subtitle": ["A Meta-Analysis"],
        }
    }
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    entry = _entry(title="Effects of Tapering on Performance: A Meta-Analysis")
    result = verify_entry(entry)
    assert result.ok
```

(`test_entry_without_locator_cannot_exist` and `test_fetch_json_returns_none_on_non_json_body`
are unchanged — the latter patches `urllib.request.urlopen`, not `_fetch_json`.)

Add new tests for the extracted function at the end of the file:

```python
from performance_agent.evidence.verify import resolve_reference, verify_entry


def test_resolve_reference_via_doi(monkeypatch):
    payload = {"message": {"title": ["A sample study"]}}
    monkeypatch.setattr(
        verify_module, "fetch_json", lambda url: payload if "crossref" in url else None
    )
    resolved = resolve_reference("10.1000/sample", None)
    assert resolved.ok
    assert resolved.title == "A sample study"


def test_resolve_reference_via_pmid(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}}}
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: payload)
    resolved = resolve_reference(None, "123456")
    assert resolved.ok
    assert resolved.title == "A sample study"


def test_resolve_reference_without_locator():
    resolved = resolve_reference(None, None)
    assert not resolved.ok
    assert "no DOI or PMID" in resolved.detail


def test_resolve_reference_doi_does_not_resolve(monkeypatch):
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: None)
    resolved = resolve_reference("10.1000/missing", None)
    assert not resolved.ok
    assert "10.1000/missing" in resolved.detail
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_verify.py -v`
Expected: FAIL — `AttributeError` (`fetch_json` doesn't exist yet) and
`ImportError`/`NameError` for `resolve_reference`.

- [ ] **Step 3: Implement the extraction in `verify.py`**

Replace the body of `src/performance_agent/evidence/verify.py` from the
`_fetch_json` definition through `verify_entry` with:

```python
@dataclass(frozen=True)
class VerificationResult:
    """Outcome of resolving one entry against its source registry."""

    entry_id: str
    ok: bool
    detail: str
    retrieved_title: str | None = None


@dataclass(frozen=True)
class ResolvedReference:
    """Outcome of resolving a bare DOI or PMID against its source registry."""

    ok: bool
    title: str | None
    detail: str


def fetch_json(url: str) -> dict | None:
    """Fetch and parse a JSON response, returning None on any network/parse failure."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _title_from_crossref(payload: dict) -> str | None:
    message = payload.get("message", {})
    titles = message.get("title") or []
    if not titles:
        return None
    subtitles = message.get("subtitle") or []
    return f"{titles[0]} {subtitles[0]}".strip() if subtitles else titles[0]


def _title_from_pubmed(payload: dict, pmid: str) -> str | None:
    return payload.get("result", {}).get(pmid, {}).get("title")


def resolve_reference(doi: str | None, pmid: str | None) -> ResolvedReference:
    """Resolve a bare DOI (preferred) or PMID against Crossref/PubMed.

    Used both by verify_entry (which additionally checks the resolved title against
    a manifest entry's title) and directly by the live-search path, which has no
    EvidenceEntry yet — only a candidate locator to prove is real.
    """
    if doi:
        payload = fetch_json(CROSSREF_URL.format(doi=doi))
        if payload is None:
            return ResolvedReference(False, None, f"DOI did not resolve: {doi}")
        title = _title_from_crossref(payload)
        if title is None:
            return ResolvedReference(False, None, "Crossref returned no title")
        return ResolvedReference(True, title, "resolved via Crossref")
    if pmid:
        payload = fetch_json(PUBMED_URL.format(pmid=pmid))
        if payload is None:
            return ResolvedReference(False, None, f"PMID did not resolve: {pmid}")
        title = _title_from_pubmed(payload, pmid)
        if title is None:
            return ResolvedReference(False, None, "PubMed returned no title")
        return ResolvedReference(True, title, "resolved via PubMed")
    return ResolvedReference(False, None, "no DOI or PMID provided")


def _titles_match(manifest_title: str, registry_title: str) -> bool:
    manifest_tokens = _tokens(manifest_title)
    registry_tokens = _tokens(registry_title)
    if not manifest_tokens or not registry_tokens:
        return False
    overlap = len(manifest_tokens & registry_tokens)
    containment = overlap / min(len(manifest_tokens), len(registry_tokens))
    return containment >= _TITLE_MATCH_THRESHOLD


def _title_result(
    entry: EvidenceEntry, registry_title: str | None, source: str
) -> VerificationResult:
    if registry_title is None:
        return VerificationResult(entry.id, False, f"{source} returned no title")
    if not _titles_match(entry.title, registry_title):
        detail = f"TITLE MISMATCH: manifest={entry.title!r} registry={registry_title!r}"
        return VerificationResult(entry.id, False, detail, registry_title)
    return VerificationResult(entry.id, True, f"resolved via {source}", registry_title)


def verify_entry(entry: EvidenceEntry) -> VerificationResult:
    """Resolve the entry's DOI (preferred) or PMID and assert its title matches the registry."""
    resolved = resolve_reference(entry.doi, entry.pmid)
    if not resolved.ok:
        return VerificationResult(entry.id, False, resolved.detail)
    source = "Crossref" if entry.doi else "PubMed"
    return _title_result(entry, resolved.title, source)
```

`_tokens`, the module constants (`CROSSREF_URL`, `PUBMED_URL`, `_TIMEOUT_S`,
`_USER_AGENT`, `_TITLE_MATCH_THRESHOLD`, `_POLITE_DELAY_S`), and `main()` are
unchanged — leave them as they are.

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_verify.py -v`
Expected: PASS (all tests, including the 4 new ones).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/verify.py tests/evidence/test_verify.py
uv run ruff format src/performance_agent/evidence/verify.py tests/evidence/test_verify.py
git add src/performance_agent/evidence/verify.py tests/evidence/test_verify.py
git commit -m "Extract resolve_reference from verify_entry for reuse by live search"
```

---

### Task 2: Extract `parse_manifest` into its own module

**Files:**
- Create: `src/performance_agent/evidence/manifest.py`
- Modify: `src/performance_agent/evidence/corpus.py`

`corpus.py` will soon need to import from the new `personal_corpus.py`, and
`personal_corpus.py` needs `parse_manifest` too. Moving `parse_manifest` into its own
module (with no dependency on `corpus.py`) avoids a circular import between the two.
`parse_manifest`'s existing tests import it via `performance_agent.evidence.corpus`,
so `corpus.py` re-exports it — no test changes needed in this task.

- [ ] **Step 1: Confirm current tests pass before touching anything**

Run: `uv run pytest tests/evidence/test_corpus.py -v`
Expected: PASS (baseline, so you can tell your refactor didn't break anything).

- [ ] **Step 2: Create `manifest.py` with the moved function**

```python
# src/performance_agent/evidence/manifest.py
"""Parsing for evidence corpus manifests (YAML lists of EvidenceEntry)."""

import yaml

from performance_agent.evidence.schemas import EvidenceEntry


def parse_manifest(text: str) -> list[EvidenceEntry]:
    """Parse manifest YAML into validated entries; ids must be unique."""
    raw = yaml.safe_load(text) or []
    if not isinstance(raw, list):
        msg = "the corpus manifest must be a YAML list of entries"
        raise ValueError(msg)
    entries = [EvidenceEntry.model_validate(item) for item in raw]
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            msg = f"duplicate corpus id: {entry.id}"
            raise ValueError(msg)
        seen.add(entry.id)
    return entries
```

- [ ] **Step 3: Update `corpus.py` to import and re-export it**

Replace the top of `src/performance_agent/evidence/corpus.py` (everything before
`load_corpus`) with:

```python
"""Load and validate the packaged evidence corpus."""

from importlib import resources

from performance_agent.evidence.manifest import parse_manifest
from performance_agent.evidence.schemas import EvidenceEntry

__all__ = ["load_corpus", "parse_manifest"]
```

Leave `load_corpus()` itself unchanged for now (Task 4 modifies it).

- [ ] **Step 4: Run the tests to confirm nothing broke**

Run: `uv run pytest tests/evidence/test_corpus.py -v`
Expected: PASS — `parse_manifest` is still importable from
`performance_agent.evidence.corpus` because of the re-export.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/manifest.py src/performance_agent/evidence/corpus.py
uv run ruff format src/performance_agent/evidence/manifest.py src/performance_agent/evidence/corpus.py
git add src/performance_agent/evidence/manifest.py src/performance_agent/evidence/corpus.py
git commit -m "Extract parse_manifest into its own module"
```

---

### Task 3: Personal corpus storage

**Files:**
- Create: `src/performance_agent/evidence/personal_corpus.py`
- Test: `tests/evidence/test_personal_corpus.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/evidence/test_personal_corpus.py
import pytest

from performance_agent.evidence.personal_corpus import (
    append_entry,
    load_personal_entries,
    personal_corpus_path,
)
from performance_agent.evidence.schemas import EvidenceEntry


def _entry(**overrides) -> EvidenceEntry:
    data = {
        "id": "live-sample",
        "title": "A live-found study",
        "authors": ["Doe J"],
        "year": 2022,
        "study_type": "rct",
        "conclusions": "x",
        "evidence_level": "moderate",
        "doi": "10.1000/live-sample",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


def test_load_personal_entries_empty_when_file_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    assert load_personal_entries() == []


def test_append_entry_creates_file_and_is_loadable(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    path = append_entry(_entry(), known_ids=set())
    assert path == personal_corpus_path()
    assert [e.id for e in load_personal_entries()] == ["live-sample"]


def test_append_entry_rejects_known_id(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="live-sample"):
        append_entry(_entry(), known_ids={"live-sample"})


def test_append_entry_preserves_previous_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    append_entry(_entry(id="live-one", doi="10.1000/one"), known_ids=set())
    append_entry(_entry(id="live-two", doi="10.1000/two"), known_ids={"live-one"})
    assert [e.id for e in load_personal_entries()] == ["live-one", "live-two"]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_personal_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: performance_agent.evidence.personal_corpus`.

- [ ] **Step 3: Implement `personal_corpus.py`**

```python
# src/performance_agent/evidence/personal_corpus.py
"""Storage for evidence entries discovered via live search, kept per-athlete.

This file is never touched by a performance-agent upgrade and never shared with
the packaged corpus in the repo — each athlete grows their own.
"""

import os
from pathlib import Path

import yaml

from performance_agent.evidence.manifest import parse_manifest
from performance_agent.evidence.schemas import EvidenceEntry
from performance_agent.memory.paths import resolve_athlete_dir

PERSONAL_CORPUS_FILE = "evidence_extra.yaml"


def personal_corpus_path() -> Path:
    """Return the path to the athlete's personal evidence corpus file."""
    return resolve_athlete_dir() / PERSONAL_CORPUS_FILE


def load_personal_entries() -> list[EvidenceEntry]:
    """Return the athlete's live-discovered entries, or an empty list if none exist."""
    path = personal_corpus_path()
    if not path.exists():
        return []
    return parse_manifest(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def append_entry(entry: EvidenceEntry, known_ids: set[str]) -> Path:
    """Validate id uniqueness against known_ids and append entry; returns its path.

    known_ids should include every id already in use across BOTH the packaged and
    personal corpus — the caller (save_evidence) is responsible for building that
    set, since this module has no reason to know about the packaged corpus.
    """
    if entry.id in known_ids:
        msg = f"{entry.id}: an entry with this id already exists in the corpus"
        raise ValueError(msg)
    existing = load_personal_entries()
    updated = [*existing, entry]
    path = personal_corpus_path()
    _atomic_write(
        path,
        yaml.safe_dump(
            [e.model_dump(mode="json") for e in updated], sort_keys=False, allow_unicode=True
        ),
    )
    return path
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_personal_corpus.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/personal_corpus.py tests/evidence/test_personal_corpus.py
uv run ruff format src/performance_agent/evidence/personal_corpus.py tests/evidence/test_personal_corpus.py
uv run ty check
git add src/performance_agent/evidence/personal_corpus.py tests/evidence/test_personal_corpus.py
git commit -m "Add per-athlete personal evidence corpus storage"
```

---

### Task 4: Merge the personal corpus into `load_corpus()`

**Files:**
- Modify: `src/performance_agent/evidence/corpus.py`
- Modify: `tests/evidence/test_corpus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_corpus.py`:

```python
def test_load_corpus_merges_personal_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    (tmp_path / "evidence_extra.yaml").write_text(
        """
- id: live-extra
  title: A personally discovered study
  authors: [Roe R]
  year: 2023
  study_type: cohort
  conclusions: Something new.
  evidence_level: moderate
  pmid: "999999"
""",
        encoding="utf-8",
    )
    ids = {e.id for e in load_corpus()}
    assert "live-extra" in ids


def test_load_corpus_without_personal_file_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    ids = {e.id for e in load_corpus()}
    assert "live-extra" not in ids
    assert len(ids) >= 8  # the packaged corpus alone


def test_load_corpus_rejects_id_collision_with_packaged(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    packaged_id = load_corpus()[0].id
    (tmp_path / "evidence_extra.yaml").write_text(
        f"""
- id: {packaged_id}
  title: Colliding id
  authors: [Roe R]
  year: 2023
  study_type: cohort
  conclusions: Something new.
  evidence_level: moderate
  pmid: "999999"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_corpus.py -v`
Expected: FAIL on the three new tests (`load_corpus()` doesn't look at the personal
corpus yet).

- [ ] **Step 3: Implement the merge**

Replace `load_corpus()` in `src/performance_agent/evidence/corpus.py`:

```python
def _packaged_manifest_text() -> str:
    data = resources.files("performance_agent.evidence") / "data" / "seed_corpus.yaml"
    return data.read_text(encoding="utf-8")


def load_corpus() -> list[EvidenceEntry]:
    """Load the packaged corpus shipped inside the package, merged with the

    athlete's own live-discovered entries (evidence/personal_corpus.py). Raises if
    a personal entry's id collides with a packaged one.
    """
    from performance_agent.evidence.personal_corpus import load_personal_entries

    packaged = parse_manifest(_packaged_manifest_text())
    personal = load_personal_entries()
    seen = {entry.id for entry in packaged}
    for entry in personal:
        if entry.id in seen:
            msg = f"duplicate corpus id across packaged and personal corpus: {entry.id}"
            raise ValueError(msg)
        seen.add(entry.id)
    return packaged + personal
```

The import of `load_personal_entries` is deliberately inside the function body:
`personal_corpus.py` doesn't import `corpus.py`, so there's no cycle, but keeping the
import local documents *why* it's not at the top with the others (readers scanning
top-of-file imports won't wonder about a dependency direction that doesn't actually
exist at module-load time).

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_corpus.py -v`
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Run the full evidence test suite to check for regressions**

Run: `uv run pytest tests/evidence/ tests/reports/ -v`
Expected: PASS — `reports/renderer.py` also calls `load_corpus()`; confirm nothing
there broke.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/corpus.py tests/evidence/test_corpus.py
uv run ruff format src/performance_agent/evidence/corpus.py tests/evidence/test_corpus.py
uv run ty check
git add src/performance_agent/evidence/corpus.py tests/evidence/test_corpus.py
git commit -m "Merge personal corpus into load_corpus"
```

---

### Task 5: Live search — PubMed

**Files:**
- Create: `src/performance_agent/evidence/live_search.py`
- Test: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/evidence/test_live_search.py
import performance_agent.evidence.live_search as live_search_module
from performance_agent.evidence.live_search import (
    PUBMED_TYPE_MAP,
    LiveCandidate,
    _map_pubmed_type,
    search_pubmed,
)
from performance_agent.evidence.schemas import StudyType


def test_map_pubmed_type_recognizes_rct():
    assert _map_pubmed_type(["Journal Article", "Randomized Controlled Trial"]) == StudyType.RCT


def test_map_pubmed_type_returns_none_when_unmapped():
    assert _map_pubmed_type(["Journal Article"]) is None


def test_map_pubmed_type_prefers_first_match_in_map_order():
    # "Meta-Analysis" and "Systematic Review" both present; either is a valid strong
    # mapping, so just assert it picked one of them, not None.
    result = _map_pubmed_type(["Systematic Review", "Meta-Analysis"])
    assert result in (StudyType.SYSTEMATIC_REVIEW, StudyType.META_ANALYSIS)


def test_search_pubmed_builds_candidates(monkeypatch):
    esearch_payload = {"esearchresult": {"idlist": ["111", "222"]}}
    esummary_payload = {
        "result": {
            "111": {
                "title": "Javelin biomechanics and throw distance",
                "authors": [{"name": "Doe J"}],
                "pubdate": "2021 Jun",
                "fulljournalname": "J Sports Sci",
                "pubtype": ["Randomized Controlled Trial"],
                "articleids": [{"idtype": "doi", "value": "10.1000/javelin"}],
            },
            "222": {
                "title": "",  # no title -> dropped
                "authors": [],
                "pubdate": "2020",
                "pubtype": [],
                "articleids": [],
            },
        }
    }

    def fake_fetch_json(url: str) -> dict | None:
        return esearch_payload if "esearch" in url else esummary_payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)

    candidates = search_pubmed("javelin throw", "en")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, LiveCandidate)
    assert candidate.pmid == "111"
    assert candidate.doi == "10.1000/javelin"
    assert candidate.suggested_study_type == StudyType.RCT
    assert candidate.source == "pubmed"
    assert candidate.found_via_language == "en"
    assert candidate.year == 2021


def test_search_pubmed_returns_empty_when_no_hits(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": []}}
    )
    assert search_pubmed("nonexistent topic", "en") == []


def test_search_pubmed_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_pubmed("javelin throw", "en") == []
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: FAIL — `ModuleNotFoundError: performance_agent.evidence.live_search`.

- [ ] **Step 3: Implement `live_search.py` (PubMed part)**

```python
# src/performance_agent/evidence/live_search.py
"""Live, verified evidence search across PubMed, Crossref and Semantic Scholar.

Every function here returns raw candidates; nothing is citable until
run_live_search re-verifies each candidate's DOI/PMID via
evidence.verify.resolve_reference — the same check the packaged corpus goes
through in evidence/verify.py before shipping.
"""

import re
from dataclasses import dataclass
from urllib.parse import quote

from performance_agent.evidence.schemas import StudyType
from performance_agent.evidence.verify import fetch_json

PUBMED_ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term={term}&retmode=json&retmax={limit}"
)
PUBMED_ESUMMARY_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json"
)

_SEARCH_LIMIT = 5

PUBMED_TYPE_MAP: dict[str, StudyType] = {
    "Randomized Controlled Trial": StudyType.RCT,
    "Meta-Analysis": StudyType.META_ANALYSIS,
    "Systematic Review": StudyType.SYSTEMATIC_REVIEW,
    "Observational Study": StudyType.COHORT,
    "Practice Guideline": StudyType.CONSENSUS,
    "Consensus Development Conference": StudyType.CONSENSUS,
}


def _map_pubmed_type(pubtypes: list[str]) -> StudyType | None:
    """Map PubMed's PublicationTypeList to a StudyType when it's unambiguous."""
    for pubtype in pubtypes:
        mapped = PUBMED_TYPE_MAP.get(pubtype)
        if mapped is not None:
            return mapped
    return None


@dataclass(frozen=True)
class LiveCandidate:
    """One study found via live search, not yet part of any corpus."""

    title: str
    authors: list[str]
    year: int
    journal: str | None
    abstract: str | None
    doi: str | None
    pmid: str | None
    suggested_study_type: StudyType | None
    source: str
    found_via_language: str


def _pubmed_year(pubdate: str) -> int | None:
    match = re.match(r"(\d{4})", pubdate)
    return int(match.group(1)) if match else None


def _pubmed_doi(doc: dict) -> str | None:
    for article_id in doc.get("articleids", []):
        if article_id.get("idtype") == "doi" and article_id.get("value"):
            return article_id["value"]
    return None


def _pubmed_candidate(doc: dict, pmid: str, language: str) -> LiveCandidate | None:
    title = doc.get("title")
    year = _pubmed_year(doc.get("pubdate", ""))
    if not title or year is None:
        return None
    authors = [a.get("name", "") for a in doc.get("authors", []) if a.get("name")]
    return LiveCandidate(
        title=title,
        authors=authors or ["Unknown"],
        year=year,
        journal=doc.get("fulljournalname") or doc.get("source"),
        abstract=None,
        doi=_pubmed_doi(doc),
        pmid=pmid,
        suggested_study_type=_map_pubmed_type(doc.get("pubtype", [])),
        source="pubmed",
        found_via_language=language,
    )


def search_pubmed(term: str, language: str) -> list[LiveCandidate]:
    """Search PubMed for term, returning candidates with a title and year."""
    search_url = PUBMED_ESEARCH_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    search_payload = fetch_json(search_url)
    if search_payload is None:
        return []
    ids = search_payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary_url = PUBMED_ESUMMARY_URL.format(ids=",".join(ids))
    summary_payload = fetch_json(summary_url)
    if summary_payload is None:
        return []
    result = summary_payload.get("result", {})
    candidates = []
    for pmid in ids:
        doc = result.get(pmid)
        if not doc:
            continue
        candidate = _pubmed_candidate(doc, pmid, language)
        if candidate is not None:
            candidates.append(candidate)
    return candidates
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
uv run ruff format src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git add src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git commit -m "Add PubMed live search"
```

---

### Task 6: Live search — Crossref and Semantic Scholar

**Files:**
- Modify: `src/performance_agent/evidence/live_search.py`
- Modify: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_live_search.py`:

```python
from performance_agent.evidence.live_search import search_crossref, search_semantic_scholar


def test_search_crossref_builds_candidates(monkeypatch):
    payload = {
        "message": {
            "items": [
                {
                    "title": ["Javelin throw kinematics"],
                    "DOI": "10.1000/kinematics",
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "published": {"date-parts": [[2019]]},
                    "container-title": ["Sports Biomechanics"],
                },
                {
                    "title": [],  # no title -> dropped
                    "DOI": "10.1000/no-title",
                    "published": {"date-parts": [[2019]]},
                },
            ]
        }
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)

    candidates = search_crossref("javelin kinematics", "en")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/kinematics"
    assert candidate.authors == ["Jane Doe"]
    assert candidate.year == 2019
    assert candidate.journal == "Sports Biomechanics"
    assert candidate.source == "crossref"


def test_search_crossref_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_crossref("javelin", "en") == []


def test_search_semantic_scholar_builds_candidates(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Speerwurf Trainingsmethoden",
                "year": 2022,
                "authors": [{"name": "Max Muller"}],
                "externalIds": {"DOI": "10.1000/speerwurf"},
                "abstract": "An overview of javelin training methods.",
                "venue": "Leistungssport",
            },
            {
                "title": "No locator study",
                "year": 2022,
                "authors": [{"name": "No One"}],
                "externalIds": {},  # no DOI or PMID -> dropped
            },
        ]
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)

    candidates = search_semantic_scholar("Speerwurf Training", "de")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/speerwurf"
    assert candidate.abstract == "An overview of javelin training methods."
    assert candidate.source == "semantic_scholar"
    assert candidate.found_via_language == "de"


def test_search_semantic_scholar_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_semantic_scholar("javelin", "en") == []
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: FAIL — `ImportError` for `search_crossref`/`search_semantic_scholar`.

- [ ] **Step 3: Implement the Crossref and Semantic Scholar searches**

Add to `src/performance_agent/evidence/live_search.py`, after `search_pubmed`:

```python
CROSSREF_SEARCH_URL = "https://api.crossref.org/works?query={term}&rows={limit}"
SEMANTIC_SCHOLAR_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
    "?query={term}&limit={limit}&fields=title,year,authors,externalIds,abstract,venue"
)


def _crossref_year(item: dict) -> int | None:
    parts = item.get("published", {}).get("date-parts", [[None]])
    year = parts[0][0] if parts and parts[0] else None
    return year if isinstance(year, int) else None


def _crossref_candidate(item: dict, language: str) -> LiveCandidate | None:
    titles = item.get("title") or []
    doi = item.get("DOI")
    year = _crossref_year(item)
    if not titles or not doi or year is None:
        return None
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in item.get("author", [])
        if a.get("family")
    ]
    journals = item.get("container-title") or []
    return LiveCandidate(
        title=titles[0],
        authors=authors or ["Unknown"],
        year=year,
        journal=journals[0] if journals else None,
        abstract=None,
        doi=doi,
        pmid=None,
        suggested_study_type=None,
        source="crossref",
        found_via_language=language,
    )


def search_crossref(term: str, language: str) -> list[LiveCandidate]:
    """Search Crossref for term, returning candidates that carry a DOI."""
    url = CROSSREF_SEARCH_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    payload = fetch_json(url)
    if payload is None:
        return []
    items = payload.get("message", {}).get("items", [])
    candidates = [_crossref_candidate(item, language) for item in items]
    return [c for c in candidates if c is not None]


def _semantic_scholar_candidate(item: dict, language: str) -> LiveCandidate | None:
    title = item.get("title")
    year = item.get("year")
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")
    pmid = external_ids.get("PubMed")
    if not title or not year or not (doi or pmid):
        return None
    authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
    return LiveCandidate(
        title=title,
        authors=authors or ["Unknown"],
        year=year,
        journal=item.get("venue") or None,
        abstract=item.get("abstract"),
        doi=doi,
        pmid=pmid,
        suggested_study_type=None,
        source="semantic_scholar",
        found_via_language=language,
    )


def search_semantic_scholar(term: str, language: str) -> list[LiveCandidate]:
    """Search Semantic Scholar for term, returning candidates with a DOI or PMID."""
    url = SEMANTIC_SCHOLAR_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    payload = fetch_json(url)
    if payload is None:
        return []
    items = payload.get("data", [])
    candidates = [_semantic_scholar_candidate(item, language) for item in items]
    return [c for c in candidates if c is not None]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
uv run ruff format src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git add src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git commit -m "Add Crossref and Semantic Scholar live search"
```

---

### Task 7: Fan-out orchestration, dedup and verification

**Files:**
- Modify: `src/performance_agent/evidence/live_search.py`
- Modify: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_live_search.py`:

```python
from performance_agent.evidence.live_search import (
    LiveSearchOutcome,
    _dedup,
    run_live_search,
)
from performance_agent.evidence.verify import ResolvedReference


def _candidate(**overrides) -> LiveCandidate:
    data = {
        "title": "A study",
        "authors": ["Doe J"],
        "year": 2021,
        "journal": "J Sports Sci",
        "abstract": None,
        "doi": "10.1000/a",
        "pmid": None,
        "suggested_study_type": None,
        "source": "pubmed",
        "found_via_language": "en",
    }
    data.update(overrides)
    return LiveCandidate(**data)


def test_dedup_by_doi_case_insensitive():
    candidates = [_candidate(doi="10.1000/A"), _candidate(doi="10.1000/a")]
    assert len(_dedup(candidates)) == 1


def test_dedup_by_pmid():
    candidates = [
        _candidate(doi=None, pmid="123"),
        _candidate(doi=None, pmid="123"),
        _candidate(doi=None, pmid="456"),
    ]
    assert len(_dedup(candidates)) == 2


def test_dedup_drops_candidates_without_any_locator():
    candidates = [_candidate(doi=None, pmid=None)]
    assert _dedup(candidates) == []


def test_run_live_search_verifies_and_reports_failures(monkeypatch):
    def fake_search_pubmed(term: str, language: str) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/found", found_via_language=language)]

    def fake_search_crossref(term: str, language: str) -> list[LiveCandidate]:
        raise OSError("network down")

    def fake_search_semantic_scholar(term: str, language: str) -> list[LiveCandidate]:
        return []

    monkeypatch.setattr(live_search_module, "search_pubmed", fake_search_pubmed)
    monkeypatch.setattr(live_search_module, "search_crossref", fake_search_crossref)
    monkeypatch.setattr(
        live_search_module, "search_semantic_scholar", fake_search_semantic_scholar
    )
    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (
            ("pubmed", fake_search_pubmed),
            ("crossref", fake_search_crossref),
            ("semantic_scholar", fake_search_semantic_scholar),
        ),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(True, "A study", "resolved via Crossref"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin throw"})

    assert isinstance(outcome, LiveSearchOutcome)
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].doi == "10.1000/found"
    assert outcome.failed_sources == ["crossref:en"]


def test_run_live_search_drops_unverified_candidates(monkeypatch):
    def fake_search_pubmed(term: str, language: str) -> list[LiveCandidate]:
        return [_candidate(doi="10.1000/unverified", found_via_language=language)]

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (
            ("pubmed", fake_search_pubmed),
            ("crossref", lambda term, language: []),
            ("semantic_scholar", lambda term, language: []),
        ),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(False, None, "did not resolve"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin throw"})

    assert outcome.candidates == []
    assert outcome.failed_sources == []
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: FAIL — `ImportError` for `LiveSearchOutcome`, `_dedup`, `run_live_search`.

- [ ] **Step 3: Implement the orchestration**

Add to `src/performance_agent/evidence/live_search.py`:

1. Add the import at the top (alongside the existing `verify` import):

```python
import time

from performance_agent.evidence.verify import fetch_json, resolve_reference
```

(replace the existing `from performance_agent.evidence.verify import fetch_json`
line with the two-name version above, and add `import time` near the top with the
other stdlib imports)

2. Add the constant near `_SEARCH_LIMIT`:

```python
_POLITE_DELAY_S = 0.5
```

3. Append at the end of the file:

```python
_SOURCES = (
    ("pubmed", search_pubmed),
    ("crossref", search_crossref),
    ("semantic_scholar", search_semantic_scholar),
)


def _locator_key(candidate: LiveCandidate) -> str | None:
    if candidate.doi:
        return f"doi:{candidate.doi.casefold()}"
    if candidate.pmid:
        return f"pmid:{candidate.pmid}"
    return None


def _dedup(candidates: list[LiveCandidate]) -> list[LiveCandidate]:
    seen: set[str] = set()
    deduped = []
    for candidate in candidates:
        key = _locator_key(candidate)
        if key is None or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _verify_candidates(candidates: list[LiveCandidate]) -> list[LiveCandidate]:
    return [c for c in candidates if resolve_reference(c.doi, c.pmid).ok]


@dataclass(frozen=True)
class LiveSearchOutcome:
    """Verified candidates from a multilingual live search, plus what failed."""

    candidates: list[LiveCandidate]
    failed_sources: list[str]


def run_live_search(language_terms: dict[str, str]) -> LiveSearchOutcome:
    """Fan out language/term pairs across PubMed, Crossref and Semantic Scholar.

    One source/language failing does not blank out the others; failures are
    reported by name in the outcome instead of raising. Every surviving candidate
    has been independently re-verified (its DOI/PMID resolves) before being
    returned — the same guarantee the packaged corpus gets from
    evidence/verify.py before shipping.
    """
    raw: list[LiveCandidate] = []
    failed: list[str] = []
    first_call = True
    for language, term in language_terms.items():
        for source_name, search_fn in _SOURCES:
            if not first_call:
                time.sleep(_POLITE_DELAY_S)
            first_call = False
            try:
                raw.extend(search_fn(term, language))
            except (OSError, ValueError):
                failed.append(f"{source_name}:{language}")
    return LiveSearchOutcome(candidates=_verify_candidates(_dedup(raw)), failed_sources=failed)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/evidence/test_live_search.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
uv run ruff format src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
uv run ty check
git add src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git commit -m "Add live-search fan-out with dedup and re-verification"
```

---

### Task 8: `search_evidence_live` MCP tool

**Files:**
- Modify: `src/performance_agent/server/evidence_tools.py`
- Modify: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Add near the top of `tests/server/test_evidence_tools.py` (after the `import
pytest` line):

```python
import performance_agent.server.evidence_tools as evidence_tools_module


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    evidence_tools_module._index.cache_clear()
    yield tmp_path
    evidence_tools_module._index.cache_clear()
```

Then append the test itself:

```python
@pytest.mark.anyio
async def test_search_evidence_live_returns_verified_candidates(client, monkeypatch):
    def fake_run_live_search(language_terms):
        from performance_agent.evidence.live_search import LiveCandidate, LiveSearchOutcome
        from performance_agent.evidence.schemas import StudyType

        return LiveSearchOutcome(
            candidates=[
                LiveCandidate(
                    title="Javelin throw training review",
                    authors=["Doe J"],
                    year=2021,
                    journal="J Sports Sci",
                    abstract=None,
                    doi="10.1000/javelin-review",
                    pmid=None,
                    suggested_study_type=StudyType.SYSTEMATIC_REVIEW,
                    source="pubmed",
                    found_via_language="en",
                )
            ],
            failed_sources=["crossref:de"],
        )

    monkeypatch.setattr(evidence_tools_module, "run_live_search", fake_run_live_search)

    result = await client.call_tool(
        "search_evidence_live", {"language_terms": {"en": "javelin throw training"}}
    )

    assert not result.isError
    body = result.structuredContent
    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["doi"] == "10.1000/javelin-review"
    assert candidate["suggested_study_type"] == "systematic_review"
    assert body["failed_sources"] == ["crossref:de"]


@pytest.mark.anyio
async def test_search_evidence_live_is_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert "search_evidence_live" in names
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: FAIL — `search_evidence_live` doesn't exist as a tool yet.

- [ ] **Step 3: Implement the tool**

In `src/performance_agent/server/evidence_tools.py`, add to the imports:

```python
from performance_agent.evidence.live_search import run_live_search
```

Add these `TypedDict`s after the existing `SearchResults` class:

```python
class LiveCandidateResult(TypedDict):
    """One live-search candidate, already DOI/PMID-verified."""

    title: str
    authors: list[str]
    year: int
    journal: str | None
    abstract: str | None
    doi: str | None
    pmid: str | None
    suggested_study_type: str | None
    source: str
    found_via_language: str


class LiveSearchResults(TypedDict):
    """Verified live-search candidates, plus any source/language that failed."""

    candidates: list[LiveCandidateResult]
    failed_sources: list[str]
```

Add the tool function after `search_evidence`:

```python
def search_evidence_live(language_terms: dict[str, str]) -> LiveSearchResults:
    """Search PubMed, Crossref and Semantic Scholar for studies outside the local corpus.

    language_terms maps an ISO language code to a search term YOU translate for
    that language, e.g. {"en": "javelin throw training", "de": "Speerwurf
    Training"}. Every returned candidate has already been verified: its DOI/PMID
    resolves against Crossref or PubMed. suggested_study_type is filled from
    PubMed's own publication-type tags when unambiguous; when it's null, read the
    abstract yourself and propose a study_type before calling save_evidence — the
    grading ceiling is enforced server-side regardless of what you propose. A
    source/language pair that failed to respond is listed in failed_sources —
    mention degraded coverage rather than silently under-searching.
    """
    outcome = run_live_search(language_terms)
    return LiveSearchResults(
        candidates=[
            LiveCandidateResult(
                title=c.title,
                authors=c.authors,
                year=c.year,
                journal=c.journal,
                abstract=c.abstract,
                doi=c.doi,
                pmid=c.pmid,
                suggested_study_type=(
                    c.suggested_study_type.value if c.suggested_study_type else None
                ),
                source=c.source,
                found_via_language=c.found_via_language,
            )
            for c in outcome.candidates
        ],
        failed_sources=outcome.failed_sources,
    )
```

Update `register()` to include the new tool:

```python
def register(mcp: FastMCP) -> None:
    """Register every evidence tool on the server."""
    for tool in (search_evidence, get_citation, check_citations, search_evidence_live):
        mcp.tool()(tool)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: PASS (all tests in the file, old and new).

- [ ] **Step 5: Run the full evidence + skills suite to check for regressions**

Run: `uv run pytest tests/evidence/ tests/server/ tests/skills/ -v`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
uv run ruff format src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
uv run ty check
git add src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
git commit -m "Add search_evidence_live MCP tool"
```

---

### Task 9: `verify_reference` MCP tool

**Files:**
- Modify: `src/performance_agent/server/evidence_tools.py`
- Modify: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/server/test_evidence_tools.py`:

```python
@pytest.mark.anyio
async def test_verify_reference_resolves_doi(client, monkeypatch):
    from performance_agent.evidence.verify import ResolvedReference

    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(True, "A federation whitepaper", "resolved via Crossref"),
    )
    result = await client.call_tool("verify_reference", {"doi": "10.1000/whitepaper"})
    assert not result.isError
    assert result.structuredContent == {
        "ok": True,
        "title": "A federation whitepaper",
        "detail": "resolved via Crossref",
    }


@pytest.mark.anyio
async def test_verify_reference_reports_failure_without_raising(client, monkeypatch):
    from performance_agent.evidence.verify import ResolvedReference

    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(False, None, "DOI did not resolve: 10.1000/fake"),
    )
    result = await client.call_tool("verify_reference", {"doi": "10.1000/fake"})
    assert not result.isError
    assert result.structuredContent["ok"] is False
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: FAIL — `verify_reference` tool doesn't exist yet.

- [ ] **Step 3: Implement the tool**

Add to the imports in `src/performance_agent/server/evidence_tools.py`:

```python
from performance_agent.evidence.verify import resolve_reference
```

Add this `TypedDict` after `LiveSearchResults`:

```python
class ReferenceResolution(TypedDict):
    """Whether a bare DOI/PMID resolves against Crossref/PubMed, and its title."""

    ok: bool
    title: str | None
    detail: str
```

Add the tool function after `search_evidence_live`:

```python
def verify_reference(
    doi: str | None = None, pmid: str | None = None
) -> ReferenceResolution:
    """Confirm a DOI or PMID found via general web search actually resolves.

    Call this before proposing save_evidence for anything found outside
    search_evidence_live — e.g. a reference surfaced by a general web search for a
    federation, thesis, or conference paper. Never save an entry whose locator did
    not resolve here.
    """
    resolved = resolve_reference(doi, pmid)
    return ReferenceResolution(ok=resolved.ok, title=resolved.title, detail=resolved.detail)
```

Update `register()`:

```python
def register(mcp: FastMCP) -> None:
    """Register every evidence tool on the server."""
    for tool in (
        search_evidence,
        get_citation,
        check_citations,
        search_evidence_live,
        verify_reference,
    ):
        mcp.tool()(tool)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
uv run ruff format src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
uv run ty check
git add src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
git commit -m "Add verify_reference MCP tool"
```

---

### Task 10: `save_evidence` MCP tool

**Files:**
- Modify: `src/performance_agent/server/evidence_tools.py`
- Modify: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/server/test_evidence_tools.py`:

```python
def _live_entry_payload(**overrides) -> dict:
    data = {
        "id": "live-javelin-review",
        "title": "Javelin throw training review",
        "authors": ["Doe J"],
        "year": 2021,
        "study_type": "systematic_review",
        "conclusions": "Periodized throwing volume improves distance over a macrocycle.",
        "evidence_level": "strong",
        "doi": "10.1000/javelin-review",
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_save_evidence_persists_and_is_immediately_searchable(client, monkeypatch):
    from performance_agent.evidence.verify import ResolvedReference

    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(True, "Javelin throw training review", "resolved via Crossref"),
    )

    save_result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    assert not save_result.isError
    assert save_result.structuredContent["path"].endswith("evidence_extra.yaml")

    search_result = await client.call_tool("search_evidence", {"query": "javelin throw training"})
    ids = {hit["id"] for hit in search_result.structuredContent["hits"]}
    assert "live-javelin-review" in ids


@pytest.mark.anyio
async def test_save_evidence_rejects_unresolvable_locator(client, monkeypatch):
    from performance_agent.evidence.verify import ResolvedReference

    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(False, None, "DOI did not resolve: 10.1000/javelin-review"),
    )

    result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    assert result.isError
    assert "could not verify" in result.content[0].text


@pytest.mark.anyio
async def test_save_evidence_rejects_grading_ceiling_violation(client):
    # a cross_sectional study cannot be graded "strong" — schemas.py enforces this
    result = await client.call_tool(
        "save_evidence",
        {
            "entry": _live_entry_payload(
                id="live-overgraded", study_type="cross_sectional", evidence_level="strong"
            )
        },
    )
    assert result.isError


@pytest.mark.anyio
async def test_save_evidence_rejects_id_collision(client, monkeypatch):
    from performance_agent.evidence.verify import ResolvedReference

    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda doi, pmid: ResolvedReference(True, "Javelin throw training review", "resolved via Crossref"),
    )
    await client.call_tool("save_evidence", {"entry": _live_entry_payload()})
    result = await client.call_tool(
        "save_evidence", {"entry": _live_entry_payload(doi="10.1000/other-doi")}
    )
    assert result.isError
    assert "live-javelin-review" in result.content[0].text
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: FAIL — `save_evidence` tool doesn't exist yet.

- [ ] **Step 3: Implement the tool**

Add to the imports in `src/performance_agent/server/evidence_tools.py`:

```python
from performance_agent.evidence.personal_corpus import append_entry
from performance_agent.evidence.corpus import load_corpus
```

(`load_corpus` is already imported — just confirm it's there; don't duplicate the
import line.)

Add this `TypedDict` after `ReferenceResolution`:

```python
class WrittenFile(TypedDict):
    """Path of the file the tool just wrote."""

    path: str
```

Add the tool function after `verify_reference`:

```python
def save_evidence(entry: EvidenceEntry) -> WrittenFile:
    """Persist a verified, graded study to your personal evidence corpus.

    The entry is re-verified here (its DOI/PMID must resolve) regardless of what
    you were told earlier by search_evidence_live or verify_reference — this tool
    never trusts a self-reported verified flag. The grading ceiling
    (schemas.GRADING_CEILING) still applies: you cannot save a cross-sectional
    study as "strong". Once saved, the entry is immediately searchable via
    search_evidence.
    """
    resolved = resolve_reference(entry.doi, entry.pmid)
    if not resolved.ok:
        msg = f"{entry.id}: could not verify before saving — {resolved.detail}"
        raise ValueError(msg)
    verified_entry = entry.model_copy(update={"verified": True})
    known_ids = {e.id for e in load_corpus()}
    path = append_entry(verified_entry, known_ids)
    _index.cache_clear()
    return WrittenFile(path=str(path))
```

Update `register()`:

```python
def register(mcp: FastMCP) -> None:
    """Register every evidence tool on the server."""
    for tool in (
        search_evidence,
        get_citation,
        check_citations,
        search_evidence_live,
        verify_reference,
        save_evidence,
    ):
        mcp.tool()(tool)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/server/test_evidence_tools.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `uv run pytest`
Expected: PASS, all tests across the whole project.

- [ ] **Step 6: Lint, type-check and commit**

```bash
uv run ruff check . && uv run ruff format --check .
uv run ty check
git add src/performance_agent/server/evidence_tools.py tests/server/test_evidence_tools.py
git commit -m "Add save_evidence MCP tool"
```

---

### Task 11: Wire the new tools into the skills

**Files:**
- Modify: `skills/goal-assessment/SKILL.md`
- Modify: `skills/program-generation/SKILL.md`
- Modify: `skills/program-adaptation/SKILL.md`

The skills test harness (`tests/skills/test_tool_references.py`) requires every tool
named in a skill's body to be declared in its frontmatter, and vice versa — so the
frontmatter and body edits below must land together.

- [ ] **Step 1: Update `goal-assessment`**

In `skills/goal-assessment/SKILL.md`, change the frontmatter `tools:` line to:

```yaml
tools: [read_athlete, get_time_context, assess_endurance_goal, predict_race_time,
        estimate_1rm, upsert_goal, search_evidence, search_evidence_live,
        save_evidence, verify_reference, check_citations]
```

Replace the `## Strength goals` section with:

```markdown
## Strength goals

The feasibility engine is endurance-only today — say so honestly. Anchor the
conversation in numbers you CAN compute: current `estimate_1rm` from a recent set,
the gap to the target, and evidence on realistic progression from `search_evidence`
(e.g. periodized progression, frequency and volume dose-response). Give a coaching
judgment labeled as such, not a fabricated probability. Same discipline as the
endurance path, minus the probability number: if the gap is clearly outside
realistic progression (say so, citing evidence on typical rates where the corpus
has it), do NOT proceed to program-generation without naming that and proposing
a milestone.

## Deep evidence search

Run on every goal assessment, right after `search_evidence`:

1. Call `search_evidence_live` with a `language_terms` dict — write the goal's key
   training question translated into en, fr, es, de, ru, no, sv, it, zh (skip any
   language you're not confident translating accurately). Each candidate already
   has its DOI/PMID verified.
2. For each candidate: if `suggested_study_type` is set, use it as-is (never
   upgrade it). If it's null, read the `abstract` and propose a `study_type` and a
   conservative 1-2 sentence `conclusions` — never a figure absent from the
   abstract. The grading ceiling still applies regardless of what you propose.
3. Call `save_evidence` for each candidate worth keeping — it becomes searchable
   immediately.
4. Still nothing relevant for a language? Fall back to a general web search
   (`WebSearch`/`WebFetch`) in that language for federations, theses, or
   conference proceedings. Any DOI/PMID you find this way MUST pass
   `verify_reference` before you attempt `save_evidence` — never propose an
   entry from an unverified web result.
5. Nothing found anywhere for the goal? Say so plainly: "deep search performed,
   no directly applicable study found for X, here is the closest available
   literature" — never force-fit an unrelated citation.
```

- [ ] **Step 2: Update `program-generation`**

In `skills/program-generation/SKILL.md`, change the frontmatter `tools:` line to:

```yaml
tools: [read_athlete, get_time_context, search_evidence, search_evidence_live,
        save_evidence, verify_reference, get_citation, check_citations,
        build_periodization_waves, prescribe_load, estimate_1rm,
        predict_race_time, compute_pace, save_program, log_session]
```

Replace the end of the `## 1. Evidence pack` section (the last sentence) with:

```markdown
If a question returns nothing from `search_evidence`, run `search_evidence_live`
with translated `language_terms` (en, fr, es, de, ru, no, sv, it, zh) before
concluding the corpus has no entry. Classify and `save_evidence` any verified
candidate worth citing — `suggested_study_type` if set, otherwise your own
abstract-based proposal (grading ceiling still enforced). Still nothing? Fall back
to a web search per language, `verify_reference` anything with a locator before
proposing `save_evidence`, and if that also comes up empty, label that part of the
plan as coaching judgment rather than force a citation.
```

- [ ] **Step 3: Update `program-adaptation`**

In `skills/program-adaptation/SKILL.md`, change the frontmatter `tools:` line to:

```yaml
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
        compute_session_load, compute_weekly_loads, compute_acwr,
        assess_endurance_goal, prescribe_load, estimate_1rm,
        build_periodization_waves, search_evidence, search_evidence_live,
        save_evidence, verify_reference, get_citation, check_citations, save_program]
```

In the `## 2. Propose the change` section, replace the "Citation repair" bullet
with:

```markdown
- Citation repair: when a render was refused for unknown references, locate the
  offending claims, replace each with a `search_evidence`-backed citation rendered
  via `get_citation` (or drop the claim). If nothing in the corpus covers the
  claim, run `search_evidence_live`, classify and `save_evidence` a verified
  candidate before citing it — never patch a refused render by weakening the
  claim into something unverifiable. Save vN+1 with reason "citation repair".
```

- [ ] **Step 4: Verify the skills harness passes**

Run: `uv run pytest tests/skills/ -v`
Expected: PASS — `test_declared_tools_exist_on_the_server` (the new tools are
registered from Tasks 8-10), `test_declared_tools_are_actually_used_in_the_body`,
and `test_bodies_do_not_reference_undeclared_tools` all green.

- [ ] **Step 5: Commit**

```bash
git add skills/goal-assessment/SKILL.md skills/program-generation/SKILL.md \
        skills/program-adaptation/SKILL.md
git commit -m "Wire live evidence search into goal-assessment, program-generation, program-adaptation"
```

---

### Task 12: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full quality gate**

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Expected: all four commands exit 0 — zero warnings, zero failing tests.

- [ ] **Step 2: Sanity-check no stray network calls in tests**

```bash
uv run pytest tests/evidence/ tests/server/ -v -m "not anyio" 2>&1 | tail -5
uv run pytest tests/evidence/test_live_search.py tests/server/test_evidence_tools.py -v
```

Confirm the run completes in a few seconds, not tens of seconds — a slow run here
usually means a test forgot to monkeypatch `fetch_json`/`resolve_reference` and is
hitting the real network.

- [ ] **Step 3: Manually verify the tool count via the packaged server**

```bash
uv run python -c "
import asyncio
from mcp.shared.memory import create_connected_server_and_client_session
from performance_agent.server.app import mcp

async def main():
    async with create_connected_server_and_client_session(mcp) as session:
        tools = await session.list_tools()
        print(sorted(t.name for t in tools.tools))

asyncio.run(main())
"
```

Expected: 26 tools total (the prior 23 plus `search_evidence_live`,
`verify_reference`, `save_evidence`).

- [ ] **Step 4: Commit final wrap-up (if anything was left staged)**

```bash
git status
```

Expected: clean tree — every task already committed its own changes.
