# Multi-Athlete Cwd Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The directory the server is launched from IS the athlete's data directory, so one coaching folder can hold one subfolder per athlete.

**Architecture:** `resolve_athlete_dir()` (called per-request by all 93 tools) drops the `./athlete/` convention and the `~/.performance-agent` fallback; resolution becomes `PERFORMANCE_AGENT_HOME` env var, else `Path.cwd()` with a guard that refuses `$HOME` and filesystem roots. Everything downstream (store, tools, exercises cache) is untouched.

**Tech Stack:** Python 3.13, pytest, uv. Spec: `docs/plans/2026-07-17-multi-athlete-cwd-design.md`.

---

### Task 1: Rewrite `resolve_athlete_dir()` (TDD)

**Files:**
- Modify: `src/performance_agent/memory/paths.py`
- Test: `tests/memory/test_paths.py`

- [ ] **Step 1: Replace the test file with the new contract**

```python
from pathlib import Path

import pytest

from performance_agent.memory.paths import resolve_athlete_dir


def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(tmp_path / "custom"))
    assert resolve_athlete_dir() == tmp_path / "custom"


def test_env_var_expands_user(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", "~/somewhere")
    assert resolve_athlete_dir() == Path.home() / "somewhere"


def test_cwd_is_the_athlete_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    athlete = tmp_path / "marie"
    athlete.mkdir()
    monkeypatch.chdir(athlete)
    assert resolve_athlete_dir() == athlete


def test_refuses_home_as_cwd(monkeypatch):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(Path.home())
    with pytest.raises(ValueError, match="PERFORMANCE_AGENT_HOME"):
        resolve_athlete_dir()


def test_refuses_filesystem_root_as_cwd(monkeypatch):
    monkeypatch.delenv("PERFORMANCE_AGENT_HOME", raising=False)
    monkeypatch.chdir(Path(Path.cwd().anchor))
    with pytest.raises(ValueError, match="PERFORMANCE_AGENT_HOME"):
        resolve_athlete_dir()


def test_env_var_bypasses_the_guard(monkeypatch):
    monkeypatch.setenv("PERFORMANCE_AGENT_HOME", str(Path.home()))
    monkeypatch.chdir(Path.home())
    assert resolve_athlete_dir() == Path.home()
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `uv run pytest tests/memory/test_paths.py -v`
Expected: `test_cwd_is_the_athlete_dir`, `test_refuses_home_as_cwd`, `test_refuses_filesystem_root_as_cwd` FAIL (old fallback logic returns `~/.performance-agent` instead of erroring/cwd); the two env-var tests PASS.

- [ ] **Step 3: Rewrite `paths.py`**

Full new content of `src/performance_agent/memory/paths.py`:

```python
"""Athlete data directory resolution.

One directory per athlete: launch the server from the athlete's folder and
that folder is the data directory. PERFORMANCE_AGENT_HOME overrides for MCP
hosts that don't let you pick the working directory (e.g. Claude Desktop).
"""

import os
from pathlib import Path

ENV_VAR = "PERFORMANCE_AGENT_HOME"


def resolve_athlete_dir() -> Path:
    """Return the athlete data directory (never creates it).

    Raises:
        ValueError: when resolution falls through to the working directory
            and that directory is the user's home or a filesystem root —
            almost certainly a launch mistake, not an athlete folder.
    """
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    cwd = Path.cwd()
    if cwd == Path.home() or cwd == Path(cwd.anchor):
        raise ValueError(
            f"Refusing to use {cwd} as the athlete data directory. "
            "Launch the server from a dedicated athlete folder "
            "(e.g. /coaching/marie/) or set PERFORMANCE_AGENT_HOME."
        )
    return cwd
```

Note: `PROJECT_DIR_NAME` is deleted. Step 5 checks nothing else imports it.

- [ ] **Step 4: Run the paths tests to verify they pass**

Run: `uv run pytest tests/memory/test_paths.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Check nothing else references the removed convention**

