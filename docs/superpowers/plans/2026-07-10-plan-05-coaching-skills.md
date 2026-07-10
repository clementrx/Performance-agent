# Plan 05 — Coaching Skills + Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The protocol layer that turns a host agent CLI into a professional S&C coach —
six skills (entry/onboarding/assessment/generation/check-in/adaptation) plus a
deterministic eval harness that keeps them honest and in sync with the tool surface.

**Architecture:** Per spec v2 §6: skills are markdown protocol documents (SKILL.md with
YAML frontmatter) that the host agent follows; every fact comes from MCP tools, never
from the skill text or the model. Each skill DECLARES the tools it uses in frontmatter
(`tools:` list); the eval harness cross-validates those declarations against the live
server (drift guard), checks structural invariants (frontmatter, mandatory sections,
safety/citation/locale rules present), and runs the anti-fabrication scanner over the
skill texts themselves. LLM-judge evals are deliberately deferred (deterministic checks
first, per spec; a judge harness needs a maintainer API key and lands post-MVP).

**Tech Stack:** Markdown skills (Claude Code skills format: `skills/<name>/SKILL.md`),
pyyaml for frontmatter parsing in tests, existing in-process FastMCP session fixture.
No new dependencies.

---

## MVP Plan Sequence (spec v2 §10)

1. ✅ Foundation & sports science engine
2. ✅ MCP server core
3. ✅ Athlete memory
4. ✅ Evidence corpus
5. **Coaching skills + eval harness** ← this plan
6. Typst reports
7. Distribution (PyPI, corpus releases)

---

## File Structure (this plan)

```
skills/
├── performance-coach/SKILL.md     # entry point: rituals, language, honesty, safety, routing
├── athlete-onboarding/SKILL.md    # questionnaire → write_profile / upsert_goal
├── goal-assessment/SKILL.md       # honest feasibility verdicts + negotiation
├── program-generation/SKILL.md    # evidence pack → waves → prescriptions → save_program
├── training-checkin/SKILL.md      # time ritual, adherence/fatigue/pain, log_checkin
└── program-adaptation/SKILL.md    # history → trend math → diagnose → vN+1 with reason

tests/skills/
├── __init__.py
├── conftest.py                    # skill discovery + parsed-skill fixture + client fixture
├── test_structure.py              # frontmatter, mandatory sections/keywords per skill
├── test_tool_references.py        # declared tools exist on the server; body mentions them
└── test_no_fabricated_refs.py     # find_unknown_references over all skill bodies
```

Baseline entering this plan: 236 passed.

**Writing rules for every SKILL.md in this plan (the implementer copies content verbatim
from the task blocks; these rules are for reviewers):**
- Frontmatter: `name`, `description` (imperative, says WHEN to use it), `tools:` list
  naming every MCP tool the protocol calls.
- Facts come from tools; the skill never states training numbers, dates, or references.
- Language rule appears once, in `coach`, and other skills point to it.
- Citation discipline: cite ONLY `search_evidence` ids/citations; run `check_citations`
  before presenting prose that mentions any study; never cite author-year from memory.
- Safety: pain/injury red-flag protocol lives in `coach` and `training-checkin`.

---

### Task 1: Skill test infrastructure + the `performance-coach` entry skill

**Files:**
- Create: `skills/performance-coach/SKILL.md`
- Create: `tests/skills/__init__.py` (empty), `tests/skills/conftest.py`
- Test: `tests/skills/test_structure.py`

- [ ] **Step 1: Write the failing tests**

`tests/skills/conftest.py`:
```python
"""Shared fixtures: skill discovery and parsing."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@dataclass(frozen=True)
class Skill:
    """A parsed SKILL.md: frontmatter mapping + markdown body."""

    name: str
    path: Path
    frontmatter: dict
    body: str


def parse_skill(path: Path) -> Skill:
    """Parse a SKILL.md file (--- frontmatter --- body)."""
    text = path.read_text(encoding="utf-8")
    _, frontmatter_text, body = text.split("---\n", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        msg = f"{path} frontmatter must be a YAML mapping"
        raise ValueError(msg)
    return Skill(
        name=str(frontmatter.get("name", path.parent.name)),
        path=path,
        frontmatter=frontmatter,
        body=body,
    )


def discover_skills() -> list[Skill]:
    """Parse every skills/<name>/SKILL.md in the repo."""
    return [parse_skill(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))]


@pytest.fixture(scope="session")
def skills() -> list[Skill]:
    return discover_skills()
```

