# Beyond-National Coach — Implementation Plan

**Mission.** Upgrade PerformanceAgent's *planning and organization* capabilities past a
national-level S&C coach: season-level backward planning from a real calendar,
day-level session autoregulation, full load accounting (including training the coach
doesn't program), individualized recalibration from the athlete's own logged response,
data-driven deloads, and proactive follow-up. Success means every athlete reaches the
best level their physiology, schedule and consistency allow — and the agent can prove
every decision (versioned, cited, audited) in a way no human coach can.

The product's honesty principle is untouched: the agent never promises outcomes the
feasibility engine cannot defend. "Better than a national-level coach" is a claim about
the *quality of planning decisions*, not a guaranteed performance outcome.

All athlete memory stays in the athlete directory (`PERFORMANCE_AGENT_HOME`, e.g.
`~/athlete-data`) as plain files — that directory is the coach's long-term memory
between sessions, and this plan extends what it stores (see §2).

---

## 0. How to execute this plan (instructions to the executing agent)

- This plan is **self-contained**. Do NOT use external planning/skill frameworks (no
  BMAD, no superpowers skills). Execute with native tools only.
- **Orient first.** Read: `README.md`, `pyproject.toml`, `.pre-commit-config.yaml`,
  `src/performance_agent/engine/` (all modules), `src/performance_agent/memory/`
  (`schemas.py`, `store.py`, `paths.py`, `time_context.py`),
  `src/performance_agent/server/` (`app.py`, `engine_tools.py`, `memory_tools.py`,
  `evidence_tools.py`, `report_tools.py`), every `skills/*/SKILL.md`, and the test
  layout under `tests/`. File/line anchors in this plan reflect the repo at the time of
  writing — re-verify by reading before editing.
- **Run the suite before touching anything** (`uv run pytest -q`) and record the
  baseline (597 tests at plan time).
- **Per phase:** feature branch `feat/phase-N-<slug>` → implement → full gate: the
  repo's own checks (pytest, ruff check + format, pre-commit, type checker if
  configured) all green, zero warnings → update the affected skills, README tool
  count / "Working today", and docs in the SAME branch → open a PR referencing this
  plan. **Ask the user once at the start** which merge flow they want (merge each PR
  before the next phase vs. stacked branches), then proceed without re-asking.
- **Never break existing athlete directories.** New schema fields are optional with
  safe defaults; legacy `programs/program-vN.md` (prose-only) must remain readable
  forever. Write a migration note in the PR when a file format gains fields.
- **Engine purity.** All new math = pure functions in `src/performance_agent/engine/`,
  no I/O, deterministic, property-tested (hypothesis), bounded inputs that raise on
  nonsense. Constants are module-level, each labeled with a corpus citation or
  `team-chosen prior` (existing repo convention). MCP wrappers go in
  `server/engine_tools.py` / `server/memory_tools.py` following the existing pattern
  (docstring = tool description; the LLM narrates, the engine computes).
- **Anti-fabrication.** Every new prescriptive rule referenced in a skill must either
  cite a corpus id (add the study first — see §Evidence) or be explicitly labeled
  coaching judgment. Never invent citations. `program-review` remains the mandatory
  gate for every program save.
- **Datetime convention:** naive local datetimes (timezone-aware values are rejected by
  the schemas). Keep it.
- **Language:** code, skills, docs in English (repo convention). Athlete-facing
  behavior stays locale-driven (en/fr/es).
- **Progress file.** Maintain `docs/plans/beyond-national-coach-progress.md`
  (phase → status → branch/PR → deviations → resume notes). Update it at every phase
  completion AND whenever a session is interrupted; read it FIRST when resuming.
- **Releases:** none during execution (user decision). PRs merge per phase, but the
  single PyPI release happens at the end — see Global definition of done.
- **Tool budget.** This plan grows the MCP surface from ~47 to ~70 tools; their
  docstrings load into every client context. Keep new tool docstrings compact.

**Locked product decisions (user-confirmed 2026-07-12):**

1. **Target athlete: serious competitor.** Daily readiness on training days and a
   complete dated calendar at onboarding are the DEFAULT expectation — the product
   asks for discipline and says so. The code still degrades gracefully (every tool
   accepts partial data; missing data triggers follow-up via `list_due_actions`,
   never a crash or a refusal to coach).
2. **Team sports: external-load constraint only** this iteration (club sessions and
   matches as logged load + calendar constraints). The full team-sport vertical
   (J-3/J-1 microcycles, playing-time management) stays on the roadmap.
3. **Activity-file import is pulled forward**: execute Phase 9 immediately after
   Phase 2 (execution order 0, 1, 2, 9, 3, 4, 5, 6, 7, 8).
4. **Single release at the end** — no intermediate version bumps.

---

## 1. Architecture invariants (non-negotiable)

1. LLMs narrate, the engine calculates. No number reaches the athlete that wasn't
   computed by a deterministic tool.
2. Citations only from the evidence corpus, pre-checked with `check_citations`;
   PDF rendering hard-fails on unknown references.
3. Athlete data = plain files in one directory. Atomic writes, append-only logs,
   immutable versioned documents with a mandatory `reason` from v2.
