# Guardian Agents (Premium Pipeline Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the two guardian agents that close the premium pipeline: le Contrôleur (`program-review` — the mandatory delivery gate: a deterministic compliance pass, then an adversarial second opinion; nothing is saved or delivered without its APPROVED verdict) and le Vigile (`training-checkin` evolved — structured-signal triggers read from the extended memory: load stalls, failed reps, bodyweight drift against the nutrition frame, fixture pile-up — plus `program-adaptation` gaining stall-driven diagnosis and the strength-vs-hypertrophy plateau distinction). Three open backlog items from the phase-5 review land here too (peaking-docstring reconciliation, skeleton intensity-mode line, nutrition-refusal escape hatch), and the older "eating-disorder signal refusal engine-side" backlog note is resolved at SKILL level (rationale in Conventions below).

**Architecture:** Skill-side only — **no new server tools this phase**; the count stays at 47 and le Contrôleur is built entirely from existing read/compute tools (`read_athlete`, `get_time_context`, `read_analysis`, `read_research_dossier`, `read_nutrition_frame`, `check_citations`, `get_citation`, `prescribe_load`, `prescribe_reps_load`, `weekly_set_targets_for`, `compute_session_load`). One new skill (`skills/program-review/`, EXPECTED_SKILLS 10 → 11), the save path in `program-optimization` and `program-adaptation` is gated behind it, `performance-coach` routing inserts the gate between optimization and delivery, and `training-checkin` becomes le Vigile. Spec: `docs/superpowers/specs/2026-07-11-premium-coach-pipeline-design.md` §2 (Controller/Sentinel — AUTHORITATIVE) and §6 (error handling and safety: "The Controller is a mandatory gate: no save_program, no PDF without sign-off; rejections are motivated and audited").

**Tech Stack:** Python 3.13, pytest, existing FastMCP in-process test harness, Claude Code skill format (SKILL.md with YAML frontmatter).

**Conventions (this repo):**
- Line length 100; `uv run ruff format . && uv run ruff check . && uv run ty check` must stay clean (zero warnings).
- In a worktree, run tools as `env -u VIRTUAL_ENV uv run pytest -q` etc. — the parent repo's venv must not leak in.
- Commits: imperative subject, no type prefix (match `git log`), ≤72 chars.
- **The skills eval harness (`tests/skills/`) must stay green after every task.** Its rules bind every SKILL.md in this plan:
  - directory name == frontmatter `name` (`test_structure.py`);
  - `tools:` list ⇄ body mentions enforced in BOTH directions: every declared tool must appear in the body, and any server tool name appearing in the body (substring match, even in prose) must be declared (`test_tool_references.py`) — so never namedrop a tool a skill doesn't declare. In particular, `program-review`'s body must never contain the string `save_program` (it tells program-optimization to save without naming the tool), and no builder tool name (`build_*`) may appear in it;
  - skills may only declare tools that exist on the server (`test_declared_tools_exist_on_the_server` — 47, unchanged this phase);
  - skill bodies must pass the anti-fabrication scanner (`test_no_fabricated_refs.py`) — no DOIs/PMIDs/ISBNs or author-year citations in skill prose.
