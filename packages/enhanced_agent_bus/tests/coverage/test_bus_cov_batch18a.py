"""
Coverage tests for:
  - enhanced_agent_bus.mcp.client
  - enhanced_agent_bus.mcp.config
  - enhanced_agent_bus.orchestration.market_based

Batch 18a - comprehensive branch and line coverage.
"""

from __future__ import annotations

import asyncio
import os
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from enhanced_agent_bus._compat.constants import MACIRole
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

# ---------------------------------------------------------------------------
# mcp.client
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp.client import (
    MCPClient,
    MCPClientConfig,
    MCPClientError,
    MCPClientState,
    MCPConnectionError,
    MCPMACIViolationError,
    MCPToolCallError,
    _role_may_call_tool,
    create_mcp_client,
)

# ---------------------------------------------------------------------------
# mcp.config
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp.config import (
    NEURAL_MCP_SERVER_NAME,
    TOOLBOX_SERVER_NAME,
    MCPConfig,
    MCPServerConfig,
    _default_neural_mcp_server,
    _default_toolbox_server,
    get_mcp_config,
    load_config,
    load_from_env,
    load_from_yaml,
)
from enhanced_agent_bus.mcp.types import MCPTool, MCPToolResult, MCPToolStatus

# ---------------------------------------------------------------------------
# orchestration.market_based
# ---------------------------------------------------------------------------
from enhanced_agent_bus.orchestration.market_based import (
    Bid,
    MarketBasedOrchestrator,
    TaskAuction,
)

# =========================================================================
# _role_may_call_tool
# =========================================================================


class TestRoleMayCallTool:
    def test_empty_role_uses_legacy_fallback(self):
        allowed, reason = _role_may_call_tool("", "execute_task")
        assert allowed is True
        assert reason == ""

    def test_unknown_role_is_rejected(self):
        allowed, reason = _role_may_call_tool("unknown_role", "execute_task")
        assert allowed is False
        assert "unknown or unmapped" in reason

    def test_judicial_cannot_execute(self):
        allowed, reason = _role_may_call_tool("judicial", "execute_command")
        assert allowed is False
        assert "judicial" in reason
        assert "execute_" in reason

    def test_judicial_cannot_propose(self):
        allowed, reason = _role_may_call_tool("judicial", "propose_amendment")
        assert allowed is False

    def test_judicial_can_validate(self):
        allowed, _ = _role_may_call_tool("judicial", "validate_constitution")
        assert allowed is True

    def test_monitor_cannot_approve(self):
        allowed, reason = _role_may_call_tool("monitor", "approve_task")
        assert allowed is False

    def test_monitor_cannot_write(self):
        allowed, _ = _role_may_call_tool("monitor", "write_config")
        assert allowed is False

    def test_auditor_cannot_modify(self):
        allowed, _ = _role_may_call_tool("auditor", "modify_record")
        assert allowed is False

    def test_auditor_cannot_delete(self):
        allowed, _ = _role_may_call_tool("auditor", "delete_record")
        assert allowed is False

    def test_executive_cannot_validate(self):
        allowed, _ = _role_may_call_tool("executive", "validate_output")
        assert allowed is False

    def test_executive_cannot_audit(self):
        allowed, _ = _role_may_call_tool("executive", "audit_log")
        assert allowed is False

    def test_executive_can_execute(self):
        allowed, _ = _role_may_call_tool("executive", "execute_task")
        assert allowed is True

    def test_implementer_cannot_validate(self):
        allowed, _ = _role_may_call_tool("implementer", "validate_result")
        assert allowed is False

    def test_implementer_can_execute(self):
        allowed, _ = _role_may_call_tool("implementer", "execute_task")
        assert allowed is True

    def test_case_insensitive_role(self):
        allowed, _ = _role_may_call_tool("JUDICIAL", "execute_task")
        assert allowed is False

    def test_case_insensitive_tool(self):
        allowed, _ = _role_may_call_tool("judicial", "EXECUTE_task")
        assert allowed is False

    def test_canonical_role_enum_is_accepted(self):
        allowed, _ = _role_may_call_tool(MACIRole.EXECUTIVE, "execute_task")
        assert allowed is True

    def test_unmapped_canonical_role_defaults_to_allow(self):
        allowed, reason = _role_may_call_tool(MACIRole.CONTROLLER, "policy_apply_v2")
        assert allowed is True
        assert reason == ""

    def test_legislative_role_defaults_to_allow_when_not_restricted(self):
        allowed, reason = _role_may_call_tool("legislative", "query_policy_state")
        assert allowed is True
        assert reason == ""


# =========================================================================
# MCPClientConfig
# =========================================================================


class TestMCPClientConfig:
    def test_defaults(self):
        cfg = MCPClientConfig()
        assert cfg.server_url == "stdio"
        assert cfg.connect_timeout == 10.0
        assert cfg.call_timeout == 30.0
        assert cfg.max_retries == 2
        assert cfg.enforce_maci is True
        assert cfg.server_id.startswith("mcp-server-")

    def test_custom_values(self):
        cfg = MCPClientConfig(
            server_url="http://localhost:9000",
            server_id="test-server",
            connect_timeout=5.0,
            call_timeout=15.0,
            max_retries=0,
            enforce_maci=False,
            metadata={"env": "test"},
        )
        assert cfg.server_url == "http://localhost:9000"
        assert cfg.server_id == "test-server"
        assert cfg.max_retries == 0
        assert cfg.enforce_maci is False
        assert cfg.metadata == {"env": "test"}


