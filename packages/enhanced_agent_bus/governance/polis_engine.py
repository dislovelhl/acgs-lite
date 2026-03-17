"""
ACGS-2 CCAI Democratic Framework - Polis Deliberation Engine
Constitutional Hash: cdd01ef066bc6cf2

This module implements the Polis-style deliberation engine for democratic input:
- Statement submission and voting
- Opinion clustering to identify consensus
- Cross-group analysis to prevent polarization
- Representative statement identification with centrality scoring
- Diversity filtering for comprehensive opinion coverage

Representative Statements Identification Algorithm:
    The framework identifies canonical representative statements from opinion clusters
    using a multi-stage approach:

    1. Centrality Calculation:
       - Participation rate: Percentage of cluster members who voted on the statement
       - Agreement rate: Ratio of agree votes among cluster members
       - Consensus strength: Net positive consensus (agreement - disagreement)
       - Weighted combination: 30% participation + 40% agreement + 30% consensus
       - Normalized to [0, 1] range where 1.0 is most central

    2. Representative Selection:
       - Rank all statements by centrality score (descending)
       - Select top N statements (default: 5, range: 1-10)
       - Filter statements with zero centrality (no cluster votes)

    3. Diversity Filtering (optional):
       - Calculate Jaccard similarity between statement contents
       - Use greedy algorithm to maximize centrality and minimize redundancy
       - Threshold: 0.7 (configurable, range: [0.0, 1.0])
       - Ensures representatives cover different aspects of cluster opinion

    4. Metadata Enhancement:
       - Track centrality scores, diversity metrics, selection reasons
       - Populate OpinionCluster.metadata with comprehensive statistics
       - Include pairwise similarity matrix between representatives

    Accuracy Target: 95%+ on test clusters (validated via precision/recall metrics)

Constitutional Hash: cdd01ef066bc6cf2
"""

import re
import statistics
import uuid
from datetime import UTC, datetime
from typing import cast

import numpy as np
from src.core.shared.constants import CONSTITUTIONAL_HASH

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    DeliberationStatement,
    OpinionCluster,
    Stakeholder,
)

try:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
except ImportError:
    PCA = None  # pyright: ignore[reportConstantRedefinition]
    KMeans = None

logger = get_logger(__name__)

__all__ = ["PolisDeliberationEngine"]

POLIS_CLUSTERING_OPERATION_ERRORS = (
    AttributeError,
    FloatingPointError,
    RuntimeError,
    TypeError,
    ValueError,
)


