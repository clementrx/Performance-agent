"""Maintainer-only corpus verification against Crossref and PubMed.

End users never run this: entries ship pre-verified in the package. Run it
whenever the manifest changes:

    uv run python -m performance_agent.evidence.verify
"""

import json
import sys
import urllib.request
from dataclasses import dataclass

from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.schemas import EvidenceEntry

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
PUBMED_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
)
_TIMEOUT_S = 20


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of resolving one entry against its source registry."""

    entry_id: str
    ok: bool
    detail: str
    retrieved_title: str | None = None


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        return None


def _title_from_crossref(payload: dict) -> str | None:
    titles = payload.get("message", {}).get("title") or []
    return titles[0] if titles else None


def _title_from_pubmed(payload: dict, pmid: str) -> str | None:
    return payload.get("result", {}).get(pmid, {}).get("title")


def verify_entry(entry: EvidenceEntry) -> VerificationResult:
    """Resolve the entry's DOI (preferred) or PMID and report what the registry says."""
    if entry.doi:
        payload = _fetch_json(CROSSREF_URL.format(doi=entry.doi))
        if payload is None:
            return VerificationResult(entry.id, False, f"DOI did not resolve: {entry.doi}")
        return VerificationResult(
            entry.id, True, "resolved via Crossref", _title_from_crossref(payload)
        )
    payload = _fetch_json(PUBMED_URL.format(pmid=entry.pmid))
    if payload is None:
        return VerificationResult(entry.id, False, f"PMID did not resolve: {entry.pmid}")
    return VerificationResult(
        entry.id, True, "resolved via PubMed", _title_from_pubmed(payload, entry.pmid or "")
    )


def main() -> int:
    """Verify every corpus entry; print a comparison table for human review."""
    failures = 0
    for entry in load_corpus():
        result = verify_entry(entry)
        status = "OK " if result.ok else "FAIL"
        print(f"[{status}] {entry.id}: {result.detail}")
        if result.retrieved_title:
            print(f"       manifest: {entry.title}")
            print(f"       registry: {result.retrieved_title}")
        failures += 0 if result.ok else 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
