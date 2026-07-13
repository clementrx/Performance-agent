# Beyond-Olympic Prep — Implementation Plan

**Mission.** Upgrade PerformanceAgent's *planning, programming and exercise selection*
past the best discipline-specific S&C coach — for ANY sport — by making three
structural changes:

1. **Sport knowledge becomes a researched, structured, versioned object** (the
   `PerformanceModel`): the LLM researches the literature and proposes, the engine
   structures, validates and computes. Today sport-specificity lives only as free
   prose in `skills/needs-analysis/SKILL.md`; after this plan it is a schema the
   research fills — for a sport the agent has never seen before.
2. **Exercise selection becomes a scored decision in a structured space** (exercise
   ontology with universal attributes + deterministic scoring), replacing free-text
   exercise authoring.
3. **Adaptation becomes a fitted individual model** (per-athlete Banister fitting,
   learned taper response, load-velocity profiling, tests planned as experiments),
   replacing fixed population rules — so the athlete responds optimally and
   continuously toward their competition deadlines.

The product's honesty principle is untouched: "better than the best discipline coach"
is a claim about the *quality of planning decisions*, never a guaranteed outcome. The
agent states its own data ceiling: with only sRPE and check-ins it says so; with VBT,
jump and split data it decides at higher resolution.

All athlete memory stays in the athlete directory (`PERFORMANCE_AGENT_HOME`) as plain
files; this plan extends what it stores (see §2).

---

## 0. How to execute this plan (instructions to the executing agent)

- This plan is **self-contained**. Do NOT use external planning/skill frameworks —
  **no superpowers skills, no `Skill` tool invocations, no BMAD**. Execute with
  native tools only (Read/Edit/Write/Bash/Grep/Glob, subagents allowed for search).
- **Orient first.** Read: `README.md`, `pyproject.toml`, `.pre-commit-config.yaml`,
  `src/performance_agent/engine/` (all modules), `src/performance_agent/memory/`
  (`schemas.py`, `store.py`, `paths.py`), `src/performance_agent/server/` (all
  `*_tools.py`, `app.py`), `src/performance_agent/importers/activity.py`, every
  `skills/*/SKILL.md`, `docs/plans/beyond-national-coach-plan.md` (the predecessor —
  its conventions are binding), and the test layout under `tests/`. File anchors in
  this plan reflect the repo at v0.3.0 — re-verify by reading before editing.
- **Run the suite before touching anything** (`uv run pytest -q`) and record the
  baseline (1016 tests at plan time) in the progress file.
- **Per phase:** feature branch `feat/phase-N-<slug>` → tests first for engine math →
  implement → full gate: `uv run pytest -q`, `uv run ruff check`,
  `uv run ruff format --check`, `uv run ty check`, pre-commit — all green, zero
  warnings → update the affected skills, README tool count / "Working today", and
  docs in the SAME branch → open a PR referencing this plan → **merge when green,
  before starting the next phase** (locked decision, same flow as the previous plan's
  execution). If `origin/main` does not yet contain this plan file, push `main` once
  before opening the first PR.
- **Never break existing athlete directories.** New schema fields are optional with
  safe defaults; every NEW file format carries `schema_version: 1`. Legacy files must
  remain readable forever. Write a migration note in the PR when a format gains fields.
- **Engine purity.** All new math = pure functions in `src/performance_agent/engine/`,
  no I/O, deterministic, property-tested (hypothesis), bounded inputs that raise on
  nonsense. Constants are module-level, each labeled with a corpus citation or
  `team-chosen prior` (existing repo convention). MCP wrappers follow the existing
  `server/*_tools.py` pattern (docstring = tool description; the LLM narrates, the
  engine computes). **No new runtime dependencies without strong justification** —
  the Banister optimizer must be pure Python (grid + local refinement is acceptable;
  property-test parameter recovery on synthetic data).
- **Anti-fabrication / provenance.** Every value the LLM fills into a structured
  object carries `provenance: cited | prior | judgment` (cited requires corpus ids).
  Every new prescriptive rule in a skill either cites a corpus id (add the study
  first — see §Evidence) or is explicitly labeled coaching judgment. Never invent
  citations. `program-review` remains the mandatory gate for every program save.
- **Datetime convention:** naive local datetimes (timezone-aware values rejected). Keep.
- **Language:** code, skills, docs in English. Athlete-facing behavior stays
  locale-driven (en/fr/es).
