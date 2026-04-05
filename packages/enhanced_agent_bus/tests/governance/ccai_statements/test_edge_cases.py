"""
Tests for Edge Cases in CCAI Representative Statements.
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time

import pytest

from enhanced_agent_bus.governance.ccai_framework import (
    DeliberationStatement,
    OpinionCluster,
    StakeholderGroup,
)

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestEdgeCases:
    """Test suite for edge cases in centrality calculation and selection."""

    async def test_constitutional_hash_validation(self, engine, sample_cluster):
        """Test that all operations maintain constitutional hash."""
        statement_id = "stmt-hash-test"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Hash validation test",
            author_id="stakeholder-1",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        assert engine.statements[statement_id].constitutional_hash == CONSTITUTIONAL_HASH
        assert sample_cluster.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_large_cluster_performance(self, engine):
        """Test centrality calculation with large cluster (100+ members)."""
        large_cluster = OpinionCluster(
            cluster_id="cluster-large",
            name="Large Cluster",
            description="Cluster with 100 members",
            representative_statements=[],
            member_stakeholders=[f"stakeholder-{i}" for i in range(100)],
            consensus_score=0.8,
            size=100,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        statement_id = "stmt-large"
        engine.statements[statement_id] = DeliberationStatement(
            statement_id=statement_id,
            content="Large cluster statement",
            author_id="stakeholder-0",
            author_group=StakeholderGroup.TECHNICAL_EXPERTS,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        votes = {}
        for i in range(80):
            votes[f"stakeholder-{i}"] = 1
        for i in range(80, 100):
            votes[f"stakeholder-{i}"] = -1

        engine.voting_matrix[statement_id] = votes

        start = time.time()
        centrality = await engine.calculate_statement_centrality(statement_id, large_cluster)
        elapsed = time.time() - start

        assert 0.0 <= centrality <= 1.0, "Centrality not in valid range"
        assert elapsed < 1.0, f"Performance issue: took {elapsed:.3f}s for 100 members"

    async def test_concurrent_centrality_calculations(self, engine, sample_cluster):
        """Test multiple concurrent centrality calculations."""
        statements = []
        for i in range(10):
            statement_id = f"stmt-concurrent-{i}"
            engine.statements[statement_id] = DeliberationStatement(
                statement_id=statement_id,
                content=f"Concurrent test {i}",
                author_id="stakeholder-1",
                author_group=StakeholderGroup.TECHNICAL_EXPERTS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            engine.voting_matrix[statement_id] = {
                "stakeholder-1": 1,
                "stakeholder-2": 1,
                "stakeholder-3": 1,
            }
            statements.append(statement_id)

        tasks = [
            engine.calculate_statement_centrality(stmt_id, sample_cluster) for stmt_id in statements
        ]
        centralities = await asyncio.gather(*tasks)

        assert len(centralities) == 10, f"Expected 10 results, got {len(centralities)}"
        for centrality in centralities:
            assert 0.0 <= centrality <= 1.0, "Invalid centrality value"
