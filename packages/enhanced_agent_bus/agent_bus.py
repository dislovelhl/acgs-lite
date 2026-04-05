"""
Backward compatibility shim for agent_bus module.

This module re-exports all symbols from the new modular structure
to maintain backward compatibility with existing imports.

Constitutional Hash: 608508a9bd224290

Migration:
    Old: from packages.enhanced_agent_bus.agent_bus import EnhancedAgentBus
    New: from packages.enhanced_agent_bus.bus import EnhancedAgentBus

Both import paths will continue to work.
"""

from __future__ import annotations

# Re-export everything from the modular bus package
from .bus import (
    BatchProcessor,
    BusMetrics,
    EnhancedAgentBus,
    GovernanceIntegration,
    MessageHandler,
    MessageValidator,
    _is_mock_instance,
    get_agent_bus,
    reset_agent_bus,
)

# Re-export feature flags via dependency bridge (migrated from imports.py)
from .dependency_bridge import get_feature_flags as _get_feature_flags

_flags = _get_feature_flags()
CIRCUIT_BREAKER_ENABLED: bool = _flags.get("CIRCUIT_BREAKER_ENABLED", False)
DELIBERATION_AVAILABLE: bool = _flags.get("DELIBERATION_AVAILABLE", False)
MACI_AVAILABLE: bool = _flags.get("MACI_AVAILABLE", False)
METERING_AVAILABLE: bool = _flags.get("METERING_AVAILABLE", False)
METRICS_ENABLED: bool = _flags.get("METRICS_ENABLED", False)
POLICY_CLIENT_AVAILABLE: bool = _flags.get("POLICY_CLIENT_AVAILABLE", False)

# Redis URL from shared config
try:
    from enhanced_agent_bus._compat.redis_config import get_redis_url

    DEFAULT_REDIS_URL: str = get_redis_url()
except ImportError:
    DEFAULT_REDIS_URL: str = "redis://localhost:6379"

__all__ = [
    "CIRCUIT_BREAKER_ENABLED",
    # Constants
    "DEFAULT_REDIS_URL",
    "DELIBERATION_AVAILABLE",
    "MACI_AVAILABLE",
    "METERING_AVAILABLE",
    "METRICS_ENABLED",
    "POLICY_CLIENT_AVAILABLE",
    "BatchProcessor",
    "BusMetrics",
    # Main class and singleton
    "EnhancedAgentBus",
    "GovernanceIntegration",
    "MessageHandler",
    # Components
    "MessageValidator",
    # Utilities
    "_is_mock_instance",
    "get_agent_bus",
    "reset_agent_bus",
]