- **Progress file.** Maintain `docs/plans/beyond-olympic-prep-progress.md`
  (phase → status → branch/PR → deviations → resume notes). Update at every phase
  completion AND on interruption; read it FIRST when resuming. If genuinely blocked
  on a product decision, write a `BLOCKED:` entry there, park the phase, and continue
  with the next independent phase if one exists.
- **Releases:** none during execution. Phase 10 prepares v0.4.0 (bump, changelog,
  tag, build) — **publishing to PyPI requires an explicit user GO**; stop there.
- **Tool budget.** This plan grows the MCP surface from 76 to ≤95 tools. Keep new
  tool docstrings compact; consolidate tools if the cap would be exceeded.

**Locked product decisions (user-confirmed 2026-07-13):**

1. **Generic-first, no sport verticals.** No hard-coded per-sport engines. Sport
   knowledge enters exclusively as researched content filling generic schemas. Seed
   models are fixtures/few-shot examples, never a lookup table that gates support.
2. **Scope = core + high-resolution + multi-year.** Core: PerformanceModel + exercise
   ontology + fitted n=1 loop. Plus: high-resolution data ingestion (VBT, jumps,
   splits, watts — optional inputs, graceful degradation) and multi-year planning
   (macrocycle, training residuals). **Environment & fine peaking (altitude, heat,
   timezones/jet lag, competition-hour) are explicitly deferred to the roadmap.**
3. **Exercise selection = engine scores, LLM chooses within top-k.** The engine
   produces a deterministic, justified ranking; the LLM picks among the top-k with a
   stated reason. Substitution upgrades from pattern+equipment to stimulus
   equivalence.
4. **Merge flow:** PR per phase, merged before the next phase. Single release at the
   end (v0.4.0); publish gated on user GO.

---

## 1. Architecture invariants (non-negotiable)

1. LLMs narrate/research/propose; the engine structures, verifies and calculates. No
   number reaches the athlete that wasn't computed by a deterministic tool.
2. Citations only from the evidence corpus, pre-checked with `check_citations`; PDF
   rendering hard-fails on unknown references.
3. Athlete data = plain files in one directory. Atomic writes, append-only logs,
   immutable versioned documents with mandatory `reason` from v2.
4. Nothing is saved as a program without `program-review` APPROVED.
5. Safety precedence: pain/injury → stop loading that pattern, refer out. Never
   diagnose, never program through an active injury.
6. **Provenance everywhere:** every LLM-filled value in a structured object is
   labeled `cited | prior | judgment`; reports display the labels.
7. **Graceful degradation:** every consumer of high-resolution data declares its
   behavior without it. Missing data never blocks coaching; it lowers stated
   resolution ("based on sRPE only").

---

## 2. Athlete-data layout additions (after all phases)

```
athlete-data/
  models/
    performance-model-v{N}.yaml   # NEW P0: discipline determinants, versioned + reason
  exercises/
    library.yaml                  # NEW P2: athlete-local exercise additions (validated)
  kpi_results.jsonl               # NEW P1: dated KPI/test measurements (append-only)
  sessions.jsonl                  # P4: entries gain optional set-level velocity data
  response/
    response-profile-v{N}.yaml    # P6/P7: + fitted Banister params, taper response,
                                  #        per-quality rates
  macro/
    macro-plan-v{N}.yaml          # NEW P8: multi-year plan, versioned + reason
```

Package data (read-only, shipped):

```
src/performance_agent/models/data/seed/       # NEW P1: 4 reference PerformanceModels
  sprint-100m.yaml · running-10k.yaml · powerlifting.yaml · football.yaml
src/performance_agent/exercises/data/seed_exercises.yaml  # NEW P2: ~120-150 exercises
```

---

## 3. Phase map and dependencies

