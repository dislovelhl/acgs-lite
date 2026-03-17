"""
Coordinator Protocol definitions for MetaOrchestrator decomposition.

Constitutional Hash: cdd01ef066bc6cf2

These protocols define the interfaces for focused coordinators that
replace the monolithic MetaOrchestrator responsibilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

if TYPE_CHECKING:
    from packages.enhanced_agent_bus.models import SwarmAgent, TaskComplexity, TaskType


@runtime_checkable
class MemoryCoordinatorProtocol(Protocol):
    constitutional_hash: str

    async def store(
        self,
        key: str,
        value: JSONDict,
        tier: str = "ephemeral",
        ttl_seconds: int | None = None,
    ) -> bool: ...

    async def retrieve(self, key: str) -> JSONDict | None: ...

    async def search(
        self,
        query: str,
        limit: int = 10,
        tier: str | None = None,
    ) -> list[JSONDict]: ...

    def get_stats(self) -> JSONDict: ...


@runtime_checkable
class SwarmCoordinatorProtocol(Protocol):
    constitutional_hash: str

    async def spawn_agent(
        self,
        agent_type: str,
        capabilities: list[str],
    ) -> SwarmAgent | None: ...

    async def route_task(
        self,
        task: str,
        complexity: TaskComplexity,
        task_type: TaskType,
    ) -> list[SwarmAgent]: ...

    async def terminate_agent(self, agent_id: str) -> bool: ...

    def get_active_agents(self) -> JSONDict: ...


@runtime_checkable
class WorkflowCoordinatorProtocol(Protocol):
    constitutional_hash: str

    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: JSONDict,
    ) -> JSONDict: ...

    async def evolve_workflow(
        self,
        workflow_id: str,
        feedback: JSONDict,
    ) -> bool: ...

    def get_workflow_stats(self) -> JSONDict: ...


@runtime_checkable
class ResearchCoordinatorProtocol(Protocol):
    constitutional_hash: str

    async def search_arxiv(self, query: str, limit: int = 5) -> list[JSONDict]: ...

    async def search_github(self, query: str, limit: int = 5) -> list[JSONDict]: ...

    async def synthesize_research(
        self,
        sources: list[JSONDict],
    ) -> JSONDict: ...


@runtime_checkable
class MACICoordinatorProtocol(Protocol):
    constitutional_hash: str

    async def validate_action(
        self,
        agent_id: str,
        action: str,
        target_output_id: str | None = None,
    ) -> JSONDict: ...

    async def register_agent(
        self,
        agent_id: str,
        role: str,
    ) -> bool: ...

    def is_enabled(self) -> bool: ...


from .context_coordinator import (  # noqa: E402
    ContextCoordinator,
    ContextCoordinatorProtocol,
    ContextProcessingResult,
)
from .maci_coordinator import MACICoordinator  # noqa: E402
from .memory_coordinator import MemoryCoordinator  # noqa: E402
from .research_coordinator import ResearchCoordinator  # noqa: E402
from .swarm_coordinator import SwarmCoordinator  # noqa: E402
from .task_coordinator import (  # noqa: E402
    TaskCoordinator,
    TaskCoordinatorProtocol,
    TaskExecutionOptions,
    TaskResult,
)
from .workflow_coordinator import WorkflowCoordinator  # noqa: E402

__all__ = [
    "ContextCoordinator",
    "ContextCoordinatorProtocol",
    "ContextProcessingResult",
    "MACICoordinator",
    "MACICoordinatorProtocol",
    "MemoryCoordinator",
    "MemoryCoordinatorProtocol",
    "ResearchCoordinator",
    "ResearchCoordinatorProtocol",
    "SwarmCoordinator",
    "SwarmCoordinatorProtocol",
    "TaskCoordinator",
    "TaskCoordinatorProtocol",
    "TaskExecutionOptions",
    "TaskResult",
    "WorkflowCoordinator",
    "WorkflowCoordinatorProtocol",
]
