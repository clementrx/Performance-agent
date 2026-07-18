"""One-command wearable connection setup (`performance-agent connect garmin`).

This is a terminal CLI, not an MCP tool: the Garmin login is interactive
(email, password, MFA code) so it must run where the athlete can type. It
chains everything that was previously three manual steps: the interactive
authentication (delegated to the community garmin_mcp server's own auth CLI,
which persists OAuth tokens to ~/.garminconnect — the password is never
stored), then registration of that server in Claude Code when the `claude`
CLI is present, or a ready-to-paste JSON snippet for every other client.
"""

import shutil
import subprocess
import sys
from collections.abc import Callable

Runner = Callable[..., subprocess.CompletedProcess]

GARMIN_MCP_GIT = "git+https://github.com/Taxuspt/garmin_mcp"
GARMIN_UVX_ARGS = ("uvx", "--python", "3.12", "--from", GARMIN_MCP_GIT)

_USAGE = """usage: performance-agent connect garmin

Connects your Garmin account to the coach in one step:
  1. interactive Garmin Connect login (MFA supported; OAuth tokens saved to
     ~/.garminconnect — your password is never stored),
  2. registers the Garmin MCP server in Claude Code (or prints the JSON
     snippet to paste into any other client's MCP config).

Strava: no blessed server yet — see docs/installing.md.
"""

_MANUAL_SNIPPET = """Add this to your client's MCP config (e.g. .mcp.json), then restart it:

  "garmin": {
    "command": "uvx",
    "args": ["--python", "3.12", "--from",
             "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"]
  }
"""

_RESTART_NOTE = (
    "\nDone. Restart your agent session (MCP servers only load at startup),\n"
    'then tell your coach: "I have a Garmin watch" — it will record the\n'
    "account on your profile and start pulling activities and sleep/HRV data."
)


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _authenticate(run: Runner | None = None) -> bool:
    runner = run or subprocess.run
    print("Step 1/2 — Garmin Connect login (interactive; MFA supported)")
    result = runner([*GARMIN_UVX_ARGS, "garmin-mcp-auth"], check=False)
    return result.returncode == 0


def _register(run: Runner | None = None) -> None:
    runner = run or subprocess.run
    print("\nStep 2/2 — registering the Garmin MCP server")
    if shutil.which("claude") is None:
        print("Claude Code CLI not found; manual configuration:")
        print(_MANUAL_SNIPPET)
        return
    add = ["claude", "mcp", "add", "garmin", "-s", "user", "--", *GARMIN_UVX_ARGS, "garmin-mcp"]
    result = runner(add, check=False)
    if result.returncode != 0:
        print("`claude mcp add` failed; manual configuration:")
        print(_MANUAL_SNIPPET)


def connect_main(args: list[str], run: Runner | None = None) -> int:
    """Run `performance-agent connect <service>`; returns the exit code.

    Only `garmin` is supported today. The interactive login needs a real
    terminal (a TTY): running it from a non-interactive shell fails with a
    readable message instead of a traceback.
    """
    if args != ["garmin"]:
        print(_USAGE, file=sys.stderr)
        return 2
    if shutil.which("uvx") is None:
        return _fail("uvx not found — install uv first: https://docs.astral.sh/uv/")
    if not sys.stdin.isatty():
        return _fail(
            "the Garmin login is interactive (email/password/MFA) and needs a real\n"
            "terminal. Open your terminal app and run: performance-agent connect garmin\n"
            "(or: uvx performance-agent connect garmin)"
        )
    if not _authenticate(run):
        return _fail("Garmin login failed — nothing was registered. Fix the login and rerun.")
    _register(run)
    print(_RESTART_NOTE)
    return 0
