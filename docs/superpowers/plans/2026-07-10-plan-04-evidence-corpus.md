# Plan 04 — Evidence Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A graded, verifiable scientific-evidence corpus with full-text search and an
anti-fabrication citation checker, exposed as 3 MCP tools — the layer that makes it
architecturally impossible for the coach to invent a reference.

**Architecture:** Per spec v2 §5: a packaged YAML manifest of graded studies (grading
ceilings enforced by schema — a cross-sectional study can never be `strong`), loaded into
an in-memory SQLite FTS5 index (corpus is tiny; no cache files, no staleness), searched
via BM25. Citations are formatted from corpus entries only; `check_citations` scans prose
for DOI/PMID-shaped strings absent from the corpus. A maintainer-only verification module
resolves DOIs/PMIDs against Crossref/PubMed — end users never need network or keys.

**Tech Stack:** stdlib sqlite3 (FTS5) + urllib (verify module only), pydantic, pyyaml,
importlib.resources for packaged data. mcp==1.28.1 FastMCP conventions from Plans 02-03
(TypedDict returns, no Optional top-level returns, camelCase test attrs).

**⚠️ ANTI-FABRICATION RULE FOR THE IMPLEMENTER (Task 5):** you must NOT write any study
metadata (title, authors, year, DOI, PMID) from memory. Every corpus entry must be
confirmed against live Crossref/PubMed API responses at implementation time, copying the
metadata from the API response. A candidate that cannot be confirmed is DROPPED, not
approximated. This is the product's core value applied to its own development.

---

## MVP Plan Sequence (spec v2 §10)

1. ✅ Foundation & sports science engine
2. ✅ MCP server core
3. ✅ Athlete memory
4. **Evidence corpus** ← this plan
5. Coaching skills + eval harness
6. Typst reports
7. Distribution (PyPI, corpus releases)

---

## File Structure (this plan)

```
src/performance_agent/
├── evidence/
│   ├── __init__.py            # docstring only
│   ├── schemas.py             # StudyType, EvidenceLevel, grading ceilings, stars, EvidenceEntry
│   ├── corpus.py              # parse_manifest(text) + load_corpus() from packaged data
│   ├── index.py               # EvidenceIndex: in-memory FTS5 build + search
│   ├── citations.py           # format_citation, find_unknown_references
│   ├── verify.py              # maintainer CLI: resolve DOI/PMID via Crossref/PubMed
│   └── data/
│       └── seed_corpus.yaml   # live-verified starter entries (Task 5)
└── server/
    ├── evidence_tools.py      # 3 MCP tools + register(mcp)
    └── app.py                 # + evidence_tools.register(mcp)

tests/
├── evidence/
│   ├── __init__.py
│   ├── test_schemas.py
│   ├── test_corpus.py
│   ├── test_index.py
│   ├── test_citations.py
│   └── test_verify.py
└── server/test_evidence_tools.py
```

Baseline entering this plan: 179 passed. Report actual totals after each task.

---

### Task 1: Evidence schemas with grading ceilings

**Files:**
- Create: `src/performance_agent/evidence/__init__.py`, `src/performance_agent/evidence/schemas.py`
- Test: `tests/evidence/__init__.py` (empty), `tests/evidence/test_schemas.py`

- [ ] **Step 1: Write the failing tests** — `tests/evidence/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from performance_agent.evidence.schemas import (
    STARS,
    EvidenceEntry,
    EvidenceLevel,
    StudyType,
)

VALID = {
    "id": "example-meta-analysis",
    "title": "An example meta-analysis",
    "authors": ["Doe J", "Roe R"],
    "year": 2020,
    "study_type": "meta_analysis",
    "conclusions": "Something robust.",
    "evidence_level": "strong",
    "doi": "10.1000/example",
}


def test_valid_entry_round_trips():
    entry = EvidenceEntry.model_validate(VALID)
    assert entry.study_type is StudyType.META_ANALYSIS
    assert entry.evidence_level is EvidenceLevel.STRONG
    assert entry.verified is False


@pytest.mark.parametrize(
    ("study_type", "too_high"),
    [
        ("cross_sectional", "strong"),
        ("cross_sectional", "moderate"),
        ("rct", "strong"),
        ("cohort", "strong"),
        ("expert_opinion", "limited"),
    ],
)
def test_grading_ceilings_are_enforced(study_type, too_high):
    with pytest.raises(ValidationError, match="ceiling"):
        EvidenceEntry.model_validate(
            {**VALID, "study_type": study_type, "evidence_level": too_high}
        )


@pytest.mark.parametrize(
    ("study_type", "level"),
    [
        ("systematic_review", "strong"),
        ("meta_analysis", "strong"),
        ("rct", "moderate"),
        ("cross_sectional", "limited"),
        ("expert_opinion", "expert"),
        ("meta_analysis", "limited"),  # grading BELOW the ceiling is always allowed
    ],
)
def test_levels_at_or_below_ceiling_are_accepted(study_type, level):
    entry = EvidenceEntry.model_validate(
        {**VALID, "study_type": study_type, "evidence_level": level}
    )
    assert entry.evidence_level is EvidenceLevel(level)


def test_an_entry_needs_a_doi_or_pmid():
    data = {**VALID}
    del data["doi"]
    with pytest.raises(ValidationError, match="DOI or a PMID"):
        EvidenceEntry.model_validate(data)


def test_pmid_alone_is_enough():
    data = {**VALID}
    del data["doi"]
    entry = EvidenceEntry.model_validate({**data, "pmid": "11708692"})
    assert entry.pmid == "11708692"


def test_stars_cover_every_level():
    assert set(STARS) == set(EvidenceLevel)
    assert STARS[EvidenceLevel.STRONG] == "★★★★★"
    assert STARS[EvidenceLevel.EXPERT] == "★☆☆☆☆"


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        EvidenceEntry.model_validate({**VALID, "impact_factor": 42})
```

