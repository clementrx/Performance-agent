"""Load and validate the packaged evidence corpus."""

from importlib import resources

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


def load_corpus() -> list[EvidenceEntry]:
    """Load the corpus shipped inside the package."""
    data = resources.files("performance_agent.evidence") / "data" / "seed_corpus.yaml"
    return parse_manifest(data.read_text(encoding="utf-8"))
