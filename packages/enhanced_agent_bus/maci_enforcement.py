"""
MACI (Maker-Approver-Checker-Inspector) Role Enforcement for Constitutional AI Governance.

This module implements separation of powers (Trias Politica) for AI governance through
role-based access control. It prevents Godel bypass attacks by enforcing strict duty
separation between agents with different roles.

MACI Role Model:
  - EXECUTIVE: Can propose governance actions and synthesize policies (cannot validate)
  - LEGISLATIVE: Can extract rules and synthesize policies (cannot propose or validate)
  - JUDICIAL: Can validate actions and audit decisions (cannot propose or synthesize)
  - MONITOR: Can monitor activity and query state (read-only)
  - AUDITOR: Can audit decisions and query state (read-only)
  - CONTROLLER: Can enforce control policies and query state
  - IMPLEMENTER: Can synthesize implementations and query state

Golden Rule: Agents NEVER validate their own output. Self-validation is a critical
security violation that enables Godel bypass attacks.

Constitutional Hash: 608508a9bd224290

NOTE: This file is a backward-compatibility shim. All implementation has been
moved to the `enhanced_agent_bus.maci` subpackage. Import from there for new code.
"""

# Backward compatibility — re-export everything from the new maci/ subpackage
from .maci import (
    CONSTITUTIONAL_HASH,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    MACIAction,
    MACIAgentRecord,
    MACIAgentRoleConfig,
    MACIConfig,
    MACIConfigLoader,
    MACICrossRoleValidationError,
    MACIEnforcer,
    MACIError,
    MACIRole,
    MACIRoleNotAssignedError,
    MACIRoleRegistry,
    MACIRoleViolationError,
    MACISelfValidationError,
    MACIValidationContext,
    MACIValidationResult,
    MACIValidationStrategy,
    _ensure_models,
    _ModelProxy,
    apply_maci_config,
    create_maci_enforcement_middleware,
    validate_maci_role_matrix,
)
from .maci_imports import (
    GLOBAL_SETTINGS_AVAILABLE,
    MACI_CORE_AVAILABLE,
    ensure_maci_models_loaded,
    get_agent_message,
    get_enum_value_func,
    get_iso_timestamp,
    get_message_type,
    global_settings,
)
from .maci_imports import (
    MACICrossRoleValidationError as _MACICrossRoleValidationError,
)
from .maci_imports import (
    MACIError as _MACIError,
)
from .maci_imports import (
    MACIRoleNotAssignedError as _MACIRoleNotAssignedError,
)
from .maci_imports import (
    MACIRoleViolationError as _MACIRoleViolationError,
)
from .maci_imports import (
    MACISelfValidationError as _MACISelfValidationError,
)
from .observability.structured_logging import get_logger

logger = get_logger(__name__)
MAX_MACI_VALIDATION_HISTORY = 1_000

# Module-level aliases that work after ensure_maci_models_loaded() is called
# Import these directly: from .maci_enforcement import AgentMessage
AgentMessage = _ModelProxy.get_agent_message
MessageType = _ModelProxy.get_message_type
get_enum_value = _ModelProxy.get_enum_value

__all__ = [
    "ROLE_PERMISSIONS",
    "VALIDATION_CONSTRAINTS",
    "MACIAction",
    "MACIAgentRecord",
    "MACIAgentRoleConfig",
    "MACIConfig",
    "MACIConfigLoader",
    # Exceptions (re-exported for consistent class identity)
    "MACICrossRoleValidationError",
    "MACIEnforcer",
    "MACIError",
    # Core classes
    "MACIRole",
    "MACIRoleNotAssignedError",
    "MACIRoleRegistry",
    "MACIRoleViolationError",
    "MACISelfValidationError",
    "MACIValidationContext",
    "MACIValidationResult",
    "MACIValidationStrategy",
    "apply_maci_config",
    "create_maci_enforcement_middleware",
    "validate_maci_role_matrix",
]
