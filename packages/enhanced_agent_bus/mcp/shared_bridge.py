"""
MCP Bridge for Swarm Orchestration (Wave R)
Constitutional Hash: 608508a9bd224290

Provides a translation layer between the MCP tool registry (MCPClientPool)
and the Adaptive Intent Graph.

- Discovers tools across all connected servers.
- Maps tool names/metadata to TaskIntents.
- Provides a unified 'dispatch' method for the graph to execute work.

Reference: Wave R Research Discovery PRD
"""

from __future__ import annotations

from typing import Any

from enhanced_agent_bus._compat.orchestration.intent_graph import SwarmTask, TaskIntent
from enhanced_agent_bus.mcp.pool import MCPClientPool
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class MCPBridge:
    """
    Bridge that connects MCP tools to Swarm Intents.
    """

    def __init__(self, mcp_pool: MCPClientPool) -> None:
        self.mcp_pool = mcp_pool
        # Mapping from Intent to a list of tool names
        self.intent_map: dict[TaskIntent, list[str]] = {
            TaskIntent.VALIDATE: [],
            TaskIntent.METRICS: [],
            TaskIntent.PROPOSE: [],
            TaskIntent.AUDIT: [],
        }

    async def sync_tools(self) -> int:
        """
        Scan the MCP pool and categorize tools by intent.
        In this prototype, we use naming conventions:
        - 'validate_*' -> VALIDATE
        - 'get_*_metrics' -> METRICS
        - 'propose_*' -> PROPOSE
        - 'audit_*' -> AUDIT
        """
        tools = await self.mcp_pool.list_tools()
        count = 0

        for tool in tools:
            name = tool.name.lower()
            if name.startswith("validate") or "check" in name:
                self.intent_map[TaskIntent.VALIDATE].append(tool.name)
            elif "metrics" in name or "stats" in name:
                self.intent_map[TaskIntent.METRICS].append(tool.name)
            elif name.startswith("propose") or "evolve" in name:
                self.intent_map[TaskIntent.PROPOSE].append(tool.name)
            elif "audit" in name or "log" in name:
                self.intent_map[TaskIntent.AUDIT].append(tool.name)
            count += 1

        logger.info("mcp_bridge_synced", tool_count=count, intents=list(self.intent_map.keys()))
        return count

    async def dispatch(self, task: SwarmTask, agent_id: str, agent_role: str) -> Any:
        """
        Execute a task using the best available tool for its intent.
        """
        available_tools = self.intent_map.get(task.intent, [])
        if not available_tools:
            logger.warning("no_tool_for_intent", intent=task.intent, task_id=task.id)
            return {"error": f"No tool found for intent {task.intent}"}

        # Simplified: pick the first available tool
        tool_name = available_tools[0]

        logger.info(
            "mcp_dispatching_task",
            task_id=task.id,
            intent=task.intent,
            tool=tool_name,
            agent_id=agent_id,
        )

        result = await self.mcp_pool.call_tool(
            tool_name=tool_name, arguments=task.payload, agent_id=agent_id, agent_role=agent_role
        )

        return result