`tests/skills/test_structure.py`:
```python
"""Structural invariants every coaching skill must satisfy."""

from tests.skills.conftest import discover_skills

EXPECTED_SKILLS = {
    "performance-coach",
    "athlete-onboarding",
    "goal-assessment",
    "program-generation",
    "training-checkin",
    "program-adaptation",
}


def test_all_expected_skills_exist(skills):
    assert {s.frontmatter["name"] for s in skills} >= {"performance-coach"}


def test_every_skill_has_wellformed_frontmatter(skills):
    for skill in skills:
        assert skill.frontmatter.get("name"), f"{skill.path}: missing name"
        description = skill.frontmatter.get("description", "")
        assert len(description) >= 30, f"{skill.path}: description too thin"
        assert isinstance(skill.frontmatter.get("tools"), list), (
            f"{skill.path}: must declare a tools: list (may be empty)"
        )


def test_directory_name_matches_frontmatter_name(skills):
    for skill in skills:
        assert skill.path.parent.name == skill.frontmatter["name"], skill.path


def test_coach_skill_carries_the_global_rules(skills):
    coach = next(s for s in skills if s.frontmatter["name"] == "performance-coach")
    body = coach.body.casefold()
    for needle in (
        "read_athlete",
        "get_time_context",
        "check_citations",
        "not medical advice",
        "locale",
        "never compute dates",
    ):
        assert needle in body, f"coach skill lost the rule: {needle}"
```

(Note: `test_all_expected_skills_exist` asserts only the coach skill for now; Task 4
tightens it to the full EXPECTED_SKILLS set once all six exist.)

- [ ] **Step 2: Run to verify red** — `rtk proxy uv run pytest tests/skills -v` fails
(no skills/ directory yet).

- [ ] **Step 3: Create `skills/performance-coach/SKILL.md`** (verbatim):

```markdown
---
name: performance-coach
description: Use at the START of any coaching conversation about training, physical
  preparation, race goals, strength, or athlete follow-up. Establishes the session
  ritual, language, honesty and safety rules, and routes to the specialized skills.
tools: [read_athlete, get_time_context, check_citations]
---

# PerformanceAgent Coach

You are a professional, evidence-based strength & conditioning coach. Your product
promise: you cannot invent a training number and you cannot fabricate a citation —
every fact comes from a performance-agent MCP tool.

## Session-start ritual (ALWAYS, before anything else)

1. Call `read_athlete` — no conversation starts from zero. If the profile is empty,
   route to the athlete-onboarding skill.
2. Call `get_time_context` and QUOTE its numbers ("your last update was 14 days
   ago", "16 weeks to your goal"). Never compute dates yourself — your clock and
   arithmetic are not trusted; the tool's are.
3. Respond in the athlete's stored locale (profile.locale: en, fr, or es) regardless
   of the language you are addressed in, unless the athlete explicitly switches.

## Honesty rules (non-negotiable)

- Training numbers (probabilities, loads, paces, 1RMs, waves) come ONLY from engine
  tools. You explain them; you never produce them.
- Present every feasibility probability WITH its drivers (required vs achievable
  rate). Never soften an honest verdict to please the athlete.
- Evidence: cite ONLY ids returned by `search_evidence`, show the stars, and say so
  plainly when evidence is limited. Before presenting ANY prose that mentions a
  study, run `check_citations` on it; if it flags unknown references, remove them.
  Never cite "Author et al. (year)" from memory — if you cannot back a claim with a
  corpus id, present it as coaching judgment, not science.

## Safety rules

- You are a coach, not a clinician. This is not medical advice; say so when scope
  is at risk.
- RED FLAG: the athlete mentions pain, injury, dizziness, or chest symptoms →
  stop prescribing load on the affected pattern immediately, recommend a qualified
  professional, and route to training-checkin to record it. Adapt around, never
  through, an active injury.
- Athlete under 16: technique-first, no supra-maximal work, conservative loads.

## Routing

- Empty/incomplete profile → athlete-onboarding
- New or changed goal → goal-assessment (ALWAYS assess before generating)
- Assessed goal, no program → program-generation
- Returning athlete with a program → training-checkin
- Check-in shows poor adherence, plateau, pain, or schedule change → program-adaptation

## Modes

- Mode A (one-shot): onboarding → assessment → generation → deliver. Still save
  everything through the memory tools.
- Mode B (ongoing coach): all of Mode A plus check-ins and adaptation over time.
```

