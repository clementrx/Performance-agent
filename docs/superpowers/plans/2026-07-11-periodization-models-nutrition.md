# Periodization Models & Nutrition Engine (Premium Pipeline Phase 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the deterministic engine with block, undulating, in-season and strength-peaking periodization models plus a nutrition module (BMR/TDEE, energy targets with hard safety guards), exposed as 6 new MCP tools — then (Task 7) the remaining §4.2 progression schemes (top-set/back-off, wave loading) and RPE→RIR conversion as 3 more, for 9 new tools total.

**Architecture:** New pure functions in `engine/periodization.py` and a new stdlib-only `engine/nutrition.py`, TypedDict/dataclass-returning wrappers in `server/engine_tools.py`. Spec: docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md §4.3-4.4. Runs after phase 2a (2026-07-11-multi-goal-feasibility-prescription.md).

**Tech Stack:** Python 3.13, stdlib-only engine (AST purity test), Hypothesis property tests, FastMCP tool wrappers.

## Conventions

- Line length 100 characters everywhere.
- Before EVERY commit, run and get a clean result from all of:
  - `uv run ruff format . && uv run ruff check . && uv run ty check`
  - `uv run pytest -q` (the tests named in the task at minimum; full suite in the final task)
- Commit messages: imperative mood, no type prefix (match `git log`: "Enforce uniform per-exercise session formatting…").
- Every numeric constant carries a comment stating that it is a team-chosen prior or citing its corpus study id (e.g. `tapering-performance-meta-2007`).
- Engine files (`src/performance_agent/engine/*.py`) import nothing beyond the stdlib (`math`, `dataclasses`, `enum`, `typing`), engine siblings, and `performance_agent.engine._validation`. The architectural test `tests/engine/test_engine_purity.py` enforces this via `ENGINE_DIR.rglob("*.py")` — it AUTO-DISCOVERS engine modules, so the new `engine/nutrition.py` is covered with NO edit to the purity test; it must stay green after every task.
- **Dependency:** this plan assumes phase 2a (2026-07-11-multi-goal-feasibility-prescription.md) has fully landed: `server/engine_tools.py` exposes 15 engine tools and the docs say 32 tools total. Verify before starting: `git log --oneline -5` shows 2a's commits (ending with "Update documented tool count to 32") and `rg -n "32 tools" docs/installing.md README.md` hits both files. If not, STOP and execute 2a first.
- Tasks 1-5 test against the submodules directly (`performance_agent.engine.periodization`, `performance_agent.engine.nutrition`), matching `tests/engine/test_periodization.py`'s existing style; the public `performance_agent.engine` re-exports land in Task 6 where the server needs them.

## Existing code the tasks build on

- `src/performance_agent/engine/periodization.py` — module docstring "Weekly volume/intensity wave generation with deloads and taper.", `WeekLoad` (frozen dataclass), `build_weekly_waves`, imports `dataclass` and `validate_whole_number` only.
- `src/performance_agent/engine/_validation.py` — `validate_whole_number(name, value)` (rejects bool and non-int with "must be a whole number"), `validate_finite(name, value)` (rejects NaN/inf with "must be finite").
- `src/performance_agent/server/engine_tools.py` (post-2a) — TypedDict results (e.g. `PeriodizationWaves(TypedDict)` with `weeks: list[WeekLoad]`), dataclass-returning tools (e.g. `assess_endurance_goal` returns `FeasibilityResult` directly), `register(mcp)` loops `mcp.tool()(tool)` over 15 tools ending with `build_periodization_waves`.
- `tests/server/conftest.py` — provides the `client` fixture (in-memory FastMCP session); server tests are `@pytest.mark.anyio` and read `result.structuredContent` / `result.isError` / `result.content[0].text`.
- `tests/engine/test_properties.py` — Hypothesis `@given` with module-level strategies and `st.sampled_from`; `assume` already imported.
- `tests/engine/test_engine_purity.py` — allowlist `{"math", "dataclasses", "enum", "typing", "collections", "collections.abc"}` plus the `performance_agent.engine` prefix; auto-discovers every `engine/*.py`.

---

## Task 1 — block periodization in `engine/periodization.py`

Three sequential phases (accumulation → intensification → realization) with constant factors
per phase. Per-week ramps stay the job of `build_weekly_waves`; this model sets the phase
structure. Phase lengths: `round(total * 0.50)` accumulation, `round(total * 0.35)`
intensification, remainder realization, each floored at 1 week (deterministic repair: while
any phase < 1, move one week from the currently largest phase to the deficient one).

### Step 1 — write the failing tests

- [ ] In `tests/engine/test_periodization.py`, replace the import block at the top with:

```python
import pytest

from performance_agent.engine.periodization import (
    ACCUMULATION_INTENSITY,
    ACCUMULATION_VOLUME,
    INTENSIFICATION_INTENSITY,
    INTENSIFICATION_VOLUME,
    REALIZATION_INTENSITY,
    REALIZATION_VOLUME,
    BlockWeek,
    WeekLoad,
    build_block_periodization,
    build_weekly_waves,
)
```

- [ ] Append to `tests/engine/test_periodization.py`:

```python
def test_block_twelve_weeks_splits_six_four_two():
    # round(12*0.50)=6, round(12*0.35)=4, 12-10=2
    weeks = build_block_periodization(total_weeks=12)
    phases = [w.phase for w in weeks]
    assert phases == ["accumulation"] * 6 + ["intensification"] * 4 + ["realization"] * 2
    assert [w.week for w in weeks] == list(range(1, 13))


def test_block_factors_match_phase_constants():
    weeks = build_block_periodization(total_weeks=12)
    assert weeks[0].volume_factor == pytest.approx(ACCUMULATION_VOLUME)
    assert weeks[0].intensity_factor == pytest.approx(ACCUMULATION_INTENSITY)
    assert weeks[6].volume_factor == pytest.approx(INTENSIFICATION_VOLUME)
    assert weeks[6].intensity_factor == pytest.approx(INTENSIFICATION_INTENSITY)
    assert weeks[10].volume_factor == pytest.approx(REALIZATION_VOLUME)
    assert weeks[10].intensity_factor == pytest.approx(REALIZATION_INTENSITY)


def test_block_six_weeks_keeps_one_week_per_phase():
    weeks = build_block_periodization(total_weeks=6)
    phases = [w.phase for w in weeks]
    assert phases == ["accumulation"] * 3 + ["intensification"] * 2 + ["realization"]


def test_block_rejects_fewer_than_six_weeks():
    with pytest.raises(ValueError, match="degenerate"):
        build_block_periodization(total_weeks=5)


@pytest.mark.parametrize("total_weeks", [12.0, True])
def test_block_rejects_non_whole_weeks(total_weeks):
    with pytest.raises(ValueError, match="whole number"):
        build_block_periodization(total_weeks=total_weeks)


def test_block_weeks_are_frozen_value_objects():
    week = BlockWeek(week=1, phase="accumulation", volume_factor=1.10, intensity_factor=0.85)
    with pytest.raises(AttributeError):
        week.volume_factor = 2.0  # ty: ignore[invalid-assignment]
```

- [ ] Append to `tests/engine/test_properties.py`, adding a submodule import line after the existing `from performance_agent.engine import (...)` block:

```python
from performance_agent.engine.periodization import build_block_periodization
```

```python
@given(total_weeks=st.integers(min_value=6, max_value=52))
def test_block_periodization_covers_every_week_with_all_three_phases(total_weeks):
    weeks = build_block_periodization(total_weeks)
    assert [w.week for w in weeks] == list(range(1, total_weeks + 1))
    for phase in ("accumulation", "intensification", "realization"):
        assert sum(1 for w in weeks if w.phase == phase) >= 1
```

(Week-number contiguity over 1..total also proves the phase counts sum to `total_weeks`.)

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'ACCUMULATION_INTENSITY' from 'performance_agent.engine.periodization'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/periodization.py`, replace the module docstring with:

```python
"""Periodization models: weekly waves, block, undulating, in-season and peaking.

Factors are multipliers against a baseline week (1.0 = baseline volume or
intensity). The Periodization agent later maps these onto concrete sessions.
"""
```

- [ ] Extend the imports (the file currently imports only `dataclass` and `validate_whole_number`):

```python
from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_whole_number
```

- [ ] Add after the existing `TAPER_INTENSITY` constant:

```python
BlockPhase = Literal["accumulation", "intensification", "realization"]

# Phase split of a block-periodized cycle (fractions of total weeks).
# Team-chosen priors following classic block schemes (~50/35/15).
BLOCK_PHASE_FRACTIONS: tuple[tuple[BlockPhase, float], ...] = (
    ("accumulation", 0.50),
    ("intensification", 0.35),
    ("realization", 0.15),
)
# Per-phase load multipliers vs baseline. Team-chosen priors: accumulation is
# high-volume/moderate-intensity, intensification inverts that, realization
# sheds volume while intensity peaks.
ACCUMULATION_VOLUME = 1.10
ACCUMULATION_INTENSITY = 0.85
INTENSIFICATION_VOLUME = 0.90
INTENSIFICATION_INTENSITY = 1.05
REALIZATION_VOLUME = 0.55
REALIZATION_INTENSITY = 1.10
# Below 6 weeks the three phases degenerate (a phase would need < 1 full
# week). Team-chosen floor.
MIN_BLOCK_WEEKS = 6

_BLOCK_PHASE_FACTORS: dict[BlockPhase, tuple[float, float]] = {
    "accumulation": (ACCUMULATION_VOLUME, ACCUMULATION_INTENSITY),
    "intensification": (INTENSIFICATION_VOLUME, INTENSIFICATION_INTENSITY),
    "realization": (REALIZATION_VOLUME, REALIZATION_INTENSITY),
}
```

- [ ] Add after `build_weekly_waves`:

```python
@dataclass(frozen=True)
class BlockWeek:
    """One week of a block-periodized cycle (week is 1-indexed)."""

    week: int
    phase: BlockPhase
    volume_factor: float
    intensity_factor: float


