---
name: program-generation
description: Use after a goal has been assessed as accepted. Builds the periodized
  program from evidence and engine math, personalizes it to the athlete's real
  constraints, and saves it through the versioned program store.
tools: [read_athlete, get_time_context, search_evidence, search_evidence_live,
        save_evidence, verify_reference, get_citation, check_citations,
        build_periodization_waves, prescribe_load, estimate_1rm,
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
`get_citation`. If a question returns nothing from `search_evidence`, run
`search_evidence_live` with translated `language_terms` (en, fr, es, de, ru, no, sv,
it, zh) before concluding the corpus has no entry. Classify and `save_evidence` any
verified candidate worth citing — `suggested_study_type` if set, otherwise your own
abstract-based proposal (grading ceiling still enforced). Still nothing? Fall back
to a web search per language, `verify_reference` anything with a locator before
proposing `save_evidence`, and if that also comes up empty, label that part of the
plan as coaching judgment rather than force a citation.

## 2. Structure

- Weeks available: quote `get_time_context`.
- Call `build_periodization_waves` (choose deload_every and taper_weeks to fit the
  goal; racing goals get a taper, strength peaks usually 1 taper week).
- The waves are multipliers against YOUR baseline week: define the baseline
  (week-1 volumes and intensities), then scale each week by its volume_factor
  (sets/duration) and intensity_factor (the %1RM you pass to `prescribe_load`, the
  pace effort you target). A wave you don't apply to the numbers is decoration.
- Map waves onto weekly session slots from profile.availability. Confirm
  availability is still current before laying out the week. Respect
  sessions_per_week strictly — a plan the athlete cannot attend is a failed plan.

## 3. Sessions

For each week, write concrete sessions. Every hard prescription must be computed:
- Strength loads: `estimate_1rm` from a recent set → `prescribe_load` for the
  percentage you program. Never guess a load in kg.
- Running paces: only RACE pace at a distance is computable (`predict_race_time` /
  `compute_pace` from a current benchmark; note the tools enforce 1500 m–marathon).
  Easy, threshold, and interval paces are coaching-judgment DERIVATIONS from race
  pace — label the NUMBER itself "coaching judgment (derived from race pace)",
  never present a derived pace as tool-computed. Never guess a pace, same rule as
  loads.
- No recent set or benchmark to compute from (e.g. the goal was assessed off a
  derived estimate)? Open the program with a benchmark/test week and label the
  early loads provisional — do not guess a number to fill the gap.
- **Formatting is not optional, and it is uniform across every session in the
  program — no exceptions for "short" or "simple" days.** Each session is a
  markdown bullet list, ONE exercise per bullet, never multiple exercises folded
  into a single prose sentence. Every bullet carries, in this order: exercise name,
  sets×reps or duration, load/pace/RPE, rest, and a one-line **purpose**. Never
  drop the rest field because it "feels obvious" — write it every time, even for
  accessory work (e.g. "rest 60-90s"). Purposes backed by evidence carry the corpus
  citation and its **stars**; purposes without corpus backing are labeled
  "coaching judgment". Template for every session, copy this shape exactly:

  ```
  **[Day] [slot] — [session name]:**
  - [Exercise]: [sets]×[reps] @ [RPE or %1RM] — rest [X min/sec]. *[Purpose]
    ([citation], [stars]) or (coaching judgment).*
  - [Exercise]: ...
  ```

  Before saving, re-read every session in the program and confirm each one matches
  this template bullet-for-bullet — a session that mixes prose and bullets, or
  omits rest/RPE on even one exercise, is not done yet.

## 4. Personalize before saving

Check the plan against profile equipment and injuries. Missing equipment → propose
the substitution, state the expected difference in stimulus, ask the athlete.
Active injury → adapt around it (performance-coach red-flag rules). Ask the athlete
to confirm the weekly layout before you save.

## 5. Save and deliver

- Run `check_citations` over the full program text; fix anything flagged.
- `save_program` (markdown body; goal_id; v1 needs no reason). Quote the saved
  version and path back. Check `read_athlete`'s program_version first: versioning
  is GLOBAL across the athlete directory, so if ANY program already exists this
  save is v2+ and REQUIRES a reason (e.g. "first program for new goal
  sub-45-10k"). Only a truly first-ever program is v1.
- Carry the assessment's named risks and checkpoints into the program's check-in
  triggers.
- Close with: how to log sessions (`log_session`), when the first check-in happens
  (Mode B), and what would trigger an early adaptation.
