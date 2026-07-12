# Beyond-National Coach — Execution Progress

Tracks execution of `beyond-national-coach-plan.md`. Read this FIRST when resuming.

**Workflow (locked 2026-07-12):** stacked branches (each phase branches off the
previous; PRs stack and merge in order at the end). Native tools only. Single PyPI
release at the very end. Baseline: **597 tests** passing at plan start.

Execution order: 0, 1, 2, 9, 3, 4, 5, 6, 7, 8.

| Order | Phase | Title | Status | Branch / PR | Notes |
|---|---|---|---|---|---|
| 1 | 0 | Machine-readable programs | done (PR open) | `feat/phase-0-machine-readable-programs` — [PR #4](https://github.com/clementrx/Performance-agent/pull/4) | 617 tests green |
| 2 | 1 | Season calendar & backward planning | done (PR open) | `feat/phase-1-season-calendar` — [PR #5](https://github.com/clementrx/Performance-agent/pull/5) | 659 tests; +6 tools (53 total) |
| 3 | 2 | Full monitoring | pending (subagent) | — | stacked on phase 1 |
| 4 | 9 | Activity file import | pending | — | — |
| 5 | 3 | Day-of session autoregulation | pending | — | — |
| 6 | 4 | Intra-week sequencing & interference | pending | — | — |
| 7 | 5 | Individual response profile | pending | — | — |
| 8 | 6 | Deloads, adherence, return-to-load | pending | — | — |
| 9 | 7 | Proactive follow-up | pending | — | — |
| 10 | 8 | End-to-end simulated evaluation | pending | — | — |

## Deviations from the plan

- **Test infra:** added `tests/__init__.py` (makes `tests` an importable package) and
  a shared `tests/program_plans.py` builder so every layer (store, reports, server)
  builds the same valid `ProgramPlan`. `TestMilestone` carries `__test__ = False` so
  pytest does not try to collect the schema as a test class.
- **Rendered-program glyphs:** the renderer emits ASCII `x` (sets x reps) and `-`
  rather than `×`/`–` to satisfy ruff RUF001 (ambiguous-unicode); reads fine in a
  printed program.
- **i18n READMEs:** the test-count line (597) in `docs/i18n/README.{fr,it,es,de}.md`
  is left for a single batched refresh before the release (plan-sanctioned: "full
  translation refresh may be a follow-up"). English README updated to 617.
- **Report templates:** Phase 0 changes the program *format* only; the rendered
  markdown still feeds the Typst report unchanged, so no report-template change was
  needed this phase.

## Migration note (PR)

`programs/program-v{N}.plan.yaml` is a NEW sibling of the existing
`program-v{N}.md`. Legacy prose-only `program-v{N}.md` files (no `.plan.yaml`) stay
readable forever — `read_program` returns `plan=None` for them, and a structured
vN+1 can be saved on top (reason = "format upgrade"). No existing athlete directory
is broken.

## Phase 1 notes

- **New tools (6, total 53):** `read_calendar`, `upsert_calendar_event`,
  `remove_calendar_event`, `set_recurring_constraints`, `build_season_plan`,
  `recommend_taper`. `set_recurring_constraints` is a small addition beyond the
  plan's literal 5-tool list — the plan's acceptance needs recurring constraints
  persisted (onboarding collects them; time_context reads them) and none of the
  5 listed tools wrote them. Whole-list replace, like `write_profile`.
- **Engine stays datetime-free:** `engine/season.py` works in integer-week space;
  the date↔week conversion lives in `memory/season.py` (like `time_context`).
- **`min_block_weeks` default = 6** (the plan signature said 3 but its prose says
  "≥ 6 weeks (matching MIN_BLOCK_WEEKS)"; followed the prose, mirrors
  `periodization.MIN_BLOCK_WEEKS`).
- **Evidence:** used the existing `tapering-performance-meta-2007` for taper
  length. Issurin block-periodization was NOT added to the corpus (would need a
  verified DOI/PMID; per the anti-fabrication rule the block-vs-waves structural
  priors are labeled team-chosen, consistent with existing `periodization.py`).
- **Report templates:** season-overview section deferred to a batched report pass
  (no athlete-visible report change wired this phase).

## Resume notes

_Phase 1 complete. Next: Phase 2 (full monitoring) — first phase to run via a
background subagent, branching off `feat/phase-1-season-calendar` (stacked)._