- Skills are written in English with French persona names in the H1 (matching "Program Planning — le Planificateur"), each under ~150 lines.
- **Design decisions this plan encodes (document nothing else as deviation):**
  1. **ED-signal refusal is a SKILL-level protocol, not engine code.** The phase-2b backlog note ("Eating-disorder signal refusal engine-side — spec §4.4 mentions 'BMI or signals'; only the BMI refusal is in `engine/nutrition.py`") resolves here without touching the engine: the signals in question are **conversational** (fear of eating, compulsive restriction, purging, pushing to bypass floors) — a pure stdlib function cannot observe a conversation — while the engine already hard-guards the entire **numeric** side (BMI refusal, absolute caloric floor, maximum loss rate, minimum protein in deficit, none bypassable by agents). So the guardians encode the refusal protocol where the signals live: `nutrition-planning` already carries it (§4), and Task 3 gives `training-checkin` (le Vigile) the identical stop / refer-out / record language. The backlog item graduates and is deleted in Task 4.
  2. **Le Contrôleur re-runs prescription tools; structural builders are checked by traceability, not re-execution.** The gate's declared tool list is deliberately limited to read/compute tools (no `build_*` builders, no new server tools this phase). Spot-checks re-run `prescribe_load` / `prescribe_reps_load` / `weekly_set_targets_for` / `compute_session_load`; for periodization structure, the skill verifies the skeleton NAMES its builder and that the quoted factors are actually applied to the numbers (baseline × factor arithmetic) — a check the reviewer can do by reading, keeping the gate lean.
  3. **The Vigile persona lands on `training-checkin` only.** Spec §2's Sentinel "evolves training-checkin + program-adaptation", but one skill carries one persona: `training-checkin` gets the "— le Vigile" H1 and the trigger battery; `program-adaptation` keeps its own name and references the Vigile as its trigger source.
  4. **`training-checkin` additionally declares `read_checkins`** (beyond the design brief's minimal `read_nutrition_frame` addition): the bodyweight-drift trigger compares a SERIES of check-ins against the frame trajectory — today's entry alone cannot show "wrong direction for 2+ check-ins".
  5. **The `Profile.weight_kg` ↔ `CheckinEntry.bodyweight_kg` mapping** (phase-1 backlog: "the Interview/Vigile skills must state the mapping when they are written") is stated in the Vigile's body in Task 3; Task 4 trims the backlog bullet to its remaining Interview half.

---

### Task 1: le Contrôleur — new `skills/program-review/SKILL.md`

The mandatory delivery gate — the final guardian of "agents narrate, the engine
calculates, the corpus cites". Two passes in strict order: (1) a deterministic
COMPLIANCE checklist (numbers trace to engine tools and are spot-checked by re-running
them; `check_citations` over the FULL draft; constraint coherence vs the profile;
nutrition coherence vs the frame; safety verdicts respected), then (2) an ADVERSARIAL
second opinion run as a genuinely independent pass. Verdict is APPROVED (and
program-optimization saves — the Contrôleur never saves itself) or RETURNED (named
recipient + objections quoted). `EXPECTED_SKILLS` grows 10 → 11.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Create: `skills/program-review/SKILL.md`

- [ ] **Step 1: Extend the harness first (failing)**

In `tests/skills/test_structure.py`: add `"program-review"` to `EXPECTED_SKILLS`
(final set, 11 skills):

```python
EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "needs-analysis",
    "program-planning",
    "program-optimization",
    "nutrition-planning",
    "program-review",
    "training-checkin",
    "program-adaptation",
    "program-report",
    "deep-research",
}
```

Append the protocol test:

```python
def test_review_skill_protocol(skills):
    review = next(s for s in skills if s.frontmatter["name"] == "program-review")
    body = review.body.casefold()
    for needle in (
        "compliance",
        "adversarial",
        "check_citations",
        "get_citation",
        "prescribe_load",
        "prescribe_reps_load",
        "weekly_set_targets_for",
        "compute_session_load",
        "read_nutrition_frame",
        "read_research_dossier",
        "exceeds_safe_rate",
        "subagent",
        "approved",
        "returned",
        "never saves",
        "verbatim",
        "program-planning",
        "program-optimization",
    ):
        assert needle in body, f"program-review skill lost: {needle}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — expected-skills set mismatch (`program-review` not on disk).

- [ ] **Step 3: Write the skill**

Create `skills/program-review/SKILL.md`:

```markdown
---
name: program-review
description: Use when program-optimization hands over an athlete-validated draft
  program, or program-adaptation a confirmed v2+ proposal. The mandatory delivery
  gate — a deterministic compliance pass, then an adversarial second opinion.
  Verdict is APPROVED (program-optimization saves) or RETURNED with named,
  quoted objections. Nothing is delivered without its sign-off.
tools: [read_athlete, get_time_context, read_analysis, read_research_dossier,
        read_nutrition_frame, check_citations, get_citation, prescribe_load,
        prescribe_reps_load, weekly_set_targets_for, compute_session_load]
---

# Program Review — le Contrôleur

Follow performance-coach global rules. You are the last agent before delivery:
independent, adversarial, impossible to skip. You never write program content
and you **never save** — you approve or you return, nothing else. **Nothing is
delivered to the athlete without an APPROVED verdict from this skill.**

## 1. Gather the dossier

`read_athlete` (constraints, injuries, availability, split_preferences,
lift_inventory, training_age), `get_time_context` (the window the draft
claims), `read_analysis` (the feasibility verdict and its safe rates),
`read_research_dossier` (the evidence the draft cites). The draft under review
arrives in the conversation from program-optimization (or program-adaptation
for a v2+ proposal). A missing brief is already a RETURN: a program that
cannot be checked cannot be approved.

## 2. Pass one — COMPLIANCE (deterministic checklist)

Work the list in order; every item is pass/fail with the evidence quoted.

1. **Every training number traces to an engine tool named in the draft's own
   justifications.** Spot-check by re-running the cited tools:
   `prescribe_load` / `prescribe_reps_load` on a sample of sessions (at least
   one per phase) against the lift_inventory 1RMs; `weekly_set_targets_for`
   (training_age) against the per-muscle weekly totals the draft actually
   programs (top priorities near optimal, nothing past maximum_adaptive_sets);
   `compute_session_load` wherever the draft quotes a session-RPE load. A
   number matching no tool output is a fail. The skeleton must NAME the
   periodization builder it used and quote its factors — verify the factors
   are applied in the numbers (baseline × factor arithmetic); structure is
   checked by traceability, not re-execution.
2. **Citations:** run `check_citations` over the FULL draft, skeleton section
   included. Any unknown reference is a fail — no exceptions, no "probably
   fine". Render spot-checked ids with `get_citation` and confirm the draft's
   stars match the corpus grade.
3. **Constraint coherence vs the profile:** sessions per week ≤ availability;
   no exercise requires equipment the athlete lacks; no exercise loads an
   active injury area; the split matches split_preferences or the draft
   justifies the deviation explicitly.
4. **Nutrition coherence:** call `read_nutrition_frame`. If a frame exists,
   the program header's annex must quote it (version, daily kcal, protein) and
   the plan must respect its synchronization rule — an aggressive deficit
   scheduled against an intensification block is a fail. If it errors, the
   draft must carry no annex at all.
5. **Safety:** the analysis' body-composition verdict is binding — a rate it
   flagged (exceeds_safe_rate) or refused must not reappear anywhere in the
   program, and engine refusals relayed upstream must still be relayed, never
   papered over. Red-flagged injury patterns from the profile stay unloaded.

## 3. Pass two — ADVERSARIAL second opinion

Compliance proves the numbers; it does not prove the coaching. Now argue
against the draft as a genuinely independent reviewer:

- **In Claude Code:** dispatch a subagent whose ONLY inputs are the draft and
  the research dossier, instructed to refute it — "is this volume sustainable
  at this availability? does the model choice contradict the dossier's
  evidence? are the progression rules coherent with this athlete's training
  age?" It looks for reasons to reject, not reasons to agree.
- **Elsewhere:** re-read the draft cold, top to bottom, arguing against it
  with the same three questions before rendering any verdict.

Discard objections that do not survive scrutiny (the dossier or an engine
output already answers them — say which). Objections that survive go back
with the draft: structural (model, phases, weekly targets) → program-planning;
session-level (exercise choice, loads, layout) → program-optimization —
always quoting the objection verbatim so the fix targets the real problem.

## 4. Verdict — APPROVED or RETURNED, nothing else

- **APPROVED:** state it, list what was checked (tools re-run, citations
  clean, constraints verified, second opinion survived), and hand back to
  program-optimization to run its save-and-deliver step. The Contrôleur
  never saves anything itself — approval authorizes the Optimizer's save, it
  does not perform it.
- **RETURNED:** name the recipient (program-planning or program-optimization),
  list every surviving objection verbatim, and state what an approvable
  revision looks like. A revised draft comes back HERE and the gate re-runs
  in full — both passes, every time.

**Nothing is delivered without APPROVED. No save, no PDF, no "here is your
program" — the gate is mandatory, not advisory.**
```

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — 11 skills; all 11 declared tools appear in the body; no undeclared
tool is namedropped (verify by eye: the body never contains `save_program`,
`read_program`, `read_sessions`, `render_report`, or any `build_` builder name —
"save-and-deliver step" and "the periodization builder it used" are the load-bearing
phrasings); no locators, so anti-fabrication stays green.

- [ ] **Step 5: Commit**

```bash
git add skills/program-review/SKILL.md tests/skills/test_structure.py
git commit -m "Add the program-review skill (le Contrôleur delivery gate)"
```

---

### Task 2: Wire the gate + the three phase-5 backlog fixes

The gate only exists if the save path runs through it. `program-optimization` replaces
its save step: after athlete validation the draft goes to program-review, and only an
APPROVED verdict triggers `check_citations` + `save_program` (both kept).
`performance-coach` routing inserts the gate between optimization and delivery.
`program-adaptation` sends adapted v2+ programs through the same gate before saving.
And `program-planning` absorbs the three backlog fixes: the hybrid-peaking clause is
qualified against `build_peaking_block`'s docstring ("Use this only when a maximal
strength test is scheduled … the last week carries intensity above 1.0 for
openers/heavy singles"), the skeleton spec gains the per-cycle intensity-mode line,
and a Nutritionniste refusal routes the goal back to needs-analysis instead of looping
the frame gate.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Modify: `skills/program-optimization/SKILL.md`
- Modify: `skills/performance-coach/SKILL.md`
- Modify: `skills/program-adaptation/SKILL.md`
- Modify: `skills/program-planning/SKILL.md`

- [ ] **Step 1: Extend the harness needles first (failing)**

In `tests/skills/test_structure.py`:

Append to the `test_coach_skill_carries_the_global_rules` needle tuple:

```python
        "program-review",
```

Append to the `test_optimization_skill_protocol` needle tuple:

```python
        "program-review",
        "approved",
        "returned",
```

Append to the `test_planning_skill_protocol` needle tuple:

```python
        "submaximal",
        "intensity mode",
        "needs-analysis",
    ```

(Note: `"needs-analysis"` already passes on the current body — it pins the §1 route
so the new refusal route cannot cannibalize it.)

Append to the `test_adaptation_skill_protocol` needle tuple:

```python
        "program-review",
        "approved",
```

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — coach, optimization, planning ("submaximal", "intensity mode") and
adaptation needles missing.

- [ ] **Step 2: Gate the Optimizer's save**

In `skills/program-optimization/SKILL.md`:

Frontmatter description — replace the last clause:

```
  exercise, iterates until the athlete validates, and saves the program through
  the versioned store.
```

with:

```
  exercise, iterates until the athlete validates, hands the draft to
  program-review, and saves through the versioned store only on an APPROVED
  verdict.
```

Replace the `## 5. Save and deliver` heading and its first bullet block — old:

```markdown
## 5. Save and deliver

- **Nutrition annex:** call `read_nutrition_frame`. If a frame exists, quote
  its daily kcal and protein target in the program header ("nutrition frame vN:
  X kcal/day, Y g protein/day"); if it errors, there is no annex — never invent
  one.
- Run `check_citations` over the full program text (skeleton section included);
  fix anything flagged.
```

new:

```markdown
## 5. The gate, then save and deliver

- **Nutrition annex:** call `read_nutrition_frame`. If a frame exists, quote
  its daily kcal and protein target in the program header ("nutrition frame vN:
  X kcal/day, Y g protein/day"); if it errors, there is no annex — never invent
  one.
- **Hand the athlete-validated draft to program-review (le Contrôleur) — the
  mandatory delivery gate.** Only an APPROVED verdict authorizes the save. A
  RETURNED verdict comes back with quoted objections: fix session-level
  objections (loads, exercise choice, layout) here and resubmit; structural
  objections (model, phases, weekly targets) go back to program-planning with
  the objection quoted. Never save a draft the Contrôleur has not approved.
- On APPROVED: run `check_citations` over the full program text (skeleton
  section included); fix anything flagged.
```

(The `save_program` bullet and everything after it stay verbatim.)

- [ ] **Step 3: Insert the gate into performance-coach routing**

In `skills/performance-coach/SKILL.md`, in the "After a skill hands back" list,
replace:

```markdown
- Skeleton handed over by program-planning → program-optimization
- Check-in shows poor adherence, plateau, pain, or schedule change → program-adaptation
```

with:

```markdown
- Skeleton handed over by program-planning → program-optimization
- Draft validated by the athlete but not yet reviewed → program-review (the
  mandatory delivery gate; only its APPROVED verdict lets program-optimization
  save and deliver)
- Check-in shows poor adherence, plateau, pain, or schedule change → program-adaptation
```

And in `## Modes`, replace:

```markdown
- Mode A (one-shot): onboarding → needs analysis → deep research → planning →
  optimization → deliver. Still save everything through the memory tools.
```

with:

```markdown
- Mode A (one-shot): onboarding → needs analysis → deep research → planning →
  optimization → review → deliver. Still save everything through the memory tools.
```

(The coach's frontmatter `tools:` list is unchanged — routing names are skill names,
not tools.)

- [ ] **Step 4: Gate adapted programs too**

In `skills/program-adaptation/SKILL.md`, in `## 3. Confirm, then version`, replace:

```markdown
- Present the proposed vN+1 and ASK the athlete to confirm before saving.
- Run `check_citations` if the proposal cites evidence.
```

with:

```markdown
- Present the proposed vN+1 and ASK the athlete to confirm before saving.
- **Adapted programs pass the same delivery gate as new ones:** hand the
  confirmed vN+1 to program-review (le Contrôleur) and save only on an
  APPROVED verdict — session-level objections are fixed here, structural ones
  route through program-planning. No adapted version is delivered unreviewed.
- Run `check_citations` if the proposal cites evidence.
```

- [ ] **Step 5: The three backlog fixes in program-planning**

In `skills/program-planning/SKILL.md`:

**(a) Qualify the hybrid-peaking clause** (§2, recurring_fixtures bullet) — replace:

```markdown
  `build_peaking_block` appended before it, on top of the in-season weeks —
  justify that hybrid the same way as any other model choice, cited from the
  dossier or labeled coaching judgment.
```

with:

```markdown
  `build_peaking_block` appended before it, on top of the in-season weeks —
  justify that hybrid the same way as any other model choice, cited from the
  dossier or labeled coaching judgment. The tool's test week assumes a 1RM
  test day: its supra-maximal (above-1.0) intensities are for test-day openers
  ONLY, so keep them only when the decisive date IS a 1RM test. Before a
  fixture, cap the final week at high but submaximal intensity and state
  plainly that this deviates from the tool's test-week numbers, and why.
```

**(b) Skeleton intensity-mode line** (§4) — replace the numbered list items 3-4:

```markdown
3. **Weekly targets** — per-muscle set targets and/or endurance
   volume/intensity per week, as numbers.
4. **Constraints the Optimizer must respect** — availability (sessions per
   week), equipment, injuries, split_preferences, and the analysis' injury
   flags.
```

with:

```markdown
3. **Weekly targets** — per-muscle set targets and/or endurance
   volume/intensity per week, as numbers.
4. **Intensity mode per cycle** — state whether each cycle prescribes by RIR
   or by %1RM; the Optimizer's prescription path follows this declaration,
   not a per-exercise choice.
5. **Constraints the Optimizer must respect** — availability (sessions per
   week), equipment, injuries, split_preferences, and the analysis' injury
   flags.
```

**(c) Nutrition-refusal escape hatch** (§5) — replace:

```markdown
  synchronization. The frame must exist (and match) before sessions are
  finalized, so training and deficit are synchronized (no aggressive deficit
  during an intensification block).
- Then route onward to program-optimization, skeleton in the conversation.
```

with:

```markdown
  synchronization. The frame must exist (and match) before sessions are
  finalized, so training and deficit are synchronized (no aggressive deficit
  during an intensification block).
- **The Nutritionniste can refuse.** If nutrition-planning came back with NO
  frame saved and a red flag recorded (an engine refusal, or disordered-eating
  signals), do not loop the frame gate and do not proceed to sessions: route
  the GOAL back to needs-analysis — a goal whose nutrition side was refused
  needs renegotiation, not a program.
- Then route onward to program-optimization, skeleton in the conversation.
```

- [ ] **Step 6: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — all new needles green; tool drift green in both directions
(`program-review` is a skill name, not a tool; the planning edits add no tool names
beyond the already-declared `build_peaking_block`).

- [ ] **Step 7: Commit**

```bash
git add skills/program-optimization/SKILL.md skills/performance-coach/SKILL.md \
        skills/program-adaptation/SKILL.md skills/program-planning/SKILL.md \
        tests/skills/test_structure.py
git commit -m "Wire the program-review gate and fix planning backlog items"
```

---

### Task 3: le Vigile — evolve `training-checkin` + `program-adaptation`

`training-checkin` becomes the watchtower (H1 gains "— le Vigile"): structured-signal
triggers read from `read_sessions`' structured exercises (`memory_tools.log_session`
docstring: "Strength sessions should carry structured exercises → sets {reps,
load_kg, rir}") and `read_checkins`' bodyweight series, compared against the
nutrition frame's trajectory when one exists. Disordered-eating conversational
signals get the same referral language as nutrition-planning §4 — this is the
skill-level resolution of the backlog's "ED signals engine-side" note (rationale:
Conventions, decision 1). `program-adaptation` gains stall-driven diagnosis from the
structured sessions and the strength-vs-hypertrophy plateau distinction, declaring
`weekly_set_targets_for` for the volume answer.

