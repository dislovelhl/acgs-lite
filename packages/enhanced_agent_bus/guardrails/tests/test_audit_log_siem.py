"""
Tests for SIEM integration in audit_log.py.

Tests Splunk and Elasticsearch providers with comprehensive coverage
of success, failure, and edge cases.

Constitutional Hash: 608508a9bd224290
"""

import json
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.guardrails.audit_log import (
    AuditLog,
    AuditLogConfig,
)
from enhanced_agent_bus.guardrails.enums import GuardrailLayer, SafetyAction
from enhanced_agent_bus.guardrails.siem_providers import (
    ElasticsearchProvider,
    SIEMProviderConfig,
    SIEMProviderType,
    SplunkHECProvider,
    create_siem_provider,
)


@pytest.fixture
def splunk_config():
    """Provide Splunk HEC configuration."""
    return SIEMProviderConfig(
        provider_type=SIEMProviderType.SPLUNK,
        endpoint_url="https://splunk.example.com:8088/services/collector/event",
        auth_token="test-token-123",
        index="acgs2_audit_test",
        source_type="acgs2:test",
        verify_ssl=False,
        timeout_seconds=5.0,
        max_retries=2,
    )


@pytest.fixture
def elasticsearch_config():
    """Provide Elasticsearch configuration."""
    return SIEMProviderConfig(
        provider_type=SIEMProviderType.ELASTICSEARCH,
        endpoint_url="https://elasticsearch.example.com:9200",
        auth_token="test-api-key",
        index="acgs2_audit_test",
        verify_ssl=False,
        timeout_seconds=5.0,
        max_retries=2,
    )


@pytest.fixture
def sample_audit_entry():
    """Provide sample audit entry data."""
    return {
        "trace_id": "test-trace-123",
        "timestamp": datetime.now(UTC).isoformat(),
        "layer": "INPUT_SANITIZER",
        "action": "ALLOW",
        "allowed": True,
        "violations": [],
        "processing_time_ms": 5.2,
        "metadata": {"test": True},
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


@pytest.fixture
def audit_log_with_siem():
    """Provide AuditLog with SIEM enabled."""
    config = AuditLogConfig(
        enabled=True,
        log_to_siem=True,
        siem_providers=[
            {
                "provider_type": "splunk",
                "endpoint_url": "https://splunk.example.com:8088/services/collector/event",
                "auth_token": "test-token",
                "index": "test_index",
            }
        ],
    )
    return AuditLog(config=config)


class TestSIEMProviderConfig:
    """Test suite for SIEMProviderConfig."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.SPLUNK,
            endpoint_url="https://test.com",
            auth_token="token",
        )
        assert config.index == "acgs2_audit"
        assert config.source_type == "acgs2:audit"
        assert config.verify_ssl is True
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 3
        assert config.enabled is True

    def test_custom_values(self):
        """Config should accept custom values."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.ELASTICSEARCH,
            endpoint_url="https://es.example.com:9200",
            auth_token="api-key",
            index="custom_index",
            source_type="custom:source",
            verify_ssl=False,
            timeout_seconds=10.0,
            max_retries=5,
            enabled=False,
        )
        assert config.provider_type == SIEMProviderType.ELASTICSEARCH
        assert config.endpoint_url == "https://es.example.com:9200"
        assert config.auth_token == "api-key"
        assert config.index == "custom_index"
        assert config.source_type == "custom:source"
        assert config.verify_ssl is False
        assert config.timeout_seconds == 10.0
        assert config.max_retries == 5
        assert config.enabled is False