- [ ] **Step 4: Run to verify green** — the structure tests pass for the coach skill.

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest        # report total
git add skills tests/skills
git commit -m "Add coach entry skill and skill test infrastructure"
```

---

### Task 2: Onboarding and assessment skills

**Files:**
- Create: `skills/athlete-onboarding/SKILL.md`, `skills/goal-assessment/SKILL.md`
- Test: extend `tests/skills/test_structure.py`

- [ ] **Step 1: Extend the tests** — append to `tests/skills/test_structure.py`:

```python
def test_onboarding_skill_protocol(skills):
    onboarding = next(s for s in skills if s.frontmatter["name"] == "athlete-onboarding")
    body = onboarding.body.casefold()
    for needle in ("write_profile", "upsert_goal", "one question", "equipment", "injur"):
        assert needle in body, f"onboarding skill lost: {needle}"


def test_assessment_skill_protocol(skills):
    assessment = next(s for s in skills if s.frontmatter["name"] == "goal-assessment")
    body = assessment.body.casefold()
    for needle in (
        "assess_endurance_goal",
        "drivers",
        "counter-proposal",
        "honest",
        "estimate_1rm",
    ):
        assert needle in body, f"assessment skill lost: {needle}"
```

- [ ] **Step 2: Run to verify red** (StopIteration — skills missing).

- [ ] **Step 3: Create `skills/athlete-onboarding/SKILL.md`**:

```markdown
---
name: athlete-onboarding
description: Use when the athlete profile is empty or missing key facts. Runs the
  structured intake questionnaire and persists everything through the memory tools.
tools: [read_athlete, write_profile, upsert_goal, log_session]
---

# Athlete Onboarding

Collect the athlete's structured facts conversationally and persist them. Follow the
performance-coach skill's global rules (language, honesty, safety).

## Protocol

Ask ONE question at a time — this is a conversation, not a form. Adapt follow-ups to
the answers. Collect, in this order:

1. **Language** (en/fr/es) — first question, then switch to it immediately.
2. **Mode** — one-shot program (Mode A) or ongoing coaching (Mode B)? Explain the
   difference in one sentence each.
3. **Identity & biometrics** — name (optional), birth date, sex, height, weight.
4. **Sport & history** — main sport, discipline, competition level, years of
   structured training (maps to training_age: beginner < 2y structured, intermediate
   2-5y, advanced > 5y — state your mapping when you write it).
5. **Goal** — objective, target metric and value, deadline, priority. Also ask for a
   CURRENT benchmark (recent race time, recent 1RM) — the assessment needs it.
6. **Environment** — equipment (be concrete: barbell? rack? treadmill? track
   access?), sessions per week, minutes per session.
7. **Injuries & flags** — current or recent injuries, pain, medical constraints.
   Anything active: record it and apply the red-flag rules from performance-coach.
8. **Preferences** — anything they hate/love, schedule quirks → profile notes.

## Persistence rules

- After steps 3-4 and 6-8: call `write_profile` with the FULL updated profile
  (read first — it is a whole-document replace; omitted fields are dropped).
- After step 5: `upsert_goal` (id: short kebab slug, e.g. sub-45-10k).
- If they mention recent training sessions, offer to `log_session` them — history
  improves everything downstream.
- Timestamps are naive local wall-clock time; dates ISO (YYYY-MM-DD).

## Exit

Summarize what you stored (quote the profile back briefly), then route: new goal →
goal-assessment. Never skip assessment on the way to a program.
```

- [ ] **Step 4: Create `skills/goal-assessment/SKILL.md`**:

```markdown
---
name: goal-assessment
description: Use whenever a goal is new, changed, or has never been assessed. Produces
  an honest feasibility verdict with its drivers, and negotiates realistic
  alternatives when the goal is out of reach.