Run: `/usr/bin/grep -rn "PROJECT_DIR_NAME" src tests --include="*.py"`
Expected: no output. If a reference exists, remove it as part of this task.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all ~1270 tests pass. If a test relied on the `./athlete/` or home
fallback, point it at `tmp_path` via `monkeypatch.setenv("PERFORMANCE_AGENT_HOME", ...)`
like the rest of the suite does.

- [ ] **Step 7: Lint and typecheck**

Run: `uv run ruff check src/performance_agent/memory/paths.py tests/memory/test_paths.py && uv run ruff format --check src tests && uv run ty check`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/performance_agent/memory/paths.py tests/memory/test_paths.py
git commit -m "Resolve athlete dir from the launch directory

PERFORMANCE_AGENT_HOME still wins; otherwise the working directory IS the
athlete folder. Drops the ./athlete/ convention and the ~/.performance-agent
fallback, and refuses \$HOME and filesystem roots with an actionable error.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Update the English docs (README + installing.md)

**Files:**
- Modify: `README.md` (Step 1 block around lines 68-79)
- Modify: `docs/installing.md` ("Where your data lives" section, lines ~181-198)

- [ ] **Step 1: Rewrite README Step 1**

Replace the Step 1 paragraph + snippet (the `claude mcp add ... --env PERFORMANCE_AGENT_HOME=~/athlete-data ...` block and the paragraph after it) with:

````markdown
**Step 1 — plug in the coach.** Run this once, from any terminal:

```bash
claude mcp add performance-agent -s user -- uvx performance-agent
```

This registers the coach's "brain" (the engine, the science library, your future
athlete profile) as a tool Claude Code can call. `-s user` makes it available in any
folder you later open `claude` from.

**The folder you launch `claude` from is the athlete's data folder.** Make one
folder per athlete and start the session from inside it:

```bash
mkdir -p ~/coaching/marie && cd ~/coaching/marie && claude
```

All of that athlete's data lives there as plain files; nothing is sent anywhere.
Coaching several athletes is just several folders — `cd` into the right one.
(If your MCP host doesn't let you pick the launch folder — Claude Desktop, for
example — set `PERFORMANCE_AGENT_HOME` to the athlete folder in the server config
instead.)
````

- [ ] **Step 2: Rewrite "Where your data lives" in docs/installing.md**

Replace the numbered resolution list and the env-var paragraph with:

````markdown
## Where your data lives

The coach stores your profile, goals, programs, and logs in a plain-file directory:

1. `PERFORMANCE_AGENT_HOME` env var, if set — for MCP hosts that don't let you
   pick the working directory (Claude Desktop), and for pinning one athlete;
2. else **the directory the server is launched from** — which, for CLI agents,
   is the folder you run `claude` (or `gemini`, `codex`) from.

One folder per athlete: `mkdir -p ~/coaching/marie && cd ~/coaching/marie && claude`.
The folder is treated as the athlete's data directory as-is — an empty folder is a
brand-new athlete, and files are created on first write. Launching from your home
directory or a filesystem root is refused with an error, so a stray session can't
scatter files there.

Set the env var in the server config when you need it, e.g. for Claude Desktop:

```json
"env": { "PERFORMANCE_AGENT_HOME": "/Users/you/coaching/marie" }
```

**Migrating from ≤0.5.x:** data previously defaulted to `~/.performance-agent/`.
Move it into a per-athlete folder: `mkdir -p ~/coaching/me && mv ~/.performance-agent/* ~/coaching/me/`
(the `cache/` subfolder can stay — it's the shared exercises-media cache, not
athlete data).
````

- [ ] **Step 3: Check no stale references remain in the two files**

Run: `/usr/bin/grep -n "athlete-data\|./athlete/" README.md docs/installing.md`
Expected: no hits (or only hits inside the migration note / transcript examples that
show `athlete/programs/...` paths in old session transcripts — update those transcript
lines to `programs/program-v1.md` since the files now live at the athlete-folder root).

