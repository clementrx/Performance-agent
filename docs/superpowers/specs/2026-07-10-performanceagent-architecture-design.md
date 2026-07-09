# PerformanceAgent — Technical Architecture Blueprint

**Date:** 2026-07-10
**Status:** Approved (2026-07-10)
**Scope:** Complete technical design for an open-source, AI-powered, evidence-based
physical preparation platform (digital strength & conditioning assistant).

---

## 1. Executive Summary

PerformanceAgent is an open-source AI coaching ecosystem that designs, explains, monitors,
and adapts physical preparation programs for any athlete, sport, and objective. It is not a
workout generator: it is a long-lived coaching system built on three pillars:

1. **Evidence first** — every recommendation traces to graded scientific sources stored in a
   verifiable evidence database. The system architecturally *cannot* fabricate references.
2. **Adaptive coaching** — programs are living objects that respond to completed sessions,
   fatigue, injuries, missed workouts, and schedule changes.
3. **Long-term athlete memory** — a structured, persistent athlete profile means no
   conversation ever starts from zero.

The architecture is a **modular monolith** (Python/FastAPI) hosting a **multi-agent
orchestration layer** (LangGraph), a **deterministic sports-science engine** (pure Python,
no LLM), a **RAG evidence pipeline** (PostgreSQL + pgvector), and a **Next.js frontend**
with first-class i18n (English, French, Spanish).

A core design stance: **LLMs narrate and reason; deterministic code calculates.** Feasibility
scores, race-time predictions, training-load models, and progression math live in a
unit-testable engine. Agents call the engine as tools and explain its outputs. This keeps
the science reproducible, testable, and honest.

---

## 2. Approach Options Considered

### Option A — Modular monolith: Python backend + LangGraph + Postgres/pgvector + Next.js (RECOMMENDED)

- **Pros:** Python owns the scientific ecosystem (numpy/scipy/pandas for the simulation
  engine), the strongest RAG/agent tooling, one deployable unit for self-hosters
  (`docker compose up`), clean extraction path to services later. LangGraph provides
  durable agent state, checkpointing, and human-in-the-loop interrupts — exactly what
  Mode B (long-term coach) requires.
- **Cons:** Two languages across the repo (Python API, TypeScript web). Mitigated by an
  OpenAPI-generated TypeScript client.

### Option B — TypeScript full-stack (Next.js + Vercel AI SDK / Mastra)

- **Pros:** One language, one runtime, simpler contributor story for web developers.
- **Cons:** The simulation engine (impulse-response load models, Bayesian feasibility
  estimation, performance prediction) fights the ecosystem; scientific literature ingestion
  and evaluation tooling are weaker; the S&C/data-science contributor community lives
  in Python.

### Option C — Microservices per agent from day one

- **Pros:** Independent scaling of agents.
- **Cons:** Nine networked services for a project with zero users is operational suicide for
  an open-source, self-hostable product. Agents share the same athlete state constantly;
  network boundaries between them add latency and failure modes without benefit.

**Decision: Option A.** Agents are modules behind interfaces, not services. If one agent ever
needs independent scaling (e.g., literature ingestion), it extracts cleanly because module
boundaries are enforced from day one.

---

## 3. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend runtime | Python 3.13 + `uv` | Scientific ecosystem, agent tooling |
| API framework | FastAPI + Pydantic v2 | Async, typed, OpenAPI-native |
| Agent orchestration | LangGraph | Stateful graphs, checkpointing, interrupts, streaming |
| LLM access | Provider-agnostic adapter (default: Anthropic Claude; OpenAI, local via Ollama/vLLM supported) | Open-source users bring their own key/model |
| Embeddings | Provider-agnostic (default: `voyage-3.5`; local fallback `bge-m3` — multilingual) | Multilingual corpus (EN/FR/ES queries against EN literature) |
| Relational DB | PostgreSQL 16 | Single source of truth |
| Vector store | pgvector (same Postgres) | One database to operate; hybrid search with `tsvector`. Revisit dedicated store (Qdrant) only if corpus > ~5M chunks |
| Background jobs | Procrastinate (Postgres-backed queue) | Zero extra infrastructure; Redis not required for MVP |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic | Standard, typed |
| Frontend | Next.js 15 (App Router) + TypeScript | SSR, ecosystem |
| UI | Tailwind CSS + shadcn/ui | Accessible, themeable |
| Data fetching | TanStack Query + OpenAPI-generated client | Type-safe API contract |
| i18n (UI) | next-intl | Message catalogs for en/fr/es |
| Charts | Recharts | Progress dashboards |
| Auth | fastapi-users (JWT + OAuth2, optional OIDC) | Self-host friendly; no SaaS dependency |
| PDF reports | Typst (via `typst` CLI in worker) | Professional typesetting, fast, templatable, versionable templates |
| Observability | OpenTelemetry + structlog; Langfuse (self-hostable) for LLM traces | Explainability requires tracing every agent decision |
| Python tooling | `uv`, `ruff`, `ty`, `pytest` | Per project standards |
| TS tooling | `pnpm`, `oxlint`, `oxfmt`, `vitest`, strict `tsc` | Per project standards |
| Packaging | Docker + docker-compose; single-node deploy | Self-host first |
| CI/CD | GitHub Actions (SHA-pinned) | Lint, typecheck, test, eval, build |