**Files:**
- Modify: `tests/skills/test_structure.py`
- Modify: `skills/training-checkin/SKILL.md` (full rewrite, small file)
- Modify: `skills/program-adaptation/SKILL.md`

- [ ] **Step 1: Extend the harness needles first (failing)**

In `tests/skills/test_structure.py`:

Replace `test_checkin_skill_protocol`'s needle tuple with:

```python
    for needle in (
        "get_time_context",
        "log_checkin",
        "log_session",
        "pain",
        "adherence",
        "fatigue",
        "vigile",
        "stall",
        "failed reps",
        "read_sessions",
        "read_checkins",
        "read_nutrition_frame",
        "bodyweight_kg",
        "weekly_change_kg",
        "drift",
        "recurring_fixtures",
        "refer out",
        "stop prescribing",
    ):
        assert needle in body, f"checkin skill lost: {needle}"
```

Append to the `test_adaptation_skill_protocol` needle tuple (after Task 2's
additions):

```python
        "vigile",
        "under-recovery",
        "under-stimulus",
        "weekly_set_targets_for",
        "rir",
```

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills/test_structure.py -q`
Expected: FAIL — checkin needles (vigile, stall, drift, …) and adaptation needles
(vigile, weekly_set_targets_for) missing.

- [ ] **Step 2: Rewrite training-checkin as le Vigile**

Replace `skills/training-checkin/SKILL.md` in full:

```markdown
---
name: training-checkin
description: Use when a returning athlete with an active program shows up — or
  whenever days have passed since the last contact. Runs the structured check-in,
  logs it, scans the structured signals (load stalls, failed reps, fatigue,
  bodyweight drift off the nutrition frame, fixture pile-up), and routes to
  adaptation when triggers fire.
