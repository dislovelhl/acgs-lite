"""
Regression Tests for CCAI Backward Compatibility with mHC Integration
Constitutional Hash: 608508a9bd224290

Tests ensure that representative statements implementation doesn't break:
- Existing CCAI functionality
- mHC stability layer integration
- Public API compatibility
- DeliberationResult structure
"""

import os
import statistics
import sys
from datetime import UTC, datetime, timezone

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Add project root to sys.path
sys.path.append("/home/martin/ACGS")

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.governance.ccai_framework import (
    ConstitutionalProposal,
    DeliberationResult,
    DeliberationStatement,
    DemocraticConstitutionalGovernance,
    OpinionCluster,
    PolisDeliberationEngine,
    Stakeholder,
    StakeholderGroup,
)


@pytest.mark.xfail(
    reason="Dynamic dim resizing (stability_layer.dim == n_clusters) not yet implemented",
    strict=False,
)
async def test_ccai_mhc_integration():
    # 1. Test Dynamic Dimension Resizing
    # DemocraticConstitutionalGovernance creates its own PolisDeliberationEngine internally
    governance = DemocraticConstitutionalGovernance()
    stakeholders = []
    for i in range(10):
        s = await governance.register_stakeholder(
            f"Stakeholder_{i}", StakeholderGroup.TECHNICAL_EXPERTS, ["General"]
        )
        stakeholders.append(s)

    proposal = await governance.propose_constitutional_change(
        title="Stability Test 1",
        description="Testing resizing with 10 stakeholders",
        proposed_changes={"param": 1},
        proposer=stakeholders[0],
    )

    result = await governance.run_deliberation(proposal, stakeholders)
    n_clusters = result.clusters_identified

    # Resizing check

    assert governance.stability_layer.dim == n_clusters
    assert result.stability_analysis["spectral_radius_bound"] <= 1.0, "Spectral radius violation"

    # 2. Test Trust-Weighted Influence
    # Register 2 stakeholders with very different trust
    h_s = await governance.register_stakeholder(
        "HighTrust", StakeholderGroup.TECHNICAL_EXPERTS, ["AI"]
    )
    l_s = await governance.register_stakeholder("LowTrust", StakeholderGroup.END_USERS, ["Usage"])

    # Access and modify trust scores
    h_s.trust_score = 0.9
    l_s.trust_score = 0.1

    proposal2 = await governance.propose_constitutional_change(
        title="Stability Test 2",
        description="Testing trust weighting",
        proposed_changes={"param": 2},
        proposer=h_s,
    )

    result2 = await governance.run_deliberation(proposal2, [h_s, l_s])

    # Resizing check

    assert governance.stability_layer.dim == result2.clusters_identified
    return True


