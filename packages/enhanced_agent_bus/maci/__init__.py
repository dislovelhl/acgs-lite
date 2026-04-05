"""
MACI (Maker-Approver-Checker-Inspector) Role Enforcement for Constitutional AI Governance.

This subpackage implements separation of powers (Trias Politica) for AI governance through
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
"""

from ..maci_imports import (
    CONSTITUTIONAL_HASH,
    MACICrossRoleValidationError,
    MACIError,
    MACIRoleNotAssignedError,
    MACIRoleViolationError,
    MACISelfValidationError,
)
from .config_loader import MACIConfigLoader, apply_maci_config
from .enforcer import MACIEnforcer
from .models import (
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    MACIAction,
    MACIAgentRoleConfig,
    MACIConfig,
    MACIRole,
    MACIValidationContext,
    MACIValidationResult,
)
from .registry import MACIAgentRecord, MACIRoleRegistry
from .strategy import MACIValidationStrategy, create_maci_enforcement_middleware
from .utils import _ensure_models, _ModelProxy, validate_maci_role_matrix

__all__ = [
    "CONSTITUTIONAL_HASH",
    "ROLE_HIERARCHY",
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
    "_ModelProxy",
    "_ensure_models",
    "apply_maci_config",
    "create_maci_enforcement_middleware",
    "validate_maci_role_matrix",
]
