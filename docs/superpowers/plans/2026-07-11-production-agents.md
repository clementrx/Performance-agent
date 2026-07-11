# Production Agents (Premium Pipeline Phase 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three production agents of the premium pipeline: le Planificateur (`program-planning` — chooses and justifies the periodization model, sets per-cycle volume/intensity targets, hands over a quantified skeleton), l'Optimiseur (`program-optimization` — concrete sessions co-built with the athlete, every load engine-computed, saved through the versioned store), and le Nutritionniste (`nutrition-planning` — the quantified nutrition frame with hard safety guards, persisted as a new versioned-doc family). `program-generation` is split into the first two and **deleted** (replace, don't deprecate).

**Architecture:** Server side, one new versioned-document family joins the store (`athlete/nutrition/frame-vN.md` via the existing `_save_versioned_doc`/`_read_versioned_doc` helpers), `AthleteSnapshot` gains `nutrition_frame_version`, and 2 new MCP tools bring the count 45 → 47. Skill side, `skills/program-generation/` is replaced by `skills/program-planning/` (upstream half: structure) and `skills/program-optimization/` (downstream half: sessions, personalization, save), `skills/nutrition-planning/` is new, and every routing reference across the skill set is rewired (10 skills total). Spec: `docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md` §2 (Planner/Optimizer/Nutritionist — AUTHORITATIVE) and §3 (data flow).

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing FastMCP in-process test harness, Claude Code skill format (SKILL.md with YAML frontmatter).

**Conventions (this repo):**
- Line length 100; `uv run ruff format . && uv run ruff check . && uv run ty check` must stay clean (zero warnings).
- In a worktree, run tools as `env -u VIRTUAL_ENV uv run pytest -q` etc. — the parent repo's venv must not leak in.
- Commits: imperative subject, no type prefix (match `git log`), ≤72 chars.
- **The skills eval harness (`tests/skills/`) must stay green after every task.** Its rules bind every SKILL.md in this plan:
  - directory name == frontmatter `name` (`test_structure.py`);
  - `tools:` list ⇄ body mentions enforced in BOTH directions: every declared tool must appear in the body, and any server tool name appearing in the body (substring match, even in prose) must be declared (`test_tool_references.py`) — so never namedrop a tool a skill doesn't declare;
  - skills may only declare tools that exist on the server (`test_declared_tools_exist_on_the_server` — 47 after Task 1);
  - skill bodies must pass the anti-fabrication scanner (`test_no_fabricated_refs.py`) — no DOIs/PMIDs/ISBNs or author-year citations in skill prose.
- Skills are written in English with French persona names in the H1 (matching "Needs Analysis — l'Analyste"), each under ~150 lines.
- **Deliberate spec deviations (both maintainer-visible, document nothing else):**
  1. Spec §3 sketches `nutrition/frame-v1.yaml`. This plan stores **markdown** (`nutrition/frame-vN.md`) like the other three document families, for store uniformity — the frame's numbers live in a fenced yaml block inside the body, so the machine-readable payload survives while the store keeps one format, one frontmatter, one reason-on-v2+ rule.
  2. `program-generation`'s old no-dossier fallback ran its own live multilingual search (`search_evidence_live` + `save_evidence` + `verify_reference`). That self-search is **dropped from the production skills**: live search is deep-research's job now. `program-planning`'s no-dossier branch routes back to deep-research — unless the athlete explicitly declined, in which case it proceeds on **corpus-only** evidence (`search_evidence` + `get_citation`) and says so.

---

### Task 1: Nutrition-frame store + 2 MCP tools (45 → 47)

New versioned-doc family through the existing helpers — no new store machinery, just
the fourth instantiation of `_save_versioned_doc`/`_read_versioned_doc`
(`NUTRITION_DIR = "nutrition"`, prefix `"frame"`, label `"nutrition frame"`).
`AthleteSnapshot` gains `nutrition_frame_version` so the coach and le Planificateur
can locate the athlete in the pipeline without probing the read tool.

**Files:**
- Modify: `src/performance_agent/memory/store.py`
- Modify: `src/performance_agent/server/memory_tools.py`
- Modify: `tests/memory/test_store_documents.py`
- Modify: `tests/server/test_memory_tools.py`
- Modify: `README.md` (line 109), `docs/installing.md` (line ~205)

- [ ] **Step 1: Write the failing store tests**

In `tests/memory/test_store_documents.py`, extend the import and the `DOC_KINDS`
parametrize (every existing versioned-doc invariant then runs against the new family
for free):

```python
from performance_agent.memory.store import (
    read_analysis,
    read_nutrition_frame,
    read_program,
    read_research_dossier,
    save_analysis,
    save_nutrition_frame,
    save_program,
    save_research_dossier,
)
```

```python
DOC_KINDS = [
    pytest.param(save_analysis, read_analysis, "analysis", "needs-analysis", id="analysis"),
    pytest.param(
        save_research_dossier, read_research_dossier, "research", "dossier", id="research"
    ),
    pytest.param(
        save_nutrition_frame, read_nutrition_frame, "nutrition", "frame", id="nutrition"
    ),
]
```