4. Nothing is saved as a program (new or adapted) without `program-review` APPROVED.
5. Safety precedence: pain/injury → stop loading that pattern, refer out. The agent
   never diagnoses and never programs *through* an active injury.

---

## 2. Target athlete-data layout (after all phases)

```
athlete-data/
  profile.yaml                     # + weekly availability by weekday (Phase 1)
  goals.yaml
  calendar.yaml                    # NEW P1: dated events + recurring constraints
  sessions.jsonl                   # + source: programmed|external, session_plan_id, avg_hr (P2)
  checkins.jsonl                   # unchanged (block-level check-ins)
  readiness.jsonl                  # NEW P2: pre-session wellness (Hooper items, optional HRV)
  session_adjustments.jsonl        # NEW P3: day-of adjustments (never a program version)
  programs/
    program-v{N}.plan.yaml         # NEW P0: structured source of truth
    program-v{N}.md                # rendered human view (generated, not hand-written)
  analysis/needs-analysis-v{N}.md
  research/dossier-v{N}.md
  nutrition/frame-v{N}.md
  response/response-profile-v{N}.yaml  # NEW P5: individual response model, versioned
  evidence_extra.yaml
```

Every NEW file format introduced by this plan (`calendar.yaml`, `*.plan.yaml`,
`readiness.jsonl` entries, `session_adjustments.jsonl` entries,
`response-profile-*.yaml`) carries a `schema_version: 1` field from day one.

---

## 3. Phase map and dependencies

| Order | Phase | Title | Depends on |
|---|---|---|---|
| 1 | 0 | Machine-readable programs | — |
| 2 | 1 | Season calendar & backward planning | — |
| 3 | 2 | Full monitoring (strain, fitness-fatigue, readiness, external load) | — |
| 4 | 9 | Activity file import (pulled forward) | 2 |
| 5 | 3 | Day-of session autoregulation | 0, 2 |
| 6 | 4 | Intra-week sequencing & interference guard | 0, 1 |
| 7 | 5 | Individual response profile & recalibration | 0, 2, 3 |
| 8 | 6 | Data-driven deloads, adherence playbook, return-to-load | 2, 5 |
| 9 | 7 | Proactive follow-up | 0, 1, 5 |
| 10 | 8 | End-to-end simulated evaluation | 0–7, 9 |

Evidence-corpus additions (§Evidence) are transversal: each phase lands its own
citations *before* its skills reference them.

---

## Phase 0 — Machine-readable programs (single source of truth)

**Goal.** Programs become structured data; the markdown becomes a deterministically
rendered view. This unblocks prescribed-vs-actual comparison (P5), day-of adjustment
(P3), and sequencing validation (P4). Today the program is free-form prose
(`store.py` `save_program`), which makes all of those impossible.

**Design.**

New Pydantic schemas in `memory/schemas.py` (strict `extra="forbid"`, bounded, same
style as existing models):

```python
ProgramPlan:   version, goal_id, created_on, reason, checkin_cadence_days (default 7),
               season_ref: str|None, test_milestones: list[TestMilestone],
               mesocycles: list[Mesocycle]
Mesocycle:     index, phase: Literal[general_prep, specific_prep, accumulation,
               intensification, realization, maintenance, taper, return_to_load],
               weeks: list[WeekPlan]
WeekPlan:      week_index (global, 1-based), is_deload, is_taper,
               volume_factor, intensity_factor,
               weekly_set_targets: dict[str,int]|None, notes: str|None,
               sessions: list[SessionPlan]
SessionPlan:   id (stable slug, e.g. "w03-s2-lower-heavy"), weekday: int|None (0-6),
               qualities: list[Literal[strength_heavy, hypertrophy, power, hiit,
               tempo, endurance_long, endurance_easy, brick, recovery, match,
               club_practice, test]],
               patterns: list[str]  # squat, hinge, push_h, push_v, pull_h, pull_v,
                                    # lunge, carry, core, run, ride, swim, ...
               est_minutes: int, purpose: str, blocks: list[ExerciseBlock],
               fallbacks: Fallbacks
ExerciseBlock: exercise: str, priority: Literal[primary, secondary, optional],
               warmup: Literal["auto", "none"] = "auto",  # auto: renderer emits
                       # ramp-up sets for primary strength work
               sets: int, reps: str|None (e.g. "5" or "8-12"),
               duration_min: float|None, distance_m: float|None,
               load_kg: float|None, pct_1rm: float|None, rir: float|None,
               rpe: float|None, pace_s_per_km: float|None,
               rest_s: int|None, progression_rule: str,  # e.g. "double_progression(...)"
               cite: str|None, notes: str|None
Fallbacks:     low_readiness: str, short_on_time: str, missing_equipment: str
TestMilestone: week_index, protocol: Literal[amrap_rir1, timetrial, one_rm_test],
               targets: list[str]  # lifts or distance labels
```

Exactly one prescription mode per block (validator: at most one of
load_kg/pct_1rm/rir/rpe/pace set, consistent with duration vs reps). `Fallbacks`
fields required non-empty (content authored by `program-optimization`; P3 adds engine
helpers that make them mechanical).

