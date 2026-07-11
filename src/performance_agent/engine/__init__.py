"""Deterministic sports science engine (no LLM, no I/O).

Public API re-exports. Agents call these functions as tools; they never
compute training numbers themselves.
"""

from performance_agent.engine.endurance import pace_s_per_km, riegel_predict
from performance_agent.engine.feasibility import (
    BodycompFeasibility,
    FeasibilityResult,
    TrainingAge,
    bodycomp_feasibility,
    endurance_feasibility,
    hypertrophy_feasibility,
    strength_feasibility,
)
from performance_agent.engine.load import (
    acute_chronic_ratio,
    session_rpe_load,
    weekly_loads,
)
from performance_agent.engine.periodization import WeekLoad, build_weekly_waves
from performance_agent.engine.strength import (
    WeeklySetTargets,
    load_for_percentage,
    one_rm_brzycki,
    one_rm_epley,
    percentage_for_reps_rir,
    reps_for_percentage_rir,
    weekly_set_targets,
)

__all__ = [
    "BodycompFeasibility",
    "FeasibilityResult",
    "TrainingAge",
    "WeekLoad",
    "WeeklySetTargets",
    "acute_chronic_ratio",
    "bodycomp_feasibility",
    "build_weekly_waves",
    "endurance_feasibility",
    "hypertrophy_feasibility",
    "load_for_percentage",
    "one_rm_brzycki",
    "one_rm_epley",
    "pace_s_per_km",
    "percentage_for_reps_rir",
    "reps_for_percentage_rir",
    "riegel_predict",
    "session_rpe_load",
    "strength_feasibility",
    "weekly_loads",
    "weekly_set_targets",
]
