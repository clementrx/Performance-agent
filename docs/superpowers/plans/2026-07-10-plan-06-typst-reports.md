# Plan 06 — Typst PDF Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Professional PDF reports rendered from saved programs via Typst — with the
citation HARD-validation gate (spec's final anti-fabrication enforcement point), coach
and expert modes, and en/fr/es labels — exposed as a `render_report` MCP tool plus a
`program-report` skill.

**Architecture:** Per spec v2 §3: `render_report` reads the saved program + profile,
runs `find_unknown_references` over the full text and ABORTS on any unknown reference,
builds Typst source programmatically (escaped — athlete text can never be interpreted
as Typst code), and shells out to the `typst` CLI. Both the `.typ` source and the `.pdf`
land in the athlete's `reports/` directory (user-owned transparency). Expert mode
appends a references section rendered from corpus entries via `format_citation`; coach
mode is terse. Static labels come from per-locale dictionaries; the program body itself
is whatever language the agent wrote it in.

**Tech Stack:** Typst CLI (subprocess; graceful error if absent), stdlib only in the
reports package (subprocess/shutil/tempfile-free — source written next to the PDF),
existing evidence/citations + memory/store modules. mcp==1.28.1 conventions.

---

## MVP Plan Sequence (spec v2 §10)

1. ✅ Foundation & sports science engine
2. ✅ MCP server core
3. ✅ Athlete memory
4. ✅ Evidence corpus
5. ✅ Coaching skills + eval harness
6. **Typst reports** ← this plan
7. Distribution (PyPI, corpus releases)

---

## File Structure (this plan)

```
src/performance_agent/
├── reports/
│   ├── __init__.py            # docstring only
│   ├── typst_text.py          # escape_typst + markdown_to_typst (pure)
│   ├── labels.py              # LABELS: per-locale static strings (en/fr/es)
│   ├── source.py              # ReportContext + build_report_source (pure)
│   └── renderer.py            # validation gate + typst compile + file placement
└── server/
    ├── report_tools.py        # render_report MCP tool + register(mcp)
    └── app.py                 # + report_tools.register(mcp)

skills/
└── program-report/SKILL.md

tests/
├── reports/
│   ├── __init__.py
│   ├── test_typst_text.py
│   ├── test_labels.py
│   ├── test_source.py
│   └── test_renderer.py
└── server/test_report_tools.py
```

Baseline entering this plan: 249 passed.

**Typst availability:** Task 3 needs the `typst` CLI. Check `typst --version`; if
missing, install it (`brew install typst` on macOS). Pure-source tests never need it;
compile tests use `pytest.mark.skipif(shutil.which("typst") is None, ...)` so the suite
stays green on machines without it. Task 6 wires typst into CI so they run there.

---

### Task 1: Typst text primitives (escape + markdown subset)

**Files:**
- Create: `src/performance_agent/reports/__init__.py`, `src/performance_agent/reports/typst_text.py`
- Test: `tests/reports/__init__.py` (empty), `tests/reports/test_typst_text.py`

- [ ] **Step 1: Write the failing tests** — `tests/reports/test_typst_text.py`:

```python
from performance_agent.reports.typst_text import escape_typst, markdown_to_typst


def test_escape_neutralizes_typst_syntax():
    hostile = r'#import "x" $math$ *bold* _em_ @ref [link] <tag> `code` \back'
    escaped = escape_typst(hostile)
    for char in "#$*_@[]<>`":
        assert f"\\{char}" in escaped
    assert "\\\\back" in escaped


def test_escape_leaves_plain_text_alone():
    assert escape_typst("Squat 5x5 at 80% — allez !") == "Squat 5x5 at 80% — allez !"


def test_headings_convert():
    md = "# Title\n## Week 1\n### Tuesday"
    assert markdown_to_typst(md) == "= Title\n== Week 1\n=== Tuesday"


def test_bullets_and_paragraphs_survive():
    md = "- easy run 45 min\n- strides\n\nRest well."
    out = markdown_to_typst(md)
    assert "- easy run 45 min" in out
    assert "Rest well." in out


def test_bold_converts():
    assert markdown_to_typst("**purpose**: economy") == "*purpose*: economy"


def test_content_inside_structures_is_escaped():
    md = "# Week #3 [taper]\n- load @ 80% *of* 1RM"
    out = markdown_to_typst(md)
    assert out.startswith("= Week \\#3 \\[taper\\]")
    assert "\\@ 80% \\*of\\*" in out


def test_hostile_injection_cannot_escape_into_code():
    md = 'Try this: #eval("1+1") and $x^2$'
    out = markdown_to_typst(md)
    assert "#eval" not in out
    assert "\\#eval" in out
    assert "\\$x\\^2\\$" in out or "\\$" in out
```

- [ ] **Step 2: Run to verify red** — ModuleNotFoundError.

- [ ] **Step 3: Implement** — `src/performance_agent/reports/typst_text.py`:

```python
"""Typst text primitives: escaping and a minimal markdown-to-Typst converter.

Program bodies are agent-written markdown. Only the subset the skills produce
is converted (headings, bullets, bold); everything else is escaped plain text,
so athlete/agent content can never execute as Typst code.
"""

# Order matters: backslash first, then Typst's special characters.
_SPECIALS = "\\#$*_@[]<>`^"


def escape_typst(text: str) -> str:
    """Escape every Typst-significant character in plain text."""
    for char in _SPECIALS:
        text = text.replace(char, "\\" + char)
    return text


def _convert_bold(line: str) -> str:
    """Convert markdown **bold** to Typst *bold* on an ALREADY-ESCAPED line."""
    # after escaping, "**" appears as "\*\*"
    parts = line.split("\\*\\*")
    if len(parts) < 3:  # noqa: PLR2004 - need at least one open/close pair
        return line
    rebuilt = parts[0]
    for index, part in enumerate(parts[1:], start=1):
        rebuilt += ("*" if index % 2 == 1 else "*") + part
    return rebuilt


def markdown_to_typst(markdown: str) -> str:
    """Convert the skills' markdown subset to Typst markup."""
    lines: list[str] = []
    for raw in markdown.splitlines():
        if raw.startswith("### "):
            lines.append("=== " + escape_typst(raw[4:]))
        elif raw.startswith("## "):
            lines.append("== " + escape_typst(raw[3:]))
        elif raw.startswith("# "):
            lines.append("= " + escape_typst(raw[2:]))
        elif raw.startswith("- "):
            lines.append("- " + _convert_bold(escape_typst(raw[2:])))
        else:
            lines.append(_convert_bold(escape_typst(raw)))
    return "\n".join(lines)
```

(If the `_convert_bold` even/odd rebuild reads wrong under test, simplify: replace
pairs of `\*\*` with `*` via `line.replace("\\*\\*", "*")` — acceptable because Typst
uses single `*` for bold; report which form you shipped.)

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/reports -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/reports tests/reports
git commit -m "Add Typst escaping and markdown conversion"
```

---

### Task 2: Locale labels + report source builder

**Files:**
- Create: `src/performance_agent/reports/labels.py`, `src/performance_agent/reports/source.py`
- Test: `tests/reports/test_labels.py`, `tests/reports/test_source.py`

- [ ] **Step 1: Write the failing tests**

`tests/reports/test_labels.py`:
```python
from performance_agent.memory.schemas import Locale
from performance_agent.reports.labels import LABEL_KEYS, LABELS


def test_all_locales_present():
    assert set(LABELS) == {"en", "fr", "es"}


def test_every_locale_has_every_key():
    for locale, mapping in LABELS.items():
        assert set(mapping) == set(LABEL_KEYS), f"{locale} label drift"


def test_locale_type_matches_schema():
    # the Locale Literal in memory.schemas is the source of truth
    assert set(LABELS) == set(Locale.__args__)
```

`tests/reports/test_source.py`:
```python
from performance_agent.reports.source import ReportContext, build_report_source

CONTEXT = ReportContext(
    locale="fr",
    mode="expert",
    athlete_name="Clément",
    goal_statement="10 km sous 45:00",
    version=2,
    created_on="2026-07-10",
    reason="plateau à la semaine 4",
    body_markdown="# Semaine 1\n- footing 45 min **facile**",
    citations=["Doe J (2020). Strength and economy. J Sports Sci. DOI: 10.1000/x."],
)


def test_source_carries_locale_and_metadata():
    source = build_report_source(CONTEXT)
    assert '#set text(lang: "fr")' in source
    assert "Clément" in source
    assert "10 km sous 45:00" in source
    assert "2026-07-10" in source
    assert "v2" in source


def test_body_is_converted_and_escaped():
    source = build_report_source(CONTEXT)
    assert "= Semaine 1" in source
    assert "*facile*" in source


def test_expert_mode_includes_references_and_reason():
    source = build_report_source(CONTEXT)
    assert "Doe J (2020)" in source
    assert "plateau à la semaine 4" in source


def test_coach_mode_omits_references_and_reason():
    coach = ReportContext(**{**CONTEXT.__dict__, "mode": "coach"})
    source = build_report_source(coach)
    assert "Doe J (2020)" not in source
    assert "plateau à la semaine 4" not in source


def test_athlete_text_cannot_inject_typst():
    hostile = ReportContext(
        **{**CONTEXT.__dict__, "athlete_name": '#eval("boom")', "citations": []}
    )
    source = build_report_source(hostile)
    assert '#eval("boom")' not in source
    assert "\\#eval" in source


def test_french_labels_used():
    source = build_report_source(CONTEXT)
    assert "Rapport d'entraînement" in source
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement**

`src/performance_agent/reports/labels.py`:
```python
"""Static report labels per locale (the program body language is the agent's)."""

LABEL_KEYS = (
    "report_title",
    "athlete",
    "goal",
    "program_version",
    "generated_on",
    "adaptation_reason",
    "references",
    "evidence_note",
)

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "report_title": "Training Report",
        "athlete": "Athlete",
        "goal": "Goal",
        "program_version": "Program version",
        "generated_on": "Generated on",
        "adaptation_reason": "Adaptation reason",
        "references": "References",
        "evidence_note": "Evidence grades: ★★★★★ strong … ★☆☆☆☆ expert opinion.",
    },
    "fr": {
        "report_title": "Rapport d'entraînement",
        "athlete": "Athlète",
        "goal": "Objectif",
        "program_version": "Version du programme",
        "generated_on": "Généré le",
        "adaptation_reason": "Raison de l'adaptation",
        "references": "Références",
        "evidence_note": "Niveaux de preuve : ★★★★★ solide … ★☆☆☆☆ avis d'expert.",
    },
    "es": {
        "report_title": "Informe de entrenamiento",
        "athlete": "Atleta",
        "goal": "Objetivo",
        "program_version": "Versión del programa",
        "generated_on": "Generado el",
        "adaptation_reason": "Motivo de la adaptación",
        "references": "Referencias",
        "evidence_note": "Niveles de evidencia: ★★★★★ sólido … ★☆☆☆☆ opinión experta.",
    },
}
```

`src/performance_agent/reports/source.py`:
```python
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
```

(Note: heading levels — the report title uses `=`; the converted body's `# ` headings
also map to `=`. Acceptable for MVP typography. The `\\` line breaks in the metadata
block are Typst line breaks, intentional, not escapes.)

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/reports -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/reports tests/reports
git commit -m "Add report labels and Typst source builder"
```

---

### Task 3: Renderer with the citation hard-validation gate

**Files:**
- Create: `src/performance_agent/reports/renderer.py`
- Test: `tests/reports/test_renderer.py`

- [ ] **Step 1: Write the failing tests** — `tests/reports/test_renderer.py`:

```python
import shutil
from datetime import date

