"""
Singleton pattern for global EnhancedAgentBus instance.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import EnhancedAgentBus

# Thread-safe singleton pattern for global agent bus
_default_bus: EnhancedAgentBus | None = None
_bus_lock = threading.Lock()


def get_agent_bus(**kwargs: object) -> EnhancedAgentBus:
    """Get the global agent bus instance (thread-safe).

    Uses double-checked locking pattern for thread safety.
    Note: kwargs are only used on first initialization.
    """
    global _default_bus
    if _default_bus is None:
        with _bus_lock:
            # Double-checked locking pattern
            if _default_bus is None:
                from .core import EnhancedAgentBus

                _default_bus = EnhancedAgentBus(**kwargs)
    return _default_bus


def reset_agent_bus() -> None:
    """Reset the global agent bus instance (thread-safe)."""
    global _default_bus
    with _bus_lock:
        _default_bus = None
