"""
ACGS-2 Enhanced Agent Bus - Exceptions
Constitutional Hash: 608508a9bd224290

Backward-compatible re-export surface for all exception symbols.
"""

import sys

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .agent import AgentAlreadyRegisteredError, AgentCapabilityError, AgentNotRegisteredError
from .base import (
    AgentBusError,
    AgentError,
    BusOperationError,
    ConstitutionalError,
    MACIError,
    MessageError,
    PolicyError,
)
from .constitutional import ConstitutionalHashMismatchError, ConstitutionalValidationError

# Backward-compatible aliases for renamed exceptions
ConstitutionalViolationError = ConstitutionalValidationError
from .maci import (
    MACIActionDeniedError,
    MACICrossRoleValidationError,
    MACIRoleNotAssignedError,
    MACIRoleViolationError,
    MACISelfValidationError,
)
from .messaging import (
    MessageDeliveryError,
    MessageFormatError,
    MessageRoutingError,
    MessageTimeoutError,
    MessageValidationError,
    RateLimitExceeded,
)
from .operations import (
    AlignmentViolationError,
    AuthenticationError,
    AuthorizationError,
    BusAlreadyStartedError,
    BusNotStartedError,
    CheckpointError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DeliberationError,
    DeliberationTimeoutError,
    DependencyError,
    GovernanceError,
    HandlerExecutionError,
    ImpactAssessmentError,
    InterruptError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ReviewConsensusError,
    ServiceUnavailableError,
    SignatureCollectionError,
    TenantIsolationError,
    TimeoutError,
    ValidationError,
)
from .policy import (
    OPAConnectionError,
    OPANotInitializedError,
    PolicyEvaluationError,
    PolicyNotFoundError,
)

_REEXPORT_ONLY = (
    MACIActionDeniedError,
    MessageFormatError,
    AuthenticationError,
    AuthorizationError,
    CircuitBreakerOpenError,
    DependencyError,
    GovernanceError,
    ImpactAssessmentError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    TenantIsolationError,
    ValidationError,
)

# Ensure module aliasing across package import paths
_module = sys.modules.get(__name__)
if _module is not None:
    _ = sys.modules.setdefault("enhanced_agent_bus.exceptions", _module)
    _ = sys.modules.setdefault("enhanced_agent_bus.exceptions", _module)
    _ = sys.modules.setdefault("core.enhanced_agent_bus.exceptions", _module)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "AgentAlreadyRegisteredError",
    # Base
    "AgentBusError",
    "AgentCapabilityError",
    # Agent
    "AgentError",
    "AgentNotRegisteredError",
    "AlignmentViolationError",
    "BusAlreadyStartedError",
    "BusNotStartedError",
    # Bus Operations
    "BusOperationError",
    # Checkpoint
    "CheckpointError",
    # Configuration
    "ConfigurationError",
    # Constitutional
    "ConstitutionalError",
    "ConstitutionalHashMismatchError",
    "ConstitutionalValidationError",
    # Deliberation
    "DeliberationError",
    "DeliberationTimeoutError",
    "HandlerExecutionError",
    # Interrupt
    "InterruptError",
    "MACICrossRoleValidationError",
    # MACI Role Separation
    "MACIError",
    "MACIRoleNotAssignedError",
    "MACIRoleViolationError",
    "MACISelfValidationError",
    "MessageDeliveryError",
    # Message
    "MessageError",
    "MessageRoutingError",
    "MessageTimeoutError",
    "MessageValidationError",
    "OPAConnectionError",
    "OPANotInitializedError",
    # Policy/OPA
    "PolicyError",
    "PolicyEvaluationError",
    "PolicyNotFoundError",
    "RateLimitExceeded",
    "ReviewConsensusError",
    "SignatureCollectionError",
    "TimeoutError",
    # Backward-compat alias
    "ConstitutionalViolationError",
]
