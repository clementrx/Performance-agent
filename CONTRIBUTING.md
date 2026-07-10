# Contributing to PerformanceAgent

Thanks for helping build an honest AI coach. Two things are sacred here: numbers come
from the deterministic engine, and references come from the verified corpus. Every
contribution is reviewed against those two promises.

## Dev setup

```bash
git clone <this repo> && cd performance-agent
uv sync                  # Python 3.13 toolchain, exact-pinned
prek install             # git hooks: ruff check/format + ty on every commit
brew install typst       # only needed for PDF report tests (they skip without it)
```

## The quality gate (run before every PR)

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
uv run pytest
```

CI runs the same gate; zero warnings is the baseline, not the goal.

## Conventions that will come up in review

- **TDD** — tests first, red, then implement. PRs without failing-test evidence for
  behavior changes will be asked for it.
- **Engine purity** — `src/performance_agent/engine/` imports stdlib math only; an
  architectural test fails the build otherwise. Agents narrate; the engine calculates.
- **Actionable errors** — every ValueError names the operation, the offending value,
  and when file-backed, the file. Tests assert on those messages.
- **MCP tools** — typed params (enums/Literal/Annotated bounds), TypedDict returns,
  no `X | None` top-level returns (FastMCP wraps them), docstrings written for the
  agent that reads them (units, ranges, honesty guidance).
- **Skills** — `skills/<name>/SKILL.md`, directory name == frontmatter name, every
  tool the protocol names must be declared in `tools:` and vice versa (the harness
  in `tests/skills/` enforces both directions and scans for fabricated references).

## Adding evidence to the corpus

The anti-fabrication rule applies to contributors too:

1. Never write study metadata from memory. Query Crossref/PubMed and copy
   title/authors/year/journal/DOI exactly from the registry response.
2. Grade at or below the ceiling for the study design (`evidence/schemas.py`), add a
   `# grading rationale:` comment, and keep conclusions to 1-2 conservative sentences
   containing no figure absent from the abstract.
3. Run `uv run python -m performance_agent.evidence.verify` — every entry must be
   `[OK]` (resolution + title match) before you open the PR.

## Pull requests

- One logical change per PR; imperative commit subjects ≤ 72 chars.
- Describe what the code does now — not the journey.
- Plain, factual language. A bug fix is a bug fix.