def build_block_periodization(total_weeks: int) -> list[BlockWeek]:
    """Split a cycle into accumulation, intensification and realization blocks.

    Phase lengths are round(total * fraction) for accumulation (0.50) and
    intensification (0.35), with realization taking the remainder; every
    phase keeps at least one week (deterministic repair: while any phase is
    below one week, one week moves from the currently largest phase to the
    deficient one). Factors are constant within a phase — per-week ramps
    stay the job of build_weekly_waves; this model sets the phase structure.
    """
    validate_whole_number("total_weeks", total_weeks)
    if total_weeks < MIN_BLOCK_WEEKS:
        msg = (
            f"total_weeks must be >= {MIN_BLOCK_WEEKS}, got {total_weeks!r}: below "
            f"{MIN_BLOCK_WEEKS} weeks the three phases degenerate — use "
            "build_weekly_waves instead"
        )
        raise ValueError(msg)
    counts: dict[BlockPhase, int] = {
        "accumulation": round(total_weeks * BLOCK_PHASE_FRACTIONS[0][1]),
        "intensification": round(total_weeks * BLOCK_PHASE_FRACTIONS[1][1]),
    }
    counts["realization"] = total_weeks - counts["accumulation"] - counts["intensification"]
    while any(count < 1 for count in counts.values()):
        deficient = min(counts, key=lambda phase: counts[phase])
        largest = max(counts, key=lambda phase: counts[phase])
        counts[largest] -= 1
        counts[deficient] += 1
    weeks: list[BlockWeek] = []
    week = 1
    for phase, _fraction in BLOCK_PHASE_FRACTIONS:
        volume, intensity = _BLOCK_PHASE_FACTORS[phase]
        for _ in range(counts[phase]):
            weeks.append(BlockWeek(week, phase, volume, intensity))
            week += 1
    return weeks
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q` — all pass, including every pre-existing wave test.

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/periodization.py tests/engine/test_periodization.py tests/engine/test_properties.py && git commit -m "Add block periodization model to the engine"`

---

## Task 2 — daily undulating week in `engine/periodization.py`

Sessions cycle heavy → light → moderate. The heavy-then-light adjacency is deliberate: the
light day buys recovery after the heaviest stimulus before quality moderate work.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_periodization.py` (extend the periodization import block with `build_undulating_week` — keep it sorted; `UndulatingSession` is exercised via the returned objects):

```python
def test_undulating_three_sessions_heavy_light_moderate():
    sessions = build_undulating_week(sessions_per_week=3)
    assert [s.session for s in sessions] == [1, 2, 3]
    assert [s.emphasis for s in sessions] == ["heavy", "light", "moderate"]
    assert sessions[0].intensity_low == pytest.approx(0.85)
    assert sessions[0].intensity_high == pytest.approx(0.925)
    assert sessions[1].intensity_low == pytest.approx(0.60)
    assert sessions[1].intensity_high == pytest.approx(0.70)
    assert sessions[2].intensity_low == pytest.approx(0.725)
    assert sessions[2].intensity_high == pytest.approx(0.80)


def test_undulating_five_sessions_wrap_the_cycle():
    sessions = build_undulating_week(sessions_per_week=5)
    assert [s.emphasis for s in sessions] == ["heavy", "light", "moderate", "heavy", "light"]


@pytest.mark.parametrize("sessions_per_week", [1, 8])
def test_undulating_rejects_out_of_range_sessions(sessions_per_week):
    with pytest.raises(ValueError, match="cannot undulate"):
        build_undulating_week(sessions_per_week=sessions_per_week)


def test_undulating_rejects_non_whole_sessions():
    with pytest.raises(ValueError, match="whole number"):
        build_undulating_week(sessions_per_week=3.0)
```

- [ ] Append to `tests/engine/test_properties.py` (extend the periodization submodule import with `build_undulating_week`):

```python
@given(sessions_per_week=st.integers(min_value=2, max_value=7))
def test_undulating_sessions_are_contiguous_with_sane_zones(sessions_per_week):
    sessions = build_undulating_week(sessions_per_week)
    assert [s.session for s in sessions] == list(range(1, sessions_per_week + 1))
    for session in sessions:
        assert 0 < session.intensity_low < session.intensity_high < 1
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'build_undulating_week'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/periodization.py`, add after `_BLOCK_PHASE_FACTORS`:

```python
SessionEmphasis = Literal["heavy", "moderate", "light"]

# Daily-undulating intensity zones as fractions of 1RM (low, high) with the
# rep quality they serve. Team-chosen priors consistent with common DUP schemes.
UNDULATION_ZONES: dict[SessionEmphasis, tuple[float, float]] = {
    "heavy": (0.85, 0.925),
    "moderate": (0.725, 0.80),
    "light": (0.60, 0.70),
}
# Heavy-then-light adjacency is deliberate: the light day buys recovery
# after the heaviest stimulus before quality moderate work.
_UNDULATION_ORDER: tuple[SessionEmphasis, ...] = ("heavy", "light", "moderate")
# A single weekly session cannot undulate; beyond daily training the cycle
# stops meaning anything. Team-chosen bounds.
MIN_UNDULATING_SESSIONS = 2
MAX_UNDULATING_SESSIONS = 7
```

- [ ] Add after `build_block_periodization`:

```python
@dataclass(frozen=True)
class UndulatingSession:
    """One session slot in a daily-undulating training week."""

    session: int
    emphasis: SessionEmphasis
    intensity_low: float
    intensity_high: float


def build_undulating_week(sessions_per_week: int) -> list[UndulatingSession]:
    """Assign daily-undulating emphases to a week's strength sessions.

    Sessions cycle heavy -> light -> moderate (heavy-then-light adjacency is
    deliberate recovery spacing). Zone bounds are fractions of 1RM from
    UNDULATION_ZONES.
    """
    validate_whole_number("sessions_per_week", sessions_per_week)
    if not MIN_UNDULATING_SESSIONS <= sessions_per_week <= MAX_UNDULATING_SESSIONS:
        msg = (
            f"sessions_per_week must be between {MIN_UNDULATING_SESSIONS} and "
            f"{MAX_UNDULATING_SESSIONS}, got {sessions_per_week!r}: a single weekly "
            "session cannot undulate, and beyond daily training the cycle is meaningless"
        )
        raise ValueError(msg)
    sessions: list[UndulatingSession] = []
    for index in range(sessions_per_week):
        emphasis = _UNDULATION_ORDER[index % len(_UNDULATION_ORDER)]
        low, high = UNDULATION_ZONES[emphasis]
        sessions.append(UndulatingSession(index + 1, emphasis, low, high))
    return sessions
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/periodization.py tests/engine/test_periodization.py tests/engine/test_properties.py && git commit -m "Add daily undulating week model"`

---

## Task 3 — in-season maintenance week in `engine/periodization.py`

Minimum effective dose around fixtures: volume drops with match count, intensity stays high
(intensity, not volume, retains strength). Zero matches and 3+ matches are both refused —
with coaching guidance in the error, since the tool relays it verbatim.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_periodization.py` (extend the periodization import block with `InseasonWeek, build_inseason_week`):

```python
def test_inseason_one_match_week():
    week = build_inseason_week(matches_this_week=1)
    assert week == InseasonWeek(
        matches=1, strength_sessions=2, volume_factor=0.50, min_intensity_factor=0.80
    )


def test_inseason_two_match_week():
    week = build_inseason_week(matches_this_week=2)
    assert week.strength_sessions == 1
    assert week.volume_factor == pytest.approx(0.30)
    assert week.min_intensity_factor == pytest.approx(0.80)


def test_inseason_zero_matches_points_to_a_building_week():
    with pytest.raises(ValueError, match="normal building week"):
        build_inseason_week(matches_this_week=0)


def test_inseason_three_matches_prescribes_rest():
    with pytest.raises(ValueError, match="rest is the prescription"):
        build_inseason_week(matches_this_week=3)


def test_inseason_rejects_negative_matches():
    with pytest.raises(ValueError, match="non-negative"):
        build_inseason_week(matches_this_week=-1)


def test_inseason_rejects_non_whole_matches():
    with pytest.raises(ValueError, match="whole number"):
        build_inseason_week(matches_this_week=1.0)
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_periodization.py -q`
- Expected failure: `ImportError: cannot import name 'InseasonWeek'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/periodization.py`, add after `MAX_UNDULATING_SESSIONS`:

```python
# In-season maintenance: minimum effective dose around fixtures. Volume
# fractions are of the athlete's off-season baseline; intensity is held high
# because intensity, not volume, retains strength. Team-chosen priors.
INSEASON_VOLUME_ONE_MATCH = 0.50
INSEASON_VOLUME_TWO_MATCHES = 0.30
INSEASON_MIN_INTENSITY = 0.80
INSEASON_SESSIONS_ONE_MATCH = 2
INSEASON_SESSIONS_TWO_MATCHES = 1
```

- [ ] Add after `build_undulating_week`:

```python
@dataclass(frozen=True)
class InseasonWeek:
    """Strength maintenance prescription for one in-season week."""

    matches: int
    strength_sessions: int
    volume_factor: float
    min_intensity_factor: float


def build_inseason_week(matches_this_week: int) -> InseasonWeek:
    """Prescribe strength maintenance around this week's fixtures (1 or 2).

    Volume is a fraction of the off-season baseline; min_intensity_factor is
    the floor to hold (intensity, not volume, retains strength). Zero matches
    and congested (3+) weeks are refused with coaching guidance in the error.
    """
    validate_whole_number("matches_this_week", matches_this_week)
    if matches_this_week < 0:
        msg = f"matches_this_week must be non-negative, got {matches_this_week!r}"
        raise ValueError(msg)
    if matches_this_week == 0:
        msg = "no fixture this week: use a normal building week, not the in-season model"
        raise ValueError(msg)
    if matches_this_week > 2:
        msg = (
            f"got {matches_this_week!r} matches: more than 2 fixtures leaves no recovery "
            "window for strength work — rest is the prescription"
        )
        raise ValueError(msg)
    if matches_this_week == 1:
        return InseasonWeek(
            matches=1,
            strength_sessions=INSEASON_SESSIONS_ONE_MATCH,
            volume_factor=INSEASON_VOLUME_ONE_MATCH,
            min_intensity_factor=INSEASON_MIN_INTENSITY,
        )
    return InseasonWeek(
        matches=2,
        strength_sessions=INSEASON_SESSIONS_TWO_MATCHES,
        volume_factor=INSEASON_VOLUME_TWO_MATCHES,
        min_intensity_factor=INSEASON_MIN_INTENSITY,
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/periodization.py tests/engine/test_periodization.py && git commit -m "Add in-season maintenance week model"`

