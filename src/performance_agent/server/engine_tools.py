"""MCP tool wrappers around the deterministic sports science engine.

The host agent narrates these results; it never computes training numbers
itself. Docstrings become the tool descriptions the agent reads, so they
state units, valid ranges, and honesty requirements.
"""

from mcp.server.fastmcp import FastMCP

from performance_agent.engine import FeasibilityResult, TrainingAge, endurance_feasibility


def assess_endurance_goal(
    current_time_s: float, target_time_s: float, weeks: int, training_age: TrainingAge
) -> FeasibilityResult:
    """Score the feasibility of an endurance time goal (honest-coach verdict).

    Both times are in seconds over the same distance; training_age is one of
    beginner, intermediate, advanced. Returns the success probability (0-1)
    with the drivers behind it (improvement_needed, required vs achievable
    weekly rates, their ratio). Always present the drivers alongside the
    probability, never the bare number.
    """
    return endurance_feasibility(current_time_s, target_time_s, weeks, training_age)


def register(mcp: FastMCP) -> None:
    """Register every engine tool on the server."""
    for tool in (assess_endurance_goal,):
        mcp.tool()(tool)