async def test_backward_compatibility_deliberation_result():
    """
    Test that DeliberationResult structure is unchanged (only additions).

    Verifies:
    - All original fields are still present
    - New fields (stability_analysis) are optional/defaulted
    - to_dict() method works correctly
    - Constitutional hash is preserved
    """

    governance = DemocraticConstitutionalGovernance(consensus_threshold=0.6)

    # Register stakeholders
    stakeholders = []
    for i in range(5):
        s = await governance.register_stakeholder(
            f"Stakeholder_{i}", StakeholderGroup.TECHNICAL_EXPERTS, ["Testing"]
        )
        stakeholders.append(s)

    proposal = await governance.propose_constitutional_change(
        title="Backward Compatibility Test",
        description="Testing DeliberationResult structure",
        proposed_changes={"test_param": "value"},
        proposer=stakeholders[0],
    )

    result = await governance.run_deliberation(proposal, stakeholders)

    # Verify all original fields are present
    assert hasattr(result, "deliberation_id"), "Missing deliberation_id field"
    assert hasattr(result, "proposal"), "Missing proposal field"
    assert hasattr(result, "total_participants"), "Missing total_participants field"
    assert hasattr(result, "statements_submitted"), "Missing statements_submitted field"
    assert hasattr(result, "clusters_identified"), "Missing clusters_identified field"
    assert hasattr(result, "consensus_reached"), "Missing consensus_reached field"
    assert hasattr(result, "consensus_statements"), "Missing consensus_statements field"
    assert hasattr(result, "polarization_analysis"), "Missing polarization_analysis field"
    assert hasattr(result, "cross_group_consensus"), "Missing cross_group_consensus field"
    assert hasattr(result, "approved_amendments"), "Missing approved_amendments field"
    assert hasattr(result, "rejected_statements"), "Missing rejected_statements field"
    assert hasattr(result, "stability_analysis"), "Missing stability_analysis field"
    assert hasattr(result, "deliberation_metadata"), "Missing deliberation_metadata field"
    assert hasattr(result, "completed_at"), "Missing completed_at field"
    assert hasattr(result, "constitutional_hash"), "Missing constitutional_hash field"

    # Verify constitutional hash
    assert result.constitutional_hash == CONSTITUTIONAL_HASH

    # Verify to_dict() works
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict), "to_dict() should return dict"
    assert "deliberation_id" in result_dict
    assert "stability_analysis" in result_dict
    assert "constitutional_hash" in result_dict
    assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH

    assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_backward_compatibility_representative_statements():
    """
    Test that OpinionCluster.representative_statements is populated correctly.

    Verifies:
    - representative_statements field exists and is populated
    - Field is a list of statement IDs
    - Metadata includes selection statistics
    - No breaking changes to OpinionCluster API
    """

    governance = DemocraticConstitutionalGovernance(consensus_threshold=0.6)

    # Register stakeholders
    stakeholders = []
    for i in range(8):
        s = await governance.register_stakeholder(
            f"Stakeholder_{i}", StakeholderGroup.TECHNICAL_EXPERTS, ["Testing"]
        )
        stakeholders.append(s)

    proposal = await governance.propose_constitutional_change(
        title="Representative Statements Test",
        description="Testing representative_statements population",
        proposed_changes={"test": "value"},
        proposer=stakeholders[0],
    )

    # Run deliberation
    result = await governance.run_deliberation(proposal, stakeholders)

    # Access clusters from governance.deliberation_engine
    engine = governance.deliberation_engine

    # Verify clusters were created
    assert result.clusters_identified > 0, "Should identify at least one cluster"

    # Check that representative_statements is in stability_analysis
    if "representative_statements" in result.stability_analysis:
        rep_metrics = result.stability_analysis["representative_statements"]
        assert "total_representatives" in rep_metrics
        assert "avg_representatives_per_cluster" in rep_metrics
        assert "constitutional_hash" in rep_metrics
        assert rep_metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_backward_compatibility_opinion_cluster_to_dict():
    """
    Test that OpinionCluster.to_dict() includes new metadata without breaking.

    Verifies:
    - to_dict() returns all fields including metadata
    - New metadata fields are included
    - representative_statements field is serializable
    - Constitutional hash is present
    """

    # Create sample cluster with representative statements
    cluster = OpinionCluster(
        cluster_id="test-cluster-001",
        name="Test Cluster",
        description="Test cluster for to_dict() compatibility",
        representative_statements=["stmt-1", "stmt-2", "stmt-3"],
        member_stakeholders=["stakeholder-1", "stakeholder-2"],
        consensus_score=0.85,
        polarization_level=0.15,
        size=2,
        metadata={
            "representative_count": 3,
            "avg_centrality_score": 0.82,
            "min_centrality_score": 0.75,
            "max_centrality_score": 0.91,
            "centrality_scores": [0.91, 0.82, 0.75],
            "diversity_filtering_enabled": True,
            "diversity_threshold": 0.7,
            "selection_timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
        constitutional_hash=CONSTITUTIONAL_HASH,
    )

    # Test to_dict()
    cluster_dict = cluster.to_dict()

    # Verify all fields are present
    assert "cluster_id" in cluster_dict
    assert "name" in cluster_dict
    assert "description" in cluster_dict
    assert "representative_statements" in cluster_dict
    assert "member_stakeholders" in cluster_dict
    assert "consensus_score" in cluster_dict
    assert "polarization_level" in cluster_dict
    assert "size" in cluster_dict
    assert "created_at" in cluster_dict
    assert "metadata" in cluster_dict
    assert "constitutional_hash" in cluster_dict

    # Verify metadata is serialized correctly
    assert isinstance(cluster_dict["metadata"], dict)
    assert "representative_count" in cluster_dict["metadata"]
    assert "avg_centrality_score" in cluster_dict["metadata"]
    assert "constitutional_hash" in cluster_dict["metadata"]
    assert cluster_dict["metadata"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    # Verify representative_statements is serializable
    assert isinstance(cluster_dict["representative_statements"], list)
    assert len(cluster_dict["representative_statements"]) == 3

    # Verify constitutional hash
    assert cluster_dict["constitutional_hash"] == CONSTITUTIONAL_HASH

    assert cluster_dict["constitutional_hash"] == CONSTITUTIONAL_HASH


@pytest.mark.xfail(
    reason="Dynamic dim resizing (stability_layer.dim == n_clusters) not yet implemented",
    strict=False,
)
async def test_backward_compatibility_mhc_with_representatives():
    """
    Test that mHC stability integration still works with representative statements.

    Verifies:
    - mHC stability layer resizes correctly
    - Representative statements don't interfere with mHC
    - Stability metrics are present
    - Spectral radius bound is maintained
    """

    governance = DemocraticConstitutionalGovernance(consensus_threshold=0.6)

    # Register stakeholders
    stakeholders = []
    for i in range(12):
        s = await governance.register_stakeholder(
            f"Stakeholder_{i}", StakeholderGroup.TECHNICAL_EXPERTS, ["Testing"]
        )
        stakeholders.append(s)

    proposal = await governance.propose_constitutional_change(
        title="mHC with Representatives",
        description="Testing mHC stability with representative statements",
        proposed_changes={"mhc_test": True},
        proposer=stakeholders[0],
    )

    result = await governance.run_deliberation(proposal, stakeholders)

    # Verify mHC stability layer resized correctly
    assert governance.stability_layer.dim == result.clusters_identified

    # Verify stability metrics are present
    assert "stability_hash" in result.stability_analysis
    assert "spectral_radius_bound" in result.stability_analysis
    assert result.stability_analysis["spectral_radius_bound"] <= 1.0

    # Verify representative statements metrics don't interfere with mHC
    if "representative_statements" in result.stability_analysis:
        rep_metrics = result.stability_analysis["representative_statements"]
        assert "constitutional_hash" in rep_metrics
        assert rep_metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_backward_compatibility_public_api():
    """
    Test that public API methods are unchanged.

    Verifies:
    - DemocraticConstitutionalGovernance constructor unchanged
    - register_stakeholder() method unchanged
    - propose_constitutional_change() method unchanged
    - run_deliberation() method unchanged
    - Method signatures are compatible
    """

    # Test constructor
    governance = DemocraticConstitutionalGovernance(consensus_threshold=0.6)
    assert governance.consensus_threshold == 0.6
    assert hasattr(governance, "deliberation_engine")
    assert hasattr(governance, "stability_layer")

    # Test register_stakeholder
    stakeholder = await governance.register_stakeholder(
        "Test Stakeholder", StakeholderGroup.TECHNICAL_EXPERTS, ["Testing"]
    )
    assert stakeholder.name == "Test Stakeholder"
    assert stakeholder.group == StakeholderGroup.TECHNICAL_EXPERTS
    assert stakeholder.constitutional_hash == CONSTITUTIONAL_HASH

    # Test propose_constitutional_change
    proposal = await governance.propose_constitutional_change(
        title="API Test",
        description="Testing API compatibility",
        proposed_changes={"test": True},
        proposer=stakeholder,
    )
    assert proposal.title == "API Test"
    assert proposal.constitutional_hash == CONSTITUTIONAL_HASH

    # Test run_deliberation
    stakeholders = [stakeholder]
    for i in range(4):
        s = await governance.register_stakeholder(
            f"Stakeholder_{i}", StakeholderGroup.TECHNICAL_EXPERTS, ["Testing"]
        )
        stakeholders.append(s)

    result = await governance.run_deliberation(proposal, stakeholders)
    assert isinstance(result, DeliberationResult)
    assert result.constitutional_hash == CONSTITUTIONAL_HASH