tools: [read_athlete, get_time_context, read_program, log_checkin, log_session,
        read_sessions, read_checkins, read_nutrition_frame, compute_session_load,
        write_profile]
---

# Training Check-in — le Vigile

Follow performance-coach global rules. The check-in is short, warm, and structured —
a coach's five minutes, not an interrogation. Confirm profile facts via
`read_athlete` before contrasting them with today's answers. Between sessions you
are the watchtower: the structured signals below fire from the DATA, whether or
not the athlete names the problem.

## Protocol

1. Open by quoting `get_time_context`: "your last update was N days ago; W weeks to
   [goal]". If days_since_last_session is null, nothing was ever logged — say so and
   start logging today.
2. Backfill: call `read_sessions` for the window since last contact to see what's
   already logged, then ask which planned sessions are still missing. `log_session`
   each one the athlete reports — for strength sessions collect the structured
   exercises → sets {reps, load_kg, rir}; the stall triggers below read them.
   Offer `compute_session_load` so the athlete sees their load trend forming.
3. Ask, one at a time: adherence (sessions done vs planned, as a %), fatigue (1-10),
   any pain or niggles (RED FLAG rules apply — an affirmative answer here overrides
   everything else), body-weight change if relevant, schedule changes coming.
   bodyweight_kg logged at check-ins is the time series the triggers read; the
   profile's static weight is updated via `write_profile` only when weight has
   durably moved.
