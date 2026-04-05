"""
MACI Coordinator - Manages constitutional validation and role enforcement.

Constitutional Hash: 608508a9bd224290

Implements Trias Politica separation to prevent Gödel bypass attacks.
Agents cannot validate their own output (MACI separation principle).
"""

from __future__ import annotations

from typing import Any, Protocol

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger


class _RegistryProtocol(Protocol):
    """Minimal interface for MACIRoleRegistry."""

    async def register_agent(self, config: Any) -> None: ...


class _EnforcerProtocol(Protocol):
    """Minimal interface for MACIEnforcer."""

    async def validate_action(
        self, agent_id: str, action: Any, target_id: str | None = None
    ) -> Any: ...


logger = get_logger(__name__)
_MACI_COORDINATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class MACICoordinator:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(self, strict_mode: bool = True, enable_audit: bool = True):
        self._strict_mode = strict_mode
        self._enable_audit = enable_audit
        self._registry: Any = None
        self._enforcer: Any = None
        self._initialized = False
        self._registered_agents: dict[str, str] = {}
        self._validation_log: list[JSONDict] = []

        self._initialize_maci()

    def _initialize_maci(self) -> None:
        try:
            from ..maci_enforcement import MACIEnforcer, MACIRoleRegistry

            self._registry = MACIRoleRegistry()
            self._enforcer = MACIEnforcer(registry=self._registry, strict_mode=self._strict_mode)
            self._initialized = True
            logger.info(f"MACICoordinator: Initialized (strict_mode={self._strict_mode})")
        except ImportError:
            logger.info("MACI enforcement not available, using basic validation")
        except _MACI_COORDINATOR_OPERATION_ERRORS as e:
            logger.warning(f"MACI initialization failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized and self._enforcer is not None

    async def register_agent(
        self,
        agent_id: str,
        role: str,
        capabilities: list[str] | None = None,
    ) -> bool:
        if self._registry:
            try:
                from ..maci_enforcement import MACIAgentRoleConfig, MACIRole

                role_enum = MACIRole.parse(role)
                config = MACIAgentRoleConfig(
                    agent_id=agent_id,
                    role=role_enum,
                    capabilities=capabilities or [],
                )
                await self._registry.register_agent(config)
                self._registered_agents[agent_id] = role_enum.value
                logger.debug(f"Registered agent {agent_id} with role {role}")
                return True
            except _MACI_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"Agent registration failed: {e}")
                return False

        self._registered_agents[agent_id] = role
        return True

    async def validate_action(
        self,
        agent_id: str,
        action: str,
        target_output_id: str | None = None,
    ) -> JSONDict:
        validation_result: JSONDict = {
            "agent_id": agent_id,
            "action": action,
            "allowed": False,
            "reason": "",
            "constitutional_hash": self.constitutional_hash,
        }

        if target_output_id == agent_id:
            validation_result["reason"] = "MACI violation: self-validation forbidden (Gödel bypass)"
            self._log_validation(validation_result)
            return validation_result

        if self._enforcer:
            try:
                from ..maci_enforcement import MACIAction

                action_enum = MACIAction(action.lower())
                result = await self._enforcer.validate_action(
                    agent_id=agent_id,
                    action=action_enum,
                    target_id=target_output_id,
                )
                validation_result["allowed"] = result.allowed
                validation_result["reason"] = result.reason if hasattr(result, "reason") else ""
                self._log_validation(validation_result)
                return validation_result

            except _MACI_COORDINATOR_OPERATION_ERRORS as e:
                validation_result["reason"] = f"Validation error: {e}"
                self._log_validation(validation_result)
                return validation_result

        agent_role = self._registered_agents.get(agent_id)
        if not agent_role:
            validation_result["reason"] = "Agent not registered"
            self._log_validation(validation_result)
            return validation_result

        allowed_actions = self._get_role_permissions(agent_role)
        if action.lower() in allowed_actions:
            validation_result["allowed"] = True
            validation_result["reason"] = "Action permitted for role"
        else:
            validation_result["reason"] = f"Action '{action}' not permitted for role '{agent_role}'"

        self._log_validation(validation_result)
        return validation_result

    def _get_role_permissions(self, role: str) -> set[str]:
        permissions = {
            "executive": {"propose", "synthesize", "query"},
            "legislative": {"extract_rules", "synthesize", "query"},
            "judicial": {"validate", "audit", "query", "emergency_cooldown"},
            "monitor": {"monitor_activity", "query"},
            "auditor": {"audit", "query"},
            "controller": {"enforce_control", "query"},
            "implementer": {"synthesize", "query"},
        }
        return permissions.get(role.lower(), {"query"})

    def _log_validation(self, result: JSONDict) -> None:
        if self._enable_audit:
            self._validation_log.append(result)
            if len(self._validation_log) > 1000:
                self._validation_log = self._validation_log[-500:]

    async def check_cross_role_constraint(
        self,
        validator_id: str,
        target_role: str,
    ) -> JSONDict:
        validator_role = self._registered_agents.get(validator_id)

        if not validator_role:
            return {
                "allowed": False,
                "reason": "Validator not registered",
                "constitutional_hash": self.constitutional_hash,
            }

        constraints = {
            "judicial": {"executive", "legislative", "implementer"},
            "auditor": {"monitor", "controller", "implementer"},
        }

        allowed_targets = constraints.get(validator_role.lower(), set())

        if target_role.lower() in allowed_targets:
            return {
                "allowed": True,
                "reason": f"{validator_role} can validate {target_role}",
                "constitutional_hash": self.constitutional_hash,
            }

        return {
            "allowed": False,
            "reason": f"{validator_role} cannot validate {target_role} (Trias Politica)",
            "constitutional_hash": self.constitutional_hash,
        }

    def is_enabled(self) -> bool:
        return self._initialized

    def get_stats(self) -> JSONDict:
        role_counts: dict[str, int] = {}
        for role in self._registered_agents.values():
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "constitutional_hash": self.constitutional_hash,
            "maci_available": self.is_available,
            "strict_mode": self._strict_mode,
            "audit_enabled": self._enable_audit,
            "registered_agents": len(self._registered_agents),
            "role_distribution": role_counts,
            "validation_log_size": len(self._validation_log),
        }

    def get_recent_validations(self, limit: int = 10) -> list[JSONDict]:
        return self._validation_log[-limit:]
