"""MCP tools for the individual taper response.

recommend_taper consults the athlete's fitted taper response (detected from the
session log and calendar) and returns an individual recommendation when >= 2
historical tapers carry outcomes, else the labeled population rule. fit_taper_response
exposes the detected windows for narration. Both read the athlete directory.
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from performance_agent.engine.season import SeasonModality
from performance_agent.memory import taper_response
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.taper_response import TaperRecommendationView, TaperResponseView


def recommend_taper(
    buildup_weeks: int,
    modality: SeasonModality,
    event_priority: Literal["A", "B", "C"],
) -> TaperRecommendationView:
    """Recommend a taper length (days), individualized from the athlete's history.

    Computes the generic population taper (endurance tapers longest, strength
    shortest — corpus taper meta-analysis; a short buildup shortens it, a B event
    gets a mini-taper), then consults the fitted taper response. basis="individual"
    (with the best-outcome duration from >= 2 historical tapers) or "population"
    (the generic rule, when fewer than 2 tapers carry outcomes) — population_days
    always shows the generic rule for comparison. modality is strength/endurance/
    mixed; buildup_weeks is non-negative. Say the basis out loud.
    """
    return taper_response.recommend_taper(
        resolve_athlete_dir(), buildup_weeks, modality, event_priority
    )


def fit_taper_response() -> TaperResponseView:
    """Detect the athlete's historical tapers and summarize outcomes.

    Scans the daily session-RPE load series for volume reductions of >= ~25% over
    >= 4 days before each calendar competition, pairs each with its event-linked KPI
    outcome (normalized so higher = better), and reports the windows, how many carry
    outcomes, and the individual-vs-population basis. With < 2 outcomes it is the
    population prior — say so; never present a thin sample as an individual law.
    """
    return taper_response.fit_taper_response_view(resolve_athlete_dir(), generic_duration_days=0)


def register(mcp: FastMCP) -> None:
    """Register the taper-response tools on the server."""
    for tool in (recommend_taper, fit_taper_response):
        mcp.tool()(tool)
