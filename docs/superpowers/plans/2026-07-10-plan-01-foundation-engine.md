# Plan 01 — Foundation & Sports Science Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the PerformanceAgent monorepo (tooling, CI) and implement the
deterministic sports science engine — 1RM math, endurance prediction, training load,
goal feasibility, and periodization waves — fully tested, with zero LLM dependencies.

**Architecture:** Per the approved spec (`docs/superpowers/specs/2026-07-10-performanceagent-architecture-design.md`),
the engine is a pure-Python package (`performance_agent.engine`) that agents will later call
as tools. "LLMs narrate, the engine calculates." This plan builds the engine and the repo
skeleton; no FastAPI, no database, no LLM yet.

**Tech Stack:** Python 3.13, uv, ruff, ty, pytest, Hypothesis. GitHub Actions (SHA-pinned).

---

## MVP Plan Sequence (context)

> **Superseded 2026-07-10 (post-completion):** the project pivoted to an agent-native
> architecture (MCP server + coaching skills inside Claude Code/Gemini/Codex; no web
> platform). This plan's deliverables are fully reused; the sequence below is replaced
> by §10 of the v2 spec (`docs/superpowers/specs/2026-07-10-performanceagent-architecture-design.md`).

Original (v1) sequence, kept for the record:

1. **Foundation & sports science engine** ← this plan
2. API core — FastAPI, auth (fastapi-users), athlete/equipment/goals CRUD, session logging, Alembic + Postgres
3. Evidence & RAG — schema, seed corpus manifest, PubMed ingestion, hybrid retrieval, grading rules
4. LLM adapter + agents & orchestration — LangGraph graphs, prompts, anti-fabrication guard, evals harness
5. Program generation pipeline end-to-end + Typst PDF reports
6. Frontend — Next.js 15, next-intl (en/fr/es), onboarding wizard, calendar, generation UI
7. Self-host packaging — docker-compose, self-hosting docs, GHCR release workflow

---

## File Structure (this plan)

```
performance-agent/                        # repo root (already git-initialized)
├── .github/workflows/ci.yml              # lint → types → tests
├── .gitignore
├── .pre-commit-config.yaml               # prek hooks: ruff check/format, ty
├── LICENSE                               # Apache-2.0
├── README.md                             # project stub
└── apps/api/
    ├── pyproject.toml                    # uv project, ruff/ty/pytest config
    ├── uv.lock
    ├── src/performance_agent/
    │   ├── __init__.py
    │   └── engine/
    │       ├── __init__.py               # public re-exports
    │       ├── strength.py               # 1RM estimation, %-based loading
    │       ├── endurance.py              # Riegel prediction, pace utilities
    │       ├── load.py                   # session-RPE load, weekly loads, ACWR
    │       ├── feasibility.py            # required vs achievable progression → probability
    │       └── periodization.py          # weekly volume/intensity waves, deload, taper
    └── tests/
        └── engine/
            ├── __init__.py
            ├── test_strength.py
            ├── test_endurance.py
            ├── test_load.py
            ├── test_feasibility.py
            ├── test_periodization.py
            ├── test_properties.py        # Hypothesis invariants
            └── test_engine_purity.py     # architectural guard: stdlib-only imports
```

Each engine module has one responsibility and no dependency on the others (except
`feasibility` importing nothing but stdlib too — modules are siblings, not a stack).

---

### Task 1: Repository scaffolding

**Files:**
- Create: `.gitignore`, `LICENSE`, `README.md`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/README.md` (required by uv: pyproject readme field)
- Create: `apps/api/src/performance_agent/__init__.py`
- Create: `apps/api/src/performance_agent/engine/__init__.py`
- Create: `apps/api/tests/engine/__init__.py`

- [ ] **Step 1: Create `.gitignore` at repo root**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/

# Node (used from Plan 6)
node_modules/
.next/

# Environment & editors
.env
.env.*
!.env.example
.DS_Store
.idea/
.vscode/
```

- [ ] **Step 2: Fetch the Apache-2.0 license text**

Run from repo root:
```bash
curl -fsS https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
head -3 LICENSE
```
Expected: first lines contain "Apache License" and "Version 2.0, January 2004".

- [ ] **Step 3: Create `README.md` at repo root**

```markdown
# PerformanceAgent

Open-source, AI-powered, evidence-based physical preparation platform — a digital
strength & conditioning assistant that designs, explains, monitors, and adapts
training programs.

**Status:** early development (MVP in progress).

## Design principles

- **Evidence first** — recommendations trace to a graded, verifiable evidence database.
- **LLMs narrate, the engine calculates** — all sports-science math lives in a
  deterministic, fully tested Python package (`performance_agent.engine`).
- **Long-term athlete memory** — no conversation starts from zero.
- **Multilingual** — English (default), French, Spanish.

## Repository layout

- `apps/api` — Python backend (FastAPI, agents, sports science engine)
- `docs/superpowers/specs` — architecture blueprint and design docs
- `docs/superpowers/plans` — implementation plans

## License

Apache-2.0 — see [LICENSE](LICENSE).
```

