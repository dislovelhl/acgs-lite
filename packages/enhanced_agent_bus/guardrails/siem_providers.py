"""
SIEM Provider Abstraction for Audit Log Integration.

Provides pluggable SIEM backends for the AuditLog guardrail component.
Supports Splunk HTTP Event Collector (HEC) and Elasticsearch.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

import httpx

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import (
    ServiceUnavailableError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_SIEM_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    OSError,
    httpx.HTTPError,
)


class SIEMProviderType(Enum):
    """Supported SIEM provider types."""

    SPLUNK = "splunk"
    ELASTICSEARCH = "elasticsearch"


@dataclass
class SIEMProviderConfig:
    """Configuration for a SIEM provider.

    Attributes:
        provider_type: Type of SIEM provider (splunk, elasticsearch)
        endpoint_url: Full URL endpoint for the SIEM
        auth_token: Authentication token (HEC token for Splunk, API key for ES)
        index: Target index name (Splunk index or ES index)
        source_type: Event source type (for Splunk)
        verify_ssl: Whether to verify SSL certificates
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        enabled: Whether this provider is enabled
    """

    provider_type: SIEMProviderType
    endpoint_url: str
    auth_token: str
    index: str = "acgs2_audit"
    source_type: str = "acgs2:audit"
    verify_ssl: bool = True
    timeout_seconds: float = 30.0
    max_retries: int = 3
    enabled: bool = True


class SIEMProvider(ABC):
    """Abstract base class for SIEM providers.

    All SIEM implementations must inherit from this class and implement
    the send_event method for shipping audit events.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: SIEMProviderConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SIEMProvider:
        """Enter async context manager."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager."""
        await self.close()

    async def start(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                verify=self.config.verify_ssl,
            )
            logger.debug(f"SIEM provider {self.__class__.__name__} started")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug(f"SIEM provider {self.__class__.__name__} closed")

    @abstractmethod
    async def send_event(self, event: JSONDict) -> bool:
        """Send an audit event to the SIEM.

        Args:
            event: The audit event data to send

        Returns:
            True if event was sent successfully, False otherwise
        """
        ...

    def _format_timestamp(self) -> str:
        """Format current timestamp in ISO format."""
        return datetime.now(UTC).isoformat()

    def _enrich_event(self, event: JSONDict) -> JSONDict:
        """Enrich event with SIEM-specific metadata.

        Args:
            event: Original audit event

        Returns:
            Enriched event with additional metadata
        """
        enriched = dict(event)
        enriched["_siem_metadata"] = {
            "ingestion_timestamp": self._format_timestamp(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "provider": self.config.provider_type.value,
        }
        return enriched


class SplunkHECProvider(SIEMProvider):
    """Splunk HTTP Event Collector (HEC) provider.

    Ships audit events to Splunk using the HTTP Event Collector API.
    Supports both raw and event endpoints with proper HEC formatting.

    Documentation: https://docs.splunk.com/Documentation/Splunk/latest/Data/HECExamples

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: SIEMProviderConfig):
        super().__init__(config)
        if config.provider_type != SIEMProviderType.SPLUNK:
            raise ACGSValidationError(
                "SplunkHECProvider requires provider_type=SPLUNK",
                error_code="SIEM_PROVIDER_TYPE_MISMATCH",
            )

    async def send_event(self, event: JSONDict) -> bool:
        """Send event to Splunk HEC.

        Args:
            event: The audit event data

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._client:
            await self.start()

        if self._client is None:
            raise ServiceUnavailableError(
                "SIEM client not initialized",
                error_code="SIEM_CLIENT_NOT_INITIALIZED",
            )

        try:
            enriched = self._enrich_event(event)
            hec_payload = self._build_hec_payload(enriched)
            headers = self._build_splunk_headers()

            return await self._send_with_retry(hec_payload, headers)

        except _SIEM_OPERATION_ERRORS as e:
            logger.error(f"Splunk HEC: Unexpected error sending event: {e}")
            return False

    def _build_hec_payload(self, enriched_event: JSONDict) -> JSONDict:
        """Build HEC payload for Splunk.

        Args:
            enriched_event: Enriched audit event

        Returns:
            HEC formatted payload
        """
        return {
            "time": datetime.now(UTC).timestamp(),
            "host": enriched_event.get("hostname", "acgs2-audit"),
            "source": self.config.source_type,
            "sourcetype": "_json",
            "index": self.config.index,
            "event": enriched_event,
        }

    def _build_splunk_headers(self) -> JSONDict:
        """Build headers for Splunk HEC request.

        Returns:
            Request headers dictionary
        """
        return {
            "Authorization": f"Splunk {self.config.auth_token}",
            "Content-Type": "application/json",
        }

    async def _send_with_retry(self, payload: JSONDict, headers: JSONDict) -> bool:
        """Send payload to Splunk with retry logic.

        Args:
            payload: HEC payload to send
            headers: Request headers

        Returns:
            True if sent successfully, False otherwise
        """
        for attempt in range(self.config.max_retries):
            try:
                if await self._attempt_splunk_send(payload, headers, attempt):
                    return True

            except (httpx.TimeoutException, httpx.ConnectError, *_SIEM_OPERATION_ERRORS) as e:
                self._log_request_error(e, attempt)

            # Don't retry on last attempt
            if attempt < self.config.max_retries - 1:
                import asyncio

                await asyncio.sleep(2**attempt)  # Exponential backoff

        logger.error("Splunk HEC: Failed to send event after all retries")
        return False

    async def _attempt_splunk_send(
        self, payload: JSONDict, headers: JSONDict, attempt: int
    ) -> bool:
        """Attempt to send event to Splunk.

        Args:
            payload: HEC payload
            headers: Request headers
            attempt: Current attempt number (0-indexed)

        Returns:
            True if successful, False if should retry
        """
        response = await self._client.post(
            self.config.endpoint_url,
            json=payload,
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 0:
                logger.debug(f"Splunk HEC: Event sent successfully (attempt {attempt + 1})")
                return True
            else:
                logger.warning(
                    f"Splunk HEC: Server returned error code {result.get('code')}: "
                    f"{result.get('text')}"
                )
        else:
            logger.warning(f"Splunk HEC: HTTP {response.status_code} (attempt {attempt + 1})")

        return False

    @staticmethod
    def _log_request_error(error: Exception, attempt: int) -> None:
        """Log request errors with consistent format.

        Args:
            error: The exception that occurred
            attempt: Current attempt number (0-indexed)
        """
        if isinstance(error, httpx.TimeoutException):
            logger.warning(f"Splunk HEC: Timeout (attempt {attempt + 1})")
        elif isinstance(error, httpx.ConnectError):
            logger.warning(f"Splunk HEC: Connection error (attempt {attempt + 1}): {error}")
        else:
            logger.warning(f"Splunk HEC: Request error (attempt {attempt + 1}): {error}")

    async def health_check(self) -> JSONDict:
        """Check Splunk HEC health.

        Returns:
            Health status dictionary
        """
        if not self._client:
            await self.start()

        if self._client is None:
            raise ServiceUnavailableError(
                "SIEM client not initialized",
                error_code="SIEM_CLIENT_NOT_INITIALIZED",
            )

        try:
            headers = {"Authorization": f"Splunk {self.config.auth_token}"}
            response = await self._client.get(
                f"{self.config.endpoint_url}/health",
                headers=headers,
            )
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "status_code": response.status_code,
            }
        except _SIEM_OPERATION_ERRORS as e:
            return {"status": "unhealthy", "error": str(e)}


class ElasticsearchProvider(SIEMProvider):
    """Elasticsearch provider for audit logging.

    Ships audit events to Elasticsearch with proper indexing and
    timestamp-based index rotation support.

    Supports both single events and bulk operations.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: SIEMProviderConfig):
        super().__init__(config)
        if config.provider_type != SIEMProviderType.ELASTICSEARCH:
            raise ACGSValidationError(
                "ElasticsearchProvider requires provider_type=ELASTICSEARCH",
                error_code="SIEM_PROVIDER_TYPE_MISMATCH",
            )
        self._index_prefix = config.index

    def _get_index_name(self) -> str:
        """Generate index name with date suffix for rotation.

        Returns:
            Index name like "acgs2_audit-2024.01.15"
        """
        date_suffix = datetime.now(UTC).strftime("%Y.%m.%d")
        return f"{self._index_prefix}-{date_suffix}"

    async def send_event(self, event: JSONDict) -> bool:
        """Send event to Elasticsearch.

        Args:
            event: The audit event data

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._client:
            await self.start()

        if self._client is None:
            raise ServiceUnavailableError(
                "SIEM client not initialized",
                error_code="SIEM_CLIENT_NOT_INITIALIZED",
            )

        try:
            enriched = self._prepare_es_event(event)
            index_name = self._get_index_name()
            url = f"{self.config.endpoint_url}/{index_name}/_doc"
            headers = self._build_es_headers()

            return await self._send_to_es_with_retry(enriched, url, headers, index_name)

        except _SIEM_OPERATION_ERRORS as e:
            logger.error(f"Elasticsearch: Unexpected error sending event: {e}")
            return False

    def _prepare_es_event(self, event: JSONDict) -> JSONDict:
        """Prepare event for Elasticsearch indexing.

        Args:
            event: Original audit event

        Returns:
            Event prepared for ES with timestamp
        """
        enriched = self._enrich_event(event)

        # Ensure timestamp field for ES
        if "@timestamp" not in enriched:
            enriched["@timestamp"] = self._format_timestamp()

        return enriched

    def _build_es_headers(self) -> JSONDict:
        """Build headers for Elasticsearch request.

        Returns:
            Request headers dictionary
        """
        return {
            "Authorization": f"ApiKey {self.config.auth_token}",
            "Content-Type": "application/json",
        }

    async def _send_to_es_with_retry(
        self, enriched: JSONDict, url: str, headers: JSONDict, index_name: str
    ) -> bool:
        """Send event to Elasticsearch with retry logic.

        Args:
            enriched: Prepared event data
            url: Elasticsearch endpoint URL
            headers: Request headers
            index_name: Target index name

        Returns:
            True if sent successfully, False otherwise
        """
        for attempt in range(self.config.max_retries):
            try:
                result = await self._attempt_es_send(enriched, url, headers, index_name, attempt)
                if result is True:
                    return True
                elif result == "retry":
                    continue  # Index creation triggered retry

            except (httpx.TimeoutException, httpx.ConnectError, *_SIEM_OPERATION_ERRORS) as e:
                self._log_es_error(e, attempt)

            # Don't retry on last attempt
            if attempt < self.config.max_retries - 1:
                import asyncio

                await asyncio.sleep(2**attempt)  # Exponential backoff

        logger.error("Elasticsearch: Failed to send event after all retries")
        return False

    async def _attempt_es_send(
        self, enriched: JSONDict, url: str, headers: JSONDict, index_name: str, attempt: int
    ) -> bool | str:
        """Attempt to send event to Elasticsearch.

        Args:
            enriched: Event data to send
            url: Elasticsearch endpoint URL
            headers: Request headers
            index_name: Target index name
            attempt: Current attempt number (0-indexed)

        Returns:
            True if successful, False if failed, "retry" if should retry due to index creation
        """
        response = await self._client.post(url, json=enriched, headers=headers)

        if response.status_code in (200, 201):
            result = response.json()
            if result.get("result") in ("created", "updated"):
                logger.debug(
                    f"Elasticsearch: Event indexed successfully "
                    f"(attempt {attempt + 1}, index: {index_name})"
                )
                return True
            else:
                logger.warning(f"Elasticsearch: Unexpected result: {result.get('result')}")
        elif response.status_code == 404:
            # Index doesn't exist, try to create it
            logger.info(f"Elasticsearch: Index {index_name} not found, attempting to create")
            if await self._create_index(index_name):
                return "retry"  # Signal to retry the document index
            else:
                logger.error(f"Elasticsearch: Failed to create index {index_name}")
        else:
            logger.warning(
                f"Elasticsearch: HTTP {response.status_code} "
                f"(attempt {attempt + 1}): {response.text[:200]}"
            )

        return False

    @staticmethod
    def _log_es_error(error: Exception, attempt: int) -> None:
        """Log Elasticsearch request errors with consistent format.

        Args:
            error: The exception that occurred
            attempt: Current attempt number (0-indexed)
        """
        if isinstance(error, httpx.TimeoutException):
            logger.warning(f"Elasticsearch: Timeout (attempt {attempt + 1})")
        elif isinstance(error, httpx.ConnectError):
            logger.warning(f"Elasticsearch: Connection error (attempt {attempt + 1}): {error}")
        else:
            logger.warning(f"Elasticsearch: Request error (attempt {attempt + 1}): {error}")

    async def _create_index(self, index_name: str) -> bool:
        """Create Elasticsearch index with proper mappings.

        Args:
            index_name: Name of the index to create

        Returns:
            True if created successfully, False otherwise
        """
        if not self._client:
            return False

        try:
            url = f"{self.config.endpoint_url}/{index_name}"
            headers = {"Authorization": f"ApiKey {self.config.auth_token}"}

            # Basic mapping for audit events
            mapping = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                },
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "timestamp": {"type": "date"},
                        "trace_id": {"type": "keyword"},
                        "layer": {"type": "keyword"},
                        "action": {"type": "keyword"},
                        "allowed": {"type": "boolean"},
                        "constitutional_hash": {"type": "keyword"},
                        "processing_time_ms": {"type": "float"},
                    }
                },
            }

            response = await self._client.put(url, json=mapping, headers=headers)
            return response.status_code == 200  # type: ignore[no-any-return]

        except _SIEM_OPERATION_ERRORS as e:
            logger.warning(f"Elasticsearch: Failed to create index {index_name}: {e}")
            return False

    async def health_check(self) -> JSONDict:
        """Check Elasticsearch cluster health.

        Returns:
            Health status dictionary
        """
        if not self._client:
            await self.start()

        if self._client is None:
            raise ServiceUnavailableError(
                "SIEM client not initialized",
                error_code="SIEM_CLIENT_NOT_INITIALIZED",
            )

        try:
            headers = {"Authorization": f"ApiKey {self.config.auth_token}"}
            response = await self._client.get(
                f"{self.config.endpoint_url}/_cluster/health",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": data.get("status", "unknown"),
                    "cluster_name": data.get("cluster_name"),
                    "number_of_nodes": data.get("number_of_nodes"),
                }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                }
        except _SIEM_OPERATION_ERRORS as e:
            return {"status": "unhealthy", "error": str(e)}


def create_siem_provider(config: SIEMProviderConfig) -> SIEMProvider:
    """Factory function to create appropriate SIEM provider.

    Args:
        config: SIEM provider configuration

    Returns:
        Configured SIEM provider instance

    Raises:
        ValueError: If provider type is not supported
    """
    if config.provider_type == SIEMProviderType.SPLUNK:
        return SplunkHECProvider(config)
    elif config.provider_type == SIEMProviderType.ELASTICSEARCH:
        return ElasticsearchProvider(config)
    else:
        raise ACGSValidationError(
            f"Unsupported SIEM provider type: {config.provider_type}",
            error_code="SIEM_PROVIDER_TYPE_UNSUPPORTED",
        )


__all__ = [
    "ElasticsearchProvider",
    "SIEMProvider",
    "SIEMProviderConfig",
    "SIEMProviderType",
    "SplunkHECProvider",
    "create_siem_provider",
]
