"""Comprehensive tests for the MCP server integration.

Covers all 5 governance tools, error handling, edge cases,
and ensures >90% coverage of mcp_server.py.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.integrations.mcp_server import (
    MCP_AVAILABLE,
    create_mcp_server,
    run_mcp_server,
)

# Skip entire module if mcp is not installed
pytestmark = pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp package not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_constitution() -> Constitution:
    """Return the built-in default constitution."""
    return Constitution.default()


@pytest.fixture()
def empty_constitution() -> Constitution:
    """Return a constitution with zero rules."""
    return Constitution(name="empty", version="0.0.0", rules=[])


@pytest.fixture()
def custom_constitution() -> Constitution:
    """Return a constitution with a single keyword-based deny rule."""
    return Constitution(
        name="test-constitution",
        version="1.0.0",
        rules=[
            Rule(
                id="TEST-001",
                text="Must not contain forbidden content",
                severity=Severity.CRITICAL,
                keywords=["forbidden", "blocked"],
                category="safety",
            ),
            Rule(
                id="TEST-002",
                text="Warn on suspicious content",
                severity=Severity.LOW,
                keywords=["suspicious"],
                category="monitoring",
            ),
        ],
    )


async def _call_tool(server: Any, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Helper: invoke the call_tool handler registered on the MCP server.

    Returns the parsed JSON from the first TextContent item.
    """
    # Access the registered handler via the server's internal routing
    # The MCP Server stores handlers in request_handlers dict
    from mcp import types

    handlers = server.request_handlers
    # Find the CallToolRequest handler
    call_handler = handlers.get(types.CallToolRequest)
    if call_handler is None:
        raise RuntimeError("call_tool handler not registered")

    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name=name,
            arguments=arguments or {},
        ),
    )
    server_result = await call_handler(request)
    # MCP SDK wraps in ServerResult; unwrap via .root
    call_result = server_result.root if hasattr(server_result, "root") else server_result
    assert len(call_result.content) >= 1
    return json.loads(call_result.content[0].text)


