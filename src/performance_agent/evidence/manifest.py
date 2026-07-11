"""Parsing for evidence corpus manifests (YAML lists of EvidenceEntry)."""

import yaml

from performance_agent.evidence.schemas import EvidenceEntry


def parse_manifest(text: str) -> list[EvidenceEntry]:
    """Parse manifest YAML into validated entries; ids must be unique."""
    raw = yaml.safe_load(text) or []
    if not isinstance(raw, list):
        msg = "the corpus manifest must be a YAML list of entries"
        raise ValueError(msg)
    entries = [EvidenceEntry.model_validate(item) for item in raw]
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            msg = f"duplicate corpus id: {entry.id}"
            raise ValueError(msg)
        seen.add(entry.id)
    return entries