| Order | Phase | Title | Depends on |
|---|---|---|---|
| 1 | 0 | PerformanceModel schemas, store & tools | — |
| 2 | 1 | Gap engine, KPI results, test battery, seed models, needs-analysis rewrite | 0 |
| 3 | 2 | Exercise ontology: schemas, seed library, athlete library | — |
| 4 | 3 | Selection engine: scoring, stimulus substitution, specificity guard | 1, 2 |
| 5 | 4 | High-resolution ingestion: VBT, jumps, splits, watts | 0 |
| 6 | 5 | Load-velocity profiling & velocity-based autoregulation | 4 |
| 7 | 6 | Fitted Banister model | 1, 4 |
| 8 | 7 | Individual taper response & per-quality response profile | 6 |
| 9 | 8 | Multi-year planning: macrocycle & training residuals | 0, 1 |
| 10 | 9 | Property tests & multi-sport e2e simulation | 0–8 |
| 11 | 10 | Skills/docs/report/i18n refresh, corpus, release prep | 0–9 |

---

## Phase 0 — PerformanceModel schemas, store & tools

**Goal.** The generic, sport-agnostic representation of "what determines performance
in this event" exists as a validated, versioned object.

**Deliverables.**
- `memory/schemas.py`: `Provenance` (literal `cited|prior|judgment` + optional
  `cite_ids: list[str]`, required non-empty when cited), `Quality` enum (generic
  body-quality axes: `max_strength, explosive_strength, reactive_strength, speed,
  acceleration, change_of_direction, aerobic_capacity, anaerobic_capacity,
  muscular_endurance, hypertrophy, mobility, balance_stability`),
  `QualityRequirement` (quality, weight 0–1, provenance, rationale),
  `KpiSpec` (id, name, quality link, test protocol free-text + `TestProtocol` when
  applicable, unit, benchmarks by level `recreational|competitive|national|elite`
  with provenance), `InjuryRiskEntry` (region, mechanism, screen, provenance),
  `EnergySystemSplit` (aerobic/anaerobic_lactic/anaerobic_alactic fractions, sum≈1),
  `PerformanceModel` (discipline, event, qualities [weights normalized], kpis,
  injury_risks, energy_systems, sources, schema_version, version, reason from v2).
- `memory/performance_models.py`: versioned store, same pattern as programs
  (immutable versions, mandatory reason from v2, atomic writes).
- `server/performance_tools.py`: `save_performance_model`, `read_performance_model`
  (latest or by version).

**Validation rules (engine-enforced, tested).** Reject: quality weights not
normalizable, a KPI without protocol or unit, cited provenance without cite_ids,
unknown quality names (the enum is the contract — the LLM cannot invent qualities;
sport-specific expression belongs in KpiSpec protocols), empty qualities list.

**Tests.** Schema round-trip, validation rejections, store versioning/immutability,
tool wrappers. Property: weight normalization invariant under permutation.

**Acceptance.** A hand-written 100 m model YAML saves, versions, re-reads; invalid
models fail with actionable messages.

---

## Phase 1 — Gap engine, KPI results, test battery, seed models, needs-analysis rewrite

**Goal.** The PerformanceModel becomes the *starting point of programming*: athlete
gaps computed against benchmarks, tests scheduled as experiments, and the
needs-analysis skill fills the model instead of writing prose.

**Deliverables.**
- `kpi_results.jsonl` (append-only): date, kpi_id, protocol, value, unit, context
  (e.g. bodyweight, conditions). `memory/kpi_results.py` + tools `log_kpi_result`,
  `read_kpi_results`.
- `engine/gaps.py`: `compute_gaps(model, kpi_results, level)` → per-KPI gap (measured
  vs benchmark, staleness of measurement, missing-data flags) and per-quality
  priority ranking (gap × weight). Honest gates: a KPI with no measurement returns
  `unmeasured`, never a guessed value. Tool: `compute_performance_gaps`.
- `engine/test_battery.py` + tool `plan_test_battery`: given model KPIs + calendar,
  propose dated test milestones (re-test cadence per quality, never inside a taper,
  respects existing `TestMilestone`/calendar patterns).
- **Seed models** (package data): `sprint-100m`, `running-10k`, `powerlifting`,
  `football` — every value provenance-labeled (cited where the corpus supports it,
  else prior). They are fixtures and few-shot examples, not a support gate.
- **`skills/needs-analysis/SKILL.md` rewritten:** the Analyste now (1) searches
  evidence (`search_evidence`, `search_evidence_live`) for the event's determinants,
  (2) proposes a PerformanceModel via `save_performance_model` (validation errors
  come back to fix), (3) runs `compute_performance_gaps`, (4) renders prose FROM the
  model. Feasibility tools unchanged. For sports with thin literature: fill with
  `judgment` provenance + structured athlete/coach interview; never refuse to model.

