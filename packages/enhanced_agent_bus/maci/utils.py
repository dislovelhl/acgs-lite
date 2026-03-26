"""
MACI Utilities.

Lazy model loading proxies, model initialization helpers,
and role matrix validation.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable

from ..maci_imports import (
    ensure_maci_models_loaded,
    get_agent_message,
    get_enum_value_func,
    get_message_type,
)
from .models import (
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    MACIAction,
    MACIRole,
)

# Lazy-loaded model references
_AgentMessage: object = None
_MessageType: object = None
_get_enum_value: Callable[..., object] | None = None


def _ensure_models() -> None:
    """Ensure model classes are loaded."""
    global _AgentMessage, _MessageType, _get_enum_value
    if _AgentMessage is None:
        ensure_maci_models_loaded()
        _AgentMessage = get_agent_message()
        _MessageType = get_message_type()
        _get_enum_value = get_enum_value_func()


# For backward compatibility, provide module-level access via properties
class _ModelProxy:
    """Proxy that lazy-loads models on first access."""

    @classmethod
    def get_agent_message(cls) -> object:
        """Get the lazy-loaded AgentMessage model class."""
        _ensure_models()
        return _AgentMessage

    @classmethod
    def get_message_type(cls) -> object:
        """Get the lazy-loaded MessageType enum class."""
        _ensure_models()
        return _MessageType

    @classmethod
    def get_enum_value(cls) -> Callable[..., object] | None:
        """Get the lazy-loaded enum value getter function."""
        _ensure_models()
        return _get_enum_value


# Module-level aliases that work after ensure_maci_models_loaded() is called
# Import these directly: from .utils import AgentMessage
AgentMessage = _ModelProxy.get_agent_message
MessageType = _ModelProxy.get_message_type
get_enum_value = _ModelProxy.get_enum_value


def validate_maci_role_matrix(
    role_permissions: dict[MACIRole, set[MACIAction]] | None = None,
    validation_constraints: dict[MACIRole, set[MACIRole]] | None = None,
) -> list[str]:
    """Validate MACI duty-separation invariants for role/action matrices.

    Checks that the role permission matrix and validation constraints maintain
    proper separation of powers (Trias Politica) by ensuring no role has
    conflicting duties (e.g., both propose and validate).

    Args:
        role_permissions: Optional custom role permissions matrix
        validation_constraints: Optional custom validation constraints

    Returns:
        list of violation messages. Empty list means matrix is valid.
    """
    permissions = role_permissions or ROLE_PERMISSIONS
    constraints = validation_constraints or VALIDATION_CONSTRAINTS
    violations: list[str] = []

    for role, actions in permissions.items():
        if MACIAction.VALIDATE in actions and MACIAction.PROPOSE in actions:
            violations.append(f"{role.value} has conflicting duties: propose and validate")
        if MACIAction.VALIDATE in actions and MACIAction.SYNTHESIZE in actions:
            violations.append(f"{role.value} has conflicting duties: synthesize and validate")

    for role, target_roles in constraints.items():
        if role in target_roles:
            violations.append(f"{role.value} can validate itself")
        role_actions = permissions.get(role, set())
        if MACIAction.VALIDATE not in role_actions and MACIAction.AUDIT not in role_actions:
            violations.append(
                f"{role.value} has validation constraints but no validate/audit permission"
            )

    return violations
