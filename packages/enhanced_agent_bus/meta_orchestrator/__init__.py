"""
Meta-Orchestrator Package
=========================

The Meta-Orchestrator is the apex coordination layer that unifies all agentic
capabilities into a single, intelligent system capable of handling any task.

This package provides:
- OrchestratorConfig: Configuration for the meta-orchestrator
- TaskResult: Results from task execution
- SwarmAgent: Agent representations for swarm coordination
- MemoryTier/MemoryEntry: Neural memory architecture models
- SAFLANeuralMemory: Four-tier memory system
- MetaOrchestrator: The main orchestration class

All exports maintain backward compatibility with the original meta_orchestrator.py module.

Constitutional Hash: 608508a9bd224290
"""

from .config import CONSTITUTIONAL_HASH, OrchestratorConfig
from .feature_imports import (
    CACHE_WARMING_AVAILABLE,
    LANGGRAPH_AVAILABLE,
    MACI_AVAILABLE,
    MAMBA_AVAILABLE,
    OPTIMIZATION_TOOLKIT_AVAILABLE,
    RESEARCH_INTEGRATION_AVAILABLE,
    SAFLA_V3_AVAILABLE,
    SWARM_AVAILABLE,
    WORKFLOW_EVOLUTION_AVAILABLE,
)
from .memory import SAFLANeuralMemory
from .models import (
    AgentCapability,
    MemoryEntry,
    MemoryTier,
    SwarmAgent,
    TaskComplexity,
    TaskResult,
    TaskType,
)
from .orchestrator import MetaOrchestrator, create_meta_orchestrator

__all__ = [
    "CACHE_WARMING_AVAILABLE",
    "CONSTITUTIONAL_HASH",
    "LANGGRAPH_AVAILABLE",
    "MACI_AVAILABLE",
    # Feature availability flags
    "MAMBA_AVAILABLE",
    "OPTIMIZATION_TOOLKIT_AVAILABLE",
    "RESEARCH_INTEGRATION_AVAILABLE",
    "SAFLA_V3_AVAILABLE",
    "SWARM_AVAILABLE",
    "WORKFLOW_EVOLUTION_AVAILABLE",
    "AgentCapability",
    "MemoryEntry",
    "MemoryTier",
    # Main class and factory
    "MetaOrchestrator",
    # Configuration
    "OrchestratorConfig",
    # Memory
    "SAFLANeuralMemory",
    "SwarmAgent",
    "TaskComplexity",
    # Models
    "TaskResult",
    "TaskType",
    "create_meta_orchestrator",
]
