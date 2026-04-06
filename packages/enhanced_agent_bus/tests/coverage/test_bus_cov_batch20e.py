"""
Coverage tests for batch 20e:
  1. enhanced_agent_bus.builder (build_sdpc_verifiers, build_pqc_service)
  2. enhanced_agent_bus.constitutional.hitl_integration (ConstitutionalHITLIntegration)
  3. enhanced_agent_bus.api.routes.agent_health (FastAPI routes)
  4. enhanced_agent_bus.enterprise_sso.saga_orchestration (SagaOrchestrator, etc.)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_proposal(
    *,
    impact_score: float = 0.5,
    status: str = "proposed",
    proposal_id: str | None = None,
) -> Any:
    """Create a minimal AmendmentProposal-like object for HITL tests."""
    from enhanced_agent_bus.constitutional.amendment_model import (
        AmendmentProposal,
        AmendmentStatus,
    )

    p = AmendmentProposal(
        proposed_changes={"rule_1": "updated value"},
        justification="Test justification for amendment proposal changes",
        proposer_agent_id="agent-42",
        target_version="1.0.0",
        new_version="1.1.0",
        impact_score=impact_score,
    )
    if proposal_id:
        p.proposal_id = proposal_id
    if status == "under_review":
        p.status = AmendmentStatus.UNDER_REVIEW
    elif status == "approved":
        p.status = AmendmentStatus.APPROVED
    return p


# ===================================================================
# 1. builder.py tests
# ===================================================================


class TestBuildSdpcVerifiers:
    """Tests for build_sdpc_verifiers()."""

    def setup_method(self):
        """Reset global cache before each test."""
        import enhanced_agent_bus.builder as b

        b._cached_sdpc = None

    def test_build_sdpc_verifiers_returns_sdpc_verifiers_dataclass(self):
        """Verifiers should be returned as SDPCVerifiers dataclass (stub or real)."""
        from enhanced_agent_bus.builder import SDPCVerifiers, build_sdpc_verifiers
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        result = build_sdpc_verifiers(config)
        assert isinstance(result, SDPCVerifiers)
        assert result.intent_classifier is not None
        assert result.asc_verifier is not None
        assert result.graph_check is not None
        assert result.pacar_verifier is not None
        assert result.evolution_controller is not None
        assert result.ampo_engine is not None
        assert result.IntentType is not None

    def test_build_sdpc_verifiers_cached_on_second_call(self):
        """Second call should return the cached instance."""
        from enhanced_agent_bus.builder import build_sdpc_verifiers
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        first = build_sdpc_verifiers(config)
        second = build_sdpc_verifiers(config)
        assert first is second

    async def test_build_sdpc_noop_verifier_verify(self):
        """NoOp verifier .verify() returns {valid: True} when stubs are used."""
        from enhanced_agent_bus.builder import build_sdpc_verifiers
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        v = build_sdpc_verifiers(config)
        # The verify method may be async (NoOp) or from the real SDPC module.
        # Only test NoOp stubs which have a simple 'verify' method.
        verifier = v.asc_verifier
        if hasattr(verifier, "verify") and type(verifier).__name__ == "_NoOpVerifier":
            result = await verifier.verify()
            assert result == {"valid": True}

    async def test_build_sdpc_noop_intent_classifier(self):
        """NoOp intent classifier .classify_intent() returns 'unknown'."""
        from enhanced_agent_bus.builder import build_sdpc_verifiers
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        v = build_sdpc_verifiers(config)
        clf = v.intent_classifier
        if hasattr(clf, "classify_intent") and type(clf).__name__ == "_NoOpIntentClassifier":
            result = await clf.classify_intent()
            assert result == "unknown"

    def test_build_sdpc_noop_evolution_controller_methods(self):
        """NoOp evolution controller methods behave correctly."""
        from enhanced_agent_bus.builder import build_sdpc_verifiers
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        v = build_sdpc_verifiers(config)
        ec = v.evolution_controller
        # Only test NoOp stubs
        if type(ec).__name__ == "_NoOpEvolutionController":
            assert ec.get_mutations("test") == []
            ec.record_feedback("intent", {"results": True})
            ec._trigger_mutation("intent")
            ec.reset_mutations()
            ec.reset_mutations("specific")
        elif hasattr(ec, "get_mutations"):
            # Real controller expects IntentType enum, not raw string
            intent_type = v.IntentType
            if hasattr(intent_type, "UNKNOWN"):
                ec.get_mutations(intent_type.UNKNOWN)


class TestBuildPqcService:
    """Tests for build_pqc_service()."""

    def setup_method(self):
        import enhanced_agent_bus.builder as b

        b._cached_pqc = None

    def test_pqc_disabled_returns_none(self):
        """When config.enable_pqc is False, returns None."""
        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = False
        result = build_pqc_service(config)
        assert result is None

    def test_pqc_enabled_import_error_returns_none(self):
        """When PQC module is unavailable, returns None."""
        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True

        with patch("importlib.import_module", side_effect=ImportError("no pqc")):
            result = build_pqc_service(config)
        assert result is None

    def test_pqc_enabled_attribute_error_returns_none(self):
        """When PQC module has wrong attributes, returns None."""
        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True

        mock_module = MagicMock()
        del mock_module.PQCConfig
        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)
        # Should return None due to AttributeError catch
        assert result is None

    def test_pqc_enabled_success(self):
        """When PQC module is available, creates and caches service."""
        import enhanced_agent_bus.builder as b

        b._cached_pqc = None

        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True
        config.pqc_mode = "hybrid"
        config.pqc_verification_mode = "strict"
        config.pqc_migration_phase = "phase_2"

        mock_pqc_config = MagicMock()
        mock_pqc_service = MagicMock()

        mock_module = MagicMock()
        mock_module.PQCConfig = MagicMock(return_value=mock_pqc_config)
        mock_module.PQCCryptoService = MagicMock(return_value=mock_pqc_service)

        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)

        assert result is mock_pqc_service

    def test_pqc_cached_on_second_call(self):
        """Second call returns cached PQC service."""
        import enhanced_agent_bus.builder as b

        sentinel = MagicMock()
        b._cached_pqc = sentinel

        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True
        result = build_pqc_service(config)
        assert result is sentinel

    def test_pqc_pqc_mode_classical_only(self):
        """PQC with classical_only mode."""
        import enhanced_agent_bus.builder as b

        b._cached_pqc = None

        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True
        config.pqc_mode = "classical_only"
        config.pqc_verification_mode = "classical_only"
        config.pqc_migration_phase = None

        mock_module = MagicMock()
        mock_module.PQCConfig = MagicMock(return_value=MagicMock())
        mock_module.PQCCryptoService = MagicMock(return_value=MagicMock())

        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)
        assert result is not None

    def test_pqc_pqc_only_mode(self):
        """PQC with pqc_only mode and verification."""
        import enhanced_agent_bus.builder as b

        b._cached_pqc = None

        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True
        config.pqc_mode = "pqc_only"
        config.pqc_verification_mode = "pqc_only"
        config.pqc_migration_phase = "phase_5"

        mock_module = MagicMock()
        mock_module.PQCConfig = MagicMock(return_value=MagicMock())
        mock_module.PQCCryptoService = MagicMock(return_value=MagicMock())

        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)
        assert result is not None

    def test_pqc_invalid_mode_defaults(self):
        """PQC with invalid mode falls back to defaults."""
        import enhanced_agent_bus.builder as b

        b._cached_pqc = None

        from enhanced_agent_bus.builder import build_pqc_service
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()
        config.enable_pqc = True
        config.pqc_mode = "invalid_mode"
        config.pqc_verification_mode = "invalid_verify"
        config.pqc_migration_phase = "not_a_phase"

        mock_module = MagicMock()
        mock_module.PQCConfig = MagicMock(return_value=MagicMock())
        mock_module.PQCCryptoService = MagicMock(return_value=MagicMock())

        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)
        assert result is not None


# ===================================================================
# 2. constitutional/hitl_integration.py tests
# ===================================================================


class TestConstitutionalHITLIntegration:
    """Tests for ConstitutionalHITLIntegration."""

    @pytest.fixture()
    def mock_storage(self):
        storage = AsyncMock()
        storage.save_amendment = AsyncMock()
        storage.get_amendment = AsyncMock()
        return storage

    @pytest.fixture()
    def hitl(self, mock_storage):
        from enhanced_agent_bus.constitutional.hitl_integration import (
            ConstitutionalHITLIntegration,
        )

        return ConstitutionalHITLIntegration(
            storage=mock_storage,
            hitl_service_url="http://test-hitl:8002",
            notification_config={
                "slack": {"webhook_url": "https://hooks.slack.com/test"},
                "pagerduty": {"integration_key": "test-key"},
                "teams": {"webhook_url": "https://teams.webhook.test"},
            },
            enable_notifications=False,
        )

    def test_init_default_chains(self, hitl):
        """Approval chains are initialized with correct defaults."""
        assert hitl.high_impact_chain.required_approvals == 3
        assert hitl.medium_impact_chain.required_approvals == 2
        assert hitl.low_impact_chain.required_approvals == 1

    def test_determine_approval_chain_high_impact(self, hitl):
        p = _make_proposal(impact_score=0.9)
        chain = hitl._determine_approval_chain(p)
        assert chain.chain_id == "constitutional_high_impact"

    def test_determine_approval_chain_medium_impact(self, hitl):
        p = _make_proposal(impact_score=0.6)
        chain = hitl._determine_approval_chain(p)
        assert chain.chain_id == "constitutional_medium_impact"

    def test_determine_approval_chain_low_impact(self, hitl):
        p = _make_proposal(impact_score=0.3)
        chain = hitl._determine_approval_chain(p)
        assert chain.chain_id == "constitutional_low_impact"

    def test_determine_approval_chain_none_defaults_medium(self, hitl):
        p = _make_proposal(impact_score=0.5)
        p.impact_score = None
        chain = hitl._determine_approval_chain(p)
        assert chain.chain_id == "constitutional_medium_impact"

    def test_format_approval_description_high(self, hitl):
        p = _make_proposal(impact_score=0.9)
        desc = hitl._format_approval_description(p)
        assert "High" in desc
        assert "1.0.0" in desc

    def test_format_approval_description_medium(self, hitl):
        p = _make_proposal(impact_score=0.6)
        desc = hitl._format_approval_description(p)
        assert "Medium" in desc

    def test_format_approval_description_low(self, hitl):
        p = _make_proposal(impact_score=0.3)
        desc = hitl._format_approval_description(p)
        assert "Low" in desc

    def test_format_impact_factors_empty(self, hitl):
        result = hitl._format_impact_factors({})
        assert result == "N/A"

    def test_format_impact_factors_with_data(self, hitl):
        result = hitl._format_impact_factors({"semantic": 0.8, "permission": 0.5})
        assert "semantic" in result
        assert "0.800" in result

    def test_generate_approval_url_default(self, hitl):
        url = hitl._generate_approval_url("prop-1")
        assert url == "http://test-hitl:8002/ui/approvals/constitutional/prop-1"

    def test_generate_approval_url_custom_base(self, hitl):
        url = hitl._generate_approval_url("prop-1", "https://custom.ui")
        assert url == "https://custom.ui/approvals/constitutional/prop-1"

    def test_format_notification_message_high(self, hitl):
        p = _make_proposal(impact_score=0.9)
        msg = hitl._format_notification_message(p)
        assert "approval" in msg.lower()

    def test_format_notification_message_low(self, hitl):
        p = _make_proposal(impact_score=0.3)
        msg = hitl._format_notification_message(p)
        assert "approval" in msg.lower()

    async def test_create_approval_request_invalid_status(self, hitl):
        """Rejected proposal cannot be submitted for HITL approval."""
        p = _make_proposal(status="approved")
        with pytest.raises(ValueError, match="cannot be submitted"):
            await hitl.create_approval_request(p)

    async def test_create_approval_request_success(self, hitl, mock_storage):
        """Happy path: proposed -> under_review with HITL submission."""
        p = _make_proposal(impact_score=0.6)

        with patch.object(
            hitl,
            "_submit_to_hitl_service",
            new_callable=AsyncMock,
            return_value={"request_id": "req-123"},
        ):
            result = await hitl.create_approval_request(p)

        assert result.request_id == "req-123"
        assert result.proposal_id == p.proposal_id
        mock_storage.save_amendment.assert_awaited()

    async def test_create_approval_request_under_review_status(self, hitl):
        """Proposal already under review can also be submitted."""
        p = _make_proposal(impact_score=0.5, status="under_review")

        with patch.object(
            hitl,
            "_submit_to_hitl_service",
            new_callable=AsyncMock,
            return_value={"request_id": "req-456"},
        ):
            result = await hitl.create_approval_request(p)

        assert result.request_id == "req-456"

    async def test_create_approval_request_hitl_failure(self, hitl):
        """HITL service failure propagates."""
        p = _make_proposal(impact_score=0.5)

        with patch.object(
            hitl,
            "_submit_to_hitl_service",
            new_callable=AsyncMock,
            side_effect=RuntimeError("HITL down"),
        ):
            with pytest.raises(RuntimeError, match="HITL down"):
                await hitl.create_approval_request(p)

    async def test_create_approval_request_with_notifications(self, mock_storage):
        """Notifications are sent when enabled."""
        from enhanced_agent_bus.constitutional.hitl_integration import (
            ConstitutionalHITLIntegration,
        )

        hitl = ConstitutionalHITLIntegration(
            storage=mock_storage,
            enable_notifications=True,
        )
        p = _make_proposal(impact_score=0.5)

        with (
            patch.object(
                hitl,
                "_submit_to_hitl_service",
                new_callable=AsyncMock,
                return_value={"request_id": "req-789"},
            ),
            patch.object(
                hitl,
                "_send_notifications",
                new_callable=AsyncMock,
                return_value={"slack": True},
            ) as mock_notify,
        ):
            await hitl.create_approval_request(p)
            mock_notify.assert_awaited_once()

    async def test_check_approval_status_success(self, hitl):
        """Successful status check."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "approved"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(hitl.http_client, "get", new_callable=AsyncMock, return_value=mock_resp):
            result = await hitl.check_approval_status("req-1")

        assert result == {"status": "approved"}

    async def test_check_approval_status_http_error(self, hitl):
        """HTTP error returns None."""
        with patch.object(
            hitl.http_client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("fail"),
        ):
            result = await hitl.check_approval_status("req-1")

        assert result is None

    async def test_process_approval_approved(self, hitl, mock_storage):
        """Process approved decision updates proposal."""
        p = _make_proposal(status="under_review")
        mock_storage.get_amendment.return_value = p

        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value={"status": "approved", "approved_by": "admin-1"},
        ):
            result = await hitl.process_approval_decision("req-1", p.proposal_id)

        assert result is True
        mock_storage.save_amendment.assert_awaited()

    async def test_process_approval_rejected(self, hitl, mock_storage):
        """Process rejected decision."""
        p = _make_proposal(status="under_review")
        mock_storage.get_amendment.return_value = p

        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value={
                "status": "rejected",
                "rejected_by": "admin-2",
                "rejection_reason": "nope",
            },
        ):
            result = await hitl.process_approval_decision("req-1", p.proposal_id)

        assert result is False

    async def test_process_approval_timed_out(self, hitl, mock_storage):
        """Process timed out decision."""
        p = _make_proposal(status="under_review")
        mock_storage.get_amendment.return_value = p

        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value={"status": "timed_out"},
        ):
            result = await hitl.process_approval_decision("req-1", p.proposal_id)

        assert result is False
        assert p.metadata.get("hitl_timeout") is True

    async def test_process_approval_pending(self, hitl, mock_storage):
        """Process pending status returns False."""
        p = _make_proposal(status="under_review")
        mock_storage.get_amendment.return_value = p

        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value={"status": "pending"},
        ):
            result = await hitl.process_approval_decision("req-1", p.proposal_id)

        assert result is False

    async def test_process_approval_no_status(self, hitl, mock_storage):
        """No status data returns False."""
        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await hitl.process_approval_decision("req-1", "prop-x")

        assert result is False

    async def test_process_approval_proposal_not_found(self, hitl, mock_storage):
        """Missing proposal returns False."""
        mock_storage.get_amendment.return_value = None

        with patch.object(
            hitl,
            "check_approval_status",
            new_callable=AsyncMock,
            return_value={"status": "approved"},
        ):
            result = await hitl.process_approval_decision("req-1", "missing")

        assert result is False

    async def test_submit_to_hitl_service_success(self, hitl):
        """Submit to HITL service returns response JSON."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"request_id": "r-1"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(hitl.http_client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await hitl._submit_to_hitl_service({"test": True})

        assert result == {"request_id": "r-1"}

    async def test_submit_to_hitl_service_http_error(self, hitl):
        """Submit to HITL service re-raises HTTP error."""
        with patch.object(
            hitl.http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("conn refused"),
        ):
            with pytest.raises(httpx.HTTPError):
                await hitl._submit_to_hitl_service({"test": True})

    async def test_send_slack_notification_no_webhook(self, hitl):
        """Slack notification without webhook returns False."""
        hitl.notification_config = {}
        result = await hitl._send_slack_notification({"request_id": "r", "title": "t"})
        assert result is False

    async def test_send_slack_notification_success(self, hitl):
        """Slack notification with webhook succeeds."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.object(hitl.http_client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await hitl._send_slack_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "message": "msg",
                    "priority": "critical",
                    "metadata": {"impact_score": 0.9, "proposal_id": "p1"},
                    "approval_url": "https://example.com",
                }
            )

        assert result is True

    async def test_send_slack_notification_http_error(self, hitl):
        """Slack notification HTTP error returns False."""
        with patch.object(
            hitl.http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("fail"),
        ):
            result = await hitl._send_slack_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "message": "msg",
                    "priority": "high",
                    "metadata": {"impact_score": 0.5, "proposal_id": "p"},
                    "approval_url": "https://example.com",
                }
            )

        assert result is False

    async def test_send_pagerduty_notification_no_key(self, hitl):
        """PagerDuty without integration key returns False."""
        hitl.notification_config = {}
        result = await hitl._send_pagerduty_notification({"request_id": "r"})
        assert result is False

    async def test_send_pagerduty_notification_success(self, hitl):
        """PagerDuty notification succeeds."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.object(hitl.http_client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await hitl._send_pagerduty_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "priority": "critical",
                    "metadata": {"proposal_id": "p", "impact_score": 0.9},
                    "approval_url": "https://example.com",
                }
            )

        assert result is True

    async def test_send_pagerduty_notification_non_critical(self, hitl):
        """PagerDuty with non-critical priority uses warning severity."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            hitl.http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_post:
            await hitl._send_pagerduty_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "priority": "high",
                    "metadata": {"proposal_id": "p", "impact_score": 0.5},
                    "approval_url": "https://example.com",
                }
            )
            payload = mock_post.call_args[1]["json"]
            assert payload["payload"]["severity"] == "warning"

    async def test_send_teams_notification_no_webhook(self, hitl):
        """Teams without webhook returns False."""
        hitl.notification_config = {}
        result = await hitl._send_teams_notification({"request_id": "r"})
        assert result is False

    async def test_send_teams_notification_success(self, hitl):
        """Teams notification succeeds."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.object(hitl.http_client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await hitl._send_teams_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "message": "msg",
                    "priority": "standard",
                    "metadata": {"impact_score": 0.3, "proposal_id": "p"},
                    "approval_url": "https://example.com",
                }
            )

        assert result is True

    async def test_send_teams_notification_http_error(self, hitl):
        """Teams notification HTTP error returns False."""
        with patch.object(
            hitl.http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ):
            result = await hitl._send_teams_notification(
                {
                    "request_id": "r",
                    "title": "t",
                    "message": "msg",
                    "priority": "standard",
                    "metadata": {"impact_score": 0.3, "proposal_id": "p"},
                    "approval_url": "https://example.com",
                }
            )

        assert result is False

    async def test_send_to_channel_slack(self, hitl):
        from enhanced_agent_bus.constitutional.hitl_integration import NotificationChannel

        with patch.object(
            hitl, "_send_slack_notification", new_callable=AsyncMock, return_value=True
        ):
            result = await hitl._send_to_channel(NotificationChannel.SLACK, {"request_id": "r"})
        assert result is True

    async def test_send_to_channel_pagerduty(self, hitl):
        from enhanced_agent_bus.constitutional.hitl_integration import NotificationChannel

        with patch.object(
            hitl, "_send_pagerduty_notification", new_callable=AsyncMock, return_value=True
        ):
            result = await hitl._send_to_channel(NotificationChannel.PAGERDUTY, {"request_id": "r"})
        assert result is True

    async def test_send_to_channel_teams(self, hitl):
        from enhanced_agent_bus.constitutional.hitl_integration import NotificationChannel

        with patch.object(
            hitl, "_send_teams_notification", new_callable=AsyncMock, return_value=True
        ):
            result = await hitl._send_to_channel(NotificationChannel.TEAMS, {"request_id": "r"})
        assert result is True

    async def test_send_notifications_multi_channel(self, mock_storage):
        """Send notifications to multiple channels."""
        from enhanced_agent_bus.constitutional.hitl_integration import (
            ApprovalChainConfig,
            ApprovalPriority,
            ConstitutionalHITLIntegration,
            HITLApprovalRequest,
            NotificationChannel,
        )

        hitl = ConstitutionalHITLIntegration(
            storage=mock_storage,
            notification_config={
                "slack": {"webhook_url": "https://hooks.slack.com/test"},
                "pagerduty": {"integration_key": "test-key"},
            },
            enable_notifications=True,
        )

        chain = ApprovalChainConfig(
            chain_id="test",
            name="Test",
            description="Test chain",
            priority=ApprovalPriority.HIGH,
            required_approvals=2,
            timeout_minutes=60,
            notification_channels=[NotificationChannel.SLACK, NotificationChannel.PAGERDUTY],
        )

        req = HITLApprovalRequest(
            request_id="req-1",
            proposal_id="prop-1",
            chain_config=chain,
            title="Test Amendment",
            description="Test description",
            context={},
            approval_url="https://example.com",
        )

        p = _make_proposal(impact_score=0.6)

        with (
            patch.object(hitl, "_send_to_channel", new_callable=AsyncMock, return_value=True),
        ):
            results = await hitl._send_notifications(req, p)

        assert results == {"slack": True, "pagerduty": True}

    async def test_close(self, hitl):
        """close() calls http_client.aclose()."""
        with patch.object(hitl.http_client, "aclose", new_callable=AsyncMock) as mock_close:
            await hitl.close()
            mock_close.assert_awaited_once()


class TestHITLDataclasses:
    """Tests for data classes in hitl_integration."""

    def test_approval_chain_config_defaults(self):
        from enhanced_agent_bus.constitutional.hitl_integration import (
            ApprovalChainConfig,
            ApprovalPriority,
            NotificationChannel,
        )

        config = ApprovalChainConfig(
            chain_id="test",
            name="Test",
            description="Test",
            priority=ApprovalPriority.LOW,
            required_approvals=1,
            timeout_minutes=30,
        )
        assert config.notification_channels == [NotificationChannel.SLACK]
        assert config.escalation_enabled is True

    def test_hitl_approval_request_defaults(self):
        from enhanced_agent_bus.constitutional.hitl_integration import (
            ApprovalChainConfig,
            ApprovalPriority,
            HITLApprovalRequest,
        )

        chain = ApprovalChainConfig(
            chain_id="t",
            name="T",
            description="D",
            priority=ApprovalPriority.STANDARD,
            required_approvals=1,
            timeout_minutes=30,
        )
        req = HITLApprovalRequest(
            request_id="r1",
            proposal_id="p1",
            chain_config=chain,
            title="Title",
            description="Desc",
            context={},
            approval_url="https://example.com",
        )
        assert req.status == "pending"
        assert req.created_at is not None

    def test_notification_channel_enum(self):
        from enhanced_agent_bus.constitutional.hitl_integration import NotificationChannel

        assert NotificationChannel.SLACK == "slack"
        assert NotificationChannel.PAGERDUTY == "pagerduty"
        assert NotificationChannel.TEAMS == "teams"

    def test_approval_priority_enum(self):
        from enhanced_agent_bus.constitutional.hitl_integration import ApprovalPriority

        assert ApprovalPriority.LOW == "low"
        assert ApprovalPriority.CRITICAL == "critical"


# ===================================================================
# 3. api/routes/agent_health.py tests
# ===================================================================


class TestAgentHealthRoutes:
    """Tests for agent_health FastAPI routes using httpx.AsyncClient."""

    @pytest.fixture()
    def mock_store(self):
        store = SimpleNamespace(
            get_health_record=AsyncMock(return_value=None),
            get_override=AsyncMock(return_value=None),
            set_override=AsyncMock(),
            delete_override=AsyncMock(),
        )
        return store

    @pytest.fixture()
    def mock_audit_client(self):
        client = AsyncMock()
        client.log = AsyncMock()
        return client

    @pytest.fixture()
    def app(self, mock_store, mock_audit_client):
        from fastapi import FastAPI

        from enhanced_agent_bus.api.routes.agent_health import (
            get_agent_health_store,
            get_audit_log_client,
            require_operator_role,
            router,
        )

        app = FastAPI()
        app.include_router(router)

        async def _operator_override():
            return "test-operator"

        async def _store_override():
            return mock_store

        async def _audit_override():
            return mock_audit_client

        # Override dependencies
        app.dependency_overrides[require_operator_role] = _operator_override
        app.dependency_overrides[get_agent_health_store] = _store_override
        app.dependency_overrides[get_audit_log_client] = _audit_override

        return app

    @pytest.fixture()
    async def client(self, app):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_get_agent_health_success(self, client, mock_store):
        """GET /api/v1/agents/{id}/health returns 200 with health data."""
        from enhanced_agent_bus.agent_health.models import (
            AgentHealthRecord,
            AutonomyTier,
            HealthState,
        )

        record = AgentHealthRecord(
            agent_id="agent-1",
            health_state=HealthState.HEALTHY,
            consecutive_failure_count=0,
            memory_usage_pct=45.0,
            last_event_at=datetime.now(UTC),
            autonomy_tier=AutonomyTier.BOUNDED,
        )
        mock_store.get_health_record.return_value = record

        resp = await client.get("/api/v1/agents/agent-1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "agent-1"
        assert body["health_state"] == "HEALTHY"

    async def test_get_agent_health_not_found(self, client, mock_store):
        """GET returns 404 when no health record exists."""
        mock_store.get_health_record.return_value = None

        resp = await client.get("/api/v1/agents/unknown/health")
        assert resp.status_code == 404

    async def test_get_agent_health_with_override(self, client, mock_store):
        """GET returns override data when healing_override_id is set."""
        from enhanced_agent_bus.agent_health.models import (
            AgentHealthRecord,
            AutonomyTier,
            HealingOverride,
            HealthState,
            OverrideMode,
        )

        now = datetime.now(UTC)
        record = AgentHealthRecord(
            agent_id="agent-2",
            health_state=HealthState.DEGRADED,
            consecutive_failure_count=3,
            memory_usage_pct=80.0,
            last_event_at=now,
            autonomy_tier=AutonomyTier.ADVISORY,
            healing_override_id="ovr-1",
        )
        override = HealingOverride(
            override_id="ovr-1",
            agent_id="agent-2",
            mode=OverrideMode.SUPPRESS_HEALING,
            reason="Testing override",
            issued_by="operator-1",
            issued_at=now,
        )
        mock_store.get_health_record.return_value = record
        mock_store.get_override.return_value = override

        resp = await client.get("/api/v1/agents/agent-2/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["healing_override"] is not None
        assert body["healing_override"]["override_id"] == "ovr-1"

    async def test_get_agent_health_override_id_but_no_override(self, client, mock_store):
        """GET with override_id set but no override record returns null override."""
        from enhanced_agent_bus.agent_health.models import (
            AgentHealthRecord,
            AutonomyTier,
            HealthState,
        )

        record = AgentHealthRecord(
            agent_id="agent-3",
            health_state=HealthState.HEALTHY,
            consecutive_failure_count=0,
            memory_usage_pct=20.0,
            last_event_at=datetime.now(UTC),
            autonomy_tier=AutonomyTier.HUMAN_APPROVED,
            healing_override_id="stale-ovr",
        )
        mock_store.get_health_record.return_value = record
        mock_store.get_override.return_value = None

        resp = await client.get("/api/v1/agents/agent-3/health")
        assert resp.status_code == 200
        assert resp.json()["healing_override"] is None

    async def test_create_healing_override_success(self, client, mock_store, mock_audit_client):
        """POST creates override with 201."""
        mock_store.get_override.return_value = None
        mock_store.set_override = AsyncMock()

        # Must mock the audit logger import inside the route
        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditEventType.APPROVAL = "APPROVAL"
        audit_module.AuditSeverity = MagicMock()
        audit_module.AuditSeverity.WARNING = "WARNING"

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.post(
                "/api/v1/agents/agent-1/health/override",
                json={
                    "mode": "SUPPRESS_HEALING",
                    "reason": "Planned maintenance window",
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["agent_id"] == "agent-1"
        assert body["mode"] == "SUPPRESS_HEALING"

    async def test_create_healing_override_invalid_mode(self, client, mock_store):
        """POST with invalid mode returns 400."""
        mock_store.get_override.return_value = None

        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditSeverity = MagicMock()

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.post(
                "/api/v1/agents/agent-1/health/override",
                json={"mode": "INVALID_MODE", "reason": "test"},
            )

        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]

    async def test_create_healing_override_reason_too_long(self, client, mock_store):
        """POST with reason > 1000 chars returns 400."""
        mock_store.get_override.return_value = None

        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditSeverity = MagicMock()

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.post(
                "/api/v1/agents/agent-1/health/override",
                json={"mode": "FORCE_RESTART", "reason": "x" * 1001},
            )

        assert resp.status_code == 400
        assert "1000 characters" in resp.json()["detail"]

    async def test_create_healing_override_expired_time(self, client, mock_store):
        """POST with past expires_at returns 400."""
        mock_store.get_override.return_value = None

        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditSeverity = MagicMock()

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.post(
                "/api/v1/agents/agent-1/health/override",
                json={
                    "mode": "FORCE_QUARANTINE",
                    "reason": "test",
                    "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        assert resp.status_code == 400
        assert "future" in resp.json()["detail"]

    async def test_create_healing_override_conflict(self, client, mock_store):
        """POST when override already exists returns 409."""
        from enhanced_agent_bus.agent_health.models import (
            HealingOverride,
            OverrideMode,
        )

        existing = HealingOverride(
            agent_id="agent-1",
            mode=OverrideMode.SUPPRESS_HEALING,
            reason="existing",
            issued_by="op",
            issued_at=datetime.now(UTC),
        )
        mock_store.get_override.return_value = existing

        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditSeverity = MagicMock()

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.post(
                "/api/v1/agents/agent-1/health/override",
                json={"mode": "FORCE_RESTART", "reason": "try again"},
            )

        assert resp.status_code == 409

    async def test_delete_healing_override_success(self, client, mock_store, mock_audit_client):
        """DELETE returns 204 on success."""
        from enhanced_agent_bus.agent_health.models import (
            HealingOverride,
            OverrideMode,
        )

        existing = HealingOverride(
            agent_id="agent-1",
            mode=OverrideMode.FORCE_RESTART,
            reason="maintenance",
            issued_by="op",
            issued_at=datetime.now(UTC),
        )
        mock_store.get_override.return_value = existing
        mock_store.delete_override = AsyncMock()

        audit_module = MagicMock()
        audit_module.AuditEventType = MagicMock()
        audit_module.AuditEventType.APPROVAL = "APPROVAL"
        audit_module.AuditSeverity = MagicMock()
        audit_module.AuditSeverity.INFO = "INFO"

        with patch.dict(sys.modules, {"src.core.shared.audit.logger": audit_module}):
            resp = await client.delete("/api/v1/agents/agent-1/health/override")

        assert resp.status_code == 204

    async def test_delete_healing_override_not_found(self, client, mock_store):
        """DELETE returns 404 when no override exists."""
        mock_store.get_override.return_value = None

        resp = await client.delete("/api/v1/agents/agent-1/health/override")
        assert resp.status_code == 404


class TestAgentHealthDependencies:
    """Tests for dependency injection functions."""

    def test_get_audit_log_client_missing(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.agent_health import get_audit_log_client

        mock_request = MagicMock()
        mock_request.app.state = SimpleNamespace()

        with pytest.raises(HTTPException) as exc_info:
            get_audit_log_client(mock_request)
        assert exc_info.value.status_code == 503

    def test_get_audit_log_client_present(self):
        from enhanced_agent_bus.api.routes.agent_health import get_audit_log_client

        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.app.state = SimpleNamespace(audit_log_client=mock_client)

        result = get_audit_log_client(mock_request)
        assert result is mock_client

    def test_get_agent_health_store_missing(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.agent_health import get_agent_health_store

        mock_request = MagicMock()
        mock_request.app.state = SimpleNamespace()

        with pytest.raises(HTTPException) as exc_info:
            get_agent_health_store(mock_request)
        assert exc_info.value.status_code == 503

    def test_get_agent_health_store_present(self):
        from enhanced_agent_bus.api.routes.agent_health import get_agent_health_store

        mock_store = MagicMock()
        mock_request = MagicMock()
        mock_request.app.state = SimpleNamespace(agent_health_store=mock_store)

        result = get_agent_health_store(mock_request)
        assert result is mock_store

    async def test_require_operator_role_no_auth_header(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.agent_health import require_operator_role

        mock_request = MagicMock()
        mock_request.headers = {}

        # Force ImportError for the compat rbac module so fallback logic is used
        with patch(
            "enhanced_agent_bus.api.routes.agent_health.require_operator_role.__globals__"
            if False  # unused path
            else "enhanced_agent_bus._compat.security.rbac.validate_operator_token",
            side_effect=ImportError("rbac not available"),
        ):
            with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
                with pytest.raises(HTTPException) as exc_info:
                    await require_operator_role(mock_request)
                assert exc_info.value.status_code == 401

    async def test_require_operator_role_dev_env_valid_token(self):
        from enhanced_agent_bus.api.routes.agent_health import require_operator_role

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token-12345678"}

        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            # Force ImportError for rbac
            original = sys.modules.get("src.core.shared.security.rbac")
            sys.modules["src.core.shared.security.rbac"] = None  # type: ignore
            try:
                result = await require_operator_role(mock_request)
                assert result.startswith("dev-operator:")
            finally:
                if original is not None:
                    sys.modules["src.core.shared.security.rbac"] = original
                else:
                    sys.modules.pop("src.core.shared.security.rbac", None)

    async def test_require_operator_role_prod_env_no_rbac(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.agent_health import require_operator_role

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer token"}

        # Patch the compat rbac module (not the old src path) to raise ImportError
        with patch(
            "enhanced_agent_bus._compat.security.rbac.validate_operator_token",
            side_effect=ImportError("rbac not available"),
        ):
            with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
                with pytest.raises(HTTPException) as exc_info:
                    await require_operator_role(mock_request)
                assert exc_info.value.status_code == 503

    async def test_require_operator_role_empty_bearer(self):
        from fastapi import HTTPException

        from enhanced_agent_bus.api.routes.agent_health import require_operator_role

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer "}

        with patch(
            "enhanced_agent_bus._compat.security.rbac.validate_operator_token",
            side_effect=ImportError("rbac not available"),
        ):
            with patch.dict("os.environ", {"ENVIRONMENT": "dev"}):
                with pytest.raises(HTTPException) as exc_info:
                    await require_operator_role(mock_request)
                assert exc_info.value.status_code == 401


# ===================================================================
# 4. enterprise_sso/saga_orchestration.py tests
# ===================================================================


class TestSagaDataClasses:
    """Tests for saga data classes and enums."""

    def test_saga_status_enum(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaStatus

        assert SagaStatus.PENDING == "pending"
        assert SagaStatus.COMPENSATED == "compensated"

    def test_saga_step_status_enum(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaStepStatus

        assert SagaStepStatus.SKIPPED == "skipped"

    def test_saga_event_type_enum(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaEventType

        assert SagaEventType.SAGA_STARTED == "saga_started"
        assert SagaEventType.STEP_COMPENSATION_FAILED == "step_compensation_failed"

    def test_compensation_strategy_enum(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import CompensationStrategy

        assert CompensationStrategy.RETRY == "retry"
        assert CompensationStrategy.MANUAL == "manual"

    def test_saga_step_result(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaStepResult

        r = SagaStepResult(success=True, data={"key": "val"})
        assert r.success is True
        assert r.data == {"key": "val"}

        r2 = SagaStepResult(success=False, error="fail")
        assert r2.error == "fail"

    def test_saga_event_defaults(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaEvent,
            SagaEventType,
        )

        e = SagaEvent(event_id="e1", saga_id="s1", event_type=SagaEventType.SAGA_STARTED)
        assert e.timestamp is not None
        assert e.details == {}

    def test_saga_context(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaContext

        ctx = SagaContext(saga_id="s1", tenant_id="t1", correlation_id="c1")
        assert ctx.data == {}
        assert ctx.step_results == {}

    def test_saga_defaults(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga, SagaStatus

        saga = Saga(saga_id="s1", tenant_id="t1", name="test", description="desc")
        assert saga.status == SagaStatus.PENDING
        assert saga.steps == []
        assert saga.current_step_index == 0


class TestSagaStore:
    """Tests for SagaStore (Redis-based)."""

    @pytest.fixture()
    def mock_redis(self):
        r = AsyncMock()
        r.setex = AsyncMock()
        r.sadd = AsyncMock()
        r.expire = AsyncMock()
        r.get = AsyncMock(return_value=None)
        r.smembers = AsyncMock(return_value=set())
        r.srem = AsyncMock()
        r.delete = AsyncMock()
        return r

    @pytest.fixture()
    def store(self, mock_redis):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaStore

        s = SagaStore(redis_url="redis://test:6379/0")
        s._redis = mock_redis
        return s

    async def test_save_and_get(self, store, mock_redis):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga

        saga = Saga(saga_id="s1", tenant_id="t1", name="test", description="desc")
        await store.save(saga)
        mock_redis.setex.assert_awaited_once()

    async def test_get_returns_none_when_missing(self, store, mock_redis):
        mock_redis.get.return_value = None
        result = await store.get("nonexistent")
        assert result is None

    async def test_get_returns_saga(self, store, mock_redis):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga, SagaStatus

        saga = Saga(saga_id="s2", tenant_id="t2", name="test2", description="d2")
        saga.status = SagaStatus.RUNNING

        saga_dict = store._saga_to_dict(saga)
        mock_redis.get.return_value = json.dumps(saga_dict)

        result = await store.get("s2")
        assert result is not None
        assert result.saga_id == "s2"
        assert result.status == SagaStatus.RUNNING

    async def test_list_by_tenant_empty(self, store, mock_redis):
        mock_redis.smembers.return_value = set()
        result = await store.list_by_tenant("t1")
        assert result == []

    async def test_list_by_tenant_with_status_filter(self, store, mock_redis):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga, SagaStatus

        saga = Saga(saga_id="s3", tenant_id="t3", name="n", description="d")
        saga.status = SagaStatus.COMPLETED
        saga_dict = store._saga_to_dict(saga)

        mock_redis.smembers.return_value = {"s3"}
        mock_redis.get.return_value = json.dumps(saga_dict)

        # Filter for COMPLETED -> should match
        result = await store.list_by_tenant("t3", status=SagaStatus.COMPLETED)
        assert len(result) == 1

        # Filter for FAILED -> should not match
        result = await store.list_by_tenant("t3", status=SagaStatus.FAILED)
        assert len(result) == 0

    async def test_delete_existing(self, store, mock_redis):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga

        saga = Saga(saga_id="s4", tenant_id="t4", name="n", description="d")
        saga_dict = store._saga_to_dict(saga)
        mock_redis.get.return_value = json.dumps(saga_dict)

        result = await store.delete("s4")
        assert result is True
        mock_redis.srem.assert_awaited()
        mock_redis.delete.assert_awaited()

    async def test_delete_nonexistent(self, store, mock_redis):
        mock_redis.get.return_value = None
        result = await store.delete("nope")
        assert result is False

    def test_saga_key(self, store):
        assert store._saga_key("abc") == "acgs:saga:abc"

    def test_tenant_key(self, store):
        assert store._tenant_key("t1") == "acgs:saga:tenant:t1"

    def test_saga_to_dict_roundtrip(self, store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            Saga,
            SagaStatus,
            SagaStepExecution,
            SagaStepStatus,
        )

        saga = Saga(
            saga_id="s5",
            tenant_id="t5",
            name="roundtrip",
            description="desc",
        )
        saga.status = SagaStatus.COMPENSATED
        saga.started_at = datetime.now(UTC)
        saga.completed_at = datetime.now(UTC)
        saga.error_message = "some error"
        saga.steps = [
            SagaStepExecution(
                step_name="step1",
                status=SagaStepStatus.COMPLETED,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                result_data={"key": "val"},
                error_message=None,
            )
        ]

        d = store._saga_to_dict(saga)
        restored = store._dict_to_saga(d)
        assert restored.saga_id == "s5"
        assert restored.status == SagaStatus.COMPENSATED
        assert restored.error_message == "some error"
        assert len(restored.steps) == 1
        assert restored.steps[0].status == SagaStepStatus.COMPLETED


class TestSagaEventPublisher:
    """Tests for SagaEventPublisher."""

    async def test_publish_and_get_events(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaEvent,
            SagaEventPublisher,
            SagaEventType,
        )

        publisher = SagaEventPublisher()
        event = SagaEvent(event_id="e1", saga_id="s1", event_type=SagaEventType.SAGA_STARTED)
        await publisher.publish(event)

        events = publisher.get_events()
        assert len(events) == 1

        events_filtered = publisher.get_events(saga_id="s1")
        assert len(events_filtered) == 1

        events_filtered = publisher.get_events(saga_id="other")
        assert len(events_filtered) == 0

        events_by_type = publisher.get_events(event_type=SagaEventType.SAGA_STARTED)
        assert len(events_by_type) == 1

    async def test_publish_handler_error_caught(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaEvent,
            SagaEventPublisher,
            SagaEventType,
        )

        publisher = SagaEventPublisher()

        async def bad_handler(event):
            raise RuntimeError("handler failure")

        publisher.subscribe(bad_handler)
        event = SagaEvent(event_id="e2", saga_id="s2", event_type=SagaEventType.SAGA_FAILED)
        # Should not raise
        await publisher.publish(event)
        assert len(publisher._event_log) == 1

    async def test_subscribe_multiple_handlers(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaEvent,
            SagaEventPublisher,
            SagaEventType,
        )

        publisher = SagaEventPublisher()
        calls = []

        async def handler1(event):
            calls.append("h1")

        async def handler2(event):
            calls.append("h2")

        publisher.subscribe(handler1)
        publisher.subscribe(handler2)

        event = SagaEvent(event_id="e3", saga_id="s3", event_type=SagaEventType.STEP_STARTED)
        await publisher.publish(event)
        assert calls == ["h1", "h2"]


class TestSagaOrchestrator:
    """Tests for SagaOrchestrator."""

    @pytest.fixture()
    def mock_store(self):
        store = AsyncMock()
        store.save = AsyncMock()
        store.get = AsyncMock(return_value=None)
        store.list_by_tenant = AsyncMock(return_value=[])
        store.get_pending_compensations = AsyncMock(return_value=[])
        return store

    @pytest.fixture()
    def orchestrator(self, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaEventPublisher,
            SagaOrchestrator,
        )

        return SagaOrchestrator(store=mock_store, event_publisher=SagaEventPublisher())

    def _make_step_def(
        self,
        name,
        *,
        succeeds=True,
        order=0,
        compensation_succeeds=True,
        compensation_strategy=None,
    ):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            CompensationStrategy,
            SagaStepDefinition,
            SagaStepResult,
        )

        async def action(ctx):
            if succeeds:
                return SagaStepResult(success=True, data={"step": name})
            return SagaStepResult(success=False, error=f"{name} failed")

        async def compensation(ctx):
            if compensation_succeeds:
                return SagaStepResult(success=True, data={"compensated": name})
            return SagaStepResult(success=False, error=f"comp {name} failed")

        return SagaStepDefinition(
            name=name,
            description=f"Step {name}",
            action=action,
            compensation=compensation,
            order=order,
            max_retries=0,
            retry_delay_seconds=0,
            timeout_seconds=5,
            compensation_strategy=compensation_strategy or CompensationStrategy.RETRY,
        )

    def test_register_and_get_definition(self, orchestrator):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaDefinition

        defn = SagaDefinition(
            name="test_saga",
            description="A test saga",
            steps=[self._make_step_def("s1")],
        )
        orchestrator.register_saga(defn)
        assert orchestrator.get_definition("test_saga") is not None
        assert orchestrator.get_definition("missing") is None

    async def test_create_saga(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaDefinition

        defn = SagaDefinition(
            name="create_test",
            description="test",
            steps=[self._make_step_def("s1")],
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("create_test", "tenant-1", {"key": "val"})
        assert saga.tenant_id == "tenant-1"
        assert saga.context is not None
        assert saga.context.data == {"key": "val"}
        assert len(saga.steps) == 1
        mock_store.save.assert_awaited()

    async def test_create_saga_unknown_definition(self, orchestrator):
        with pytest.raises(ValueError, match="Unknown saga definition"):
            await orchestrator.create_saga("nonexistent", "t1")

    async def test_execute_saga_success(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaDefinition,
            SagaStatus,
        )

        defn = SagaDefinition(
            name="exec_ok",
            description="test",
            steps=[
                self._make_step_def("step1", order=0),
                self._make_step_def("step2", order=1),
            ],
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("exec_ok", "t1")
        mock_store.get.return_value = saga

        result = await orchestrator.execute(saga.saga_id)
        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) == 2

    async def test_execute_saga_step_failure_triggers_compensation(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaDefinition,
            SagaStatus,
        )

        defn = SagaDefinition(
            name="exec_fail",
            description="test",
            steps=[
                self._make_step_def("step1", order=0, succeeds=True),
                self._make_step_def("step2", order=1, succeeds=False),
            ],
            max_compensation_retries=0,
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("exec_fail", "t1")
        mock_store.get.return_value = saga

        result = await orchestrator.execute(saga.saga_id)
        assert result.success is False
        assert result.failed_step == "step2"
        assert "step1" in result.compensated_steps

    async def test_execute_saga_not_found(self, orchestrator, mock_store):
        mock_store.get.return_value = None
        with pytest.raises(ValueError, match="Saga not found"):
            await orchestrator.execute("missing-id")

    async def test_execute_saga_definition_not_found(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga

        saga = Saga(saga_id="s1", tenant_id="t1", name="missing_def", description="d")
        mock_store.get.return_value = saga

        with pytest.raises(ValueError, match="Saga definition not found"):
            await orchestrator.execute("s1")

    async def test_execute_compensation_failure(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaDefinition,
            SagaStatus,
        )

        defn = SagaDefinition(
            name="comp_fail",
            description="test",
            steps=[
                self._make_step_def("step1", order=0, compensation_succeeds=False),
                self._make_step_def("step2", order=1, succeeds=False),
            ],
            max_compensation_retries=0,
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("comp_fail", "t1")
        mock_store.get.return_value = saga

        result = await orchestrator.execute(saga.saga_id)
        assert result.success is False
        assert result.status == SagaStatus.PARTIALLY_COMPENSATED

    async def test_execute_compensation_skip_strategy(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            CompensationStrategy,
            SagaDefinition,
            SagaStatus,
        )

        defn = SagaDefinition(
            name="comp_skip",
            description="test",
            steps=[
                self._make_step_def(
                    "step1",
                    order=0,
                    compensation_succeeds=False,
                    compensation_strategy=CompensationStrategy.SKIP,
                ),
                self._make_step_def("step2", order=1, succeeds=False),
            ],
            max_compensation_retries=0,
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("comp_skip", "t1")
        mock_store.get.return_value = saga

        result = await orchestrator.execute(saga.saga_id)
        assert result.success is False
        # SKIP strategy makes compensation "succeed"
        assert result.status == SagaStatus.COMPENSATED

    async def test_cancel_saga_pending(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaDefinition,
            SagaStatus,
        )

        defn = SagaDefinition(
            name="cancel_test",
            description="test",
            steps=[self._make_step_def("s1")],
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("cancel_test", "t1")
        mock_store.get.return_value = saga

        result = await orchestrator.cancel_saga(saga.saga_id)
        assert result is True

    async def test_cancel_saga_not_found(self, orchestrator, mock_store):
        mock_store.get.return_value = None
        assert await orchestrator.cancel_saga("missing") is False

    async def test_cancel_saga_completed(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga, SagaStatus

        saga = Saga(saga_id="s1", tenant_id="t1", name="n", description="d")
        saga.status = SagaStatus.COMPLETED
        mock_store.get.return_value = saga

        assert await orchestrator.cancel_saga("s1") is False

    async def test_cancel_saga_no_definition(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga, SagaStatus

        saga = Saga(saga_id="s1", tenant_id="t1", name="unknown", description="d")
        saga.status = SagaStatus.RUNNING
        mock_store.get.return_value = saga

        assert await orchestrator.cancel_saga("s1") is False

    async def test_cancel_saga_with_completed_steps(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaDefinition,
            SagaStatus,
            SagaStepExecution,
            SagaStepStatus,
        )

        defn = SagaDefinition(
            name="cancel_comp",
            description="test",
            steps=[self._make_step_def("s1"), self._make_step_def("s2", order=1)],
            max_compensation_retries=0,
        )
        orchestrator.register_saga(defn)

        saga = await orchestrator.create_saga("cancel_comp", "t1")
        saga.status = SagaStatus.RUNNING
        saga.steps[0].status = SagaStepStatus.COMPLETED
        mock_store.get.return_value = saga

        result = await orchestrator.cancel_saga(saga.saga_id)
        assert result is True

    async def test_get_saga(self, orchestrator, mock_store):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import Saga

        saga = Saga(saga_id="s1", tenant_id="t1", name="n", description="d")
        mock_store.get.return_value = saga
        result = await orchestrator.get_saga("s1")
        assert result is saga

    async def test_list_sagas(self, orchestrator, mock_store):
        mock_store.list_by_tenant.return_value = []
        result = await orchestrator.list_sagas("t1")
        assert result == []


class TestSagaMetrics:
    """Tests for SagaMetrics."""

    def test_record_successful_saga(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaExecutionResult,
            SagaMetrics,
            SagaStatus,
        )

        metrics = SagaMetrics()
        result = SagaExecutionResult(
            saga_id="s1",
            success=True,
            status=SagaStatus.COMPLETED,
            completed_steps=["s1", "s2"],
            execution_time_ms=150.0,
        )
        metrics.record_saga_completed(result)

        stats = metrics.get_stats()
        assert stats["total_sagas"] == 1
        assert stats["successful_sagas"] == 1
        assert stats["failed_sagas"] == 0
        assert stats["success_rate"] == 100.0
        assert stats["total_steps_executed"] == 2
        assert stats["average_execution_time_ms"] == 150.0

    def test_record_failed_saga_with_compensation(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaExecutionResult,
            SagaMetrics,
            SagaStatus,
        )

        metrics = SagaMetrics()
        result = SagaExecutionResult(
            saga_id="s2",
            success=False,
            status=SagaStatus.COMPENSATED,
            completed_steps=["s1"],
            failed_step="s2",
            compensated_steps=["s1"],
            error="step failed",
            execution_time_ms=200.0,
        )
        metrics.record_saga_completed(result)

        stats = metrics.get_stats()
        assert stats["failed_sagas"] == 1
        assert stats["compensated_sagas"] == 1
        assert stats["total_compensations"] == 1
        assert stats["success_rate"] == 0

    def test_get_stats_empty(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaMetrics

        metrics = SagaMetrics()
        stats = metrics.get_stats()
        assert stats["total_sagas"] == 0
        assert stats["success_rate"] == 0
        assert stats["average_execution_time_ms"] == 0


class TestMigrationSagaBuilder:
    """Tests for MigrationSagaBuilder."""

    @pytest.fixture()
    def builder(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            MigrationSagaBuilder,
            SagaOrchestrator,
            SagaStore,
        )

        store = AsyncMock()
        store.save = AsyncMock()
        orchestrator = SagaOrchestrator(store=store)
        return MigrationSagaBuilder(orchestrator)

    def test_build_policy_migration_saga(self, builder):
        defn = builder.build_policy_migration_saga()
        assert defn.name == "policy_migration"
        assert len(defn.steps) == 5
        step_names = [s.name for s in defn.steps]
        assert "validate_source" in step_names
        assert "verify_migration" in step_names

    def test_build_database_migration_saga(self, builder):
        defn = builder.build_database_migration_saga()
        assert defn.name == "database_migration"
        assert len(defn.steps) == 4
        step_names = [s.name for s in defn.steps]
        assert "backup_database" in step_names
        assert "validate_migration" in step_names

    async def test_policy_migration_mock_handlers(self, builder):
        """Verify mock handlers work correctly."""
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaContext

        defn = builder.build_policy_migration_saga()

        ctx = SagaContext(
            saga_id="s1",
            tenant_id="t1",
            correlation_id="c1",
            data={"source_tenant_id": "src", "target_tenant_id": "tgt"},
        )

        # Execute validate_source step
        result = await defn.steps[0].action(ctx)
        assert result.success is True

        # Execute export step
        result = await defn.steps[1].action(ctx)
        assert result.success is True

        # Compensation for export
        result = await defn.steps[1].compensation(ctx)
        assert result.success is True

    async def test_policy_migration_missing_required_key(self, builder):
        """Validate source step fails when source_tenant_id missing."""
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaContext

        defn = builder.build_policy_migration_saga()

        ctx = SagaContext(
            saga_id="s1",
            tenant_id="t1",
            correlation_id="c1",
            data={},
        )

        result = await defn.steps[0].action(ctx)
        assert result.success is False
        assert "Missing" in result.error

    async def test_database_migration_mock_handlers(self, builder):
        """Verify database migration mock handlers work correctly."""
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import SagaContext

        defn = builder.build_database_migration_saga()

        ctx = SagaContext(
            saga_id="s1",
            tenant_id="t1",
            correlation_id="c1",
            data={"target_version": "v2.0.0", "expected_records": 100},
        )

        for step in defn.steps:
            result = await step.action(ctx)
            assert result.success is True

            result = await step.compensation(ctx)
            assert result.success is True


class TestSagaRecoveryService:
    """Tests for SagaRecoveryService."""

    async def test_start_and_stop(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaOrchestrator,
            SagaRecoveryService,
        )

        store = AsyncMock()
        store.get_pending_compensations = AsyncMock(return_value=[])
        store.save = AsyncMock()
        orchestrator = SagaOrchestrator(store=store)
        recovery = SagaRecoveryService(orchestrator)

        await recovery.start(check_interval_seconds=1)
        assert recovery._running is True
        assert recovery._recovery_task is not None

        await recovery.stop()
        assert recovery._running is False

    async def test_recover_pending_compensations(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            Saga,
            SagaDefinition,
            SagaOrchestrator,
            SagaRecoveryService,
            SagaStatus,
            SagaStepExecution,
            SagaStepResult,
            SagaStepStatus,
        )

        saga = Saga(saga_id="s1", tenant_id="t1", name="recover", description="d")
        saga.status = SagaStatus.COMPENSATING
        saga.steps = [SagaStepExecution(step_name="s1", status=SagaStepStatus.COMPLETED)]

        store = AsyncMock()
        store.get_pending_compensations = AsyncMock(return_value=[saga])
        store.save = AsyncMock()
        store.get = AsyncMock(return_value=saga)

        async def comp(ctx):
            return SagaStepResult(success=True)

        defn = SagaDefinition(
            name="recover",
            description="d",
            steps=[
                MagicMock(
                    name="s1",
                    compensation=comp,
                    timeout_seconds=5,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=0,
                )
            ],
            max_compensation_retries=0,
        )

        orchestrator = SagaOrchestrator(store=store)
        orchestrator.register_saga(defn)

        recovery = SagaRecoveryService(orchestrator)
        await recovery._recover_pending_compensations()

        store.save.assert_awaited()


class TestRunWithRetries:
    """Tests for the _run_with_retries method."""

    @pytest.fixture()
    def orchestrator(self):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaOrchestrator,
        )

        store = AsyncMock()
        return SagaOrchestrator(store=store)

    async def test_timeout_error(self, orchestrator):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaContext,
            SagaStepExecution,
            SagaStepResult,
        )

        async def slow_action(ctx):
            await asyncio.sleep(10)
            return SagaStepResult(success=True)

        ctx = SagaContext(saga_id="s1", tenant_id="t1", correlation_id="c1")
        step_exec = SagaStepExecution(step_name="slow_step")

        result = await orchestrator._run_with_retries(
            action=slow_action,
            context=ctx,
            timeout_seconds=0,  # immediate timeout
            max_retries=0,
            retry_delay_seconds=0,
            step_execution=step_exec,
        )
        assert result.success is False
        assert "timed out" in result.error

    async def test_exception_during_action(self, orchestrator):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaContext,
            SagaStepExecution,
            SagaStepResult,
        )

        async def failing_action(ctx):
            raise RuntimeError("action failed")

        ctx = SagaContext(saga_id="s1", tenant_id="t1", correlation_id="c1")
        step_exec = SagaStepExecution(step_name="fail_step")

        result = await orchestrator._run_with_retries(
            action=failing_action,
            context=ctx,
            timeout_seconds=5,
            max_retries=0,
            retry_delay_seconds=0,
            step_execution=step_exec,
        )
        assert result.success is False
        assert "action failed" in result.error

    async def test_compensation_retry_tracking(self, orchestrator):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaContext,
            SagaStepExecution,
            SagaStepResult,
        )

        async def fail_comp(ctx):
            raise RuntimeError("comp fail")

        ctx = SagaContext(saga_id="s1", tenant_id="t1", correlation_id="c1")
        step_exec = SagaStepExecution(step_name="comp_step")

        result = await orchestrator._run_with_retries(
            action=fail_comp,
            context=ctx,
            timeout_seconds=5,
            max_retries=1,
            retry_delay_seconds=0,
            step_execution=step_exec,
            is_compensation=True,
        )
        assert result.success is False
        assert step_exec.compensation_retry_count == 2

    async def test_unsuccessful_result_without_exception(self, orchestrator):
        from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
            SagaContext,
            SagaStepExecution,
            SagaStepResult,
        )

        async def soft_fail(ctx):
            return SagaStepResult(success=False, error="soft failure")

        ctx = SagaContext(saga_id="s1", tenant_id="t1", correlation_id="c1")
        step_exec = SagaStepExecution(step_name="soft")

        result = await orchestrator._run_with_retries(
            action=soft_fail,
            context=ctx,
            timeout_seconds=5,
            max_retries=0,
            retry_delay_seconds=0,
            step_execution=step_exec,
        )
        assert result.success is False
        assert "soft failure" in result.error
