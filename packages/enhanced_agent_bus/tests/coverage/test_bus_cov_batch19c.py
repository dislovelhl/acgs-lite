"""
Coverage tests for:
  - enhanced_agent_bus.constitutional.proposal_engine
  - enhanced_agent_bus.constitutional.activation_saga
  - enhanced_agent_bus.observability.telemetry

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONST_HASH = "608508a9bd224290"


def _make_version(
    version: str = "1.0.0",
    status: str = "active",
    content: dict | None = None,
    version_id: str | None = None,
) -> ConstitutionalVersion:
    return ConstitutionalVersion(
        version_id=version_id or str(uuid4()),
        version=version,
        constitutional_hash=CONST_HASH,
        content=content or {"rules": "default"},
        status=status,
    )


def _make_amendment(
    target_version: str = "1.0.0",
    status: AmendmentStatus = AmendmentStatus.PROPOSED,
    proposed_changes: dict | None = None,
    new_version: str | None = "1.1.0",
) -> AmendmentProposal:
    return AmendmentProposal(
        proposed_changes=proposed_changes or {"new_rule": "value"},
        justification="A sufficiently long justification for testing",
        proposer_agent_id="agent-test-1",
        target_version=target_version,
        new_version=new_version,
        status=status,
        impact_score=0.5,
    )


def _mock_storage(
    active_version: ConstitutionalVersion | None = None,
    amendment: AmendmentProposal | None = None,
) -> AsyncMock:
    storage = AsyncMock()
    storage.get_active_version = AsyncMock(return_value=active_version)
    storage.get_amendment = AsyncMock(return_value=amendment)
    storage.save_amendment = AsyncMock()
    storage.save_version = AsyncMock()
    storage.get_version = AsyncMock(return_value=active_version)
    storage.activate_version = AsyncMock()
    return storage


# ===================================================================
# proposal_engine tests
# ===================================================================


class TestProposalValidationError:
    def test_error_attributes(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            ProposalValidationError,
        )

        err = ProposalValidationError("bad input")
        assert err.http_status_code == 400
        assert err.error_code == "PROPOSAL_VALIDATION_ERROR"
        assert "bad input" in str(err)


class TestProposalRequest:
    def test_valid_request(self):
        from enhanced_agent_bus.constitutional.proposal_engine import ProposalRequest

        req = ProposalRequest(
            proposed_changes={"x": 1},
            justification="This is a valid justification text",
            proposer_agent_id="agent-1",
        )
        assert req.proposer_agent_id == "agent-1"
        assert req.target_version is None
        assert req.new_version is None
        assert req.metadata == {}

    def test_version_pattern(self):
        from enhanced_agent_bus.constitutional.proposal_engine import ProposalRequest

        req = ProposalRequest(
            proposed_changes={"x": 1},
            justification="This is a valid justification text",
            proposer_agent_id="agent-1",
            target_version="2.3.4",
            new_version="2.4.0",
        )
        assert req.target_version == "2.3.4"

    def test_invalid_version_pattern(self):
        from enhanced_agent_bus.constitutional.proposal_engine import ProposalRequest

        with pytest.raises(ValidationError):
            ProposalRequest(
                proposed_changes={"x": 1},
                justification="This is a valid justification text",
                proposer_agent_id="agent-1",
                target_version="bad",
            )


class TestProposalResponse:
    def test_basic_response(self):
        from enhanced_agent_bus.constitutional.proposal_engine import ProposalResponse

        amendment = _make_amendment()
        resp = ProposalResponse(
            proposal=amendment,
            diff_preview=None,
            validation_results={"valid": True},
        )
        assert resp.proposal.proposal_id == amendment.proposal_id
        assert resp.diff_preview is None


class TestAmendmentProposalEngine:
    """Tests for AmendmentProposalEngine."""

    def _make_engine(self, storage=None, **kwargs):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        s = storage or _mock_storage()
        return AmendmentProposalEngine(
            storage=s,
            diff_engine=MagicMock(),
            impact_scorer=MagicMock(),
            enable_maci=False,
            enable_audit=False,
            **kwargs,
        )

    def test_init_defaults(self):
        engine = self._make_engine()
        assert engine.enable_maci is False
        assert engine.enable_audit is False

    def test_init_with_audit_enabled_no_client(self):
        """When audit enabled but no client, it tries to create one."""
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        storage = _mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=True,
            audit_client=None,
        )
        # audit_client is either set or enable_audit is False (fallback)
        assert engine.audit_client is not None or engine.enable_audit is False

    def test_merge_changes(self):
        engine = self._make_engine()
        result = engine._merge_changes({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_compute_next_version(self):
        engine = self._make_engine()
        assert engine._compute_next_version("1.0.0", {"x": 1}) == "1.1.0"
        assert engine._compute_next_version("3.5.2", {}) == "3.6.2"

    async def test_validate_proposed_changes_empty(self):
        engine = self._make_engine()
        active = _make_version()
        result = await engine._validate_proposed_changes({}, active)
        assert result["valid"] is False
        assert any("empty" in e.lower() for e in result["errors"])

    async def test_validate_proposed_changes_critical_fields(self):
        engine = self._make_engine()
        active = _make_version(content={"constitutional_hash": "abc", "version": "1.0"})
        result = await engine._validate_proposed_changes({"constitutional_hash": "new"}, active)
        assert result["valid"] is False
        assert any("critical" in e.lower() for e in result["errors"])

    async def test_validate_proposed_changes_valid(self):
        engine = self._make_engine()
        active = _make_version(content={"rules": "x"})
        result = await engine._validate_proposed_changes({"new_rule": "y"}, active)
        assert result["valid"] is True
        assert result["errors"] == []

    async def test_compute_impact_score_basic(self):
        engine = self._make_engine()
        active = _make_version()
        result = await engine._compute_impact_score({"a": 1}, "justification", active)
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.factors, dict)

    async def test_compute_impact_score_with_principles(self):
        engine = self._make_engine()
        active = _make_version()
        result = await engine._compute_impact_score(
            {"principles": "new", "enforcement": "strict"},
            "justification text here",
            active,
        )
        assert result.score >= 0.5
        assert result.factors.get("principles_modified", 0) > 0

    async def test_compute_impact_score_high_triggers_deliberation(self):
        engine = self._make_engine()
        active = _make_version()
        # Many changes + principles + enforcement = high score
        changes = {f"key{i}": i for i in range(10)}
        changes["principles"] = "x"
        changes["enforcement"] = "y"
        result = await engine._compute_impact_score(changes, "just", active)
        assert result.requires_deliberation is True

    async def test_generate_diff_preview_success(self):
        engine = self._make_engine()
        diff_mock = MagicMock()
        engine.diff_engine.compute_diff = AsyncMock(return_value=diff_mock)
        v1 = _make_version()
        v2 = _make_version(version="1.1.0")
        result = await engine._generate_diff_preview(v1, v2)
        assert result is diff_mock

    async def test_generate_diff_preview_error(self):
        engine = self._make_engine()
        engine.diff_engine.compute_diff = AsyncMock(side_effect=RuntimeError("fail"))
        v1 = _make_version()
        v2 = _make_version(version="1.1.0")
        result = await engine._generate_diff_preview(v1, v2)
        assert result is None

    async def test_log_audit_event_disabled(self):
        engine = self._make_engine()
        engine.enable_audit = False
        # Should not raise
        await engine._log_audit_event("test", "agent-1", {"key": "val"})

    async def test_log_audit_event_enabled(self):
        engine = self._make_engine()
        engine.enable_audit = True
        engine.audit_client = AsyncMock()
        engine.audit_client.log_event = AsyncMock()
        await engine._log_audit_event("test_event", "agent-1", {"k": "v"})
        engine.audit_client.log_event.assert_awaited_once()

    async def test_log_audit_event_error_swallowed(self):
        engine = self._make_engine()
        engine.enable_audit = True
        engine.audit_client = AsyncMock()
        engine.audit_client.log_event = AsyncMock(side_effect=RuntimeError("oops"))
        # Should not raise
        await engine._log_audit_event("test_event", "agent-1", {})

    async def test_submit_for_review_not_found(self):
        storage = _mock_storage(amendment=None)
        engine = self._make_engine(storage=storage)
        with pytest.raises(ValueError, match="not found"):
            await engine.submit_for_review("missing-id", "agent-1")

    async def test_submit_for_review_wrong_status(self):
        amendment = _make_amendment(status=AmendmentStatus.APPROVED)
        storage = _mock_storage(amendment=amendment)
        engine = self._make_engine(storage=storage)
        with pytest.raises(ValueError, match="cannot be submitted"):
            await engine.submit_for_review(amendment.proposal_id, "agent-1")

    async def test_submit_for_review_success(self):
        amendment = _make_amendment(status=AmendmentStatus.PROPOSED)
        storage = _mock_storage(amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.submit_for_review(amendment.proposal_id, "agent-1")
        assert result.status == AmendmentStatus.UNDER_REVIEW
        storage.save_amendment.assert_awaited_once()

    async def test_submit_for_review_with_audit(self):
        amendment = _make_amendment(status=AmendmentStatus.PROPOSED)
        storage = _mock_storage(amendment=amendment)
        engine = self._make_engine(storage=storage)
        engine.enable_audit = True
        engine.audit_client = AsyncMock()
        engine.audit_client.log_event = AsyncMock()
        await engine.submit_for_review(amendment.proposal_id, "agent-1")
        engine.audit_client.log_event.assert_awaited_once()

    async def test_validate_proposal_not_found(self):
        storage = _mock_storage(amendment=None)
        engine = self._make_engine(storage=storage)
        result = await engine.validate_proposal("missing")
        assert result["valid"] is False
        assert any("not found" in e.lower() for e in result["errors"])

    async def test_validate_proposal_version_mismatch(self):
        amendment = _make_amendment(target_version="2.0.0")
        active = _make_version(version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.validate_proposal(amendment.proposal_id)
        assert result["valid"] is False
        assert any("no longer active" in e.lower() for e in result["errors"])

    async def test_validate_proposal_success(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(target_version="1.0.0", proposed_changes={"new_rule": "y"})
        storage = _mock_storage(active_version=active, amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.validate_proposal(amendment.proposal_id)
        assert result["valid"] is True

    async def test_validate_proposal_no_active_version(self):
        amendment = _make_amendment(target_version="1.0.0")
        storage = _mock_storage(active_version=None, amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.validate_proposal(amendment.proposal_id)
        assert result["valid"] is False

    async def test_get_proposal_not_found(self):
        storage = _mock_storage(amendment=None)
        engine = self._make_engine(storage=storage)
        result = await engine.get_proposal("missing")
        assert result is None

    async def test_get_proposal_without_diff(self):
        amendment = _make_amendment()
        storage = _mock_storage(amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.get_proposal(amendment.proposal_id, include_diff=False)
        assert result is not None
        assert "proposal" in result
        assert "diff_preview" not in result

    async def test_get_proposal_with_diff(self):
        active = _make_version(content={"rules": "x"})
        amendment = _make_amendment()
        storage = _mock_storage(active_version=active, amendment=amendment)
        engine = self._make_engine(storage=storage)
        diff_mock = MagicMock()
        diff_mock.model_dump.return_value = {"changes": []}
        engine.diff_engine.compute_diff = AsyncMock(return_value=diff_mock)
        result = await engine.get_proposal(amendment.proposal_id, include_diff=True)
        assert result is not None
        assert "diff_preview" in result

    async def test_get_proposal_with_diff_no_active_version(self):
        amendment = _make_amendment()
        storage = _mock_storage(active_version=None, amendment=amendment)
        engine = self._make_engine(storage=storage)
        result = await engine.get_proposal(amendment.proposal_id, include_diff=True)
        assert result is not None
        assert "diff_preview" not in result

    async def test_list_proposals_empty(self):
        engine = self._make_engine()
        result = await engine.list_proposals()
        assert result == []

    async def test_list_proposals_with_audit(self):
        engine = self._make_engine()
        engine.enable_audit = True
        engine.audit_client = AsyncMock()
        engine.audit_client.log_event = AsyncMock()
        result = await engine.list_proposals(status=AmendmentStatus.PROPOSED)
        assert result == []
        engine.audit_client.log_event.assert_awaited_once()

    async def test_list_proposals_with_filters(self):
        engine = self._make_engine()
        result = await engine.list_proposals(
            status=AmendmentStatus.APPROVED,
            proposer_agent_id="agent-1",
            limit=10,
            offset=5,
        )
        assert result == []

    async def test_create_proposal_invariant_unavailable(self):
        """When invariant imports unavailable, proposals are blocked (fail-closed)."""
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
            ProposalValidationError,
        )

        active = _make_version(content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            False,
        ):
            with pytest.raises(ProposalValidationError, match="fail-closed"):
                await engine.create_proposal(request)

    async def test_create_proposal_maci_violation(self):
        """MACI enforcer rejects unauthorized agent."""
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        maci = AsyncMock()
        maci.validate_action = AsyncMock(return_value={"allowed": False})

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            maci_enforcer=maci,
            enable_maci=True,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-bad",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            with pytest.raises(ValueError, match="MACI violation"):
                await engine.create_proposal(request)

    async def test_create_proposal_maci_violation_with_audit(self):
        """MACI violation also logs audit event."""
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        maci = AsyncMock()
        maci.validate_action = AsyncMock(return_value={"allowed": False})
        audit = AsyncMock()
        audit.log_event = AsyncMock()

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            maci_enforcer=maci,
            audit_client=audit,
            enable_maci=True,
            enable_audit=True,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-bad",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            with pytest.raises(ValueError, match="MACI violation"):
                await engine.create_proposal(request)
        audit.log_event.assert_awaited_once()

    async def test_create_proposal_no_active_version(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
            ProposalValidationError,
        )

        storage = _mock_storage(active_version=None)
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            with pytest.raises(ProposalValidationError, match="No active"):
                await engine.create_proposal(request)

    async def test_create_proposal_version_mismatch(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
            ProposalValidationError,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
            target_version="2.0.0",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            with pytest.raises(ProposalValidationError, match="does not match"):
                await engine.create_proposal(request)

    async def test_create_proposal_invalid_changes(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
            ProposalValidationError,
        )

        active = _make_version(
            version="1.0.0",
            content={"constitutional_hash": "old", "version": "1.0"},
        )
        storage = _mock_storage(active_version=active)
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"constitutional_hash": "new"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
            target_version="1.0.0",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            with pytest.raises(ProposalValidationError, match="Invalid proposal"):
                await engine.create_proposal(request)

    async def test_create_proposal_success(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        diff_engine = MagicMock()
        diff_engine.compute_diff = AsyncMock(return_value=None)

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=diff_engine,
            enable_maci=False,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            response = await engine.create_proposal(request)

        assert response.proposal.status == AmendmentStatus.PROPOSED
        assert response.proposal.proposer_agent_id == "agent-1"
        storage.save_amendment.assert_awaited_once()

    async def test_create_proposal_with_audit(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        diff_engine = MagicMock()
        diff_engine.compute_diff = AsyncMock(return_value=None)
        audit = AsyncMock()
        audit.log_event = AsyncMock()

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=diff_engine,
            audit_client=audit,
            enable_maci=False,
            enable_audit=True,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            await engine.create_proposal(request)

        audit.log_event.assert_awaited_once()

    async def test_create_proposal_maci_passes(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        diff_engine = MagicMock()
        diff_engine.compute_diff = AsyncMock(return_value=None)
        maci = AsyncMock()
        maci.validate_action = AsyncMock(return_value={"allowed": True})

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=diff_engine,
            maci_enforcer=maci,
            enable_maci=True,
            enable_audit=False,
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            response = await engine.create_proposal(request)

        assert response.proposal.status == AmendmentStatus.PROPOSED

    async def test_create_proposal_with_invariant_validator(self):
        """Invariant validator passes with classification."""
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        diff_engine = MagicMock()
        diff_engine.compute_diff = AsyncMock(return_value=None)

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=diff_engine,
            enable_maci=False,
            enable_audit=False,
        )

        classification = SimpleNamespace(
            touches_invariants=True,
            touched_invariant_ids=["inv-1"],
            requires_refoundation=False,
            reason="touches tier-2 invariant",
        )
        validator = MagicMock()
        validator.invariant_hash = "abc123"
        validator.validate_proposal = AsyncMock(return_value=classification)

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=validator)
            response = await engine.create_proposal(request)

        assert response.proposal.invariant_hash == "abc123"
        assert "inv-1" in response.proposal.invariant_impact

    def test_get_invariant_validator_none_when_not_available(self):
        engine = self._make_engine()
        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine.ProposalInvariantValidator",
            None,
        ):
            result = engine._get_invariant_validator()
        assert result is None

    def test_get_invariant_validator_init_error(self):
        engine = self._make_engine()
        mock_validator_cls = MagicMock(side_effect=RuntimeError("init fail"))
        mock_manifest = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine.ProposalInvariantValidator",
                mock_validator_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine.get_default_manifest",
                mock_manifest,
            ),
        ):
            result = engine._get_invariant_validator()
        assert result is None


# ===================================================================
# activation_saga tests
# ===================================================================


class TestActivationSagaError:
    def test_error_attributes(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        err = ActivationSagaError("saga failed")
        assert err.http_status_code == 500
        assert err.error_code == "ACTIVATION_SAGA_ERROR"


class TestActivationSagaActivities:
    def _make_activities(self, storage=None):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaActivities,
        )

        s = storage or _mock_storage()
        return ActivationSagaActivities(
            storage=s,
            opa_url="http://localhost:8181",
            audit_service_url="http://localhost:8001",
            redis_url="redis://localhost:6379",
        )

    def test_compute_constitutional_hash(self):
        activities = self._make_activities()
        content = {"rules": "test", "version": "1.0"}
        expected = hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()
        assert activities._compute_constitutional_hash(content) == expected

    def test_compute_constitutional_hash_deterministic(self):
        activities = self._make_activities()
        content = {"b": 2, "a": 1}
        h1 = activities._compute_constitutional_hash(content)
        h2 = activities._compute_constitutional_hash({"a": 1, "b": 2})
        assert h1 == h2

    async def test_initialize_no_redis_no_opa(self):
        """Initialize without Redis/OPA available."""
        activities = self._make_activities()
        with (
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.REDIS_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.OPAClient",
                None,
            ),
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.AuditClient",
                None,
            ),
        ):
            await activities.initialize()
        assert activities._http_client is not None
        assert activities._redis_client is None
        await activities.close()

    async def test_close_all_none(self):
        activities = self._make_activities()
        activities._http_client = None
        activities._redis_client = None
        activities._opa_client = None
        activities._audit_client = None
        await activities.close()  # should not raise

    async def test_close_with_clients(self):
        activities = self._make_activities()
        activities._http_client = AsyncMock()
        activities._redis_client = AsyncMock()
        activities._opa_client = AsyncMock()
        activities._audit_client = AsyncMock()
        await activities.close()
        activities._http_client.aclose.assert_awaited_once()
        activities._redis_client.close.assert_awaited_once()
        activities._opa_client.close.assert_awaited_once()
        activities._audit_client.stop.assert_awaited_once()

    async def test_validate_activation_missing_amendment_id(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        activities = self._make_activities()
        with pytest.raises(ActivationSagaError, match="Missing amendment_id"):
            await activities.validate_activation({"saga_id": "s1", "context": {}})

    async def test_validate_activation_amendment_not_found(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        storage = _mock_storage(amendment=None)
        activities = self._make_activities(storage=storage)
        with pytest.raises(ActivationSagaError, match="not found"):
            await activities.validate_activation(
                {"saga_id": "s1", "context": {"amendment_id": "a1"}}
            )

    async def test_validate_activation_not_approved(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        amendment = _make_amendment(status=AmendmentStatus.PROPOSED)
        storage = _mock_storage(amendment=amendment)
        activities = self._make_activities(storage=storage)
        with pytest.raises(ActivationSagaError, match="not approved"):
            await activities.validate_activation(
                {"saga_id": "s1", "context": {"amendment_id": "a1"}}
            )

    async def test_validate_activation_success(self):
        active = _make_version(version="1.0.0")
        amendment = _make_amendment(status=AmendmentStatus.APPROVED, target_version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)

        result = await activities.validate_activation(
            {"saga_id": "s1", "context": {"amendment_id": "a1"}}
        )
        assert result["is_valid"] is True
        assert result["amendment_id"] == "a1"

    async def test_validate_activation_inactive_target(self):
        """Target version not matching active version logs warning."""
        active = _make_version(version="1.0.0", version_id="v-active")
        target = _make_version(version="1.0.0", version_id="v-target")
        amendment = _make_amendment(status=AmendmentStatus.APPROVED, target_version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=target)
        activities = self._make_activities(storage=storage)

        result = await activities.validate_activation(
            {"saga_id": "s1", "context": {"amendment_id": "a1"}}
        )
        assert result["is_valid"] is True

    async def test_log_validation_failure(self):
        activities = self._make_activities()
        result = await activities.log_validation_failure({"saga_id": "s1", "context": {}})
        assert result is True

    async def test_backup_current_version(self):
        active = _make_version(version="1.0.0")
        storage = _mock_storage(active_version=active)
        activities = self._make_activities(storage=storage)

        result = await activities.backup_current_version({"saga_id": "s1", "context": {}})
        assert result["version"] == "1.0.0"
        assert "backup_id" in result

    async def test_backup_no_active_version(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        storage = _mock_storage(active_version=None)
        activities = self._make_activities(storage=storage)
        with pytest.raises(ActivationSagaError, match="No active"):
            await activities.backup_current_version({"saga_id": "s1", "context": {}})

    async def test_restore_backup_success(self):
        storage = _mock_storage()
        activities = self._make_activities(storage=storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {"version_id": "v-1"},
                },
            }
        )
        assert result is True
        storage.activate_version.assert_awaited_once_with("v-1")

    async def test_restore_backup_no_data(self):
        activities = self._make_activities()
        result = await activities.restore_backup({"saga_id": "s1", "context": {}})
        assert result is False

    async def test_restore_backup_error(self):
        storage = _mock_storage()
        storage.activate_version = AsyncMock(side_effect=RuntimeError("fail"))
        activities = self._make_activities(storage=storage)
        result = await activities.restore_backup(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {"version_id": "v-1"},
                },
            }
        )
        assert result is False

    async def test_update_opa_policies_no_http_client(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(
            status=AmendmentStatus.APPROVED,
            target_version="1.0.0",
            proposed_changes={"new": "rule"},
        )
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)
        activities._http_client = None

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["updated"] is True
        assert "new_hash" in result

    async def test_update_opa_policies_with_http(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(
            status=AmendmentStatus.APPROVED,
            target_version="1.0.0",
        )
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        activities._http_client = mock_client

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["updated"] is True
        mock_client.put.assert_awaited_once()

    async def test_update_opa_policies_http_error(self):
        """HTTP error during OPA update continues without raising."""
        import httpx

        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(
            status=AmendmentStatus.APPROVED,
            target_version="1.0.0",
        )
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)

        mock_client = AsyncMock()
        mock_client.put = AsyncMock(
            side_effect=httpx.RequestError("conn failed", request=MagicMock())
        )
        activities._http_client = mock_client

        result = await activities.update_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["updated"] is True

    async def test_update_opa_amendment_not_found(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        storage = _mock_storage(amendment=None)
        activities = self._make_activities(storage=storage)
        with pytest.raises(ActivationSagaError, match="not found"):
            await activities.update_opa_policies(
                {
                    "saga_id": "s1",
                    "context": {
                        "validate_activation": {"new_version": "1.1.0"},
                        "amendment_id": "a1",
                    },
                }
            )

    async def test_update_opa_target_version_not_found(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            ActivationSagaError,
        )

        amendment = _make_amendment(status=AmendmentStatus.APPROVED)
        storage = _mock_storage(amendment=amendment)
        storage.get_version = AsyncMock(return_value=None)
        activities = self._make_activities(storage=storage)
        with pytest.raises(ActivationSagaError, match="Target version not found"):
            await activities.update_opa_policies(
                {
                    "saga_id": "s1",
                    "context": {
                        "validate_activation": {"new_version": "1.1.0"},
                        "amendment_id": "a1",
                    },
                }
            )

    async def test_revert_opa_no_http_client(self):
        activities = self._make_activities()
        activities._http_client = None
        result = await activities.revert_opa_policies(
            {"saga_id": "s1", "context": {"backup_current_version": {}}}
        )
        assert result is True

    async def test_revert_opa_success(self):
        activities = self._make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        activities._http_client = mock_client

        result = await activities.revert_opa_policies(
            {
                "saga_id": "s1",
                "context": {
                    "backup_current_version": {
                        "constitutional_hash": "old_hash",
                        "version": "0.9.0",
                    },
                },
            }
        )
        assert result is True

    async def test_revert_opa_failure_status(self):
        activities = self._make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        activities._http_client = mock_client

        result = await activities.revert_opa_policies(
            {"saga_id": "s1", "context": {"backup_current_version": {}}}
        )
        assert result is False

    async def test_revert_opa_exception(self):
        import httpx

        activities = self._make_activities()
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(side_effect=httpx.RequestError("fail", request=MagicMock()))
        activities._http_client = mock_client

        result = await activities.revert_opa_policies(
            {"saga_id": "s1", "context": {"backup_current_version": {}}}
        )
        assert result is False

    async def test_update_cache_no_redis(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(status=AmendmentStatus.APPROVED, target_version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)
        activities._redis_client = None
        # Mock _compute_constitutional_hash to return a valid 16-char hex
        activities._compute_constitutional_hash = MagicMock(return_value=CONST_HASH)

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is False
        storage.save_version.assert_awaited_once()
        storage.activate_version.assert_awaited_once()

    async def test_update_cache_with_redis(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(status=AmendmentStatus.APPROVED, target_version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONST_HASH)

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        activities._redis_client = mock_redis

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is True
        mock_redis.delete.assert_awaited_once()

    async def test_update_cache_redis_error(self):
        active = _make_version(version="1.0.0", content={"rules": "x"})
        amendment = _make_amendment(status=AmendmentStatus.APPROVED, target_version="1.0.0")
        storage = _mock_storage(active_version=active, amendment=amendment)
        storage.get_version = AsyncMock(return_value=active)
        activities = self._make_activities(storage=storage)
        activities._compute_constitutional_hash = MagicMock(return_value=CONST_HASH)

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=OSError("redis down"))
        activities._redis_client = mock_redis

        result = await activities.update_cache(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["activated"] is True
        assert result["cache_invalidated"] is False

    async def test_revert_cache_no_redis(self):
        activities = self._make_activities()
        activities._redis_client = None
        result = await activities.revert_cache({"saga_id": "s1"})
        assert result is True

    async def test_revert_cache_success(self):
        activities = self._make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        activities._redis_client = mock_redis
        result = await activities.revert_cache({"saga_id": "s1"})
        assert result is True

    async def test_revert_cache_error(self):
        activities = self._make_activities()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=OSError("fail"))
        activities._redis_client = mock_redis
        result = await activities.revert_cache({"saga_id": "s1"})
        assert result is False

    async def test_audit_activation(self):
        activities = self._make_activities()
        activities._audit_client = None

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {"new_version": "1.1.0"},
                    "backup_current_version": {"version": "1.0.0", "version_id": "v0"},
                    "update_cache": {"new_version_id": "v1"},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["event_type"] == "constitutional_version_activated"
        assert result["amendment_id"] == "a1"

    async def test_audit_activation_with_client(self):
        activities = self._make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock()
        activities._audit_client = mock_audit

        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {},
                    "backup_current_version": {},
                    "update_cache": {},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["event_type"] == "constitutional_version_activated"
        mock_audit.log.assert_awaited_once()

    async def test_audit_activation_client_error(self):
        activities = self._make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=RuntimeError("audit fail"))
        activities._audit_client = mock_audit

        # Should not raise
        result = await activities.audit_activation(
            {
                "saga_id": "s1",
                "context": {
                    "validate_activation": {},
                    "backup_current_version": {},
                    "update_cache": {},
                    "amendment_id": "a1",
                },
            }
        )
        assert result["event_type"] == "constitutional_version_activated"

    async def test_mark_audit_failed(self):
        activities = self._make_activities()
        activities._audit_client = None

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {
                    "audit_activation": {"audit_id": "aud-1"},
                },
            }
        )
        assert result is True

    async def test_mark_audit_failed_with_client(self):
        activities = self._make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock()
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {
                    "audit_activation": {"audit_id": "aud-1"},
                },
            }
        )
        assert result is True
        mock_audit.log.assert_awaited_once()

    async def test_mark_audit_failed_client_error(self):
        activities = self._make_activities()
        mock_audit = AsyncMock()
        mock_audit.log = AsyncMock(side_effect=OSError("fail"))
        activities._audit_client = mock_audit

        result = await activities.mark_audit_failed(
            {
                "saga_id": "s1",
                "context": {
                    "audit_activation": {},
                },
            }
        )
        assert result is True

    async def test_mark_audit_failed_no_context(self):
        activities = self._make_activities()
        activities._audit_client = None
        result = await activities.mark_audit_failed({"saga_id": "s1", "context": {}})
        assert result is True


class TestCreateActivationSaga:
    def test_raises_when_saga_workflow_unavailable(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            create_activation_saga,
        )

        storage = _mock_storage()
        with patch(
            "enhanced_agent_bus.constitutional.activation_saga.ConstitutionalSagaWorkflow",
            None,
        ):
            with pytest.raises(ImportError):
                create_activation_saga("a1", storage)

    def test_creates_saga_when_available(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            create_activation_saga,
        )

        mock_saga = MagicMock()
        mock_saga.saga_id = "test-saga"
        mock_step_cls = MagicMock()
        mock_comp_cls = MagicMock()

        storage = _mock_storage()
        with (
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.ConstitutionalSagaWorkflow",
                MagicMock(return_value=mock_saga),
            ),
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.SagaStep",
                mock_step_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.SagaCompensation",
                mock_comp_cls,
            ),
        ):
            saga = create_activation_saga("a1", storage)
        assert saga is mock_saga
        assert mock_saga.add_step.call_count == 5


class TestActivateAmendment:
    async def test_raises_when_saga_context_unavailable(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            activate_amendment,
        )

        storage = _mock_storage()
        with patch(
            "enhanced_agent_bus.constitutional.activation_saga.SagaContext",
            None,
        ):
            with pytest.raises(ImportError):
                await activate_amendment("a1", storage)

    async def test_calls_saga_execute(self):
        from enhanced_agent_bus.constitutional.activation_saga import (
            activate_amendment,
        )

        mock_saga = MagicMock()
        mock_saga.saga_id = "test-saga"
        mock_saga._steps = []
        mock_result = MagicMock()
        mock_saga.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.set_step_result = MagicMock()

        storage = _mock_storage()
        with (
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.create_activation_saga",
                return_value=mock_saga,
            ),
            patch(
                "enhanced_agent_bus.constitutional.activation_saga.SagaContext",
                MagicMock(return_value=mock_context),
            ),
        ):
            result = await activate_amendment("a1", storage)
        assert result is mock_result


# ===================================================================
# telemetry tests
# ===================================================================


class TestNoOpSpan:
    def test_set_attribute(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.set_attribute("key", "value")  # no-op

    def test_add_event(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.add_event("event", attributes={"k": "v"})

    def test_record_exception(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.record_exception(RuntimeError("test"))

    def test_set_status(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.set_status("OK")

    def test_context_manager(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        with span as s:
            assert s is span
        # __exit__ returns False
        assert span.__exit__(None, None, None) is False


class TestNoOpTracer:
    def test_start_as_current_span(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan, NoOpTracer

        tracer = NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            assert isinstance(span, NoOpSpan)

    def test_start_span(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan, NoOpTracer

        tracer = NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, NoOpSpan)


class TestNoOpCounter:
    def test_add(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        counter = NoOpCounter()
        counter.add(5)
        counter.add(1, attributes={"key": "value"})


class TestNoOpHistogram:
    def test_record(self):
        from enhanced_agent_bus.observability.telemetry import NoOpHistogram

        histogram = NoOpHistogram()
        histogram.record(5.0)
        histogram.record(1.0, attributes={"key": "value"})


class TestNoOpUpDownCounter:
    def test_add(self):
        from enhanced_agent_bus.observability.telemetry import NoOpUpDownCounter

        counter = NoOpUpDownCounter()
        counter.add(1)
        counter.add(-1, attributes={"key": "value"})


class TestNoOpMeter:
    def test_create_counter(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter, NoOpMeter

        meter = NoOpMeter()
        counter = meter.create_counter("test")
        assert isinstance(counter, NoOpCounter)

    def test_create_histogram(self):
        from enhanced_agent_bus.observability.telemetry import (
            NoOpHistogram,
            NoOpMeter,
        )

        meter = NoOpMeter()
        histogram = meter.create_histogram("test")
        assert isinstance(histogram, NoOpHistogram)

    def test_create_up_down_counter(self):
        from enhanced_agent_bus.observability.telemetry import (
            NoOpMeter,
            NoOpUpDownCounter,
        )

        meter = NoOpMeter()
        counter = meter.create_up_down_counter("test")
        assert isinstance(counter, NoOpUpDownCounter)

    def test_create_observable_gauge(self):
        from enhanced_agent_bus.observability.telemetry import NoOpMeter

        meter = NoOpMeter()
        result = meter.create_observable_gauge("test", callbacks=None)
        assert result is None


class TestCrossModuleNoOpType:
    def test_same_class_isinstance(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        counter = NoOpCounter()
        assert isinstance(counter, NoOpCounter)

    def test_cross_module_isinstance(self):
        from enhanced_agent_bus.observability.telemetry import _CrossModuleNoOpType

        # Create a fake class that mimics a cross-module import
        FakeCounter = _CrossModuleNoOpType(
            "NoOpCounter", (), {"add": lambda self, amount, attrs=None: None}
        )

        # Create instance from different module path ending with .observability.telemetry
        class FakeModule:
            pass

        fake_instance = FakeCounter()
        fake_instance.__class__ = type(
            "NoOpCounter",
            (),
            {"__module__": "some.other.observability.telemetry"},
        )
        # The metaclass should match on name + module suffix
        assert isinstance(fake_instance, FakeCounter)


class TestTelemetryConfig:
    def test_defaults(self):
        from enhanced_agent_bus.observability.telemetry import TelemetryConfig

        config = TelemetryConfig()
        assert config.service_name == "acgs2-agent-bus"
        assert config.service_version == "2.0.0"
        assert config.batch_span_processor is True
        assert config.constitutional_hash == CONST_HASH

    def test_custom_values(self):
        from enhanced_agent_bus.observability.telemetry import TelemetryConfig

        config = TelemetryConfig(
            service_name="custom-service",
            service_version="3.0.0",
            otlp_endpoint="http://custom:4317",
            export_traces=False,
            export_metrics=False,
            trace_sample_rate=0.5,
        )
        assert config.service_name == "custom-service"
        assert config.export_traces is False


class TestConfigHelpers:
    def test_get_env_default_no_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_env_default

        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            result = _get_env_default()
        assert isinstance(result, str)

    def test_get_env_default_with_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_env_default

        mock_settings = MagicMock()
        mock_settings.env = "production"
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_env_default() == "production"

    def test_get_otlp_endpoint_no_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_otlp_endpoint

        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            result = _get_otlp_endpoint()
        assert isinstance(result, str)

    def test_get_otlp_endpoint_with_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_otlp_endpoint

        mock_settings = MagicMock()
        mock_settings.telemetry.otlp_endpoint = "http://custom:4317"
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_otlp_endpoint() == "http://custom:4317"

    def test_get_export_traces_no_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_export_traces

        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_export_traces() is True

    def test_get_export_traces_with_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_export_traces

        mock_settings = MagicMock()
        mock_settings.telemetry.export_traces = False
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_export_traces() is False

    def test_get_export_metrics_no_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_export_metrics

        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_export_metrics() is True

    def test_get_export_metrics_with_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_export_metrics

        mock_settings = MagicMock()
        mock_settings.telemetry.export_metrics = False
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_export_metrics() is False

    def test_get_trace_sample_rate_no_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_trace_sample_rate

        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_trace_sample_rate() == 1.0

    def test_get_trace_sample_rate_with_settings(self):
        from enhanced_agent_bus.observability.telemetry import _get_trace_sample_rate

        mock_settings = MagicMock()
        mock_settings.telemetry.trace_sample_rate = 0.25
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_trace_sample_rate() == 0.25


class TestConfigureTelemetry:
    def test_returns_noop_when_otel_unavailable(self):
        from enhanced_agent_bus.observability.telemetry import (
            NoOpMeter,
            NoOpTracer,
            configure_telemetry,
        )

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer, meter = configure_telemetry()
        assert isinstance(tracer, NoOpTracer)
        assert isinstance(meter, NoOpMeter)

    def test_returns_noop_with_config(self):
        from enhanced_agent_bus.observability.telemetry import (
            NoOpTracer,
            TelemetryConfig,
            configure_telemetry,
        )

        config = TelemetryConfig(service_name="test")
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer, meter = configure_telemetry(config)
        assert isinstance(tracer, NoOpTracer)


class TestGetTracer:
    def test_returns_noop_when_unavailable(self):
        from enhanced_agent_bus.observability.telemetry import NoOpTracer, get_tracer

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)

    def test_returns_cached_tracer(self):
        from enhanced_agent_bus.observability.telemetry import _tracers, get_tracer

        sentinel = object()
        _tracers["my-service"] = sentinel
        try:
            result = get_tracer("my-service")
            assert result is sentinel
        finally:
            _tracers.pop("my-service", None)

    def test_returns_noop_with_service_name(self):
        from enhanced_agent_bus.observability.telemetry import NoOpTracer, get_tracer

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer = get_tracer("nonexistent-service")
        assert isinstance(tracer, NoOpTracer)


class TestGetMeter:
    def test_returns_noop_when_unavailable(self):
        from enhanced_agent_bus.observability.telemetry import NoOpMeter, get_meter

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            meter = get_meter()
        assert isinstance(meter, NoOpMeter)

    def test_returns_cached_meter(self):
        from enhanced_agent_bus.observability.telemetry import _meters, get_meter

        sentinel = object()
        _meters["my-service"] = sentinel
        try:
            result = get_meter("my-service")
            assert result is sentinel
        finally:
            _meters.pop("my-service", None)

    def test_returns_noop_with_service_name(self):
        from enhanced_agent_bus.observability.telemetry import NoOpMeter, get_meter

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            meter = get_meter("nonexistent-service")
        assert isinstance(meter, NoOpMeter)


class TestGetResourceAttributes:
    def test_fallback_when_import_fails(self):
        from enhanced_agent_bus.observability.telemetry import (
            TelemetryConfig,
            _get_resource_attributes,
        )

        config = TelemetryConfig()
        # The function catches NameError internally when get_resource_attributes
        # is not importable. We can trigger that by temporarily removing it from
        # the module namespace if it exists, or by calling directly when it
        # already falls back.
        import enhanced_agent_bus.observability.telemetry as tel_mod

        original = getattr(tel_mod, "get_resource_attributes", None)
        # Remove the function to force NameError path
        if hasattr(tel_mod, "get_resource_attributes"):
            delattr(tel_mod, "get_resource_attributes")
        try:
            attrs = _get_resource_attributes(config)
            assert attrs["service.name"] == "acgs2-agent-bus"
            assert attrs["constitutional.hash"] == CONST_HASH
        finally:
            if original is not None:
                tel_mod.get_resource_attributes = original  # type: ignore[attr-defined]

    def test_success_when_available(self):
        from enhanced_agent_bus.observability.telemetry import (
            TelemetryConfig,
            _get_resource_attributes,
        )

        config = TelemetryConfig()
        # Just call it - it either uses the real function or falls back
        attrs = _get_resource_attributes(config)
        assert "constitutional.hash" in attrs or "service.name" in attrs


class TestTracingContext:
    def test_enter_exit_noop(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            ctx = TracingContext("test_span", attributes={"k": "v"})
            with ctx as span:
                span.set_attribute("x", "y")

    def test_enter_exit_with_exception(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            ctx = TracingContext("test_span")
            try:
                with ctx:
                    raise ValueError("test error")
            except ValueError:
                pass

    def test_exit_with_exception_records(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            ctx = TracingContext("test_span")
            # Manually test __exit__ with exception info
            ctx._span = MagicMock()
            ctx._context = MagicMock()
            ctx._context.__exit__ = MagicMock(return_value=False)

            result = ctx.__exit__(ValueError, ValueError("err"), None)
            ctx._span.record_exception.assert_called_once()

    def test_exit_no_context(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        ctx = TracingContext("test")
        ctx._span = None
        ctx._context = None
        result = ctx.__exit__(None, None, None)
        assert result is False


class TestMetricsRegistry:
    def test_init(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry("test-service")
        assert registry.service_name == "test-service"

    def test_get_counter(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        counter = registry.get_counter("test_counter", description="a counter")
        # Should return same instance on second call
        assert registry.get_counter("test_counter") is counter

    def test_get_histogram(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        histogram = registry.get_histogram("test_hist", unit="s")
        assert registry.get_histogram("test_hist") is histogram

    def test_get_gauge(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        gauge = registry.get_gauge("test_gauge")
        assert registry.get_gauge("test_gauge") is gauge

    def test_increment_counter(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        # Should not raise
        registry.increment_counter("requests")
        registry.increment_counter("requests", amount=5, attributes={"method": "GET"})

    def test_record_latency(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        registry.record_latency("processing", 12.5)
        registry.record_latency("processing", 5.0, attributes={"step": "validate"})

    def test_set_gauge(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            registry = MetricsRegistry()
        registry.set_gauge("active_connections", 1)
        registry.set_gauge("active_connections", -1, attributes={"pool": "main"})