**Tests.** Gap math (unit + property: gap monotone in benchmark distance), staleness,
unmeasured paths, battery placement rules, seed models load & validate.

**Acceptance.** For a seeded sport AND a hand-filled unseeded sport, gaps + a dated
test battery come out of the tools; the rewritten skill references only existing tools.

---

## Phase 2 — Exercise ontology: schemas, seed library, athlete library

**Goal.** Exercises become structured objects with universal attributes.

**Deliverables.**
- `memory/schemas.py`: `ForceVector` (`axial|horizontal|lateral|rotational|mixed`),
  `ContractionRegime` (`concentric_dominant|eccentric_dominant|isometric|plyometric|
  ballistic|mixed`), `SpecificityLevel` (`general|special|specific|competition` —
  Bondarchuk-style), `ExerciseDefinition` (name, movement patterns [existing
  `MovementPattern` enum], force_vector, contraction_regime, chain open/closed,
  equipment tokens [same vocabulary as `substitutions.py`], specificity_level,
  qualities_trained `dict[Quality, float 0–1]`, contraindications [regions],
  unilateral, skill_complexity 1–3, provenance).
- `src/performance_agent/exercises/data/seed_exercises.yaml`: ~120–150 common
  exercises fully attributed (squat/hinge/push/pull/lunge/carry/core families, jumps
  & plyos, sprints/drills, Olympic lift derivatives, common machines, run/ride/swim
  modalities). Attribution provenance: `prior` unless corpus-citable.
- `memory/exercise_library.py`: read-only package seed + athlete-local
  `exercises/library.yaml` for additions; tools `list_exercises` (filter by pattern,
  quality, equipment, specificity) and `propose_exercise` (LLM submits a fully
  attributed definition; engine validates schema + vocabulary and persists with
  provenance `judgment`).

**Tests.** Seed file loads and validates entirely (CI guard), filters, proposal
validation rejections (unknown quality, bad equipment token), athlete-library merge
precedence.

**Acceptance.** `list_exercises(quality=reactive_strength, equipment=[bodyweight])`
returns sensible plyometric entries from the seed.

---

## Phase 3 — Selection engine: scoring, stimulus substitution, specificity guard

**Goal.** Exercise selection becomes a deterministic, justified ranking; the LLM
chooses within the top-k.

**Deliverables.**
- `engine/exercise_selection.py`: `score_exercises(candidates, quality_targets,
  phase, available_equipment, contraindicated_regions, recent_exposure)` →
  per-candidate score with an attribute-by-attribute justification breakdown
  (quality match × phase-appropriate specificity × equipment feasibility ×
  contraindication hard-exclusion × novelty/variety modifier). Deterministic,
  tie-broken by name. Tool: `score_exercises`.
- **`substitute_exercise` upgraded:** same tool name/signature extended — when the
  original exercise exists in the ontology, substitutes rank by *stimulus
  equivalence* (qualities_trained similarity + same force_vector/regime preferred),
  filtered by equipment and contraindications; falls back to the existing
  pattern+equipment table for unknown exercises (never breaks current behavior).
- `engine/specificity.py` + check integrated into the existing week-sequencing guard
  (or a sibling `check_program_specificity` tool): the general→competition
  specificity mix per mesocycle phase is validated against phase-appropriate target
  bands (module constants, `team-chosen prior` labels; e.g. general_prep is
  general-dominant, realization is specific-dominant).
- **Skills updated:** `program-planning` (per-quality set targets now driven by gap
  priorities), `program-optimization` (mandatory flow: `list_exercises` →
  `score_exercises` → choose within top-k with stated reason → cite or label; the
  `ExerciseBlock` gains optional `exercise_id` linking to the ontology).

**Tests.** Scoring determinism + property tests (adding a contraindication never
raises a score; equipment filter is a hard gate), substitution equivalence vs
fallback, specificity band checks.

**Acceptance.** For the 100 m seed model in `specific_prep`, the top-k for
`reactive_strength` is dominated by plyometric/sprint-specific entries with visible
justifications — and the same call for the 10k model ranks differently.

---

## Phase 4 — High-resolution ingestion: VBT, jumps, splits, watts

**Goal.** The data ceiling rises: optional high-resolution inputs enter the athlete
directory through the existing parse-and-propose discipline.

