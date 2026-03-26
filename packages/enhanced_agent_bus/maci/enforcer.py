"""
MACI Core Enforcement Engine.

Enforces separation of powers (Trias Politica) for AI governance,
preventing Godel bypass attacks through role-based access control.
Supports session-scoped agent registration and validation.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from collections import deque
from datetime import UTC, datetime

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.interfaces import RoleMatrixValidatorProtocol

from ..maci_imports import (
    CONSTITUTIONAL_HASH,
    MACICrossRoleValidationError,
    MACIRoleNotAssignedError,
    MACIRoleViolationError,
    MACISelfValidationError,
)
from ..observability.structured_logging import get_logger
from .models import (
    ROLE_PERMISSIONS,
    MACIAction,
    MACIValidationResult,
)
from .registry import MACIAgentRecord, MACIRoleRegistry
from .role_matrix_validator import RoleMatrixValidator
from .utils import validate_maci_role_matrix

logger = get_logger(__name__)
MAX_MACI_VALIDATION_HISTORY = 10_000


class MACIEnforcer:
    """MACI role enforcement with session context support.

    Enforces separation of powers (Trias Politica) for AI governance,
    preventing Godel bypass attacks through role-based access control.
    Supports session-scoped agent registration and validation.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        registry: MACIRoleRegistry | None = None,
        strict_mode: bool = True,
        enable_session_audit: bool = True,
        role_matrix_validator: RoleMatrixValidatorProtocol | None = None,
    ):
        """Initialize MACI enforcer.

        Args:
            registry: Optional MACIRoleRegistry instance
            strict_mode: If True, reject unauthorized actions (fail-closed)
            enable_session_audit: If True, include session context in audit logs
        """
        self.registry = registry or MACIRoleRegistry()
        self.strict_mode = strict_mode
        self.enable_session_audit = enable_session_audit
        self._role_matrix_validator = role_matrix_validator or RoleMatrixValidator()
        self._validation_log: deque[MACIValidationResult] = deque(
            maxlen=MAX_MACI_VALIDATION_HISTORY
        )
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._matrix_violations = validate_maci_role_matrix()
        if self._matrix_violations:
            err = "; ".join(self._matrix_violations)
            logger.error("Invalid MACI role matrix: %s", err)
            self._role_matrix_validator.validate(
                violations=self._matrix_violations,
                strict_mode=self.strict_mode,
            )

    async def validate_action(
        self,
        agent_id: str,
        action: MACIAction,
        target_output_id: str | None = None,
        target_agent_id: str | None = None,
        session_id: str | None = None,
    ) -> MACIValidationResult:
        """Validate an action with optional session context.

        Args:
            agent_id: Agent requesting the action
            action: Action being requested
            target_output_id: Optional output ID being targeted
            target_agent_id: Optional target agent ID
            session_id: Optional session ID for session-aware validation

        Returns:
            MACIValidationResult with validation outcome

        Raises:
            MACIRoleNotAssignedError: If agent has no role in strict mode
            MACIRoleViolationError: If action is not permitted for agent's role
            MACISelfValidationError: If agent tries to validate own output
            MACICrossRoleValidationError: If cross-role validation constraints violated
        """
        # Get agent record, optionally scoped to session
        rec = await self.registry.get_agent(agent_id, session_id=session_id)
        if not rec:
            if self.strict_mode:
                result = MACIValidationResult(
                    is_valid=False,
                    violation_type="not_assigned",
                    session_id=session_id,
                    details={"agent_id": agent_id, "action": action.value},
                )
                self._validation_log.append(result)
                raise MACIRoleNotAssignedError(agent_id, action.value)
            # Non-strict mode: unregistered agents are restricted to OBSERVER level (QUERY only).
            # Never grant write/execute actions to unknown agents — that would bypass MACI entirely.
            logger.warning(
                "Unregistered agent attempted action in non-strict mode; "
                "restricting to OBSERVER-level (QUERY only)",
                agent_id=agent_id,
                action=action.value,
                session_id=session_id,
            )
            if action != MACIAction.QUERY:
                result = MACIValidationResult(
                    is_valid=False,
                    violation_type="unregistered_agent_non_query",
                    session_id=session_id,
                    details={"agent_id": agent_id, "action": action.value},
                )
                self._validation_log.append(result)
                raise MACIRoleViolationError(  # type: ignore[call-arg]
                    agent_id,
                    "unregistered",
                    action.value,
                    allowed_roles=[],
                )
            return MACIValidationResult(is_valid=True, session_id=session_id)

        if not rec.can_perform(action):
            result = MACIValidationResult(
                is_valid=False,
                violation_type="role_violation",
                session_id=session_id,
                details={
                    "agent_id": agent_id,
                    "role": rec.role.value,
                    "action": action.value,
                },
            )
            self._validation_log.append(result)
            raise MACIRoleViolationError(  # type: ignore[call-arg]
                agent_id,
                rec.role.value,
                action.value,
                allowed_roles=[r.value for r in ROLE_PERMISSIONS if action in ROLE_PERMISSIONS[r]],
            )

        if action == MACIAction.VALIDATE:
            if target_agent_id:
                await self._check_cross_agent_constraint(rec, agent_id, target_agent_id, session_id)
            if target_output_id:
                await self._check_output_ownership_constraint(
                    rec, agent_id, target_output_id, session_id
                )

        # Successful validation with session context
        res = MACIValidationResult(
            is_valid=True,
            session_id=session_id,
            details={
                "agent_id": agent_id,
                "action": action.value,
                "agent_role": rec.role.value,
            },
        )
        self._validation_log.append(res)
        return res

    async def _verify_target_role_constraint(
        self,
        rec: "MACIAgentRecord",
        agent_id: str,
        target_agent: "MACIAgentRecord | None",
        target_id: str,
        target_type: str,
        session_id: str | None,
        not_found_action_name: str,
    ) -> None:
        """Helper to verify target agent existence and role constraints."""
        if not target_agent:
            if self.strict_mode:
                result = MACIValidationResult(
                    is_valid=False,
                    violation_type="target_not_found",
                    error_message=f"{target_type.capitalize()} {target_id} not found",
                    session_id=session_id,
                    details={f"target_{target_type}_id": target_id},
                )
                self._validation_log.append(result)
                if target_type == "agent":
                    raise MACIRoleNotAssignedError(target_id, not_found_action_name)
        elif not rec.can_validate_role(target_agent.role):
            result = MACIValidationResult(
                is_valid=False,
                violation_type="cross_role",
                session_id=session_id,
                details={
                    "agent_id": agent_id,
                    "agent_role": rec.role.value,
                    f"target_{target_type}_id": target_agent.agent_id,
                    f"{target_type}_role": target_agent.role.value,
                },
            )
            self._validation_log.append(result)
            raise MACICrossRoleValidationError(
                agent_id,
                rec.role.value,
                target_agent.agent_id,
                target_agent.role.value,
                "Role constraint violation",
            )

    async def _check_cross_agent_constraint(
        self,
        rec: "MACIAgentRecord",
        agent_id: str,
        target_agent_id: str,
        session_id: str | None,
    ) -> None:
        """Validate cross-role constraint when targeting another agent."""
        if agent_id == target_agent_id:
            result = MACIValidationResult(
                is_valid=False,
                violation_type="self_validation",
                session_id=session_id,
                details={"agent_id": agent_id, "action": MACIAction.VALIDATE.value},
            )
            self._validation_log.append(result)
            raise MACISelfValidationError(agent_id, MACIAction.VALIDATE.value)

        target = await self.registry.get_agent(target_agent_id, session_id=session_id)
        await self._verify_target_role_constraint(
            rec, agent_id, target, target_agent_id, "agent", session_id, "validate_target"
        )

    async def _check_output_ownership_constraint(
        self,
        rec: "MACIAgentRecord",
        agent_id: str,
        target_output_id: str,
        session_id: str | None,
    ) -> None:
        """Validate self-validation and cross-role constraints for output ownership."""
        producer_id = await self.registry.get_output_producer(
            target_output_id,
            session_id=session_id,
        )
        if producer_id == agent_id or target_output_id in rec.outputs:
            result = MACIValidationResult(
                is_valid=False,
                violation_type="self_validation",
                session_id=session_id,
                details={
                    "agent_id": agent_id,
                    "target_output_id": target_output_id,
                },
            )
            self._validation_log.append(result)
            raise MACISelfValidationError(agent_id, "validate", target_output_id)

        producer = (
            await self.registry.get_agent(producer_id, session_id=session_id)
            if producer_id
            else None
        )
        await self._verify_target_role_constraint(
            rec, agent_id, producer, target_output_id, "producer", session_id, ""
        )

    async def batch_validate_actions(
        self,
        requests: list[JSONDict],
        session_id: str | None = None,
    ) -> list[MACIValidationResult]:
        """Validate multiple actions in parallel to reduce latency.

        Each request should contain:
            - agent_id: str (required)
            - action: MACIAction (required)
            - target_output_id: str (optional)
            - target_agent_id: str (optional)
            - session_id: str (optional, overrides parameter)

        Args:
            requests: list of validation request dicts
            session_id: Default session ID for all requests (can be overridden per-request)

        Returns:
            list of MACIValidationResult (or exceptions for failed validations)
        """
        tasks = []
        for req in requests:
            # Allow per-request session_id override
            req_session_id = req.get("session_id", session_id)
            tasks.append(
                self.validate_action(
                    agent_id=req["agent_id"],
                    action=req["action"],
                    target_output_id=req.get("target_output_id"),
                    target_agent_id=req.get("target_agent_id"),
                    session_id=req_session_id,
                )
            )

        # Execute all validations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Convert exceptions to invalid validation results
        processed_results: list[MACIValidationResult] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                error_result = MACIValidationResult(
                    is_valid=False,
                    session_id=session_id,
                    details={"error": str(result), "request_index": i},
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)
        return processed_results

    def get_validation_log(self, session_id: str | None = None) -> list[MACIValidationResult]:
        """Get validation log, optionally filtered by session.

        Args:
            session_id: Optional session ID to filter by

        Returns:
            list of MACIValidationResult entries
        """
        if session_id is None:
            return list(self._validation_log)
        return [r for r in self._validation_log if r.session_id == session_id]

    def get_audit_log(self, session_id: str | None = None) -> list[JSONDict]:
        """Get audit log in dictionary format for external systems.

        Args:
            session_id: Optional session ID to filter by

        Returns:
            list of audit log dictionaries with constitutional hash
        """
        log = self.get_validation_log(session_id)
        return [r.to_audit_dict() for r in log]

    def clear_validation_log(self, session_id: str | None = None) -> int:
        """Clear validation log, optionally for a specific session.

        Args:
            session_id: Optional session ID to clear (clears all if None)

        Returns:
            Number of entries cleared
        """
        if session_id is None:
            count = len(self._validation_log)
            self._validation_log.clear()
            return count

        # Filter out entries for the specified session
        original_count = len(self._validation_log)
        self._validation_log = deque(
            (r for r in self._validation_log if r.session_id != session_id),
            maxlen=MAX_MACI_VALIDATION_HISTORY,
        )
        return original_count - len(self._validation_log)

    async def validate_session_bypass(
        self,
        agent_id: str,
        action: MACIAction,
        session_id: str,
    ) -> MACIValidationResult:
        """Validate that session policies cannot bypass MACI enforcement.

        This is a critical security check that ensures session-level governance
        cannot circumvent role-based access control. All actions must still
        go through MACI validation even with session overrides.

        Args:
            agent_id: Agent requesting the action
            action: Action being requested
            session_id: Session identifier

        Returns:
            MACIValidationResult with bypass check outcome

        Raises:
            MACISelfValidationError: If self-validation is attempted (Godel bypass prevention)

        Note:
            This validation is ALWAYS enforced regardless of session policies.
            Constitutional hash: 608508a9bd224290
        """
        # CRITICAL: MACI enforcement cannot be bypassed by session policies
        # All session policies must operate within MACI constraints

        try:
            # First, validate the action through normal MACI validation
            result = await self.validate_action(
                agent_id=agent_id,
                action=action,
                session_id=session_id,
            )

            # Add bypass check metadata to the result
            result.details["bypass_check"] = "passed"
            result.details["bypass_check_timestamp"] = datetime.now(UTC).isoformat()
            result.details["constitutional_hash"] = self.constitutional_hash

        except MACISelfValidationError:
            # Self-validation is a critical Godel bypass attempt
            # This MUST be re-raised and cannot be caught
            raise

        except (  # type: ignore[misc]
            MACIRoleViolationError,
            MACICrossRoleValidationError,
            MACIRoleNotAssignedError,
        ) as e:
            # Role violations are blocked but converted to result for consistency
            result = MACIValidationResult(
                is_valid=False,
                violation_type=getattr(e, "violation_type", "role_violation"),
                error_message=str(e),
                session_id=session_id,
                details={
                    "bypass_check": "blocked",
                    "bypass_check_reason": "MACI enforcement cannot be bypassed",
                    "original_error": str(e),
                },
            )
            self._validation_log.append(result)

        logger.debug(
            f"Session bypass check for agent {agent_id}, action {action.value}, "
            f"session {session_id}: {'passed' if result.is_valid else 'blocked'}"
        )
        return result