4. `log_checkin` with what you collected. Quote the stored days_since_last back.

## Structured-signal triggers — scan them at every check-in

After logging, scan `read_sessions` and `read_checkins` for the recent window:

- **Load stall:** the same exercise shows no load or rep increase across 3+
  logged sessions → plateau suspicion, route to program-adaptation.
- **Failed reps:** logged reps land well below the program's target range
  (`read_program` for the targets) on repeated exposures → program-adaptation.
- **Fatigue ≥ 8** → program-adaptation.
- **Bodyweight drift:** when a nutrition frame exists, call
  `read_nutrition_frame` and compare the check-ins' bodyweight_kg series
  against the frame's weekly_change_kg trajectory. Drift >2% off trajectory,
  or movement in the wrong direction across 2+ consecutive check-ins → route
  to nutrition-planning for a frame recalculation AND flag it to
  program-adaptation (the training side may need to move too).
- **Fixture pile-up:** calendar_type is recurring_fixtures and the athlete
  reports extra matches beyond what the program assumed → program-adaptation.

## Red flags

- Pain: record it in the profile injuries — read the current profile, add the
  injury, `write_profile` the FULL document (whole-document replace). Stop
  loading that pattern, recommend a professional if it is more than a niggle,
  then program-adaptation to reshape the week.
- Disordered-eating signals in conversation (fear of eating, compulsive
  restriction, purging, pushing to bypass the safety floors): stop prescribing,
  refer out to a health professional, and record the flag — the same rule
  nutrition-planning applies. The engine hard-guards the numbers; the
  conversational signals are YOURS to catch.

## Route

- Any trigger above → its named destination (program-adaptation, or
  nutrition-planning + program-adaptation for bodyweight drift).
- Adherence < 70% or schedule change → program-adaptation.
- All green → encourage, preview the next block (`read_program`), done. If
  `read_athlete`'s program_version is null there is no program to preview —
  route to program-planning instead.
```

- [ ] **Step 3: Extend program-adaptation's diagnosis**

In `skills/program-adaptation/SKILL.md`:

Frontmatter `tools:` — add `weekly_set_targets_for` (insert after
`assess_bodycomp_goal,`):

```
        assess_bodycomp_goal, weekly_set_targets_for, prescribe_load, estimate_1rm,
```

In `## 1. Diagnose from data, not vibes`, after the `read_sessions` /
`read_checkins` bullet, insert:

```markdown
- Stall and failed-rep triggers arrive from training-checkin (le Vigile) with
  structured sessions behind them — diagnose from the exercise data, not the
  trigger label: loads falling ACROSS THE BOARD (multiple exercises, reps
  missed at previously handled loads) reads as under-recovery; everything
  completed easily (RIR consistently high, rep targets exceeded) reads as
  under-stimulus.
```

