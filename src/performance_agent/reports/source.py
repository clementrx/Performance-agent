"""Build the Typst source for a report (pure string assembly, fully escaped)."""

from dataclasses import dataclass
from typing import Literal

from performance_agent.reports.labels import LABELS
from performance_agent.reports.typst_text import escape_typst, markdown_to_typst

ReportMode = Literal["coach", "expert"]


@dataclass(frozen=True)
class ReportContext:
    """Everything the report needs, already fetched and validated by the caller."""

    locale: str
    mode: ReportMode
    athlete_name: str
    goal_statement: str
    version: int
    created_on: str
    reason: str | None
    body_markdown: str
    citations: list[str]


def build_report_source(context: ReportContext) -> str:
    """Assemble the full Typst document source."""
    labels = LABELS[context.locale]
    parts = [
        f'#set text(lang: "{context.locale}")',
        "#set page(margin: 2cm)",
        f"= {escape_typst(labels['report_title'])}",
        "",
        f"*{escape_typst(labels['athlete'])}:* {escape_typst(context.athlete_name)} \\",
        f"*{escape_typst(labels['goal'])}:* {escape_typst(context.goal_statement)} \\",
        f"*{escape_typst(labels['program_version'])}:* v{context.version} \\",
        f"*{escape_typst(labels['generated_on'])}:* {escape_typst(context.created_on)}",
        "",
    ]
    if context.mode == "expert" and context.reason:
        parts += [
            f"*{escape_typst(labels['adaptation_reason'])}:* {escape_typst(context.reason)}",
            "",
        ]
    parts += ["#line(length: 100%)", "", markdown_to_typst(context.body_markdown), ""]
    if context.mode == "expert" and context.citations:
        parts += [f"= {escape_typst(labels['references'])}", ""]
        parts += [f"- {escape_typst(citation)}" for citation in context.citations]
        parts += ["", escape_typst(labels["evidence_note"])]
    return "\n".join(parts)
