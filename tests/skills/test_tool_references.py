"""Drift guard: skills may only declare tools that actually exist on the server."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from performance_agent.server.app import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _server_tool_names() -> set[str]:
    async with create_connected_server_and_client_session(mcp) as session:
        listed = await session.list_tools()
        return {tool.name for tool in listed.tools}


@pytest.mark.anyio
async def test_declared_tools_exist_on_the_server(skills):
    names = await _server_tool_names()
    for skill in skills:
        declared = set(skill.frontmatter["tools"])
        unknown = declared - names
        assert not unknown, f"{skill.path} declares nonexistent tools: {sorted(unknown)}"


def test_declared_tools_are_actually_used_in_the_body(skills):
    for skill in skills:
        for tool in skill.frontmatter["tools"]:
            assert tool in skill.body, f"{skill.path} declares but never uses: {tool}"


@pytest.mark.anyio
async def test_bodies_do_not_reference_undeclared_tools(skills):
    names = await _server_tool_names()
    for skill in skills:
        declared = set(skill.frontmatter["tools"])
        used = {name for name in names if name in skill.body}
        undeclared = used - declared
        assert not undeclared, f"{skill.path} uses undeclared tools: {sorted(undeclared)}"