import pytest

from performance_agent.memory.schemas import Goal, Profile
from performance_agent.memory.store import save_program, upsert_goal, write_profile
from performance_agent.reports.renderer import render_report_files

TODAY = date(2026, 7, 10)
HAS_TYPST = shutil.which("typst") is not None


def _seed_athlete(tmp_path, body: str) -> None:
    write_profile(tmp_path, Profile(locale="fr", display_name="Clément"))
    upsert_goal(tmp_path, Goal(id="sub-45-10k", statement="10 km sous 45:00"))
    save_program(tmp_path, body, "sub-45-10k", today=TODAY)


def test_fabricated_reference_aborts_before_any_file_is_written(tmp_path):
    _seed_athlete(tmp_path, "# Plan\nProuvé par la science (doi:10.9999/fake).")
    with pytest.raises(ValueError, match="10.9999/fake"):
        render_report_files(tmp_path, mode="expert")
    assert not (tmp_path / "reports").exists()


def test_source_file_is_always_written(tmp_path, monkeypatch):
    _seed_athlete(tmp_path, "# Plan\n- footing 45 min")
    monkeypatch.setattr(
        "performance_agent.reports.renderer._typst_binary", lambda: None
    )
    with pytest.raises(ValueError, match="typst"):
        render_report_files(tmp_path, mode="coach")
    source_path = tmp_path / "reports" / "program-v1-coach-fr.typ"
    assert source_path.exists()
    assert "= Rapport d'entraînement" in source_path.read_text(encoding="utf-8")


