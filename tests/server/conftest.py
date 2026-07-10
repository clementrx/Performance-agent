import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from performance_agent.server.app import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with create_connected_server_and_client_session(mcp) as session:
        yield session
