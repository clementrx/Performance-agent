# Multi-Goal Feasibility & Strength Prescription (Premium Pipeline Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the deterministic engine with feasibility scoring for strength, hypertrophy and body-composition goals, and with strength-prescription primitives (RIR↔%1RM, per-muscle volume targets, double progression, two extra 1RM formulas), exposed as 6 new MCP tools.

**Architecture:** Pure additive extensions to `engine/feasibility.py` and `engine/strength.py` (stdlib-only, property-tested), new TypedDict-returning wrappers in `server/engine_tools.py`. Spec: docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md §4.1-4.2.

**Tech Stack:** Python 3.13, stdlib-only engine (enforced by AST purity test), Hypothesis property tests, FastMCP tool wrappers.

## Conventions

- Line length 100 characters everywhere.
- Before EVERY commit, run and get a clean result from all of:
  - `uv run ruff format . && uv run ruff check . && uv run ty check`
  - `uv run pytest -q` (the tests named in the task at minimum; full suite in the final task)
- Commit messages: imperative mood, no type prefix (match `git log`: "Enforce uniform per-exercise session formatting…").
- Every numeric constant carries a comment stating that it is a team-chosen prior or citing its corpus study id (e.g. `resistance-training-volume-hypertrophy-meta-2017`).
- Engine files (`src/performance_agent/engine/*.py`) import nothing beyond the stdlib (`math`, `dataclasses`, `enum`, `typing`), engine siblings, and `performance_agent.engine._validation`. The architectural test `tests/engine/test_engine_purity.py` enforces this and must stay green after every task.
- `git add` only the files the task touched — `README.md` has unrelated uncommitted changes in the working tree; never stage it before Task 9.
- All feasibility probabilities must stay in the open interval (0, 1) — asserted in unit tests and Hypothesis properties.

## Existing code the tasks build on

- `src/performance_agent/engine/feasibility.py` — `TrainingAge` (StrEnum), `FeasibilityResult` (frozen dataclass with fields `improvement_needed`, `required_weekly_rate`, `achievable_weekly_rate`, `ratio`, `probability`), `LOGISTIC_STEEPNESS = 3.0`, `MAX_LOGISTIC_EXPONENT = 30.0`, `endurance_feasibility`.
- `src/performance_agent/engine/strength.py` — `MAX_ESTIMATION_REPS = 12`, `MAX_PERCENTAGE = 1.3`, `_validate_load_and_reps`, `one_rm_epley`, `one_rm_brzycki`, `load_for_percentage`.
- `src/performance_agent/engine/_validation.py` — `validate_whole_number(name, value)` (rejects bool and non-int), `validate_finite(name, value)`.
- `src/performance_agent/server/engine_tools.py` — `_ONE_RM_FORMULAS = {"brzycki": one_rm_brzycki, "epley": one_rm_epley}`, TypedDict results, `register(mcp)` loops `mcp.tool()(tool)`.
- `tests/server/conftest.py` — provides the `client` fixture (in-memory FastMCP session) and `anyio_backend`; server tests are `@pytest.mark.anyio` and read `result.structuredContent` / `result.isError`.
- `tests/engine/test_properties.py` — Hypothesis `@given` with module-level strategies (`loads`, `times`) and `st.sampled_from` for formula/age sampling.

---

## Task 1 — `strength_feasibility` in `engine/feasibility.py`

Strength goals invert the endurance sign convention: a BIGGER target is better, so
`improvement_needed = (target - current) / current`. Reuses the logistic mapping, which this
task first extracts into a shared private helper `_logistic_probability` (behavior-preserving
refactor — all existing endurance tests must stay green).

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_feasibility.py` (also add the new imports to the existing import block at the top of the file):

```python
import math

from performance_agent.engine.feasibility import strength_feasibility
```

(merge into the existing `from performance_agent.engine.feasibility import (...)` block:
`FeasibilityResult, TrainingAge, endurance_feasibility, strength_feasibility` — and add
`import math` above `import pytest` per isort order.)

```python
def test_strength_feasibility_exact_values():
    # 100 -> 110 kg in 20 weeks, intermediate: 10% improvement, 0.5%/wk required
    # vs 0.35%/wk achievable -> ratio 10/7, probability 1/(1+exp(3*(10/7-1)))
    result = strength_feasibility(
        current_one_rm_kg=100.0,
        target_one_rm_kg=110.0,
        weeks=20,
        training_age=TrainingAge.INTERMEDIATE,
    )
    assert isinstance(result, FeasibilityResult)
    assert result.improvement_needed == pytest.approx(0.10)
    assert result.required_weekly_rate == pytest.approx(0.005)
    assert result.achievable_weekly_rate == pytest.approx(0.0035)
    assert result.ratio == pytest.approx(10 / 7)
    assert result.probability == pytest.approx(1 / (1 + math.exp(3 * (10 / 7 - 1))))
    assert result.probability == pytest.approx(0.2166, abs=0.001)


def test_strength_already_met_goal_is_easy():
    # Target below current: improvement <= 0, required rate <= 0, ratio <= 0,
    # and the logistic yields near-certainty. Already-met goals are easy.
    result = strength_feasibility(
        current_one_rm_kg=100.0,
        target_one_rm_kg=95.0,
        weeks=8,
        training_age=TrainingAge.ADVANCED,
    )
    assert result.improvement_needed <= 0
    assert result.required_weekly_rate <= 0
    assert result.ratio <= 0
    assert result.probability > 0.95


@pytest.mark.parametrize(
    ("current", "target", "weeks"),
    [(0, 110, 20), (-100, 110, 20), (100, 0, 20), (100, -110, 20), (100, 110, 0)],
)
def test_strength_inputs_are_validated(current, target, weeks):
    with pytest.raises(ValueError, match="positive"):
        strength_feasibility(
            current_one_rm_kg=current,
            target_one_rm_kg=target,
            weeks=weeks,
            training_age=TrainingAge.INTERMEDIATE,
        )