- [ ] **Step 4: Commit**

```bash
git add README.md docs/installing.md
git commit -m "Document per-athlete folders in README and installing guide

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Update the four translated READMEs

**Files:**
- Modify: `docs/i18n/README.fr.md` (Step 1 block, line ~71)
- Modify: `docs/i18n/README.de.md` (line ~70)
- Modify: `docs/i18n/README.es.md` (line ~70)
- Modify: `docs/i18n/README.it.md` (line ~70)

- [ ] **Step 1: Apply the same Step 1 rewrite as Task 2 in each language**

Same structural change as Task 2 Step 1, translated. The snippet becomes
`claude mcp add performance-agent -s user -- uvx performance-agent` plus the
per-athlete-folder paragraph and the `mkdir -p ~/coaching/marie && cd ~/coaching/marie && claude`
example. Key sentence per language (translate the rest to match the English flow):

- fr: « **Le dossier depuis lequel vous lancez `claude` est le dossier de données de l'athlète.** Créez un dossier par athlète et démarrez la session depuis celui-ci. »
- de: „**Der Ordner, aus dem Sie `claude` starten, ist der Datenordner des Athleten.** Legen Sie pro Athlet einen Ordner an und starten Sie die Sitzung von dort."
- es: «**La carpeta desde la que lanzas `claude` es la carpeta de datos del atleta.** Crea una carpeta por atleta e inicia la sesión desde ella.»
- it: «**La cartella da cui avvii `claude` è la cartella dati dell'atleta.** Crea una cartella per atleta e avvia la sessione da lì.»

Also update transcript lines showing `athlete/programs/program-v1.md` to
`programs/program-v1.md` in each translated README (grep `athlete/` per file).

- [ ] **Step 2: Verify no stale snippet remains**

Run: `/usr/bin/grep -n "athlete-data" docs/i18n/*.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add docs/i18n/README.fr.md docs/i18n/README.de.md docs/i18n/README.es.md docs/i18n/README.it.md
git commit -m "Update translated READMEs for per-athlete folders

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Version bump + CHANGELOG

**Files:**
- Modify: `pyproject.toml:3` (`version = "0.5.0"` → `"0.6.0"`)
- Modify: `CHANGELOG.md` (new section above `## 0.5.0`)

- [ ] **Step 1: Bump the version**

In `pyproject.toml`, set `version = "0.6.0"`.

- [ ] **Step 2: Add the CHANGELOG section**

Insert above `## 0.5.0 — Session HTML`:

```markdown
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
```

- [ ] **Step 3: Run the packaging tests (they often assert the version)**

Run: `uv run pytest tests/packaging -q`
Expected: pass. If a test pins `0.5.0`, update it to `0.6.0`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml CHANGELOG.md tests/packaging
git commit -m "Bump to 0.6.0 with per-athlete folder changelog

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Final verification

- [ ] **Step 1: Full suite, lint, format, types**

Run: `uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run ty check`
Expected: all clean.

- [ ] **Step 2: End-to-end smoke of the new resolution**

Run:
```bash
cd "$(mktemp -d)" && mkdir marie && cd marie && \
  env -u PERFORMANCE_AGENT_HOME uv run --project /Users/clementrieux/projets/PerformanceAgent \
  python -c "from performance_agent.memory.paths import resolve_athlete_dir; print(resolve_athlete_dir())"
```
Expected: prints the `…/marie` temp path. Then from `$HOME`:
```bash
cd ~ && env -u PERFORMANCE_AGENT_HOME uv run --project /Users/clementrieux/projets/PerformanceAgent \
  python -c "from performance_agent.memory.paths import resolve_athlete_dir; print(resolve_athlete_dir())"
```
Expected: `ValueError` with the "dedicated athlete folder" message.

- [ ] **Step 3: Mark plan checkboxes done and commit any stragglers**