And extend `test_document_families_version_independently` — after the three existing
`save_*` calls, add the frame and assert it does not disturb the others:

```python
def test_document_families_version_independently(tmp_path):
    save_program(tmp_path, "program", "squat-160", today=TODAY)
    save_analysis(tmp_path, "analysis", "squat-160", today=TODAY)
    save_research_dossier(tmp_path, "dossier", "squat-160", today=TODAY)
    save_nutrition_frame(tmp_path, "frame", "squat-160", today=TODAY)
    # Each family has its own v1 counter — a program does not bump the analysis.
    path, version = save_analysis(
        tmp_path, "analysis v2", "squat-160", reason="verdict changed", today=TODAY
    )
    assert version == 2
    assert path == tmp_path / "analysis" / "needs-analysis-v2.md"
    result = read_program(tmp_path)
    assert result is not None
    assert result[0]["version"] == 1
    frame = read_nutrition_frame(tmp_path)
    assert frame is not None
    assert frame[0]["version"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/memory/test_store_documents.py -q`
Expected: FAIL — `ImportError: cannot import name 'save_nutrition_frame'`

- [ ] **Step 3: Implement the store family**

In `src/performance_agent/memory/store.py`, add the directory constant next to
`RESEARCH_DIR`:

```python
NUTRITION_DIR = "nutrition"
```

Add the latest-version helper next to `latest_research_dossier_version`:

```python
def latest_nutrition_frame_version(base_dir: Path) -> int | None:
    """Return the highest existing nutrition-frame version, or None."""
    return _latest_doc_version(base_dir, NUTRITION_DIR, "frame")
```

Add the save/read pair after `read_research_dossier`:

```python
def save_nutrition_frame(
    base_dir: Path,
    markdown_body: str,
    goal_id: str,
    reason: str | None = None,
    today: date | None = None,
) -> tuple[Path, int]:
    """Write the next nutrition-frame version; recalculation requires a reason.

    Same immutable-version audit trail as programs; lives in nutrition/. The
    body is markdown with the engine-computed numbers in a fenced yaml block
    (store uniformity over the spec's frame-v1.yaml sketch — deliberate).
    """
    return _save_versioned_doc(
        base_dir,
        markdown_body,
        goal_id,
        subdir=NUTRITION_DIR,
        prefix="frame",
        label="nutrition frame",
        reason=reason,
        today=today,
    )


def read_nutrition_frame(
    base_dir: Path, version: int | None = None
) -> tuple[dict[str, object], str] | None:
    """Return (frontmatter, body) for the given or latest frame; None when empty."""
    return _read_versioned_doc(
        base_dir,
        subdir=NUTRITION_DIR,
        prefix="frame",
        label="nutrition frame",
        version=version,
    )
```

- [ ] **Step 4: Run the memory suite**

Run: `env -u VIRTUAL_ENV uv run pytest tests/memory -q`
Expected: PASS — the three parametrized ids (analysis, research, nutrition) all green,
program tests untouched.

- [ ] **Step 5: Write the failing server tests**

In `tests/server/test_memory_tools.py`:

Extend `test_read_athlete_on_fresh_directory` with one assertion:

```python
    assert snapshot["nutrition_frame_version"] is None
```

Append the lifecycle and snapshot tests:

```python
@pytest.mark.anyio
async def test_nutrition_frame_lifecycle(client, athlete_home):
    saved = await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "# Frame", "goal_id": "cut-15pct"}
    )
    assert not saved.isError
    assert saved.structuredContent["version"] == 1
    assert (athlete_home / "nutrition" / "frame-v1.md").exists()

    read_back = await client.call_tool("read_nutrition_frame", {})
    assert read_back.structuredContent["goal_id"] == "cut-15pct"
    assert read_back.structuredContent["body"] == "# Frame"

    unreasoned = await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "v2", "goal_id": "cut-15pct"}
    )
    assert unreasoned.isError
    assert "reason" in unreasoned.content[0].text


@pytest.mark.anyio
async def test_read_athlete_reports_nutrition_frame_version(client):
    await client.call_tool(
        "save_nutrition_frame", {"markdown_body": "# Frame", "goal_id": "cut-15pct"}
    )
    result = await client.call_tool("read_athlete", {})
    assert result.structuredContent["nutrition_frame_version"] == 1
```

Extend `test_reading_unsaved_documents_errors_readably` with:

```python
    frame = await client.call_tool("read_nutrition_frame", {})
    assert frame.isError
    assert "save_nutrition_frame" in frame.content[0].text
```

Extend the `test_memory_tools_are_listed` set with:

```python
        "save_nutrition_frame",
        "read_nutrition_frame",
```

- [ ] **Step 6: Run to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/server/test_memory_tools.py -q`
Expected: FAIL — `Unknown tool: save_nutrition_frame`, missing snapshot key, and the
listed-tools assertion.

- [ ] **Step 7: Implement the MCP tools and the snapshot field**

In `src/performance_agent/server/memory_tools.py`:

`AthleteSnapshot` gains the field and an updated docstring:

```python
class AthleteSnapshot(TypedDict):
    """Everything stored about the athlete, in one read.

    The four version fields tell you where the athlete is in the pipeline:
    analysis but no dossier means the deep research has not run yet;
    nutrition_frame_version is null unless the Nutritionist has run.
    """

    athlete_dir: str
    profile: Profile
    goals: list[Goal]
    program_version: int | None
    analysis_version: int | None
    dossier_version: int | None
    nutrition_frame_version: int | None
```

`read_athlete` fills it:

```python
        nutrition_frame_version=store.latest_nutrition_frame_version(base),
```

Add the two tools after `read_research_dossier`:

```python
def save_nutrition_frame(
    markdown_body: str, goal_id: str, reason: str | None = None
) -> VersionedDocSaved:
    """Write the NEXT nutrition-frame version (immutable audit trail).

    The frame is the Nutritionist's output: a fenced yaml block carrying the
    engine-computed numbers (goal, daily_kcal, protein_g_per_day,
    weekly_change_kg, clamped_to_floor, review_trigger) plus prose explaining
    them and the training phase the frame assumes. Version 1 needs no reason;
    every recalculation (v2+ — weight change, phase change) requires a
    reason. Existing versions are never overwritten.
    """
    path, version = store.save_nutrition_frame(
        resolve_athlete_dir(), markdown_body, goal_id, reason
    )
    return VersionedDocSaved(path=str(path), version=version)


def read_nutrition_frame(version: int | None = None) -> VersionedDocView:
    """Return the latest (or a specific) nutrition-frame version.

    Raises a readable error when no frame has been saved yet — run the
    nutrition-planning skill (which ends with save_nutrition_frame) first.
    """
    return _doc_view(
        store.read_nutrition_frame(resolve_athlete_dir(), version),
        "no nutrition frame has been saved yet; call save_nutrition_frame first",
    )
```

Add both to the `register()` tuple (after `read_research_dossier`). Memory tools:
14 → 16.

- [ ] **Step 8: Run the server suite**

Run: `env -u VIRTUAL_ENV uv run pytest tests/server -q`
Expected: PASS.

- [ ] **Step 9: Update the documented tool counts**

`README.md` line 109 — current sentence: `You should see 45 tools. Then ask:` →

```
You should see 47 tools. Then ask:
```

`docs/installing.md` line ~205 — current sentence starts `Ask your agent: *"List the
performance-agent tools."* You should see 45 tools (24` / `engine + 14 memory + 6
evidence + 1 report: ...` →

```
Ask your agent: *"List the performance-agent tools."* You should see 47 tools (24
engine + 16 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).
```

- [ ] **Step 10: Lint, type-check, full suite, commit**

Run: `env -u VIRTUAL_ENV uv run ruff format . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check && env -u VIRTUAL_ENV uv run pytest -q`
Expected: clean, all green (the two new tools are additions, so the skills drift guard
stays green).

```bash
git add src/performance_agent/memory/store.py src/performance_agent/server/memory_tools.py \
        tests/memory/test_store_documents.py tests/server/test_memory_tools.py \
        README.md docs/installing.md
git commit -m "Add versioned nutrition-frame store and tools"
```

---

### Task 2: le Planificateur — new `skills/program-planning/SKILL.md`

The upstream half of the old `program-generation`: structure, cited. It reads the
analysis and the dossier, CHOOSES the periodization model from calendar_type + goal +
evidence, sets per-cycle volume/intensity targets through the engine, and writes the
skeleton — which lives in the conversation, not a store, and lands inside the saved
program when l'Optimiseur finishes. `program-generation` stays in place until Task 5,
so `EXPECTED_SKILLS` grows by one here (9 entries, temporarily including both).

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/program-planning/SKILL.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`: add `"program-planning"` to `EXPECTED_SKILLS`
and append:

```python
def test_planning_skill_protocol(skills):
    planning = next(s for s in skills if s.frontmatter["name"] == "program-planning")
    body = planning.body.casefold()
    for needle in (
        "read_analysis",
        "read_research_dossier",
        "calendar_type",
        "build_block_cycle",
        "build_periodization_waves",
        "build_undulating_sessions",
        "build_inseason_maintenance",
        "build_peaking_block",
        "weekly_set_targets_for",
        "skeleton",
        "coaching judgment",
        "check_citations",
        "nutrition-planning",
        "program-optimization",
    ):
        assert needle in body, f"program-planning skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch.

- [ ] **Step 3: Write the skill**

Create `skills/program-planning/SKILL.md`:

```markdown
---
name: program-planning
description: Use after the research dossier is saved (or the athlete has explicitly
  declined deep research). Chooses and justifies the periodization model from the
  calendar and the evidence, splits macro to meso to microcycles with deloads and
  tapers, sets per-cycle volume and intensity targets through the engine, and
  hands the quantified skeleton to program-optimization.
tools: [read_athlete, get_time_context, read_analysis, read_research_dossier,
        search_evidence, get_citation, check_citations, build_periodization_waves,
        build_block_cycle, build_undulating_sessions, build_inseason_maintenance,
        build_peaking_block, weekly_set_targets_for]
---

# Program Planning — le Planificateur

The architect of the program: structure first, sessions later. Follow
performance-coach global rules. You produce the quantified SKELETON — the
periodization model, the cycles, the weekly targets — and program-optimization
turns it into concrete sessions with the athlete. You never write individual
exercises or session loads; that is the Optimizer's job.

## 1. Read the briefs

- `read_athlete` for calendar_type, training_age, availability and constraints;
  `get_time_context` for the weeks available — quote its numbers, never count
  weeks yourself.
- `read_analysis` (latest) — the quality hierarchy and muscle/pattern priorities
  the structure must serve. If it errors, stop and route back to needs-analysis;
  never plan without a brief.
- `read_research_dossier` — the evidence the structure is justified from. If it
  errors and the athlete has NOT declined deep research, route back to
  deep-research: the premium promise is a plan built on a dossier.

**Degraded mode — athlete declined deep research:** proceed on corpus-only
evidence. Query `search_evidence` for the skeleton's structural questions
(periodization for this calendar_type, dose-response for the priority
qualities) and render any id you quote with `get_citation`. What the corpus
does not cover is labeled coaching judgment. State plainly in the skeleton
that it was built without a research dossier.

## 2. Choose the periodization model — and justify it

The choice follows calendar_type + goal + what the dossier says:

- **single_deadline** 6+ weeks out → `build_block_cycle` (accumulation →
  intensification → realization). A scheduled 1RM test date → append
  `build_peaking_block` for the final 1-3 weeks. A shorter runway, or a dossier
  facet arguing against distinct blocks for this athlete →
  `build_periodization_waves` (generic ramp with deloads and taper) instead.
- **recurring_fixtures** → `build_inseason_maintenance` per typical week (1 or
  2 matches). It REFUSES 0 matches (use a normal building week) and 3+ (rest is
  the prescription) — relay refusals, never work around them.
- **open_ended**, or concurrent qualities with no deadline pressure →
  `build_undulating_sessions` to structure intensity within the week, and/or
  `build_periodization_waves` across weeks.

Name the model you chose and WHY — cited from the dossier's periodization facet
(`get_citation` for the full string and stars) or explicitly labeled coaching
judgment. Where the dossier shows a live disagreement, say which camp the
structure follows and why; a facet it marked thin stays coaching judgment here.

## 3. Per-cycle volume and intensity targets

Structure without numbers is decoration:

- **Strength/hypertrophy volume:** `weekly_set_targets_for` (training_age)
  gives the per-muscle weekly hard-set landmarks. Distribute them across the
  analysis' muscle priorities: top priorities program toward optimal_high_sets,
  secondary ones toward minimum_effective_sets; never exceed
  maximum_adaptive_sets.
- **Endurance volume/intensity:** define the baseline week (week-1 durations
  and efforts), then scale every week by its volume_factor and intensity_factor
  from the model. A wave you don't apply to the numbers is decoration.
- Deloads and tapers land where the model puts them — never silently dropped.

## 4. Write the skeleton

The skeleton is a markdown section of the EVENTUAL program — it is not saved
separately and there is no skeleton store by design: it lives in this
conversation and lands inside the saved program when program-optimization
finishes. It carries:

1. **Model & justification** — chosen model, the citation or coaching-judgment
   label on every structural choice.
2. **Macro → meso → micro layout** — the weeks, phase by phase, deloads and
   tapers marked.
3. **Weekly targets** — per-muscle set targets and/or endurance
   volume/intensity per week, as numbers.
4. **Constraints the Optimizer must respect** — availability (sessions per
   week), equipment, injuries, split_preferences, and the analysis' injury
   flags.

## 5. Hand off

- Run `check_citations` over the skeleton text; fix anything flagged.
- Goal touches body composition (cut, gain, recomp) and `read_athlete`'s
  nutrition_frame_version is null → route to nutrition-planning FIRST: the
  frame must exist before sessions are finalized, so training and deficit are
  synchronized (no aggressive deficit during an intensification block).