- `src/performance_agent/programs/render.py` (new): deterministic renderer
  `ProgramPlan → markdown`, same human format as today's programs (purpose lines,
  evidence grades, citations included). Golden-file tested.
- Warm-up ramping: new engine helper `warmup_scheme(target_load_kg) -> list[(pct,
  reps)]` (standard ramp, constants labeled team prior); the renderer emits it for
  `warmup="auto"` blocks in `strength_heavy` sessions so printed programs include
  the ramp-up sets a real coach writes.
- `memory/store.py`: `save_program(plan: ProgramPlan, reason)` validates, renders, and
  atomically writes BOTH `programs/program-v{N}.plan.yaml` and `program-v{N}.md`
  (same immutable `_save_versioned_doc` discipline: never overwrite, reason mandatory
  from v2). `read_program` returns `{version, markdown, plan|None}` — `plan` is None
  for legacy prose-only versions.
- MCP (`server/memory_tools.py`): `save_program` signature replaced (replace, don't
  deprecate — the LLM must now hand a structured plan), `read_program` extended.

**Skills to update.**
- `program-optimization`: rewrite the output contract — it authors the `ProgramPlan`
  (blocks, purposes, progression rules, fallbacks) instead of raw markdown; the md is
  rendered by the tool.
- `program-review`: add structural checks — plan present, weekly set sums vs
  `weekly_set_targets`, every session has non-empty purpose and fallbacks, every
  `cite` id passes `check_citations`.