**Assumption stated:** Redis is deliberately excluded from the MVP. Procrastinate gives
Postgres-backed queues/schedules; caching needs at MVP scale are served by Postgres and
in-process caches. Add Redis only when measured.

---

## 4. System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          Next.js Web App                           │
│   onboarding wizard · chat · program calendar · dashboards · PDF   │
│                    next-intl (en / fr / es)                        │
└───────────────┬────────────────────────────────────────────────────┘
                │ HTTPS (REST + SSE streaming)
┌───────────────▼────────────────────────────────────────────────────┐
│                        FastAPI Application                         │
│  ┌──────────────┐  ┌───────────────────────────────────────────┐  │
│  │  REST API    │  │        Agent Orchestrator (LangGraph)     │  │
│  │  auth        │  │  coach graph · onboarding graph ·         │  │
│  │  athletes    │  │  program-generation graph · check-in graph│  │
│  │  programs    │  └──────┬──────────────────┬─────────────────┘  │
│  │  sessions    │         │ tools            │ state              │
│  │  chat (SSE)  │  ┌──────▼──────┐   ┌───────▼───────┐            │
│  │  reports     │  │ Sports      │   │ Athlete       │            │
│  │  evidence    │  │ Science     │   │ Memory        │            │
│  └──────────────┘  │ Engine      │   │ Service       │            │
│                    │ (pure py,   │   │ (profile ·    │            │
│  ┌──────────────┐  │  no LLM)    │   │  episodic ·   │            │
│  │ RAG Service  │  └─────────────┘   │  semantic)    │            │
│  │ hybrid       │                    └───────────────┘            │
│  │ retrieval ·  │  ┌─────────────────────────────────┐            │
│  │ evidence     │  │ Procrastinate Workers           │            │
│  │ grading      │  │ literature ingestion · PDF gen ·│            │
│  └──────────────┘  │ simulations · scheduled check-in│            │
└────────┬───────────┴────────────────┬────────────────┴────────────┘
         │                            │
┌────────▼────────────────────────────▼───────────┐   ┌────────────┐
│        PostgreSQL 16 (+ pgvector)               │   │ LLM / Embed│
│  relational schema · vector chunks · job queue  │   │ providers  │
│  · LangGraph checkpoints                        │   │ (BYOK)     │
└─────────────────────────────────────────────────┘   └────────────┘
```

### 4.1 The two coaching modes map to two execution patterns

- **Mode A — Program Generator:** a finite pipeline (onboarding → assessment → research →
  prescription → periodization → personalization → report). Runs the program-generation
  graph once, emits a program + PDF. Stateless after delivery (profile still saved).
- **Mode B — Long-Term AI Coach:** the same pipeline *plus* a persistent coach graph whose
  checkpointed state survives across conversations, a check-in protocol driven by time
  deltas, and the adaptation loop (§7.2). LangGraph's Postgres checkpointer stores thread
  state; the Athlete Memory Service stores durable facts.

### 4.2 LLMs narrate, the engine calculates

The **Sports Science Engine** is a deterministic, fully unit-tested Python package with no
LLM dependency:

- Performance predictors: Riegel/VDOT-style endurance models, CP/W′ (critical power),
  strength progression estimators (validated 1RM formulas: Epley, Brzycki), sprint/jump
  benchmark tables by age/sex/level.
- Training-load models: session-RPE load, ACWR (with its documented limitations), Banister
  impulse-response fitness–fatigue model for simulation.
- Feasibility scoring: required progression rate vs. empirical progression-rate
  distributions by training age → probability estimate with confidence interval.
- Periodization math: volume/intensity wave generation, taper kinetics, deload placement.

Agents call these as tools. An agent never invents a probability or a load number; it
requests one, then explains it. This is the single most important testability decision in
the system.

---

## 5. Data Model (PostgreSQL)

Core entities (columns abridged; all tables get `id UUID`, `created_at`, `updated_at`):

```
users                 (email, hashed_password, locale, role)
athletes              (user_id, display_name, birth_date, sex, height_cm, weight_kg,
                       body_composition JSONB, training_age_years, sport, discipline,
                       competition_level, locale, coaching_mode ENUM('generator','coach'))
