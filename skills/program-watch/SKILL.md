---
name: program-watch
description: Use every two weeks, at each mesocycle boundary, or on demand to audit
  whether the running program is working exercise by exercise. Produces a keep /
  watch / substitution-candidate verdict per exercise and never edits anything.
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
  compare_prescribed_actual, estimate_1rm, compute_weekly_loads,
  compute_monotony_strain, score_exercises, get_citation, save_watch_report]
---

# Program watch

The running program's auditor. Data only, per exercise — the question is never
"is the athlete tired" (training-checkin owns that) but "is THIS exercise doing
its job". Designed to run as a subagent launched by performance-coach or
training-checkin: audit silently, come back with a short report.

## Signals, per exercise

1. Open with `read_athlete` + `get_time_context` (quote its dates), then
   `read_program`, `read_sessions`, `read_checkins` over the current mesocycle.
2. Trajectory — best sets per exercise through `estimate_1rm`: is the estimated
   1RM (or pace at heart rate, via compare_prescribed_actual, for endurance
   blocks) moving the way the block intends?
3. Adherence — an exercise systematically skipped or cut short is a signal about
   THAT exercise (friction, equipment, quiet pain), not laziness.
4. Pain — pain_flags and session notes that recur around one movement.
5. Chronic gap — compare_prescribed_actual: prescribed vs done, week after week.
6. Load shape — compute_weekly_loads + compute_monotony_strain when the pattern
   suggests a structural problem (everything hard, nothing varied).

## Verdict and report

Per audited exercise: **keep** (working — say why in one line), **watch** (name
the signal and the check for next time), or **substitution candidate** (name the
signal, propose 1-2 replacements via score_exercises, cite corpus evidence with
get_citation when one backs the swap — otherwise label it coaching judgment).

Write the report with save_watch_report (goal_id from the program; v2+ reason =
the trigger: "biweekly watch", "mesocycle boundary", "athlete request"). Keep it
short: verdicts first, data behind them after.

## Hard boundary

This skill NEVER edits the program, never prescribes, never substitutes in
place. Substitution candidates route to program-adaptation, which owns the
diagnosis conversation, the versioned save and the program-review gate. At a
mesocycle boundary, pair with deep-research's incremental watch: this report
says what to watch, the research says what the science says.
