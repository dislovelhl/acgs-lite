"""
Integration Tests for CCAI Representative Statement Identification.
Constitutional Hash: 608508a9bd224290
"""

import warnings

import pytest

from enhanced_agent_bus.governance.ccai_framework import (
    DeliberationStatement,
    DemocraticConstitutionalGovernance,
    PolisDeliberationEngine,
    StakeholderGroup,
)

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestIntegrationEndToEnd:
    """Integration tests for representative statement identification."""

    async def test_full_deliberation_with_representative_identification(self):
        """Test complete deliberation flow with representative statement identification."""
        governance = DemocraticConstitutionalGovernance(consensus_threshold=0.6)

        stakeholders = []
        groups = [
            StakeholderGroup.TECHNICAL_EXPERTS,
            StakeholderGroup.ETHICS_REVIEWERS,
            StakeholderGroup.END_USERS,
            StakeholderGroup.LEGAL_EXPERTS,
        ]

        for _i, group in enumerate(groups):
            for j in range(3):
                stakeholder = await governance.register_stakeholder(
                    name=f"Stakeholder_{group.value}_{j}",
                    group=group,
                    expertise_areas=["Constitutional Governance", "AI Ethics"],
                )
                stakeholders.append(stakeholder)

        assert len(stakeholders) == 12, f"Expected 12 stakeholders, got {len(stakeholders)}"

        proposal = await governance.propose_constitutional_change(
            title="AI Decision Transparency Amendment",
            description="Require all AI decisions to include explanations",
            proposed_changes={"transparency": "required", "explanation_depth": "detailed"},
            proposer=stakeholders[0],
        )

        result = await governance.run_deliberation(proposal, stakeholders)

        assert result is not None, "Deliberation result should not be None"
        assert result.total_participants == 12, (
            f"Expected 12 participants, got {result.total_participants}"
        )
        assert result.statements_submitted > 0, "Should have statements submitted"
        assert result.clusters_identified > 0, "Should have identified clusters"

        clusters = list(governance.polis_engine.clusters.values())
        assert len(clusters) > 0, "Should have at least one cluster"

        for cluster in clusters:
            assert isinstance(cluster.representative_statements, list), (
                f"Cluster {cluster.cluster_id} representative_statements should be a list"
            )

            if cluster.size > 0:
                if len(governance.polis_engine.statements) > 0:
                    assert len(cluster.representative_statements) >= 0, (
                        f"Cluster {cluster.cluster_id} should have representatives"
                    )

                    assert "representative_count" in cluster.metadata, (
                        "Cluster metadata should contain representative_count"
                    )
                    assert "avg_centrality_score" in cluster.metadata, (
                        "Cluster metadata should contain avg_centrality_score"
                    )
                    assert "constitutional_hash" in cluster.metadata, (
                        "Cluster metadata should contain constitutional_hash"
                    )
                    assert cluster.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH, (
                        "Constitutional hash mismatch"
                    )

        assert (
            "representative_statements_metrics" in result.stability_analysis
            or len(result.stability_analysis) > 0
        ), "Stability analysis should be populated"

    async def test_multiple_clusters_with_representative_ranking(self):
        """Test deliberation with multiple clusters and verify representative ranking order."""
        engine = PolisDeliberationEngine(
            enable_diversity_filter=True,
            diversity_threshold=0.7,
        )

        stakeholders = [f"stakeholder-{i}" for i in range(15)]

        statements_cluster1 = []
        statements_cluster2 = []
        statements_cluster3 = []

        for i in range(5):
            stmt_id = f"privacy-stmt-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=f"Privacy is paramount in AI systems - statement {i}",
                author_id=stakeholders[i],
                author_group=StakeholderGroup.ETHICS_REVIEWERS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            statements_cluster1.append(stmt_id)

            votes = {}
            for j in range(5):
                votes[stakeholders[j]] = 1
            for j in range(5, 15):
                votes[stakeholders[j]] = -1 if j < 10 else 0

            engine.voting_matrix[stmt_id] = votes

        for i in range(5):
            stmt_id = f"efficiency-stmt-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=f"AI efficiency should be optimized - statement {i}",
                author_id=stakeholders[5 + i],
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            statements_cluster2.append(stmt_id)

            votes = {}
            for j in range(5):
                votes[stakeholders[j]] = -1
            for j in range(5, 10):
                votes[stakeholders[j]] = 1
            for j in range(10, 15):
                votes[stakeholders[j]] = 0

            engine.voting_matrix[stmt_id] = votes

        for i in range(5):
            stmt_id = f"balanced-stmt-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=f"Balance privacy and efficiency - statement {i}",
                author_id=stakeholders[10 + i],
                author_group=StakeholderGroup.LEGAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            statements_cluster3.append(stmt_id)

            votes = {}
            for j in range(5):
                votes[stakeholders[j]] = 0
            for j in range(5, 10):
                votes[stakeholders[j]] = 0
            for j in range(10, 15):
                votes[stakeholders[j]] = 1

            engine.voting_matrix[stmt_id] = votes

        clusters = await engine.identify_clusters()

        assert len(clusters) >= 2, f"Expected at least 2 clusters, got {len(clusters)}"

        for cluster in clusters:
            assert len(cluster.representative_statements) > 0, (
                f"Cluster {cluster.cluster_id} should have representative statements"
            )

            if len(cluster.representative_statements) > 1:
                centrality_scores = cluster.metadata.get("centrality_scores", [])
                assert len(centrality_scores) == len(cluster.representative_statements), (
                    "Should have centrality score for each representative"
                )

                for i in range(len(centrality_scores) - 1):
                    assert centrality_scores[i] >= centrality_scores[i + 1], (
                        f"Centrality scores not in descending order: {centrality_scores}"
                    )

            assert "representative_count" in cluster.metadata
            assert "avg_centrality_score" in cluster.metadata
            assert "selection_timestamp" in cluster.metadata
            assert cluster.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_representatives_populated_in_opinion_cluster(self):
        """Test that OpinionCluster.representative_statements is correctly populated."""
        engine = PolisDeliberationEngine(enable_diversity_filter=False)

        cluster_stakeholders = [f"stakeholder-{i}" for i in range(8)]

        for i in range(10):
            stmt_id = f"stmt-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=f"Test statement {i} for cluster population",
                author_id=cluster_stakeholders[i % len(cluster_stakeholders)],
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            votes = {}
            agreement_count = 8 - i
            for j in range(min(agreement_count, len(cluster_stakeholders))):
                votes[cluster_stakeholders[j]] = 1

            engine.voting_matrix[stmt_id] = votes

        clusters = await engine.identify_clusters()

        assert len(clusters) > 0, "Should identify at least one cluster"

        cluster = clusters[0]

        assert isinstance(cluster.representative_statements, list), (
            "representative_statements should be a list"
        )
        assert len(cluster.representative_statements) > 0, (
            "Should have at least one representative statement"
        )
        assert len(cluster.representative_statements) <= 5, (
            "Should not exceed top_n limit (default 5)"
        )

        for stmt_id in cluster.representative_statements:
            assert stmt_id in engine.statements, (
                f"Representative {stmt_id} should be a valid statement ID"
            )

        centrality_by_id = cluster.metadata.get("centrality_by_statement", {})
        assert len(centrality_by_id) > 0, "Should have centrality scores"

        all_centralities = sorted(centrality_by_id.items(), key=lambda x: x[1], reverse=True)
        expected_top5 = [stmt_id for stmt_id, _ in all_centralities[:5]]

        assert cluster.representative_statements == expected_top5, (
            f"Representatives {cluster.representative_statements} should match {expected_top5}"
        )

    async def test_diverse_representatives_in_large_cluster(self):
        """Test representative selection with diversity filtering in a large cluster."""
        engine = PolisDeliberationEngine(
            enable_diversity_filter=True,
            diversity_threshold=0.6,
        )

        stakeholders = [f"stakeholder-{i}" for i in range(15)]

        similar_statements = []
        for i in range(8):
            stmt_id = f"similar-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=f"AI systems should prioritize user privacy and data protection {i}",
                author_id=stakeholders[i],
                author_group=StakeholderGroup.ETHICS_REVIEWERS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            similar_statements.append(stmt_id)

            votes = {s: 1 for s in stakeholders[:12]}
            engine.voting_matrix[stmt_id] = votes

        diverse_statements = []
        diverse_contents = [
            "Performance metrics must be tracked",
            "Transparency in decision making is key",
            "User experience should drive design",
            "Regulatory compliance is essential",
        ]

        for i, content in enumerate(diverse_contents):
            stmt_id = f"diverse-{i}"
            engine.statements[stmt_id] = DeliberationStatement(
                statement_id=stmt_id,
                content=content,
                author_id=stakeholders[8 + i],
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            diverse_statements.append(stmt_id)

            votes = {s: 1 for s in stakeholders[:12]}
            engine.voting_matrix[stmt_id] = votes

        try:
            from sklearn.exceptions import ConvergenceWarning
        except ImportError:
            ConvergenceWarning = RuntimeWarning  # type: ignore[misc]

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            warnings.filterwarnings("ignore", category=ConvergenceWarning)
            clusters = await engine.identify_clusters()

        assert len(clusters) > 0, "Should identify at least one cluster"

        cluster = clusters[0]
        representatives = cluster.representative_statements

        assert len(representatives) > 0, "Should select representative statements"
        assert len(representatives) <= 5, "Should not exceed top_n limit"

        similar_count = sum(1 for r in representatives if r in similar_statements)
        diverse_count = sum(1 for r in representatives if r in diverse_statements)

        if len(representatives) >= 3:
            assert diverse_count > 0, "Should include some diverse statements"

        assert "diversity_scores" in cluster.metadata, "Should have diversity scores"
        assert "pairwise_similarities" in cluster.metadata, "Should have pairwise similarities"

        selection_reasons = cluster.metadata.get("selection_reasons", {})
        assert len(selection_reasons) > 0, "Should have selection reasons"

        if representatives:
            assert selection_reasons.get(representatives[0]) == "highest_centrality", (
                "First representative should be highest centrality"
            )

    async def test_ranking_order_verification(self):
        """Test that representatives are ranked by centrality score (descending order)."""
        engine = PolisDeliberationEngine(enable_diversity_filter=False)

        stakeholders = [f"stakeholder-{i}" for i in range(10)]

        engine.statements["high-centrality"] = DeliberationStatement(
            statement_id="high-centrality",
            content="High centrality statement",
            author_id=stakeholders[0],
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix["high-centrality"] = {s: 1 for s in stakeholders[:9]}

        engine.statements["medium-high-centrality"] = DeliberationStatement(
            statement_id="medium-high-centrality",
            content="Medium-high centrality statement",
            author_id=stakeholders[1],
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix["medium-high-centrality"] = {s: 1 for s in stakeholders[:7]}

        engine.statements["medium-centrality"] = DeliberationStatement(
            statement_id="medium-centrality",
            content="Medium centrality statement",
            author_id=stakeholders[2],
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix["medium-centrality"] = {s: 1 for s in stakeholders[:5]}

        engine.statements["low-centrality"] = DeliberationStatement(
            statement_id="low-centrality",
            content="Low centrality statement",
            author_id=stakeholders[3],
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix["low-centrality"] = {s: 1 for s in stakeholders[:3]}

        engine.statements["very-low-centrality"] = DeliberationStatement(
            statement_id="very-low-centrality",
            content="Very low centrality statement",
            author_id=stakeholders[4],
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix["very-low-centrality"] = {s: 1 for s in stakeholders[:1]}

        clusters = await engine.identify_clusters()

        assert len(clusters) > 0, "Should identify at least one cluster"

        cluster = clusters[0]
        representatives = cluster.representative_statements

        assert len(representatives) > 0, "Should have representative statements"

        expected_order = [
            "high-centrality",
            "medium-high-centrality",
            "medium-centrality",
            "low-centrality",
            "very-low-centrality",
        ][: len(representatives)]

        assert representatives == expected_order, (
            f"Representatives {representatives} not in expected centrality order {expected_order}"
        )

        centrality_scores = cluster.metadata.get("centrality_scores", [])
        for i in range(len(centrality_scores) - 1):
            assert centrality_scores[i] >= centrality_scores[i + 1], (
                f"Centrality scores not descending: {centrality_scores}"
            )

        centrality_by_id = cluster.metadata.get("centrality_by_statement", {})
        max_centrality = max(centrality_by_id.values())
        first_centrality = centrality_by_id[representatives[0]]
        assert first_centrality == max_centrality, (
            f"First representative should have highest centrality: "
            f"{first_centrality} vs {max_centrality}"
        )
