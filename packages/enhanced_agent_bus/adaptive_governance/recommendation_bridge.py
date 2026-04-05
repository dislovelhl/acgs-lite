"""Bridge between AmendmentRecommender and ProposalEngine.

Transforms pending AmendmentRecommendations into ProposalRequests and
submits them through the constitutional proposal pipeline. This closes
the feedback loop: adaptive governance signals → amendment proposals →
human approval → constitutional activation.

MACI role: PROPOSER — creates proposals from recommendations, cannot
validate or execute.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .amendment_recommender import AmendmentRecommendation, AmendmentRecommender

logger = logging.getLogger(__name__)

# Default proposer ID for automated recommendations.
# IMPORTANT: This agent must be registered with PROPOSE permission in the
# MACI enforcer before using with the real ProposalEngine. The real engine
# validates MACI roles at create_proposal() time.
AUTOMATED_PROPOSER_ID = "adaptive-governance-recommender"


@dataclass(slots=True)
class BridgeResult:
    """Result of bridging a single recommendation to a proposal."""

    recommendation_id: str
    success: bool
    proposal_id: str = ""
    error: str = ""


@dataclass
class BridgeReport:
    """Summary of a bridge batch operation."""

    total: int = 0
    submitted: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[BridgeResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Bridge: {self.total} recommendations, "
            f"{self.submitted} submitted, "
            f"{self.failed} failed, "
            f"{self.skipped} skipped"
        )


def recommendation_to_proposal_dict(
    rec: AmendmentRecommendation,
    *,
    proposer_id: str = AUTOMATED_PROPOSER_ID,
) -> dict[str, Any]:
    """Transform an AmendmentRecommendation into a ProposalRequest-compatible dict.

    This is a pure data transformation — no side effects.

    Returns a dict matching ``ProposalRequest`` fields so it can be used
    with either the real ProposalEngine or a test stub.
    """
    return {
        "proposed_changes": rec.proposed_changes,
        "justification": (
            f"[{rec.trigger.value}] {rec.justification} "
            f"(priority: {rec.priority.value}, risk: {rec.risk_score:.2f})"
        ),
        "proposer_agent_id": proposer_id,
        "target_version": None,
        "new_version": None,
        "metadata": {
            "recommendation_id": rec.recommendation_id,
            "trigger": rec.trigger.value,
            "priority": rec.priority.value,
            "target_area": rec.target_area,
            "evidence": rec.evidence,
            "risk_score": rec.risk_score,
            "source": "amendment_recommender_bridge",
        },
    }


class RecommendationBridge:
    """Bridges AmendmentRecommender to ProposalEngine.

    Parameters
    ----------
    recommender:
        The ``AmendmentRecommender`` instance to drain recommendations from.
    proposal_engine:
        An object with ``async create_proposal(request)`` method.
        Pass ``None`` for dry-run mode (transforms but doesn't submit).
    proposer_id:
        Agent ID to use as the proposer in ProposalRequests.
    auto_acknowledge:
        If True, automatically acknowledge recommendations after successful
        submission. If False, caller must acknowledge manually.
    """

    def __init__(
        self,
        recommender: AmendmentRecommender,
        proposal_engine: Any = None,
        *,
        proposer_id: str = AUTOMATED_PROPOSER_ID,
        auto_acknowledge: bool = True,
    ) -> None:
        self._recommender = recommender
        self._engine = proposal_engine
        self._proposer_id = proposer_id
        self._auto_acknowledge = auto_acknowledge

    def get_pending_as_proposals(self) -> list[dict[str, Any]]:
        """Transform all pending recommendations into proposal dicts (dry run).

        Does NOT submit or acknowledge — purely for inspection.
        """
        pending = self._recommender.get_pending()
        return [
            recommendation_to_proposal_dict(rec, proposer_id=self._proposer_id) for rec in pending
        ]

    async def submit_pending(self) -> BridgeReport:
        """Submit all pending recommendations as proposals.

        Steps for each recommendation:
        1. Transform to ProposalRequest dict
        2. Submit via proposal_engine.create_proposal() (if engine provided)
        3. On success, acknowledge the recommendation (if auto_acknowledge)
        4. On failure, log and continue (fail-soft for individual items)
        """
        pending = self._recommender.get_pending()
        report = BridgeReport(total=len(pending))

        for rec in pending:
            proposal_dict = recommendation_to_proposal_dict(
                rec,
                proposer_id=self._proposer_id,
            )

            if self._engine is None:
                # Dry-run mode — skip submission
                report.skipped += 1
                report.results.append(
                    BridgeResult(
                        recommendation_id=rec.recommendation_id,
                        success=False,
                        error="dry-run: no proposal engine configured",
                    )
                )
                continue

            try:
                # Import ProposalRequest lazily to avoid hard dependency
                from enhanced_agent_bus.constitutional.proposal_engine import ProposalRequest

                request = ProposalRequest(**proposal_dict)
                response = await self._engine.create_proposal(request)
                proposal_id = getattr(getattr(response, "proposal", None), "proposal_id", "")

                report.submitted += 1
                report.results.append(
                    BridgeResult(
                        recommendation_id=rec.recommendation_id,
                        success=True,
                        proposal_id=proposal_id,
                    )
                )

                if self._auto_acknowledge:
                    self._recommender.acknowledge(rec.recommendation_id)

                logger.info(
                    "recommendation_bridged",
                    extra={
                        "recommendation_id": rec.recommendation_id,
                        "proposal_id": proposal_id,
                        "trigger": rec.trigger.value,
                        "priority": rec.priority.value,
                    },
                )

            except Exception as exc:
                report.failed += 1
                report.results.append(
                    BridgeResult(
                        recommendation_id=rec.recommendation_id,
                        success=False,
                        error=type(exc).__name__,
                    )
                )
                logger.warning(
                    "recommendation_bridge_failed",
                    extra={
                        "recommendation_id": rec.recommendation_id,
                        "error": type(exc).__name__,
                    },
                )

        return report


__all__ = [
    "AUTOMATED_PROPOSER_ID",
    "BridgeReport",
    "BridgeResult",
    "RecommendationBridge",
    "recommendation_to_proposal_dict",
]
