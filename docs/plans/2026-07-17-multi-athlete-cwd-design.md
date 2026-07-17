# Multi-athlete data directories resolved from the launch directory

**Date:** 2026-07-17
**Status:** Approved

## Problem

The server resolves a single athlete directory (`PERFORMANCE_AGENT_HOME`, else
`./athlete/`, else `~/.performance-agent`). Coaching several athletes from one
machine is impossible without juggling env vars, and the silent home fallback
hides where data actually lands.

## Decision

One folder per athlete. The CLI is launched **from the athlete's directory**,
and that directory is the data directory:

```
/coaching/
├─ marie/          ← cd marie && claude
│  ├─ profile.yaml
│  ├─ sessions.jsonl
│  └─ programs/
└─ paul/
   └─ profile.yaml
```

An empty directory is a brand-new athlete: onboarding (`write_profile`)
creates `profile.yaml` and everything else follows. No init command, no
marker file.

## Resolution rules (`memory/paths.py`)

`resolve_athlete_dir()` returns, in order:

1. `PERFORMANCE_AGENT_HOME` if set — points directly at the athlete's
   directory. Needed for MCP hosts that don't let you pick the working
   directory (Claude Desktop) and for tests. No guard applies.
2. `Path.cwd()` otherwise.

Removed entirely (replace, don't deprecate): the `./athlete/` project
convention and the `~/.performance-agent` fallback.

## Guard

When resolution falls through to the cwd and that cwd is `$HOME` or a
filesystem root, `resolve_athlete_dir()` raises an error telling the user to
launch from a dedicated athlete folder (e.g. `/coaching/marie/`) or set
`PERFORMANCE_AGENT_HOME`. The server still starts; the error surfaces in each
MCP tool call, which is where the agent can relay the fix.

## Unchanged

The exercises-dataset cache stays global in
`~/.performance-agent/cache/exercises-dataset`, shared by all athletes
(`PERFORMANCE_AGENT_EXERCISES_DATASET` still overrides).

## Documentation

README + the four translations and `docs/installing.md`: document the
per-athlete folder structure, the `cd marie && claude` flow, and a migration
note — `mv ~/.performance-agent/* /coaching/<name>/` (the `cache/` subfolder
may stay where it is).

## Tests

`tests/memory/test_paths.py`: env var wins, cwd is the default, error on
`$HOME` and on the filesystem root, env var bypasses the guard. Drop the
`./athlete/` and home-fallback tests.

## Versioning

Behavior-breaking change → v0.6.0 with a CHANGELOG entry and the migration
note.