# =========================================================================
# MCPClientState
# =========================================================================


class TestMCPClientState:
    def test_enum_values(self):
        assert MCPClientState.DISCONNECTED.value == "disconnected"
        assert MCPClientState.CONNECTING.value == "connecting"
        assert MCPClientState.CONNECTED.value == "connected"
        assert MCPClientState.DISCONNECTING.value == "disconnecting"
        assert MCPClientState.ERROR.value == "error"


# =========================================================================
# MCPClientError hierarchy
# =========================================================================


class TestMCPClientErrors:
    def test_base_error(self):
        err = MCPClientError("test error", server_id="srv-1")
        assert str(err) == "test error"
        assert err.server_id == "srv-1"
        assert err.constitutional_hash  # should have a value

    def test_connection_error_is_client_error(self):
        err = MCPConnectionError("connect fail")
        assert isinstance(err, MCPClientError)

    def test_tool_call_error(self):
        err = MCPToolCallError("tool fail")
        assert isinstance(err, MCPClientError)

    def test_maci_violation_error(self):
        err = MCPMACIViolationError("violation")
        assert isinstance(err, MCPClientError)


# =========================================================================
# MCPClient
# =========================================================================


class TestMCPClient:
    def test_initial_state(self):
        client = MCPClient()
        assert client.state == MCPClientState.DISCONNECTED
        assert client.is_connected is False
        assert client.server_id.startswith("mcp-server-")
        assert client.constitutional_hash

    def test_repr(self):
        client = MCPClient(MCPClientConfig(server_id="test-srv"))
        r = repr(client)
        assert "test-srv" in r
        assert "disconnected" in r

    async def test_connect_disconnect(self):
        client = MCPClient()
        await client.connect()
        assert client.state == MCPClientState.CONNECTED
        assert client.is_connected is True

        await client.disconnect()
        assert client.state == MCPClientState.DISCONNECTED
        assert client.is_connected is False

    async def test_connect_already_connected_is_noop(self):
        client = MCPClient()
        await client.connect()
        await client.connect()  # should be no-op
        assert client.is_connected is True
        await client.disconnect()

    async def test_disconnect_already_disconnected_is_noop(self):
        client = MCPClient()
        await client.disconnect()  # no-op
        assert client.state == MCPClientState.DISCONNECTED

    async def test_connect_timeout(self):
        client = MCPClient(MCPClientConfig(connect_timeout=0.01))

        async def slow_connect():
            await asyncio.sleep(10)

        client._do_connect = slow_connect  # type: ignore[assignment]

        with pytest.raises(MCPConnectionError, match="timed out"):
            await client.connect()
        assert client.state == MCPClientState.ERROR

    async def test_connect_generic_error(self):
        client = MCPClient()

        async def fail_connect():
            raise RuntimeError("boom")

        client._do_connect = fail_connect  # type: ignore[assignment]

        with pytest.raises(MCPConnectionError, match="boom"):
            await client.connect()
        assert client.state == MCPClientState.ERROR

    async def test_connect_from_error_state(self):
        """After an error, connect should work again (transitions ERROR -> CONNECTING)."""
        client = MCPClient()

        async def fail_once():
            raise RuntimeError("first fail")

        client._do_connect = fail_once  # type: ignore[assignment]
        with pytest.raises(MCPConnectionError):
            await client.connect()
        assert client.state == MCPClientState.ERROR

        # Now fix and retry
        client._do_connect = AsyncMock()  # type: ignore[assignment]
        await client.connect()
        assert client.is_connected is True
        await client.disconnect()

    async def test_disconnect_with_error_in_do_disconnect(self):
        client = MCPClient()
        await client.connect()

        async def fail_disconnect():
            raise RuntimeError("disconnect boom")

        client._do_disconnect = fail_disconnect  # type: ignore[assignment]
        await client.disconnect()
        # Should still end up disconnected
        assert client.state == MCPClientState.DISCONNECTED

    async def test_context_manager(self):
        async with MCPClient() as client:
            assert client.is_connected is True
        assert client.state == MCPClientState.DISCONNECTED

    async def test_list_tools_not_connected(self):
        client = MCPClient()
        with pytest.raises(RuntimeError, match="Cannot perform"):
            await client.list_tools()

    async def test_list_tools(self):
        client = MCPClient()
        tools = [
            MCPTool(name="tool1", description="desc1", input_schema={}),
            MCPTool(name="tool2", description="desc2", input_schema={}),
        ]
        client._fetch_tools = AsyncMock(return_value=tools)  # type: ignore[assignment]
        await client.connect()
        result = await client.list_tools()
        assert len(result) == 2
        assert result[0].name == "tool1"
        await client.disconnect()

    async def test_call_tool_not_connected(self):
        client = MCPClient()
        with pytest.raises(RuntimeError, match="Cannot perform"):
            await client.call_tool("test_tool")

    async def test_call_tool_success(self):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value={"result": "ok"})  # type: ignore[assignment]
            result = await client.call_tool(
                "search_docs",
                arguments={"q": "test"},
                agent_id="agent-1",
                maci_role="executive",
            )
            assert result.status == MCPToolStatus.SUCCESS
            assert result.content == {"result": "ok"}

    async def test_call_tool_maci_forbidden_returns_result(self):
        async with MCPClient() as client:
            result = await client.call_tool(
                "execute_command",
                agent_id="agent-1",
                maci_role="judicial",
            )
            assert result.status == MCPToolStatus.FORBIDDEN
            assert "judicial" in (result.error or "")

    async def test_call_tool_maci_forbidden_raises(self):
        async with MCPClient() as client:
            with pytest.raises(MCPMACIViolationError):
                await client.call_tool(
                    "execute_command",
                    agent_id="agent-1",
                    maci_role="judicial",
                    raise_on_forbidden=True,
                )

    async def test_call_tool_maci_not_enforced(self):
        cfg = MCPClientConfig(enforce_maci=False)
        async with MCPClient(cfg) as client:
            client._do_call_tool = AsyncMock(return_value="ok")  # type: ignore[assignment]
            result = await client.call_tool(
                "execute_command",
                maci_role="judicial",
            )
            assert result.status == MCPToolStatus.SUCCESS

    async def test_call_tool_no_role_uses_legacy_fallback(self):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value="ok")  # type: ignore[assignment]
            result = await client.call_tool("execute_command", maci_role="")
            assert result.status == MCPToolStatus.SUCCESS
            assert result.error is None

    async def test_call_tool_unknown_role_is_forbidden(self):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value="ok")  # type: ignore[assignment]
            result = await client.call_tool("execute_command", maci_role="unknown_role")
            assert result.status == MCPToolStatus.FORBIDDEN
            assert "unknown or unmapped" in (result.error or "")

    @pytest.mark.parametrize("maci_role", [MACIRole.CONTROLLER, "legislative"])
    async def test_call_tool_allows_unmapped_canonical_roles(self, maci_role: object):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value="ok")  # type: ignore[assignment]
            result = await client.call_tool("query_policy_state", maci_role=maci_role)
            assert result.status == MCPToolStatus.SUCCESS
            assert result.content == "ok"

    async def test_call_tool_timeout(self):
        async with MCPClient(MCPClientConfig(call_timeout=0.01)) as client:

            async def slow_tool(name: str, args: dict) -> Any:
                await asyncio.sleep(10)

            client._do_call_tool = slow_tool  # type: ignore[assignment]
            result = await client.call_tool("slow_tool", maci_role="executive")
            assert result.status == MCPToolStatus.TIMEOUT
            assert "timed out" in (result.error or "")

    async def test_call_tool_retry_then_fail(self):
        cfg = MCPClientConfig(max_retries=1, call_timeout=5.0)
        async with MCPClient(cfg) as client:
            call_count = 0

            async def fail_tool(name: str, args: dict) -> Any:
                nonlocal call_count
                call_count += 1
                raise ValueError("transient error")

            client._do_call_tool = fail_tool  # type: ignore[assignment]
            result = await client.call_tool("flaky_tool", maci_role="executive")
            assert result.status == MCPToolStatus.ERROR
            assert "transient error" in (result.error or "")
            assert call_count == 2  # 1 initial + 1 retry

    async def test_call_tool_retry_success_on_second(self):
        cfg = MCPClientConfig(max_retries=2, call_timeout=5.0)
        async with MCPClient(cfg) as client:
            attempts = 0

            async def flaky_tool(name: str, args: dict) -> Any:
                nonlocal attempts
                attempts += 1
                if attempts < 2:
                    raise ValueError("transient")
                return "recovered"

            client._do_call_tool = flaky_tool  # type: ignore[assignment]
            result = await client.call_tool("flaky_tool", maci_role="executive")
            assert result.status == MCPToolStatus.SUCCESS
            assert result.content == "recovered"

    async def test_call_tool_with_metadata(self):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value="ok")  # type: ignore[assignment]
            result = await client.call_tool(
                "test_tool",
                maci_role="executive",
                metadata={"trace_id": "abc"},
            )
            assert result.status == MCPToolStatus.SUCCESS
            assert result.metadata.get("trace_id") == "abc"

    async def test_call_tool_custom_timeout(self):
        async with MCPClient() as client:
            client._do_call_tool = AsyncMock(return_value="fast")  # type: ignore[assignment]
            result = await client.call_tool("test_tool", timeout=1.0, maci_role="executive")
            assert result.status == MCPToolStatus.SUCCESS

    async def test_require_connected_guard(self):
        client = MCPClient()
        with pytest.raises(RuntimeError, match="call_tool"):
            client._require_connected("call_tool")


