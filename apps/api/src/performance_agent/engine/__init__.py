"""Deterministic sports science engine (no LLM, no I/O).

Public API re-exports. Agents call these functions as tools; they never
compute training numbers themselves.
"""

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict
from performance_agent.engine.feasibility import (
    FeasibilityResult,
    TrainingAge,
    endurance_feasibility,
)
from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)
from performance_agent.engine.periodization import WeekLoad, build_weekly_waves
from performance_agent.engine.strength import (
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
)

__all__ = [
    "FeasibilityResult",
    "TrainingAge",
    "WeekLoad",
    "acute_chronic_ratio",
    "build_weekly_waves",
    "endurance_feasibility",
    "load_for_percentage",
    "one_rm_brzycki",
    "one_rm_epley",
    "pace_s_per_km",
    "riegel_predict",
    "session_rpe_load",
    "weekly_loads",
]
