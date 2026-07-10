# Plan 02 — MCP Server Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the deterministic sports-science engine as an MCP server that Claude
Code / Gemini CLI / Codex can call as tools, with a console entrypoint and install docs.

**Architecture:** Per spec v2 (`docs/superpowers/specs/2026-07-10-performanceagent-architecture-design.md`
§3, §7, §10), the host agent CLI is the coach; this plan builds the `performance-agent`
MCP server (stdio) whose tools own every training number. Also flattens the repo
(apps/api → root) since the web app that justified the monorepo is gone.

**Tech Stack:** Python 3.13, `mcp` SDK v2 (`MCPServer`, formerly FastMCP; in-memory
`mcp.Client` for tests), uv/ruff/ty/pytest (unchanged).

**SDK facts verified 2026-07-10 via context7 (`/modelcontextprotocol/python-sdk`):**
- Server: `from mcp.server import MCPServer`; `mcp = MCPServer("name")`;
  `@mcp.tool()` on typed functions (docstring = tool description, type hints →
  input/output schema); `mcp.run()` = stdio.
- Tests: `from mcp import Client`; `async with Client(mcp) as client:` (in-process);
  `await client.call_tool(name, args)` → result with `.is_error`,
  `.structured_content`, `.content`. anyio-based: `@pytest.mark.anyio` +
  `anyio_backend` fixture returning `"asyncio"`.
- Errors: a `ValueError` raised inside a tool does NOT raise client-side — the result
  has `is_error=True` and the message (prefixed with the tool name) in `content` for
  the model to read. Exactly what we want for the engine's actionable messages.
- Stdio client (E2E): `Client(stdio_client(StdioServerParameters(command=..., args=[...])))`.
- If any imported name differs in the installed SDK version (e.g. `StdioServerParameters`
  location, `list_tools()` return shape), adapt minimally to the installed API and
  report the deviation — do NOT downgrade the SDK to match the plan.

---

## MVP Plan Sequence (spec v2 §10)

1. ✅ Foundation & sports science engine
2. **MCP server core** ← this plan
3. Athlete memory (file schemas, memory tools, time context)
4. Evidence corpus (seed manifest, SQLite FTS5, citation check)
5. Coaching skills + eval harness
6. Typst reports
7. Distribution (PyPI, corpus releases)

---

## File Structure (after this plan)

```
performance-agent/                    # repo root — package moves here from apps/api
├── pyproject.toml                    # + [project.scripts] performance-agent, + mcp dep
├── uv.lock
├── .python-version
├── src/performance_agent/
│   ├── engine/                       # untouched (Plan 01)
│   └── server/
│       ├── __init__.py               # docstring only
│       ├── engine_tools.py           # 9 tool functions + register(mcp)
│       └── app.py                    # MCPServer instance + main()
├── tests/
│   ├── engine/                       # untouched (93 tests)
│   └── server/
│       ├── __init__.py
│       ├── conftest.py               # anyio backend + in-memory client fixtures
│       ├── test_engine_tools.py      # happy paths + tool listing
│       ├── test_errors.py            # ValueError → is_error surfacing
│       └── test_stdio_e2e.py         # real subprocess over stdio
├── docs/installing.md                # Claude Code / Gemini CLI / Codex setup
└── .github/workflows/ci.yml          # working-directory removed
```

`engine_tools.py` = tool functions only; `app.py` = server assembly + entrypoint.
Plans 03/04/06 will add sibling `memory_tools.py` / `evidence_tools.py` /
`report_tools.py` and register them in `app.py`.

---

### Task 1: Flatten the repository (apps/api → root)

The monorepo `apps/` split existed for the now-dropped web app. Single Python package
→ package at root. `git mv` preserves history.