- [ ] **Step 4: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "performance-agent"
version = "0.1.0"
description = "Evidence-based AI physical preparation platform — backend"
readme = "README.md"
requires-python = ">=3.13"
license = "Apache-2.0"
dependencies = []

[build-system]
requires = ["uv_build>=0.9,<1"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "performance_agent"

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E", "W", "F", "I", "N", "UP", "B", "C4", "C90",
    "SIM", "RET", "ARG", "PL", "RUF", "D",
]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.mccabe]
max-complexity = 8

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "PLR2004"]

[tool.ty.environment]
python-version = "3.13"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 5: Create the package skeleton**

Run from repo root:
```bash
mkdir -p apps/api/src/performance_agent/engine apps/api/tests/engine
```

Create `apps/api/src/performance_agent/__init__.py`:
```python
"""PerformanceAgent backend: evidence-based AI physical preparation platform."""
```

Create `apps/api/src/performance_agent/engine/__init__.py`:
```python
"""Deterministic sports science engine (no LLM, no I/O)."""
```

Create `apps/api/tests/engine/__init__.py` as an empty file.

- [ ] **Step 6: Install dev toolchain (pins current versions into `uv.lock`)**

Run from `apps/api/`:
```bash
uv sync
uv add --dev pytest hypothesis ruff ty
```
Expected: `uv.lock` created; `Installed N packages` output.

- [ ] **Step 7: Verify the toolchain runs clean**

Run from `apps/api/`:
```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
```
Expected: ruff OK; ty `All checks passed`; pytest `no tests ran` (exit code 5 is
acceptable for pytest at this stage — an empty suite).

- [ ] **Step 8: Commit**

```bash
git add .gitignore LICENSE README.md apps/
git commit -m "Scaffold monorepo with API project and toolchain"
```

---

### Task 2: Git hooks (prek)

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create `.pre-commit-config.yaml` at repo root**

The `rev` values below are placeholders by design — the next step pins them to current
releases.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: ty
        name: ty check
        entry: bash -c 'cd apps/api && uv run ty check'
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 2: Pin hook versions and install**

Run from repo root:
```bash
prek auto-update --cooldown-days 7
prek install
prek run --all-files
```
Expected: `rev` updated to the latest ruff-pre-commit release; all hooks pass.

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "Add prek hooks: ruff check/format and ty"
```

---

### Task 3: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

SHAs below were resolved on 2026-07-10 (`actions/checkout` v5, `astral-sh/setup-uv` v7 —
the setup-uv SHA is the dereferenced commit, not the annotated tag object).

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  api:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd  # v5
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78  # v7
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run ty check
      - run: uv run pytest
```

- [ ] **Step 2: Lint the workflow**

Run from repo root:
```bash
actionlint .github/workflows/ci.yml && zizmor .github/workflows/ci.yml
```
Expected: no findings from either tool (zizmor may need `--no-online-audits` offline).

**As-built deviations:** after review, the workflow gained a `concurrency` block
(cancel superseded runs on the same ref) and `apps/api/.python-version` was added to
pin the interpreter uv resolves. The `pytest` step also briefly tolerated exit code 5
(empty test suite) until Task 4 landed the first tests, at which point that tolerance
was removed again.

- [ ] **Step 3: Commit**

```bash
git add .github/
git commit -m "Add CI: lint, format check, types, tests"
```

---

### Task 4: `engine.strength` — 1RM estimation and load prescription

**Files:**
- Create: `apps/api/src/performance_agent/engine/strength.py`
- Test: `apps/api/tests/engine/test_strength.py`

All commands in Tasks 4–10 run from `apps/api/`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/engine/test_strength.py`:

```python
import pytest

from performance_agent.engine.strength import (
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
)


def test_epley_known_value():
    assert one_rm_epley(load_kg=100, reps=5) == pytest.approx(116.67, abs=0.01)


def test_epley_single_rep_is_the_load_itself():
    assert one_rm_epley(load_kg=100, reps=1) == 100.0


def test_brzycki_known_value():
    assert one_rm_brzycki(load_kg=100, reps=5) == pytest.approx(112.5, abs=0.01)


@pytest.mark.parametrize("reps", [0, -1, 13])
def test_rep_range_is_validated(reps):
    with pytest.raises(ValueError, match="reps"):
        one_rm_epley(load_kg=100, reps=reps)
    with pytest.raises(ValueError, match="reps"):
        one_rm_brzycki(load_kg=100, reps=reps)


@pytest.mark.parametrize("load_kg", [0, -20])
def test_load_must_be_positive(load_kg):
    with pytest.raises(ValueError, match="load"):
        one_rm_epley(load_kg=load_kg, reps=5)


def test_load_for_percentage():
    assert load_for_percentage(one_rm_kg=150, percentage=0.8) == pytest.approx(120.0)


