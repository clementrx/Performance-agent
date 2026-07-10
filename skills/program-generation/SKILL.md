---
name: program-generation
description: Use after a goal has been assessed as accepted. Builds the periodized
  program from evidence and engine math, personalizes it to the athlete's real
  constraints, and saves it through the versioned program store.
tools: [read_athlete, get_time_context, search_evidence, get_citation,
        check_citations, build_periodization_waves, prescribe_load, estimate_1rm,
        predict_race_time, compute_pace, save_program, log_session]
---

# Program Generation

Follow performance-coach global rules. The program is a coaching document the
athlete will live with — make it concrete, honest, and traceable. Profile
constraints (equipment, injuries, availability) come from `read_athlete`.

## 1. Evidence pack

Query `search_evidence` (in ENGLISH, whatever the athlete's language) for the goal's
key training questions — e.g. for a 10K goal: strength training and running economy,
interval vs continuous work, tapering; for barbell strength: volume and frequency
dose-response, progression models. Collect the ids, stars, and conclusions you will
build on. Render the full citation string for any id you plan to quote with
`get_citation`. If a question returns nothing, say the corpus has no entry yet and
label that part of the plan as coaching judgment.

## 2. Structure

- Weeks available: quote `get_time_context`.
- Call `build_periodization_waves` (choose deload_every and taper_weeks to fit the
  goal; racing goals get a taper, strength peaks usually 1 taper week).
- Map waves onto weekly session slots from profile.availability. Respect
  sessions_per_week strictly — a plan the athlete cannot attend is a failed plan.

## 3. Sessions

For each week, write concrete sessions. Every hard prescription must be computed:
- Strength loads: `estimate_1rm` from a recent set → `prescribe_load` for the
  percentage you program. Never guess a load in kg.
- Running paces: `predict_race_time` / `compute_pace` from a current benchmark.
- Each session line carries: what, sets×reps or duration, the computed load/pace,
  rest, and a one-line **purpose**. Purposes backed by evidence carry the corpus
  citation and its **stars**; purposes without corpus backing are labeled
  "coaching judgment".

## 4. Personalize before saving

Check the plan against profile equipment and injuries. Missing equipment → propose
the substitution, state the expected difference in stimulus, ask the athlete.
Active injury → adapt around it (performance-coach red-flag rules). Ask the athlete
to confirm the weekly layout before you save.

## 5. Save and deliver

- Run `check_citations` over the full program text; fix anything flagged.
- `save_program` (markdown body; goal_id; v1 needs no reason). Quote the saved
  version and path back.
- Close with: how to log sessions (`log_session`), when the first check-in happens
  (Mode B), and what would trigger an early adaptation.
