"""
ACGS-2 CCAI Democratic Framework
Constitutional Hash: cdd01ef066bc6cf2

CCAI (Collective Constitutional AI) provides breakthrough democratic governance:
- Polis deliberation platform for stakeholder input
- Cross-group consensus filtering to prevent polarization
- Performance-legitimacy balance with hybrid fast/slow paths
- Constitutional amendment workflow
- Representative statements identification for cluster interpretability

This addresses Challenge 5: Democratic AI Governance by ensuring
legitimate governance through democratic deliberation.

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

BACKWARD COMPATIBILITY:
    This module re-exports all public APIs from the refactored submodules.
    Import from this module continues to work as before.

    New modular structure:
    - governance/models.py: Data models (Enums, dataclasses)
    - governance/polis_engine.py: PolisDeliberationEngine class
    - governance/democratic_governance.py: DemocraticConstitutionalGovernance class

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio

from enhanced_agent_bus.observability.structured_logging import get_logger

from .democratic_governance import (
    DemocraticConstitutionalGovernance,
    ccai_governance,
    deliberate_on_proposal,
    get_ccai_governance,
)
from .models import (
    CONSTITUTIONAL_HASH,
    ConstitutionalProposal,
    DeliberationPhase,
    DeliberationResult,
    DeliberationStatement,
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)
from .polis_engine import PolisDeliberationEngine

logger = get_logger(__name__)

__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalProposal",
    "DeliberationPhase",
    "DeliberationResult",
    "DeliberationStatement",
    "DemocraticConstitutionalGovernance",
    "OpinionCluster",
    "PolisDeliberationEngine",
    "Stakeholder",
    "StakeholderGroup",
    "ccai_governance",
    "deliberate_on_proposal",
    "get_ccai_governance",
]

if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    async def main():
        logger.info("=" * 80)
        logger.info("CCAI Democratic Constitutional Governance - Representative Statements Demo")
        logger.info("Constitutional Hash: %s", CONSTITUTIONAL_HASH)
        logger.info("=" * 80)

        governance = DemocraticConstitutionalGovernance()

        status = await governance.get_governance_status()
        logger.info("\n[1] System Status")
        logger.info("    Governance status: %s", status["status"])
        logger.info("    Capabilities: Polis deliberation enabled")

        logger.info("\n[2] Registering Stakeholders")
        tech_expert = await governance.register_stakeholder(
            "Dr. Sarah Chen", StakeholderGroup.TECHNICAL_EXPERTS, ["AI", "security"]
        )
        ethicist = await governance.register_stakeholder(
            "Prof. Michael Torres", StakeholderGroup.ETHICS_REVIEWERS, ["ethics", "governance"]
        )
        end_user = await governance.register_stakeholder(
            "Jane Doe", StakeholderGroup.END_USERS, ["usability", "privacy"]
        )
        legal_expert = await governance.register_stakeholder(
            "Atty. Robert Kim", StakeholderGroup.LEGAL_EXPERTS, ["compliance", "regulation"]
        )
        business_lead = await governance.register_stakeholder(
            "Maria Garcia", StakeholderGroup.BUSINESS_STAKEHOLDERS, ["product", "strategy"]
        )

        stakeholders = [tech_expert, ethicist, end_user, legal_expert, business_lead]
        logger.info(
            "    Registered %d stakeholders across %d groups",
            len(stakeholders),
            len(set(s.group for s in stakeholders)),
        )

        logger.info("\n[3] Creating Proposal")
        proposal = await governance.propose_constitutional_change(
            title="Enhanced Transparency Requirements",
            description="Require all AI decisions to provide detailed explanations",
            proposed_changes={
                "transparency": "mandatory",
                "explanation_depth": "detailed",
                "audit_trail": "comprehensive",
            },
            proposer=tech_expert,
        )
        logger.info("    Proposal: %s", proposal.title)
        logger.info("    Proposer: %s (%s)", tech_expert.name, tech_expert.group.value)

        logger.info("\n[4] Running Deliberation Process")
        result = await governance.run_deliberation(proposal, stakeholders, duration_hours=24)

        logger.info("    Deliberation completed")
        logger.info("    Participants: %d", result.total_participants)
        logger.info("    Statements: %d", result.statements_submitted)
        logger.info("    Clusters: %d", result.clusters_identified)
        logger.info("    Consensus reached: %s", result.consensus_reached)
        logger.info("    Approved amendments: %d", len(result.approved_amendments))

        test_decision = {
            "id": "test_decision_001",
            "description": "Approve routine maintenance",
            "type": "maintenance",
        }

        fast_result = await governance.fast_govern(test_decision, 1000, stakeholders)
        logger.info("\n[5] Fast Governance Result")
        logger.info("    Decision approved: %s", fast_result["immediate_decision"]["approved"])
        logger.info("    Deliberation pending: %s", fast_result["deliberation_pending"])

        logger.info("\n" + "=" * 80)
        logger.info("DEMO COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        logger.info("Constitutional Hash: %s", CONSTITUTIONAL_HASH)

    asyncio.run(main())
