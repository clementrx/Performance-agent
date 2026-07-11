# Premium Coach Pipeline — Design

**Date:** 2026-07-11
**Status:** Validated with maintainer, awaiting implementation plans
**Supersedes:** extends the architecture blueprint (2026-07-10) and the live-evidence-search design (2026-07-10)

## Goal

Turn PerformanceAgent into a premium physical-preparation coach that serves **any**
athlete goal — hypertrophy, fat loss / recomposition, maximal strength (1RM),
endurance, and mixed-sport profiles (team sports, Hyrox, track) — with the same
honesty guarantees the endurance vertical has today. Every program is preceded by a
**deep, personalized, multilingual scientific literature search** run live for that
athlete; nothing is prescribed from a shallow evidence base.

The audit of 2026-07-11 found the current system endurance-only in practice: the
feasibility engine, memory schemas, and prescription math cannot represent a
strength athlete, and the live evidence search is a single shallow pass. This design
closes those gaps by reorganizing the product around the methodology of a real
strength & conditioning coach: a **pipeline of eight named agents**, backed by an
extended deterministic engine and a rebuilt research pipeline.

## Decisions taken with the maintainer

- Research is **deep and wide** (multi-country, multilingual, multi-query), run
  **live at every program creation** — minutes-long searches are an accepted cost.
- Coverage target: **all four pillars plus mixed-sport profiles** in this effort.
- Nutrition: **full quantified frame** (TDEE, deficit/surplus, protein, safe rates)
  with hard safety guards; no meal plans.
- No pre-computed discipline library: the needs analysis and research are
  **personalized per athlete**, every time.
- Reference **books** enter the corpus via ISBN verification (capped at
  expert-opinion grade). First entry: *Manuel ultime de musculation — Connaissances
  scientifiques et méthodologie*, Pourcelot, Reiss, Caverne, Albignac, Éditions
  Amphora, 2023, ISBN 978-2-7576-0546-2.

## 1. Architecture overview

The system becomes an eight-agent coaching practice, orchestrated as a pipeline:

```
Interview ─▶ Analyst ─▶ Researcher ─▶ Planner ─▶ Optimizer ─▶ Controller ─▶ 📄 program
 (intake)    (needs      (deep, live   (macro/     (concrete     (compliance
              analysis +  personalized  meso/micro  sessions,     + adversarial
              feasibility) research)    cycles)     co-built)     second opinion)
                                          ▲
              Nutritionist ───────────────┘ (joins when the goal touches body composition)

 Sentinel (continuous follow-up: logs, check-ins, stall/fatigue/weight-drift
 triggers; recalls the Planner when the program must change)
```

Agent names are user-facing personas, localized like the rest of the product
(fr: l'Entretien, l'Analyste, le Chercheur, le Planificateur, l'Optimiseur,
le Nutritionniste, le Contrôleur, le Vigile). Technically each agent is a dedicated skill
(its protocol, allowed tools, tone); heavy steps (Researcher, the Controller's
second opinion) run as real subagents in Claude Code. The founding principle
applies to every agent: **agents narrate, the engine calculates, the corpus cites**
— the Controller is its final guardian.

