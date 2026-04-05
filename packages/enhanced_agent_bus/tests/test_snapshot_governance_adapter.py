"""
Tests for enhanced_agent_bus.snapshot.snapshot_governance_adapter
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.snapshot.snapshot_governance_adapter import (
    SnapshotGovernanceAdapter,
    SnapshotProposal,
    SnapshotProposalState,
    SnapshotSpace,
    SnapshotVotingAnalytics,
)

# ---------------------------------------------------------------------------
# SnapshotSpace
# ---------------------------------------------------------------------------


class TestSnapshotSpace:
    def test_to_dict(self):
        space = SnapshotSpace(
            space_id="test.eth",
            name="Test DAO",
            members=["a", "b"],
            proposal_count=10,
            follower_count=100,
            voting_strategies=[{"name": "erc20-balance-of"}],
        )
        d = space.to_dict()
        assert d["space_id"] == "test.eth"
        assert d["member_count"] == 2
        assert d["strategy_count"] == 1

    def test_defaults(self):
        space = SnapshotSpace(space_id="x.eth", name="X")
        assert space.members == []
        assert space.proposal_count == 0


# ---------------------------------------------------------------------------
# SnapshotProposal
# ---------------------------------------------------------------------------


class TestSnapshotProposal:
    def _make_proposal(self, **kwargs):
        now = datetime.now(UTC)
        defaults = {
            "proposal_id": "prop_1",
            "space_id": "test.eth",
            "title": "Test Proposal",
            "body": "Body text",
            "state": SnapshotProposalState.ACTIVE,
            "author": "0xabc",
            "created": now,
            "start": now,
            "end": now + timedelta(days=3),
        }
        defaults.update(kwargs)
        return SnapshotProposal(**defaults)

    def test_to_dict(self):
        p = self._make_proposal()
        d = p.to_dict()
        assert d["proposal_id"] == "prop_1"
        assert d["state"] == "active"
        assert d["choices"] == ["For", "Against", "Abstain"]

    def test_long_body_truncated(self):
        p = self._make_proposal(body="x" * 600)
        d = p.to_dict()
        assert d["body"].endswith("...")
        assert len(d["body"]) <= 504  # 500 + "..."


# ---------------------------------------------------------------------------
# SnapshotVotingAnalytics
# ---------------------------------------------------------------------------


class TestSnapshotVotingAnalytics:
    def test_leading_choice(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s1",
            total_votes=10,
            scores_by_choice={"For": 7.0, "Against": 3.0},
            participation_rate=0.1,
            quorum_reached=True,
        )
        assert analytics.leading_choice == "For"

    def test_leading_choice_empty(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s1",
            total_votes=0,
            scores_by_choice={},
            participation_rate=0.0,
            quorum_reached=False,
        )
        assert analytics.leading_choice is None

    def test_approval_rate(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s1",
            total_votes=10,
            scores_by_choice={"For": 8.0, "Against": 2.0},
            participation_rate=0.5,
            quorum_reached=True,
        )
        assert analytics.approval_rate == pytest.approx(0.8)

    def test_approval_rate_zero_total(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s1",
            total_votes=0,
            scores_by_choice={},
            participation_rate=0.0,
            quorum_reached=False,
        )
        assert analytics.approval_rate == 0.0

    def test_to_dict(self):
        analytics = SnapshotVotingAnalytics(
            proposal_id="p1",
            space_id="s1",
            total_votes=5,
            scores_by_choice={"For": 3.0, "Against": 2.0},
            participation_rate=0.5,
            quorum_reached=True,
        )
        d = analytics.to_dict()
        assert d["leading_choice"] == "For"
        assert "approval_rate" in d


# ---------------------------------------------------------------------------
# SnapshotGovernanceAdapter
# ---------------------------------------------------------------------------


class TestSnapshotGovernanceAdapter:
    def _make_adapter(self, **kwargs):
        defaults = {"space_id": "test.eth"}
        defaults.update(kwargs)
        return SnapshotGovernanceAdapter(**defaults)

    def test_init(self):
        adapter = self._make_adapter()
        assert adapter.space_id == "test.eth"

    def test_get_metrics_initial(self):
        adapter = self._make_adapter()
        m = adapter.get_metrics()
        assert m["proposals_synced"] == 0
        assert m["space_id"] == "test.eth"
        assert m["total_proposals"] == 0

    @pytest.mark.asyncio
    async def test_submit_constitutional_amendment(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="amend_1",
            title="Fix governance",
            body="Details here",
            author="0xabc",
        )
        assert isinstance(pid, str)
        assert len(pid) == 16

        proposal = adapter.get_proposal(pid)
        assert proposal is not None
        assert proposal.acgs2_amendment_id == "amend_1"
        assert proposal.state == SnapshotProposalState.ACTIVE

    @pytest.mark.asyncio
    async def test_submit_empty_amendment_id_raises(self):
        adapter = self._make_adapter()
        with pytest.raises(ValueError, match="amendment_id"):
            await adapter.submit_constitutional_amendment(
                amendment_id="", title="t", body="b", author="0xabc"
            )

    @pytest.mark.asyncio
    async def test_submit_empty_author_raises(self):
        adapter = self._make_adapter()
        with pytest.raises(ValueError, match="author"):
            await adapter.submit_constitutional_amendment(
                amendment_id="a1", title="t", body="b", author=""
            )

    @pytest.mark.asyncio
    async def test_sync_proposals_empty(self):
        adapter = self._make_adapter()
        proposals = await adapter.sync_proposals()
        assert proposals == []

    @pytest.mark.asyncio
    async def test_sync_proposals_with_state_filter(self):
        adapter = self._make_adapter()
        await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        active = await adapter.sync_proposals(state=SnapshotProposalState.ACTIVE)
        assert len(active) == 1
        closed = await adapter.sync_proposals(state=SnapshotProposalState.CLOSED)
        assert len(closed) == 0

    @pytest.mark.asyncio
    async def test_sync_proposals_limit(self):
        adapter = self._make_adapter()
        for i in range(5):
            await adapter.submit_constitutional_amendment(
                amendment_id=f"a{i}", title=f"t{i}", body="b", author="0xabc"
            )
        proposals = await adapter.sync_proposals(limit=3)
        assert len(proposals) == 3

    @pytest.mark.asyncio
    async def test_record_vote(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        ok = await adapter.record_vote(pid, "voter_1", "For", 2.0)
        assert ok is True

        proposal = adapter.get_proposal(pid)
        assert proposal.votes_count == 1
        assert proposal.scores_total == 2.0

    @pytest.mark.asyncio
    async def test_record_vote_invalid_choice(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        ok = await adapter.record_vote(pid, "voter_1", "Invalid")
        assert ok is False

    @pytest.mark.asyncio
    async def test_record_vote_nonexistent_proposal(self):
        adapter = self._make_adapter()
        ok = await adapter.record_vote("nonexistent", "voter_1", "For")
        assert ok is False

    @pytest.mark.asyncio
    async def test_record_vote_empty_voter_raises(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        with pytest.raises(ValueError, match="voter"):
            await adapter.record_vote(pid, "", "For")

    @pytest.mark.asyncio
    async def test_record_vote_closed_proposal(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        adapter._proposals[pid].state = SnapshotProposalState.CLOSED
        ok = await adapter.record_vote(pid, "voter_1", "For")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_voting_analytics(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        await adapter.record_vote(pid, "v1", "For", 5.0)
        await adapter.record_vote(pid, "v2", "Against", 3.0)

        analytics = await adapter.get_voting_analytics(pid)
        assert analytics is not None
        assert analytics.total_votes == 2
        assert analytics.scores_by_choice["For"] == 5.0

    @pytest.mark.asyncio
    async def test_get_voting_analytics_cached(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        a1 = await adapter.get_voting_analytics(pid)
        a2 = await adapter.get_voting_analytics(pid)
        assert a1 is a2  # Same cached object

    @pytest.mark.asyncio
    async def test_get_voting_analytics_nonexistent(self):
        adapter = self._make_adapter()
        result = await adapter.get_voting_analytics("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_proposal_summary(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1",
            title="Security Fix",
            body="This is a security related change",
            author="0xabc",
        )
        summary = await adapter.get_proposal_summary(pid)
        assert summary is not None
        assert summary["risk_level"] == "high"
        assert summary["is_amendment"] is True

    @pytest.mark.asyncio
    async def test_get_proposal_summary_medium_risk(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1",
            title="Treasury Update",
            body="Adjust treasury fund allocation",
            author="0xabc",
        )
        summary = await adapter.get_proposal_summary(pid)
        assert summary["risk_level"] == "medium"

    @pytest.mark.asyncio
    async def test_get_proposal_summary_low_risk(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1",
            title="Minor Update",
            body="Small cosmetic change",
            author="0xabc",
        )
        summary = await adapter.get_proposal_summary(pid)
        assert summary["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_get_proposal_summary_nonexistent(self):
        adapter = self._make_adapter()
        result = await adapter.get_proposal_summary("nonexistent")
        assert result is None

    def test_get_active_proposals(self):
        adapter = self._make_adapter()
        assert adapter.get_active_proposals() == []

    def test_add_space(self):
        adapter = self._make_adapter()
        space = SnapshotSpace(space_id="ens.eth", name="ENS")
        adapter.add_space(space)
        assert "ens.eth" in adapter._spaces

    @pytest.mark.asyncio
    async def test_analytics_with_space(self):
        adapter = self._make_adapter()
        space = SnapshotSpace(space_id="test.eth", name="Test", follower_count=200)
        adapter.add_space(space)

        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        await adapter.record_vote(pid, "v1", "For")

        analytics = await adapter.get_voting_analytics(pid)
        assert analytics.participation_rate == pytest.approx(1 / 200)

    @pytest.mark.asyncio
    async def test_vote_invalidates_analytics_cache(self):
        adapter = self._make_adapter()
        pid = await adapter.submit_constitutional_amendment(
            amendment_id="a1", title="t", body="b", author="0xabc"
        )
        a1 = await adapter.get_voting_analytics(pid)
        await adapter.record_vote(pid, "v1", "For")
        a2 = await adapter.get_voting_analytics(pid)
        assert a1 is not a2
