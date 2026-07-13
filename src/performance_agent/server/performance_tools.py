"""MCP tools for the sport-agnostic PerformanceModel (event determinants).

The Analyste researches the literature, proposes a PerformanceModel filling the
generic schema (qualities, KPIs with benchmarks, injury risks, energy systems),
and saves it as an immutable version. The engine validates the schema, rejects
invented qualities and uncited "cited" values, and normalizes quality weights.
Every value the LLM fills carries a provenance label the reports render.
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from performance_agent.memory import store
from performance_agent.memory.paths import resolve_athlete_dir
from performance_agent.memory.schemas import PerformanceModel


class VersionedDocSaved(TypedDict):
    """Result of writing a new performance-model version."""

    path: str
    version: int


def save_performance_model(model: PerformanceModel, reason: str | None = None) -> VersionedDocSaved:
    """Write the NEXT performance-model version (immutable YAML audit trail).

    Hand a fully attributed PerformanceModel: discipline, event, a non-empty
    qualities list (each with a weight 0-1 and a provenance label
    cited|prior|judgment — cited requires cite_ids from the corpus), KPIs (each
    with a test protocol, unit and level benchmarks), injury risks and an
    optional energy-system split. The engine normalizes the quality weights to
    sum to 1, rejects invented quality names, KPIs missing a protocol or unit,
    and "cited" provenance without cite_ids. The store stamps the authoritative
    version and reason; version 1 needs no reason, every later version (v2+)
    requires one stating what changed. Existing versions are never overwritten.
    """
    path, version = store.save_performance_model(resolve_athlete_dir(), model, reason)
    return VersionedDocSaved(path=str(path), version=version)


def read_performance_model(version: int | None = None) -> PerformanceModel:
    """Return the latest (or a specific) performance-model version.

    Raises a readable error when none has been saved yet. Read this before
    programming: the quality weights drive per-quality priorities and the KPIs
    with their benchmarks are what athlete measurements are scored against.
    """
    model = store.read_performance_model(resolve_athlete_dir(), version)
    if model is None:
        msg = "no performance model has been saved yet; research and save_performance_model first"
        raise ValueError(msg)
    return model


def register(mcp: FastMCP) -> None:
    """Register every performance-model tool on the server."""
    for tool in (save_performance_model, read_performance_model):
        mcp.tool()(tool)
