"""
Coverage tests for batch 35d:
  - enhanced_agent_bus.constitutional.proposal_engine (87.1% -> 95%+)
  - enhanced_agent_bus.online_learning_infra.consumer (81.4% -> 95%+)
  - enhanced_agent_bus.mcp_integration.auth.oidc_provider (90.3% -> 95%+)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.version_model import (
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
    return storage


# ===================================================================
# 1. proposal_engine -- uncovered paths
# ===================================================================


class TestProposalEngineInvariantViolation:
    """Test invariant violation path during create_proposal (line 297-298)."""

    async def test_create_proposal_invariant_violation_raises(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
            ProposalRequest,
            ProposalValidationError,
        )

        active = _make_version(version="1.0.0", content={"rules": "x"})
        storage = _mock_storage(active_version=active)
        diff_engine = MagicMock()

        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=diff_engine,
            enable_maci=False,
            enable_audit=False,
        )

        # Validator that raises ConstitutionalInvariantViolation
        mock_violation = type("ConstitutionalInvariantViolation", (Exception,), {})
        validator = MagicMock()
        validator.validate_proposal = AsyncMock(
            side_effect=mock_violation("tier-1 invariant breached")
        )

        request = ProposalRequest(
            proposed_changes={"new_rule": "y"},
            justification="A valid justification for testing",
            proposer_agent_id="agent-1",
        )

        with (
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine.ConstitutionalInvariantViolation",
                mock_violation,
            ),
        ):
            engine._get_invariant_validator = MagicMock(return_value=validator)
            with pytest.raises(ProposalValidationError, match="invariant violation"):
                await engine.create_proposal(request)


class TestProposalEngineCreateWithInvariantClassificationNoTouch:
    """Invariant classification that does NOT touch invariants."""

    async def test_create_proposal_invariant_no_touch(self):
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
            touches_invariants=False,
            touched_invariant_ids=[],
            requires_refoundation=False,
            reason="no invariants affected",
        )
        validator = MagicMock()
        validator.invariant_hash = "hash456"
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

        # When touches_invariants is False, invariant_impact should be empty
        assert response.proposal.invariant_impact == []
        assert response.proposal.requires_refoundation is False
        assert response.proposal.invariant_hash == "hash456"
        # metadata should NOT have invariant_note
        assert "invariant_note" not in response.proposal.metadata


class TestProposalEngineCreateWithRefoundation:
    """Invariant classification that requires refoundation."""

    async def test_create_proposal_requires_refoundation(self):
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
            touched_invariant_ids=["inv-tier1-sovereignty"],
            requires_refoundation=True,
            reason="modifies tier-1 sovereignty invariant",
        )
        validator = MagicMock()
        validator.invariant_hash = "refound-hash"
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

        assert response.proposal.requires_refoundation is True
        assert "inv-tier1-sovereignty" in response.proposal.invariant_impact
        assert "invariant_note" in response.proposal.metadata


class TestProposalEngineCreateWithExplicitVersions:
    """Test create_proposal with explicit target_version and new_version."""

    async def test_create_proposal_with_explicit_new_version(self):
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
            target_version="1.0.0",
            new_version="2.0.0",
        )

        with patch(
            "enhanced_agent_bus.constitutional.proposal_engine._INVARIANT_IMPORTS_AVAILABLE",
            True,
        ):
            engine._get_invariant_validator = MagicMock(return_value=None)
            response = await engine.create_proposal(request)

        assert response.proposal.new_version == "2.0.0"
        assert response.proposal.target_version == "1.0.0"


class TestProposalEngineGetInvariantValidatorSuccess:
    """Test _get_invariant_validator when initialization succeeds."""

    def test_get_invariant_validator_success(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        storage = _mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        mock_manifest = MagicMock()
        mock_validator_instance = MagicMock()
        mock_validator_cls = MagicMock(return_value=mock_validator_instance)

        with (
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine.ProposalInvariantValidator",
                mock_validator_cls,
            ),
            patch(
                "enhanced_agent_bus.constitutional.proposal_engine.get_default_manifest",
                MagicMock(return_value=mock_manifest),
            ),
        ):
            result = engine._get_invariant_validator()

        assert result is mock_validator_instance
        mock_validator_cls.assert_called_once_with(mock_manifest)

    def test_get_invariant_validator_cached(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        storage = _mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )

        cached_validator = MagicMock()
        engine._invariant_validator = cached_validator

        # Should return cached without calling constructor
        result = engine._get_invariant_validator()
        assert result is cached_validator


class TestProposalEngineGetProposalDiffNone:
    """Test get_proposal when diff_preview computes to None."""

    async def test_get_proposal_diff_returns_none(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        active = _make_version(content={"rules": "x"})
        amendment = _make_amendment()
        storage = _mock_storage(active_version=active, amendment=amendment)
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=False,
        )
        engine.diff_engine.compute_diff = AsyncMock(return_value=None)

        result = await engine.get_proposal(amendment.proposal_id, include_diff=True)
        assert result is not None
        assert result["diff_preview"] is None


class TestProposalEngineListProposalsNoStatus:
    """Test list_proposals with audit enabled but no status filter."""

    async def test_list_proposals_audit_no_status(self):
        from enhanced_agent_bus.constitutional.proposal_engine import (
            AmendmentProposalEngine,
        )

        storage = _mock_storage()
        engine = AmendmentProposalEngine(
            storage=storage,
            diff_engine=MagicMock(),
            enable_maci=False,
            enable_audit=True,
            audit_client=AsyncMock(),
        )
        engine.audit_client.log_event = AsyncMock()

        result = await engine.list_proposals(proposer_agent_id="agent-x")
        assert result == []
        engine.audit_client.log_event.assert_awaited_once()


# ===================================================================
# 2. online_learning_infra.consumer -- uncovered paths
# ===================================================================

from enhanced_agent_bus.online_learning_infra.consumer import FeedbackKafkaConsumer


class TestConsumerConsumeLoopError:
    """Test _consume_loop when the iterator raises a non-cancellation error."""

    async def test_consume_loop_operational_error(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = True

        class _ErrorIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("broker disconnected")

        consumer._consumer = _ErrorIter()
        # Should NOT raise; consume_loop catches operational errors
        await consumer._consume_loop()
        assert consumer._stats.status == "error"


class TestConsumerConsumeLoopProcessError:
    """Test _consume_loop when _process_message raises."""

    async def test_consume_loop_message_processing_error(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = True

        msg = SimpleNamespace(
            offset=42,
            value={"features": {"x": 1}, "actual_impact": 0.5, "decision_id": "d1"},
        )

        class _SingleMsgIter:
            def __init__(self):
                self._yielded = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._yielded:
                    self._yielded = True
                    return msg
                raise StopAsyncIteration

        consumer._consumer = _SingleMsgIter()
        # Force _process_message to raise
        consumer._process_message = AsyncMock(side_effect=ValueError("bad value"))
        await consumer._consume_loop()
        assert consumer._stats.messages_failed >= 1


class TestConsumerConsumeLoopRunningFlagCheck:
    """Test that consume loop exits when _running is set to False."""

    async def test_consume_loop_stops_on_flag(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = False  # Already stopped

        msg = SimpleNamespace(offset=0, value={})

        class _InfiniteIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                return msg

        consumer._consumer = _InfiniteIter()
        # Should exit immediately because _running is False
        await consumer._consume_loop()


class TestConsumerProcessMessageNoFeaturesNoOutcome:
    """Test _process_message with event data lacking features/outcome."""

    async def test_process_message_no_features(self):
        consumer = FeedbackKafkaConsumer()
        consumer._pipeline = MagicMock()
        msg = SimpleNamespace(
            offset=10,
            value={"event_type": "feedback", "metadata": {}},
        )
        await consumer._process_message(msg)
        assert consumer._stats.messages_received == 1
        assert consumer._stats.messages_processed == 1
        # learn_from_feedback should NOT be called
        consumer._pipeline.learn_from_feedback.assert_not_called()

    async def test_process_message_features_but_none_outcome(self):
        consumer = FeedbackKafkaConsumer()
        consumer._pipeline = MagicMock()
        msg = SimpleNamespace(
            offset=11,
            value={"features": {"x": 1}, "outcome": "unknown"},
        )
        # _extract_outcome for "unknown" returns None
        await consumer._process_message(msg)
        assert consumer._stats.messages_processed == 1
        consumer._pipeline.learn_from_feedback.assert_not_called()


class TestConsumerProcessMessageLearningFails:
    """Test _process_message when learn_from_feedback returns failure."""

    async def test_process_message_learning_failure(self):
        from enhanced_agent_bus.online_learning_infra.models import LearningResult

        pipeline = MagicMock()
        pipeline.learn_from_feedback.return_value = LearningResult(
            success=False,
            error_message="model diverged",
        )

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        msg = SimpleNamespace(
            offset=12,
            value={
                "features": {"x": 1, "y": 2},
                "actual_impact": 0.8,
                "decision_id": "dec-1",
            },
        )
        await consumer._process_message(msg)
        assert consumer._stats.messages_processed == 1
        # samples_learned should NOT increment on failure
        assert consumer._stats.samples_learned == 0


class TestConsumerProcessMessageCallbackInvoked:
    """Test on_message_callback is invoked during _process_message."""

    async def test_process_message_callback(self):
        callback_calls = []
        consumer = FeedbackKafkaConsumer(
            on_message_callback=lambda data: callback_calls.append(data),
        )
        consumer._pipeline = MagicMock()
        msg = SimpleNamespace(
            offset=20,
            value={"features": {"a": 1}, "actual_impact": 1.0},
        )
        from enhanced_agent_bus.online_learning_infra.models import LearningResult

        consumer._pipeline.learn_from_feedback.return_value = LearningResult(
            success=True, samples_learned=1
        )
        await consumer._process_message(msg)
        assert len(callback_calls) == 1
        assert callback_calls[0]["features"] == {"a": 1}


class TestConsumerProcessMessageRaisesOnError:
    """Test that _process_message re-raises after logging failure."""

    async def test_process_message_exception_reraises(self):
        consumer = FeedbackKafkaConsumer()
        consumer._pipeline = MagicMock()
        consumer._pipeline.learn_from_feedback.side_effect = TypeError("bad type")

        msg = SimpleNamespace(
            offset=30,
            value={
                "features": {"x": 1},
                "actual_impact": 0.5,
                "decision_id": "d-err",
            },
        )
        with pytest.raises(TypeError, match="bad type"):
            await consumer._process_message(msg)
        assert consumer._stats.messages_failed >= 1


class TestConsumerExtractOutcomeEdgeCases:
    """Test _extract_outcome with various input patterns."""

    def test_extract_outcome_feedback_type_positive(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"feedback_type": "positive"})
        assert result == 1

    def test_extract_outcome_feedback_type_negative(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"feedback_type": "negative"})
        assert result == 0

    def test_extract_outcome_feedback_type_neutral(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"feedback_type": "neutral"})
        assert result == 0.5

    def test_extract_outcome_feedback_type_correction(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"feedback_type": "correction"})
        assert result is None

    def test_extract_outcome_outcome_partial(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"outcome": "partial"})
        assert result == 0.5

    def test_extract_outcome_outcome_success(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"outcome": "success"})
        assert result == 1

    def test_extract_outcome_outcome_failure(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"outcome": "failure"})
        assert result == 0

    def test_extract_outcome_all_empty(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({})
        assert result is None

    def test_extract_outcome_unknown_feedback_type(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._extract_outcome({"feedback_type": "custom_type"})
        assert result is None


class TestConsumerStartExceptionHandling:
    """Test start() when consumer creation fails."""

    async def test_start_consumer_creation_fails(self):
        consumer = FeedbackKafkaConsumer()
        with (
            patch.object(consumer, "_check_dependencies", return_value=True),
            patch(
                "enhanced_agent_bus.online_learning_infra.consumer.AIOKafkaConsumer",
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            consumer._pipeline = MagicMock()
            result = await consumer.start()
            assert result is False
            assert consumer._stats.status == "error"
            assert consumer._consumer is None


class TestConsumerStopConsumerError:
    """Test stop() when the underlying consumer.stop() raises."""

    async def test_stop_consumer_error_swallowed(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = True
        consumer._stats.status = "running"

        mock_kafka = AsyncMock()
        mock_kafka.stop = AsyncMock(side_effect=OSError("connection lost"))
        consumer._consumer = mock_kafka
        consumer._consume_task = None

        await consumer.stop()
        assert consumer._running is False
        assert consumer._stats.status == "stopped"
        assert consumer._consumer is None


class TestConsumerGetStatsPipelineVariants:
    """Test get_stats() with different pipeline stat formats."""

    def test_get_stats_pipeline_stats_object(self):
        pipeline = MagicMock()
        pipeline_stats = MagicMock()
        pipeline_stats.learning_stats.samples_learned = 42
        pipeline.get_stats.return_value = pipeline_stats
        # Ensure it does NOT look like a dict
        type(pipeline_stats).__contains__ = MagicMock(return_value=False)

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        stats = consumer.get_stats()
        assert stats.samples_learned == 42

    def test_get_stats_pipeline_dict_with_object_learning_stats(self):
        pipeline = MagicMock()
        ls_obj = SimpleNamespace(samples_learned=17)
        pipeline.get_stats.return_value = {"learning_stats": ls_obj}

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        stats = consumer.get_stats()
        assert stats.samples_learned == 17

    def test_get_stats_no_pipeline(self):
        consumer = FeedbackKafkaConsumer()
        stats = consumer.get_stats()
        assert stats.samples_learned == 0
        assert stats.status == "stopped"


class TestConsumerSanitizeBootstrapMultipleServers:
    """Test _sanitize_bootstrap with multiple servers."""

    def test_sanitize_bootstrap_multiple(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._sanitize_bootstrap("broker1:9092,broker2:9093,broker3:9094")
        assert result == "broker1:****,broker2:****,broker3:****"

    def test_sanitize_bootstrap_no_port(self):
        consumer = FeedbackKafkaConsumer()
        result = consumer._sanitize_bootstrap("broker1")
        assert result == "broker1:****"


class TestConsumerProperties:
    """Test is_running and pipeline properties."""

    def test_is_running_false(self):
        consumer = FeedbackKafkaConsumer()
        assert consumer.is_running is False

    def test_pipeline_property(self):
        pipeline = MagicMock()
        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        assert consumer.pipeline is pipeline


# ===================================================================
# 3. mcp_integration.auth.oidc_provider -- uncovered paths
# ===================================================================

from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import (
    OAuth2Token,
)
from enhanced_agent_bus.mcp_integration.auth.oidc_provider import (
    JWKSCache,
    OIDCConfig,
    OIDCProvider,
    OIDCProviderMetadata,
    OIDCTokens,
)


class TestOIDCProviderMetadataFromDict:
    """Test OIDCProviderMetadata.from_dict with various fields."""

    def test_from_dict_minimal(self):
        data = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/auth",
            "token_endpoint": "https://example.com/token",
        }
        meta = OIDCProviderMetadata.from_dict(data)
        assert meta.issuer == "https://example.com"
        assert meta.userinfo_endpoint is None
        assert meta.scopes_supported == []

    def test_from_dict_full(self):
        data = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/auth",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "jwks_uri": "https://example.com/jwks",
            "registration_endpoint": "https://example.com/register",
            "revocation_endpoint": "https://example.com/revoke",
            "introspection_endpoint": "https://example.com/introspect",
            "end_session_endpoint": "https://example.com/logout",
            "device_authorization_endpoint": "https://example.com/device",
            "scopes_supported": ["openid", "profile"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            "claims_supported": ["sub", "email"],
            "code_challenge_methods_supported": ["S256"],
        }
        meta = OIDCProviderMetadata.from_dict(data)
        assert meta.userinfo_endpoint == "https://example.com/userinfo"
        assert meta.scopes_supported == ["openid", "profile"]
        assert meta.code_challenge_methods_supported == ["S256"]


class TestOIDCProviderMetadataToDict:
    """Test OIDCProviderMetadata.to_dict."""

    def test_to_dict_contains_expected_keys(self):
        meta = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
        )
        d = meta.to_dict()
        assert d["issuer"] == "https://example.com"
        assert "discovered_at" in d
        assert "constitutional_hash" in d


class TestOIDCTokensProperties:
    """Test OIDCTokens subject, email, name properties."""

    def test_subject(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={"sub": "user-42"},
        )
        assert tokens.subject == "user-42"

    def test_email_from_claims(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={"email": "test@example.com"},
        )
        assert tokens.email == "test@example.com"

    def test_email_from_userinfo(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={},
            userinfo={"email": "info@example.com"},
        )
        assert tokens.email == "info@example.com"

    def test_name_from_claims(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={"name": "Alice"},
        )
        assert tokens.name == "Alice"

    def test_name_from_userinfo(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={},
            userinfo={"name": "Bob"},
        )
        assert tokens.name == "Bob"

    def test_to_dict(self):
        token = OAuth2Token(access_token="abc123")
        tokens = OIDCTokens(
            oauth2_token=token,
            id_token_claims={"sub": "user-1", "email": "a@b.com"},
            validated=True,
        )
        d = tokens.to_dict()
        assert d["subject"] == "user-1"
        assert d["email"] == "a@b.com"
        assert d["validated"] is True
        assert "constitutional_hash" in d


class TestOIDCProviderDiscoverCached:
    """Test discover() returns cached metadata when valid."""

    async def test_discover_returns_cached(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            discovered_at=datetime.now(UTC),
        )
        result = await provider.discover()
        assert result is provider._metadata

    async def test_discover_no_httpx(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
            False,
        ):
            result = await provider.discover()
        assert result is None


class TestOIDCProviderDiscoverHTTP:
    """Test discover() with mocked httpx."""

    async def test_discover_success(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)

        discovery_response = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/auth",
            "token_endpoint": "https://example.com/token",
            "jwks_uri": "https://example.com/jwks",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = discovery_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.discover(force_refresh=True)

        assert result is not None
        assert result.issuer == "https://example.com"
        assert provider._oauth2_provider is not None
        assert provider._stats["discoveries"] == 1

    async def test_discover_http_error(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.discover(force_refresh=True)

        assert result is None

    async def test_discover_connection_error(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.discover(force_refresh=True)

        assert result is None


class TestOIDCProviderAcquireTokens:
    """Test acquire_tokens paths."""

    async def test_acquire_tokens_no_provider_discover_fails(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        with patch.object(provider, "discover", AsyncMock(return_value=None)):
            result = await provider.acquire_tokens()
        assert result is None

    async def test_acquire_tokens_oauth2_returns_none(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()
        provider._oauth2_provider.acquire_token = AsyncMock(return_value=None)
        provider._oauth2_provider.get_pkce_verifier = MagicMock(return_value=None)

        result = await provider.acquire_tokens()
        assert result is None

    async def test_acquire_tokens_with_id_token_valid(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            validate_id_token=False,
        )
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()

        # Build a simple JWT-like token (header.payload.sig)
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": "user-1", "iss": "https://example.com"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        fake_token = f"eyJhbGciOiJSUzI1NiJ9.{payload}.fake_sig"

        oauth2_token = OAuth2Token(
            access_token="access-tok",
            id_token=fake_token,
        )
        provider._oauth2_provider.acquire_token = AsyncMock(return_value=oauth2_token)
        provider._oauth2_provider.get_pkce_verifier = MagicMock(return_value=None)

        result = await provider.acquire_tokens(nonce="test-nonce")
        assert result is not None
        assert result.oauth2_token is oauth2_token
        assert provider._stats["tokens_acquired"] == 1

    async def test_acquire_tokens_adds_openid_scope(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            default_scopes=["profile"],
        )
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()
        provider._oauth2_provider.acquire_token = AsyncMock(return_value=None)
        provider._oauth2_provider.get_pkce_verifier = MagicMock(return_value=None)

        await provider.acquire_tokens(scopes=["profile"])
        call_args = provider._oauth2_provider.acquire_token.call_args
        assert "openid" in call_args.kwargs["scopes"]

    async def test_acquire_tokens_with_state_gets_pkce_verifier(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()
        provider._oauth2_provider.acquire_token = AsyncMock(return_value=None)
        provider._oauth2_provider.get_pkce_verifier = MagicMock(return_value="verifier-123")

        await provider.acquire_tokens(state="state-abc")
        provider._oauth2_provider.get_pkce_verifier.assert_called_with("state-abc")


class TestOIDCProviderGetUserinfo:
    """Test get_userinfo paths."""

    async def test_get_userinfo_no_metadata(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = await provider.get_userinfo("token")
        assert result is None

    async def test_get_userinfo_no_endpoint(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            userinfo_endpoint=None,
        )
        result = await provider.get_userinfo("token")
        assert result is None

    async def test_get_userinfo_no_httpx(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            userinfo_endpoint="https://example.com/userinfo",
        )
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
            False,
        ):
            result = await provider.get_userinfo("token")
        assert result is None

    async def test_get_userinfo_success(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            userinfo_endpoint="https://example.com/userinfo",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sub": "user-1", "email": "a@b.com"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.get_userinfo("my-token")

        assert result == {"sub": "user-1", "email": "a@b.com"}
        assert provider._stats["userinfo_fetched"] == 1

    async def test_get_userinfo_http_error(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            userinfo_endpoint="https://example.com/userinfo",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.get_userinfo("my-token")

        assert result is None

    async def test_get_userinfo_connection_error(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            userinfo_endpoint="https://example.com/userinfo",
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider.get_userinfo("my-token")

        assert result is None


class TestOIDCProviderValidateIdToken:
    """Test _validate_id_token paths not covered by integration tests."""

    async def test_validate_skip_when_disabled(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            validate_id_token=False,
        )
        provider = OIDCProvider(config)

        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": "u1", "iss": "https://example.com"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        token = f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig"

        claims, errors = await provider._validate_id_token(token, "access", None)
        assert claims["sub"] == "u1"
        assert errors == []

    async def test_validate_skip_decode_error(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            validate_id_token=False,
        )
        provider = OIDCProvider(config)

        claims, errors = await provider._validate_id_token("not.a.valid-jwt", "access", None)
        assert len(errors) > 0
        assert "decode" in errors[0].lower() or "Token decode error" in errors[0]

    async def test_validate_no_jwks_keys(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            validate_id_token=True,
        )
        provider = OIDCProvider(config)
        provider._fetch_jwks = AsyncMock(return_value=None)

        claims, errors = await provider._validate_id_token("a.b.c", "access", None)
        assert claims == {}
        assert any("No JWKS" in e for e in errors)

    async def test_validate_empty_jwks_keys(self):
        config = OIDCConfig(
            issuer_url="https://example.com",
            client_id="test",
            validate_id_token=True,
        )
        provider = OIDCProvider(config)
        provider._fetch_jwks = AsyncMock(return_value=[])

        claims, errors = await provider._validate_id_token("a.b.c", "access", None)
        assert any("No JWKS" in e for e in errors)


class TestOIDCProviderDecodeJwtPayload:
    """Test _decode_jwt_payload."""

    def test_decode_valid_jwt(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)

        payload_data = {"sub": "user-1", "email": "test@example.com"}
        payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode().rstrip("=")
        token = f"header.{payload}.signature"

        result = provider._decode_jwt_payload(token)
        assert result["sub"] == "user-1"

    def test_decode_invalid_format(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)

        with pytest.raises(ValueError, match="Invalid JWT format"):
            provider._decode_jwt_payload("not-a-jwt")


class TestOIDCProviderComputeAtHash:
    """Test _compute_at_hash with different algorithms."""

    def test_at_hash_sha256(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider._compute_at_hash("access-token-123", {"alg": "RS256"})
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(b"access-token-123").digest()[:16])
            .decode()
            .rstrip("=")
        )
        assert result == expected

    def test_at_hash_sha384(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider._compute_at_hash("access-token-123", {"alg": "RS384"})
        digest = hashlib.sha384(b"access-token-123").digest()
        expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).decode().rstrip("=")
        assert result == expected

    def test_at_hash_sha512(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider._compute_at_hash("access-token-123", {"alg": "RS512"})
        digest = hashlib.sha512(b"access-token-123").digest()
        expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).decode().rstrip("=")
        assert result == expected

    def test_at_hash_unknown_alg_falls_back_to_sha256(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider._compute_at_hash("access-token-123", {"alg": "ES256K"})
        # ES256K does not end in 256/384/512 so falls back to sha256
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(b"access-token-123").digest()[:16])
            .decode()
            .rstrip("=")
        )
        assert result == expected


class TestOIDCProviderFetchJWKS:
    """Test _fetch_jwks paths."""

    async def test_fetch_jwks_no_metadata(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = await provider._fetch_jwks()
        assert result is None

    async def test_fetch_jwks_no_jwks_uri(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            jwks_uri=None,
        )
        result = await provider._fetch_jwks()
        assert result is None

    async def test_fetch_jwks_cached(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            jwks_uri="https://example.com/jwks",
        )
        cached_keys = [{"kid": "key-1", "kty": "RSA"}]
        provider._jwks_cache = JWKSCache(
            keys=cached_keys,
            fetched_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        result = await provider._fetch_jwks()
        assert result == cached_keys

    async def test_fetch_jwks_expired_cache(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            jwks_uri="https://example.com/jwks",
        )
        provider._jwks_cache = JWKSCache(
            keys=[],
            fetched_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"keys": [{"kid": "new-key"}]}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider._fetch_jwks()

        assert result == [{"kid": "new-key"}]
        assert provider._jwks_cache is not None
        assert provider._jwks_cache.keys == [{"kid": "new-key"}]

    async def test_fetch_jwks_http_error(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            jwks_uri="https://example.com/jwks",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
                True,
            ):
                result = await provider._fetch_jwks()

        assert result is None

    async def test_fetch_jwks_no_httpx(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            jwks_uri="https://example.com/jwks",
        )
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE",
            False,
        ):
            result = await provider._fetch_jwks()
        assert result is None


class TestOIDCProviderBuildAuthorizationUrl:
    """Test build_authorization_url paths."""

    def test_build_auth_url_no_provider(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider.build_authorization_url("https://example.com/callback")
        assert result is None

    def test_build_auth_url_success(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()
        provider._oauth2_provider.build_authorization_url.return_value = (
            "https://example.com/auth?client_id=test",
            "state-123",
            "nonce-123",
        )

        result = provider.build_authorization_url(
            "https://example.com/callback",
            login_hint="user@example.com",
            prompt="consent",
        )
        assert result is not None
        url, state, nonce = result
        assert "example.com" in url

    def test_build_auth_url_with_custom_nonce(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._oauth2_provider = MagicMock()
        provider._oauth2_provider.build_authorization_url.return_value = (
            "https://example.com/auth",
            "state-1",
            "custom-nonce",
        )

        result = provider.build_authorization_url(
            "https://example.com/callback",
            nonce="custom-nonce",
        )
        assert result is not None


class TestOIDCProviderBuildLogoutUrl:
    """Test build_logout_url paths."""

    def test_build_logout_url_no_metadata(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        result = provider.build_logout_url()
        assert result is None

    def test_build_logout_url_no_end_session_endpoint(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            end_session_endpoint=None,
        )
        result = provider.build_logout_url()
        assert result is None

    def test_build_logout_url_no_params(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            end_session_endpoint="https://example.com/logout",
        )
        result = provider.build_logout_url()
        assert result == "https://example.com/logout"

    def test_build_logout_url_with_params(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
            end_session_endpoint="https://example.com/logout",
        )
        result = provider.build_logout_url(
            id_token_hint="tok-hint",
            post_logout_redirect_uri="https://example.com/home",
            state="state-x",
        )
        assert "id_token_hint=tok-hint" in result
        assert "post_logout_redirect_uri=" in result
        assert "state=state-x" in result


class TestOIDCProviderGetMetadataAndStats:
    """Test get_metadata and get_stats."""

    def test_get_metadata_none(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        assert provider.get_metadata() is None

    def test_get_stats(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        stats = provider.get_stats()
        assert stats["metadata_cached"] is False
        assert stats["jwks_cached"] is False
        assert stats["issuer"] is None
        assert "constitutional_hash" in stats

    def test_get_stats_with_metadata(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/auth",
            token_endpoint="https://example.com/token",
        )
        stats = provider.get_stats()
        assert stats["metadata_cached"] is True
        assert stats["issuer"] == "https://example.com"


class TestOIDCProviderVerifyJwtSignatureNoJwt:
    """Test _verify_jwt_signature when JWT is unavailable."""

    def test_verify_jwt_no_jwt_available(self):
        config = OIDCConfig(issuer_url="https://example.com", client_id="test")
        provider = OIDCProvider(config)
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.JWT_AVAILABLE",
            False,
        ):
            with pytest.raises(ValueError, match="PyJWT is required"):
                provider._verify_jwt_signature("token", [{"kid": "k1"}])
