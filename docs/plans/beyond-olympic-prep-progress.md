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
| 3 | 2 | Exercise ontology & libraries | done (merged) | `feat/phase-2-exercise-ontology` / PR #17 `0a8048d` | 1097 tests (+14); 84 tools (+2); 123 seed exercises |
| 4 | 3 | Selection engine & specificity guard | done (merged) | `feat/phase-3-selection-engine` / PR #18 `daf6215` | 1126 tests (+29); 86 tools (+2) |
| 5 | 4 | High-resolution ingestion | done (merged) | `feat/phase-4-highres-ingestion` / PR #19 `0a8e60f` | 1148 tests (+22); 86 tools |
| 6 | 5 | Load-velocity profiling & VBT autoregulation | done (merged) | `feat/phase-5-load-velocity` / PR #20 `e013009` | 1168 tests (+20); 87 tools (+1) |
| 7 | 6 | Fitted Banister model | done (merged) | `feat/phase-6-fitted-banister` / PR #21 `4fb2438` | 1181 tests (+13); 88 tools (+1) |
| 8 | 7 | Individual taper response & per-quality profile | done (merged) | `feat/phase-7-taper-response` / PR #22 `778a927` | 1196 tests (+15); 89 tools (+1) |
| 9 | 8 | Multi-year planning & residuals | done (merged) | `feat/phase-8-macro-residuals` / PR #23 `62f7172` | 1223 tests (+27); 93 tools (+4) |
| 10 | 9 | Property tests & multi-sport e2e sim | done | `feat/phase-9-multisport-sim` / PR pending | 1242 tests (+19); 93 tools (no new) |
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
- **P3 — `substitute_exercise` memory signature gains `base_dir`** (the tool
  signature is unchanged). Stimulus-equivalence path when the exercise is in the
  ontology, else the pattern+equipment fallback. The pre-existing
  `test_substitute_exercise_passthrough` was rewritten into two tests (fallback +
  stimulus) since a seeded exercise now takes the stimulus path.
- **P3 — `check_program_specificity` is a sibling tool** (not folded into the
  week-sequencing guard) — it reasons over whole mesocycles via `exercise_id`
  links, a different altitude than the intra-week `check_week_sequencing`.
- **P3 — `ExerciseBlock.exercise_id`** added (optional, links a block to the
  ontology). `score_exercises`/specificity depend on it. `program-optimization`
  now sets it when choosing within top-k.
- **P3 — selection-layer domain logic in `memory/exercise_library.py`** (scoring,
  stimulus substitution, program-specificity), keeping engine pure in
  `engine/exercise_selection.py` + `engine/specificity.py`.