**Files:**
- Move: `apps/api/pyproject.toml`, `apps/api/uv.lock`, `apps/api/.python-version` → repo root
- Move: `apps/api/src` → `src`, `apps/api/tests` → `tests`
- Delete: `apps/api/README.md` (root README.md now serves as the package readme)
- Modify: `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `README.md`

- [ ] **Step 1: Move the package**

Run from repo root:
```bash
git mv apps/api/pyproject.toml apps/api/uv.lock apps/api/.python-version .
git mv apps/api/src src
git mv apps/api/tests tests
git rm -q apps/api/README.md
```
Then remove the leftover (untracked `.venv`, empty dirs): `trash apps/` (never `rm -rf`).
Note: `pyproject.toml`'s `readme = "README.md"` now resolves to the root showcase
README — correct, no edit needed.

- [ ] **Step 2: Re-sync the environment at root**

```bash
uv sync
```
Expected: creates `./.venv`, `Resolved 11 packages`, no lockfile changes.

- [ ] **Step 3: Update `.pre-commit-config.yaml`** — the three hooks no longer need
`cd apps/api`. Replace the file content with:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --fix .
        language: system
        types: [python]
        pass_filenames: false
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format .
        language: system
        types: [python]
        pass_filenames: false
      - id: ty
        name: ty check
        entry: uv run ty check
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 4: Update `.github/workflows/ci.yml`** — delete the `defaults:` block
(3 lines: `defaults:`, `run:`, `working-directory: apps/api`). Everything else stays.

- [ ] **Step 5: Update `README.md`** — in the "For developers" section, replace
"Repository layout: `apps/api` (Python package: engine, soon MCP server) ·" with
"Repository layout: `src/performance_agent` (engine + MCP server) ·".

- [ ] **Step 6: Full gate — everything must still be green**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 93 passed
prek run --all-files
actionlint .github/workflows/ci.yml
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Flatten repo: move Python package from apps/api to root"
```

---

### Task 2: Server skeleton with the first tool (TDD)

**Files:**
- Create: `src/performance_agent/server/__init__.py`
- Create: `src/performance_agent/server/engine_tools.py`
- Create: `src/performance_agent/server/app.py`
- Create: `tests/server/__init__.py` (empty), `tests/server/conftest.py`
- Test: `tests/server/test_engine_tools.py`

- [ ] **Step 1: Add the mcp dependency (exact pin, current version)**

```bash
uv add --bounds exact mcp
```

- [ ] **Step 2: Write the failing test**

`tests/server/conftest.py`:
```python
import pytest
from mcp import Client

from performance_agent.server.app import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c
```

`tests/server/test_engine_tools.py`:
```python
import pytest


@pytest.mark.anyio
async def test_assess_endurance_goal_returns_honest_verdict(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {
            "current_time_s": 3300,
            "target_time_s": 2100,
            "weeks": 12,
            "training_age": "beginner",
        },
    )
    assert not result.is_error
    verdict = result.structured_content
    assert verdict["probability"] < 0.05
    assert verdict["improvement_needed"] == pytest.approx(0.3636, abs=0.001)
    assert verdict["required_weekly_rate"] == pytest.approx(0.0303, abs=0.001)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.010)
```

- [ ] **Step 3: Run to verify red**

Run: `rtk proxy uv run pytest tests/server -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'performance_agent.server'`.

- [ ] **Step 4: Implement**

`src/performance_agent/server/__init__.py`:
```python
"""MCP server exposing the deterministic engine (and later: memory, evidence, reports)."""
```

