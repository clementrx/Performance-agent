"""End-to-end: spawn the real server subprocess and speak MCP over stdio."""

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.anyio
async def test_stdio_server_exposes_engine_tools():
    params = StdioServerParameters(command="uv", args=["run", "performance-agent"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        assert "assess_endurance_goal" in names

        result = await session.call_tool(
            "assess_endurance_goal",
            {
                "current_time_s": 3300,
                "target_time_s": 2100,
                "weeks": 12,
                "training_age": "beginner",
            },
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["probability"] < 0.05
