"""MCP server assembly and stdio entrypoint."""

from mcp.server.fastmcp import FastMCP

from performance_agent.server import (
    autoregulation_tools,
    engine_tools,
    evidence_tools,
    import_tools,
    memory_tools,
    report_tools,
    response_tools,
)

mcp = FastMCP("performance-agent")
engine_tools.register(mcp)
memory_tools.register(mcp)
autoregulation_tools.register(mcp)
evidence_tools.register(mcp)
report_tools.register(mcp)
import_tools.register(mcp)
response_tools.register(mcp)


def main() -> None:
    """Run the performance-agent MCP server over stdio."""
    mcp.run()
