"""
Governance Validator Component.

Constitutional Hash: cdd01ef066bc6cf2
MACI Role: JUDICIAL (constitutional validation)
"""

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

try:
    from ..adaptive_governance import (
        initialize_adaptive_governance,
        provide_governance_feedback,
    )

    ADAPTIVE_GOVERNANCE_AVAILABLE = True
except ImportError:
    ADAPTIVE_GOVERNANCE_AVAILABLE = False

logger = get_logger(__name__)
_GOVERNANCE_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class GovernanceValidator:
    """
    Handles constitutional validation and adaptive governance.
    Extracts governance logic from EnhancedAgentBus.
    """

    def __init__(
        self,
        config: JSONDict,
        policy_client: object | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        enable_adaptive_governance: bool = False,
    ):
        self.config = config
        self._policy_client = policy_client
        self._constitutional_hash = constitutional_hash
        self._enable_adaptive_governance = (
            enable_adaptive_governance and ADAPTIVE_GOVERNANCE_AVAILABLE
        )
        self._adaptive_governance: object | None = None
        self._metrics_ref: object | None = None  # Set by BusCore if needed, or passed in calls

    @property
    def constitutional_hash(self) -> str:
        return self._constitutional_hash

    async def initialize(self) -> None:
        """Initialize policy client and adaptive governance."""
        if self._policy_client:
            try:
                await self._policy_client.initialize()
                # Check for mock or dynamic policy needs
                if (
                    self.config.get("use_dynamic_policy", False)
                    or getattr(self._policy_client, "_is_mock", False)
                    or "mock" in str(self._policy_client).lower()
                ):
                    res = await self._policy_client.get_current_public_key()
                    if res:
                        self._constitutional_hash = res
            except _GOVERNANCE_OPERATION_ERRORS as e:
                logger.warning(f"Policy client initialization failed: {e}")

        # Initialize adaptive governance
        if self._enable_adaptive_governance:
            try:
                self._adaptive_governance = await initialize_adaptive_governance(
                    self.constitutional_hash
                )
                logger.info("Adaptive governance initialized")
            except _GOVERNANCE_OPERATION_ERRORS as e:
                logger.warning(f"Failed to initialize adaptive governance: {e}")
                self._adaptive_governance = None

    async def shutdown(self) -> None:
        """Shutdown adaptive governance."""
        if self._adaptive_governance:
            try:
                await self._adaptive_governance.shutdown()
            except _GOVERNANCE_OPERATION_ERRORS as e:
                logger.error(f"Error shutting down adaptive governance: {e}")

    def validate_constitutional_hash(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """Validate message constitutional hash matches bus hash."""
        if msg.constitutional_hash != self.constitutional_hash:
            result.add_error(
                f"Constitutional hash mismatch: expected '{self.constitutional_hash[:8]}...', "
                f"got '{msg.constitutional_hash[:8]}...'"
            )
            return False
        return True

    async def evaluate_adaptive_governance(
        self, msg: AgentMessage, context: JSONDict
    ) -> tuple[bool, str]:
        """Evaluate message using adaptive governance."""
        if not self._adaptive_governance:
            return True, "Adaptive governance not available"

        try:
            # Prepare context for governance evaluation
            gov_context = {
                "tenant_id": msg.tenant_id,
                "constitutional_hash": self.constitutional_hash,
                **context,
            }

            # Convert message to governance evaluation format
            message_dict = {
                "from_agent": msg.from_agent,
                "to_agent": msg.to_agent,
                "content": msg.content,
                "tenant_id": msg.tenant_id,
                "constitutional_hash": msg.constitutional_hash,
                "metadata": msg.metadata,
            }

            # Get governance decision
            decision = await self._adaptive_governance.evaluate_governance_decision(
                message_dict, gov_context
            )

            # Log decision
            logger.info(
                f"Governance decision for message {msg.message_id}: "
                f"allowed={decision.action_allowed}, "
                f"impact={decision.impact_level.value}, "
                f"confidence={decision.confidence_score:.3f}"
            )

            return decision.action_allowed, decision.reasoning

        except _GOVERNANCE_OPERATION_ERRORS as e:
            logger.error(f"Adaptive governance evaluation failed: {e}")
            return False, f"Governance evaluation failed: {e}"

    def provide_feedback(self, msg: AgentMessage, success: bool) -> None:
        """Provide feedback to adaptive governance."""
        if self._adaptive_governance and hasattr(self._adaptive_governance, "decision_history"):
            # Find the most recent governance decision for this message
            recent_decisions = [
                d
                for d in reversed(self._adaptive_governance.decision_history)
                if hasattr(d, "features_used")
                and d.features_used.message_length == len(str(msg.content))
            ][:1]

            if recent_decisions:
                decision = recent_decisions[0]
                if ADAPTIVE_GOVERNANCE_AVAILABLE and provide_governance_feedback:
                    provide_governance_feedback(decision, success)
