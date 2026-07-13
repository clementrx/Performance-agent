---
name: program-adaptation
description: Use when a check-in fires a trigger (missed sessions, high fatigue,
  pain, plateau, schedule change). Diagnoses from logged data and writes the next
  program version with an explicit reason.
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
        read_session_adjustments, compute_session_load, compute_weekly_loads, compute_acwr,
        assess_endurance_goal, assess_strength_goal, assess_hypertrophy_goal,
        assess_bodycomp_goal, weekly_set_targets_for, prescribe_load, estimate_1rm,
        build_periodization_waves, compare_prescribed_actual, read_response_profile,
        search_evidence, search_evidence_live, save_evidence, verify_reference,
        get_citation, check_citations, save_program]
---

# Program Adaptation

Follow performance-coach global rules. Adaptations are versioned coaching decisions:
every one carries a reason the athlete (and future you) can audit.

## 1. Diagnose from data, not vibes

- Start with `read_athlete` for current constraints (injuries, availability),
  `get_time_context` for the window, and `read_program` for the active plan you're
  about to change — it returns the structured `plan` (null only for a legacy
  prose version; adapt those into a structured vN+1). Reuse the unchanged
  mesocycles/weeks/sessions and edit only what the diagnosis touches.
- `read_sessions` / `read_checkins` for the recent window.
- Stall and failed-rep triggers arrive from training-checkin (le Vigile) with
  structured sessions behind them — diagnose from the exercise data, not the
  trigger label: loads falling ACROSS THE BOARD (multiple exercises, reps
  missed at previously handled loads) reads as under-recovery; everything
  completed easily (RIR consistently high, rep targets exceeded) reads as
  under-stimulus.
- Build the daily-load series from logged sessions (rpe × duration via
  `compute_session_load` values, zeros for rest days) → `compute_weekly_loads` and
  `compute_acwr`. Build the series date-indexed: from `get_time_context`'s today
  back at least 28 days, one value per calendar day, SUMMING same-day sessions,
  zero for days with no session and for sessions missing rpe/duration; the array's
  LAST element must be today. `compute_acwr` is date-blind — a misaligned array
  gives a wrong-but-plausible number with no error. Present ACWR as a descriptive
  trend only — its injury-prediction validity is contested; never present it as an
  injury probability.
- Use the RIGHT feasibility tool for the goal type — `assess_endurance_goal` for a
  race/distance goal, `assess_strength_goal` for a lift target, `assess_hypertrophy_goal`
  for a muscle-growth goal, `assess_bodycomp_goal` for a weight/body-fat goal. Never
  default to the endurance tool for a non-endurance goal.
- If `get_time_context` shows the deadline already passed (negative
  days_remaining), do NOT call the assessment tool (it errors on non-positive
  weeks); route to needs-analysis to renegotiate the deadline first.
- Re-run the goal-type-matched assessment tool with today's numbers if the goal's
  feasibility may have moved (quote the new drivers vs the old ones).
- Call `read_session_adjustments` and read the day-of history: it is direct evidence
  of where the plan meets friction. Repeated time compressions point to a schedule
  mismatch (the program asks for more minutes than the life has); repeated readiness
  downgrades point to under-recovery (the load is landing harder than planned). An
  escalate=true signal is often what routed here — name which pattern it is.
- Add the individual response to the diagnosis vocabulary: `compare_prescribed_actual`
  gives per-session done/partial/modified/missed and weekly prescribed-vs-performed
  volume (a plateau under low adherence is a behaviour problem, not a stimulus one);
  `read_response_profile` gives the measured rate, `adherence_by_quality`, and any
  `volume_tolerance_flags`. A higher_volume_higher_fatigue flag means the next version
  should size volume with `weekly_set_targets_for`'s `tolerance_adjustment="reduce"`;
  a stalling lift whose measured rate is near the population prior is genuine, not a
  data artefact. Never invent a rate the profile does not carry.
- Name the diagnosis in one sentence: under-recovery / under-stimulus / interrupted
  training / life-constraint change / pain-driven (map check-in triggers loosely:
  fatigue ≥ 8 → under-recovery; adherence < 70% → interrupted training; but
  diagnose from the data, not the trigger label).

## 2. Propose the change

Smallest change that addresses the diagnosis: swap sessions, cut a week's volume
(deload), extend the timeline, re-negotiate the goal (route back to needs-analysis
when the goal itself must move). Recompute affected loads/paces with the engine
tools (`prescribe_load` from a fresh `estimate_1rm` for strength; the pace tools for
endurance) — never carry stale numbers forward. If you rebuild waves via
`build_periodization_waves`, apply the factors to the recomputed loads/paces — a
wave you don't apply is decoration (see program-planning §3). Session-level
rebuilds follow program-optimization's load and formatting rules; if the
STRUCTURE itself must change (new periodization model, changed calendar),
route through program-planning instead of patching sessions in place.

- Plateaus split by goal. A STRENGTH plateau is addressed through intensity
  and specificity (heavier exposures, work closer to the tested lift), not
  more sets. A HYPERTROPHY plateau is addressed through volume — raise the
  weekly sets within the `weekly_set_targets_for` landmarks for the athlete's
  training age, never past maximum_adaptive_sets.

- Citation repair: when a render was refused for unknown references, locate the
  offending claims, replace each with a `search_evidence`-backed citation rendered
  via `get_citation` (or drop the claim). If nothing in the corpus covers the
  claim, run `search_evidence_live` with translated `language_terms` (en, fr, es,
  de, ru, no, sv, it, zh). Classify and `save_evidence` any verified candidate —
  `suggested_study_type` if set, otherwise your own abstract-based proposal
  (grading ceiling still enforced) — before citing it. If that also comes up
  empty, fall back to a web search per language; anything found that way MUST
  pass `verify_reference` before you propose `save_evidence` — never propose an
  entry from an unverified web result, and never patch a refused render by
  weakening the claim into something unverifiable. The repaired vN+1 carries
  the reason "citation repair" and goes through §3 like every other
  proposal — it is not saved here.

## 3. Confirm, then version

- Present the proposed vN+1 and ASK the athlete to confirm before saving.
- **Adapted programs pass the same delivery gate as new ones:** hand the
  confirmed vN+1 to program-review (le Contrôleur) and save only on an
  APPROVED verdict — session-level objections are fixed here, structural ones
  route through program-planning. No adapted version is delivered unreviewed.
- Run `check_citations` if the proposal cites evidence. If it flags anything,
  the fix INVALIDATES the verdict — resubmit to program-review before saving.
- `save_program(plan, reason)` — hand the full edited `ProgramPlan` with a reason
  that states the diagnosis and the change (e.g. "missed week 3 with a cold;
  shifted block back one week and cut week-4 volume"). If the review returned the
  proposal before approving, record it in the reason. The store refuses v2+
  without a reason — that is by design, not friction.
- Quote the new version number back, and state what the next check-in will watch.