- Then route onward to program-optimization, skeleton in the conversation.
```

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — all 13 declared tools appear in the body; no undeclared server tool
is namedropped (watch: `nutrition_frame_version` is a snapshot FIELD, not a tool
name, and does not contain `read_nutrition_frame` — safe; "the saved program" prose
must never become the tool name, which this skill does not declare). The
route-onward names (program-optimization, nutrition-planning) are skill names the
harness does not resolve — they exist by Tasks 3-4.

- [ ] **Step 5: Commit**

```bash
git add skills/program-planning/SKILL.md tests/skills/test_structure.py
git commit -m "Add the program-planning skill (le Planificateur protocol)"
```

---

### Task 3: l'Optimiseur — new `skills/program-optimization/SKILL.md`

The downstream half of the old `program-generation`: the session template, the
personalization rules and the save protocol are kept verbatim where they were good
(uniform per-exercise format, derived-pace honesty rule, global-versioning warning).
New: the skeleton contract, the per-exercise progression rules through the phase-2
tools, and the nutrition annex.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/program-optimization/SKILL.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`: add `"program-optimization"` to
`EXPECTED_SKILLS` and append:

```python
def test_optimization_skill_protocol(skills):
    optimization = next(
        s for s in skills if s.frontmatter["name"] == "program-optimization"
    )
    body = optimization.body.casefold()
    for needle in (
        "skeleton",
        "prescribe_reps_load",
        "prescribe_load",
        "estimate_1rm",
        "progress_double_progression",
        "prescribe_top_set_backoff",
        "prescribe_wave_loading",
        "convert_rpe_to_rir",
        "predict_race_time",
        "read_nutrition_frame",
        "save_program",
        "check_citations",
        "split_preferences",
        "rest",
        "purpose",
        "stars",
    ):
        assert needle in body, f"program-optimization skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch.

- [ ] **Step 3: Write the skill**

Create `skills/program-optimization/SKILL.md`:

````markdown
---
name: program-optimization
description: Use when program-planning has handed over a quantified skeleton.
  Builds the concrete sessions with the athlete under their real constraints,
  computes every load and pace through the engine, states a progression rule per
  exercise, iterates until the athlete validates, and saves the program through
  the versioned store.
tools: [read_athlete, get_time_context, read_research_dossier, get_citation,
        check_citations, prescribe_load, prescribe_reps_load, estimate_1rm,
        progress_double_progression, prescribe_top_set_backoff,
        prescribe_wave_loading, convert_rpe_to_rir, predict_race_time,
        compute_pace, read_nutrition_frame, save_program]
---

# Program Optimization — l'Optimiseur

Follow performance-coach global rules. The program is a coaching document the
athlete will live with — make it concrete, honest, and traceable.

## 1. The skeleton is your contract

program-planning hands the skeleton over in the conversation — the periodization
model, the weekly volume/intensity targets, the constraints. If there is no
skeleton in the conversation, route back to program-planning; never invent
structure here. `read_athlete` for equipment, injuries, availability,
split_preferences and lift_inventory; `get_time_context` for the window. For
evidence prose, `read_research_dossier` supplies the facet syntheses — respect
its confidence levels (a "thin evidence" facet stays coaching judgment) and
render any corpus id you quote with `get_citation`.

## 2. Loads are computed, never guessed

- **Strength sets** are sets×reps @ RIR or %1RM. RIR path: `prescribe_reps_load`
  from the lift's 1RM in lift_inventory. %1RM path: `prescribe_load`. Only a
  recent heavy set on file? `estimate_1rm` first (one formula per athlete and
  lift, stay consistent). The athlete speaks RPE? `convert_rpe_to_rir` before
  prescribing — the prescription tools take RIR.
- **A progression rule per exercise, stated in the program.** Default: double
  progression — name the rep range and load increment; between-session
  decisions follow `progress_double_progression` (fill the range, then add
  load). Where the skeleton calls for them: top set/back-off sessions via
  `prescribe_top_set_backoff`, wave loading via `prescribe_wave_loading` (relay
  its refusals — the supra-maximal cap is not yours to bypass).
- **Endurance paces:** only RACE pace at a distance is computable
  (`predict_race_time` / `compute_pace` from a current benchmark; the tools
  enforce 1500 m–marathon). Easy, threshold, and interval paces are
  coaching-judgment DERIVATIONS from race pace — label the NUMBER itself
  "coaching judgment (derived from race pace)", never present a derived pace as
  tool-computed. Never guess a pace, same rule as loads.
- No recent set or benchmark to compute from? Open the program with a
  benchmark/test week and label the early loads provisional — do not guess a
  number to fill the gap.

## 3. Sessions with the athlete

- **Split design:** map the skeleton's per-muscle weekly set targets onto the
  athlete's available days, respecting split_preferences and sessions_per_week
  strictly — a plan the athlete cannot attend is a failed plan. Confirm
  availability is still current before laying out the week.
- **Substitutions:** missing equipment → propose the substitution, state the
  expected difference in stimulus, ask the athlete. Active injury → adapt
  around it (performance-coach red-flag rules), never through it. Preferences
  the athlete has voiced beat your defaults when the stimulus is equivalent.
- **Formatting is not optional, and it is uniform across every session in the
  program — no exceptions for "short" or "simple" days.** Each session is a
  markdown bullet list, ONE exercise per bullet, never multiple exercises
  folded into a single prose sentence. Every bullet carries, in this order:
  exercise name, sets×reps or duration, load/pace/RPE, rest, and a one-line
  **purpose**. Never drop the rest field because it "feels obvious" — write it
  every time, even for accessory work (e.g. "rest 60-90s"). Purposes backed by
  evidence carry the corpus citation and its **stars**; purposes without corpus
  backing are labeled "coaching judgment". Template for every session, copy
  this shape exactly:

  ```
  **[Day] [slot] — [session name]:**
  - [Exercise]: [sets]×[reps] @ [RPE or %1RM] — rest [X min/sec]. *[Purpose]
    ([citation], [stars]) or (coaching judgment).*
  - [Exercise]: ...
  ```

  Before saving, re-read every session in the program and confirm each one
  matches this template bullet-for-bullet — a session that mixes prose and
  bullets, or omits rest/RPE on even one exercise, is not done yet.

## 4. Iterate until the athlete validates

Present the draft week by week and ASK. Adjust exercises, days, and volumes with
the athlete inside the skeleton's targets; a change that breaks the skeleton's
structure (model, phases, weekly targets) goes back to program-planning instead.
Do not save until the athlete validates the layout.

## 5. Save and deliver

- **Nutrition annex:** call `read_nutrition_frame`. If a frame exists, quote
  its daily kcal and protein target in the program header ("nutrition frame vN:
  X kcal/day, Y g protein/day"); if it errors, there is no annex — never invent
  one.
- Run `check_citations` over the full program text (skeleton section included);
  fix anything flagged.
- `save_program` (markdown body — the skeleton section plus the sessions;
  goal_id; v1 needs no reason). Quote the saved version and path back. Check
  `read_athlete`'s program_version first: PROGRAM versioning is global across
  goals (analyses and dossiers count separately), so if ANY program already
  exists this save is v2+ and REQUIRES a reason (e.g. "first program for new
  goal sub-45-10k"). Only a truly first-ever program is v1.
- Carry the assessment's named risks and checkpoints into the program's
  check-in triggers.
- Route back to performance-coach: session logging and the first check-in run
  through training-checkin (Mode B), and name what would trigger an early
  adaptation.
````

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — all 16 declared tools appear in the body; no undeclared tool is
namedropped (watch: write "session logging", never the log tool's name — this skill
does not declare it; the skeleton tools like the wave builders belong to
program-planning and must not appear here by name).

- [ ] **Step 5: Commit**

```bash
git add skills/program-optimization/SKILL.md tests/skills/test_structure.py
git commit -m "Add the program-optimization skill (l'Optimiseur protocol)"
```

---

### Task 4: le Nutritionniste — new `skills/nutrition-planning/SKILL.md`

Activated when the goal touches body composition (cut, gain, recomp) — routed from
program-planning or the coach. Everything numeric comes from `compute_bmr_tdee` and
`prescribe_nutrition_targets`; the safe weekly rate is capped by the needs analysis'
body-composition verdict (the skill must NOT name the assessment tool — it does not
declare it, and the harness's substring guard would fail; it says "the needs
analysis' body-composition feasibility verdict" instead).

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/nutrition-planning/SKILL.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`: add `"nutrition-planning"` to `EXPECTED_SKILLS`
and append:

```python
def test_nutrition_skill_protocol(skills):
    nutrition = next(s for s in skills if s.frontmatter["name"] == "nutrition-planning")
    body = nutrition.body.casefold()
    for needle in (
        "compute_bmr_tdee",
        "prescribe_nutrition_targets",
        "save_nutrition_frame",
        "clamped_to_floor",
        "protein",
        "activity factor",
        "not medical advice",
        "refer",
        "relay",
        "review_trigger",
        "intensification",
    ):
        assert needle in body, f"nutrition-planning skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch.

- [ ] **Step 3: Write the skill**

Create `skills/nutrition-planning/SKILL.md`:

````markdown
---
name: nutrition-planning
description: Use when the goal touches body composition (cut, gain, or
  recomposition) — routed from program-planning or the coach. Computes the
  quantified nutrition frame (TDEE, daily kcal, protein, safe weekly rate)
  through the engine's hard guards and saves it as a versioned document. No
  meal plans; not medical advice.
tools: [read_athlete, get_time_context, read_analysis, search_evidence,
        get_citation, compute_bmr_tdee, prescribe_nutrition_targets,
        check_citations, save_nutrition_frame]
---

# Nutrition Planning — le Nutritionniste

A quantified frame, not a diet: daily calories, protein, and a safe weekly
rate, every number from an engine tool. Follow performance-coach global rules.
This is not medical advice — say so when you deliver the frame — and there are
no meal plans here by design.

## 1. Inputs first

- `read_athlete`: weight_kg, height_cm, sex, birth_date. Age in whole years is
  derived from birth_date against `get_time_context`'s today — quote the
  tool's date and state the age you derived. Missing weight, height, or sex?
  Ask before computing — the engine errors without them.
- `read_analysis` for the body-composition feasibility verdict the needs
  analysis rendered: its safe weekly rate is your ceiling. Never prescribe a
  faster rate than the verdict called safe, even if the athlete pushes — the
  deadline moves, not the rate. If the verdict relayed a refusal (target below
  the healthy minimum), that refusal stands here too.
- Activity: choose the activity factor honestly from the PLANNED training load
  (sessions per week × minutes from availability, plus the skeleton's phase if
  program-planning routed you here) — document the factor you chose and why.
  Don't flatter it: an aspirational factor inflates TDEE and deepens the real
  deficit.

## 2. Compute the frame — engine only

- `compute_bmr_tdee` (sex, weight, height, age, activity factor). It REFUSES
  under-15s with a paediatric referral — relay it and stop.
- `prescribe_nutrition_targets` (tdee, goal direction cut/maintain/gain, the
  safe weekly rate as a fraction of bodyweight, weight, height, sex). Its
  guards are hard-coded: relay every refusal verbatim (underweight BMI →
  referral to a health professional); never work around one, never re-call
  with softened inputs to dodge a guard.
- clamped_to_floor=True on a CUT means the deadline demands too deep a
  deficit: extend the deadline, never deepen — say so and renegotiate the
  timeline with the athlete. On maintain/gain it means the TDEE input is
  almost certainly an upstream estimation error — re-check the activity factor
  and the biometrics before trusting any number.
- Quote the protein target the tool returned for the goal (g/day) — you never
  invent a protein number. Evidence prose (why protein rises on a cut, why the
  rate cap exists) cites corpus ids only: `search_evidence`, rendered via
  `get_citation`, or labeled coaching judgment.

## 3. The frame document

One fenced yaml block carrying the numbers, then prose explaining them:

  ```yaml
  goal: cut                      # cut | maintain | gain
  daily_kcal: 2150               # prescribe_nutrition_targets output
  protein_g_per_day: 158         # prescribe_nutrition_targets output
  weekly_change_kg: -0.55        # the SAFE rate, not the asked one
  clamped_to_floor: false
  review_trigger: bodyweight drift >2% from trajectory
  ```

The prose states, for each number, which tool produced it; the activity-factor
rationale; and the **synchronization rule**: name the training phase the frame
assumes. No aggressive deficit during an intensification block — if the
skeleton has one, schedule the deficit around it and SAY so in the frame.

## 4. Scope and red flags

You are a coach, not a clinician — not medical advice, no meal plans, no
supplement prescriptions. Disordered-eating signals (fear of eating,
compulsive restriction, purging, pushing to bypass the safety floors) → STOP
prescribing, refer out to a health professional, and record the flag. The
engine's refusals on unsafe targets are relayed the same way, verbatim.

## 5. Save and route back

Run `check_citations` over the prose; fix anything flagged. Then
`save_nutrition_frame` (markdown body; goal_id; v1 needs no reason; every
recalculation — weight change, phase change — is v2+ and requires a reason).
Quote the saved version and path, then route back to program-planning so the
sessions are finalized against the frame.
````

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — all 9 declared tools appear in the body; no undeclared tool is
namedropped (the assessment tool names and the check-in/session log tools must not
appear); the yaml example contains no locators, so the anti-fabrication scanner
stays green.

- [ ] **Step 5: Commit**

```bash
git add skills/nutrition-planning/SKILL.md tests/skills/test_structure.py
git commit -m "Add the nutrition-planning skill (le Nutritionniste protocol)"
```

---

### Task 5: Replace program-generation + rewire routing everywhere

Replace, don't deprecate: `skills/program-generation/` is deleted and every reference
to it across skills, tests, and README is rewired onto the planning → optimization
pair. `EXPECTED_SKILLS` lands at its final 10.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Delete: `skills/program-generation/` (git rm)
- Modify: `skills/performance-coach/SKILL.md`
- Modify: `skills/deep-research/SKILL.md`
- Modify: `skills/program-adaptation/SKILL.md`
- Modify: `skills/training-checkin/SKILL.md`
- Modify: `skills/program-report/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update the harness first (failing)**

