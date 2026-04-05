"""
ACGS-2 Workflow Persistence Layer

Constitutional Hash: 608508a9bd224290
Version: 1.0.0

This module provides durable workflow execution with:
- Persistent state storage (PostgreSQL/Redis)
- Deterministic replay capability
- Checkpoint-based recovery
- Saga compensation tracking
"""

# -- Namespace Boundary ---------------------------------------------------
# This package handles WORKFLOW EXECUTION lifecycle:
#   WorkflowInstance, WorkflowStep, WorkflowEvent, WorkflowCompensation
#   DurableWorkflowExecutor, ReplayEngine
#   PostgreSQL-only storage (postgres_repository.py)
#
# DO NOT CONFUSE with saga_persistence/ which handles DISTRIBUTED SAGA STATE
# (PersistedSagaState, SagaCheckpoint, multi-backend Redis+PostgreSQL,
# factory pattern). The two packages have ZERO cross-domain imports.
# -------------------------------------------------------------------------

from .executor import DurableWorkflowExecutor
from .models import (
    CandidateArtifact,
    DatasetSnapshot,
    DecisionEvent,
    EvaluationRun,
    EventType,
    EvidenceBundle,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from .replay import ReplayEngine
from .repository import InMemoryWorkflowRepository, WorkflowRepository

try:
    from .postgres_repository import PostgresWorkflowRepository
except ImportError:
    PostgresWorkflowRepository = None  # type: ignore[misc,assignment]

__all__ = [
    "CandidateArtifact",
    "DatasetSnapshot",
    "DecisionEvent",
    "DurableWorkflowExecutor",
    "EvaluationRun",
    "EventType",
    "EvidenceBundle",
    "InMemoryWorkflowRepository",
    "PostgresWorkflowRepository",
    "ReplayEngine",
    "StepStatus",
    "StepType",
    "WorkflowCompensation",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowRepository",
    "WorkflowStatus",
    "WorkflowStep",
]

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
