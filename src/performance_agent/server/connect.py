"""One-command wearable connection setup (`performance-agent connect <service>`).

This is a terminal CLI, not an MCP tool. `connect garmin` chains the
interactive Garmin login (delegated to the community garmin_mcp server's own
auth CLI — MFA supported, OAuth tokens persisted to ~/.garminconnect, the
password is never stored) with the server registration. `connect strava`
registers the community Strava server (npm); its OAuth happens later in the
browser, started from the coaching conversation itself. Registration goes
through `claude mcp add` when the Claude Code CLI is present, and falls back
to a ready-to-paste JSON snippet for every other client.
"""

import shutil
import subprocess
import sys
from collections.abc import Callable

Runner = Callable[..., subprocess.CompletedProcess]

GARMIN_MCP_GIT = "git+https://github.com/Taxuspt/garmin_mcp"
GARMIN_UVX_ARGS = ("uvx", "--python", "3.12", "--from", GARMIN_MCP_GIT)
STRAVA_NPX_ARGS = ("npx", "-y", "@r-huijts/strava-mcp-server")

_USAGE = """usage: performance-agent connect {garmin|strava}

Connects your wearable/app account to the coach in one step.

garmin:  interactive Garmin Connect login (MFA supported; OAuth tokens saved
         to ~/.garminconnect — your password is never stored), then registers
         the Garmin MCP server in Claude Code (or prints the JSON snippet to
         paste into any other client's MCP config).

strava:  registers the Strava MCP server the same way. The authorization
         itself happens later in your browser, started from the coaching
         conversation ("connect my Strava account"). One-time prerequisite:
         create a free API app at https://www.strava.com/settings/api with
         Authorization Callback Domain set to "localhost".
"""

_GARMIN_SNIPPET = """Add this to your client's MCP config (e.g. .mcp.json), then restart it:

  "garmin": {
    "command": "uvx",
    "args": ["--python", "3.12", "--from",
             "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"]
  }
"""

_STRAVA_SNIPPET = """Add this to your client's MCP config (e.g. .mcp.json), then restart it:

  "strava": {
    "command": "npx",
    "args": ["-y", "@r-huijts/strava-mcp-server"]
  }
"""

_GARMIN_DONE = (
    "\nDone. Restart your agent session (MCP servers only load at startup),\n"
    'then tell your coach: "I have a Garmin watch" — it will record the\n'
    "account on your profile and start pulling activities and sleep/HRV data."
)

_STRAVA_DONE = (
    "\nDone. Two more steps:\n"
    "  1. If you haven't yet: create a free API app at\n"
    '     https://www.strava.com/settings/api ("Authorization Callback\n'
    '     Domain": localhost) and keep the Client ID/Secret at hand.\n'
    "  2. Restart your agent session (MCP servers only load at startup),\n"
    '     then tell your coach: "connect my Strava account" — the browser\n'
    "     opens for the Strava authorization, and tokens persist locally."
)


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _garmin_login(run: Runner | None = None) -> bool:
    runner = run or subprocess.run
    print("Step 1/2 — Garmin Connect login (interactive; MFA supported)")
    result = runner([*GARMIN_UVX_ARGS, "garmin-mcp-auth"], check=False)
    return result.returncode == 0


def _register(name: str, command: tuple[str, ...], snippet: str, run: Runner | None = None) -> None:
    runner = run or subprocess.run
    print(f"Registering the {name} MCP server")
    if shutil.which("claude") is None:
        print("Claude Code CLI not found; manual configuration:")
        print(snippet)
        return
    add = ["claude", "mcp", "add", name, "-s", "user", "--", *command]
    result = runner(add, check=False)
    if result.returncode != 0:
        print("`claude mcp add` failed; manual configuration:")
        print(snippet)


def _connect_garmin(run: Runner | None) -> int:
    if shutil.which("uvx") is None:
        return _fail("uvx not found — install uv first: https://docs.astral.sh/uv/")
    if not sys.stdin.isatty():
        return _fail(
            "the Garmin login is interactive (email/password/MFA) and needs a real\n"
            "terminal. Open your terminal app and run: performance-agent connect garmin\n"
            "(or: uvx performance-agent connect garmin)"
        )
    if not _garmin_login(run):
        return _fail("Garmin login failed — nothing was registered. Fix the login and rerun.")
    print("\nStep 2/2 — ", end="")
    _register("garmin", (*GARMIN_UVX_ARGS, "garmin-mcp"), _GARMIN_SNIPPET, run)
    print(_GARMIN_DONE)
    return 0


def _connect_strava(run: Runner | None) -> int:
    if shutil.which("npx") is None:
        return _fail("npx not found — install Node.js first: https://nodejs.org/")
    _register("strava", STRAVA_NPX_ARGS, _STRAVA_SNIPPET, run)
    print(_STRAVA_DONE)
    return 0


def connect_main(args: list[str], run: Runner | None = None) -> int:
    """Run `performance-agent connect <service>`; returns the exit code.

    Supports `garmin` (interactive terminal login, then registration) and
    `strava` (registration; the OAuth runs later in the browser from the
    coaching conversation). A non-interactive shell fails with a readable
    message instead of a traceback where a terminal is required.
    """
    if args == ["garmin"]:
        return _connect_garmin(run)
    if args == ["strava"]:
        return _connect_strava(run)
    print(_USAGE, file=sys.stderr)
    return 2
