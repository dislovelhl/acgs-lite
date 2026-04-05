"""
Tests for Representative Statement Selection.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus.governance.ccai_framework import (
    DeliberationStatement,
    StakeholderGroup,
)

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestRepresentativeStatementSelection:
    """Test suite for select_representative_statements() method."""

    async def test_select_top_n_representatives(self, engine, sample_cluster):
        """Test selection of top N representative statements."""
        statements = []
        for i in range(5):
            statement_id = f"stmt-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Statement {i}",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            statements.append(statement_id)

            if i == 0:
                votes = {"stakeholder-1": 1, "stakeholder-2": 1, "stakeholder-3": 1}
            elif i == 1:
                votes = {"stakeholder-1": 1, "stakeholder-2": 1, "stakeholder-3": -1}
            elif i == 2:
                votes = {"stakeholder-1": 1, "stakeholder-2": -1, "stakeholder-3": -1}
            elif i == 3:
                votes = {"stakeholder-1": -1, "stakeholder-2": -1, "stakeholder-3": -1}
            else:
                votes = {"stakeholder-1": 1, "stakeholder-2": 1}

            engine.voting_matrix[statement_id] = votes

        representatives = await engine.select_representative_statements(sample_cluster, top_n=3)

        assert len(representatives) == 3, f"Expected 3 representatives, got {len(representatives)}"
        assert representatives[0] == "stmt-0", "Highest centrality should be first"
        assert "stmt-3" not in representatives, "Lowest centrality should not be selected"

    async def test_select_with_empty_cluster(self, engine, empty_cluster):
        """Test selection with empty cluster returns empty list."""
        representatives = await engine.select_representative_statements(empty_cluster, top_n=5)

        assert representatives == [], f"Expected empty list, got {representatives}"

    async def test_select_with_no_votes(self, engine, sample_cluster):
        """Test selection when no statements have votes returns empty list."""
        for i in range(3):
            statement_id = f"stmt-no-vote-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Statement {i} with no votes",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            engine.voting_matrix[statement_id] = {}

        representatives = await engine.select_representative_statements(sample_cluster, top_n=3)

        assert representatives == [], f"Expected empty list, got {representatives}"

    async def test_select_fewer_statements_than_top_n(self, engine, sample_cluster):
        """Test selection when fewer statements available than requested."""
        for i in range(2):
            statement_id = f"stmt-few-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Statement {i}",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            engine.voting_matrix[statement_id] = {
                "stakeholder-1": 1,
                "stakeholder-2": 1,
                "stakeholder-3": 1,
            }

        representatives = await engine.select_representative_statements(sample_cluster, top_n=5)

        assert len(representatives) == 2, f"Expected 2 representatives, got {len(representatives)}"

    async def test_select_with_invalid_top_n(self, engine, sample_cluster):
        """Test selection with invalid top_n values."""
        statement_id = "stmt-valid"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Valid statement",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        engine.voting_matrix[statement_id] = {
            "stakeholder-1": 1,
            "stakeholder-2": 1,
            "stakeholder-3": 1,
        }

        representatives = await engine.select_representative_statements(sample_cluster, top_n=0)
        assert len(representatives) == 1, "Should return available statements"

        representatives = await engine.select_representative_statements(sample_cluster, top_n=15)
        assert len(representatives) == 1, "Should return available statements"

    async def test_select_ranking_order(self, engine, sample_cluster):
        """Test that representatives are ranked by centrality score (descending)."""
        for i in range(5):
            statement_id = f"stmt-rank-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Statement {i}",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            agrees = i + 1
            if agrees <= 3:
                votes = {}
                for j in range(agrees):
                    votes[f"stakeholder-{j + 1}"] = 1
                engine.voting_matrix[statement_id] = votes

        sample_cluster.member_stakeholders = [
            "stakeholder-1",
            "stakeholder-2",
            "stakeholder-3",
        ]

        representatives = await engine.select_representative_statements(sample_cluster, top_n=3)

        assert len(representatives) == 3, "Expected 3 representatives"

        centralities = []
        for stmt_id in representatives:
            centrality = await engine.calculate_statement_centrality(stmt_id, sample_cluster)
            centralities.append(centrality)

        for i in range(len(centralities) - 1):
            assert centralities[i] >= centralities[i + 1], (
                f"Representatives not in descending order: {centralities}"
            )