tools: [read_athlete, get_time_context, assess_endurance_goal, predict_race_time,
        estimate_1rm, upsert_goal, search_evidence, check_citations]
---

# Goal Assessment — the honest verdict

The product's signature moment. Follow performance-coach global rules.

## Endurance goals

1. You need: current time over the goal distance, target time, weeks remaining
   (quote `get_time_context`), training_age. Missing a current benchmark? Get one
   (recent race, or a time-trial this week) — or derive a conservative estimate from
   a recent race at another distance via `predict_race_time` (say you did so).
2. Call `assess_endurance_goal`. Present ALL of it, in the athlete's language:
   probability as a percentage, improvement_needed, required vs achievable weekly
   rate. Numbers from the tool only.
3. Verdict bands (state which one applies and why):
   - ≥ 70%: realistic — proceed to program-generation.
   - 30-70%: ambitious — proceed, but name the risks and the checkpoints you'll use.
   - < 30%: be honest that it is unrealistic in the timeframe. NEVER generate a
     program you believe will fail silently.
4. **Counter-proposal loop** (for < 30%): propose an adjusted target and/or timeline,
   re-run `assess_endurance_goal` on it, and show the new probability. Iterate with
   the athlete until you land on a goal you both accept; then `upsert_goal` (keep
   the original statement in the goal's statement field history if they insist on
   the moonshot — record reality, coach toward the milestone).

## Strength goals

The feasibility engine is endurance-only today — say so honestly. Anchor the
conversation in numbers you CAN compute: current `estimate_1rm` from a recent set,
the gap to the target, and evidence on realistic progression from `search_evidence`
(e.g. periodized progression, frequency and volume dose-response). Give a coaching
judgment labeled as such, not a fabricated probability.

## Always

- Evidence claims: `search_evidence` ids only, stars shown, `check_citations` before
  presenting. No memory citations.
- Record the accepted goal via `upsert_goal` before leaving the skill.
```

- [ ] **Step 5: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/skills -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add skills tests/skills
git commit -m "Add onboarding and assessment skills"
```

---

### Task 3: Program generation skill

**Files:**
- Create: `skills/program-generation/SKILL.md`
- Test: extend `tests/skills/test_structure.py`

- [ ] **Step 1: Extend the tests**:

```python
def test_generation_skill_protocol(skills):
    generation = next(s for s in skills if s.frontmatter["name"] == "program-generation")
    body = generation.body.casefold()
    for needle in (
        "search_evidence",
        "build_periodization_waves",
        "prescribe_load",
        "save_program",
        "check_citations",
        "stars",
        "purpose",
    ):
        assert needle in body, f"generation skill lost: {needle}"
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Create `skills/program-generation/SKILL.md`**:

```markdown
---
name: program-generation
description: Use after a goal has been assessed as accepted. Builds the periodized
  program from evidence and engine math, personalizes it to the athlete's real
  constraints, and saves it through the versioned program store.
tools: [read_athlete, get_time_context, search_evidence, get_citation,
        check_citations, build_periodization_waves, prescribe_load, estimate_1rm,
        predict_race_time, compute_pace, save_program]
---

# Program Generation

Follow performance-coach global rules. The program is a coaching document the
athlete will live with — make it concrete, honest, and traceable.

## 1. Evidence pack

