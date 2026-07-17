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