@pytest.mark.parametrize("percentage", [0, -0.1, 1.31])
def test_percentage_is_validated(percentage):
    with pytest.raises(ValueError, match="percentage"):
        load_for_percentage(one_rm_kg=150, percentage=percentage)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_strength.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'performance_agent.engine.strength'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/performance_agent/engine/strength.py`:

```python
"""Strength math: 1RM estimation and percentage-based load prescription.

Formulas are only validated for 1-12 repetitions; both Epley and Brzycki
degrade badly beyond ~10 reps, so higher inputs are rejected.
"""

MAX_ESTIMATION_REPS = 12
MAX_PERCENTAGE = 1.3  # supra-maximal work (eccentrics, partials) tops out around 130%


def _validate_load_and_reps(load_kg: float, reps: int) -> None:
    if load_kg <= 0:
        msg = f"load_kg must be positive, got {load_kg}"
        raise ValueError(msg)
    if not 1 <= reps <= MAX_ESTIMATION_REPS:
        msg = f"reps must be between 1 and {MAX_ESTIMATION_REPS}, got {reps}"
        raise ValueError(msg)


def one_rm_epley(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Epley formula: load * (1 + reps / 30).

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * (1 + reps / 30)


def one_rm_brzycki(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Brzycki formula: load * 36 / (37 - reps)."""
    _validate_load_and_reps(load_kg, reps)
    return load_kg * 36 / (37 - reps)


def load_for_percentage(one_rm_kg: float, percentage: float) -> float:
    """Return the absolute load for a fraction of 1RM (e.g. 0.8 for 80%)."""
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg}"
        raise ValueError(msg)
    if not 0 < percentage <= MAX_PERCENTAGE:
        msg = f"percentage must be in (0, {MAX_PERCENTAGE}], got {percentage}"
        raise ValueError(msg)
    return one_rm_kg * percentage
```

**As-built deviations:** the shipped `strength.py` rejects non-integer and boolean
`reps` (`"reps must be a whole number"`), and tests were added for accepted boundary
values. Brzycki later gained the same `reps == 1` early-return guard as Epley — a
Hypothesis counterexample surfaced `100 * 36 / 36` landing one ULP below `100.0` due to
floating-point rounding, fixed in Task 9's commits.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_strength.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/strength.py tests/engine/test_strength.py
git commit -m "Add engine.strength: 1RM estimation and load prescription"
```

---

### Task 5: `engine.endurance` — Riegel prediction and pace utilities

**Files:**
- Create: `apps/api/src/performance_agent/engine/endurance.py`
- Test: `apps/api/tests/engine/test_endurance.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/engine/test_endurance.py`:

```python
import pytest

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict


def test_riegel_20min_5k_predicts_about_41_42_10k():
    predicted = riegel_predict(
        known_distance_m=5000, known_time_s=1200, target_distance_m=10000
    )
    assert predicted == pytest.approx(2502, abs=2)


def test_riegel_same_distance_returns_same_time():
    assert riegel_predict(
        known_distance_m=5000, known_time_s=1200, target_distance_m=5000
    ) == pytest.approx(1200)


def test_riegel_shorter_distance_predicts_faster_time():
    predicted = riegel_predict(
        known_distance_m=10000, known_time_s=2700, target_distance_m=5000
    )
    assert predicted < 1350  # faster than half the 10K time is impossible; slower pace-wise


@pytest.mark.parametrize(
    ("known_d", "known_t", "target_d"),
    [(0, 1200, 5000), (5000, 0, 10000), (5000, 1200, -1)],
)
def test_riegel_validates_inputs(known_d, known_t, target_d):
    with pytest.raises(ValueError, match="positive"):
        riegel_predict(
            known_distance_m=known_d, known_time_s=known_t, target_distance_m=target_d
        )


def test_pace_s_per_km():
    assert pace_s_per_km(distance_m=10000, time_s=2700) == pytest.approx(270.0)


def test_pace_validates_inputs():
    with pytest.raises(ValueError, match="positive"):
        pace_s_per_km(distance_m=0, time_s=2700)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_endurance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'performance_agent.engine.endurance'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/performance_agent/engine/endurance.py`:

```python
"""Endurance performance prediction (Riegel model) and pace utilities."""

RIEGEL_EXPONENT = 1.06  # Riegel (1981) empirical fatigue exponent for running


def riegel_predict(
    known_distance_m: float,
    known_time_s: float,
    target_distance_m: float,
    exponent: float = RIEGEL_EXPONENT,
) -> float:
    """Predict a race time at a new distance from a known performance.

    Uses Riegel's power law: t2 = t1 * (d2 / d1) ** exponent. Reasonable for
    race distances between ~1.5 km and the marathon; accuracy degrades outside
    that range.
    """
    if known_distance_m <= 0 or known_time_s <= 0 or target_distance_m <= 0:
        msg = (
            "known_distance_m, known_time_s and target_distance_m must be positive, "
            f"got {known_distance_m}, {known_time_s}, {target_distance_m}"
        )
        raise ValueError(msg)
    return known_time_s * (target_distance_m / known_distance_m) ** exponent


def pace_s_per_km(distance_m: float, time_s: float) -> float:
    """Return pace in seconds per kilometre."""
    if distance_m <= 0 or time_s <= 0:
        msg = f"distance_m and time_s must be positive, got {distance_m}, {time_s}"
        raise ValueError(msg)
    return time_s / (distance_m / 1000)
```

**As-built deviations:** the shipped `endurance.py` additionally enforces the Riegel
model's validity band — both `known_distance_m` and `target_distance_m` must fall
within `[RIEGEL_MIN_DISTANCE_M, RIEGEL_MAX_DISTANCE_M]` (1500 to 42195 m) — and rejects
`exponent` outside `(0, MAX_RIEGEL_EXPONENT]` (1.3), raising `ValueError` for both.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_endurance.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/endurance.py tests/engine/test_endurance.py
git commit -m "Add engine.endurance: Riegel prediction and pace utilities"
```

---

### Task 6: `engine.load` — session-RPE load and ACWR

**Files:**
- Create: `apps/api/src/performance_agent/engine/load.py`
- Test: `apps/api/tests/engine/test_load.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/engine/test_load.py`:

```python
import pytest

from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)


def test_session_rpe_load():
    assert session_rpe_load(rpe=7, duration_min=60) == 420.0


@pytest.mark.parametrize(("rpe", "duration"), [(0, 60), (11, 60), (7, 0)])
def test_session_rpe_load_validates_inputs(rpe, duration):
    with pytest.raises(ValueError, match="rpe|duration"):
        session_rpe_load(rpe=rpe, duration_min=duration)


def test_weekly_loads_sums_by_seven_day_blocks():
    assert weekly_loads([100.0] * 14) == [700.0, 700.0]


def test_weekly_loads_keeps_partial_final_week():
    assert weekly_loads([100.0] * 10) == [700.0, 300.0]


def test_weekly_loads_empty_input():
    assert weekly_loads([]) == []


def test_acwr_uniform_history_is_one():
    assert acute_chronic_ratio([100.0] * 28) == pytest.approx(1.0)


def test_acwr_spike_in_last_week():
    history = [100.0] * 21 + [150.0] * 7
    assert acute_chronic_ratio(history) == pytest.approx(1.3333, abs=0.001)


def test_acwr_requires_28_days_of_history():
    assert acute_chronic_ratio([100.0] * 27) is None


def test_acwr_zero_chronic_load_returns_none():
    assert acute_chronic_ratio([0.0] * 28) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_load.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'performance_agent.engine.load'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/performance_agent/engine/load.py`:

```python
"""Training load quantification: session-RPE and acute:chronic workload ratio.

ACWR is provided as a monitoring signal only. Its injury-prediction validity
is contested in the literature; downstream agents must present it as a
descriptive trend, never as an injury probability.
"""

from collections.abc import Sequence

MIN_RPE = 1
MAX_RPE = 10
DAYS_PER_WEEK = 7
CHRONIC_WINDOW_DAYS = 28


def session_rpe_load(rpe: int, duration_min: int) -> float:
    """Return Foster's session-RPE load: RPE (CR-10) x duration in minutes."""
    if not MIN_RPE <= rpe <= MAX_RPE:
        msg = f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe}"
        raise ValueError(msg)
    if duration_min <= 0:
        msg = f"duration_min must be positive, got {duration_min}"
        raise ValueError(msg)
    return float(rpe * duration_min)


def weekly_loads(daily_loads: Sequence[float]) -> list[float]:
    """Sum daily loads into consecutive 7-day blocks (last block may be partial)."""
    return [
        sum(daily_loads[start : start + DAYS_PER_WEEK])
        for start in range(0, len(daily_loads), DAYS_PER_WEEK)
    ]


def acute_chronic_ratio(daily_loads: Sequence[float]) -> float | None:
    """Return acute (7-day mean) over chronic (28-day mean) workload ratio.

    Returns None when fewer than 28 days of history exist or when the chronic
    load is zero (an untrained window makes the ratio meaningless).
    """
    if len(daily_loads) < CHRONIC_WINDOW_DAYS:
        return None
    window = daily_loads[-CHRONIC_WINDOW_DAYS:]
    chronic = sum(window) / CHRONIC_WINDOW_DAYS
    if chronic == 0:
        return None
    acute = sum(window[-DAYS_PER_WEEK:]) / DAYS_PER_WEEK
    return acute / chronic
```

**As-built deviations:** the shipped `load.py` rejects non-finite daily loads
(`math.isfinite`), documents that `acute_chronic_ratio` computes the *coupled* ACWR
(the acute window sits inside the chronic window, inflating self-correlation) directly
in its docstring, and adds whole-number guards on `rpe` and `duration_min`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_load.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/load.py tests/engine/test_load.py
git commit -m "Add engine.load: session-RPE load, weekly blocks, ACWR"
```

---

### Task 7: `engine.feasibility` — goal feasibility scoring

**Files:**
- Create: `apps/api/src/performance_agent/engine/feasibility.py`
- Test: `apps/api/tests/engine/test_feasibility.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/engine/test_feasibility.py`:

```python
import pytest

from performance_agent.engine.feasibility import (
    FeasibilityResult,
    TrainingAge,
    endurance_feasibility,
)


def test_unrealistic_goal_gets_near_zero_probability():
    # 10K from 55:00 to 35:00 in 12 weeks (the spec's canonical honest-coach case)
    result = endurance_feasibility(
        current_time_s=3300,
        target_time_s=2100,
        weeks=12,
        training_age=TrainingAge.BEGINNER,
    )
    assert result.probability < 0.05


def test_reasonable_goal_gets_high_probability():
    # 10K from 47:00 to 45:00 in 16 weeks, intermediate athlete
    result = endurance_feasibility(
        current_time_s=2820,
        target_time_s=2700,
        weeks=16,
        training_age=TrainingAge.INTERMEDIATE,
    )
    assert 0.7 < result.probability < 0.9


def test_already_achieved_goal_is_near_certain():
    result = endurance_feasibility(
        current_time_s=2700,
        target_time_s=2820,
        weeks=8,
        training_age=TrainingAge.ADVANCED,
    )
    assert result.probability > 0.9


def test_result_exposes_the_rates_behind_the_probability():
    result = endurance_feasibility(
        current_time_s=3300,
        target_time_s=3000,
        weeks=10,
        training_age=TrainingAge.BEGINNER,
    )
    assert isinstance(result, FeasibilityResult)
    assert result.required_weekly_rate == pytest.approx(0.00909, abs=0.0001)
    assert result.achievable_weekly_rate == pytest.approx(0.010)
    assert result.ratio == pytest.approx(0.909, abs=0.01)


def test_more_time_never_lowers_probability():
    p_short = endurance_feasibility(
        current_time_s=3300, target_time_s=2820, weeks=8,
        training_age=TrainingAge.INTERMEDIATE,
    ).probability
    p_long = endurance_feasibility(
        current_time_s=3300, target_time_s=2820, weeks=24,
        training_age=TrainingAge.INTERMEDIATE,
    ).probability
    assert p_long > p_short


@pytest.mark.parametrize(
    ("current", "target", "weeks"),
    [(0, 2100, 12), (3300, 0, 12), (3300, 2100, 0)],
)
def test_inputs_are_validated(current, target, weeks):
    with pytest.raises(ValueError, match="positive"):
        endurance_feasibility(
            current_time_s=current,
            target_time_s=target,
            weeks=weeks,
            training_age=TrainingAge.BEGINNER,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_feasibility.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'performance_agent.engine.feasibility'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/performance_agent/engine/feasibility.py`:

```python
"""Goal feasibility: required progression rate vs empirically achievable rates.

Model (documented assumption, revisit with data): improvement demand is spread
linearly over the available weeks and compared against sustainable weekly
improvement rates by training age. The required/achievable ratio maps to a
probability through a logistic curve centred at ratio 1.0. This is a coarse,
honest prior — not a guarantee — and downstream agents must present it with
its drivers (the two rates), never as a bare number.
"""

import math
from dataclasses import dataclass
from enum import StrEnum


class TrainingAge(StrEnum):
    """Coarse training-experience buckets used for achievable-rate lookup."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Sustainable weekly improvement in endurance performance (fraction of current
# time), by training age. Conservative mid-points from coaching literature.
ACHIEVABLE_WEEKLY_RATE: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.010,
    TrainingAge.INTERMEDIATE: 0.005,
    TrainingAge.ADVANCED: 0.0025,
}

LOGISTIC_STEEPNESS = 3.0
# Clamp the logistic exponent so extreme ratios neither overflow math.exp nor
# collapse the probability to exactly 0.0 or 1.0 (it must stay in (0, 1)).
MAX_LOGISTIC_EXPONENT = 30.0


@dataclass(frozen=True)
class FeasibilityResult:
    """Feasibility verdict with the rates that produced it (for explainability)."""

    required_weekly_rate: float
    achievable_weekly_rate: float
    ratio: float
    probability: float


def endurance_feasibility(
    current_time_s: float,
    target_time_s: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of an endurance time goal.

    Args:
        current_time_s: Current performance over the goal distance, in seconds.
        target_time_s: Target performance over the same distance, in seconds.
        weeks: Weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    if current_time_s <= 0 or target_time_s <= 0 or weeks <= 0:
        msg = (
            "current_time_s, target_time_s and weeks must be positive, "
            f"got {current_time_s}, {target_time_s}, {weeks}"
        )
        raise ValueError(msg)
    improvement_needed = (current_time_s - target_time_s) / current_time_s
    required_weekly_rate = improvement_needed / weeks
    achievable_weekly_rate = ACHIEVABLE_WEEKLY_RATE[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    exponent = LOGISTIC_STEEPNESS * (ratio - 1)
    exponent = max(min(exponent, MAX_LOGISTIC_EXPONENT), -MAX_LOGISTIC_EXPONENT)
    probability = 1 / (1 + math.exp(exponent))
    return FeasibilityResult(
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=probability,
    )
```

**As-built deviations:** `FeasibilityResult` gained `improvement_needed` as its first
field (alongside the existing rates). The module docstring discloses that the model
assumes a constant achievable rate over arbitrary horizons and no asymptotic
performance limit, so long-horizon and already-met verdicts are optimistic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_feasibility.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/feasibility.py tests/engine/test_feasibility.py
git commit -m "Add engine.feasibility: rate-based goal feasibility scoring"
```

---

### Task 8: `engine.periodization` — weekly waves, deloads, taper

**Files:**
- Create: `apps/api/src/performance_agent/engine/periodization.py`
- Test: `apps/api/tests/engine/test_periodization.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/engine/test_periodization.py`:

```python
import pytest

from performance_agent.engine.periodization import WeekLoad, build_weekly_waves


def test_eight_week_block_shape():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    assert len(waves) == 8
    assert [w.week for w in waves] == list(range(1, 9))


def test_deload_lands_every_fourth_building_week():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    assert waves[3].is_deload
    assert not waves[3].is_taper
    assert waves[3].volume_factor < waves[2].volume_factor
    assert waves[3].intensity_factor < 1.0


def test_volume_ramps_within_a_building_block():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    building = waves[0:3]
    volumes = [w.volume_factor for w in building]
    assert volumes == sorted(volumes)
    assert volumes[0] < volumes[-1]


def test_taper_cuts_volume_but_keeps_intensity():
    waves = build_weekly_waves(total_weeks=8, deload_every=4, taper_weeks=1)
    taper = waves[-1]
    assert taper.is_taper
    assert taper.volume_factor < 0.7
    assert taper.intensity_factor >= 1.0


def test_no_taper_when_taper_weeks_is_zero():
    waves = build_weekly_waves(total_weeks=4, deload_every=4, taper_weeks=0)
    assert not any(w.is_taper for w in waves)


def test_weeks_are_frozen_value_objects():
    week = WeekLoad(
        week=1, volume_factor=1.0, intensity_factor=1.0, is_deload=False, is_taper=False
    )
    with pytest.raises(AttributeError):
        week.volume_factor = 2.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("total_weeks", "deload_every", "taper_weeks"),
    [(0, 4, 1), (8, 1, 1), (8, 4, 8)],
)
def test_inputs_are_validated(total_weeks, deload_every, taper_weeks):
    with pytest.raises(ValueError, match="weeks|deload"):
        build_weekly_waves(
            total_weeks=total_weeks, deload_every=deload_every, taper_weeks=taper_weeks
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_periodization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'performance_agent.engine.periodization'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/performance_agent/engine/periodization.py`:

```python
"""Weekly volume/intensity wave generation with deloads and taper.

Factors are multipliers against a baseline week (1.0 = baseline volume or
intensity). The Periodization agent later maps these onto concrete sessions.
"""

from dataclasses import dataclass

MIN_DELOAD_EVERY = 2
DEFAULT_VOLUME_RAMP = 0.05
DEFAULT_INTENSITY_RAMP = 0.025
DELOAD_INTENSITY = 0.9
TAPER_VOLUME = 0.5
TAPER_INTENSITY = 1.0


@dataclass(frozen=True)
class WeekLoad:
    """Planned load multipliers for one training week (week is 1-indexed)."""

    week: int
    volume_factor: float
    intensity_factor: float
    is_deload: bool
    is_taper: bool


def build_weekly_waves(
    total_weeks: int,
    *,
    deload_every: int = 4,
    taper_weeks: int = 1,
    volume_ramp: float = DEFAULT_VOLUME_RAMP,
    deload_volume: float = 0.6,
) -> list[WeekLoad]:
    """Generate week-by-week load multipliers for a training block.

    Building weeks ramp volume by ``volume_ramp`` and intensity by 2.5% per
    week within each mesocycle; every ``deload_every``-th building week drops
    to ``deload_volume`` volume at 90% intensity; the final ``taper_weeks``
    weeks halve volume while holding intensity.
    """
    if total_weeks < 1:
        msg = f"total_weeks must be >= 1, got {total_weeks}"
        raise ValueError(msg)
    if deload_every < MIN_DELOAD_EVERY:
        msg = f"deload_every must be >= {MIN_DELOAD_EVERY}, got {deload_every}"
        raise ValueError(msg)
    if not 0 <= taper_weeks < total_weeks:
        msg = f"taper_weeks must be >= 0 and < total_weeks, got {taper_weeks}"
        raise ValueError(msg)

    waves: list[WeekLoad] = []
    week_in_block = 0
    for week in range(1, total_weeks + 1):
        if week > total_weeks - taper_weeks:
            waves.append(
                WeekLoad(week, TAPER_VOLUME, TAPER_INTENSITY, is_deload=False, is_taper=True)
            )
            continue
        week_in_block += 1
        if week_in_block == deload_every:
            waves.append(
                WeekLoad(week, deload_volume, DELOAD_INTENSITY, is_deload=True, is_taper=False)
            )
            week_in_block = 0
            continue
        volume = 1.0 + volume_ramp * (week_in_block - 1)
        intensity = 1.0 + DEFAULT_INTENSITY_RAMP * (week_in_block - 1)
        waves.append(WeekLoad(week, volume, intensity, is_deload=False, is_taper=False))
    return waves
```

**As-built deviations:** `volume_ramp` and `deload_volume` were demoted from function
parameters to module constants (`DEFAULT_VOLUME_RAMP`, `DELOAD_VOLUME = 0.6`) — they
were never varied by callers. The shipped signature is
`build_weekly_waves(total_weeks, *, deload_every=4, taper_weeks=1)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_periodization.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/periodization.py tests/engine/test_periodization.py
git commit -m "Add engine.periodization: weekly waves with deloads and taper"
```

---

### Task 9: Public engine API and property-based invariants

**Files:**
- Modify: `apps/api/src/performance_agent/engine/__init__.py`
- Test: `apps/api/tests/engine/test_properties.py`

- [ ] **Step 1: Write the failing property tests**

Create `apps/api/tests/engine/test_properties.py`:

```python
from hypothesis import assume, given
from hypothesis import strategies as st

from performance_agent.engine import (
    build_weekly_waves,
    endurance_feasibility,
    one_rm_epley,
    riegel_predict,
)
from performance_agent.engine.feasibility import TrainingAge

loads = st.floats(min_value=1, max_value=500, allow_nan=False)
times = st.floats(min_value=60, max_value=36000, allow_nan=False)
riegel_distances = st.floats(min_value=1500, max_value=42195, allow_nan=False)


@given(load_kg=loads, reps=st.integers(min_value=1, max_value=11))
def test_one_rm_never_decreases_with_more_reps(load_kg, reps):
    assert one_rm_epley(load_kg, reps + 1) >= one_rm_epley(load_kg, reps)


@given(load_kg=loads, reps=st.integers(min_value=1, max_value=12))
def test_one_rm_is_at_least_the_lifted_load(load_kg, reps):
    assert one_rm_epley(load_kg, reps) >= load_kg


@given(d1=riegel_distances, d2=riegel_distances, known_t=times)
def test_riegel_longer_distance_takes_longer(d1, d2, known_t):
    assume(abs(d2 - d1) > 1.0)
    lo, hi = min(d1, d2), max(d1, d2)
    assert riegel_predict(lo, known_t, hi) > known_t


@given(
    current=times,
    target=times,
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_feasibility_probability_is_a_probability(current, target, weeks, age):
    result = endurance_feasibility(current, target, weeks, age)
    assert 0.0 < result.probability < 1.0


@given(
    total_weeks=st.integers(min_value=2, max_value=52),
    deload_every=st.integers(min_value=2, max_value=8),
)
def test_waves_cover_every_week_with_positive_factors(total_weeks, deload_every):
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=1)
    assert len(waves) == total_weeks
    assert all(w.volume_factor > 0 and w.intensity_factor > 0 for w in waves)
```

**As-built deviations:** the plan's original `test_riegel_longer_distance_takes_longer`
(drawing `known_d` from a 1000-42195 m strategy and multiplying by a random `factor`)
was latently broken against the Riegel validity band `endurance.py` enforces (Task 5's
as-built deviation) — `known_d * factor` can land above 42195 m or the distances can be
lower than the 1500 m floor, both now rejected with `ValueError`. The as-built version
above draws both endpoints from `riegel_distances` (1500-42195 m), discards draws closer
than 1 m apart with `assume`, and orders them low-to-high before calling
`riegel_predict`. Properties were later parametrized over both 1RM formulas
(`one_rm_formulas = st.sampled_from([one_rm_epley, one_rm_brzycki])`) and extended with
load-conservation (`weekly_loads` sums equal the input total), ACWR non-negativity, and
week-numbering properties.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_properties.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_weekly_waves' from 'performance_agent.engine'`
(the names are not yet re-exported).

- [ ] **Step 3: Re-export the public engine API**

Replace `apps/api/src/performance_agent/engine/__init__.py` with:

```python
"""Deterministic sports science engine (no LLM, no I/O).

Public API re-exports. Agents call these functions as tools; they never
compute training numbers themselves.
"""

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict
from performance_agent.engine.feasibility import (
    FeasibilityResult,
    TrainingAge,
    endurance_feasibility,
)
from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)
from performance_agent.engine.periodization import WeekLoad, build_weekly_waves
from performance_agent.engine.strength import (
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
)

__all__ = [
    "FeasibilityResult",
    "TrainingAge",
    "WeekLoad",
    "acute_chronic_ratio",
    "build_weekly_waves",
    "endurance_feasibility",
    "load_for_percentage",
    "one_rm_brzycki",
    "one_rm_epley",
    "pace_s_per_km",
    "riegel_predict",
    "session_rpe_load",
    "weekly_loads",
]
```

- [ ] **Step 4: Run the full engine suite**

Run: `uv run pytest tests/engine -v`
Expected: all PASS (property tests included).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run ty check
git add src/performance_agent/engine/__init__.py tests/engine/test_properties.py
git commit -m "Add engine public API and Hypothesis invariant tests"
```

---

### Task 10: Architectural guard — engine purity

**Files:**
- Test: `apps/api/tests/engine/test_engine_purity.py`

The spec (§12) requires "no LLM imports in engine — enforced". This test IS the
enforcement: it fails the build if anyone ever imports an LLM SDK, HTTP client,
or ORM inside `engine/`.

- [ ] **Step 1: Write the test (passes immediately — it guards the future)**

Create `apps/api/tests/engine/test_engine_purity.py`:

```python
"""Architectural test: the engine must stay pure (stdlib-only, no I/O)."""

import ast
from pathlib import Path

import performance_agent.engine

assert performance_agent.engine.__file__ is not None  # a real package on disk
ENGINE_DIR = Path(performance_agent.engine.__file__).parent

ALLOWED_STDLIB = {
    "math",
    "statistics",
    "dataclasses",
    "enum",
    "typing",
    "collections",
    "collections.abc",
}
ALLOWED_INTERNAL_PREFIX = "performance_agent.engine"


def iter_imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def test_engine_modules_import_only_stdlib_math_and_engine_siblings():
    violations = []
    for path in sorted(ENGINE_DIR.rglob("*.py")):
        for module in iter_imported_modules(path):
            allowed = module in ALLOWED_STDLIB or module.startswith(ALLOWED_INTERNAL_PREFIX)
            if not allowed:
                violations.append(f"{path.name} imports {module}")
    assert not violations, (
        "engine/ must stay deterministic and dependency-free (spec section 4.2); "
        f"forbidden imports found: {violations}"
    )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/engine/test_engine_purity.py -v`
Expected: PASS.

- [ ] **Step 3: Verify the test actually catches violations (break it on purpose)**

Temporarily add `import json` (not in the allow-list) to the top of
`src/performance_agent/engine/strength.py`, run the test again:

Run: `uv run pytest tests/engine/test_engine_purity.py -v`
Expected: FAIL with `strength.py imports json` in the message.

Remove the temporary import, re-run, confirm PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/engine/test_engine_purity.py
git commit -m "Add architectural test enforcing engine purity"
```

---

### Task 11: Final verification sweep

**As-built deviations:** the README-engine-section step below moved to a dedicated
follow-up task — a full README rewrite is planned separately, so this plan's closeout
no longer touches `README.md`.

**Files:**
- Modify: `README.md` (engine section) — **superseded, see note above**

- [ ] **Step 1: Run the complete quality gate**

Run from `apps/api/`:
```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
```
Expected: zero warnings, all tests pass.

Run from repo root:
```bash
prek run --all-files
```
Expected: all hooks pass.

- [ ] **Step 2: Document the engine in the README**

Append to the repo-root `README.md`, after the "Repository layout" section:

```markdown
## Sports science engine

`performance_agent.engine` is the deterministic core: 1RM estimation
(Epley/Brzycki), Riegel endurance prediction, session-RPE training load and
ACWR, rate-based goal feasibility scoring, and periodization wave generation.
It has no LLM, network, or database dependencies — enforced by an
architectural test (`tests/engine/test_engine_purity.py`).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document sports science engine in README"
```

---

## Self-Review Notes

- **Spec coverage (this plan's slice):** engine models from spec §4.2 —
  1RM formulas ✓ (Task 4), endurance predictors ✓ (Task 5), session-RPE/ACWR ✓ (Task 6),
  feasibility scoring ✓ (Task 7), periodization math ✓ (Task 8), purity enforcement ✓
  (Task 10). Banister fitness–fatigue and Monte Carlo simulation are V2 per spec §16 —
  deliberately absent. CP/W′ and sprint/jump benchmark tables are deferred to Plan 5
  (program generation), where their consumers exist — noted here so it isn't lost.
- **Type consistency:** function and type names verified identical across tasks 4–10
  (`one_rm_epley`, `riegel_predict`, `session_rpe_load`, `endurance_feasibility`,
  `build_weekly_waves`, `FeasibilityResult`, `TrainingAge`, `WeekLoad`).
- **Placeholder scan:** the only intentional placeholder is the `rev` in Task 2 Step 1,
  immediately pinned by `prek auto-update` in Step 2.
