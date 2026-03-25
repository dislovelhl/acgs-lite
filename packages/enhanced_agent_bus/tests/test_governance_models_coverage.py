# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/governance/models.py
Target: ≥95% line coverage of governance/models.py (76 stmts)

Constitutional Hash: 608508a9bd224290
"""

import os
import sys
from unittest.mock import MagicMock

# Block Rust imports before any module imports
if os.environ.get("TEST_WITH_RUST", "0") != "1":
    sys.modules["enhanced_agent_bus_rust"] = None

from dataclasses import fields
from datetime import UTC, datetime, timezone

from enhanced_agent_bus.governance.models import (
    CONSTITUTIONAL_HASH,
    ConstitutionalProposal,
    DeliberationPhase,
    DeliberationResult,
    DeliberationStatement,
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXPECTED_HASH = CONSTITUTIONAL_HASH


def make_stakeholder(**kwargs) -> Stakeholder:
    defaults = dict(
        stakeholder_id="stake-001",
        name="Alice Expert",
        group=StakeholderGroup.TECHNICAL_EXPERTS,
        expertise_areas=["AI", "security"],
    )
    defaults.update(kwargs)
    return Stakeholder(**defaults)


def make_statement(**kwargs) -> DeliberationStatement:
    defaults = dict(
        statement_id="stmt-001",
        content="This is a test statement.",
        author_id="stake-001",
        author_group=StakeholderGroup.ETHICS_REVIEWERS,
    )
    defaults.update(kwargs)
    return DeliberationStatement(**defaults)


def make_cluster(**kwargs) -> OpinionCluster:
    defaults = dict(
        cluster_id="cluster-001",
        name="Opinion Group 1",
        description="A cluster for testing.",
        representative_statements=["stmt-001", "stmt-002"],
        member_stakeholders=["stake-001", "stake-002"],
    )
    defaults.update(kwargs)
    return OpinionCluster(**defaults)


def make_proposal(**kwargs) -> ConstitutionalProposal:
    defaults = dict(
        proposal_id="prop-001",
        title="Test Proposal",
        description="A proposal for testing purposes.",
        proposed_changes={"rule": "new_value"},
        proposer_id="stake-001",
        deliberation_id="delib-001",
    )
    defaults.update(kwargs)
    return ConstitutionalProposal(**defaults)


def make_result(**kwargs) -> DeliberationResult:
    proposal = make_proposal()
    defaults = dict(
        deliberation_id="delib-001",
        proposal=proposal,
        total_participants=150,
        statements_submitted=42,
        clusters_identified=3,
        consensus_reached=True,
        consensus_statements=[{"stmt_id": "s1", "score": 0.8}],
        polarization_analysis={"level": 0.2},
        cross_group_consensus={"ratio": 0.7},
        approved_amendments=[{"change": "rule_update"}],
        rejected_statements=[{"stmt_id": "s99"}],
    )
    defaults.update(kwargs)
    return DeliberationResult(**defaults)


# ---------------------------------------------------------------------------
# CONSTITUTIONAL_HASH tests
# ---------------------------------------------------------------------------


class TestConstitutionalHashExport:
    def test_hash_value_is_correct(self):
        assert CONSTITUTIONAL_HASH == EXPECTED_HASH

    def test_hash_is_string(self):
        assert isinstance(CONSTITUTIONAL_HASH, str)

    def test_hash_length(self):
        assert len(CONSTITUTIONAL_HASH) == 16


# ---------------------------------------------------------------------------
# DeliberationPhase enum tests
# ---------------------------------------------------------------------------


class TestDeliberationPhase:
    def test_proposal_value(self):
        assert DeliberationPhase.PROPOSAL.value == "proposal"

    def test_discussion_value(self):
        assert DeliberationPhase.DISCUSSION.value == "discussion"

    def test_clustering_value(self):
        assert DeliberationPhase.CLUSTERING.value == "clustering"

    def test_voting_value(self):
        assert DeliberationPhase.VOTING.value == "voting"

    def test_consensus_value(self):
        assert DeliberationPhase.CONSENSUS.value == "consensus"

    def test_amendment_value(self):
        assert DeliberationPhase.AMENDMENT.value == "amendment"

    def test_all_phases_count(self):
        assert len(DeliberationPhase) == 6

    def test_enum_members_are_unique(self):
        values = [p.value for p in DeliberationPhase]
        assert len(values) == len(set(values))

    def test_phase_lookup_by_value(self):
        phase = DeliberationPhase("voting")
        assert phase == DeliberationPhase.VOTING

    def test_phase_names(self):
        names = {p.name for p in DeliberationPhase}
        expected = {"PROPOSAL", "DISCUSSION", "CLUSTERING", "VOTING", "CONSENSUS", "AMENDMENT"}
        assert names == expected


# ---------------------------------------------------------------------------
# StakeholderGroup enum tests
# ---------------------------------------------------------------------------


class TestStakeholderGroup:
    def test_technical_experts_value(self):
        assert StakeholderGroup.TECHNICAL_EXPERTS.value == "technical_experts"

    def test_ethics_reviewers_value(self):
        assert StakeholderGroup.ETHICS_REVIEWERS.value == "ethics_reviewers"

    def test_end_users_value(self):
        assert StakeholderGroup.END_USERS.value == "end_users"

    def test_legal_experts_value(self):
        assert StakeholderGroup.LEGAL_EXPERTS.value == "legal_experts"

    def test_business_stakeholders_value(self):
        assert StakeholderGroup.BUSINESS_STAKEHOLDERS.value == "business_stakeholders"

    def test_civil_society_value(self):
        assert StakeholderGroup.CIVIL_SOCIETY.value == "civil_society"

    def test_regulators_value(self):
        assert StakeholderGroup.REGULATORS.value == "regulators"

    def test_all_groups_count(self):
        assert len(StakeholderGroup) == 7

    def test_enum_members_are_unique(self):
        values = [g.value for g in StakeholderGroup]
        assert len(values) == len(set(values))

    def test_group_lookup_by_value(self):
        group = StakeholderGroup("end_users")
        assert group == StakeholderGroup.END_USERS

    def test_group_names(self):
        names = {g.name for g in StakeholderGroup}
        expected = {
            "TECHNICAL_EXPERTS",
            "ETHICS_REVIEWERS",
            "END_USERS",
            "LEGAL_EXPERTS",
            "BUSINESS_STAKEHOLDERS",
            "CIVIL_SOCIETY",
            "REGULATORS",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# Stakeholder tests
# ---------------------------------------------------------------------------


class TestStakeholder:
    def test_basic_creation(self):
        s = make_stakeholder()
        assert s.stakeholder_id == "stake-001"
        assert s.name == "Alice Expert"
        assert s.group == StakeholderGroup.TECHNICAL_EXPERTS
        assert s.expertise_areas == ["AI", "security"]

    def test_default_voting_weight(self):
        s = make_stakeholder()
        assert s.voting_weight == 1.0

    def test_default_participation_score(self):
        s = make_stakeholder()
        assert s.participation_score == 0.0

    def test_default_trust_score(self):
        s = make_stakeholder()
        assert s.trust_score == 0.5

    def test_default_constitutional_hash(self):
        s = make_stakeholder()
        assert s.constitutional_hash == EXPECTED_HASH

    def test_registered_at_is_datetime(self):
        s = make_stakeholder()
        assert isinstance(s.registered_at, datetime)

    def test_last_active_is_datetime(self):
        s = make_stakeholder()
        assert isinstance(s.last_active, datetime)

    def test_registered_at_timezone_aware(self):
        s = make_stakeholder()
        assert s.registered_at.tzinfo is not None

    def test_last_active_timezone_aware(self):
        s = make_stakeholder()
        assert s.last_active.tzinfo is not None

    def test_custom_voting_weight(self):
        s = make_stakeholder(voting_weight=2.5)
        assert s.voting_weight == 2.5

    def test_custom_participation_score(self):
        s = make_stakeholder(participation_score=0.9)
        assert s.participation_score == 0.9

    def test_custom_trust_score(self):
        s = make_stakeholder(trust_score=0.8)
        assert s.trust_score == 0.8

    def test_custom_constitutional_hash(self):
        s = make_stakeholder(constitutional_hash="custom_hash")
        assert s.constitutional_hash == "custom_hash"

    def test_empty_expertise_areas(self):
        s = make_stakeholder(expertise_areas=[])
        assert s.expertise_areas == []

    def test_multiple_expertise_areas(self):
        s = make_stakeholder(expertise_areas=["AI", "ML", "security", "ethics"])
        assert len(s.expertise_areas) == 4

    def test_all_stakeholder_groups(self):
        for group in StakeholderGroup:
            s = make_stakeholder(group=group)
            assert s.group == group

    def test_to_dict_returns_dict(self):
        s = make_stakeholder()
        result = s.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_stakeholder_id(self):
        s = make_stakeholder()
        assert s.to_dict()["stakeholder_id"] == "stake-001"

    def test_to_dict_name(self):
        s = make_stakeholder()
        assert s.to_dict()["name"] == "Alice Expert"

    def test_to_dict_group_is_value(self):
        s = make_stakeholder()
        assert s.to_dict()["group"] == "technical_experts"

    def test_to_dict_expertise_areas(self):
        s = make_stakeholder()
        assert s.to_dict()["expertise_areas"] == ["AI", "security"]

    def test_to_dict_voting_weight(self):
        s = make_stakeholder()
        assert s.to_dict()["voting_weight"] == 1.0

    def test_to_dict_participation_score(self):
        s = make_stakeholder()
        assert s.to_dict()["participation_score"] == 0.0

    def test_to_dict_trust_score(self):
        s = make_stakeholder()
        assert s.to_dict()["trust_score"] == 0.5

    def test_to_dict_registered_at_is_isoformat(self):
        s = make_stakeholder()
        result = s.to_dict()
        # Should be parseable ISO format
        parsed = datetime.fromisoformat(result["registered_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_last_active_is_isoformat(self):
        s = make_stakeholder()
        result = s.to_dict()
        parsed = datetime.fromisoformat(result["last_active"])
        assert isinstance(parsed, datetime)

    def test_to_dict_constitutional_hash(self):
        s = make_stakeholder()
        assert s.to_dict()["constitutional_hash"] == EXPECTED_HASH

    def test_to_dict_all_keys_present(self):
        s = make_stakeholder()
        result = s.to_dict()
        expected_keys = {
            "stakeholder_id",
            "name",
            "group",
            "expertise_areas",
            "voting_weight",
            "participation_score",
            "trust_score",
            "registered_at",
            "last_active",
            "constitutional_hash",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_group_for_each_group(self):
        for group in StakeholderGroup:
            s = make_stakeholder(group=group)
            assert s.to_dict()["group"] == group.value

    def test_custom_registered_at(self):
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        s = make_stakeholder(registered_at=dt)
        assert s.registered_at == dt

    def test_custom_last_active(self):
        dt = datetime(2025, 6, 15, tzinfo=UTC)
        s = make_stakeholder(last_active=dt)
        assert s.last_active == dt


# ---------------------------------------------------------------------------
# DeliberationStatement tests
# ---------------------------------------------------------------------------


class TestDeliberationStatement:
    def test_basic_creation(self):
        s = make_statement()
        assert s.statement_id == "stmt-001"
        assert s.content == "This is a test statement."
        assert s.author_id == "stake-001"
        assert s.author_group == StakeholderGroup.ETHICS_REVIEWERS

    def test_default_votes(self):
        s = make_statement()
        assert s.votes == {}

    def test_default_agreement_score(self):
        s = make_statement()
        assert s.agreement_score == 0.0

    def test_default_disagreement_score(self):
        s = make_statement()
        assert s.disagreement_score == 0.0

    def test_default_consensus_potential(self):
        s = make_statement()
        assert s.consensus_potential == 0.0

    def test_default_cluster_id_is_none(self):
        s = make_statement()
        assert s.cluster_id is None

    def test_default_metadata(self):
        s = make_statement()
        assert s.metadata == {}

    def test_default_constitutional_hash(self):
        s = make_statement()
        assert s.constitutional_hash == EXPECTED_HASH

    def test_created_at_is_datetime(self):
        s = make_statement()
        assert isinstance(s.created_at, datetime)

    def test_created_at_timezone_aware(self):
        s = make_statement()
        assert s.created_at.tzinfo is not None

    def test_custom_votes(self):
        votes = {"stake-001": 1, "stake-002": -1, "stake-003": 0}
        s = make_statement(votes=votes)
        assert s.votes == votes

    def test_custom_agreement_score(self):
        s = make_statement(agreement_score=0.75)
        assert s.agreement_score == 0.75

    def test_custom_disagreement_score(self):
        s = make_statement(disagreement_score=0.25)
        assert s.disagreement_score == 0.25

    def test_custom_consensus_potential(self):
        s = make_statement(consensus_potential=0.5)
        assert s.consensus_potential == 0.5

    def test_custom_cluster_id(self):
        s = make_statement(cluster_id="cluster-001")
        assert s.cluster_id == "cluster-001"

    def test_custom_metadata(self):
        meta = {"source": "test", "priority": 1}
        s = make_statement(metadata=meta)
        assert s.metadata == meta

    def test_to_dict_returns_dict(self):
        s = make_statement()
        result = s.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_statement_id(self):
        s = make_statement()
        assert s.to_dict()["statement_id"] == "stmt-001"

    def test_to_dict_content(self):
        s = make_statement()
        assert s.to_dict()["content"] == "This is a test statement."

    def test_to_dict_author_id(self):
        s = make_statement()
        assert s.to_dict()["author_id"] == "stake-001"

    def test_to_dict_author_group_is_value(self):
        s = make_statement()
        assert s.to_dict()["author_group"] == "ethics_reviewers"

    def test_to_dict_created_at_is_isoformat(self):
        s = make_statement()
        parsed = datetime.fromisoformat(s.to_dict()["created_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_votes(self):
        s = make_statement(votes={"stake-001": 1})
        assert s.to_dict()["votes"] == {"stake-001": 1}

    def test_to_dict_agreement_score(self):
        s = make_statement(agreement_score=0.6)
        assert s.to_dict()["agreement_score"] == 0.6

    def test_to_dict_disagreement_score(self):
        s = make_statement(disagreement_score=0.3)
        assert s.to_dict()["disagreement_score"] == 0.3

    def test_to_dict_consensus_potential(self):
        s = make_statement(consensus_potential=0.3)
        assert s.to_dict()["consensus_potential"] == 0.3

    def test_to_dict_cluster_id_none(self):
        s = make_statement()
        assert s.to_dict()["cluster_id"] is None

    def test_to_dict_cluster_id_set(self):
        s = make_statement(cluster_id="cluster-abc")
        assert s.to_dict()["cluster_id"] == "cluster-abc"

    def test_to_dict_metadata(self):
        meta = {"key": "value"}
        s = make_statement(metadata=meta)
        assert s.to_dict()["metadata"] == meta

    def test_to_dict_constitutional_hash(self):
        s = make_statement()
        assert s.to_dict()["constitutional_hash"] == EXPECTED_HASH

    def test_to_dict_all_keys_present(self):
        s = make_statement()
        result = s.to_dict()
        expected_keys = {
            "statement_id",
            "content",
            "author_id",
            "author_group",
            "created_at",
            "votes",
            "agreement_score",
            "disagreement_score",
            "consensus_potential",
            "cluster_id",
            "metadata",
            "constitutional_hash",
        }
        assert set(result.keys()) == expected_keys

    def test_author_group_for_each_group(self):
        for group in StakeholderGroup:
            s = make_statement(author_group=group)
            assert s.to_dict()["author_group"] == group.value


# ---------------------------------------------------------------------------
# OpinionCluster tests
# ---------------------------------------------------------------------------


class TestOpinionCluster:
    def test_basic_creation(self):
        c = make_cluster()
        assert c.cluster_id == "cluster-001"
        assert c.name == "Opinion Group 1"
        assert c.description == "A cluster for testing."

    def test_representative_statements(self):
        c = make_cluster()
        assert c.representative_statements == ["stmt-001", "stmt-002"]

    def test_member_stakeholders(self):
        c = make_cluster()
        assert c.member_stakeholders == ["stake-001", "stake-002"]

    def test_default_canonical_statement_id_is_none(self):
        c = make_cluster()
        assert c.canonical_statement_id is None

    def test_default_canonical_representation_is_none(self):
        c = make_cluster()
        assert c.canonical_representation is None

    def test_default_consensus_score(self):
        c = make_cluster()
        assert c.consensus_score == 0.0

    def test_default_polarization_level(self):
        c = make_cluster()
        assert c.polarization_level == 0.0

    def test_default_cross_group_consensus(self):
        c = make_cluster()
        assert c.cross_group_consensus == 0.0

    def test_default_size(self):
        c = make_cluster()
        assert c.size == 0

    def test_default_metadata(self):
        c = make_cluster()
        assert c.metadata == {}

    def test_default_constitutional_hash(self):
        c = make_cluster()
        assert c.constitutional_hash == EXPECTED_HASH

    def test_created_at_is_datetime(self):
        c = make_cluster()
        assert isinstance(c.created_at, datetime)

    def test_created_at_timezone_aware(self):
        c = make_cluster()
        assert c.created_at.tzinfo is not None

    def test_custom_canonical_statement_id(self):
        c = make_cluster(canonical_statement_id="stmt-canon-1")
        assert c.canonical_statement_id == "stmt-canon-1"

    def test_custom_canonical_representation(self):
        c = make_cluster(canonical_representation="This represents the cluster view.")
        assert c.canonical_representation == "This represents the cluster view."

    def test_custom_consensus_score(self):
        c = make_cluster(consensus_score=0.85)
        assert c.consensus_score == 0.85

    def test_custom_polarization_level(self):
        c = make_cluster(polarization_level=0.4)
        assert c.polarization_level == 0.4

    def test_custom_cross_group_consensus(self):
        c = make_cluster(cross_group_consensus=0.6)
        assert c.cross_group_consensus == 0.6

    def test_custom_size(self):
        c = make_cluster(size=42)
        assert c.size == 42

    def test_custom_metadata(self):
        meta = {"diversity_index": 0.7}
        c = make_cluster(metadata=meta)
        assert c.metadata == meta

    def test_to_dict_returns_dict(self):
        c = make_cluster()
        assert isinstance(c.to_dict(), dict)

    def test_to_dict_cluster_id(self):
        c = make_cluster()
        assert c.to_dict()["cluster_id"] == "cluster-001"

    def test_to_dict_name(self):
        c = make_cluster()
        assert c.to_dict()["name"] == "Opinion Group 1"

    def test_to_dict_description(self):
        c = make_cluster()
        assert c.to_dict()["description"] == "A cluster for testing."

    def test_to_dict_representative_statements(self):
        c = make_cluster()
        assert c.to_dict()["representative_statements"] == ["stmt-001", "stmt-002"]

    def test_to_dict_member_stakeholders(self):
        c = make_cluster()
        assert c.to_dict()["member_stakeholders"] == ["stake-001", "stake-002"]

    def test_to_dict_canonical_statement_id_none(self):
        c = make_cluster()
        assert c.to_dict()["canonical_statement_id"] is None

    def test_to_dict_canonical_statement_id_set(self):
        c = make_cluster(canonical_statement_id="stmt-x")
        assert c.to_dict()["canonical_statement_id"] == "stmt-x"

    def test_to_dict_canonical_representation_none(self):
        c = make_cluster()
        assert c.to_dict()["canonical_representation"] is None

    def test_to_dict_canonical_representation_set(self):
        c = make_cluster(canonical_representation="The main view.")
        assert c.to_dict()["canonical_representation"] == "The main view."

    def test_to_dict_consensus_score(self):
        c = make_cluster(consensus_score=0.75)
        assert c.to_dict()["consensus_score"] == 0.75

    def test_to_dict_polarization_level(self):
        c = make_cluster(polarization_level=0.2)
        assert c.to_dict()["polarization_level"] == 0.2

    def test_to_dict_size(self):
        c = make_cluster(size=10)
        assert c.to_dict()["size"] == 10

    def test_to_dict_created_at_is_isoformat(self):
        c = make_cluster()
        parsed = datetime.fromisoformat(c.to_dict()["created_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_metadata(self):
        meta = {"algo": "kmeans"}
        c = make_cluster(metadata=meta)
        assert c.to_dict()["metadata"] == meta

    def test_to_dict_constitutional_hash(self):
        c = make_cluster()
        assert c.to_dict()["constitutional_hash"] == EXPECTED_HASH

    def test_to_dict_all_keys_present(self):
        c = make_cluster()
        result = c.to_dict()
        expected_keys = {
            "cluster_id",
            "name",
            "description",
            "representative_statements",
            "canonical_statement_id",
            "canonical_representation",
            "member_stakeholders",
            "consensus_score",
            "polarization_level",
            "size",
            "created_at",
            "metadata",
            "constitutional_hash",
        }
        assert set(result.keys()) == expected_keys

    def test_empty_representative_statements(self):
        c = make_cluster(representative_statements=[])
        assert c.to_dict()["representative_statements"] == []

    def test_empty_member_stakeholders(self):
        c = make_cluster(member_stakeholders=[])
        assert c.to_dict()["member_stakeholders"] == []


# ---------------------------------------------------------------------------
# ConstitutionalProposal tests
# ---------------------------------------------------------------------------


class TestConstitutionalProposal:
    def test_basic_creation(self):
        p = make_proposal()
        assert p.proposal_id == "prop-001"
        assert p.title == "Test Proposal"
        assert p.description == "A proposal for testing purposes."

    def test_proposed_changes(self):
        p = make_proposal()
        assert p.proposed_changes == {"rule": "new_value"}

    def test_proposer_id(self):
        p = make_proposal()
        assert p.proposer_id == "stake-001"

    def test_deliberation_id(self):
        p = make_proposal()
        assert p.deliberation_id == "delib-001"

    def test_default_status(self):
        p = make_proposal()
        assert p.status == "proposed"

    def test_default_consensus_threshold(self):
        p = make_proposal()
        assert p.consensus_threshold == 0.6

    def test_default_min_participants(self):
        p = make_proposal()
        assert p.min_participants == 100

    def test_default_deliberation_results(self):
        p = make_proposal()
        assert p.deliberation_results == {}

    def test_default_implementation_plan_is_none(self):
        p = make_proposal()
        assert p.implementation_plan is None

    def test_default_constitutional_hash(self):
        p = make_proposal()
        assert p.constitutional_hash == EXPECTED_HASH

    def test_created_at_is_datetime(self):
        p = make_proposal()
        assert isinstance(p.created_at, datetime)

    def test_created_at_timezone_aware(self):
        p = make_proposal()
        assert p.created_at.tzinfo is not None

    def test_custom_status_deliberating(self):
        p = make_proposal(status="deliberating")
        assert p.status == "deliberating"

    def test_custom_status_approved(self):
        p = make_proposal(status="approved")
        assert p.status == "approved"

    def test_custom_status_rejected(self):
        p = make_proposal(status="rejected")
        assert p.status == "rejected"

    def test_custom_status_implemented(self):
        p = make_proposal(status="implemented")
        assert p.status == "implemented"

    def test_custom_consensus_threshold(self):
        p = make_proposal(consensus_threshold=0.75)
        assert p.consensus_threshold == 0.75

    def test_custom_min_participants(self):
        p = make_proposal(min_participants=50)
        assert p.min_participants == 50

    def test_custom_implementation_plan(self):
        plan = {"phase": 1, "steps": ["a", "b"]}
        p = make_proposal(implementation_plan=plan)
        assert p.implementation_plan == plan

    def test_custom_deliberation_results(self):
        results = {"consensus": 0.8}
        p = make_proposal(deliberation_results=results)
        assert p.deliberation_results == results

    def test_to_dict_returns_dict(self):
        p = make_proposal()
        assert isinstance(p.to_dict(), dict)

    def test_to_dict_proposal_id(self):
        p = make_proposal()
        assert p.to_dict()["proposal_id"] == "prop-001"

    def test_to_dict_title(self):
        p = make_proposal()
        assert p.to_dict()["title"] == "Test Proposal"

    def test_to_dict_description(self):
        p = make_proposal()
        assert p.to_dict()["description"] == "A proposal for testing purposes."

    def test_to_dict_proposed_changes(self):
        p = make_proposal()
        assert p.to_dict()["proposed_changes"] == {"rule": "new_value"}

    def test_to_dict_proposer_id(self):
        p = make_proposal()
        assert p.to_dict()["proposer_id"] == "stake-001"

    def test_to_dict_deliberation_id(self):
        p = make_proposal()
        assert p.to_dict()["deliberation_id"] == "delib-001"

    def test_to_dict_status(self):
        p = make_proposal()
        assert p.to_dict()["status"] == "proposed"

    def test_to_dict_consensus_threshold(self):
        p = make_proposal()
        assert p.to_dict()["consensus_threshold"] == 0.6

    def test_to_dict_min_participants(self):
        p = make_proposal()
        assert p.to_dict()["min_participants"] == 100

    def test_to_dict_created_at_is_isoformat(self):
        p = make_proposal()
        parsed = datetime.fromisoformat(p.to_dict()["created_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_deliberation_results(self):
        results = {"ratio": 0.7}
        p = make_proposal(deliberation_results=results)
        assert p.to_dict()["deliberation_results"] == results

    def test_to_dict_implementation_plan_none(self):
        p = make_proposal()
        assert p.to_dict()["implementation_plan"] is None

    def test_to_dict_implementation_plan_set(self):
        plan = {"steps": ["deploy"]}
        p = make_proposal(implementation_plan=plan)
        assert p.to_dict()["implementation_plan"] == plan

    def test_to_dict_constitutional_hash(self):
        p = make_proposal()
        assert p.to_dict()["constitutional_hash"] == EXPECTED_HASH

    def test_to_dict_all_keys_present(self):
        p = make_proposal()
        result = p.to_dict()
        expected_keys = {
            "proposal_id",
            "title",
            "description",
            "proposed_changes",
            "proposer_id",
            "deliberation_id",
            "status",
            "consensus_threshold",
            "min_participants",
            "created_at",
            "deliberation_results",
            "implementation_plan",
            "constitutional_hash",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# DeliberationResult tests
# ---------------------------------------------------------------------------


class TestDeliberationResult:
    def test_basic_creation(self):
        r = make_result()
        assert r.deliberation_id == "delib-001"
        assert r.total_participants == 150
        assert r.statements_submitted == 42
        assert r.clusters_identified == 3

    def test_consensus_reached_true(self):
        r = make_result(consensus_reached=True)
        assert r.consensus_reached is True

    def test_consensus_reached_false(self):
        r = make_result(consensus_reached=False)
        assert r.consensus_reached is False

    def test_proposal_is_constitutional_proposal(self):
        r = make_result()
        assert isinstance(r.proposal, ConstitutionalProposal)

    def test_consensus_statements(self):
        r = make_result()
        assert r.consensus_statements == [{"stmt_id": "s1", "score": 0.8}]

    def test_polarization_analysis(self):
        r = make_result()
        assert r.polarization_analysis == {"level": 0.2}

    def test_cross_group_consensus(self):
        r = make_result()
        assert r.cross_group_consensus == {"ratio": 0.7}

    def test_approved_amendments(self):
        r = make_result()
        assert r.approved_amendments == [{"change": "rule_update"}]

    def test_rejected_statements(self):
        r = make_result()
        assert r.rejected_statements == [{"stmt_id": "s99"}]

    def test_default_stability_analysis(self):
        r = make_result()
        assert r.stability_analysis == {}

    def test_default_deliberation_metadata(self):
        r = make_result()
        assert r.deliberation_metadata == {}

    def test_default_constitutional_hash(self):
        r = make_result()
        assert r.constitutional_hash == EXPECTED_HASH

    def test_completed_at_is_datetime(self):
        r = make_result()
        assert isinstance(r.completed_at, datetime)

    def test_completed_at_timezone_aware(self):
        r = make_result()
        assert r.completed_at.tzinfo is not None

    def test_custom_stability_analysis(self):
        sa = {"metric": 0.95, "stable": True}
        r = make_result(stability_analysis=sa)
        assert r.stability_analysis == sa

    def test_custom_deliberation_metadata(self):
        meta = {"duration_hours": 24, "participation_rate": 0.85}
        r = make_result(deliberation_metadata=meta)
        assert r.deliberation_metadata == meta

    def test_custom_completed_at(self):
        dt = datetime(2025, 12, 31, tzinfo=UTC)
        r = make_result(completed_at=dt)
        assert r.completed_at == dt

    def test_to_dict_returns_dict(self):
        r = make_result()
        assert isinstance(r.to_dict(), dict)

    def test_to_dict_deliberation_id(self):
        r = make_result()
        assert r.to_dict()["deliberation_id"] == "delib-001"

    def test_to_dict_proposal_is_dict(self):
        r = make_result()
        assert isinstance(r.to_dict()["proposal"], dict)

    def test_to_dict_proposal_calls_proposal_to_dict(self):
        # Verify nested to_dict is called on proposal
        r = make_result()
        result = r.to_dict()
        assert result["proposal"]["proposal_id"] == "prop-001"

    def test_to_dict_total_participants(self):
        r = make_result()
        assert r.to_dict()["total_participants"] == 150

    def test_to_dict_statements_submitted(self):
        r = make_result()
        assert r.to_dict()["statements_submitted"] == 42

    def test_to_dict_clusters_identified(self):
        r = make_result()
        assert r.to_dict()["clusters_identified"] == 3

    def test_to_dict_consensus_reached_true(self):
        r = make_result(consensus_reached=True)
        assert r.to_dict()["consensus_reached"] is True

    def test_to_dict_consensus_reached_false(self):
        r = make_result(consensus_reached=False)
        assert r.to_dict()["consensus_reached"] is False

    def test_to_dict_consensus_statements(self):
        r = make_result()
        assert r.to_dict()["consensus_statements"] == [{"stmt_id": "s1", "score": 0.8}]

    def test_to_dict_polarization_analysis(self):
        r = make_result()
        assert r.to_dict()["polarization_analysis"] == {"level": 0.2}

    def test_to_dict_stability_analysis(self):
        sa = {"score": 0.99}
        r = make_result(stability_analysis=sa)
        assert r.to_dict()["stability_analysis"] == sa

    def test_to_dict_cross_group_consensus(self):
        r = make_result()
        assert r.to_dict()["cross_group_consensus"] == {"ratio": 0.7}

    def test_to_dict_approved_amendments(self):
        r = make_result()
        assert r.to_dict()["approved_amendments"] == [{"change": "rule_update"}]

    def test_to_dict_rejected_statements(self):
        r = make_result()
        assert r.to_dict()["rejected_statements"] == [{"stmt_id": "s99"}]

    def test_to_dict_deliberation_metadata(self):
        meta = {"rate": 0.9}
        r = make_result(deliberation_metadata=meta)
        assert r.to_dict()["deliberation_metadata"] == meta

    def test_to_dict_completed_at_is_isoformat(self):
        r = make_result()
        parsed = datetime.fromisoformat(r.to_dict()["completed_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_constitutional_hash(self):
        r = make_result()
        assert r.to_dict()["constitutional_hash"] == EXPECTED_HASH

    def test_to_dict_all_keys_present(self):
        r = make_result()
        result = r.to_dict()
        expected_keys = {
            "deliberation_id",
            "proposal",
            "total_participants",
            "statements_submitted",
            "clusters_identified",
            "consensus_reached",
            "consensus_statements",
            "polarization_analysis",
            "stability_analysis",
            "cross_group_consensus",
            "approved_amendments",
            "rejected_statements",
            "deliberation_metadata",
            "completed_at",
            "constitutional_hash",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_empty_consensus_statements(self):
        r = make_result(consensus_statements=[])
        assert r.to_dict()["consensus_statements"] == []

    def test_to_dict_multiple_approved_amendments(self):
        amendments = [{"change": "a"}, {"change": "b"}, {"change": "c"}]
        r = make_result(approved_amendments=amendments)
        assert r.to_dict()["approved_amendments"] == amendments

    def test_to_dict_multiple_rejected_statements(self):
        rejected = [{"id": "1"}, {"id": "2"}]
        r = make_result(rejected_statements=rejected)
        assert r.to_dict()["rejected_statements"] == rejected


# ---------------------------------------------------------------------------
# Cross-model integration tests
# ---------------------------------------------------------------------------


class TestCrossModelIntegration:
    def test_stakeholder_and_statement_share_group(self):
        group = StakeholderGroup.LEGAL_EXPERTS
        s = make_stakeholder(group=group)
        stmt = make_statement(author_group=group)
        assert s.to_dict()["group"] == stmt.to_dict()["author_group"]

    def test_statement_cluster_id_matches_cluster(self):
        cluster = make_cluster(cluster_id="clu-x")
        stmt = make_statement(cluster_id="clu-x")
        assert stmt.cluster_id == cluster.cluster_id

    def test_proposal_embedded_in_result(self):
        proposal = make_proposal(status="deliberating")
        result = make_result(proposal=proposal)
        assert result.to_dict()["proposal"]["status"] == "deliberating"

    def test_deliberation_result_with_zero_participants(self):
        r = make_result(total_participants=0, statements_submitted=0, clusters_identified=0)
        d = r.to_dict()
        assert d["total_participants"] == 0
        assert d["statements_submitted"] == 0
        assert d["clusters_identified"] == 0

    def test_all_models_use_same_constitutional_hash(self):
        s = make_stakeholder()
        stmt = make_statement()
        c = make_cluster()
        p = make_proposal()
        r = make_result()
        for model in [s, stmt, c, p, r]:
            assert model.constitutional_hash == EXPECTED_HASH

    def test_all_to_dicts_include_constitutional_hash(self):
        for d in [
            make_stakeholder().to_dict(),
            make_statement().to_dict(),
            make_cluster().to_dict(),
            make_proposal().to_dict(),
            make_result().to_dict(),
        ]:
            assert d["constitutional_hash"] == EXPECTED_HASH


# ---------------------------------------------------------------------------
# __all__ export tests
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_constitutional_hash_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "CONSTITUTIONAL_HASH")

    def test_deliberation_phase_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "DeliberationPhase")

    def test_stakeholder_group_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "StakeholderGroup")

    def test_stakeholder_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "Stakeholder")

    def test_deliberation_statement_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "DeliberationStatement")

    def test_opinion_cluster_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "OpinionCluster")

    def test_constitutional_proposal_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "ConstitutionalProposal")

    def test_deliberation_result_exported(self):
        from enhanced_agent_bus.governance import models as m

        assert hasattr(m, "DeliberationResult")