def test_missing_program_is_a_readable_error(tmp_path):
    write_profile(tmp_path, Profile(locale="en"))
    with pytest.raises(ValueError, match="save_program"):
        render_report_files(tmp_path, mode="coach")


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_pdf_compiles_end_to_end(tmp_path):
    _seed_athlete(tmp_path, "# Semaine 1\n- footing 45 min **facile**\n\nBon courage !")
    result = render_report_files(tmp_path, mode="coach")
    assert result.pdf_path.exists()
    assert result.pdf_path.name == "program-v1-coach-fr.pdf"
    assert result.pdf_path.stat().st_size > 1000
    assert result.source_path.exists()


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_expert_report_with_real_corpus_citation_compiles(tmp_path):
    from performance_agent.evidence.corpus import load_corpus

    entry = load_corpus()[0]
    locator = f"DOI: {entry.doi}" if entry.doi else f"PMID: {entry.pmid}"
    _seed_athlete(tmp_path, f"# Plan\nBloc force ({locator}).")
    result = render_report_files(tmp_path, mode="expert")
    assert result.pdf_path.exists()
    text = result.source_path.read_text(encoding="utf-8")
    assert "Références" in text  # expert mode, fr labels
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Implement** — `src/performance_agent/reports/renderer.py`:

```python
"""Render a saved program to PDF via Typst, behind the citation gate.

This is the spec's final anti-fabrication enforcement point: any DOI/PMID-shaped
reference in the report that is not in the evidence corpus ABORTS the render.
The .typ source is written next to the .pdf for user-owned transparency.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from performance_agent.evidence.citations import find_unknown_references, format_citation
from performance_agent.evidence.corpus import load_corpus
from performance_agent.memory import store
from performance_agent.reports.source import ReportContext, ReportMode, build_report_source

REPORTS_DIR = "reports"
_COMPILE_TIMEOUT_S = 60


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


def _citations_for(body: str) -> list[str]:
    """Formatted citations for every corpus entry whose locator appears in the body."""
    citations = []
    for entry in load_corpus():
        doi_hit = entry.doi and entry.doi.casefold() in body.casefold()
        pmid_hit = entry.pmid and entry.pmid in body
        if doi_hit or pmid_hit:
            citations.append(format_citation(entry))
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
    completed = subprocess.run(  # noqa: S603 - fixed binary, no shell
        [binary, "compile", str(source_path), str(pdf_path)],
        capture_output=True,
        timeout=_COMPILE_TIMEOUT_S,
        check=False,
    )
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
```

