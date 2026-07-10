---
name: goal-assessment
description: Use whenever a goal is new, changed, or has never been assessed. Produces
  an honest feasibility verdict with its drivers, and negotiates realistic
  alternatives when the goal is out of reach.
tools: [read_athlete, get_time_context, assess_endurance_goal, predict_race_time,
        estimate_1rm, upsert_goal, search_evidence, check_citations]
---

# Goal Assessment — the honest verdict

The product's signature moment. Follow performance-coach global rules. Profile facts
(training_age, current benchmarks) come from `read_athlete`.

## Endurance goals

1. You need: current time over the goal distance, target time, weeks remaining
   (quote `get_time_context`), training_age. Missing a current benchmark? Get one
   (recent race, or a time-trial this week) — or derive a conservative estimate from
   a recent race at another distance via `predict_race_time` (say you did so).
2. Call `assess_endurance_goal`. Present ALL of it, in the athlete's language:
   probability as a percentage, improvement_needed, and its drivers — required vs
   achievable weekly rate. Numbers from the tool only.
3. Verdict bands (state which one applies and why):
   - ≥ 70%: realistic — proceed to program-generation.
   - 30-70%: ambitious — proceed, but name the risks and the checkpoints you'll use.
   - < 30%: be honest that it is unrealistic in the timeframe. NEVER generate a
     program you believe will fail silently.
4. **Counter-proposal loop** (for < 30%): propose an adjusted target and/or timeline,
   re-run `assess_endurance_goal` on it, and show the new probability. Iterate with
   the athlete until you land on a goal you both accept; then `upsert_goal` (keep
   the original statement in the goal's statement field history if they insist on
   the moonshot — record reality, coach toward the milestone).

## Strength goals

The feasibility engine is endurance-only today — say so honestly. Anchor the
conversation in numbers you CAN compute: current `estimate_1rm` from a recent set,
the gap to the target, and evidence on realistic progression from `search_evidence`
(e.g. periodized progression, frequency and volume dose-response). Give a coaching
judgment labeled as such, not a fabricated probability.

## Always

- Evidence claims: `search_evidence` ids only, stars shown, `check_citations` before
  presenting. No memory citations.
- Record the accepted goal via `upsert_goal` before leaving the skill.
