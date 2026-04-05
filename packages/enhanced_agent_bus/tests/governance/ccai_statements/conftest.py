"""
Shared fixtures for CCAI Representative Statements tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.governance.ccai_framework import (
    OpinionCluster,
    PolisDeliberationEngine,
    StakeholderGroup,
)

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


@pytest.fixture
def engine():
    """Create a PolisDeliberationEngine instance for testing."""
    return PolisDeliberationEngine(
        enable_diversity_filter=False,  # Test basic centrality first
    )


@pytest.fixture
def sample_cluster():
    """Create a sample OpinionCluster for testing."""
    return OpinionCluster(
        cluster_id="cluster-001",
        name="Test Cluster",
        description="Test cluster for centrality calculation",
        representative_statements=[],
        member_stakeholders=["stakeholder-1", "stakeholder-2", "stakeholder-3"],
        consensus_score=0.8,
        size=3,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def empty_cluster():
    """Create an empty OpinionCluster for edge case testing."""
    return OpinionCluster(
        cluster_id="cluster-empty",
        name="Empty Cluster",
        description="Empty cluster for edge cases",
        representative_statements=[],
        member_stakeholders=[],
        consensus_score=0.0,
        size=0,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )
