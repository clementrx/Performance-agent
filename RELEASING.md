# Releasing PerformanceAgent

Everything below needs maintainer credentials — none of it is automatable from a
local agent session. The repo is release-ready when this checklist completes.

## One-time setup

1. **Check the PyPI name.** https://pypi.org/project/performance-agent/ — if taken,
   pick a distribution name (e.g. performanceagent-coach), update `[project] name`
   in pyproject.toml, and re-run `uv run pytest tests/packaging`.
2. **Create the GitHub repository** and push:
   ```bash
   gh repo create <org>/performance-agent --public --source . --push
   ```
3. **Replace the placeholder URLs.** Search for `<your-org>` (docs/installing.md)
   and replace with the real org/repo. Add to pyproject.toml under `[project]`:
   ```toml
   [project.urls]
   Homepage = "https://github.com/<org>/performance-agent"
   Issues = "https://github.com/<org>/performance-agent/issues"
   ```
   Commit via a PR (branch protection: never push to main directly once public).
4. **Configure PyPI trusted publishing** (no tokens): PyPI → your project (or
   "pending publisher" for the first release) → Publishing → GitHub:
   owner `<org>`, repo `performance-agent`, workflow `release.yml`, environment `pypi`.
5. **Create the `pypi` environment** in GitHub repo Settings → Environments (add
   yourself as required reviewer if you want a manual gate before each publish).
6. **Optional, distro-friendliness:** the sdist currently ships the build-sufficient
   set only (no tests/); if downstream distros ever need test-in-build, extend
   uv_build's sdist includes.

## Every release

1. Update the version in `pyproject.toml`; commit via PR.
2. Tag and push:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
3. The `release` workflow re-runs the full gate, builds, and publishes. Verify on
   PyPI, then smoke-test the published package:
   ```bash
   uvx performance-agent@latest < /dev/null; echo "exit: $?"   # expect 0
   claude mcp add performance-agent -- uvx performance-agent    # the post-PyPI form
   ```
4. Update docs/installing.md to the `uvx` form (drop the `--directory` local-clone
   form) in the release PR that bumps the version — not before.

## Corpus releases (V2 workflow, recorded for later)

Corpus updates ship as normal package releases: curate → verify (`python -m
performance_agent.evidence.verify`) → version bump → tag. Users get corpus updates
by upgrading the package; no separate channel until the corpus outgrows the wheel.
