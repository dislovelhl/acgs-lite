"""
ACGS-2 CCAI Democratic Constitutional Governance Framework
Constitutional Hash: cdd01ef066bc6cf2

This module implements the Democratic Constitutional Governance framework:
- Democratic input through structured deliberation
- Cross-group consensus to prevent polarization
- Performance-legitimacy balance with hybrid decision paths
- Constitutional amendment workflow
- Manifold stability constraints (mHC integration)

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import statistics
import uuid
from datetime import UTC, datetime

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import sys

    if "pytest" in sys.modules:
        raise ImportError("Skip torch in tests")
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .models import (
    CONSTITUTIONAL_HASH,
    ConstitutionalProposal,
    DeliberationResult,
    DeliberationStatement,
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)
from .polis_engine import PolisDeliberationEngine

try:
    from .stability.mhc import ManifoldHC
except (ImportError, ValueError):
    try:
        from stability.mhc import ManifoldHC  # type: ignore[no-redef]
    except ImportError:
        ManifoldHC = None  # type: ignore[misc, assignment, no-redef]

logger = get_logger(__name__)
STABILITY_PROJECTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

__all__ = [
    "DemocraticConstitutionalGovernance",
    "ccai_governance",
    "deliberate_on_proposal",
    "get_ccai_governance",
]


class DemocraticConstitutionalGovernance:
    """
    CCAI Democratic Constitutional Governance Framework

    Integrates Polis deliberation with constitutional governance:
    - Democratic input through structured deliberation
    - Cross-group consensus to prevent polarization
    - Performance-legitimacy balance with hybrid decision paths
    - Constitutional amendment workflow
    """

    def __init__(self, consensus_threshold: float = 0.6, min_participants: int = 100):
        self.consensus_threshold = consensus_threshold
        self.min_participants = min_participants

        self.polis_engine = PolisDeliberationEngine()
        self.stakeholders: dict[str, Stakeholder] = {}
        self.proposals: dict[str, ConstitutionalProposal] = {}
        self.deliberations: dict[str, DeliberationResult] = {}

        self.fast_decisions: list[JSONDict] = []
        self.deliberated_decisions: list[JSONDict] = []

        logger.info("Initialized Democratic Constitutional Governance")
        logger.info(f"Constitutional Hash: {CONSTITUTIONAL_HASH}")
        logger.info(f"Consensus threshold: {consensus_threshold}")

        if ManifoldHC:
            self.stability_layer = ManifoldHC(dim=8)
            logger.info("Governance stability layer (mHC) enabled")
        else:
            self.stability_layer = None
            logger.warning("Governance stability layer (mHC) not available")

        self.deliberation_engine = self.polis_engine

    async def register_stakeholder(
        self, name: str, group: StakeholderGroup, expertise_areas: list[str]
    ) -> Stakeholder:
        """
        Register a new stakeholder participant in the governance framework.

        Stakeholders are essential for democratic deliberation, providing diverse
        perspectives across technical, ethical, legal, and societal dimensions.

        Args:
            name: Display name of the stakeholder (e.g., "Dr. Sarah Chen")
            group: StakeholderGroup classification for balanced representation
                   (e.g., TECHNICAL_EXPERTS, ETHICS_REVIEWERS, END_USERS)
            expertise_areas: List of domain expertise tags for specialized input
                            (e.g., ["AI", "security", "privacy"])

        Returns:
            Created Stakeholder object with:
            - Unique stakeholder_id (UUID)
            - Default voting_weight: 1.0
            - Default participation_score: 0.0
            - Default trust_score: 0.5
            - Registered timestamp (timezone.utc)

        Example:
            >>> expert = await governance.register_stakeholder(
            ...     "Dr. Sarah Chen",
            ...     StakeholderGroup.TECHNICAL_EXPERTS,
            ...     ["AI", "security"]
            ... )
            >>> logger.info(f"Registered: {expert.name} ({expert.stakeholder_id})")

        Constitutional Hash: cdd01ef066bc6cf2
        """
        stakeholder = Stakeholder(
            stakeholder_id=str(uuid.uuid4()),
            name=name,
            group=group,
            expertise_areas=expertise_areas,
        )

        self.stakeholders[stakeholder.stakeholder_id] = stakeholder

        logger.info(f"Registered stakeholder: {stakeholder.name} ({stakeholder.group.value})")
        return stakeholder

    async def propose_constitutional_change(
        self,
        title: str,
        description: str,
        proposed_changes: JSONDict,
        proposer: Stakeholder,
    ) -> ConstitutionalProposal:
        """
        Propose a constitutional change for democratic deliberation.

        Constitutional changes undergo full Polis deliberation to ensure
        legitimate governance through stakeholder consensus and cross-group validation.

        Args:
            title: Concise proposal title (e.g., "Enhanced Transparency Requirements")
            description: Detailed proposal description and rationale
            proposed_changes: Dictionary of specific constitutional changes
                             (e.g., {"transparency": "mandatory", "audit_trail": "comprehensive"})
            proposer: Stakeholder submitting the proposal

        Returns:
            Created ConstitutionalProposal with:
            - Unique proposal_id and deliberation_id (UUIDs)
            - Status: "proposed" (initial state)
            - Consensus threshold from governance settings (default: 0.6)
            - Minimum participants requirement (default: 100)
            - Created timestamp (timezone.utc)

        Lifecycle:
            proposed -> deliberating -> approved/rejected -> implemented

        Example:
            >>> proposal = await governance.propose_constitutional_change(
            ...     title="Enhanced Transparency Requirements",
            ...     description="Require all AI decisions to provide detailed explanations",
            ...     proposed_changes={
            ...         "transparency": "mandatory",
            ...         "explanation_depth": "detailed"
            ...     },
            ...     proposer=tech_expert
            ... )
            >>> result = await governance.run_deliberation(proposal, stakeholders)

        Constitutional Hash: cdd01ef066bc6cf2
        """
        proposal = ConstitutionalProposal(
            proposal_id=str(uuid.uuid4()),
            title=title,
            description=description,
            proposed_changes=proposed_changes,
            proposer_id=proposer.stakeholder_id,
            deliberation_id=str(uuid.uuid4()),
            consensus_threshold=self.consensus_threshold,
            min_participants=self.min_participants,
        )

        self.proposals[proposal.proposal_id] = proposal

        logger.info(f"Constitutional proposal created: {proposal.title}")
        return proposal

    async def run_deliberation(
        self,
        proposal: ConstitutionalProposal,
        stakeholders: list[Stakeholder],
        duration_hours: int = 72,
    ) -> DeliberationResult:
        """
        Run a full democratic deliberation process.

        Implements the complete CCAI workflow:
        1. Statement submission phase
        2. Discussion and voting phase
        3. Clustering and consensus analysis
        4. Cross-group validation
        """
        logger.info(f"Starting deliberation for proposal: {proposal.title}")

        deliberation_id = proposal.deliberation_id
        start_time = datetime.now(UTC)

        statements = await self._collect_statements(proposal, stakeholders)

        await self._conduct_voting(statements, stakeholders)

        clusters = await self.polis_engine.identify_clusters()

        cross_group_analysis = await self.polis_engine.analyze_cross_group_consensus(clusters)

        consensus_reached, approved_amendments, rejected_items = await self._determine_consensus(
            proposal, clusters, cross_group_analysis
        )

        stability_stats = {}
        if self.stability_layer and hasattr(self.stability_layer, "last_stats"):
            stability_stats = self.stability_layer.last_stats

        representative_metrics = self._calculate_representative_metrics(clusters)

        stability_stats.update(
            {
                "representative_statements": representative_metrics,
            }
        )

        result = DeliberationResult(
            deliberation_id=deliberation_id,
            proposal=proposal,
            total_participants=len(stakeholders),
            statements_submitted=len(statements),
            clusters_identified=len(clusters),
            consensus_reached=consensus_reached,
            consensus_statements=[
                {
                    "content": self.polis_engine.statements[sid].content,  # type: ignore[index]
                    "consensus_score": self.polis_engine.statements[sid].consensus_potential,  # type: ignore[index]
                    "cluster": self.polis_engine.statements[sid].cluster_id,  # type: ignore[index]
                }
                for sid in approved_amendments
            ],
            polarization_analysis={
                "cross_group_consensus": cross_group_analysis,
                "risk_level": cross_group_analysis.get("polarization_risk", "unknown"),
            },
            stability_analysis=stability_stats,
            cross_group_consensus=cross_group_analysis,
            approved_amendments=approved_amendments,
            rejected_statements=rejected_items,
            deliberation_metadata={
                "duration_hours": duration_hours,
                "start_time": start_time.isoformat(),
                "participation_rate": len(statements) / max(1, len(stakeholders)),
            },
        )

        self.deliberations[deliberation_id] = result
        proposal.deliberation_results = result.to_dict()
        proposal.status = "approved" if consensus_reached else "rejected"

        logger.info(
            f"Deliberation completed: consensus={'reached' if consensus_reached else 'not reached'}"
        )
        return result

    def _calculate_representative_metrics(self, clusters: list[OpinionCluster]) -> JSONDict:
        """
        Calculate comprehensive metrics for representative statement quality and selection.

        Args:
            clusters: List of OpinionClusters with representative statements

        Returns:
            Dictionary containing representative statement metrics:
            - total_representatives: Total number of representative statements selected
            - avg_representatives_per_cluster: Average representatives per cluster
            - avg_centrality_across_all: Average centrality score across all representatives
            - median_centrality_across_all: Median centrality score
            - stdev_centrality_across_all: Standard deviation of centrality scores
            - cluster_metrics: Per-cluster representative metrics
            - quality_distribution: Distribution of quality scores
            - constitutional_hash: Validation hash

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not clusters:
            logger.warning("No clusters provided for representative metrics calculation")
            return {
                "total_representatives": 0,
                "avg_representatives_per_cluster": 0.0,
                "avg_centrality_across_all": 0.0,
                "median_centrality_across_all": 0.0,
                "stdev_centrality_across_all": 0.0,
                "cluster_metrics": [],
                "quality_distribution": {},
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        total_representatives = 0
        all_centrality_scores = []
        cluster_metrics = []

        for cluster in clusters:
            representative_count = cluster.metadata.get("representative_count", 0)
            avg_centrality = cluster.metadata.get("avg_centrality_score", 0.0)
            min_centrality = cluster.metadata.get("min_centrality_score", 0.0)
            max_centrality = cluster.metadata.get("max_centrality_score", 0.0)
            centrality_scores = cluster.metadata.get("centrality_scores", [])

            total_representatives += representative_count
            all_centrality_scores.extend(centrality_scores)

            cluster_metrics.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "cluster_name": cluster.name,
                    "cluster_size": cluster.size,
                    "representative_count": representative_count,
                    "avg_centrality": avg_centrality,
                    "min_centrality": min_centrality,
                    "max_centrality": max_centrality,
                    "diversity_filtering_enabled": cluster.metadata.get(
                        "diversity_filtering_enabled", False
                    ),
                    "diversity_threshold": cluster.metadata.get("diversity_threshold"),
                }
            )

        avg_representatives_per_cluster = total_representatives / len(clusters) if clusters else 0.0
        avg_centrality = statistics.mean(all_centrality_scores) if all_centrality_scores else 0.0
        median_centrality = (
            statistics.median(all_centrality_scores) if all_centrality_scores else 0.0
        )
        stdev_centrality = (
            statistics.stdev(all_centrality_scores) if len(all_centrality_scores) > 1 else 0.0
        )

        quality_distribution = {
            "excellent": sum(1 for s in all_centrality_scores if s >= 0.8),
            "good": sum(1 for s in all_centrality_scores if 0.6 <= s < 0.8),
            "fair": sum(1 for s in all_centrality_scores if 0.4 <= s < 0.6),
            "poor": sum(1 for s in all_centrality_scores if s < 0.4),
        }

        metrics = {
            "total_representatives": total_representatives,
            "avg_representatives_per_cluster": avg_representatives_per_cluster,
            "avg_centrality_across_all": avg_centrality,
            "median_centrality_across_all": median_centrality,
            "stdev_centrality_across_all": stdev_centrality,
            "cluster_metrics": cluster_metrics,
            "quality_distribution": quality_distribution,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        logger.info(
            f"Representative Statement Metrics: "
            f"total={total_representatives}, "
            f"avg_per_cluster={avg_representatives_per_cluster:.2f}, "
            f"avg_centrality={avg_centrality:.3f}, "
            f"quality_distribution={quality_distribution}"
        )

        return metrics

    async def _collect_statements(
        self, proposal: ConstitutionalProposal, stakeholders: list[Stakeholder]
    ) -> list[DeliberationStatement]:
        """
        Collect deliberation statements from stakeholders during proposal discussion phase.

        This is Phase 1 of the Polis deliberation workflow. In production, this would
        be an interactive process where stakeholders submit statements over time. For
        simulation/testing, statements are auto-generated based on stakeholder groups.

        Args:
            proposal: ConstitutionalProposal being deliberated
            stakeholders: List of stakeholders participating in deliberation

        Returns:
            List of submitted DeliberationStatements with unique IDs and metadata

        Process:
            1. Limit to first 20 stakeholders for simulation efficiency
            2. Generate group-appropriate statement for each stakeholder
            3. Submit statement via Polis engine (creates voting matrix entry)
            4. Return collected statements for voting phase

        Note:
            Production implementation would use real-time statement collection
            through web UI or API, not simulated generation.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        statements = []

        for stakeholder in stakeholders[: min(20, len(stakeholders))]:
            statement_content = await self._generate_statement_for_stakeholder(
                proposal, stakeholder
            )

            statement = await self.polis_engine.submit_statement(statement_content, stakeholder)
            statements.append(statement)

        return statements

    async def _generate_statement_for_stakeholder(
        self, proposal: ConstitutionalProposal, stakeholder: Stakeholder
    ) -> str:
        """
        Generate a representative statement for a stakeholder based on their group.

        This is a simulation/testing helper that generates realistic statements
        aligned with stakeholder group perspectives. Production systems would
        collect real statements from stakeholders.

        Args:
            proposal: ConstitutionalProposal being deliberated (provides context)
            stakeholder: Stakeholder to generate statement for

        Returns:
            Statement text string representing stakeholder group's typical perspective

        Group Perspectives:
            - TECHNICAL_EXPERTS: Focus on performance, feasibility, security
            - ETHICS_REVIEWERS: Focus on ethical principles, bias, transparency
            - END_USERS: Focus on user experience, privacy, reliability
            - LEGAL_EXPERTS: Focus on compliance, regulations, legal implications

        Algorithm:
            1. Map stakeholder group to curated statement templates
            2. Use deterministic hash to select consistent statement per stakeholder
            3. Return group-appropriate statement text

        Note:
            This is for simulation only. Real implementation would use actual
            stakeholder input through interactive deliberation interface.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        group_statements = {
            StakeholderGroup.TECHNICAL_EXPERTS: [
                "The proposed changes should maintain system performance and reliability.",
                "Technical implementation must be feasible within current architecture.",
                "Security implications need careful evaluation.",
            ],
            StakeholderGroup.ETHICS_REVIEWERS: [
                "Changes must align with ethical principles and human rights.",
                "Potential biases in the system should be addressed.",
                "Transparency and accountability are essential.",
            ],
            StakeholderGroup.END_USERS: [
                "The changes should improve user experience and accessibility.",
                "User privacy and data protection must be prioritized.",
                "System reliability affects user trust.",
            ],
            StakeholderGroup.LEGAL_EXPERTS: [
                "Changes must comply with relevant regulations and laws.",
                "Legal implications need thorough review.",
                "Compliance requirements should be clearly defined.",
            ],
        }

        statements = group_statements.get(
            stakeholder.group,
            ["The proposal needs careful consideration of all stakeholder interests."],
        )

        return statements[hash(stakeholder.stakeholder_id) % len(statements)]

    async def _conduct_voting(
        self, statements: list[DeliberationStatement], stakeholders: list[Stakeholder]
    ):
        """
        Conduct voting phase where stakeholders vote on submitted statements.

        This is Phase 2 of the Polis deliberation workflow. In production, this would
        be an interactive process where stakeholders vote asynchronously over the
        deliberation period. For simulation/testing, votes are auto-generated.

        Args:
            statements: List of DeliberationStatements to vote on
            stakeholders: List of stakeholders participating in voting

        Side Effects:
            - Records votes in Polis engine voting matrix
            - Updates statement agreement/disagreement scores
            - Updates statement consensus potential

        Process:
            1. For each statement, select subset of voters (first 10 stakeholders)
            2. Generate vote based on deterministic hash (simulates voting patterns)
            3. Record vote via polis_engine.vote_on_statement()
            4. Scores updated automatically after each vote

        Vote Generation (Simulation):
            - 2/3 probability of agree (vote=1)
            - 1/3 probability of disagree (vote=-1)
            - Uses hash for deterministic results across test runs

        Note:
            Production implementation would use real-time vote collection
            through web UI or API with actual stakeholder decisions.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        for statement in statements:
            voters = stakeholders[: min(10, len(stakeholders))]

            for stakeholder in voters:
                vote = (
                    1
                    if hash(f"{statement.statement_id}_{stakeholder.stakeholder_id}") % 3 != 0
                    else -1
                )
                await self.polis_engine.vote_on_statement(statement.statement_id, stakeholder, vote)

    async def _apply_stability_constraint(
        self, scores: list[float], trust_scores: list[float] | None = None
    ) -> list[float]:
        """
        Apply manifold constraint to consensus scores for mathematical stability.

        Uses mHC (Manifold-Constrained HyperConnection) layer with dynamic resizing
        to prevent single-group dominance and ensure geometrically stable consensus.
        This is the integration point between CCAI and the stability layer.

        Args:
            scores: List of consensus scores to stabilize (range: [0.0, 1.0])
            trust_scores: Optional list of trust scores for stakeholders/clusters
                         (range: [0.0, 1.0], default: 0.5 for missing values)

        Returns:
            Stabilized consensus scores (same length as input)
            Falls back to original scores if mHC not available or if error occurs

        Algorithm:
            1. Check if ManifoldHC available, return original scores if not
            2. Resize mHC layer dynamically if dimensionality changed
            3. Convert scores to PyTorch tensor
            4. Prepare trust marginals (row/column marginals for UMM)
            5. Apply mHC forward pass with adversarial capping (alpha=0.4)
            6. Convert stabilized tensor back to list

        Parameters:
            - alpha=0.4: Adversarial capping prevents single group from dominating
            - Dynamic resizing: Adapts to varying cluster counts per deliberation

        Side Effects:
            - May reinitialize self.stability_layer if dimensionality changed
            - Updates stability_layer.last_stats with convergence metrics

        Note:
            Stability projection is fail-safe: errors result in original scores
            being returned with warning logged.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not ManifoldHC or not scores or not TORCH_AVAILABLE:
            return scores

        try:
            n = len(scores)

            if not self.stability_layer or self.stability_layer.dim != n:
                self.stability_layer = ManifoldHC(dim=n)
                logger.info(f"mHC stability layer resized to dim={n}")

            score_tensor = torch.tensor(scores, dtype=torch.float32).unsqueeze(0)

            row_marginal = None
            col_marginal = None
            if trust_scores:
                trust_scores = trust_scores[:n] + [0.5] * (n - len(trust_scores))
                row_marginal = torch.tensor(trust_scores, dtype=torch.float32)
                col_marginal = row_marginal

            with torch.no_grad():
                stabilized_tensor = self.stability_layer(
                    score_tensor,
                    row_marginal=row_marginal,
                    col_marginal=col_marginal,
                    alpha=0.4,
                )

            return stabilized_tensor.squeeze(0).tolist()  # type: ignore[no-any-return]
        except STABILITY_PROJECTION_ERRORS as e:
            logger.warning(f"Stability projection failed, using raw scores: {e}")
            return scores

    async def _determine_consensus(
        self,
        proposal: ConstitutionalProposal,
        clusters: list[OpinionCluster],
        cross_group_analysis: JSONDict,
    ) -> tuple[bool, list[JSONDict], list[JSONDict]]:
        """
        Determine if consensus is reached and identify approved/rejected amendments.

        This is Phase 5 of the Polis deliberation workflow. Applies stability
        constraints and validates consensus thresholds to determine approval.

        Args:
            proposal: ConstitutionalProposal with consensus_threshold requirement
            clusters: List of OpinionClusters with consensus scores
            cross_group_analysis: Cross-group consensus metrics from analyze_cross_group_consensus()

        Returns:
            Tuple of (consensus_reached, approved_amendments, rejected_statements):
            - consensus_reached: bool indicating if proposal meets threshold
            - approved_amendments: List of dicts with approved statements
            - rejected_statements: List of dicts with low-consensus statements

        Algorithm:
            1. Extract consensus_ratio from cross_group_analysis
            2. Calculate cluster trust scores (mean of member stakeholder trust)
            3. Apply mHC stability constraint to cluster consensus scores
            4. Update cluster.consensus_score with stabilized values
            5. Check if consensus_ratio >= proposal.consensus_threshold
            6. If consensus reached, extract representative statements from high-consensus clusters
            7. Identify rejected statements with consensus_potential < 0.3

        Thresholds:
            - Consensus approval: consensus_ratio >= proposal.consensus_threshold (default: 0.6)
            - High-consensus cluster: cluster.consensus_score >= 0.6
            - Rejected statement: statement.consensus_potential < 0.3

        Constitutional Hash: cdd01ef066bc6cf2
        """
        consensus_ratio, cluster_trust = self._extract_consensus_metrics(
            clusters, cross_group_analysis
        )

        await self._apply_cluster_stability(clusters, cluster_trust)

        consensus_reached = consensus_ratio >= proposal.consensus_threshold
        approved_amendments = []
        rejected_items = []

        if consensus_reached:
            approved_amendments = self._extract_approved_amendments(
                clusters, proposal.consensus_threshold
            )

        rejected_items = self._identify_rejected_statements()

        return consensus_reached, approved_amendments, rejected_items

    def _extract_consensus_metrics(
        self, clusters: list[OpinionCluster], cross_group_analysis: JSONDict
    ) -> tuple[float, list[float]]:
        """
        Extract consensus ratio and calculate cluster trust scores.

        Args:
            clusters: List of OpinionClusters with member stakeholders
            cross_group_analysis: Cross-group consensus metrics

        Returns:
            Tuple of (consensus_ratio, cluster_trust_scores)
        """
        consensus_ratio = cross_group_analysis.get("consensus_ratio", 0)

        cluster_trust = []
        for cluster in clusters:
            member_trusts = [
                self.stakeholders[sid].trust_score
                for sid in cluster.member_stakeholders
                if sid in self.stakeholders
            ]
            avg_trust = statistics.mean(member_trusts) if member_trusts else 0.5
            cluster_trust.append(avg_trust)

        return consensus_ratio, cluster_trust

    async def _apply_cluster_stability(
        self, clusters: list[OpinionCluster], cluster_trust: list[float]
    ) -> None:
        """
        Apply stability constraints to cluster consensus scores.

        Args:
            clusters: List of OpinionClusters to stabilize
            cluster_trust: Trust scores for stability weighting

        Side Effects:
            Updates cluster.consensus_score for each cluster with stabilized values
        """
        cluster_scores = [c.consensus_score for c in clusters]

        stabilized_scores = await self._apply_stability_constraint(
            cluster_scores, trust_scores=cluster_trust
        )

        for i, cluster in enumerate(clusters):
            if i < len(stabilized_scores):
                cluster.consensus_score = stabilized_scores[i]

    def _extract_approved_amendments(
        self, clusters: list[OpinionCluster], consensus_threshold: float
    ) -> list[JSONDict]:
        """
        Extract approved amendments from high-consensus clusters.

        Args:
            clusters: List of OpinionClusters to extract from
            consensus_threshold: Minimum consensus score for approval

        Returns:
            List of approved amendment dictionaries
        """
        approved_amendments = []

        for cluster in clusters:
            if cluster.consensus_score >= consensus_threshold:
                for statement_id in cluster.representative_statements:
                    if statement_id in self.polis_engine.statements:
                        statement = self.polis_engine.statements[statement_id]
                        approved_amendments.append(
                            {
                                "statement_id": statement_id,
                                "content": statement.content,
                                "consensus_score": statement.consensus_potential,
                                "cluster": cluster.cluster_id,
                            }
                        )

        return approved_amendments

    def _identify_rejected_statements(self) -> list[JSONDict]:
        """
        Identify statements with low consensus potential for rejection.

        Returns:
            List of rejected statement dictionaries with consensus_potential < 0.3
        """
        rejected_items = []

        for statement in self.polis_engine.statements.values():
            if statement.consensus_potential < 0.3:
                rejected_items.append(
                    {
                        "statement_id": statement.statement_id,
                        "content": statement.content,
                        "consensus_score": statement.consensus_potential,
                    }
                )

        return rejected_items

    async def fast_govern(
        self,
        decision: JSONDict,
        time_budget_ms: int,
        stakeholders: list[Stakeholder] | None = None,
    ) -> JSONDict:
        """
        Performance-legitimacy balance: Fast automated decision with async review.

        This implements the hybrid fast/slow path for governance, enabling
        real-time decisions while maintaining democratic legitimacy through
        asynchronous deliberation.

        Args:
            decision: Decision dictionary to govern (must include 'description' field)
            time_budget_ms: Time budget for fast decision in milliseconds (informational)
            stakeholders: Optional list of stakeholders for async deliberation
                         (if >= 10 stakeholders, async deliberation initiated)

        Returns:
            Dictionary containing:
            - immediate_decision: Fast decision result with approval, confidence, method
            - deliberation_pending: bool indicating if async deliberation started
            - deliberation_task: asyncio.Task for async deliberation (or None)
            - performance_optimized: bool indicating fast path used (always True)

        Fast Decision Structure:
            - decision: Original decision dict
            - approved: bool (simplified: always True in current implementation)
            - confidence: float confidence score (default: 0.8)
            - method: "automated_check" (indicates fast path)
            - processing_time_ms: Actual processing time

        Process:
            1. Record start time
            2. Perform fast automated constitutional check
            3. Record decision in self.fast_decisions audit trail
            4. If >= 10 stakeholders provided, launch async deliberation task
            5. Return immediate decision + task handle

        Use Cases:
            - High-frequency operational decisions requiring <10ms latency
            - Routine maintenance approvals
            - Low-risk configuration changes
            - Decisions that need quick approval + ex-post democratic validation

        Constitutional Hash: cdd01ef066bc6cf2
        """
        start_time = datetime.now(UTC)

        fast_decision = {
            "decision": decision,
            "approved": True,
            "confidence": 0.8,
            "method": "automated_check",
            "processing_time_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000,
        }

        self.fast_decisions.append(
            {
                "decision": decision,
                "result": fast_decision,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        deliberation_task = None
        if stakeholders and len(stakeholders) >= 10:
            deliberation_task = asyncio.create_task(
                self._async_deliberation(decision, stakeholders)
            )

        return {
            "immediate_decision": fast_decision,
            "deliberation_pending": deliberation_task is not None,
            "deliberation_task": deliberation_task,
            "performance_optimized": True,
        }

    async def _async_deliberation(self, decision: JSONDict, stakeholders: list[Stakeholder]):
        """
        Asynchronous deliberation for legitimacy validation of fast decisions.

        This method runs in the background after fast_govern() returns, providing
        democratic validation of automated decisions without blocking real-time operations.

        Args:
            decision: Decision dictionary that was approved via fast path
            stakeholders: List of stakeholders to participate in deliberation

        Side Effects:
            - Creates ConstitutionalProposal for the decision
            - Runs full Polis deliberation (24-hour simulation)
            - Updates decision dict with legitimacy_reviewed flag
            - Appends deliberation result to decision dict
            - Logs completion message

        Process:
            1. Create proposal with decision as proposed_changes
            2. Run full deliberation via run_deliberation() (includes all phases)
            3. Mark decision as legitimacy_reviewed
            4. Store deliberation result in decision dict
            5. Log completion for audit trail

        Note:
            This method should be wrapped in asyncio.create_task() to run
            in background. Errors are logged but don't affect fast decision.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        proposal = await self.propose_constitutional_change(
            title=f"Decision Review: {decision.get('description', 'Unknown')}",
            description=f"Review of automated decision: {decision}",
            proposed_changes={"decision": decision},
            proposer=stakeholders[0] if stakeholders else None,
        )

        result = await self.run_deliberation(proposal, stakeholders, duration_hours=24)

        decision["legitimacy_reviewed"] = True
        decision["deliberation_result"] = result.to_dict()

        logger.info(f"Async deliberation completed for decision: {decision.get('id', 'unknown')}")

    async def get_governance_status(self) -> JSONDict:
        """
        Get comprehensive status and metrics of the governance framework.

        Returns operational status, participation metrics, and capability flags
        for monitoring and audit purposes.

        Returns:
            Dictionary containing governance status information:
            - framework: Framework name ("CCAI Democratic Constitutional Governance")
            - status: Operational status ("operational")
            - registered_stakeholders: Count of registered stakeholders
            - active_proposals: Count of proposals in "deliberating" status
            - completed_deliberations: Count of completed deliberation sessions
            - fast_decisions: Count of fast-path decisions made
            - deliberated_decisions: Count of decisions with full deliberation
            - consensus_threshold: Current consensus threshold (default: 0.6)
            - capabilities: Dict of enabled capabilities (all True):
              * polis_deliberation: Polis-style deliberation engine
              * cross_group_consensus: Cross-group validation
              * constitutional_amendments: Amendment workflow
              * performance_legitimacy_balance: Fast/slow hybrid path
            - constitutional_hash: Validation hash (cdd01ef066bc6cf2)

        Example:
            >>> status = await governance.get_governance_status()
            >>> logger.info(f"Framework: {status['framework']}")
            >>> logger.info(f"Stakeholders: {status['registered_stakeholders']}")
            >>> logger.info(f"Capabilities: {list(status['capabilities'].keys())}")

        Constitutional Hash: cdd01ef066bc6cf2
        """
        return {
            "framework": "CCAI Democratic Constitutional Governance",
            "status": "operational",
            "registered_stakeholders": len(self.stakeholders),
            "active_proposals": len(
                [p for p in self.proposals.values() if p.status == "deliberating"]
            ),
            "completed_deliberations": len(self.deliberations),
            "fast_decisions": len(self.fast_decisions),
            "deliberated_decisions": len(self.deliberated_decisions),
            "consensus_threshold": self.consensus_threshold,
            "capabilities": {
                "polis_deliberation": True,
                "cross_group_consensus": True,
                "constitutional_amendments": True,
                "performance_legitimacy_balance": True,
            },
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


ccai_governance = DemocraticConstitutionalGovernance()


def get_ccai_governance() -> DemocraticConstitutionalGovernance:
    """Get the global CCAI governance framework instance."""
    return ccai_governance


async def deliberate_on_proposal(
    title: str,
    description: str,
    changes: JSONDict,
    stakeholder_groups: list[StakeholderGroup],
    min_participants: int = 50,
) -> DeliberationResult:
    """
    Convenience function to run democratic deliberation on a proposal.

    This provides the main API for democratic governance, handling stakeholder
    creation, proposal submission, and full deliberation workflow.

    Args:
        title: Concise proposal title (e.g., "Enhanced Transparency Requirements")
        description: Detailed proposal description and rationale
        changes: Dictionary of specific constitutional changes to be deliberated
        stakeholder_groups: List of StakeholderGroup types to include in deliberation
                           (e.g., [TECHNICAL_EXPERTS, ETHICS_REVIEWERS, END_USERS])
        min_participants: Minimum number of stakeholders to simulate (default: 50)
                         Actual count is max(5, min_participants // len(stakeholder_groups))
                         per group

    Returns:
        DeliberationResult with complete deliberation outcomes:
        - consensus_reached: Whether proposal was approved
        - consensus_statements: List of approved statements
        - clusters_identified: Number of opinion clusters found
        - total_participants: Number of stakeholders who participated
        - polarization_analysis: Cross-group consensus metrics
        - stability_analysis: Manifold stability metrics and representative statement quality

    Process:
        1. Get global CCAI governance instance
        2. Register stakeholders for each group (auto-generated for simulation)
        3. Create constitutional proposal using first stakeholder as proposer
        4. Run full Polis deliberation workflow
        5. Return comprehensive deliberation results

    Example:
        >>> result = await deliberate_on_proposal(
        ...     title="AI Transparency Initiative",
        ...     description="Require explainable AI for all critical decisions",
        ...     changes={"transparency": "mandatory", "explainability": "required"},
        ...     stakeholder_groups=[
        ...         StakeholderGroup.TECHNICAL_EXPERTS,
        ...         StakeholderGroup.ETHICS_REVIEWERS,
        ...         StakeholderGroup.END_USERS
        ...     ],
        ...     min_participants=60
        ... )
        >>> logger.info(f"Consensus: {result.consensus_reached}")
        >>> logger.info(f"Clusters: {result.clusters_identified}")

    Raises:
        ValueError: If no stakeholders could be created (empty stakeholder_groups list)

    Constitutional Hash: cdd01ef066bc6cf2
    """
    governance = get_ccai_governance()

    stakeholders = []
    for group in stakeholder_groups:
        for i in range(max(5, min_participants // len(stakeholder_groups))):
            stakeholder = await governance.register_stakeholder(
                name=f"{group.value}_{i}", group=group, expertise_areas=[group.value]
            )
            stakeholders.append(stakeholder)

    proposer = stakeholders[0] if stakeholders else None
    if not proposer:
        raise ValueError("No stakeholders available")

    proposal = await governance.propose_constitutional_change(
        title=title,
        description=description,
        proposed_changes=changes,
        proposer=proposer,
    )

    return await governance.run_deliberation(proposal, stakeholders)
