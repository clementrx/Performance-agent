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
| 6 | 4 | Intra-week sequencing & interference | done (PR open) | `feat/phase-4-sequencing` — PR (base: phase 3) | 860 tests; +1 tool (69 total) |
| 7 | 5 | Individual response profile | pending | — | — |
| 8 | 6 | Deloads, adherence, return-to-load | pending | — | — |
| 9 | 7 | Proactive follow-up | pending | — | — |
| 10 | 8 | End-to-end simulated evaluation | pending | — | — |

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

## Resume notes

_Phase 4 complete. Next in execution order: **Phase 5 (individual response profile &
recalibration)** (order 0, 1, 2, 9, 3, 4, **5**, 6, 7, 8); depends on Phase 0's
structured `ProgramPlan`, Phase 2's monitoring, and Phase 3's autoregulation logs.
Branch off `feat/phase-4-sequencing` (stacked)._