injury_records        (athlete_id, area, description, occurred_on, status, restrictions JSONB)
medical_flags         (athlete_id, description, severity, requires_clearance BOOL)
equipment_profiles    (athlete_id, context ENUM('gym','home','outdoor'), items JSONB)
                      -- items validated against a catalog enum: barbell, rack, sled, skierg…
technology_profiles   (athlete_id, devices JSONB)  -- gps, hr_monitor, vbt, force_plates…
availability          (athlete_id, sessions_per_week, minutes_per_session,
                       weekly_pattern JSONB, constraints TEXT)

goals                 (athlete_id, statement, sport, metric, target_value, current_value,
                       deadline DATE, priority, status)
competitions          (athlete_id, name, date, priority ENUM('A','B','C'))

assessments           (athlete_id, goal_id, feasibility_score, success_probability,
                       probability_ci JSONB, risks JSONB, recommendations JSONB,
                       engine_inputs JSONB, agent_rationale TEXT)

programs              (athlete_id, goal_id, status, philosophy TEXT, start_date, end_date,
                       version INT, parent_version_id)   -- programs are versioned, never
                                                          -- mutated in place
macrocycles           (program_id, ordinal, focus, start_date, end_date)
mesocycles            (macrocycle_id, ordinal, type ENUM('accumulation','intensification',
                       'realization','deload','taper','maintenance'), objective)
microcycles           (mesocycle_id, week_number, planned_load, notes)
planned_sessions      (microcycle_id, day_offset, title, session_type, duration_min)
prescriptions         (planned_session_id, exercise_id, ordinal, sets, reps, load_scheme
                       JSONB {pct_1rm, rpe, velocity_target}, rest_sec, purpose TEXT,
                       evidence_level, citation_ids UUID[])

exercises             (canonical_name, aliases JSONB, patterns JSONB, equipment_required
                       JSONB, substitutions JSONB, coaching_cues JSONB, i18n JSONB)

completed_sessions    (athlete_id, planned_session_id NULL, performed_at, srpe INT,
                       duration_min, notes)
completed_sets        (completed_session_id, prescription_id NULL, exercise_id, set_number,
                       reps, load_kg, rpe, velocity_mps)
metrics               (athlete_id, kind ENUM('body_mass','hr_rest','hrv','1rm_estimate',
                       'time_trial','jump_height',…), value, unit, measured_at, source)
check_ins             (athlete_id, occurred_at, days_since_last, adherence_pct,
                       fatigue_score, pain_flags JSONB, responses JSONB, summary TEXT)
plan_adaptations      (program_id, check_in_id, trigger, diagnosis JSONB,
                       changes JSONB, from_version, to_version)

evidence_documents    (source ENUM('pubmed','semantic_scholar','cochrane','consensus',
                       'textbook'), external_id, doi, pmid, title, authors JSONB, year,
                       journal, study_type ENUM('systematic_review','meta_analysis','rct',
                       'cohort','cross_sectional','consensus','expert_opinion'),
                       population JSONB, methodology TEXT, conclusions TEXT,
                       evidence_level ENUM('strong','moderate','limited','expert'),
                       verified_at TIMESTAMPTZ)         -- verified against source API
evidence_chunks       (document_id, content, embedding VECTOR, tsv tsvector, section)
citations             (target_kind, target_id, document_id, claim TEXT, locale)

conversation_threads  (athlete_id, graph_name, langgraph_thread_id, last_message_at)
memory_facts          (athlete_id, kind ENUM('preference','constraint','history','feedback'),
                       content TEXT, embedding VECTOR, source_thread_id, superseded_by NULL)