---

## Task 4 — strength peaking in `engine/periodization.py`

Fixed 1-3 week taper schedules toward a 1RM test: volume drops hard while intensity climbs
to near-max. `intensity_factor > 1.0` on the final week of the 2- and 3-week schedules
represents openers/heavy singles above training loads, not a projected new max.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_periodization.py` (extend the periodization import block with `PeakingWeek, build_strength_peaking`):

```python
def test_peaking_one_week_schedule():
    weeks = build_strength_peaking(weeks=1)
    assert weeks == [
        PeakingWeek(week=1, volume_factor=0.40, intensity_factor=1.00, is_test_week=True)
    ]


def test_peaking_two_week_schedule():
    weeks = build_strength_peaking(weeks=2)
    assert [(w.volume_factor, w.intensity_factor) for w in weeks] == [
        (0.55, 0.95),
        (0.35, 1.025),
    ]
    assert [w.is_test_week for w in weeks] == [False, True]


def test_peaking_three_week_schedule():
    weeks = build_strength_peaking(weeks=3)
    assert [(w.volume_factor, w.intensity_factor) for w in weeks] == [
        (0.65, 0.925),
        (0.50, 0.975),
        (0.35, 1.025),
    ]
    assert [w.week for w in weeks] == [1, 2, 3]
    assert [w.is_test_week for w in weeks] == [False, False, True]


@pytest.mark.parametrize("weeks", [0, 4])
def test_peaking_rejects_out_of_range_lengths(weeks):
    with pytest.raises(ValueError, match="detrain"):
        build_strength_peaking(weeks=weeks)


def test_peaking_rejects_non_whole_weeks():
    with pytest.raises(ValueError, match="whole number"):
        build_strength_peaking(weeks=2.0)
```

- [ ] Append to `tests/engine/test_properties.py` (extend the periodization submodule import with `build_strength_peaking`):

```python
@given(weeks=st.integers(min_value=1, max_value=3))
def test_peaking_volume_falls_while_intensity_climbs(weeks):
    taper = build_strength_peaking(weeks)
    volumes = [w.volume_factor for w in taper]
    intensities = [w.intensity_factor for w in taper]
    # For weeks=1 the pair lists are empty and both hold trivially.
    assert all(a > b for a, b in zip(volumes, volumes[1:], strict=False))
    assert all(a < b for a, b in zip(intensities, intensities[1:], strict=False))
    assert taper[-1].is_test_week
    assert not any(w.is_test_week for w in taper[:-1])
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'PeakingWeek'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/periodization.py`, add after `INSEASON_SESSIONS_TWO_MATCHES`:

```python
# Peaking toward a 1RM test: volume drops hard while intensity climbs to
# near-max, with the final days as full rest/openers. Team-chosen priors
# consistent with powerlifting taper practice and the tapering meta-analysis
# in the corpus (tapering-performance-meta-2007: ~2-week tapers with 41-60%
# volume reduction perform best).
PEAKING_MAX_WEEKS = 3
PEAKING_SCHEDULE: dict[int, tuple[tuple[float, float], ...]] = {
    1: ((0.40, 1.00),),
    2: ((0.55, 0.95), (0.35, 1.025)),
    3: ((0.65, 0.925), (0.50, 0.975), (0.35, 1.025)),
}
```

- [ ] Add after `build_inseason_week`:

```python
@dataclass(frozen=True)
class PeakingWeek:
    """One week of a 1RM peaking taper (week is 1-indexed, last week = test week)."""

    week: int
    volume_factor: float
    intensity_factor: float
    is_test_week: bool


def build_strength_peaking(weeks: int) -> list[PeakingWeek]:
    """Taper the final 1-3 weeks before a 1RM test.

    Uses the fixed PEAKING_SCHEDULE (volume, intensity) pairs; the last
    emitted week is the test week. intensity_factor above 1.0 on the final
    week of the 2- and 3-week schedules represents openers/heavy singles
    above training loads, not a projected new max.
    """
    validate_whole_number("weeks", weeks)
    if not 1 <= weeks <= PEAKING_MAX_WEEKS:
        msg = (
            f"weeks must be between 1 and {PEAKING_MAX_WEEKS}, got {weeks!r}: peaking "
            f"blocks longer than {PEAKING_MAX_WEEKS} weeks detrain; schedule a block "
            "cycle first"
        )
        raise ValueError(msg)
    return [
        PeakingWeek(index + 1, volume, intensity, is_test_week=index + 1 == weeks)
        for index, (volume, intensity) in enumerate(PEAKING_SCHEDULE[weeks])
    ]
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_periodization.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/periodization.py tests/engine/test_periodization.py tests/engine/test_properties.py && git commit -m "Add strength peaking taper model"`

---

## Task 5 — new `engine/nutrition.py`

BMR (Mifflin-St Jeor), TDEE, and energy targets whose safety guards live in code, not in
prompts: no agent can prescribe below the caloric floor, above the safe loss rate, or a
deficit to an underweight athlete. New test file `tests/engine/test_nutrition.py`. The
purity test auto-discovers the new module — no purity-test edit needed; its imports
(`dataclasses`, `typing`, `performance_agent.engine._validation`) are all allowlisted.

### Step 1 — write the failing tests

- [ ] Create `tests/engine/test_nutrition.py` in full:

```python
import pytest

from performance_agent.engine.nutrition import (
    EnergyTarget,
    bmr_mifflin_st_jeor,
    prescribe_energy_target,
    tdee_from_bmr,
)


def test_bmr_male_known_value():
    # 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert bmr_mifflin_st_jeor("male", 80.0, 180.0, 30) == pytest.approx(1780.0)


def test_bmr_female_known_value():
    # 10*80 + 6.25*180 - 5*30 - 161 = 1614
    assert bmr_mifflin_st_jeor("female", 80.0, 180.0, 30) == pytest.approx(1614.0)


def test_bmr_rejects_unknown_sex():
    with pytest.raises(ValueError, match="sex"):
        bmr_mifflin_st_jeor("other", 80.0, 180.0, 30)


@pytest.mark.parametrize(
    ("weight", "height"),
    [(30.0, 180.0), (250.0, 180.0), (80.0, 100.0), (80.0, 250.0)],
)
def test_bmr_rejects_out_of_range_body_measures(weight, height):
    with pytest.raises(ValueError, match="weight_kg|height_cm"):
        bmr_mifflin_st_jeor("male", weight, height, 30)


def test_bmr_refuses_youth():
    with pytest.raises(ValueError, match="paediatric"):
        bmr_mifflin_st_jeor("male", 60.0, 170.0, 14)


def test_bmr_rejects_age_ninety_and_up():
    with pytest.raises(ValueError, match="age_years"):
        bmr_mifflin_st_jeor("male", 80.0, 180.0, 90)


def test_bmr_rejects_non_whole_age():
    with pytest.raises(ValueError, match="whole number"):
        bmr_mifflin_st_jeor("male", 80.0, 180.0, 30.5)


def test_tdee_known_value():
    assert tdee_from_bmr(1780.0, 1.55) == pytest.approx(2759.0)


@pytest.mark.parametrize("factor", [1.19, 2.41, 0.0, -1.5])
def test_tdee_rejects_out_of_band_activity_factor(factor):
    with pytest.raises(ValueError, match="activity_factor"):
        tdee_from_bmr(1780.0, factor)


@pytest.mark.parametrize("bmr", [0.0, -100.0, float("nan"), float("inf")])
def test_tdee_rejects_bad_bmr(bmr):
    with pytest.raises(ValueError, match="bmr_kcal|finite"):
        tdee_from_bmr(bmr, 1.55)


def test_cut_prescription_exact_values():
    # TDEE 2600, 0.75%/wk on 80 kg -> 0.6 kg/wk -> 0.6*7700/7 = 660 kcal/day deficit
    target = prescribe_energy_target(
        tdee_kcal=2600.0,
        goal="cut",
        weekly_change_pct_bw=0.0075,
        weight_kg=80.0,
        height_cm=180.0,
        sex="male",
    )
    assert isinstance(target, EnergyTarget)
    assert target.goal == "cut"
    assert target.daily_kcal == pytest.approx(1940.0)
    assert target.protein_g_per_day == pytest.approx(176.0)
    assert target.weekly_weight_change_kg == pytest.approx(-0.6)
    assert target.clamped_to_floor is False


def test_cut_clamps_to_caloric_floor():
    # TDEE 1700, 1%/wk on 55 kg -> 605 kcal/day deficit -> raw 1095 < 1200 floor
    target = prescribe_energy_target(
        tdee_kcal=1700.0,
        goal="cut",
        weekly_change_pct_bw=0.010,
        weight_kg=55.0,
        height_cm=165.0,
        sex="female",
    )
    assert target.daily_kcal == pytest.approx(1200.0)
    assert target.clamped_to_floor is True
    assert target.weekly_weight_change_kg == pytest.approx(-0.55)
    assert target.protein_g_per_day == pytest.approx(121.0)


def test_cut_refused_for_underweight_athlete():
    # 50 kg at 175 cm -> BMI 16.3, below the 18.5 healthy minimum
    with pytest.raises(ValueError, match="below the healthy minimum"):
        prescribe_energy_target(
            tdee_kcal=2200.0,
            goal="cut",
            weekly_change_pct_bw=0.005,
            weight_kg=50.0,
            height_cm=175.0,
            sex="male",
        )


def test_cut_rate_above_one_percent_rejected():
    with pytest.raises(ValueError, match="lean-mass"):
        prescribe_energy_target(
            tdee_kcal=2600.0,
            goal="cut",
            weekly_change_pct_bw=0.011,
            weight_kg=80.0,
            height_cm=180.0,
            sex="male",
        )


def test_maintain_requires_zero_rate():
    with pytest.raises(ValueError, match="must be 0 for maintain"):
        prescribe_energy_target(
            tdee_kcal=2500.0,
            goal="maintain",
            weekly_change_pct_bw=0.001,
            weight_kg=75.0,
            height_cm=178.0,
            sex="male",
        )


def test_maintain_prescription():
    target = prescribe_energy_target(
        tdee_kcal=2500.0,
        goal="maintain",
        weekly_change_pct_bw=0.0,
        weight_kg=75.0,
        height_cm=178.0,
        sex="male",
    )
    assert target.daily_kcal == pytest.approx(2500.0)
    assert target.protein_g_per_day == pytest.approx(120.0)
    assert target.weekly_weight_change_kg == 0.0
    assert target.clamped_to_floor is False