@pytest.mark.parametrize("weeks", [2.5, True])
def test_strength_non_integer_weeks_rejected(weeks):
    with pytest.raises(ValueError, match="whole number"):
        strength_feasibility(
            current_one_rm_kg=100.0,
            target_one_rm_kg=110.0,
            weeks=weeks,
            training_age=TrainingAge.INTERMEDIATE,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_strength_non_finite_loads_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        strength_feasibility(
            current_one_rm_kg=bad,
            target_one_rm_kg=110.0,
            weeks=20,
            training_age=TrainingAge.INTERMEDIATE,
        )
    with pytest.raises(ValueError, match="finite"):
        strength_feasibility(
            current_one_rm_kg=100.0,
            target_one_rm_kg=bad,
            weeks=20,
            training_age=TrainingAge.INTERMEDIATE,
        )
```

- [ ] Append to `tests/engine/test_properties.py` (add `strength_feasibility` to the existing `from performance_agent.engine import (...)` block):

```python
@given(
    current=st.floats(min_value=20, max_value=500, allow_nan=False),
    target=st.floats(min_value=20, max_value=500, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_strength_feasibility_probability_is_a_probability(current, target, weeks, age):
    result = strength_feasibility(current, target, weeks, age)
    assert 0.0 < result.probability < 1.0
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'strength_feasibility' from 'performance_agent.engine.feasibility'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/feasibility.py`, add after `LOGISTIC_STEEPNESS`/`MAX_LOGISTIC_EXPONENT`:

```python
# Sustainable weekly 1RM improvement (fraction of current 1RM), by training
# age. Team-chosen priors, not yet validated against data; strength gains
# decay far faster with training age than endurance gains.
STRENGTH_ACHIEVABLE_WEEKLY_RATE: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.010,
    TrainingAge.INTERMEDIATE: 0.0035,
    TrainingAge.ADVANCED: 0.0010,
}
```

- [ ] Extract the logistic mapping into a private helper (placed right after `FeasibilityResult`) and rewrite the tail of `endurance_feasibility` to use it (behavior-preserving):

```python
def _logistic_probability(ratio: float) -> float:
    """Map a required/achievable ratio to a probability via the shared logistic."""
    exponent = LOGISTIC_STEEPNESS * (ratio - 1)
    exponent = max(min(exponent, MAX_LOGISTIC_EXPONENT), -MAX_LOGISTIC_EXPONENT)
    return 1 / (1 + math.exp(exponent))
```

In `endurance_feasibility`, replace the three lines

```python
    exponent = LOGISTIC_STEEPNESS * (ratio - 1)
    exponent = max(min(exponent, MAX_LOGISTIC_EXPONENT), -MAX_LOGISTIC_EXPONENT)
    probability = 1 / (1 + math.exp(exponent))
```

with

```python
    probability = _logistic_probability(ratio)
```

- [ ] Add the load-input validator (parallel to `_validate_inputs`, but naming loads instead of times) and the public function:

```python
def _validate_load_inputs(
    current_one_rm_kg: float, target_one_rm_kg: float, weeks: int
) -> None:
    validate_whole_number("weeks", weeks)
    for name, value in (
        ("current_one_rm_kg", current_one_rm_kg),
        ("target_one_rm_kg", target_one_rm_kg),
    ):
        validate_finite(name, value)
    if current_one_rm_kg <= 0 or target_one_rm_kg <= 0 or weeks <= 0:
        msg = (
            "current_one_rm_kg, target_one_rm_kg and weeks must be positive, "
            f"got {current_one_rm_kg!r}, {target_one_rm_kg!r}, {weeks!r}"
        )
        raise ValueError(msg)


def strength_feasibility(
    current_one_rm_kg: float,
    target_one_rm_kg: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of a strength (1RM) goal.

    Sign convention is INVERTED versus endurance: a bigger target is better,
    so improvement_needed = (target - current) / current. A target at or
    below the current 1RM yields improvement <= 0, ratio <= 0 and a
    probability above 0.95 — already-met goals are easy by construction.

    Args:
        current_one_rm_kg: Current estimated 1RM for the lift, in kg.
        target_one_rm_kg: Target 1RM for the same lift, in kg.
        weeks: Whole weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    _validate_load_inputs(current_one_rm_kg, target_one_rm_kg, weeks)
    improvement_needed = (target_one_rm_kg - current_one_rm_kg) / current_one_rm_kg
    required_weekly_rate = improvement_needed / weeks
    achievable_weekly_rate = STRENGTH_ACHIEVABLE_WEEKLY_RATE[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    return FeasibilityResult(
        improvement_needed=improvement_needed,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=_logistic_probability(ratio),
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q` — all pass, including every pre-existing endurance test (the `_logistic_probability` refactor must not change any value).

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/feasibility.py tests/engine/test_feasibility.py tests/engine/test_properties.py && git commit -m "Add strength feasibility scoring with shared logistic mapping"`

---

## Task 2 — `hypertrophy_feasibility` in `engine/feasibility.py`

Rates here are ABSOLUTE kg/week, not fractions of current performance. The target gain is
stored in the existing `improvement_needed` field (documented in the docstring).

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_feasibility.py` (add `hypertrophy_feasibility` to the feasibility import block):

```python
def test_hypertrophy_feasibility_exact_values():
    # 5 kg lean gain in 26 weeks, beginner: required 5/26 kg/wk vs 0.23 kg/wk
    # achievable -> ratio ~0.836, probability 1/(1+exp(3*(ratio-1))) ~ 0.6205
    result = hypertrophy_feasibility(
        target_lean_gain_kg=5.0,
        weeks=26,
        training_age=TrainingAge.BEGINNER,
    )
    assert isinstance(result, FeasibilityResult)
    assert result.improvement_needed == pytest.approx(5.0)
    assert result.required_weekly_rate == pytest.approx(5 / 26)
    assert result.achievable_weekly_rate == pytest.approx(0.23)
    assert result.ratio == pytest.approx((5 / 26) / 0.23)
    assert result.probability == pytest.approx(
        1 / (1 + math.exp(3 * ((5 / 26) / 0.23 - 1)))
    )
    assert result.probability == pytest.approx(0.6205, abs=0.001)


@pytest.mark.parametrize(
    ("gain", "weeks"),
    [(0, 26), (-2.0, 26), (5.0, 0), (5.0, -4)],
)
def test_hypertrophy_inputs_are_validated(gain, weeks):
    with pytest.raises(ValueError, match="positive"):
        hypertrophy_feasibility(
            target_lean_gain_kg=gain,
            weeks=weeks,
            training_age=TrainingAge.BEGINNER,
        )


@pytest.mark.parametrize("weeks", [2.5, True])
def test_hypertrophy_non_integer_weeks_rejected(weeks):
    with pytest.raises(ValueError, match="whole number"):
        hypertrophy_feasibility(
            target_lean_gain_kg=5.0,
            weeks=weeks,
            training_age=TrainingAge.BEGINNER,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_hypertrophy_non_finite_gain_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        hypertrophy_feasibility(
            target_lean_gain_kg=bad,
            weeks=26,
            training_age=TrainingAge.BEGINNER,
        )
```

- [ ] Append to `tests/engine/test_properties.py` (add `hypertrophy_feasibility` to the engine import block):

```python
@given(
    gain=st.floats(min_value=0.1, max_value=30, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    age=st.sampled_from(list(TrainingAge)),
)
def test_hypertrophy_feasibility_probability_is_a_probability(gain, weeks, age):
    result = hypertrophy_feasibility(gain, weeks, age)
    assert 0.0 < result.probability < 1.0
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'hypertrophy_feasibility'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/feasibility.py`, add after `STRENGTH_ACHIEVABLE_WEEKLY_RATE`:

```python
# Sustainable lean-mass gain (kg per week), by training age. Team-chosen
# priors derived from common coaching heuristics (~1%/0.5%/0.25% bodyweight
# per month for 70-90 kg athletes); revisit with data.
HYPERTROPHY_ACHIEVABLE_WEEKLY_KG: dict[TrainingAge, float] = {
    TrainingAge.BEGINNER: 0.23,
    TrainingAge.INTERMEDIATE: 0.11,
    TrainingAge.ADVANCED: 0.05,
}
```

- [ ] Add the public function after `strength_feasibility`:

```python
def hypertrophy_feasibility(
    target_lean_gain_kg: float,
    weeks: int,
    training_age: TrainingAge,
) -> FeasibilityResult:
    """Score the feasibility of a lean-mass gain goal.

    Unlike the endurance and strength paths, rates are ABSOLUTE kilograms per
    week, not fractions of current performance: improvement_needed carries
    the target gain in kg, and required/achievable_weekly_rate are kg/week.
    The ratio and logistic mapping are shared with the other goal types.

    Args:
        target_lean_gain_kg: Lean mass to gain, in kg (must be positive).
        weeks: Whole weeks available until the goal deadline.
        training_age: Athlete's training-experience bucket.

    Returns:
        A FeasibilityResult whose probability is in the open interval (0, 1).
    """
    validate_whole_number("weeks", weeks)
    validate_finite("target_lean_gain_kg", target_lean_gain_kg)
    if target_lean_gain_kg <= 0 or weeks <= 0:
        msg = (
            "target_lean_gain_kg and weeks must be positive, "
            f"got {target_lean_gain_kg!r}, {weeks!r}"
        )
        raise ValueError(msg)
    required_weekly_rate = target_lean_gain_kg / weeks
    achievable_weekly_rate = HYPERTROPHY_ACHIEVABLE_WEEKLY_KG[training_age]
    ratio = required_weekly_rate / achievable_weekly_rate
    return FeasibilityResult(
        improvement_needed=target_lean_gain_kg,
        required_weekly_rate=required_weekly_rate,
        achievable_weekly_rate=achievable_weekly_rate,
        ratio=ratio,
        probability=_logistic_probability(ratio),
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/feasibility.py tests/engine/test_feasibility.py tests/engine/test_properties.py && git commit -m "Add hypertrophy feasibility scoring"`

---

## Task 3 — `bodycomp_feasibility` in `engine/feasibility.py`

Body-composition goals get their own frozen result dataclass (`BodycompFeasibility`) because
they carry a safety flag (`exceeds_safe_rate`) and refuse sub-healthy targets outright.
`Literal` comes from `typing`, which IS stdlib and already in the purity allowlist.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_feasibility.py` (add `BodycompFeasibility, bodycomp_feasibility` to the feasibility import block):

```python
def test_bodycomp_feasibility_exact_values():
    # 80 kg at 20% -> 12% in 16 weeks, male. Constant lean mass 64 kg;
    # target weight 64/0.88 ~ 72.727 kg; fat to lose ~7.2727 kg;
    # required (7.2727/80)/16 ~ 0.5682%/wk vs 0.75%/wk -> ratio ~0.7576.
    result = bodycomp_feasibility(
        current_weight_kg=80.0,
        current_body_fat_pct=20.0,
        target_body_fat_pct=12.0,
        weeks=16,
        sex="male",
    )
    assert isinstance(result, BodycompFeasibility)
    assert result.fat_mass_to_lose_kg == pytest.approx(80.0 - 64.0 / 0.88)
    assert result.fat_mass_to_lose_kg == pytest.approx(7.2727, abs=0.001)
    assert result.required_weekly_loss_pct_bw == pytest.approx(0.005682, abs=0.00001)
    assert result.achievable_weekly_loss_pct_bw == pytest.approx(0.0075)
    assert result.ratio == pytest.approx(0.7576, abs=0.001)
    assert result.probability == pytest.approx(
        1 / (1 + math.exp(3 * (0.757576 - 1))), abs=0.001
    )
    assert result.probability == pytest.approx(0.6742, abs=0.001)
    assert result.exceeds_safe_rate is False


def test_bodycomp_refuses_sub_healthy_target():
    with pytest.raises(ValueError, match="healthy minimum for male"):
        bodycomp_feasibility(
            current_weight_kg=80.0,
            current_body_fat_pct=15.0,
            target_body_fat_pct=4.0,
            weeks=16,
            sex="male",
        )
    with pytest.raises(ValueError, match="healthy minimum for female"):
        bodycomp_feasibility(
            current_weight_kg=60.0,
            current_body_fat_pct=22.0,
            target_body_fat_pct=10.0,
            weeks=16,
            sex="female",
        )


def test_bodycomp_refuses_gain_direction():
    with pytest.raises(ValueError, match="not modelled; treat as hypertrophy"):
        bodycomp_feasibility(
            current_weight_kg=80.0,
            current_body_fat_pct=12.0,
            target_body_fat_pct=15.0,
            weeks=16,
            sex="male",
        )


def test_bodycomp_aggressive_deadline_flags_muscle_risk_but_still_scores():
    # Same 80 kg 20% -> 12% squeezed into 8 weeks: required ~1.136%/wk > 1.0%/wk cap.
    result = bodycomp_feasibility(
        current_weight_kg=80.0,
        current_body_fat_pct=20.0,
        target_body_fat_pct=12.0,
        weeks=8,
        sex="male",
    )
    assert result.exceeds_safe_rate is True
    assert result.required_weekly_loss_pct_bw == pytest.approx(0.011364, abs=0.00001)
    assert 0.0 < result.probability < 0.5


@pytest.mark.parametrize(
    ("weight", "weeks"),
    [(0, 16), (-80, 16), (80, 0), (80, -4)],
)
def test_bodycomp_weight_and_weeks_are_validated(weight, weeks):
    with pytest.raises(ValueError, match="positive"):
        bodycomp_feasibility(
            current_weight_kg=weight,
            current_body_fat_pct=20.0,
            target_body_fat_pct=15.0,
            weeks=weeks,
            sex="male",
        )


@pytest.mark.parametrize("bad_pct", [3.0, 2.0, 60.0, 75.0])
def test_bodycomp_body_fat_percent_range_is_validated(bad_pct):
    with pytest.raises(ValueError, match="between 3 and 60"):
        bodycomp_feasibility(
            current_weight_kg=80.0,
            current_body_fat_pct=bad_pct,
            target_body_fat_pct=bad_pct,
            weeks=16,
            sex="male",
        )
```

- [ ] Append to `tests/engine/test_properties.py` (add `bodycomp_feasibility` to the engine import block):

```python
@given(
    weight=st.floats(min_value=40, max_value=200, allow_nan=False),
    current_bf=st.floats(min_value=13, max_value=55, allow_nan=False),
    target_bf=st.floats(min_value=12, max_value=50, allow_nan=False),
    weeks=st.integers(min_value=1, max_value=104),
    sex=st.sampled_from(["male", "female"]),
)
def test_bodycomp_probability_is_a_probability(weight, current_bf, target_bf, weeks, sex):
    assume(target_bf < current_bf)
    result = bodycomp_feasibility(weight, current_bf, target_bf, weeks, sex)
    assert 0.0 < result.probability < 1.0
```

(`assume` is already imported in this file.)

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'BodycompFeasibility'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/feasibility.py`, change the typing import line (add near the top, after `from enum import StrEnum`):

```python
from typing import Literal
```

- [ ] Add constants after `HYPERTROPHY_ACHIEVABLE_WEEKLY_KG`:

```python
# Safe weekly fat-loss rate as a fraction of bodyweight. 0.5-1.0 %/week is
# the range commonly recommended to preserve lean mass; we score against the
# 0.75% midpoint and flag anything above 1.0% as muscle-risking.
BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW = 0.0075
BODYCOMP_MAX_SAFE_WEEKLY_LOSS_PCT_BW = 0.010
# Essential-fat floors below which we refuse to plan. Team-chosen priors
# aligned with common physiology references.
MIN_HEALTHY_BODY_FAT_PCT: dict[str, float] = {"male": 5.0, "female": 12.0}
```

- [ ] Add the dataclass and function after `hypertrophy_feasibility`:

```python
@dataclass(frozen=True)
class BodycompFeasibility:
    """Body-composition verdict with its drivers (for explainability)."""

    fat_mass_to_lose_kg: float
    required_weekly_loss_pct_bw: float
    achievable_weekly_loss_pct_bw: float
    ratio: float
    probability: float
    exceeds_safe_rate: bool


def bodycomp_feasibility(
    current_weight_kg: float,
    current_body_fat_pct: float,
    target_body_fat_pct: float,
    weeks: int,
    sex: Literal["male", "female"],
) -> BodycompFeasibility:
    """Score the feasibility of a fat-loss body-composition goal.

    Assumes constant lean mass: fat to lose is the weight change needed to
    hit the target body-fat percentage at today's lean mass. The required
    weekly loss (fraction of current bodyweight) is scored against the 0.75%
    midpoint of the commonly recommended 0.5-1.0%/week band; anything above
    1.0%/week additionally sets exceeds_safe_rate (muscle-risking deadline).
    Targets below the healthy minimum for the athlete's sex are refused with
    a ValueError. Body-fat GAIN goals are out of scope and also refused.

    Args:
        current_weight_kg: Current bodyweight, in kg.
        current_body_fat_pct: Current body-fat percentage, in (3, 60).
        target_body_fat_pct: Target body-fat percentage, in (3, 60), below
            current and at or above the healthy floor for `sex`.
        weeks: Whole weeks available until the goal deadline.
        sex: "male" or "female" (selects the healthy body-fat floor).

    Returns:
        A BodycompFeasibility whose probability is in the open interval (0, 1).
    """
    validate_whole_number("weeks", weeks)
    validate_finite("current_weight_kg", current_weight_kg)
    for name, value in (
        ("current_body_fat_pct", current_body_fat_pct),
        ("target_body_fat_pct", target_body_fat_pct),
    ):
        validate_finite(name, value)
    if current_weight_kg <= 0 or weeks <= 0:
        msg = (
            "current_weight_kg and weeks must be positive, "
            f"got {current_weight_kg!r}, {weeks!r}"
        )
        raise ValueError(msg)
    for name, value in (
        ("current_body_fat_pct", current_body_fat_pct),
        ("target_body_fat_pct", target_body_fat_pct),
    ):
        if not 3 < value < 60:
            msg = f"{name} must be between 3 and 60 percent (exclusive), got {value!r}"
            raise ValueError(msg)
    if target_body_fat_pct >= current_body_fat_pct:
        msg = (
            "target_body_fat_pct must be below current_body_fat_pct; "
            "body-fat GAIN goals are not modelled; treat as hypertrophy"
        )
        raise ValueError(msg)
    healthy_floor = MIN_HEALTHY_BODY_FAT_PCT[sex]
    if target_body_fat_pct < healthy_floor:
        msg = (
            f"target_body_fat_pct {target_body_fat_pct!r} is below the healthy minimum "
            f"for {sex} ({healthy_floor}%) — refuse and refer to a health professional"
        )
        raise ValueError(msg)
    lean_mass_kg = current_weight_kg * (1 - current_body_fat_pct / 100)
    target_weight_kg = lean_mass_kg / (1 - target_body_fat_pct / 100)
    fat_mass_to_lose_kg = current_weight_kg - target_weight_kg
    required_weekly_loss_pct_bw = (fat_mass_to_lose_kg / current_weight_kg) / weeks
    ratio = required_weekly_loss_pct_bw / BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW
    return BodycompFeasibility(
        fat_mass_to_lose_kg=fat_mass_to_lose_kg,
        required_weekly_loss_pct_bw=required_weekly_loss_pct_bw,
        achievable_weekly_loss_pct_bw=BODYCOMP_ACHIEVABLE_WEEKLY_LOSS_PCT_BW,
        ratio=ratio,
        probability=_logistic_probability(ratio),
        exceeds_safe_rate=required_weekly_loss_pct_bw > BODYCOMP_MAX_SAFE_WEEKLY_LOSS_PCT_BW,
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_feasibility.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/feasibility.py tests/engine/test_feasibility.py tests/engine/test_properties.py && git commit -m "Add body-composition feasibility with healthy-floor refusal"`

---

## Task 4 — RIR↔%1RM in `engine/strength.py`

Epley inverted at effective reps = reps + RIR. `strength.py` gains `import math` for the
floor in the inversion.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_strength.py` (extend the strength import block with `percentage_for_reps_rir, reps_for_percentage_rir`):

```python
def test_percentage_for_reps_rir_known_value():
    # 5 reps with 2 in reserve = 7 effective reps -> 1/(1 + 7/30) = 30/37
    assert percentage_for_reps_rir(reps=5, rir=2) == pytest.approx(30 / 37)
    assert percentage_for_reps_rir(reps=5, rir=2) == pytest.approx(0.8108, abs=0.001)


def test_percentage_for_single_all_out_rep_is_full_1rm():
    assert percentage_for_reps_rir(reps=1, rir=0) == 1.0


def test_reps_for_percentage_rir_known_value():
    # 30/37 of 1RM leaves 7 effective reps; 2 in reserve -> 5 clean reps
    assert reps_for_percentage_rir(percentage=30 / 37, rir=2) == 5


def test_reps_for_full_1rm_with_zero_rir_is_one_rep():
    assert reps_for_percentage_rir(percentage=1.0, rir=0) == 1


def test_percentage_too_high_to_leave_reps_in_reserve():
    with pytest.raises(ValueError, match="reserve"):
        reps_for_percentage_rir(percentage=1.0, rir=2)


def test_effective_reps_beyond_cap_rejected():
    with pytest.raises(ValueError, match="18"):
        percentage_for_reps_rir(reps=15, rir=4)


@pytest.mark.parametrize(("reps", "rir"), [(0, 0), (-1, 2), (5, -1)])
def test_reps_and_rir_bounds_rejected(reps, rir):
    with pytest.raises(ValueError):
        percentage_for_reps_rir(reps=reps, rir=rir)


@pytest.mark.parametrize("percentage", [0, -0.5, 1.01])
def test_reps_for_percentage_rir_percentage_validated(percentage):
    with pytest.raises(ValueError, match="percentage"):
        reps_for_percentage_rir(percentage=percentage, rir=1)


@pytest.mark.parametrize(("reps", "rir"), [(2.5, 0), (True, 0), (5, 1.5)])
def test_rir_functions_reject_non_whole_numbers(reps, rir):
    with pytest.raises(ValueError, match="whole number"):
        percentage_for_reps_rir(reps=reps, rir=rir)
```

- [ ] Append to `tests/engine/test_properties.py` (add `percentage_for_reps_rir, reps_for_percentage_rir` to the engine import block):

```python
@given(
    reps=st.integers(min_value=1, max_value=18),
    rir=st.integers(min_value=0, max_value=17),
)
def test_reps_rir_percentage_round_trips(reps, rir):
    assume(reps + rir <= 18)
    percentage = percentage_for_reps_rir(reps, rir)
    assert reps_for_percentage_rir(percentage, rir) == reps
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'percentage_for_reps_rir'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/strength.py`, add `import math` at the top (before the `_validation` import), add the constant after `MAX_PERCENTAGE`:

```python
MAX_EFFECTIVE_REPS = 18  # reps + RIR beyond this leaves the formula's validated range
```

- [ ] Add both functions after `load_for_percentage`:

```python
def percentage_for_reps_rir(reps: int, rir: int) -> float:
    """Fraction of 1RM at which `reps` clean reps leave `rir` in reserve.

    Epley inverted at effective reps = reps + rir:
    pct = 1 / (1 + (reps + rir) / 30). Effective reps are capped at 18; the
    Epley curve is validated to ~12, so 13-18 carry extra uncertainty the
    caller must label. One all-out rep (reps=1, rir=0) is by definition
    100% of 1RM, so effective reps == 1 returns exactly 1.0.
    """
    validate_whole_number("reps", reps)
    validate_whole_number("rir", rir)
    if reps < 1:
        msg = f"reps must be at least 1, got {reps!r}"
        raise ValueError(msg)
    if rir < 0:
        msg = f"rir must be non-negative, got {rir!r}"
        raise ValueError(msg)
    effective_reps = reps + rir
    if effective_reps > MAX_EFFECTIVE_REPS:
        msg = f"reps + rir must be at most {MAX_EFFECTIVE_REPS}, got {effective_reps!r}"
        raise ValueError(msg)
    if effective_reps == 1:
        return 1.0
    return 1 / (1 + effective_reps / 30)


def reps_for_percentage_rir(percentage: float, rir: int) -> int:
    """Max clean reps at a fraction of 1RM leaving `rir` in reserve (floor).

    Inverts percentage_for_reps_rir: effective reps = floor(30 * (1/pct - 1)),
    with at least one effective rep (a single rep is always possible at or
    below 100% of 1RM), then subtracts `rir`. Raises if the percentage is
    too high to leave `rir` reps in reserve.
    """
    validate_whole_number("rir", rir)
    if not 0 < percentage <= 1:
        msg = f"percentage must be in (0, 1], got {percentage!r}"
        raise ValueError(msg)
    if rir < 0:
        msg = f"rir must be non-negative, got {rir!r}"
        raise ValueError(msg)
    # The epsilon absorbs float rounding so exact Epley percentages round-trip.
    effective_reps = max(math.floor(30 * (1 / percentage - 1) + 1e-9), 1)
    reps = effective_reps - rir
    if reps < 1:
        msg = (
            f"percentage {percentage!r} is too high to leave {rir!r} reps in reserve; "
            "lower the percentage or the RIR"
        )
        raise ValueError(msg)
    return reps
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/strength.py tests/engine/test_strength.py tests/engine/test_properties.py && git commit -m "Add RIR-aware percentage and rep prescription primitives"`

---

## Task 5 — volume landmarks in `engine/strength.py`

Per-muscle weekly hard-set targets by training age. `TrainingAge` is imported from the
sibling `performance_agent.engine.feasibility` module — engine-internal imports are allowed
by the purity test (it permits engine siblings).

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_strength.py` (extend the strength import block with `WeeklySetTargets, weekly_set_targets`; add `from performance_agent.engine.feasibility import TrainingAge` to the imports):

```python
@pytest.mark.parametrize("age", list(TrainingAge))
def test_weekly_set_targets_fields_strictly_increase(age):
    targets = weekly_set_targets(age)
    assert isinstance(targets, WeeklySetTargets)
    assert (
        targets.minimum_effective
        < targets.optimal_low
        < targets.optimal_high
        < targets.maximum_adaptive
    )


def test_weekly_set_targets_beginner_values():
    targets = weekly_set_targets(TrainingAge.BEGINNER)
    assert targets == WeeklySetTargets(
        minimum_effective=6, optimal_low=8, optimal_high=12, maximum_adaptive=16
    )


def test_weekly_set_targets_scale_with_training_age():
    beginner = weekly_set_targets(TrainingAge.BEGINNER)
    intermediate = weekly_set_targets(TrainingAge.INTERMEDIATE)
    advanced = weekly_set_targets(TrainingAge.ADVANCED)
    assert beginner.optimal_low < intermediate.optimal_low < advanced.optimal_low
    assert beginner.maximum_adaptive < intermediate.maximum_adaptive < advanced.maximum_adaptive
```

- [ ] Append to `tests/engine/test_properties.py` (add `weekly_set_targets` to the engine import block):

```python
@given(age=st.sampled_from(list(TrainingAge)))
def test_weekly_set_targets_invariant_ordering(age):
    targets = weekly_set_targets(age)
    assert (
        0
        < targets.minimum_effective
        < targets.optimal_low
        < targets.optimal_high
        < targets.maximum_adaptive
    )
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py -q`
- Expected failure: `ImportError: cannot import name 'WeeklySetTargets'` (collection error).

### Step 3 — implement

- [ ] In `src/performance_agent/engine/strength.py`, add to the imports (after `import math`):

```python
from dataclasses import dataclass

from performance_agent.engine.feasibility import TrainingAge
```

(keep the existing `from performance_agent.engine._validation import validate_whole_number`.)

- [ ] Add after `reps_for_percentage_rir`:

```python
@dataclass(frozen=True)
class WeeklySetTargets:
    """Weekly hard-set targets for one muscle group."""

    minimum_effective: int
    optimal_low: int
    optimal_high: int
    maximum_adaptive: int


# Weekly hard sets per muscle group by training age. Anchored on the
# dose-response meta-analysis in the corpus (resistance-training-volume-
# hypertrophy-meta-2017: 10+ sets/muscle/week outperform fewer); the spread
# across training ages is a team-chosen prior.
WEEKLY_SET_TARGETS: dict[TrainingAge, WeeklySetTargets] = {
    TrainingAge.BEGINNER: WeeklySetTargets(6, 8, 12, 16),
    TrainingAge.INTERMEDIATE: WeeklySetTargets(8, 10, 16, 20),
    TrainingAge.ADVANCED: WeeklySetTargets(10, 12, 20, 26),
}


def weekly_set_targets(training_age: TrainingAge) -> WeeklySetTargets:
    """Return per-muscle weekly hard-set targets for a training-age bucket."""
    return WEEKLY_SET_TARGETS[training_age]
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/strength.py tests/engine/test_strength.py tests/engine/test_properties.py && git commit -m "Add weekly hard-set volume targets by training age"`

---

## Task 6 — double progression in `engine/strength.py`

Fill the rep range first, then add load. All sets at the top of the range → load goes up
by `increment_kg` and the target resets to `rep_range_low`; otherwise the load holds and the
target is the lowest achieved set plus one, capped at `rep_range_high`.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_strength.py` (extend the strength import block with `ProgressionDecision, double_progression`):

```python
def test_double_progression_all_sets_at_top_increments_load():
    decision = double_progression(
        reps_achieved=[12, 12, 12],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert decision == ProgressionDecision(
        next_load_kg=62.5, next_target_reps=8, load_increased=True
    )


def test_double_progression_partial_achievement_holds_load():
    decision = double_progression(
        reps_achieved=[12, 11, 10],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert decision.next_load_kg == 60.0
    assert decision.load_increased is False
    # lowest set (10) drives the target: 10 + 1 = 11
    assert decision.next_target_reps == 11


def test_double_progression_target_is_capped_at_range_top():
    # lowest achieved already at the top (e.g. logged above range): cap at high
    decision = double_progression(
        reps_achieved=[13, 12, 14],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    # every set reached the top -> load increases instead of rep chasing
    assert decision.load_increased is True

    held = double_progression(
        reps_achieved=[12, 12, 11],
        load_kg=60.0,
        rep_range_low=8,
        rep_range_high=12,
        increment_kg=2.5,
    )
    assert held.load_increased is False
    assert held.next_target_reps == 12  # min(11 + 1, 12)


def test_double_progression_validation_rejections():
    with pytest.raises(ValueError, match="empty"):
        double_progression(
            reps_achieved=[], load_kg=60.0, rep_range_low=8, rep_range_high=12, increment_kg=2.5
        )
    with pytest.raises(ValueError, match="rep range"):
        double_progression(
            reps_achieved=[10],
            load_kg=60.0,
            rep_range_low=12,
            rep_range_high=8,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="rep range"):
        double_progression(
            reps_achieved=[10],
            load_kg=60.0,
            rep_range_low=8,
            rep_range_high=19,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="non-negative"):
        double_progression(
            reps_achieved=[10, -1],
            load_kg=60.0,
            rep_range_low=8,
            rep_range_high=12,
            increment_kg=2.5,
        )
    with pytest.raises(ValueError, match="load_kg"):
        double_progression(
            reps_achieved=[10], load_kg=0, rep_range_low=8, rep_range_high=12, increment_kg=2.5
        )
    with pytest.raises(ValueError, match="increment_kg"):
        double_progression(
            reps_achieved=[10], load_kg=60.0, rep_range_low=8, rep_range_high=12, increment_kg=0
        )
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_strength.py -q`
- Expected failure: `ImportError: cannot import name 'ProgressionDecision'` (collection error).

### Step 3 — implement

- [ ] Append to `src/performance_agent/engine/strength.py`:

```python
@dataclass(frozen=True)
class ProgressionDecision:
    """Next-session prescription from a double-progression rule."""

    next_load_kg: float
    next_target_reps: int
    load_increased: bool


def double_progression(
    reps_achieved: list[int],
    load_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    increment_kg: float,
) -> ProgressionDecision:
    """Apply the double-progression rule to one exercise's last session.

    Fill the rep range first, then add load: when every set reached
    rep_range_high, add increment_kg and reset the target to rep_range_low;
    otherwise hold the load and target one rep above the lowest achieved
    set, capped at rep_range_high.

    Args:
        reps_achieved: Reps completed per set last session (non-empty, >= 0).
        load_kg: Load used last session, in kg (positive).
        rep_range_low: Bottom of the working rep range (>= 1).
        rep_range_high: Top of the working rep range (> low, <= 18).
        increment_kg: Load added when the range is filled (positive).

    Returns:
        A ProgressionDecision with the next load, next rep target and
        whether the load increased.
    """
    for name, value in (("rep_range_low", rep_range_low), ("rep_range_high", rep_range_high)):
        validate_whole_number(name, value)
    if not 1 <= rep_range_low < rep_range_high <= MAX_EFFECTIVE_REPS:
        msg = (
            f"rep range must satisfy 1 <= low < high <= {MAX_EFFECTIVE_REPS}, "
            f"got low={rep_range_low!r}, high={rep_range_high!r}"
        )
        raise ValueError(msg)
    if load_kg <= 0:
        msg = f"load_kg must be positive, got {load_kg!r}"
        raise ValueError(msg)
    if increment_kg <= 0:
        msg = f"increment_kg must be positive, got {increment_kg!r}"
        raise ValueError(msg)
    if not reps_achieved:
        msg = "reps_achieved must not be empty"
        raise ValueError(msg)
    for reps in reps_achieved:
        validate_whole_number("reps_achieved entry", reps)
        if reps < 0:
            msg = f"reps_achieved entries must be non-negative, got {reps!r}"
            raise ValueError(msg)
    if all(reps >= rep_range_high for reps in reps_achieved):
        return ProgressionDecision(
            next_load_kg=load_kg + increment_kg,
            next_target_reps=rep_range_low,
            load_increased=True,
        )
    return ProgressionDecision(
        next_load_kg=load_kg,
        next_target_reps=min(min(reps_achieved) + 1, rep_range_high),
        load_increased=False,
    )
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/strength.py tests/engine/test_strength.py && git commit -m "Add double progression decision rule"`

---

## Task 7 — Lombardi & Wathan 1RM formulas + `estimate_1rm` widening

Two more 1RM estimators sharing `_validate_load_and_reps` (1-12 reps) and the reps==1
shortcut. Note: Wathan at reps=1 mathematically gives ~1.3% above the lifted load
(100/(48.8 + 53.8·e^-0.075) ≈ 1.013), so the shortcut is a deliberate consistency clamp,
documented like Brzycki's. This task also widens the server's `estimate_1rm` tool.

### Step 1 — write the failing tests

- [ ] Append to `tests/engine/test_strength.py` (extend the strength import block with `one_rm_lombardi, one_rm_wathan`):

```python
def test_lombardi_known_value():
    # 100 * 8**0.1 ~ 123.11
    assert one_rm_lombardi(load_kg=100, reps=8) == pytest.approx(123.11, abs=0.01)


def test_wathan_known_value():
    # 100 * 100 / (48.8 + 53.8 * e^-0.6) ~ 127.67
    assert one_rm_wathan(load_kg=100, reps=8) == pytest.approx(127.67, abs=0.01)


def test_lombardi_and_wathan_single_rep_is_the_load_itself():
    # Wathan at reps=1 would give ~1.3% above the load; the shortcut clamps it.
    assert one_rm_lombardi(load_kg=100, reps=1) == 100.0
    assert one_rm_wathan(load_kg=100, reps=1) == 100.0


@pytest.mark.parametrize("reps", [0, -1, 13])
def test_lombardi_and_wathan_rep_range_is_validated(reps):
    with pytest.raises(ValueError, match="reps"):
        one_rm_lombardi(load_kg=100, reps=reps)
    with pytest.raises(ValueError, match="reps"):
        one_rm_wathan(load_kg=100, reps=reps)


@pytest.mark.parametrize("load_kg", [0, -20])
def test_lombardi_and_wathan_load_must_be_positive(load_kg):
    with pytest.raises(ValueError, match="load"):
        one_rm_lombardi(load_kg=load_kg, reps=5)
    with pytest.raises(ValueError, match="load"):
        one_rm_wathan(load_kg=load_kg, reps=5)
```

- [ ] In `tests/engine/test_properties.py`, extend the existing formula strategy so BOTH existing 1RM properties (`test_one_rm_never_decreases_with_more_reps`, `test_one_rm_is_at_least_the_lifted_load`) now cover all four formulas. Add `one_rm_lombardi, one_rm_wathan` to the engine import block and change:

```python
one_rm_formulas = st.sampled_from([one_rm_epley, one_rm_brzycki])
```

to:

```python
one_rm_formulas = st.sampled_from([one_rm_epley, one_rm_brzycki, one_rm_lombardi, one_rm_wathan])
```

- [ ] Append to `tests/server/test_engine_tools.py`:

```python
@pytest.mark.anyio
async def test_estimate_1rm_lombardi(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 8, "formula": "lombardi"}
    )
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(123.11, abs=0.01)
    assert result.structuredContent["formula"] == "lombardi"


@pytest.mark.anyio
async def test_estimate_1rm_wathan(client):
    result = await client.call_tool(
        "estimate_1rm", {"load_kg": 100, "reps": 8, "formula": "wathan"}
    )
    assert not result.isError
    assert result.structuredContent["one_rm_kg"] == pytest.approx(127.67, abs=0.01)
    assert result.structuredContent["formula"] == "wathan"
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py -q`
- Expected failure: `ImportError: cannot import name 'one_rm_lombardi'` (collection error).

### Step 3 — implement

- [ ] Append to `src/performance_agent/engine/strength.py` (after `one_rm_brzycki`, keeping the 1RM formulas together):

```python
def one_rm_lombardi(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Lombardi formula: load * reps^0.10.

    A single rep at a given load is, by definition, at least a 1RM at that
    load, so ``reps == 1`` returns ``load_kg`` unchanged.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return load_kg * reps**0.10


def one_rm_wathan(load_kg: float, reps: int) -> float:
    """Estimate 1RM with the Wathan formula: 100*load / (48.8 + 53.8*e^(-0.075*reps)).

    At ``reps == 1`` the raw formula lands about 1.3% ABOVE the lifted load
    (100 / (48.8 + 53.8*e^-0.075) ~ 1.013), but a single rep at a given load
    is, by definition, at least a 1RM at that load — so ``reps == 1`` returns
    ``load_kg`` unchanged as a deliberate consistency clamp, matching the
    other formulas.
    """
    _validate_load_and_reps(load_kg, reps)
    if reps == 1:
        return float(load_kg)
    return 100 * load_kg / (48.8 + 53.8 * math.exp(-0.075 * reps))
```

- [ ] In `src/performance_agent/server/engine_tools.py`:
  - Extend the engine import block with `one_rm_lombardi, one_rm_wathan` (this requires the `engine/__init__.py` export — add just these two names now, alphabetically, to `src/performance_agent/engine/__init__.py`'s strength import and `__all__`; the remaining exports land in Task 8):

```python
from performance_agent.engine.strength import (
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    one_rm_lombardi,
    one_rm_wathan,
)
```

  and add `"one_rm_lombardi",` and `"one_rm_wathan",` to `__all__` (keep it sorted).

  - Widen the formula registry:

```python
_ONE_RM_FORMULAS = {
    "brzycki": one_rm_brzycki,
    "epley": one_rm_epley,
    "lombardi": one_rm_lombardi,
    "wathan": one_rm_wathan,
}
```

  - Widen `OneRmEstimate`:

```python
class OneRmEstimate(TypedDict):
    """Estimated one-rep max and the formula that produced it."""

    one_rm_kg: float
    formula: Literal["epley", "brzycki", "lombardi", "wathan"]
```

  - Widen `estimate_1rm`'s signature and keep the docstring guidance:

```python
def estimate_1rm(
    load_kg: float,
    reps: int,
    formula: Literal["epley", "brzycki", "lombardi", "wathan"] = "epley",
) -> OneRmEstimate:
    """Estimate a one-rep max in kg from a submaximal set (1-12 reps).

    Pick one formula per athlete and lift and stay consistent; do not average
    them.
    """
    return OneRmEstimate(one_rm_kg=_ONE_RM_FORMULAS[formula](load_kg, reps), formula=formula)
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py tests/engine/test_engine_purity.py -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/strength.py src/performance_agent/engine/__init__.py src/performance_agent/server/engine_tools.py tests/engine/test_strength.py tests/engine/test_properties.py tests/server/test_engine_tools.py && git commit -m "Add Lombardi and Wathan 1RM formulas and widen estimate_1rm"`

---

## Task 8 — engine exports + 5 new MCP tools

Export everything new from `performance_agent.engine`, then wrap the three feasibility
functions and the three prescription primitives as MCP tools (6 new tools total —
`prescribe_reps_load` composes two engine functions into one tool).

### Step 1 — write the failing tests

- [ ] Append to `tests/server/test_engine_tools.py`:

```python
@pytest.mark.anyio
async def test_assess_strength_goal(client):
    result = await client.call_tool(
        "assess_strength_goal",
        {
            "current_one_rm_kg": 100.0,
            "target_one_rm_kg": 110.0,
            "weeks": 20,
            "training_age": "intermediate",
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["improvement_needed"] == pytest.approx(0.10)
    assert verdict["required_weekly_rate"] == pytest.approx(0.005)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.0035)
    assert verdict["probability"] == pytest.approx(0.2166, abs=0.001)


@pytest.mark.anyio
async def test_assess_hypertrophy_goal(client):
    result = await client.call_tool(
        "assess_hypertrophy_goal",
        {"target_lean_gain_kg": 5.0, "weeks": 26, "training_age": "beginner"},
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["required_weekly_rate"] == pytest.approx(5 / 26)
    assert verdict["achievable_weekly_rate"] == pytest.approx(0.23)
    assert verdict["probability"] == pytest.approx(0.6205, abs=0.001)


@pytest.mark.anyio
async def test_assess_bodycomp_goal(client):
    result = await client.call_tool(
        "assess_bodycomp_goal",
        {
            "current_weight_kg": 80.0,
            "current_body_fat_pct": 20.0,
            "target_body_fat_pct": 12.0,
            "weeks": 16,
            "sex": "male",
        },
    )
    assert not result.isError
    verdict = result.structuredContent
    assert verdict["fat_mass_to_lose_kg"] == pytest.approx(7.2727, abs=0.001)
    assert verdict["probability"] == pytest.approx(0.6742, abs=0.001)
    assert verdict["exceeds_safe_rate"] is False


@pytest.mark.anyio
async def test_assess_bodycomp_goal_refuses_sub_healthy_target(client):
    result = await client.call_tool(
        "assess_bodycomp_goal",
        {
            "current_weight_kg": 80.0,
            "current_body_fat_pct": 15.0,
            "target_body_fat_pct": 4.0,
            "weeks": 16,
            "sex": "male",
        },
    )
    assert result.isError
    assert "healthy minimum" in result.content[0].text


@pytest.mark.anyio
async def test_prescribe_reps_load(client):
    result = await client.call_tool(
        "prescribe_reps_load", {"one_rm_kg": 100.0, "reps": 5, "rir": 2}
    )
    assert not result.isError
    prescription = result.structuredContent
    assert prescription["percentage"] == pytest.approx(30 / 37)
    assert prescription["load_kg"] == pytest.approx(100 * 30 / 37)


@pytest.mark.anyio
async def test_weekly_set_targets_for(client):
    result = await client.call_tool("weekly_set_targets_for", {"training_age": "intermediate"})
    assert not result.isError
    targets = result.structuredContent
    assert targets["minimum_effective"] == 8
    assert targets["optimal_low"] == 10
    assert targets["optimal_high"] == 16
    assert targets["maximum_adaptive"] == 20


@pytest.mark.anyio
async def test_progress_double_progression(client):
    result = await client.call_tool(
        "progress_double_progression",
        {
            "reps_achieved": [12, 12, 12],
            "load_kg": 60.0,
            "rep_range_low": 8,
            "rep_range_high": 12,
            "increment_kg": 2.5,
        },
    )
    assert not result.isError
    decision = result.structuredContent
    assert decision["next_load_kg"] == pytest.approx(62.5)
    assert decision["next_target_reps"] == 8
    assert decision["load_increased"] is True
```

- [ ] In the existing `test_all_engine_tools_are_listed`, extend the expected name set to:

```python
    assert {
        "assess_endurance_goal",
        "assess_strength_goal",
        "assess_hypertrophy_goal",
        "assess_bodycomp_goal",
        "predict_race_time",
        "compute_pace",
        "estimate_1rm",
        "prescribe_load",
        "prescribe_reps_load",
        "weekly_set_targets_for",
        "progress_double_progression",
        "compute_session_load",
        "compute_weekly_loads",
        "compute_acwr",
        "build_periodization_waves",
    } <= names
```

### Step 2 — run tests, expect FAIL

- [ ] `uv run pytest tests/server/test_engine_tools.py -q`
- Expected failures: each new tool call fails (FastMCP returns an unknown-tool error / `isError` with "Unknown tool"), and `test_all_engine_tools_are_listed` fails the subset assertion.

### Step 3 — implement

- [ ] Rewrite `src/performance_agent/engine/__init__.py` in full:

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
from performance_agent.engine.periodization import WeekLoad, build_weekly_waves
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
    "BodycompFeasibility",
    "FeasibilityResult",
    "ProgressionDecision",
    "TrainingAge",
    "WeekLoad",
    "WeeklySetTargets",
    "acute_chronic_ratio",
    "bodycomp_feasibility",
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
    "reps_for_percentage_rir",
    "riegel_predict",
    "session_rpe_load",
    "strength_feasibility",
    "weekly_loads",
    "weekly_set_targets",
]
```

- [ ] In `src/performance_agent/server/engine_tools.py`, extend the engine import block with `BodycompFeasibility, ProgressionDecision, WeeklySetTargets, bodycomp_feasibility, double_progression, hypertrophy_feasibility, percentage_for_reps_rir, strength_feasibility, weekly_set_targets` (keep sorted; `weekly_set_targets` gets the alias below to avoid a name clash with the tool). Import it aliased:

```python
from performance_agent.engine import weekly_set_targets as engine_weekly_set_targets
```

  (all other names go in the main sorted import block as usual).

- [ ] Add the TypedDict after `LoadPrescription`:

```python
class RepsLoadPrescription(TypedDict):
    """Percentage of 1RM and absolute load for a reps-at-RIR prescription."""

    percentage: float
    load_kg: float
```

- [ ] Add the six tools after `assess_endurance_goal`:

```python
def assess_strength_goal(
    current_one_rm_kg: float, target_one_rm_kg: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of a strength (1RM) goal (honest-coach verdict).

    Both loads are in kg for the same lift; training_age is one of beginner,
    intermediate, advanced. Sign convention: improvement_needed is positive
    when the target is above the current 1RM. Returns the success
    probability (0-1) with the drivers behind it (improvement_needed,
    required vs achievable weekly rates as fractions of current 1RM, their
    ratio). Always present the drivers alongside the probability, never the
    bare number.
    """
    return strength_feasibility(current_one_rm_kg, target_one_rm_kg, weeks, training_age)


def assess_hypertrophy_goal(
    target_lean_gain_kg: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of a lean-mass gain goal (honest-coach verdict).

    target_lean_gain_kg is lean mass in kg (positive); rates are ABSOLUTE
    kg/week, not fractions — improvement_needed carries the target gain in
    kg. Returns the success probability (0-1) with the drivers behind it
    (required vs achievable kg/week, their ratio). Always present the
    drivers alongside the probability, never the bare number.
    """
    return hypertrophy_feasibility(target_lean_gain_kg, weeks, training_age)


def assess_bodycomp_goal(
    current_weight_kg: float,
    current_body_fat_pct: float,
    target_body_fat_pct: float,
    weeks: int,
    sex: Literal["male", "female"],
) -> BodycompFeasibility:
    """Score the feasibility of a fat-loss goal (honest-coach verdict).

    Weight in kg; body-fat percentages in (3, 60) with target below current.
    REFUSES targets below the healthy minimum for the athlete's sex (5% male,
    12% female) with an error telling you to refer to a health professional —
    relay that refusal, do not work around it. exceeds_safe_rate=True means
    the deadline demands more than 1% bodyweight/week and risks muscle loss;
    say so explicitly. Always present the drivers (fat_mass_to_lose_kg,
    required vs achievable weekly loss as fractions of bodyweight, their
    ratio) alongside the probability, never the bare number.
    """
    return bodycomp_feasibility(
        current_weight_kg, current_body_fat_pct, target_body_fat_pct, weeks, sex
    )


def prescribe_reps_load(one_rm_kg: float, reps: int, rir: int) -> RepsLoadPrescription:
    """Prescribe the %1RM and absolute load for a reps-at-RIR target.

    Epley-based: percentage = 1 / (1 + (reps + rir) / 30). Effective reps
    (reps + rir) are capped at 18, and the model is only validated to ~12 —
    when reps + rir is 13-18, label the prescription as carrying extra
    uncertainty. Returns the fraction of 1RM and the load in kg.
    """
    percentage = percentage_for_reps_rir(reps, rir)
    return RepsLoadPrescription(
        percentage=percentage, load_kg=load_for_percentage(one_rm_kg, percentage)
    )


def weekly_set_targets_for(training_age: TrainingAge) -> WeeklySetTargets:
    """Weekly hard-set targets per muscle group for a training-age bucket.

    Returns minimum_effective, optimal_low-optimal_high (the range to
    program), and maximum_adaptive (do not exceed) in hard sets per muscle
    per week. Anchored on the volume dose-response meta-analysis in the
    corpus; the training-age spread is a team-chosen prior.
    """
    return engine_weekly_set_targets(training_age)


def progress_double_progression(
    reps_achieved: list[int],
    load_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    increment_kg: float,
) -> ProgressionDecision:
    """Decide the next session's load and rep target by double progression.

    Fill the rep range first, then add load: when every set reached
    rep_range_high, the load goes up by increment_kg and the target resets
    to rep_range_low; otherwise the load holds and the target is one rep
    above the lowest achieved set, capped at rep_range_high. Loads in kg;
    rep range must satisfy 1 <= low < high <= 18.
    """
    return double_progression(reps_achieved, load_kg, rep_range_low, rep_range_high, increment_kg)
```

- [ ] Extend `register()`:

```python
def register(mcp: FastMCP) -> None:
    """Register every engine tool on the server."""
    for tool in (
        assess_endurance_goal,
        assess_strength_goal,
        assess_hypertrophy_goal,
        assess_bodycomp_goal,
        predict_race_time,
        compute_pace,
        estimate_1rm,
        prescribe_load,
        prescribe_reps_load,
        weekly_set_targets_for,
        progress_double_progression,
        compute_session_load,
        compute_weekly_loads,
        compute_acwr,
        build_periodization_waves,
    ):
        mcp.tool()(tool)
```

### Step 4 — run tests, expect PASS

- [ ] `uv run pytest tests/server/test_engine_tools.py tests/engine -q`

### Step 5 — lint, typecheck, commit

- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest -q`
- [ ] `git add src/performance_agent/engine/__init__.py src/performance_agent/server/engine_tools.py tests/server/test_engine_tools.py && git commit -m "Expose six new engine tools over MCP"`

---

## Task 9 — docs tool count + full sweep

The server now exposes 32 tools (15 engine + 10 memory + 6 evidence + 1 report). Two doc
files carry counts. NOTE: `README.md` currently says 23 (stale — it was never bumped to 26
when installing.md was) and "9 tools" for the engine; both get corrected here. `README.md`
also has unrelated uncommitted wording changes in the working tree — leave those intact,
edit only the count sentences.

### Step 1 — no new test (docs-only task); instead capture the current suite state

- [ ] `uv run pytest -q` — full suite green before touching docs.

### Step 2 — verify the stale strings exist

- [ ] `grep -n "26 tools" docs/installing.md` — expect line ~205.
- [ ] `grep -n "23 tools" README.md && grep -n "9 tools" README.md` — expect lines ~109 and ~219.

### Step 3 — edit

- [ ] In `docs/installing.md`, replace exactly:

```
Ask your agent: *"List the performance-agent tools."* You should see 26 tools (9
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).
```

with:

```
Ask your agent: *"List the performance-agent tools."* You should see 32 tools (15
engine + 10 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).
```

- [ ] In `README.md`, replace exactly:

```
You should see 23 tools. Then ask:
```

with:

```
You should see 32 tools. Then ask:
```

- [ ] In `README.md`, replace exactly:

```
- ✅ MCP server exposing the engine as 9 tools — see [docs/installing.md](docs/installing.md)
```

with:

```
- ✅ MCP server exposing the engine as 15 tools — see [docs/installing.md](docs/installing.md)
```

### Step 4 — full verification sweep

- [ ] `uv run pytest -q` — full suite.
- [ ] `uv run pytest tests/skills -q` — skills declare tool subsets; adding tools must not break the harness. **If this fails, STOP and report — do not edit skill files.**
- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check` — clean.

### Step 5 — commit

- [ ] `git add docs/installing.md README.md && git commit -m "Update documented tool count to 32"`
  (This intentionally sweeps in README.md's pre-existing uncommitted wording changes — flag that in the final report so the user knows their in-progress README edits were committed alongside; if they object, they can split the commit.)

---

## Final verification checklist

- [ ] `uv run pytest -q` — entire suite green, including `tests/engine/test_engine_purity.py` (engine still stdlib-only) and `tests/skills`.
- [ ] `uv run ruff format . && uv run ruff check . && uv run ty check` — zero warnings.
- [ ] All new probabilities asserted in the open interval (0, 1) — unit tests and four Hypothesis properties (strength, hypertrophy, bodycomp, plus the pre-existing endurance one).
- [ ] 9 commits, one per task, imperative subjects.
- [ ] `git log --oneline -9` matches the plan's commit messages.