class TestSplunkHECProvider:
    """Test suite for SplunkHECProvider."""

    async def test_send_event_success(self, splunk_config, sample_audit_entry):
        """Should successfully send event to Splunk."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"code": 0, "text": "Success"}
            mock_post.return_value = mock_response

            result = await provider.send_event(sample_audit_entry)

            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert splunk_config.endpoint_url in str(call_args)

    async def test_send_event_server_error(self, splunk_config, sample_audit_entry):
        """Should handle server error response."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response

            result = await provider.send_event(sample_audit_entry)

            assert result is False

    async def test_send_event_timeout(self, splunk_config, sample_audit_entry):
        """Should handle timeout with retry."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Connection timeout")

            result = await provider.send_event(sample_audit_entry)

            assert result is False
            # Should have retried max_retries times
            assert mock_post.call_count == splunk_config.max_retries

    async def test_send_event_connection_error(self, splunk_config, sample_audit_entry):
        """Should handle connection error."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            result = await provider.send_event(sample_audit_entry)

            assert result is False

    async def test_health_check_success(self, splunk_config):
        """Should return healthy status."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            health = await provider.health_check()

            assert health["status"] == "healthy"
            assert health["status_code"] == 200

    async def test_health_check_failure(self, splunk_config):
        """Should return unhealthy status on failure."""
        provider = SplunkHECProvider(splunk_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")

            health = await provider.health_check()

            assert health["status"] == "unhealthy"
            assert "error" in health

    def test_hec_payload_format(self, splunk_config, sample_audit_entry):
        """Should format HEC payload correctly."""
        provider = SplunkHECProvider(splunk_config)
        enriched = provider._enrich_event(sample_audit_entry)

        assert "_siem_metadata" in enriched
        assert enriched["_siem_metadata"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert enriched["_siem_metadata"]["provider"] == "splunk"

    def test_invalid_provider_type(self):
        """Should raise error for invalid provider type."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.ELASTICSEARCH,  # Wrong type
            endpoint_url="https://test.com",
            auth_token="token",
        )
        with pytest.raises(ACGSValidationError, match="SPLUNK"):
            SplunkHECProvider(config)


class TestElasticsearchProvider:
    """Test suite for ElasticsearchProvider."""

    async def test_send_event_success(self, elasticsearch_config, sample_audit_entry):
        """Should successfully index event in Elasticsearch."""
        provider = ElasticsearchProvider(elasticsearch_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"result": "created"}
            mock_post.return_value = mock_response

            result = await provider.send_event(sample_audit_entry)

            assert result is True

    async def test_send_event_updated(self, elasticsearch_config, sample_audit_entry):
        """Should handle updated result."""
        provider = ElasticsearchProvider(elasticsearch_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "updated"}
            mock_post.return_value = mock_response

            result = await provider.send_event(sample_audit_entry)

            assert result is True

    async def test_send_event_index_not_found(self, elasticsearch_config, sample_audit_entry):
        """Should attempt to create index if not found."""
        provider = ElasticsearchProvider(elasticsearch_config)

        with (
            patch("httpx.AsyncClient.post") as mock_post,
            patch("httpx.AsyncClient.put") as mock_put,
        ):
            # First call returns 404, index creation succeeds
            mock_post.side_effect = [
                MagicMock(status_code=404, text="Index not found"),
                MagicMock(status_code=201, json=lambda: {"result": "created"}),
            ]
            mock_put.return_value = MagicMock(status_code=200)

            result = await provider.send_event(sample_audit_entry)

            assert result is True
            assert mock_post.call_count == 2
            mock_put.assert_called_once()

    async def test_send_event_timeout(self, elasticsearch_config, sample_audit_entry):
        """Should handle timeout with retry."""
        provider = ElasticsearchProvider(elasticsearch_config)

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            result = await provider.send_event(sample_audit_entry)

            assert result is False
            assert mock_post.call_count == elasticsearch_config.max_retries

    async def test_health_check_success(self, elasticsearch_config):
        """Should return cluster health status."""
        provider = ElasticsearchProvider(elasticsearch_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "green",
                "cluster_name": "test-cluster",
                "number_of_nodes": 3,
            }
            mock_get.return_value = mock_response

            health = await provider.health_check()

            assert health["status"] == "green"
            assert health["cluster_name"] == "test-cluster"
            assert health["number_of_nodes"] == 3

    def test_index_name_generation(self, elasticsearch_config):
        """Should generate index name with date suffix."""
        provider = ElasticsearchProvider(elasticsearch_config)
        index_name = provider._get_index_name()

        # Should contain prefix and date
        assert index_name.startswith("acgs2_audit_test-")
        # Should have date format YYYY.MM.DD
        parts = index_name.split("-")
        assert len(parts) == 2
        date_parts = parts[1].split(".")
        assert len(date_parts) == 3

    def test_event_enrichment(self, elasticsearch_config, sample_audit_entry):
        """Should enrich event with metadata."""
        provider = ElasticsearchProvider(elasticsearch_config)
        enriched = provider._enrich_event(sample_audit_entry)

        assert "_siem_metadata" in enriched
        assert enriched["_siem_metadata"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert enriched["_siem_metadata"]["provider"] == "elasticsearch"

    def test_invalid_provider_type(self):
        """Should raise error for invalid provider type."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.SPLUNK,  # Wrong type
            endpoint_url="https://test.com",
            auth_token="token",
        )
        with pytest.raises(ACGSValidationError, match="ELASTICSEARCH"):
            ElasticsearchProvider(config)


class TestCreateSIEMProvider:
    """Test suite for create_siem_provider factory function."""

    def test_create_splunk_provider(self):
        """Factory should create Splunk provider."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.SPLUNK,
            endpoint_url="https://splunk.example.com",
            auth_token="token",
        )
        provider = create_siem_provider(config)
        assert isinstance(provider, SplunkHECProvider)

    def test_create_elasticsearch_provider(self):
        """Factory should create Elasticsearch provider."""
        config = SIEMProviderConfig(
            provider_type=SIEMProviderType.ELASTICSEARCH,
            endpoint_url="https://es.example.com",
            auth_token="token",
        )
        provider = create_siem_provider(config)
        assert isinstance(provider, ElasticsearchProvider)

    def test_create_unknown_provider(self):
        """Factory should raise error for unknown provider type."""
        # Create a mock config with invalid type
        config = MagicMock()
        config.provider_type = "unknown"

        with pytest.raises(ACGSValidationError, match="Unsupported"):
            create_siem_provider(config)