def test_gain_prescription_exact_values():
    # 0.4%/wk on 75 kg -> +0.3 kg/wk -> +330 kcal/day surplus
    target = prescribe_energy_target(
        tdee_kcal=2800.0,
        goal="gain",
        weekly_change_pct_bw=0.004,
        weight_kg=75.0,
        height_cm=178.0,
        sex="male",
    )
    assert target.daily_kcal == pytest.approx(3130.0)
    assert target.protein_g_per_day == pytest.approx(135.0)
    assert target.weekly_weight_change_kg == pytest.approx(0.3)
    assert target.clamped_to_floor is False


def test_gain_rate_above_half_percent_rejected():
    with pytest.raises(ValueError, match=r"0\.5%"):
        prescribe_energy_target(
            tdee_kcal=2800.0,
            goal="gain",
            weekly_change_pct_bw=0.006,
            weight_kg=75.0,
            height_cm=178.0,
            sex="male",
        )
```

- [ ] Append to `tests/engine/test_properties.py`, adding the submodule import line (after the periodization one):

```python
from performance_agent.engine.nutrition import CALORIC_FLOOR_KCAL, prescribe_energy_target
```

```python
@given(
    tdee=st.floats(min_value=1300, max_value=5000, allow_nan=False),
    rate=st.floats(min_value=0.001, max_value=0.010, allow_nan=False),
    weight=st.floats(min_value=45, max_value=150, allow_nan=False),
    height=st.floats(min_value=140, max_value=210, allow_nan=False),
    sex=st.sampled_from(["male", "female"]),
)
def test_cut_prescription_never_goes_below_the_floor(tdee, rate, weight, height, sex):
    assume(weight / (height / 100) ** 2 >= 18.5)
    target = prescribe_energy_target(tdee, "cut", rate, weight, height, sex)
    assert target.daily_kcal >= CALORIC_FLOOR_KCAL[sex]
    assert target.protein_g_per_day > 0
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_nutrition.py tests/engine/test_properties.py -q`
- Expected failure: `ModuleNotFoundError: No module named 'performance_agent.engine.nutrition'` (collection error).

### Step 3 — implement

- [ ] Create `src/performance_agent/engine/nutrition.py` in full:

```python
"""Energy and protein targets with hard safety guards.

The guards live HERE, not in prompts: no agent can prescribe below the
caloric floor, above the safe loss rate, or to an underweight athlete.
Numbers are team-chosen priors from mainstream sports-nutrition consensus;
they parameterize honesty, not medical advice — the tools refuse and refer
out when a request crosses a red line.
"""

from dataclasses import dataclass
from typing import Literal

from performance_agent.engine._validation import validate_finite, validate_whole_number

Sex = Literal["male", "female"]
GoalDirection = Literal["cut", "maintain", "gain"]

# Mifflin-St Jeor sex offsets (kcal/day) — published constants of the source
# equation, not tunable priors.
MALE_BMR_OFFSET = 5.0
FEMALE_BMR_OFFSET = -161.0
# Activity-factor band: 1.2 (sedentary) to 2.4 (extreme training loads).
# Team-chosen bounds on the standard multiplier tables.
MIN_ACTIVITY_FACTOR = 1.2
MAX_ACTIVITY_FACTOR = 2.4
# Absolute daily floors (kcal) below which we refuse to prescribe.
# Team-chosen priors matching mainstream dietetic guidance.
CALORIC_FLOOR_KCAL = {"male": 1500.0, "female": 1200.0}
# Safe weekly bodyweight-change caps as fractions of bodyweight. Team-chosen
# priors: up to 1%/week loss preserves lean mass; above 0.5%/week gain
# mostly adds fat.
MAX_WEEKLY_LOSS_PCT_BW = 0.010
MAX_WEEKLY_GAIN_PCT_BW = 0.005
# Protein targets (g per kg bodyweight per day) by goal direction.
# Team-chosen priors from sports-nutrition consensus ranges.
PROTEIN_G_PER_KG = {"cut": 2.2, "maintain": 1.6, "gain": 1.8}
# Energy density of a kilogram of bodyweight change — the classic 7700
# kcal/kg approximation (team-chosen prior).
KCAL_PER_KG_TISSUE = 7700.0
# WHO underweight threshold; below it we refuse to prescribe a deficit.
MIN_HEALTHY_BMI = 18.5

# Plausible adult athlete measurement bands (exclusive). Team-chosen priors;
# outside them the equations are extrapolating.
_WEIGHT_RANGE_KG = (30.0, 250.0)
_HEIGHT_RANGE_CM = (100.0, 250.0)
_AGE_RANGE_YEARS = (14, 90)


def _validate_sex(sex: str) -> None:
    if sex not in ("male", "female"):
        msg = f'sex must be "male" or "female", got {sex!r}'
        raise ValueError(msg)


def _validate_open_range(name: str, value: float, bounds: tuple[float, float]) -> None:
    validate_finite(name, value)
    low, high = bounds
    if not low < value < high:
        msg = f"{name} must be between {low} and {high} (exclusive), got {value!r}"
        raise ValueError(msg)


def _validate_age(age_years: int) -> None:
    validate_whole_number("age_years", age_years)
    low, high = _AGE_RANGE_YEARS
    if age_years <= low:
        msg = (
            f"age_years must be over {low}, got {age_years!r}: youth nutrition is "
            "out of scope; refer to a paediatric professional"
        )
        raise ValueError(msg)
    if age_years >= high:
        msg = f"age_years must be under {high}, got {age_years!r}"
        raise ValueError(msg)


def bmr_mifflin_st_jeor(sex: Sex, weight_kg: float, height_cm: float, age_years: int) -> float:
    """Basal metabolic rate in kcal/day (Mifflin-St Jeor).

    10*weight_kg + 6.25*height_cm - 5*age_years + offset(sex). weight_kg in
    (30, 250), height_cm in (100, 250), age_years a whole number in
    (14, 90) — under-15s are refused (youth nutrition is out of scope).
    """
    _validate_sex(sex)
    _validate_open_range("weight_kg", weight_kg, _WEIGHT_RANGE_KG)
    _validate_open_range("height_cm", height_cm, _HEIGHT_RANGE_CM)
    _validate_age(age_years)
    offset = MALE_BMR_OFFSET if sex == "male" else FEMALE_BMR_OFFSET
    return 10 * weight_kg + 6.25 * height_cm - 5 * age_years + offset


def tdee_from_bmr(bmr_kcal: float, activity_factor: float) -> float:
    """Total daily energy expenditure: BMR scaled by an activity factor.

    bmr_kcal must be positive and finite; activity_factor must be in
    [1.2, 2.4] (sedentary to extreme training loads).
    """
    validate_finite("bmr_kcal", bmr_kcal)
    validate_finite("activity_factor", activity_factor)
    if bmr_kcal <= 0:
        msg = f"bmr_kcal must be positive, got {bmr_kcal!r}"
        raise ValueError(msg)
    if not MIN_ACTIVITY_FACTOR <= activity_factor <= MAX_ACTIVITY_FACTOR:
        msg = (
            f"activity_factor must be in [{MIN_ACTIVITY_FACTOR}, {MAX_ACTIVITY_FACTOR}], "
            f"got {activity_factor!r}"
        )
        raise ValueError(msg)
    return bmr_kcal * activity_factor


@dataclass(frozen=True)
class EnergyTarget:
    """Daily energy & protein prescription with its guard status."""

    goal: GoalDirection
    daily_kcal: float
    protein_g_per_day: float
    weekly_weight_change_kg: float
    clamped_to_floor: bool


def _validate_target_inputs(
    tdee_kcal: float, goal: str, weight_kg: float, height_cm: float, sex: str
) -> None:
    _validate_sex(sex)
    if goal not in PROTEIN_G_PER_KG:
        msg = f'goal must be "cut", "maintain" or "gain", got {goal!r}'
        raise ValueError(msg)
    validate_finite("tdee_kcal", tdee_kcal)
    if tdee_kcal <= 0:
        msg = f"tdee_kcal must be positive, got {tdee_kcal!r}"
        raise ValueError(msg)
    _validate_open_range("weight_kg", weight_kg, _WEIGHT_RANGE_KG)
    _validate_open_range("height_cm", height_cm, _HEIGHT_RANGE_CM)


def _validate_rate(goal: GoalDirection, weekly_change_pct_bw: float) -> None:
    validate_finite("weekly_change_pct_bw", weekly_change_pct_bw)
    if goal == "maintain" and weekly_change_pct_bw != 0:
        msg = f"weekly_change_pct_bw must be 0 for maintain, got {weekly_change_pct_bw!r}"
        raise ValueError(msg)
    if goal == "cut" and not 0 < weekly_change_pct_bw <= MAX_WEEKLY_LOSS_PCT_BW:
        msg = (
            f"weekly_change_pct_bw for a cut must be in (0, {MAX_WEEKLY_LOSS_PCT_BW}] — "
            f"1%/week is the lean-mass-preserving cap, got {weekly_change_pct_bw!r}"
        )
        raise ValueError(msg)
    if goal == "gain" and not 0 < weekly_change_pct_bw <= MAX_WEEKLY_GAIN_PCT_BW:
        msg = (
            f"weekly_change_pct_bw for a gain must be in (0, {MAX_WEEKLY_GAIN_PCT_BW}] — "
            f"0.5%/week for gains — faster mostly adds fat, got {weekly_change_pct_bw!r}"
        )
        raise ValueError(msg)


