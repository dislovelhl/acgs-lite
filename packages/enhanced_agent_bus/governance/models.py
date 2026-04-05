"""
ACGS-2 CCAI Democratic Framework - Data Models
Constitutional Hash: 608508a9bd224290

This module contains all data models (dataclasses and Enums) for the CCAI
(Collective Constitutional AI) Democratic Governance Framework.

Models:
    - DeliberationPhase: Enum for deliberation workflow phases
    - StakeholderGroup: Enum for stakeholder classification
    - Stakeholder: Dataclass for governance participants
    - DeliberationStatement: Dataclass for submitted statements
    - OpinionCluster: Dataclass for identified opinion groups
    - ConstitutionalProposal: Dataclass for governance proposals
    - DeliberationResult: Dataclass for deliberation outcomes

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalProposal",
    "DeliberationPhase",
    "DeliberationResult",
    "DeliberationStatement",
    "OpinionCluster",
    "Stakeholder",
    "StakeholderGroup",
]


class DeliberationPhase(Enum):
    """
    Phases of democratic deliberation in the CCAI framework.

    Deliberation progresses through multiple phases to ensure thorough
    stakeholder input and consensus building.

    Attributes:
        PROPOSAL: Initial proposal submission phase
        DISCUSSION: Open discussion and statement submission phase
        CLUSTERING: Analysis phase for identifying opinion groups
        VOTING: Stakeholder voting on submitted statements
        CONSENSUS: Consensus analysis and validation phase
        AMENDMENT: Final amendment and implementation planning phase

    Constitutional Hash: 608508a9bd224290
    """

    PROPOSAL = "proposal"
    DISCUSSION = "discussion"
    CLUSTERING = "clustering"
    VOTING = "voting"
    CONSENSUS = "consensus"
    AMENDMENT = "amendment"


class StakeholderGroup(Enum):
    """
    Types of stakeholder groups for balanced representation in deliberation.

    CCAI ensures diverse stakeholder participation across technical, ethical,
    legal, and societal dimensions to prevent polarization and ensure
    comprehensive governance.

    Attributes:
        TECHNICAL_EXPERTS: System architects, engineers, AI researchers
        ETHICS_REVIEWERS: Ethicists, philosophers, human rights experts
        END_USERS: System users, affected individuals, advocacy groups
        LEGAL_EXPERTS: Lawyers, compliance officers, regulatory specialists
        BUSINESS_STAKEHOLDERS: Business leaders, product managers, executives
        CIVIL_SOCIETY: NGOs, community organizations, public interest groups
        REGULATORS: Government officials, policy makers, oversight bodies

    Constitutional Hash: 608508a9bd224290
    """

    TECHNICAL_EXPERTS = "technical_experts"
    ETHICS_REVIEWERS = "ethics_reviewers"
    END_USERS = "end_users"
    LEGAL_EXPERTS = "legal_experts"
    BUSINESS_STAKEHOLDERS = "business_stakeholders"
    CIVIL_SOCIETY = "civil_society"
    REGULATORS = "regulators"


@dataclass
class Stakeholder:
    """
    A stakeholder participant in democratic deliberation.

    Stakeholders represent diverse perspectives in the governance process,
    with tracking for participation, trust, and expertise.

    Attributes:
        stakeholder_id: Unique identifier for the stakeholder (UUID format)
        name: Display name of the stakeholder
        group: StakeholderGroup classification for balanced representation
        expertise_areas: list of domain expertise tags (e.g., ["AI", "security"])
        voting_weight: Weight applied to votes (default: 1.0, range: [0.0, 10.0])
        participation_score: Activity score (default: 0.0, range: [0.0, 1.0])
        trust_score: Reputation score (default: 0.5, range: [0.0, 1.0])
        registered_at: Timestamp of stakeholder registration (timezone.utc)
        last_active: Timestamp of last stakeholder activity (timezone.utc)
        constitutional_hash: Governance framework validation hash

    Constitutional Hash: 608508a9bd224290
    """

    stakeholder_id: str
    name: str
    group: StakeholderGroup
    expertise_areas: list[str]
    voting_weight: float = 1.0
    participation_score: float = 0.0
    trust_score: float = 0.5
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """
        Convert stakeholder to dictionary representation.

        Returns:
            Dictionary containing all stakeholder attributes with serialized datetimes

        Constitutional Hash: 608508a9bd224290
        """
        return {
            "stakeholder_id": self.stakeholder_id,
            "name": self.name,
            "group": self.group.value,
            "expertise_areas": self.expertise_areas,
            "voting_weight": self.voting_weight,
            "participation_score": self.participation_score,
            "trust_score": self.trust_score,
            "registered_at": self.registered_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class DeliberationStatement:
    """
    A statement submitted during deliberation process.

    Statements capture stakeholder positions and are analyzed for consensus
    potential through voting and clustering algorithms.

    Attributes:
        statement_id: Unique identifier for the statement (UUID format)
        content: Text content of the statement
        author_id: Stakeholder ID of the statement author
        author_group: StakeholderGroup of the author
        created_at: Timestamp when statement was submitted (timezone.utc)
        votes: Mapping of stakeholder_id to vote value (-1: disagree, 0: skip, 1: agree)
        agreement_score: Ratio of agree votes (range: [0.0, 1.0])
        disagreement_score: Ratio of disagree votes (range: [0.0, 1.0])
        consensus_potential: Net consensus (agreement - disagreement, range: [-1.0, 1.0])
        cluster_id: Opinion cluster ID this statement belongs to (None if not clustered)
        metadata: Additional statement metadata and analytics
        constitutional_hash: Governance framework validation hash

    Constitutional Hash: 608508a9bd224290
    """

    statement_id: str
    content: str
    author_id: str
    author_group: StakeholderGroup
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    votes: dict[str, int] = field(default_factory=dict)  # stakeholder_id -> vote (-1, 0, 1)
    agreement_score: float = 0.0
    disagreement_score: float = 0.0
    consensus_potential: float = 0.0
    cluster_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """
        Convert statement to dictionary representation.

        Returns:
            Dictionary containing all statement attributes with serialized datetimes

        Constitutional Hash: 608508a9bd224290
        """
        return {
            "statement_id": self.statement_id,
            "content": self.content,
            "author_id": self.author_id,
            "author_group": self.author_group.value,
            "created_at": self.created_at.isoformat(),
            "votes": self.votes,
            "agreement_score": self.agreement_score,
            "disagreement_score": self.disagreement_score,
            "consensus_potential": self.consensus_potential,
            "cluster_id": self.cluster_id,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class OpinionCluster:
    """
    A cluster of similar opinions identified through Polis-style clustering.

    Opinion clusters group stakeholders with similar voting patterns to identify
    consensus areas and prevent polarization through cross-group analysis.

    Attributes:
        cluster_id: Unique identifier for the cluster (UUID format)
        name: Human-readable cluster name (e.g., "Opinion Group 1")
        description: Description of the cluster's position or characteristics
        representative_statements: list of statement IDs that best represent cluster opinion
        member_stakeholders: list of stakeholder IDs belonging to this cluster
        consensus_score: Internal consensus strength (range: [0.0, 1.0])
        polarization_level: Polarization measure vs other clusters (range: [0.0, 1.0])
        size: Number of stakeholders in the cluster
        created_at: Timestamp when cluster was identified (timezone.utc)
        metadata: Clustering metrics, centrality scores, and diversity analysis
        constitutional_hash: Governance framework validation hash

    Algorithm:
        Uses PCA + K-Means clustering on voting matrix to identify opinion groups

    Constitutional Hash: 608508a9bd224290
    """

    cluster_id: str
    name: str
    description: str
    representative_statements: list[str]  # statement_ids
    member_stakeholders: list[str]  # stakeholder_ids
    canonical_statement_id: str | None = None
    canonical_representation: str | None = None
    consensus_score: float = 0.0
    polarization_level: float = 0.0
    cross_group_consensus: float = 0.0
    size: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """
        Convert cluster to dictionary representation.

        Returns:
            Dictionary containing all cluster attributes with serialized datetimes

        Constitutional Hash: 608508a9bd224290
        """
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "description": self.description,
            "representative_statements": self.representative_statements,
            "canonical_statement_id": self.canonical_statement_id,
            "canonical_representation": self.canonical_representation,
            "member_stakeholders": self.member_stakeholders,
            "consensus_score": self.consensus_score,
            "polarization_level": self.polarization_level,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ConstitutionalProposal:
    """
    A proposal for constitutional change requiring democratic deliberation.

    Constitutional proposals undergo full Polis deliberation to ensure
    legitimate governance changes with cross-stakeholder consensus.

    Attributes:
        proposal_id: Unique identifier for the proposal (UUID format)
        title: Concise proposal title
        description: Detailed proposal description and rationale
        proposed_changes: Dictionary of specific constitutional changes to be made
        proposer_id: Stakeholder ID of the proposal author
        deliberation_id: Associated deliberation session ID (UUID format)
        status: Proposal lifecycle status (proposed, deliberating, approved, rejected, implemented)
        consensus_threshold: Required consensus ratio for approval (default: 0.6, range: [0.0, 1.0])
        min_participants: Minimum stakeholders required for valid deliberation (default: 100)
        created_at: Timestamp when proposal was created (timezone.utc)
        deliberation_results: Results dictionary from completed deliberation
        implementation_plan: Implementation roadmap if approved (None if pending)
        constitutional_hash: Governance framework validation hash

    Constitutional Hash: 608508a9bd224290
    """

    proposal_id: str
    title: str
    description: str
    proposed_changes: JSONDict
    proposer_id: str
    deliberation_id: str
    status: str = "proposed"  # proposed, deliberating, approved, rejected, implemented
    consensus_threshold: float = 0.6
    min_participants: int = 100
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deliberation_results: JSONDict = field(default_factory=dict)
    implementation_plan: JSONDict | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """
        Convert proposal to dictionary representation.

        Returns:
            Dictionary containing all proposal attributes with serialized datetimes

        Constitutional Hash: 608508a9bd224290
        """
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "description": self.description,
            "proposed_changes": self.proposed_changes,
            "proposer_id": self.proposer_id,
            "deliberation_id": self.deliberation_id,
            "status": self.status,
            "consensus_threshold": self.consensus_threshold,
            "min_participants": self.min_participants,
            "created_at": self.created_at.isoformat(),
            "deliberation_results": self.deliberation_results,
            "implementation_plan": self.implementation_plan,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class DeliberationResult:
    """
    Comprehensive results of a democratic deliberation session.

    Contains all deliberation outcomes including consensus analysis,
    polarization metrics, and approved/rejected statements.

    Attributes:
        deliberation_id: Unique identifier for the deliberation session (UUID format)
        proposal: The ConstitutionalProposal that was deliberated
        total_participants: Number of stakeholders who participated
        statements_submitted: Number of statements submitted during deliberation
        clusters_identified: Number of opinion clusters identified
        consensus_reached: Whether consensus threshold was met (bool)
        consensus_statements: list of statements with high consensus approval
        polarization_analysis: Metrics on group polarization and division
        cross_group_consensus: Cross-stakeholder-group consensus validation results
        approved_amendments: list of approved constitutional amendments
        rejected_statements: list of statements with low consensus
        stability_analysis: Manifold stability metrics from mHC layer
        deliberation_metadata: Session metadata (duration, participation rate, etc.)
        completed_at: Timestamp when deliberation completed (timezone.utc)
        constitutional_hash: Governance framework validation hash

    Constitutional Hash: 608508a9bd224290
    """

    deliberation_id: str
    proposal: ConstitutionalProposal
    total_participants: int
    statements_submitted: int
    clusters_identified: int
    consensus_reached: bool
    consensus_statements: list[JSONDict]
    polarization_analysis: JSONDict
    cross_group_consensus: JSONDict
    approved_amendments: list[JSONDict]
    rejected_statements: list[JSONDict]
    stability_analysis: JSONDict = field(default_factory=dict)
    deliberation_metadata: JSONDict = field(default_factory=dict)
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """
        Convert deliberation result to dictionary representation.

        Returns:
            Dictionary containing all result attributes with serialized proposal and datetimes

        Constitutional Hash: 608508a9bd224290
        """
        return {
            "deliberation_id": self.deliberation_id,
            "proposal": self.proposal.to_dict(),
            "total_participants": self.total_participants,
            "statements_submitted": self.statements_submitted,
            "clusters_identified": self.clusters_identified,
            "consensus_reached": self.consensus_reached,
            "consensus_statements": self.consensus_statements,
            "polarization_analysis": self.polarization_analysis,
            "stability_analysis": self.stability_analysis,
            "cross_group_consensus": self.cross_group_consensus,
            "approved_amendments": self.approved_amendments,
            "rejected_statements": self.rejected_statements,
            "deliberation_metadata": self.deliberation_metadata,
            "completed_at": self.completed_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }
