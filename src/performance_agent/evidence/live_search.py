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
