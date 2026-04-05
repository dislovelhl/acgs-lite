"""
ACGS-2 Enhanced Agent Communication Bus
Constitutional Hash: 608508a9bd224290

High-performance, multi-tenant agent communication infrastructure for ACGS-2
constitutional governance platform.
"""

import sys

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__version__ = "3.0.2"
__constitutional_hash__ = CONSTITUTIONAL_HASH

# Backward-compatible import aliases for legacy module paths.
_module = sys.modules.get(__name__)
if _module is not None:
    for _alias in ("enhanced_agent_bus", "packages.enhanced_agent_bus", "core.enhanced_agent_bus"):
        if _alias not in sys.modules:
            sys.modules[_alias] = _module


class Init:
    def __init__(self, constitutional_hash: str | None = None) -> None:
        self._constitutional_hash = constitutional_hash or CONSTITUTIONAL_HASH

    def process(self, input_value: str | None) -> str | None:
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value


# fmt: off
from .agent_bus import EnhancedAgentBus
from .config import BusConfiguration
from .dependency_bridge import get_feature_flags as _get_feature_flags
from .exceptions import (
    AgentAlreadyRegisteredError,
    AgentBusError,
    AgentCapabilityError,
    AgentError,
    AgentNotRegisteredError,
    BusAlreadyStartedError,
    BusNotStartedError,
    BusOperationError,
    ConfigurationError,
    ConstitutionalError,
    ConstitutionalHashMismatchError,
    ConstitutionalValidationError,
    DeliberationError,
    DeliberationTimeoutError,
    HandlerExecutionError,
    MessageDeliveryError,
    MessageError,
    MessageRoutingError,
    MessageTimeoutError,
    MessageValidationError,
    OPAConnectionError,
    OPANotInitializedError,
    PolicyError,
    PolicyEvaluationError,
    PolicyNotFoundError,
    ReviewConsensusError,
    SignatureCollectionError,
)
from .interfaces import (
    AgentRegistry,
    MessageHandler,
    MessageRouter,
    MetricsCollector,
    ValidationStrategy,
)
from .message_processor import MessageProcessor
from .metering_manager import MeteringManager, create_metering_manager
from .models import CONSTITUTIONAL_HASH as MODEL_HASH
from .models import (
    AgentMessage,
    MessageStatus,
    MessageType,
    Priority,
    RiskLevel,
    RoutingContext,
    SessionGovernanceConfig,
    ValidationStatus,
)
from .models import PQCMetadata as ModelPQCMetadata
from .policy_resolver import PolicyResolutionResult, PolicyResolver
from .registry import (
    CapabilityBasedRouter,
    CompositeValidationStrategy,
    DirectMessageRouter,
    DynamicPolicyValidationStrategy,
    InMemoryAgentRegistry,
    RedisAgentRegistry,
    RustValidationStrategy,
    StaticHashValidationStrategy,
)
from .runtime_security import (
    RuntimeSecurityConfig,
    RuntimeSecurityScanner,
    SecurityEvent,
    SecurityEventType,
    SecurityScanResult,
    SecuritySeverity,
    get_runtime_security_scanner,
    scan_content,
)
from .session_context import (
    SessionContext,
    SessionContextManager,
    SessionContextStore,
)
from .siem_integration import (
    AlertLevel,
    AlertManager,
    AlertThreshold,
    EventCorrelator,
    SIEMConfig,
    SIEMEventFormatter,
    SIEMFormat,
    SIEMIntegration,
    close_siem,
    get_siem_integration,
    initialize_siem,
    log_security_event,
    security_audit,
)
from .validators import ValidationResult

_feature_flags = _get_feature_flags()
CIRCUIT_BREAKER_ENABLED: bool = _feature_flags.get("CIRCUIT_BREAKER_ENABLED", False)
DELIBERATION_AVAILABLE: bool = _feature_flags.get("DELIBERATION_AVAILABLE", False)
METERING_AVAILABLE: bool = _feature_flags.get("METERING_AVAILABLE", False)
METRICS_ENABLED: bool = _feature_flags.get("METRICS_ENABLED", False)
USE_RUST: bool = _feature_flags.get("USE_RUST", False)
del _feature_flags

