---
name: next-week-loads
description: Use when the athlete has logged their training week (or the loads_review
  due action fires) and wants next week's working weights. Presents the engine's
  deterministic suggestions block by block and never modifies the program.
tools: [read_athlete, get_time_context, read_program, read_sessions,
  suggest_next_week_loads]
---

# Next week's loads

The weekly review ritual: the athlete finished their training week, the logs are
in — hand them next week's numbers. All math is engine math: this skill quotes
`suggest_next_week_loads`, it never invents a load, and it NEVER versions the program
(structure changes belong to program-adaptation).

## Ritual

1. Open with `read_athlete` + `get_time_context` (quote its dates, never compute
   your own). `read_program` for the active version.
2. Call `suggest_next_week_loads`. Present the verdicts as a compact per-session
   table in the athlete's locale: exercise, what they did, next load, and the
   engine's rationale_key rendered as a sentence ("all sets at the top of the
   range — +2.5 kg").
3. Flags are conversations, not errors:
   - `no_rule` — the block predates structured progression: agree the next load
     with the athlete conversationally, from their logs (`read_sessions` for
     context), and say plainly it is coaching judgment.
   - `failed_sets` / `no_logged_sets` / `no_rir_logged` / `no_e1rm` /
     `ambiguous_reps` — say what is missing and what would unlock the number.
   - `clamped` — the autoregulated jump was capped at ±10% for safety; say so.
   - `no_matched_week` — the logs don't map to any program week; ask what
     actually happened this week.
4. Repeated `failed_sets` on the same exercise, pain mentions, or a stalled lift
   are NOT solved here: name the signal and route to program-adaptation (and to
   program-watch when the athlete wants the full audit).
5. `last_week` flag: the program just ended — route to training-checkin /
   program-planning for what comes next.

Numbers are quoted, never negotiated upward past the engine's suggestion; the
athlete can always choose LESS than suggested.
