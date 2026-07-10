"""Live, verified evidence search across PubMed, Crossref and Semantic Scholar.

Every function here returns raw candidates; nothing is citable until
run_live_search re-verifies each candidate's DOI/PMID via
evidence.verify.resolve_reference — the same check the packaged corpus goes
through in evidence/verify.py before shipping.
"""

import re
import time
from dataclasses import dataclass
from urllib.parse import quote

from performance_agent.evidence.schemas import StudyType
from performance_agent.evidence.verify import fetch_json, resolve_reference

PUBMED_ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term={term}&retmode=json&retmax={limit}"
)
PUBMED_ESUMMARY_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json"
)

_SEARCH_LIMIT = 5
_POLITE_DELAY_S = 0.5

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