# =========================================================================
# create_mcp_client factory
# =========================================================================


class TestCreateMCPClient:
    def test_default_factory(self):
        client = create_mcp_client()
        assert isinstance(client, MCPClient)
        assert client.server_id.startswith("mcp-")

    def test_custom_factory(self):
        client = create_mcp_client(
            server_url="http://localhost:9000",
            server_id="my-server",
            enforce_maci=False,
            connect_timeout=5.0,
            call_timeout=15.0,
        )
        assert client.server_id == "my-server"

    def test_auto_generated_server_id(self):
        client = create_mcp_client(server_id="")
        assert client.server_id.startswith("mcp-")


# =========================================================================
# MCPServerConfig (mcp.config)
# =========================================================================


class TestMCPServerConfig:
    def test_http_server_config(self):
        cfg = MCPServerConfig(
            name="test-http",
            transport="http",
            url="http://localhost:5000",
        )
        assert cfg.name == "test-http"
        assert cfg.transport == "http"
        assert cfg.url == "http://localhost:5000"
        assert cfg.timeout == 30.0
        assert cfg.enabled is True

    def test_stdio_server_config(self):
        cfg = MCPServerConfig(
            name="test-stdio",
            transport="stdio",
            command=["node", "index.js"],
        )
        assert cfg.command == ["node", "index.js"]

    def test_sse_server_config(self):
        cfg = MCPServerConfig(
            name="test-sse",
            transport="sse",
            url="http://localhost:5000/sse",
        )
        assert cfg.transport == "sse"

    def test_name_whitespace_stripped(self):
        cfg = MCPServerConfig(
            name="  test-server  ",
            transport="stdio",
            command=["node"],
        )
        assert cfg.name == "test-server"

    def test_blank_name_rejected(self):
        with pytest.raises(PydanticValidationError):
            MCPServerConfig(name="   ", transport="stdio", command=["node"])

    def test_url_trailing_slash_stripped(self):
        cfg = MCPServerConfig(
            name="srv",
            transport="http",
            url="http://localhost:5000/",
        )
        assert cfg.url == "http://localhost:5000"

    def test_invalid_url_scheme(self):
        with pytest.raises(Exception, match="http"):
            MCPServerConfig(name="srv", transport="http", url="ftp://bad")

    def test_https_url_valid(self):
        cfg = MCPServerConfig(name="srv", transport="http", url="https://secure.example.com")
        assert cfg.url == "https://secure.example.com"

    def test_ws_url_valid(self):
        cfg = MCPServerConfig(name="srv", transport="http", url="ws://localhost:8080")
        assert cfg.url is not None

    def test_wss_url_valid(self):
        cfg = MCPServerConfig(name="srv", transport="http", url="wss://secure.ws")
        assert cfg.url is not None

    def test_empty_command_rejected(self):
        with pytest.raises(Exception, match="at least one element"):
            MCPServerConfig(name="srv", transport="stdio", command=[])

    def test_http_requires_url(self):
        with pytest.raises(Exception, match="url"):
            MCPServerConfig(name="srv", transport="http")

    def test_sse_requires_url(self):
        with pytest.raises(Exception, match="url"):
            MCPServerConfig(name="srv", transport="sse")

    def test_stdio_requires_command(self):
        with pytest.raises(Exception, match="command"):
            MCPServerConfig(name="srv", transport="stdio")

    def test_as_dict_masks_auth_token(self):
        cfg = MCPServerConfig(
            name="srv",
            transport="http",
            url="http://localhost",
            auth_token="secret-token",
        )
        d = cfg.as_dict()
        assert d["auth_token"] == "***"

    def test_as_dict_no_auth_token(self):
        cfg = MCPServerConfig(
            name="srv",
            transport="http",
            url="http://localhost",
        )
        d = cfg.as_dict()
        assert d["auth_token"] is None

    def test_url_none_passes_validator(self):
        cfg = MCPServerConfig(name="srv", transport="stdio", command=["node"])
        assert cfg.url is None

    def test_command_none_passes_validator(self):
        cfg = MCPServerConfig(name="srv", transport="http", url="http://localhost")
        assert cfg.command is None


