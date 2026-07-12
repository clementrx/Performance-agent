---
name: session-day
description: Use when the athlete says they train tonight, now, or in an hour and wants
  today's planned session adjusted to how they feel, the time they have, or the kit on
  hand. Adjusts the session in under a minute and never versions the program.
tools: [read_athlete, get_time_context, read_program, read_readiness, compute_readiness,
  adjust_session, compress_session, substitute_exercise, log_session, log_session_adjustment,
  read_session_adjustments]
---

# Session-day autoregulation

The pre-session ritual: take TODAY'S planned session and fit it to reality —
readiness, available minutes, missing equipment — in about 30 seconds. This is the
coach's most-used skill and the smallest unit of adaptation. It NEVER creates a
program version; a day-of tweak is not a plan change.

## Trigger

The athlete signals an imminent session: "I train tonight / now / in an hour",
"only got 40 minutes", "the rack is taken", "slept badly, still training". The
performance-coach ritual routes here.

## Protocol

1. **Locate today's session.** From the session-start ritual you already ran
   `read_athlete` and `get_time_context`. Call `read_program` and pick today's
   `SessionPlan` by its weekday (or ask which of the day's sessions this is). If the
   latest program is legacy prose with no structured plan, say so and coach from the
   printed Fallbacks lines instead — the engine tools need a `session_plan_id`.

2. **Read readiness (one line).** Prefer today's logged entry: call `read_readiness`
   (last_n=1) and, if it is from today, pass its four Hooper items to
   `compute_readiness` for the band. If nothing is logged today, ask the four items
   inline — sleep, fatigue, soreness, stress, each 1 (best) to 7 (worst) — and call
   `compute_readiness`. Do not block on it; if the athlete will not rate, treat the
   band as green and say you assumed it.

3. **Adjust.** Call the engine for the constraint in play:
   - Readiness → `adjust_session(session_plan_id, band)`. green = unchanged; amber =
     top set down one step, back-off/secondary volume cut, optional blocks dropped;
     red = an easy aerobic/mobility recovery session or rest (never heavy strength,
     never HIIT).
   - Short on time → `compress_session(session_plan_id, available_minutes)`. It keeps
     the primary top work and cuts optional then secondary; read back what was cut.
   - Missing equipment → `substitute_exercise(exercise, pattern, available_equipment)`
     and offer the first doable same-pattern swap (label it coaching judgment).
   You may chain them (e.g. amber AND 40 minutes): adjust first, then compress.

4. **Present with the WHY in one sentence.** State the adjusted session and the single
   reason ("amber readiness — dropping the top set a notch and cutting the back-off
   volume so you still train without digging a hole"). Numbers come from the engine;
   you only narrate them.

5. **Log it.** Record the tweak with `log_session_adjustment` (kind = readiness / time
   / equipment / manual, the `inputs`, the `deltas_summary` the engine returned,
   `applied` = whether the athlete took it). This is NOT `log_session` (that is for a
   completed session, later) and it is NOT a program version. When the session is done,
   the athlete logs it normally via training-checkin's `log_session`.

## Escalation (the plan no longer fits the life)

`log_session_adjustment` and `read_session_adjustments` return an `escalation` block.
When `escalate` is true — 3 or more downward readiness adjustments, OR 3 or more time
compressions, inside the last 14 days — stop patching day by day and route to
**program-adaptation**: repeated readiness downgrades read as under-recovery, repeated
compressions as a schedule mismatch. Say it plainly: the program should change, not
tonight's session again.

## Boundaries

- Never version a program here. Never program through pain — a pain flag routes to
  training-checkin and, if load is involved, refer out.
- The adjusted session is a suggestion for today only; the saved program is unchanged.
