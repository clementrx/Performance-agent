# Installing PerformanceAgent

PerformanceAgent runs as an MCP server inside your AI agent CLI. Until the first
PyPI release, install from a local clone.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — the only thing you
  need to install yourself; it fetches the right Python (3.13) automatically.
- One of the three agent CLIs below, already working.

```bash
git clone https://github.com/<your-org>/performance-agent
cd performance-agent && uv sync
```

(repo not yet public — replace with this repository's actual location)

## Claude Code

```bash
claude mcp add performance-agent -- uv --directory /path/to/performance-agent run performance-agent
```

Or in your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "performance-agent": {
      "command": "uv",
      "args": ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
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
      "command": "uv",
      "args": ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
    }
  }
}
```

If the file already exists, merge the entry into the existing `mcpServers` object.

## Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.performance-agent]
command = "uv"
args = ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
```

## Where your data lives

The coach stores your profile, goals, programs, and logs in a plain-file directory:

1. `PERFORMANCE_AGENT_HOME` env var, if set — **recommended**;
2. else `./athlete/` relative to the server's working directory — note that with the
   `uv --directory` commands above, that working directory is the performance-agent
   clone itself, so prefer the env var;
3. else `~/.performance-agent/`.

Set the env var in the server config, e.g. for Claude Code:

    claude mcp add performance-agent --env PERFORMANCE_AGENT_HOME=~/athlete-data -- uv --directory /path/to/performance-agent run performance-agent

(`.mcp.json`, Gemini `settings.json` and Codex `config.toml` all accept an `env` map on
the server entry.)

## Verify

Some CLIs only pick up new servers on restart — reload the session first.

Ask your agent: *"List the performance-agent tools."* You should see 22 tools (9
engine + 10 memory + 3 evidence: assess_endurance_goal, read_athlete, search_evidence, …).

Once published to PyPI (roadmap Plan 07), the `command`/`args` simplify to
`uvx` / `["performance-agent"]`.
