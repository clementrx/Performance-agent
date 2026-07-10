"""MCP tool for rendering PDF reports (the final anti-fabrication gate)."""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.reports.renderer import render_report_files
from performance_agent.reports.source import ReportMode


class ReportResult(TypedDict):
    """Artifacts produced by a successful render."""

    pdf_path: str
    source_path: str
    version: int
    mode: str
    locale: str


def render_report(mode: ReportMode = "coach", version: int | None = None) -> ReportResult:
    """Render the saved program (latest or a specific version) to PDF via Typst.

    coach mode is terse instructions; expert mode adds the adaptation reason and
    a references section built from corpus entries cited in the program. The
    render HARD-FAILS if the program cites any reference that is not in the
    evidence corpus — fix the program (save an adapted version) rather than
    trying to bypass the gate. The .typ source is kept next to the .pdf.
    """
    rendered = render_report_files(resolve_athlete_dir(), mode=mode, version=version)
    return ReportResult(
        pdf_path=str(rendered.pdf_path),
        source_path=str(rendered.source_path),
        version=rendered.version,
        mode=rendered.mode,
        locale=rendered.locale,
    )


def register(mcp: FastMCP) -> None:
    """Register the report tool on the server."""
    for tool in (render_report,):
        mcp.tool()(tool)
