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

## Where your data lives

The coach stores your profile, goals, programs, and logs in a plain-file directory:

1. `PERFORMANCE_AGENT_HOME` env var, if set — **recommended**;
2. else `./athlete/` relative to the server's working directory — with the `uvx`
   commands above that directory depends on where your agent CLI spawns the server,
   so prefer the env var;
3. else `~/.performance-agent/`.

Set the env var in the server config, e.g. for Claude Code:

    claude mcp add performance-agent -s user --env PERFORMANCE_AGENT_HOME=~/athlete-data -- uvx performance-agent

(`.mcp.json`, Gemini `settings.json` and Codex `config.toml` all accept an `env` map on
the server entry.) The directory is created automatically on first write — no need to
`mkdir` it yourself, and it doesn't need to match the directory you run `claude` from.

## Verify

MCP servers are only loaded when a session *starts*. If you had a session already
open, fully quit it and run `claude` (or your CLI's equivalent) again — a new tab of
the same running session won't pick up the new server.

Ask your agent: *"List the performance-agent tools."* You should see 47 tools (24
engine + 16 memory + 6 evidence + 1 report: assess_endurance_goal, read_athlete,
search_evidence, search_evidence_live, verify_reference, save_evidence, …).

Also verify the coaching skills (see the section above): ask what the
performance-coach skill's session ritual is.
