"""
ACGS-2 Snapshot Governance Integration
Constitutional Hash: 608508a9bd224290

Bridges ACGS-2 constitutional governance to Ethereum DAO governance via Snapshot.
- Sync proposals from Snapshot spaces
- Voting analytics with constitutional alignment scoring
- Constitutional amendment submission via off-chain voting
"""

from .snapshot_governance_adapter import (
    SnapshotGovernanceAdapter,
    SnapshotProposal,
    SnapshotProposalState,
    SnapshotSpace,
    SnapshotVotingAnalytics,
)

__all__ = [
    "SnapshotGovernanceAdapter",
    "SnapshotProposal",
    "SnapshotProposalState",
    "SnapshotSpace",
    "SnapshotVotingAnalytics",
]
