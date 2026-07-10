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
from performance_agent.evidence.schemas import STARS, EvidenceEntry, EvidenceLevel, StudyType


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
def _corpus_by_id() -> dict[str, EvidenceEntry]:
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


def register(mcp: FastMCP) -> None:
    """Register every evidence tool on the server."""
    for tool in (search_evidence, get_citation, check_citations):
        mcp.tool()(tool)