**Deliverables.**
- Schemas: `VbtSet` (exercise, load_kg, mean_velocity, top_velocity?, reps, per-rep
  velocities optional), session entries gain optional `vbt_sets`; `JumpTestResult`
  (type CMJ/SJ/drop, height_cm and/or RSI, conditions) carried as the `context`
  payload of cmj entries in `kpi_results.jsonl`;
  `SplitSeries` (distances + times) and power summary (avg/NP watts, cadence) on
  imported activities. `TestProtocol` extended: `cmj`, `sprint_split`,
  `vbt_profile`, `ftp`.
- `importers/activity.py` extended: extract power/cadence/lap-splits from .fit/.tcx
  where present (today discarded); `importers/vbt_csv.py`: column-mapped CSV import
  for common VBT app exports (load, velocity, reps) — parse-and-propose, never
  silent-log. `import_activity_file` tool surface extended accordingly.
- Jump and sprint measurements land in `kpi_results.jsonl` via `log_kpi_result`
  (protocol `cmj`/`sprint_split`, `kpi_id` nullable, one entry per measured value);
  `training-checkin` skill updated to ask for/route these when the athlete has the
  hardware (profile gains optional `equipment_sensors` field).

**Tests.** Parser fixtures (.fit with power laps, VBT CSV variants, malformed files
fail actionably), schema optionality (old session entries still parse), proposal
flow.

**Acceptance.** A .fit ride yields watts+splits in the proposal; a VBT CSV yields
structured sets; an athlete with no sensors experiences zero new friction.

---

## Phase 5 — Load-velocity profiling & velocity-based autoregulation

**Goal.** Bar velocity becomes an input to daily decisions.

**Deliverables.**
- `engine/vbt.py`: `fit_load_velocity(vbt_sets)` → per-exercise linear load-velocity
  profile (slope, intercept, r², minimal detectable change), daily e1RM estimate
  from a submaximal set, and velocity-loss guidance (set termination thresholds by
  goal, constants labeled with citations — see §Evidence). Honest gates: ≥4 distinct
  loads spanning ≥30% 1RM range, else refuse with reason. Tool: `fit_load_velocity`.
- `adjust_session` (day-of autoregulation) accepts optional velocity evidence:
  today's warm-up velocity vs profile → load adjustment suggestion, labeled and
  bounded; without velocity data behavior is unchanged (degradation invariant).
- `program-optimization` / `program-adaptation` skills: velocity-loss set guidance
  offered when profile exists; `prescribe_load` narrative can reference daily e1RM.

**Tests.** Regression math (property: recovering synthetic profiles with noise),
gates, MDC, adjust_session with/without velocity, bounds.

**Acceptance.** Synthetic profile recovered within tolerance; a slow warm-up set
produces a bounded, explained load reduction suggestion.

---

## Phase 6 — Fitted Banister model

**Goal.** The fitness-fatigue model stops being a fixed-τ convention and becomes a
per-athlete fitted model — with honesty gates.

**Deliverables.**
- `engine/banister.py`: two-component impulse-response
  `p̂(t) = p0 + k1·Σw(s)e^-((t-s)/τ1) − k2·Σw(s)e^-((t-s)/τ2)` fitted by pure-Python
  bounded optimization (coarse grid over (τ1, τ2) + linear least squares for
  (p0, k1, k2), then local refinement; deterministic seeding). Inputs: daily loads +
  dated performance points (KPI results for one chosen KPI, or e1RM series). Output:
  params, fit quality (R², residual SE), approximate CIs (labeled approximation),
  and a `usable: bool` verdict. **Gates:** ≥8 weeks of load history AND ≥5
  performance points spanning it, τ bounds sane (require τ1 > τ2 —
  fitness decays slower than fatigue; reject fits pinned at parameter bounds), else
  refuse with reason.
- Tool `fit_banister` (stores nothing by itself); fitted params persist into the
  versioned response profile (`response/response-profile-vN.yaml`) via the existing
  response tools; `compute_fitness_fatigue` accepts optional fitted params (falls
  back to the labeled EWMA defaults — existing behavior untouched).
- `compute_response_profile` extended to include the fit when data qualifies.

**Tests.** Property: parameter recovery on synthetic athletes (known params + noise →
recovered within tolerance); gates; degenerate data (constant loads) refused;
EWMA fallback unchanged (regression tests on existing outputs).

