# PerformanceAgent — Technical Architecture Blueprint (v2, agent-native)

**Date:** 2026-07-10 (v2 — agent-native pivot, same day)
**Status:** Approved direction; v2 pending final review
**Supersedes:** v1 (web platform architecture) — see git history of this file. The v1
product vision, evidence philosophy, safety rules, and MVP verticals are unchanged;
the delivery architecture is replaced.

---

## 1. Executive Summary

PerformanceAgent is an open-source, evidence-based AI Strength & Conditioning coach that
runs **inside the user's existing AI coding agent** — Claude Code, Gemini CLI, Codex —
using their existing LLM subscription. There is no backend, no web app, no API key to
provision, nothing to host.

The product is three things, installed together:

1. **An MCP server** exposing deterministic tools: the sports-science engine
   (feasibility, predictions, loads, periodization — built, 93 tests), a graded
   scientific-evidence corpus with search and citation validation, file-based athlete
   memory, and a Typst PDF report renderer.
2. **A set of coaching skills** (structured protocol documents) that turn the host
   agent into a professional S&C coach: onboarding, assessment, program generation,
   personalization, check-ins, adaptation.
3. **A transparent athlete data directory** (plain markdown/YAML files) holding the
   profile, goals, program versions, session logs, and check-in history — readable,
   diffable, portable, syncable by the user.

The host agent (Claude/Gemini/Codex) does what LLMs do best — converse, reason, adapt,
explain — and is architecturally prevented from doing what they do worst: it cannot
invent a training number (numbers come from engine tools) and it cannot fabricate a
citation (citations must resolve against the local evidence corpus, enforced at report
rendering).

**Core stance unchanged from v1: LLMs narrate, deterministic code calculates.**

---

## 2. Why agent-native (decision record)

The v1 blueprint designed a self-hosted web platform (FastAPI + LangGraph + Next.js +
Postgres) with bring-your-own-key LLM access. The maintainer redirected: all interaction
must flow through existing agent CLIs and the user's LLM subscription — no per-call API
billing, no separate infrastructure.

Consequences:

| v1 (replaced) | v2 (agent-native) |
|---|---|
| FastAPI backend + REST/SSE | MCP server (stdio), tools called by the host agent |
| LangGraph multi-agent graphs | Coaching skills (protocol markdown) executed by the host agent |
| Next.js web app + auth | The agent CLI *is* the interface; no auth needed (local files) |
| PostgreSQL + pgvector | SQLite (FTS5) for evidence; plain files for athlete data |
| BYOK LLM adapter | The host agent brings its own model/subscription |
| Procrastinate workers | None — everything is synchronous tool calls |
| Langfuse tracing | The host CLI's own transcript is the trace |

What survives intact: the deterministic engine (Plan 01, done), the evidence-first
philosophy and grading hierarchy, anti-fabrication as an architectural guarantee, the
honest feasibility verdicts, long-term athlete memory, multilingual coaching (en/fr/es),
Typst reports, the MVP verticals (running 5K–marathon + barbell strength), and all
safety rules (§9).

Trade-off accepted: the MVP targets users comfortable installing a CLI tool. A web
front-end for non-technical athletes is explicitly out of scope until the agent-native
core proves itself (it would reuse the same MCP server).

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│        Host agent CLI (Claude Code / Gemini CLI / Codex)     │
│        — the conversation, reasoning, and orchestration —    │
│                                                              │
│   Coaching skills (installed protocol docs):                 │
│   onboarding · assessment · program-generation ·             │
│   personalization · check-in · adaptation · nutrition ·      │
│   reporting                                                  │
└───────────────┬──────────────────────────────────────────────┘
                │ MCP (stdio)
┌───────────────▼──────────────────────────────────────────────┐
│                 performance-agent MCP server (Python)        │
│                                                              │
│  Engine tools (deterministic, built)                         │
│   assess_endurance_goal · predict_race_time · estimate_1rm  │
│   prescribe_load · session_load · weekly_loads · acwr ·      │
│   build_periodization_waves                                  │
│                                                              │
│  Evidence tools                                              │
│   search_evidence(query, filters) → graded chunks + IDs      │
│   get_citation(id) → formatted reference (DOI/PMID)          │
│                                                              │
│  Memory tools                                                │
│   read_athlete() · update_profile(...) · log_session(...) ·  │
│   log_checkin(...) · save_program(...) · get_time_context()  │
│                                                              │
│  Report tool                                                 │
│   render_report(program_id, mode, locale) → PDF (Typst)      │
│   — validates every citation ID against the corpus; any      │
│     unknown reference aborts the render (anti-fabrication)   │
└───────┬──────────────────────────┬───────────────────────────┘
        │                          │
