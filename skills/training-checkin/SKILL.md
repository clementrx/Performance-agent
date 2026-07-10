---
name: training-checkin
description: Use when a returning athlete with an active program shows up — or
  whenever days have passed since the last contact. Runs the structured check-in,
  logs it, and routes to adaptation when triggers fire.
tools: [read_athlete, get_time_context, read_program, log_checkin, log_session,
        read_sessions, compute_session_load]
---

# Training Check-in

Follow performance-coach global rules. The check-in is short, warm, and structured —
a coach's five minutes, not an interrogation. Confirm profile facts via
`read_athlete` before contrasting them with today's answers.

## Protocol

1. Open by quoting `get_time_context`: "your last update was N days ago; W weeks to
   [goal]". If days_since_last_session is null, nothing was ever logged — say so and
   start logging today.
2. Backfill: call `read_sessions` for the window since last contact to see what's
   already logged, then ask which planned sessions are still missing. `log_session`
   each one the athlete reports (performed_at, rpe, duration_min, kind, notes).
   Offer `compute_session_load` so the athlete sees their load trend forming.
3. Ask, one at a time: adherence (sessions done vs planned, as a %), fatigue (1-10),
   any pain or niggles (RED FLAG rules apply — an affirmative answer here overrides
   everything else), body-weight change if relevant, schedule changes coming.
4. `log_checkin` with what you collected. Quote the stored days_since_last back.
5. Route:
   - Pain flagged → record it in the profile injuries (via athlete-onboarding's
     persistence rules), stop loading that pattern, recommend a professional if
     it is more than a niggle, and go to program-adaptation to reshape the week.
   - Adherence < 70%, fatigue ≥ 8, plateau suspicion, or schedule change →
     program-adaptation.
   - All green → encourage, preview the next block (read_program), done.