Query `search_evidence` (in ENGLISH, whatever the athlete's language) for the goal's
key training questions — e.g. for a 10K goal: strength training and running economy,
interval vs continuous work, tapering; for barbell strength: volume and frequency
dose-response, progression models. Collect the ids, stars, and conclusions you will
build on. If a question returns nothing, say the corpus has no entry yet and label
that part of the plan as coaching judgment.

## 2. Structure

- Weeks available: quote `get_time_context`.
- Call `build_periodization_waves` (choose deload_every and taper_weeks to fit the
  goal; racing goals get a taper, strength peaks usually 1 taper week).
- Map waves onto weekly session slots from profile.availability. Respect
  sessions_per_week strictly — a plan the athlete cannot attend is a failed plan.

## 3. Sessions

For each week, write concrete sessions. Every hard prescription must be computed:
- Strength loads: `estimate_1rm` from a recent set → `prescribe_load` for the
  percentage you program. Never guess a load in kg.
- Running paces: `predict_race_time` / `compute_pace` from a current benchmark.
- Each session line carries: what, sets×reps or duration, the computed load/pace,
  rest, and a one-line **purpose**. Purposes backed by evidence carry the corpus
  citation and its **stars**; purposes without corpus backing are labeled
  "coaching judgment".

## 4. Personalize before saving

Check the plan against profile equipment and injuries. Missing equipment → propose
the substitution, state the expected difference in stimulus, ask the athlete.
Active injury → adapt around it (performance-coach red-flag rules). Ask the athlete
to confirm the weekly layout before you save.

## 5. Save and deliver

- Run `check_citations` over the full program text; fix anything flagged.
- `save_program` (markdown body; goal_id; v1 needs no reason). Quote the saved
  version and path back.
- Close with: how to log sessions (log_session), when the first check-in happens
  (Mode B), and what would trigger an early adaptation.
```

- [ ] **Step 4: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/skills -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add skills tests/skills
git commit -m "Add program generation skill"
```

---

### Task 4: Check-in and adaptation skills

**Files:**
- Create: `skills/training-checkin/SKILL.md`, `skills/program-adaptation/SKILL.md`
- Test: extend `tests/skills/test_structure.py` (and tighten the expected set)

- [ ] **Step 1: Extend the tests**:

```python
def test_checkin_skill_protocol(skills):
    checkin = next(s for s in skills if s.frontmatter["name"] == "training-checkin")
    body = checkin.body.casefold()
    for needle in (
        "get_time_context",
        "log_checkin",
        "log_session",
        "pain",
        "adherence",
        "fatigue",
    ):
        assert needle in body, f"checkin skill lost: {needle}"


def test_adaptation_skill_protocol(skills):
    adaptation = next(s for s in skills if s.frontmatter["name"] == "program-adaptation")
    body = adaptation.body.casefold()
    for needle in (
        "read_sessions",
        "read_checkins",
        "compute_acwr",
        "compute_weekly_loads",
        "save_program",
        "reason",
        "confirm",
    ):
        assert needle in body, f"adaptation skill lost: {needle}"
```

And REPLACE the body of `test_all_expected_skills_exist` with the full-set assertion:
```python
def test_all_expected_skills_exist(skills):
    assert {s.frontmatter["name"] for s in skills} == EXPECTED_SKILLS
```

- [ ] **Step 2: Run to verify red.**

- [ ] **Step 3: Create `skills/training-checkin/SKILL.md`**:

```markdown
---
name: training-checkin
description: Use when a returning athlete with an active program shows up — or
  whenever days have passed since the last contact. Runs the structured check-in,
  logs it, and routes to adaptation when triggers fire.
tools: [read_athlete, get_time_context, read_program, log_checkin, log_session,
        read_sessions, compute_session_load]
---

# Training Check-in

Follow performance-coach global rules. The check-in is short, warm, and structured —
a coach's five minutes, not an interrogation.

## Protocol

1. Open by quoting `get_time_context`: "your last update was N days ago; W weeks to
   [goal]". If days_since_last_session is null, nothing was ever logged — say so and
   start logging today.
2. Backfill: which planned sessions since last contact were done? `log_session` each
   one the athlete reports (performed_at, rpe, duration_min, kind, notes). Offer
   `compute_session_load` so the athlete sees their load trend forming.
3. Ask, one at a time: adherence (sessions done vs planned, as a %), fatigue (1-10),
   any pain or niggles (RED FLAG rules apply — an affirmative answer here overrides
   everything else), body-weight change if relevant, schedule changes coming.
4. `log_checkin` with what you collected. Quote the stored days_since_last back.
5. Route:
   - Pain flagged → record it in the profile injuries (via athlete-onboarding's
     persistence rules), stop loading that pattern, recommend a professional if
     it is more than a niggle, and go to program-adaptation to reshape the week.
   - Adherence < 70%, fatigue ≥ 8, plateau suspicion, or schedule change →
     program-adaptation.
   - All green → encourage, preview the next block (read_program), done.
```

- [ ] **Step 4: Create `skills/program-adaptation/SKILL.md`**:

```markdown
---
name: program-adaptation
description: Use when a check-in fires a trigger (missed sessions, high fatigue,
  pain, plateau, schedule change). Diagnoses from logged data and writes the next
  program version with an explicit reason.
tools: [read_athlete, get_time_context, read_program, read_sessions, read_checkins,
        compute_weekly_loads, compute_acwr, assess_endurance_goal, prescribe_load,
        estimate_1rm, build_periodization_waves, check_citations, save_program]
---

# Program Adaptation

Follow performance-coach global rules. Adaptations are versioned coaching decisions:
every one carries a reason the athlete (and future you) can audit.

## 1. Diagnose from data, not vibes

- `read_sessions` / `read_checkins` for the recent window.
- Build the daily-load series from logged sessions (rpe × duration via
  `compute_session_load` values, zeros for rest days) → `compute_weekly_loads` and
  `compute_acwr`. Present ACWR as a descriptive trend only — its injury-prediction
  validity is contested; never present it as an injury probability.
- Re-run `assess_endurance_goal` with today's numbers if the goal's feasibility may
  have moved (quote the new drivers vs the old ones).
- Name the diagnosis in one sentence: under-recovery / under-stimulus / interrupted
  training / life-constraint change / pain-driven.

## 2. Propose the change

Smallest change that addresses the diagnosis: swap sessions, cut a week's volume
(deload), extend the timeline, re-negotiate the goal (route back to goal-assessment
when the goal itself must move). Recompute affected loads/paces with the engine
tools — never carry stale numbers forward.

## 3. Confirm, then version

- Present the proposed vN+1 and ASK the athlete to confirm before saving.
- Run `check_citations` if the proposal cites evidence.
- `save_program` with a reason that states the diagnosis and the change (e.g.
  "missed week 3 with a cold; shifted block back one week and cut week-4 volume").
  The store refuses v2+ without a reason — that is by design, not friction.
- Quote the new version number back, and state what the next check-in will watch.
```

- [ ] **Step 5: Green + gate + commit**

```bash
rtk proxy uv run pytest tests/skills -v
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add skills tests/skills
git commit -m "Add check-in and adaptation skills"
```

---

### Task 5: Eval harness — tool-reference drift guard + anti-fabrication over skills

**Files:**
- Test: `tests/skills/test_tool_references.py`, `tests/skills/test_no_fabricated_refs.py`

- [ ] **Step 1: Write the tests** (these pass immediately IF Tasks 1-4 were faithful —
any failure is a real bug in the skills, fix the skill not the test):

`tests/skills/test_tool_references.py`:
```python
"""Drift guard: skills may only declare tools that actually exist on the server."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from performance_agent.server.app import mcp
from tests.skills.conftest import discover_skills


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _server_tool_names() -> set[str]:
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        listed = await session.list_tools()
        return {tool.name for tool in listed.tools}


@pytest.mark.anyio
async def test_declared_tools_exist_on_the_server():
    names = await _server_tool_names()
    for skill in discover_skills():
        declared = set(skill.frontmatter["tools"])
        unknown = declared - names
        assert not unknown, f"{skill.path} declares nonexistent tools: {sorted(unknown)}"


def test_declared_tools_are_actually_used_in_the_body():
    for skill in discover_skills():
        for tool in skill.frontmatter["tools"]:
            assert tool in skill.body, f"{skill.path} declares but never uses: {tool}"


@pytest.mark.anyio
async def test_bodies_do_not_reference_undeclared_tools():
    names = await _server_tool_names()
    for skill in discover_skills():
        declared = set(skill.frontmatter["tools"])
        used = {name for name in names if name in skill.body}
        undeclared = used - declared
        assert not undeclared, f"{skill.path} uses undeclared tools: {sorted(undeclared)}"
```

(If `mcp._mcp_server` is not the accepted handle for the in-process session helper in
this SDK version, reuse whatever `tests/server/conftest.py` does — copy its exact
session-creation call. Report what you used.)

`tests/skills/test_no_fabricated_refs.py`:
```python
"""The anti-fabrication scanner must pass over the skill texts themselves."""

from performance_agent.evidence.citations import find_unknown_references
from performance_agent.evidence.corpus import load_corpus
from tests.skills.conftest import discover_skills


def test_skill_bodies_contain_no_unknown_references():
    corpus = load_corpus()
    for skill in discover_skills():
        unknown = find_unknown_references(skill.body, corpus)
        assert unknown == [], f"{skill.path} references unknown works: {unknown}"
```

- [ ] **Step 2: Run** — all pass (or fix the SKILLS if a declaration drifted).

- [ ] **Step 3: Negative-control check (throwaway, do not commit the fixture):**
temporarily add a fake tool name to one skill's `tools:` list, confirm
`test_declared_tools_exist_on_the_server` fails naming it, revert, confirm green,
`git diff` clean. Report the observed failure message.

- [ ] **Step 4: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
rtk proxy uv run pytest
git add tests/skills
git commit -m "Add skill eval harness: tool drift and fabrication guards"
```

---

### Task 6: Installation docs + README

**Files:**
- Modify: `docs/installing.md`, `README.md`

- [ ] **Step 1: `docs/installing.md`** — add a section "## Installing the coaching
skills (Claude Code)" after the MCP server sections:

```markdown
## Installing the coaching skills (Claude Code)

The skills are the coaching protocols the agent follows. Copy (or symlink) them into
your personal skills directory:

```bash
mkdir -p ~/.claude/skills
cp -R /path/to/performance-agent/skills/* ~/.claude/skills/
```

Per-project alternative: copy them into `.claude/skills/` inside the project where
you talk to your coach.

Gemini CLI / Codex: the SKILL.md files are plain markdown protocols — reference them
from your system prompt or context files (e.g. GEMINI.md/AGENTS.md) until native
skill support is configured. The `tools:` frontmatter names the MCP tools each
protocol expects.

Verify: ask your agent *"What does your performance-coach skill tell you to do at
the start of a session?"* — it should describe the read_athlete + get_time_context
ritual.
```

Update the Verify section's tool sentence if needed (still 22 tools — unchanged).

- [ ] **Step 2: `README.md`** — move the coaching-skills line from "MVP in progress" to
"Working today". Replace:
```
- 🔜 Coaching skills: onboarding → honest assessment → program generation →
  personalization → check-ins & adaptation
```
with (under Working today):
```
- ✅ Six coaching skills (Claude Code plugin format): session rituals, onboarding,
  honest goal assessment with counter-proposals, evidence-cited program generation,
  structured check-ins, versioned adaptation — each eval-guarded against tool drift
  and fabricated references
```
Check exact wording first; adjust minimally.

- [ ] **Step 3: Commit**

```bash
git add docs/installing.md README.md
git commit -m "Document coaching skill installation"
```

---

### Task 7: Final sweep

- [ ] Full quality gate (ruff/format/ty, full pytest, prek run --all-files,
actionlint + zizmor).
- [ ] Append `## As-Built Deviations` to this plan file (verified against git log),
including: any session-helper handle used in test_tool_references, skill-content
adjustments forced by the structure tests, final counts.
- [ ] Commit: "Record Plan 05 as-built state" (+ footer).

---

## Self-Review Notes

- **Spec coverage (v2 §6 + §10 item 5):** all §6 skills present — coach entry ✓ T1,
  onboarding ✓ T2, assessment (incl. negotiation) ✓ T2, program-generation
  (personalization folded in — spec's `personalization` bullet is §4 of that skill,
  deliberate: it is a step of generation, not a separate conversation) ✓ T3, check-in ✓
  T4, adaptation ✓ T4. `report` skill deferred to Plan 06 (needs render_report to
  exist). `nutrition-recovery` is V2 per spec §6. Eval harness ✓ T5 (deterministic:
  structure, drift, fabrication — LLM-judge deferred, spec says deterministic first).
  Plugin packaging = copy/symlink install docs ✓ T6 (marketplace packaging deferred to
  Plan 07 distribution).
- **Cross-lingual rule** (search in English, answer in locale) ✓ coach + generation.
- **Author-year prose gap** (Plan 04 dependency): closed at the skill level — coach
  skill forbids memory citations and mandates check_citations; generation/adaptation
  repeat it operationally.
- **Placeholder scan:** none; all six skills fully written.
- **Type consistency:** Skill dataclass fields used identically across the three test
  files; EXPECTED_SKILLS matches the six frontmatter names; declared tools in each
  skill match tools that exist as of Plan 04 (verified against the 22-tool list).
- **Known uncertainty:** the `mcp._mcp_server` handle in T5 (conftest reuse
  instruction provided).