(Adapt the `# noqa` to what ruff actually flags — if `S` rules are disabled, drop it.
Note the ordering: the citation gate runs BEFORE the reports dir is created, pinned by
`test_fabricated_reference_aborts_before_any_file_is_written`.)

- [ ] **Step 4: Green + gate + commit** (if typst is absent, install it: `brew install typst`)

```bash
typst --version
rtk proxy uv run pytest tests/reports -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/reports tests/reports
git commit -m "Add report renderer with citation hard-validation"
```

---

### Task 4: The render_report MCP tool

**Files:**
- Create: `src/performance_agent/server/report_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_report_tools.py`

- [ ] **Step 1: Write the failing tests** — `tests/server/test_report_tools.py`:

```python
"""In-process tests for the report MCP tool (isolated athlete dir per test)."""

import shutil

import pytest

HAS_TYPST = shutil.which("typst") is not None


@pytest.fixture(autouse=True)
def athlete_home(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    return tmp_path


async def _seed(client):
    await client.call_tool("write_profile", {"profile": {"locale": "en"}})
    await client.call_tool(
        "upsert_goal", {"goal": {"id": "sub-45-10k", "statement": "10K under 45:00"}}
    )
    await client.call_tool(
        "save_program", {"markdown_body": "# Week 1\n- easy run", "goal_id": "sub-45-10k"}
    )


@pytest.mark.anyio
async def test_fabricated_citation_aborts_render(client):
    await client.call_tool("write_profile", {"profile": {"locale": "en"}})
    await client.call_tool(
        "upsert_goal", {"goal": {"id": "g", "statement": "goal"}}
    )
    await client.call_tool(
        "save_program",
        {"markdown_body": "Proven (doi:10.9999/fake).", "goal_id": "g"},
    )
    result = await client.call_tool("render_report", {"mode": "expert"})
    assert result.isError
    assert "10.9999/fake" in result.content[0].text


@pytest.mark.anyio
async def test_render_before_any_program_is_readable_error(client):
    result = await client.call_tool("render_report", {})
    assert result.isError
    assert "save_program" in result.content[0].text


@pytest.mark.anyio
@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
async def test_render_report_produces_pdf(client, athlete_home):
    await _seed(client)
    result = await client.call_tool("render_report", {"mode": "coach"})
    assert not result.isError
    report = result.structuredContent
    assert report["version"] == 1
    assert report["mode"] == "coach"
    assert report["locale"] == "en"
    assert report["pdf_path"].endswith("program-v1-coach-en.pdf")
    assert (athlete_home / "reports" / "program-v1-coach-en.pdf").exists()


@pytest.mark.anyio
async def test_report_tool_is_listed(client):
    listed = await client.list_tools()
    assert "render_report" in {tool.name for tool in listed.tools}
```