`src/performance_agent/server/engine_tools.py` (first tool only; the rest come in
Tasks 3-4):
```python
"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from dataclasses import asdict

from mcp.server import MCPServer

from performance_agent.engine import TrainingAge, endurance_feasibility


def assess_endurance_goal(
    current_time_s: float, target_time_s: float, weeks: int, training_age: str
) -> dict[str, float]:
    """Score the feasibility of an endurance time goal (honest-coach verdict).

    Both times are in seconds over the same distance; training_age is one of
    beginner, intermediate, advanced. Returns the success probability (0-1)
    with the drivers behind it (improvement_needed, required vs achievable
    weekly rates, their ratio). Always present the drivers alongside the
    probability, never the bare number.
    """
    try:
        age = TrainingAge(training_age)
    except ValueError:
        valid = ", ".join(a.value for a in TrainingAge)
        msg = f"training_age must be one of: {valid}; got {training_age!r}"
        raise ValueError(msg) from None
    return asdict(endurance_feasibility(current_time_s, target_time_s, weeks, age))


def register(mcp: MCPServer) -> None:
    """Register every engine tool on the server."""
    for tool in (assess_endurance_goal,):
        mcp.tool()(tool)
```

`src/performance_agent/server/app.py`:
```python
"""MCP server assembly and stdio entrypoint."""

from mcp.server import MCPServer

from performance_agent.server import engine_tools

mcp = MCPServer("performance-agent")
engine_tools.register(mcp)


def main() -> None:
    """Run the performance-agent MCP server over stdio."""
    mcp.run()
```

- [ ] **Step 5: Run to verify green**

Run: `rtk proxy uv run pytest tests/server -v`
Expected: 1 passed.

- [ ] **Step 6: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 94 passed
git add pyproject.toml uv.lock src/performance_agent/server tests/server
git commit -m "Add MCP server skeleton with assess_endurance_goal tool"
```

---

### Task 3: Prediction and strength tools (TDD)

**Files:**
- Modify: `src/performance_agent/server/engine_tools.py`
- Test: `tests/server/test_engine_tools.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/server/test_engine_tools.py`:

```python
@pytest.mark.anyio
async def test_predict_race_time_includes_pace(client):
    result = await client.call_tool(
        "predict_race_time",
        {"known_distance_m": 5000, "known_time_s": 1200, "target_distance_m": 10000},
    )
    assert not result.is_error
    prediction = result.structured_content
    assert prediction["predicted_time_s"] == pytest.approx(2502, abs=2)
    assert prediction["pace_s_per_km"] == pytest.approx(250.2, abs=0.5)


@pytest.mark.anyio
async def test_compute_pace(client):
    result = await client.call_tool("compute_pace", {"distance_m": 10000, "time_s": 2700})
    assert not result.is_error
    assert result.structured_content["pace_s_per_km"] == pytest.approx(270.0)


@pytest.mark.anyio
async def test_estimate_1rm_default_epley(client):
    result = await client.call_tool("estimate_1rm", {"load_kg": 100, "reps": 5})
    assert not result.is_error
    assert result.structured_content["one_rm_kg"] == pytest.approx(116.67, abs=0.01)
    assert result.structured_content["formula"] == "epley"


@pytest.mark.anyio
async def test_estimate_1rm_brzycki(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 5, "formula": "brzycki"}
    )
    assert not result.is_error
    assert result.structured_content["one_rm_kg"] == pytest.approx(112.5, abs=0.01)


@pytest.mark.anyio
async def test_prescribe_load(client):
    result = await client.call_tool("prescribe_load", {"one_rm_kg": 150, "percentage": 0.8})
    assert not result.is_error
    assert result.structured_content["load_kg"] == pytest.approx(120.0)
```

- [ ] **Step 2: Run to verify red**

Run: `rtk proxy uv run pytest tests/server -v`
Expected: the 5 new tests FAIL (unknown tool), the first passes.

- [ ] **Step 3: Implement** — in `engine_tools.py`, extend the engine import to:

```python
from performance_agent.engine import (
    TrainingAge,
    endurance_feasibility,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    pace_s_per_km,
    riegel_predict,
)
```

add below the imports:

```python
_ONE_RM_FORMULAS = {"brzycki": one_rm_brzycki, "epley": one_rm_epley}
```

add the tool functions:

```python
def predict_race_time(
    known_distance_m: float, known_time_s: float, target_distance_m: float
) -> dict[str, float]:
    """Predict a race time at a new distance from a known performance (Riegel).

    Distances must be within 1500-42195 m (enforced model validity band).
    Returns the predicted time in seconds and the implied pace in s/km.
    """
    predicted = riegel_predict(known_distance_m, known_time_s, target_distance_m)
    return {
        "predicted_time_s": predicted,
        "pace_s_per_km": pace_s_per_km(target_distance_m, predicted),
    }