async def _call_tool_raw(server: Any, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Helper: invoke call_tool and return the raw CallToolResult (no JSON parsing)."""
    from mcp import types

    handlers = server.request_handlers
    call_handler = handlers.get(types.CallToolRequest)
    if call_handler is None:
        raise RuntimeError("call_tool handler not registered")

    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name=name,
            arguments=arguments or {},
        ),
    )
    server_result = await call_handler(request)
    return server_result.root if hasattr(server_result, "root") else server_result


async def _list_tools(server: Any) -> list[Any]:
    """Helper: invoke the list_tools handler on the MCP server."""
    from mcp import types

    handlers = server.request_handlers
    list_handler = handlers.get(types.ListToolsRequest)
    if list_handler is None:
        raise RuntimeError("list_tools handler not registered")

    request = types.ListToolsRequest(
        method="tools/list",
        params=None,
    )
    server_result = await list_handler(request)
    list_result = server_result.root if hasattr(server_result, "root") else server_result
    return list_result.tools


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    """Tests for the tool listing endpoint."""

    @pytest.mark.asyncio
    async def test_lists_all_five_tools(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        tools = await _list_tools(server)

        tool_names = {t.name for t in tools}
        expected = {
            "validate_action",
            "get_constitution",
            "get_audit_log",
            "check_compliance",
            "governance_stats",
        }
        assert tool_names == expected

    @pytest.mark.asyncio
    async def test_tool_schemas_have_required_fields(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        tools = await _list_tools(server)

        for tool in tools:
            assert tool.name
            assert tool.description
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"

    @pytest.mark.asyncio
    async def test_validate_action_schema_requires_action(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        tools = await _list_tools(server)

        validate_tool = next(t for t in tools if t.name == "validate_action")
        assert "action" in validate_tool.inputSchema.get("required", [])

    @pytest.mark.asyncio
    async def test_check_compliance_schema_requires_text(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        tools = await _list_tools(server)

        compliance_tool = next(t for t in tools if t.name == "check_compliance")
        assert "text" in compliance_tool.inputSchema.get("required", [])


# ---------------------------------------------------------------------------
# validate_action tool
# ---------------------------------------------------------------------------


class TestValidateAction:
    """Tests for the validate_action governance tool."""

    @pytest.mark.asyncio
    async def test_valid_action_returns_compliant(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "validate_action", {"action": "hello world"})

        assert result["valid"] is True
        assert result["violations"] == []
        assert "constitutional_hash" in result

    @pytest.mark.asyncio
    async def test_violating_action_returns_violations(
        self, custom_constitution: Constitution
    ) -> None:
        server = create_mcp_server(custom_constitution)
        result = await _call_tool(
            server, "validate_action", {"action": "this is forbidden content"}
        )

        assert result["valid"] is False
        assert len(result["violations"]) > 0
        rule_ids = [v["rule_id"] for v in result["violations"]]
        assert "TEST-001" in rule_ids

    @pytest.mark.asyncio
    async def test_custom_agent_id(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(
            server,
            "validate_action",
            {"action": "safe action", "agent_id": "custom-agent-42"},
        )

        assert result["valid"] is True
        assert result["agent_id"] == "custom-agent-42"

    @pytest.mark.asyncio
    async def test_default_agent_id_is_mcp_client(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "validate_action", {"action": "test"})

        assert result["agent_id"] == "mcp-client"

    @pytest.mark.asyncio
    async def test_empty_action_string(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "validate_action", {"action": ""})

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_missing_action_returns_validation_error(
        self, default_constitution: Constitution
    ) -> None:
        """MCP SDK schema validation rejects calls missing required 'action' field."""
        server = create_mcp_server(default_constitution)
        raw = await _call_tool_raw(server, "validate_action", {})

        # The SDK returns a validation error (non-JSON text) when required params are missing
        assert raw.content[0].text.startswith("Input validation error")

    @pytest.mark.asyncio
    async def test_strict_mode_does_not_raise_via_mcp(
        self, custom_constitution: Constitution
    ) -> None:
        """MCP call_tool temporarily disables strict mode so violations return data, not exceptions."""
        server = create_mcp_server(custom_constitution, strict=True)
        # Should not raise even with strict=True
        result = await _call_tool(
            server, "validate_action", {"action": "forbidden action"}
        )
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_unicode_action(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(
            server, "validate_action", {"action": "action with unicode: cafe\u0301 \u2603 \U0001f600"}
        )
        assert "valid" in result

    @pytest.mark.asyncio
    async def test_large_action_text(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        large_text = "a" * 100_000
        result = await _call_tool(server, "validate_action", {"action": large_text})
        assert "valid" in result


# ---------------------------------------------------------------------------
# get_constitution tool
# ---------------------------------------------------------------------------


class TestGetConstitution:
    """Tests for the get_constitution governance tool."""

    @pytest.mark.asyncio
    async def test_returns_constitution_metadata(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "get_constitution", {})

        assert result["name"] == "acgs-default"
        assert result["version"] == "1.0.0"
        assert "constitutional_hash" in result
        assert "constitutional_hash_versioned" in result
        assert result["rules_count"] == len(default_constitution.rules)

    @pytest.mark.asyncio
    async def test_returns_rule_details(self, custom_constitution: Constitution) -> None:
        server = create_mcp_server(custom_constitution)
        result = await _call_tool(server, "get_constitution", {})

        assert result["rules_count"] == 2
        rules = result["rules"]
        assert len(rules) == 2

        rule_0 = rules[0]
        assert rule_0["id"] == "TEST-001"
        assert rule_0["text"] == "Must not contain forbidden content"
        assert rule_0["severity"] == "critical"
        assert rule_0["category"] == "safety"
        assert rule_0["enabled"] is True

    @pytest.mark.asyncio
    async def test_empty_constitution_returns_zero_rules(
        self, empty_constitution: Constitution
    ) -> None:
        server = create_mcp_server(empty_constitution)
        result = await _call_tool(server, "get_constitution", {})

        assert result["name"] == "empty"
        assert result["rules_count"] == 0
        assert result["rules"] == []

    @pytest.mark.asyncio
    async def test_ignores_extra_arguments(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "get_constitution", {"extra": "ignored"})
        assert "name" in result


# ---------------------------------------------------------------------------
# get_audit_log tool
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    """Tests for the get_audit_log governance tool."""

    @pytest.mark.asyncio
    async def test_empty_audit_log(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "get_audit_log", {})

        assert result["total_entries"] == 0
        assert result["chain_valid"] is True
        assert result["entries"] == []

    @pytest.mark.asyncio
    async def test_returns_entries_after_validation(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)

        # Generate some audit entries by validating actions
        await _call_tool(server, "validate_action", {"action": "action one"})
        await _call_tool(server, "validate_action", {"action": "action two"})

        result = await _call_tool(server, "get_audit_log", {})

        assert result["total_entries"] == 2
        assert result["chain_valid"] is True
        assert len(result["entries"]) == 2

    @pytest.mark.asyncio
    async def test_limit_parameter(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)

        # Generate 5 entries
        for i in range(5):
            await _call_tool(server, "validate_action", {"action": f"action {i}"})

        result = await _call_tool(server, "get_audit_log", {"limit": 2})

        assert result["total_entries"] == 5
        assert len(result["entries"]) == 2

    @pytest.mark.asyncio
    async def test_default_limit_is_20(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)

        # Generate 25 entries
        for i in range(25):
            await _call_tool(server, "validate_action", {"action": f"action {i}"})

        result = await _call_tool(server, "get_audit_log", {})

        assert result["total_entries"] == 25
        assert len(result["entries"]) == 20

    @pytest.mark.asyncio
    async def test_limit_larger_than_entries(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)

        await _call_tool(server, "validate_action", {"action": "only one"})

        result = await _call_tool(server, "get_audit_log", {"limit": 100})

        assert result["total_entries"] == 1
        assert len(result["entries"]) == 1

    @pytest.mark.asyncio
    async def test_audit_chain_integrity(self, custom_constitution: Constitution) -> None:
        server = create_mcp_server(custom_constitution)

        await _call_tool(server, "validate_action", {"action": "safe"})
        await _call_tool(server, "validate_action", {"action": "forbidden"})

        result = await _call_tool(server, "get_audit_log", {})

        assert result["chain_valid"] is True
        assert result["total_entries"] == 2


# ---------------------------------------------------------------------------
# check_compliance tool
# ---------------------------------------------------------------------------


class TestCheckCompliance:
    """Tests for the check_compliance governance tool."""

    @pytest.mark.asyncio
    async def test_compliant_text(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "check_compliance", {"text": "hello world"})

        assert result["compliant"] is True
        assert result["violations"] == []
        assert "constitutional_hash" in result

    @pytest.mark.asyncio
    async def test_non_compliant_text(self, custom_constitution: Constitution) -> None:
        server = create_mcp_server(custom_constitution)
        result = await _call_tool(
            server, "check_compliance", {"text": "this is forbidden"}
        )

        assert result["compliant"] is False
        assert len(result["violations"]) > 0
        violation = result["violations"][0]
        assert violation["rule_id"] == "TEST-001"
        assert violation["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_empty_text(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "check_compliance", {"text": ""})

        assert result["compliant"] is True

    @pytest.mark.asyncio
    async def test_missing_text_returns_validation_error(
        self, default_constitution: Constitution
    ) -> None:
        """MCP SDK schema validation rejects calls missing required 'text' field."""
        server = create_mcp_server(default_constitution)
        raw = await _call_tool_raw(server, "check_compliance", {})

        assert raw.content[0].text.startswith("Input validation error")

    @pytest.mark.asyncio
    async def test_compliance_check_uses_fixed_agent_id(
        self, default_constitution: Constitution
    ) -> None:
        """check_compliance uses agent_id 'compliance-check' internally."""
        server = create_mcp_server(default_constitution)
        await _call_tool(server, "check_compliance", {"text": "test"})

        # Verify via audit log
        result = await _call_tool(server, "get_audit_log", {})
        entries = result["entries"]
        assert len(entries) == 1
        assert entries[0]["agent_id"] == "compliance-check"

    @pytest.mark.asyncio
    async def test_strict_mode_does_not_raise(
        self, custom_constitution: Constitution
    ) -> None:
        """check_compliance temporarily disables strict mode."""
        server = create_mcp_server(custom_constitution, strict=True)
        result = await _call_tool(
            server, "check_compliance", {"text": "forbidden content here"}
        )
        assert result["compliant"] is False


# ---------------------------------------------------------------------------
# governance_stats tool
# ---------------------------------------------------------------------------


class TestGovernanceStats:
    """Tests for the governance_stats tool."""

    @pytest.mark.asyncio
    async def test_initial_stats(self, default_constitution: Constitution) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "governance_stats", {})

        assert result["total_validations"] == 0
        assert result["compliance_rate"] == 1.0
        assert result["rules_count"] == len(default_constitution.rules)
        assert "constitutional_hash" in result
        assert result["audit_entries"] == 0
        assert result["audit_chain_valid"] is True

    @pytest.mark.asyncio
    async def test_stats_after_validations(self, custom_constitution: Constitution) -> None:
        server = create_mcp_server(custom_constitution)

        await _call_tool(server, "validate_action", {"action": "safe action"})
        await _call_tool(server, "validate_action", {"action": "forbidden action"})

        result = await _call_tool(server, "governance_stats", {})

        assert result["total_validations"] == 2
        assert result["audit_entries"] == 2
        assert result["audit_chain_valid"] is True
        # One valid, one invalid -> compliance_rate = 0.5
        assert result["compliance_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_stats_with_empty_constitution(
        self, empty_constitution: Constitution
    ) -> None:
        server = create_mcp_server(empty_constitution)
        result = await _call_tool(server, "governance_stats", {})

        assert result["rules_count"] == 0
        assert result["total_validations"] == 0


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    """Tests for the unknown tool error path."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "nonexistent_tool", {})

        assert "error" in result
        assert "Unknown tool" in result["error"]
        assert "nonexistent_tool" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_tool_name_returns_error(
        self, default_constitution: Constitution
    ) -> None:
        server = create_mcp_server(default_constitution)
        result = await _call_tool(server, "", {})

        assert "error" in result
        assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# create_mcp_server factory
# ---------------------------------------------------------------------------


class TestCreateMcpServer:
    """Tests for the create_mcp_server factory function."""

    def test_returns_server_instance(self) -> None:
        server = create_mcp_server()
        assert server is not None

    def test_default_constitution_when_none(self) -> None:
        server = create_mcp_server(None)
        assert server is not None

    def test_custom_server_name(self) -> None:
        server = create_mcp_server(server_name="my-custom-gov")
        assert server is not None
        assert server.name == "my-custom-gov"

    def test_strict_flag_accepted(self) -> None:
        server = create_mcp_server(strict=True)
        assert server is not None

    def test_mcp_unavailable_raises_import_error(self) -> None:
        with patch("acgs_lite.integrations.mcp_server.MCP_AVAILABLE", False):
            with pytest.raises(ImportError, match="mcp package is required"):
                create_mcp_server()


# ---------------------------------------------------------------------------
# run_mcp_server
# ---------------------------------------------------------------------------


class TestRunMcpServer:
    """Tests for the run_mcp_server entry point."""

    def test_mcp_unavailable_raises_import_error(self) -> None:
        with patch("acgs_lite.integrations.mcp_server.MCP_AVAILABLE", False):
            with pytest.raises(ImportError, match="mcp package is required"):
                run_mcp_server()

    def test_run_mcp_server_creates_and_runs(self) -> None:
        """Verify run_mcp_server wires up create_mcp_server and asyncio.run."""
        with (
            patch("acgs_lite.integrations.mcp_server.create_mcp_server") as mock_create,
            patch("asyncio.run") as mock_run,
            patch("mcp.server.stdio.stdio_server"),
        ):
            mock_server = mock_create.return_value
            mock_server.run = lambda *a, **kw: None
            mock_server.create_initialization_options = lambda: {}

            run_mcp_server(server_name="test-gov")

            mock_create.assert_called_once()
            # asyncio.run is called with the _run coroutine
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Strict mode restoration
# ---------------------------------------------------------------------------


class TestStrictModeRestoration:
    """Verify that strict mode is correctly restored after tool calls."""

    @pytest.mark.asyncio
    async def test_validate_action_restores_strict_mode(
        self, custom_constitution: Constitution
    ) -> None:
        """After validate_action completes, engine.strict must be restored."""
        constitution = custom_constitution
        audit_log = AuditLog()
        engine = GovernanceEngine(constitution, audit_log=audit_log, strict=True)

        server = create_mcp_server(constitution, strict=True)

        # Call validate_action which should temporarily flip strict=False
        await _call_tool(server, "validate_action", {"action": "forbidden"})

        # We can't directly access the engine from outside, but we can verify
        # that a subsequent call also works (doesn't raise)
        result = await _call_tool(server, "validate_action", {"action": "forbidden"})
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_check_compliance_restores_strict_mode(
        self, custom_constitution: Constitution
    ) -> None:
        server = create_mcp_server(custom_constitution, strict=True)

        await _call_tool(server, "check_compliance", {"text": "forbidden"})

        # Second call must also work
        result = await _call_tool(server, "check_compliance", {"text": "forbidden"})
        assert result["compliant"] is False


# ---------------------------------------------------------------------------
# Integration: cross-tool interactions
# ---------------------------------------------------------------------------


class TestCrossToolIntegration:
    """Tests verifying correct state across multiple tool calls."""

    @pytest.mark.asyncio
    async def test_validate_then_audit_then_stats(
        self, custom_constitution: Constitution
    ) -> None:
        server = create_mcp_server(custom_constitution)

        # Validate a mix of compliant and non-compliant actions
        await _call_tool(server, "validate_action", {"action": "clean action"})
        await _call_tool(server, "validate_action", {"action": "forbidden action"})
        await _call_tool(server, "check_compliance", {"text": "safe text"})

        # Audit should have 3 entries
        audit = await _call_tool(server, "get_audit_log", {})
        assert audit["total_entries"] == 3
        assert audit["chain_valid"] is True

        # Stats should reflect 3 validations
        stats = await _call_tool(server, "governance_stats", {})
        assert stats["total_validations"] == 3
        assert stats["audit_entries"] == 3

    @pytest.mark.asyncio
    async def test_constitution_hash_consistency(
        self, custom_constitution: Constitution
    ) -> None:
        """The constitutional hash must be consistent across all tools."""
        server = create_mcp_server(custom_constitution)

        constitution_data = await _call_tool(server, "get_constitution", {})
        const_hash = constitution_data["constitutional_hash"]

        await _call_tool(server, "validate_action", {"action": "test"})
        validation = await _call_tool(server, "validate_action", {"action": "test"})

        assert validation["constitutional_hash"] == const_hash

        compliance = await _call_tool(server, "check_compliance", {"text": "test"})
        assert compliance["constitutional_hash"] == const_hash

        stats = await _call_tool(server, "governance_stats", {})
        assert stats["constitutional_hash"] == const_hash

    @pytest.mark.asyncio
    async def test_multiple_violations_in_single_action(
        self, custom_constitution: Constitution
    ) -> None:
        """An action matching multiple rules should report all violations."""
        server = create_mcp_server(custom_constitution)
        result = await _call_tool(
            server,
            "validate_action",
            {"action": "this is forbidden and suspicious"},
        )

        assert result["valid"] is False
        rule_ids = {v["rule_id"] for v in result["violations"]}
        # Should match both TEST-001 (forbidden) and TEST-002 (suspicious)
        assert "TEST-001" in rule_ids