- [ ] **Step 2: Run to verify red** (unknown tool).

- [ ] **Step 3: Implement** — `src/performance_agent/server/report_tools.py`:

```python
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
```

Modify `app.py` to import and register `report_tools` (fourth group).

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/server -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add src/performance_agent/server tests/server/test_report_tools.py
git commit -m "Add render_report MCP tool"
```

---

### Task 5: The program-report skill

**Files:**
- Create: `skills/program-report/SKILL.md`
- Test: extend `tests/skills/test_structure.py`

- [ ] **Step 1: Extend the tests** — add "program-report" to EXPECTED_SKILLS and:

```python
def test_report_skill_protocol(skills):
    report = next(s for s in skills if s.frontmatter["name"] == "program-report")
    body = report.body.casefold()
    for needle in ("render_report", "check_citations", "coach", "expert", "mode"):
        assert needle in body, f"report skill lost: {needle}"
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Create `skills/program-report/SKILL.md`**:

```markdown
---
name: program-report
description: Use when the athlete wants their program as a shareable PDF document.
  Chooses the mode, pre-checks citations, renders via Typst, and hands back the file.
tools: [read_athlete, read_program, check_citations, render_report]
---

# Program Report

Follow performance-coach global rules. The report is the athlete's take-away
document — it must be as honest as the conversation that produced it.

## Protocol

1. Confirm there is a program: `read_athlete` → program_version. Null → route to
   program-generation; a report of nothing helps nobody.
2. Ask which mode (one question): **coach** — terse instructions to train with;
   **expert** — adds the adaptation reason and the full references section with
   evidence grades. Default to coach for athletes, expert for anyone who asks
   "why" a lot.
3. Pre-flight: `read_program` and run `check_citations` on the body. If anything
   is flagged, do NOT render — fix the program first (route to program-adaptation
   to save a corrected version with a reason). The renderer enforces the same
   gate and will refuse; the pre-flight just saves the athlete a failed attempt.
4. `render_report` (mode; version only if the athlete asked for an old one). The
   language follows the athlete's stored locale automatically.
5. Hand back the PDF path, note that the .typ source sits next to it, and — for
   coach mode — offer the expert version if they ever want the "why".

## If the render fails

- Unknown references: the program cites something outside the corpus — route to
  program-adaptation, replace the claim with a `search_evidence`-backed one (or
  drop it), save vN+1, render again.
- typst not installed: give the athlete the install hint from the error message
  and point them at the .typ source that was still written.
```