def compute_pace(distance_m: float, time_s: float) -> dict[str, float]:
    """Return running pace in seconds per kilometre for a distance and time."""
    return {"pace_s_per_km": pace_s_per_km(distance_m, time_s)}


def estimate_1rm(load_kg: float, reps: int, formula: str = "epley") -> dict[str, float | str]:
    """Estimate a one-rep max in kg from a submaximal set (1-12 reps).

    formula is "epley" (default) or "brzycki". Pick one formula per athlete
    and lift and stay consistent; do not average the two.
    """
    try:
        one_rm = _ONE_RM_FORMULAS[formula]
    except KeyError:
        valid = ", ".join(sorted(_ONE_RM_FORMULAS))
        msg = f"formula must be one of: {valid}; got {formula!r}"
        raise ValueError(msg) from None
    return {"one_rm_kg": one_rm(load_kg, reps), "formula": formula}


def prescribe_load(one_rm_kg: float, percentage: float) -> dict[str, float]:
    """Return the absolute load in kg for a fraction of 1RM (e.g. 0.8 = 80%)."""
    return {"load_kg": load_for_percentage(one_rm_kg, percentage)}
```

and extend `register`'s tuple to:

```python
    for tool in (
        assess_endurance_goal,
        predict_race_time,
        compute_pace,
        estimate_1rm,
        prescribe_load,
    ):
```

- [ ] **Step 4: Run to verify green**

Run: `rtk proxy uv run pytest tests/server -v`
Expected: 6 passed.

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 99 passed
git add src/performance_agent/server/engine_tools.py tests/server/test_engine_tools.py
git commit -m "Add prediction and strength MCP tools"
```

---

### Task 4: Load and periodization tools (TDD)

**Files:**
- Modify: `src/performance_agent/server/engine_tools.py`
- Test: `tests/server/test_engine_tools.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
@pytest.mark.anyio
async def test_compute_session_load(client):
    result = await client.call_tool("compute_session_load", {"rpe": 7, "duration_min": 60})
    assert not result.is_error
    assert result.structured_content["session_load"] == pytest.approx(420.0)


@pytest.mark.anyio
async def test_compute_weekly_loads(client):
    result = await client.call_tool("compute_weekly_loads", {"daily_loads": [100.0] * 10})
    assert not result.is_error
    assert result.structured_content["weekly_totals"] == [700.0, 300.0]


@pytest.mark.anyio
async def test_compute_acwr_with_history(client):
    history = [100.0] * 21 + [150.0] * 7
    result = await client.call_tool("compute_acwr", {"daily_loads": history})
    assert not result.is_error
    assert result.structured_content["acute_chronic_ratio"] == pytest.approx(1.3333, abs=0.001)


@pytest.mark.anyio
async def test_compute_acwr_short_history_is_null_not_error(client):
    result = await client.call_tool("compute_acwr", {"daily_loads": [100.0] * 10})
    assert not result.is_error
    assert result.structured_content["acute_chronic_ratio"] is None


@pytest.mark.anyio
async def test_build_periodization_waves(client):
    result = await client.call_tool(
        "build_periodization_waves",
        {"total_weeks": 8, "deload_every": 4, "taper_weeks": 1},
    )
    assert not result.is_error
    weeks = result.structured_content["weeks"]
    assert len(weeks) == 8
    assert weeks[3]["is_deload"] is True
    assert weeks[3]["volume_factor"] == pytest.approx(0.6)
    assert weeks[7]["is_taper"] is True
    assert weeks[7]["intensity_factor"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_all_engine_tools_are_listed(client):
    listed = await client.list_tools()
    # v2 Client may return an object with .tools or a plain list — handle the
    # installed SDK's actual shape (adapt if needed, report the deviation).
    tools = listed.tools if hasattr(listed, "tools") else listed
    names = {tool.name for tool in tools}
    assert {
        "assess_endurance_goal",
        "predict_race_time",
        "compute_pace",
        "estimate_1rm",
        "prescribe_load",
        "compute_session_load",
        "compute_weekly_loads",
        "compute_acwr",
        "build_periodization_waves",
    } <= names
```