**Acceptance.** A 12-week synthetic athlete yields a usable fit with recovered
params; a 3-week athlete gets an honest refusal naming the missing data.

---

## Phase 7 — Individual taper response & per-quality response profile

**Goal.** Taper duration/depth come from the athlete's own history when it exists.

**Deliverables.**
- `engine/taper_response.py`: detect historical taper windows from sessions +
  calendar (volume reduction ≥~25% over ≥4 days preceding an event), pair each with
  an outcome (event-linked KPI result, race time, or peri-event e1RM/readiness
  delta), and summarize `fit_taper_response` → observed (duration, reduction) →
  outcome table with n and uncertainty stated. With n≥2, produce an individual
  recommendation delta vs the generic rule; with n<2, return the generic rule
  explicitly labeled `population prior`.
- `recommend_taper` upgraded to consult the fitted taper response (same tool,
  extended output: `basis: individual|population`).
- Response profile extended **per quality** (not only per lift): measured progression
  rates keyed to Quality via KPI linkage; `compute_response_profile` output and
  schema updated (schema_version bump, old profiles still readable).
- Optional: Banister-derived taper window (predicted TSB peak) surfaced as a labeled
  *model estimate* alongside, never silently overriding.

**Tests.** Taper detection on synthetic histories (including none detected),
pairing logic, n-gates, recommend_taper basis switching, profile backward-compat.

**Acceptance.** An athlete with two logged tapers gets an individualized
recommendation with the evidence shown; a first-taper athlete gets the labeled
generic rule.

---

## Phase 8 — Multi-year planning: macrocycle & training residuals

**Goal.** Planning extends beyond one season: 1–4 year horizon, quality budgets, and
residual-driven sequencing.

**Deliverables.**
- Schemas: `MacroYear` (index, type `development|qualification|realization`,
  primary_event ref, quality_emphases `dict[Quality, float]`), `MacroPlan`
  (horizon_years 1–4, years, major_event_id, schema_version, versioned + reason).
  Store `memory/macro.py`; tools `save_macro_plan`, `read_macro_plan`,
  `build_macro_plan`.
