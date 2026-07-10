# Plan 07 — Distribution Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything needed to publish PerformanceAgent — complete PyPI metadata with a
packaging regression test, a tag-triggered trusted-publishing release workflow, a
CONTRIBUTING guide, and a RELEASING runbook — prepared locally, stopping at the
external actions (GitHub repo creation, PyPI account/publisher setup) that belong to
the maintainer.

**Architecture:** The release path is: maintainer follows RELEASING.md → creates the
GitHub repo and PyPI trusted publisher → pushes main → tags `vX.Y.Z` → the release
workflow re-runs the full gate, builds sdist+wheel with uv, and publishes via PyPA's
trusted-publishing action (no long-lived tokens). A session-scoped packaging test keeps
the wheel honest (console script, seed corpus, LICENSE all present) from now on.

**Tech Stack:** uv build, pypa/gh-action-pypi-publish (SHA-pinned, resolved live),
GitHub environments + OIDC id-token. No new runtime dependencies.

---

## MVP Plan Sequence (spec v2 §10)

1-6. ✅ All complete (engine, MCP server, memory, evidence, skills, reports)
7. **Distribution prep** ← this plan (external actions handed to the maintainer)

---

## File Structure (this plan)

```
pyproject.toml                 # + keywords, classifiers (urls added at release time)
tests/packaging/
├── __init__.py
└── test_distribution.py       # wheel-contents regression test (session-scoped build)
.github/workflows/release.yml  # tag-triggered: gate → build → PyPI trusted publishing
CONTRIBUTING.md
RELEASING.md                   # the maintainer runbook (external steps live here)
README.md                      # Contributing section links the new files
```

Baseline entering this plan: 285 passed.

---

### Task 1: PyPI metadata + packaging regression test

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/packaging/__init__.py` (empty), `tests/packaging/test_distribution.py`

- [ ] **Step 1: Check the PyPI name is free** (report, don't block):
`curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/performance-agent/json`
— 404 means free; 200 means taken (report it; the runbook's name-check step covers the
maintainer decision, do not rename anything yourself).

- [ ] **Step 2: Write the failing test** — `tests/packaging/test_distribution.py`:

```python
"""Packaging regression: the wheel must ship everything the runtime needs."""

import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def wheel_path(tmp_path_factory) -> Path:
    out_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=120,
    )
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def test_wheel_ships_the_seed_corpus(wheel_path):
    assert "performance_agent/evidence/data/seed_corpus.yaml" in _names(wheel_path)


def test_wheel_ships_the_license(wheel_path):
    names = _names(wheel_path)
    assert any(name.endswith("licenses/LICENSE") or name.endswith("LICENSE") for name in names)


def test_wheel_declares_the_console_script(wheel_path):
    with zipfile.ZipFile(wheel_path) as archive:
        entry_points = next(n for n in archive.namelist() if n.endswith("entry_points.txt"))
        content = archive.read(entry_points).decode("utf-8")
    assert "performance-agent = performance_agent.server.app:main" in content


def test_wheel_has_no_test_or_skill_leakage(wheel_path):
    names = _names(wheel_path)
    assert not any(name.startswith(("tests/", "skills/")) for name in names)


