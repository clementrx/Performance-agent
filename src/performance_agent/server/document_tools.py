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
