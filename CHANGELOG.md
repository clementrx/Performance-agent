# Changelog

All notable changes to PerformanceAgent. Versions follow the git tags.

## Unreleased

### Added

- **Claude Code plugin** — one-command setup that installs the MCP server **and**
  all 16 coaching skills together, replacing the manual `claude mcp add` + skills
  copy. From inside Claude Code:
  `/plugin marketplace add clementrx/Performance-agent` then
  `/plugin install performance-agent@performance-agent`. The repo is its own
  marketplace (`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`,
  and a root `.mcp.json` running `uvx performance-agent`); Claude Code keeps it
  updated via `/plugin marketplace update performance-agent`. Non-Claude-Code
  clients keep the manual per-host setup in [docs/installing.md](docs/installing.md).

## 0.10.0 — Garmin/Strava Connection & Recovery Analyst

### Added

- **One-command wearable connection** — `uvx performance-agent connect garmin`
  chains the interactive Garmin Connect login (MFA supported; OAuth tokens in
  `~/.garminconnect`, the password is never stored) with the MCP server
  registration in Claude Code (other clients get a paste-ready JSON snippet);
  `connect strava` registers the Strava server the same way, with the
  authorization running later in the browser from the coaching conversation.
  Recommended community servers: [taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)
  and [r-huijts/strava-mcp](https://github.com/r-huijts/strava-mcp).
- **Connected services on the profile** — `connected_services` records the
  athlete's Garmin/Strava accounts. When the matching MCP server is present in
  the session, check-ins pull activities directly (the original `.fit`/`.tcx`
  through `import_activity_file` when the server can download it, summary
  fields through the same propose → confirm → log flow otherwise) and device
  wellness (sleep, overnight HRV, stress) opens the readiness conversation —
  the athlete's own ratings remain the source of truth, and nothing is ever
  logged without confirmation. When the account exists but no server is
  connected, the skills walk the athlete through the setup steps in
  conversation instead of pointing at docs.
- **Deterministic recovery trends** — `analyze_wellness_trend` (103 tools)
  reads dated device series: overnight HRV as the last 7 days' rolling
  ln(rMSSD) mean against the preceding 28-day baseline with the smallest
  worthwhile change (0.5 × baseline SD, departures reported in BOTH
  directions), resting-HR bands beyond ±5 bpm, and sleep debt against a
  nightly target. Thin data returns `usable=false` with the reason, never a
  fabricated baseline; the HRV `delta_pct` feeds `compute_readiness`'s hrv
  modifier.
- **New skill `recovery-analyst`** (16 skills) — the device-data specialist:
  collects ~5 weeks of HRV/resting-HR/sleep, reads trends only through the
  engine, narrates them against training load (TSB, ACWR, monotony/strain),
  and routes convergent fatigue reads to session-day or program-adaptation.
  Descriptive trends only, never a diagnosis. Routed from performance-coach,
  training-checkin's sync path, and every mesocycle boundary.

## 0.9.0 — Pre-Competition Protocol

### Added

- **Pre-competition protocol** — the final days before any competition planned
  day by day, per calendar event, delivered as a versioned document
  (`competition/protocol-<event>-vN`) plus a standalone offline phone page for
  the event (no JS, en/fr/es, J0 open by default, starred bibliography).
- **Engine math for the final days** — `carb_loading_targets` (evidence-based
  g/kg windows by event duration + in-race fueling ranges), `select_attempts`
  (meet-day attempts from the estimated 1RM, with honesty flags when the goal
  is outside what the data supports), `pacing_plan` (even or negative splits
  landing on the target time), `protocol_window_days` (priority-adaptive
  trigger window derived from the taper).
- **Safety by construction** — risky peak-week practices (water/sodium
  manipulation, weight cuts) can only be stored as documented practices with a
  schema-required warning and an evidence grade; they are described, never
  dosed, never engine-quantified. `save_competition_protocol` refuses any
  citation id not in the evidence corpus.
- **Proactive trigger** — `list_due_actions` surfaces `competition_protocol`
  when an A/B event enters its window with no protocol saved (urgent within a
  week of the event).
- **New skill `pre-competition`** (15 skills) — the protocol-author ritual:
  re-reads the existing protocol before a v2, runs a dedicated research
  mini-wave, builds engine-first, passes program-review's protocol gate before
  saving, and routes the post-event debrief into the athlete's taper history.
  Five skills updated (coach routing, check-in debrief, session-day opens J0
  from the protocol page, deep-research pre-competition wave, program-review
  made protocol-aware).

## 0.8.0 — Living Evidence & Weekly Follow-up

### Added

- **Athlete document drop folder** — every athlete directory gets a
  `documentation/` folder (created at onboarding); drop studies, physio reports,
  lab results or past programs there and the coach picks them up at the next
  conversation. Verified studies (DOI/PMID/ISBN) join the evidence corpus;
  everything else informs coaching as context, never presented as science.
  New tools: `list_athlete_documents`, `mark_document_processed`.
- **Weekly loads review** — exercise blocks now carry a structured `progression`
  rule (double progression, linear load, RIR target, %1RM, none) and the new
  `suggest_next_week_loads` tool computes next week's exact working weights from
  the logged week — deterministic engine math with flags instead of guesses
  (`no_rule`, `failed_sets`, `clamped`, `no_matched_week`, …). New skill:
  `next-week-loads`. The review never modifies the program.
- **Program watch** — a biweekly per-exercise audit (keep / watch / substitution
  candidate) written as an immutable versioned report under `watch/` via
  `save_watch_report`; substitutions route through program-adaptation, never
  silently. New skill: `program-watch`. `list_due_actions` now surfaces an
  overdue loads review and an unaudited program.
- **Science on the gym page** — programs can carry cited `advice` and
  `rationale` lines; the markdown and offline HTML open with them and close
  with a starred bibliography (`[n]` markers on citing blocks, DOI links).
  `save_program` refuses any citation id not in the evidence corpus.
- **Research that stays alive** — deep-research gains document intake (step 0),
  targeted mini-waves on plateaus/injuries/athlete questions, and an
  incremental literature watch (`year_from` delta queries) at every mesocycle
  boundary, all folded into the versioned dossier.

## 0.7.0 — Dated Program Filenames

### Changed

- **Program files are named after their save date** — `programs/program-20260718.md`
  (+ `.html`, `.plan.yaml`); a second version the same day gets `-2`, then `-3`.
  The version number now lives only in the frontmatter and plan yaml — the
  store indexes versions by reading frontmatter, so pre-0.7 `program-vN.*`
  files stay readable and adaptable in place, no migration needed. Report PDFs
  keep their `program-vN-<mode>-<locale>.pdf` names.

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