- **P4 — no standalone `JumpTestResult`/`SplitSeries` pydantic models.** Jumps/
  sprints log through the existing `KpiResult` (protocol `cmj`/`sprint_split`,
  value + `context`) — "carried as the context payload" per the plan; power/splits
  live on the `ParsedActivity` dataclass and the import proposal, not stored on
  `SessionEntry` (the plan's data layout adds only `vbt_sets` to sessions). No
  phantom schemas.
- **P4 — FIT power/lap extraction unit-tested at the helper level** (`_fit_power`,
  `_fit_splits`, `_normalized_power`, `_power_summary`) plus a full TCX-ride
  end-to-end fixture (`ride.tcx`); a hand-encoded power/lap FIT binary fixture was
  skipped as low-value given the helpers carry the logic. `.fit` session/record
  reading stays covered by the existing `run.fit` fixture.
- **P4 — VBT CSV importer reuses `activity.py`'s `_read_csv_rows`/`_to_float`**;
  no new MCP tool (import_activity_file extended to detect VBT and return a `vbt`
  proposal). Tool count stays 86.
- **P5 — velocity autoregulation extends `adjust_session`** with three optional
  params (velocity_exercise/load/velocity) and an optional `velocity_suggestion`
  output field, rather than a separate tool — the plan says adjust_session
  "accepts optional velocity evidence". `fit_load_velocity` is the one new tool.
- **P5 — load-velocity profiles are fit on demand, not persisted.** Both
  `fit_load_velocity` and the day-of suggestion refit from logged `vbt_sets`
  (single source of truth), matching how response profiles compute from logs.
- **P5 — MVT / velocity-loss thresholds are team-chosen priors** (Sánchez-Medina /
  González-Badillo studies land in the P10 corpus pass; labeled priors until then).
- **P6 — Banister property test asserts fit REPRODUCES the data (R² > 0.9) + τ1 > τ2,
  not exact parameter recovery.** Exact recovery isn't identifiable with a coarse
  grid and collinear decay features (the classic Banister issue); one well-conditioned
  clean-recovery test covers exact params, the property test covers goodness-of-fit
  across athletes. Honest about the limitation.
- **P6 — fitted params fold into `compute_response_profile`** via an optional
  `banister_kpi_id` param + a new `ResponseProfile.banister` field, and a standalone
  `fit_banister` tool; `compute_fitness_fatigue` gained optional `ctl_tau`/`atl_tau`
  (pass fitted τ1/τ2). EWMA defaults unchanged when omitted. Banister 1975 / Morton
  1990 corpus citations deferred to P10 (τ bounds are priors until then).
- **P7 — `recommend_taper` moved from `engine_tools.py` to a new
  `server/taper_tools.py`** (it now reads athlete data — layering: engine_tools stays
  pure). Same tool name; output extended with `basis`/`population_days`/`note`. New
  `fit_taper_response` diagnostic tool (net +1). Detection counts consecutive
  sub-75%-of-baseline days before an event (true taper duration), not the longest
  ≥25%-average window (which over-reports on deep tapers).
- **P7 — `ResponseProfile.schema_version` bumped 1→2** for `per_quality_rates`
  (v1 profiles still validate — additive field). `QualityRate.quality` is `str`
  (mirrors `LiftRate.lift`; the PerformanceQuality literal is defined later in
  schemas.py, and the value is validated upstream on the KPI).
- **P7 — Banister-derived taper window (predicted TSB peak) deferred.** The plan
  marks it "Optional"; the individual-history path is the core deliverable. Follow-up
  candidate for a later iteration.
- **P8 — macro tools in a new `server/macro_tools.py`** (build/save/read_macro_plan
  + check_residuals). `check_residuals` reads the active program and resolves
  `exercise_id` → ontology qualities (blocks without an id are skipped). `MacroYear.
  quality_emphases` built via `model_validate` to satisfy the literal-dict typing.
- **P8 — `build_season_plan` macro context is a passthrough**: optional
  `year_emphases` echoed back as `macro_emphases`; the segment tiling is unchanged
  (faithful to "accepts the year's emphases; existing behavior unchanged without it").
- **P8 — training-age block length via `build_block_cycle(training_age=...)`**
  (beginner 6 / intermediate 9 / advanced 12 weeks, team-chosen priors); `total_weeks`
  still works and wins when both are given.
- **P8 — residual durations & macro tilts are team-chosen priors** (Issurin 2010 lands
  in the P10 corpus pass). Tool count 93 (≤95 cap; P9/P10 add no tools).
- **P9 — new sim personas drive the memory/engine layer directly** (not via MCP
  tools) for determinism/speed; a separate `test_new_tool_coverage.py` exercises every
  new Phase 0-8 MCP tool through the in-process client. Personas: P4 sprinter (seeded,
  Banister gate), P5 powerlifter (seeded, load-velocity + individual taper), P6 kayak
  (UNSEEDED, hand-authored mixed prior/judgment model — seed-independence proof).
- **P9 — kayak model uses prior/judgment provenance, not `cited`** (no corpus study
  for canoe sprint; fabricating a citation would violate anti-fabrication). "Mixed
  provenance" is satisfied by prior+judgment; `cited` is exercised in the P0 tool tests.
- **P9 — consolidated cross-cutting property file** re-asserts load-velocity/Banister
  recovery, selection contraindication monotonicity, and residual gap monotonicity in
  one suite; per-module property tests remain.

## Resume notes

(update on every interruption; read first when resuming)
