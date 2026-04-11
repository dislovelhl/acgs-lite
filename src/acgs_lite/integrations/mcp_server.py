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

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.integrations.workflow import (
    WORKFLOW_AVAILABLE,
    GovernanceWorkflowCompiler,
    GovernanceWorkflowExecutor,
    list_workflow_templates,
)

logger = structlog.get_logger(__name__)

CONSTITUTIONAL_HASH = "608508a9bd224290"

# Keywords used by check_capability_tier heuristic (no CapabilityPassport available)
_RESTRICTED_KEYWORDS = frozenset({"delete", "destroy", "admin", "override", "drop", "truncate"})
_FULL_KEYWORDS = frozenset({"read", "list", "get", "fetch", "view", "show", "describe"})

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
    engine = GovernanceEngine(constitution, audit_log=audit_log, strict=strict, audit_mode="full")

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
            types.Tool(
                name="explain_violation",
                description=(
                    "Explain a constitutional violation in human-readable form. "
                    "Validates the action and returns detailed violation information "
                    "including rule text, severity, and description."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The action text to explain violations for",
                        },
                        "rule_id": {
                            "type": "string",
                            "description": "Optional rule ID to filter explanation to a specific rule",
                        },
                    },
                    "required": ["action"],
                },
            ),
            types.Tool(
                name="check_capability_tier",
                description=(
                    "Check the autonomy capability tier for an action. "
                    "Returns RESTRICTED, SUPERVISED, or FULL based on the action content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action_text": {
                            "type": "string",
                            "description": "The action text to check the capability tier for",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional domain context for tier determination",
                        },
                    },
                    "required": ["action_text"],
                },
            ),
            types.Tool(
                name="verify_audit_chain",
                description=(
                    "Verify the integrity of the audit chain. "
                    "Checks hash chain consistency across recent audit entries."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of recent entries to check",
                            "default": 100,
                        },
                    },
                },
            ),
            *(
                [
                    types.Tool(
                        name="compile_workflow",
                        description=(
                            "Compile a governance workflow GoalSpec into an executable TaskDAG. "
                            "Validates step domains against known governance domains and returns "
                            "node list with IDs, titles, domains, and dependency edges."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "workflow": {
                                    "type": "object",
                                    "description": (
                                        "GoalSpec dict with keys: goal (str), "
                                        "domains (list[str]), steps (list[dict])"
                                    ),
                                },
                            },
                        },
                    ),
                    types.Tool(
                        name="execute_workflow",
                        description=(
                            "Compile and execute a governance workflow. Each step is dispatched "
                            "to the matching acgs-lite governance function. Returns per-step results "
                            "with constitutional proof."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "workflow": {
                                    "type": "object",
                                    "description": "GoalSpec dict (same as compile_workflow)",
                                },
                                "inputs": {
                                    "type": "object",
                                    "description": (
                                        "Shared inputs for steps: action (str), text (str), "
                                        "limit (int)"
                                    ),
                                    "default": {},
                                },
                            },
                        },
                    ),
                    types.Tool(
                        name="list_workflow_templates",
                        description=(
                            "List pre-built governance workflow templates. "
                            "Returns template names and YAML file paths for common patterns: "
                            "action_validation, compliance_assessment, agent_onboarding."
                        ),
                        inputSchema={"type": "object", "properties": {}},
                    ),
                ]
                if WORKFLOW_AVAILABLE
                else []
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

        elif name == "explain_violation":
            action = arguments.get("action", "")
            rule_id_filter: str | None = arguments.get("rule_id")

            try:
                old_strict = engine.strict
                engine.strict = False
                result = engine.validate(action, agent_id="explain-tool")
                engine.strict = old_strict

                violations = result.violations
                if rule_id_filter:
                    violations = [v for v in violations if v.rule_id == rule_id_filter]

                explanation: dict[str, Any] = {
                    "action": action,
                    "compliant": result.valid,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "violations": [
                        {
                            "rule_id": v.rule_id,
                            "severity": v.severity.value,
                            "rule_text": v.rule_text,
                            "description": getattr(v, "description", v.rule_text),
                        }
                        for v in violations
                    ],
                    "summary": (
                        f"Action is compliant — no violations found."
                        if result.valid
                        else (
                            f"Action violates {len(violations)} rule(s): "
                            + ", ".join(v.rule_id for v in violations)
                        )
                    ),
                }
                logger.info(
                    "explain_violation",
                    action_length=len(action),
                    violations_count=len(violations),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(explanation, indent=2),
                    )
                ]
            except Exception as exc:
                logger.warning(
                    "explain_violation_error",
                    error_type=type(exc).__name__,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": type(exc).__name__, "action": action}),
                    )
                ]

        elif name == "check_capability_tier":
            action_text = arguments.get("action_text", "")
            domain: str | None = arguments.get("domain")

            try:
                lower = action_text.lower()
                words = set(lower.split())

                if words & _RESTRICTED_KEYWORDS:
                    tier = "RESTRICTED"
                elif words & _FULL_KEYWORDS:
                    tier = "FULL"
                else:
                    tier = "SUPERVISED"

                data: dict[str, Any] = {
                    "tier": tier,
                    "action": action_text,
                    "domain": domain,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
                logger.info(
                    "check_capability_tier",
                    tier=tier,
                    domain=domain,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(data, indent=2),
                    )
                ]
            except Exception as exc:
                logger.warning(
                    "check_capability_tier_error",
                    error_type=type(exc).__name__,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": type(exc).__name__, "action_text": action_text}
                        ),
                    )
                ]

        elif name == "verify_audit_chain":
            limit = arguments.get("limit", 100)

            try:
                chain_valid = audit_log.verify_chain()
                entries = audit_log.export_dicts()
                recent = entries[-limit:] if len(entries) > limit else entries

                result_data: dict[str, Any] = {
                    "status": "ok" if chain_valid else "chain_broken",
                    "chain_valid": chain_valid,
                    "total_entries": len(entries),
                    "entries_checked": len(recent),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
                logger.info(
                    "verify_audit_chain",
                    chain_valid=chain_valid,
                    entries_checked=len(recent),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result_data, indent=2),
                    )
                ]
            except Exception as exc:
                logger.warning(
                    "verify_audit_chain_error",
                    error_type=type(exc).__name__,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": type(exc).__name__}),
                    )
                ]

        elif name == "compile_workflow" and WORKFLOW_AVAILABLE:
            workflow_spec = arguments.get("workflow") if arguments else None
            if not workflow_spec:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": "Missing required argument: workflow"}),
                    )
                ]
            try:
                compiler = GovernanceWorkflowCompiler(CONSTITUTIONAL_HASH)
                dag = compiler.compile_from_dict(workflow_spec)
                nodes = [
                    {
                        "node_id": node.node_id,
                        "title": node.title,
                        "domain": node.domain,
                        "depends_on": list(node.depends_on),
                        "priority": node.priority,
                    }
                    for node in dag.nodes.values()
                ]
                data = {
                    "dag_id": dag.dag_id,
                    "goal": dag.goal,
                    "node_count": len(nodes),
                    "nodes": nodes,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
                logger.info(
                    "compile_workflow",
                    node_count=len(nodes),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
            except Exception as exc:
                logger.warning(
                    "compile_workflow_error",
                    error_type=type(exc).__name__,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": type(exc).__name__, "detail": str(exc)}),
                    )
                ]

        elif name == "execute_workflow" and WORKFLOW_AVAILABLE:
            workflow_spec = arguments.get("workflow") if arguments else None
            if not workflow_spec:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": "Missing required argument: workflow"}),
                    )
                ]
            inputs: dict[str, Any] = (arguments.get("inputs") or {}) if arguments else {}
            try:
                compiler = GovernanceWorkflowCompiler(CONSTITUTIONAL_HASH)
                dag = compiler.compile_from_dict(workflow_spec)
                executor = GovernanceWorkflowExecutor(
                    engine=engine,
                    constitution=constitution,
                    audit_log=audit_log,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                step_results = executor.execute(dag, inputs)
                data = {
                    "goal": dag.goal,
                    "steps_completed": len(step_results),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "steps": [sr.to_dict() for sr in step_results],
                }
                logger.info(
                    "execute_workflow",
                    steps_completed=len(step_results),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))]
            except Exception as exc:
                logger.warning(
                    "execute_workflow_error",
                    error_type=type(exc).__name__,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": type(exc).__name__, "detail": str(exc)}),
                    )
                ]

        elif name == "list_workflow_templates" and WORKFLOW_AVAILABLE:
            templates = list_workflow_templates()
            data = {
                "templates": templates,
                "count": len(templates),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

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