class TestAuditLogSIEMIntegration:
    """Test suite for AuditLog SIEM integration."""

    async def test_siem_initialization(self):
        """AuditLog should initialize SIEM providers from config."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[
                {
                    "provider_type": "splunk",
                    "endpoint_url": "https://splunk.example.com",
                    "auth_token": "token1",
                    "index": "idx1",
                },
                {
                    "provider_type": "elasticsearch",
                    "endpoint_url": "https://es.example.com",
                    "auth_token": "token2",
                    "index": "idx2",
                },
            ],
        )

        audit_log = AuditLog(config=config)

        assert len(audit_log._siem_providers) == 2
        assert audit_log._siem_metrics["providers_configured"] == 2

    async def test_siem_disabled_no_providers(self):
        """Should not initialize providers when SIEM disabled."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=False,
            siem_providers=[
                {
                    "provider_type": "splunk",
                    "endpoint_url": "https://splunk.example.com",
                    "auth_token": "token",
                }
            ],
        )

        audit_log = AuditLog(config=config)

        assert len(audit_log._siem_providers) == 0

    async def test_log_to_siem_success(self, sample_audit_entry):
        """Should successfully log to SIEM."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[
                {
                    "provider_type": "splunk",
                    "endpoint_url": "https://splunk.example.com",
                    "auth_token": "token",
                }
            ],
        )

        audit_log = AuditLog(config=config)

        # Mock the provider's send_event method
        mock_provider = MagicMock()
        mock_provider.send_event = AsyncMock(return_value=True)
        mock_provider.__class__.__name__ = "MockSplunkProvider"
        audit_log._siem_providers = [mock_provider]

        await audit_log._log_to_siem(sample_audit_entry)

        mock_provider.send_event.assert_called_once()
        assert audit_log._siem_metrics["events_sent"] == 1

    async def test_log_to_siem_multiple_providers(self, sample_audit_entry):
        """Should log to all configured providers."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_fail_silent=True,
        )

        audit_log = AuditLog(config=config)

        # Mock multiple providers
        mock_provider1 = MagicMock()
        mock_provider1.send_event = AsyncMock(return_value=True)
        mock_provider1.__class__.__name__ = "Provider1"

        mock_provider2 = MagicMock()
        mock_provider2.send_event = AsyncMock(return_value=True)
        mock_provider2.__class__.__name__ = "Provider2"

        audit_log._siem_providers = [mock_provider1, mock_provider2]

        await audit_log._log_to_siem(sample_audit_entry)

        mock_provider1.send_event.assert_called_once()
        mock_provider2.send_event.assert_called_once()
        assert audit_log._siem_metrics["events_sent"] == 2

    async def test_log_to_siem_partial_failure(self, sample_audit_entry):
        """Should handle partial provider failures."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_fail_silent=True,
        )

        audit_log = AuditLog(config=config)

        # One succeeds, one fails
        mock_provider1 = MagicMock()
        mock_provider1.send_event = AsyncMock(return_value=True)
        mock_provider1.__class__.__name__ = "Provider1"

        mock_provider2 = MagicMock()
        mock_provider2.send_event = AsyncMock(return_value=False)
        mock_provider2.__class__.__name__ = "Provider2"

        audit_log._siem_providers = [mock_provider1, mock_provider2]

        await audit_log._log_to_siem(sample_audit_entry)

        assert audit_log._siem_metrics["events_sent"] == 1
        assert audit_log._siem_metrics["events_failed"] == 1

    async def test_log_to_siem_fail_not_silent(self, sample_audit_entry):
        """Should raise exception when siem_fail_silent is False."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_fail_silent=False,
        )

        audit_log = AuditLog(config=config)

        mock_provider = MagicMock()
        mock_provider.send_event = AsyncMock(return_value=False)
        mock_provider.__class__.__name__ = "FailingProvider"
        audit_log._siem_providers = [mock_provider]

        with pytest.raises(RuntimeError, match="SIEM logging failed"):
            await audit_log._log_to_siem(sample_audit_entry)

    async def test_log_to_siem_exception_handling(self, sample_audit_entry):
        """Should handle provider exceptions gracefully."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_fail_silent=True,
        )

        audit_log = AuditLog(config=config)

        mock_provider = MagicMock()
        mock_provider.send_event = AsyncMock(side_effect=RuntimeError("Provider error"))
        mock_provider.__class__.__name__ = "ExceptionProvider"
        audit_log._siem_providers = [mock_provider]

        await audit_log._log_to_siem(sample_audit_entry)

        assert audit_log._siem_metrics["events_failed"] == 1

    async def test_siem_enrichment(self, sample_audit_entry):
        """Should enrich events with SIEM metadata."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
        )

        audit_log = AuditLog(config=config)

        mock_provider = MagicMock()
        mock_provider.send_event = AsyncMock(return_value=True)
        mock_provider.__class__.__name__ = "MockProvider"
        audit_log._siem_providers = [mock_provider]

        await audit_log._log_to_siem(sample_audit_entry)

        # Check that event was enriched
        call_args = mock_provider.send_event.call_args[0][0]
        assert "_siem" in call_args
        assert call_args["_siem"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert call_args["_siem"]["source"] == "acgs2_audit_log"

    def test_get_siem_metrics(self):
        """Should return SIEM metrics."""
        config = AuditLogConfig(enabled=True, log_to_siem=True)
        audit_log = AuditLog(config=config)
        audit_log._siem_metrics = {
            "events_sent": 10,
            "events_failed": 2,
            "providers_configured": 1,
        }

        metrics = audit_log.get_siem_metrics()

        assert metrics["events_sent"] == 10
        assert metrics["events_failed"] == 2
        assert metrics["providers_configured"] == 1

    async def test_health_check_siem(self):
        """Should check health of all SIEM providers."""
        config = AuditLogConfig(enabled=True, log_to_siem=True)
        audit_log = AuditLog(config=config)

        mock_provider = MagicMock()
        mock_provider.health_check = AsyncMock(return_value={"status": "healthy"})
        mock_provider.__class__.__name__ = "MockProvider"
        audit_log._siem_providers = [mock_provider]

        health = await audit_log.health_check_siem()

        assert "MockProvider_0" in health
        assert health["MockProvider_0"]["status"] == "healthy"


class TestAuditLogSIEMEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_required_fields_in_config(self):
        """Should skip providers with missing required fields."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[
                {
                    # Missing endpoint_url and auth_token
                    "provider_type": "splunk",
                }
            ],
        )

        audit_log = AuditLog(config=config)

        # Provider should not be initialized due to missing fields
        assert len(audit_log._siem_providers) == 0

    def test_disabled_provider_skipped(self):
        """Should skip disabled providers."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[
                {
                    "provider_type": "splunk",
                    "endpoint_url": "https://splunk.example.com",
                    "auth_token": "token",
                    "enabled": False,
                }
            ],
        )

        audit_log = AuditLog(config=config)

        assert len(audit_log._siem_providers) == 0

    async def test_no_providers_configured_warning(self, caplog):
        """Should log warning when SIEM enabled but no valid providers."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[],  # Empty list
        )

        with caplog.at_level("WARNING"):
            audit_log = AuditLog(config=config)

        assert "no valid providers configured" in caplog.text.lower()

    async def test_log_to_siem_no_providers(self, sample_audit_entry):
        """Should handle logging when no providers initialized."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[],  # Empty
        )

        audit_log = AuditLog(config=config)

        # Should not raise, just return
        await audit_log._log_to_siem(sample_audit_entry)

    async def test_invalid_provider_type_in_config(self):
        """Should handle invalid provider type gracefully."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_providers=[
                {
                    "provider_type": "invalid_provider",
                    "endpoint_url": "https://example.com",
                    "auth_token": "token",
                }
            ],
        )

        # Should not raise, just skip invalid provider
        audit_log = AuditLog(config=config)
        assert len(audit_log._siem_providers) == 0


class TestAuditLogSIEMEndToEnd:
    """End-to-end tests with AuditLog process method."""

    async def test_process_with_siem_logging(self):
        """Full flow: process audit entry and log to SIEM."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=True,
            siem_fail_silent=True,
        )

        audit_log = AuditLog(config=config)

        mock_provider = MagicMock()
        mock_provider.send_event = AsyncMock(return_value=True)
        mock_provider.__class__.__name__ = "MockProvider"
        audit_log._siem_providers = [mock_provider]

        context = {
            "trace_id": "e2e-test-123",
            "current_layer": GuardrailLayer.AUDIT_LOG,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 10.0,
            "metadata": {"e2e": True},
        }

        result = await audit_log.process(data="test", context=context)

        assert result.allowed is True
        mock_provider.send_event.assert_called_once()

    async def test_process_siem_disabled(self):
        """Process should not call SIEM when disabled."""
        config = AuditLogConfig(
            enabled=True,
            log_to_siem=False,
        )

        audit_log = AuditLog(config=config)
        audit_log._log_to_siem = AsyncMock()

        context = {
            "trace_id": "test-123",
            "current_layer": GuardrailLayer.AUDIT_LOG,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 1.0,
            "metadata": {},
        }

        await audit_log.process(data="test", context=context)

        audit_log._log_to_siem.assert_not_called()


@pytest.mark.constitutional
def test_siem_providers_constitutional_hash():
    """All SIEM events should include constitutional hash."""
    from enhanced_agent_bus.guardrails.siem_providers import (
        CONSTITUTIONAL_HASH as ProviderHash,
    )

    assert ProviderHash == CONSTITUTIONAL_HASH
