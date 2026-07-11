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
from performance_agent.evidence.live_search import run_live_search
from performance_agent.evidence.personal_corpus import append_entry
from performance_agent.evidence.schemas import STARS, EvidenceEntry, EvidenceLevel, StudyType
from performance_agent.evidence.verify import resolve_reference


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


class LiveSearchResults(TypedDict):
    """Verified live-search candidates, plus any source/language that failed."""

    candidates: list[LiveCandidateResult]
    failed_sources: list[str]


class ReferenceResolution(TypedDict):
    """Whether a bare DOI/PMID resolves against Crossref/PubMed, and its title."""

    ok: bool
    title: str | None
    detail: str


class WrittenFile(TypedDict):
    """Path of the file the tool just wrote."""

    path: str


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


def _corpus_by_id() -> dict[str, EvidenceEntry]:
    return _index().by_id


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

    Multi-word queries match ANY term (OR), not all — adding terms broadens
    rather than narrows. Results are ordered most-relevant first: prefer the
    top hits and read each hit's conclusions before citing it. Word variants
    are stemmed (taper matches tapering).
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
            f"unknown evidence id {evidence_id!r}; only ids returned by search_evidence are citable"
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


def verify_reference(doi: str | None = None, pmid: str | None = None) -> ReferenceResolution:
    """Confirm a DOI or PMID found via general web search actually resolves.

    Call this before proposing save_evidence for anything found outside
    search_evidence_live — e.g. a reference surfaced by a general web search for a
    federation, thesis, or conference paper. Never save an entry whose locator did
    not resolve here.
    """
    resolved = resolve_reference(doi, pmid)
    return ReferenceResolution(ok=resolved.ok, title=resolved.title, detail=resolved.detail)


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
