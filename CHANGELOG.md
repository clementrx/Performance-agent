# Changelog

All notable changes to PerformanceAgent. Versions follow the git tags.

## 0.6.1 — Dated Program Titles

### Changed

- **Program titles carry their date** — the markdown H1 and the session-HTML
  `<title>`/`<h1>` now read `Program v2 — 20260717 — <goal>`: each version is
  stamped with its creation date (YYYYMMDD), so versions are tellable apart at
  a glance. File names are unchanged (`program-vN.md`/`.html` — the store's
  immutable version chain).

## 0.6.0 — One Folder per Athlete

The directory the server is launched from IS the athlete's data directory, so a
coaching folder can hold one subfolder per athlete: `cd ~/coaching/marie && claude`.
93 MCP tools (unchanged).

### Changed

- **Athlete dir = launch dir** — `resolve_athlete_dir()` now returns
  `PERFORMANCE_AGENT_HOME` if set, else the server's working directory. The
  `./athlete/` convention and the `~/.performance-agent` fallback are removed.
  Launching from `$HOME` or a filesystem root is refused with an actionable
  error. **Migration:** `mkdir -p ~/coaching/me && mv ~/.performance-agent/* ~/coaching/me/`
  (`cache/` can stay — the shared exercises-media cache location is unchanged).

### Fixed

- **Session HTML GIFs on phones** — the page previously injected each GIF's
  data URI via an inline script, so viewers that don't run JavaScript (iOS
  Quick Look from the Files app, in-app file previews) showed no media. GIFs
  are now embedded as shared CSS `background-image` rules — same
  one-copy-per-GIF dedup, zero JavaScript on the page.

## 0.5.0 — Session HTML

The program the athlete actually opens at the gym. 1243 → 1270 tests; 93 MCP
tools (unchanged).

### Added

- **Standalone session HTML** — `save_program` now writes `program-vN.html` next
  to the markdown: a self-contained, offline-ready page for the gym with each
  strength exercise's animation GIF (embedded base64, deduplicated), step-by-step
  technique in the athlete's locale (en/fr/es), sets, reps, load, rest, warm-up
  ramps, progression rules and per-session fallbacks. Media and instructions come
  from [hasaneyldrm/exercises-dataset](https://github.com/hasaneyldrm/exercises-dataset)
  (1,324 exercises), cloned to `~/.performance-agent/cache/exercises-dataset` by a
  background sync at server start (`PERFORMANCE_AGENT_EXERCISES_DATASET` overrides
  the location; `PERFORMANCE_AGENT_NO_DATASET_SYNC=1` disables the sync). Blocks
  resolve through a curated seed→dataset mapping (~80 exercises) with a
  high-cutoff name fallback — an unresolved exercise renders without media rather
  than with the wrong GIF; without the clone the page still carries the full
  prescription.

## 0.4.0 — Beyond-Olympic Prep

Upgrades planning, programming and exercise selection past a discipline-specific
S&C coach, for ANY sport, by making sport knowledge, exercise choice and adaptation
into structured, computed decisions. 76 → 93 MCP tools; 1016 → 1243 tests.

### Added

- **Sport-agnostic PerformanceModel** — the researched, versioned answer to "what
  determines performance in this event": trainable qualities (normalized weights),
  KPIs with level benchmarks, injury risks and an energy-system split, every value
  provenance-labeled `cited | prior | judgment`. Four packaged seed models (sprint,
  10k, powerlifting, football) are examples, not a support gate.
- **Gap analysis & test battery** — measured KPIs scored against benchmarks (per-KPI
  gaps, per-quality priorities; unmeasured stays unmeasured), and a dated test
  battery scheduled as experiments around the calendar.
- **Exercise ontology & scored selection** — ~120 attributed exercises + athlete
  additions; deterministic scored ranking (quality match × phase specificity ×
  equipment × contraindication × novelty), stimulus-equivalence substitution and a
  mesocycle specificity-mix guard.
- **High-resolution ingestion (optional)** — velocity-based-training CSV import,
  power/normalized-power/cadence/lap-splits from `.fit`/`.tcx`, jump/sprint KPIs;
  missing data lowers stated resolution rather than blocking.
- **Load-velocity profiling** — fitted per-exercise velocity-load line with an
  estimated 1RM and honest gates, feeding bounded day-of load suggestions.
- **Fitted Banister model** — per-athlete two-component fitness-fatigue fit
  (pure-Python grid + OLS), gated (≥8 weeks load, ≥5 spanning points, τ1 > τ2).
- **Individual taper response** — detects past tapers from the log and recommends
  duration/reduction from the athlete's own best-outcome taper, else the labeled
  population rule; per-quality progression rates keyed through the model KPIs.
- **Multi-year macrocycle & training residuals** — a 1-4 year plan typed backward
  from the major event with per-year quality budgets from the gap priorities, and a
  residuals guard (Issurin retention windows). Training age modulates block length.
- **Reports** — the expert report now renders the fitted fitness-fatigue summary
  (Banister params, approximate CIs, or a "population model stands" line) and
  per-quality rates, with provenance and uncertainty shown (en/fr/es).

### Notes

- **Environment & fine peaking** (altitude/heat/jet-lag/competition-hour) are
  deliberately deferred to the next iteration.
- Corpus citations for several new constants (Banister/Morton, Issurin,
  González-Badillo/Sánchez-Medina) are labeled team-chosen priors pending
  DOI/PMID/ISBN verification — never fabricated.

## 0.3.0

Beyond-national coach planning pipeline: season calendar, backward season planning,
readiness/autoregulation, individual response profile, deload & return-to-load,
proactive follow-up, deterministic end-to-end simulation, Typst PDF reports.

## 0.2.0

Evidence corpus, feasibility engine, structured programs, nutrition frame.

## 0.1.0

Initial MCP server: deterministic S&C engine and file-based athlete memory.
