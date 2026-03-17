"""
ACGS-2 Deliberation Layer - OPA Policy Guard
Constitutional Hash: cdd01ef066bc6cf2

Provides OPA-based policy guard integration for the deliberation layer.
Implements VERIFY-BEFORE-ACT pattern with multi-signature collection,
critic agent integration, and comprehensive audit logging.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional, TypeAlias, Union, cast

from src.core.shared.type_guards import (
    get_bool,
    get_float,
    get_str,
    is_json_dict,
    is_policy_result,
)
from src.core.shared.types import JSONDict, JSONValue

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from packages.enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageStatus
    from packages.enhanced_agent_bus.opa_client import OPAClient, get_opa_client
    from packages.enhanced_agent_bus.validators import ValidationResult
except ImportError:
    try:
        from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageStatus
        from enhanced_agent_bus.opa_client import OPAClient, get_opa_client
        from enhanced_agent_bus.validators import ValidationResult
    except ImportError:
        try:
            from packages.enhanced_agent_bus.models import (
                CONSTITUTIONAL_HASH,
                AgentMessage,
                MessageStatus,
            )
            from packages.enhanced_agent_bus.validators import ValidationResult

            from ..opa_client import OPAClient, get_opa_client
        except ImportError:
            # Fallback for direct execution or testing
            from opa_client import OPAClient, get_opa_client  # type: ignore[no-redef]

try:
    from .opa_guard_models import (
        GUARD_CONSTITUTIONAL_HASH,
        CriticReview,
        GuardDecision,
        GuardResult,
        ReviewResult,
        ReviewStatus,
        Signature,
        SignatureResult,
        SignatureStatus,
    )
except ImportError:
    # Fallback for direct execution or testing
    from opa_guard_models import (  # type: ignore[no-redef]
        GUARD_CONSTITUTIONAL_HASH,
        CriticReview,
        GuardDecision,
        GuardResult,
        ReviewResult,
        ReviewStatus,
        Signature,
        SignatureResult,
        SignatureStatus,
    )

try:
    from .adaptive_router import get_adaptive_router
    from .deliberation_queue import DeliberationStatus, VoteType, get_deliberation_queue
except ImportError:
    # Fallback for direct execution or testing
    pass  # type: ignore[empty-body]

logger = get_logger(__name__)
_OPA_GUARD_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class OPAGuard:
    """
    OPA Policy Guard for the ACGS-2 deliberation layer.

    Implements VERIFY-BEFORE-ACT pattern with:
    - Pre-action policy validation
    - Multi-signature collection for high-risk decisions
    - Critic agent integration for comprehensive review
    - Audit logging for compliance tracking
    - Constitutional compliance enforcement
    """

    def __init__(
        self,
        opa_client: OPAClient | None = None,
        fail_closed: bool = True,
        enable_signatures: bool = True,
        enable_critic_review: bool = True,
        signature_timeout: int = 300,
        review_timeout: int = 300,
        high_risk_threshold: float = 0.8,
        critical_risk_threshold: float = 0.95,
    ):
        """
        Initialize OPA Guard.

        Args:
            opa_client: OPA client for policy evaluation (uses global if None)
            fail_closed: Deny actions when OPA evaluation fails
            enable_signatures: Enable multi-signature collection
            enable_critic_review: Enable critic agent reviews
            signature_timeout: Timeout for signature collection in seconds
            review_timeout: Timeout for critic reviews in seconds
            high_risk_threshold: Risk score threshold for requiring signatures
            critical_risk_threshold: Risk score threshold for requiring full review
        """
        self.opa_client = opa_client
        self.fail_closed = fail_closed
        self.enable_signatures = enable_signatures
        self.enable_critic_review = enable_critic_review
        self.signature_timeout = signature_timeout
        self.review_timeout = review_timeout
        self.high_risk_threshold = high_risk_threshold
        self.critical_risk_threshold = critical_risk_threshold

        # Active tracking
        self._pending_signatures: dict[str, SignatureResult] = {}
        self._pending_reviews: dict[str, ReviewResult] = {}
        self._audit_log: list[JSONDict] = []

        # Statistics
        self._stats = {
            "total_verifications": 0,
            "allowed": 0,
            "denied": 0,
            "required_signatures": 0,
            "required_reviews": 0,
            "signatures_collected": 0,
            "reviews_completed": 0,
            "constitutional_failures": 0,
        }

        # Registered critic agents
        self._critic_agents: dict[str, JSONDict] = {}

        # Default signers for different risk levels
        self._default_signers: dict[str, list[str]] = {
            "high": ["supervisor_agent", "compliance_agent"],
            "critical": ["supervisor_agent", "compliance_agent", "security_agent", "ethics_agent"],
        }

        logger.info(f"Initialized OPAGuard with constitutional hash {GUARD_CONSTITUTIONAL_HASH}")

    async def initialize(self) -> None:
        """Initialize the guard and its dependencies."""
        if self.opa_client is None:
            self.opa_client = get_opa_client(fail_closed=self.fail_closed)
        elif hasattr(self.opa_client, "fail_closed"):
            self.opa_client.fail_closed = self.fail_closed

        # At this point opa_client is guaranteed to be non-None
        await self.opa_client.initialize()
        logger.info("OPAGuard initialized successfully")

    async def close(self):
        """Close the guard and cleanup resources."""
        if self.opa_client:
            await self.opa_client.close()

        self._pending_signatures.clear()
        self._pending_reviews.clear()
        logger.info("OPAGuard closed")

    async def verify_action(
        self, agent_id: str, action: JSONDict, context: JSONDict
    ) -> GuardResult:
        """
        Pre-action validation using VERIFY-BEFORE-ACT pattern.

        This is the primary entry point for action validation. It:
        1. Validates constitutional compliance
        2. Evaluates OPA policies
        3. Assesses risk level
        4. Determines if signatures or reviews are required

        Args:
            agent_id: ID of the agent requesting the action
            action: Action details including type and parameters
            context: Additional context for the action

        Returns:
            GuardResult with validation outcome and requirements
        """
        self._stats["total_verifications"] += 1

        # Use type-safe getter for action type
        action_type = get_str(action, "type", "unknown")

        result = GuardResult(
            agent_id=agent_id,
            action_type=action_type,
        )

        try:
            # Step 1: Check constitutional compliance
            constitutional_valid = await self.check_constitutional_compliance(action)
            result.constitutional_valid = constitutional_valid

            if not constitutional_valid:
                self._stats["constitutional_failures"] += 1
                result.decision = GuardDecision.DENY
                result.is_allowed = False
                result.validation_errors.append("Constitutional compliance check failed")
                await self.log_decision({"action": action, "agent_id": agent_id}, result.to_dict())
                return result

            # Step 2: Evaluate OPA policy
            policy_input: JSONDict = {
                "agent_id": agent_id,
                "action": action,
                "context": context,
                "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Use type-safe getter for policy_path
            policy_path = get_str(action, "policy_path", "data.acgs.guard.verify")

            # Ensure OPA client is available
            if self.opa_client is None:
                result.decision = GuardDecision.DENY
                result.is_allowed = False
                result.validation_errors.append("OPA client not initialized")
                self._stats["denied"] += 1
                return result

            policy_result = await self.opa_client.evaluate_policy(policy_input, policy_path)

            result.policy_path = policy_path
            result.policy_result = policy_result

            # Step 3: Assess risk
            risk_score = self._calculate_risk_score(action, context, policy_result)
            result.risk_score = risk_score
            result.risk_level = self._determine_risk_level(risk_score)
            result.risk_factors = self._identify_risk_factors(action, context)

            # Step 4: Determine decision based on policy and risk
            if not policy_result.get("allowed", False):
                result.decision = GuardDecision.DENY
                result.is_allowed = False
                result.validation_errors.append(
                    policy_result.get("reason", "Policy evaluation denied action")
                )
                self._stats["denied"] += 1
            elif risk_score >= self.critical_risk_threshold:
                # Critical risk: require both signatures and review
                result.decision = GuardDecision.REQUIRE_REVIEW
                result.is_allowed = False
                result.requires_signatures = True
                result.requires_review = True
                result.required_signers = self._default_signers.get("critical", [])
                result.required_reviewers = list(self._critic_agents.keys())
                self._stats["required_reviews"] += 1
                self._stats["required_signatures"] += 1
            elif risk_score >= self.high_risk_threshold:
                # High risk: require signatures
                result.decision = GuardDecision.REQUIRE_SIGNATURES
                result.is_allowed = False
                result.requires_signatures = True
                result.required_signers = self._default_signers.get("high", [])
                self._stats["required_signatures"] += 1
            else:
                # Low/medium risk: allow
                result.decision = GuardDecision.ALLOW
                result.is_allowed = True
                self._stats["allowed"] += 1

            # Add any warnings from policy
            if policy_result.get("metadata", {}).get("mode") == "fallback":
                result.validation_warnings.append("OPA unavailable, using fallback validation")

            # Log the decision
            await self.log_decision(
                {"action": action, "agent_id": agent_id, "context": context}, result.to_dict()
            )

            return result

        except asyncio.CancelledError:
            raise
        except _OPA_GUARD_OPERATION_ERRORS as e:
            logger.error(f"Error in verify_action: {type(e).__name__}: {e}")
            result.decision = GuardDecision.DENY
            result.is_allowed = False
            result.validation_errors.append(f"Verification error: {e!s}")
            self._stats["denied"] += 1
            return result

    def _calculate_risk_score(
        self, action: JSONDict, context: JSONDict, policy_result: JSONDict
    ) -> float:
        """Calculate risk score for the action.

        Uses type-safe accessors for security-critical risk calculation.
        """
        risk_score = 0.0

        # Base risk from action type - use type-safe getter
        action_type = get_str(action, "type", "")
        high_risk_actions = {"delete", "modify", "execute", "deploy", "shutdown"}
        if action_type.lower() in high_risk_actions:
            risk_score += 0.3

        # Risk from impact score if present - try action first, then context
        impact_score_raw = action.get("impact_score")
        if impact_score_raw is None:
            impact_score_raw = context.get("impact_score", 0.0)
        # Safely convert to float
        impact_score: float = (
            float(impact_score_raw) if isinstance(impact_score_raw, (int, float)) else 0.0
        )
        risk_score += impact_score * 0.4

        # Risk from scope - use type-safe getter with fallback to context
        scope = get_str(action, "scope", "")
        if not scope:
            scope = get_str(context, "scope", "")
        if scope in {"global", "system", "all"}:
            risk_score += 0.2
        elif scope in {"organization", "tenant"}:
            risk_score += 0.1

        # Risk from policy result - safely navigate nested dict
        policy_metadata = policy_result.get("metadata")
        policy_risk: float = 0.0
        if is_json_dict(policy_metadata):
            policy_risk_raw = policy_metadata.get("risk_score", 0.0)
            if isinstance(policy_risk_raw, (int, float)):
                policy_risk = float(policy_risk_raw)
        risk_score += policy_risk * 0.1

        return min(risk_score, 1.0)

    def _determine_risk_level(self, risk_score: float) -> str:
        """Determine risk level from score."""
        if risk_score >= 0.9:
            return "critical"
        elif risk_score >= 0.7:
            return "high"
        elif risk_score >= 0.4:
            return "medium"
        else:
            return "low"

    def _identify_risk_factors(self, action: JSONDict, context: JSONDict) -> list[str]:
        """Identify specific risk factors for the action.

        Uses type-safe accessors for security-critical risk assessment.
        """
        factors: list[str] = []

        # Use type-safe getter for action type
        action_type = get_str(action, "type", "")
        if action_type.lower() in {"delete", "modify"}:
            factors.append(f"Destructive action type: {action_type}")

        # Use type-safe bool getter
        if get_bool(action, "affects_users", False):
            factors.append("Action affects user data")

        if get_bool(action, "irreversible", False):
            factors.append("Action is irreversible")

        # Use type-safe getter with fallback
        scope = get_str(action, "scope", "")
        if not scope:
            scope = get_str(context, "scope", "")
        if scope in {"global", "system", "all"}:
            factors.append(f"Wide scope: {scope}")

        if get_bool(context, "production", False):
            factors.append("Production environment")

        return factors

    async def collect_signatures(
        self,
        decision_id: str,
        required_signers: list[str],
        threshold: float = 1.0,
        timeout: int | None = None,
    ) -> SignatureResult:
        """
        Collect multi-signatures for high-risk decisions.

        Args:
            decision_id: Unique ID for the decision
            required_signers: list of required signer IDs
            threshold: Percentage of signatures required (0.0-1.0)
            timeout: Timeout in seconds (uses default if None)

        Returns:
            SignatureResult with collection status
        """
        timeout = timeout or self.signature_timeout

        # Create signature request
        signature_result = SignatureResult(
            decision_id=decision_id,
            required_signers=required_signers,
            required_count=len(required_signers),
            threshold=threshold,
            expires_at=datetime.now(UTC),
        )

        # Calculate expiry
        signature_result.expires_at = signature_result.created_at + timedelta(seconds=timeout)

        # Store for tracking
        self._pending_signatures[decision_id] = signature_result

        logger.info(
            f"Started signature collection for decision {decision_id}, "
            f"requiring {len(required_signers)} signers"
        )

        # Event-driven wait for signatures or timeout
        sig_event = asyncio.Event()
        signature_result._completion_event = sig_event  # type: ignore[attr-defined]

        try:
            await asyncio.wait_for(sig_event.wait(), timeout=timeout)
        except TimeoutError:
            signature_result.status = SignatureStatus.EXPIRED
            logger.warning(f"Signature collection timed out for decision {decision_id}")

        if signature_result.is_complete:
            self._stats["signatures_collected"] += 1
            logger.info(f"Signature collection completed for decision {decision_id}")
        elif signature_result.status == SignatureStatus.REJECTED:
            logger.warning(f"Signature collection rejected for decision {decision_id}")

        # Cleanup
        self._pending_signatures.pop(decision_id, None)

        return signature_result

    async def submit_signature(
        self, decision_id: str, signer_id: str, reasoning: str = "", confidence: float = 1.0
    ) -> bool:
        """
        Submit a signature for a pending decision.

        Args:
            decision_id: Decision ID to sign
            signer_id: ID of the signer
            reasoning: Reason for signing
            confidence: Confidence level (0.0-1.0)

        Returns:
            True if signature was accepted
        """
        signature_result = self._pending_signatures.get(decision_id)
        if not signature_result:
            logger.warning(f"No pending signature request for decision {decision_id}")
            return False

        signature = Signature(
            signer_id=signer_id,
            reasoning=reasoning,
            confidence=confidence,
        )

        success = signature_result.add_signature(signature)
        if success:
            logger.info(f"Signature from {signer_id} accepted for decision {decision_id}")
            # Signal event-driven waiters
            event = getattr(signature_result, "_completion_event", None)
            if event and (
                signature_result.is_complete or signature_result.status == SignatureStatus.REJECTED
            ):
                event.set()

        return success

    async def reject_signature(self, decision_id: str, signer_id: str, reason: str = "") -> bool:
        """
        Reject signing a decision.

        Args:
            decision_id: Decision ID to reject
            signer_id: ID of the rejecting signer
            reason: Reason for rejection

        Returns:
            True if rejection was recorded
        """
        signature_result = self._pending_signatures.get(decision_id)
        if not signature_result:
            logger.warning(f"No pending signature request for decision {decision_id}")
            return False

        success = signature_result.reject(signer_id, reason)
        if success:
            logger.info(f"Signature rejected by {signer_id} for decision {decision_id}: {reason}")
            # Signal event-driven waiters
            event = getattr(signature_result, "_completion_event", None)
            if event:
                event.set()

        return success

    async def submit_for_review(
        self,
        decision: JSONDict,
        critic_agents: list[str],
        review_types: list[str] | None = None,
        timeout: int | None = None,
    ) -> ReviewResult:
        """
        Submit a decision for critic agent review.

        Args:
            decision: Decision details to review
            critic_agents: list of critic agent IDs to request reviews from
            review_types: Types of review to request
            timeout: Timeout in seconds

        Returns:
            ReviewResult with review outcomes
        """
        timeout = timeout or self.review_timeout
        decision_id = decision.get("id", str(uuid.uuid4()))

        review_result = ReviewResult(
            decision_id=decision_id,
            required_critics=critic_agents,
            review_types=review_types or ["general", "safety"],
            timeout_seconds=timeout,
        )

        # Store for tracking
        self._pending_reviews[decision_id] = review_result

        logger.info(
            f"Started critic review for decision {decision_id}, "
            f"requesting {len(critic_agents)} reviewers"
        )

        # Notify critic agents (in a real system, this would send messages)
        for critic_id in critic_agents:
            if critic_id in self._critic_agents:
                callback = self._critic_agents[critic_id].get("callback")
                if callback:
                    try:
                        _t = asyncio.create_task(callback(decision, review_result))
                        _cid = critic_id
                        _t.add_done_callback(
                            lambda t, cid=_cid: (
                                t.exception()
                                and logger.warning(
                                    "Critic callback failed for %s: %s", cid, t.exception()
                                )
                            )
                        )
                    except _OPA_GUARD_OPERATION_ERRORS as e:
                        logger.error(f"Error notifying critic {critic_id}: {e}")

        # Wait for reviews or timeout using bounded iteration
        start_time = datetime.now(UTC)
        max_poll_iterations = int(timeout) + 1  # One iteration per second max
        for _ in range(max_poll_iterations):
            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed >= timeout:
                if not review_result.consensus_reached:
                    review_result.status = ReviewStatus.ESCALATED
                    logger.warning(f"Review timed out for decision {decision_id}")
                break

            if review_result.consensus_reached:
                self._stats["reviews_completed"] += 1
                logger.info(
                    f"Review completed for decision {decision_id}: "
                    f"{review_result.consensus_verdict}"
                )
                break

            await asyncio.sleep(1)

        # Cleanup
        self._pending_reviews.pop(decision_id, None)

        return review_result

    async def submit_review(
        self,
        decision_id: str,
        critic_id: str,
        verdict: str,
        reasoning: str = "",
        concerns: list[str] | None = None,
        recommendations: list[str] | None = None,
        confidence: float = 1.0,
    ) -> bool:
        """
        Submit a critic review for a pending decision.

        Args:
            decision_id: Decision ID being reviewed
            critic_id: ID of the critic agent
            verdict: Review verdict (approve/reject/escalate)
            reasoning: Reason for verdict
            concerns: list of concerns raised
            recommendations: list of recommendations
            confidence: Confidence level

        Returns:
            True if review was accepted
        """
        review_result = self._pending_reviews.get(decision_id)
        if not review_result:
            logger.warning(f"No pending review for decision {decision_id}")
            return False

        review = CriticReview(
            critic_id=critic_id,
            verdict=verdict,
            reasoning=reasoning,
            confidence=confidence,
            concerns=concerns or [],
            recommendations=recommendations or [],
        )

        success = review_result.add_review(review)
        if success:
            logger.info(
                f"Review from {critic_id} for decision {decision_id}: "
                f"{verdict} (confidence: {confidence})"
            )

        return success

    def register_critic_agent(
        self,
        critic_id: str,
        review_types: list[str],
        callback: object | None = None,
        metadata: JSONDict | None = None,
    ):
        """
        Register a critic agent for reviews.

        Args:
            critic_id: Unique ID for the critic agent
            review_types: Types of reviews this critic can perform
            callback: Async callback function for review requests
            metadata: Additional metadata about the critic
        """
        self._critic_agents[critic_id] = {
            "review_types": review_types,
            "callback": callback,
            "metadata": metadata or {},
            "registered_at": datetime.now(UTC).isoformat(),
        }
        logger.info(f"Registered critic agent {critic_id} for review types: {review_types}")

    def unregister_critic_agent(self, critic_id: str):
        """Unregister a critic agent."""
        if critic_id in self._critic_agents:
            del self._critic_agents[critic_id]
            logger.info(f"Unregistered critic agent {critic_id}")

    async def log_decision(self, decision: JSONDict, result: JSONDict):
        """
        Log a decision for audit purposes.

        Args:
            decision: Decision details
            result: Result of the decision evaluation
        """
        log_entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "decision": decision,
            "result": result,
            "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
        }

        self._audit_log.append(log_entry)

        # Keep only recent logs (last 10000)
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-10000:]

    async def check_constitutional_compliance(self, action: JSONDict) -> bool:
        """
        Check if an action complies with constitutional requirements.

        SECURITY: Respects fail_closed setting. When fail_closed=True (default),
        any evaluation error or missing result results in denial for security.

        Args:
            action: Action to check

        Returns:
            True if action is constitutionally compliant
        """
        try:
            # Check for constitutional hash in action - use type-safe getter
            action_hash = get_str(action, "constitutional_hash", "")
            if action_hash and action_hash != GUARD_CONSTITUTIONAL_HASH:
                logger.warning(f"Constitutional hash mismatch: {action_hash}")
                self._stats["constitutional_failures"] += 1
                return False

            # Ensure opa_client is initialized before evaluation
            if self.opa_client is None:
                logger.error("OPA client not initialized for constitutional check")
                self._stats["constitutional_failures"] += 1
                return not self.fail_closed

            # Evaluate constitutional policy
            input_data: JSONDict = {
                "action": action,
                "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            result = await self.opa_client.evaluate_policy(
                input_data, policy_path="data.acgs.constitutional.validate"
            )

            # SECURITY: Respect fail_closed setting when result is missing
            # If fail_closed=True, missing "allowed" key means deny
            # If fail_closed=False, missing "allowed" key means allow (legacy behavior)
            default_value = not self.fail_closed

            # type-safe extraction of allowed field
            if is_json_dict(result):
                return cast(bool, get_bool(result, "allowed", default_value))
            return default_value

        except _OPA_GUARD_OPERATION_ERRORS as e:
            logger.error(f"Constitutional compliance check error: {e}")
            self._stats["constitutional_failures"] += 1
            # SECURITY: Respect fail_closed setting on exceptions
            if self.fail_closed:
                logger.warning(
                    "Constitutional compliance check failed - denying action (fail_closed=True)"
                )
                return False
            else:
                logger.warning(
                    "Constitutional compliance check failed - allowing action "
                    "(fail_closed=False, availability mode)"
                )
                return True

    async def evaluate(
        self, message_data: JSONDict, policy_path: str = "data.acgs.guard.verify"
    ) -> JSONDict:
        """
        Evaluate OPA policy for a message.

        This is a simplified interface for policy evaluation used by workflow components.
        For full action verification with risk assessment, use verify_action() instead.

        Args:
            message_data: Message/action data to evaluate
            policy_path: OPA policy path (default: data.acgs.guard.verify)

        Returns:
            dict with 'allow', 'reasons', and 'version' keys
        """
        try:
            # Ensure OPA client is available
            if self.opa_client is None:
                logger.error("OPA client not initialized for policy evaluation")
                return {
                    "allow": not self.fail_closed,
                    "reasons": ["OPA client not initialized"],
                    "version": "error",
                }

            # Build input for OPA evaluation
            input_data: JSONDict = {
                "message": message_data,
                "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            result = await self.opa_client.evaluate_policy(input_data, policy_path)

            # type-safe extraction with fallback chain
            # SECURITY: Respect fail_closed when response is missing expected keys
            default_allow = not self.fail_closed
            allow_value: bool
            if is_json_dict(result):
                # Try 'allowed' first, then 'allow', default to fail_closed policy
                allowed_raw = result.get("allowed")
                if isinstance(allowed_raw, bool):
                    allow_value = allowed_raw
                else:
                    allow_raw = result.get("allow")
                    allow_value = allow_raw if isinstance(allow_raw, bool) else default_allow

                reasons_raw = result.get("reasons")
                reasons: list[str] = (
                    cast(list[str], reasons_raw) if isinstance(reasons_raw, list) else []
                )

                version = get_str(result, "version", "1.0.0")
            else:
                allow_value = default_allow
                reasons = []
                version = "1.0.0"

            return {
                "allow": allow_value,
                "reasons": reasons,
                "version": version,
            }

        except _OPA_GUARD_OPERATION_ERRORS as e:
            logger.error(f"OPA evaluation error: {e}")
            # Fallback: allow with warning when OPA unavailable
            return {
                "allow": not self.fail_closed,
                "reasons": [f"OPA evaluation error: {e!s}"],
                "version": "fallback",
            }

    def get_stats(self) -> JSONDict:
        """Get guard statistics."""
        return {
            **self._stats,
            "pending_signatures": len(self._pending_signatures),
            "pending_reviews": len(self._pending_reviews),
            "registered_critics": len(self._critic_agents),
            "audit_log_size": len(self._audit_log),
            "constitutional_hash": GUARD_CONSTITUTIONAL_HASH,
        }

    def get_audit_log(
        self, limit: int = 100, offset: int = 0, agent_id: str | None = None
    ) -> list[JSONDict]:
        """
        Get audit log entries.

        Args:
            limit: Maximum entries to return
            offset: Offset for pagination
            agent_id: Filter by agent ID

        Returns:
            list of audit log entries
        """
        logs = self._audit_log

        if agent_id:
            logs = [log for log in logs if log.get("decision", {}).get("agent_id") == agent_id]

        return logs[offset : offset + limit]


# Global guard instance
_opa_guard: OPAGuard | None = None


def get_opa_guard() -> OPAGuard:
    """Get or create global OPA guard instance."""
    global _opa_guard
    if _opa_guard is None:
        _opa_guard = OPAGuard()
    return _opa_guard


async def initialize_opa_guard(**kwargs) -> OPAGuard:
    """
    Initialize global OPA guard.

    Args:
        **kwargs: Arguments passed to OPAGuard constructor

    Returns:
        Initialized OPA guard
    """
    global _opa_guard
    _opa_guard = OPAGuard(**kwargs)
    await _opa_guard.initialize()
    return _opa_guard


async def close_opa_guard():
    """Close global OPA guard."""
    global _opa_guard
    if _opa_guard:
        await _opa_guard.close()
        _opa_guard = None


def reset_opa_guard() -> None:
    """Reset the global OPA guard instance without async cleanup.

    Used primarily for test isolation to prevent state leakage between tests.
    For graceful shutdown, use close_opa_guard() instead.
    Constitutional Hash: cdd01ef066bc6cf2
    """
    global _opa_guard
    _opa_guard = None


__all__ = [
    # Constants
    "GUARD_CONSTITUTIONAL_HASH",
    "CriticReview",
    # Models (re-exported for backward compatibility)
    "GuardDecision",
    "GuardResult",
    # Main class
    "OPAGuard",
    "ReviewResult",
    "ReviewStatus",
    "Signature",
    "SignatureResult",
    "SignatureStatus",
    "close_opa_guard",
    # Helper functions
    "get_opa_guard",
    "initialize_opa_guard",
    "reset_opa_guard",
]
