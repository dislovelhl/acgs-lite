"""ACGS-Lite MCP Server Integration.

Exposes constitutional governance as an MCP (Model Context Protocol) server.
Any MCP-compatible client (Claude Desktop, VS Code, Cursor, etc.) can call
these tools to validate actions, inspect constitutions, and query audit logs.

Usage::

    # Run from command line:
    python -m acgs_lite.integrations.mcp_server

    # Or programmatically:
    from acgs_lite.integrations.mcp_server import create_mcp_server, run_mcp_server
    run_mcp_server()

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

try:
    from mcp import types
    from mcp.server import Server

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None  # type: ignore[assignment,misc]


def create_mcp_server(
    constitution: Constitution | None = None,
    *,
    server_name: str = "acgs-governance",
    strict: bool = False,
) -> Any:
    """Create an MCP server exposing governance tools.

    Args:
        constitution: Rules to enforce. Defaults to built-in rules.
        server_name: Name of the MCP server.
        strict: If True, raise on violations in validate_action.

    Returns:
        MCP Server instance.
    """
    if not MCP_AVAILABLE:
        raise ImportError("mcp package is required. Install with: pip install acgs-lite[mcp]")

    constitution = constitution if constitution is not None else Constitution.default()
    audit_log = AuditLog()
    engine = GovernanceEngine(constitution, audit_log=audit_log, strict=strict)

    server = Server(server_name)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        """Return the list of available governance tools."""
        return [
            types.Tool(
                name="validate_action",
                description=(
                    "Validate an agent action against constitutional governance rules. "
                    "Returns whether the action is compliant and any violations found."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The action text to validate",
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent performing the action",
                            "default": "mcp-client",
                        },
                    },
                    "required": ["action"],
                },
            ),
            types.Tool(
                name="get_constitution",
                description=(
                    "Get the current constitution: name, version, hash, and the full list of rules."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="get_audit_log",
                description=("Get recent audit log entries showing governance decisions."),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum entries to return",
                            "default": 20,
                        },
                    },
                },
            ),
            types.Tool(
                name="check_compliance",
                description=(
                    "Quick compliance check — returns whether text contains "
                    "any constitutional violations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to check for compliance",
                        },
                    },
                    "required": ["text"],
                },
            ),
            types.Tool(
                name="governance_stats",
                description=(
                    "Get governance statistics: total validations, compliance rate, "
                    "average latency, and audit chain integrity."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        """Dispatch a governance tool call by name."""
        if name == "validate_action":
            action = arguments.get("action", "")
            agent_id = arguments.get("agent_id", "mcp-client")

            # Use non-strict for MCP (return result, don't raise)
            old_strict = engine.strict
            engine.strict = False
            result = engine.validate(action, agent_id=agent_id)
            engine.strict = old_strict

            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(result.to_dict(), indent=2),
                )
            ]

        elif name == "get_constitution":
            data = {
                "name": constitution.name,
                "version": constitution.version,
                "constitutional_hash": constitution.hash,
                "constitutional_hash_versioned": constitution.hash_versioned,
                "rules_count": len(constitution.rules),
                "rules": [
                    {
                        "id": r.id,
                        "text": r.text,
                        "severity": r.severity.value,
                        "category": r.category,
                        "enabled": r.enabled,
                    }
                    for r in constitution.rules
                ],
            }
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(data, indent=2),
                )
            ]

        elif name == "get_audit_log":
            limit = arguments.get("limit", 20)
            entries = audit_log.export_dicts()[-limit:]
            data = {
                "total_entries": len(audit_log),
                "chain_valid": audit_log.verify_chain(),
                "entries": entries,
            }
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(data, indent=2, default=str),
                )
            ]

        elif name == "check_compliance":
            text = arguments.get("text", "")
            old_strict = engine.strict
            engine.strict = False
            result = engine.validate(text, agent_id="compliance-check")
            engine.strict = old_strict

            data = {
                "compliant": result.valid,
                "constitutional_hash": result.constitutional_hash,
                "violations": [
                    {"rule_id": v.rule_id, "severity": v.severity.value} for v in result.violations
                ],
            }
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(data, indent=2),
                )
            ]

        elif name == "governance_stats":
            stats = {
                **engine.stats,
                "audit_entries": len(audit_log),
                "audit_chain_valid": audit_log.verify_chain(),
            }
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(stats, indent=2),
                )
            ]

        else:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )
            ]

    return server


def run_mcp_server(
    constitution: Constitution | None = None,
    *,
    server_name: str = "acgs-governance",
) -> None:
    """Run the governance MCP server over stdio.

    Usage::

        python -m acgs_lite.integrations.mcp_server
    """
    if not MCP_AVAILABLE:
        raise ImportError("mcp package is required. Install with: pip install acgs-lite[mcp]")

    from mcp.server.stdio import stdio_server

    server = create_mcp_server(constitution, server_name=server_name)

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    run_mcp_server()
