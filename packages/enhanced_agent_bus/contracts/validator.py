"""
ACGS-2 Enhanced Agent Bus - Contract Validator & Registry
Constitutional Hash: 608508a9bd224290

Provides:
- ContractValidationResult — outcome of validating a message against a contract
- ContractValidator — stateless validator that checks messages against C=(P,I,G,R)
- ContractRegistry — singleton registry mapping agent_id -> AgentBehavioralContract

Validation is **advisory by default** — violations are logged as warnings and
returned in the result, but do not hard-block message processing unless the
caller opts to enforce.  Controlled by the ``ACGS_ENABLE_ABC_CONTRACTS``
environment variable.
"""

from __future__ import annotations

import os
import threading
from typing import ClassVar

from pydantic import BaseModel, Field

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import AgentBehavioralContract

logger = get_logger(__name__)

# Feature flag ----------------------------------------------------------
_ABC_ENABLED_ENV = "ACGS_ENABLE_ABC_CONTRACTS"


def _is_abc_enabled() -> bool:
    """Return True when behavioral contract validation is active."""
    return os.environ.get(_ABC_ENABLED_ENV, "").lower() in {"1", "true", "yes"}


# Validation result -----------------------------------------------------


class ContractValidationResult(BaseModel):
    """Outcome of validating a message against an agent behavioral contract.

    Attributes:
        valid: True when no violations were found.
        violations: Hard violations that SHOULD block the message.
        warnings: Soft issues that warrant attention but are non-blocking.
    """

    valid: bool = True
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# Validator -------------------------------------------------------------


class ContractValidator:
    """Stateless validator that checks message metadata against a contract.

    The validator inspects:
    1. **Constitutional hash** — the contract's hash must match the message's.
    2. **Permissions** — the requested action must be in ``allowed_actions``
       (when the list is non-empty) and the impact score must not exceed
       ``max_impact_score``.
    3. **Restrictions** — the requested action must NOT appear in
       ``prohibited_actions``, and the requested resource must NOT appear
       in ``prohibited_resources``.
    """

    def validate_message(
        self,
        message_metadata: dict[str, object],
        contract: AgentBehavioralContract,
    ) -> ContractValidationResult:
        """Validate *message_metadata* against *contract*.

        Args:
            message_metadata: Dictionary with optional keys ``action``,
                ``resource``, ``impact_score``, and ``constitutional_hash``.
            contract: The agent's behavioral contract to validate against.

        Returns:
            A ``ContractValidationResult`` with any violations or warnings.
        """
        violations: list[str] = []
        warnings: list[str] = []

        # --- Constitutional hash check ---------------------------------
        msg_hash = message_metadata.get("constitutional_hash")
        if msg_hash is not None and msg_hash != contract.constitutional_hash:
            violations.append(
                f"Constitutional hash mismatch: message={msg_hash}, "
                f"contract={contract.constitutional_hash}"
            )

        action: str | None = message_metadata.get("action")  # type: ignore[assignment]
        resource: str | None = message_metadata.get("resource")  # type: ignore[assignment]
        impact_score: float | None = message_metadata.get("impact_score")  # type: ignore[assignment]

        # --- Permission checks -----------------------------------------
        if action and contract.permissions.allowed_actions:
            if action not in contract.permissions.allowed_actions:
                violations.append(
                    f"Action '{action}' not in allowed_actions: "
                    f"{contract.permissions.allowed_actions}"
                )

        if impact_score is not None:
            if impact_score > contract.permissions.max_impact_score:
                violations.append(
                    f"Impact score {impact_score} exceeds max "
                    f"{contract.permissions.max_impact_score}"
                )

        # --- Restriction checks ----------------------------------------
        if action and action in contract.restrictions.prohibited_actions:
            violations.append(f"Action '{action}' is prohibited by contract restrictions")

        if resource and resource in contract.restrictions.prohibited_resources:
            violations.append(f"Resource '{resource}' is prohibited by contract restrictions")

        valid = len(violations) == 0

        if not valid:
            logger.warning(
                "Contract validation failed",
                agent_id=contract.agent_id,
                violations=violations,
            )

        return ContractValidationResult(
            valid=valid,
            violations=violations,
            warnings=warnings,
        )


# Registry (thread-safe singleton) -------------------------------------


class ContractRegistry:
    """Thread-safe singleton registry mapping agent IDs to behavioral contracts.

    Usage::

        registry = ContractRegistry()
        registry.register("agent-1", contract)
        contract = registry.get("agent-1")
    """

    _instance: ClassVar[ContractRegistry | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> ContractRegistry:
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._contracts = {}
                cls._instance = instance
            return cls._instance

    # -- public API -----------------------------------------------------

    def register(
        self,
        agent_id: str,
        contract: AgentBehavioralContract,
    ) -> None:
        """Register or overwrite the contract for *agent_id*.

        Args:
            agent_id: The agent whose contract is being registered.
            contract: The behavioral contract to associate.
        """
        with self._lock:
            self._contracts[agent_id] = contract
            logger.info(
                "Registered behavioral contract",
                agent_id=agent_id,
                version=contract.version,
            )

    def get(self, agent_id: str) -> AgentBehavioralContract | None:
        """Return the contract for *agent_id*, or ``None`` if unregistered."""
        with self._lock:
            return self._contracts.get(agent_id)  # type: ignore[no-any-return]

    def list_agents(self) -> list[str]:
        """Return a sorted list of all registered agent IDs."""
        with self._lock:
            return sorted(self._contracts.keys())

    def unregister(self, agent_id: str) -> bool:
        """Remove the contract for *agent_id*.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        with self._lock:
            if agent_id in self._contracts:
                del self._contracts[agent_id]
                logger.info("Unregistered behavioral contract", agent_id=agent_id)
                return True
            return False

    def clear(self) -> None:
        """Remove all registered contracts.  Intended for testing."""
        with self._lock:
            self._contracts.clear()

    @classmethod
    def _reset_singleton(cls) -> None:
        """Destroy the singleton instance.  **Test-only.**"""
        with cls._lock:
            cls._instance = None
