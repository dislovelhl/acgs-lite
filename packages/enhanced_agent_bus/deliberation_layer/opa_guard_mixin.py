"""
ACGS-2 Deliberation Layer - OPA Guard Mixin
Mixin class providing OPA Guard integration for the DeliberationLayer.
Constitutional Hash: 608508a9bd224290

This mixin encapsulates all OPA Guard-related methods used by the
DeliberationLayer class, implementing the VERIFY-BEFORE-ACT pattern
with multi-signature collection and critic agent reviews.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from .opa_guard import GuardResult, OPAGuard, ReviewResult, SignatureResult


class OPAGuardMixin:
    """
    Mixin providing OPA Guard integration methods.

    Expected attributes on the class using this mixin:
    - opa_guard: OPAGuard | None
    - deliberation_timeout: int
    """

    # type hints for expected attributes (set by the using class)
    opa_guard: "OPAGuard" | None
    deliberation_timeout: int

    async def verify_action(
        self, agent_id: str, action: JSONDict, context: JSONDict | None = None
    ) -> "GuardResult" | None:
        """
        Verify an action using OPA Guard (VERIFY-BEFORE-ACT pattern).

        Args:
            agent_id: ID of the agent performing the action
            action: Action details
            context: Additional context

        Returns:
            GuardResult with verification outcome, or None if guard disabled
        """
        if not self.opa_guard:
            return None

        return await self.opa_guard.verify_action(
            agent_id=agent_id,
            action=action,
            context=context or {},
        )

    async def collect_signatures(
        self,
        decision_id: str,
        required_signers: list[str],
        threshold: float = 1.0,
        timeout: int | None = None,
    ) -> "SignatureResult" | None:
        """
        Collect multi-signatures for a decision.

        Args:
            decision_id: Unique ID for the decision
            required_signers: list of required signer IDs
            threshold: Percentage of signatures required
            timeout: Timeout in seconds

        Returns:
            SignatureResult, or None if guard disabled
        """
        if not self.opa_guard:
            return None

        return await self.opa_guard.collect_signatures(
            decision_id=decision_id,
            required_signers=required_signers,
            threshold=threshold,
            timeout=timeout or self.deliberation_timeout,
        )

    async def submit_signature(
        self, decision_id: str, signer_id: str, reasoning: str = "", confidence: float = 1.0
    ) -> bool:
        """
        Submit a signature for a pending decision.

        Args:
            decision_id: Decision ID to sign
            signer_id: ID of the signer
            reasoning: Reason for signing
            confidence: Confidence level

        Returns:
            True if signature was accepted
        """
        if not self.opa_guard:
            return False

        return await self.opa_guard.submit_signature(
            decision_id=decision_id,
            signer_id=signer_id,
            reasoning=reasoning,
            confidence=confidence,
        )

    async def submit_for_review(
        self,
        decision: JSONDict,
        critic_agents: list[str],
        review_types: list[str] | None = None,
        timeout: int | None = None,
    ) -> "ReviewResult" | None:
        """
        Submit a decision for critic agent review.

        Args:
            decision: Decision details to review
            critic_agents: list of critic agent IDs
            review_types: Types of review to request
            timeout: Timeout in seconds

        Returns:
            ReviewResult, or None if guard disabled
        """
        if not self.opa_guard:
            return None

        return await self.opa_guard.submit_for_review(
            decision=decision,
            critic_agents=critic_agents,
            review_types=review_types,
            timeout=timeout or self.deliberation_timeout,
        )

    async def submit_critic_review(
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
        if not self.opa_guard:
            return False

        return await self.opa_guard.submit_review(
            decision_id=decision_id,
            critic_id=critic_id,
            verdict=verdict,
            reasoning=reasoning,
            concerns=concerns,
            recommendations=recommendations,
            confidence=confidence,
        )

    def register_critic_agent(
        self,
        critic_id: str,
        review_types: list[str],
        callback: Callable | None = None,
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
        if self.opa_guard:
            self.opa_guard.register_critic_agent(
                critic_id=critic_id,
                review_types=review_types,
                callback=callback,
                metadata=metadata,
            )

    def unregister_critic_agent(self, critic_id: str):
        """Unregister a critic agent."""
        if self.opa_guard:
            self.opa_guard.unregister_critic_agent(critic_id)

    def get_guard_audit_log(
        self, limit: int = 100, offset: int = 0, agent_id: str | None = None
    ) -> list[JSONDict]:
        """
        Get OPA guard audit log entries.

        Args:
            limit: Maximum entries to return
            offset: Offset for pagination
            agent_id: Filter by agent ID

        Returns:
            list of audit log entries
        """
        if not self.opa_guard:
            return []

        return self.opa_guard.get_audit_log(
            limit=limit,
            offset=offset,
            agent_id=agent_id,
        )


__all__ = ["OPAGuardMixin"]
