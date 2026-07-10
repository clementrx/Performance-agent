---
name: program-adaptation
description: Use when a check-in fires a trigger (missed sessions, high fatigue,
  pain, plateau, schedule change). Diagnoses from logged data and writes the next
  program version with an explicit reason.
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
        compute_session_load, compute_weekly_loads, compute_acwr,
        assess_endurance_goal, prescribe_load, estimate_1rm,
        build_periodization_waves, check_citations, save_program]
---

# Program Adaptation

Follow performance-coach global rules. Adaptations are versioned coaching decisions:
every one carries a reason the athlete (and future you) can audit.

## 1. Diagnose from data, not vibes

- Start with `read_athlete` for current constraints (injuries, availability),
  `get_time_context` for the window, and `read_program` for the active plan you're
  about to change.
- `read_sessions` / `read_checkins` for the recent window.
- Build the daily-load series from logged sessions (rpe × duration via
  `compute_session_load` values, zeros for rest days) → `compute_weekly_loads` and
  `compute_acwr`. Build the series date-indexed: from `get_time_context`'s today
  back at least 28 days, one value per calendar day, SUMMING same-day sessions,
  zero for days with no session and for sessions missing rpe/duration; the array's
  LAST element must be today. `compute_acwr` is date-blind — a misaligned array
  gives a wrong-but-plausible number with no error. Present ACWR as a descriptive
  trend only — its injury-prediction validity is contested; never present it as an
  injury probability.
- If `get_time_context` shows the deadline already passed (negative
  days_remaining), do NOT call `assess_endurance_goal` (it errors on non-positive
  weeks); route to goal-assessment to renegotiate the deadline first.
- Re-run `assess_endurance_goal` with today's numbers if the goal's feasibility may
  have moved (quote the new drivers vs the old ones).
- Name the diagnosis in one sentence: under-recovery / under-stimulus / interrupted
  training / life-constraint change / pain-driven (map check-in triggers loosely:
  fatigue ≥ 8 → under-recovery; adherence < 70% → interrupted training; but
  diagnose from the data, not the trigger label).

## 2. Propose the change

Smallest change that addresses the diagnosis: swap sessions, cut a week's volume
(deload), extend the timeline, re-negotiate the goal (route back to goal-assessment
when the goal itself must move). Recompute affected loads/paces with the engine
tools (`prescribe_load` from a fresh `estimate_1rm` for strength; the pace tools for
endurance) — never carry stale numbers forward. If you rebuild waves via
`build_periodization_waves`, apply the factors to the recomputed loads/paces — a
wave you don't apply is decoration (see program-generation §2).

## 3. Confirm, then version

- Present the proposed vN+1 and ASK the athlete to confirm before saving.
- Run `check_citations` if the proposal cites evidence.
- `save_program` with a reason that states the diagnosis and the change (e.g.
  "missed week 3 with a cold; shifted block back one week and cut week-4 volume").
  The store refuses v2+ without a reason — that is by design, not friction.
- Quote the new version number back, and state what the next check-in will watch.