The pipeline rests on three shared foundations (the audit's gaps):

1. **Extended memory** — structured strength sessions (exercises, sets, reps, load,
   RIR), multi-lift 1RM inventory, bodyweight/body-fat time series, calendar type
   (single deadline vs recurring fixtures).
2. **Extended engine** — feasibility for strength/hypertrophy/body-composition,
   RIR↔%1RM↔reps tables, per-muscle volume landmarks, progression schemes, block/
   undulating/in-season periodization, nutrition math with hard safety floors.
3. **Deep research v2** — multi-query faceted fan-out, abstracts from all sources,
   date/publication-type filters, evidence-tier ordering, title cross-check,
   ISBN-verified books, systematic persistence into the athlete's personal corpus.

## 2. The eight agents

### Interview (evolves `athlete-onboarding`)
Intake conversation: goal(s), discipline, deadline and **calendar type** (single
competition / weekly fixtures / open-ended), training history, current performance
inventory (per-lift 1RMs, race times, bodyweight, body-fat if known), equipment,
availability, injuries, preferences. Persists via `write_profile` / `upsert_goal`.
New vs today: multi-lift inventory and calendar type.

### Analyst (new)
Translates discipline + goal into a **needs analysis**: priority muscle groups,
target qualities (strength, power, explosiveness, endurance, hypertrophy, mixed)
with their hierarchy, energy-system demands, sport-typical injury risks. Every claim
is cited or labeled coaching judgment. Also renders the **feasibility verdict**
through the extended engine (a real probability for any goal type, not only
endurance) and negotiates a counter-proposal when the goal is unrealistic. Output:
a versioned needs-analysis document in the athlete directory — the brief the
Researcher and Planner receive.

### Researcher (new — the core of the premium promise)
Receives the needs analysis and runs the **deep personalized research** (protocol in
§5): facet decomposition, multi-query multilingual fan-out, coverage loop, verified
persistence, contradiction-aware synthesis. Output: an **evidence dossier** —
per-facet synthesis with evidence grades, disagreements surfaced, everything saved
through `save_evidence`.

### Planner (new — absorbs the upstream half of `program-generation`)
From the evidence dossier + calendar, chooses and justifies the periodization model
(block toward a deadline, daily/weekly undulating, in-season maintenance around
fixtures), splits macro → meso → microcycles, places deloads and tapers, sets
volume/intensity targets per cycle through the engine. Output: a quantified program
skeleton, every structural choice cited.

### Optimizer (absorbs the downstream half of `program-generation`)
Turns the skeleton into concrete sessions **with** the athlete: exercise selection
under equipment/injury/preference constraints, sets×reps @ %1RM or RIR (loads
computed by `prescribe_load`, never guessed), split design matched to available
days. Iterates until the athlete validates. Output: a complete draft program.

### Nutritionist (new — activates when the goal touches body composition)
TDEE, target deficit/surplus, protein g/kg, safe weekly rate of loss/gain — all
computed by the engine, with inviolable guards (caloric floor, maximum loss rate,
minimum protein in deficit, refusal + referral to a health professional on
eating-disorder red flags). Synchronizes with the Planner (no aggressive deficit
during an intensification block). Output: a quantified nutrition frame annexed to
the program. No meal plans.

### Controller (new — the delivery gate)
Dual role. **(a) Compliance:** every number traces to an engine tool, every citation
passes `check_citations`, safety guards respected, program consistent with declared
constraints (equipment, days, injuries). **(b) Adversarial second opinion:** an
independent subagent receives the program and the evidence dossier and tries to
tear it down ("is this volume sustainable on 3 sessions/week? does this planning
contradict study X?"). Surviving objections go back to the Planner/Optimizer.
Nothing is delivered (`save_program`, PDF) without its sign-off; rejections are
motivated and audited.

### Sentinel (evolves `training-checkin` + `program-adaptation`)
Lives between sessions: structured session logging, check-ins, and extended
triggers — load stall over N sessions, failed reps, fatigue ≥ 8, bodyweight
drifting off the cut trajectory, fixture pile-up. On trigger, diagnoses from logged
data and recalls the Planner/Optimizer for a new program version (audited reason,
as today).

## 3. Data flow and athlete directory

Every agent reads and writes plain files in the athlete directory — the pipeline's
shared state. Each artifact is versioned and dated (the audit trail extends to
analyses and research dossiers), and each agent only writes its own artifacts,
keeping the pipeline diagnosable.

```
athlete/
├── profile.yaml            # extended: per-lift 1RM inventory, body-fat %,
│                           # calendar type, split preferences
├── goals.yaml              # multi-goal, prioritized
├── needs-analysis-v1.md    # NEW — Analyst output (versioned)
├── research/
│   └── dossier-v1.md       # NEW — Researcher output: per-facet synthesis,
│                           # evidence grades, contradictions
├── evidence_extra.yaml     # existing — every found study persisted verified
├── programs/
│   └── program-v1.md       # enriched: justified mesocycles, sessions with
│                           # sets×reps×load×RIR, nutrition annex
├── nutrition/
│   └── frame-v1.yaml       # NEW — Nutritionist output (versioned, recomputed
│                           # when weight or phase changes)
├── sessions.yaml           # EXTENDED — structured sessions: exercises →
│                           # sets {reps, load_kg, rir}, plus rpe/duration
└── checkins.yaml           # EXTENDED — bodyweight, measurements, PRs, signals
```

Nominal flow: Interview fills `profile` + `goals` → Analyst writes
`needs-analysis` (with feasibility verdict) → Researcher fills `research/` and
`evidence_extra` → Planner + Optimizer (+ Nutritionist when relevant) produce a
draft → Controller approves or returns it → `save_program` writes
`program-v1.md`. Then the Sentinel feeds `sessions`/`checkins` and, on trigger,
recalls the Planner, producing `program-v2.md` with an audited reason.

## 4. Engine extensions

The engine stays pure (stdlib, zero LLM, property-tested). Every constant
(progression rates, volume landmarks, caloric floors) is sourced from literature
and documented in code. Four new families:

### 4.1 Multi-goal feasibility (`feasibility.py` extended)
- `strength_feasibility`: same logistic mapping as endurance, with 1RM progression
  rates by training age (and relative to bodyweight).
- `hypertrophy_feasibility`: realistic lean-mass gain rates by training age
  (kg/month); horizon required for "+5 kg of muscle".
- `bodycomp_feasibility`: safe fat-loss rates (% bodyweight/week) with
  muscle-retention constraints — answers "12 % body fat in 10 weeks: realistic,
  and at what cost".

### 4.2 Strength/hypertrophy prescription (`strength.py` extended)
- Bidirectional RIR/RPE ↔ %1RM ↔ reps table — the core triad of modern
  prescription.
- Per-muscle weekly volume landmarks (minimum/optimal/maximum ranges by level).
- Progression schemes as deterministic functions "current state → next
  prescription": double progression, load increments, top set/back-off, wave
  loading.
- Additional 1RM formulas (Lombardi, Wathan) with widened validity ranges.

### 4.3 Multi-model periodization (`periodization.py` extended)
- Adds to the current waves: **block** periodization (accumulation →
  intensification → realization, for the 6-months-out deadline), **daily/weekly
  undulating** (DUP), and **in-season** (minimum effective dose around fixtures,
  1-vs-2-match weeks).
- Strength peaking: taper toward a 1RM test (volume drop, intensity maintained,
  last heavy exposures placed).

### 4.4 Nutrition (`nutrition.py`, new)
- BMR (Mifflin-St Jeor) → TDEE (activity factor including planned training load)
  → target deficit/surplus → daily calories and protein g/kg.
- Hard-coded guards, not bypassable by agents: absolute caloric floor, maximum
  loss rate, minimum protein in deficit, refusal when BMI or signals indicate a
  risk profile (referral to a health professional).

Every function is exposed as an MCP tool (count grows from ~26 to ~40). Memory
schemas extend in parallel (§3).

## 5. Deep research v2 (the Researcher)

Split between deterministic server code and agent reasoning.

### Server side — `search_evidence_live` v2
- **Abstracts everywhere:** PubMed moves from esummary to efetch (full abstracts);
  **OpenAlex** joins Crossref and Semantic Scholar as a fourth keyless source.
- **Filters exposed to the agent:** date range, publication type (meta-analysis,
  systematic review, RCT), minimum population size where the source provides it.
- **Evidence-tier ordering:** candidates return ranked meta-analyses → reviews →
  RCTs → cohorts, most recent first within a tier.
- **Pagination and budget:** up to ~25 results per query (vs 5 today), DOI/PMID
  dedup across sources and queries.
- **Integrity:** the agent-reported title is cross-checked against the registry
  (same token-overlap check as the maintainer corpus — closes a current gap).
- **Books:** a `reference_book` corpus category verified by **ISBN** (Open
  Library / Google Books lookup, same anti-fabrication principle as DOI/PMID).
  Grade capped at expert opinion: a book can source exercise-technique and
  pedagogy prose, never override a meta-analysis. Tracing rule: when a book makes
  a measurable claim, the Researcher traces it to the primary studies rather than
  citing the book.

### Agent side — the Researcher protocol
1. **Facet decomposition** from the needs analysis: periodization × calendar,
   dose-response per target quality, exercise selection per priority muscle,
   population specifics (age, sex, level, sport).
2. **Fan-out:** 3–5 queries per facet (synonyms, competing terminologies), each in
   several languages (en/fr/es/de/pt/zh/ru/…).
3. **Coverage loop:** after each wave, assess which facets remain thin and
   relaunch reformulated queries until covered or reformulations are exhausted —
   never a single pass.
4. **Systematic persistence:** every retained study is verified (DOI/PMID + title)
   then saved to `evidence_extra.yaml` with its grade.
5. **Contradiction-aware synthesis:** the dossier presents, per facet, what
   converges, what disagrees (both camps cited), and the confidence level.

Accepted order of magnitude: dozens of queries and a few minutes per program.

## 6. Error handling, safety, and testing

### Degraded modes and honesty
- Researcher finds nothing on a facet → the dossier says so ("thin evidence,
  recommendation = coaching judgment").
- A search API fails → continue with remaining sources, flag the gap.
- The engine refuses a computation (nutrition guard, out-of-bounds goal) → the
  agent relays the refusal; it never works around it.
- The Controller is a mandatory gate: no `save_program`, no PDF without sign-off;
  rejections are motivated and audited.
- Health guards (nutrition floors, pain/eating-disorder red flags) live in the
  engine, not in prompts — no agent can disable them.

### Testing
- Property-based tests on all new math: feasibilities bounded [0,1],
  prescriptions never violate a volume landmark or caloric floor, periodizations
  sum correctly across weeks.
- The engine-purity architectural test extends to new modules; the skills'
  anti-fabrication tests extend to all eight agents.
- Pipeline integration tests: a synthetic athlete profile traverses all eight
  stages end to end.

## 7. Build phases

Each phase is one implementation plan, shippable and testable alone; the order
follows dependencies (agents cannot exist before their tools).

1. **Memory foundation** — extended schemas (structured sessions, 1RM inventory,
   bodyweight/body-fat series, calendar type). Everything depends on this.
2. **Multi-goal engine** — feasibilities, RIR tables, volume landmarks,
   progressions, periodization models, nutrition.
3. **Deep research v2** — abstracts, OpenAlex, filters, evidence-tier ordering,
   title cross-check, ISBN book category (Manuel ultime de musculation as first
   entry).
4. **Upstream agents** — enriched Interview, Analyst, Researcher (the skill
   protocols exploiting phases 1–3).
5. **Production agents** — Planner, Optimizer, Nutritionist.
6. **Guardians** — Controller (compliance + adversarial second opinion) and
   Sentinel (extended triggers).

At the end of phase 6, the full practice is in place: any athlete, any goal,
premium treatment.
