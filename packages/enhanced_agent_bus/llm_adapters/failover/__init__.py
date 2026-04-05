"""
ACGS-2 LLM Failover Package
Constitutional Hash: 608508a9bd224290

Enhanced failover capabilities for LLM providers with:
- LLM-specific circuit breaker configurations
- Provider health scoring (latency, errors, quality)
- Proactive failover (switch before failure)
- Provider warmup mechanism
- Request hedging for critical operations

Success Metrics:
- Provider failover < 500ms
- Zero single-provider dependency for critical paths
"""

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH

from .config import (
    LLM_CIRCUIT_CONFIGS,
    LLMProviderType,
    get_llm_circuit_config,
)
from .failover import (
    FailoverEvent,
    ProactiveFailoverManager,
)
from .health import (
    HealthMetrics,
    ProviderHealthScore,
    ProviderHealthScorer,
)
from .hedging import (
    HedgedRequest,
    RequestHedgingManager,
)
from .orchestrator import (
    LLMFailoverOrchestrator,
    get_llm_failover_orchestrator,
    reset_llm_failover_orchestrator,
)
from .warmup import (
    ProviderWarmupManager,
    WarmupResult,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "LLM_CIRCUIT_CONFIGS",
    # Failover
    "FailoverEvent",
    # Health Scoring
    "HealthMetrics",
    # Hedging
    "HedgedRequest",
    # Orchestrator
    "LLMFailoverOrchestrator",
    # Enums
    "LLMProviderType",
    "ProactiveFailoverManager",
    "ProviderHealthScore",
    "ProviderHealthScorer",
    "ProviderWarmupManager",
    "RequestHedgingManager",
    # Warmup
    "WarmupResult",
    # Configuration
    "get_llm_circuit_config",
    "get_llm_failover_orchestrator",
    "reset_llm_failover_orchestrator",
]
