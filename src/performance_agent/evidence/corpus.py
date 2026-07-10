"""Load and validate the packaged evidence corpus."""

from importlib import resources

from performance_agent.evidence.manifest import parse_manifest
from performance_agent.evidence.schemas import EvidenceEntry

__all__ = ["load_corpus", "parse_manifest"]


def load_corpus() -> list[EvidenceEntry]:
    """Load the corpus shipped inside the package."""
    data = resources.files("performance_agent.evidence") / "data" / "seed_corpus.yaml"
    return parse_manifest(data.read_text(encoding="utf-8"))