def prescribe_energy_target(
    tdee_kcal: float,
    goal: GoalDirection,
    weekly_change_pct_bw: float,
    weight_kg: float,
    height_cm: float,
    sex: Sex,
) -> EnergyTarget:
    """Prescribe daily energy and protein for a cut, maintain or gain goal.

    weekly_change_pct_bw is the weekly bodyweight change as a fraction of
    bodyweight: 0 for maintain, in (0, 0.010] for a cut, in (0, 0.005] for a
    gain. Hard guards, in order: an underweight athlete (BMI < 18.5) is
    refused a deficit outright; the rate caps are enforced; and a cut whose
    daily kcal would land below the sex-specific caloric floor is clamped to
    the floor with clamped_to_floor=True — the coach must then extend the
    deadline instead of deepening the deficit. weekly_weight_change_kg is
    negative for a cut, zero for maintain, positive for a gain.
    """
    _validate_target_inputs(tdee_kcal, goal, weight_kg, height_cm, sex)
    bmi = weight_kg / (height_cm / 100) ** 2
    if bmi < MIN_HEALTHY_BMI and goal == "cut":
        msg = (
            f"BMI {bmi:.1f} is below the healthy minimum ({MIN_HEALTHY_BMI}): refusing "
            "to prescribe a deficit — refer to a health professional"
        )
        raise ValueError(msg)
    _validate_rate(goal, weekly_change_pct_bw)
    weekly_change_kg = weekly_change_pct_bw * weight_kg
    daily_adjustment_kcal = weekly_change_kg * KCAL_PER_KG_TISSUE / 7
    clamped = False
    if goal == "cut":
        daily_kcal = tdee_kcal - daily_adjustment_kcal
        weekly_weight_change_kg = -weekly_change_kg
        if daily_kcal < CALORIC_FLOOR_KCAL[sex]:
            daily_kcal = CALORIC_FLOOR_KCAL[sex]
            clamped = True
    elif goal == "gain":
        daily_kcal = tdee_kcal + daily_adjustment_kcal
        weekly_weight_change_kg = weekly_change_kg
    else:
        daily_kcal = tdee_kcal
        weekly_weight_change_kg = 0.0
    return EnergyTarget(
        goal=goal,
        daily_kcal=daily_kcal,
        protein_g_per_day=PROTEIN_G_PER_KG[goal] * weight_kg,
        weekly_weight_change_kg=weekly_weight_change_kg,
        clamped_to_floor=clamped,
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_nutrition.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q` — the purity test now sweeps `nutrition.py` automatically and must stay green.

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/nutrition.py tests/engine/test_nutrition.py tests/engine/test_properties.py && git commit -m "Add nutrition module with energy and protein guards"`

---

## Task 6 — engine exports + 6 MCP tools + docs + sweep

Export the new API from `performance_agent.engine`, wrap it as 6 MCP tools (engine tool
count 15 → 21, total 32 → 38), bump the doc counts, run the full sweep. The four
periodization tools' docstrings each say which situation they serve, since the Planner
picks between them.

### Step 1 — write the failing tests

- [ ] Append to `tests/server/test_engine_tools.py`:

```python
@pytest.mark.anyio
async def test_build_block_cycle(client):
    result = await client.call_tool("build_block_cycle", {"total_weeks": 12})
    assert not result.isError
    weeks = result.structuredContent["weeks"]
    assert len(weeks) == 12
    assert [w["phase"] for w in weeks[:7]] == ["accumulation"] * 6 + ["intensification"]
    assert weeks[0]["volume_factor"] == pytest.approx(1.10)
    assert weeks[0]["intensity_factor"] == pytest.approx(0.85)
    assert weeks[11]["phase"] == "realization"
    assert weeks[11]["intensity_factor"] == pytest.approx(1.10)


@pytest.mark.anyio
async def test_build_undulating_sessions(client):
    result = await client.call_tool("build_undulating_sessions", {"sessions_per_week": 3})
    assert not result.isError
    sessions = result.structuredContent["sessions"]
    assert [s["emphasis"] for s in sessions] == ["heavy", "light", "moderate"]
    assert sessions[0]["intensity_low"] == pytest.approx(0.85)
    assert sessions[0]["intensity_high"] == pytest.approx(0.925)


@pytest.mark.anyio
async def test_build_inseason_maintenance(client):
    result = await client.call_tool("build_inseason_maintenance", {"matches_this_week": 1})
    assert not result.isError
    week = result.structuredContent
    assert week["strength_sessions"] == 2
    assert week["volume_factor"] == pytest.approx(0.50)
    assert week["min_intensity_factor"] == pytest.approx(0.80)


@pytest.mark.anyio
async def test_build_inseason_maintenance_refuses_congested_week(client):
    result = await client.call_tool("build_inseason_maintenance", {"matches_this_week": 3})
    assert result.isError
    assert "rest is the prescription" in result.content[0].text


@pytest.mark.anyio
async def test_build_peaking_block(client):
    result = await client.call_tool("build_peaking_block", {"weeks": 2})
    assert not result.isError
    weeks = result.structuredContent["weeks"]
    assert weeks[0]["volume_factor"] == pytest.approx(0.55)
    assert weeks[0]["is_test_week"] is False
    assert weeks[1]["intensity_factor"] == pytest.approx(1.025)
    assert weeks[1]["is_test_week"] is True


@pytest.mark.anyio
async def test_compute_bmr_tdee(client):
    result = await client.call_tool(
        "compute_bmr_tdee",
        {
            "sex": "male",
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "age_years": 30,
            "activity_factor": 1.55,
        },
    )
    assert not result.isError
    energy = result.structuredContent
    assert energy["bmr_kcal"] == pytest.approx(1780.0)
    assert energy["tdee_kcal"] == pytest.approx(2759.0)


@pytest.mark.anyio
async def test_prescribe_nutrition_targets(client):
    result = await client.call_tool(
        "prescribe_nutrition_targets",
        {
            "tdee_kcal": 2600.0,
            "goal": "cut",
            "weekly_change_pct_bw": 0.0075,
            "weight_kg": 80.0,
            "height_cm": 180.0,
            "sex": "male",
        },
    )
    assert not result.isError
    target = result.structuredContent
    assert target["daily_kcal"] == pytest.approx(1940.0)
    assert target["protein_g_per_day"] == pytest.approx(176.0)
    assert target["weekly_weight_change_kg"] == pytest.approx(-0.6)
    assert target["clamped_to_floor"] is False


@pytest.mark.anyio
async def test_prescribe_nutrition_targets_refuses_underweight_cut(client):
    result = await client.call_tool(
        "prescribe_nutrition_targets",
        {
            "tdee_kcal": 2200.0,
            "goal": "cut",
            "weekly_change_pct_bw": 0.005,
            "weight_kg": 50.0,
            "height_cm": 175.0,
            "sex": "male",
        },
    )
    assert result.isError
    assert "below the healthy minimum" in result.content[0].text
```

- [ ] In the existing `test_all_engine_tools_are_listed`, extend the expected name set (it holds 15 names after phase 2a) with:

```python
        "build_block_cycle",
        "build_undulating_sessions",
        "build_inseason_maintenance",
        "build_peaking_block",
        "compute_bmr_tdee",
        "prescribe_nutrition_targets",
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/server/test_engine_tools.py -q`
- Expected failures: each new tool call fails (FastMCP unknown-tool error / `isError`), and `test_all_engine_tools_are_listed` fails the subset assertion.

### Step 3 — implement

- [ ] Rewrite `src/performance_agent/engine/__init__.py` in full (phase 2a's version plus the twelve new names):

```python
"""Deterministic sports science engine (no LLM, no I/O).

Public API re-exports. Agents call these functions as tools; they never
compute training numbers themselves.
"""

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict
from performance_agent.engine.feasibility import (
    BodycompFeasibility,
    FeasibilityResult,
    TrainingAge,
    bodycomp_feasibility,
    endurance_feasibility,
    hypertrophy_feasibility,
    strength_feasibility,
)
from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)
from performance_agent.engine.nutrition import (
    EnergyTarget,
    bmr_mifflin_st_jeor,
    prescribe_energy_target,
    tdee_from_bmr,
)
from performance_agent.engine.periodization import (
    BlockWeek,
    InseasonWeek,
    PeakingWeek,
    UndulatingSession,
    WeekLoad,
    build_block_periodization,
    build_inseason_week,
    build_strength_peaking,
    build_undulating_week,
    build_weekly_waves,
)
from performance_agent.engine.strength import (
    ProgressionDecision,
    WeeklySetTargets,
    double_progression,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    weekly_set_targets,
)

__all__ = [
    "BlockWeek",
    "BodycompFeasibility",
    "EnergyTarget",
    "FeasibilityResult",
    "InseasonWeek",
    "PeakingWeek",
    "ProgressionDecision",
    "TrainingAge",
    "UndulatingSession",
    "WeekLoad",
    "WeeklySetTargets",
    "acute_chronic_ratio",
    "bmr_mifflin_st_jeor",
    "bodycomp_feasibility",
    "build_block_periodization",
    "build_inseason_week",
    "build_strength_peaking",
    "build_undulating_week",
    "build_weekly_waves",
    "double_progression",
    "endurance_feasibility",
    "hypertrophy_feasibility",
    "load_for_percentage",
    "one_rm_brzycki",
    "one_rm_epley",
    "one_rm_lombardi",
    "one_rm_wathan",
    "pace_s_per_km",
    "percentage_for_reps_rir",
    "prescribe_energy_target",
    "reps_for_percentage_rir",
    "riegel_predict",
    "session_rpe_load",
    "strength_feasibility",
    "tdee_from_bmr",
    "weekly_loads",
    "weekly_set_targets",
]
```

- [ ] In `src/performance_agent/server/engine_tools.py`, extend the main `from performance_agent.engine import (...)` block with (keep sorted): `BlockWeek`, `EnergyTarget`, `InseasonWeek`, `PeakingWeek`, `UndulatingSession`, `bmr_mifflin_st_jeor`, `build_block_periodization`, `build_inseason_week`, `build_strength_peaking`, `build_undulating_week`, `prescribe_energy_target`, `tdee_from_bmr`.

- [ ] Add the TypedDicts after `PeriodizationWaves`:

```python
class BlockCycle(TypedDict):
    """Accumulation/intensification/realization weeks of a block cycle."""

    weeks: list[BlockWeek]


class UndulatingWeekPlan(TypedDict):
    """Session-by-session emphases for a daily-undulating week."""

    sessions: list[UndulatingSession]


class PeakingBlock(TypedDict):
    """Week-by-week taper toward a 1RM test."""

    weeks: list[PeakingWeek]


class BmrTdee(TypedDict):
    """Basal and total daily energy expenditure, in kcal/day."""

    bmr_kcal: float
    tdee_kcal: float
```

- [ ] Add the six tools after `build_periodization_waves`:

```python
def build_block_cycle(total_weeks: int) -> BlockCycle:
    """Split a training cycle into accumulation/intensification/realization blocks.

    Use this when a single deadline goal is 6+ weeks out and benefits from
    distinct sequential emphases (build_periodization_waves is the generic
    ramp, build_peaking_block covers the final 1-3 weeks before a 1RM test,
    build_inseason_maintenance covers weeks with competitive fixtures).
    Phase split is ~50/35/15% of total_weeks with at least 1 week per phase;
    accumulation is 1.10 volume at 0.85 intensity, intensification 0.90 at
    1.05, realization 0.55 at 1.10 — multipliers against a baseline week.
    total_weeks must be a whole number >= 6.
    """
    return BlockCycle(weeks=build_block_periodization(total_weeks))


def build_undulating_sessions(sessions_per_week: int) -> UndulatingWeekPlan:
    """Assign daily-undulating (DUP) emphases to a week's strength sessions.

    Use this to structure intensity WITHIN a training week (2-7 sessions)
    when all qualities are trained concurrently — the block and peaking
    tools structure across weeks instead. Sessions cycle heavy (0.85-0.925
    of 1RM), light (0.60-0.70), moderate (0.725-0.80); heavy-then-light
    adjacency is deliberate recovery spacing. A single weekly session cannot
    undulate (error).
    """
    return UndulatingWeekPlan(sessions=build_undulating_week(sessions_per_week))


def build_inseason_maintenance(matches_this_week: int) -> InseasonWeek:
    """Prescribe in-season strength maintenance around this week's fixtures.

    Use this when the athlete has 1 or 2 competitive matches this week and
    strength work must shrink to the minimum effective dose. 1 match: 2
    sessions at 0.50 of off-season volume; 2 matches: 1 session at 0.30 —
    both holding intensity at or above 0.80 (intensity, not volume, retains
    strength). REFUSES 0 matches (use a normal building week) and 3+ matches
    (rest is the prescription) — relay those refusals, do not work around
    them.
    """
    return build_inseason_week(matches_this_week)


def build_peaking_block(weeks: int) -> PeakingBlock:
    """Taper the final 1-3 weeks before a 1RM test day.

    Use this only when a maximal strength test is scheduled: volume falls
    week over week while intensity climbs to near-max, and the last week
    (is_test_week=True) carries intensity above 1.0 for openers/heavy
    singles — not a projected new max. Blocks longer than 3 weeks are
    refused (they detrain; schedule a block cycle first).
    """
    return PeakingBlock(weeks=build_strength_peaking(weeks))


def compute_bmr_tdee(
    sex: Literal["male", "female"],
    weight_kg: float,
    height_cm: float,
    age_years: int,
    activity_factor: float,
) -> BmrTdee:
    """Estimate BMR (Mifflin-St Jeor) and TDEE, both in kcal/day.

    weight_kg in (30, 250), height_cm in (100, 250), age_years a whole
    number in (14, 90) — under-15s are refused (youth nutrition is out of
    scope; relay the paediatric referral). activity_factor in [1.2, 2.4],
    sedentary to extreme training loads.
    """
    bmr = bmr_mifflin_st_jeor(sex, weight_kg, height_cm, age_years)
    return BmrTdee(bmr_kcal=bmr, tdee_kcal=tdee_from_bmr(bmr, activity_factor))


def prescribe_nutrition_targets(
    tdee_kcal: float,
    goal: Literal["cut", "maintain", "gain"],
    weekly_change_pct_bw: float,
    weight_kg: float,
    height_cm: float,
    sex: Literal["male", "female"],
) -> EnergyTarget:
    """Prescribe daily kcal and protein for a cut, maintain or gain goal.

    This is not medical advice; the guards are hard-coded and must be
    relayed, never worked around. REFUSES a deficit for an underweight
    athlete (BMI < 18.5) with a referral to a health professional. Caps the
    weekly rate at 1% of bodyweight for a cut and 0.5% for a gain
    (weekly_change_pct_bw is a fraction: 0.0075 = 0.75%/week; must be 0 for
    maintain). A cut landing below the caloric floor (1500 kcal male, 1200
    female) is clamped to the floor with clamped_to_floor=True — that flag
    means "extend the deadline, never deepen the deficit". Protein is 2.2
    g/kg on a cut, 1.6 maintaining, 1.8 gaining.
    """
    return prescribe_energy_target(
        tdee_kcal, goal, weekly_change_pct_bw, weight_kg, height_cm, sex
    )
```

- [ ] Extend `register()` by appending the six tools after `build_periodization_waves` in the loop tuple:

```python
        build_block_cycle,
        build_undulating_sessions,
        build_inseason_maintenance,
        build_peaking_block,
        compute_bmr_tdee,
        prescribe_nutrition_targets,
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/server/test_engine_tools.py tests/engine -q`

### Step 5 — lint, typecheck, commit the tool code

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/__init__.py src/performance_agent/server/engine_tools.py tests/server/test_engine_tools.py && git commit -m "Expose six periodization and nutrition tools over MCP"`

### Step 6 — docs tool count (32 → 38)

The server now exposes 38 tools (21 engine + 10 memory + 6 evidence + 1 report). These
edits depend on phase 2a's Task 9 having landed first — the old strings below are exactly
what 2a leaves behind. (Task 7 bumps the counts again, 38 → 41 and 21 → 24; its docs step
expects exactly the strings this step leaves behind, so do NOT skip or reword this step.)

- [ ] Verify the post-2a strings exist: `rg -n "32 tools" docs/installing.md README.md` and `rg -n "15 tools" README.md` — all three must hit. If not, STOP and report (2a has not landed or the wording drifted).
- [ ] In `docs/installing.md`, replace exactly:

```
Ask your agent: *"List the performance-agent tools."* You should see 32 tools (15
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
```

with:

```
Ask your agent: *"List the performance-agent tools."* You should see 38 tools (21
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
```

- [ ] In `README.md`, replace exactly:

```
You should see 32 tools. Then ask:
```

with:

```
You should see 38 tools. Then ask:
```

- [ ] In `README.md`, replace exactly:

```
- ✅ MCP server exposing the engine as 15 tools — see [docs/installing.md](docs/installing.md)
```

with:

```
- ✅ MCP server exposing the engine as 21 tools — see [docs/installing.md](docs/installing.md)
```

### Step 7 — full verification sweep

- [ ] `uv run pytest -q` — full suite, including `tests/engine/test_engine_purity.py` (engine still stdlib-only with `nutrition.py` swept in automatically).
- [ ] `uv run pytest tests/skills -q` — skills declare tool subsets; adding tools must not break the harness. **If this fails, STOP and report — do not edit skill files.**
- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check` — clean.

### Step 8 — commit the docs

- [ ] `git add docs/installing.md README.md && git commit -m "Update documented tool count to 38"`

---

## Task 7 — remaining progression schemes + RPE conversion

Top-set/back-off and wave-loading prescriptions plus the RPE→RIR conversion, completing
spec §4.2's progression schemes (double progression landed in phase 2a). All engine code
goes in `engine/strength.py` (it already holds `MAX_PERCENTAGE = 1.3` and the
`load_for_percentage` message style these functions reuse); tools go in
`server/engine_tools.py` (24 engine tools after this task, 41 total). **Depends on Task 6
having fully landed** — the engine `__init__.py` rewrite, the 21-tool register tuple, and
the "38 tools" doc strings below are all Task 6's output.

### Step 1 — write the failing tests

- [ ] In `tests/engine/test_strength.py`, replace the strength import block at the top with:

```python
from performance_agent.engine.strength import (
    ProgressionDecision,
    TopSetBackoff,
    WeeklySetTargets,
    double_progression,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    rir_from_rpe,
    top_set_backoff,
    wave_loading,
    weekly_set_targets,
)
```

- [ ] Append to `tests/engine/test_strength.py`:

```python
def test_top_set_backoff_known_values():
    # top = 200 * 0.9 = 180; backoff = 200 * (0.9 - 0.10) = 160
    prescription = top_set_backoff(
        one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.10, backoff_sets=3
    )
    assert isinstance(prescription, TopSetBackoff)
    assert prescription.top_set_load_kg == pytest.approx(180.0)
    assert prescription.backoff_load_kg == pytest.approx(160.0)
    assert prescription.backoff_sets == 3


def test_top_set_backoff_rejects_drop_beyond_half():
    with pytest.raises(ValueError, match="backoff_drop"):
        top_set_backoff(one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.6, backoff_sets=3)


def test_top_set_backoff_rejects_drop_that_leaves_no_load():
    # 0.4 - 0.5 <= 0: both inputs pass their own range checks but combine to nothing
    with pytest.raises(ValueError, match="leaves no back-off load"):
        top_set_backoff(one_rm_kg=200.0, top_percentage=0.4, backoff_drop=0.5, backoff_sets=3)


@pytest.mark.parametrize("backoff_sets", [0, 11])
def test_top_set_backoff_rejects_out_of_range_sets(backoff_sets):
    with pytest.raises(ValueError, match="backoff_sets"):
        top_set_backoff(
            one_rm_kg=200.0, top_percentage=0.9, backoff_drop=0.10, backoff_sets=backoff_sets
        )


def test_wave_loading_classic_two_by_three():
    # wave 1: 0.70, 0.75, 0.80; wave 2 restarts 0.025 up: 0.725, 0.775, 0.825
    steps = wave_loading(
        one_rm_kg=100.0,
        base_percentage=0.70,
        step_increment=0.05,
        steps_per_wave=3,
        waves=2,
        inter_wave_increment=0.025,
    )
    assert [(s.wave, s.step) for s in steps] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    assert [s.percentage for s in steps] == pytest.approx([0.70, 0.75, 0.80, 0.725, 0.775, 0.825])
    assert [s.load_kg for s in steps] == pytest.approx([70.0, 75.0, 80.0, 72.5, 77.5, 82.5])


def test_wave_loading_rejects_peak_over_max_percentage():
    # peak = 1.0 + 4*0.1 + 3*0.05 = 1.55 > 1.3
    with pytest.raises(ValueError, match="peak"):
        wave_loading(
            one_rm_kg=100.0,
            base_percentage=1.0,
            step_increment=0.1,
            steps_per_wave=5,
            waves=4,
            inter_wave_increment=0.05,
        )


def test_wave_loading_rejects_non_overlapping_waves():
    # inter_wave_increment == step_increment: wave 2 would start where wave 1 ended
    with pytest.raises(ValueError, match="inter_wave_increment"):
        wave_loading(
            one_rm_kg=100.0,
            base_percentage=0.70,
            step_increment=0.05,
            steps_per_wave=3,
            waves=2,
            inter_wave_increment=0.05,
        )


def test_wave_loading_bounds_rejections():
    with pytest.raises(ValueError, match="base_percentage"):
        wave_loading(100.0, 1.1, 0.05, 3, 2, 0.025)
    with pytest.raises(ValueError, match="step_increment"):
        wave_loading(100.0, 0.70, 0.15, 3, 2, 0.025)
    with pytest.raises(ValueError, match="steps_per_wave"):
        wave_loading(100.0, 0.70, 0.05, 1, 2, 0.025)
    with pytest.raises(ValueError, match="waves must be"):
        wave_loading(100.0, 0.70, 0.05, 3, 5, 0.025)


@pytest.mark.parametrize(("rpe", "expected_rir"), [(8.0, 2.0), (8.5, 1.5), (10.0, 0.0)])
def test_rir_from_rpe_known_values(rpe, expected_rir):
    assert rir_from_rpe(rpe) == pytest.approx(expected_rir)


@pytest.mark.parametrize("rpe", [0.5, 10.5])
def test_rir_from_rpe_rejects_out_of_scale(rpe):
    with pytest.raises(ValueError, match="rpe must be between"):
        rir_from_rpe(rpe)


def test_rir_from_rpe_rejects_quarter_points():
    with pytest.raises(ValueError, match="half-point"):
        rir_from_rpe(8.25)


def test_rir_from_rpe_rejects_nan():
    with pytest.raises(ValueError, match="finite"):
        rir_from_rpe(float("nan"))
```

- [ ] Append to `tests/engine/test_properties.py`, adding the submodule import line (after the
  nutrition one). The increments are drawn from `st.sampled_from` grids so the overlap slack
  (`step_increment - inter_wave_increment >= 0.005`) stays far above float noise — the
  overlap assertion needs no epsilon:

```python
from performance_agent.engine.strength import MAX_PERCENTAGE, top_set_backoff, wave_loading
```

```python
@given(
    one_rm_kg=st.floats(min_value=1, max_value=500, allow_nan=False),
    top_percentage=st.floats(min_value=0.51, max_value=1.3, allow_nan=False),
    backoff_drop=st.floats(min_value=0.05, max_value=0.5, allow_nan=False),
    backoff_sets=st.integers(min_value=1, max_value=10),
)
def test_backoff_load_is_positive_and_below_top_set(
    one_rm_kg, top_percentage, backoff_drop, backoff_sets
):
    prescription = top_set_backoff(one_rm_kg, top_percentage, backoff_drop, backoff_sets)
    assert 0 < prescription.backoff_load_kg < prescription.top_set_load_kg


@given(
    one_rm_kg=st.floats(min_value=40, max_value=300, allow_nan=False),
    base_percentage=st.floats(min_value=0.4, max_value=0.7, allow_nan=False),
    step_increment=st.sampled_from([0.02, 0.025, 0.05, 0.075, 0.1]),
    steps_per_wave=st.integers(min_value=2, max_value=5),
    waves=st.integers(min_value=2, max_value=4),
    inter_wave_increment=st.sampled_from([0.0, 0.01, 0.02, 0.025, 0.05]),
)
def test_wave_loading_consecutive_waves_overlap(
    one_rm_kg, base_percentage, step_increment, steps_per_wave, waves, inter_wave_increment
):
    assume(inter_wave_increment < step_increment)
    peak = (
        base_percentage
        + (steps_per_wave - 1) * step_increment
        + (waves - 1) * inter_wave_increment
    )
    assume(peak <= MAX_PERCENTAGE)
    steps = wave_loading(
        one_rm_kg, base_percentage, step_increment, steps_per_wave, waves, inter_wave_increment
    )
    assert len(steps) == waves * steps_per_wave
    assert all(s.load_kg > 0 for s in steps)
    for wave in range(1, waves):
        last_of_previous = steps[wave * steps_per_wave - 1]
        first_of_next = steps[wave * steps_per_wave]
        assert first_of_next.percentage < last_of_previous.percentage
```

- [ ] Append to `tests/server/test_engine_tools.py`:

```python
@pytest.mark.anyio
async def test_prescribe_top_set_backoff(client):
    result = await client.call_tool(
        "prescribe_top_set_backoff",
        {"one_rm_kg": 200.0, "top_percentage": 0.9, "backoff_drop": 0.10, "backoff_sets": 3},
    )
    assert not result.isError
    prescription = result.structuredContent
    assert prescription["top_set_load_kg"] == pytest.approx(180.0)
    assert prescription["backoff_load_kg"] == pytest.approx(160.0)
    assert prescription["backoff_sets"] == 3


@pytest.mark.anyio
async def test_prescribe_wave_loading(client):
    result = await client.call_tool(
        "prescribe_wave_loading",
        {
            "one_rm_kg": 100.0,
            "base_percentage": 0.70,
            "step_increment": 0.05,
            "steps_per_wave": 3,
            "waves": 2,
            "inter_wave_increment": 0.025,
        },
    )
    assert not result.isError
    steps = result.structuredContent["steps"]
    assert len(steps) == 6
    assert [s["load_kg"] for s in steps] == pytest.approx([70.0, 75.0, 80.0, 72.5, 77.5, 82.5])
    assert steps[3]["wave"] == 2
    assert steps[3]["step"] == 1


@pytest.mark.anyio
async def test_prescribe_wave_loading_refuses_peak_over_cap(client):
    result = await client.call_tool(
        "prescribe_wave_loading",
        {
            "one_rm_kg": 100.0,
            "base_percentage": 1.0,
            "step_increment": 0.1,
            "steps_per_wave": 5,
            "waves": 4,
            "inter_wave_increment": 0.05,
        },
    )
    assert result.isError
    assert "peak" in result.content[0].text


@pytest.mark.anyio
async def test_convert_rpe_to_rir(client):
    result = await client.call_tool("convert_rpe_to_rir", {"rpe": 8.5})
    assert not result.isError
    assert result.structuredContent["rir"] == pytest.approx(1.5)
```

- [ ] In the existing `test_all_engine_tools_are_listed`, extend the expected name set (it
  holds 21 names after Task 6) with:

```python
        "prescribe_top_set_backoff",
        "prescribe_wave_loading",
        "convert_rpe_to_rir",
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py -q`
- Expected failures: `ImportError: cannot import name 'TopSetBackoff' from 'performance_agent.engine.strength'` (collection error on both engine files); each new tool call fails (FastMCP unknown-tool error / `isError`) and `test_all_engine_tools_are_listed` fails the subset assertion.

### Step 3 — implement

- [ ] In `src/performance_agent/engine/strength.py`, extend the validation import (the file currently imports `validate_whole_number` only):

```python
from performance_agent.engine._validation import validate_finite, validate_whole_number
```

- [ ] Add after the `MAX_EFFECTIVE_REPS` constant:

```python
# Back-off drops beyond 50% of 1RM stop being training weight (team-chosen prior).
MAX_BACKOFF_DROP = 0.5
# More than 10 back-off sets is volume programming, not a top-set day (team-chosen prior).
MAX_BACKOFF_SETS = 10
# Wave-loading bounds, all team-chosen priors: per-set jumps above 10% of 1RM
# skip too much of the intensity curve; 2-5 sets per wave and 1-4 waves cover
# every classic scheme.
MAX_WAVE_STEP = 0.1
MIN_STEPS_PER_WAVE = 2
MAX_STEPS_PER_WAVE = 5
MAX_WAVES = 4
# CR-10 session-RPE scale bounds (published scale, not a tunable prior).
MIN_RPE = 1.0
MAX_RPE = 10.0
```

- [ ] Add after `double_progression`:

```python
@dataclass(frozen=True)
class TopSetBackoff:
    """A top-set/back-off session prescription."""

    top_set_load_kg: float
    backoff_load_kg: float
    backoff_sets: int


def top_set_backoff(
    one_rm_kg: float,
    top_percentage: float,
    backoff_drop: float,
    backoff_sets: int,
) -> TopSetBackoff:
    """Prescribe one top set and its back-off sets from a 1RM.

    Top load is one_rm_kg * top_percentage; back-off load sits backoff_drop
    (a fraction of 1RM, e.g. 0.10 = 10 percentage points) below the top
    percentage, for backoff_sets sets. top_percentage must be in
    (0, MAX_PERCENTAGE], backoff_drop in (0, 0.5], backoff_sets a whole
    number 1-10, and the resulting back-off percentage must stay positive.
    """
    validate_whole_number("backoff_sets", backoff_sets)
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < top_percentage <= MAX_PERCENTAGE:
        msg = f"top_percentage must be in (0, {MAX_PERCENTAGE}], got {top_percentage!r}"
        raise ValueError(msg)
    if not 0 < backoff_drop <= MAX_BACKOFF_DROP:
        msg = (
            f"backoff_drop must be in (0, {MAX_BACKOFF_DROP}], got {backoff_drop!r}: "
            "back-off drops beyond 50% stop being training weight"
        )
        raise ValueError(msg)
    if not 1 <= backoff_sets <= MAX_BACKOFF_SETS:
        msg = f"backoff_sets must be between 1 and {MAX_BACKOFF_SETS}, got {backoff_sets!r}"
        raise ValueError(msg)
    backoff_percentage = top_percentage - backoff_drop
    if backoff_percentage <= 0:
        msg = (
            f"backoff_drop {backoff_drop!r} leaves no back-off load below "
            f"top_percentage {top_percentage!r}"
        )
        raise ValueError(msg)
    return TopSetBackoff(
        top_set_load_kg=one_rm_kg * top_percentage,
        backoff_load_kg=one_rm_kg * backoff_percentage,
        backoff_sets=backoff_sets,
    )


@dataclass(frozen=True)
class WaveStep:
    """One set in a wave-loading scheme (wave and step are 1-indexed)."""

    wave: int
    step: int
    percentage: float
    load_kg: float


def _validate_wave_loading_inputs(
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> None:
    """Raise ValueError if any wave_loading input is out of range."""
    validate_whole_number("steps_per_wave", steps_per_wave)
    validate_whole_number("waves", waves)
    if one_rm_kg <= 0:
        msg = f"one_rm_kg must be positive, got {one_rm_kg!r}"
        raise ValueError(msg)
    if not 0 < base_percentage <= 1:
        msg = f"base_percentage must be in (0, 1], got {base_percentage!r}"
        raise ValueError(msg)
    if not 0 < step_increment <= MAX_WAVE_STEP:
        msg = f"step_increment must be in (0, {MAX_WAVE_STEP}], got {step_increment!r}"
        raise ValueError(msg)
    if not MIN_STEPS_PER_WAVE <= steps_per_wave <= MAX_STEPS_PER_WAVE:
        msg = (
            f"steps_per_wave must be between {MIN_STEPS_PER_WAVE} and "
            f"{MAX_STEPS_PER_WAVE}, got {steps_per_wave!r}"
        )
        raise ValueError(msg)
    if not 1 <= waves <= MAX_WAVES:
        msg = f"waves must be between 1 and {MAX_WAVES}, got {waves!r}"
        raise ValueError(msg)
    if not 0 <= inter_wave_increment < step_increment:
        msg = (
            f"inter_wave_increment must be in [0, step_increment), got "
            f"{inter_wave_increment!r} with step_increment {step_increment!r}: waves must "
            "overlap — each wave starts below where the previous one ended"
        )
        raise ValueError(msg)


def wave_loading(
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> list[WaveStep]:
    """Generate a wave-loading set sequence (waves and steps are 1-indexed).

    Wave w, step s: percentage = base_percentage + (s-1)*step_increment +
    (w-1)*inter_wave_increment; load = one_rm_kg * percentage.
    inter_wave_increment must stay strictly below step_increment so waves
    OVERLAP — the defining property of wave loading: wave 2 starts lower
    than wave 1 ended. The peak percentage (last step of the last wave)
    must not exceed MAX_PERCENTAGE.
    """
    _validate_wave_loading_inputs(
        one_rm_kg, base_percentage, step_increment, steps_per_wave, waves, inter_wave_increment
    )
    peak = (
        base_percentage
        + (steps_per_wave - 1) * step_increment
        + (waves - 1) * inter_wave_increment
    )
    if peak > MAX_PERCENTAGE:
        msg = (
            f"wave scheme peaks at {peak!r} of 1RM, above the {MAX_PERCENTAGE} supra-maximal "
            "cap — lower base_percentage, step_increment, waves or inter_wave_increment"
        )
        raise ValueError(msg)
    steps: list[WaveStep] = []
    for wave in range(1, waves + 1):
        for step in range(1, steps_per_wave + 1):
            percentage = (
                base_percentage
                + (step - 1) * step_increment
                + (wave - 1) * inter_wave_increment
            )
            steps.append(WaveStep(wave, step, percentage, one_rm_kg * percentage))
    return steps


def rir_from_rpe(rpe: float) -> float:
    """Convert session RPE (1-10 scale) to reps in reserve: RIR = 10 - RPE.

    Accepts half-point RPEs (e.g. 8.5 -> 1.5 RIR). Prescription work lives
    at RPE 5-10; below 5 the conversion is arithmetic but rarely meaningful.
    """
    validate_finite("rpe", rpe)
    if not MIN_RPE <= rpe <= MAX_RPE:
        msg = f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe!r}"
        raise ValueError(msg)
    # Half points are exactly representable in binary floats, so a valid
    # rpe * 2 is an exact integer and the comparison is safe.
    doubled = rpe * 2
    if doubled != round(doubled):
        msg = f"rpe must be on the half-point scale (1.0, 1.5, ... 10.0), got {rpe!r}"
        raise ValueError(msg)
    return MAX_RPE - rpe
```

- [ ] In `src/performance_agent/engine/__init__.py` (Task 6's version), replace the strength
  import block with:

```python
from performance_agent.engine.strength import (
    ProgressionDecision,
    TopSetBackoff,
    WaveStep,
    WeeklySetTargets,
    double_progression,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    rir_from_rpe,
    top_set_backoff,
    wave_loading,
    weekly_set_targets,
)
```

  and insert into `__all__`, keeping it sorted: `"TopSetBackoff"` after
  `"ProgressionDecision"`, `"WaveStep"` after `"UndulatingSession"`, `"rir_from_rpe"` after
  `"riegel_predict"`, and `"top_set_backoff"` then `"wave_loading"` after `"tdee_from_bmr"`.

- [ ] In `src/performance_agent/server/engine_tools.py`, extend the main
  `from performance_agent.engine import (...)` block with (keep sorted): `TopSetBackoff`,
  `WaveStep`, `rir_from_rpe`, `top_set_backoff`, `wave_loading`.

- [ ] Add the TypedDicts after `BmrTdee`:

```python
class WaveLoadingPlan(TypedDict):
    """Ordered wave-loading sets (wave and step are 1-indexed)."""

    steps: list[WaveStep]


class RirValue(TypedDict):
    """Reps in reserve equivalent to a session RPE."""

    rir: float
```

- [ ] Add the three tools after `prescribe_nutrition_targets`:

```python
def prescribe_top_set_backoff(
    one_rm_kg: float, top_percentage: float, backoff_drop: float, backoff_sets: int
) -> TopSetBackoff:
    """Prescribe a top-set/back-off strength session from a 1RM.

    One top set at top_percentage of 1RM (in (0, 1.3]), then backoff_sets
    sets (whole number 1-10) at top_percentage - backoff_drop. backoff_drop
    is a fraction of 1RM in (0, 0.5] — drops beyond 50% stop being training
    weight — and must leave a positive back-off percentage. Loads in kg.
    """
    return top_set_backoff(one_rm_kg, top_percentage, backoff_drop, backoff_sets)


def prescribe_wave_loading(
    one_rm_kg: float,
    base_percentage: float,
    step_increment: float,
    steps_per_wave: int,
    waves: int,
    inter_wave_increment: float,
) -> WaveLoadingPlan:
    """Generate a wave-loading set sequence for one strength session.

    Each wave climbs from base_percentage (in (0, 1]) in step_increment
    jumps (in (0, 0.1]) for steps_per_wave sets (2-5); the next wave
    restarts inter_wave_increment above the previous wave's base (1-4
    waves). inter_wave_increment must stay strictly below step_increment so
    waves OVERLAP — each wave starts below where the previous one ended;
    that overlap is the defining property of wave loading. The peak
    percentage (base + (steps_per_wave-1)*step_increment +
    (waves-1)*inter_wave_increment) is REFUSED above 1.3, the supra-maximal
    cap — relay that refusal, do not work around it. Loads in kg.
    """
    return WaveLoadingPlan(
        steps=wave_loading(
            one_rm_kg,
            base_percentage,
            step_increment,
            steps_per_wave,
            waves,
            inter_wave_increment,
        )
    )


def convert_rpe_to_rir(rpe: float) -> RirValue:
    """Convert a session RPE (1-10, half points allowed) to reps in reserve.

    RIR = 10 - RPE (e.g. RPE 8.5 -> 1.5 RIR). Use this when the athlete or
    a source speaks RPE; the prescription tools (prescribe_reps_load) take
    RIR. Quarter-point RPEs are refused — the scale is half-point.
    """
    return RirValue(rir=rir_from_rpe(rpe))
```

- [ ] Extend `register()` by appending the three tools after `prescribe_nutrition_targets`
  in the loop tuple:

```python
        prescribe_top_set_backoff,
        prescribe_wave_loading,
        convert_rpe_to_rir,
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py tests/engine/test_engine_purity.py -q` — all pass, including every pre-existing strength and property test.

### Step 5 — lint, typecheck, commit the code

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/strength.py src/performance_agent/engine/__init__.py src/performance_agent/server/engine_tools.py tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py && git commit -m "Add top-set/back-off, wave loading and RPE conversion" -m "Completes spec §4.2 progression schemes (double progression landed in phase 2a)."`

### Step 6 — docs tool count (38 → 41)

The server now exposes 41 tools (24 engine + 10 memory + 6 evidence + 1 report). The old
strings below are exactly what Task 6's Step 6 leaves behind.

- [ ] Verify the post-Task-6 strings exist: `rg -n "38 tools" docs/installing.md README.md` and `rg -n "21 tools" README.md` — all three must hit. If not, STOP and report (Task 6 has not landed or the wording drifted).
- [ ] In `docs/installing.md`, replace exactly:

```
Ask your agent: *"List the performance-agent tools."* You should see 38 tools (21
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
```

with:

```
Ask your agent: *"List the performance-agent tools."* You should see 41 tools (24
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
```

- [ ] In `README.md`, replace exactly:

```
You should see 38 tools. Then ask:
```

with:

```
You should see 41 tools. Then ask:
```

- [ ] In `README.md`, replace exactly:

```
- ✅ MCP server exposing the engine as 21 tools — see [docs/installing.md](docs/installing.md)
```

with:

```
- ✅ MCP server exposing the engine as 24 tools — see [docs/installing.md](docs/installing.md)
```

### Step 7 — full verification sweep

- [ ] `uv run pytest -q` — full suite, including `tests/engine/test_engine_purity.py` (strength.py's new imports are `math`, `dataclasses` and `_validation`, all allowlisted).
- [ ] `uv run pytest tests/skills -q` — skills declare tool subsets; adding tools must not break the harness. **If this fails, STOP and report — do not edit skill files.**
- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check` — clean.

### Step 8 — commit the docs

- [ ] `git add docs/installing.md README.md && git commit -m "Update documented tool count to 41"`

---

## Final verification checklist

- [ ] `uv run pytest -q` — entire suite green, including `tests/engine/test_engine_purity.py` and `tests/skills`.
- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check` — zero warnings.
- [ ] Server lists 24 engine tools; docs say 41 total (24 engine + 10 memory + 6 evidence + 1 report).
- [ ] All safety guards proven by tests: block < 6 weeks refused, 0/3+ match weeks refused, peaking > 3 weeks refused, underweight cut refused, rate caps enforced, caloric floor clamps with `clamped_to_floor=True`, youth BMR refused, back-off drop beyond 50% refused, no-load back-off refused, non-overlapping waves refused, wave peak above 1.3 refused, quarter-point RPEs refused.
- [ ] 9 commits, one logical change each, imperative subjects; `git log --oneline -9` matches the plan's commit messages.