- `program-planning`, `program-adaptation`: hand off / re-save through the new format.
- `training-checkin`: at the FIRST check-in after this upgrade, offer to regenerate
  the active prose program as a structured version (vN+1, reason = "format
  upgrade", passes program-review as usual) so P3/P5 features unlock without
  waiting for the next natural program change.

**Tests.** Schema round-trip (yaml↔model), renderer golden test, single-prescription-
mode validator, legacy read path, immutability preserved, property: every exercise in
the plan appears in the rendered md; version numbering unaffected.

**Acceptance.** A new program saves as a yaml+md pair; an old athlete dir with prose
programs still reads and adapts; suite green.

---

## Phase 1 — Season calendar & backward planning

**Goal.** Replace "one deadline + a 3-value enum" with a real, first-class calendar,
and plan the season backward from it. Today: one `deadline` per goal,
`calendar_type` enum, `build_inseason_maintenance` reasons on one isolated week
(`engine/periodization.py:252`), no multi-event logic, and the periodization builders
are uncoordinated.

**Design.**

Schemas (`memory/schemas.py`) + new athlete file `calendar.yaml`:

```python
CalendarEvent:       id (slug), date, kind: Literal[competition, test, camp, travel,
                     holiday, other], priority: Literal[A, B, C], label,
                     goal_id: str|None (links the event to goals.yaml),
                     sport: str|None, notes: str|None
RecurringConstraint: weekday (0-6), kind: Literal[club_practice, match_day,
                     unavailable], est_minutes: int|None, est_srpe: float|None (CR10),
                     label
Calendar:            events: list[CalendarEvent], recurring: list[RecurringConstraint]
```

`Profile.availability` gains optional `weekdays: list[int]|None` (the real training
days, not just a count). Optional fields only — old profiles keep loading.

Engine — new module `engine/season.py` (pure, property-tested):

- `plan_season(events, start_date, min_block_weeks=3) -> list[SeasonSegment]` where
  `SeasonSegment = {start_week, end_week, phase_type, anchor_event_id, rationale}`.
  Algorithm (deterministic backward pass):
  1. Sort A-priority competitions descending; for each, reserve taper
     (`recommend_taper_length`), competition week, then 1 transition week if another
     segment follows.
  2. Fill remaining gaps forward with development blocks: `block` phases if the gap
     ≥ 6 weeks (matching `MIN_BLOCK_WEEKS`), else `waves`.
  3. B events: embedded light week / 3–4-day mini-taper inside the current block —
     never a full taper. C events: train through, flag only.
  4. Two A events < 6 weeks apart → maintenance bridge between them + explicit
     `compromise` flag in the rationale (the LLM must surface it honestly).
  5. Planned breaks (`holiday`/`travel` ≥ 14 days): insert a `maintenance` segment
     (minimal travel template noted) followed by a 1-week re-entry ramp on return
     (short band of P6's `build_return_progression`; until P6 lands, flag it in the
     rationale).
  6. Multi-goal arbitration: events carry `goal_id`; when events of two goals
     conflict, the A-priority goal's events win and the compromise is stated in the
     rationale.
- `recommend_taper_length(buildup_weeks, modality: Literal[strength, endurance,
  mixed], event_priority) -> days` — bounded 4–14 days; defaults sourced from the
  taper meta-analysis already in the corpus (`tapering-performance-meta-2007`:
  ~8–14 days endurance, shorter for strength; label remaining spread as team prior).

MCP tools: `upsert_calendar_event`, `remove_calendar_event`, `read_calendar`,
`build_season_plan`, `recommend_taper`. Extend `get_time_context`
(`memory/time_context.py`) with: next A/B events + countdowns, active recurring
constraints for the current week.

**Skills to update.**
- `athlete-onboarding`: new calendar step — collect ALL dated events (competitions
  with A/B/C priority, camps, travel, exam periods) and weekly recurring constraints
  (club sessions with typical duration + intensity, match day, unavailable days) →
  `calendar.yaml`; collect real training weekdays into the profile. This step is
  MANDATORY (serious-competitor decision): an athlete with no dated events must
  explicitly confirm it before `open_ended` is accepted. The goal deadline remains
  on the goal; the calendar is the scheduling source of truth.
- `program-planning`: when ≥1 dated event exists, MUST call `build_season_plan` and
  chain the existing builders per segment (block/waves/peaking/in-season per
  `phase_type`); quote each segment's rationale. `ProgramPlan.season_ref` records it.
- `training-checkin`: always ask "any calendar changes?"; a changed/added/removed
  dated event routes to `program-adaptation` for a replan of affected segments (new
  program version, reason = the calendar change).
- `program-review`: verify taper lands immediately before each A event and B/C events
  got the right treatment.

**Tests.** Properties: segments tile the horizon with no overlap; taper always
immediately precedes its A event; B never receives a full taper; determinism. Units:
0 events → open-ended fallback; 2 A events 4 weeks apart → compromise flag; event in
the past → rejected. Hypothesis over random event sets.

**Acceptance.** A fixture season (two dated races 16 weeks apart + weekly club
constraint) yields a coherent multi-segment plan; moving race 2 by two weeks produces
a new program version whose reason cites the date change.

---

## Phase 2 — Full monitoring: strain, fitness-fatigue, readiness, external load

**Goal.** See fatigue coming instead of finding it at ≥8/10, and count the load the
coach doesn't program. Today: sRPE + coupled rolling 7/28 ACWR only
(`engine/load.py`), single `fatigue` scalar at check-in, no external-load concept
(grep-confirmed).

**Design.**

`engine/load.py` additions (constants labeled, citations added to corpus first):

- `weekly_monotony(daily_loads_7) -> float|None` = mean/σ (population σ, zero days
  count; σ=0 → None + flag). `weekly_strain(daily_loads_7)` = weekly load × monotony.
  (Foster 1998 — the missing half of the already-implemented sRPE method.)
- `fitness_fatigue_series(daily_loads, ctl_tau=42, atl_tau=7) -> list[DayState]` with
  `DayState = {date_index, ctl, atl, tsb}` — EWMA impulse-response (Coggan-style
  CTL/ATL/TSB). Presented as descriptive fitness/fatigue/freshness trends; taus
  overridable, labeled conventions. (True two-exponential Banister fitting stays on
  the roadmap; this is its deterministic precursor.)
- `readiness_score(sleep, fatigue, soreness, stress, hrv_delta_pct=None) ->
  {score_0_100, band: green|amber|red, drivers}` — Hooper items each 1–7 (1 = best),
  inverted/normalized; optional HRV modifier (±); band thresholds team priors
  (document them: e.g. ≥75 green, 50–74 amber, <50 red).
- `estimate_srpe_from_hr(avg_hr, hr_max) -> float` — CR10 estimate from %HRmax
  (Foster's table) for club sessions and future imports.
- `budget_weekly_load(target_weekly_load, external_loads) -> {programmable_budget,
  conflict: bool, drivers}` — subtract recurring external load; conflict when budget
  < the week's minimum effective programmed load.
- `acute_chronic_ratio`: add `method: Literal["rolling","ewma"]="rolling"` (EWMA
  variant per Williams et al.; keep the descriptive-only framing).
- `flag_implausible_session(entry, history) -> list[Flag]` — data-quality guards
  that protect P5's learning loop from noise: e1RM jump > 15% vs. recent history,
  load > known 1RM × 1.15 outside a test context, duration/distance outliers.
  Thresholds labeled team priors.

`engine/endurance.py`: `training_zones_from_race(distance_m, time_s) -> 5 pace zones`
derived from a Riegel-based threshold estimate; assumptions labeled.

Schemas: `SessionEntry` += `source: Literal["programmed","external"]="programmed"`,
`session_plan_id: str|None`, `avg_hr: float|None` (all optional → backward
compatible). New `ReadinessEntry {at, sleep, fatigue, soreness, stress (1-7 each),
hrv_ms: float|None, notes}` → append-only `readiness.jsonl` (same store mechanics as
sessions).

MCP tools: `compute_monotony_strain`, `compute_fitness_fatigue`, `compute_readiness`,
`log_readiness`, `read_readiness`, `endurance_zones`, `budget_weekly_load`,
`flag_implausible_session`; extend `compute_acwr` with `method`. `log_session`
returns plausibility flags with its result; the skill must confirm flagged values
with the athlete before treating them as facts (entries stay logged, flags recorded).

**Skills to update.**
- `training-checkin`: explicitly ask "anything I didn't program? club practice,
  matches, physical work" → log as `source="external"` with estimated sRPE; weekly
  load narration must state the external share; quote monotony/strain and TSB trends
  alongside ACWR (all descriptive).
- `program-planning` / `program-optimization`: pull recurring constraints from the
  calendar, compute the external load budget, and size programmed volume within it;
  surface conflicts honestly (reduce target or accept higher total with monitoring).
- `performance-coach`: daily readiness on training days is the DEFAULT expectation
  (serious-competitor decision) — the ritual asks for it when today is a planned
  training day and none is logged; framed as the professional standard, never as a
  blocker (the coach still works with partial data).

**Tests.** Foster worked examples from the literature; EWMA properties (constant load
→ ctl converges to load; tsb sign flips after a spike); readiness bounds and band
edges; budget conflicts; zone monotonicity; hypothesis fuzzing on all inputs.

**Acceptance.** For a synthetic footballer week (3 club sessions + 1 match external,
2 gym sessions programmed), weekly narration shows total vs external load, strain,
TSB trend, and a budget-aware programmed volume.

---

## Phase 3 — Day-of session autoregulation

**Goal.** Give the agent the coach's most-used skill: adjust *today's* session in
30 seconds. Today the smallest adaptation unit is a full re-versioned program through
the review gate, and generated sessions embed no contingency rules (grep-confirmed).

**Design.**

New `engine/autoregulation.py`:

- `adjust_session_for_readiness(session: SessionPlan, band) -> AdjustedSession`
  (deterministic deltas): green = unchanged; amber = top-block intensity down one
  step (target RPE −1 / RIR +1 / pct_1rm −5pts), back-off & secondary volume −20–30%,
  optional blocks dropped; red = replace with a recovery template (technique / Z1–Z2
  aerobic / mobility) or rest — never `strength_heavy`, never HIIT. Returns the
  adjusted session + a machine-readable delta summary.
- `compress_session(session, available_minutes) -> CompressedSession` — time model
  per block: `sets × (≈40s work + rest_s)` + the block's generated warm-up sets
  (P0's `warmup_scheme`); cut order: optional →
  secondary back-off volume → superset accessories; primary top work survives if it
  fits at all; returns plan + what was cut.
- `substitute_exercise(exercise, pattern, available_equipment) -> alternatives` from
  a curated substitution table (data module, per movement pattern; each entry cited
  or labeled judgment).

New append-only file `session_adjustments.jsonl`:
`{at, session_plan_id, kind: readiness|time|equipment|manual, inputs (band/minutes/
missing), deltas_summary, applied: bool}`.

MCP tools: `adjust_session`, `compress_session`, `substitute_exercise`,
`log_session_adjustment`, `read_session_adjustments`.

New skill `skills/session-day/SKILL.md` — the pre-session ritual:
1. Trigger: athlete says "I train tonight / now / in an hour" (performance-coach
   routes here).
2. Read today's planned session from the structured program; quick readiness (use
   today's `readiness.jsonl` entry, else ask the 4 Hooper items — one line).
3. Call the engine, present the adjusted/compressed session with the WHY in one
   sentence, log the adjustment. **Never creates a program version.**
4. Escalation rule: ≥3 downward adjustments (or ≥3 compressions) within 14 days →
   route to `program-adaptation` (the plan no longer fits the life).

`program-optimization` must now author every session's `Fallbacks` strings using the
same engine logic (so the printed program is self-serve when the athlete is offline:
"tired: top set at RPE 7, skip block C", "35 min: A + B1 only", "no rack: goblet
squat 3×10 @ RIR 2").

**Skills to update.** `performance-coach` (routing), `training-checkin` and
`program-adaptation` (read adjustments as diagnostic signals: repeated time
compressions = schedule mismatch, repeated readiness downgrades = under-recovery).

**Tests.** Properties: adjusted volume ≤ original; red output contains no
strength_heavy/hiit quality; compression keeps primary blocks whenever
`available_minutes ≥ their cost`; determinism. Golden render of an adjusted session.
Unit: escalation counting logic fixtures.

**Acceptance.** Scripted flow "slept 4h, only 40 minutes" on a fixture program yields
a compressed amber session, logged in `session_adjustments.jsonl`, program version
unchanged; the same signals three times in two weeks triggers the adaptation route.

---

## Phase 4 — Intra-week sequencing & interference guard

**Goal.** Encode what separates a coach from a spreadsheet: the order of the week.
Today: volume is allocated by priority but no spacing/ordering/interference rule
exists anywhere (grep-confirmed); `build_undulating_sessions` cycles heavy/light/
moderate blind to content.

**Design.**

New `engine/sequencing.py`:
`check_week_sequencing(week: WeekPlan, recurring: list[RecurringConstraint]) ->
list[Violation]` with `Violation = {rule_id, severity: block|warn, session_ids,
message}`. Rules (each with a corpus citation or labeled judgment; constants
module-level):

- **R1** ≥48h between two `strength_heavy` sessions loading the same primary pattern
  (72h when the week's `volume_factor ≥ 1.1`).
- **R2** no `hiit` within 24h *before* lower-body `strength_heavy` (acute
  interference; Wilson 2012 meta, Coffey & Hawley).
- **R3** same-day strength + endurance: strength first when a strength/hypertrophy
  goal is A-priority; ≥6h gap ideal → otherwise `warn` with the tradeoff stated.
- **R4** no more than 2 consecutive high days (high = strength_heavy | hiit | match).
- **R5** match day −1 = low/priming only; match day +1 = recovery/low (uses
  `RecurringConstraint.match_day` and calendar events).
- **R6** `endurance_long` not the day before a match or a key hiit session.
- **R7** per-day total `est_minutes` ≤ the athlete's available minutes.

MCP tool: `check_week_sequencing`.

**Skills to update.**
- `program-optimization`: after laying out each week, MUST run the check and iterate
  until zero `block` violations (max 3 attempts, then surface the constraint conflict
  to the athlete honestly instead of silently violating).
- `program-review`: re-runs the check on every week; any `block` violation →
  RETURNED. `warn` violations must be acknowledged in the program notes.

**Tests.** One constructed week per rule that triggers it; zero-violation reference
templates for 2–6 sessions/week pass; determinism; property: permuting session days
changes violations consistently.

**Acceptance.** Heavy squat Monday + heavy deadlift Tuesday gets blocked; the Hyrox
4-day template (intervals / stations / brick / long easy) passes; a footballer week
places lifting away from match ±1 day.

---

## Phase 5 — Individual response profile & recalibration

**Goal.** Learn the athlete instead of forever applying population priors. Today
feasibility and volume targets key off `training_age` buckets only; logs are never
distilled; prescribed-vs-actual isn't even computable (fixed by P0).

**Design.**

New `engine/response.py` (all descriptive, honest about n):

- `e1rm_timeline(sessions, lift) -> list[(date, e1rm)]` from each session's best set
  (existing Epley path). Entries flagged implausible by P2's data-quality guards are
  excluded unless athlete-confirmed.
- `progression_rate(timeline, window_weeks=8) -> {pct_per_week, r2, n}|None` — least
  squares; None when n < 6 points or span < 4 weeks.
- `compare_prescribed_actual(plan: ProgramPlan, sessions) -> ComplianceReport` —
  match on `session_plan_id` (fallback: weekday+quality); per session/exercise:
  done / partial / modified / missed; weekly volume prescribed vs performed.
- `volume_tolerance(sessions, readiness_entries, checkins) -> flags|None` — observed
  weekly hard sets vs readiness/fatigue trend (correlation direction only, needs ≥8
  weeks, else None; never causal claims).
- `adherence_stats(compliance, by=quality_tag)`.
- `build_response_profile(...) -> ResponseProfile`.

Schema + storage: `ResponseProfile {as_of, per_lift_rates, per_goal_measured_rate
{value, n, window_weeks, r2}, volume_tolerance_flags, adherence_by_quality,
adjustment_patterns (from P3 logs), caveats}` → versioned immutable
`response/response-profile-v{N}.yaml` via `_save_versioned_doc` (reason mandatory).

Recalibration path: `assess_strength_goal` / `assess_endurance_goal` /
`assess_hypertrophy_goal` / `assess_bodycomp_goal` gain optional
`measured_weekly_rate` (+ `measured_n_weeks`); when provided, the verdict reports
BOTH probabilities — population prior AND measured-rate — with drivers and small-n
caveats. The engine keeps printing its assumptions (honesty preserved).
`weekly_set_targets_for` gains optional `tolerance_adjustment: Literal[reduce,
default, extend]` mapped from tolerance flags (bounded within the existing
min/max landmarks).

Re-test milestones: `program-planning` places a `TestMilestone` at each mesocycle
end (protocol `amrap_rir1` for lifts — safer than true 1RM — or `timetrial` for
endurance); results are logged as sessions and feed `estimate_1rm` / Riegel and the
next profile version.

MCP tools: `compute_response_profile`, `save_response_profile`,
`read_response_profile`, `compare_prescribed_actual`.

**Skills to update.**
- `training-checkin`: at each mesocycle end → compute + save the profile, narrate
  deltas ("measured 0.5%/week vs the 1%/week prior I planned with").
- `needs-analysis` and `program-planning`: MUST read the latest response profile;
  pass `measured_weekly_rate` when n is sufficient; state which rate the plan uses.
- `program-adaptation`: use adherence/tolerance flags in its diagnosis vocabulary.

**Tests.** Property: synthetic linear progress at rate r is recovered within
tolerance; insufficient-data paths return None everywhere (never a fabricated rate);
compliance matcher edge cases (swapped exercise, extra unplanned session, missed
week); profile versioning immutable.

**Acceptance.** After 8 weeks of synthetic logs at 0.5%/week, the strength assessment
quotes both probabilities and the next program version's reason cites the measured
rate.

---

## Phase 6 — Data-driven deloads, adherence playbook, return-to-load

**Goal.** Deloads placed by evidence of fatigue (with the planned counter as
guardrail), a real behavior playbook when adherence collapses, and a graded
return-to-load after time off. Today deloads are a fixed counter
(`engine/periodization.py`), adherence <70% just routes to adaptation, and
return-from-injury stops at "refer out".

**Design.**

New `engine/regulation.py`:
- `should_deload(weeks_since_deload, monotony_recent, strain_trend, tsb,
  readiness_trend, adherence_pct) -> {recommendation: none|light|full, drivers}` —
  documented thresholds (team priors, e.g. `tsb < -25` with amber/red readiness →
  full; `monotony > 2.0` with strain spike → light; `weeks_since_deload ≥ planned
  interval + 1` → full regardless). Descriptive; the LLM decides and narrates.

New `engine/return_to_load.py`:
- `build_return_progression(weeks_off, sessions_per_week, pain_free: bool) ->
  list[WeekFactor]` — banded restart ladder: <1 week off → 0.90 vol / 0.95 int;
  1–2 → 0.70/0.85; 2–4 → 0.50/0.70; >4 → start 0.40/0.60 and +10–15%/week;
  progression gated on `pain_free`; encodes the 24h rule (post-session pain ≤3/10
  resolving within 24h = acceptable, else step back one week). Constants labeled;
  cite return-to-sport consensus (see §Evidence). Hard precondition documented in
  the tool: only after professional clearance.

MCP tools: `recommend_deload`, `build_return_progression`.

**Skills to update.**
- `program-adaptation`: deload branch calls `recommend_deload` and quotes drivers;
  new return-to-load branch — REQUIRES the athlete to confirm professional clearance,
  then builds the ramp as a new program version (mesocycle phase `return_to_load`);
  never through pain, refer-out language preserved.
- Adherence playbook (in `program-adaptation`): persistent adherence <70% → diagnose
  the cause in the athlete's words (time / motivation / life / pain), then propose
  the **minimum viable program** (2-day template at `minimum_effective_sets`,
  shortest sessions that keep the goal alive per the feasibility engine), renegotiate
  cadence, and version it with that reason. Never shame; the best program is the one
  that gets done.
- `training-checkin`: surface `recommend_deload` output proactively when signals
  accumulate (before fatigue hits 8).

**Tests.** Threshold unit tests each side of every boundary; ramp properties
(factors monotone non-decreasing, capped at 1.0, longer layoff → longer ramp);
scenario: synthetic overreach series (rising strain, falling tsb/readiness) fires
`full` within one week of the injected spike.

**Acceptance.** The overreach scenario produces a deload recommendation with drivers
quoted; "3 weeks off, cleared by physio" produces a versioned 3-week return ramp.

---

## Phase 7 — Proactive follow-up (within a passive server)

**Goal.** The coach speaks first. The MCP server is stdio request/response
(`server/app.py`) and cannot push — so centralize "what is due" in a tool the ritual
MUST call, and document client-side reminders. Today nothing reaches out; follow-up
depends entirely on athlete discipline.

**Design.**

New `engine/diligence.py` + MCP tool `list_due_actions()`:
reads time context, the active `ProgramPlan` (checkin_cadence_days, test_milestones,
deload/taper weeks), `calendar.yaml` (A/B events ≤21 days out → taper/peaking about
to start), `sessions.jsonl` (planned sessions in the past N days with no matching
log), `readiness.jsonl` (no readiness on ≥3 recent training days — serious-competitor
expectation), calendar completeness (goal has a deadline but no dated events),
response-profile staleness (>6 weeks), readiness red streaks →
`[{kind, severity, due_since_days|due_in_days, message_key}]`, sorted by severity.
Message rendering stays with the LLM (locale-aware); the tool returns facts.

- `ProgramPlan.checkin_cadence_days` is set by `program-planning` (default 7).
- `performance-coach` ritual: call `list_due_actions` immediately after
  `get_time_context` and OPEN with the top items ("Check-in is 3 days overdue; your
  race is in 18 days — taper starts next week; no log since Tuesday's intervals").
- New doc `docs/proactive-reminders.md`: optional client-side recipes — an OS cron /
  scheduled agent run that starts a session with "coach check" so `list_due_actions`
  fires; explicitly documented as optional, no server change.

**Tests.** Fixtures: overdue check-in, imminent A event, missed planned sessions,
stale profile, all-green (empty list); ordering by severity; boundary days.

**Acceptance.** Opening any session on a stale athlete dir surfaces the correct top-3
without being asked.

---

## Phase 8 — End-to-end simulated evaluation (the proof)

**Goal.** Prove the whole loop deterministically — this reintroduces the previously
descoped e2e evaluation as an engine-level simulation (no LLM in CI, no flakiness).

**Design.** `tests/e2e_sim/` — a simulation harness driving the real engine + store
against synthetic athletes:

- **P1 runner**: 10K goal, 3 runs/week, clean logs, injected true response
  0.6%/week + noise.
- **P2 amateur footballer**: 3 club practices + 1 match (external load), 2 gym
  slots, one fixture pile-up week.
- **P3 Hyrox hybrid**: 4 sessions/week, one A race + one B race, a calendar change
  at week 6, one 2-week sick break (return-to-load path).

Each persona: build calendar + profile → plan season + program (real builders +
season planner + sequencing check) → simulate 12–16 weeks of session/readiness logs
with controlled perturbations → run check-in math weekly.

**Assertions.** Season segments valid (P1 invariants); zero `block` sequencing
violations in every generated week; external load present in weekly totals (P2);
injected strain spike → `should_deload` fires within one simulated week; calendar
change → replanned season keeps taper before the new date; response profile recovers
the injected rate ±0.2 pts; injected implausible log entries are flagged and excluded
from the profile; `list_due_actions` correct after a silent week (including missing
readiness days); return-to-load ramp engaged after the sick break; every program
version has a reason.

Also: `docs/eval-checklist.md` — a short manual skill-level eval script (personas +
expected agent behaviors) for release testing with a live LLM.

**Acceptance.** `e2e_sim` suite green in CI; README "Working today" updated to claim
the simulated end-to-end evaluation.

---

## Phase 9 — Activity file import (pulled forward: execute right after Phase 2)

**Goal.** Lower logging friction — the single biggest threat to everything above.
Executing early is deliberate (user decision): passive import feeds every later
phase with richer, more reliable data. Files only, no OAuth/cloud (philosophy:
filesystem is the database, no backend).

**Design.** MCP tool `import_activity_file(path)`:
- Parse `.fit`/`.tcx`/`.gpx` (choose a maintained parser at implementation time —
  verify current stable versions, do not trust memory; CSV fallback for
  Garmin/Strava exports).
- Extract duration, distance, avg HR → propose a `SessionEntry` (match against
  today's planned session via distance/duration proximity → `programmed` +
  `session_plan_id`, else `external`); sRPE from `estimate_srpe_from_hr` when HR
  present, else ask the athlete. Athlete confirms before `log_session` (never silent
  writes). Optional HRV CSV → `readiness.jsonl` entries.
- Imported entries run through P2's `flag_implausible_session` guards.
- Fixture-file tests for each format; malformed files fail with actionable errors.

If the parser landscape turns out poor, descope to CSV-only and REPORT it to the
user — never silently skip the phase.

---

## Evidence corpus additions (transversal — land citations before skills cite them)

Add through the existing pipeline (verify DOI/PMID with `verify_reference`, grade per
the project's scheme; never cite from memory — verify each reference really says what
the rule claims):

- Foster 1998 — session-RPE monotony & strain (P2, P6).
- Banister-style impulse-response / CTL-ATL reviews (P2) — label EWMA taus as
  conventions.
- Bosquet et al. 2007 taper meta — already in corpus as
  `tapering-performance-meta-2007`; extend usage to `recommend_taper_length` (P1).
- ACWR critique literature (descriptive-only framing — repo already takes this
  stance; add the EWMA-variant reference) (P2).
- Wilson et al. 2012 concurrent-training meta; Coffey & Hawley interference reviews
  (P4).
- Hooper & Mackinnon 1995 wellness monitoring (P2, P3).
- Issurin block periodization reviews (P1).
- Helms et al. RIR/RPE framework (P3 adjustment steps).
- Return-to-sport consensus (e.g. Ardern et al. 2016) + detraining/retraining
  (Mujika & Padilla) (P6).

Any rule that can't be sourced gets the existing `team-chosen prior` / coaching-
judgment label in code and skills — never a fake citation.

---

## Report templates refresh (transversal)

Any phase that adds athlete-visible data extends the Typst report templates (coach &
expert modes, en/fr/es) in the SAME PR, or records a listed follow-up in the progress
file. Concretely: P1 → season overview (segments, events, taper placement); P2/P9 →
load trends (weekly load with external share, monotony/strain, CTL/ATL/TSB); P5 →
response summary (measured vs. prior rates, adherence); P8 → a final coherence pass
across both modes and all three languages. The hard citation gate applies to report
content as everywhere else.

---

## Out of scope

OAuth/cloud integrations; web or mobile UI; multi-athlete server (one directory per
athlete remains the model); exercise technique/video analysis; nutrition beyond the
existing frame; medical diagnosis (always refer out); menstrual-cycle tracking
(proposed, not selected — revisit on demand); the full team-sport vertical (locked
decision: external-load-only this iteration); force-velocity/jump profiling (needs
measurement hardware); non-7-day microcycles (7-day weeks are a documented modeling
limit of `WeekPlan`).

---

## Global definition of done

1. All phases merged; full suite green (baseline 597 tests + new engine/property/e2e
   tests); linters/type checks clean; zero warnings; pre-commit green.
2. README ("Working today", tool count, athlete-dir layout) and `docs/installing.md`
   check strings updated; i18n READMEs link-consistent (full translation refresh may
   be a follow-up, note it); `examples/` updated where the user-visible flow changed
   (English first, note follow-ups for other languages).
3. Every skill's `tools:` frontmatter matches the tools it actually uses; the
   delivery gate (`program-review`) covers the new checks (structure, sequencing,
   calendar coherence, citations).
4. A fresh athlete directory can, end to end: onboard with a dated two-event season
   and club constraints → receive a season-planned structured program with fallbacks
   and test milestones → log sessions including external load (typed or imported
   from a file) → adjust tonight's session in under a minute without re-versioning →
   get a data-driven deload recommendation → recalibrate at block end from measured
   response → replan on a calendar change → render a PDF report including the new
   season/load/response sections, all citations passing.
5. Every number remains traceable: engine constant (sourced or labeled prior) or
   corpus citation. The LLM still never does the math.
6. Single release at the end (user decision): version bump + changelog per
   `RELEASING.md` once every phase is merged; no intermediate PyPI releases.
7. `docs/plans/beyond-national-coach-progress.md` is complete: every phase, its PR,
   and any deviation from this plan recorded.
