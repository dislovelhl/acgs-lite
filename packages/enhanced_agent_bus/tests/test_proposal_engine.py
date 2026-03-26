"""
Tests for enhanced_agent_bus.constitutional.proposal_engine
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.constitutional.proposal_engine import (
    AmendmentProposalEngine,
    ProposalRequest,
    ProposalResponse,
    ProposalValidationError,
)

# ---------------------------------------------------------------------------
# ProposalRequest model
# ---------------------------------------------------------------------------


class TestProposalRequest:
    def test_valid_request(self):
        req = ProposalRequest(
            proposed_changes={"new_principle": "Be fair"},
            justification="This is a very good reason to change things",
            proposer_agent_id="agent_1",
        )
        assert req.proposer_agent_id == "agent_1"
        assert req.target_version is None
        assert req.metadata == {}

    def test_empty_proposed_changes_accepted_at_request_level(self):
        """ProposalRequest allows empty changes; AmendmentProposal validates non-empty."""
        req = ProposalRequest(
            proposed_changes={},
            justification="This is a very good reason to change things",
            proposer_agent_id="agent_1",
        )
        assert req.proposed_changes == {}

    def test_short_justification_rejected(self):
        with pytest.raises(ValidationError):
            ProposalRequest(
                proposed_changes={"a": 1},
                justification="short",
                proposer_agent_id="agent_1",
            )

    def test_invalid_version_format(self):
        with pytest.raises(ValidationError):
            ProposalRequest(
                proposed_changes={"a": 1},
                justification="This is a valid justification text",
                proposer_agent_id="agent_1",
                target_version="bad",
            )

    def test_valid_version_format(self):
        req = ProposalRequest(
            proposed_changes={"a": 1},
            justification="This is a valid justification text",
            proposer_agent_id="agent_1",
            target_version="1.2.3",
            new_version="1.3.0",
        )
        assert req.target_version == "1.2.3"
        assert req.new_version == "1.3.0"


# ---------------------------------------------------------------------------
# ProposalValidationError
# ---------------------------------------------------------------------------


class TestProposalValidationError:
    def test_is_exception(self):
        err = ProposalValidationError("test error")
        assert isinstance(err, Exception)
        assert "test error" in str(err)


# ---------------------------------------------------------------------------
# AmendmentProposalEngine helpers
# ---------------------------------------------------------------------------


def _mock_storage():
    storage = AsyncMock()
    storage.get_active_version = AsyncMock()
    storage.save_amendment = AsyncMock()
    storage.get_amendment = AsyncMock()
    return storage


def _mock_version(version="1.0.0", content=None):
    v = MagicMock()
    v.version = version
    v.version_id = "v_id_1"
    v.content = content or {"rules": ["be good"]}
    return v


def _make_engine(storage=None, enable_maci=False, enable_audit=False, **kwargs):
    storage = storage or _mock_storage()
    diff_engine = MagicMock()
    diff_engine.compute_diff = AsyncMock(return_value=None)
    impact_scorer = MagicMock()
    return AmendmentProposalEngine(
        storage=storage,
        diff_engine=diff_engine,
        impact_scorer=impact_scorer,
        enable_maci=enable_maci,
        enable_audit=enable_audit,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _merge_changes
# ---------------------------------------------------------------------------


class TestMergeChanges:
    def test_merge_adds_new_keys(self):
        engine = _make_engine()
        result = engine._merge_changes({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_merge_overwrites_existing(self):
        engine = _make_engine()
        result = engine._merge_changes({"a": 1}, {"a": 99})
        assert result == {"a": 99}

    def test_merge_does_not_mutate_base(self):
        engine = _make_engine()
        base = {"a": 1}
        engine._merge_changes(base, {"b": 2})
        assert "b" not in base


# ---------------------------------------------------------------------------
# _compute_next_version
# ---------------------------------------------------------------------------


class TestComputeNextVersion:
    def test_increments_minor(self):
        engine = _make_engine()
        assert engine._compute_next_version("1.0.0", {"x": 1}) == "1.1.0"

    def test_preserves_major_and_patch(self):
        engine = _make_engine()
        assert engine._compute_next_version("2.3.5", {"x": 1}) == "2.4.5"


# ---------------------------------------------------------------------------
# _validate_proposed_changes
# ---------------------------------------------------------------------------


class TestValidateProposedChanges:
    @pytest.mark.asyncio
    async def test_empty_changes_invalid(self):
        engine = _make_engine()
        version = _mock_version()
        result = await engine._validate_proposed_changes({}, version)
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_critical_field_modification_invalid(self):
        engine = _make_engine()
        version = _mock_version(content={"constitutional_hash": "abc", "rules": []})
        result = await engine._validate_proposed_changes(
            {"constitutional_hash": "new_hash"}, version
        )
        assert result["valid"] is False
        assert any("critical" in e.lower() for e in result["errors"])

    @pytest.mark.asyncio
    async def test_valid_changes(self):
        engine = _make_engine()
        version = _mock_version(content={"rules": ["be good"]})
        result = await engine._validate_proposed_changes({"new_section": "content"}, version)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# _compute_impact_score
# ---------------------------------------------------------------------------


class TestComputeImpactScore:
    @pytest.mark.asyncio
    async def test_basic_score(self):
        engine = _make_engine()
        version = _mock_version()
        analysis = await engine._compute_impact_score({"a": 1}, "test justification", version)
        assert 0.0 <= analysis.score <= 1.0

    @pytest.mark.asyncio
    async def test_principles_increase_score(self):
        engine = _make_engine()
        version = _mock_version()
        a1 = await engine._compute_impact_score({"x": 1}, "justification", version)
        a2 = await engine._compute_impact_score(
            {"principles": "new", "x": 1}, "justification", version
        )
        assert a2.score > a1.score

    @pytest.mark.asyncio
    async def test_enforcement_increases_score(self):
        engine = _make_engine()
        version = _mock_version()
        a1 = await engine._compute_impact_score({"x": 1}, "justification", version)
        a2 = await engine._compute_impact_score(
            {"enforcement": "strict", "x": 1}, "justification", version
        )
        assert a2.score > a1.score

    @pytest.mark.asyncio
    async def test_high_impact_requires_deliberation(self):
        engine = _make_engine()
        version = _mock_version()
        # principles + enforcement + many changes = high score
        changes = {f"k{i}": i for i in range(10)}
        changes["principles"] = "new"
        changes["enforcement"] = "strict"
        analysis = await engine._compute_impact_score(changes, "justification", version)
        assert analysis.requires_deliberation is True


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class TestSubmitForReview:
    @pytest.mark.asyncio
    async def test_proposal_not_found_raises(self):
        storage = _mock_storage()
        storage.get_amendment = AsyncMock(return_value=None)
        engine = _make_engine(storage=storage)

        with pytest.raises(ValueError, match="not found"):
            await engine.submit_for_review("nonexistent", "agent_1")

    @pytest.mark.asyncio
    async def test_non_proposed_raises(self):
        storage = _mock_storage()
        proposal = MagicMock()
        proposal.is_proposed = False
        proposal.status = "approved"
        proposal.proposal_id = "p1"
        storage.get_amendment = AsyncMock(return_value=proposal)
        engine = _make_engine(storage=storage)

        with pytest.raises(ValueError, match="cannot be submitted"):
            await engine.submit_for_review("p1", "agent_1")

    @pytest.mark.asyncio
    async def test_successful_submit(self):
        storage = _mock_storage()
        proposal = MagicMock()
        proposal.is_proposed = True
        proposal.proposal_id = "p1"
        storage.get_amendment = AsyncMock(return_value=proposal)
        engine = _make_engine(storage=storage)

        result = await engine.submit_for_review("p1", "agent_1")
        proposal.submit_for_review.assert_called_once()
        storage.save_amendment.assert_called_once()
        assert result is proposal


# ---------------------------------------------------------------------------
# validate_proposal
# ---------------------------------------------------------------------------


class TestValidateProposal:
    @pytest.mark.asyncio
    async def test_not_found(self):
        storage = _mock_storage()
        storage.get_amendment = AsyncMock(return_value=None)
        engine = _make_engine(storage=storage)

        result = await engine.validate_proposal("nonexistent")
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_target_version_mismatch(self):
        storage = _mock_storage()
        proposal = MagicMock()
        proposal.target_version = "1.0.0"
        proposal.proposed_changes = {"x": 1}
        storage.get_amendment = AsyncMock(return_value=proposal)
        storage.get_active_version = AsyncMock(return_value=_mock_version(version="2.0.0"))
        engine = _make_engine(storage=storage)

        result = await engine.validate_proposal("p1")
        assert result["valid"] is False
        assert any("no longer active" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_no_active_version(self):
        storage = _mock_storage()
        proposal = MagicMock()
        proposal.target_version = "1.0.0"
        storage.get_amendment = AsyncMock(return_value=proposal)
        storage.get_active_version = AsyncMock(return_value=None)
        engine = _make_engine(storage=storage)

        result = await engine.validate_proposal("p1")
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_valid_proposal(self):
        storage = _mock_storage()
        version = _mock_version(version="1.0.0", content={"rules": []})
        proposal = MagicMock()
        proposal.target_version = "1.0.0"
        proposal.proposed_changes = {"new_rule": "be nice"}
        storage.get_amendment = AsyncMock(return_value=proposal)
        storage.get_active_version = AsyncMock(return_value=version)
        engine = _make_engine(storage=storage)

        result = await engine.validate_proposal("p1")
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# get_proposal
# ---------------------------------------------------------------------------


class TestGetProposal:
    @pytest.mark.asyncio
    async def test_not_found(self):
        storage = _mock_storage()
        storage.get_amendment = AsyncMock(return_value=None)
        engine = _make_engine(storage=storage)

        result = await engine.get_proposal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_found_without_diff(self):
        storage = _mock_storage()
        proposal = MagicMock()
        proposal.to_dict.return_value = {"proposal_id": "p1"}
        storage.get_amendment = AsyncMock(return_value=proposal)
        engine = _make_engine(storage=storage)

        result = await engine.get_proposal("p1", include_diff=False)
        assert result is not None
        assert result["proposal"] == {"proposal_id": "p1"}


# ---------------------------------------------------------------------------
# list_proposals
# ---------------------------------------------------------------------------


class TestListProposals:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        engine = _make_engine()
        proposals = await engine.list_proposals()
        assert proposals == []


# ---------------------------------------------------------------------------
# _log_audit_event
# ---------------------------------------------------------------------------


class TestLogAuditEvent:
    @pytest.mark.asyncio
    async def test_disabled_audit_does_nothing(self):
        engine = _make_engine(enable_audit=False)
        # Should not raise
        await engine._log_audit_event("test", "agent_1", {})

    @pytest.mark.asyncio
    async def test_with_audit_client(self):
        audit_client = AsyncMock()
        engine = _make_engine(enable_audit=True, audit_client=audit_client)
        await engine._log_audit_event("test_event", "agent_1", {"key": "val"})
        audit_client.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_raise(self):
        audit_client = AsyncMock()
        audit_client.log_event = AsyncMock(side_effect=RuntimeError("audit down"))
        engine = _make_engine(enable_audit=True, audit_client=audit_client)
        # Should not raise
        await engine._log_audit_event("test_event", "agent_1", {})