- [ ] **Step 4: Green** (the skill harness auto-covers the new skill: structure,
tool-drift both directions, fabrication scan) **+ gate + commit**

```bash
rtk proxy uv run pytest tests/skills -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add skills/program-report tests/skills
git commit -m "Add program report skill"
```

---

### Task 6: CI typst + docs

**Files:**
- Modify: `.github/workflows/ci.yml`, `docs/installing.md`, `README.md`

- [ ] **Step 1: Wire typst into CI.** Resolve the CURRENT SHA for the
`typst-community/setup-typst` action (same procedure as Plan 01: `gh api
repos/typst-community/setup-typst/git/ref/tags/<latest-major>` and dereference
annotated tags via `gh api .../git/tags/<sha>`; check the action's README for the
current major tag and inputs first). Add the step to ci.yml after setup-uv:

```yaml
      - uses: typst-community/setup-typst@<RESOLVED-COMMIT-SHA>  # v<major>
```

(If the action requires a `typst-version` input for pinning, pin the version you have
locally — `typst --version`. actionlint + zizmor must stay clean; report the resolved
SHA and version.)

- [ ] **Step 2: `docs/installing.md`** — add to Prerequisites: "- [`typst`](https://typst.app)
— only needed for PDF reports (`brew install typst`); everything else works without it."
Update the Verify tool count: 22 → 23 ("23 tools (9 engine + 10 memory + 3 evidence +
1 report: …")).

- [ ] **Step 3: `README.md`** — replace the "🔜 Report MCP tools" and the PDF 🔜 line
with a ✅ line under Working today: "✅ Typst PDF reports (coach & expert modes,
en/fr/es) behind a hard citation gate — a program citing anything outside the corpus
refuses to render". Check exact current wording; keep "🔜 Corpus growth…" as-is.

- [ ] **Step 4: Full gate + commit** — "Wire typst into CI and document reports".

---

### Task 7: Final sweep

- [ ] Full quality gate (all commands, incl. actionlint+zizmor after the CI change).
- [ ] Append `## As-Built Deviations` to this plan (verified against git log):
bold-conversion form shipped, noqa adaptations, typst availability/install on the dev
machine, setup-typst SHA/version resolved, final suite count.
- [ ] Commit "Record Plan 06 as-built state".

---

## Self-Review Notes

- **Spec coverage (v2 §3 + §10 item 6):** render_report tool ✓ T4; citation
  hard-validation abort ✓ T3 (gate runs before the reports dir is even created,
  pinned by test); coach/expert modes ✓ T2-T4; en/fr/es labels ✓ T2 (completeness +
  schema-Locale sync tests); .typ transparency ✓ T3; graceful typst-missing error ✓
  T3; report skill ✓ T5 (harness auto-guards); Typst in CI ✓ T6.
- **Deliberate cuts:** no custom typography/branding (default Typst + margins);
  reports of sessions/check-in history (V2); no PDF preview embedding in README
  (screenshot when a real athlete report exists — honesty).
- **Type consistency:** ReportContext/ReportMode/RenderedReport/ReportResult names and
  fields consistent across T2-T4; render_report_files(base_dir, mode, version)
  signature matches T4's usage; labels keys used in source.py all exist in LABEL_KEYS.
- **Known uncertainties, handled in-plan:** _convert_bold rebuild (simplify-and-report
  fallback); ruff noqa needs; setup-typst action inputs (check README live);
  frontmatter dict access via str()/int() casts (established Plan 03 pattern).

## As-Built Deviations

- **T1 (848a51e, f457c18):** shipped with security hardening beyond the plan's
  draft. `_SPECIALS` was extended from `"\\#$*_@[]<>`^"` to add `/=+`, neutralizing
  `//`/`/* */` comment syntax and line-start heading/enum syntax (`=`, `+`) inside
  escaped text. `escape_typst` now collapses all line boundaries (`splitlines()` +
  `" ".join`) before escaping, so escaped text can never smuggle in a newline and
  therefore can never forge Typst line-start syntax. `_convert_bold` was rewritten
  from the plan's index-based `\*\*`-split rebuild (which the plan itself flagged as
  possibly reading wrong, with a "simplify to `.replace`" fallback) to a
  balance-aware regex, `_BOLD_PAIR = re.compile(r"\\\*\\\*(.+?)\\\*\\\*")`, so only
  complete open/close `**` pairs convert to Typst bold and an unmatched `\*\*` stays
  literal — neither the plan's original dead-branch rebuild nor its literal fallback
  shipped. The plan's proposed test assertion `assert "#eval" not in out` (step 1,
  `test_hostile_injection_cannot_escape_into_code`) was dropped as logically
  impossible to satisfy alongside `assert "\\#eval" in out` in the same test — the
  escaped form `\#eval` necessarily contains `#eval` as a substring — and replaced
  with a comment explaining why, keeping only the escaped-form assertion.

