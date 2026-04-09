"""EU AI Act Article 14 — Human Oversight Integration.

Article 14 requires that high-risk AI systems be designed so that natural
persons can effectively oversee them. Specifically, systems must:

- Allow designated persons to monitor, understand, and interpret outputs
- Enable intervention, halt, or override of the system
- Prevent over-reliance on AI outputs in high-impact decisions
- Be operable by persons with appropriate training

This module provides a lightweight Human-in-the-Loop (HITL) gateway that
can be wired into any AI pipeline to enforce Article 14 oversight requirements.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.eu_ai_act import HumanOversightGateway, OversightDecision

    gateway = HumanOversightGateway(
        system_id="cv-screener-v1",
        require_oversight_above_score=0.8,
    )

    # AI produces a decision with a confidence/impact score
    decision = gateway.submit(
        operation="reject_candidate",
        ai_output="Rejected: insufficient Python experience",
        impact_score=0.9,  # High impact — triggers oversight requirement
        context={"candidate_id": "abc123"},
    )

    if decision.requires_human_review:
        # Send to human reviewer via your notification system
        notify_reviewer(decision)
        # Wait for approval (via your own queue, webhook, etc.)
        decision = gateway.approve(decision.decision_id, reviewer_id="hr-manager-1")

    print(decision.outcome)  # "approved" | "rejected" | "pending"
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

CONSTITUTIONAL_HASH = "608508a9bd224290"

# Article 14 threshold: decisions with impact >= this require human oversight
DEFAULT_OVERSIGHT_THRESHOLD = 0.8


class OversightOutcome(StrEnum):
    """Possible outcomes of a human oversight decision."""

    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"  # Below threshold — no oversight needed
    ESCALATED = "escalated"


@dataclass
class OversightDecision:
    """A single oversight decision record.

    Attributes:
        decision_id: Unique identifier for this decision.
        system_id: ID of the AI system that produced the output.
        operation: The operation that requires oversight.
        ai_output: The AI system's proposed output or decision.
        impact_score: Estimated impact/risk score (0.0–1.0).
        outcome: Current decision state.
        requires_human_review: True if impact >= oversight threshold.
        reviewer_id: ID of the human reviewer (if assigned).
        reviewer_notes: Notes from the human reviewer.
        constitutional_hash: Hash validating governance configuration.
        submitted_at: ISO timestamp of submission.
        reviewed_at: ISO timestamp of human review (if completed).
        context: Arbitrary context metadata.
    """

    decision_id: str
    system_id: str
    operation: str
    ai_output: str
    impact_score: float
    outcome: OversightOutcome = OversightOutcome.PENDING
    requires_human_review: bool = False
    reviewer_id: str | None = None
    reviewer_notes: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH
    submitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reviewed_at: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the oversight decision to a dictionary for audit export."""
        return {
            "decision_id": self.decision_id,
            "system_id": self.system_id,
            "operation": self.operation,
            "ai_output": self.ai_output,
            "impact_score": self.impact_score,
            "outcome": self.outcome.value,
            "requires_human_review": self.requires_human_review,
            "reviewer_id": self.reviewer_id,
            "reviewer_notes": self.reviewer_notes,
            "constitutional_hash": self.constitutional_hash,
            "submitted_at": self.submitted_at,
            "reviewed_at": self.reviewed_at,
            "context": self.context,
        }


# Type alias for notification callback
NotificationCallback = Callable[[OversightDecision], None]


