"""Tests for guardrails/siem_providers.py — SIEM provider abstraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus._compat.errors import (
    ServiceUnavailableError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)
from enhanced_agent_bus.guardrails.siem_providers import (
    ElasticsearchProvider,
    SIEMProviderConfig,
    SIEMProviderType,
    SplunkHECProvider,
    create_siem_provider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _splunk_config(**overrides: object) -> SIEMProviderConfig:
    defaults = {
        "provider_type": SIEMProviderType.SPLUNK,
        "endpoint_url": "https://splunk.example.com/services/collector",
        "auth_token": "test-token-123",
        "index": "acgs2_audit",
    }
    return SIEMProviderConfig(**{**defaults, **overrides})


def _es_config(**overrides: object) -> SIEMProviderConfig:
    defaults = {
        "provider_type": SIEMProviderType.ELASTICSEARCH,
        "endpoint_url": "https://es.example.com",
        "auth_token": "es-api-key",
        "index": "acgs2_audit",
    }
    return SIEMProviderConfig(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# SIEMProviderConfig
# ---------------------------------------------------------------------------


class TestSIEMProviderConfig:
    def test_defaults(self) -> None:
        cfg = _splunk_config()
        assert cfg.verify_ssl is True
        assert cfg.timeout_seconds == 30.0
        assert cfg.max_retries == 3
        assert cfg.enabled is True
        assert cfg.source_type == "acgs2:audit"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateSIEMProvider:
    def test_creates_splunk(self) -> None:
        provider = create_siem_provider(_splunk_config())
        assert isinstance(provider, SplunkHECProvider)

    def test_creates_elasticsearch(self) -> None:
        provider = create_siem_provider(_es_config())
        assert isinstance(provider, ElasticsearchProvider)

    def test_rejects_unknown_type(self) -> None:
        cfg = _splunk_config()
        # Force an invalid type
        cfg.provider_type = "invalid"  # type: ignore[assignment]
        with pytest.raises(ACGSValidationError):
            create_siem_provider(cfg)


# ---------------------------------------------------------------------------
# SplunkHECProvider
# ---------------------------------------------------------------------------


class TestSplunkHECProvider:
    def test_wrong_provider_type_raises(self) -> None:
        with pytest.raises(ACGSValidationError):
            SplunkHECProvider(_es_config())

    def test_build_hec_payload(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        event = {"action": "test", "_siem_metadata": {}}
        payload = provider._build_hec_payload(event)
        assert "time" in payload
        assert payload["index"] == "acgs2_audit"
        assert payload["event"] is event

    def test_build_splunk_headers(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        headers = provider._build_splunk_headers()
        assert headers["Authorization"] == "Splunk test-token-123"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_event_success(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_event_no_client_starts_one(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        assert provider._client is None

        # Patch start to install a mock client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def fake_start() -> None:
            provider._client = mock_client

        provider.start = fake_start  # type: ignore[assignment]

        result = await provider.send_event({"action": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_event_server_error_code(self) -> None:
        provider = SplunkHECProvider(_splunk_config(max_retries=1))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 5, "text": "internal error"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_event_http_error(self) -> None:
        provider = SplunkHECProvider(_splunk_config(max_retries=1))
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("conn refused"))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"

    def test_log_request_error_timeout(self) -> None:
        # Should not raise
        SplunkHECProvider._log_request_error(httpx.TimeoutException("timeout"), 0)

    def test_log_request_error_connect(self) -> None:
        SplunkHECProvider._log_request_error(httpx.ConnectError("refused"), 1)

    def test_log_request_error_other(self) -> None:
        SplunkHECProvider._log_request_error(RuntimeError("unknown"), 2)


# ---------------------------------------------------------------------------
# ElasticsearchProvider
# ---------------------------------------------------------------------------


class TestElasticsearchProvider:
    def test_wrong_provider_type_raises(self) -> None:
        with pytest.raises(ACGSValidationError):
            ElasticsearchProvider(_splunk_config())

    def test_get_index_name(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        name = provider._get_index_name()
        assert name.startswith("acgs2_audit-")
        assert "." in name  # date format YYYY.MM.DD

    def test_prepare_es_event_adds_timestamp(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        event = {"action": "test"}
        enriched = provider._prepare_es_event(event)
        assert "@timestamp" in enriched
        assert "_siem_metadata" in enriched

    def test_prepare_es_event_preserves_existing_timestamp(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        event = {"action": "test", "@timestamp": "2025-01-01T00:00:00Z"}
        enriched = provider._prepare_es_event(event)
        assert enriched["@timestamp"] == "2025-01-01T00:00:00Z"

    def test_build_es_headers(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        headers = provider._build_es_headers()
        assert headers["Authorization"] == "ApiKey es-api-key"

    @pytest.mark.asyncio
    async def test_send_event_success(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"result": "created"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_event_404_create_index_retry(self) -> None:
        provider = ElasticsearchProvider(_es_config(max_retries=2))

        response_404 = MagicMock()
        response_404.status_code = 404
        response_404.text = "index not found"

        response_201 = MagicMock()
        response_201.status_code = 201
        response_201.json.return_value = {"result": "created"}

        create_response = MagicMock()
        create_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[response_404, response_201])
        mock_client.put = AsyncMock(return_value=create_response)
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_event_exception_returns_false(self) -> None:
        provider = ElasticsearchProvider(_es_config(max_retries=1))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("network error"))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "green",
            "cluster_name": "test",
            "number_of_nodes": 3,
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "green"
        assert result["cluster_name"] == "test"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_status_code(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=OSError("connection refused"))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_create_index_success(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider._create_index("test-index")
        assert result is True

    @pytest.mark.asyncio
    async def test_create_index_failure(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        mock_response = MagicMock()
        mock_response.status_code = 400

        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider._create_index("test-index")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_index_no_client(self) -> None:
        provider = ElasticsearchProvider(_es_config())
        provider._client = None
        result = await provider._create_index("test-index")
        assert result is False

    def test_log_es_error_timeout(self) -> None:
        ElasticsearchProvider._log_es_error(httpx.TimeoutException("timeout"), 0)

    def test_log_es_error_connect(self) -> None:
        ElasticsearchProvider._log_es_error(httpx.ConnectError("refused"), 1)

    def test_log_es_error_other(self) -> None:
        ElasticsearchProvider._log_es_error(RuntimeError("unknown"), 2)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestSIEMProviderContextManager:
    @pytest.mark.asyncio
    async def test_aenter_aexit(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        async with provider as p:
            assert p is provider
            assert p._client is not None
        # After exit, client should be None
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        await provider.close()  # no-op when no client
        assert provider._client is None


# ---------------------------------------------------------------------------
# _enrich_event
# ---------------------------------------------------------------------------


class TestEnrichEvent:
    def test_adds_siem_metadata(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        event = {"action": "test"}
        enriched = provider._enrich_event(event)
        assert "_siem_metadata" in enriched
        meta = enriched["_siem_metadata"]
        assert "ingestion_timestamp" in meta
        assert meta["provider"] == "splunk"

    def test_does_not_mutate_original(self) -> None:
        provider = SplunkHECProvider(_splunk_config())
        event = {"action": "test"}
        provider._enrich_event(event)
        assert "_siem_metadata" not in event
