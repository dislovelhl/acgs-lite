"""
Multi-Agent Optimization Toolkit
Constitutional Hash: 608508a9bd224290

This package provides comprehensive multi-agent performance optimization
capabilities for ACGS-2, including:

- Multi-domain performance profiling (Database, Application, Cache, Agent Coordination)
- Context window optimization for LLM interactions
- Cost optimization for model selection
- Parallel profiling with async coordination

Reference: SPEC_ACGS2_ENHANCED_v2.3 Section 16 (Performance Engineering)
"""

# Constitutional Hash - immutable reference
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .agents import (
    CONSTITUTIONAL_HASH as AGENTS_HASH,
)
from .agents import (
    AgentCoordinationProfiler,
    ApplicationPerformanceAgent,
    CachePerformanceAgent,
    DatabasePerformanceAgent,
    FrontendPerformanceAgent,
    OptimizationDomain,
    PerformanceAgent,
    PerformanceMetrics,
    PerformanceProfile,
    PerformanceProfiler,
)
from .context import (
    ContextCompressor,
    ContextWindowOptimizer,
    compress_context,
)
from .cost import (
    CostOptimizer,
    UsageRecord,
)
from .orchestrator import (
    MultiAgentOrchestrator,
    OptimizationResult,
    OptimizationScope,
    PerformanceTracker,
    create_optimization_toolkit,
)

__all__ = [
    # Constitutional hash
    "CONSTITUTIONAL_HASH",
    "AgentCoordinationProfiler",
    "ApplicationPerformanceAgent",
    "CachePerformanceAgent",
    "ContextCompressor",
    # Context optimization
    "ContextWindowOptimizer",
    # Cost optimization
    "CostOptimizer",
    # Profiling agents
    "DatabasePerformanceAgent",
    "FrontendPerformanceAgent",
    # Orchestration
    "MultiAgentOrchestrator",
    # Domains and models
    "OptimizationDomain",
    "OptimizationResult",
    "OptimizationScope",
    "PerformanceAgent",
    "PerformanceMetrics",
    "PerformanceProfile",
    # Profiler base
    "PerformanceProfiler",
    "PerformanceTracker",
    "UsageRecord",
    "compress_context",
    "create_optimization_toolkit",
]
