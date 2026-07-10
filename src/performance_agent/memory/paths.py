"""Athlete data directory resolution.

Precedence: PERFORMANCE_AGENT_HOME env var, then ./athlete/ when it exists
(project-local coaching folder), then ~/.performance-agent/.
"""

import os
from pathlib import Path

ENV_VAR = "PERFORMANCE_AGENT_HOME"
PROJECT_DIR_NAME = "athlete"


def resolve_athlete_dir() -> Path:
    """Return the athlete data directory (never creates it)."""
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    project_dir = Path.cwd() / PROJECT_DIR_NAME
    if project_dir.is_dir():
        return project_dir
    return Path.home() / ".performance-agent"
