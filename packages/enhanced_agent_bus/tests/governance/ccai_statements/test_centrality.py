"""
Tests for Statement Centrality Calculation.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus.governance.ccai_framework import (
    DeliberationStatement,
    OpinionCluster,
    StakeholderGroup,
)

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestStatementCentralityCalculation:
    """Test suite for calculate_statement_centrality() method."""

    async def test_centrality_with_unanimous_agreement(self, engine, sample_cluster):
        """Test centrality calculation with unanimous agreement (all votes = 1)."""
        statement_id = "stmt-unanimous"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="We all agree on this",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 1,
            "stakeholder-3": 1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        assert centrality == 1.0, f"Expected 1.0, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_unanimous_disagreement(self, engine, sample_cluster):
        """Test centrality calculation with unanimous disagreement (all votes = -1)."""
        statement_id = "stmt-disagree"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="We all disagree on this",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": -1,
            "stakeholder-2": -1,
            "stakeholder-3": -1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        assert centrality == 0.3, f"Expected 0.3, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_split_votes(self, engine, sample_cluster):
        """Test centrality calculation with split votes (mixed agree/disagree)."""
        statement_id = "stmt-split"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="We have mixed opinions",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 1,
            "stakeholder-3": -1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        expected = 0.3 * 1.0 + 0.4 * (2 / 3) + 0.3 * ((1 / 3 + 1) / 2)
        assert abs(centrality - expected) < 0.001, f"Expected {expected:.3f}, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_partial_participation(self, engine, sample_cluster):
        """Test centrality calculation with partial participation (not all voted)."""
        statement_id = "stmt-partial"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Only some voted",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        expected = 0.3 * (2 / 3) + 0.4 * 1.0 + 0.3 * 1.0
        assert abs(centrality - expected) < 0.001, f"Expected {expected:.3f}, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_no_votes(self, engine, sample_cluster):
        """Test centrality calculation when no cluster members voted."""
        statement_id = "stmt-no-votes"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="No cluster members voted",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {}

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        assert centrality == 0.0, f"Expected 0.0, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_single_stakeholder(self, engine):
        """Test centrality calculation with a single stakeholder cluster."""
        single_cluster = OpinionCluster(
            cluster_id="cluster-single",
            name="Single Stakeholder Cluster",
            description="Cluster with one member",
            representative_statements=[],
            member_stakeholders=["stakeholder-1"],
            consensus_score=1.0,
            size=1,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        statement_id = "stmt-single"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Single stakeholder statement",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {"stakeholder-1": 1}

        centrality = await engine.calculate_statement_centrality(statement_id, single_cluster)

        assert centrality == 1.0, f"Expected 1.0, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_empty_cluster(self, engine, empty_cluster):
        """Test centrality calculation with an empty cluster."""
        statement_id = "stmt-empty-cluster"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Statement for empty cluster",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {"stakeholder-1": 1}

        centrality = await engine.calculate_statement_centrality(statement_id, empty_cluster)

        assert centrality == 0.0, f"Expected 0.0, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_with_nonexistent_statement(self, engine, sample_cluster):
        """Test centrality calculation with a statement ID that doesn't exist."""
        centrality = await engine.calculate_statement_centrality(
            "nonexistent-statement", sample_cluster
        )

        assert centrality == 0.0, f"Expected 0.0, got {centrality}"

    async def test_centrality_with_votes_outside_cluster(self, engine, sample_cluster):
        """Test that votes from non-cluster members are ignored."""
        statement_id = "stmt-mixed-voters"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Statement with mixed voters",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 1,
            "stakeholder-3": 1,
            "stakeholder-4": -1,  # NOT a cluster member
            "stakeholder-5": -1,  # NOT a cluster member
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        assert centrality == 1.0, f"Expected 1.0, got {centrality}"

    async def test_centrality_with_neutral_votes(self, engine, sample_cluster):
        """Test centrality calculation with neutral votes (value = 0)."""
        statement_id = "stmt-neutral"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Statement with neutral votes",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 0,
            "stakeholder-3": -1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, sample_cluster)

        expected = 0.3 * 1.0 + 0.4 * (1 / 3) + 0.3 * 0.5
        assert abs(centrality - expected) < 0.001, f"Expected {expected:.3f}, got {centrality}"
        assert 0.0 <= centrality <= 1.0, "Centrality not in [0, 1] range"

    async def test_centrality_score_normalization(self, engine, sample_cluster):
        """Test that centrality scores are always normalized to [0, 1] range."""
        test_cases = [
            (3, 0, 0),
            (0, 3, 0),
            (2, 1, 0),
            (1, 2, 0),
            (1, 1, 1),
            (0, 0, 3),
        ]

        for i, (agree_count, disagree_count, neutral_count) in enumerate(test_cases):
            statement_id = f"stmt-norm-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Normalization test {i}",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            votes = {}
            stakeholder_idx = 0
            for _ in range(agree_count):
                votes[f"stakeholder-{stakeholder_idx}"] = 1
                stakeholder_idx += 1
            for _ in range(disagree_count):
                votes[f"stakeholder-{stakeholder_idx}"] = -1
                stakeholder_idx += 1
            for _ in range(neutral_count):
                votes[f"stakeholder-{stakeholder_idx}"] = 0
                stakeholder_idx += 1

            engine.voting_matrix[statement_id] = votes

            test_cluster = OpinionCluster(
                cluster_id=f"cluster-norm-{i}",
                name=f"Normalization Test Cluster {i}",
                description="Test cluster",
                representative_statements=[],
                member_stakeholders=list(votes.keys()),
                consensus_score=0.5,
                size=len(votes),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            centrality = await engine.calculate_statement_centrality(statement_id, test_cluster)

            assert 0.0 <= centrality <= 1.0, (
                f"Test case {i}: Centrality {centrality} not in [0, 1] range"
            )

    async def test_centrality_with_multiple_stakeholder_groups(self, engine):
        """Test centrality with diverse stakeholder groups in cluster."""
        diverse_cluster = OpinionCluster(
            cluster_id="cluster-diverse",
            name="Diverse Stakeholder Cluster",
            description="Cluster with multiple stakeholder groups",
            representative_statements=[],
            member_stakeholders=["technical-1", "ethics-1", "enduser-1", "legal-1"],
            consensus_score=0.8,
            size=4,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        statement_id = "stmt-diverse"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Cross-group consensus statement",
            author_id="technical-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        engine.voting_matrix[statement_id] = {
            "technical-1": 1,
            "ethics-1": 1,
            "enduser-1": 1,
            "legal-1": 1,
        }

        centrality = await engine.calculate_statement_centrality(statement_id, diverse_cluster)

        assert centrality == 1.0, f"Expected 1.0, got {centrality}"
