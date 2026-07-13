# Beyond-National Coach — Execution Progress

Tracks execution of `beyond-national-coach-plan.md`. Read this FIRST when resuming.

**Workflow (locked 2026-07-12):** stacked branches (each phase branches off the
previous; PRs stack and merge in order at the end). Native tools only. Single PyPI
release at the very end. Baseline: **597 tests** passing at plan start.

Execution order: 0, 1, 2, 9, 3, 4, 5, 6, 7, 8.

| Order | Phase | Title | Status | Branch / PR | Notes |
|---|---|---|---|---|---|
| 1 | 0 | Machine-readable programs | done (PR open) | `feat/phase-0-machine-readable-programs` — [PR #4](https://github.com/clementrx/Performance-agent/pull/4) | 617 tests green |
| 2 | 1 | Season calendar & backward planning | done (PR open) | `feat/phase-1-season-calendar` — [PR #5](https://github.com/clementrx/Performance-agent/pull/5) | 659 tests; +6 tools (53 total) |
| 3 | 2 | Full monitoring | done (PR open) | `feat/phase-2-full-monitoring` — [PR #6](https://github.com/clementrx/Performance-agent/pull/6) (base: phase 1) | 749 tests; +9 tools (62 total) |
| 4 | 9 | Activity file import | done (PR open) | `feat/phase-9-activity-import` — [PR #7](https://github.com/clementrx/Performance-agent/pull/7) | 782 tests; +1 tool (63 total); +fitdecode dep |
| 5 | 3 | Day-of session autoregulation | done (PR open) | `feat/phase-3-session-autoregulation` — [PR #8](https://github.com/clementrx/Performance-agent/pull/8) | 823 tests; +5 tools (68 total) |
| 6 | 4 | Intra-week sequencing & interference | done (PR open) | `feat/phase-4-sequencing` — [PR #9](https://github.com/clementrx/Performance-agent/pull/9) (base: phase 3) | 860 tests; +1 tool (69 total) |
| 7 | 5 | Individual response profile | done (PR open) | `feat/phase-5-response-profile` — [PR #10](https://github.com/clementrx/Performance-agent/pull/10) (base: phase 4) | 902 tests; +4 tools (73 total) |
| 8 | 6 | Deloads, adherence, return-to-load | done (PR open) | `feat/phase-6-regulation` — [PR #11](https://github.com/clementrx/Performance-agent/pull/11) | 957 tests; +2 tools (75 total) |
| 9 | 7 | Proactive follow-up | done (PR open) | `feat/phase-7-proactive-followup` — [PR #12](https://github.com/clementrx/Performance-agent/pull/12) (base: phase 6) | 987 tests; +1 tool (76 total) |
| 10 | 8 | End-to-end simulated evaluation | done (PR open) | `feat/phase-8-e2e-sim` — [PR #13](https://github.com/clementrx/Performance-agent/pull/13) | 1001 tests; +0 tools (76 total); +14 e2e_sim tests |

**All 10 phases implemented and independently gate-verified.** Stacked PRs #4→#13
(each verified: pytest green, ruff/ruff-format/ty clean, engine-purity held, corpus
untouched across the whole stack). Baseline 597 → **1001 tests**; 47 → **76 tools**.

### Remaining before release (batched wrap-up, then user-gated merge + publish)
1. Typst report-template sections: P1 season overview, P2/P9 load trends, P5 response
   summary — coach & expert modes, en/fr/es (deferred each phase; required by Global
   DoD item 4). Hard citation gate applies.
2. i18n README refresh (`docs/i18n/README.{fr,it,es,de}.md`): test count → 1001,
   tool count → 76, new-capability lines.
3. `docs/installing.md` tool-count check string (still 47).
4. **User-gated:** merge the stacked PRs #4→#13 into main in order; then the single
   version bump + changelog per `RELEASING.md` and the PyPI publish (irreversible
   external action — requires explicit user go-ahead).

## Deviations from the plan

- **Test infra:** added `tests/__init__.py` (makes `tests` an importable package) and
  a shared `tests/program_plans.py` builder so every layer (store, reports, server)
  builds the same valid `ProgramPlan`. `TestMilestone` carries `__test__ = False` so
  pytest does not try to collect the schema as a test class.
- **Rendered-program glyphs:** the renderer emits ASCII `x` (sets x reps) and `-`
  rather than `×`/`–` to satisfy ruff RUF001 (ambiguous-unicode); reads fine in a
  printed program.
- **i18n READMEs:** the test-count line (597) in `docs/i18n/README.{fr,it,es,de}.md`
  is left for a single batched refresh before the release (plan-sanctioned: "full
  translation refresh may be a follow-up"). English README updated to 617.
- **Report templates:** Phase 0 changes the program *format* only; the rendered
  markdown still feeds the Typst report unchanged, so no report-template change was
  needed this phase.

## Migration note (PR)

`programs/program-v{N}.plan.yaml` is a NEW sibling of the existing
`program-v{N}.md`. Legacy prose-only `program-v{N}.md` files (no `.plan.yaml`) stay
readable forever — `read_program` returns `plan=None` for them, and a structured
vN+1 can be saved on top (reason = "format upgrade"). No existing athlete directory
is broken.

## Phase 1 notes

- **New tools (6, total 53):** `read_calendar`, `upsert_calendar_event`,
  `remove_calendar_event`, `set_recurring_constraints`, `build_season_plan`,
  `recommend_taper`. `set_recurring_constraints` is a small addition beyond the
  plan's literal 5-tool list — the plan's acceptance needs recurring constraints
  persisted (onboarding collects them; time_context reads them) and none of the
  5 listed tools wrote them. Whole-list replace, like `write_profile`.
- **Engine stays datetime-free:** `engine/season.py` works in integer-week space;
  the date↔week conversion lives in `memory/season.py` (like `time_context`).
- **`min_block_weeks` default = 6** (the plan signature said 3 but its prose says
  "≥ 6 weeks (matching MIN_BLOCK_WEEKS)"; followed the prose, mirrors
  `periodization.MIN_BLOCK_WEEKS`).
- **Evidence:** used the existing `tapering-performance-meta-2007` for taper
  length. Issurin block-periodization was NOT added to the corpus (would need a
  verified DOI/PMID; per the anti-fabrication rule the block-vs-waves structural
  priors are labeled team-chosen, consistent with existing `periodization.py`).
- **Report templates:** season-overview section deferred to a batched report pass
  (no athlete-visible report change wired this phase).

## Phase 2 notes

- **New tools (9, total 62):** engine — `compute_monotony_strain`,
  `compute_fitness_fatigue`, `compute_readiness`, `estimate_srpe_from_hr`,
  `endurance_zones`, `budget_weekly_load`, `flag_implausible_session`; memory —
  `log_readiness`, `read_readiness`. `compute_acwr` gained a `method`
  ("rolling"/"ewma") argument, and `log_session` now returns data-quality flags
  alongside its count (its result type changed from `SessionCount` to
  `SessionLogResult` = `{total_sessions, flags}`; the `total_sessions` field is
  unchanged so existing callers keep working).
- **New engine functions (`engine/load.py`):** `weekly_monotony`, `weekly_strain`,
  `fitness_fatigue_series` (EWMA CTL/ATL/TSB, taus 42/7 labeled conventions),
  `readiness_score` (Hooper items, optional HRV modifier, green≥75/amber≥50/red
  bands — all team-chosen priors), `estimate_srpe_from_hr` (%HRmax→CR10 linear map
  anchored on Foster's table), `budget_weekly_load`, `flag_implausible_session`
  (e1RM-jump / load-over-1RM / duration-outlier guards). `engine/endurance.py`:
  `training_zones_from_race` (Riegel-projected 10 km threshold proxy → 5 pace
  zones). All new module-level constants are labeled `team-chosen prior` or tie to
  the corpus.
- **Data-quality glue:** `memory/monitoring.py` extracts the numbers
  `flag_implausible_session` needs (best estimated 1RM per lift from history, known
  1RM from the profile, recent median duration) so the pure engine guard stays
  numeric; `log_session` runs it and returns the flags. Flags never block a
  write — the entry is logged, the coach confirms flagged values.
- **Schema/storage:** `SessionEntry` gained optional `source`
  ("programmed"/"external"), `session_plan_id`, `avg_hr` (all backward-compatible;
  legacy `sessions.jsonl` lines still load). New `ReadinessEntry` (schema_version 1)
  → append-only `readiness.jsonl`, mirroring `append_session`/`read_sessions`.
- **Tool-name collisions:** the engine functions `budget_weekly_load`,
  `estimate_srpe_from_hr`, `flag_implausible_session` are imported into
  `server/engine_tools.py` under `engine_*` aliases so the MCP tools can keep the
  plan's exact names.
- **Evidence:** no new corpus entries (no verified network to confirm DOIs/PMIDs).
  Foster monotony/strain and readiness reuse the existing
  `session-rpe-training-load-2001` where genuinely applicable; every new threshold
  (EWMA taus, readiness bands, HRV slope, plausibility guards, HR→RPE slope, zone
  multipliers, 10 km threshold proxy) is labeled `team-chosen prior` in code, per
  the plan's anti-fabrication fallback. Foster 1998, Hooper 1995, Banister/Coggan
  and the ACWR-EWMA (Williams) references named in the plan's evidence corpus
  section were NOT added to the corpus for the same reason — deferred to a future
  online verification pass.
- **Report templates:** the P2/P9 load-trend section (weekly load with external
  share, monotony/strain, CTL/ATL/TSB) is DEFERRED to a batched report pass, like
  Phase 1's season overview (plan-sanctioned follow-up; no athlete-visible report
  change wired this phase).
- **i18n READMEs:** the 4 translated READMEs in `docs/i18n/` are left for the
  single batched pre-release refresh (unchanged this phase). English README updated
  to 62 tools / 749 tests.

## Phase 9 notes

- **New tool (1, total 63):** `import_activity_file(path)` in the new
  `server/import_tools.py` (registered in `server/app.py`). It PARSES and
  PROPOSES only — it never logs. It returns a proposed `SessionEntry` (matched to
  a planned session or `source="external"`), whether the sRPE was estimated from
  HR / whether the athlete still owes one, data-quality flags, and — for an HRV
  CSV — dated readings to attach Hooper items to. Logging still goes through the
  existing `log_session` / `log_readiness` after the athlete confirms.
- **New modules (outside `engine/`, as required — parsing files is I/O):**
  `importers/activity.py` (pure file parsing: `.fit` via fitdecode, `.tcx`/`.gpx`
  via stdlib `xml.etree`, and activity/HRV `.csv`; normalizes to a
  `ParsedActivity`; malformed files raise `ActivityImportError` with actionable
  messages) and `importers/proposal.py` (athlete-aware: reads the active
  `ProgramPlan`, profile and session history to match the activity, estimate
  sRPE, and run the plausibility guard).
- **Phase-2 reuse:** sRPE from `engine.estimate_srpe_from_hr` (HR present +
  age-predicted HRmax derivable from `profile.birth_date`); the proposed entry
  runs through `memory.monitoring.session_plausibility_flags`, which wraps
  `engine.flag_implausible_session` (duration-outlier guard fires on imports —
  see deviation on distance below). Uses the Phase-2 `SessionEntry.source` /
  `session_plan_id` / `avg_hr` fields; HRV → `readiness.jsonl` via `log_readiness`.
- **Dependency decision:** added **`fitdecode==0.11.0`** (exact pin; current
  stable, released 2025-08-06, maintained) for `.fit` (binary) parsing —
  `.fit` was NOT descoped. `.tcx`/`.gpx` are XML and use the stdlib (no
  dependency). The `.fit` fixture is a hand-built 50-byte binary; its generator
  is committed at `tests/importers/make_fit_fixture.py` so the binary is
  reproducible and reviewable.
- **Session matching:** duration/distance proximity across all `SessionPlan`s in
  the active plan (mean relative error ≤ 0.20, halved when the planned weekday
  matches — both team-chosen priors); best match → `source="programmed"` +
  `session_plan_id`, else `external`. No structured plan (or a legacy prose-only
  program) → `external`.
- **Deviations:** (a) `SessionEntry` has no distance field, so only the
  duration-outlier plausibility guard flows through an imported entry; the
  distance guard in `flag_implausible_session` is not reachable from imports
  (documented, not a silent skip). (b) HRmax for the HR→sRPE estimate is derived
  as `220 - age` (Fox age-predicted, labeled team-chosen prior) from
  `profile.birth_date`; with no birth date the tool sets `needs_srpe=true` and
  asks the athlete rather than guessing. (c) Timestamps from tz-aware files
  (.fit/.tcx/.gpx are UTC) are converted to naive local wall-clock to match the
  schema convention.
- **Skill updated:** `training-checkin` gained step 3c (offer file import, always
  confirm before logging) and `import_activity_file` in its `tools:` frontmatter.
- **Report templates / i18n READMEs:** the P2/P9 load-trend report section stays
  DEFERRED to the batched report pass (unchanged this phase); the 4 `docs/i18n/`
  READMEs stay for the single batched pre-release refresh. English README updated
  to 63 tools / 782 tests and a line about activity-file import.

## Phase 3 notes

- **New tools (5, total 68):** `adjust_session`, `compress_session`,
  `substitute_exercise`, `log_session_adjustment`, `read_session_adjustments` — all
  in the new `server/autoregulation_tools.py` (registered in `server/app.py`).
  `adjust_session`/`compress_session` look the session up by id in the latest
  structured program (`store.find_session_plan`); `read_session_adjustments` and
  `log_session_adjustment` also return the rolling-window `escalation` block.
- **Engine/memory split (purity preserved):** `engine/autoregulation.py` is pure —
  it imports ONLY stdlib + engine siblings (`engine/load.ReadinessBand`,
  `engine/strength.warmup_scheme`, `engine/substitutions`) and operates on
  engine-local `@dataclass`es (`Session`/`Block`/`BlockDelta`/`CompressedSession`/
  `AdjustmentRecord`). It NEVER imports `memory.schemas`, mirroring the
  `engine/season.py` ↔ `memory/season.py` pattern; `tests/engine/test_engine_purity.py`
  passes. `memory/autoregulation.py` owns all `SessionPlan` ↔ engine conversion,
  builds the red-readiness recovery `SessionPlan`, and does the file I/O for
  escalation counting (`datetime`-based days-ago). `engine/substitutions.py` holds
  the per-movement-pattern swap table.
- **Escalation logic location:** deterministic and pure in
  `engine.count_escalation_signals` (≥3 downward readiness adjustments OR ≥3 time
  compressions in a rolling 14-day window); `memory.autoregulation.escalation_signals`
  only converts stored entries → engine records with a reference datetime. Unit-tested
  with fixtures at both layers.
- **Schema/storage:** new `SessionAdjustmentEntry` (schema_version 1) with a bounded
  `AdjustmentInputs` submodel → append-only `session_adjustments.jsonl`, mirroring
  `append_session`/`read_sessions`. A day-of adjustment is NEVER a program version.
- **Evidence decisions:** no new corpus entries (no verified network). The RIR/RPE
  adjustment step sizes (RPE −1 / RIR +1 / −5% 1RM) are labeled team-chosen prior /
  coaching judgment in code (Helms et al. named in-spirit only, NOT added to the
  corpus unverified). The per-set time model, the −25% volume cut, escalation
  thresholds, and every substitution-table entry are labeled team-chosen prior /
  coaching judgment — no fabricated citations.
- **Skills:** new `skills/session-day/SKILL.md` (pre-session ritual, escalation
  route to program-adaptation, never versions a program); `session-day` added to
  `EXPECTED_SKILLS` in `tests/skills/test_structure.py` with a focused protocol test.
  `performance-coach` routes to it; `training-checkin` and `program-adaptation` read
  `read_session_adjustments` as a diagnostic signal; `program-optimization` now
  authors each session's `Fallbacks` via the same engine logic (and calls
  `substitute_exercise` for the missing-equipment line).
- **Substring guard:** `log_session` is a substring of `log_session_adjustment`, so
  the session-day skill declares `log_session` too (the tool-reference test matches
  substrings); the skill text distinguishes them explicitly.
- **Report templates / i18n READMEs:** no new athlete-visible report section this
  phase (day-of adjustments are ephemeral, not a program artifact); the batched
  report pass and the 4 `docs/i18n/` READMEs stay DEFERRED to the pre-release
  refresh. English README updated to 68 tools / 823 tests + a day-of-autoregulation
  phrase.

## Phase 4 notes

- **New tool (1, total 69):** `check_week_sequencing(week, strength_priority=True)`
  in `server/memory_tools.py` (it needs a `WeekPlan` and reads the athlete's stored
  calendar + profile, so it lives with the memory-layer tools, not `engine_tools.py`).
  Returns `{violations: [{rule_id, severity, session_ids, message}], block_count,
  warn_count}`.
- **Engine/memory split (purity preserved):** `engine/sequencing.py` is pure — it
  imports ONLY stdlib + `engine._validation` and operates on engine-local
  `@dataclass`es (`SessionInput`/`RecurringInput`/`Violation`). It does NOT import
  `memory.schemas`; `tests/engine/test_engine_purity.py` passes. `memory/sequencing.py`
  converts `WeekPlan` + `list[RecurringConstraint]` → engine inputs, supplies the
  per-day available minutes, and calls the pure `check_week_sequencing`;
  `check_week_for_athlete` reads calendar/profile from the store. Mirrors the
  `engine/season.py` ↔ `memory/season.py` pattern.
- **Rules (all day-based on the `weekday` field, 0=Mon):** R1 same-pattern heavy
  spacing (<48h block; 72h when the week's `volume_factor ≥ 1.1`), R2 HIIT the day
  before lower-body `strength_heavy` (block), R3 same-day strength+endurance ordering
  (warn, only when `strength_priority`), R4 >2 consecutive high days (block; high =
  strength_heavy|hiit|match, match weekdays from `RecurringConstraint.match_day`), R5
  match −1 low/priming & +1 recovery/low (block), R6 endurance_long before a
  match/HIIT (warn), R7 per-day total `est_minutes` (sessions + recurring load) vs the
  athlete's available minutes (block). block ↔ warn split: block = R1,R2,R4,R5,R7;
  warn = R3,R6.
- **Per-rule evidence decisions:** NO new corpus entries (no verified network). Every
  rule constant is labeled `team-chosen prior` / coaching judgment in code. The plan
  names Wilson et al. 2012 (concurrent-training meta) and Coffey & Hawley for the R1/R2
  interference rules — these are NOT in the evidence corpus, so no corpus id is claimed;
  the module docstring records that the thresholds reflect that literature in spirit
  only, consistent with the anti-fabrication rule and Phase 2/3's approach.
- **Unscheduled sessions:** a `SessionPlan` with `weekday=None` cannot be placed in the
  week, so it is skipped by every day-based rule (R1–R7). Documented in the engine
  docstring and the tool description — the coach must assign weekdays before the check
  is meaningful. A week that leaves sessions unscheduled simply returns no violations
  for them (not a false pass on scheduled ones).
- **R7 available-minutes decision:** the per-day budget is `Profile.availability
  .minutes_per_session` (the athlete's daily training window); None → R7 disabled.
  Recurring club/match minutes on a day count toward that day's total. A day with two
  sessions summing over the window is flagged — a defensible team decision, documented.
- **Skills:** `program-optimization` gained §3b — after laying out each week it MUST run
  `check_week_sequencing`, iterate to zero `block` (max 3 attempts, then surface the
  constraint conflict honestly), and note every `warn` tradeoff in the week `notes`.
  `program-review` compliance pass item 8 re-runs the check on EVERY week — any `block`
  → RETURNED; an unacknowledged `warn` is itself a fail. `check_week_sequencing` added
  to both skills' `tools:` frontmatter and to the structure-test needle lists.
- **Report templates / i18n READMEs:** no new athlete-visible report section (sequencing
  is a build-time gate, not a program artifact); the batched report pass and the 4
  `docs/i18n/` READMEs stay DEFERRED to the pre-release refresh. English README updated
  to 69 tools / 860 tests + a sequencing/interference phrase.

## Phase 5 notes

- **New tools (4, total 73):** `compute_response_profile`, `save_response_profile`,
  `read_response_profile`, `compare_prescribed_actual` — all in the new
  `server/response_tools.py` (registered in `server/app.py`). Two existing tools
  gained OPTIONAL params (backward compatible): `assess_strength_goal` /
  `assess_endurance_goal` / `assess_hypertrophy_goal` / `assess_bodycomp_goal` gained
  `measured_weekly_rate` (+ `measured_n_weeks`), and `weekly_set_targets_for` gained
  `tolerance_adjustment`.
- **Engine/memory split (purity preserved):** `engine/response.py` is pure — it
  imports ONLY stdlib + engine siblings (`engine/strength`, `engine/_validation`) and
  operates on engine-local `@dataclass`es (`SessionSets`/`TimelinePoint`/
  `ProgressionRate`/`PlannedSession`/`LoggedSession`/`ComplianceReport`/
  `VolumeTolerance`/`ResponseProfileData`). It NEVER imports `memory.schemas` or
  `datetime`; `tests/engine/test_engine_purity.py` passes. `memory/response.py` owns
  all date→day/week conversion and `SessionEntry`/`ProgramPlan`→engine extraction,
  builds the pydantic `ResponseProfile`, and the implausible-entry exclusion (reuses
  `engine.flag_implausible_session`, dropping `e1rm_jump`-flagged points). Mirrors the
  `engine/season.py` ↔ `memory/season.py` pattern.
- **Versioned-yaml store:** added `_doc_path`/`_latest_doc_version` a `suffix` param
  (default `.md`, kept DRY) and a parallel `save_response_profile` /
  `read_response_profile` / `latest_response_profile_version` in `store.py`. A
  `ResponseProfile` persists to `response/response-profile-v{N}.yaml` (`schema_version:
  1`) with the SAME immutable-versioned discipline as programs: never overwritten,
  reason mandatory from v2, store stamps version/as_of/reason. `ResponseProfile`
  carries `version`/`reason` fields (like `ProgramPlan`) so the yaml payload is
  self-describing.
- **assess_* backward-compat:** params are optional (default None → unchanged
  behaviour, existing tests untouched). The return type changed from
  `FeasibilityResult`/`BodycompFeasibility` to a `GoalAssessment`/`BodycompAssessment`
  TypedDict that keeps every existing top-level field AND adds `measured` (null unless
  a measured rate is supplied). Existing tests read the same keys and still pass; new
  `measured` key carries the recalibrated probability + `small_n`. Engine helper
  `recalibrated_feasibility` shares the population logistic so the two probabilities
  are directly comparable.
- **Honesty about n (returns None, never a fabricated rate):** `progression_rate`
  returns None below 6 points or a 4-week span (and on zero span); `volume_tolerance`
  returns None below 8 aligned weeks or when either series is flat, and reports
  association DIRECTION only (never causal); `compute_response_profile` records n,
  window_weeks, r2 per rate and appends a caveat wherever a signal is thin or absent
  (null measured rate → "using population prior"). Property-tested: a synthetic linear
  rate r is recovered within 1e-3.
- **Evidence decisions:** no new corpus entries (no verified network). Every new
  constant (min points/span, tolerance week/correlation thresholds, measured small-n
  window, done-volume fraction, tolerance-adjustment landmarks) is labeled
  `team-chosen prior` in code; the tolerance-adjusted set targets stay bounded by the
  existing corpus-anchored `WEEKLY_SET_TARGETS` min/max landmarks.
- **Skills:** `training-checkin` (+compute/save profile + compare tools; recompute &
  narrate deltas at each mesocycle end), `needs-analysis` and `program-planning`
  (+`read_response_profile`; pass the measured rate to the feasibility tools / size to
  it, map a tolerance flag to `weekly_set_targets_for`; program-planning also places a
  `TestMilestone` at each mesocycle end), `program-adaptation` (+`compare_prescribed_actual`
  / `read_response_profile`; adherence & tolerance flags in the diagnosis vocabulary).
  All new tools added to the relevant `tools:` frontmatter and referenced in the body.
- **Report templates / i18n READMEs:** the P5 response-summary report section (measured
  vs prior rates, adherence) stays DEFERRED to the batched report pass, like the
  earlier phases (plan-sanctioned follow-up; no athlete-visible report change wired
  this phase). The 4 `docs/i18n/` READMEs stay for the single batched pre-release
  refresh. English README updated to 73 tools / 902 tests + an individualized-recalibration
  phrase.

## Phase 6 notes

- **New tools (2, total 75):** `recommend_deload`, `build_return_progression` — both
  pure engine wrappers in `server/engine_tools.py` (registered in `register()`). The
  tool `build_return_progression` shares its name with the engine function, so the
  engine one is imported as `engine_build_return_progression` (same aliasing pattern
  as Phase 2's `engine_*` imports).
- **New engine modules (pure, purity test green):** `engine/regulation.py`
  (`should_deload`) and `engine/return_to_load.py` (`build_return_progression`). Both
  take plain numbers / bools only — no datetime, no `memory.schemas` — so
  `tests/engine/test_engine_purity.py` passes unchanged. `return_to_load.py` imports
  `math` (allowed) for `math.ceil`.
- **Deload thresholds (all team-chosen priors, documented in-code):**
  `weeks_since_deload >= planned_interval_weeks + 1` → `full` regardless (planned
  counter is the backstop; `planned_interval_weeks` default 4); `tsb < -25` with
  readiness trend `<= 0` → `full` when adherence `>= 70%`, else downgraded to `light`
  (fatigue signals unreliable under low adherence → adherence playbook); `monotony >
  2.0` with `strain_trend > 0` → at least `light`. `full` dominates `light` when both
  fire. Returns a descriptive `{recommendation, drivers}` — the LLM decides/narrates.
  `should_deload` gained a 7th param `planned_interval_weeks` beyond the plan's literal
  6-arg signature because the "≥ planned interval + 1" rule needs it (the plan text
  names the rule; the signature omitted the input). Kept a default so callers that
  only pass the 6 monitoring args still work.
- **Return-to-load bands (team-chosen priors):** `< 1 wk off` → 0.90 vol / 0.95 int;
  `1–2` → 0.70/0.85; `2–4` → 0.50/0.70; `> 4` → 0.40/0.60. Ramp then climbs +12.5%/wk
  volume, +7.5%/wk intensity (12.5% = midpoint of the plan's 10–15% band), capped at
  1.0, both reaching baseline on the last week; longer layoff → lower start → longer
  ramp (property-tested). Every progressing week's note encodes the 24h rule (pain
  ≤3/10 clearing within 24h = advance, else repeat the week). `pain_free=False` returns
  a single holding week at the band start (no progression through pain).
- **Clearance gating:** the HARD "only after professional clearance" precondition is
  enforced at the tool boundary — the `build_return_progression` MCP tool takes an extra
  `cleared_by_professional: bool` (not in the engine signature) and raises a refer-out
  ValueError when it is False (server test `test_build_return_progression_tool_requires_
  clearance`). The `program-adaptation` return-to-load branch requires the athlete to
  confirm clearance before calling it, preserves refer-out language, and never programs
  through pain.
- **Evidence decisions:** no new corpus entries (no verified network). The return-to-
  sport consensus (Ardern et al. 2016) and detraining/retraining (Mujika & Padilla)
  named in the plan are referenced in the module docstring "in spirit only" and every
  constant is labelled `team-chosen prior` — consistent with Phases 2–5's anti-
  fabrication approach; no unverified citations added.
- **Overreach scenario test:** `test_overreach_scenario_fires_full_after_spike` builds
  6 calm weeks then a spike week of daily loads, runs the real `fitness_fatigue_series`
  / `weekly_strain`, confirms TSB is driven below −25 with a negative readiness trend,
  and asserts `should_deload` returns `full` with a TSB driver — within the one injected
  spike week.
- **Skills:** `program-adaptation` gained a deload branch (calls `recommend_deload`,
  quotes drivers), a return-to-load branch (clearance-gated, `build_return_progression`,
  `return_to_load` mesocycle phase, refer-out preserved), and an adherence playbook
  (persistent <70% → diagnose cause in the athlete's words → 2-day minimum-effective
  template via `weekly_set_targets_for`'s `minimum_effective_sets`, renegotiate cadence,
  version with that reason, never shame). `training-checkin` surfaces `recommend_deload`
  proactively before fatigue hits 8. New tools added to both skills' `tools:` frontmatter
  and referenced in the body; existing needles preserved.
- **Report templates / i18n READMEs / docs/installing.md:** the batched report pass and
  the 4 `docs/i18n/` READMEs stay DEFERRED to the single pre-release refresh; the
  `docs/installing.md` tool-count line is also left for that batched refresh (known
  batched items). English README updated to 75 tools / 957 tests + a deload/return-to-
  load phrase.

## Phase 7 notes

- **New tool (1, total 76):** `list_due_actions()` in `server/memory_tools.py` (it
  reads many athlete files, so it lives with the memory-layer tools). Returns a list
  of `DueActionView` = `{kind, severity, message_key, due_since_days|due_in_days,
  ref}`, sorted most-severe-first. It returns **facts, not prose** — a stable
  locale-neutral `message_key` plus the numbers; the LLM renders the sentence in the
  athlete's language. An all-green athlete returns `[]`.
- **Engine/memory split (purity preserved):** `engine/diligence.py` is pure — it
  imports ONLY stdlib (`dataclasses`, `typing`) and operates on engine-local
  `@dataclass`es (`DiligenceFacts` = already-extracted numbers/bools, `UpcomingEvent`,
  `DueAction`). It has NO datetime and NO `memory.schemas` import;
  `tests/engine/test_engine_purity.py` passes. `memory/diligence.py` owns ALL file
  reading and date math (time context, program cadence, calendar, sessions,
  readiness, response profile → `DiligenceFacts`) and maps `DueAction` → the JSON
  view. Mirrors `engine/season.py` ↔ `memory/season.py`. Deterministic via an
  optional `today` param, like `build_time_context` / `build_season_plan`.
- **Due conditions implemented (7 kinds):** `checkin` (overdue past
  `checkin_cadence_days`, or never — only when a program exists), `event` (A/B within
  21 days), `missed_sessions` (expected weekly training days minus sessions logged in
  the last 7 days), `readiness_gap` (≥3 recent training days with no readiness read),
  `calendar_incomplete` (an active goal has a deadline but the calendar has zero
  events), `response_profile_stale` (>6 weeks / 42 days since `as_of`),
  `readiness_red_streak` (trailing run of red readiness reads).
- **Severity ordering:** `high` > `medium` > `low`; within a severity, most urgent
  first (soonest upcoming event, longest overdue), then a stable tiebreak on
  kind + ref → fully deterministic. Severity assignment: check-in high once a full
  extra cadence late (else medium; never-checked-in = high); A event high ≤14 d else
  medium ≤21 d; B event medium ≤7 d else low ≤21 d; missed ≥3 high else medium;
  readiness gap medium; calendar_incomplete medium; profile stale low; red streak ≥3
  high else medium (≥2). Every threshold is a **team-chosen prior** (no corpus rule
  prescribes coach-outreach timing) — labeled in code, consistent with Phases 2-6.
- **`message_key` approach:** the tool never emits a localized sentence. Keys are
  `checkin_overdue`, `checkin_never`, `event_approaching`, `missed_sessions`,
  `readiness_gap`, `calendar_incomplete`, `response_profile_stale`,
  `readiness_red_streak`; the `performance-coach` skill renders each in the athlete's
  locale and quotes the numbers.
- **New doc:** `docs/proactive-reminders.md` — documents `list_due_actions` and
  OPTIONAL client-side reminder recipes (cron / launchd / scheduled agent run that
  opens a session with "coach check" so the tool fires). Explicitly optional, no
  server change; the server stays passive (stdio request/response, cannot push).
- **Skill:** `performance-coach` calls `list_due_actions` immediately after
  `get_time_context` and OPENS with the top items (the coach speaks first);
  `list_due_actions` added to its `tools:` frontmatter and body. Existing needles and
  the tool-reference test preserved (only added).
- **No new corpus entries** (no verified network); no evidence needed (follow-up
  timing is coaching judgment, not a cited prescription).
- **Report templates / i18n READMEs / docs/installing.md:** the batched report pass,
  the 4 `docs/i18n/` READMEs and the `docs/installing.md` tool-count line stay
  DEFERRED to the single pre-release refresh (known batched items). English README
  updated to 76 tools / 987 tests + a proactive-follow-up phrase.

## Phase 8 notes

- **New tests (14, total 1001; +0 tools, still 76):** `tests/e2e_sim/` — a
  deterministic simulation harness (`harness.py`) driving the REAL engine + store
  against three synthetic personas. No LLM anywhere; every date is explicit
  (`today=`, ORIGIN = Monday 2026-01-05) and the only "randomness" is a SEEDED
  `random.Random(seed)` (P1's ±1% load noise, seed 101). Runs identically every time.
  Added `tests/e2e_sim/__init__.py` (the repo's test subdirs are packages).
- **Personas & the assertions each exercises:**
  - **P1 runner** (`test_persona_p1_runner.py`): season P1 invariants (segments tile
    the horizon; taper ends the week before the A race, competition on it); zero
    `block` sequencing violations in *every* generated week; response-profile recovery
    of an injected 0.6%/week strength progression within ±0.2 pts
    (`compute_response_profile`); an injected 400 kg implausible squat flagged
    (`session_plausibility_flags` → `e1rm_jump`) and excluded from the fitted rate;
    every program version has a reason.
  - **P2 footballer** (`test_persona_p2_footballer.py`): external load present in the
    weekly totals (majority share from club/match `source="external"`); zero `block`
    violations for a footballer week (lifting off match ±1); an injected fixture
    pile-up week firing `should_deload != "none"` within one simulated week, driven by
    the real `fitness_fatigue_series` / `weekly_strain` / `weekly_monotony`;
    `list_due_actions` surfacing both `missed_sessions` and `readiness_gap` after a
    silent week.
  - **P3 Hyrox** (`test_persona_p3_hyrox.py`): a mixed-modality season with a taper
    before the A race and only a secondary-event surface for the B race; a calendar
    change (A race moved +2 weeks, re-planned from week 6) that keeps a taper
    immediately before the new date and saves a v2 whose reason cites the new date;
    zero `block` violations for the 4-day intervals/stations/brick/long template; a
    return-to-load ramp after a 2-week break (`build_return_progression`: starts below
    baseline, monotone non-decreasing, reaches 1.0) persisted as a `return_to_load`
    program version with a reason; every version has a reason.
- **Determinism approach:** seeded RNG + explicit dates only, as above. The response
  profile keys its per-goal rate off the tracked lift (`Back Squat`) via the store's
  real alignment anchor (program `created_on`); for the runner the S&C lift is the
  natural carrier of a measurable rate (a pure-pace rate is not what the response
  engine measures — noted here, not a gap).
- **No production code changed.** The harness is pure test code under `tests/e2e_sim/`
  so it may import across layers; it drives only the existing public store/engine/
  memory APIs. No engine/memory bug was found while wiring the sim — the prior phases
  compose as designed. Tool count unchanged (76). Manual gate re-verified green:
  pytest (1001), ruff check + format, ty, prek --all-files.
- **New doc:** `docs/eval-checklist.md` — a short MANUAL skill-level eval script (the
  3 personas + expected agent behaviours + cross-cutting safety/honesty checks) for
  release testing with a live LLM, the human counterpart to the LLM-free sim.
- **Report templates / i18n READMEs / docs/installing.md:** unchanged this phase.
  Remaining pre-release BATCHED items for the main orchestrator (NOT this phase):
  the i18n README refresh (test/tool counts in `docs/i18n/README.{fr,it,es,de}.md`),
  the `docs/installing.md` tool-count line, the Typst report-template sections
  (P1 season overview / P2-P9 load trends / P5 response summary), and the single PyPI
  release. English README updated to 1001 tests + the simulated-e2e "Working today"
  claim (tool count stays 76).

## Resume notes

_All phases (0, 1, 2, 9, 3, 4, 5, 6, 7, 8) complete. Phase 8 is the last. Remaining
before release are the batched, non-phase items listed in the Phase 8 notes above
(i18n README refresh, `docs/installing.md` tool-count line, Typst report-template
sections, single PyPI release) — for the main orchestrator, not a phase branch._
