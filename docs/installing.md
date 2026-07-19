# Installing PerformanceAgent

PerformanceAgent runs as an MCP server inside your AI agent CLI. The server is
published on PyPI as [`performance-agent`](https://pypi.org/project/performance-agent/);
`uvx` fetches it on demand — nothing to clone for the server itself.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — the only thing you
  need to install yourself; it fetches the right Python (3.13) automatically.
- One of the three agent CLIs below, already working. Don't have one? Claude Code:
  `curl -fsSL https://claude.ai/install.sh | bash` (full instructions:
  [code.claude.com/docs](https://code.claude.com/docs/en/quickstart.md)).
- [`typst`](https://typst.app) — only needed for PDF reports (`brew install typst`);
  everything else works without it.


## Claude Code

**Recommended — the plugin.** One install ships both the MCP server *and* the 16
coaching skills, and Claude Code keeps them updated. From inside Claude Code:

```
/plugin marketplace add clementrx/Performance-agent
/plugin install performance-agent@performance-agent
```

The MCP server registers at user scope (available in every folder) and every coaching
skill loads with it — so with the plugin you can skip the "Installing the coaching
skills" section below. Update later with `/plugin marketplace update performance-agent`.

**Manual — MCP server only.** To register just the server (and handle skills
separately, below):

```bash
claude mcp add performance-agent -s user -- uvx performance-agent
```

`-s user` registers the server globally, so it's available in any project or
directory you later talk to the coach from. Without it, `claude mcp add` defaults to
`local` scope — private to whichever directory you ran the command in — and the coach
will silently have no tools anywhere else. If you already added it without `-s user`
and need to fix the scope:

```bash
claude mcp remove performance-agent -s local
claude mcp add performance-agent -s user -- uvx performance-agent
```

Or in your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

## Gemini CLI

In `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

If the file already exists, merge the entry into the existing `mcpServers` object.

## Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.performance-agent]
command = "uvx"
args = ["performance-agent"]
```

## Cursor

Project-only: `.cursor/mcp.json` in the repo root. Every project: `~/.cursor/mcp.json`.
Same format as Claude Code's `.mcp.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

Or via the UI: Cursor Settings → Tools & MCP → Add new MCP server.

## Windsurf

`~/.codeium/windsurf/mcp_config.json` (create the file if it doesn't exist yet):

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

Or via the UI: Windsurf Settings → Advanced Settings → Cascade → Add Server.

## VS Code (GitHub Copilot)

`.vscode/mcp.json` in the workspace, or your user profile for a server available in
every workspace. Note the root key is `servers`, not `mcpServers`:

```json
{
  "servers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

## Cline (VS Code extension)

Open the MCP Servers icon in the Cline panel → Configure → Configure MCP Servers, which
opens `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uvx",
      "args": ["performance-agent"]
    }
  }
}
```

## Installing the coaching skills (Claude Code)

The skills are the coaching protocols the agent follows — what to ask, when to be
honest about a goal, how to periodize. Claude Code has native support for them; every
other client needs the same content pasted into its own instructions mechanism, since
none of them read `SKILL.md` files directly.

> **On Claude Code, the plugin already did this.** `/plugin install
> performance-agent@performance-agent` (above) bundles all 16 skills — skip straight to
> "Connecting Garmin or Strava". The manual copy below is only for a skills-dir install
> without the plugin.

**Claude Code** — copy (or symlink) them into your personal skills directory:

```bash
mkdir -p ~/.claude/skills
git clone --depth 1 https://github.com/clementrx/Performance-agent
cp -R Performance-agent/skills/* ~/.claude/skills/
```

Per-project alternative: copy them into `.claude/skills/` inside the project where
you talk to your coach.

**Every other client** — there's no native skill/plugin format that reads `SKILL.md`
directly, so paste each skill's content into whichever instructions file your client
supports:

| Client | Instructions file |
|---|---|
| Gemini CLI | `GEMINI.md` |
| Codex | `AGENTS.md` |
| Cursor | `.cursor/rules/*.mdc` (one rule file per skill, or all concatenated) |
| Windsurf | its equivalent rules/memories settings |
| VS Code (Copilot) | `.github/copilot-instructions.md` |
| Cline | `.clinerules/` (one `.md` file per skill) |

The `tools:` frontmatter in each `SKILL.md` names the MCP tools that protocol expects
— useful for checking nothing was lost in the copy. This is manual and there's no
tooling for it yet; contributions to automate it are welcome.

Verify: ask your agent *"What does your performance-coach skill tell you to do at
the start of a session?"* — it should describe the read_athlete + get_time_context
ritual.

## Connecting Garmin or Strava (optional)

If the athlete tracks training with a Garmin watch or Strava, the coach can pull
activities straight from the service at check-in — no manual `.fit`/`.tcx` export
needed. This works by running a community MCP server for the service *alongside*
performance-agent; the coach detects its tools in the session and uses them when
the athlete's profile lists the account (`connected_services`, recorded during
onboarding).

Two things to set up:

1. **Tell the coach about the account** — during onboarding it asks; for an
   existing athlete, just say "I have a Garmin watch" and the coach records it
   in the profile.
2. **Add the service's MCP server to your client**, next to the
   performance-agent entry.

   **Garmin** — one command, in a real terminal (the login is interactive):

   ```bash
   uvx performance-agent connect garmin
   ```

   It walks you through the Garmin Connect login once (MFA supported; OAuth
   tokens are saved to `~/.garminconnect` — your password is never stored),
   then registers the Garmin MCP server in Claude Code for you (with any
   other client, it prints the JSON snippet to paste). Restart your session
   afterwards and tell your coach "I have a Garmin watch".

   Under the hood this uses
   [taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT, actively
   maintained, 110+ tools: activities, sleep, HRV, stress, resting HR, body
   composition, training status). Manual setup, if you prefer, in
   `.mcp.json` (any client):

   ```json
   {
     "mcpServers": {
       "performance-agent": { "command": "uvx", "args": ["performance-agent"] },
       "garmin": {
         "command": "uvx",
         "args": ["--python", "3.12", "--from",
                  "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"]
       }
     }
   }
   ```

   **Strava** — one command too:

   ```bash
   uvx performance-agent connect strava
   ```

   It registers [r-huijts/strava-mcp](https://github.com/r-huijts/strava-mcp)
   (MIT, on npm, 25 tools: detailed activities with HR and laps, stats,
   records, training zones, segments, GPX/TCX routes; needs Node.js for
   `npx`). One-time prerequisite: create a free API app at
   [strava.com/settings/api](https://www.strava.com/settings/api) with
   "Authorization Callback Domain" set to `localhost`. The authorization
   itself happens in your browser, started from the coaching conversation:
   restart your session and tell your coach "connect my Strava account".
   Manual setup for other clients:

   ```json
   "strava": { "command": "npx", "args": ["-y", "@r-huijts/strava-mcp-server"] }
   ```

Everything downstream is unchanged: fetched activities go through the same
propose → confirm → `log_session` flow as file imports, and nothing is ever
logged without the athlete's confirmation. No server connected? File export
keeps working exactly as before.

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

Set the env var in the server config when you need it (`.mcp.json`, Gemini
`settings.json` and Codex `config.toml` all accept an `env` map on the server
entry), e.g. for Claude Desktop:

```json
"env": { "PERFORMANCE_AGENT_HOME": "/Users/you/coaching/marie" }
```

**Migrating from ≤0.5.x:** data previously defaulted to `~/.performance-agent/`.
Move it into a per-athlete folder: `mkdir -p ~/coaching/me && mv ~/.performance-agent/* ~/coaching/me/`
(the `cache/` subfolder can stay — it's the shared exercises-media cache, not
athlete data).

## Verify

MCP servers are only loaded when a session *starts*. If you had a session already
open, fully quit it and run `claude` (or your CLI's equivalent) again — a new tab of
the same running session won't pick up the new server.

Ask your agent: *"List the performance-agent tools."* You should see 103 tools (across
the engine, memory, evidence, and report categories: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).

Also verify the coaching skills (see the section above): ask what the
performance-coach skill's session ritual is.