- [ ] **Step 2: Run to verify red** — the 5 new tool tests + listing test FAIL.

- [ ] **Step 3: Implement** — extend the engine import with
`acute_chronic_ratio, build_weekly_waves, session_rpe_load, weekly_loads`, add:

```python
def compute_session_load(rpe: int, duration_min: int) -> dict[str, float]:
    """Return Foster's session-RPE training load (CR-10 RPE x whole minutes)."""
    return {"session_load": session_rpe_load(rpe, duration_min)}


def compute_weekly_loads(daily_loads: list[float]) -> dict[str, list[float]]:
    """Sum daily session loads into consecutive 7-day blocks.

    Blocks are anchored at the first element (oldest day); a short final block
    contains the most recent days.
    """
    return {"weekly_totals": weekly_loads(daily_loads)}


def compute_acwr(daily_loads: list[float]) -> dict[str, float | None]:
    """Acute:chronic workload ratio over the most recent 28 days (coupled variant).

    Returns null when history is shorter than 28 days or the chronic load is
    zero. Descriptive trend only — its injury-prediction validity is contested;
    never present it as an injury probability.
    """
    return {"acute_chronic_ratio": acute_chronic_ratio(daily_loads)}


def build_periodization_waves(
    total_weeks: int, deload_every: int = 4, taper_weeks: int = 1
) -> dict[str, list[dict[str, float | int | bool]]]:
    """Generate week-by-week volume/intensity multipliers for a training block.

    Building weeks ramp volume (+5%/wk) and intensity (+2.5%/wk) within each
    mesocycle; every deload_every-th building week is a deload (0.6 volume,
    0.9 intensity); the final taper_weeks weeks halve volume at baseline
    intensity. Factors are multipliers against a baseline week (1.0).
    """
    waves = build_weekly_waves(total_weeks, deload_every=deload_every, taper_weeks=taper_weeks)
    return {"weeks": [asdict(week) for week in waves]}
```

and extend `register`'s tuple with the four new names (final order:
`assess_endurance_goal, predict_race_time, compute_pace, estimate_1rm,
prescribe_load, compute_session_load, compute_weekly_loads, compute_acwr,
build_periodization_waves`).

- [ ] **Step 4: Run to verify green** — `rtk proxy uv run pytest tests/server -v`: 12 passed.

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 105 passed
git add src/performance_agent/server/engine_tools.py tests/server/test_engine_tools.py
git commit -m "Add load and periodization MCP tools"
```

---

### Task 5: Error surfacing — the agent must receive actionable messages

**Files:**
- Test: `tests/server/test_errors.py`

The engine's `ValueError`s are the product's honesty mechanism; this task proves they
reach the model as readable tool errors (SDK behavior: `is_error=True`, message in
`content`, prefixed with the tool name).

- [ ] **Step 1: Write the tests**

```python
import pytest


async def _error_text(result) -> str:
    assert result.is_error
    return result.content[0].text


@pytest.mark.anyio
async def test_impossible_weeks_surfaces_engine_message(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {"current_time_s": 3300, "target_time_s": 2100, "weeks": 0, "training_age": "beginner"},
    )
    assert "positive" in await _error_text(result)


