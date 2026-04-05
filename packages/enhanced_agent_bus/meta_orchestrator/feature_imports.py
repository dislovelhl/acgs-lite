"""
Meta-Orchestrator Feature Imports Module
=========================================

Conditional imports for optional features with graceful fallbacks.
This module handles all the optional dependency loading.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections.abc import Callable

from enhanced_agent_bus._compat.feature_flags import FEATURES
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Mamba-2 Hybrid Processor
ConstitutionalContextManager: type | None = None
Mamba2Config: type | None = None
create_constitutional_context_manager: Callable[..., object] | None = None
MAMBA_AVAILABLE = False

if FEATURES.mamba_enabled:
    try:
        from ..mamba2_hybrid_processor import (
            ConstitutionalContextManager,
            Mamba2Config,
            create_constitutional_context_manager,
        )

        MAMBA_AVAILABLE = True
    except ImportError:
        logger.warning("Mamba-2 processor not available, using fallback context")

# MACI Enforcement
MACIAction: type | None = None
MACIConfig: type | None = None
MACIConfigLoader: type | None = None
MACIEnforcer: type | None = None
MACIRole: type | None = None
MACIRoleRegistry: type | None = None
create_maci_enforcement_middleware: Callable[..., object] | None = None
MACI_AVAILABLE = False

if FEATURES.maci_enabled:
    try:
        from ..maci_enforcement import (
            MACIAction,
            MACIConfig,
            MACIConfigLoader,
            MACIEnforcer,
            MACIRole,
            MACIRoleRegistry,
            create_maci_enforcement_middleware,
        )

        MACI_AVAILABLE = True
    except ImportError:
        logger.warning("MACI enforcement not available")

# LangGraph Orchestrator
WorkflowDefinition: type | None = None
WorkflowExecutor: type | None = None
create_governance_workflow: Callable[..., object] | None = None
LANGGRAPH_AVAILABLE = False

if FEATURES.langgraph_enabled:
    try:
        from ..langgraph_orchestrator import (
            WorkflowDefinition,
            WorkflowExecutor,
            create_governance_workflow,
        )

        LANGGRAPH_AVAILABLE = True
    except ImportError:
        logger.warning("LangGraph orchestrator not available")

# SAFLA Memory v3.0
SAFLAMemoryConfig: type | None = None
SAFLANeuralMemoryV3: type | None = None
create_safla_memory: Callable[..., object] | None = None
SAFLA_V3_AVAILABLE = False

if FEATURES.safla_enabled:
    try:
        from ..safla_memory import SAFLAConfig as SAFLAMemoryConfig
        from ..safla_memory import SAFLANeuralMemoryV3, create_safla_memory

        SAFLA_V3_AVAILABLE = True
    except ImportError:
        logger.info("SAFLA Memory v3.0 not available, using built-in memory")

# Swarm Intelligence
SwarmAgentCapability: type | None = None
SwarmCoordinator: type | None = None
create_swarm_coordinator: Callable[..., object] | None = None
SwarmTaskPriority: type | None = None
SWARM_AVAILABLE = False

if FEATURES.swarm_enabled:
    try:
        from ..swarm_intelligence import AgentCapability as SwarmAgentCapability
        from ..swarm_intelligence import SwarmCoordinator, create_swarm_coordinator
        from ..swarm_intelligence import TaskPriority as SwarmTaskPriority

        SWARM_AVAILABLE = True
    except ImportError:
        logger.info("Swarm Intelligence not available, using basic agent management")

# Workflow Evolution Engine
EvolutionStrategy: type | None = None
OptimizationType: type | None = None
WorkflowEvolutionEngine: type | None = None
create_workflow_engine: Callable[..., object] | None = None
WORKFLOW_EVOLUTION_AVAILABLE = False

if FEATURES.workflow_evolution_enabled:
    try:
        from ..workflow_evolution import (
            EvolutionStrategy,
            OptimizationType,
            WorkflowEvolutionEngine,
            create_workflow_engine,
        )

        WORKFLOW_EVOLUTION_AVAILABLE = True
    except ImportError:
        logger.info("Workflow Evolution Engine not available, using static workflows")

# Research Integration
ResearchIntegrator: type | None = None
ResearchSource: type | None = None
ResearchType: type | None = None
create_research_integrator: Callable[..., object] | None = None
RESEARCH_INTEGRATION_AVAILABLE = False

if FEATURES.research_enabled:
    try:
        from ..research_integration import (
            ResearchIntegrator,
            ResearchSource,
            ResearchType,
            create_research_integrator,
        )

        RESEARCH_INTEGRATION_AVAILABLE = True
    except ImportError:
        logger.info("Research Integration not available, using basic research")

# Optimization Toolkit
OptimizationToolkit: type | None = None
OPTIMIZATION_TOOLKIT_AVAILABLE = False

if FEATURES.optimization_enabled:
    try:
        from ..optimization_toolkit import MultiAgentOrchestrator as OptimizationToolkit

        OPTIMIZATION_TOOLKIT_AVAILABLE = True
    except ImportError:
        logger.info("Optimization Toolkit not available")

# Cache Warming
CacheWarmer: type | None = None
CACHE_WARMING_AVAILABLE = False

if FEATURES.cache_warming_enabled:
    try:
        from enhanced_agent_bus._compat.cache_warming import CacheWarmer

        CACHE_WARMING_AVAILABLE = True
    except ImportError:
        logger.info("Cache Warming not available")

__all__ = [
    "CACHE_WARMING_AVAILABLE",
    "LANGGRAPH_AVAILABLE",
    "MACI_AVAILABLE",
    "MAMBA_AVAILABLE",
    "OPTIMIZATION_TOOLKIT_AVAILABLE",
    "RESEARCH_INTEGRATION_AVAILABLE",
    "SAFLA_V3_AVAILABLE",
    "SWARM_AVAILABLE",
    "WORKFLOW_EVOLUTION_AVAILABLE",
    # Cache
    "CacheWarmer",
    # Mamba-2
    "ConstitutionalContextManager",
    # Workflow Evolution
    "EvolutionStrategy",
    # MACI
    "MACIAction",
    "MACIConfig",
    "MACIConfigLoader",
    "MACIEnforcer",
    "MACIRole",
    "MACIRoleRegistry",
    "Mamba2Config",
    # Optimization
    "OptimizationToolkit",
    "OptimizationType",
    # Research
    "ResearchIntegrator",
    "ResearchSource",
    "ResearchType",
    # SAFLA
    "SAFLAMemoryConfig",
    "SAFLANeuralMemoryV3",
    # Swarm
    "SwarmAgentCapability",
    "SwarmCoordinator",
    "SwarmTaskPriority",
    # LangGraph
    "WorkflowDefinition",
    "WorkflowEvolutionEngine",
    "WorkflowExecutor",
    "create_constitutional_context_manager",
    "create_governance_workflow",
    "create_maci_enforcement_middleware",
    "create_research_integrator",
    "create_safla_memory",
    "create_swarm_coordinator",
    "create_workflow_engine",
]
