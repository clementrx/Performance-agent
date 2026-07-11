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

## Descoped with rationale (maintainer decision 2026-07-11)

- **Bodyweight-relative 1RM progression rates** (spec §4.1 "and relative to
  bodyweight") — deferred: needs strength-standards tables we don't have
  evidence-grade sources for yet; absolute-1RM rates by training age cover
  the feasibility need. Revisit when the corpus gains strength-standards
  data.
- **`reps_for_percentage_rir` as an MCP tool** — engine-only for now; the
  forward direction (`prescribe_reps_load`) is what prescription needs, and
  the inverse mainly serves the round-trip property test. Expose it if a
  skill ever needs "how many reps at X%".
