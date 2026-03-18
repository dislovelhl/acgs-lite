"""
Message validation helpers for EnhancedAgentBus.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from ..components import GovernanceValidator

from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.validators import ValidationResult

from ..security.tenant_validator import TenantValidator
from ..security_helpers import normalize_tenant_id, validate_tenant_consistency

logger = get_logger(__name__)


# Mock detection helper - avoids importing unittest.mock in production
def _is_mock_instance(obj: object) -> bool:
    """Check if an object is a mock instance without importing unittest.mock."""
    return hasattr(obj, "_mock_name") or type(obj).__name__ in (
        "MagicMock",
        "Mock",
        "AsyncMock",
    )


class MessageValidator:
    """
    Validates messages for constitutional compliance and tenant isolation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        governance: GovernanceValidator,
        agents: JSONDict,
        metrics: JSONDict,
    ) -> None:
        """
        Initialize the message validator.

        Args:
            governance: GovernanceValidator component for constitutional checks.
            agents: Dict of registered agents for tenant validation.
            metrics: Metrics dict reference for recording failures/successes.
        """
        self._governance = governance
        self._agents = agents
        self._metrics = metrics

    def record_metrics_failure(self) -> None:
        """
        Record failure metrics atomically for message processing.

        Increments both 'messages_failed' and 'failed' counters in the internal
        metrics dictionary. This method is called when message validation,
        tenant verification, or constitutional hash checks fail.

        Thread Safety:
            This method modifies shared state. In high-concurrency scenarios,
            consider using atomic operations or locks if precise counts are
            required for billing/audit purposes.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        self._metrics["messages_failed"] += 1
        self._metrics["failed"] += 1

    def record_metrics_success(self) -> None:
        """
        Record success metrics atomically for message processing.

        Increments both 'sent' and 'messages_sent' counters in the internal
        metrics dictionary. This method is called after successful message
        validation and delivery.

        Thread Safety:
            This method modifies shared state. In high-concurrency scenarios,
            consider using atomic operations or locks if precise counts are
            required for billing/audit purposes.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        self._metrics["sent"] += 1
        self._metrics["messages_sent"] += 1

    def validate_constitutional_hash_for_message(
        self, msg: AgentMessage, result: ValidationResult
    ) -> bool:
        """
        Validate message constitutional hash via governance component.

        Ensures the message's constitutional hash matches the expected system
        hash (cdd01ef066bc6cf2). This is a critical security check that prevents
        unauthorized governance policy modifications or bypass attempts.

        Args:
            msg: The AgentMessage to validate. Must contain a constitutional_hash
                field that will be compared against the system hash.
            result: ValidationResult object where errors will be recorded if
                validation fails.

        Returns:
            bool: True if the constitutional hash is valid, False otherwise.
                On failure, the result object will contain specific error details.

        Side Effects:
            - Records failure metrics if validation fails
            - Increments sent counter for tracking total attempts

        Constitutional Hash: cdd01ef066bc6cf2
        """
        valid = self._governance.validate_constitutional_hash(msg, result)
        if not valid:
            self.record_metrics_failure()
            self._metrics["sent"] += 1
        return valid

    def validate_and_normalize_tenant(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """
        Normalize and validate tenant ID for multi-tenant message isolation.

        Performs three-stage tenant validation:
        1. Normalizes the tenant ID format (handles None, empty, whitespace)
        2. Validates tenant ID against security patterns (TenantValidator)
        3. Checks cross-tenant consistency between sender and receiver agents

        Args:
            msg: The AgentMessage to validate. The tenant_id field will be
                modified in-place to the normalized value.
            result: ValidationResult object where errors will be recorded if
                validation fails.

        Returns:
            bool: True if tenant validation passes, False otherwise.
                On failure, result.errors will contain specific violation details.

        Side Effects:
            - Modifies msg.tenant_id in-place with normalized value
            - Sets tenant_id to "default" if None after normalization
            - Records failure metrics on validation errors

        Raises:
            No exceptions are raised; errors are recorded in the result object.

        Security:
            Prevents cross-tenant data leakage by ensuring agents can only
            communicate within their tenant boundary.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        msg.tenant_id = normalize_tenant_id(msg.tenant_id)
        if msg.tenant_id is None:
            msg.tenant_id = "default"

        if msg.tenant_id and not TenantValidator.validate(msg.tenant_id):
            result.add_error(f"Invalid tenant_id format: {msg.tenant_id}")
            self.record_metrics_failure()
            self._metrics["sent"] += 1
            return False

        # Use registry manager's agents for consistency check
        errors = validate_tenant_consistency(
            self._agents, msg.from_agent, msg.to_agent, msg.tenant_id
        )
        if errors:
            for error in errors:
                result.add_error(error)
            self.record_metrics_failure()
            return False

        return True
