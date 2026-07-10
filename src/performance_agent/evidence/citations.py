"""Citation rendering and the anti-fabrication reference check.

Citations are ALWAYS rendered from corpus entries — never from free text. The
checker scans prose for DOI/PMID-shaped strings that are not in the corpus;
anything it finds is a fabricated or unverifiable reference.
"""

import re

from performance_agent.evidence.schemas import EvidenceEntry

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]]+", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"\bPMID:?\s*(\d{6,9})\b", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:"


def format_citation(entry: EvidenceEntry) -> str:
    """Render a human-readable citation from a corpus entry."""
    authors = ", ".join(entry.authors)
    parts = [f"{authors} ({entry.year}). {entry.title}."]
    if entry.journal:
        parts.append(f"{entry.journal}.")
    if entry.doi:
        parts.append(f"DOI: {entry.doi}.")
    if entry.pmid:
        parts.append(f"PMID: {entry.pmid}.")
    return " ".join(parts)


def find_unknown_references(text: str, corpus: list[EvidenceEntry]) -> list[str]:
    """Return DOI/PMID-shaped strings in the text that are not corpus entries."""
    known_dois = {entry.doi.casefold() for entry in corpus if entry.doi}
    known_pmids = {entry.pmid for entry in corpus if entry.pmid}
    unknown: list[str] = []
    for match in _DOI_PATTERN.findall(text):
        doi = match.rstrip(_TRAILING_PUNCTUATION)
        if doi.casefold() not in known_dois:
            unknown.append(doi)
    for pmid in _PMID_PATTERN.findall(text):
        if pmid not in known_pmids:
            unknown.append(f"PMID:{pmid}")
    return unknown