In `tests/skills/test_structure.py`:

1. Remove `"program-generation"` from `EXPECTED_SKILLS`. Final set (10 skills):

```python
EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "needs-analysis",
    "program-planning",
    "program-optimization",
    "nutrition-planning",
    "training-checkin",
    "program-adaptation",
    "program-report",
    "deep-research",
}
```

2. Delete `test_generation_skill_protocol` entirely (its coverage now lives in the
   three protocol tests added in Tasks 2-4).
3. Extend `test_coach_skill_carries_the_global_rules` needles with the new routing
   targets — append to the tuple:

```python
        "program-planning",
        "program-optimization",
        "nutrition-planning",
```

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills mismatch (program-generation still on disk) and the
coach needles.

- [ ] **Step 2: Delete the old skill**

```bash
git rm -r skills/program-generation
```

- [ ] **Step 3: Rewire performance-coach**

In `skills/performance-coach/SKILL.md`, replace the `## Routing` section with:

```markdown
## Routing

At session start:

- Empty/incomplete profile → athlete-onboarding
- New or changed goal → needs-analysis (ALWAYS analyze and assess before generating)
- Returning athlete with a program → training-checkin
- Goal analyzed and accepted, but no research dossier → deep-research
- Analysis and dossier done, but no saved program → program-planning (it hands
  the skeleton to program-optimization, and routes to nutrition-planning first
  when the goal touches body composition)
- Athlete explicitly declines deep research → program-planning anyway (its
  degraded corpus-only branch handles the no-dossier state); record the decline
  in the conversation and do not re-offer deep-research this session.

After a skill hands back:

- Accepted goal, no dossier → deep-research
- Dossier saved, no program → program-planning
- Skeleton handed over by program-planning → program-optimization
- Check-in shows poor adherence, plateau, pain, or schedule change → program-adaptation

Re-evaluate routing after each skill completes.
```