In `## 2. Propose the change`, after the first paragraph (ending "route through
program-planning instead of patching sessions in place."), insert:

```markdown
- Plateaus split by goal. A STRENGTH plateau is addressed through intensity
  and specificity (heavier exposures, work closer to the tested lift), not
  more sets. A HYPERTROPHY plateau is addressed through volume — raise the
  weekly sets within the `weekly_set_targets_for` landmarks for the athlete's
  training age, never past maximum_adaptive_sets.
```

- [ ] **Step 4: Run the harness**

Run: `env -u VIRTUAL_ENV uv run pytest tests/skills -q`
Expected: PASS — checkin declares 10 tools, all mentioned; no undeclared tool
namedropped (skill names nutrition-planning / program-adaptation / program-planning
are not tools; `weekly_change_kg` and `bodyweight_kg` are schema fields, not tool
names); adaptation's new `weekly_set_targets_for` is declared AND mentioned;
anti-fabrication green (no locators added).

- [ ] **Step 5: Commit**

```bash
git add skills/training-checkin/SKILL.md skills/program-adaptation/SKILL.md \
        tests/skills/test_structure.py
git commit -m "Extend check-in and adaptation with Vigile structured triggers"
```

---

### Task 4: README + backlog + full verification sweep

The public story catches up: the mermaid pipeline shows the gate, the changelog
counts eleven skills and names the guardians, any save-flow prose reflects "the
Optimizer saves only on the Contrôleur's APPROVED verdict", and the graduated
backlog items are deleted (backlog convention: items graduate into a plan task and
get deleted there).

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/BACKLOG.md`
- Verify only: `docs/installing.md` (copies `skills/*` wholesale; no skill-name
  enumeration expected — verify, don't assume)

- [ ] **Step 1: README mermaid + changelog bullet**

Mermaid SK node (line ~196) — replace:

```
planning · optimization · nutrition · check-ins · adaptation]
```

with:

```
planning · optimization · nutrition · review · check-ins · adaptation]
```

Changelog bullet (line ~233) — replace the whole "✅ Ten coaching skills …" bullet
(all seven lines) with:

```markdown
- ✅ Eleven coaching skills (Claude Code plugin format): session rituals, onboarding
  with a multi-lift 1RM inventory, needs analysis with honest multi-goal feasibility
  verdicts and counter-proposals, deep multilingual research dossiers, evidence-cited
  periodization planning (le Planificateur), athlete-validated session optimization
  with engine-computed loads (l'Optimiseur), a quantified nutrition frame behind hard
  safety guards (le Nutritionniste), a mandatory delivery gate running a compliance
  checklist plus an adversarial second opinion (le Contrôleur), signal-driven
  check-ins watching load stalls and bodyweight drift (le Vigile), versioned
  adaptation — each eval-guarded against tool drift and fabricated references
```

- [ ] **Step 2: Sweep for stale save-flow prose**

Run: `grep -rn "Optimizer saves\|saves the program\|sign-off\|[Tt]en coaching\|ten skills" README.md docs/installing.md`
Expected: no hits after Step 1 (the current README has none — verify). Any hit found
must be rewritten to say the save happens only on program-review's APPROVED verdict.
Also confirm `docs/installing.md` needs no change: it copies `skills/*` wholesale,
does not enumerate skill names, and the tool count stays 47 —
`grep -n "47\|skills" docs/installing.md` to verify.

- [ ] **Step 3: Graduate the backlog items**

In `docs/superpowers/BACKLOG.md`:

1. Delete the entire section `## Open items for the guardians phase (from phase 5
   final review, 2026-07-12)` (all three bullets — peaking docstring, skeleton
   intensity mode, nutrition refusal escape hatch — landed in Task 2).
2. Delete the phase-2b bullet `**Eating-disorder signal refusal engine-side**`
   (resolved at skill level in Task 3 and nutrition-planning §4; rationale recorded
   in this plan's Conventions, decision 1).
3. Trim the phase-1 bullet `**Profile.weight_kg vs CheckinEntry.bodyweight_kg**` —
   replace:

```markdown
- **`Profile.weight_kg` vs `CheckinEntry.bodyweight_kg`** — same quantity,
  two names (static fact vs time series). The Interview/Vigile skills must
  state the mapping when they are written.
```

with:

```markdown
- **`Profile.weight_kg` vs `CheckinEntry.bodyweight_kg`** — same quantity,
  two names (static fact vs time series). The Vigile states the mapping
  (guardians phase, 2026-07-12); the Interview skill must state it too when
  next touched.
```

- [ ] **Step 4: Full suite + zero-warning gate**

Run: `env -u VIRTUAL_ENV uv run pytest -q`
Expected: all green — skills harness (11 skills, structure, tool drift both
directions, anti-fabrication), memory, server, engine, evidence, reports.

Run: `env -u VIRTUAL_ENV uv run ruff format --check . && env -u VIRTUAL_ENV uv run ruff check . && env -u VIRTUAL_ENV uv run ty check`
Expected: clean output, no warnings.

- [ ] **Step 5: Residual greps + line budget**

Run: `grep -rn "program-review" skills/ | grep -v "skills/program-review/"`
Expected: hits in performance-coach (routing), program-optimization (gate),
program-adaptation (gate) — and nowhere else.

Run: `grep -rn "guardians phase" docs/superpowers/BACKLOG.md`
Expected: no hits.

Run: `wc -l skills/*/SKILL.md`
Expected: every skill under ~150 lines (program-review ~110, training-checkin ~85,
program-planning ~125, program-optimization ~125, program-adaptation ~95).

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/BACKLOG.md
git commit -m "Update README and backlog for the guardians phase"
git status --short
```

Expected: clean tree.
