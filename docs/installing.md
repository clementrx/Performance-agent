# Installing PerformanceAgent

PerformanceAgent runs as an MCP server inside your AI agent CLI. Until the first
PyPI release, install from a local clone:

```bash
git clone https://github.com/<org>/performance-agent
cd performance-agent && uv sync
```

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

## Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.performance-agent]
command = "uv"
args = ["--directory", "/path/to/performance-agent", "run", "performance-agent"]
```

## Verify

Ask your agent: *"List the performance-agent tools."* You should see nine engine
tools (assess_endurance_goal, predict_race_time, estimate_1rm, …).

Once published to PyPI (roadmap Plan 07), the `command`/`args` simplify to
`uvx` / `["performance-agent"]`.