class HumanOversightGateway:
    """Article 14 compliant human oversight gateway for high-risk AI decisions.

    Routes high-impact decisions to human reviewers before allowing them to
    proceed. Low-impact decisions are automatically approved.

    The gateway does NOT implement the notification transport — that is your
    responsibility (email, Slack, queue, webhook). The gateway provides:
    - Decision submission and routing based on impact score
    - Approval/rejection recording with audit trail
    - Escalation path for decisions pending beyond SLA
    - Article 14 compliance summary

    Usage::

        def notify_hr(decision: OversightDecision) -> None:
            slack.post(f"Review needed: {decision.decision_id}")

        gateway = HumanOversightGateway(
            system_id="cv-screener-v1",
            oversight_threshold=0.7,
            on_review_required=notify_hr,
        )

        decision = gateway.submit("reject_candidate", ai_output, impact_score=0.9)
        # notify_hr is called automatically

        # Later, when reviewer responds:
        gateway.approve(decision.decision_id, reviewer_id="hr-1", notes="Looks correct")
    """

    def __init__(
        self,
        system_id: str,
        *,
        oversight_threshold: float = DEFAULT_OVERSIGHT_THRESHOLD,
        on_review_required: NotificationCallback | None = None,
        on_approved: NotificationCallback | None = None,
        on_rejected: NotificationCallback | None = None,
    ) -> None:
        if not 0.0 <= oversight_threshold <= 1.0:
            raise ValueError(
                f"oversight_threshold must be between 0.0 and 1.0, got {oversight_threshold}"
            )
        self.system_id = system_id
        self.oversight_threshold = oversight_threshold
        self._on_review_required = on_review_required
        self._on_approved = on_approved
        self._on_rejected = on_rejected
        self._decisions: dict[str, OversightDecision] = {}

    def submit(
        self,
        operation: str,
        ai_output: str,
        *,
        impact_score: float = 0.0,
        context: dict[str, Any] | None = None,
    ) -> OversightDecision:
        """Submit an AI decision for oversight evaluation.

        Decisions with impact_score >= oversight_threshold are routed to
        human reviewers. Lower-impact decisions are auto-approved.

        Args:
            operation: Name of the operation (e.g. "reject_candidate").
            ai_output: The AI system's proposed output or decision text.
            impact_score: Risk/impact score from 0.0 (low) to 1.0 (high).
            context: Optional metadata (e.g. entity IDs, request context).

        Returns:
            OversightDecision with current outcome and review status.
        """
        impact_score = max(0.0, min(1.0, impact_score))
        requires_review = impact_score >= self.oversight_threshold
        outcome = OversightOutcome.PENDING if requires_review else OversightOutcome.AUTO_APPROVED

        decision = OversightDecision(
            decision_id=str(uuid.uuid4())[:8],
            system_id=self.system_id,
            operation=operation,
            ai_output=ai_output[:2000],
            impact_score=impact_score,
            outcome=outcome,
            requires_human_review=requires_review,
            context=context or {},
        )

        self._decisions[decision.decision_id] = decision
        if requires_review:
            self._notify(self._on_review_required, decision)

        return decision

    def approve(
        self,
        decision_id: str,
        *,
        reviewer_id: str,
        notes: str | None = None,
    ) -> OversightDecision:
        """Record a human approval of a pending decision.

        Args:
            decision_id: The decision to approve.
            reviewer_id: ID of the approving reviewer.
            notes: Optional reviewer notes for the audit trail.

        Returns:
            Updated OversightDecision with approved outcome.

        Raises:
            KeyError: If decision_id is not found.
            ValueError: If decision is not in pending state.
        """
        decision = self._get_pending(decision_id)
        updated = OversightDecision(
            **{
                **decision.to_dict(),
                "outcome": OversightOutcome.APPROVED,
                "reviewer_id": reviewer_id,
                "reviewer_notes": notes,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._decisions[decision_id] = updated
        self._notify(self._on_approved, updated)

        return updated

    def reject(
        self,
        decision_id: str,
        *,
        reviewer_id: str,
        notes: str | None = None,
    ) -> OversightDecision:
        """Record a human rejection of a pending decision.

        Args:
            decision_id: The decision to reject.
            reviewer_id: ID of the rejecting reviewer.
            notes: Optional rejection rationale for the audit trail.

        Returns:
            Updated OversightDecision with rejected outcome.

        Raises:
            KeyError: If decision_id is not found.
            ValueError: If decision is not in pending state.
        """
        decision = self._get_pending(decision_id)
        updated = OversightDecision(
            **{
                **decision.to_dict(),
                "outcome": OversightOutcome.REJECTED,
                "reviewer_id": reviewer_id,
                "reviewer_notes": notes,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._decisions[decision_id] = updated
        self._notify(self._on_rejected, updated)

        return updated

    def escalate(self, decision_id: str, *, reason: str = "") -> OversightDecision:
        """Escalate a pending decision (e.g. SLA breach, unresolvable conflict).

        Args:
            decision_id: The decision to escalate.
            reason: Escalation reason for the audit trail.

        Returns:
            Updated OversightDecision with escalated outcome.
        """
        if decision_id not in self._decisions:
            raise KeyError(f"Decision {decision_id!r} not found")
        decision = self._decisions[decision_id]
        updated = OversightDecision(
            **{
                **decision.to_dict(),
                "outcome": OversightOutcome.ESCALATED,
                "reviewer_notes": reason or "Escalated — no reviewer response within SLA",
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._decisions[decision_id] = updated
        return updated

    def get_decision(self, decision_id: str) -> OversightDecision | None:
        """Retrieve a decision by ID."""
        return self._decisions.get(decision_id)

    def _notify(
        self,
        callback: NotificationCallback | None,
        decision: OversightDecision,
    ) -> None:
        """Fire an optional callback without letting notification failures block governance."""
        if callback is None:
            return
        with suppress(Exception):
            callback(decision)

    def pending_decisions(self) -> list[OversightDecision]:
        """Return all decisions awaiting human review."""
        return [d for d in self._decisions.values() if d.outcome == OversightOutcome.PENDING]

    def compliance_summary(self) -> dict[str, Any]:
        """Return an Article 14 compliance summary for this gateway instance."""
        total = len(self._decisions)
        if total == 0:
            return {
                "article": "Article 14 — Human Oversight",
                "compliant": True,
                "total_decisions": 0,
                "oversight_threshold": self.oversight_threshold,
                "system_id": self.system_id,
                "note": "No decisions submitted yet.",
            }

        required_review = sum(1 for d in self._decisions.values() if d.requires_human_review)
        reviewed = sum(
            1
            for d in self._decisions.values()
            if d.outcome in (OversightOutcome.APPROVED, OversightOutcome.REJECTED)
        )
        pending = sum(1 for d in self._decisions.values() if d.outcome == OversightOutcome.PENDING)

        return {
            "article": "Article 14 — Human Oversight",
            "compliant": pending == 0,
            "total_decisions": total,
            "required_human_review": required_review,
            "reviewed": reviewed,
            "pending": pending,
            "oversight_threshold": self.oversight_threshold,
            "oversight_rate": round(required_review / total, 4) if total else 0.0,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "system_id": self.system_id,
        }

    def export_decisions(self) -> list[dict[str, Any]]:
        """Export all decisions as a list of dicts for audit purposes."""
        return [d.to_dict() for d in self._decisions.values()]

    def _get_pending(self, decision_id: str) -> OversightDecision:
        if decision_id not in self._decisions:
            raise KeyError(f"Decision {decision_id!r} not found")
        decision = self._decisions[decision_id]
        if decision.outcome != OversightOutcome.PENDING:
            raise ValueError(
                f"Decision {decision_id!r} is not pending "
                f"(current outcome: {decision.outcome.value})"
            )
        return decision

    def __repr__(self) -> str:
        pending = len(self.pending_decisions())
        return (
            f"HumanOversightGateway(system_id={self.system_id!r}, "
            f"threshold={self.oversight_threshold}, "
            f"pending={pending})"
        )
