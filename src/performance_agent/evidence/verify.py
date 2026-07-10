"""Maintainer-only corpus verification against Crossref and PubMed.

End users never run this: entries ship pre-verified in the package. Run it
whenever the manifest changes:

    uv run python -m performance_agent.evidence.verify
"""

import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass

from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.schemas import EvidenceEntry

CROSSREF_URL = "https://api.crossref.org/works/{doi}"
PUBMED_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
)
_TIMEOUT_S = 20
_USER_AGENT = "performance-agent-corpus-verify (https://github.com/performance-agent)"
_TITLE_MATCH_THRESHOLD = 0.6
_POLITE_DELAY_S = 0.5


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of resolving one entry against its source registry."""

    entry_id: str
    ok: bool
    detail: str
    retrieved_title: str | None = None


def _fetch_json(url: str) -> dict | None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _title_from_crossref(payload: dict) -> str | None:
    message = payload.get("message", {})
    titles = message.get("title") or []
    if not titles:
        return None
    subtitles = message.get("subtitle") or []
    return f"{titles[0]} {subtitles[0]}".strip() if subtitles else titles[0]


def _title_from_pubmed(payload: dict, pmid: str) -> str | None:
    return payload.get("result", {}).get(pmid, {}).get("title")


def _tokens(text: str) -> set[str]:
    return {token for token in re.sub(r"[^\w\s]", " ", text.casefold()).split() if token}


def _titles_match(manifest_title: str, registry_title: str) -> bool:
    manifest_tokens = _tokens(manifest_title)
    registry_tokens = _tokens(registry_title)
    if not manifest_tokens or not registry_tokens:
        return False
    overlap = len(manifest_tokens & registry_tokens)
    containment = overlap / min(len(manifest_tokens), len(registry_tokens))
    return containment >= _TITLE_MATCH_THRESHOLD


def _title_result(
    entry: EvidenceEntry, registry_title: str | None, source: str
) -> VerificationResult:
    if registry_title is None:
        return VerificationResult(entry.id, False, f"{source} returned no title")
    if not _titles_match(entry.title, registry_title):
        detail = f"TITLE MISMATCH: manifest={entry.title!r} registry={registry_title!r}"
        return VerificationResult(entry.id, False, detail, registry_title)
    return VerificationResult(entry.id, True, f"resolved via {source}", registry_title)


def verify_entry(entry: EvidenceEntry) -> VerificationResult:
    """Resolve the entry's DOI (preferred) or PMID and assert its title matches the registry."""
    if entry.doi:
        payload = _fetch_json(CROSSREF_URL.format(doi=entry.doi))
        if payload is None:
            return VerificationResult(entry.id, False, f"DOI did not resolve: {entry.doi}")
        return _title_result(entry, _title_from_crossref(payload), "Crossref")
    payload = _fetch_json(PUBMED_URL.format(pmid=entry.pmid))
    if payload is None:
        return VerificationResult(entry.id, False, f"PMID did not resolve: {entry.pmid}")
    return _title_result(entry, _title_from_pubmed(payload, entry.pmid or ""), "PubMed")


def main() -> int:
    """Verify every corpus entry; print a comparison table for human review."""
    failures = 0
    entries = load_corpus()
    for index, entry in enumerate(entries):
        if index:
            time.sleep(_POLITE_DELAY_S)
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