# =========================================================================
# MCPConfig
# =========================================================================


class TestMCPConfig:
    def test_defaults(self):
        cfg = MCPConfig()
        assert cfg.enabled is True
        assert cfg.servers == []
        assert cfg.maci_role_overrides == {}

    def test_with_servers(self):
        srv = MCPServerConfig(name="s1", transport="http", url="http://localhost")
        cfg = MCPConfig(servers=[srv])
        assert len(cfg.servers) == 1

    def test_duplicate_server_names_rejected(self):
        srv1 = MCPServerConfig(name="dup", transport="http", url="http://a")
        srv2 = MCPServerConfig(name="dup", transport="http", url="http://b")
        with pytest.raises(Exception, match="Duplicate"):
            MCPConfig(servers=[srv1, srv2])

    def test_get_server_found(self):
        srv = MCPServerConfig(name="found", transport="http", url="http://a")
        cfg = MCPConfig(servers=[srv])
        assert cfg.get_server("found") is srv

    def test_get_server_not_found(self):
        cfg = MCPConfig()
        assert cfg.get_server("nope") is None

    def test_enabled_servers(self):
        srv1 = MCPServerConfig(name="a", transport="http", url="http://a", enabled=True)
        srv2 = MCPServerConfig(name="b", transport="http", url="http://b", enabled=False)
        cfg = MCPConfig(servers=[srv1, srv2])
        enabled = cfg.enabled_servers
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_as_dict(self):
        cfg = MCPConfig(
            servers=[MCPServerConfig(name="x", transport="http", url="http://x")],
            maci_role_overrides={"x": {"proposer", "validator"}},
        )
        d = cfg.as_dict()
        assert d["enabled"] is True
        assert len(d["servers"]) == 1
        assert isinstance(d["maci_role_overrides"]["x"], list)

    def test_wrong_constitutional_hash_rejected(self):
        with pytest.raises(Exception, match="constitutional_hash"):
            MCPConfig(constitutional_hash="wrong_hash")


