# Living Evidence & Weekly Follow-up — Design

Date: 2026-07-17
Status: approved (design review with owner)
Target release: v0.8.0

## 1. Overview

Four features that turn the research pipeline from an intake ritual into a
living loop, and give the coach a weekly follow-up rhythm:

- **A. Athlete documentation folder** — a `documentation/` directory in the
  athlete's data folder where they drop documents (published studies, physio
  reports, lab results, past programs). The agent detects new files
  automatically and routes each into one of two lanes.
- **B. Research during the program** — targeted "mini-waves" of the
  deep-research protocol, triggered by adaptation events, mesocycle
  boundaries, and dropped documents. Skills-only; no new server code.
- **C. Science in the HTML deliverable** — the offline program HTML gains an
  advice banner (nutrition/supplements), a "why this program" section, `[n]`
  citation markers on exercise blocks, and a starred bibliography.
- **D. Weekly follow-up** — a `next-week-loads` skill backed by a
  deterministic engine tool that computes next week's loads from the logged
  week, and a `program-watch` skill that audits the running program per
  exercise and routes substitution candidates to `program-adaptation`.

Explicitly excluded by owner decision: any photo/video check-in (privacy).
Supplement guidance is advice, never prescription.

## 2. Decisions taken with the owner

| Question | Decision |
|---|---|
| What science shows in the HTML | Vulgarized header (advice + rationale) + `[n]` markers on blocks + starred bibliography in footer |
| Status of dropped documents | Two lanes: verified locator → evidence corpus; everything else → athlete context, never cited as science |
| When documents are read | Automatic: deep-research always scans first; coach/check-in entry points detect new files |
| Documents architecture | Dedicated MCP tools for inventory + registry; the client reads files (native PDF reading) |
| Research during the program | In scope here (owner priority), via mini-waves |
| Weekly loads + program audit | Two separate skills, each with its own cadence |
| Next-week load computation | Structured progression rule on blocks + deterministic engine tool |

## 3. The athlete documentation folder

### 3.1 Creation

`documentation/` lives in the athlete data directory, next to `research/` and
`programs/`. It is created (with a short bilingual FR/EN `README.md`
explaining what to drop and what happens to it) by two paths:

- `write_profile` — so onboarding creates it;
- the first call to `list_athlete_documents` — so existing athletes get it
  without re-onboarding.

`resolve_athlete_dir()` stays pure (never creates anything).

### 3.2 The registry

`documentation/index.yaml`, validated by a Pydantic `DocumentRecord` model,
written atomically (same pattern as `personal_corpus`). One record per
processed file:

```yaml
documents:
  - filename: "creatine-meta.pdf"
    sha256: "…"
    size_bytes: 812345
    first_seen: "2026-07-17"
    processed_on: "2026-07-18"
    status: processed        # processed | unreadable
    lane: evidence           # evidence | context | null (unreadable)
    summary: "Meta-analysis, creatine 3-5 g/day, strength outcomes."
    key_points: ["…"]
    evidence_ids: ["creatine-kreider-2017"]
```

Only `processed` and `unreadable` are stored. `new`, `modified` and `removed`
are **derived at scan time** (file present but not in registry; hash differs
from registry; registry entry without file). The registry file itself and
`README.md` are excluded from scans. A deleted or corrupt registry is
rebuilt empty: files simply show up as `new` again; re-processing an
already-saved study fails cleanly on corpus id uniqueness.

### 3.3 New MCP tools

**`list_athlete_documents()`** — creates folder + README if missing, scans,
compares hashes against the registry, returns
`{path, new: […], modified: […], processed: […], removed: […], unreadable: […]}`
where each item carries absolute path, size and (for processed) the stored
summary — so the agent knows what it already knows without re-reading.
Never writes the registry.

**`mark_document_processed(filename, lane, summary?, key_points?, evidence_ids?)`**
— records the outcome. Validations: file must exist in `documentation/`,
`lane ∈ {evidence, context, unreadable}`, `summary` required unless
unreadable, every `evidence_id` must exist in the loaded corpus (no phantom
traceability).

Reading the documents themselves is the **client's** job (Claude reads PDFs
natively, better than any server-side extraction). The server hands out
paths, never file content.

### 3.4 The two lanes

Hard rule, preserving the zero-fabricated-citation guarantee:

- **Evidence lane** — only if a DOI/PMID/ISBN found in the document
  **resolves via `verify_reference`**. Then the existing pipeline applies
  unchanged: `save_evidence` re-verifies locator + title match. Bonus: the
  agent read the full text, so saved `conclusions` can be richer than the
  abstract-only live-search entries.
- **Context lane** — everything else (physio reports, lab results, past
  programs, blog articles, unverifiable PDFs). Summary + key points persist
  in the registry and inform personalization (needs-analysis, planning,
  adaptation), but are **never rendered as scientific citations** in any
  deliverable.

### 3.5 Skill integration

- `deep-research` — new mandatory step 0: process the documentation folder
  before any online search; dropped documents shape the facets.
- `performance-coach` and `training-checkin` — call `list_athlete_documents`
  in their opening ritual (alongside `list_due_actions`) and handle
  new/modified files.
- `athlete-onboarding` — tells the athlete the folder exists and what to
  drop in it.

## 4. Research during the program — mini-waves

No new server code: `search_evidence_live` filters (`year_from`,
`publication_types`) and the immutable, reason-carrying dossier versioning
already support this. Skills change only.

### 4.1 The mini-wave

A reduced deep-research pass scoped to **one question**: corpus first, then
2-3 live queries in English + the athlete's locale (+1 language if the facet
is thin), same verification and save rules, result folded into the dossier
as **v+1 with `reason` = the trigger** and a "what changed vs v{N}" section.
Minutes, not the full multi-facet protocol.

### 4.2 Triggers

1. **Substantive adaptation trigger** (confirmed plateau, recurring pain,
   calendar or method change). Urgency rule: **adapt first, research
   second** — tonight's session never waits for literature; the mini-wave
   informs the program's next version, not the immediate fix.
   `program-adaptation` gains `read_research_dossier` and
   `save_research_dossier` in its tool list plus the mini-wave protocol.
2. **Mesocycle boundary — incremental watch**: replay the dossier facets'
   queries with `year_from` = the current dossier's year; thin facets first.
   Something new → dossier v+1; nothing → no new version. Carried by
   `training-checkin` (it sees calendar and program).
3. **A drop or a question**: a new document touching a program facet
   (§3.5), or an explicit athlete question ("I read that…").

### 4.3 Safety loop

A mini-wave that contradicts the active program routes to
`program-adaptation`, which proposes the sourced change to the athlete —
never a silent program edit. Quality gate unchanged: `program-review` and
the citation locks at every delivery.

## 5. Weekly follow-up

### 5.1 Structured progression rules

`ExerciseBlock` gains an optional `progression: ProgressionRule | None`.
The existing free-text `progression_rule` stays (human display, old
programs); when the structured rule is present it is the **source of
computation** and the text is its rendering (written by
`program-optimization`, coherence checked by `program-review`).

```python
class ProgressionRule(BaseModel):
    kind: Literal["double", "linear_load", "rir_target", "from_pct", "none"]
    rep_min: int | None = None          # double
    rep_max: int | None = None          # double
    increment_kg: float | None = None   # double, linear_load
    target_rir: float | None = None     # rir_target
    adjust_pct_per_rir: float = 0.03    # rir_target
    rounding_kg: float = 2.5
```

Per-kind validators enforce required params. Semantics:

- `double` — all logged sets reached `rep_max` → next = load +
  `increment_kg` (aim back at `rep_min`); otherwise same load, aim for more
  reps.
- `linear_load` — all sets hit prescribed reps → +`increment_kg`; any
  failed set → hold (no auto-deload in v1; repeated failure is
  `program-watch`'s signal).
- `rir_target` — next = load × (1 + `adjust_pct_per_rir` × (mean logged RIR
  − `target_rir`)), rounded to `rounding_kg`.
- `from_pct` — for blocks prescribed in `pct_1rm` (waves, top-set plans):
  e1RM = best logged set of that exercise in the last 14 days
  (engine Epley), falling back to `lift_inventory`; next = next week's
  planned pct × e1RM.
- `none` — no numeric suggestion ("per plan"): endurance pace blocks,
  technique work.

### 5.2 Engine tool `suggest_next_week_loads()`

Deterministic, zero LLM in the loop. Reads the active program and the
logged sessions (window `days_back`, default 7) from the store, matches
logs to program blocks by exercise identity (`exercise_id`, falling back to
name). The program week whose sessions match the most logged sessions in
the window is the current week (`week_matched`); suggestions target each
matched block's **next occurrence** — the same block when the program
repeats its week, the following week's block (e.g. its planned pct for
`from_pct`) when weeks differ. Applies each block's rule and returns in
one call:

```json
{
  "week_matched": 3,
  "blocks": [{
    "session": "A", "exercise": "Bench press", "rule_kind": "double",
    "prescribed": {"sets": 4, "reps": "8-12", "load_kg": 80},
    "actual": {"sets_completed": 4, "reps": [12,12,12,12], "mean_rir": 1.5},
    "next": {"load_kg": 82.5},
    "rationale": "double progression: top of range on all sets — +2.5 kg",
    "flags": []
  }],
  "unmatched_logs": ["Face pull (not in program)"],
  "flags": ["no_rule: Nordic curl"]
}
```

Degraded cases are flags, never guesses: `no_rule` (unstructured block —
the skill handles it manually), `unmatched` (block with no logged session),
`failed_sets` (→ hold). A successful run records its date in a one-line
state file so diligence can see the review happened.

### 5.3 Skill `next-week-loads`

Thin. Triggered at the end of a training week (routed by
`performance-coach`; new diligence action "training week finished without a
loads review", read from the state file). Calls the tool, presents the
table, discusses flagged blocks with the athlete, answers "why" from the
rationale. **Versions nothing** — it concretizes next week, it does not
modify the program.

### 5.4 Skill `program-watch`

The running program's auditor. Data only, **per exercise**: e1RM trajectory
over the mesocycle (endurance: pace/HR via `compare_prescribed_actual`),
per-exercise adherence (a systematically skipped or cut-short movement is a
signal), recurring pain linked to a movement (`pain_flags` + session
notes), chronic prescribed-vs-actual gaps, load monotony per pattern.

Verdict per exercise: **keep / watch / substitution candidate** (reason,
replacements proposed via `score_exercises`, citation when one exists).
It **never edits anything**: substitution candidates route to
`program-adaptation` (diagnosis, versioning, `program-review` gate all
unchanged).

Cadence: every 2 weeks + at each mesocycle boundary (where it pairs with
the incremental watch of §4.2: watch says *what to watch*, the mini-wave
says *what the science says*) + on demand. Designed to run as a
**subagent** launched by `performance-coach`/`training-checkin`, returning
a short report.

### 5.5 `save_watch_report` + diligence

`save_watch_report(markdown_body)` persists the report as a versioned doc
(`watch/report-vN.md`, generic `_save_versioned_doc` helper). This gives an
audit history and a timestamp diligence can read. New diligence actions:

- `weekly_loads_review_due` — logged sessions this week and no review
  recorded for ≥6 days.
- `program_watch_due` — active program and no watch report for ≥14 days.

## 6. Science in the HTML deliverable

### 6.1 Model

`ProgramPlan` gains two optional lists:

```python
class Guidance(BaseModel):
    text: str            # 1..300 chars
    cite: str | None     # corpus id, same semantics as ExerciseBlock.cite

advice: list[Guidance] = []      # nutrition / supplement / recovery advice
rationale: list[Guidance] = []   # "why this program" key messages
```

Filled by `program-optimization` (supplement content sourced from the
dossier/corpus; `nutrition-planning` provides the frame). Honesty rule
identical to blocks: no corpus backing → phrased as coaching judgment,
never a fake cite. `program-review` checks these sections like the rest.

### 6.2 Rendering

- **HTML** (`render_html.py`): header banner (💊 advice, then 🔬 rationale,
  per the validated mockup), `[n]` markers on exercise blocks from the
  existing `cite` field, starred bibliography in the footer
  (`format_citation` + `STARS`, DOI as a clickable `https://doi.org/…`
  link — inert offline, breaks nothing). Numbering by order of first
  appearance: advice → rationale → blocks in program order. Section titles
  localized via the existing `_t` mechanism.
- **Markdown** (`render.py`): renders the same two sections and a final
  "Sources" section with full citations (DOI/PMID in clear), which also
  makes the Typst PDF's expert-mode bibliography pick them up unchanged.
- **PDF**: no renderer change needed beyond what flows in from the
  markdown body.

## 7. Error handling & edge cases

- Unreadable/corrupt dropped file → `lane: unreadable`; only revisited if
  its hash changes.
- Deleted file → reported `removed` at scan; its corpus entries stay (they
  are independently verified).
- Registry deleted/corrupt → rebuilt; duplicate corpus ids fail cleanly.
- Large files → size returned by the scan; the agent paginates its read.
- `mark_document_processed` with unknown filename or corpus-missing
  `evidence_id` → `ValueError` with the offending value.
- `suggest_next_week_loads` with no active program or an all-`none` week →
  explicit empty result with reason, not an error.
- Week with partial logs → per-block `unmatched` flags; computation
  proceeds for matched blocks.
- Old programs without structured rules → every block flagged `no_rule`;
  the skill falls back to conversational handling (v1 behavior for legacy
  programs, no migration).
- Mini-wave finding that contradicts the active program → routed proposal,
  never a silent edit (§4.3).

## 8. Testing

All offline, no network, tmp-dir athlete folders:

- Registry: scan states (new/modified/processed/removed/unreadable),
  corrupt registry rebuild, atomic write, README creation paths
  (`write_profile` and first `list`).
- `mark_document_processed`: lane validation, evidence-id existence check,
  unreadable path without summary.
- Engine: each `ProgressionRule` kind × (achieved / failed / partial logs /
  unmatched / no rule); rounding; e1RM fallback to `lift_inventory`;
  `from_pct` next-week resolution; state-file write.
- Schemas: `ProgressionRule` per-kind validators, `Guidance` cite/text
  bounds, `ProgramPlan` backward compat (old docs without new fields load).
- Rendering: HTML with/without advice/rationale/cites (snapshot),
  numbering order, bibliography formatting, markdown Sources section.
- Diligence: both new actions fire and clear on their conditions.

## 9. Out of scope

- Pre-competition spec (peak week, race week/day) — separate design.
- Server-side PDF text extraction — the client reads files.
- Any push mechanism — diligence stays pull-based.
- Auto-deload on repeated failure — `program-watch` surfaces it,
  `program-adaptation` decides.

## 10. Tally

- Tools: 93 → **97** (`list_athlete_documents`, `mark_document_processed`,
  `suggest_next_week_loads`, `save_watch_report`).
- Skills: 12 → **14** (`next-week-loads`, `program-watch`), plus edits to
  `deep-research`, `program-adaptation`, `training-checkin`,
  `performance-coach`, `athlete-onboarding`, `program-optimization`,
  `program-review`.
- Schemas: `DocumentRecord`, `ProgressionRule`, `Guidance`; `ExerciseBlock`
  and `ProgramPlan` gain optional fields (backward compatible).