- **T2 (d6a1237):** `tests/reports/test_source.py` builds `ReportContext` variants
  with `dataclasses.replace(CONTEXT, ...)` instead of the plan's proposed
  `ReportContext(**{**CONTEXT.__dict__, ...})` splat (lines 265/273 of the original
  draft) — `ty` treats the `__dict__` splat as untyped, `dataclasses.replace` is the
  type-safe equivalent for a frozen dataclass. The same impossible-substring-assertion
  fix from T1 was applied in `test_athlete_text_cannot_inject_typst`: `"#eval(...)"
  not in source` was dropped in favor of asserting only the escaped `"\\#eval" in
  source`, with the same explanatory comment.

- **T3 (3e5aecb, 3da3f3c):** typst 0.15.0 was installed locally via `brew install
  typst` to develop and test the renderer against a real binary. The plan's proposed
  `# noqa: S603` on `subprocess.run` was never added — `S` (flake8-bandit) is not in
  this project's `ruff.lint.select` list (`pyproject.toml`), so ruff never flags
  S603 and the noqa would itself be a bare/unused-noqa violation. Two noqas the plan
  didn't anticipate were needed in `tests/reports/test_renderer.py`: `# noqa: RUF043`
  on a `pytest.raises(..., match="10.9999/fake")` (literal-string regex match) and
  `# noqa: PLC0415` on a test-local `from performance_agent.evidence.corpus import
  load_corpus`. Post-review (commit 3da3f3c, after the initial T3 commit landed),
  `subprocess.TimeoutExpired` was caught explicitly and re-raised as `ValueError`
  with a readable "typst compile timed out after {N}s" message, instead of letting
  the raw `TimeoutExpired` propagate uncaught.

- **T5 (9e27769, 9186bf1):** the program-report skill's "If the render fails" prose
  was worded differently from the plan's draft. The plan's line ("replace the claim
  with a `search_evidence`-backed one") named a tool the skill doesn't declare
  (`tools:` frontmatter for program-report lists only `read_athlete`, `read_program`,
  `check_citations`, `render_report`); `tests/skills/test_tool_references.py::
  test_bodies_do_not_reference_undeclared_tools` would have failed, so the shipped
  text reads "replace the claim with an evidence-corpus-backed one" instead. Beyond
  the plan's scope, `skills/program-adaptation/SKILL.md` was extended post-review
  (9186bf1) to add `search_evidence` and `get_citation` to its declared tools and a
  new "Citation repair" protocol bullet: when a render is refused for unknown
  references, locate the offending claims, replace each with a `search_evidence`-
  backed citation rendered via `get_citation` (or drop the claim), and save vN+1
  with reason "citation repair" — closing the loop the report skill's failure path
  routes into.

- **T6 (0fbe528):** `typst-community/setup-typst` was pinned to `v5` at
  `63ac138db421d586de61f7f5ac3bcef6a2e6c78c`, with `typst-version: '0.15.0'` pinned
  via the action's input (matching the locally installed version). Unlike the SHA
  resolution in Plan 01, the plan's documented dereference step (`gh api
  .../git/tags/<sha>` to unwrap an annotated tag) was not needed: `gh api
  repos/typst-community/setup-typst/git/ref/tags/v5` resolves directly to a
  `"type": "commit"` object — `v5` is a lightweight tag, so the ref SHA already is
  the commit SHA.

- **Final suite count:** 282 tests passed (`rtk proxy uv run pytest`), matching the
  count recorded at the start of this plan — no net test count change from Task 7
  itself (Task 7 only runs the gate and documents deviations; all test additions
  happened in T1-T6).
