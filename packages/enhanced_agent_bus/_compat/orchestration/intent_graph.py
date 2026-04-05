"""Shim for src.core.shared.orchestration.intent_graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

try:
    from src.core.shared.orchestration.intent_graph import *  # noqa: F403
except ImportError:

    class TaskIntent(StrEnum):
        EXECUTE = "execute"
        VALIDATE = "validate"
        MONITOR = "monitor"
        DELEGATE = "delegate"
        REPORT = "report"

    @dataclass
    class SwarmTask:
        task_id: str = ""
        intent: str = "execute"
        description: str = ""
        dependencies: list[str] = field(default_factory=list)
        assigned_agent: str = ""
        status: str = "pending"
        result: Any = None
        metadata: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class IntentGraph:
        tasks: list[SwarmTask] = field(default_factory=list)
        edges: list[tuple[str, str]] = field(default_factory=list)

        def add_task(self, task: SwarmTask) -> None:
            self.tasks.append(task)

        def add_edge(self, from_id: str, to_id: str) -> None:
            self.edges.append((from_id, to_id))

        def get_ready_tasks(self) -> list[SwarmTask]:
            """Return tasks with no unfinished dependencies."""
            completed = {t.task_id for t in self.tasks if t.status == "completed"}
            ready: list[SwarmTask] = []
            for task in self.tasks:
                if task.status != "pending":
                    continue
                deps_met = all(d in completed for d in task.dependencies)
                if deps_met:
                    ready.append(task)
            return ready
