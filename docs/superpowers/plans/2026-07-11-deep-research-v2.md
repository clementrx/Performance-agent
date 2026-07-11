# Deep Research v2 (Premium Pipeline Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the server side of the Researcher per spec §5: PubMed candidates hydrated with full abstracts (efetch), OpenAlex as a fourth keyless source, year/publication-type filters, a 25-per-source budget with evidence-tier ordering, a title cross-check on the save path (closes the audit's integrity gap), and an ISBN-verified `reference_book` corpus category capped at expert opinion — with *Manuel ultime de musculation* as its first documented entry.

**Architecture:** All changes live in the existing evidence modules: `evidence/live_search.py` (sources, filters, budget, ordering), `evidence/verify.py` (registry resolution incl. new `resolve_isbn`, public `titles_match`), `evidence/schemas.py` (`reference_book` study type + ISBN locator), `evidence/citations.py` (ISBN anti-fabrication), and `server/evidence_tools.py` (tool surface). No new tools — `verify_reference` gains an `isbn` param, `search_evidence_live` gains filter params; the tool count stays 41. The bundled seed corpus stays studies-only. Spec: `docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md` §5 & §7-phase-3.

**Tech Stack:** Python 3.13, stdlib `urllib`/`xml.etree.ElementTree`, Pydantic v2, pytest, existing FastMCP in-process test harness.

**Conventions (this repo):**
- Line length 100, `ruff format` + `ruff check` + `ty check` must stay clean (zero warnings).
- Commits: imperative subject, no type prefix (match `git log`), ≤72 chars.
- **Network access happens ONLY in `live_search.py` and `verify.py`.** The engine-purity
  architectural test doesn't cover `evidence/`, but keep the existing module boundaries:
  every HTTP call goes through `verify.fetch_json` / `verify.fetch_text` (added in Task 1);
  no other module opens a socket.
- **All new HTTP calls are mocked in tests exactly like the existing ones:**
  `monkeypatch.setattr(live_search_module, "fetch_json", …)` /
  `monkeypatch.setattr(verify_module, "fetch_json", …)` — never a real network call,
  never `responses`/`respx`-style libraries.
- Run Python via `env -u VIRTUAL_ENV uv run ...` in worktrees (the parent repo's venv
  otherwise leaks into the worktree).
- When a step asserts a test count, read it from a run **without `-q`** (the `-q` summary
  can elide the collected count).

---

### Task 1: PubMed abstracts via efetch

Replace the esummary hydration step with efetch (`rettype=abstract&retmode=xml`): parse
`ArticleTitle`, `AbstractText` (join labeled sections), `PubDate` year,
`PublicationTypeList` (kept mapping through the existing `PUBMED_TYPE_MAP`), DOI from
`ArticleIdList`. The current `LiveCandidate` already carries `abstract: str | None` (only
Semantic Scholar fills it today) and a **required** `year: int` — year becomes
`int | None` so no source ever silently drops a year-less paper (spec §5: the agent
grades; ordering puts `None` years last in Task 4).

Exact new candidate shape (was `year: int`, everything else unchanged):

```python
@dataclass(frozen=True)
class LiveCandidate:
    """One study found via live search, not yet part of any corpus."""

    title: str
    authors: list[str]
    year: int | None
    journal: str | None
    abstract: str | None
    doi: str | None
    pmid: str | None
    suggested_study_type: StudyType | None
    source: str
    found_via_language: str
```

**Files:**
- Modify: `src/performance_agent/evidence/verify.py` (add `fetch_text` — network stays here)
- Modify: `src/performance_agent/evidence/live_search.py`
- Modify: `src/performance_agent/server/evidence_tools.py` (`LiveCandidateResult.year` → `int | None`)
- Test: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

In `tests/evidence/test_live_search.py`, **replace** `test_search_pubmed_builds_candidates`
with the efetch version below, and add the XML fixture at module top (after the imports):

```python
_EFETCH_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">111</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
          <Title>Journal of Sports Sciences</Title>
        </Journal>
        <ArticleTitle>Javelin biomechanics and throw distance</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Throwing is complex.</AbstractText>
          <AbstractText Label="RESULTS">Distance improved.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Doe</LastName><Initials>J</Initials></Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType>Randomized Controlled Trial</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">111</ArticleId>
        <ArticleId IdType="doi">10.1000/javelin</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">222</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><MedlineDate>Winter 2020</MedlineDate></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle></ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_search_pubmed_builds_candidates_from_efetch(monkeypatch):
    esearch_payload = {"esearchresult": {"idlist": ["111", "222"]}}

    def fake_fetch_json(url: str) -> dict | None:
        assert "esearch" in url
        return esearch_payload

    def fake_fetch_text(url: str) -> str | None:
        assert "efetch" in url
        assert "rettype=abstract" in url
        assert "retmode=xml" in url
        assert "id=111,222" in url
        return _EFETCH_XML

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(live_search_module, "fetch_text", fake_fetch_text)

    candidates = search_pubmed("javelin throw", "en")

    assert len(candidates) == 1  # the empty-title article is dropped
    candidate = candidates[0]
    assert isinstance(candidate, LiveCandidate)
    assert candidate.pmid == "111"
    assert candidate.doi == "10.1000/javelin"
    assert candidate.title == "Javelin biomechanics and throw distance"
    assert candidate.abstract == "Throwing is complex. Distance improved."
    assert candidate.year == 2021
    assert candidate.journal == "Journal of Sports Sciences"
    assert candidate.authors == ["Doe J"]
    assert candidate.suggested_study_type == StudyType.RCT
    assert candidate.source == "pubmed"
    assert candidate.found_via_language == "en"


def test_search_pubmed_keeps_candidate_without_year(monkeypatch):
    xml = _EFETCH_XML.replace("<Year>2021</Year>", "")
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: xml)
    candidates = search_pubmed("javelin throw", "en")
    assert candidates[0].year is None


def test_search_pubmed_returns_empty_on_malformed_xml(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: "<not-xml")
    assert search_pubmed("javelin throw", "en") == []


def test_search_pubmed_returns_empty_when_efetch_fails(monkeypatch):
    monkeypatch.setattr(
        live_search_module, "fetch_json", lambda _url: {"esearchresult": {"idlist": ["111"]}}
    )
    monkeypatch.setattr(live_search_module, "fetch_text", lambda _url: None)
    assert search_pubmed("javelin throw", "en") == []
```

Also update the existing crossref/semantic-scholar year-dropping expectations: candidates
without a year are now **kept**. Append:

```python
def test_search_crossref_keeps_candidate_without_year(monkeypatch):
    payload = {
        "message": {
            "items": [{"title": ["Undated but real"], "DOI": "10.1000/undated"}]
        }
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)
    candidates = search_crossref("javelin", "en")
    assert len(candidates) == 1
    assert candidates[0].year is None


def test_search_semantic_scholar_keeps_candidate_without_year(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Undated study",
                "authors": [{"name": "Doe J"}],
                "externalIds": {"DOI": "10.1000/undated"},
            }
        ]
    }
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: payload)
    candidates = search_semantic_scholar("javelin", "en")
    assert len(candidates) == 1
    assert candidates[0].year is None
```

And in `tests/evidence/test_verify.py`, append the `fetch_text` failure-mode test:

```python
def test_fetch_text_returns_none_on_network_failure(monkeypatch):
    def raise_oserror(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(verify_module.urllib.request, "urlopen", raise_oserror)
    assert verify_module.fetch_text("https://example.org") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py tests/evidence/test_verify.py -q`
Expected: FAIL — `AttributeError: … has no attribute 'fetch_text'` and the new pubmed tests fail.

- [ ] **Step 3: Implement**

In `src/performance_agent/evidence/verify.py`, add below `fetch_json`:

```python
def fetch_text(url: str) -> str | None:
    """Fetch a raw text response body, returning None on any network failure."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            return response.read().decode("utf-8")
    except (OSError, http.client.HTTPException):
        return None
```

In `src/performance_agent/evidence/live_search.py`:

Replace the imports/URL block at the top:

