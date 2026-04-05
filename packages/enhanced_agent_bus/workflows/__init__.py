"""
ACGS-2 Enhanced Agent Bus - Workflow Module
Constitutional Hash: 608508a9bd224290

Entity Workflow patterns for agent lifecycle management.
Implements the Actor Model pattern with signals, queries, and activities.
"""

from .agent_entity_workflow import (
    AgentConfig,
    AgentEntityWorkflow,
    AgentResult,
    AgentState,
    AgentStatus,
    ShutdownRequest,
    Task,
    TaskResult,
    WorkflowActivity,
    checkpoint_agent_activity,
    execute_task_activity,
    initialize_agent_activity,
    shutdown_agent_activity,
)
from .workflow_base import (
    Activity,
    InMemoryWorkflowExecutor,
    Query,
    Signal,
    WorkflowContext,
    WorkflowDefinition,
)

__all__ = [
    "Activity",
    "AgentConfig",
    "AgentEntityWorkflow",
    "AgentResult",
    # Agent Entity Workflow
    "AgentState",
    "AgentStatus",
    "InMemoryWorkflowExecutor",
    "Query",
    "ShutdownRequest",
    "Signal",
    "Task",
    "TaskResult",
    "WorkflowActivity",
    "WorkflowContext",
    # Workflow Base
    "WorkflowDefinition",
    "checkpoint_agent_activity",
    "execute_task_activity",
    "initialize_agent_activity",
    "shutdown_agent_activity",
]
