"""MCP server assembly and stdio entrypoint."""

from mcp.server.fastmcp import FastMCP

from performance_agent.exercises.dataset import start_background_sync
from performance_agent.server import (
    autoregulation_tools,
    competition_tools,
    document_tools,
    engine_tools,
    evidence_tools,
    exercise_tools,
    followup_tools,
    import_tools,
    macro_tools,
    memory_tools,
    performance_tools,
    report_tools,
    response_tools,
    taper_tools,
)

mcp = FastMCP("performance-agent")
engine_tools.register(mcp)
memory_tools.register(mcp)
autoregulation_tools.register(mcp)
evidence_tools.register(mcp)
report_tools.register(mcp)
import_tools.register(mcp)
response_tools.register(mcp)
performance_tools.register(mcp)
exercise_tools.register(mcp)
taper_tools.register(mcp)
macro_tools.register(mcp)
document_tools.register(mcp)
followup_tools.register(mcp)
competition_tools.register(mcp)


def main() -> None:
    """Run the performance-agent MCP server over stdio.

    The exercises-dataset clone (media + instructions for the session HTML)
    syncs in a daemon thread so startup never blocks on the network.
    """
    start_background_sync()
    mcp.run()