# =========================================================================
# Default server builders
# =========================================================================


class TestDefaultServers:
    def test_default_neural_mcp_server(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove env vars that might interfere
            env = {k: v for k, v in os.environ.items() if not k.startswith("NEURAL_MCP")}
            with patch.dict(os.environ, env, clear=True):
                srv = _default_neural_mcp_server()
                assert srv.name == NEURAL_MCP_SERVER_NAME
                assert srv.transport == "stdio"
                assert srv.command is not None

    def test_neural_mcp_custom_command(self):
        with patch.dict(os.environ, {"NEURAL_MCP_COMMAND": '["python", "server.py"]'}):
            srv = _default_neural_mcp_server()
            assert srv.command == ["python", "server.py"]

    def test_neural_mcp_bad_command_json(self):
        with patch.dict(os.environ, {"NEURAL_MCP_COMMAND": "not-json"}):
            srv = _default_neural_mcp_server()
            # Falls back to default command
            assert srv.command == ["node", "/app/neural-mcp/dist/index.js"]

    def test_neural_mcp_command_not_list(self):
        with patch.dict(os.environ, {"NEURAL_MCP_COMMAND": '"just-a-string"'}):
            srv = _default_neural_mcp_server()
            assert srv.command == ["node", "/app/neural-mcp/dist/index.js"]

    def test_neural_mcp_disabled(self):
        with patch.dict(os.environ, {"NEURAL_MCP_ENABLED": "false"}):
            srv = _default_neural_mcp_server()
            assert srv.enabled is False

    def test_neural_mcp_disabled_zero(self):
        with patch.dict(os.environ, {"NEURAL_MCP_ENABLED": "0"}):
            srv = _default_neural_mcp_server()
            assert srv.enabled is False

    def test_default_toolbox_server(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("TOOLBOX_URL", "TOOLBOX_AUTH_TOKEN", "TOOLBOX_ENABLED", "TOOLBOX_TIMEOUT")
        }
        with patch.dict(os.environ, env, clear=True):
            srv = _default_toolbox_server()
            assert srv.name == TOOLBOX_SERVER_NAME
            assert srv.transport == "http"
            assert srv.url == "http://toolbox:5000"

    def test_toolbox_custom_url(self):
        with patch.dict(os.environ, {"TOOLBOX_URL": "http://custom:8080"}):
            srv = _default_toolbox_server()
            assert srv.url == "http://custom:8080"

    def test_toolbox_disabled(self):
        with patch.dict(os.environ, {"TOOLBOX_ENABLED": "off"}):
            srv = _default_toolbox_server()
            assert srv.enabled is False

    def test_toolbox_custom_timeout(self):
        with patch.dict(os.environ, {"TOOLBOX_TIMEOUT": "60.0"}):
            srv = _default_toolbox_server()
            assert srv.timeout == 60.0

    def test_toolbox_bad_timeout(self):
        with patch.dict(os.environ, {"TOOLBOX_TIMEOUT": "not-a-number"}):
            srv = _default_toolbox_server()
            assert srv.timeout == 30.0  # default fallback

    def test_toolbox_negative_timeout(self):
        with patch.dict(os.environ, {"TOOLBOX_TIMEOUT": "-5"}):
            srv = _default_toolbox_server()
            assert srv.timeout == 30.0  # default fallback

    def test_toolbox_with_auth_token(self):
        with patch.dict(os.environ, {"TOOLBOX_AUTH_TOKEN": "my-token"}):
            srv = _default_toolbox_server()
            assert srv.auth_token == "my-token"


# =========================================================================
# load_from_env
# =========================================================================


class TestLoadFromEnv:
    def test_defaults(self):
        cfg = load_from_env()
        assert isinstance(cfg, MCPConfig)
        assert len(cfg.servers) == 2

    def test_mcp_disabled(self):
        with patch.dict(os.environ, {"MCP_ENABLED": "false"}):
            cfg = load_from_env()
            assert cfg.enabled is False

    def test_mcp_disabled_no(self):
        with patch.dict(os.environ, {"MCP_ENABLED": "no"}):
            cfg = load_from_env()
            assert cfg.enabled is False


# =========================================================================
# load_from_yaml
# =========================================================================


class TestLoadFromYaml:
    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_from_yaml(tmp_path / "nonexistent.yaml")

    def test_valid_yaml(self, tmp_path: Path):
        from enhanced_agent_bus.mcp.config import _CONSTITUTIONAL_HASH

        yaml_content = textwrap.dedent(f"""\
            enabled: true
            constitutional_hash: "{_CONSTITUTIONAL_HASH}"
            servers:
              - name: test-srv
                transport: http
                url: http://localhost:5000
                timeout: 10.0
                enabled: true
        """)
        yaml_file = tmp_path / "mcp.yaml"
        yaml_file.write_text(yaml_content)
        cfg = load_from_yaml(yaml_file)
        assert cfg.enabled is True
        assert len(cfg.servers) == 1
        assert cfg.servers[0].name == "test-srv"

    def test_yaml_not_mapping(self, tmp_path: Path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(Exception, match="mapping"):
            load_from_yaml(yaml_file)

    def test_yaml_with_role_overrides(self, tmp_path: Path):
        from enhanced_agent_bus.mcp.config import _CONSTITUTIONAL_HASH

        yaml_content = textwrap.dedent(f"""\
            enabled: true
            constitutional_hash: "{_CONSTITUTIONAL_HASH}"
            servers:
              - name: gov
                transport: http
                url: http://localhost:5000
            maci_role_overrides:
              gov:
                - proposer
                - validator
        """)
        yaml_file = tmp_path / "mcp.yaml"
        yaml_file.write_text(yaml_content)
        cfg = load_from_yaml(yaml_file)
        assert "proposer" in cfg.maci_role_overrides["gov"]

    def test_yaml_validation_error(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            enabled: true
            constitutional_hash: "wrong_hash"
            servers: []
        """)
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml_content)
        with pytest.raises(ACGSValidationError):
            load_from_yaml(yaml_file)


# =========================================================================
# load_config
# =========================================================================


class TestLoadConfig:
    def test_no_yaml_env_falls_back_to_env(self):
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": ""}, clear=False):
            cfg = load_config()
            assert isinstance(cfg, MCPConfig)

    def test_yaml_env_file_missing(self, tmp_path: Path):
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "missing.yaml")}):
            cfg = load_config()
            assert isinstance(cfg, MCPConfig)

    def test_yaml_env_file_exists(self, tmp_path: Path):
        from enhanced_agent_bus.mcp.config import _CONSTITUTIONAL_HASH

        yaml_file = tmp_path / "mcp.yaml"
        yaml_file.write_text(
            textwrap.dedent(f"""\
            enabled: false
            constitutional_hash: "{_CONSTITUTIONAL_HASH}"
            servers:
              - name: yaml-srv
                transport: stdio
                command: ["echo"]
        """)
        )
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": str(yaml_file)}):
            cfg = load_config()
            assert cfg.enabled is False

    def test_yaml_env_file_bad_content(self, tmp_path: Path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("not: valid: yaml: {{{{")
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": str(yaml_file)}):
            # Should fall back to env loading
            cfg = load_config()
            assert isinstance(cfg, MCPConfig)


# =========================================================================
# get_mcp_config (singleton)
# =========================================================================


class TestGetMCPConfig:
    def test_returns_config(self):
        import enhanced_agent_bus.mcp.config as config_mod

        config_mod._cached_config = None
        cfg = get_mcp_config()
        assert isinstance(cfg, MCPConfig)

    def test_cached(self):
        import enhanced_agent_bus.mcp.config as config_mod

        config_mod._cached_config = None
        cfg1 = get_mcp_config()
        cfg2 = get_mcp_config()
        assert cfg1 is cfg2

    def test_reload(self):
        import enhanced_agent_bus.mcp.config as config_mod

        config_mod._cached_config = None
        cfg1 = get_mcp_config()
        cfg2 = get_mcp_config(reload=True)
        # New object, not the same
        assert cfg1 is not cfg2


# =========================================================================
# Bid
# =========================================================================


class TestBid:
    def test_composite_score(self):
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=10.0,
            capability_score=0.8,
            availability_score=0.6,
            estimated_completion_time=30.0,
        )
        expected = 10.0 * 0.5 + (1.0 - 0.8) * 0.3 + (1.0 - 0.6) * 0.2
        assert abs(bid.composite_score - expected) < 1e-9

    def test_perfect_bid(self):
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=0.0,
            capability_score=1.0,
            availability_score=1.0,
            estimated_completion_time=1.0,
        )
        assert bid.composite_score == 0.0

    def test_defaults(self):
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=5.0,
            capability_score=0.5,
            availability_score=0.5,
            estimated_completion_time=10.0,
        )
        assert isinstance(bid.timestamp, datetime)
        assert bid.metadata == {}


# =========================================================================
# TaskAuction
# =========================================================================


class TestTaskAuction:
    def _make_bid(
        self, agent_id: str = "a1", amount: float = 5.0, capabilities: list[str] | None = None
    ) -> Bid:
        return Bid(
            agent_id=agent_id,
            task_id="t1",
            bid_amount=amount,
            capability_score=0.8,
            availability_score=0.9,
            estimated_completion_time=30.0,
            metadata={"capabilities": capabilities or []},
        )

    def test_add_bid_open(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test task",
            task_requirements=[],
        )
        bid = self._make_bid()
        assert auction.add_bid(bid) is True
        assert len(auction.bids) == 1

    def test_add_bid_closed(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            status="closed",
        )
        assert auction.add_bid(self._make_bid()) is False

    def test_add_bid_past_deadline(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            deadline=past,
        )
        assert auction.add_bid(self._make_bid()) is False
        assert auction.status == "closed"

    def test_add_bid_exceeds_max(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            max_bid_amount=3.0,
        )
        bid = self._make_bid(amount=5.0)
        assert auction.add_bid(bid) is False

    def test_add_bid_under_max(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            max_bid_amount=10.0,
        )
        bid = self._make_bid(amount=5.0)
        assert auction.add_bid(bid) is True

    def test_add_bid_missing_capabilities(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=["nlp", "vision"],
        )
        bid = self._make_bid(capabilities=["nlp"])
        assert auction.add_bid(bid) is False

    def test_add_bid_has_capabilities(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=["nlp", "vision"],
        )
        bid = self._make_bid(capabilities=["nlp", "vision", "audio"])
        assert auction.add_bid(bid) is True

    def test_select_winner_no_bids(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
        )
        assert auction.select_winner() is None

    def test_select_winner_picks_best(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
        )
        bid_high = Bid(
            agent_id="expensive",
            task_id="t1",
            bid_amount=100.0,
            capability_score=0.5,
            availability_score=0.5,
            estimated_completion_time=30.0,
            metadata={"capabilities": []},
        )
        bid_low = Bid(
            agent_id="cheap",
            task_id="t1",
            bid_amount=1.0,
            capability_score=0.9,
            availability_score=0.9,
            estimated_completion_time=10.0,
            metadata={"capabilities": []},
        )
        auction.add_bid(bid_high)
        auction.add_bid(bid_low)
        winner = auction.select_winner()
        assert winner is not None
        assert winner.agent_id == "cheap"
        assert auction.status == "awarded"

    def test_close_auction_open(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
        )
        bid = self._make_bid()
        auction.add_bid(bid)
        winner = auction.close_auction()
        assert winner is not None
        assert auction.status == "awarded"

    def test_close_auction_already_closed(self):
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            status="closed",
        )
        result = auction.close_auction()
        assert result is None  # winning_bid is None


# =========================================================================
# MarketBasedOrchestrator
# =========================================================================


class TestMarketBasedOrchestrator:
    def test_init(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=10.0)
        assert orch.auction_timeout_seconds == 10.0
        assert len(orch.active_auctions) == 0
        assert len(orch.completed_auctions) == 0

    def test_register_agent(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("agent-1", ["nlp", "vision"], base_cost=2.0)
        assert "agent-1" in orch.registered_agents
        info = orch.registered_agents["agent-1"]
        assert info["capabilities"] == ["nlp", "vision"]
        assert info["base_cost"] == 2.0
        assert info["active_tasks"] == 0

    def test_register_agent_with_metadata(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("agent-1", ["nlp"], metadata={"region": "us-east"})
        assert orch.registered_agents["agent-1"]["metadata"] == {"region": "us-east"}

    async def test_create_auction(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=60.0)
        auction = await orch.create_auction(
            task_id="t1",
            task_description="Test task",
            task_requirements=["nlp"],
        )
        assert auction.task_id == "t1"
        assert "t1" in orch.active_auctions
        # Clean up background task
        for task in orch._background_tasks:
            task.cancel()

    async def test_create_auction_with_deadline(self):
        orch = MarketBasedOrchestrator()
        auction = await orch.create_auction(
            task_id="t1",
            task_description="Test",
            task_requirements=[],
            deadline_seconds=10.0,
        )
        assert auction.deadline is not None
        # No background task should be created when deadline is set
        # (background tasks only for non-deadline auctions)

    async def test_submit_bid_unregistered_agent(self):
        orch = MarketBasedOrchestrator()
        await orch.create_auction("t1", "Test", [])
        result = await orch.submit_bid("unregistered", "t1", 5.0, 0.8, 30.0)
        assert result is False
        for task in orch._background_tasks:
            task.cancel()

    async def test_submit_bid_no_auction(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", ["nlp"])
        result = await orch.submit_bid("a1", "no-auction", 5.0, 0.8, 30.0)
        assert result is False

    async def test_submit_bid_success(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", ["nlp"])
        await orch.create_auction("t1", "Test", ["nlp"])
        result = await orch.submit_bid("a1", "t1", 5.0, 0.8, 30.0)
        assert result is True
        assert len(orch.active_auctions["t1"].bids) == 1
        for task in orch._background_tasks:
            task.cancel()

    async def test_submit_bid_with_metadata(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", ["nlp"])
        await orch.create_auction("t1", "Test", ["nlp"])
        result = await orch.submit_bid("a1", "t1", 5.0, 0.8, 30.0, metadata={"priority": "high"})
        assert result is True
        for task in orch._background_tasks:
            task.cancel()

    async def test_run_auction_not_found(self):
        orch = MarketBasedOrchestrator()
        winner = await orch.run_auction("nonexistent", wait_for_bids=False)
        assert winner is None

    async def test_run_auction_no_wait(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", ["nlp"])
        await orch.create_auction("t1", "Test", ["nlp"])
        await orch.submit_bid("a1", "t1", 5.0, 0.8, 30.0)
        winner = await orch.run_auction("t1", wait_for_bids=False)
        assert winner is not None
        assert winner.agent_id == "a1"
        assert "t1" not in orch.active_auctions
        assert len(orch.completed_auctions) == 1
        for task in orch._background_tasks:
            task.cancel()

    async def test_run_auction_wait_timeout(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=0.1)
        orch.register_agent("a1", [])
        await orch.create_auction("t1", "Test", [])
        # Wait for 2 bids that never come - should timeout
        winner = await orch.run_auction("t1", wait_for_bids=True, min_bids=2)
        # No bids were submitted, so no winner
        assert winner is None
        for task in orch._background_tasks:
            task.cancel()

    def test_finalize_auction_with_winner(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", [])
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=5.0,
            capability_score=0.8,
            availability_score=0.9,
            estimated_completion_time=30.0,
            metadata={"capabilities": []},
        )
        auction.bids.append(bid)
        auction.select_winner()
        orch.active_auctions["t1"] = auction
        orch._finalize_auction("t1")
        assert "t1" not in orch.active_auctions
        assert len(orch.completed_auctions) == 1
        assert orch.registered_agents["a1"]["active_tasks"] == 1

    def test_finalize_auction_no_winner(self):
        orch = MarketBasedOrchestrator()
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        orch.active_auctions["t1"] = auction
        orch._finalize_auction("t1")
        assert len(orch.completed_auctions) == 1

    def test_finalize_auction_nonexistent(self):
        orch = MarketBasedOrchestrator()
        orch._finalize_auction("nonexistent")  # should not raise

    def test_get_auction_status_active(self):
        orch = MarketBasedOrchestrator()
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        orch.active_auctions["t1"] = auction
        status = orch.get_auction_status("t1")
        assert status is not None
        assert status["task_id"] == "t1"
        assert status["status"] == "open"
        assert status["winning_bid"] is None

    def test_get_auction_status_completed(self):
        orch = MarketBasedOrchestrator()
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=5.0,
            capability_score=0.8,
            availability_score=0.9,
            estimated_completion_time=30.0,
            metadata={"capabilities": []},
        )
        auction.bids.append(bid)
        auction.select_winner()
        orch.completed_auctions.append(auction)
        status = orch.get_auction_status("t1")
        assert status is not None
        assert status["winning_bid"]["agent_id"] == "a1"

    def test_get_auction_status_not_found(self):
        orch = MarketBasedOrchestrator()
        assert orch.get_auction_status("nonexistent") is None

    def test_get_market_stats_empty(self):
        orch = MarketBasedOrchestrator()
        stats = orch.get_market_stats()
        assert stats["active_auctions"] == 0
        assert stats["completed_auctions"] == 0
        assert stats["registered_agents"] == 0
        assert stats["total_bids"] == 0

    def test_get_market_stats_with_data(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", [])
        orch.register_agent("a2", [])
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=5.0,
            capability_score=0.8,
            availability_score=0.9,
            estimated_completion_time=30.0,
            metadata={"capabilities": []},
        )
        auction.bids.append(bid)
        orch.active_auctions["t1"] = auction
        stats = orch.get_market_stats()
        assert stats["active_auctions"] == 1
        assert stats["registered_agents"] == 2
        assert stats["total_bids"] == 1

    async def test_auto_close_auction(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=0.05)
        orch.register_agent("a1", [])
        auction = TaskAuction(task_id="t1", task_description="test", task_requirements=[])
        bid = Bid(
            agent_id="a1",
            task_id="t1",
            bid_amount=5.0,
            capability_score=0.8,
            availability_score=0.9,
            estimated_completion_time=30.0,
            metadata={"capabilities": []},
        )
        auction.bids.append(bid)
        orch.active_auctions["t1"] = auction
        await orch._auto_close_auction("t1")
        assert "t1" not in orch.active_auctions
        assert len(orch.completed_auctions) == 1

    async def test_auto_close_auction_already_closed(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=0.01)
        auction = TaskAuction(
            task_id="t1",
            task_description="test",
            task_requirements=[],
            status="closed",
        )
        orch.active_auctions["t1"] = auction
        await orch._auto_close_auction("t1")
        # Should not finalize since status is not "open"
        assert "t1" in orch.active_auctions

    async def test_auto_close_auction_not_found(self):
        orch = MarketBasedOrchestrator(auction_timeout_seconds=0.01)
        await orch._auto_close_auction("nonexistent")  # should not raise

    async def test_availability_score_computation(self):
        orch = MarketBasedOrchestrator()
        orch.register_agent("a1", ["nlp"])
        orch.registered_agents["a1"]["active_tasks"] = 5
        orch.registered_agents["a1"]["max_concurrent_tasks"] = 10
        await orch.create_auction("t1", "Test", ["nlp"])
        result = await orch.submit_bid("a1", "t1", 5.0, 0.8, 30.0)
        assert result is True
        bid = orch.active_auctions["t1"].bids[0]
        assert abs(bid.availability_score - 0.5) < 1e-9
        for task in orch._background_tasks:
            task.cancel()
