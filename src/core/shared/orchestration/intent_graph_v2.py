"""
Adaptive Intent Graph v2 (Wave R)
Constitutional Hash: cdd01ef066bc6cf2

This module enhances the IntentGraph to use the MCPBridge for dynamic
routing and task execution in a swarm environment.

Reference: Wave R Research Discovery PRD
"""

from __future__ import annotations

from typing import Any, Protocol

from src.core.shared.orchestration.intent_graph import AdaptiveIntentGraph, SwarmTask, TaskIntent
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class MCPBridgeProtocol(Protocol):
    """Minimal bridge contract for swarm orchestration."""

    async def sync_tools(self) -> int: ...

    async def dispatch(self, task: SwarmTask, agent_id: str, agent_role: str) -> Any: ...


class AdaptiveIntentGraphV2(AdaptiveIntentGraph):
    """
    Enhanced Intent Graph with MCP-enabled execution.
    """

    def __init__(self, bridge: MCPBridgeProtocol) -> None:
        super().__init__()
        self.bridge = bridge

    async def execute_swarm(
        self, initial_tasks: list[SwarmTask], agent_id: str, agent_role: str
    ) -> list[SwarmTask]:
        """
        Run a swarm of tasks, dynamically adding new tasks as needed.
        """
        # First, ensure our bridge is synced with the current MCP tool set
        await self.bridge.sync_tools()

        queue = list(initial_tasks)
        completed: list[SwarmTask] = []

        while queue:
            current_task = queue.pop(0)
            logger.info("executing_task", task_id=current_task.id, intent=current_task.intent)

            # Use the bridge to dispatch to the correct tool
            result = await self.bridge.dispatch(current_task, agent_id, agent_role)

            # Update task status and result
            current_task.status = "completed"
            current_task.result = result
            completed.append(current_task)

            # Adapt the graph: add any next steps suggested by the result
            next_tasks = self.get_next_steps(current_task)
            for next_task in next_tasks:
                logger.info("adding_dynamic_task", parent=current_task.id, new_task=next_task.id)
                queue.append(next_task)

        return completed

    def get_next_steps(self, completed_task: SwarmTask) -> list[SwarmTask]:
        """
        Overridden to support more complex dynamic logic.
        """
        # Base logic for volatility
        next_steps = super().get_next_steps(completed_task)

        # New prototype logic: if a PROPOSE task succeeds, inject a VALIDATE task immediately
        if completed_task.intent == TaskIntent.PROPOSE and completed_task.result:
            if not any(t.intent == TaskIntent.VALIDATE for t in next_steps):
                next_steps.append(
                    SwarmTask(
                        id=f"validate-after-propose-{completed_task.id}",
                        intent=TaskIntent.VALIDATE,
                        payload={"proposal_id": completed_task.id},
                    )
                )
        return next_steps
