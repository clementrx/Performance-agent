# Engineering Backlog

Durable record of review findings and maintainer descope decisions that no
single plan owns. Items graduate into a plan task (and get deleted here) or
stay with their rationale.

## Open items (from phase 1-2a reviews, 2026-07-11)

- **Shared validation helper** — `engine/feasibility.py` now has four
  near-identical validate-finite/positive blocks (`_validate_inputs`,
  `_validate_load_inputs`, plus inline blocks in `hypertrophy_feasibility`
  and `bodycomp_feasibility`). Extract a shared helper in
  `engine/_validation.py`; interpolate `MIN/MAX_PLAUSIBLE_BODY_FAT_PCT` into
  the bodycomp error message while touching it.
- **`Goal.current_value`/`target_value` accept NaN/inf** —
  `memory/schemas.py`; add `allow_inf_nan=False` bounds like
  `CheckinEntry.measurements`.
- **Bodycomp `pct` naming** — inputs are true percents (12.0), output rate
  fields are fractions (0.0075). Documented in docstrings; rename outputs to
  `_frac_bw` on the next schema-touching task.
- **`weekly_set_targets_for` naming** — breaks the verb-first tool
  convention; rename to `get_weekly_set_targets` only if a breaking-change
  window appears.
- **Lift-name normalization** — `LiftRecord.lift`, `RepPR.lift` and
  `ExercisePerformed.name` are free strings; the first tool that joins them
  (stall detection, auto 1RM refresh) must introduce canonical names or a
  normalizer at the join point.
- **`Profile.weight_kg` vs `CheckinEntry.bodyweight_kg`** — same quantity,
  two names (static fact vs time series). The Interview/Vigile skills must
  state the mapping when they are written.

## Open items (from phase 2b reviews, 2026-07-11)

- **Weekly undulating (WUP) variant** — spec §4.3 says "daily/weekly
  undulating"; only daily landed. Weekly can be composed from
  `build_undulating_sessions` across weeks; add a dedicated model only if a
  Planner use case demands it.
- **Eating-disorder signal refusal engine-side** — spec §4.4 mentions
  "BMI or signals"; only the BMI refusal is in `engine/nutrition.py`. The
  signal-based red flags belong to the guardians phase (Contrôleur/Vigile) —
  do not silently drop.
- **Load-increment recommendations** — spec §4.2 "load increments" exists
  only as `double_progression`'s `increment_kg` parameter; training-age- and
  exercise-specific increment suggestions (2.5 kg upper / 5 kg lower) are
  Optimizer-skill coaching judgment, not engine math.
- **`weekly_weight_change_kg` on clamped results** reflects the requested,
  not achievable, rate (documented in docstrings); revisit if a consumer
  starts trusting it numerically.

## Open items (from phase 3 reviews, 2026-07-11)

- **`titles_match` min-set containment leniency** — a very short claimed
  title whose tokens all appear in the registry title passes. Accepted
  residual (it is what makes subtitle omissions and Open Library short
  titles work); the phase-4 Researcher protocol must instruct agents to
  save the registry's canonical title (translated titles are rejected by
  design).
- **Verification latency at full budget** — `run_live_search` sleeps 0.5s
  per candidate post-dedup; a multi-language full-budget run can take a few
  minutes (documented in the docstring). If latency ever matters, verify in
  tier order and stop at K.

## Descoped with rationale (maintainer decision 2026-07-11)

- **Minimum-population-size live-search filter** (spec §5 "where the source
  provides it") — none of PubMed/Crossref/Semantic Scholar/OpenAlex exposes
  sample size in search results, so the condition resolves to nowhere.
  Deliberately not implemented; the agent grades population from abstracts.

- **Bodyweight-relative 1RM progression rates** (spec §4.1 "and relative to
  bodyweight") — deferred: needs strength-standards tables we don't have
  evidence-grade sources for yet; absolute-1RM rates by training age cover
  the feasibility need. Revisit when the corpus gains strength-standards
  data.
- **`reps_for_percentage_rir` as an MCP tool** — engine-only for now; the
  forward direction (`prescribe_reps_load`) is what prescription needs, and
  the inverse mainly serves the round-trip property test. Expose it if a
  skill ever needs "how many reps at X%".
