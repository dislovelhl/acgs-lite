"""
Enhanced Agent Bus - Modular package for high-performance agent communication.

This package provides the EnhancedAgentBus and related components for
agent-to-agent communication with constitutional compliance.

Constitutional Hash: 608508a9bd224290
"""

from .batch import BatchProcessor
from .core import EnhancedAgentBus
from .governance import GovernanceIntegration
from .messaging import MessageHandler
from .metrics import BusMetrics
from .singleton import get_agent_bus, reset_agent_bus
from .validation import MessageValidator, _is_mock_instance

__all__ = [
    "BatchProcessor",
    "BusMetrics",
    # Main class
    "EnhancedAgentBus",
    "GovernanceIntegration",
    "MessageHandler",
    # Components
    "MessageValidator",
    # Utilities
    "_is_mock_instance",
    # Singleton functions
    "get_agent_bus",
    "reset_agent_bus",
]
