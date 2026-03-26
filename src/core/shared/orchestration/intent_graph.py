"""
Adaptive Intent Graph for Swarm Orchestration
Constitutional Hash: 608508a9bd224290

This module implements Phase R3 (Agentic Orchestration) of the Research Roadmap.
It replaces static task lists with a dynamic graph that routes work based on
'Intent' and 'Tool Discovery' via MCP patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from src.core.shared.types import JSONDict


class TaskIntent(StrEnum):
    VALIDATE = "validate"
    METRICS = "metrics"
    PROPOSE = "propose"
    AUDIT = "audit"


@dataclass
class SwarmTask:
    id: str
    intent: TaskIntent
    payload: JSONDict
    status: str = "pending"
    result: JSONDict | None = None


class MCPTool(Protocol):
    """Structural protocol for MCP-compatible tools."""

    name: str

    async def __call__(self, **kwargs: object) -> object: ...


@dataclass
class AdaptiveIntentGraph:
    """
    Dynamic task graph that maps Intent to MCP Tools.

    In a real system, this would:
    1. Scan MCP servers for tools tagged with specific intents.
    2. Build a DAG based on task dependencies.
    3. Re-route or retry failed nodes using Reflection.
    """

    tools: dict[TaskIntent, list[str]] = field(default_factory=dict)

    def register_tool(self, intent: TaskIntent, tool_name: str) -> None:
        if intent not in self.tools:
            self.tools[intent] = []
        self.tools[intent].append(tool_name)

    def route_task(self, task: SwarmTask) -> str:
        """Find the best tool for the task's intent."""
        available = self.tools.get(task.intent, [])
        if not available:
            return "fallback_reasoner"
        return available[0]  # Simplistic routing for prototype

    def get_next_steps(self, completed_task: SwarmTask) -> list[SwarmTask]:
        """
        Dynamically determine next tasks based on result.
        This is the 'Adaptive' part.
        """
        if completed_task.intent == TaskIntent.METRICS:
            # If metrics show high volatility, inject a validation task
            volatility = completed_task.result.get("volatility", 0)
            if volatility > 50:
                return [
                    SwarmTask(
                        id=f"auto-val-{completed_task.id}",
                        intent=TaskIntent.VALIDATE,
                        payload={"reason": "high_volatility_detected"},
                    )
                ]
        return []
