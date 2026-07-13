# Beyond-Olympic Prep — Progress Log

Plan: `docs/plans/beyond-olympic-prep-plan.md` (read §0 first — it is binding).
Executor: Claude Code session (opus) in tmux, native tools only, no superpowers.

**Baseline at plan time:** 1016 tests, 76 MCP tools, v0.3.0 on main. The executor
must re-run `uv run pytest -q` before Phase 0 and record the actual figure here.

**Baseline verified 2026-07-13 (execution start):** `uv run pytest` → **1016 passed
in 3.72s**. Branch `main`, clean tree. Matches plan-time figure. Proceeding to Phase 0.

## Phase status

| Order | Phase | Title | Status | Branch / PR | Notes |
|---|---|---|---|---|---|
| 1 | 0 | PerformanceModel schemas, store & tools | done (merged) | `feat/phase-0-performance-model` / PR #15 `55718c9` | 1043 tests (+27); 78 tools (+2) |
| 2 | 1 | Gaps, KPI results, test battery, seeds, needs-analysis rewrite | done (merged) | `feat/phase-1-gaps-kpi-battery` / PR #16 `51b5496` | 1083 tests (+40); 82 tools (+4); 4 seed models |
| 3 | 2 | Exercise ontology & libraries | done | `feat/phase-2-exercise-ontology` / PR pending | 1097 tests (+14); 84 tools (+2); 123 seed exercises |
| 4 | 3 | Selection engine & specificity guard | pending | — | |
| 5 | 4 | High-resolution ingestion | pending | — | |
| 6 | 5 | Load-velocity profiling & VBT autoregulation | pending | — | |
| 7 | 6 | Fitted Banister model | pending | — | |
| 8 | 7 | Individual taper response & per-quality profile | pending | — | |
| 9 | 8 | Multi-year planning & residuals | pending | — | |
| 10 | 9 | Property tests & multi-sport e2e sim | pending | — | |
| 11 | 10 | Skills/docs/i18n/corpus & release prep | pending | — | |

Statuses: pending → in_progress → done (merged). Use `BLOCKED: <reason>` when parked.

## Deviations from plan

- **P0 — `Quality` enum renamed `PerformanceQuality`.** `schemas.py` already
  defines `Quality` (session-tag literal: `strength_heavy`, `power`, …). The
  plan's generic body-quality axis would collide, so it ships as
  `PerformanceQuality`. Same 12 axes as specified.
- **P0 — versioned store lives in `store.py`, not a new
  `memory/performance_models.py`.** It follows the existing response-profile
  precedent exactly (`save_/read_/latest_performance_model_version`, `models/`
  dir, `.yaml` suffix, immutable versions, reason from v2) — zero helper
  duplication. A dedicated `performance_models.py` module is deferred to Phase 1
  when it will carry real athlete-layer logic (seed loading, gap wiring).
- **P0 — `Provenance` also rejects `cite_ids` on non-`cited` kinds**, and
  `EnergySystemSplit`/`Benchmark` carry a `provenance` label (invariant 6:
  provenance on every LLM-filled structured value). Additive, within plan intent.
- **P1 — KPI-results jsonl store lives in `store.py`** (`append_kpi_result`,
  `read_kpi_results`) with all other append-only logs, not a separate
  `memory/kpi_results.py`. Domain orchestration (seed loading, gap wiring,
  test-battery scheduling) lives in the new `memory/performance_models.py` — the
  module deferred from P0, now created with real logic.
- **P1 — added `KpiSpec.higher_is_better: bool = True`** (additive, default True).
  The gap engine needs gap direction (a sprint-time gap grows as time rises; a 1RM
  gap grows as load falls). Backward-compatible: old models default to True.
- **P1 — seed models labeled `prior` throughout, no `cited`.** The corpus does not
  yet hold the determinant/benchmark studies (Suchomel 2016 etc. are the P10
  evidence pass). Honest priors now beat fabricated citations; P10 upgrades them.
- **P1 — Typst report "model & gaps" section deferred to Phase 10**, which already
  scopes it ("performance model & gaps section"). Recorded here per the transversal
  report-refresh note (extend in the same PR OR record a follow-up).
- **P1 — no runtime seed-reading tool.** Seeds are package data + test fixtures +
  an inline example in `needs-analysis`; the LLM authors models from the schema and
  the referenced seed files, keeping the tool surface lean (82, not 84).
- **P2 — `MovementPattern` is a Literal in `schemas.py`, not an enum.**
  `engine/substitutions.py` uses `MovementPattern = str`; the ontology needs strict
  validation, so a `MovementPattern` Literal (16 values incl. jump/sprint/throw/
  olympic beyond the substitution table's 12) is the contract for
  `ExerciseDefinition`. `SessionPlan.patterns` stays `list[str]` (untouched).
- **P2 — `ExerciseDefinition` has an `id`** (slug) beyond the plan's field list —
  Phase 3's `ExerciseBlock.exercise_id` links to it. Equipment vocabulary extends
  substitutions' tokens with sled/medicine_ball/bodyweight (needed by plyo/throw/
  sprint families); "bodyweight" is the explicit no-equipment available token.
- **P2 — athlete exercise-library file I/O in `store.py`** (`read_/write_exercise_
  library`, like `calendar.yaml`); domain logic (seed load, merge, filter, propose)
  in `memory/exercise_library.py`. Consistent with the P0/P1 store-consolidation.

## Resume notes

(update on every interruption; read first when resuming)
