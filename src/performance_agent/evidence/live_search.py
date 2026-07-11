"""Live, verified evidence search across PubMed, Crossref, Semantic Scholar and OpenAlex.

PubMed candidates are hydrated with full abstracts via efetch. Every function
here returns raw candidates; nothing is citable until run_live_search
re-verifies each candidate's DOI/PMID via evidence.verify.resolve_reference —
the same check the packaged corpus goes through in evidence/verify.py before
shipping.
"""

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
    year: int | None
    journal: str | None
    abstract: str | None
    doi: str | None
    pmid: str | None
    suggested_study_type: StudyType | None
    source: str
    found_via_language: str


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
            continue
        collective = author.findtext("CollectiveName")
        if collective:
            authors.append(collective)
    return authors


def _pubmed_candidate(article: ElementTree.Element, language: str) -> LiveCandidate | None:
    pmid = article.findtext("MedlineCitation/PMID")
    title_node = article.find("MedlineCitation/Article/ArticleTitle")
    title = " ".join(title_node.itertext()).strip() if title_node is not None else ""
    if not pmid or not title:
        return None
    pubtypes = [
        node.text.strip()
        for node in article.findall("MedlineCitation/Article/PublicationTypeList/PublicationType")
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
    if not titles or not doi:
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
    if not title or not (doi or pmid):
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


_SOURCES = (
    ("pubmed", search_pubmed),
    ("crossref", search_crossref),
    ("semantic_scholar", search_semantic_scholar),
    ("openalex", search_openalex),
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
    verified = []
    first_call = True
    for candidate in candidates:
        if not first_call:
            time.sleep(_POLITE_DELAY_S)
        first_call = False
        if resolve_reference(candidate.doi, candidate.pmid).ok:
            verified.append(candidate)
    return verified


@dataclass(frozen=True)
class LiveSearchOutcome:
    """Verified candidates from a multilingual live search, plus what failed."""

    candidates: list[LiveCandidate]
    failed_sources: list[str]


def run_live_search(language_terms: dict[str, str]) -> LiveSearchOutcome:
    """Fan out language/term pairs across PubMed, Crossref, Semantic Scholar and OpenAlex.

    One source/language failing does not blank out the others; failures are
    reported by name in the outcome instead of raising. Every surviving candidate
    has been independently re-verified (its DOI/PMID resolves) before being
    returned — the same guarantee the packaged corpus gets from
    evidence/verify.py before shipping.
    """
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
                raw.extend(search_fn(term, language))
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                # search_fn walks an untrusted third-party JSON response; a
                # malformed shape (e.g. items not a list, missing author keys)
                # should only drop this source/language, not abort the run.
                failed.append(f"{source_name}:{language}")
    return LiveSearchOutcome(candidates=_verify_candidates(_dedup(raw)), failed_sources=failed)
