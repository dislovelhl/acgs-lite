"""
ACGS-2 Enhanced Agent Bus - MACI Exceptions
Constitutional Hash: 608508a9bd224290
"""

from .base import MACIError


class MACIRoleViolationError(MACIError):
    """Raised when an agent attempts an action outside its role."""

    error_code = "MACI_ROLE_VIOLATION"

    def __init__(
        self,
        agent_id: str,
        role: str,
        action: str,
        allowed_roles: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.action = action
        self.allowed_roles = allowed_roles or []
        message = f"Agent '{agent_id}' ({role}) cannot perform '{action}'"
        if allowed_roles:
            message += f" - allowed roles: {', '.join(allowed_roles)}"
        super().__init__(
            message=message,
            details={
                "agent_id": agent_id,
                "role": role,
                "action": action,
                "allowed_roles": self.allowed_roles,
            },
        )


class MACISelfValidationError(MACIError):
    """Raised when an agent attempts to validate its own output (Gödel bypass)."""

    error_code = "MACI_SELF_VALIDATION"

    def __init__(
        self,
        agent_id: str,
        action: str,
        output_id: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.action = action
        self.output_id = output_id
        message = f"Agent '{agent_id}' cannot {action} its own output (Gödel bypass prevention)"
        if output_id:
            message += f" [output: {output_id}]"
        super().__init__(
            message=message,
            details={
                "agent_id": agent_id,
                "action": action,
                "output_id": output_id,
                "prevention_type": "godel_bypass",
            },
        )


class MACICrossRoleValidationError(MACIError):
    """Raised when cross-role validation constraints are violated."""

    error_code = "MACI_CROSS_ROLE_VALIDATION"

    def __init__(
        self,
        validator_agent: str,
        validator_role: str,
        target_agent: str,
        target_role: str,
        reason: str,
    ) -> None:
        self.validator_agent = validator_agent
        self.validator_role = validator_role
        self.target_agent = target_agent
        self.target_role = target_role
        self.reason = reason
        super().__init__(
            message=f"Cross-role validation error: {validator_agent} ({validator_role}) "
            f"cannot validate {target_agent} ({target_role}): {reason}",
            details={
                "validator_agent": validator_agent,
                "validator_role": validator_role,
                "target_agent": target_agent,
                "target_role": target_role,
                "reason": reason,
            },
        )


class MACIRoleNotAssignedError(MACIError):
    """Raised when an agent has no MACI role assigned."""

    error_code = "MACI_ROLE_NOT_ASSIGNED"

    def __init__(self, agent_id: str, operation: str) -> None:
        self.agent_id = agent_id
        self.operation = operation
        super().__init__(
            message=f"Agent '{agent_id}' has no MACI role assigned for operation: {operation}",
            details={
                "agent_id": agent_id,
                "operation": operation,
            },
        )


class MACIActionDeniedError(MACIError):
    """Raised when a MACI action is denied."""

    error_code = "MACI_ACTION_DENIED"


__all__ = [
    "MACIActionDeniedError",
    "MACICrossRoleValidationError",
    "MACIError",
    "MACIRoleNotAssignedError",
    "MACIRoleViolationError",
    "MACISelfValidationError",
]