@pytest.mark.anyio
async def test_unknown_training_age_lists_valid_values(client):
    result = await client.call_tool(
        "assess_endurance_goal",
        {"current_time_s": 3300, "target_time_s": 2100, "weeks": 12, "training_age": "elite"},
    )
    text = await _error_text(result)
    assert "beginner" in text
    assert "intermediate" in text
    assert "advanced" in text


@pytest.mark.anyio
async def test_unknown_formula_lists_valid_values(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 5, "formula": "lombardi"}
    )
    text = await _error_text(result)
    assert "brzycki" in text
    assert "epley" in text


@pytest.mark.anyio
async def test_out_of_band_distance_is_rejected_with_the_band(client):
    result = await client.call_tool(
        "predict_race_time",
        {"known_distance_m": 5000, "known_time_s": 1200, "target_distance_m": 100},
    )
    assert "distance" in await _error_text(result)


@pytest.mark.anyio
async def test_negative_load_is_rejected(client):
    result = await client.call_tool(
        "compute_weekly_loads", {"daily_loads": [100.0, -5.0]}
    )
    assert "negative" in await _error_text(result)
```

(Note: `_error_text` is async only to keep call sites uniform with one `await`; if
ruff flags the needless async, make it a plain function and drop the awaits.)

- [ ] **Step 2: Run — all 5 must pass immediately** (they exercise behavior built in
Tasks 2-4). If any fails, that is a real gap in error propagation: investigate the
SDK's error handling before touching the assertions, and report what you find.

Run: `rtk proxy uv run pytest tests/server/test_errors.py -v`

- [ ] **Step 3: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 110 passed
git add tests/server/test_errors.py
git commit -m "Pin actionable error surfacing through MCP tool results"
```

---

### Task 6: Console entrypoint + stdio E2E smoke test

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/server/test_stdio_e2e.py`

- [ ] **Step 1: Add the console script** — in `pyproject.toml`, after the
`[project]` table (before `[build-system]`), add:

```toml
[project.scripts]
performance-agent = "performance_agent.server.app:main"
```

Then re-sync so the script is installed into the venv:
```bash
uv sync
uv run performance-agent --help 2>/dev/null; echo "exit: $?"
```
(An MCP stdio server has no --help and will wait on stdin or exit on EOF — any exit
without a traceback is fine here; this just proves the script resolves.)

- [ ] **Step 2: Write the E2E test** — `tests/server/test_stdio_e2e.py`:

```python
"""End-to-end: spawn the real server subprocess and speak MCP over stdio."""

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

# If the installed SDK exposes StdioServerParameters elsewhere (e.g.
# mcp.client.stdio), adjust the import minimally and report the deviation.


@pytest.mark.anyio
async def test_stdio_server_exposes_engine_tools():
    params = StdioServerParameters(command="uv", args=["run", "performance-agent"])
    async with Client(stdio_client(params)) as client:
        listed = await client.list_tools()
        tools = listed.tools if hasattr(listed, "tools") else listed
        names = {tool.name for tool in tools}
        assert "assess_endurance_goal" in names

        result = await client.call_tool(
            "assess_endurance_goal",
            {
                "current_time_s": 3300,
                "target_time_s": 2100,
                "weeks": 12,
                "training_age": "beginner",
            },
        )
        assert not result.is_error
        assert result.structured_content["probability"] < 0.05
```

`tests/server/conftest.py` already provides the `anyio_backend` fixture for this
directory — no changes needed.

- [ ] **Step 3: Run it**

Run: `rtk proxy uv run pytest tests/server/test_stdio_e2e.py -v`
Expected: 1 passed (slower than the in-memory tests — it boots a subprocess).

- [ ] **Step 4: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 111 passed
git add pyproject.toml uv.lock tests/server/test_stdio_e2e.py
git commit -m "Add console entrypoint and stdio end-to-end test"
```

