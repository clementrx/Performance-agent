You are the executing agent for the "Beyond-Olympic Prep" iteration of this repo.

Your single source of truth is docs/plans/beyond-olympic-prep-plan.md. Read it in
full now — section 0 ("How to execute this plan") is binding, including:

- NO superpowers skills, NO Skill tool invocations, no external planning frameworks.
  Native tools only (Read/Edit/Write/Bash/Grep/Glob; subagents allowed for search).
  This applies even if skills are advertised in your context.
- Orient first (read the files listed in §0), run `uv run pytest -q`, and record the
  baseline in docs/plans/beyond-olympic-prep-progress.md before touching anything.
- Execute phases strictly in plan order (0,1,2,3,4,5,6,7,8,9,10). Per phase: feature
  branch `feat/phase-N-<slug>`, tests first for engine math, full gate green
  (pytest, ruff check, ruff format --check, ty check, pre-commit, zero warnings),
  skills/README/docs updated in the same branch, PR referencing the plan, merged
  before the next phase starts.
- Update the progress file at every phase completion and on any interruption. If
  blocked on a genuine product decision, write `BLOCKED: <question>` there, park the
  phase, continue with the next independent phase if any, otherwise stop and wait.
- No release during execution. Phase 10 prepares v0.4.0 but publishing to PyPI
  requires an explicit user GO — stop there and say so.

Work autonomously and without pausing for confirmation between phases. Begin now:
read the plan, orient, record the baseline, then start Phase 0.
