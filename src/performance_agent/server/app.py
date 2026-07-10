"""MCP server assembly and stdio entrypoint."""

from mcp.server.fastmcp import FastMCP

from performance_agent.server import engine_tools, memory_tools

mcp = FastMCP("performance-agent")
engine_tools.register(mcp)
memory_tools.register(mcp)


def main() -> None:
    """Run the performance-agent MCP server over stdio."""
    mcp.run()