And replace the `## Modes` section with:

```markdown
## Modes

- Mode A (one-shot): onboarding → needs analysis → deep research → planning →
  optimization → deliver. Still save everything through the memory tools.
- Mode B (ongoing coach): all of Mode A plus check-ins and adaptation over time.
```

(The frontmatter `tools:` list is unchanged — routing names are skill names, not
tools.)

- [ ] **Step 4: Rewire the remaining skill references**

`grep -rn "program-generation" skills/` — expected hits and exact fixes:

In `skills/deep-research/SKILL.md` (§7, last line):
- `covered vs thin, studies saved, languages searched), then route onward: dossier` /
  `saved → program-generation.` → route-onward becomes:

```markdown
covered vs thin, studies saved, languages searched), then route onward: dossier
saved → program-planning (le Planificateur builds the skeleton on the dossier
you just saved).
```

In `skills/program-adaptation/SKILL.md` (§2):
- `wave you don't apply is decoration (see program-generation §2).` →

```markdown
wave you don't apply is decoration (see program-planning §3). Session-level
rebuilds follow program-optimization's load and formatting rules; if the
STRUCTURE itself must change (new periodization model, changed calendar),
route through program-planning instead of patching sessions in place.
```

In `skills/training-checkin/SKILL.md`:
- `route to program-generation instead.` → `route to program-planning instead.`

In `skills/program-report/SKILL.md`:
- `program-generation; a report of nothing helps nobody.` →
  `program-planning; a report of nothing helps nobody.`

- [ ] **Step 5: Update README's skill mentions**

In `README.md`:

- Mermaid node (line ~195, second line of the SK node): replace
  `program generation · check-ins · adaptation]` with
  `planning · optimization · nutrition · check-ins · adaptation]`
- Changelog bullet (line ~233): replace the "✅ Eight coaching skills …" bullet
  (all five lines) with:

```markdown
- ✅ Ten coaching skills (Claude Code plugin format): session rituals, onboarding
  with a multi-lift 1RM inventory, needs analysis with honest multi-goal feasibility
  verdicts and counter-proposals, deep multilingual research dossiers, evidence-cited
  periodization planning (le Planificateur), athlete-validated session optimization
  with engine-computed loads (l'Optimiseur), a quantified nutrition frame behind hard
  safety guards (le Nutritionniste), structured check-ins, versioned adaptation —
  each eval-guarded against tool drift and fabricated references
```

- Check `grep -n "program.generation\|[Ee]ight coaching" README.md docs/installing.md`
  for anything this plan missed; `docs/installing.md` copies `skills/*` wholesale and
  does not enumerate skill names — verify, don't assume.

- [ ] **Step 6: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — 10 skills, the three new protocol tests green, the coach needles
green, tool drift green in both directions, anti-fabrication green.

- [ ] **Step 7: Commit**

```bash
git add -A skills/ README.md tests/skills/test_structure.py
git commit -m "Replace program-generation with planning and optimization skills"
```

---

### Task 6: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Full test suite**

Run: `env -u VIRTUAL_ENV uv run pytest -q`
Expected: all green — memory, server, skills harness (structure, tool drift both
directions, anti-fabrication), engine, evidence, reports, packaging.

- [ ] **Step 2: Zero-warning gate**

Run: `env -u VIRTUAL_ENV uv run ruff format --check . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`
Expected: clean output, no warnings.

- [ ] **Step 3: Residual reference check**

Run: `grep -rn "program-generation" README.md docs/installing.md skills/ tests/ src/`
Expected: no hits outside `docs/superpowers/` history (specs/plans/backlog are
records and stay as written).

- [ ] **Step 4: Skill line budget**

Run: `wc -l skills/*/SKILL.md`
Expected: every skill under ~150 lines.

- [ ] **Step 5: Commit any stragglers**

```bash
git status --short
```

Expected: clean tree. If formatting touched files:

```bash
git add -A && git commit -m "Apply formatting"
```
