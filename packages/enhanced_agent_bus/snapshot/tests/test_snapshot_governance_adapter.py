"""Tests for SnapshotGovernanceAdapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.unit


from enhanced_agent_bus.snapshot.snapshot_governance_adapter import (
    CONSTITUTIONAL_HASH,
    SnapshotGovernanceAdapter,
    SnapshotProposal,
    SnapshotProposalState,
    SnapshotSpace,
    SnapshotVotingAnalytics,
)


@pytest.fixture
def adapter():
    return SnapshotGovernanceAdapter("test-dao.eth", quorum_threshold=0.1)


@pytest.fixture
def sample_proposal():
    now = datetime.now(UTC)
    return SnapshotProposal(
        proposal_id="prop-001",
        space_id="test-dao.eth",
        title="Increase treasury allocation",
        body="Proposal to increase the treasury allocation for governance tooling.",
        state=SnapshotProposalState.ACTIVE,
        author="0xAuthor",
        created=now,
        start=now,
        end=now + timedelta(days=3),
        choices=["For", "Against", "Abstain"],
        scores=[100.0, 30.0, 10.0],
        scores_total=140.0,
        votes_count=42,
    )


class TestSnapshotSpace:
    def test_to_dict(self):
        space = SnapshotSpace(
            space_id="ens.eth",
            name="ENS DAO",
            members=["0x1", "0x2"],
            proposal_count=150,
            follower_count=5000,
        )
        d = space.to_dict()
        assert d["space_id"] == "ens.eth"
        assert d["member_count"] == 2
        assert d["proposal_count"] == 150

    def test_defaults(self):
        space = SnapshotSpace(space_id="x.eth", name="X")
        assert space.members == []
        assert space.proposal_count == 0


class TestSnapshotProposal:
    def test_to_dict(self, sample_proposal):
        d = sample_proposal.to_dict()
        assert d["proposal_id"] == "prop-001"
        assert d["state"] == "active"
        assert d["votes_count"] == 42
        assert d["acgs2_amendment_id"] is None

    def test_body_truncation(self):
        prop = SnapshotProposal(
            proposal_id="p",
            space_id="s",
            title="t",
            body="x" * 600,
            state=SnapshotProposalState.ACTIVE,
            author="a",
            created=datetime.now(UTC),
            start=datetime.now(UTC),
            end=datetime.now(UTC),
        )
        d = prop.to_dict()
        assert d["body"].endswith("...")
        assert len(d["body"]) == 503  # 500 + "..."


class TestSnapshotVotingAnalytics:
    def test_leading_choice(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s",
            total_votes=10,
            scores_by_choice={"For": 70.0, "Against": 20.0, "Abstain": 10.0},
            participation_rate=0.5,
            quorum_reached=True,
        )
        assert analytics.leading_choice == "For"
        assert analytics.approval_rate == 0.7

    def test_empty_scores(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p2",
            space_id="s",
            total_votes=0,
            scores_by_choice={},
            participation_rate=0.0,
            quorum_reached=False,
        )
        assert analytics.leading_choice is None
        assert analytics.approval_rate == 0.0

    def test_to_dict_includes_constitutional_hash(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p3",
            space_id="s",
            total_votes=1,
            scores_by_choice={"For": 1.0},
            participation_rate=0.01,
            quorum_reached=False,
        )
        d = analytics.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAdapterInit:
    def test_default_properties(self, adapter):
        assert adapter.space_id == "test-dao.eth"
        assert adapter.get_metrics()["space_id"] == "test-dao.eth"

    def test_initial_metrics(self, adapter):
        m = adapter.get_metrics()
        assert m["proposals_synced"] == 0
        assert m["total_proposals"] == 0
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSyncProposals:
    async def test_sync_empty(self, adapter):
        proposals = await adapter.sync_proposals()
        assert proposals == []
        assert adapter.get_metrics()["proposals_synced"] == 0

    async def test_sync_returns_cached(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        proposals = await adapter.sync_proposals()
        assert len(proposals) == 1
        assert proposals[0].proposal_id == "prop-001"

    async def test_sync_filter_by_state(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        closed = SnapshotProposal(
            proposal_id="prop-002",
            space_id="test-dao.eth",
            title="Old proposal",
            body="Done",
            state=SnapshotProposalState.CLOSED,
            author="0xA",
            created=datetime.now(UTC),
            start=datetime.now(UTC),
            end=datetime.now(UTC),
        )
        adapter._proposals["prop-002"] = closed

        active = await adapter.sync_proposals(state=SnapshotProposalState.ACTIVE)
        assert len(active) == 1
        assert active[0].proposal_id == "prop-001"

    async def test_sync_respects_limit(self, adapter):
        for i in range(10):
            adapter._proposals[f"p-{i}"] = SnapshotProposal(
                proposal_id=f"p-{i}",
                space_id="test-dao.eth",
                title=f"Prop {i}",
                body="body",
                state=SnapshotProposalState.ACTIVE,
                author="0xA",
                created=datetime.now(UTC),
                start=datetime.now(UTC),
                end=datetime.now(UTC),
            )
        results = await adapter.sync_proposals(limit=3)
        assert len(results) == 3


class TestSubmitAmendment:
    async def test_creates_proposal(self, adapter):
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="AMD-001",
            title="Update policy threshold",
            body="Change HITL trigger from 0.8 to 0.7",
            author="0xProposer",
        )
        assert pid is not None
        assert len(pid) == 16

        proposal = adapter.get_proposal(pid)
        assert proposal is not None
        assert proposal.state == SnapshotProposalState.ACTIVE
        assert proposal.acgs2_amendment_id == "AMD-001"
        assert "[Constitutional Amendment]" in proposal.title

    async def test_custom_choices(self, adapter):
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="AMD-002",
            title="Binary vote",
            body="Yes or no",
            author="0xA",
            choices=["Accept", "Reject"],
        )
        proposal = adapter.get_proposal(pid)
        assert proposal.choices == ["Accept", "Reject"]

    async def test_metrics_increment(self, adapter):
        await adapter.submit_constitutional_amendment(
            amendment_id="AMD-003",
            title="Test",
            body="body",
            author="0xA",
        )
        assert adapter.get_metrics()["proposals_created"] == 1


class TestRecordVote:
    async def test_valid_vote(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        ok = await adapter.record_vote("prop-001", "0xVoter", "For", 5.0)
        assert ok is True

        p = adapter.get_proposal("prop-001")
        assert p.votes_count == 43  # 42 + 1
        assert p.scores[0] == 105.0  # 100 + 5

    async def test_vote_on_missing_proposal(self, adapter):
        ok = await adapter.record_vote("nonexistent", "0xV", "For")
        assert ok is False

    async def test_vote_on_closed_proposal(self, adapter):
        closed = SnapshotProposal(
            proposal_id="closed-1",
            space_id="test-dao.eth",
            title="Done",
            body="body",
            state=SnapshotProposalState.CLOSED,
            author="0xA",
            created=datetime.now(UTC),
            start=datetime.now(UTC),
            end=datetime.now(UTC),
        )
        adapter._proposals["closed-1"] = closed
        ok = await adapter.record_vote("closed-1", "0xV", "For")
        assert ok is False

    async def test_invalid_choice(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        ok = await adapter.record_vote("prop-001", "0xV", "InvalidChoice")
        assert ok is False

    async def test_empty_voter_raises(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        with pytest.raises(ValueError, match="voter must not be empty"):
            await adapter.record_vote("prop-001", "", "For")

    async def test_empty_author_raises(self, adapter):
        with pytest.raises(ValueError, match="author must not be empty"):
            await adapter.submit_constitutional_amendment(
                amendment_id="A1", title="T", body="B", author=""
            )

    async def test_vote_invalidates_analytics_cache(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        # Pre-compute analytics
        await adapter.get_voting_analytics("prop-001")
        assert "prop-001" in adapter._analytics

        # Vote invalidates cache
        await adapter.record_vote("prop-001", "0xV", "For")
        assert "prop-001" not in adapter._analytics


class TestVotingAnalytics:
    async def test_compute_from_proposal(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        analytics = await adapter.get_voting_analytics("prop-001")
        assert analytics is not None
        assert analytics.total_votes == 42
        assert analytics.scores_by_choice["For"] == 100.0
        assert analytics.participation_rate == 0.42  # 42/100 default eligible

    async def test_quorum_with_space(self, adapter, sample_proposal):
        space = SnapshotSpace(space_id="test-dao.eth", name="Test", follower_count=200)
        adapter.add_space(space)
        adapter._proposals["prop-001"] = sample_proposal

        analytics = await adapter.get_voting_analytics("prop-001")
        assert analytics.participation_rate == 0.21  # 42/200
        assert analytics.quorum_reached is True  # 0.21 >= 0.1

    async def test_missing_proposal_returns_none(self, adapter):
        result = await adapter.get_voting_analytics("nonexistent")
        assert result is None


class TestProposalSummary:
    async def test_summary_basic(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        summary = await adapter.get_proposal_summary("prop-001")
        assert summary is not None
        assert summary["proposal_id"] == "prop-001"
        assert summary["risk_level"] == "medium"  # "treasury" in body
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_summary_security_risk(self, adapter):
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="SEC-1",
            title="Security upgrade",
            body="Emergency security patch for critical vulnerability",
            author="0xA",
        )
        summary = await adapter.get_proposal_summary(pid)
        assert summary["risk_level"] == "high"

    async def test_summary_missing_proposal(self, adapter):
        result = await adapter.get_proposal_summary("nonexistent")
        assert result is None

    async def test_summary_amendment_flag(self, adapter):
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="AMD-5",
            title="Test",
            body="body",
            author="0xA",
        )
        summary = await adapter.get_proposal_summary(pid)
        assert summary["is_amendment"] is True


class TestActiveProposals:
    def test_no_active(self, adapter):
        assert adapter.get_active_proposals() == []

    def test_filters_by_state(self, adapter, sample_proposal):
        adapter._proposals["prop-001"] = sample_proposal
        closed = SnapshotProposal(
            proposal_id="prop-002",
            space_id="test-dao.eth",
            title="Done",
            body="b",
            state=SnapshotProposalState.CLOSED,
            author="a",
            created=datetime.now(UTC),
            start=datetime.now(UTC),
            end=datetime.now(UTC),
        )
        adapter._proposals["prop-002"] = closed
        active = adapter.get_active_proposals()
        assert len(active) == 1
        assert active[0].proposal_id == "prop-001"