---

### Task 7: Install documentation

**Files:**
- Create: `docs/installing.md`
- Modify: `README.md`

- [ ] **Step 1: Verify current client-config syntax.** Before writing, check the
current official docs for the three CLIs (WebFetch or context7):
- Claude Code MCP config: https://docs.claude.com/en/docs/claude-code/mcp
- Gemini CLI MCP config: https://geminicli.com/docs (mcpServers in settings.json)
- Codex MCP config: https://developers.openai.com/codex (mcp_servers in config.toml)
If any snippet below doesn't match current syntax, fix it and report the correction.

- [ ] **Step 2: Create `docs/installing.md`**

```markdown
# Installing PerformanceAgent

PerformanceAgent runs as an MCP server inside your AI agent CLI. Until the first
PyPI release, install from a local clone:

```bash
git clone https://github.com/<org>/performance-agent
cd performance-agent && uv sync
```

## Claude Code

```bash
claude mcp add performance-agent -- uv --directory /path/to/performance-agent run performance-agent
```

Or in your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uv",
      "args": ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
    }
  }
}
```

## Gemini CLI

In `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uv",
      "args": ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
    }
  }
}
```

## Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.performance-agent]
command = "uv"
args = ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
```

## Verify

Ask your agent: *"List the performance-agent tools."* You should see nine engine
tools (assess_endurance_goal, predict_race_time, estimate_1rm, …).

Once published to PyPI (roadmap Plan 07), the `command`/`args` simplify to
`uvx` / `["performance-agent"]`.
```

- [ ] **Step 3: Update `README.md`** — in the Features section, change the line

`- 🔜 MCP server exposing the engine, evidence, memory, and report tools`

to

`- ✅ MCP server exposing the engine as 9 tools — see [docs/installing.md](docs/installing.md)`

and keep evidence/memory/report tools listed under 🔜 as their own line:

`- 🔜 Evidence, memory, and report MCP tools`

- [ ] **Step 4: Commit**

```bash
git add docs/installing.md README.md
git commit -m "Add MCP install docs for Claude Code, Gemini CLI, and Codex"
```

---

### Task 8: Final sweep

