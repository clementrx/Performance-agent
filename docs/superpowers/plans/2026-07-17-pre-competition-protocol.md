# Pre-Competition Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `docs/superpowers/specs/2026-07-17-pre-competition-protocol-design.md`: the per-event, day-by-day competition protocol — pure engine math (carb loading, attempts, pacing, trigger window), versioned `competition/` doc family with a phone-ready HTML page, five MCP tools, the `competition_protocol` due action, one new skill and five edited ones.

**Architecture:** Engine stays pure (`engine/competition.py`, no memory imports). Schemas in `memory/schemas.py`, persistence in `memory/store.py` (yaml source + rendered md, like programs), rendering in `programs/render_protocol.py` (markdown) and `programs/render_protocol_html.py` (phone page). Citation resolution stays server-side (`server/competition_tools.py`). Diligence trigger uses the population `mixed` taper prior (no per-athlete modality is persisted — spec §9 fallback); the skill computes the individualized window at authoring time.

**Tech Stack:** Python 3.13, uv, pydantic v2, FastMCP, pytest. Run everything with `uv run`. Run pytest as `rtk proxy uv run pytest …` (plain rtk swallows the output) and verify every commit landed with `git log --oneline -1`.

**Branch:** work continues on `pre-competition-protocol-spec` (spec already committed). Version bump/release is NOT part of this plan.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/performance_agent/engine/competition.py` | create | Pure math: carb loading, attempt selection, pacing plan, trigger window |
| `src/performance_agent/memory/schemas.py` | modify | Protocol schemas: `ProtocolLine`, `ProtocolDay`, `PacingSegment`, `AttemptPlan`, `FuelingPlan`, `DocumentedPractice`, `CompetitionProtocol` |
| `src/performance_agent/programs/render_protocol.py` | create | `protocol_citation_ids`, deterministic markdown rendering |
| `src/performance_agent/memory/store.py` | modify | `save_competition_protocol`, `read_competition_protocol`, `latest_competition_protocol_version` |
| `src/performance_agent/programs/render_protocol_html.py` | create | Standalone offline phone page (no JS, en/fr/es, ⚠ warnings, starred sources) |
| `src/performance_agent/server/competition_tools.py` | create | 5 MCP tools; citations resolved server-side |
| `src/performance_agent/server/app.py` | modify | Register `competition_tools` |
| `src/performance_agent/engine/diligence.py` | modify | `UpcomingEvent` protocol fields + `competition_protocol` due action |
| `src/performance_agent/memory/diligence.py` | modify | Fill protocol window + has-protocol facts |
| `src/performance_agent/server/memory_tools.py` | modify | `list_due_actions` docstring |
| `skills/pre-competition/SKILL.md` | create | The protocol author ritual |
| 5 existing `skills/*/SKILL.md` | modify | coach routing, checkin debrief, session-day J0, deep-research wave, review gate |
| `tests/skills/test_structure.py` | modify | EXPECTED_SKILLS + protocol invariants |
| `README.md` | modify | Tool/skill counts + feature bullet |

---

## Phase 1 — Engine

### Task 1: `engine/competition.py` — carb-loading targets

**Files:**
- Create: `src/performance_agent/engine/competition.py`
- Test: `tests/engine/test_competition.py`

- [x] **Step 1: Write the failing tests**

Create `tests/engine/test_competition.py`:

```python
"""Pure pre-competition math: carb loading, attempts, pacing, window."""

import pytest

from performance_agent.engine.competition import carb_loading_targets


def test_long_event_loads_8_to_12_g_per_kg_over_48h():
    result = carb_loading_targets(70.0, 180.0)
    assert result.loading_required is True
    assert (result.carb_g_per_kg_low, result.carb_g_per_kg_high) == (8.0, 12.0)
    assert (result.carb_g_per_day_low, result.carb_g_per_day_high) == (560.0, 840.0)
    assert result.window_hours == 48
    assert (result.race_carb_g_per_h_low, result.race_carb_g_per_h_high) == (60.0, 90.0)


def test_mid_event_loads_6_to_8_g_per_kg_over_24h():
    result = carb_loading_targets(60.0, 75.0)
    assert result.loading_required is True
    assert (result.carb_g_per_kg_low, result.carb_g_per_kg_high) == (6.0, 8.0)
    assert (result.carb_g_per_day_low, result.carb_g_per_day_high) == (360.0, 480.0)
    assert result.window_hours == 24
    assert (result.race_carb_g_per_h_low, result.race_carb_g_per_h_high) == (30.0, 60.0)


def test_short_event_needs_no_loading_and_no_race_fuel():
    result = carb_loading_targets(80.0, 45.0)
    assert result.loading_required is False
    assert result.carb_g_per_kg_low is None
    assert result.carb_g_per_day_high is None
    assert result.window_hours is None
    assert result.race_carb_g_per_h_low is None


def test_carb_guards_reject_out_of_range_inputs():
    with pytest.raises(ValueError, match="body_mass_kg"):
        carb_loading_targets(20.0, 180.0)
    with pytest.raises(ValueError, match="event_duration_min"):
        carb_loading_targets(70.0, 2.0)
    with pytest.raises(ValueError, match="event_duration_min"):
        carb_loading_targets(70.0, 2000.0)
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py -q` — Expected: FAIL (`ModuleNotFoundError`)

- [x] **Step 3: Implement**

Create `src/performance_agent/engine/competition.py`:

```python
"""Pre-competition math: carb loading, attempt selection, pacing, trigger window.

Pure and deterministic — no I/O, no memory imports. Thresholds are corpus-cited
priors (IOC/Burke carbohydrate consensus, powerlifting attempt-selection
convention, the taper meta-analysis) recorded as constants with their rationale.
Anything the literature does not quantify (meal timing, water/sodium
manipulation, weight-cut tactics) deliberately has NO function here: it is
sourced advice with warnings in the protocol document, never engine math.
"""

from dataclasses import dataclass

_MIN_BODY_MASS_KG = 30.0
_MAX_BODY_MASS_KG = 250.0
_MIN_EVENT_MIN = 5.0
_MAX_EVENT_MIN = 1440.0
# Carb-loading priors (IOC consensus): events >= 90 min load 8-12 g/kg/day over
# the final ~48 h; 60-90 min take 6-8 g/kg/day the day before; shorter events
# need no loading. In-race: none under 60 min, 30-60 g/h up to ~2.5 h, 60-90 g/h
# beyond (multiple transportable carbohydrates).
_LONG_EVENT_MIN = 90.0
_MID_EVENT_MIN = 60.0
_RACE_FUEL_LONG_MIN = 150.0


@dataclass(frozen=True)
class CarbLoadingTargets:
    """Evidence-based carbohydrate targets for the final window and the race."""

    loading_required: bool
    carb_g_per_kg_low: float | None = None
    carb_g_per_kg_high: float | None = None
    carb_g_per_day_low: float | None = None
    carb_g_per_day_high: float | None = None
    window_hours: int | None = None
    race_carb_g_per_h_low: float | None = None
    race_carb_g_per_h_high: float | None = None


def carb_loading_targets(body_mass_kg: float, event_duration_min: float) -> CarbLoadingTargets:
    """Carb-loading and in-race fueling ranges from body mass and event duration."""
    if not _MIN_BODY_MASS_KG <= body_mass_kg <= _MAX_BODY_MASS_KG:
        msg = (
            f"body_mass_kg must be within [{_MIN_BODY_MASS_KG}, {_MAX_BODY_MASS_KG}], "
            f"got {body_mass_kg!r}"
        )
        raise ValueError(msg)
    if not _MIN_EVENT_MIN <= event_duration_min <= _MAX_EVENT_MIN:
        msg = (
            f"event_duration_min must be within [{_MIN_EVENT_MIN}, {_MAX_EVENT_MIN}], "
            f"got {event_duration_min!r}"
        )
        raise ValueError(msg)
    if event_duration_min < _MID_EVENT_MIN:
        return CarbLoadingTargets(loading_required=False)
    if event_duration_min >= _LONG_EVENT_MIN:
        g_low, g_high, window = 8.0, 12.0, 48
    else:
        g_low, g_high, window = 6.0, 8.0, 24
    if event_duration_min > _RACE_FUEL_LONG_MIN:
        race_low, race_high = 60.0, 90.0
    else:
        race_low, race_high = 30.0, 60.0
    return CarbLoadingTargets(
        loading_required=True,
        carb_g_per_kg_low=g_low,
        carb_g_per_kg_high=g_high,
        carb_g_per_day_low=round(g_low * body_mass_kg, 1),
        carb_g_per_day_high=round(g_high * body_mass_kg, 1),
        window_hours=window,
        race_carb_g_per_h_low=race_low,
        race_carb_g_per_h_high=race_high,
    )
```

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py tests/engine/test_engine_purity.py -q` — Expected: PASS (purity guard must stay green)

- [x] **Step 5: Lint + commit**

```bash
uv run ruff check src/performance_agent/engine/competition.py tests/engine/test_competition.py && uv run ty check
git add src/performance_agent/engine/competition.py tests/engine/test_competition.py
git commit -m "Add carb-loading targets to the competition engine

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 2: `select_attempts`

**Files:**
- Modify: `src/performance_agent/engine/competition.py` (append)
- Test: `tests/engine/test_competition.py` (append)

- [x] **Step 1: Write the failing tests** (append)

```python
from performance_agent.engine.competition import select_attempts


def test_attempts_goal_within_range_becomes_third():
    result = select_attempts(200.0, 205.0)
    assert result.opener_kg == 182.5   # 0.91 * 200 = 182 -> 182.5
    assert result.second_kg == 192.5   # 0.96 * 200 = 192 -> 192.5
    assert result.third_kg == 205.0
    assert result.flags == ()


def test_attempts_goal_beyond_e1rm_is_flagged_and_capped():
    result = select_attempts(200.0, 215.0)  # > 105% of e1RM
    assert result.third_kg == 202.5         # 1.01 * 200 = 202 -> 202.5
    assert "goal_beyond_e1rm" in result.flags


def test_attempts_stay_strictly_increasing_after_rounding():
    result = select_attempts(52.0, 50.0)
    assert result.opener_kg < result.second_kg < result.third_kg


def test_attempts_guards():
    with pytest.raises(ValueError, match="e1rm_kg"):
        select_attempts(10.0, 50.0)
    with pytest.raises(ValueError, match="goal_kg"):
        select_attempts(200.0, 0.0)
    with pytest.raises(ValueError, match="rounding_kg"):
        select_attempts(200.0, 205.0, rounding_kg=0.0)
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py -q` — Expected: FAIL (`ImportError: select_attempts`)

- [x] **Step 3: Implement** (append to `engine/competition.py`)

```python
from performance_agent.engine.progression import round_to_increment

_MIN_E1RM_KG = 20.0
_MAX_E1RM_KG = 600.0
# Attempt-selection convention (powerlifting coaching literature): opener ~91%
# of e1RM (a weight you can triple), second ~96%, third at the goal when the
# data supports it — 93-105% of e1RM — else a conservative ~101% PR attempt.
_OPENER_PCT = 0.91
_SECOND_PCT = 0.96
_THIRD_FALLBACK_PCT = 1.01
_GOAL_MIN_PCT = 0.93
_GOAL_MAX_PCT = 1.05


@dataclass(frozen=True)
class AttemptSelection:
    """Opening, second and third attempts for one lift on meet day."""

    opener_kg: float
    second_kg: float
    third_kg: float
    flags: tuple[str, ...] = ()


def select_attempts(
    e1rm_kg: float, goal_kg: float, rounding_kg: float = 2.5
) -> AttemptSelection:
    """Three meet-day attempts from the estimated 1RM and the athlete's goal.

    The honesty gate lives here: a goal outside 93-105% of e1RM is never
    silently endorsed — the third falls back to ~101% and the goal_beyond_e1rm
    flag tells the skill to name the gap.
    """
    if not _MIN_E1RM_KG <= e1rm_kg <= _MAX_E1RM_KG:
        msg = f"e1rm_kg must be within [{_MIN_E1RM_KG}, {_MAX_E1RM_KG}], got {e1rm_kg!r}"
        raise ValueError(msg)
    if goal_kg <= 0:
        msg = f"goal_kg must be positive, got {goal_kg!r}"
        raise ValueError(msg)
    if rounding_kg <= 0:
        msg = f"rounding_kg must be positive, got {rounding_kg!r}"
        raise ValueError(msg)
    opener = round_to_increment(_OPENER_PCT * e1rm_kg, rounding_kg)
    second = round_to_increment(_SECOND_PCT * e1rm_kg, rounding_kg)
    flags: tuple[str, ...] = ()
    if _GOAL_MIN_PCT * e1rm_kg <= goal_kg <= _GOAL_MAX_PCT * e1rm_kg:
        third = round_to_increment(goal_kg, rounding_kg)
    else:
        third = round_to_increment(_THIRD_FALLBACK_PCT * e1rm_kg, rounding_kg)
        flags = ("goal_beyond_e1rm",)
    if second <= opener:
        second = opener + rounding_kg
    if third <= second:
        third = second + rounding_kg
    return AttemptSelection(opener, second, third, flags)
```

(Move the `from performance_agent.engine.progression import round_to_increment` line up into the module's import block.)

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py tests/engine/test_engine_purity.py -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/engine/competition.py tests/engine/test_competition.py
git commit -m "Add meet-day attempt selection with the e1RM honesty gate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 3: `pacing_plan` + `protocol_window_days`

**Files:**
- Modify: `src/performance_agent/engine/competition.py` (append)
- Test: `tests/engine/test_competition.py` (append)

- [x] **Step 1: Write the failing tests** (append)

```python
from performance_agent.engine.competition import pacing_plan, protocol_window_days


def test_even_pacing_splits_evenly_and_lands_on_target():
    splits = pacing_plan(10000.0, 2400.0, segment_m=1000.0, strategy="even")
    assert len(splits) == 10
    assert all(s.target_pace_s_per_km == 240.0 for s in splits)
    assert splits[-1].cumulative_time_s == pytest.approx(2400.0, abs=1.0)


def test_negative_split_first_half_slower_lands_on_target():
    splits = pacing_plan(10000.0, 2400.0, segment_m=1000.0, strategy="negative")
    assert splits[0].target_pace_s_per_km > splits[-1].target_pace_s_per_km
    assert splits[0].target_pace_s_per_km == pytest.approx(242.4, abs=0.01)
    assert splits[-1].cumulative_time_s == pytest.approx(2400.0, abs=1.0)


def test_pacing_remainder_becomes_last_short_segment():
    splits = pacing_plan(10500.0, 2520.0, segment_m=1000.0, strategy="even")
    assert len(splits) == 11
    assert splits[-1].distance_m == pytest.approx(500.0)


def test_pacing_oversized_segment_yields_single_split():
    splits = pacing_plan(5000.0, 1200.0, segment_m=8000.0, strategy="even")
    assert len(splits) == 1
    assert splits[0].distance_m == pytest.approx(5000.0)


def test_pacing_guards():
    with pytest.raises(ValueError, match="distance_m"):
        pacing_plan(0.0, 2400.0)
    with pytest.raises(ValueError, match="target_time_s"):
        pacing_plan(10000.0, -5.0)
    with pytest.raises(ValueError, match="strategy"):
        pacing_plan(10000.0, 2400.0, strategy="wild")


def test_window_scales_with_priority():
    assert protocol_window_days(10, "A") == 10
    assert protocol_window_days(4, "A") == 7    # floor
    assert protocol_window_days(25, "A") == 21  # ceiling
    assert protocol_window_days(5, "B") == 5
    assert protocol_window_days(2, "B") == 3    # floor
    assert protocol_window_days(12, "B") == 10  # ceiling
    assert protocol_window_days(10, "C") == 0   # never auto-surfaced


def test_window_guards():
    with pytest.raises(ValueError, match="taper_days"):
        protocol_window_days(-1, "A")
    with pytest.raises(ValueError, match="priority"):
        protocol_window_days(10, "X")
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py -q` — Expected: FAIL (`ImportError`)

- [x] **Step 3: Implement** (append to `engine/competition.py`)

```python
# Negative-split prior: first half ~1% slower than mean pace, second half
# balanced exactly so the cumulative time lands on the target.
_NEGATIVE_SPLIT_PCT = 0.01
# Protocol windows per priority (spec §4): A events open with the taper but
# never closer than a week nor further than three; B events get a short window;
# C events are never auto-surfaced.
_WINDOW_A_MIN, _WINDOW_A_MAX = 7, 21
_WINDOW_B_MIN, _WINDOW_B_MAX = 3, 10


@dataclass(frozen=True)
class PacingSplit:
    """One race segment: its target pace and the cumulative time at its end."""

    label: str
    distance_m: float
    target_pace_s_per_km: float
    cumulative_time_s: float


def _segment_distances(distance_m: float, segment_m: float) -> list[float]:
    full = int(distance_m // segment_m)
    segments = [segment_m] * full
    remainder = distance_m - full * segment_m
    if remainder > 1.0:
        segments.append(remainder)
    elif not segments:
        segments = [distance_m]
    return segments


def pacing_plan(
    distance_m: float,
    target_time_s: float,
    segment_m: float = 1000.0,
    strategy: str = "even",
) -> list[PacingSplit]:
    """Distribute a target time over segments (even or negative split).

    The target comes from the athlete's goal or predict_race_time upstream —
    this function only distributes it; cumulative time always lands on the
    target within a second.
    """
    if distance_m <= 0:
        msg = f"distance_m must be positive, got {distance_m!r}"
        raise ValueError(msg)
    if target_time_s <= 0:
        msg = f"target_time_s must be positive, got {target_time_s!r}"
        raise ValueError(msg)
    if segment_m <= 0:
        msg = f"segment_m must be positive, got {segment_m!r}"
        raise ValueError(msg)
    if strategy not in ("even", "negative"):
        msg = f"strategy must be 'even' or 'negative', got {strategy!r}"
        raise ValueError(msg)
    distances = _segment_distances(distance_m, segment_m)
    mean_pace = target_time_s / (distance_m / 1000.0)
    halfway = distance_m / 2.0
    paces: list[float]
    if strategy == "even" or len(distances) == 1:
        paces = [mean_pace] * len(distances)
    else:
        start = 0.0
        first_half = []
        for dist in distances:
            first_half.append(start + dist / 2.0 < halfway)
            start += dist
        d1_km = sum(d for d, f in zip(distances, first_half, strict=True) if f) / 1000.0
        d2_km = sum(d for d, f in zip(distances, first_half, strict=True) if not f) / 1000.0
        pace_1 = mean_pace * (1 + _NEGATIVE_SPLIT_PCT)
        pace_2 = (target_time_s - pace_1 * d1_km) / d2_km if d2_km else mean_pace
        paces = [pace_1 if f else pace_2 for f in first_half]
    splits: list[PacingSplit] = []
    cumulative = 0.0
    position = 0.0
    for dist, pace in zip(distances, paces, strict=True):
        cumulative += pace * dist / 1000.0
        position += dist
        splits.append(
            PacingSplit(
                label=f"{position / 1000.0:g} km",
                distance_m=dist,
                target_pace_s_per_km=round(pace, 1),
                cumulative_time_s=round(cumulative, 1),
            )
        )
    return splits


def protocol_window_days(taper_days: int, priority: str) -> int:
    """The adaptive due-action window: taper-driven, clamped per priority."""
    if taper_days < 0:
        msg = f"taper_days must be non-negative, got {taper_days!r}"
        raise ValueError(msg)
    if priority not in ("A", "B", "C"):
        msg = f"priority must be A, B or C, got {priority!r}"
        raise ValueError(msg)
    if priority == "A":
        return min(max(taper_days, _WINDOW_A_MIN), _WINDOW_A_MAX)
    if priority == "B":
        return min(max(taper_days, _WINDOW_B_MIN), _WINDOW_B_MAX)
    return 0
```

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/engine/test_competition.py tests/engine/test_engine_purity.py -q` — Expected: PASS. Note the rounded paces mean cumulative sums drift by < 1 s — the tests use `abs=1.0`; never widen past one second.

- [x] **Step 5: Lint + commit**

```bash
uv run ruff check src/performance_agent/engine/competition.py tests/engine/test_competition.py && uv run ty check
git add src/performance_agent/engine/competition.py tests/engine/test_competition.py
git commit -m "Add pacing plan and adaptive protocol window to the engine

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

---

## Phase 2 — Schemas, rendering, store

### Task 4: Protocol schemas

**Files:**
- Modify: `src/performance_agent/memory/schemas.py` (insert the whole block right BEFORE `class CalendarEvent`)
- Test: `tests/memory/test_schemas_protocol.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_schemas_protocol.py`:

```python
"""CompetitionProtocol schemas: structure and validator errors."""

from datetime import date

import pytest
from pydantic import ValidationError

from performance_agent.memory.schemas import (
    AttemptPlan,
    CompetitionProtocol,
    DocumentedPractice,
    FuelingPlan,
    Guidance,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)

EVENT_DATE = date(2026, 8, 1)


def _day(offset, title="Race day"):
    return ProtocolDay(
        day_offset=offset,
        title=title,
        lines=[ProtocolLine(text="Easy 20 min shakeout.", time_hint="07:30")],
    )


def _protocol(**overrides):
    fields = {
        "version": 1,
        "event_id": "nationals",
        "event_date": EVENT_DATE,
        "goal_id": "sub-40-10k",
        "created_on": date(2026, 7, 25),
        "window_days": 7,
        "days": [_day(-2, "Carb load"), _day(-1, "Rest"), _day(0)],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_valid_protocol_with_all_sections():
    protocol = _protocol(
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        attempts=[
            AttemptPlan(
                lift="Squat", e1rm_kg=200, opener_kg=182.5, second_kg=192.5,
                third_kg=205, basis="engine", flags=[],
            )
        ],
        fueling=FuelingPlan(
            carb_g_per_kg_low=8, carb_g_per_kg_high=12, window_hours=48,
            race_carb_g_per_h_low=60, race_carb_g_per_h_high=90,
        ),
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Described in physique literature; effect sizes small.",
                warning="Dehydration risk — never do this without supervision.",
            )
        ],
        checklist=["Pin race bib", "Bottle in fridge"],
        advice=[Guidance(text="Nothing new on race day.")],
    )
    assert protocol.days[-1].day_offset == 0
    assert protocol.practices[0].warning.startswith("Dehydration")


def test_days_must_be_sorted_unique_and_end_at_zero():
    with pytest.raises(ValidationError, match="day_offset"):
        _protocol(days=[_day(0), _day(-1)])
    with pytest.raises(ValidationError, match="day_offset"):
        _protocol(days=[_day(-1), _day(-1), _day(0)])
    with pytest.raises(ValidationError, match="J0"):
        _protocol(days=[_day(-2), _day(-1)])


def test_window_must_cover_the_days_span():
    with pytest.raises(ValidationError, match="window_days"):
        _protocol(window_days=1, days=[_day(-5), _day(0)])


def test_practice_requires_a_warning():
    with pytest.raises(ValidationError):
        DocumentedPractice(name="X", summary="Y", warning="")


def test_attempts_must_strictly_increase():
    with pytest.raises(ValidationError, match="increasing"):
        AttemptPlan(
            lift="Squat", e1rm_kg=200, opener_kg=190, second_kg=190,
            third_kg=200, basis="engine",
        )


def test_fueling_low_cannot_exceed_high():
    with pytest.raises(ValidationError, match="carb_g_per_kg"):
        FuelingPlan(carb_g_per_kg_low=10, carb_g_per_kg_high=8, window_hours=48)
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/memory/test_schemas_protocol.py -q` — Expected: FAIL (`ImportError`)

- [x] **Step 3: Implement** — in `src/performance_agent/memory/schemas.py`, insert immediately before `class CalendarEvent`:

```python
# --- Competition protocol (per-event final-days plan) ---------------------


class ProtocolLine(BaseModel):
    """One line of a protocol day: what to do, optionally when and why."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    time_hint: str | None = Field(default=None, max_length=20)
    cite: str | None = None
    warning: bool = False


class ProtocolDay(BaseModel):
    """One day of the pre-competition window; day_offset 0 is the event day."""

    model_config = ConfigDict(extra="forbid")

    day_offset: int = Field(ge=-21, le=0)
    title: str = Field(min_length=1, max_length=80)
    lines: list[ProtocolLine] = Field(min_length=1)


class PacingSegment(BaseModel):
    """One race segment with its target pace and cumulative split."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    distance_m: float = Field(gt=0)
    target_pace_s_per_km: float = Field(gt=0)
    cumulative_time_s: float = Field(gt=0)


class AttemptPlan(BaseModel):
    """Meet-day attempts for one lift; engine-computed or athlete-agreed."""

    model_config = ConfigDict(extra="forbid")

    lift: str = Field(min_length=1, max_length=60)
    e1rm_kg: float = Field(gt=0)
    opener_kg: float = Field(gt=0)
    second_kg: float = Field(gt=0)
    third_kg: float = Field(gt=0)
    basis: Literal["engine", "agreed"]
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _attempts_increase(self) -> Self:
        if not self.opener_kg < self.second_kg < self.third_kg:
            msg = (
                f"{self.lift}: attempts must be strictly increasing, got "
                f"{self.opener_kg}/{self.second_kg}/{self.third_kg}"
            )
            raise ValueError(msg)
        return self


class FuelingPlan(BaseModel):
    """Engine-computed carbohydrate targets for the final window and the race."""

    model_config = ConfigDict(extra="forbid")

    carb_g_per_kg_low: float = Field(gt=0)
    carb_g_per_kg_high: float = Field(gt=0)
    window_hours: int = Field(gt=0)
    race_carb_g_per_h_low: float | None = Field(default=None, ge=0)
    race_carb_g_per_h_high: float | None = Field(default=None, ge=0)
    cite: str | None = None

    @model_validator(mode="after")
    def _low_not_above_high(self) -> Self:
        if self.carb_g_per_kg_low > self.carb_g_per_kg_high:
            msg = (
                "carb_g_per_kg low must not exceed high, got "
                f"{self.carb_g_per_kg_low} > {self.carb_g_per_kg_high}"
            )
            raise ValueError(msg)
        return self


class DocumentedPractice(BaseModel):
    """A risky-but-documented practice: described with its grade, never dosed.

    warning is schema-required and non-empty — a practice cannot be stored
    without one (owner decision: labeled advice, never engine-quantified).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=400)
    cite: str | None = None
    warning: str = Field(min_length=1, max_length=300)


class CompetitionProtocol(BaseModel):
    """The per-event final-days plan: days J-N to J0 plus computed sections."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    version: int = Field(ge=1)
    event_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    event_date: date
    goal_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    created_on: date
    reason: str | None = None
    window_days: int = Field(ge=1, le=21)
    days: list[ProtocolDay] = Field(min_length=1)
    pacing: list[PacingSegment] = Field(default_factory=list)
    attempts: list[AttemptPlan] = Field(default_factory=list)
    fueling: FuelingPlan | None = None
    practices: list[DocumentedPractice] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    advice: list[Guidance] = Field(default_factory=list)

    @model_validator(mode="after")
    def _days_cover_the_window(self) -> Self:
        offsets = [day.day_offset for day in self.days]
        if offsets != sorted(offsets) or len(set(offsets)) != len(offsets):
            msg = f"day_offset values must be unique and increasing, got {offsets}"
            raise ValueError(msg)
        if offsets[-1] != 0:
            msg = f"the last day must be J0 (day_offset 0), got {offsets[-1]}"
            raise ValueError(msg)
        if self.window_days < -offsets[0]:
            msg = (
                f"window_days ({self.window_days}) must cover the earliest day "
                f"(J{offsets[0]})"
            )
            raise ValueError(msg)
        return self
```

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/memory/test_schemas_protocol.py tests/memory/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/performance_agent/memory/schemas.py tests/memory/test_schemas_protocol.py
git commit -m "Add competition protocol schemas

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 5: `programs/render_protocol.py` — citation ids + markdown

**Files:**
- Create: `src/performance_agent/programs/render_protocol.py`
- Test: `tests/programs/test_render_protocol.py`

- [x] **Step 1: Write the failing tests**

Create `tests/programs/test_render_protocol.py`:

```python
"""Deterministic protocol markdown rendering and citation ordering."""

from datetime import date

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import (
    AttemptPlan,
    CompetitionProtocol,
    DocumentedPractice,
    FuelingPlan,
    Guidance,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.programs.render_protocol import (
    protocol_citation_ids,
    render_protocol,
)

CITATIONS = {
    "carb-2017": ResolvedCitation(
        citation="Burke et al. (2017). Carbohydrates for training and competition. "
        "DOI: 10.1080/02640414.2011.585473.",
        stars="★★★★★",
        doi="10.1080/02640414.2011.585473",
        pmid=None,
    )
}


def _full_protocol():
    return CompetitionProtocol(
        version=1,
        event_id="nationals",
        event_date=date(2026, 8, 1),
        goal_id="sub-40-10k",
        created_on=date(2026, 7, 25),
        window_days=7,
        advice=[Guidance(text="Nothing new on race day.", cite="carb-2017")],
        days=[
            ProtocolDay(
                day_offset=-1,
                title="Carb load",
                lines=[ProtocolLine(text="8-12 g/kg carbs.", cite="carb-2017")],
            ),
            ProtocolDay(
                day_offset=0,
                title="Race day",
                lines=[ProtocolLine(text="Breakfast 3 h before.", time_hint="06:00")],
            ),
        ],
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        attempts=[
            AttemptPlan(
                lift="Squat", e1rm_kg=200, opener_kg=182.5, second_kg=192.5,
                third_kg=205, basis="engine",
            )
        ],
        fueling=FuelingPlan(carb_g_per_kg_low=8, carb_g_per_kg_high=12, window_hours=48),
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Documented in physique prep; small effect sizes.",
                warning="Dehydration risk; supervision required.",
            )
        ],
        checklist=["Pin race bib"],
    )


def test_citation_ids_ordered_and_deduped():
    assert protocol_citation_ids(_full_protocol()) == ["carb-2017"]


def test_markdown_renders_all_sections():
    text = render_protocol(_full_protocol(), citations=CITATIONS)
    assert "# Competition protocol v1 — nationals — 2026-08-01" in text
    assert "## J-1 — Carb load" in text
    assert "## J0 — Race day" in text
    assert "[06:00]" in text
    assert "## Pacing" in text
    assert "## Attempts" in text
    assert "182.5 / 192.5 / 205" in text
    assert "## Fueling" in text
    assert "## Documented practices" in text
    assert "⚠ Dehydration risk" in text
    assert "## Checklist" in text
    assert "## Sources" in text
    assert "★★★★★" in text


def test_markdown_without_optional_sections_is_lean():
    protocol = CompetitionProtocol(
        version=1,
        event_id="local-5k",
        event_date=date(2026, 8, 1),
        goal_id="sub-20-5k",
        created_on=date(2026, 7, 28),
        window_days=3,
        days=[
            ProtocolDay(
                day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up 15 min.")]
            )
        ],
    )
    text = render_protocol(protocol)
    assert "## Pacing" not in text
    assert "## Attempts" not in text
    assert "## Sources" not in text
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/programs/test_render_protocol.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/programs/render_protocol.py`:

```python
"""Deterministic CompetitionProtocol -> markdown (the human/audit view).

Generated at save time from the structured protocol, like the program markdown,
so the document can never drift from the source of truth. Citation numbering
order (advice, then day lines, then fueling, then practices) is shared with the
HTML page via protocol_citation_ids.
"""

from collections.abc import Mapping

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import CompetitionProtocol


def protocol_citation_ids(protocol: CompetitionProtocol) -> list[str]:
    """Every corpus id the protocol cites, in first-appearance order, deduplicated."""
    ids: list[str] = []
    seen: set[str] = set()

    def add(cite: str | None) -> None:
        if cite and cite not in seen:
            seen.add(cite)
            ids.append(cite)

    for guidance in protocol.advice:
        add(guidance.cite)
    for day in protocol.days:
        for line in day.lines:
            add(line.cite)
    if protocol.fueling is not None:
        add(protocol.fueling.cite)
    for practice in protocol.practices:
        add(practice.cite)
    return ids


def _day_label(offset: int) -> str:
    return "J0" if offset == 0 else f"J{offset}"


def _num(value: float) -> str:
    return f"{value:g}"


def _line_text(text: str, time_hint: str | None, cite: str | None, warning: bool) -> str:
    parts = []
    if time_hint:
        parts.append(f"[{time_hint}]")
    parts.append(text)
    if warning:
        parts.append("⚠")
    if cite:
        parts.append(f"[{cite}]")
    return "- " + " ".join(parts)


def _sections(protocol: CompetitionProtocol) -> list[str]:
    lines: list[str] = []
    if protocol.advice:
        lines += ["", "## Advice"]
        for guidance in protocol.advice:
            suffix = f" [{guidance.cite}]" if guidance.cite else ""
            lines.append(f"- {guidance.text}{suffix}")
    for day in protocol.days:
        lines += ["", f"## {_day_label(day.day_offset)} — {day.title}"]
        for line in day.lines:
            lines.append(_line_text(line.text, line.time_hint, line.cite, line.warning))
    if protocol.pacing:
        lines += ["", "## Pacing", "", "| Segment | Distance | Pace | Cumulative |", "|---|---|---|---|"]
        for seg in protocol.pacing:
            minutes, seconds = divmod(round(seg.target_pace_s_per_km), 60)
            total_min, total_s = divmod(round(seg.cumulative_time_s), 60)
            lines.append(
                f"| {seg.label} | {_num(seg.distance_m)} m | {minutes}:{seconds:02d}/km "
                f"| {total_min}:{total_s:02d} |"
            )
    if protocol.attempts:
        lines += ["", "## Attempts"]
        for attempt in protocol.attempts:
            flags = f" ({', '.join(attempt.flags)})" if attempt.flags else ""
            lines.append(
                f"- {attempt.lift}: {_num(attempt.opener_kg)} / {_num(attempt.second_kg)} "
                f"/ {_num(attempt.third_kg)} kg — e1RM {_num(attempt.e1rm_kg)} kg, "
                f"{attempt.basis}{flags}"
            )
    if protocol.fueling is not None:
        fueling = protocol.fueling
        lines += ["", "## Fueling"]
        cite = f" [{fueling.cite}]" if fueling.cite else ""
        lines.append(
            f"- {_num(fueling.carb_g_per_kg_low)}-{_num(fueling.carb_g_per_kg_high)} g/kg/day "
            f"carbs over the final {fueling.window_hours} h{cite}"
        )
        if fueling.race_carb_g_per_h_low is not None and fueling.race_carb_g_per_h_high is not None:
            lines.append(
                f"- In race: {_num(fueling.race_carb_g_per_h_low)}-"
                f"{_num(fueling.race_carb_g_per_h_high)} g/h"
            )
    if protocol.practices:
        lines += ["", "## Documented practices"]
        for practice in protocol.practices:
            cite = f" [{practice.cite}]" if practice.cite else ""
            lines.append(f"- **{practice.name}** — {practice.summary}{cite}")
            lines.append(f"  ⚠ {practice.warning}")
    if protocol.checklist:
        lines += ["", "## Checklist"]
        lines += [f"- [ ] {item}" for item in protocol.checklist]
    return lines


def render_protocol(
    protocol: CompetitionProtocol,
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str:
    """Render the protocol to markdown (deterministic; Sources iff citations)."""
    lines = [
        f"# Competition protocol v{protocol.version} — {protocol.event_id} — "
        f"{protocol.event_date.isoformat()}",
        "",
        f"- Window: J-{protocol.window_days} → J0",
        f"- Goal: {protocol.goal_id}",
    ]
    if protocol.reason:
        lines.append(f"- Reason: {protocol.reason}")
    lines += _sections(protocol)
    if citations is not None:
        ids = [cid for cid in protocol_citation_ids(protocol) if cid in citations]
        if ids:
            lines += ["", "## Sources"]
            for number, cid in enumerate(ids, start=1):
                resolved = citations[cid]
                lines.append(f"{number}. {resolved.stars} {resolved.citation}")
    return "\n".join(lines).strip() + "\n"
```

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/programs/test_render_protocol.py -q` — Expected: PASS

- [x] **Step 5: Lint + commit**

```bash
uv run ruff check src/performance_agent/programs/render_protocol.py tests/programs/test_render_protocol.py && uv run ty check
git add src/performance_agent/programs/render_protocol.py tests/programs/test_render_protocol.py
git commit -m "Render competition protocols to markdown

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 6: Store — save/read/latest per event

**Files:**
- Modify: `src/performance_agent/memory/store.py` (constants + append at end)
- Test: `tests/memory/test_store_protocol.py`

- [x] **Step 1: Write the failing tests**

Create `tests/memory/test_store_protocol.py`:

```python
"""Competition protocols: per-event immutable versions, calendar validation."""

from datetime import date

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    CalendarEvent,
    CompetitionProtocol,
    ProtocolDay,
    ProtocolLine,
)

TODAY = date(2026, 7, 25)
EVENT_DATE = date(2026, 8, 1)


def _seed_event(base, event_id="nationals", event_date=EVENT_DATE):
    store.upsert_calendar_event(
        base,
        CalendarEvent(
            id=event_id, date=event_date, kind="competition", priority="A", label="Nationals"
        ),
    )


def _protocol(event_id="nationals", event_date=EVENT_DATE, **overrides):
    fields = {
        "version": 1,
        "event_id": event_id,
        "event_date": event_date,
        "goal_id": "sub-40-10k",
        "created_on": TODAY,
        "window_days": 7,
        "days": [
            ProtocolDay(day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up.")])
        ],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_save_and_read_roundtrip(tmp_path):
    _seed_event(tmp_path)
    path, version = store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    assert version == 1
    assert path == tmp_path / "competition" / "protocol-nationals-v1.md"
    assert (tmp_path / "competition" / "protocol-nationals-v1.yaml").exists()
    stored = store.read_competition_protocol(tmp_path, "nationals")
    assert stored is not None
    assert stored.version == 1
    assert stored.protocol.event_id == "nationals"
    assert "# Competition protocol v1" in stored.markdown


def test_v2_requires_reason_and_versions_are_per_event(tmp_path):
    _seed_event(tmp_path)
    _seed_event(tmp_path, event_id="tune-up", event_date=date(2026, 7, 30))
    store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    with pytest.raises(ValueError, match="reason"):
        store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    _, v2 = store.save_competition_protocol(
        tmp_path, _protocol(), reason="taper adjusted", today=TODAY
    )
    assert v2 == 2
    _, other = store.save_competition_protocol(
        tmp_path,
        _protocol(event_id="tune-up", event_date=date(2026, 7, 30)),
        today=TODAY,
    )
    assert other == 1  # independent lineage per event


def test_save_rejects_unknown_event_and_date_drift(tmp_path):
    with pytest.raises(ValueError, match="calendar"):
        store.save_competition_protocol(tmp_path, _protocol(), today=TODAY)
    _seed_event(tmp_path)
    with pytest.raises(ValueError, match="date"):
        store.save_competition_protocol(
            tmp_path, _protocol(event_date=date(2026, 8, 2)), today=TODAY
        )


def test_save_rejects_past_event(tmp_path):
    _seed_event(tmp_path)
    with pytest.raises(ValueError, match="past"):
        store.save_competition_protocol(tmp_path, _protocol(), today=date(2026, 8, 5))


def test_latest_version_none_when_empty(tmp_path):
    assert store.latest_competition_protocol_version(tmp_path, "nationals") is None
    assert store.read_competition_protocol(tmp_path, "nationals") is None
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/memory/test_store_protocol.py -q` — Expected: FAIL (`AttributeError`)

- [x] **Step 3: Implement**

In `src/performance_agent/memory/store.py`:

Add to the constants block (after `WATCH_DIR = "watch"`):

```python
COMPETITION_DIR = "competition"
```

Add the imports (merge into the existing import lines): `CompetitionProtocol` into the `from performance_agent.memory.schemas import (...)` block, and

```python
from performance_agent.programs.render_protocol import render_protocol
```

Append at the end of the file:

```python
@dataclass(frozen=True)
class ProtocolRead:
    """A stored competition-protocol version: structured plan plus its markdown."""

    version: int
    event_id: str
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    protocol: CompetitionProtocol


def _protocol_prefix(event_id: str) -> str:
    return f"protocol-{event_id}"


def latest_competition_protocol_version(base_dir: Path, event_id: str) -> int | None:
    """Highest stored protocol version for this event, or None."""
    return _latest_doc_version(base_dir, COMPETITION_DIR, _protocol_prefix(event_id))


def save_competition_protocol(
    base_dir: Path,
    protocol: CompetitionProtocol,
    reason: str | None = None,
    today: date | None = None,
    citations: "Mapping[str, ResolvedCitation] | None" = None,
) -> tuple[Path, int]:
    """Validate against the calendar and write the next protocol version.

    The event must exist in calendar.yaml with the same date (a rescheduled
    event needs a v2 with a reason, never a silent drift) and must not be in
    the past. yaml is the source of truth, markdown the rendered view; both
    are immutable once written. citations maps corpus ids to their resolved
    rendering (the server resolves them; None keeps a citation-less render).
    """
    current = today or date.today()
    event = next(
        (e for e in read_calendar(base_dir).events if e.id == protocol.event_id), None
    )
    if event is None:
        msg = f"event {protocol.event_id!r} is not in the calendar; add it first"
        raise ValueError(msg)
    if event.date != protocol.event_date:
        msg = (
            f"protocol event_date {protocol.event_date} does not match the calendar "
            f"date {event.date} for {protocol.event_id!r}"
        )
        raise ValueError(msg)
    if event.date < current:
        msg = f"event {protocol.event_id!r} ({event.date}) is in the past"
        raise ValueError(msg)
    prefix = _protocol_prefix(protocol.event_id)
    latest = latest_competition_protocol_version(base_dir, protocol.event_id)
    version = 1 if latest is None else latest + 1
    if version > 1 and not reason:
        msg = (
            f"adapting protocol v{latest} to v{version} for {protocol.event_id!r} "
            "requires a reason (audit trail)"
        )
        raise ValueError(msg)
    stamped = protocol.model_copy(
        update={"version": version, "reason": reason, "created_on": current}
    )
    frontmatter = {
        "version": version,
        "event_id": stamped.event_id,
        "goal_id": stamped.goal_id,
        "created_on": current.isoformat(),
        "reason": reason,
    }
    md_path = base_dir / COMPETITION_DIR / f"{prefix}-v{version}.md"
    yaml_path = md_path.with_suffix(".yaml")
    content = (
        "---\n"
        + _to_yaml(frontmatter)
        + "---\n\n"
        + render_protocol(stamped, citations=citations).strip()
        + "\n"
    )
    _atomic_write(yaml_path, _to_yaml(stamped.model_dump(mode="json")))
    try:
        _atomic_write(md_path, content)
    except OSError:
        yaml_path.unlink(missing_ok=True)
        raise
    return md_path, version


def read_competition_protocol(
    base_dir: Path, event_id: str, version: int | None = None
) -> ProtocolRead | None:
    """Return the given or latest protocol for an event; None when none exists."""
    target = (
        version
        if version is not None
        else latest_competition_protocol_version(base_dir, event_id)
    )
    if target is None:
        return None
    prefix = _protocol_prefix(event_id)
    md_path = base_dir / COMPETITION_DIR / f"{prefix}-v{target}.md"
    yaml_path = md_path.with_suffix(".yaml")
    if not md_path.exists() or not yaml_path.exists():
        msg = f"protocol v{target} for {event_id!r} does not exist"
        raise ValueError(msg)
    frontmatter, markdown = _split_frontmatter(md_path, md_path.read_text(encoding="utf-8"))
    protocol = _validated(
        yaml_path,
        lambda: CompetitionProtocol.model_validate(_load_yaml(yaml_path) or {}),
    )
    return ProtocolRead(
        version=target,
        event_id=event_id,
        goal_id=str(frontmatter["goal_id"]),
        created_on=str(frontmatter["created_on"]),
        reason=str(frontmatter["reason"]) if frontmatter.get("reason") is not None else None,
        markdown=markdown,
        protocol=protocol,
    )
```

(`Mapping` and `ResolvedCitation` are already imported since v0.8.0 — check the import block; if `ResolvedCitation` appears only in the quoted annotation, keep the existing import as is.)

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/memory/test_store_protocol.py tests/memory/ -q` — Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff check src/performance_agent/memory/store.py tests/memory/test_store_protocol.py && uv run ty check
git add src/performance_agent/memory/store.py tests/memory/test_store_protocol.py
git commit -m "Add per-event competition protocol store

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 7: `programs/render_protocol_html.py` — phone page

**Files:**
- Create: `src/performance_agent/programs/render_protocol_html.py`
- Test: `tests/programs/test_render_protocol_html.py`

- [x] **Step 1: Write the failing tests**

Create `tests/programs/test_render_protocol_html.py`:

```python
"""Protocol phone page: offline, no JS, warnings flagged, starred sources."""

from datetime import date

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import (
    CompetitionProtocol,
    DocumentedPractice,
    PacingSegment,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.programs.render_protocol_html import render_protocol_html

CITATIONS = {
    "carb-2017": ResolvedCitation(
        citation="Burke et al. (2017). Carbohydrates for training and competition. "
        "DOI: 10.1080/02640414.2011.585473.",
        stars="★★★★★",
        doi="10.1080/02640414.2011.585473",
        pmid=None,
    )
}


def _protocol():
    return CompetitionProtocol(
        version=1,
        event_id="nationals",
        event_date=date(2026, 8, 1),
        goal_id="sub-40-10k",
        created_on=date(2026, 7, 25),
        window_days=7,
        days=[
            ProtocolDay(
                day_offset=-1,
                title="Veille",
                lines=[ProtocolLine(text="8-12 g/kg carbs.", cite="carb-2017")],
            ),
            ProtocolDay(
                day_offset=0,
                title="Race day",
                lines=[
                    ProtocolLine(text="Breakfast.", time_hint="06:00"),
                    ProtocolLine(text="No new shoes.", warning=True),
                ],
            ),
        ],
        pacing=[
            PacingSegment(
                label="1 km", distance_m=1000, target_pace_s_per_km=240, cumulative_time_s=240
            )
        ],
        practices=[
            DocumentedPractice(
                name="Water manipulation",
                summary="Documented in physique prep.",
                warning="Dehydration risk; supervision required.",
            )
        ],
        checklist=["Pin race bib"],
    )


def test_page_is_selfcontained_and_scriptless():
    page = render_protocol_html(_protocol(), citations=CITATIONS)
    assert page.startswith("<!doctype html>")
    assert "<script" not in page
    assert "http" not in page.replace("https://doi.org/", "")


def test_event_day_open_warnings_and_sources_rendered():
    page = render_protocol_html(_protocol(), citations=CITATIONS)
    assert "<details" in page and "open" in page
    assert "⚠" in page
    assert "Dehydration risk" in page
    assert "★★★★★" in page
    assert "https://doi.org/10.1080/02640414.2011.585473" in page
    assert "[1]" in page


def test_french_labels():
    page = render_protocol_html(_protocol(), locale="fr", citations=CITATIONS)
    assert "Jour J" in page
    assert "Allures" in page
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/programs/test_render_protocol_html.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/programs/render_protocol_html.py`:

```python
"""Deterministic CompetitionProtocol -> standalone phone page for the event.

Same rules as the session HTML: fully self-contained (inline CSS, zero
JavaScript, no external requests except DOI links), phone-first, en/fr/es
labels from the athlete's locale. J0 renders open, earlier days collapsed.
Practice warnings are visually flagged — the page never softens them.
"""

import html
from collections.abc import Mapping

from performance_agent.evidence.citations import ResolvedCitation
from performance_agent.memory.schemas import CompetitionProtocol, ProtocolDay
from performance_agent.programs.render_protocol import protocol_citation_ids

_LABELS = {
    "en": {
        "protocol": "Competition protocol",
        "window": "Window",
        "goal": "Goal",
        "event_day": "Event day",
        "day": "Day",
        "advice": "Advice",
        "pacing": "Pacing",
        "segment": "Segment",
        "pace": "Pace",
        "cumulative": "Cumulative",
        "attempts": "Attempts",
        "fueling": "Fueling",
        "in_race": "In race",
        "practices": "Documented practices",
        "checklist": "Checklist",
        "sources": "Sources",
    },
    "fr": {
        "protocol": "Protocole de compétition",
        "window": "Fenêtre",
        "goal": "Objectif",
        "event_day": "Jour J",
        "day": "Jour",
        "advice": "Conseils",
        "pacing": "Allures",
        "segment": "Segment",
        "pace": "Allure",
        "cumulative": "Cumulé",
        "attempts": "Tentatives",
        "fueling": "Ravitaillement",
        "in_race": "En course",
        "practices": "Pratiques documentées",
        "checklist": "Checklist",
        "sources": "Sources",
    },
    "es": {
        "protocol": "Protocolo de competición",
        "window": "Ventana",
        "goal": "Objetivo",
        "event_day": "Día D",
        "day": "Día",
        "advice": "Consejos",
        "pacing": "Ritmos",
        "segment": "Segmento",
        "pace": "Ritmo",
        "cumulative": "Acumulado",
        "attempts": "Intentos",
        "fueling": "Avituallamiento",
        "in_race": "En carrera",
        "practices": "Prácticas documentadas",
        "checklist": "Checklist",
        "sources": "Fuentes",
    },
}

_CSS = """
:root { --bg: #f6f7f9; --card: #ffffff; --ink: #1c2330; --muted: #5b6472;
  --line: #e3e6eb; --accent: #2563eb; --chip: #eef2f8; --warn: #b45309;
  --warnbg: #fef3c7; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #10141b; --card: #1a202b; --ink: #e8ecf2; --muted: #9aa4b2;
    --line: #2a3140; --accent: #7aa2ff; --chip: #232b39; --warn: #fbbf24;
    --warnbg: #3a2f14; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); line-height: 1.5;
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 1rem 1rem 4rem; }
header.top h1 { margin: 1.5rem 0 0.25rem; font-size: 1.4rem; }
header.top p { margin: 0.15rem 0; color: var(--muted); }
h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; }
details.day { background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; margin: 0.6rem 0; overflow: hidden; }
details.day > summary { cursor: pointer; padding: 0.8rem 1rem; font-weight: 600;
  list-style: none; }
details.day > summary::-webkit-details-marker { display: none; }
details.day ul { margin: 0 0 0.8rem; padding: 0 1rem 0 2rem; }
details.day li { margin: 0.35rem 0; }
.hint { display: inline-block; background: var(--chip); border-radius: 999px;
  padding: 0 0.5rem; font-size: 0.85rem; margin-right: 0.3rem; }
li.warn { background: var(--warnbg); border-radius: 8px; padding: 0.25rem 0.5rem;
  list-style: none; margin-left: -1rem; }
.warnmark { color: var(--warn); font-weight: 700; }
sup.cite { color: var(--accent); font-weight: 600; }
table { border-collapse: collapse; width: 100%; background: var(--card);
  border-radius: 12px; overflow: hidden; }
th, td { border-bottom: 1px solid var(--line); padding: 0.45rem 0.7rem;
  text-align: left; font-size: 0.95rem; }
.practice { background: var(--warnbg); border-radius: 12px; padding: 0.7rem 1rem;
  margin: 0.6rem 0; }
.practice p { margin: 0.25rem 0; }
.practice .warnline { color: var(--warn); font-weight: 600; }
ul.checklist { padding-left: 1.2rem; }
section.sources ol { padding-left: 1.2rem; }
section.sources li { margin: 0.35rem 0; font-size: 0.9rem; }
section.sources .stars { color: var(--accent); letter-spacing: 0.05em; }
"""


def _t(locale: str, key: str) -> str:
    return _LABELS.get(locale, _LABELS["en"])[key]


def _marker(numbers: dict[str, int], cite: str | None) -> str:
    if cite is None or cite not in numbers:
        return ""
    return f'<sup class="cite">[{numbers[cite]}]</sup>'


def _pace(value: float) -> str:
    minutes, seconds = divmod(round(value), 60)
    return f"{minutes}:{seconds:02d}/km"


def _clock(value: float) -> str:
    minutes, seconds = divmod(round(value), 60)
    return f"{minutes}:{seconds:02d}"


def _day_html(day: ProtocolDay, numbers: dict[str, int], locale: str) -> str:
    title = (
        _t(locale, "event_day")
        if day.day_offset == 0
        else f"{_t(locale, 'day')} J{day.day_offset}"
    )
    items = []
    for line in day.lines:
        hint = f'<span class="hint">{html.escape(line.time_hint)}</span>' if line.time_hint else ""
        warn = '<span class="warnmark">⚠ </span>' if line.warning else ""
        css = ' class="warn"' if line.warning else ""
        items.append(
            f"<li{css}>{hint}{warn}{html.escape(line.text)}{_marker(numbers, line.cite)}</li>"
        )
    is_open = " open" if day.day_offset == 0 else ""
    return (
        f'<details class="day"{is_open}><summary>{title} — {html.escape(day.title)}</summary>'
        f"<ul>{''.join(items)}</ul></details>"
    )


def _pacing_html(protocol: CompetitionProtocol, locale: str) -> str:
    if not protocol.pacing:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(seg.label)}</td><td>{seg.distance_m:g} m</td>"
        f"<td>{_pace(seg.target_pace_s_per_km)}</td><td>{_clock(seg.cumulative_time_s)}</td></tr>"
        for seg in protocol.pacing
    )
    return (
        f"<h2>🏁 {_t(locale, 'pacing')}</h2><table><tr><th>{_t(locale, 'segment')}</th>"
        f"<th></th><th>{_t(locale, 'pace')}</th><th>{_t(locale, 'cumulative')}</th></tr>"
        f"{rows}</table>"
    )


def _attempts_html(protocol: CompetitionProtocol, locale: str) -> str:
    if not protocol.attempts:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(a.lift)}</td><td>{a.opener_kg:g}</td>"
        f"<td>{a.second_kg:g}</td><td>{a.third_kg:g}</td></tr>"
        for a in protocol.attempts
    )
    return (
        f"<h2>🏋️ {_t(locale, 'attempts')}</h2><table><tr><th></th><th>1</th><th>2</th>"
        f"<th>3</th></tr>{rows}</table>"
    )


def _fueling_html(protocol: CompetitionProtocol, numbers: dict[str, int], locale: str) -> str:
    fueling = protocol.fueling
    if fueling is None:
        return ""
    lines = [
        f"<li>{fueling.carb_g_per_kg_low:g}-{fueling.carb_g_per_kg_high:g} g/kg/day — "
        f"{fueling.window_hours} h{_marker(numbers, fueling.cite)}</li>"
    ]
    if fueling.race_carb_g_per_h_low is not None and fueling.race_carb_g_per_h_high is not None:
        lines.append(
            f"<li>{_t(locale, 'in_race')}: {fueling.race_carb_g_per_h_low:g}-"
            f"{fueling.race_carb_g_per_h_high:g} g/h</li>"
        )
    return f"<h2>🍝 {_t(locale, 'fueling')}</h2><ul>{''.join(lines)}</ul>"


def _practices_html(protocol: CompetitionProtocol, numbers: dict[str, int], locale: str) -> str:
    if not protocol.practices:
        return ""
    cards = "".join(
        f'<div class="practice"><p><strong>{html.escape(p.name)}</strong> — '
        f"{html.escape(p.summary)}{_marker(numbers, p.cite)}</p>"
        f'<p class="warnline">⚠ {html.escape(p.warning)}</p></div>'
        for p in protocol.practices
    )
    return f"<h2>⚠️ {_t(locale, 'practices')}</h2>{cards}"


def _sources_html(
    citations: Mapping[str, ResolvedCitation], numbers: dict[str, int], locale: str
) -> str:
    ordered = sorted((cid for cid in numbers if cid in citations), key=lambda cid: numbers[cid])
    if not ordered:
        return ""
    rows = []
    for cid in ordered:
        resolved = citations[cid]
        link = (
            f' <a href="https://doi.org/{html.escape(resolved.doi)}">DOI</a>'
            if resolved.doi
            else ""
        )
        rows.append(
            f'<li><span class="stars">{resolved.stars}</span> '
            f"{html.escape(resolved.citation)}{link}</li>"
        )
    return (
        f'<section class="sources"><h2>📚 {_t(locale, "sources")}</h2>'
        f"<ol>{''.join(rows)}</ol></section>"
    )


def render_protocol_html(
    protocol: CompetitionProtocol,
    locale: str = "en",
    citations: Mapping[str, ResolvedCitation] | None = None,
) -> str:
    """Render the protocol to a standalone, offline-ready phone page."""
    numbers = (
        {cid: i for i, cid in enumerate(protocol_citation_ids(protocol), start=1)}
        if citations
        else {}
    )
    advice = ""
    if protocol.advice:
        rows = "".join(
            f"<li>{html.escape(g.text)}{_marker(numbers, g.cite)}</li>" for g in protocol.advice
        )
        advice = f"<h2>💡 {_t(locale, 'advice')}</h2><ul>{rows}</ul>"
    days = "".join(_day_html(day, numbers, locale) for day in protocol.days)
    checklist = ""
    if protocol.checklist:
        items = "".join(f"<li>☐ {html.escape(item)}</li>" for item in protocol.checklist)
        checklist = f"<h2>🎒 {_t(locale, 'checklist')}</h2><ul class='checklist'>{items}</ul>"
    title = (
        f"{_t(locale, 'protocol')} v{protocol.version} — {html.escape(protocol.event_id)} — "
        f"{protocol.event_date.isoformat()}"
    )
    header = (
        f'<header class="top"><h1>{title}</h1>'
        f"<p>{_t(locale, 'window')}: J-{protocol.window_days} → J0 · "
        f"{_t(locale, 'goal')}: {html.escape(protocol.goal_id)}</p></header>"
    )
    return (
        f'<!doctype html><html lang="{locale}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_CSS}</style></head><body><main>"
        f"{header}{advice}{days}{_pacing_html(protocol, locale)}"
        f"{_attempts_html(protocol, locale)}{_fueling_html(protocol, numbers, locale)}"
        f"{_practices_html(protocol, numbers, locale)}{checklist}"
        f"{_sources_html(citations or {}, numbers, locale)}</main></body></html>"
    )
```

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/programs/ -q` — Expected: PASS

- [x] **Step 5: Lint + commit**

```bash
uv run ruff check src/performance_agent/programs/render_protocol_html.py tests/programs/test_render_protocol_html.py && uv run ty check
git add src/performance_agent/programs/render_protocol_html.py tests/programs/test_render_protocol_html.py
git commit -m "Render the competition protocol phone page

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

---

## Phase 3 — Server + diligence

### Task 8: `server/competition_tools.py` + registration

**Files:**
- Create: `src/performance_agent/server/competition_tools.py`
- Modify: `src/performance_agent/server/app.py`
- Test: `tests/server/test_competition_tools.py`

- [x] **Step 1: Write the failing tests**

Create `tests/server/test_competition_tools.py`:

```python
"""MCP wrappers for the pre-competition protocol."""

from datetime import date
from pathlib import Path

import pytest

from performance_agent.memory import store
from performance_agent.memory.schemas import (
    CalendarEvent,
    CompetitionProtocol,
    Guidance,
    Profile,
    ProtocolDay,
    ProtocolLine,
)
from performance_agent.server import competition_tools

TODAY = date.today()


@pytest.fixture
def athlete_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path))
    store.write_profile(tmp_path, Profile())
    store.upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nationals",
            date=TODAY.replace(year=TODAY.year + 1),
            kind="competition",
            priority="A",
            label="Nationals",
        ),
    )
    return tmp_path


def _protocol(**overrides):
    fields = {
        "version": 1,
        "event_id": "nationals",
        "event_date": TODAY.replace(year=TODAY.year + 1),
        "goal_id": "sub-40-10k",
        "created_on": TODAY,
        "window_days": 7,
        "days": [
            ProtocolDay(day_offset=0, title="Race", lines=[ProtocolLine(text="Warm up.")])
        ],
    }
    fields.update(overrides)
    return CompetitionProtocol.model_validate(fields)


def test_engine_wrappers_quote_engine_numbers(athlete_dir):
    carbs = competition_tools.carb_loading_targets(70.0, 180.0)
    assert carbs["carb_g_per_day_high"] == 840.0
    attempts = competition_tools.select_attempts("Squat", 200.0, 205.0)
    assert attempts["lift"] == "Squat"
    assert attempts["third_kg"] == 205.0
    splits = competition_tools.pacing_plan(10000.0, 2400.0)
    assert len(splits) == 10


def test_save_renders_html_and_read_roundtrips(athlete_dir):
    result = competition_tools.save_competition_protocol(_protocol())
    assert result["version"] == 1
    page = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "<script" not in page
    view = competition_tools.read_competition_protocol("nationals")
    assert view["version"] == 1
    assert view["protocol"]["event_id"] == "nationals"


def test_save_rejects_unknown_citation(athlete_dir):
    protocol = _protocol(advice=[Guidance(text="Fake.", cite="phantom-id")])
    with pytest.raises(ValueError, match="phantom-id"):
        competition_tools.save_competition_protocol(protocol)


def test_read_without_protocol_raises(athlete_dir):
    with pytest.raises(ValueError, match="no protocol"):
        competition_tools.read_competition_protocol("nationals")
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/server/test_competition_tools.py -q` — Expected: FAIL (module missing)

- [x] **Step 3: Implement**

Create `src/performance_agent/server/competition_tools.py`:

```python
"""MCP tools for the pre-competition protocol.

Engine numbers are quoted, never renegotiated upward; the athlete may always
choose the more conservative option. The save gate resolves every citation id
against the corpus — an unknown id aborts before anything is written.
"""

from dataclasses import asdict
from typing import Any, TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import competition as competition_engine
from performance_agent.evidence.citations import resolve_citations
from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import CompetitionProtocol
from performance_agent.programs.render_protocol import protocol_citation_ids
from performance_agent.programs.render_protocol_html import render_protocol_html


class AttemptView(TypedDict):
    """Meet-day attempts for one lift, engine-computed."""

    lift: str
    e1rm_kg: float
    opener_kg: float
    second_kg: float
    third_kg: float
    flags: list[str]


class ProtocolSaved(TypedDict):
    """Result of writing a protocol version (markdown + phone page)."""

    path: str
    version: int
    html_path: str


class ProtocolView(TypedDict):
    """A stored protocol version: structured plan plus rendered markdown."""

    version: int
    event_id: str
    goal_id: str
    created_on: str
    reason: str | None
    markdown: str
    protocol: dict[str, Any]


def carb_loading_targets(body_mass_kg: float, event_duration_min: float) -> dict[str, Any]:
    """Carb-loading and in-race fueling ranges for an event (evidence-based).

    Events >= 90 min: 8-12 g/kg/day over the final 48 h; 60-90 min: 6-8 g/kg/day
    over 24 h; shorter: loading_required=false (say so, don't invent a load).
    In-race: none under 60 min, 30-60 g/h up to ~2.5 h, 60-90 g/h beyond. Quote
    the ranges as ranges — food choices and timing are coaching conversation.
    """
    return asdict(competition_engine.carb_loading_targets(body_mass_kg, event_duration_min))


def select_attempts(
    lift: str, e1rm_kg: float, goal_kg: float, rounding_kg: float = 2.5
) -> AttemptView:
    """Three meet-day attempts from the e1RM (get it from estimate_1rm first).

    Opener ~91% (a confident triple), second ~96%, third at the goal when it
    lies within 93-105% of e1RM — else ~101% with flag goal_beyond_e1rm: name
    the gap honestly, never pretend the goal is on the bar. The athlete may
    always call lighter attempts; never push heavier than the engine's numbers.
    """
    selection = competition_engine.select_attempts(e1rm_kg, goal_kg, rounding_kg)
    return AttemptView(
        lift=lift,
        e1rm_kg=e1rm_kg,
        opener_kg=selection.opener_kg,
        second_kg=selection.second_kg,
        third_kg=selection.third_kg,
        flags=list(selection.flags),
    )


def pacing_plan(
    distance_m: float,
    target_time_s: float,
    segment_m: float = 1000.0,
    strategy: str = "even",
) -> list[dict[str, Any]]:
    """Per-segment target paces and cumulative splits for a race plan.

    target_time_s comes from the athlete's goal or predict_race_time — this
    only distributes it. strategy 'even' or 'negative' (first half ~1% slower,
    second half balanced so the total lands on target).
    """
    return [
        asdict(split)
        for split in competition_engine.pacing_plan(
            distance_m, target_time_s, segment_m, strategy
        )
    ]


def save_competition_protocol(
    protocol: CompetitionProtocol, reason: str | None = None
) -> ProtocolSaved:
    """Write the NEXT protocol version for its event (immutable audit trail).

    The event must exist in the calendar with a matching, non-past date.
    Version 1 needs no reason; v2+ requires one naming the trigger. Every cite
    (advice, day lines, fueling, practices) must be a real corpus id — an
    unknown id aborts the save (anti-fabrication). Every documented practice
    carries its warning by schema. Alongside the markdown, a standalone phone
    page is written — hand that file to the athlete for the event.
    MANDATORY: pass the draft through program-review's protocol gate BEFORE
    saving; only an APPROVED verdict saves.
    """
    base = resolve_athlete_dir()
    citations = resolve_citations(protocol_citation_ids(protocol))
    path, version = store.save_competition_protocol(base, protocol, reason, citations=citations)
    stored = store.read_competition_protocol(base, protocol.event_id, version)
    if stored is None:  # pragma: no cover - just written above
        msg = f"protocol v{version} vanished after save"
        raise ValueError(msg)
    locale = store.read_profile(base).locale
    page = render_protocol_html(stored.protocol, locale=locale, citations=citations)
    html_path = path.with_suffix(".html")
    html_path.write_text(page, encoding="utf-8")
    return ProtocolSaved(path=str(path), version=version, html_path=str(html_path))


def read_competition_protocol(event_id: str, version: int | None = None) -> ProtocolView:
    """Return the latest (or a specific) protocol version for an event."""
    stored = store.read_competition_protocol(resolve_athlete_dir(), event_id, version)
    if stored is None:
        msg = f"no protocol saved for event {event_id!r}; save_competition_protocol first"
        raise ValueError(msg)
    return ProtocolView(
        version=stored.version,
        event_id=stored.event_id,
        goal_id=stored.goal_id,
        created_on=stored.created_on,
        reason=stored.reason,
        markdown=stored.markdown,
        protocol=stored.protocol.model_dump(mode="json"),
    )


def register(mcp: FastMCP) -> None:
    """Register the competition tools on the server."""
    for tool in (
        carb_loading_targets,
        select_attempts,
        pacing_plan,
        save_competition_protocol,
        read_competition_protocol,
    ):
        mcp.tool()(tool)
```

In `src/performance_agent/server/app.py`: add `competition_tools,` to the import tuple (alphabetical, after `autoregulation_tools`) and `competition_tools.register(mcp)` after `followup_tools.register(mcp)`.

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/server/ -q` — Expected: PASS

- [x] **Step 5: Lint + commit**

```bash
uv run ruff check src/performance_agent/server/competition_tools.py src/performance_agent/server/app.py tests/server/test_competition_tools.py && uv run ty check
git add src/performance_agent/server/competition_tools.py src/performance_agent/server/app.py tests/server/test_competition_tools.py
git commit -m "Add the five pre-competition MCP tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 9: Diligence — `competition_protocol` due action

**Files:**
- Modify: `src/performance_agent/engine/diligence.py`
- Modify: `src/performance_agent/memory/diligence.py`
- Modify: `src/performance_agent/server/memory_tools.py` (docstring)
- Test: `tests/engine/test_diligence.py` (append), `tests/memory/test_diligence.py` (append)

- [x] **Step 1: Write the failing tests**

Append to `tests/engine/test_diligence.py`:

```python
def test_competition_protocol_due_inside_window_without_protocol():
    facts = _facts(
        upcoming_events=(
            UpcomingEvent(
                event_id="nationals", priority="A", days_until=8,
                protocol_window_days=10, has_protocol=False,
            ),
        )
    )
    action = next(a for a in list_due_actions(facts) if a.kind == "competition_protocol")
    assert action.severity == "medium"
    assert action.due_in_days == 8
    assert action.ref == "nationals"


def test_competition_protocol_high_when_event_is_close():
    facts = _facts(
        upcoming_events=(
            UpcomingEvent(
                event_id="nationals", priority="A", days_until=5,
                protocol_window_days=10, has_protocol=False,
            ),
        )
    )
    action = next(a for a in list_due_actions(facts) if a.kind == "competition_protocol")
    assert action.severity == "high"


def test_competition_protocol_quiet_outside_window_or_covered():
    outside = _facts(
        upcoming_events=(
            UpcomingEvent(
                event_id="nationals", priority="A", days_until=15,
                protocol_window_days=10, has_protocol=False,
            ),
        )
    )
    covered = _facts(
        upcoming_events=(
            UpcomingEvent(
                event_id="nationals", priority="A", days_until=5,
                protocol_window_days=10, has_protocol=True,
            ),
        )
    )
    for facts in (outside, covered):
        kinds = {a.kind for a in list_due_actions(facts)}
        assert "competition_protocol" not in kinds
```

Append to `tests/memory/test_diligence.py`:

```python
def test_a_event_without_protocol_surfaces_competition_protocol(tmp_path):
    upsert_calendar_event(
        tmp_path,
        CalendarEvent(
            id="nationals",
            date=TODAY + timedelta(days=6),
            kind="competition",
            priority="A",
            label="Nationals",
        ),
    )
    action = _action(tmp_path, "competition_protocol")
    assert action["ref"] == "nationals"
    assert action["due_in_days"] == 6
```

- [x] **Step 2: Run** — `rtk proxy uv run pytest tests/engine/test_diligence.py tests/memory/test_diligence.py -q` — Expected: FAIL (`unexpected keyword argument 'protocol_window_days'`)

- [x] **Step 3: Implement**

In `src/performance_agent/engine/diligence.py`:

Add to the thresholds block (after `_WATCH_DUE_DAYS = 14`):

```python
# Inside a week of the event, a missing protocol is urgent.
_PROTOCOL_URGENT_DAYS = 7
```

Extend `UpcomingEvent` (append two defaulted fields — existing constructions stay valid):

```python
    protocol_window_days: int = 0
    has_protocol: bool = True
```

(and extend its docstring with: `protocol_window_days is the taper-derived due window for a pre-competition protocol; has_protocol says whether one exists for this event.`)

Add the action builder (after `_watch_action`):

```python
def _protocol_action(event: UpcomingEvent) -> DueAction | None:
    if event.has_protocol or event.protocol_window_days <= 0:
        return None
    if event.days_until > event.protocol_window_days:
        return None
    severity: Severity = "high" if event.days_until <= _PROTOCOL_URGENT_DAYS else "medium"
    return DueAction(
        "competition_protocol",
        severity,
        "competition_protocol_due",
        due_in_days=event.days_until,
        ref=event.event_id,
    )
```

Register it inside `list_due_actions`, right after the existing `candidates.extend(_event_action(event) for event in facts.upcoming_events)` line:

```python
    candidates.extend(_protocol_action(event) for event in facts.upcoming_events)
```

In `src/performance_agent/memory/diligence.py`:

Add imports: `from performance_agent.engine.competition import protocol_window_days` and `from performance_agent.engine.season import recommend_taper_length` (merged with existing imports).

Add after the module's threshold constants:

```python
# The due-action window uses the population mixed-modality taper prior — no
# per-athlete modality is persisted; the skill computes the individualized
# window (recommend_taper) when it actually authors the protocol.
_NEUTRAL_BUILDUP_WEEKS = 8
```

Replace `_upcoming_events` with (it gains `base_dir` and fills the two new fields):

```python
def _upcoming_events(base_dir: Path, context: TimeContext) -> tuple[UpcomingEvent, ...]:
    events = []
    for event in context["next_events"]:
        if event["priority"] not in ("A", "B") or not 0 <= event["days_until"] <= _EVENT_HORIZON_DAYS:
            continue
        taper_days = recommend_taper_length(_NEUTRAL_BUILDUP_WEEKS, "mixed", event["priority"])
        events.append(
            UpcomingEvent(
                event_id=event["event_id"],
                priority=event["priority"],
                days_until=event["days_until"],
                protocol_window_days=protocol_window_days(taper_days, event["priority"]),
                has_protocol=store.latest_competition_protocol_version(
                    base_dir, event["event_id"]
                )
                is not None,
            )
        )
    return tuple(events)
```

and update its call site in `_build_facts` to `upcoming_events=_upcoming_events(base_dir, context),`.

In `src/performance_agent/server/memory_tools.py`, extend the `list_due_actions` docstring list with: `an A/B event inside its protocol window with no pre-competition protocol saved`.

- [x] **Step 4: Run** — `rtk proxy uv run pytest tests/engine/test_diligence.py tests/memory/ tests/server/ -q` — Expected: PASS. If `test_imminent_a_event_is_high`-style existing tests now ALSO see a `competition_protocol` action, that is correct behavior — fix only tests that assert exact action lists (add the new kind or a protocol), never the engine.

- [x] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run ty check
git add src/performance_agent/engine/diligence.py src/performance_agent/memory/diligence.py src/performance_agent/server/memory_tools.py tests/engine/test_diligence.py tests/memory/test_diligence.py
git commit -m "Surface the competition-protocol due action

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 10: Phase gate

- [x] **Step 1:** Run: `rtk proxy uv run pytest -q >/dev/null 2>&1; echo "exit=$?"` — Expected: `exit=0`
- [x] **Step 2:** Run: `uv run ruff check src tests && uv run ty check` — Expected: clean. Fix anything before Phase 4.

---

## Phase 4 — Skills + README

### Task 11: New skill `pre-competition`

**Files:**
- Create: `skills/pre-competition/SKILL.md`

- [x] **Step 1: Write the skill**

````markdown
---
name: pre-competition
description: Use when a competition_protocol due action fires or the athlete says
  their competition is coming up. Authors the per-event, day-by-day protocol for
  the final days (J-N to J0) and delivers the phone page for the event.
tools: [read_athlete, get_time_context, read_calendar, read_program, read_sessions,
  read_research_dossier, recommend_taper, predict_race_time, estimate_1rm,
  carb_loading_targets, select_attempts, pacing_plan, get_citation,
  save_competition_protocol, read_competition_protocol, log_kpi_result]
---

# Pre-competition

The protocol author: the final days before a competition, planned day by day and
handed over as a phone page the athlete reads on the morning of the event. Sport
comes from the research, numbers come from the engine, and this skill NEVER
edits the program — taper structure changes route to program-adaptation.

## Ritual

1. Open with `read_athlete` + `get_time_context` (quote its dates) and
   `read_calendar`; name the event, its priority, and days until. `read_program`
   for the planned taper; sanity-check it against `recommend_taper` (say the
   basis — individual or population).
2. First protocol for this event → run the dedicated mini-wave (deep-research
   rules): ONE question — "the final days before [this event] for [this
   athlete]" — verified studies join the corpus, the dossier gets a v+1.
   `read_research_dossier` for what is already known.
3. Build the day-by-day plan from J-window to J0, engine first:
   - Endurance: target from the goal or `predict_race_time`; `pacing_plan` for
     the splits; `carb_loading_targets` for fueling (quote ranges as ranges).
   - Strength: e1RM via `estimate_1rm` (recent best sets); `select_attempts`
     per lift. `goal_beyond_e1rm` flag → name the gap honestly; the athlete may
     call lighter, never heavier than the engine's numbers.
   - Everything else (meal timing, warm-up, logistics, checklist) is advice:
     cited (`get_citation`) or plainly labeled coaching judgment.
4. Documented practices (peak-week water/sodium, weight-cut tactics): describe
   ONLY what the literature documents, each with its evidence grade and an
   explicit warning — never a dose, never a schedule, never engine math. Red
   flags and medical conditions keep precedence: refer out.
5. Walk the draft through with the athlete, then submit it to program-review's
   protocol gate. Only an APPROVED verdict saves: `save_competition_protocol`
   (v2+ reason = the trigger). Hand the athlete the html_path — that page is
   their event-day companion.
6. Day J-0 to J+2: route the debrief to training-checkin and log the result
   with `log_kpi_result` — the outcome feeds fit_taper_response for next time.
````

- [x] **Step 2: Verify** — Run: `rtk proxy uv run pytest tests/skills/ -q` — Expected: only `test_all_expected_skills_exist` fails (fixed in Task 12). If `test_tool_references` fails, fix the frontmatter now.

- [x] **Step 3: Commit**

```bash
git add skills/pre-competition/SKILL.md
git commit -m "Add pre-competition skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 12: Edit the five existing skills + test invariants

**Files:**
- Modify: `skills/performance-coach/SKILL.md`, `skills/training-checkin/SKILL.md`, `skills/session-day/SKILL.md`, `skills/deep-research/SKILL.md`, `skills/program-review/SKILL.md`
- Modify: `tests/skills/test_structure.py`

- [x] **Step 1: Update the invariants first (they drive the edits)**

In `tests/skills/test_structure.py`:

Add to `EXPECTED_SKILLS`: `"pre-competition",`

Append the protocol test:

```python
def test_pre_competition_skill_protocol(skills):
    precomp = next(s for s in skills if s.frontmatter["name"] == "pre-competition")
    body = precomp.body.casefold()
    for needle in (
        "save_competition_protocol",
        "carb_loading_targets",
        "select_attempts",
        "pacing_plan",
        "recommend_taper",
        "mini-wave",
        "warning",
        "program-review",
        "never edits the program",
        "log_kpi_result",
        "coaching judgment",
    ):
        assert needle in body, f"pre-competition skill lost: {needle}"
```

Extend existing needle tuples (append to each):
- `test_coach_skill_carries_the_global_rules` (the test that asserts coach body content, ~line 37): `"pre-competition"`
- `test_checkin_skill_protocol`: `"debrief"`
- `test_review_skill_protocol`: `"protocol"` and `"warning"` (both appear in the Task 12 Step 6 checklist block)

Run: `rtk proxy uv run pytest tests/skills/ -q` — Expected: FAIL on exactly these invariants.

**Beware line wrap:** every needle must appear UNBROKEN on one line in the skill body (casefolded). Reflow sentences if needed.

- [x] **Step 2: `skills/performance-coach/SKILL.md`**

In the routing section, after the next-week-loads / program-watch lines added in v0.8.0, add:

```markdown
- competition_protocol action fires, or "my competition is in N days" →
  **pre-competition** (authors the final-days protocol and the event-day page).
```

- [x] **Step 3: `skills/training-checkin/SKILL.md`**

In the "Mesocycle boundary duties" section (or right after it), add:

```markdown
## Around a competition

A competition_protocol due action routes to pre-competition. The first check-in
AFTER an event owns the debrief: how it went vs the protocol, log the result
with log_kpi_result (it feeds the individual taper response), and any pain or
red flag follows the normal rules.
```

Frontmatter: add `log_kpi_result` to `tools` if not already declared.

- [x] **Step 4: `skills/session-day/SKILL.md`**

Add near the top of the protocol/ritual section:

```markdown
If today is an event day (J0) and a saved protocol exists
(read_competition_protocol for the calendar event), open FROM the protocol page
instead of improvising: quote its timeline, paces or attempts as written.
Adjustments follow the protocol's fallbacks, never a rewrite an hour before.
```

Frontmatter: add `read_competition_protocol` to `tools`.

- [x] **Step 5: `skills/deep-research/SKILL.md`**

In the "Mini-waves and the incremental watch" section, append one line to the mini-wave paragraph:

```markdown
The pre-competition wave is a mini-wave whose single question is the final days
before a named event (taper execution, fueling, pacing or attempts, weigh-in).
```

- [x] **Step 6: `skills/program-review/SKILL.md`**

Append to the deterministic compliance checklist (after the v0.8.0 structured-progression/guidance items):

```markdown
- Competition protocols (when the draft is a protocol, not a program): every
  documented practice carries an evidence grade (verify cites with
  get_citation) and an explicit warning; every engine-attributed number
  (attempts, paces, carb targets) matches a tool recomputation; dehydration or
  water-manipulation content stated as a computed or prescriptive line — rather
  than a warned, graded practice — is an objection.
```

- [x] **Step 7: Run the full skills suite** — `rtk proxy uv run pytest tests/skills/ -q` — Expected: PASS. If `test_bodies_do_not_reference_undeclared_tools` fails, add the mentioned tool to that skill's frontmatter `tools`.

- [x] **Step 8: Commit**

```bash
git add skills/ tests/skills/test_structure.py
git commit -m "Wire the pre-competition protocol into the skills

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

### Task 13: README + final gate

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update README** — replace `You should see 97 tools.` with `You should see 102 tools.`; replace `97 MCP` with `102 MCP`; replace `fourteen coaching skills` with `fifteen coaching skills`; add one feature bullet after the "Science on the gym page" bullet:

```markdown
- **Pre-competition protocol** — the final days before any competition planned
  day by day (engine-computed attempts, pacing splits and carb loading; risky
  peak-week practices described only with evidence grade + explicit warning),
  delivered as a versioned document and an offline phone page for the event.
```

Then recount the suite and update the test count: run `rtk proxy uv run python -m pytest --collect-only -q 2>/dev/null | awk -F': ' '{s+=$2} END {print s}'` and replace the `1339 tests` figure with the new number.

- [x] **Step 2: Full suite + linters** — Run: `rtk proxy uv run pytest -q >/dev/null 2>&1; echo "exit=$?"` then `uv run ruff check src tests && uv run ty check` — Expected: exit=0, everything clean.

- [x] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document the pre-competition protocol

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -1
```

- [x] **Step 4: NOT in this plan** — version bump, CHANGELOG, PyPI release.

---

## Plan self-review notes

- Spec coverage: §3 → Task 4; §4 → Tasks 1-3; §5 → Tasks 5-7; §6 → Task 8; §7 → Task 9; §8 → Tasks 11-12; §9 (errors) → distributed into module tests; §10 → every task test-first; §11 out-of-scope respected.
- Known deviation from spec §7 wording: the diligence window uses the population `mixed` taper prior (`recommend_taper_length(8, "mixed", priority)`) because no per-athlete modality is persisted; the individualized window (spec's `recommend_taper`) is computed by the skill at authoring time. This matches spec §9's fallback and avoids inventing a modality.
- Type consistency: `CarbLoadingTargets`/`AttemptSelection`/`PacingSplit` (engine, Tasks 1-3) vs `FuelingPlan`/`AttemptPlan`/`PacingSegment` (schemas, Task 4) are deliberately separate layers — the skill/server map between them; `ProtocolRead` (Task 6) feeds `ProtocolView` (Task 8); `protocol_citation_ids` shared by Tasks 5, 7, 8.
- Execution lessons carried from the v0.8.0 run: run pytest via `rtk proxy`; verify every commit with `git log --oneline -1` (prek hook failures hide behind rtk's "ok"); move test imports to module level (PLC0415); pytest `match=` strings with dots need raw-escaped patterns (RUF043).
