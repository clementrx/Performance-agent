"""Render a saved program to PDF via Typst, behind the citation gate.

This is the spec's final anti-fabrication enforcement point: any DOI/PMID-shaped
reference in the report that is not in the evidence corpus ABORTS the render.
The .typ source is written next to the .pdf for user-owned transparency.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from performance_agent.evidence.citations import find_unknown_references, format_citation
from performance_agent.evidence.corpus import load_corpus
from performance_agent.evidence.schemas import STARS
from performance_agent.memory import store
from performance_agent.reports.source import ReportContext, ReportMode, build_report_source

REPORTS_DIR = "reports"
_COMPILE_TIMEOUT_S = 60

# Mirrors the two PMID forms recognized by evidence.citations: an explicit
# "PMID:" prefix or a PubMed URL. Bare digits in prose are never a citation.
_PMID_CONTEXT = r"(?:PMID:?\s*|(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/))"


@dataclass(frozen=True)
class RenderedReport:
    """Paths of the artifacts a render produced."""

    source_path: Path
    pdf_path: Path
    version: int
    mode: str
    locale: str


def _typst_binary() -> str | None:
    return shutil.which("typst")


def _pmid_cited(pmid: str, body: str) -> bool:
    return re.search(rf"{_PMID_CONTEXT}{re.escape(pmid)}\b", body, re.IGNORECASE) is not None


def _citations_for(body: str) -> list[str]:
    """Star-graded citations for every corpus entry whose locator appears in the body."""
    citations = []
    for entry in load_corpus():
        doi_hit = entry.doi and entry.doi.casefold() in body.casefold()
        pmid_hit = entry.pmid and _pmid_cited(entry.pmid, body)
        if doi_hit or pmid_hit:
            citations.append(f"{STARS[entry.evidence_level]} {format_citation(entry)}")
    return citations


def render_report_files(
    base_dir: Path, mode: ReportMode = "coach", version: int | None = None
) -> RenderedReport:
    """Validate, build, and compile the report; returns the artifact paths."""
    program = store.read_program(base_dir, version)
    if program is None:
        msg = "no program has been saved yet; call save_program first"
        raise ValueError(msg)
    frontmatter, body = program

    unknown = find_unknown_references(body, load_corpus())
    if unknown:
        msg = (
            "report aborted: the program cites references that are not in the "
            f"evidence corpus: {unknown}. Remove them or replace them with "
            "search_evidence results, then save an adapted program version."
        )
        raise ValueError(msg)

    profile = store.read_profile(base_dir)
    goals = {goal.id: goal for goal in store.read_goals(base_dir)}
    goal = goals.get(str(frontmatter.get("goal_id", "")))
    context = ReportContext(
        locale=profile.locale,
        mode=mode,
        athlete_name=profile.display_name or "—",
        goal_statement=goal.statement if goal else str(frontmatter.get("goal_id", "—")),
        version=int(str(frontmatter["version"])),
        created_on=str(frontmatter["created_on"]),
        reason=str(frontmatter["reason"]) if frontmatter.get("reason") else None,
        body_markdown=body,
        citations=_citations_for(body) if mode == "expert" else [],
    )
    source = build_report_source(context)

    reports_dir = base_dir / REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"program-v{context.version}-{mode}-{context.locale}"
    source_path = reports_dir / f"{stem}.typ"
    pdf_path = reports_dir / f"{stem}.pdf"
    source_path.write_text(source, encoding="utf-8")

    binary = _typst_binary()
    if binary is None:
        msg = (
            f"typst CLI not found; the report source was written to {source_path}. "
            "Install typst (https://typst.app, `brew install typst`) and retry."
        )
        raise ValueError(msg)
    try:
        completed = subprocess.run(
            [binary, "compile", str(source_path), str(pdf_path)],
            capture_output=True,
            timeout=_COMPILE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"typst compile timed out after {_COMPILE_TIMEOUT_S}s for {source_path}"
        raise ValueError(msg) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")[:500]
        msg = f"typst compile failed for {source_path}: {stderr}"
        raise ValueError(msg)
    return RenderedReport(
        source_path=source_path,
        pdf_path=pdf_path,
        version=context.version,
        mode=mode,
        locale=context.locale,
    )
