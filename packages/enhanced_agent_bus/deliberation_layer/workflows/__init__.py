"""
ACGS-2 Temporal Workflow Patterns for Deliberation Layer
Constitutional Hash: 608508a9bd224290

This module implements Temporal-based workflow orchestration patterns:
1. DeliberationWorkflow - Main workflow for high-impact message processing
2. ConstitutionalSagaWorkflow - Saga pattern with compensation for constitutional operations
3. AgentLifecycleWorkflow - Entity workflow for agent state management
4. HumanApprovalWorkflow - Async callback pattern for HITL approval

Reference: https://docs.temporal.io/workflows
"""

from .constitutional_saga import (
    ConstitutionalSagaWorkflow,
    DefaultSagaActivities,
    SagaCompensation,
    SagaStep,
)
from .deliberation_workflow import (
    DefaultDeliberationActivities,
    DeliberationWorkflow,
    DeliberationWorkflowInput,
    DeliberationWorkflowResult,
)

__all__ = [
    # Constitutional Saga
    "ConstitutionalSagaWorkflow",
    "DefaultDeliberationActivities",
    # Deliberation Workflow
    "DeliberationWorkflow",
    "DeliberationWorkflowInput",
    "DeliberationWorkflowResult",
    "SagaActivities",
    "SagaCompensation",
    "SagaStep",
]