def test_metadata_carries_classifiers(wheel_path):
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(n for n in archive.namelist() if n.endswith("METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    assert "Classifier: Development Status :: 3 - Alpha" in metadata
    assert "Classifier: Programming Language :: Python :: 3.13" in metadata
    assert "Keywords:" in metadata
```

(LICENSE inclusion: uv_build includes the license file per the `license` field; if the
first run shows it absent from the wheel, add `license-files = ["LICENSE"]` to
`[project]` and report. The `licenses/LICENSE` dist-info path is the modern layout.)

- [ ] **Step 3: Run to verify red** — the classifiers test fails (none declared yet).

- [ ] **Step 4: Extend `pyproject.toml`'s `[project]`** (after the `license` line):

```toml
keywords = [
    "strength-and-conditioning",
    "training",
    "coaching",
    "mcp",
    "evidence-based",
    "sports-science",
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: Healthcare Industry",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering",
    "Typing :: Typed",
]
```

(License classifier deliberately omitted — the SPDX `license = "Apache-2.0"` field is
the modern source of truth and newer build backends reject the redundant classifier.
If `uv build` warns otherwise, follow the tool and report. `[project.urls]` is
deliberately absent until the repo exists — RELEASING.md step 2 adds it.)

- [ ] **Step 5: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/packaging -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add pyproject.toml tests/packaging
git commit -m "Add PyPI metadata and packaging regression tests"
```

---

### Task 2: Release workflow (trusted publishing)

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Resolve the CURRENT SHA for `pypa/gh-action-pypi-publish`'s latest
release tag** (`gh api repos/pypa/gh-action-pypi-publish/releases/latest`, then
`git/ref/tags/<tag>`, dereferencing annotated tags via `git/tags/<sha>` if
`"type": "tag"`). Reuse the checkout/setup-uv/setup-typst SHAs already pinned in
ci.yml (copy them verbatim). Report all SHAs used.

- [ ] **Step 2: Create `.github/workflows/release.yml`:**

```yaml
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<CHECKOUT-SHA-FROM-CI>  # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP-UV-SHA-FROM-CI>  # v7
      - uses: typst-community/setup-typst@<SETUP-TYPST-SHA-FROM-CI>  # v5
        with:
          typst-version: '0.15.0'
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run ty check
      - run: uv run pytest

  publish:
    needs: gate
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@<CHECKOUT-SHA-FROM-CI>  # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<SETUP-UV-SHA-FROM-CI>  # v7
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@<RESOLVED-SHA>  # v<version>
```

(Replace every `<...-SHA...>` placeholder with the real values from Step 1 — the
committed file must contain only full 40-char SHAs with version comments. If zizmor
flags anything — e.g. missing artifact hardening or the publish job needing
`contents: read` explicitly — fix per its guidance and report.)

- [ ] **Step 3: Lint** — `actionlint .github/workflows/release.yml && uvx zizmor
.github/workflows/release.yml` must be clean.

- [ ] **Step 4: Commit** — "Add tag-triggered PyPI release workflow".

---

### Task 3: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`
- Modify: `README.md` (Contributing section links it)

- [ ] **Step 1: Create `CONTRIBUTING.md`:**

```markdown
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
```

- [ ] **Step 2: `README.md`** — in the Contributing section, link the file:
replace "Early development, moving fast." with "Early development, moving fast — see
[CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup and review conventions." (check
exact wording, adjust minimally, keep the sports-scientists sentence).

- [ ] **Step 3: Commit** — "Add contributing guide".

---

### Task 4: RELEASING.md runbook (the maintainer's external steps)

**Files:**
- Create: `RELEASING.md`

- [ ] **Step 1: Create `RELEASING.md`:**

```markdown
# Releasing PerformanceAgent

Everything below needs maintainer credentials — none of it is automatable from a
local agent session. The repo is release-ready when this checklist completes.

## One-time setup

1. **Check the PyPI name.** https://pypi.org/project/performance-agent/ — if taken,
   pick a distribution name (e.g. performanceagent-coach), update `[project] name`
   in pyproject.toml, and re-run `uv run pytest tests/packaging`.
2. **Create the GitHub repository** and push:
   ```bash
   gh repo create <org>/performance-agent --public --source . --push
   ```
3. **Replace the placeholder URLs.** Search for `<your-org>` (docs/installing.md,
   CONTRIBUTING.md's clone line) and replace with the real org/repo. Add to
   pyproject.toml under `[project]`:
   ```toml
   [project.urls]
   Homepage = "https://github.com/<org>/performance-agent"
   Issues = "https://github.com/<org>/performance-agent/issues"
   ```
   Commit via a PR (branch protection: never push to main directly once public).
4. **Configure PyPI trusted publishing** (no tokens): PyPI → your project (or
   "pending publisher" for the first release) → Publishing → GitHub:
   owner `<org>`, repo `performance-agent`, workflow `release.yml`, environment `pypi`.
5. **Create the `pypi` environment** in GitHub repo Settings → Environments (add
   yourself as required reviewer if you want a manual gate before each publish).

## Every release

1. Update the version in `pyproject.toml`; commit via PR.
2. Tag and push:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
3. The `release` workflow re-runs the full gate, builds, and publishes. Verify on
   PyPI, then smoke-test the published package:
   ```bash
   uvx performance-agent@latest < /dev/null; echo "exit: $?"   # expect 0
   claude mcp add performance-agent -- uvx performance-agent    # the post-PyPI form
   ```
4. Update docs/installing.md to the `uvx` form (drop the `--directory` local-clone
   form) in the release PR that bumps the version — not before.

## Corpus releases (V2 workflow, recorded for later)

Corpus updates ship as normal package releases: curate → verify (`python -m
performance_agent.evidence.verify`) → version bump → tag. Users get corpus updates
by upgrading the package; no separate channel until the corpus outgrows the wheel.
```

- [ ] **Step 2: Commit** — "Add release runbook".

---

### Task 5: Final sweep

- [ ] Full quality gate (all commands; actionlint+zizmor over BOTH workflows).
- [ ] Append `## As-Built Deviations` to this plan (PyPI name check result, resolved
action SHAs, license-file packaging outcome, final suite count).
- [ ] Commit "Record Plan 07 as-built state".

---

## Self-Review Notes

- **Spec coverage (v2 §10 item 7):** PyPI packaging ✓ T1 (with regression tests);
  release automation ✓ T2 (trusted publishing, no tokens, gate re-run on tag);
  corpus-release path recorded ✓ T4 (V2 workflow documented, wheel-carried for now);
  the `uvx` simplification of installing.md is explicitly deferred TO the release
  itself ✓ T4 step 4 (honesty: don't document an install path that doesn't work yet).
- **External-action boundary:** repo creation, URL replacement, PyPI publisher setup,
  environment creation, tagging — all in RELEASING.md for the maintainer; nothing in
  this plan performs an external action.
- **Placeholder scan:** the `<...>` placeholders in T2's YAML are explicitly resolved
  in T2 Step 1 (live SHA lookups) before commit; `<org>`/`<your-org>` in RELEASING.md
  are intentional maintainer-fill markers, documented as such.
- **Type consistency:** wheel_path fixture used by all five packaging tests; no
  cross-task code references.
