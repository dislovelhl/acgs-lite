"""
MCP Client Tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPClientConfig:
    """Tests for MCPClientConfig."""

    def test_create_config(self):
        """Test creating client config."""
        from ...mcp_integration.client import MCPClientConfig

        config = MCPClientConfig(
            server_url="http://localhost:8000",
            server_name="test-server",
            timeout_ms=5000,
        )

        assert config.server_url == "http://localhost:8000"
        assert config.server_name == "test-server"
        assert config.timeout_ms == 5000
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_config_defaults(self):
        """Test config default values."""
        from ...mcp_integration.client import MCPClientConfig

        config = MCPClientConfig()

        assert config.retry_attempts == 3
        assert config.enable_validation is True
        assert config.strict_mode is True


class TestMCPClient:
    """Tests for MCPClient."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        from ...mcp_integration.client import MCPClient, MCPClientConfig

        config = MCPClientConfig(
            server_url="http://localhost:8000",
            server_name="test-server",
        )
        return MCPClient(config=config, agent_id="test-agent")

    async def test_connect(self, client):
        """Test connecting to server."""
        await client.connect()

        assert client.is_connected is True
        assert client.state.value == "ready"

    async def test_disconnect(self, client):
        """Test disconnecting from server."""
        await client.connect()
        await client.disconnect()

        assert client.is_connected is False

    async def test_call_tool(self, client):
        """Test calling a tool."""
        await client.connect()

        result = await client.call_tool(
            tool_name="example_tool",
            arguments={"input": "test"},
        )

        assert result is not None
        assert "content" in result

    async def test_read_resource(self, client):
        """Test reading a resource."""
        await client.connect()

        result = await client.read_resource(uri="example://resource")

        assert result is not None
        assert "contents" in result

    async def test_ping(self, client):
        """Test ping."""
        await client.connect()

        result = await client.ping()

        assert result["status"] == "ok"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_tools(self, client):
        """Test getting discovered tools."""
        await client.connect()

        tools = client.get_tools()

        assert isinstance(tools, list)

    async def test_get_resources(self, client):
        """Test getting discovered resources."""
        await client.connect()

        resources = client.get_resources()

        assert isinstance(resources, list)

    def test_get_metrics(self, client):
        """Test getting client metrics."""
        metrics = client.get_metrics()

        assert "server_id" in metrics
        assert "state" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_event_handlers(self, client):
        """Test event handlers."""
        connected = []
        disconnected = []

        def on_connect(conn):
            connected.append(conn)

        def on_disconnect(conn):
            disconnected.append(conn)

        client.on_connect(on_connect)
        client.on_disconnect(on_disconnect)

        await client.connect()
        assert len(connected) == 1

        await client.disconnect()
        assert len(disconnected) == 1


class TestMCPConnectionPool:
    """Tests for MCPConnectionPool."""

    @pytest.fixture
    def pool(self):
        """Create pool fixture."""
        from ...mcp_integration.client import MCPConnectionPool

        return MCPConnectionPool()

    async def test_add_server(self, pool):
        """Test adding a server to pool."""
        from ...mcp_integration.client import MCPClientConfig

        config = MCPClientConfig(
            server_url="http://localhost:8001",
            server_name="server-1",
        )

        client = await pool.add_server(config)

        assert client is not None
        assert client.is_connected is True

    async def test_remove_server(self, pool):
        """Test removing a server from pool."""
        from ...mcp_integration.client import MCPClientConfig

        config = MCPClientConfig(
            server_url="http://localhost:8002",
            server_name="server-2",
        )

        client = await pool.add_server(config)
        server_id = client.server_id

        success = await pool.remove_server(server_id)

        assert success is True
        assert pool.get_client(server_id) is None

    async def test_list_servers(self, pool):
        """Test listing servers in pool."""
        from ...mcp_integration.client import MCPClientConfig

        for i in range(3):
            config = MCPClientConfig(
                server_url=f"http://localhost:800{i}",
                server_name=f"server-{i}",
            )
            await pool.add_server(config)

        servers = pool.list_servers()

        assert len(servers) == 3

    async def test_disconnect_all(self, pool):
        """Test disconnecting all servers."""
        from ...mcp_integration.client import MCPClientConfig

        for i in range(2):
            config = MCPClientConfig(
                server_url=f"http://localhost:810{i}",
                server_name=f"dc-server-{i}",
            )
            await pool.add_server(config)

        await pool.disconnect_all()

        for server_info in pool.list_servers():
            client = pool.get_client(server_info.get("server_id", ""))
            if client:
                assert not client.is_connected

    def test_get_metrics(self, pool):
        """Test getting pool metrics."""
        metrics = pool.get_metrics()

        assert "total_servers" in metrics
        assert "max_connections" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH
