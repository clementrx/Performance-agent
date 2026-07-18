# Pre-Competition Protocol — Design

**Date:** 2026-07-17
**Status:** validated with owner (conversation of 2026-07-17)
**Depends on:** v0.8.0 (living evidence: mini-waves, `resolve_citations`, guidance
rendering, documentation folder)

## 1. Overview

The coach plans seasons, programs and weeks, but goes quiet exactly when the athlete
needs it most: the final days before a competition. This design adds the
**competition protocol** — a versioned, per-event, day-by-day plan covering the
window from J-N to race/meet/stage day (J0), delivered as a phone-ready offline HTML
page the athlete can read on the morning of the event.

The protocol is **sport-agnostic by construction**, like the performance model: no
hard-coded per-sport playbook. What "getting the final days right" means for THIS
event comes from a dedicated research mini-wave; the numbers that can be computed
(carb loading, attempt selection, pacing splits, taper) come from the deterministic
engine; everything else is sourced advice or labeled coaching judgment.

## 2. Decisions taken with the owner

1. **Any sport, one model.** The protocol structure is discipline-neutral; peak week
   (physique), race week/day (endurance) and meet day (strength) are instances the
   research fills in, not separate features.
2. **Deliverable = versioned protocol + phone HTML.** A new per-event versioned
   document family plus a standalone offline HTML page for J0 (same CSS/i18n
   conventions as the session HTML). Not a program version, not conversational-only.
3. **Dedicated research mini-wave.** The first protocol for an event triggers a
   deep-research mini-wave scoped to "the final days before [this event] for [this
   athlete]"; verified studies join the corpus and the protocol cites them with
   evidence stars.
4. **Engine scope: three new computations + existing taper.** Carb-loading targets,
   attempt selection, pacing plan. Day-of meal/warm-up timing and logistics stay
   advice — no fake precision.
5. **Risky practices: documented advice with warnings, never engine-quantified.**
   Peak-week practices (water/sodium manipulation, weight-cut tactics) ARE described
   when the literature documents them — always carrying an evidence grade and an
   explicit warning, never computed or dosed by the engine, never presented as
   prescription. The existing red-flag protocol (medical conditions → refer out)
   keeps precedence.
6. **Adaptive trigger.** The protocol window is not a fixed J-14: it is computed
   from the event's modality and priority (a marathon A opens earlier than a 5K B or
   a meet-day weigh-in), reusing the individualized taper recommendation.

## 3. The protocol model

New schemas in `memory/schemas.py` (same conventions: `extra="forbid"`, strict
fields, validators with readable messages):

```
ProtocolLine      text (1..300), time_hint (str|None, e.g. "07:30" or "T-45 min"),
                  cite (str|None — corpus id), warning (bool, default False)
ProtocolDay       day_offset (int, -21..0; 0 = event day), title (1..80),
                  lines (list[ProtocolLine], min 1)
PacingSegment     label (1..40), distance_m (float>0),
                  target_pace_s_per_km (float>0), cumulative_time_s (float>0)
AttemptPlan       lift (1..60), e1rm_kg (float>0), opener_kg, second_kg, third_kg
                  (floats>0, strictly increasing), basis ("engine"|"agreed"),
                  flags (list[str])
FuelingPlan       carb_g_per_kg_low/high (floats>0, low<=high), window_hours (int>0),
                  race_carb_g_per_h_low/high (floats>=0)|None, cite (str|None)
DocumentedPractice name (1..80), summary (1..400), cite (str|None),
                  warning (str, min 1 — REQUIRED, non-empty by schema)
CompetitionProtocol schema_version=1, version (>=1), event_id (calendar id),
                  event_date (date), goal_id, created_on, reason (str|None),
                  window_days (int 1..21), days (list[ProtocolDay], min 1),
                  pacing (list[PacingSegment], default []),
                  attempts (list[AttemptPlan], default []),
                  fueling (FuelingPlan|None), practices (list[DocumentedPractice]),
                  checklist (list[str], default []), advice (list[Guidance])
```

Validators: `days` sorted by `day_offset`, unique offsets, last day is 0;
`window_days >= -min(day_offset)`. `DocumentedPractice.warning` being schema-required
is the structural encoding of decision 5: a practice cannot be stored without its
warning. The engine never fills `practices` — only the skill does, from research.

## 4. Engine — `engine/competition.py` (pure, no I/O)

Four functions, all deterministic, all raising readable `ValueError` on bad input:

