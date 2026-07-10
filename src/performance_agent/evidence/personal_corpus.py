"""Storage for evidence entries discovered via live search, kept per-athlete.

This file is never touched by a performance-agent upgrade and never shared with
the packaged corpus in the repo — each athlete grows their own.
"""

import os
from pathlib import Path

import yaml

from performance_agent.evidence.manifest import parse_manifest
from performance_agent.evidence.schemas import EvidenceEntry
from performance_agent.memory.paths import resolve_athlete_dir

PERSONAL_CORPUS_FILE = "evidence_extra.yaml"


def personal_corpus_path() -> Path:
    """Return the path to the athlete's personal evidence corpus file."""
    return resolve_athlete_dir() / PERSONAL_CORPUS_FILE


def load_personal_entries() -> list[EvidenceEntry]:
    """Return the athlete's live-discovered entries, or an empty list if none exist."""
    path = personal_corpus_path()
    if not path.exists():
        return []
    return parse_manifest(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def append_entry(entry: EvidenceEntry, known_ids: set[str]) -> Path:
    """Validate id uniqueness against known_ids and append entry; returns its path.

    known_ids should include every id already in use across BOTH the packaged and
    personal corpus — the caller (save_evidence) is responsible for building that
    set, since this module has no reason to know about the packaged corpus.
    """
    if entry.id in known_ids:
        msg = f"{entry.id}: an entry with this id already exists in the corpus"
        raise ValueError(msg)
    existing = load_personal_entries()
    updated = [*existing, entry]
    path = personal_corpus_path()
    _atomic_write(
        path,
        yaml.safe_dump(
            [e.model_dump(mode="json") for e in updated], sort_keys=False, allow_unicode=True
        ),
    )
    return path