- `engine/macro.py`: backward pass from the major event (e.g. Games/championship):
  year typing, quality-emphasis budgets per year derived from the PerformanceModel
  gap priorities (development years bias general capacities & weaknesses;
  realization year biases specific/competition qualities), season boundaries
  proposed per year. `build_season_plan` gains an optional macro context (accepts
  the year's emphases; existing single-season behavior unchanged without it).
- `engine/residuals.py`: retention-duration table per Quality (module constants from
  Issurin, labeled cited/prior) + `check_residuals(planned_blocks)` → warnings when
  a maintained quality would decay beyond its residual without a refresh stimulus.
  Tool `check_residuals`; the season planner surfaces these warnings.
- Training age now modulates *structure* where the engine builds blocks (e.g. block
  length defaults by training age — labeled priors), not only rate priors.
- `program-planning` skill updated: macro-aware flow for athletes with >1-year
  horizons; `performance-coach` routing mentions it.

**Tests.** Backward year typing, budget derivation from gaps, residual warnings
(property: extending a gap between stimuli never removes a warning), season-plan
compatibility (existing tests untouched), store versioning.

**Acceptance.** A 2027-major-event athlete gets a typed 2-year macro with quality
budgets flowing into `build_season_plan`, and a residual warning fires when speed
work disappears for longer than its retention window.

---

## Phase 9 — Property tests & multi-sport e2e simulation

**Goal.** Prove the generic machine end-to-end — including on a sport with no seed.

**Deliverables.**
- Extend the deterministic no-LLM e2e simulation (Phase 8 of the previous plan) with
  new personas: **sprinter (100 m, seeded model)**, **powerlifter (seeded)**, and
  **kayak sprint (NO seed)** — the kayak persona uses a hand-authored
  PerformanceModel fixture marked as research-filled (mixed provenance) to prove the
  pipeline is seed-independent: model → gaps → test battery → scored selection →
  program → monitoring → fitted response (synthetic logs long enough to qualify for
  the Banister gate on at least one persona).
- Cross-cutting property-test suite consolidation: parameter recovery (Banister,
  load-velocity), scoring invariances, residual monotonicity.
- Determinism guard: two runs of the full sim produce identical outputs.

**Tests.** The sim IS the test; plus a coverage check that every new tool is
exercised at least once across sim personas.

**Acceptance.** All personas complete; the kayak persona produces a coherent program
with provenance labels and no code path special-cases its sport string.

---

## Phase 10 — Skills/docs/report/i18n refresh, corpus, release prep

**Goal.** Everything user-facing catches up; release prepared but not published.

**Deliverables.**
- Skills coherence pass: `performance-coach` routing (model-first flow),
  `athlete-onboarding` (sensor/equipment questions), `goal-assessment` (gap-aware
  framing), `program-report` sections. Remove any stale instructions contradicting
  the new flow (replace, don't deprecate).
- Typst report templates (coach & expert, en/fr/es): performance model & gaps
  section, macro overview, fitted-response summary (params + basis + uncertainty),
  provenance labels rendered. Citation gate applies.
- README: hook/positioning updated (any-sport determinants engine, scored selection,
  fitted individualization, multi-year), tool count, "Working today", roadmap
  (environment & fine peaking listed as deferred). Examples: add one worked example
  under `examples/en/` for a non-seeded sport.
- §Evidence corpus additions completed (verify DOI/PMID/ISBN via `verify_reference`;
  unverifiable → labeled priors, never fake citations).
- Release prep: version 0.4.0, changelog, tag, build artifacts, install docs
  re-checked. **STOP before `publish` — ask the user for GO in the progress file /
  final message.**

**Acceptance.** Full gate green on main; README claims match shipped behavior;
release artifacts built; publish awaiting user GO.

---

## Evidence corpus additions (transversal — land citations before skills cite them)

Verify each with `verify_reference` (never cite from memory; confirm the reference
supports the rule). Unverifiable → `team-chosen prior` label:

- Banister 1975 / Morton et al. 1990 — impulse-response performance modeling (P6).
- Busso 2003 — variable dose-response model, fitting practice (P6).
- Issurin 2010 (block periodization reviews) — training residuals (P8).
- Bondarchuk — *Transfer of Training in Sports* (ISBN) — specificity classification (P2/P3).
- Verkhoshansky & Siff — *Supertraining* / special strength (ISBN) — dynamic
  correspondence framing (P2/P3, framing only).
- González-Badillo & Sánchez-Medina 2010 — movement velocity as intensity measure (P5).
- Sánchez-Medina & González-Badillo 2011 — velocity loss & fatigue (P5).
- Weakley et al. 2021 — VBT applications review (P4/P5).
- Suchomel et al. 2016 — muscular strength as performance determinant (P1 seed models).
- Mujika & Padilla 2003 — taper physiology (P7; corpus already holds the 2007 meta).

---

## Report templates refresh (transversal)

Any phase adding athlete-visible data extends the Typst templates (both modes, three
languages) in the SAME PR or records a follow-up in the progress file: P1 → model &
gaps; P5/P6/P7 → fitted-response summaries; P8 → macro overview. Hard citation gate
applies everywhere.

---

## Out of scope (this iteration)

**Environment & fine peaking: altitude/hypoxia camps, heat acclimatization,
timezone/jet-lag protocols, competition-hour scheduling (user decision 2026-07-13 —
next iteration candidate).** Unchanged from the previous plan: OAuth/cloud, web/mobile
UI, multi-athlete server, exercise technique/video analysis, nutrition beyond the
existing frame, medical diagnosis, menstrual-cycle tracking (revisit on demand), full
team-sport vertical, non-7-day microcycles (`WeekPlan` limit stands; MacroPlan sits
above seasons and does not change week granularity).

---

## Global definition of done

1. All 11 phases merged to main; full suite green (baseline 1016 + new unit/property/
   e2e-sim tests); ruff, ty, pre-commit clean; zero warnings.
2. The e2e sim proves: an unseeded sport flows research→model→gaps→scored
   selection→program→fitted adaptation with provenance labels end to end.
3. Every new constant is cited or labeled; `check_citations` passes on all skills and
   report templates.
4. README/docs/i18n/examples updated; tool count ≤95 and accurate.
5. `docs/plans/beyond-olympic-prep-progress.md` complete (per-phase status, PRs,
   deviations, resume notes).
6. v0.4.0 prepared (bump, changelog, tag, build) — **published only after explicit
   user GO**.
