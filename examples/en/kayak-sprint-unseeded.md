> **Example output** — the determinants-engine flow for a sport PerformanceAgent
> ships **no seed model** for (canoe sprint). The point: an unseeded sport is coached
> exactly like a seeded one. The coach researches the event, fills a structured
> PerformanceModel, and the deterministic engine does the rest — gaps, test battery,
> scored exercise selection, and a multi-year macrocycle. Numbers are illustrative;
> provenance labels and honesty gates are real.

# K1 200 m sprint — modeling an unseeded sport

**Athlete:** national-level sprint kayaker, major target 2 years out (Worlds).
**Why this example:** there is no `canoe-sprint.yaml` in the seed library. The machine
does not need one.

## 1. The researched PerformanceModel (saved, versioned)

The Analyste searches the literature, then fills the generic schema — every value
carries a provenance label (`cited` needs a corpus id; otherwise `prior` or
`judgment`). For canoe sprint the corpus is thin, so most values are coach `judgment`:

| Quality | Weight | Provenance |
|---|---|---|
| anaerobic_capacity | 0.35 | prior |
| max_strength | 0.20 | judgment |
| muscular_endurance | 0.20 | judgment |
| explosive_strength | 0.15 | judgment |
| aerobic_capacity | 0.10 | prior |

KPIs: **K1 200 m time** (s, lower-is-better; elite 34.0) and **bench-pull 1RM**
(kg, higher-is-better; elite 110). Energy split ≈ 60% lactic / 25% aerobic / 15%
alactic. Injury flag: shoulder (repetitive high-rate pulling).

`save_performance_model` validates it (unknown quality names, uncited "cited" values,
un-normalizable weights are all rejected) and stores `models/performance-model-v1.yaml`.

## 2. Gaps against the elite benchmark (engine)

The athlete logs two measurements: K1 200 m in **38.0 s** and a bench pull of **95 kg**.
`compute_performance_gaps(level="elite")`:

- `k1-200-time`: 38.0 vs 34.0 → gap **11.8%** (anaerobic_capacity)
- `bench-pull-1rm`: 95 vs 110 → gap **13.6%** (max_strength)
- CMJ / other qualities: **unmeasured** — reported as unknowns to test, never a
  guessed number.

Per-quality priority (mean gap × weight) ranks the measured weaknesses first;
unmeasured qualities sink to the end as "test these".

## 3. Test battery & scored selection

`plan_test_battery` schedules baseline and cadence re-tests around the calendar,
never inside a taper. `score_exercises` (targeting `max_strength`, equipment the
athlete has) returns a justified ranking — e.g. **Barbell Row** and **Pendlay Row**
top a `pull_h` search, each with an attribute breakdown (quality match × phase
specificity × equipment × contraindication × novelty). The shoulder flag hard-excludes
anything contraindicated for the shoulder.

## 4. Two-year macrocycle (engine)

`build_macro_plan(horizon_years=2)` types the years backward from Worlds:

- **Year 1 — development:** general-capacity bias (max_strength, muscular_endurance,
  aerobic base) plus the biggest measured weaknesses.
- **Year 2 — realization:** specific/competition bias (anaerobic_capacity, explosive
  strength) toward the 200 m.

Each year's quality budget feeds `build_season_plan`; `check_residuals` warns if a
maintained quality (e.g. max_strength, ~30-day retention) would decay across a long
development block without a refresh.

---

No code path anywhere special-cases the string "canoe sprint". The same tools that
coach a sprinter or a powerlifter coached this — that is the whole point of the
determinants engine.