1. `carb_loading_targets(body_mass_kg, event_duration_min) -> CarbLoadingTargets`
   — evidence-based ranges: events ≥ 90 min → 8–12 g/kg/day over the final
   36–48 h; 60–90 min → 6–8 g/kg/day; < 60 min → maintenance (no loading, the
   result says so via `loading_required=False`). In-race fueling range from
   duration: < 60 min → none needed, 1–2.5 h → 30–60 g/h, > 2.5 h → 60–90 g/h.
   Guards: body mass 30–250 kg, duration 5 min–24 h. Returns g/kg AND absolute
   g/day. The thresholds are corpus-cited priors (Burke/IOC consensus) recorded as
   constants with their rationale.
2. `select_attempts(e1rm_kg, goal_kg, rounding_kg) -> AttemptPlan` — opener at
   90–92 % of e1RM, second at 95–97 %, third at `goal_kg` when it lies within
   93–105 % of e1RM, else at 100–102 % with flag `goal_beyond_e1rm` (the honesty
   gate: the plan never silently endorses a goal the data does not support; the
   skill names the gap). All loads rounded to `rounding_kg` (default 2.5), strict
   monotonicity enforced after rounding.
3. `pacing_plan(distance_m, target_time_s, segment_m, strategy) -> list[PacingSegment]`
   — splits the distance into segments of `segment_m` (last segment takes the
   remainder), strategy `"even"` (uniform pace) or `"negative"` (first half +1 %
   of mean pace, second half −1 %, halves balanced so cumulative time lands on
   `target_time_s` within one second). Target time comes from the athlete's goal
   or `predict_race_time` upstream — this function only distributes it.
4. `protocol_window_days(taper_days, priority) -> int` — the adaptive trigger
   window: priority A → `clamp(max(taper_days, 7), 7, 21)`; B →
   `clamp(taper_days, 3, 10)`; C → 0 (never auto-surfaced). `taper_days` comes
   from the individualized `recommend_taper` (modality- and history-aware), which
   is how sport magnitude adapts the window.

Purity: no imports outside stdlib + engine siblings (structural `Protocol` if a
schema view is needed, as done for `ProgressionRule`).

## 5. Persistence and deliverables

Store additions (`memory/store.py`), mirroring the program trio (yaml source +
rendered md + standalone html), but **per event**:

- Directory `competition/`; files `protocol-<event_id>-vN.yaml` (structured source
  of truth), `-vN.md` (rendered markdown), `-vN.html` (phone page). Versions
  immutable; v2+ requires a `reason`.
- `save_competition_protocol(base_dir, protocol, reason=None, today=None,
  citations=None) -> (Path, int)` — validates that `event_id` exists in the
  calendar and that `event_date` matches the calendar date (drift = error), stamps
  version/created_on/reason, renders md, writes atomically.
- `read_competition_protocol(base_dir, event_id, version=None)`,
  `latest_competition_protocol_version(base_dir, event_id)`.

Rendering (`programs/render_protocol_html.py` + md rendering in
`programs/render.py` style):

- Phone page: timeline of `days` (J0 open by default, previous days collapsed),
  `time_hint` chips, pacing table with cumulative splits, attempt cards, fueling
  numbers, checklist as tap-friendly list, practices section with the warning
  visually flagged (⚠ + distinct style) and evidence stars, final Sources section
  with DOI links. Same rules as the session HTML: inline CSS, zero JavaScript,
  en/fr/es labels from `profile.locale`, no external requests.
- Citations resolved server-side with the existing `resolve_citations` — an
  unknown corpus id on any line/practice/advice aborts the save (anti-fabrication,
  same lock as programs).

## 6. Server — `server/competition_tools.py`

Five tools (97 → 102):

- `carb_loading_targets`, `select_attempts`, `pacing_plan` — thin wrappers over the
  engine, docstrings teaching when each applies and that outputs are quoted, never
  renegotiated upward.
- `save_competition_protocol(protocol, reason=None)` — resolves citations (hard
  gate), saves, renders md + HTML, returns `{path, version, html_path}`.
- `read_competition_protocol(event_id, version=None)` — frontmatter + structured
  protocol + markdown.

## 7. Trigger — diligence

- `memory/diligence.py` extracts, for each upcoming A/B calendar event within 21
  days: its computed window (`protocol_window_days` fed by the stored program's
  modality and `recommend_taper`) and whether a protocol exists for its id.
- `engine/diligence.py` gains `competition_protocol` due actions: fires when
  `days_until <= window` and no protocol exists; severity high when
  `days_until <= 7`, medium otherwise; `ref` = event id. C events never fire.
- `list_due_actions` docstring extended.

## 8. Skills