reports               (athlete_id, program_id, mode ENUM('coach','expert'), locale,
                       storage_path, generated_at)
```

Design notes:

- **Programs are immutable versions.** Adaptation creates version N+1 with a
  `plan_adaptations` record explaining *why*. This gives a full audit trail of coaching
  decisions — essential for explainability and for training future improvements.
- **`citation_ids` are foreign keys**, not text. A prescription can only cite documents that
  exist in `evidence_documents` with a verified DOI/PMID. See §8.3.
- **Time management** needs no extra machinery: `last_message_at`, `check_ins.days_since_last`,
  and goal deadlines are computed from timestamps at graph-entry time and injected into
  agent context (current date, days since last interaction, weeks to objective).

---

## 6. Athlete Memory Architecture

Three complementary layers, one service (`memory/`):

1. **Structured profile (source of truth):** the relational tables above. Facts with schema
   (injuries, equipment, goals, metrics) always live here, never as free text.
2. **Episodic memory:** append-only event log per athlete (sessions completed, check-ins,
   adaptations, reports). Time-ordered; powers "your last update was 14 days ago" and
   trend analysis.
3. **Semantic memory (`memory_facts`):** distilled free-text facts extracted by the
   orchestrator at end of each conversation ("prefers morning sessions", "hates burpees",
   "travels for work every third week"). Embedded for retrieval; a fact can be superseded,
   never silently deleted.

**Context assembly at graph entry:** profile snapshot + active program summary + last N
episodic events + top-k semantic facts relevant to the current message + temporal header
(current date, days since last contact, weeks to deadline). This bounded, deterministic
context recipe keeps token use predictable and behavior reproducible.

---

## 7. Multi-Agent Design

All agents are **LangGraph nodes/subgraphs** in `agents/`, each with: a system prompt
(versioned template), a typed input/output schema (Pydantic), an allow-listed toolset,
and its own eval suite. One shared `CoachState` schema flows through graphs.

The **Orchestrator** is not an LLM router by default: for well-defined flows (onboarding,
generation, check-in) routing is explicit graph structure. LLM-based routing exists only
in the open chat entry point ("intent classification" node).

| # | Agent | Type | Tools | Notes |
|---|---|---|---|---|
| 1 | Assessment & Feasibility | LLM + engine | `engine.feasibility`, `engine.predictors`, memory read | Honest by construction: probability comes from the engine; the agent explains drivers, risks, realistic alternatives |
| 2 | Scientific Research | LLM + retrieval | `rag.search`, `ingestion.request(pubmed/semantic_scholar)` | Retrieval-only citations; can enqueue ingestion of new literature; outputs structured evidence summaries with grade |
| 3 | Exercise Prescription | LLM + catalog | `rag.search`, `exercises.lookup`, `engine.load_math` | Every prescription carries purpose + evidence level + citation FK |
| 4 | Periodization & Planning | LLM + engine | `engine.periodize`, competition calendar | Single peak, multi-peak, and in-season maintenance; emits macro/meso/micro structures |
| 5 | Personalization | LLM | equipment/availability read, `exercises.substitutions` | Diff between optimal and feasible plan; asks validation questions; records substitution impact |
| 6 | Nutrition & Recovery | LLM + retrieval | `rag.search`, profile read | Evidence-gated: supplement advice only above evidence threshold; hard scope limit — no medical nutrition therapy |
| 7 | Simulation | Engine-first | `engine.simulate` (Banister FFM, predictor models, Monte Carlo over adherence) | LLM only formats/explains the numeric output (probability, positive factors, limiting factors) |
| 8 | Progression & Adaptation | LLM + engine | episodic memory, `engine.trend_detect`, plan diff tools | Detects plateau/overreach/under-stimulus from data; proposes plan version N+1 with diagnosis |
| 9 | Report Generation | Deterministic + LLM prose | Typst templates, program/citation read | Coach mode (terse instructions) vs Expert mode (rationale + references); en/fr/es |

### 7.1 Program-generation flow (Mode A, also the bootstrap of Mode B)

```
onboarding (lang → mode → questionnaire)
  → Assessment (feasibility gate: if unrealistic, negotiate goal with user — interrupt)
  → Research (evidence pack for sport/goal)
  → Periodization (structure) ─┐
  → Prescription (sessions)  ──┤ share evidence pack
  → Personalization (constraint fit; interrupt for validation questions)
  → Simulation (expected outcome envelope)
  → Report (PDF, chosen mode + locale)