┌───────▼───────────┐   ┌──────────▼──────────────────────────┐
│ evidence.db       │   │ athlete data directory (user-owned) │
│ SQLite FTS5,      │   │ ~/.performance-agent/ or ./athlete/ │
│ seeded from a     │   │  profile.yaml · goals.yaml ·        │
│ curated manifest  │   │  programs/program-v3.md ·           │
│ (~200 graded      │   │  sessions.jsonl · checkins.jsonl ·  │
│ studies, MVP)     │   │  reports/*.pdf                      │
└───────────────────┘   └─────────────────────────────────────┘
```

### 3.1 Division of labour

- **Skills** own the coaching *process*: what to ask during onboarding, when to call
  which tool, how to negotiate an unrealistic goal, how to structure a check-in after
  N days away, how to present evidence grades, which language to respond in.
- **MCP tools** own every *fact*: numbers, dates, citations, athlete history. A skill
  never states a probability or a load; it calls a tool and explains the result.
- **The athlete directory** owns all *state*. The MCP server is stateless between
  calls; everything durable is a file the user can read and version.

### 3.2 The nine v1 agents map to skills + tools

| v1 agent | v2 realization |
|---|---|
| 1 Assessment & Feasibility | skill `assessment` + `assess_endurance_goal` tool |
| 2 Scientific Research | skill guidance + `search_evidence`/`get_citation` tools |
| 3 Exercise Prescription | skill `program-generation` + engine load tools + exercise catalog |
| 4 Periodization & Planning | same skill + `build_periodization_waves` tool |
| 5 Personalization | skill `personalization` (equipment/constraints negotiation) |
| 6 Nutrition & Recovery | skill `nutrition-recovery` (V2), evidence-gated |
| 7 Simulation | engine tools (Banister/Monte Carlo in V2) |
| 8 Progression & Adaptation | skill `check-in` + memory tools + engine trend math |
| 9 Report Generation | `render_report` tool (Typst; coach/expert modes, i18n) |

---

## 4. Athlete Memory (file-based)

Directory resolution: `PERFORMANCE_AGENT_HOME` env var → else `./athlete/` if present
(project-local coaching folder) → else `~/.performance-agent/`.

```
athlete/
├── profile.yaml        # identity, locale, biometrics, training age, injuries,
│                       # equipment, availability — schema-validated by the server
├── goals.yaml          # goals with target/deadline/priority/status
├── programs/
│   ├── program-v1.md   # human-readable program, YAML frontmatter for structure
│   └── program-v2.md   # adaptations create new versions + a diagnosis note (§ audit)
├── sessions.jsonl      # one completed session per line (sRPE, sets, notes)
├── checkins.jsonl      # check-in records (adherence, fatigue, pain flags)
└── reports/            # rendered PDFs
```

- **Structured facts live in files with schemas**; the server validates on write and
  returns actionable errors the agent can relay.
- **`get_time_context()`** returns current date, days since last interaction, days
  since last logged session, and weeks to each goal deadline — powering "your last
  update was 14 days ago" without trusting the LLM's clock.
- **Program versioning**: `save_program` never overwrites; adaptation writes vN+1 with
  a required `reason` field. Full audit trail of coaching decisions, as in v1.
- Free-text preferences ("hates burpees") live in a `notes` section of profile.yaml —
  the host agent's own memory features complement this but the athlete directory is
  the portable source of truth.

---

## 5. Evidence System

- **Corpus**: a curated seed manifest (`data/seed_corpus/manifest.yaml`) of ~200 graded
  studies for the two MVP verticals — title, authors, year, study type, population,
  conclusions summary, evidence level, DOI/PMID. Grading ceilings enforced by rules
  (a cross-sectional study can never be `strong`), as in v1.
- **Storage**: single-file SQLite with FTS5 (BM25) full-text search. No embeddings in
  the MVP — no API key may be required for any core function. The host agent
  compensates by reformulating queries (it is good at that). Cross-lingual: corpus is
  English; skills instruct the agent to search in English and explain in the athlete's
  language.
- **Anti-fabrication (unchanged guarantee, new enforcement point)**: skills mandate
  citing only IDs returned by `search_evidence`; `render_report` hard-fails on any
  citation ID absent from the corpus, and a lint tool (`check_citations(text)`) lets
  the agent self-verify DOI/PMID-shaped strings in prose before presenting them.
- **Confidence stars** computed by the server from cited documents' grades
  (★★★★★ strong … ★☆☆☆☆ expert), never by the LLM.
- Live PubMed/Semantic Scholar ingestion becomes a V2 maintainer pipeline that ships
  corpus updates as versioned releases users pull — user installs never call
  external APIs.

---

## 6. Coaching Skills (the protocol layer)

Skills are markdown protocol documents, versioned in-repo, installable as a Claude Code
plugin (and mirrored as Gemini/Codex-compatible prompt packs from the same source).

- `coach` (entry): language selection (en/fr/es, stored), Mode A (one-shot program) vs
  Mode B (ongoing coach), routing to other skills.
- `onboarding`: the questionnaire protocol (personal, sport, goal, environment,
  equipment, availability) → writes profile.yaml/goals.yaml via tools.
- `assessment`: run `assess_endurance_goal` (or strength equivalents), present the
  verdict with drivers honestly, negotiate realistic alternatives on low probability.
- `program-generation`: evidence pack via `search_evidence` → structure via
  `build_periodization_waves` → sessions with purpose + evidence level per
  prescription → `save_program`.
- `personalization`: constraint fit, exercise substitutions with expected-impact notes.
- `check-in` (Mode B): `get_time_context` → adherence/fatigue/pain protocol →
  `log_checkin` → route to adaptation when triggers fire; pain → safety protocol (§9).
- `adaptation` (Mode B): diagnose (data via memory tools + engine trend math), propose
  program vN+1 with reasons, require athlete confirmation before `save_program`.
- `report`: gather, choose coach/expert mode, call `render_report`.

Skill evals (maintainer CI): golden-scenario suites — the canonical "55→35 in 12
weeks" must produce a refusal with the engine's probability; prescriptions must carry
valid citation IDs; locale must be respected. Deterministic checks first (schema,
citation validity), rubric-based LLM judging where needed. CI uses a maintainer key;
end users never need one.

---

## 7. Technology Stack (v2)

| Layer | Choice |
|---|---|
| Language/runtime | Python 3.13, `uv` (unchanged) |
| MCP server | official `mcp` Python SDK (FastMCP), stdio transport |
| Engine | `performance_agent.engine` (built; unchanged) |
| Evidence store | SQLite + FTS5 (stdlib `sqlite3`) |
| Athlete data | YAML (schema-validated: Pydantic v2) + JSONL + markdown |
| PDF reports | Typst CLI (bundled check at first run; graceful message if absent) |
| Skills packaging | Claude Code plugin structure; generated prompt packs for Gemini/Codex |
| Distribution | PyPI package, run via `uvx performance-agent` / `claude mcp add` |
| Tooling/CI | uv, ruff, ty, pytest, Hypothesis, prek, SHA-pinned Actions (unchanged) |

Dropped: FastAPI, Next.js, LangGraph, Postgres/pgvector, Procrastinate, fastapi-users,
Langfuse, embeddings.

---

## 8. Repository Structure (v2)

```
performance-agent/
├── apps/api/ → becomes the single Python package (rename path in Plan 02):
│   src/performance_agent/
│   ├── engine/            # built (Plan 01)
│   ├── server/            # MCP server: tool definitions, entrypoint
│   ├── memory/            # athlete-dir schemas, readers/writers, time context
│   ├── evidence/          # corpus build, FTS5 search, grading rules, citation check
│   └── reports/           # typst templates (en/fr/es) + renderer
├── skills/                # coaching protocol docs (plugin source of truth)
├── data/seed_corpus/manifest.yaml
├── data/exercises/catalog.yaml
├── docs/                  # specs, plans, self-hosting → "installing" docs
└── tests/                 # engine (built) + server + memory + evidence + skill evals
```

## 9. Safety & Scope (unchanged from v1)

Not medical advice; red-flag protocol on pain/injury (stop loading advice on the
affected pattern, recommend a professional, record a flag, adapt around); honest
feasibility always presented with drivers; conservative rules for minors; all data
local by construction (file-based, no server) — GDPR concerns collapse to "it's your
directory".

## 10. Revised Plan Sequence

1. ✅ **Foundation & sports science engine** (done — fully reused)
2. **MCP server core** — FastMCP server exposing the engine as tools; packaging
   (uvx entrypoint); install docs for Claude Code/Gemini/Codex; integration tests
   via MCP client harness
3. **Athlete memory** — file schemas, memory tools, time context, program versioning
4. **Evidence corpus** — seed manifest (~200 graded studies), SQLite FTS5 build +
   search/citation tools, anti-fabrication check tool
5. **Coaching skills** — the protocol layer (onboarding → assessment → generation →
   personalization → check-in/adaptation), plugin packaging, eval harness
6. **Reports** — Typst templates (coach/expert × en/fr/es), render_report tool
7. **Distribution & docs** — PyPI release, README/installing polish, corpus-update
   release pipeline

V2 (post-MVP): Banister/Monte Carlo simulation tools, nutrition skill, live literature
ingestion pipeline, more sports. V3: optional web front-end reusing the same MCP server.