**New skill `pre-competition`** (15th): the protocol author. Ritual: open with
`read_athlete` + `get_time_context` + `read_calendar` (quote days-until); check the
taper actually planned (`read_program`, `recommend_taper`); run the dedicated
mini-wave via deep-research rules (first protocol for the event) and
`read_research_dossier`; build the day-by-day plan — engine numbers via
`carb_loading_targets` / `select_attempts` / `pacing_plan` (and `predict_race_time`
for the target), advice lines cited or labeled judgment, documented practices ONLY
with grade + warning; walk it through with the athlete; pass the program-review
protocol gate; save and hand over the HTML. Post-event: route to training-checkin
for the debrief and `log_kpi_result` (feeds `fit_taper_response` for next time).
Hard boundaries: never edits the program (taper structure changes route to
program-adaptation); the engine's attempt/pacing numbers are quoted, the athlete
may choose more conservative, never more aggressive.

**Edited skills:**

- `performance-coach` — routing: `competition_protocol` due action or "my
  competition is in N days" → **pre-competition**; add tool `read_calendar` if not
  declared.
- `training-checkin` — surface the due action; day-after-event: debrief + KPI
  logging duty.
- `session-day` — when today is J0 and a protocol exists, open from the protocol
  page instead of improvising.
- `deep-research` — one line in the mini-wave section: the pre-competition wave is
  a mini-wave whose question is the event's final days.
- `program-review` — new deterministic section "Competition protocols": every
  `DocumentedPractice` has grade + warning; every engine-attributed number matches
  a tool recomputation; any dehydration/water-manipulation content that appears as
  a computed or prescriptive line (rather than a warned practice) is an objection.
  The gate is mandatory before `save_competition_protocol`, same APPROVED/RETURNED
  contract.

`tests/skills/test_structure.py`: EXPECTED_SKILLS + `pre-competition`; a protocol
test asserting the needles (`save_competition_protocol`, `select_attempts`,
`pacing_plan`, `carb_loading_targets`, `mini-wave`, `warning`, `program-review`,
`never edits the program`, `session-day`); extended needles for the five edited
skills.

## 9. Error handling & edge cases

- `event_id` not in calendar, or calendar date ≠ `event_date` → readable error at
  save (protocols cannot outlive a rescheduled event silently; re-save v2 with
  reason after the calendar moves).
- Event in the past → error at save.
- `select_attempts` without a usable e1RM upstream: the tool is pure — the skill
  gets the e1RM from `estimate_1rm`/lift inventory; absent → no attempts section,
  flag it conversationally (no invented openers).
- `pacing_plan` with `segment_m > distance_m` → single segment; nonsensical inputs
  (non-positive) → error.
- Unknown citation id anywhere → save aborts before writing (existing lock).
- v2+ without reason → error (audit trail).
- Two events on the same day: protocols are per `event_id`, both can exist.
- Legacy athletes (no structured program): window falls back to the population
  taper for the goal's modality; the protocol itself does not require a structured
  program.

## 10. Testing

Test-first per module, following the repo's invariants:

- Engine: property tests — attempts strictly increasing and plate-rounded for all
  valid inputs; `goal_beyond_e1rm` flag iff goal outside 93–105 %; pacing cumulative
  time within 1 s of target for both strategies and any segmentation; carb ranges
  monotone in duration class; window clamps and C→0. Purity test must stay green.
- Store: per-event versioning (v1, v2+reason, immutability), calendar validation,
  read round-trip.
- Render: HTML has zero `<script>`, warnings rendered with ⚠ styling, stars +
  DOI links present iff citations, en/fr/es labels, J0 open by default.
- Server: save gate (unknown cite refused), read, tool wrappers.
- Diligence: due action fires/holds around the window per priority.
- Skills: structure + tool-reference invariants for the new and edited skills.

## 11. Out of scope (this iteration)

- Environment factors (altitude, heat acclimatization, jet-lag, competition-hour
  shifting) — already on the roadmap as its own iteration.
- Automatic program rescheduling around the event (program-adaptation owns program
  changes).
- Live in-race guidance and multi-attempt in-meet re-planning (the page is static;
  the athlete talks to the coach between attempts if they want).
- Outcome simulation (Monte Carlo on the fitted Banister model).
- Team-sport match-week protocols beyond what the generic model already expresses.

## 12. Tally

| | before | after |
|---|---|---|
| MCP tools | 97 | 102 |
| Skills | 14 | 15 (+5 edited) |
| New engine modules | — | `engine/competition.py` |
| New doc family | — | `competition/protocol-<event_id>-vN.{yaml,md,html}` |