```

LangGraph **interrupts** implement every "ask the user" moment; state checkpoints mean the
flow resumes across sessions or crashes.

### 7.2 Check-in & adaptation loop (Mode B)

Entry trigger: user message OR scheduled prompt (Procrastinate cron per athlete cadence).
The graph computes time-delta context, asks the check-in question set (adherence, fatigue,
pain, performance, body mass, schedule changes), writes a `check_ins` row, then routes:
pain flags → safety protocol (see §10); poor adherence or plateau → Adaptation agent →
new program version → user approval interrupt → activation.
(Referenced as the "adaptation loop" from §4.1.)

---

## 8. RAG & Evidence System

### 8.1 Ingestion pipeline (worker jobs)

`fetch → parse → extract structured metadata → grade → chunk → embed → index`

- **Sources:** PubMed (E-utilities), Semantic Scholar API, Europe PMC, Cochrane; manually
  curated consensus statements (NSCA, ACSM, IOC) added via an admin CLI with mandatory
  metadata. The repo ships a **seed corpus manifest** (list of PMIDs/DOIs + grading), not
  copyrighted full texts — ingestion fetches abstracts/open-access content at deploy time.
- **Grading:** study type is extracted from metadata (publication type tags) and mapped to
  the evidence hierarchy; an LLM pass proposes `evidence_level`, a rules layer enforces
  ceilings (e.g., a single cross-sectional study can never be graded `strong`). Human
  override supported via admin CLI; overrides are logged.
- **Verification:** a document is only citable after its DOI/PMID has been resolved against
  the source API (`verified_at` set). Unverifiable entries are quarantined.

### 8.2 Retrieval

Hybrid search: pgvector cosine + Postgres full-text (`tsv`), reciprocal-rank fusion,
optional cross-encoder re-rank. Filters: study type, population (age/sex/level/sport),
recency. Queries in FR/ES are searched with multilingual embeddings (bge-m3/voyage handle
cross-lingual retrieval against the English corpus) — no translation step needed.

### 8.3 Anti-fabrication guarantee (architectural, not prompt-based)

1. Agents cite by returning **chunk IDs** from retrieval results — never free-text refs.
2. The rendering layer resolves IDs → `evidence_documents` rows → formatted citations.
3. An output guard scans generated prose for DOI/PMID-shaped strings not present in the
   citation set and blocks/regenerates the response.
4. Confidence stars are computed from the cited documents' `evidence_level` distribution
   (`strong`→★★★★★, `moderate`→★★★☆☆, `limited`→★★☆☆☆, `expert`→★☆☆☆☆), displayed on
   every recommendation; prose degrades
   honestly when evidence is thin ("limited evidence; based on expert recommendation").

---

## 9. Multilingual Design

- **Stored preference:** `users.locale` / `athletes.locale` (en default, fr, es) set at
  step 1 of onboarding, changeable anytime.
- **UI:** next-intl message catalogs (`apps/web/messages/{en,fr,es}.json`); no hardcoded
  strings (CI check).
- **AI output:** prompt templates receive `locale`; system prompts mandate response
  language. Templates themselves are English with locale-specific style notes — LLMs
  generate fluent fr/es directly; separate prompt translations are not maintained (single
  source of truth, tested per-locale in evals).
- **Domain data:** `exercises.i18n` JSONB holds name/cues per locale. Evidence stays in
  English; agent summaries of evidence are generated in the user's locale.
- **Reports:** Typst templates parameterized by locale; static labels from the same
  catalogs as the web app.

---

## 10. Safety & Scope Boundaries

- **Not medical advice.** Persistent disclaimer in UI and reports; nutrition agent excludes
  clinical populations and medical nutrition therapy.
- **Red-flag protocol:** pain/injury mentions route to a safety node — stop loading advice
  on the affected pattern, recommend qualified professional, log a `medical_flags` entry,
  and adapt the plan around (not through) the issue.
- **Feasibility honesty:** the assessment agent must present engine-computed probability
  even when discouraging; templates forbid motivational inflation of numbers.
- **Minor athletes:** age < 16 → conservative prescription rules in the engine (no
  supra-maximal work, technique-first), flagged in reports.
- **PII:** self-hosted by design; secrets via env; athlete data export/delete endpoints
  (GDPR-friendly) from MVP.

---

## 11. API Surface (v1, prefix `/api/v1`)

```
POST   /auth/register | /auth/login | /auth/refresh
GET    /me                          PATCH /me            (locale, settings)
POST   /athletes                    GET/PATCH /athletes/{id}
PUT    /athletes/{id}/equipment     PUT /athletes/{id}/availability
POST   /athletes/{id}/injuries      POST /athletes/{id}/metrics
POST   /goals                       GET/PATCH /goals/{id}
POST   /assessments                 (runs feasibility flow, may 202 + poll)
POST   /programs/generate           (Mode A pipeline; SSE progress)
GET    /programs/{id}               GET /programs/{id}/versions
GET    /programs/{id}/calendar      (planned sessions, week view)
POST   /sessions/{planned_id}/log   (completed session + sets)
POST   /chat/threads                POST /chat/threads/{id}/messages   (SSE stream)
POST   /check-ins                   (Mode B; graph-driven)
POST   /reports                     GET /reports/{id}/download
GET    /evidence/search             GET /evidence/{id}
GET    /exercises                   GET /exercises/{id}
GET    /export/me                   DELETE /me            (GDPR)
```

SSE streams carry typed events: `token`, `agent_started`, `tool_call`, `interrupt`
(question for the user), `state_update`, `done` — the frontend renders agent activity
transparently (explainable AI as UX).

---

## 12. Repository Structure (monorepo)

```
performance-agent/
├── apps/
│   ├── api/                          # Python 3.13, uv project
│   │   ├── src/performance_agent/
│   │   │   ├── agents/               # one package per agent (9) + orchestrator/
│   │   │   ├── engine/               # deterministic sports science (no LLM imports — enforced)
│   │   │   ├── rag/                  # ingestion/, retrieval/, grading/
│   │   │   ├── memory/               # profile, episodic, semantic services
│   │   │   ├── domain/               # SQLAlchemy models, Pydantic schemas
│   │   │   ├── api/                  # routers, deps, SSE
│   │   │   ├── llm/                  # provider adapter (anthropic, openai, ollama)
│   │   │   ├── prompts/              # versioned templates (see below)
│   │   │   ├── reports/              # typst templates + builder
│   │   │   ├── workers/              # procrastinate tasks
│   │   │   ├── i18n/                 # backend catalogs (report labels, emails)
│   │   │   └── core/                 # config, auth, logging, telemetry
│   │   ├── tests/                    # mirrors src; + evals/ (see §14)
│   │   ├── alembic/
│   │   └── pyproject.toml
│   └── web/                          # Next.js 15, pnpm
│       ├── src/app/[locale]/…        # onboarding, chat, calendar, dashboard, reports
│       ├── src/lib/api/              # generated OpenAPI client
│       ├── messages/{en,fr,es}.json
│       └── package.json
├── data/
│   ├── seed_corpus/manifest.yaml     # PMIDs/DOIs + grades, no copyrighted text
│   └── exercises/catalog.yaml        # canonical exercise catalog + i18n
├── docs/
│   ├── architecture/  adr/  agents/  api/  self-hosting/  contributing/
│   └── superpowers/specs/            # design docs (this file)
├── deploy/
│   ├── docker-compose.yml            # postgres+pgvector, api, worker, web
│   └── Dockerfile.api  Dockerfile.web
├── .github/workflows/                # ci.yml, evals.yml, release.yml (SHA-pinned)
├── .pre-commit-config.yaml           # prek: ruff, ty, oxlint, shellcheck, zizmor
└── README.md  LICENSE(Apache-2.0)  CONTRIBUTING.md  CODE_OF_CONDUCT.md
```

**Prompt template format** (`prompts/<agent>/<name>.md`): markdown body + YAML frontmatter
(`version`, `schema_in`, `schema_out`, `locales_tested`, `changelog`). Prompts are code:
reviewed in PRs, covered by evals, breaking changes bump version.

---

## 13. Explainability

- Every agent step is traced (OpenTelemetry + Langfuse): inputs, retrieved evidence,
  engine calls, output. A program can answer "why is this session here?" by walking
  prescription → citations + engine inputs + agent rationale (stored, not regenerated).
- Reports in **Expert mode** render this chain; **Coach mode** hides it but the data
  exists — the mode is a view, not a data difference.

---

## 14. Testing & Evaluation Strategy

1. **Engine (highest rigor):** pure pytest, property-based tests (Hypothesis) on
   predictors/load models, golden values from published papers (e.g., known VDOT tables).
   Mutation testing via `mutmut` on `engine/`.
2. **API/domain:** pytest + async test client against ephemeral Postgres (testcontainers);
   behavior-level tests (log a session → program stats update), edge/error paths required.
3. **RAG:** retrieval quality evals — curated query→relevant-document sets per sport;
   recall@k tracked in CI; grading-rules unit tests (ceiling enforcement).
4. **Agents (LLM evals, `tests/evals/`):** golden scenario suites per agent — e.g.,
   Assessment must refuse the "55→35 min 10K in 3 months" goal; Prescription outputs must
   validate against schema, cite only retrieved IDs, and respect equipment constraints.
   Scored by rubric-based LLM-as-judge + deterministic checks (schema, citation validity,
   locale). Run nightly + on prompt changes (`evals.yml`); regression gates on merges
   touching `prompts/` or `agents/`.
5. **Anti-fabrication guard:** adversarial test set that prompts agents toward inventing
   references; guard must catch 100% of injected fake DOIs.
6. **Frontend:** vitest + Playwright smoke on onboarding/chat/calendar; i18n key coverage
   check (no missing/unused keys).
7. **CI order:** lint (ruff/oxlint) → types (ty/tsc) → unit → integration → build →
   evals (nightly/label-gated to control cost).

---

## 15. Deployment

- **Self-host (primary):** `docker compose up` — postgres, api, worker, web. `.env` for
  LLM keys. First-run wizard checks provider connectivity and ingests the seed corpus.
- **Images:** GHCR, multi-arch, published on tagged releases (semver) via GitHub Actions.
- **Scaling path:** api and worker are separate containers from day one; Postgres managed
  or self-hosted; extract ingestion worker first if needed.

---

## 16. Roadmap

### MVP (v0.1–v0.4) — "the honest program generator"

Mode A end-to-end for **two sport verticals** (running: 5K–marathon; strength: barbell
sports) to prove depth before breadth: onboarding (3 steps, 3 locales — the mode-choice
step captures and stores Mode B interest but presents it as "coming in V2"), athlete
profile +
equipment, Assessment with engine-backed feasibility, seed evidence corpus (~200 curated
documents) + retrieval, Prescription + Periodization (single objective), Personalization,
Typst PDF (coach/expert modes), session logging, docker-compose self-host, auth,
export/delete. **Explicitly out:** Mode B, simulation Monte Carlo, live literature
ingestion, wearables.

### V2 — "the coach" (Mode B)

Persistent coach graph + check-in protocol + time-delta awareness; Adaptation agent with
program versioning; Simulation engine (Banister + Monte Carlo adherence); Nutrition &
Recovery agent; progress dashboards; scheduled check-ins; live PubMed/Semantic Scholar
ingestion with grading pipeline; multi-peak periodization; more sports (Hyrox, football,
tennis, tactical/military tests); CSV import (Garmin/Strava export files).

### V3 — "the professional platform"

Coach-facing multi-athlete dashboard (human coach supervising AI); teams/organizations;
device integrations (VBT, force plates, live wearable APIs); readiness modeling (HRV
trends); plugin system for community sport modules + exercise packs; PWA/mobile;
community evidence-curation workflow (moderated grading contributions); optional
federation-grade reporting.

---

## 17. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| LLM cost for self-hosters | BYOK + local model support; engine-first design minimizes LLM calls; context recipes bounded |
| Evidence corpus licensing | Store abstracts/metadata + open-access only; manifest-based seeding; never redistribute paywalled full text |
| Scope explosion (every sport at once) | Vertical-first MVP (running + strength); sport modules as plugins later |
| LLM judge drift in evals | Deterministic checks first; judge rubrics versioned; golden outputs pinned |
| Liability (injury claims) | Disclaimers, red-flag protocol, conservative defaults, no medical claims — reviewed in CONTRIBUTING |

Decisions confirmed by the maintainer (2026-07-10):

1. License: **Apache-2.0**.
2. MVP verticals: **running (5K–marathon) + barbell strength**.

Remaining open question: default hosted demo instance (costs money, great for adoption) —
deferred, later decision.
