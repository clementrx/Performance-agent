"""In-memory FTS5 search over the evidence corpus.

The corpus is small (hundreds of entries), so the index is rebuilt from the
manifest in-process — no cache files, no staleness, no extra infrastructure.
"""

import sqlite3
from dataclasses import dataclass

from performance_agent.evidence.schemas import (
    LEVEL_RANK,
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
    """Quote every term and OR them so user text can never be parsed as FTS5 syntax.

    OR (rather than FTS5's default AND) lets a multi-word query match entries
    that contain only some of the terms, with BM25 ranking surfacing the
    entries that match the most/best.
    """
    terms = [term.replace('"', "") for term in query.split()]
    return " OR ".join(f'"{term}"' for term in terms if term)


class EvidenceIndex:
    """Builds and queries an in-memory FTS5 index over corpus entries."""

    def __init__(self, entries: list[EvidenceEntry]) -> None:
        """Build the in-memory FTS5 index from corpus entries."""
        self._entries = {entry.id: entry for entry in entries}
        # Process-lifetime singleton (built once via lru_cache in the tools layer);
        # the :memory: connection is intentionally never closed.
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE evidence USING fts5("
            "id UNINDEXED, title, conclusions, population, tokenize='porter unicode61')"
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
            if min_level is not None and LEVEL_RANK[entry.evidence_level] < LEVEL_RANK[min_level]:
                continue
            hits.append(SearchHit(entry=entry, rank=rank))
            if len(hits) >= limit:
                break
        return hits