- [ ] **Step 1: Full quality gate**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # expect: 111 passed
prek run --all-files
actionlint .github/workflows/ci.yml && uvx zizmor .github/workflows/ci.yml
```

- [ ] **Step 2: Manual smoke via a real client** — from a DIFFERENT directory, run
`claude mcp add` per docs/installing.md against this clone, ask the agent to call
`assess_endurance_goal` with the canonical case, confirm it reports ~0.2%. Remove the
test registration afterwards (`claude mcp remove performance-agent`). If no `claude`
CLI is available in the execution environment, note it and rely on the stdio E2E test.

- [ ] **Step 3: Record as-built deviations in this plan file** (SDK import
adjustments, list_tools shape, any config-syntax corrections from Task 7 Step 1),
then commit:

```bash
git add docs/superpowers/plans/2026-07-10-plan-02-mcp-server.md
git commit -m "Record Plan 02 as-built deviations"
```

---

## Self-Review Notes

- **Spec coverage (v2 §10 item 2):** engine exposed as MCP tools ✓ (Tasks 2-4, all 13
  public engine functions reachable: feasibility, riegel+pace, both 1RM formulas via
  `formula` param, load prescription, sRPE, weekly, ACWR, waves — FeasibilityResult/
  TrainingAge/WeekLoad surface as dict/str shapes); packaging/entrypoint ✓ (Task 6);
  install docs for the three CLIs ✓ (Task 7); MCP client integration tests ✓ (in-memory
  Tasks 2-5, subprocess Task 6). Repo flattening (spec §8 note) ✓ (Task 1).
- **Deliberate scope cuts:** no memory/evidence/report tools (Plans 03/04/06); no PyPI
  publishing (Plan 07); no HTTP transport (stdio only — the CLIs spawn subprocesses).
- **Type consistency:** tool names and signatures identical across Tasks 2-6 test/impl
  blocks; `register` tuple grows monotonically; canonical feasibility numbers match
  Plan 01's verified values (0.3636 / 0.0303 / 0.010 / p<0.05; pace 2502s→250.2 s/km).
- **Known uncertainty, handled in-plan:** exact SDK shapes for `list_tools()` return
  and `StdioServerParameters` import location — both flagged with explicit
  adapt-and-report instructions rather than false certainty.

## As-Built Deviations

1. **SDK reality.** The installed stable dependency is `mcp==1.28.1` (the v1 API
   line), not the v2 line this plan's "SDK facts" section cites. Actual shapes used
   throughout the implementation: `FastMCP` from `mcp.server.fastmcp` (not
   `MCPServer` from `mcp.server`); in-process tool tests via
   `mcp.shared.memory.create_connected_server_and_client_session` (no `mcp.Client`);
   tool-call result attributes are camelCase (`isError`, `structuredContent`); the
   stdio E2E test uses `stdio_client(StdioServerParameters(...))` +
   `ClientSession` from `mcp.client.stdio` / `mcp` directly.

2. **Schema-typing pattern upgrade (from the Task 2 quality review).** The plan's
   Task 2-4 code blocks show tool signatures taking plain `str` params and returning
   `asdict(...)` dicts. The as-built code instead uses engine enums, dataclasses, and
   `Literal` types in tool signatures plus `TypedDict` return shapes (see
   `src/performance_agent/server/engine_tools.py`: `RacePrediction`, `Pace`,
   `OneRmEstimate`, `LoadPrescription`, `SessionLoad`, `WeeklyLoads`, `AcwrResult`,
   `PeriodizationWaves`, and `Literal["epley", "brzycki"]` on `estimate_1rm`). This
   makes enum values and named properties appear directly in the generated MCP tool
   schemas, which the plan's superseded shapes did not provide.

3. **Task 5 (error surfacing).** The test helper is a synchronous `error_text(result)`
   function (flagged by ruff as not needing `async`), not async as a naive port of the
   async test functions might suggest. The enum/`Literal`-typed params (formula,
   training_age) now surface invalid-value errors via Pydantic's pre-call validation
   rather than the engine raising `ValueError` — both paths produce readable
   tool-error text, so no behavior gap. `tests/server/test_errors.py` carries two more
   per-category cases and a tightened band assertion beyond what the plan's Task 5
   block specified (commit 1adc254, "Round out per-category error surfacing
   coverage").

4. **Task 6 (stdio E2E).** Hardened beyond the plan's sketch: the test pins
   `cwd=REPO_ROOT` when spawning the subprocess and wraps the exchange in
   `anyio.fail_after(30)` to bound the smoke test (commit 6818db6, "Harden stdio E2E:
   pinned cwd and bounded timeout"), plus an SIM117 `with` collapse and an explicit
   `structuredContent is not None` narrowing assert before indexing into it.

5. **Task 7 (install docs).** All three CLI config syntaxes (Claude Code, Gemini CLI,
   Codex) in `docs/installing.md` were verified against current official docs with
   zero corrections needed. The doc was subsequently polished with prerequisites,
   config-merge guidance, and a restart caveat (commit 08920a7, "Polish install docs:
   prerequisites and merge caveats").

6. **Task 1 (flatten).** The `.claude/` runtime directory is untracked (it appears
   nowhere in git history and holds no `.gitignore` entry of its own) and was
   correctly excluded from commit 2916f22 ("Flatten repo: move Python package from
   apps/api to root"), which only moved tracked `apps/api/*` paths to repo root.

7. **Suite size.** The plan's Task 8 quality-gate snippet expects "111 passed"; the
   as-built suite (after Tasks 5 and 6 added coverage beyond the plan) is 113 passed.
