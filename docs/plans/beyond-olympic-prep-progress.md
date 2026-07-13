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
| 1 | 0 | PerformanceModel schemas, store & tools | done | `feat/phase-0-performance-model` / PR pending | 1043 tests (+27); 78 tools (+2) |
| 2 | 1 | Gaps, KPI results, test battery, seeds, needs-analysis rewrite | pending | — | |
| 3 | 2 | Exercise ontology & libraries | pending | — | |
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

## Resume notes

(update on every interruption; read first when resuming)
