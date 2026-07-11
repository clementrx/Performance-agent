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

_SEARCH_LIMIT = 25
_POLITE_DELAY_S = 0.5

_ALLOWED_PUBLICATION_TYPES = ("meta_analysis", "systematic_review", "rct")


@dataclass(frozen=True)
class SearchFilters:
    """Optional narrowing, applied per source at whatever fidelity each supports."""

    year_from: int | None = None
    year_to: int | None = None
    publication_types: tuple[str, ...] | None = None


_NO_FILTERS = SearchFilters()


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


def search_pubmed(
    term: str, language: str, filters: SearchFilters = _NO_FILTERS
) -> list[LiveCandidate]:
    """Search PubMed, hydrating candidates with full abstracts via efetch.

    Year and publication-type filters are faithful here: both are expressed
    server-side in the esearch term ([dp] date range, [pt] publication types).
    """
    search_url = PUBMED_ESEARCH_URL.format(
        term=quote(_pubmed_term(term, filters)), limit=_SEARCH_LIMIT
    )
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


CROSSREF_SEARCH_URL = (
    "https://api.crossref.org/works?query={term}&rows={limit}"
    "&mailto=performance-agent@users.noreply.github.com"
)
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
    term: str, language: str, filters: SearchFilters = _NO_FILTERS
) -> list[LiveCandidate]:
    """Search Crossref for term, returning candidates that carry a DOI."""
    url = CROSSREF_SEARCH_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    filter_clause = _crossref_filter(filters)
    if filter_clause:
        url = f"{url}&filter={filter_clause}"
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


_SEMANTIC_SCHOLAR_TYPE_FILTERS = {
    "meta_analysis": "MetaAnalysis",
    "systematic_review": "Review",
    "rct": "ClinicalTrial",
}


def search_semantic_scholar(
    term: str, language: str, filters: SearchFilters = _NO_FILTERS
) -> list[LiveCandidate]:
    """Search Semantic Scholar for term, returning candidates with a DOI or PMID."""
    url = SEMANTIC_SCHOLAR_URL.format(term=quote(term), limit=_SEARCH_LIMIT)
    if filters.year_from is not None or filters.year_to is not None:
        low = filters.year_from if filters.year_from is not None else ""
        high = filters.year_to if filters.year_to is not None else ""
        url = f"{url}&year={low}-{high}"
    if filters.publication_types:
        labels = dict.fromkeys(_SEMANTIC_SCHOLAR_TYPE_FILTERS[t] for t in filters.publication_types)
        url = f"{url}&publicationTypes={','.join(labels)}"
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


_OPENALEX_COMPATIBLE_TYPES = {"article", "review"}


def _openalex_candidate(work: dict, language: str, filters: SearchFilters) -> LiveCandidate | None:
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
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in work.get("authorships", [])
        if (a.get("author") or {}).get("display_name")
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


def search_openalex(
    term: str, language: str, filters: SearchFilters = _NO_FILTERS
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
    verified = _verify_candidates(_dedup(raw))
    verified.sort(key=_ordering_key)
    return LiveSearchOutcome(candidates=verified, failed_sources=failed)