- [ ] **Step 2: Run to verify red** — `rtk proxy uv run pytest tests/evidence -v` →
ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/performance_agent/evidence/__init__.py`:
```python
"""Graded scientific evidence corpus (packaged, searchable, fabrication-proof)."""
```

`src/performance_agent/evidence/schemas.py`:
```python
"""Schemas and grading rules for the evidence corpus.

The grading ceiling is the honesty rule of spec v2 §5: an entry's evidence
level can never exceed what its study design can support.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudyType(StrEnum):
    """Study designs, strongest first (spec v2 §1 hierarchy)."""

    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    RCT = "rct"
    COHORT = "cohort"
    CROSS_SECTIONAL = "cross_sectional"
    CONSENSUS = "consensus"
    EXPERT_OPINION = "expert_opinion"


class EvidenceLevel(StrEnum):
    """Graded strength of evidence, shown to athletes as stars."""

    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"
    EXPERT = "expert"


_LEVEL_RANK: dict[EvidenceLevel, int] = {
    EvidenceLevel.EXPERT: 0,
    EvidenceLevel.LIMITED: 1,
    EvidenceLevel.MODERATE: 2,
    EvidenceLevel.STRONG: 3,
}

GRADING_CEILING: dict[StudyType, EvidenceLevel] = {
    StudyType.SYSTEMATIC_REVIEW: EvidenceLevel.STRONG,
    StudyType.META_ANALYSIS: EvidenceLevel.STRONG,
    StudyType.RCT: EvidenceLevel.MODERATE,
    StudyType.COHORT: EvidenceLevel.MODERATE,
    StudyType.CROSS_SECTIONAL: EvidenceLevel.LIMITED,
    StudyType.CONSENSUS: EvidenceLevel.MODERATE,
    StudyType.EXPERT_OPINION: EvidenceLevel.EXPERT,
}

STARS: dict[EvidenceLevel, str] = {
    EvidenceLevel.STRONG: "★★★★★",
    EvidenceLevel.MODERATE: "★★★☆☆",
    EvidenceLevel.LIMITED: "★★☆☆☆",
    EvidenceLevel.EXPERT: "★☆☆☆☆",
}


class EvidenceEntry(BaseModel):
    """One graded study in the corpus. Only corpus entries are ever citable."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=80)
    title: str
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1950, le=2100)
    journal: str | None = None
    study_type: StudyType
    population: str | None = None
    conclusions: str
    evidence_level: EvidenceLevel
    doi: str | None = None
    pmid: str | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _enforce_grading_ceiling(self) -> Self:
        ceiling = GRADING_CEILING[self.study_type]
        if _LEVEL_RANK[self.evidence_level] > _LEVEL_RANK[ceiling]:
            msg = (
                f"{self.id}: a {self.study_type.value} study cannot be graded "
                f"{self.evidence_level.value}; its ceiling is {ceiling.value}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _require_locator(self) -> Self:
        if self.doi is None and self.pmid is None:
            msg = f"{self.id}: an entry needs a DOI or a PMID to be citable"
            raise ValueError(msg)
        return self
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/evidence -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # report total
git add src/performance_agent/evidence tests/evidence
git commit -m "Add evidence schemas with grading ceilings"
```

---

### Task 2: Corpus loader (packaged data)

**Files:**
- Create: `src/performance_agent/evidence/corpus.py`
- Create: `src/performance_agent/evidence/data/seed_corpus.yaml` (placeholder header + ONE
  synthetic-but-schema-valid bootstrap entry so the loader is testable; Task 5 replaces
  the content with live-verified real studies)
- Test: `tests/evidence/test_corpus.py`

- [ ] **Step 1: Write the failing tests** — `tests/evidence/test_corpus.py`:

```python
import pytest

from performance_agent.evidence.corpus import load_corpus, parse_manifest

MANIFEST = """
- id: entry-one
  title: First entry
  authors: [Doe J]
  year: 2019
  study_type: rct
  conclusions: Something.
  evidence_level: moderate
  doi: 10.1000/one
- id: entry-two
  title: Second entry
  authors: [Roe R]
  year: 2021
  study_type: meta_analysis
  conclusions: Something else.
  evidence_level: strong
  pmid: "123456"
"""


def test_parse_manifest_returns_entries_in_order():
    entries = parse_manifest(MANIFEST)
    assert [e.id for e in entries] == ["entry-one", "entry-two"]


def test_duplicate_ids_are_rejected():
    duplicated = MANIFEST + MANIFEST.replace("entry-one", "entry-two", 1)
    with pytest.raises(ValueError, match="duplicate"):
        parse_manifest(duplicated + "")  # any dup id must be named in the error


def test_manifest_must_be_a_list():
    with pytest.raises(ValueError, match="list"):
        parse_manifest("id: not-a-list\n")


def test_packaged_corpus_loads_and_validates():
    entries = load_corpus()
    assert len(entries) >= 1
    assert all(entry.doi or entry.pmid for entry in entries)
```

(Note on the duplicate test: build the duplicated text however is clearest — the
assertion that matters is a ValueError naming the duplicated id.)

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement**

`src/performance_agent/evidence/corpus.py`:
```python
"""Load and validate the packaged evidence corpus."""

from importlib import resources

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


def load_corpus() -> list[EvidenceEntry]:
    """Load the corpus shipped inside the package."""
    data = resources.files("performance_agent.evidence") / "data" / "seed_corpus.yaml"
    return parse_manifest(data.read_text(encoding="utf-8"))
```

`src/performance_agent/evidence/data/seed_corpus.yaml` (bootstrap content, replaced in
Task 5 — this entry is clearly labeled synthetic and is NOT presented as science):
```yaml
# PerformanceAgent seed corpus.
# Every entry here MUST have been verified against Crossref/PubMed by a maintainer
# (see performance_agent/evidence/verify.py). Do not add entries from memory.
- id: bootstrap-placeholder
  title: "Bootstrap placeholder (replaced by live-verified entries in Plan 04 Task 5)"
  authors: [PerformanceAgent Maintainers]
  year: 2026
  study_type: expert_opinion
  conclusions: Placeholder entry so the loader has content before curation lands.
  evidence_level: expert
  doi: 10.0000/placeholder
```

Packaging check: run `uv build` and verify the wheel contains
`performance_agent/evidence/data/seed_corpus.yaml` (`unzip -l dist/*.whl | grep seed`).
If uv_build excludes non-Python files, add the needed include configuration under
`[tool.uv.build-backend]` (check uv docs: `data` / `module-root` options) and report
what was required.

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/evidence -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/evidence tests/evidence
git commit -m "Add corpus loader with packaged seed manifest"
```

---

### Task 3: In-memory FTS5 search index

**Files:**
- Create: `src/performance_agent/evidence/index.py`
- Test: `tests/evidence/test_index.py`

- [ ] **Step 1: Write the failing tests** — `tests/evidence/test_index.py`:

```python
from performance_agent.evidence.index import EvidenceIndex
from performance_agent.evidence.schemas import EvidenceEntry, EvidenceLevel, StudyType


def _entry(entry_id: str, title: str, conclusions: str, **overrides) -> EvidenceEntry:
    data = {
        "id": entry_id,
        "title": title,
        "authors": ["Doe J"],
        "year": 2020,
        "study_type": "rct",
        "conclusions": conclusions,
        "evidence_level": "moderate",
        "doi": f"10.1000/{entry_id}",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


ENTRIES = [
    _entry(
        "strength-economy",
        "Strength training improves running economy",
        "Heavy strength training improves running economy in trained runners.",
        study_type="meta_analysis",
        evidence_level="strong",
    ),
    _entry(
        "taper-performance",
        "Tapering and competition performance",
        "Two-week exponential tapers improve endurance performance.",
    ),
    _entry(
        "stretching-injury",
        "Static stretching and injury risk",
        "Static stretching shows no clear effect on injury incidence.",
        study_type="cross_sectional",
        evidence_level="limited",
    ),
]


def test_search_finds_by_content_and_ranks_relevant_first():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("running economy strength")
    assert hits
    assert hits[0].entry.id == "strength-economy"


def test_search_respects_limit():
    index = EvidenceIndex(ENTRIES)
    assert len(index.search("performance training injury", limit=1)) == 1


def test_search_filters_by_study_type():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("training", study_type=StudyType.META_ANALYSIS)
    assert all(h.entry.study_type is StudyType.META_ANALYSIS for h in hits)


def test_search_filters_by_min_level():
    index = EvidenceIndex(ENTRIES)
    hits = index.search("injury stretching", min_level=EvidenceLevel.MODERATE)
    assert all(h.entry.evidence_level in {EvidenceLevel.MODERATE, EvidenceLevel.STRONG} for h in hits)


def test_no_hits_is_an_empty_list_not_an_error():
    index = EvidenceIndex(ENTRIES)
    assert index.search("quantum chromodynamics") == []


def test_hostile_query_syntax_does_not_crash():
    index = EvidenceIndex(ENTRIES)
    for query in ['"unbalanced', "AND OR NOT", "col:umn", "a*b(c)", "   "]:
        index.search(query)  # must not raise


def test_empty_query_returns_empty():
    index = EvidenceIndex(ENTRIES)
    assert index.search("") == []
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement** — `src/performance_agent/evidence/index.py`:

```python
"""In-memory FTS5 search over the evidence corpus.

The corpus is small (hundreds of entries), so the index is rebuilt from the
manifest in-process — no cache files, no staleness, no extra infrastructure.
"""

import sqlite3
from dataclasses import dataclass

from performance_agent.evidence.schemas import (
    _LEVEL_RANK,
    EvidenceEntry,
    EvidenceLevel,
    StudyType,
)


@dataclass(frozen=True)
class SearchHit:
    """One search result with its BM25 relevance rank (lower = more relevant)."""

    entry: EvidenceEntry
    rank: float


def _sanitized_match_query(query: str) -> str:
    """Quote every term so user text can never be parsed as FTS5 syntax."""
    terms = [term.replace('"', "") for term in query.split()]
    return " ".join(f'"{term}"' for term in terms if term)


class EvidenceIndex:
    """Builds and queries an in-memory FTS5 index over corpus entries."""

    def __init__(self, entries: list[EvidenceEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE evidence USING fts5(id UNINDEXED, title, conclusions, population)"
        )
        self._db.executemany(
            "INSERT INTO evidence (id, title, conclusions, population) VALUES (?, ?, ?, ?)",
            [(e.id, e.title, e.conclusions, e.population or "") for e in entries],
        )
        self._db.commit()

    def search(
        self,
        query: str,
        limit: int = 5,
        study_type: StudyType | None = None,
        min_level: EvidenceLevel | None = None,
    ) -> list[SearchHit]:
        """Return BM25-ranked hits; filters apply after ranking (corpus is tiny)."""
        match = _sanitized_match_query(query)
        if not match:
            return []
        rows = self._db.execute(
            "SELECT id, rank FROM evidence WHERE evidence MATCH ? ORDER BY rank",
            (match,),
        ).fetchall()
        hits = []
        for entry_id, rank in rows:
            entry = self._entries[entry_id]
            if study_type is not None and entry.study_type is not study_type:
                continue
            if min_level is not None and _LEVEL_RANK[entry.evidence_level] < _LEVEL_RANK[min_level]:
                continue
            hits.append(SearchHit(entry=entry, rank=rank))
            if len(hits) >= limit:
                break
        return hits
```

(If ruff flags the private `_LEVEL_RANK` cross-module import, rename it to `LEVEL_RANK`
in schemas.py — updating Task 1's ceiling validator too — and report the rename.)

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/evidence -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/evidence/index.py tests/evidence/test_index.py
git commit -m "Add in-memory FTS5 evidence search"
```

---

### Task 4: Citation formatting and the anti-fabrication check

**Files:**
- Create: `src/performance_agent/evidence/citations.py`
- Test: `tests/evidence/test_citations.py`

- [ ] **Step 1: Write the failing tests** — `tests/evidence/test_citations.py`:

```python
from performance_agent.evidence.citations import find_unknown_references, format_citation
from performance_agent.evidence.schemas import EvidenceEntry

ENTRY = EvidenceEntry.model_validate(
    {
        "id": "strength-economy",
        "title": "Strength training improves running economy",
        "authors": ["Doe J", "Roe R", "Poe P"],
        "year": 2020,
        "journal": "J Sports Sci",
        "study_type": "meta_analysis",
        "conclusions": "It works.",
        "evidence_level": "strong",
        "doi": "10.1000/strength",
        "pmid": "123456",
    }
)


def test_citation_contains_the_load_bearing_fields():
    citation = format_citation(ENTRY)
    assert "Doe J" in citation
    assert "2020" in citation
    assert "Strength training improves running economy" in citation
    assert "10.1000/strength" in citation


def test_citation_without_journal_still_formats():
    entry = ENTRY.model_copy(update={"journal": None})
    assert "2020" in format_citation(entry)


def test_known_references_pass_the_check():
    text = "Heavy lifting helps (DOI: 10.1000/strength, PMID: 123456)."
    assert find_unknown_references(text, [ENTRY]) == []


def test_unknown_doi_is_flagged():
    text = "As shown in the landmark study (doi:10.9999/fabricated)."
    unknown = find_unknown_references(text, [ENTRY])
    assert unknown == ["10.9999/fabricated"]


def test_unknown_pmid_is_flagged():
    text = "See PMID: 99887766 for details."
    assert find_unknown_references(text, [ENTRY]) == ["PMID:99887766"]


def test_doi_with_trailing_punctuation_is_normalized():
    text = "Great result (10.9999/fabricated)."
    assert find_unknown_references(text, [ENTRY]) == ["10.9999/fabricated"]


def test_text_without_references_is_clean():
    assert find_unknown_references("Squat 5x5 at 80%.", [ENTRY]) == []
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement** — `src/performance_agent/evidence/citations.py`:

```python
"""Citation rendering and the anti-fabrication reference check.

Citations are ALWAYS rendered from corpus entries — never from free text. The
checker scans prose for DOI/PMID-shaped strings that are not in the corpus;
anything it finds is a fabricated or unverifiable reference.
"""

import re

from performance_agent.evidence.schemas import EvidenceEntry

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]]+", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"\bPMID:?\s*(\d{6,9})\b", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:"


def format_citation(entry: EvidenceEntry) -> str:
    """Render a human-readable citation from a corpus entry."""
    authors = ", ".join(entry.authors)
    parts = [f"{authors} ({entry.year}). {entry.title}."]
    if entry.journal:
        parts.append(f"{entry.journal}.")
    if entry.doi:
        parts.append(f"DOI: {entry.doi}.")
    if entry.pmid:
        parts.append(f"PMID: {entry.pmid}.")
    return " ".join(parts)


def find_unknown_references(text: str, corpus: list[EvidenceEntry]) -> list[str]:
    """Return DOI/PMID-shaped strings in the text that are not corpus entries."""
    known_dois = {entry.doi.casefold() for entry in corpus if entry.doi}
    known_pmids = {entry.pmid for entry in corpus if entry.pmid}
    unknown: list[str] = []
    for match in _DOI_PATTERN.findall(text):
        doi = match.rstrip(_TRAILING_PUNCTUATION)
        if doi.casefold() not in known_dois:
            unknown.append(doi)
    for pmid in _PMID_PATTERN.findall(text):
        if pmid not in known_pmids:
            unknown.append(f"PMID:{pmid}")
    return unknown
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/evidence -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/evidence/citations.py tests/evidence/test_citations.py
git commit -m "Add citation rendering and anti-fabrication check"
```

---

### Task 5: Maintainer verification module + live-verified starter corpus

**Files:**
- Create: `src/performance_agent/evidence/verify.py`
- Modify: `src/performance_agent/evidence/data/seed_corpus.yaml` (replace bootstrap content)
- Test: `tests/evidence/test_verify.py`

- [ ] **Step 1: Write the failing tests** — `tests/evidence/test_verify.py` (network is
mocked; the live run happens in Step 4):

```python
import json

import performance_agent.evidence.verify as verify_module
from performance_agent.evidence.schemas import EvidenceEntry
from performance_agent.evidence.verify import verify_entry


def _entry(**overrides) -> EvidenceEntry:
    data = {
        "id": "sample",
        "title": "A sample study",
        "authors": ["Doe J"],
        "year": 2020,
        "study_type": "rct",
        "conclusions": "x",
        "evidence_level": "moderate",
        "doi": "10.1000/sample",
    }
    data.update(overrides)
    return EvidenceEntry.model_validate(data)


def test_doi_resolution_success(monkeypatch):
    payload = {"message": {"title": ["A sample study"]}}
    monkeypatch.setattr(
        verify_module, "_fetch_json", lambda url: payload if "crossref" in url else None
    )
    result = verify_entry(_entry())
    assert result.ok
    assert "A sample study" in (result.retrieved_title or "")


def test_doi_resolution_failure(monkeypatch):
    monkeypatch.setattr(verify_module, "_fetch_json", lambda url: None)
    result = verify_entry(_entry())
    assert not result.ok
    assert "10.1000/sample" in result.detail


def test_pmid_resolution_success(monkeypatch):
    payload = {"result": {"123456": {"title": "A sample study"}, "uids": ["123456"]}}
    monkeypatch.setattr(verify_module, "_fetch_json", lambda url: payload)
    entry = _entry(doi=None, pmid="123456")
    result = verify_entry(entry)
    assert result.ok


def test_entry_without_locator_cannot_exist():
    # schema guarantees doi or pmid; verify_entry may assume it
    entry = _entry()
    assert entry.doi or entry.pmid
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement** — `src/performance_agent/evidence/verify.py`:

```python
"""Maintainer-only corpus verification against Crossref and PubMed.

End users never run this: entries ship pre-verified in the package. Run it
whenever the manifest changes:

    uv run python -m performance_agent.evidence.verify
"""

import json
import sys
import urllib.request
from dataclasses import dataclass

from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.schemas import EvidenceEntry

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
PUBMED_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&id={pmid}&retmode=json"
)
_TIMEOUT_S = 20


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of resolving one entry against its source registry."""

    entry_id: str
    ok: bool
    detail: str
    retrieved_title: str | None = None


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        return None


def _title_from_crossref(payload: dict) -> str | None:
    titles = payload.get("message", {}).get("title") or []
    return titles[0] if titles else None


def _title_from_pubmed(payload: dict, pmid: str) -> str | None:
    return payload.get("result", {}).get(pmid, {}).get("title")


def verify_entry(entry: EvidenceEntry) -> VerificationResult:
    """Resolve the entry's DOI (preferred) or PMID and report what the registry says."""
    if entry.doi:
        payload = _fetch_json(CROSSREF_URL.format(doi=entry.doi))
        if payload is None:
            return VerificationResult(entry.id, False, f"DOI did not resolve: {entry.doi}")
        return VerificationResult(
            entry.id, True, "resolved via Crossref", _title_from_crossref(payload)
        )
    payload = _fetch_json(PUBMED_URL.format(pmid=entry.pmid))
    if payload is None:
        return VerificationResult(entry.id, False, f"PMID did not resolve: {entry.pmid}")
    return VerificationResult(
        entry.id, True, "resolved via PubMed", _title_from_pubmed(payload, entry.pmid or "")
    )


def main() -> int:
    """Verify every corpus entry; print a comparison table for human review."""
    failures = 0
    for entry in load_corpus():
        result = verify_entry(entry)
        status = "OK " if result.ok else "FAIL"
        print(f"[{status}] {entry.id}: {result.detail}")  # noqa: T201
        if result.retrieved_title:
            print(f"       manifest: {entry.title}")  # noqa: T201
            print(f"       registry: {result.retrieved_title}")  # noqa: T201
        failures += 0 if result.ok else 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

(Adapt the two `# noqa` codes to whatever ruff actually flags — print statements in a
CLI `main()` are intentional; if the project's ruff config has no `T`/`S` rules enabled,
drop the noqa comments. Report what was needed.)

- [ ] **Step 4: Curate the starter corpus — LIVE VERIFICATION, NO MEMORY.**

Replace the bootstrap content of `src/performance_agent/evidence/data/seed_corpus.yaml`
with real studies confirmed against live registries. Protocol, for EACH candidate:

1. Query Crossref's search API with title keywords, e.g.
   `curl -s "https://api.crossref.org/works?query.bibliographic=<keywords>&rows=3"`
   (or WebFetch), and locate the intended work in the response.
2. Copy title/authors/year/journal/DOI EXACTLY from the API response — never from memory.
3. Write the entry with a conclusions summary in your own words (one-two sentences,
   faithful to the abstract if present in the response, else to the title's claim —
   conservative wording), a study_type consistent with the title/registry metadata, and
   an evidence_level AT OR BELOW the grading ceiling.
4. Set `verified: true` only for entries you confirmed this way.
5. If the intended work cannot be found or the metadata is ambiguous: DROP the candidate.

Candidate topics to search (aim for 8-12 confirmed entries; drop freely — an honest 8
beats a doubtful 12). These are TOPICS, not references — find the actual studies:
- meta-analysis: strength training and running economy in distance runners
- systematic review: strength training and distance-running performance (e.g. Blagrove et al.)
- meta-analysis: effects of tapering on performance (e.g. Bosquet et al.)
- session-RPE method for quantifying training load (Foster et al.)
- meta-analysis: resistance-training volume and hypertrophy (e.g. Schoenfeld et al.)
- meta-analysis: resistance-training frequency and strength (e.g. Grgic et al.)
- acute:chronic workload ratio and injury (e.g. Hulin/Gabbett) — grade honestly (cohort!)
- review/meta: intervals vs continuous training and VO2max
- meta-analysis: plyometric training and sprint/jump performance
- position stand / consensus: resistance-training progression (grade as consensus)

Then run the LIVE verification:
```bash
uv run python -m performance_agent.evidence.verify
```
Expected: every line `[OK ]`, and manifest/registry titles matching. Paste the full
output into your report. If any line is FAIL, fix or drop that entry and re-run.

- [ ] **Step 5: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/evidence -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/evidence tests/evidence
git commit -m "Add live-verified starter corpus and verification CLI"
```

---

### Task 6: Evidence MCP tools

**Files:**
- Create: `src/performance_agent/server/evidence_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests** — `tests/server/test_evidence_tools.py`:

```python
"""In-process tests for the evidence MCP tools (real packaged corpus)."""

import pytest


@pytest.mark.anyio
async def test_search_evidence_returns_graded_hits(client):
    result = await client.call_tool("search_evidence", {"query": "strength training"})
    assert not result.isError
    hits = result.structuredContent["hits"]
    assert hits, "the live-verified starter corpus must match a strength query"
    first = hits[0]
    assert set(first) >= {"id", "title", "year", "study_type", "evidence_level", "stars",
                          "conclusions", "citation"}
    assert first["stars"].count("★") + first["stars"].count("☆") == 5


@pytest.mark.anyio
async def test_search_evidence_empty_result_is_not_an_error(client):
    result = await client.call_tool("search_evidence", {"query": "quantum chromodynamics"})
    assert not result.isError
    assert result.structuredContent["hits"] == []


@pytest.mark.anyio
async def test_get_citation_by_id(client):
    search = await client.call_tool("search_evidence", {"query": "strength training"})
    entry_id = search.structuredContent["hits"][0]["id"]
    result = await client.call_tool("get_citation", {"evidence_id": entry_id})
    assert not result.isError
    assert result.structuredContent["citation"]
    assert result.structuredContent["stars"]


@pytest.mark.anyio
async def test_get_citation_unknown_id_is_readable_error(client):
    result = await client.call_tool("get_citation", {"evidence_id": "no-such-entry"})
    assert result.isError
    assert "search_evidence" in result.content[0].text


@pytest.mark.anyio
async def test_check_citations_flags_fabrications(client):
    result = await client.call_tool(
        "check_citations", {"text": "Proven by science (doi:10.9999/fabricated)."}
    )
    assert not result.isError
    report = result.structuredContent
    assert report["ok"] is False
    assert "10.9999/fabricated" in report["unknown_references"]


@pytest.mark.anyio
async def test_check_citations_passes_clean_text(client):
    result = await client.call_tool("check_citations", {"text": "Squat 5x5 at 80%."})
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["unknown_references"] == []


@pytest.mark.anyio
async def test_evidence_tools_are_listed(client):
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert {"search_evidence", "get_citation", "check_citations"} <= names
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement** — `src/performance_agent/server/evidence_tools.py`:

```python
"""MCP tools for the graded evidence corpus.

Citation discipline for the coach: only cite ids returned by search_evidence;
render references via get_citation; run check_citations on any prose that
mentions a study before presenting it to the athlete.
"""

from functools import lru_cache
from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from performance_agent.evidence.citations import find_unknown_references, format_citation
from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.index import EvidenceIndex
from performance_agent.evidence.schemas import STARS, EvidenceLevel, StudyType


class EvidenceHit(TypedDict):
    """One graded search result."""

    id: str
    title: str
    year: int
    study_type: str
    evidence_level: str
    stars: str
    conclusions: str
    citation: str


class SearchResults(TypedDict):
    """Ranked search hits (most relevant first)."""

    hits: list[EvidenceHit]


class CitationResult(TypedDict):
    """A rendered citation with its confidence stars."""

    citation: str
    stars: str
    doi: str | None
    pmid: str | None


class CitationCheck(TypedDict):
    """Anti-fabrication verdict for a piece of prose."""

    ok: bool
    unknown_references: list[str]


@lru_cache(maxsize=1)
def _index() -> EvidenceIndex:
    return EvidenceIndex(load_corpus())


@lru_cache(maxsize=1)
def _corpus_by_id() -> dict[str, object]:
    return {entry.id: entry for entry in load_corpus()}


def search_evidence(
    query: str,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
    study_type: StudyType | None = None,
    min_level: EvidenceLevel | None = None,
) -> SearchResults:
    """Search the graded evidence corpus (BM25 over titles/conclusions).

    Cite ONLY ids returned here. Stars come from the study design's grading
    ceiling (★★★★★ strong … ★☆☆☆☆ expert opinion); present them with every
    recommendation and say so honestly when evidence is limited.
    """
    hits = _index().search(query, limit=limit, study_type=study_type, min_level=min_level)
    return SearchResults(
        hits=[
            EvidenceHit(
                id=hit.entry.id,
                title=hit.entry.title,
                year=hit.entry.year,
                study_type=hit.entry.study_type.value,
                evidence_level=hit.entry.evidence_level.value,
                stars=STARS[hit.entry.evidence_level],
                conclusions=hit.entry.conclusions,
                citation=format_citation(hit.entry),
            )
            for hit in hits
        ]
    )


def get_citation(evidence_id: str) -> CitationResult:
    """Render the citation for a corpus entry by id (ids come from search_evidence)."""
    entry = _corpus_by_id().get(evidence_id)
    if entry is None:
        msg = (
            f"unknown evidence id {evidence_id!r}; only ids returned by "
            "search_evidence are citable"
        )
        raise ValueError(msg)
    return CitationResult(
        citation=format_citation(entry),
        stars=STARS[entry.evidence_level],
        doi=entry.doi,
        pmid=entry.pmid,
    )


def check_citations(text: str) -> CitationCheck:
    """Scan prose for DOI/PMID references that are NOT in the corpus.

    Run this on any answer that mentions studies before presenting it. A
    non-empty unknown_references list means a fabricated or unverifiable
    reference — remove it or replace it with a real search_evidence hit.
    """
    unknown = find_unknown_references(text, list(_corpus_by_id().values()))
    return CitationCheck(ok=not unknown, unknown_references=unknown)


def register(mcp: FastMCP) -> None:
    """Register every evidence tool on the server."""
    for tool in (search_evidence, get_citation, check_citations):
        mcp.tool()(tool)
```

(Note: `_corpus_by_id` is typed `dict[str, object]` above only if ty forces it — prefer
`dict[str, EvidenceEntry]` with the proper import; use whichever passes the gate and
report. The `entry` uses below assume EvidenceEntry attributes.)

Modify `app.py` to import and register `evidence_tools` alongside engine and memory.

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/server -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/server tests/server/test_evidence_tools.py
git commit -m "Add evidence MCP tools with anti-fabrication check"
```

---

### Task 7: Final sweep

- [ ] **Step 1: Full quality gate** (ruff/format/ty, full pytest, prek run --all-files,
actionlint + zizmor).

- [ ] **Step 2: `README.md`** — move the evidence line to "Working today":
replace `- 🔜 Curated evidence corpus (~200 graded studies) with anti-fabrication enforcement`
with a ✅ line reflecting reality (live-verified starter corpus of N entries, grading
ceilings, FTS5 search, check_citations tool; the ~200-study curation is ongoing content
work — keep a 🔜 line "Corpus growth to ~200 studies (curation pipeline)"). Update the
"🔜 Evidence and report MCP tools" line to "🔜 Report MCP tools". Check exact wording.

- [ ] **Step 3: `docs/installing.md`** — Verify section: 19 → 22 tools
("22 tools (9 engine + 10 memory + 3 evidence: …)"). Check exact wording.

- [ ] **Step 4: As-built deviations** section appended to this plan file (verified
against code/git log), including the final corpus size and the verification output
summary.

- [ ] **Step 5: Commit** (`git add -A -- ':!.claude' ':!athlete'`).

---

## Self-Review Notes

- **Spec coverage (v2 §5 + §10 item 4):** manifest with grading ceilings enforced ✓ T1;
  packaged seed corpus ✓ T2/T5; FTS5 BM25 search with filters, no embeddings/keys ✓ T3;
  citations rendered only from entries + prose checker ✓ T4; maintainer verification
  (Crossref/PubMed) with users never needing network ✓ T5; stars from grade ✓ T1/T6;
  3 MCP tools ✓ T6. Cross-lingual note: spec says the agent searches in English —
  that's a skills-layer instruction (Plan 05), nothing to build here.
- **Deliberate scope cuts:** ~200-study curation is content work beyond this plan (starter
  is 8-12 live-verified entries; growth is ongoing); live PubMed/Semantic Scholar
  ingestion pipeline is V2; re-ranking/embeddings deliberately absent (no-keys rule).
- **Type consistency:** EvidenceEntry/StudyType/EvidenceLevel/STARS consistent across
  T1-T6; SearchHit.entry used by T6's mapping; find_unknown_references(text, corpus)
  signature identical in T4 impl and T6 usage; format_citation(entry) everywhere.
- **Known uncertainties, handled in-plan:** uv_build packaging of the data file (check +
  configure + report); ruff noqa needs in verify.py; `_LEVEL_RANK` privacy (rename
  instruction); FastMCP enum-param handling for StudyType/EvidenceLevel filters is
  proven by Plan 02's TrainingAge precedent.
