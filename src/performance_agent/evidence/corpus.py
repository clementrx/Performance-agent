"""Load and validate the packaged evidence corpus."""

from importlib import resources

from performance_agent.evidence.manifest import parse_manifest

# no cycle: personal_corpus does not import this module
from performance_agent.evidence.personal_corpus import load_personal_entries
from performance_agent.evidence.schemas import EvidenceEntry

__all__ = ["load_corpus", "parse_manifest"]


def _packaged_manifest_text() -> str:
    data = resources.files("performance_agent.evidence") / "data" / "seed_corpus.yaml"
    return data.read_text(encoding="utf-8")


def load_corpus() -> list[EvidenceEntry]:
    """Load the packaged corpus merged with the athlete's live-discovered entries.

    Raises ValueError if a personal entry's id collides with a packaged one.
    """
    packaged = parse_manifest(_packaged_manifest_text())
    personal = load_personal_entries()
    seen = {entry.id for entry in packaged}
    for entry in personal:
        if entry.id in seen:
            msg = f"duplicate corpus id across packaged and personal corpus: {entry.id}"
            raise ValueError(msg)
        seen.add(entry.id)
    return packaged + personal