```python
import re
import time
from dataclasses import dataclass
from urllib.parse import quote
from xml.etree import ElementTree

from performance_agent.evidence.schemas import StudyType
from performance_agent.evidence.verify import fetch_json, fetch_text, resolve_reference

PUBMED_ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term={term}&retmode=json&retmax={limit}"
)
PUBMED_EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pubmed&id={ids}&rettype=abstract&retmode=xml"
)
```

(`PUBMED_ESUMMARY_URL` is deleted — replace, don't deprecate.)

Change the dataclass field `year: int` to `year: int | None` (shape shown in the task
intro). Then **replace** `_pubmed_year`, `_pubmed_doi`, `_pubmed_candidate` and
`search_pubmed` with the efetch implementations:

```python
def _pubmed_abstract(article: ElementTree.Element) -> str | None:
    sections = [
        " ".join(node.itertext()).strip()
        for node in article.findall("MedlineCitation/Article/Abstract/AbstractText")
    ]
    joined = " ".join(section for section in sections if section)
    return joined or None


def _pubmed_year(article: ElementTree.Element) -> int | None:
    pubdate = "MedlineCitation/Article/Journal/JournalIssue/PubDate"
    year = article.findtext(f"{pubdate}/Year")
    if year and year.isdigit():
        return int(year)
    match = re.search(r"\d{4}", article.findtext(f"{pubdate}/MedlineDate") or "")
    return int(match.group(0)) if match else None


def _pubmed_doi(article: ElementTree.Element) -> str | None:
    for article_id in article.findall("PubmedData/ArticleIdList/ArticleId"):
        if article_id.get("IdType") == "doi" and article_id.text:
            return article_id.text.strip()
    return None


def _pubmed_authors(article: ElementTree.Element) -> list[str]:
    authors = []
    for author in article.findall("MedlineCitation/Article/AuthorList/Author"):
        last = author.findtext("LastName")
        initials = author.findtext("Initials")
        if last:
            authors.append(f"{last} {initials}".strip() if initials else last)
    return authors


def _pubmed_candidate(article: ElementTree.Element, language: str) -> LiveCandidate | None:
    pmid = article.findtext("MedlineCitation/PMID")
    title_node = article.find("MedlineCitation/Article/ArticleTitle")
    title = " ".join(title_node.itertext()).strip() if title_node is not None else ""
    if not pmid or not title:
        return None
    pubtypes = [
        node.text.strip()
        for node in article.findall(
            "MedlineCitation/Article/PublicationTypeList/PublicationType"
        )
        if node.text
    ]
    return LiveCandidate(
        title=title,
        authors=_pubmed_authors(article) or ["Unknown"],
        year=_pubmed_year(article),
        journal=article.findtext("MedlineCitation/Article/Journal/Title"),
        abstract=_pubmed_abstract(article),
        doi=_pubmed_doi(article),
        pmid=pmid,
        suggested_study_type=_map_pubmed_type(pubtypes),
        source="pubmed",
        found_via_language=language,
    )


def search_pubmed(term: str, language: str) -> list[LiveCandidate]:
    """Search PubMed, hydrating candidates with full abstracts via efetch."""
    search_url = PUBMED_ESEARCH_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    search_payload = fetch_json(search_url)
    if search_payload is None:
        return []
    ids = search_payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    body = fetch_text(PUBMED_EFETCH_URL.format(ids=",".join(ids)))
    if body is None:
        return []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    candidates = []
    for article in root.findall("PubmedArticle"):
        candidate = _pubmed_candidate(article, language)
        if candidate is not None:
            candidates.append(candidate)
    return candidates
```

In `_crossref_candidate`, drop the year requirement — change

```python
    if not titles or not doi or year is None:
        return None
```

to

```python
    if not titles or not doi:
        return None
```

In `_semantic_scholar_candidate`, change

```python
    if not title or not year or not (doi or pmid):
        return None
```

to

```python
    if not title or not (doi or pmid):
        return None
```

(and pass `year=item.get("year")` unchanged — it's already `int | None` there).

In `src/performance_agent/server/evidence_tools.py`, update the TypedDict field:

```python
class LiveCandidateResult(TypedDict):
    """One live-search candidate, already DOI/PMID-verified."""

    title: str
    authors: list[str]
    year: int | None
    journal: str | None
    abstract: str | None
    doi: str | None
    pmid: str | None
    suggested_study_type: str | None
    source: str
    found_via_language: str
```

Also update the module docstring's first line in `live_search.py` to name the hydration:

```python
"""Live, verified evidence search across PubMed, Crossref and Semantic Scholar.

PubMed candidates are hydrated with full abstracts via efetch. Every function
here returns raw candidates; nothing is citable until run_live_search
re-verifies each candidate's DOI/PMID via evidence.verify.resolve_reference —
the same check the packaged corpus goes through in evidence/verify.py before
shipping.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence tests/server/test_evidence_tools.py -q`
Expected: PASS (all, including pre-existing tests).

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`
Expected: clean.

```bash
git add src/performance_agent/evidence/verify.py src/performance_agent/evidence/live_search.py \
        src/performance_agent/server/evidence_tools.py \
        tests/evidence/test_live_search.py tests/evidence/test_verify.py
git commit -m "Hydrate PubMed live-search candidates with efetch abstracts"
```

---

### Task 2: OpenAlex as a fourth source

Keyless `GET https://api.openalex.org/works?search={term}&per-page={limit}&mailto=…`.
Parse DOI (strip the `https://doi.org/` prefix), title, `publication_year`, `type`, and
reconstruct the abstract from `abstract_inverted_index`. OpenAlex work types are
deliberately **not** mapped to a `StudyType`: its `review` lumps narrative and systematic
reviews together and `article` says nothing about design, so any mapping would over-grade
— `suggested_study_type` stays `None` and the agent grades from the abstract (ceiling
enforced at save time).

**Files:**
- Modify: `src/performance_agent/evidence/live_search.py`
- Test: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_live_search.py` (extend the live_search import with
`_openalex_abstract, search_openalex`):

```python
def test_openalex_abstract_reconstruction_places_words_at_positions():
    inverted = {"training": [2], "Javelin": [0], "throw": [1], "works": [3, 5], "it": [4]}
    assert _openalex_abstract(inverted) == "Javelin throw training works it works"


def test_openalex_abstract_reconstruction_handles_missing_index():
    assert _openalex_abstract(None) is None
    assert _openalex_abstract({}) is None


def test_search_openalex_builds_candidates(monkeypatch):
    payload = {
        "results": [
            {
                "title": "Lancer de javelot et biomécanique",
                "doi": "https://doi.org/10.1000/javelot",
                "publication_year": 2020,
                "type": "review",
                "abstract_inverted_index": {"Une": [0], "revue": [1]},
                "authorships": [{"author": {"display_name": "Jean Dupont"}}],
                "primary_location": {"source": {"display_name": "Science et Sport"}},
            },
            {
                "title": None,  # no title -> dropped
                "doi": "https://doi.org/10.1000/no-title",
            },
            {
                "title": "No locator work",  # no DOI -> dropped
                "doi": None,
            },
        ]
    }

    def fake_fetch_json(url: str) -> dict | None:
        assert "api.openalex.org/works" in url
        assert "mailto=performance-agent@users.noreply.github.com" in url
        return payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)

    candidates = search_openalex("lancer de javelot", "fr")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1000/javelot"
    assert candidate.title == "Lancer de javelot et biomécanique"
    assert candidate.year == 2020
    assert candidate.abstract == "Une revue"
    assert candidate.authors == ["Jean Dupont"]
    assert candidate.journal == "Science et Sport"
    # OpenAlex cannot distinguish systematic from narrative reviews: never mapped
    assert candidate.suggested_study_type is None
    assert candidate.source == "openalex"
    assert candidate.found_via_language == "fr"


def test_search_openalex_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(live_search_module, "fetch_json", lambda _url: None)
    assert search_openalex("javelin", "en") == []


def test_run_live_search_fans_out_to_four_sources(monkeypatch):
    calls: list[str] = []

    def fake_source(name):
        def search(_term, language):
            calls.append(f"{name}:{language}")
            return []

        return search

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        tuple((name, fake_source(name)) for name, _fn in live_search_module._SOURCES),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    run_live_search({"en": "javelin"})

    assert calls == ["pubmed:en", "crossref:en", "semantic_scholar:en", "openalex:en"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py -q`
Expected: FAIL — `ImportError: cannot import name 'search_openalex'`.

- [ ] **Step 3: Implement**

In `src/performance_agent/evidence/live_search.py`, add below the Semantic Scholar block:

```python
OPENALEX_URL = (
    "https://api.openalex.org/works?search={term}&per-page={limit}"
    "&mailto=performance-agent@users.noreply.github.com"
)


def _openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Rebuild an abstract from OpenAlex's inverted index (word -> positions)."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions[index] = word
    return " ".join(positions[index] for index in sorted(positions))


def _openalex_doi(work: dict) -> str | None:
    doi = work.get("doi")
    if not doi:
        return None
    return doi.removeprefix("https://doi.org/")


def _openalex_journal(work: dict) -> str | None:
    source = (work.get("primary_location") or {}).get("source") or {}
    return source.get("display_name")


def _openalex_candidate(work: dict, language: str) -> LiveCandidate | None:
    title = work.get("title")
    doi = _openalex_doi(work)
    if not title or not doi:
        return None
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    # OpenAlex `type` is deliberately NOT mapped to a StudyType: "review" lumps
    # narrative and systematic reviews together and "article" says nothing about
    # design, so any mapping would over-grade. The agent reads the abstract and
    # proposes a type instead; the grading ceiling is enforced at save time.
    return LiveCandidate(
        title=title,
        authors=authors or ["Unknown"],
        year=work.get("publication_year"),
        journal=_openalex_journal(work),
        abstract=_openalex_abstract(work.get("abstract_inverted_index")),
        doi=doi,
        pmid=None,
        suggested_study_type=None,
        source="openalex",
        found_via_language=language,
    )


def search_openalex(term: str, language: str) -> list[LiveCandidate]:
    """Search OpenAlex for term, returning candidates that carry a DOI."""
    url = OPENALEX_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    payload = fetch_json(url)
    if payload is None:
        return []
    works = payload.get("results", [])
    candidates = [_openalex_candidate(work, language) for work in works]
    return [c for c in candidates if c is not None]
```

Extend `_SOURCES`:

```python
_SOURCES = (
    ("pubmed", search_pubmed),
    ("crossref", search_crossref),
    ("semantic_scholar", search_semantic_scholar),
    ("openalex", search_openalex),
)
```

Update the module docstring's first line to
`"""Live, verified evidence search across PubMed, Crossref, Semantic Scholar and OpenAlex.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`

```bash
git add src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git commit -m "Add OpenAlex as a fourth live-search source"
```

---

### Task 3: Year and publication-type filters

`run_live_search` and the `search_evidence_live` MCP tool gain optional
`year_from`, `year_to`, `publication_types` (allowed values: `"meta_analysis"`,
`"systematic_review"`, `"rct"` — anything else is rejected with a readable error).
Per-source fidelity:

| source | year filter | type filter |
|---|---|---|
| PubMed | `AND ("Y1"[dp] : "Y2"[dp])` term suffix | `AND (meta-analysis[pt] OR …)` — faithful, server-side |
| Crossref | `filter=from-pub-date:Y1-01-01,until-pub-date:Y2-12-31` | `type:journal-article` only (bibliographic type, not design) |
| Semantic Scholar | `year=Y1-Y2` | `publicationTypes=MetaAnalysis,Review,ClinicalTrial` (conservative superset) |
| OpenAlex | `filter=from_publication_date:…,to_publication_date:…` | none server-side; post-filter drops clearly incompatible work types (book, dataset, …) |

Where a source cannot express a type filter faithfully, the candidate passes through
with `suggested_study_type=None` — **never silently dropped**; the agent grades.

**Files:**
- Modify: `src/performance_agent/evidence/live_search.py`
- Modify: `src/performance_agent/server/evidence_tools.py`
- Test: `tests/evidence/test_live_search.py`
- Test: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_live_search.py` (extend the live_search import with
`SearchFilters, _crossref_filter, _pubmed_term`; add `import pytest` if not present):

```python
def test_pubmed_term_encodes_year_range_and_types():
    filters = SearchFilters(
        year_from=2016, year_to=2026, publication_types=("meta_analysis", "rct")
    )
    term = _pubmed_term("hypertrophy volume", filters)
    assert term.startswith("hypertrophy volume")
    assert 'AND ("2016"[dp] : "2026"[dp])' in term
    assert "AND (meta-analysis[pt] OR randomized controlled trial[pt])" in term


def test_pubmed_term_open_ended_year_bounds():
    term = _pubmed_term("tapering", SearchFilters(year_from=2016))
    assert 'AND ("2016"[dp] : "3000"[dp])' in term
    term = _pubmed_term("tapering", SearchFilters(year_to=2020))
    assert 'AND ("1000"[dp] : "2020"[dp])' in term


def test_pubmed_term_without_filters_is_unchanged():
    assert _pubmed_term("tapering", SearchFilters()) == "tapering"


def test_crossref_filter_clause():
    filters = SearchFilters(year_from=2016, year_to=2026, publication_types=("rct",))
    assert _crossref_filter(filters) == (
        "from-pub-date:2016-01-01,until-pub-date:2026-12-31,type:journal-article"
    )
    assert _crossref_filter(SearchFilters()) == ""


def test_semantic_scholar_url_carries_year_and_types(monkeypatch):
    seen: list[str] = []

    def fake_fetch_json(url: str) -> dict | None:
        seen.append(url)
        return {"data": []}

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    filters = SearchFilters(
        year_from=2016, year_to=2026, publication_types=("meta_analysis", "systematic_review")
    )
    search_semantic_scholar("tapering", "en", filters)
    assert "year=2016-2026" in seen[0]
    assert "publicationTypes=MetaAnalysis,Review" in seen[0]


def test_openalex_url_carries_date_filter_and_postfilters_types(monkeypatch):
    seen: list[str] = []
    payload = {
        "results": [
            {"title": "A dataset", "doi": "https://doi.org/10.1/d", "type": "dataset"},
            {"title": "A review", "doi": "https://doi.org/10.1/r", "type": "review"},
            {"title": "Untyped", "doi": "https://doi.org/10.1/u"},
        ]
    }

    def fake_fetch_json(url: str) -> dict | None:
        seen.append(url)
        return payload

    monkeypatch.setattr(live_search_module, "fetch_json", fake_fetch_json)
    filters = SearchFilters(year_from=2016, year_to=2026, publication_types=("rct",))
    candidates = search_openalex("tapering", "en", filters)
    assert "filter=from_publication_date:2016-01-01,to_publication_date:2026-12-31" in seen[0]
    # incompatible type dropped; ambiguous/missing types pass through ungraded
    assert [c.doi for c in candidates] == ["10.1/r", "10.1/u"]
    assert all(c.suggested_study_type is None for c in candidates)


def test_run_live_search_rejects_unknown_publication_type():
    with pytest.raises(ValueError, match="cohort"):
        run_live_search({"en": "x"}, publication_types=["cohort"])


def test_run_live_search_rejects_inverted_year_range():
    with pytest.raises(ValueError, match="year_from"):
        run_live_search({"en": "x"}, year_from=2026, year_to=2016)


def test_run_live_search_passes_filters_to_every_source(monkeypatch):
    received: list[SearchFilters] = []

    def fake_source(_term, _language, filters):
        received.append(filters)
        return []

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        tuple((name, fake_source) for name, _fn in live_search_module._SOURCES),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    run_live_search({"en": "x"}, year_from=2016, publication_types=["meta_analysis"])

    assert len(received) == 4
    assert all(f == SearchFilters(year_from=2016, publication_types=("meta_analysis",)) for f in received)
```

The existing `_SOURCES`-monkeypatching tests (`test_run_live_search_verifies_and_reports_failures`,
`test_run_live_search_drops_unverified_candidates`, `test_run_live_search_fans_out_to_four_sources`)
must have their fake source functions gain a third `_filters` parameter, e.g.
`def fake_search_pubmed(_term, language, _filters):` — update them in this step.

Append to `tests/server/test_evidence_tools.py`:

```python
@pytest.mark.anyio
async def test_search_evidence_live_forwards_filters(client, monkeypatch):
    received: dict = {}

    def fake_run_live_search(language_terms, year_from=None, year_to=None, publication_types=None):
        received.update(
            language_terms=language_terms,
            year_from=year_from,
            year_to=year_to,
            publication_types=publication_types,
        )
        return LiveSearchOutcome(candidates=[], failed_sources=[])

    monkeypatch.setattr(evidence_tools_module, "run_live_search", fake_run_live_search)

    result = await client.call_tool(
        "search_evidence_live",
        {
            "language_terms": {"en": "tapering"},
            "year_from": 2016,
            "year_to": 2026,
            "publication_types": ["meta_analysis", "rct"],
        },
    )
    assert not result.isError
    assert received == {
        "language_terms": {"en": "tapering"},
        "year_from": 2016,
        "year_to": 2026,
        "publication_types": ["meta_analysis", "rct"],
    }


@pytest.mark.anyio
async def test_search_evidence_live_rejects_bad_publication_type(client):
    result = await client.call_tool(
        "search_evidence_live",
        {"language_terms": {"en": "tapering"}, "publication_types": ["cohort"]},
    )
    assert result.isError
    assert "cohort" in result.content[0].text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py tests/server/test_evidence_tools.py -q`
Expected: FAIL — `ImportError: cannot import name 'SearchFilters'`.

- [ ] **Step 3: Implement**

In `src/performance_agent/evidence/live_search.py`, add after the `_POLITE_DELAY_S` block:

```python
_ALLOWED_PUBLICATION_TYPES = ("meta_analysis", "systematic_review", "rct")


@dataclass(frozen=True)
class SearchFilters:
    """Optional narrowing, applied per source at whatever fidelity each supports."""

    year_from: int | None = None
    year_to: int | None = None
    publication_types: tuple[str, ...] | None = None


def _validated_filters(
    year_from: int | None, year_to: int | None, publication_types: list[str] | None
) -> SearchFilters:
    if publication_types is not None:
        unknown = sorted(set(publication_types) - set(_ALLOWED_PUBLICATION_TYPES))
        if unknown:
            msg = (
                f"unsupported publication_types {unknown}; "
                f"allowed: {list(_ALLOWED_PUBLICATION_TYPES)}"
            )
            raise ValueError(msg)
    if year_from is not None and year_to is not None and year_from > year_to:
        msg = f"year_from ({year_from}) must not exceed year_to ({year_to})"
        raise ValueError(msg)
    types = tuple(dict.fromkeys(publication_types)) if publication_types else None
    return SearchFilters(year_from=year_from, year_to=year_to, publication_types=types)
```

PubMed — add the term builder and thread it through `search_pubmed`:

```python
_PUBMED_TYPE_FILTERS = {
    "meta_analysis": "meta-analysis[pt]",
    "systematic_review": "systematic review[pt]",
    "rct": "randomized controlled trial[pt]",
}


def _pubmed_term(term: str, filters: SearchFilters) -> str:
    parts = [term]
    if filters.year_from is not None or filters.year_to is not None:
        low = filters.year_from if filters.year_from is not None else 1000
        high = filters.year_to if filters.year_to is not None else 3000
        parts.append(f'AND ("{low}"[dp] : "{high}"[dp])')
    if filters.publication_types:
        clauses = " OR ".join(_PUBMED_TYPE_FILTERS[t] for t in filters.publication_types)
        parts.append(f"AND ({clauses})")
    return " ".join(parts)
```

```python
def search_pubmed(
    term: str, language: str, filters: SearchFilters = SearchFilters()
) -> list[LiveCandidate]:
    """Search PubMed, hydrating candidates with full abstracts via efetch.

    Year and publication-type filters are faithful here: both are expressed
    server-side in the esearch term ([dp] date range, [pt] publication types).
    """
    search_url = PUBMED_ESEARCH_URL.format(
        term=quote(_pubmed_term(term, filters)), limit=_SEARCH_LIMIT
    )
    # … rest unchanged from Task 1 …
```

Crossref — clause builder plus URL threading:

```python
def _crossref_filter(filters: SearchFilters) -> str:
    clauses = []
    if filters.year_from is not None:
        clauses.append(f"from-pub-date:{filters.year_from}-01-01")
    if filters.year_to is not None:
        clauses.append(f"until-pub-date:{filters.year_to}-12-31")
    if filters.publication_types:
        # Crossref indexes bibliographic type, not study design; journal-article is
        # the closest faithful narrowing. Candidates keep suggested_study_type=None
        # and pass through — the agent grades from the abstract.
        clauses.append("type:journal-article")
    return ",".join(clauses)


def search_crossref(
    term: str, language: str, filters: SearchFilters = SearchFilters()
) -> list[LiveCandidate]:
    """Search Crossref for term, returning candidates that carry a DOI."""
    url = CROSSREF_SEARCH_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    filter_clause = _crossref_filter(filters)
    if filter_clause:
        url = f"{url}&filter={filter_clause}"
    # … rest unchanged …
```

Semantic Scholar — conservative type map (its `Review` and `ClinicalTrial` are supersets
of systematic reviews and RCTs; candidates keep `suggested_study_type=None`):

```python
_SEMANTIC_SCHOLAR_TYPE_FILTERS = {
    "meta_analysis": "MetaAnalysis",
    "systematic_review": "Review",
    "rct": "ClinicalTrial",
}


def search_semantic_scholar(
    term: str, language: str, filters: SearchFilters = SearchFilters()
) -> list[LiveCandidate]:
    """Search Semantic Scholar for term, returning candidates with a DOI or PMID."""
    url = SEMANTIC_SCHOLAR_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    if filters.year_from is not None or filters.year_to is not None:
        low = filters.year_from if filters.year_from is not None else ""
        high = filters.year_to if filters.year_to is not None else ""
        url = f"{url}&year={low}-{high}"
    if filters.publication_types:
        labels = dict.fromkeys(
            _SEMANTIC_SCHOLAR_TYPE_FILTERS[t] for t in filters.publication_types
        )
        url = f"{url}&publicationTypes={','.join(labels)}"
    # … rest unchanged …
```

OpenAlex — date filter server-side, type post-filter on the returned `type` (dropping
only clearly incompatible types; ambiguous `article`/`review` and missing types pass
through ungraded):

```python
_OPENALEX_COMPATIBLE_TYPES = {"article", "review"}


def _openalex_candidate(
    work: dict, language: str, filters: SearchFilters
) -> LiveCandidate | None:
    title = work.get("title")
    doi = _openalex_doi(work)
    if not title or not doi:
        return None
    work_type = work.get("type")
    if (
        filters.publication_types
        and work_type is not None
        and work_type not in _OPENALEX_COMPATIBLE_TYPES
    ):
        # a book/dataset/dissertation cannot be a meta-analysis, review or RCT;
        # "article"/"review"/missing stays in with suggested_study_type=None.
        return None
    # … rest unchanged from Task 2 …


def search_openalex(
    term: str, language: str, filters: SearchFilters = SearchFilters()
) -> list[LiveCandidate]:
    """Search OpenAlex for term, returning candidates that carry a DOI."""
    url = OPENALEX_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    clauses = []
    if filters.year_from is not None:
        clauses.append(f"from_publication_date:{filters.year_from}-01-01")
    if filters.year_to is not None:
        clauses.append(f"to_publication_date:{filters.year_to}-12-31")
    if clauses:
        url = f"{url}&filter={','.join(clauses)}"
    payload = fetch_json(url)
    if payload is None:
        return []
    works = payload.get("results", [])
    candidates = [_openalex_candidate(work, language, filters) for work in works]
    return [c for c in candidates if c is not None]
```

`run_live_search` — validate, then pass filters into the fan-out:

```python
def run_live_search(
    language_terms: dict[str, str],
    year_from: int | None = None,
    year_to: int | None = None,
    publication_types: list[str] | None = None,
) -> LiveSearchOutcome:
    """Fan out language/term pairs across PubMed, Crossref, Semantic Scholar and OpenAlex.

    Optional filters narrow the search at each source's native fidelity (see the
    search_evidence_live tool docstring for the per-source table); a source that
    cannot express a filter faithfully returns its candidates ungraded rather than
    dropping them. One source/language failing does not blank out the others;
    failures are reported by name in the outcome instead of raising. Every
    surviving candidate has been independently re-verified (its DOI/PMID resolves)
    before being returned.
    """
    filters = _validated_filters(year_from, year_to, publication_types)
    raw: list[LiveCandidate] = []
    failed: list[str] = []
    # only the very first network call of the whole run skips the delay
    first_call = True
    for language, term in language_terms.items():
        for source_name, search_fn in _SOURCES:
            if not first_call:
                time.sleep(_POLITE_DELAY_S)
            first_call = False
            try:
                raw.extend(search_fn(term, language, filters))
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                # search_fn walks an untrusted third-party JSON response; a
                # malformed shape (e.g. items not a list, missing author keys)
                # should only drop this source/language, not abort the run.
                failed.append(f"{source_name}:{language}")
    return LiveSearchOutcome(candidates=_verify_candidates(_dedup(raw)), failed_sources=failed)
```

In `src/performance_agent/server/evidence_tools.py`, extend the tool signature (full
docstring lands in Task 7):

```python
def search_evidence_live(
    language_terms: dict[str, str],
    year_from: Annotated[int | None, Field(ge=1900, le=2100)] = None,
    year_to: Annotated[int | None, Field(ge=1900, le=2100)] = None,
    publication_types: list[str] | None = None,
) -> LiveSearchResults:
    # existing docstring for now — rewritten in Task 7
    outcome = run_live_search(
        language_terms,
        year_from=year_from,
        year_to=year_to,
        publication_types=publication_types,
    )
    # … rest unchanged …
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence tests/server/test_evidence_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`

```bash
git add src/performance_agent/evidence/live_search.py src/performance_agent/server/evidence_tools.py \
        tests/evidence/test_live_search.py tests/server/test_evidence_tools.py
git commit -m "Add year and publication-type filters to live search"
```

---

### Task 4: Budget 25 and evidence-tier ordering

`_SEARCH_LIMIT` goes 5 → 25 (polite delay unchanged). After dedup + verification,
candidates are ordered by evidence tier (meta_analysis → systematic_review → rct →
everything else, including `None`) and, within a tier, by year descending with `None`
years last.

**Files:**
- Modify: `src/performance_agent/evidence/live_search.py`
- Test: `tests/evidence/test_live_search.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_live_search.py` (extend the live_search import with
`_SEARCH_LIMIT, _tier_rank`):

```python
def test_search_limit_is_25():
    assert _SEARCH_LIMIT == 25


def test_tier_rank_orders_designs():
    assert _tier_rank(_candidate(suggested_study_type=StudyType.META_ANALYSIS)) == 0
    assert _tier_rank(_candidate(suggested_study_type=StudyType.SYSTEMATIC_REVIEW)) == 1
    assert _tier_rank(_candidate(suggested_study_type=StudyType.RCT)) == 2
    assert _tier_rank(_candidate(suggested_study_type=StudyType.COHORT)) == 3
    assert _tier_rank(_candidate(suggested_study_type=None)) == 3


def test_run_live_search_orders_by_tier_then_year(monkeypatch):
    synthetic = [
        _candidate(doi="10.1/rct-old", year=2010, suggested_study_type=StudyType.RCT),
        _candidate(doi="10.1/none-2024", year=2024, suggested_study_type=None),
        _candidate(doi="10.1/ma-2018", year=2018, suggested_study_type=StudyType.META_ANALYSIS),
        _candidate(doi="10.1/sr-2022", year=2022, suggested_study_type=StudyType.SYSTEMATIC_REVIEW),
        _candidate(doi="10.1/ma-2023", year=2023, suggested_study_type=StudyType.META_ANALYSIS),
        _candidate(doi="10.1/none-undated", year=None, suggested_study_type=None),
    ]

    def fake_source(_term, _language, _filters):
        return synthetic

    monkeypatch.setattr(
        live_search_module,
        "_SOURCES",
        (("pubmed", fake_source),),
    )
    monkeypatch.setattr(
        live_search_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(True, "A study", "resolved via Crossref"),
    )
    monkeypatch.setattr(live_search_module, "_POLITE_DELAY_S", 0)

    outcome = run_live_search({"en": "javelin"})

    assert [c.doi for c in outcome.candidates] == [
        "10.1/ma-2023",
        "10.1/ma-2018",
        "10.1/sr-2022",
        "10.1/rct-old",
        "10.1/none-2024",
        "10.1/none-undated",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py -q`
Expected: FAIL — `ImportError: cannot import name '_tier_rank'` (and the limit test).

- [ ] **Step 3: Implement**

In `src/performance_agent/evidence/live_search.py`:

```python
_SEARCH_LIMIT = 25
```

Add above `run_live_search`:

```python
_TIER_ORDER: dict[StudyType, int] = {
    StudyType.META_ANALYSIS: 0,
    StudyType.SYSTEMATIC_REVIEW: 1,
    StudyType.RCT: 2,
}
_DEFAULT_TIER = 3


def _tier_rank(candidate: LiveCandidate) -> int:
    """Evidence tier: meta-analysis → systematic review → RCT → everything else."""
    if candidate.suggested_study_type is None:
        return _DEFAULT_TIER
    return _TIER_ORDER.get(candidate.suggested_study_type, _DEFAULT_TIER)


def _ordering_key(candidate: LiveCandidate) -> tuple[int, int, int]:
    year_missing = 1 if candidate.year is None else 0
    return (_tier_rank(candidate), year_missing, -(candidate.year or 0))
```

And change the final line of `run_live_search` to:

```python
    verified = _verify_candidates(_dedup(raw))
    verified.sort(key=_ordering_key)
    return LiveSearchOutcome(candidates=verified, failed_sources=failed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_live_search.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`

```bash
git add src/performance_agent/evidence/live_search.py tests/evidence/test_live_search.py
git commit -m "Raise live-search budget to 25 and order candidates by evidence tier"
```

---

### Task 5: Title cross-check on the save path

`save_evidence` currently re-verifies only that the locator resolves; an agent could save
a real DOI under a fabricated title. Export the maintainer's 0.6 token-overlap check as
public `titles_match(claimed, registry)` in `verify.py` (it is `_titles_match` today) and
run it in `save_evidence`, rejecting mismatches with an error that names both titles.

**Files:**
- Modify: `src/performance_agent/evidence/verify.py` (rename `_titles_match` → `titles_match`)
- Modify: `src/performance_agent/server/evidence_tools.py`
- Test: `tests/evidence/test_verify.py`
- Test: `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_verify.py`:

```python
def test_titles_match_is_public_and_tolerant():
    assert verify_module.titles_match(
        "Effects of Tapering on Performance: A Meta-Analysis",
        "Effects of tapering on performance — a meta-analysis",
    )


def test_titles_match_rejects_disjoint_titles():
    assert not verify_module.titles_match(
        "Javelin throw training review", "Completely Different Study About Fish"
    )
```

Append to `tests/server/test_evidence_tools.py` (the existing
`test_save_evidence_persists_and_is_immediately_searchable` already saves with a matching
registry title, covering the positive path):

```python
@pytest.mark.anyio
async def test_save_evidence_rejects_title_mismatch(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_reference",
        lambda _doi, _pmid: ResolvedReference(
            True, "Completely Different Study About Fish", "resolved via Crossref"
        ),
    )

    result = await client.call_tool("save_evidence", {"entry": _live_entry_payload()})

    assert result.isError
    text = result.content[0].text
    assert "Javelin throw training review" in text
    assert "Completely Different Study About Fish" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence/test_verify.py tests/server/test_evidence_tools.py -q`
Expected: FAIL — `AttributeError: … has no attribute 'titles_match'` and the mismatch save succeeds.

- [ ] **Step 3: Implement**

In `src/performance_agent/evidence/verify.py`, rename `_titles_match` and update its two
call sites (`_title_result`):

```python
def titles_match(claimed_title: str, registry_title: str) -> bool:
    """Token-overlap containment >= 0.6 — the corpus anti-fabrication title check.

    Used by the maintainer verification CLI and by save_evidence to cross-check
    an agent-supplied title against what the registry actually says.
    """
    claimed_tokens = _tokens(claimed_title)
    registry_tokens = _tokens(registry_title)
    if not claimed_tokens or not registry_tokens:
        return False
    overlap = len(claimed_tokens & registry_tokens)
    containment = overlap / min(len(claimed_tokens), len(registry_tokens))
    return containment >= _TITLE_MATCH_THRESHOLD
```

In `src/performance_agent/server/evidence_tools.py`, import it
(`from performance_agent.evidence.verify import resolve_reference, titles_match`) and
extend `save_evidence` after the resolution check:

```python
    resolved = resolve_reference(entry.doi, entry.pmid)
    if not resolved.ok:
        msg = f"{entry.id}: could not verify before saving — {resolved.detail}"
        raise ValueError(msg)
    if resolved.title is not None and not titles_match(entry.title, resolved.title):
        msg = (
            f"{entry.id}: title mismatch — you supplied {entry.title!r} but the "
            f"registry says {resolved.title!r}; fix the title (or the locator) and retry"
        )
        raise ValueError(msg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence tests/server/test_evidence_tools.py -q`
Expected: PASS (including the pre-existing save tests, whose mocked registry title
already matches their entry title).

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`

```bash
git add src/performance_agent/evidence/verify.py src/performance_agent/server/evidence_tools.py \
        tests/evidence/test_verify.py tests/server/test_evidence_tools.py
git commit -m "Cross-check titles against the registry when saving evidence"
```

---

### Task 6: ISBN-verified `reference_book` category

New study type `reference_book`, ceiling `expert` (a book sources technique and pedagogy
prose; it never overrides a meta-analysis). Locator is an ISBN, verified against Open
Library with a Google Books fallback — the same anti-fabrication principle as DOI/PMID.
Books enter only the **personal** corpus: the bundled seed corpus stays studies-only,
because books are a user-recommendation surface (an athlete's coach recommends a book to
*that athlete*), not shipped evidence. First documented entry: *Manuel ultime de
musculation — Connaissances scientifiques et méthodologie* (Pourcelot/Reiss/Caverne/
Albignac, Éditions Amphora, 2023, ISBN 978-2-7576-0546-2), graded expert_opinion-ceiling
`expert`.

The grading-ceiling mechanism in `schemas.py` is the `GRADING_CEILING: dict[StudyType,
EvidenceLevel]` table enforced by the `_enforce_grading_ceiling` model validator — the new
type extends the table in-style. The locator rule lives in `_require_locator`, extended
so books require an ISBN and non-books still require DOI/PMID (and may not carry an ISBN).

**Files:**
- Modify: `src/performance_agent/evidence/schemas.py`
- Modify: `src/performance_agent/evidence/verify.py` (`resolve_isbn` — network stays here)
- Modify: `src/performance_agent/evidence/citations.py` (ISBN rendering + anti-fabrication)
- Modify: `src/performance_agent/server/evidence_tools.py` (`save_evidence` dispatch, `verify_reference` isbn param)
- Test: `tests/evidence/test_schemas.py`, `tests/evidence/test_verify.py`,
  `tests/evidence/test_citations.py`, `tests/server/test_evidence_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/evidence/test_schemas.py` (match the file's existing entry-builder
style; imports of `EvidenceEntry`, `StudyType`, `ValidationError`, `pytest` already exist
there — extend as needed):

```python
def test_reference_book_requires_isbn():
    entry = EvidenceEntry(
        id="book-manuel-ultime-musculation",
        title="Manuel ultime de musculation — Connaissances scientifiques et méthodologie",
        authors=["Pourcelot C", "Reiss D", "Caverne A", "Albignac T"],
        year=2023,
        journal="Éditions Amphora",
        study_type=StudyType.REFERENCE_BOOK,
        conclusions="Technique and pedagogy reference for strength training.",
        evidence_level="expert",
        isbn="978-2-7576-0546-2",
    )
    assert entry.isbn == "978-2-7576-0546-2"

    with pytest.raises(ValidationError, match="ISBN"):
        EvidenceEntry(
            id="book-without-isbn",
            title="A book",
            authors=["Doe J"],
            year=2023,
            study_type=StudyType.REFERENCE_BOOK,
            conclusions="x",
            evidence_level="expert",
        )


def test_reference_book_ceiling_is_expert():
    with pytest.raises(ValidationError, match="ceiling"):
        EvidenceEntry(
            id="book-overgraded",
            title="A book",
            authors=["Doe J"],
            year=2023,
            study_type=StudyType.REFERENCE_BOOK,
            conclusions="x",
            evidence_level="strong",
            isbn="978-2-7576-0546-2",
        )


def test_non_book_entries_may_not_carry_isbn():
    with pytest.raises(ValidationError, match="reference_book"):
        EvidenceEntry(
            id="study-with-isbn",
            title="A study",
            authors=["Doe J"],
            year=2020,
            study_type=StudyType.RCT,
            conclusions="x",
            evidence_level="moderate",
            doi="10.1000/sample",
            isbn="978-2-7576-0546-2",
        )
```

Append to `tests/evidence/test_verify.py`:

```python
def test_resolve_isbn_via_open_library(monkeypatch):
    def fake_fetch_json(url: str) -> dict | None:
        assert url == "https://openlibrary.org/isbn/9782757605462.json"
        return {"title": "Manuel ultime de musculation"}

    monkeypatch.setattr(verify_module, "fetch_json", fake_fetch_json)
    resolved = verify_module.resolve_isbn("978-2-7576-0546-2")
    assert resolved.ok
    assert resolved.title == "Manuel ultime de musculation"
    assert "Open Library" in resolved.detail


def test_resolve_isbn_falls_back_to_google_books(monkeypatch):
    def fake_fetch_json(url: str) -> dict | None:
        if "openlibrary" in url:
            return None
        assert "googleapis.com/books/v1/volumes?q=isbn:9782757605462" in url
        return {"items": [{"volumeInfo": {"title": "Manuel ultime de musculation"}}]}

    monkeypatch.setattr(verify_module, "fetch_json", fake_fetch_json)
    resolved = verify_module.resolve_isbn("9782757605462")
    assert resolved.ok
    assert "Google Books" in resolved.detail


def test_resolve_isbn_rejects_malformed_isbn():
    resolved = verify_module.resolve_isbn("not-an-isbn")
    assert not resolved.ok
    assert "ISBN" in resolved.detail


def test_resolve_isbn_reports_unresolvable(monkeypatch):
    monkeypatch.setattr(verify_module, "fetch_json", lambda _url: None)
    resolved = verify_module.resolve_isbn("978-2-7576-0546-2")
    assert not resolved.ok
    assert "did not resolve" in resolved.detail
```

Append to `tests/evidence/test_citations.py` (its `ENTRY` constant is a study; add a
book entry alongside):

```python
BOOK = EvidenceEntry(
    id="book-manuel-ultime-musculation",
    title="Manuel ultime de musculation — Connaissances scientifiques et méthodologie",
    authors=["Pourcelot C", "Reiss D", "Caverne A", "Albignac T"],
    year=2023,
    journal="Éditions Amphora",
    study_type="reference_book",
    conclusions="Technique and pedagogy reference for strength training.",
    evidence_level="expert",
    isbn="978-2-7576-0546-2",
)


def test_format_citation_includes_isbn():
    citation = format_citation(BOOK)
    assert "ISBN: 978-2-7576-0546-2." in citation
    assert "Éditions Amphora." in citation


def test_known_isbn_reference_passes():
    text = "Technique cues follow the Manuel ultime (ISBN 978-2-7576-0546-2)."
    assert find_unknown_references(text, [BOOK]) == []


def test_unknown_isbn_reference_is_flagged():
    text = "As shown in some book (ISBN: 978-0-0000-0000-2)."
    assert find_unknown_references(text, [BOOK]) == ["ISBN:978-0-0000-0000-2"]


def test_isbn_matching_ignores_hyphenation():
    text = "See ISBN 9782757605462 for details."
    assert find_unknown_references(text, [BOOK]) == []
```

Append to `tests/server/test_evidence_tools.py` (integration: mocks Open Library and
saves this exact book; also the `verify_reference` isbn param):

```python
import performance_agent.evidence.verify as verify_module


_MANUEL_ULTIME = {
    "id": "book-manuel-ultime-musculation",
    "title": "Manuel ultime de musculation — Connaissances scientifiques et méthodologie",
    "authors": ["Pourcelot C", "Reiss D", "Caverne A", "Albignac T"],
    "year": 2023,
    "journal": "Éditions Amphora",
    "study_type": "reference_book",
    "conclusions": "Exercise-technique and pedagogy reference for strength training.",
    "evidence_level": "expert",
    "isbn": "978-2-7576-0546-2",
}


@pytest.mark.anyio
async def test_save_evidence_accepts_isbn_verified_reference_book(client, monkeypatch):
    def fake_fetch_json(url: str) -> dict | None:
        assert "openlibrary.org/isbn/9782757605462.json" in url
        return {"title": "Manuel ultime de musculation"}

    monkeypatch.setattr(verify_module, "fetch_json", fake_fetch_json)

    save_result = await client.call_tool("save_evidence", {"entry": _MANUEL_ULTIME})
    assert not save_result.isError
    assert save_result.structuredContent["path"].endswith("evidence_extra.yaml")

    search_result = await client.call_tool("search_evidence", {"query": "musculation"})
    ids = {hit["id"] for hit in search_result.structuredContent["hits"]}
    assert "book-manuel-ultime-musculation" in ids

    check = await client.call_tool(
        "check_citations", {"text": "Voir le Manuel ultime (ISBN 978-2-7576-0546-2)."}
    )
    assert check.structuredContent["ok"] is True


@pytest.mark.anyio
async def test_save_evidence_rejects_book_with_mismatched_title(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_isbn",
        lambda _isbn: ResolvedReference(
            True, "Completely Different Book About Fish", "resolved via Open Library"
        ),
    )
    result = await client.call_tool("save_evidence", {"entry": _MANUEL_ULTIME})
    assert result.isError
    assert "Completely Different Book About Fish" in result.content[0].text


@pytest.mark.anyio
async def test_verify_reference_resolves_isbn(client, monkeypatch):
    monkeypatch.setattr(
        evidence_tools_module,
        "resolve_isbn",
        lambda _isbn: ResolvedReference(
            True, "Manuel ultime de musculation", "resolved via Open Library"
        ),
    )
    result = await client.call_tool("verify_reference", {"isbn": "978-2-7576-0546-2"})
    assert not result.isError
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["title"] == "Manuel ultime de musculation"
```

Note: the title cross-check passes for the real book because `titles_match` uses
containment over the *smaller* token set — Open Library's short title
("Manuel ultime de musculation") is fully contained in the entry's full title.

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence tests/server/test_evidence_tools.py -q`
Expected: FAIL — `AttributeError: … StudyType has no attribute 'REFERENCE_BOOK'`,
`resolve_isbn` missing, unknown `isbn` field.

- [ ] **Step 3: Implement**

`src/performance_agent/evidence/schemas.py` — extend the enum, the ceiling table, the
entry, and the module docstring:

```python
"""Schemas and grading rules for the evidence corpus.

The grading ceiling is the honesty rule of spec v2 §5: an entry's evidence
level can never exceed what its study design can support.

The corpus admits journal-indexed work carrying a DOI or PMID, plus
reference books carrying an ISBN (capped at expert opinion — a book sources
technique and pedagogy prose, never overrides a meta-analysis). Books live
only in the athlete's personal corpus: they are a user-recommendation
surface, so the bundled seed corpus stays studies-only. Guideline documents
without any locator remain out of scope for now (deliberate, revisit if
curation drops a candidate for this reason).
"""
```

```python
class StudyType(StrEnum):
    """Study designs, strongest first (spec v2 §1 hierarchy)."""

    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    RCT = "rct"
    COHORT = "cohort"
    CROSS_SECTIONAL = "cross_sectional"
    CONSENSUS = "consensus"
    EXPERT_OPINION = "expert_opinion"
    REFERENCE_BOOK = "reference_book"
```

Add to `GRADING_CEILING`:

```python
    StudyType.REFERENCE_BOOK: EvidenceLevel.EXPERT,
```

Add the field to `EvidenceEntry` (after `pmid`):

```python
    isbn: str | None = None
```

Replace `_require_locator`:

```python
    @model_validator(mode="after")
    def _require_locator(self) -> Self:
        if self.study_type is StudyType.REFERENCE_BOOK:
            if self.isbn is None:
                msg = f"{self.id}: a reference_book entry needs an ISBN to be citable"
                raise ValueError(msg)
            return self
        if self.isbn is not None:
            msg = f"{self.id}: only reference_book entries may carry an ISBN"
            raise ValueError(msg)
        if self.doi is None and self.pmid is None:
            msg = f"{self.id}: an entry needs a DOI or a PMID to be citable"
            raise ValueError(msg)
        return self
```

`src/performance_agent/evidence/verify.py` — add below `resolve_reference`:

```python
OPENLIBRARY_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"
GOOGLE_BOOKS_ISBN_URL = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
_ISBN_SHAPE = re.compile(r"\d{9}[\dXx]|\d{13}")


def _normalized_isbn(isbn: str) -> str:
    return re.sub(r"[\s-]", "", isbn)


def _google_books_title(payload: dict) -> str | None:
    for item in payload.get("items") or []:
        info = item.get("volumeInfo", {})
        title = info.get("title")
        if title:
            subtitle = info.get("subtitle")
            return f"{title} {subtitle}".strip() if subtitle else title
    return None


def resolve_isbn(isbn: str) -> ResolvedReference:
    """Resolve an ISBN against Open Library, falling back to Google Books.

    The reference_book counterpart of resolve_reference: same anti-fabrication
    principle, different registry. Both endpoints are keyless.
    """
    normalized = _normalized_isbn(isbn)
    if not _ISBN_SHAPE.fullmatch(normalized):
        return ResolvedReference(False, None, f"not a valid ISBN-10/ISBN-13 shape: {isbn}")
    payload = fetch_json(OPENLIBRARY_ISBN_URL.format(isbn=normalized))
    if payload is not None and payload.get("title"):
        return ResolvedReference(True, payload["title"], "resolved via Open Library")
    fallback = fetch_json(GOOGLE_BOOKS_ISBN_URL.format(isbn=normalized))
    if fallback is not None:
        title = _google_books_title(fallback)
        if title is not None:
            return ResolvedReference(True, title, "resolved via Google Books")
    return ResolvedReference(False, None, f"ISBN did not resolve: {isbn}")
```

`src/performance_agent/evidence/citations.py` — extend rendering and the checker:

```python
_ISBN_PATTERN = re.compile(
    r"\bISBN[:\s]*((?:97[89][\s-]?)?(?:\d[\s-]?){9}[\dXx])\b", re.IGNORECASE
)


def _normalized_isbn(isbn: str) -> str:
    return re.sub(r"[\s-]", "", isbn).upper()
```

In `format_citation`, after the `pmid` branch:

```python
    if entry.isbn:
        parts.append(f"ISBN: {entry.isbn}.")
```

In `find_unknown_references`, add before the `return`:

```python
    known_isbns = {_normalized_isbn(entry.isbn) for entry in corpus if entry.isbn}
    for isbn in _ISBN_PATTERN.findall(text):
        if _normalized_isbn(isbn) not in known_isbns:
            unknown.append(f"ISBN:{isbn}")
```

Also update the module docstring's second sentence to
`The checker scans prose for DOI/PMID/ISBN-shaped strings that are not in the corpus;`.

`src/performance_agent/server/evidence_tools.py` — import `resolve_isbn` and `StudyType`
is already imported; dispatch in `save_evidence` (replacing the single `resolve_reference`
line, keeping the Task 5 title check which now covers both paths):

```python
    if entry.study_type is StudyType.REFERENCE_BOOK:
        resolved = resolve_isbn(entry.isbn or "")
    else:
        resolved = resolve_reference(entry.doi, entry.pmid)
    if not resolved.ok:
        msg = f"{entry.id}: could not verify before saving — {resolved.detail}"
        raise ValueError(msg)
    if resolved.title is not None and not titles_match(entry.title, resolved.title):
        ...  # unchanged from Task 5
```

And `verify_reference` gains the param (docstring finalized in Task 7):

```python
def verify_reference(
    doi: str | None = None, pmid: str | None = None, isbn: str | None = None
) -> ReferenceResolution:
    """Confirm a DOI, PMID or ISBN found outside search_evidence_live actually resolves.

    DOI/PMID resolve against Crossref/PubMed; an ISBN (reference books only)
    resolves against Open Library with a Google Books fallback. Never save an
    entry whose locator did not resolve here.
    """
    resolved = resolve_isbn(isbn) if isbn else resolve_reference(doi, pmid)
    return ReferenceResolution(ok=resolved.ok, title=resolved.title, detail=resolved.detail)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/evidence tests/server -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`

```bash
git add src/performance_agent/evidence/schemas.py src/performance_agent/evidence/verify.py \
        src/performance_agent/evidence/citations.py src/performance_agent/server/evidence_tools.py \
        tests/evidence/test_schemas.py tests/evidence/test_verify.py \
        tests/evidence/test_citations.py tests/server/test_evidence_tools.py
git commit -m "Add ISBN-verified reference_book evidence category"
```

---

### Task 7: Tool docstrings, docs, and full sweep

Finalize the MCP tool surface documentation (per-source fidelity table, tier ordering,
25/source budget, abstracts, reference-book path), refresh the README evidence bullets,
and run the full verification sweep. Tool count stays **41** — no new tools;
`verify_reference` only gained a parameter (`docs/installing.md:205` and `README.md:109`
keep saying 41 and need no change).

README/`docs/installing.md` were read for stale descriptions of the old behavior:
neither describes the source list, the 5-result limit, or the save path in prose — the
only evidence text is the README feature bullet, which predates live search entirely.
So there is nothing stale to rewrite; instead the README bullet list gains the missing
live-search line (exact old/new below). This is the "personal-corpus documentation
example" carrier: the *Manuel ultime de musculation* book is named there as the first
reference-book example, and it is NOT added to the bundled seed corpus — books are a
user-recommendation surface, per Task 6.

**Files:**
- Modify: `src/performance_agent/server/evidence_tools.py` (docstrings only)
- Modify: `README.md`

- [ ] **Step 1: Rewrite the two tool docstrings**

`search_evidence_live` (body unchanged from Task 3):

```python
def search_evidence_live(
    language_terms: dict[str, str],
    year_from: Annotated[int | None, Field(ge=1900, le=2100)] = None,
    year_to: Annotated[int | None, Field(ge=1900, le=2100)] = None,
    publication_types: list[str] | None = None,
) -> LiveSearchResults:
    """Search PubMed, OpenAlex, Crossref and Semantic Scholar for studies outside the corpus.

    language_terms maps an ISO language code to a search term YOU translate for
    that language, e.g. {"en": "javelin throw training", "de": "Speerwurf
    Training"}. Up to 25 results per source per language; DOI/PMID dedup across
    sources; every returned candidate has already been verified (its DOI/PMID
    resolves against Crossref or PubMed). Candidates arrive ordered by evidence
    tier — meta-analyses, then systematic reviews, then RCTs, then everything
    else — most recent first within a tier (unknown years last). PubMed
    candidates carry full abstracts (efetch); read them before grading.

    Optional filters — applied at each source's native fidelity, never by
    silently dropping candidates a source cannot classify:
    - year_from/year_to: PubMed [dp] range, Crossref from/until-pub-date,
      Semantic Scholar year=, OpenAlex from/to_publication_date. Faithful at
      all four sources.
    - publication_types (any of "meta_analysis", "systematic_review", "rct";
      anything else is rejected): faithful only at PubMed ([pt] tags). Crossref
      narrows to journal-article, Semantic Scholar to a conservative superset
      (MetaAnalysis/Review/ClinicalTrial), OpenAlex only drops clearly
      incompatible work types (books, datasets). Non-PubMed candidates keep
      suggested_study_type=null — read the abstract and propose a study_type
      yourself before calling save_evidence; the grading ceiling is enforced
      server-side regardless of what you propose.

    A source/language pair that failed to respond is listed in failed_sources —
    mention degraded coverage rather than silently under-searching.
    """
```

`save_evidence` (body unchanged from Task 6):

```python
def save_evidence(entry: EvidenceEntry) -> WrittenFile:
    """Persist a verified, graded study or reference book to your personal evidence corpus.

    The entry is re-verified here regardless of what you were told earlier by
    search_evidence_live or verify_reference — this tool never trusts a
    self-reported verified flag. Two independent checks run before anything is
    written: the locator must resolve (DOI/PMID via Crossref/PubMed; ISBN via
    Open Library/Google Books for study_type "reference_book"), and the title
    you supply must match the registry's title (0.6 token-overlap — a real DOI
    under an invented title is rejected). The grading ceiling
    (schemas.GRADING_CEILING) still applies: you cannot save a cross-sectional
    study as "strong", and a reference_book is always capped at "expert" — e.g.
    Manuel ultime de musculation (ISBN 978-2-7576-0546-2) enters as
    expert-opinion technique/pedagogy support, never as evidence against a
    meta-analysis. Books carry an isbn instead of doi/pmid; studies must not
    carry an isbn. Once saved, the entry is immediately searchable via
    search_evidence and its locator is recognized by check_citations.
    """
```

- [ ] **Step 2: Update the README feature bullets**

In `README.md`, replace the evidence bullet (old, exact):

```
- ✅ Evidence corpus: live-verified starter corpus of 10 studies with grading ceilings
  enforced by schema, Porter-stemmed FTS5 full-text search, an anti-fabrication
  `check_citations` tool, and a maintainer verification CLI that asserts registry title
  matches before an entry ships
```

with (new, exact):

```
- ✅ Evidence corpus: live-verified starter corpus of 10 studies with grading ceilings
  enforced by schema, Porter-stemmed FTS5 full-text search, an anti-fabrication
  `check_citations` tool (DOI, PMID and ISBN), and a maintainer verification CLI that
  asserts registry title matches before an entry ships
- ✅ Live evidence search across PubMed (full abstracts), OpenAlex, Crossref and
  Semantic Scholar: multilingual fan-out, year and publication-type filters, 25
  results per source with evidence-tier ordering, and a double verification gate
  (locator resolution + registry title cross-check) before anything can be saved or
  cited; ISBN-verified reference books (e.g. *Manuel ultime de musculation*) join the
  athlete's personal corpus capped at expert opinion
```

- [ ] **Step 3: Full test suite**

Run: `env -u VIRTUAL_ENV uv run pytest`
Expected: all pass; the run started from 524 collected tests and this plan adds roughly
40 (final count read from this un-`-q` run's header). No test may be skipped or xfailed
by this plan.

- [ ] **Step 4: Skills eval harness and tool count**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills`
Expected: PASS — the three skills declaring `search_evidence_live`/`save_evidence`/
`verify_reference` keep working because no tool was renamed, added, or removed (count
stays 41). A failure here means a tool docstring drifted from what a skill declares —
fix the docstring wording, not the skill.

- [ ] **Step 5: Zero-warning gate, stragglers, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format --check . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`
Expected: clean output, no warnings.

Run: `git status --short` — expected: only the files below. Then:

```bash
git add src/performance_agent/server/evidence_tools.py README.md
git commit -m "Document live-search v2 surface and refresh evidence docs"
```