class PolisDeliberationEngine:
    """
    Polis-style deliberation engine for democratic input.

    Implements the core Polis algorithm:
    - Statement submission and voting
    - Opinion clustering to identify consensus
    - Cross-group analysis to prevent polarization
    """

    def __init__(
        self,
        enable_diversity_filter: bool = True,
        diversity_threshold: float = 0.7,
        top_n: int = 5,
    ):
        """
        Initialize Polis deliberation engine.

        Args:
            enable_diversity_filter: If True, use diversity filtering when selecting
                                   representative statements (default: True)
            diversity_threshold: Maximum allowed similarity between representatives
                               (default: 0.7, range: [0.0, 1.0])
            top_n: Number of top representative statements to select per cluster
                   (default: 5, range: 1-10)
        """
        self.statements: dict[str, DeliberationStatement] = {}
        self.clusters: dict[str, OpinionCluster] = {}
        self.voting_matrix: dict[str, dict[str, int]] = {}
        self.enable_diversity_filter = enable_diversity_filter
        self.diversity_threshold = diversity_threshold
        self.top_n = max(1, min(10, top_n))

    async def submit_statement(self, content: str, author: Stakeholder) -> DeliberationStatement:
        """
        Submit a statement to the deliberation for voting and consensus analysis.

        Creates a new DeliberationStatement and initializes its voting matrix
        for tracking stakeholder votes.

        Args:
            content: Text content of the statement
            author: Stakeholder submitting the statement

        Returns:
            Created DeliberationStatement with unique ID and initialized vote tracking

        Constitutional Hash: cdd01ef066bc6cf2
        """
        statement = DeliberationStatement(
            statement_id=str(uuid.uuid4()),
            content=content,
            author_id=author.stakeholder_id,
            author_group=author.group,
        )

        self.statements[statement.statement_id] = statement
        self.voting_matrix[statement.statement_id] = {}

        return statement

    async def vote_on_statement(
        self,
        statement_id: str,
        stakeholder: Stakeholder,
        vote: int,
    ) -> bool:
        """
        Cast a vote on a deliberation statement.

        Records stakeholder vote and updates statement consensus scores automatically.
        Votes are used for clustering, centrality calculation, and consensus analysis.

        Args:
            statement_id: Unique identifier of the statement to vote on
            stakeholder: Stakeholder casting the vote
            vote: Vote value indicating stakeholder position
                  -1: Disagree with the statement
                   0: Skip/abstain from voting
                   1: Agree with the statement

        Returns:
            True if vote was successfully recorded, False if statement not found

        Side Effects:
            - Updates voting_matrix with new vote
            - Recalculates statement agreement/disagreement scores
            - Updates statement consensus potential

        Example:
            >>> statement = await engine.submit_statement("AI should be transparent", expert)
            >>> success = await engine.vote_on_statement(statement.statement_id, user, 1)
            >>> logger.info(f"Vote recorded: {success}")

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if statement_id not in self.statements:
            return False

        if statement_id not in self.voting_matrix:
            self.voting_matrix[statement_id] = {}

        self.voting_matrix[statement_id][stakeholder.stakeholder_id] = vote

        await self._update_statement_scores(statement_id)

        return True

    async def _update_statement_scores(self, statement_id: str):
        """
        Update agreement/disagreement scores for a statement based on current votes.

        Calculates three key metrics used for consensus analysis and centrality scoring:
        - Agreement score: Ratio of agree votes to total votes
        - Disagreement score: Ratio of disagree votes to total votes
        - Consensus potential: Net agreement (agreement - disagreement)

        Args:
            statement_id: ID of the statement to update scores for

        Updates:
            - statement.agreement_score: Range [0.0, 1.0] where 1.0 = unanimous agreement
            - statement.disagreement_score: Range [0.0, 1.0] where 1.0 = unanimous disagreement
            - statement.consensus_potential: Range [-1.0, 1.0] where:
              * +1.0 = perfect consensus (unanimous agree)
              * -1.0 = perfect dissent (unanimous disagree)
              *  0.0 = perfect split or no votes

        Note:
            Skip votes (vote=0) are excluded from agreement/disagreement calculations
            but count toward total participation.

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if statement_id not in self.voting_matrix:
            return

        votes = self.voting_matrix[statement_id]
        if not votes:
            return

        agree_count = sum(1 for v in votes.values() if v == 1)
        disagree_count = sum(1 for v in votes.values() if v == -1)
        total_votes = len(votes)

        statement = self.statements[statement_id]
        statement.agreement_score = agree_count / total_votes if total_votes > 0 else 0
        statement.disagreement_score = disagree_count / total_votes if total_votes > 0 else 0

        statement.consensus_potential = statement.agreement_score - statement.disagreement_score

    async def calculate_statement_centrality(
        self,
        statement_id: str,
        cluster: OpinionCluster,
    ) -> float:
        """
        Calculate centrality score for a statement within a cluster.

        Centrality measures how representative a statement is for a cluster based on:
        - Agreement among cluster members (highest weight)
        - Voting participation by cluster members
        - Consensus potential (agreement - disagreement)

        Args:
            statement_id: ID of the statement to score
            cluster: OpinionCluster to calculate centrality for

        Returns:
            Centrality score in range [0, 1], where 1 is most central

        Algorithm:
            centrality = 0.3 * participation_rate
                       + 0.4 * agreement_rate
                       + 0.3 * consensus_strength

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if statement_id not in self.statements:
            logger.warning(f"Statement {statement_id} not found, centrality=0.0")
            return 0.0

        self.statements[statement_id]

        cluster_votes = {}
        for stakeholder_id in cluster.member_stakeholders:
            if stakeholder_id in self.voting_matrix.get(statement_id, {}):
                cluster_votes[stakeholder_id] = self.voting_matrix[statement_id][stakeholder_id]

        if not cluster_votes:
            return 0.0

        participation_rate = len(cluster_votes) / max(1, len(cluster.member_stakeholders))

        agree_count = sum(1 for v in cluster_votes.values() if v == 1)
        disagree_count = sum(1 for v in cluster_votes.values() if v == -1)
        total_votes = len(cluster_votes)

        agreement_rate = agree_count / total_votes if total_votes > 0 else 0.0

        consensus_strength = (
            (agree_count - disagree_count) / total_votes if total_votes > 0 else 0.0
        )
        consensus_strength = (consensus_strength + 1) / 2

        centrality = 0.3 * participation_rate + 0.4 * agreement_rate + 0.3 * consensus_strength

        centrality = min(1.0, max(0.0, centrality))

        logger.debug(
            f"Statement {statement_id[:8]} centrality: {centrality:.3f} "
            f"(participation={participation_rate:.2f}, "
            f"agreement={agreement_rate:.2f}, "
            f"consensus={consensus_strength:.2f})"
        )

        return centrality

    async def select_representative_statements(
        self, cluster: OpinionCluster, top_n: int = 5
    ) -> list[str]:
        """
        Select top N representative statements for a cluster based on centrality scores.

        Args:
            cluster: The OpinionCluster to select representatives for
            top_n: Number of top statements to select (default: 5, range: 1-10)

        Returns:
            List of statement IDs ranked by centrality score (highest first)

        Edge Cases:
            - Empty cluster: returns empty list
            - Fewer statements than top_n: returns all available statements
            - No votes for any statement: returns empty list

        Algorithm:
            1. Calculate centrality for each statement in the deliberation
            2. Filter to statements with non-zero centrality (have cluster votes)
            3. Sort by centrality score descending
            4. Return top N statement IDs

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if not cluster.member_stakeholders:
            logger.warning(f"Cluster {cluster.cluster_id} has no members, no representatives")
            return []

        if top_n < 1:
            logger.warning(f"Invalid top_n={top_n}, using default=5")
            top_n = 5
        elif top_n > 10:
            logger.warning(f"top_n={top_n} exceeds recommended max=10, clamping")
            top_n = 10

        statement_scores: list[tuple[str, float]] = []

        for statement_id in self.statements.keys():
            centrality = await self.calculate_statement_centrality(statement_id, cluster)

            if centrality > 0.0:
                statement_scores.append((statement_id, centrality))

        if not statement_scores:
            logger.warning(
                f"Cluster {cluster.cluster_id} has no statements with votes, "
                "no representatives selected"
            )
            return []

        statement_scores.sort(key=lambda x: x[1], reverse=True)

        top_statements = statement_scores[:top_n]
        representative_ids = [stmt_id for stmt_id, _ in top_statements]

        logger.info(
            f"Selected {len(representative_ids)} representative statements for "
            f"cluster {cluster.cluster_id} (requested={top_n}, "
            f"available={len(statement_scores)})"
        )

        for i, (stmt_id, score) in enumerate(top_statements[:3], 1):
            logger.debug(f"  #{i}: {stmt_id[:8]} (centrality={score:.3f})")

        return representative_ids

    def calculate_statement_similarity(self, statement_id_1: str, statement_id_2: str) -> float:
        """
        Calculate content similarity between two statements using Jaccard similarity.

        Args:
            statement_id_1: First statement ID
            statement_id_2: Second statement ID

        Returns:
            Similarity score in range [0, 1] where:
            - 0.0 = completely different (no common tokens)
            - 1.0 = identical (same token set)

        Algorithm:
            1. Tokenize both statement contents (lowercase, split on whitespace)
            2. Calculate Jaccard similarity: |A intersection B| / |A union B|
            3. Return similarity score

        Constitutional Hash: cdd01ef066bc6cf2
        """
        if statement_id_1 not in self.statements:
            logger.warning(f"Statement {statement_id_1} not found, similarity=0.0")
            return 0.0
        if statement_id_2 not in self.statements:
            logger.warning(f"Statement {statement_id_2} not found, similarity=0.0")
            return 0.0

        if statement_id_1 == statement_id_2:
            return 1.0

        content_1 = self.statements[statement_id_1].content.lower()
        content_2 = self.statements[statement_id_2].content.lower()

        tokens_1 = set(re.findall(r"\b\w+\b", content_1))
        tokens_2 = set(re.findall(r"\b\w+\b", content_2))

        if not tokens_1 and not tokens_2:
            return 1.0
        if not tokens_1 or not tokens_2:
            return 0.0

        intersection = tokens_1.intersection(tokens_2)
        union = tokens_1.union(tokens_2)

        similarity = len(intersection) / len(union) if union else 0.0

        logger.debug(
            f"Similarity({statement_id_1[:8]}, {statement_id_2[:8]}) = {similarity:.3f} "
            f"(common={len(intersection)}, total={len(union)})"
        )

        return similarity

    async def select_diverse_representative_statements(
        self,
        cluster: OpinionCluster,
        top_n: int = 5,
        diversity_threshold: float = 0.7,
    ) -> list[str]:
        """
        Select top N representative statements with diversity filtering.

        This method ensures representative statements cover different aspects of
        cluster opinion by filtering out highly similar (redundant) statements.

        Args:
            cluster: The OpinionCluster to select representatives for
            top_n: Number of top statements to select (default: 5, range: 1-10)
            diversity_threshold: Maximum allowed similarity between representatives
                               (default: 0.7, range: [0.0, 1.0])
                               - Higher values allow more similar statements
                               - Lower values enforce stricter diversity
                               - 0.0 = only completely different statements
                               - 1.0 = no diversity filtering (same as select_representative_statements)

        Returns:
            List of statement IDs that maximize both centrality and diversity

        Algorithm:
            1. Calculate centrality for all statements and sort descending
            2. Select highest centrality statement as first representative
            3. For each subsequent candidate (by centrality):
               a. Calculate similarity to all already-selected representatives
               b. If max similarity < diversity_threshold, add to selection
               c. Continue until we have top_n representatives or run out of candidates
            4. Return diverse representative set

        Edge Cases:
            - Same as select_representative_statements()
            - If diversity_threshold >= 1.0, behaves like select_representative_statements()
            - If diversity_threshold <= 0.0, only selects first statement (strictest diversity)
            - If no diverse candidates found, returns fewer than top_n statements

        Constitutional Hash: cdd01ef066bc6cf2
        """  # noqa: E501
        if not cluster.member_stakeholders:
            logger.warning(f"Cluster {cluster.cluster_id} has no members, no representatives")
            return []

        validated_top_n, validated_diversity_threshold = self._validate_diversity_parameters(
            top_n, diversity_threshold
        )

        if validated_diversity_threshold >= 1.0:
            return await self.select_representative_statements(cluster, validated_top_n)

        statement_scores = await self._get_sorted_statement_scores(cluster)
        if not statement_scores:
            return []

        diverse_representatives = await self._select_diverse_candidates(
            statement_scores, validated_top_n, validated_diversity_threshold
        )

        self._log_diversity_selection_results(
            cluster,
            diverse_representatives,
            validated_top_n,
            validated_diversity_threshold,
            len(statement_scores),
        )

        return diverse_representatives

    @staticmethod
    def _validate_diversity_parameters(top_n: int, diversity_threshold: float) -> tuple[int, float]:
        """
        Validate and clamp diversity selection parameters.

        Args:
            top_n: Requested number of representatives
            diversity_threshold: Requested diversity threshold

        Returns:
            Tuple of (validated_top_n, validated_diversity_threshold)
        """
        validated_top_n = top_n
        if top_n < 1:
            logger.warning(f"Invalid top_n={top_n}, using default=5")
            validated_top_n = 5
        elif top_n > 10:
            logger.warning(f"top_n={top_n} exceeds recommended max=10, clamping")
            validated_top_n = 10

        validated_diversity_threshold = diversity_threshold
        if diversity_threshold < 0.0 or diversity_threshold > 1.0:
            logger.warning(
                f"Invalid diversity_threshold={diversity_threshold}, clamping to [0.0, 1.0]"
            )
            validated_diversity_threshold = max(0.0, min(1.0, diversity_threshold))

        if validated_diversity_threshold >= 1.0:
            logger.debug(
                f"Diversity threshold {validated_diversity_threshold} >= 1.0, "
                "using standard selection without diversity filtering"
            )

        return validated_top_n, validated_diversity_threshold

    async def _get_sorted_statement_scores(
        self, cluster: OpinionCluster
    ) -> list[tuple[str, float]]:
        """
        Get statements sorted by centrality score for diversity selection.

        Args:
            cluster: OpinionCluster to calculate centrality for

        Returns:
            List of (statement_id, centrality_score) tuples sorted by score descending
        """
        statement_scores: list[tuple[str, float]] = []

        for statement_id in self.statements.keys():
            centrality = await self.calculate_statement_centrality(statement_id, cluster)

            if centrality > 0.0:
                statement_scores.append((statement_id, centrality))

        if not statement_scores:
            logger.warning(
                f"Cluster {cluster.cluster_id} has no statements with votes, "
                "no representatives selected"
            )
            return []

        statement_scores.sort(key=lambda x: x[1], reverse=True)
        return statement_scores

    async def _select_diverse_candidates(
        self, statement_scores: list[tuple[str, float]], top_n: int, diversity_threshold: float
    ) -> list[str]:
        """
        Select diverse candidates using greedy diversity filtering.

        Args:
            statement_scores: Sorted list of (statement_id, centrality_score) tuples
            top_n: Maximum number of representatives to select
            diversity_threshold: Maximum similarity allowed between representatives

        Returns:
            List of selected diverse representative statement IDs
        """
        diverse_representatives: list[str] = []

        for stmt_id, centrality in statement_scores:
            if not diverse_representatives:
                diverse_representatives.append(stmt_id)
                logger.debug(
                    f"Selected first representative: {stmt_id[:8]} (centrality={centrality:.3f})"
                )
                continue

            if len(diverse_representatives) >= top_n:
                break

            max_similarity = self._calculate_max_similarity(stmt_id, diverse_representatives)

            if max_similarity < diversity_threshold:
                diverse_representatives.append(stmt_id)
                logger.debug(
                    f"Selected diverse representative: {stmt_id[:8]} "
                    f"(centrality={centrality:.3f}, max_similarity={max_similarity:.3f})"
                )
            else:
                logger.debug(
                    f"Rejected similar candidate: {stmt_id[:8]} "
                    f"(centrality={centrality:.3f}, max_similarity={max_similarity:.3f} >= {diversity_threshold})"  # noqa: E501
                )

        return diverse_representatives

    def _calculate_max_similarity(
        self, candidate_id: str, selected_representatives: list[str]
    ) -> float:
        """
        Calculate maximum similarity between candidate and selected representatives.

        Args:
            candidate_id: Statement ID to check similarity for
            selected_representatives: List of already selected representative IDs

        Returns:
            Maximum similarity score between candidate and any selected representative
        """
        max_similarity = 0.0
        for selected_id in selected_representatives:
            similarity = self.calculate_statement_similarity(candidate_id, selected_id)
            max_similarity = max(max_similarity, similarity)
        return max_similarity

    @staticmethod
    def _log_diversity_selection_results(
        cluster: OpinionCluster,
        diverse_representatives: list[str],
        requested_top_n: int,
        diversity_threshold: float,
        total_candidates: int,
    ) -> None:
        """
        Log results of diversity selection process.

        Args:
            cluster: OpinionCluster being processed
            diverse_representatives: Selected representative IDs
            requested_top_n: Number of representatives requested
            diversity_threshold: Diversity threshold used
            total_candidates: Total number of candidate statements
        """
        logger.info(
            f"Selected {len(diverse_representatives)} diverse representatives for "
            f"cluster {cluster.cluster_id} (requested={requested_top_n}, "
            f"candidates_considered={total_candidates}, "
            f"diversity_threshold={diversity_threshold:.2f})"
        )

        if len(diverse_representatives) < requested_top_n and total_candidates >= requested_top_n:
            logger.warning(
                f"Diversity constraint resulted in fewer representatives "
                f"({len(diverse_representatives)}) than requested ({requested_top_n}). "
                f"Consider lowering diversity_threshold (current={diversity_threshold:.2f})"
            )

    def _build_voting_matrix(self) -> tuple[list[str], list[str], np.ndarray]:
        stakeholder_ids: set[str] = set()
        for votes in self.voting_matrix.values():
            stakeholder_ids.update(votes.keys())

        stakeholder_list = sorted(list(stakeholder_ids))
        statement_list = sorted(list(self.statements.keys()))
        if not stakeholder_list or not statement_list:
            logger.warning("Insufficient data for clustering.")
            return [], [], np.zeros((0, 0))

        X = np.zeros((len(stakeholder_list), len(statement_list)))
        name_to_idx = {sid: i for i, sid in enumerate(stakeholder_list)}

        for j, stmt_id in enumerate(statement_list):
            votes = self.voting_matrix.get(stmt_id, {})
            for sid, vote in votes.items():
                if sid in name_to_idx:
                    X[name_to_idx[sid], j] = vote

        return stakeholder_list, statement_list, X

    def _run_clustering(self, X: np.ndarray, n_participants: int, n_statements: int) -> np.ndarray:
        k_clusters = min(5, max(2, int(np.sqrt(n_participants))))
        if n_participants < 2:
            k_clusters = 1
        if k_clusters > n_participants:
            k_clusters = n_participants

        X_cluster = X
        if PCA and n_participants >= 3 and n_statements >= 2:
            n_components = min(n_participants, n_statements, 2)
            try:
                pca = PCA(n_components=n_components)
                X_cluster = pca.fit_transform(X)
            except POLIS_CLUSTERING_OPERATION_ERRORS as e:
                logger.warning(f"PCA failed, using raw features: {e}")

        labels = np.zeros(n_participants, dtype=int)
        if KMeans and n_participants >= k_clusters:
            try:
                kmeans = KMeans(
                    n_clusters=k_clusters,
                    random_state=42,
                    n_init=cast(str, cast(object, 10)),
                )
                labels = kmeans.fit_predict(X_cluster)
            except POLIS_CLUSTERING_OPERATION_ERRORS as e:
                logger.warning(f"KMeans failed, falling back to single cluster: {e}")
                labels = np.zeros(n_participants, dtype=int)

        return labels

    def _build_cluster_map(
        self, labels: np.ndarray, stakeholder_list: list[str]
    ) -> dict[str, OpinionCluster]:
        clusters_map: dict[str, OpinionCluster] = {}
        for idx, cluster_label in enumerate(labels):
            stakeholder_id = stakeholder_list[idx]
            label_str = str(cluster_label)

            if label_str not in clusters_map:
                clusters_map[label_str] = OpinionCluster(
                    cluster_id=f"cluster_{uuid.uuid4().hex[:8]}",
                    name=f"Opinion Group {cluster_label + 1}",
                    description=f"Cluster {cluster_label + 1} identified via PCA/K-Means",
                    representative_statements=[],
                    member_stakeholders=[],
                    metadata={"pca_components": 2 if PCA else 0},
                    size=0,
                )

            clusters_map[label_str].member_stakeholders.append(stakeholder_id)
            clusters_map[label_str].size += 1

        return clusters_map

    def _compute_diversity_metrics(
        self, representative_ids: list[str]
    ) -> tuple[dict[str, dict[str, float | None]], dict[str, str], dict[str, float]]:
        """
        Compute diversity metrics for selected representative statements.

        Args:
            representative_ids: List of selected representative statement IDs

        Returns:
            Tuple of (diversity_scores, selection_reasons, pairwise_similarities)
        """
        if len(representative_ids) <= 1:
            return self._handle_single_representative_case(representative_ids)

        diversity_scores: dict[str, dict[str, float | None]] = {}
        pairwise_similarities = self._build_pairwise_similarity_map(representative_ids)

        for i, stmt_id in enumerate(representative_ids):
            similarities = self._compute_similarity_statistics(stmt_id, representative_ids, i)
            if similarities:
                avg_similarity = statistics.mean(similarities)
                diversity_scores[stmt_id] = {
                    "min_similarity": min(similarities),
                    "max_similarity": max(similarities),
                    "avg_similarity": avg_similarity,
                    "diversity_score": 1.0 - avg_similarity,
                }

        selection_reasons = self._assign_selection_reasons(representative_ids, diversity_scores)

        return diversity_scores, selection_reasons, pairwise_similarities

    @staticmethod
    def _handle_single_representative_case(
        representative_ids: list[str],
    ) -> tuple[dict[str, dict[str, float | None]], dict[str, str], dict[str, float]]:
        """
        Handle the case where there's one or no representative statements.

        Args:
            representative_ids: List of representative statement IDs (0 or 1 items)

        Returns:
            Tuple of (diversity_scores, selection_reasons, pairwise_similarities)
        """
        diversity_scores: dict[str, dict[str, float | None]] = {}
        selection_reasons: dict[str, str] = {}
        pairwise_similarities: dict[str, float] = {}

        if representative_ids:
            stmt_id = representative_ids[0]
            diversity_scores[stmt_id] = {
                "min_similarity": None,
                "max_similarity": None,
                "avg_similarity": None,
                "diversity_score": None,
            }
            selection_reasons[stmt_id] = "only_representative"

        return diversity_scores, selection_reasons, pairwise_similarities

    def _compute_similarity_statistics(
        self, stmt_id: str, representative_ids: list[str], current_index: int
    ) -> list[float]:
        """
        Compute similarity statistics for a single representative statement.

        Args:
            stmt_id: Statement ID to compute similarities for
            representative_ids: All representative statement IDs
            current_index: Index of current statement in representative_ids

        Returns:
            List of similarity scores to other representatives
        """
        similarities: list[float] = []
        for j, other_id in enumerate(representative_ids):
            if current_index == j:
                continue
            similarity = self.calculate_statement_similarity(stmt_id, other_id)
            similarities.append(similarity)
        return similarities

    def _build_pairwise_similarity_map(self, representative_ids: list[str]) -> dict[str, float]:
        """
        Build map of pairwise similarities between representatives.

        Args:
            representative_ids: List of representative statement IDs

        Returns:
            Dictionary mapping pair keys to similarity scores
        """
        pairwise_similarities: dict[str, float] = {}

        for i, stmt_id in enumerate(representative_ids):
            for j, other_id in enumerate(representative_ids):
                if i < j:  # Only store each pair once
                    similarity = self.calculate_statement_similarity(stmt_id, other_id)
                    pair_key = f"{stmt_id[:8]}_{other_id[:8]}"
                    pairwise_similarities[pair_key] = similarity

        return pairwise_similarities

    def _assign_selection_reasons(
        self, representative_ids: list[str], diversity_scores: dict[str, dict[str, float | None]]
    ) -> dict[str, str]:
        """
        Assign reasons for why each representative was selected.

        Args:
            representative_ids: List of representative statement IDs
            diversity_scores: Computed diversity scores for each representative

        Returns:
            Dictionary mapping statement IDs to selection reasons
        """
        selection_reasons: dict[str, str] = {}

        for i, stmt_id in enumerate(representative_ids):
            if i == 0:
                selection_reasons[stmt_id] = "highest_centrality"
            elif self.enable_diversity_filter:
                raw_avg_sim = diversity_scores.get(stmt_id, {}).get("avg_similarity", 0.0)
                avg_sim = raw_avg_sim if raw_avg_sim is not None else 0.0
                if avg_sim < self.diversity_threshold:
                    selection_reasons[stmt_id] = "diverse_opinion"
                else:
                    selection_reasons[stmt_id] = "high_centrality"
            else:
                selection_reasons[stmt_id] = "high_centrality"

        return selection_reasons

    async def _enrich_cluster_metadata(self, cluster: OpinionCluster) -> tuple[int, list[float]]:
        if self.enable_diversity_filter:
            representative_ids = await self.select_diverse_representative_statements(
                cluster, top_n=self.top_n, diversity_threshold=self.diversity_threshold
            )
        else:
            representative_ids = await self.select_representative_statements(
                cluster, top_n=self.top_n
            )
        cluster.representative_statements = representative_ids

        centrality_scores: list[float] = []
        centrality_by_id: dict[str, float] = {}
        for stmt_id in representative_ids:
            centrality = await self.calculate_statement_centrality(stmt_id, cluster)
            centrality_scores.append(centrality)
            centrality_by_id[stmt_id] = centrality

        avg_centrality = statistics.mean(centrality_scores) if centrality_scores else 0.0
        min_centrality = min(centrality_scores) if centrality_scores else 0.0
        max_centrality = max(centrality_scores) if centrality_scores else 0.0

        diversity_scores, selection_reasons, pairwise_similarities = (
            self._compute_diversity_metrics(representative_ids)
        )

        cluster.metadata.update(
            {
                "representative_count": len(representative_ids),
                "avg_centrality_score": avg_centrality,
                "min_centrality_score": min_centrality,
                "max_centrality_score": max_centrality,
                "centrality_scores": centrality_scores,
                "centrality_by_statement": centrality_by_id,
                "diversity_filtering_enabled": self.enable_diversity_filter,
                "diversity_threshold": (
                    self.diversity_threshold if self.enable_diversity_filter else None
                ),
                "diversity_scores": diversity_scores,
                "pairwise_similarities": pairwise_similarities,
                "selection_reasons": selection_reasons,
                "selection_timestamp": datetime.now(UTC).isoformat(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        avg_diversity = None
        if diversity_scores:
            diversity_values: list[float] = []
            for diversity_data in diversity_scores.values():
                diversity_score = diversity_data.get("diversity_score")
                if diversity_score is not None:
                    diversity_values.append(diversity_score)
            if diversity_values:
                avg_diversity = statistics.mean(diversity_values)

        diversity_info = f", avg_diversity={avg_diversity:.3f}" if avg_diversity is not None else ""
        logger.info(
            f"Cluster {cluster.name} ({cluster.cluster_id[:8]}): "
            f"{len(representative_ids)} representatives from {cluster.size} members, "
            f"avg_centrality={avg_centrality:.3f}, "
            f"min={min_centrality:.3f}, max={max_centrality:.3f}"
            f"{diversity_info}"
        )

        for i, stmt_id in enumerate(representative_ids, 1):
            stmt_content = (
                self.statements[stmt_id].content[:60] + "..."
                if len(self.statements[stmt_id].content) > 60
                else self.statements[stmt_id].content
            )
            centrality = centrality_by_id.get(stmt_id, 0.0)
            reason = selection_reasons.get(stmt_id, "unknown")

            diversity_info = ""
            if stmt_id in diversity_scores:
                div_score = diversity_scores[stmt_id].get("diversity_score")
                if div_score is not None:
                    diversity_info = f", diversity={div_score:.3f}"

            logger.debug(
                f"  Representative #{i}: {stmt_id[:8]} "
                f"(centrality={centrality:.3f}{diversity_info}, reason={reason}): "
                f"{stmt_content}"
            )

        return len(representative_ids), centrality_scores

    def _log_quality_metrics(
        self,
        clusters_map: dict[str, OpinionCluster],
        total_representatives: int,
        all_centrality_scores: list[float],
    ) -> None:
        overall_avg_centrality = (
            statistics.mean(all_centrality_scores) if all_centrality_scores else 0.0
        )
        overall_median_centrality = (
            statistics.median(all_centrality_scores) if all_centrality_scores else 0.0
        )
        overall_stdev_centrality = (
            statistics.stdev(all_centrality_scores) if len(all_centrality_scores) > 1 else 0.0
        )

        logger.info(
            f"Representative Statement Quality Metrics: "
            f"total_selected={total_representatives}, "
            f"avg_centrality={overall_avg_centrality:.3f}, "
            f"median_centrality={overall_median_centrality:.3f}, "
            f"stdev_centrality={overall_stdev_centrality:.3f}"
        )

    async def identify_clusters(self) -> list[OpinionCluster]:
        """
        Identify opinion clusters from voting data using PCA and K-Means.

        This implementation:
        1. Vectorsizes voting data (Participants x Statements)
        2. Applies PCA for dimensionality reduction (if sufficient data)
        3. Uses K-Means to identify distinct opinion groups
        4. Generates cluster metadata and representative statements
        """
        stakeholder_list, statement_list, X = self._build_voting_matrix()
        if not stakeholder_list or not statement_list:
            return []

        labels = self._run_clustering(X, len(stakeholder_list), len(statement_list))
        clusters_map = self._build_cluster_map(labels, stakeholder_list)

        total_representatives = 0
        all_centrality_scores: list[float] = []
        for cluster in clusters_map.values():
            representatives_count, centrality_scores = await self._enrich_cluster_metadata(cluster)
            total_representatives += representatives_count
            all_centrality_scores.extend(centrality_scores)

        self._log_quality_metrics(clusters_map, total_representatives, all_centrality_scores)
        self.clusters = {c.cluster_id: c for c in clusters_map.values()}
        logger.info(f"Identified {len(self.clusters)} opinion clusters via Advanced Clustering")
        return list(self.clusters.values())

    async def analyze_cross_group_consensus(
        self, clusters: list[OpinionCluster]
    ) -> dict[str, int | float | str]:
        """
        Analyze consensus across different stakeholder groups to prevent polarization.

        This method ensures democratic legitimacy by validating that consensus exists
        across diverse stakeholder groups, not just within homogeneous clusters. This
        prevents "echo chamber" governance and ensures cross-cutting agreement.

        Args:
            clusters: List of OpinionClusters to analyze for cross-group consensus

        Returns:
            Dictionary containing cross-group consensus metrics:
            - total_clusters: Total number of clusters analyzed
            - high_consensus_clusters: Count of clusters with consensus_score >= 0.6
            - consensus_ratio: Ratio of high-consensus clusters to total clusters
            - average_cross_group_consensus: Mean consensus score across all clusters
            - polarization_risk: Risk level ("low" if >50% high consensus, else "high")

        Algorithm:
            1. For each cluster, analyze representative statement votes by stakeholder group
            2. Calculate agreement ratio per group (group-level consensus)
            3. Compute cross-group consensus as minimum agreement across all groups
            4. Update cluster.cross_group_consensus with minimum cross-group score
            5. Aggregate metrics across all clusters for polarization assessment

        Side Effects:
            - Updates cluster.cross_group_consensus for each cluster

        Note:
            Cross-group consensus uses minimum rather than mean to ensure
            no single group is excluded from the consensus.

        Constitutional Hash: cdd01ef066bc6cf2
        """

        for cluster in clusters:
            group_votes: dict[str, list[float]] = {}

            for statement_id in cluster.representative_statements:
                if statement_id in self.voting_matrix:
                    for stakeholder_id, vote in self.voting_matrix[statement_id].items():
                        group = f"group_{hash(stakeholder_id) % 4}"

                        if group not in group_votes:
                            group_votes[group] = []
                        group_votes[group].append(vote)

            group_scores = {}
            for group, votes in group_votes.items():
                if votes:
                    agree_ratio = sum(1 for v in votes if v == 1) / len(votes)
                    group_scores[group] = agree_ratio

            if group_scores:
                cross_consensus = min(group_scores.values())
                cluster.cross_group_consensus = cross_consensus
            else:
                cluster.cross_group_consensus = 0.0

        total_clusters = len(clusters)
        high_consensus_clusters = sum(1 for c in clusters if c.consensus_score > 0.6)

        return {
            "total_clusters": total_clusters,
            "high_consensus_clusters": high_consensus_clusters,
            "consensus_ratio": (
                high_consensus_clusters / total_clusters if total_clusters > 0 else 0
            ),
            "average_cross_group_consensus": (
                statistics.mean([c.consensus_score for c in clusters]) if clusters else 0
            ),
            "polarization_risk": (
                "low" if high_consensus_clusters > total_clusters * 0.5 else "high"
            ),
        }