from ._ext_cache_warming import *
from ._ext_cache_warming import _EXT_ALL as _CW_ALL
from ._ext_chaos import *
from ._ext_chaos import _EXT_ALL as _CHAOS_ALL
from ._ext_circuit_breaker import *
from ._ext_circuit_breaker import _EXT_ALL as _CB_ALL
from ._ext_circuit_breaker_clients import *
from ._ext_circuit_breaker_clients import _EXT_ALL as _CBC_ALL
from ._ext_cognitive import *
from ._ext_cognitive import _EXT_ALL as _COG_ALL
from ._ext_context_memory import *
from ._ext_context_memory import _EXT_ALL as _CM_ALL

# Phase 4: Context Window Optimization
from ._ext_context_optimization import *
from ._ext_context_optimization import _EXT_ALL as _CTX_ALL
from ._ext_decision_store import *
from ._ext_decision_store import _EXT_ALL as _DS_ALL
from ._ext_explanation_service import *
from ._ext_explanation_service import _EXT_ALL as _ES_ALL
from ._ext_langgraph import *
from ._ext_langgraph import _EXT_ALL as _LG_ALL
from ._ext_mcp import *
from ._ext_mcp import _EXT_ALL as _MCP_ALL

# Phase 6: Performance Optimization
from ._ext_performance import *
from ._ext_performance import _EXT_ALL as _PERF_ALL
from ._ext_persistence import *
from ._ext_persistence import _EXT_ALL as _PER_ALL
from ._ext_pqc import *
from ._ext_pqc import _EXT_ALL as _PQC_ALL
from ._ext_response_quality import *
from ._ext_response_quality import _EXT_ALL as _RQ_ALL

__all__ = [
    "CONSTITUTIONAL_HASH", "BusConfiguration", "MeteringManager", "create_metering_manager",
    "METRICS_ENABLED", "CIRCUIT_BREAKER_ENABLED", "DELIBERATION_AVAILABLE",
    "USE_RUST", "METERING_AVAILABLE", "AgentMessage", "MessageType", "Priority", "MessageStatus",
    "ValidationStatus", "RoutingContext", "RiskLevel", "SessionGovernanceConfig", "SessionContext",
    "SessionContextStore", "SessionContextManager", "PolicyResolver", "PolicyResolutionResult",
    "EnhancedAgentBus", "MessageProcessor", "ValidationResult", "AgentRegistry", "MessageRouter",
    "ValidationStrategy", "MessageHandler", "MetricsCollector", "InMemoryAgentRegistry",
    "DirectMessageRouter", "CapabilityBasedRouter", "StaticHashValidationStrategy",
    "DynamicPolicyValidationStrategy", "RustValidationStrategy", "CompositeValidationStrategy",
    "RedisAgentRegistry", "AgentBusError", "ConstitutionalError", "ConstitutionalHashMismatchError",
    "ConstitutionalValidationError", "MessageError", "MessageValidationError", "MessageDeliveryError",
    "MessageTimeoutError", "MessageRoutingError", "AgentError", "AgentNotRegisteredError",
    "AgentAlreadyRegisteredError", "AgentCapabilityError", "PolicyError", "PolicyEvaluationError",
    "PolicyNotFoundError", "OPAConnectionError", "OPANotInitializedError", "DeliberationError",
    "DeliberationTimeoutError", "SignatureCollectionError", "ReviewConsensusError", "BusOperationError",
    "BusNotStartedError", "BusAlreadyStartedError", "HandlerExecutionError", "ConfigurationError",
    "RuntimeSecurityConfig", "RuntimeSecurityScanner", "SecurityEvent", "SecurityEventType",
    "SecurityScanResult", "SecuritySeverity", "get_runtime_security_scanner", "scan_content",
    "SIEMFormat", "SIEMConfig", "SIEMEventFormatter", "SIEMIntegration", "AlertLevel", "AlertThreshold",
    "AlertManager", "EventCorrelator", "initialize_siem", "close_siem", "get_siem_integration",
    "log_security_event", "security_audit",
    "MODEL_HASH", "ModelPQCMetadata",
    *_CB_ALL, *_PQC_ALL, *_CW_ALL, *_COG_ALL, *_PER_ALL, *_CBC_ALL,
    *_DS_ALL, *_ES_ALL, *_MCP_ALL, *_CM_ALL, *_LG_ALL, *_CHAOS_ALL,
    *_CTX_ALL,  # Phase 4: Context Window Optimization
    *_RQ_ALL,   # Phase 5: Response Quality Enhancement
    *_PERF_ALL,  # Phase 6: Performance Optimization
]
# fmt: on
