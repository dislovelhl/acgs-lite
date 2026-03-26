"""
ACGS-2 OPA Client Package
Constitutional Hash: 608508a9bd224290

Re-exports all public symbols for backward compatibility.
Callers can continue to use:
    from enhanced_agent_bus.opa_client import OPAClient, get_opa_client, ...
"""

# Cache mixin and its module-level constants
from .cache import (
    _CACHE_HASH_MODES,
    DEFAULT_CACHE_HASH_MODE,
    FAST_HASH_AVAILABLE,
    REDIS_AVAILABLE,
    REDIS_CLIENT_AVAILABLE,
    OPAClientCacheMixin,
    aioredis,
    get_redis_url,
)

# Core: OPAClient (composed class), OPAClientCore, singleton functions, SDK flag
from .core import (
    OPA_SDK_AVAILABLE,
    EmbeddedOPA,
    OPAClient,
    OPAClientCore,
    _opa_client,
    close_opa_client,
    get_opa_client,
    initialize_opa_client,
)

# Health / multi-path mixin
from .health import OPAClientHealthMixin

__all__ = [
    "OPAClient",
    "close_opa_client",
    "get_opa_client",
    "initialize_opa_client",
]
