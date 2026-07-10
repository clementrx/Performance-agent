---
name: goal-assessment
description: Use whenever a goal is new, changed, or has never been assessed. Produces
  an honest feasibility verdict with its drivers, and negotiates realistic
  alternatives when the goal is out of reach.
tools: [read_athlete, get_time_context, assess_endurance_goal, predict_race_time,
        estimate_1rm, upsert_goal, search_evidence, search_evidence_live,
        save_evidence, verify_reference, check_citations]
---

# Goal Assessment — the honest verdict

The product's signature moment. Follow performance-coach global rules. Profile facts
(training_age, current benchmarks) come from `read_athlete`.

## Endurance goals

1. You need: current time over the goal distance, target time, weeks remaining
   (quote `get_time_context`), training_age. Missing a current benchmark? Get one
   (recent race, or a time-trial this week) — or derive a conservative estimate from
   a recent race at another distance via `predict_race_time` (say you did so).
   No deadline on file? Ask for one BEFORE calling `assess_endurance_goal` — it
   requires whole-number weeks and errors without them. If the athlete has no fixed
   date, have them pick a working horizon for the assessment.
2. Call `assess_endurance_goal`. Present ALL of it, in the athlete's language:
   probability as a percentage, improvement_needed, and its drivers — required vs
   achievable weekly rate. Numbers from the tool only.
3. Verdict bands (state which one applies and why):
   - ≥ 70%: realistic — proceed to program-generation.
   - 30% to <70%: ambitious — proceed, but name the risks and the checkpoints
     you'll use.
   - < 30%: be honest that it is unrealistic in the timeframe. NEVER generate a
     program you believe will fail silently.
4. **Counter-proposal loop** (for < 30%): propose an adjusted target and/or timeline,
   re-run `assess_endurance_goal` on it, and show the new probability. Iterate with
   the athlete until you land on a goal you both accept. If the athlete insists on
   the original target, `upsert_goal` the negotiated milestone as the active goal (REUSE the original goal's id so it overwrites the raw ask)
   and note the original ask inline in the statement (e.g. "sub-45 10k — originally
   sub-40, renegotiated after a <30% verdict"). Never upsert the infeasible original
   as-is.

## Strength goals

The feasibility engine is endurance-only today — say so honestly. Anchor the
conversation in numbers you CAN compute: current `estimate_1rm` from a recent set,
the gap to the target, and evidence on realistic progression from `search_evidence`
(e.g. periodized progression, frequency and volume dose-response). Give a coaching
judgment labeled as such, not a fabricated probability. Same discipline as the
endurance path, minus the probability number: if the gap is clearly outside
realistic progression (say so, citing evidence on typical rates where the corpus
has it), do NOT proceed to program-generation without naming that and proposing
a milestone.

## Deep evidence search

Run on every goal assessment, right after `search_evidence`:

1. Call `search_evidence_live` with a `language_terms` dict — write the goal's key
   training question translated into en, fr, es, de, ru, no, sv, it, zh (skip any
   language you're not confident translating accurately). Each candidate already
   has its DOI/PMID verified.
2. For each candidate: if `suggested_study_type` is set, use it as-is (never
   upgrade it). If it's null, read the `abstract` and propose a `study_type` and a
   conservative 1-2 sentence `conclusions` — never a figure absent from the
   abstract. The grading ceiling still applies regardless of what you propose.
3. Call `save_evidence` for each candidate worth keeping — it becomes searchable
   immediately.
4. Still nothing relevant for a language? Fall back to a general web search
   (`WebSearch`/`WebFetch`) in that language for federations, theses, or
   conference proceedings. Any DOI/PMID you find this way MUST pass
   `verify_reference` before you attempt `save_evidence` — never propose an
   entry from an unverified web result.
5. Nothing found anywhere for the goal? Say so plainly: "deep search performed,
   no directly applicable study found for X, here is the closest available
   literature" — never force-fit an unrelated citation.

## Always

- Evidence claims: `search_evidence` ids only, stars shown, `check_citations` before
  presenting. No memory citations.
- Record the accepted goal via `upsert_goal` before leaving the skill.
