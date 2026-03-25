"""WorkOS webhook ingestion service with deduplication and audit forwarding.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

from src.core.shared.audit_client import AuditClient
from src.core.shared.auth import WorkOSWebhookEvent
from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.interfaces import CacheClient
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)

WORKOS_EVENT_REDIS_KEY_PREFIX: Final[str] = "acgs:workos:webhook:event:"
WORKOS_EVENT_REDIS_MAX_CONNECTIONS: Final[int] = 20

_workos_redis_connection_pool = None


class WorkOSEventForwardingError(RuntimeError):
    """Raised when forwarding a webhook event fails in fail-closed mode."""


@dataclass(slots=True)
class WorkOSEventIngestionOutcome:
    """Outcome of ingesting a single WorkOS webhook event."""

    duplicate: bool
    forwarded: bool
    audit_entry_hash: str | None = None


class WorkOSEventIngestionService:
    """Deduplicates WorkOS events and forwards accepted events to audit."""

    def __init__(
        self,
        *,
        dedupe_ttl_seconds: int,
        fail_closed_on_forward_error: bool,
        audit_service_url: str,
    ) -> None:
        self._dedupe_ttl_seconds = dedupe_ttl_seconds
        self._fail_closed_on_forward_error = fail_closed_on_forward_error
        self._audit_client = AuditClient(service_url=audit_service_url)

        self._local_seen_events: dict[str, float] = {}
        self._redis_client: CacheClient | None = None
        self._redis_initialized = False
        self._redis_healthy = False

    async def ingest_event(self, event: WorkOSWebhookEvent) -> WorkOSEventIngestionOutcome:
        """Deduplicate and forward a verified WorkOS event."""
        is_new_event = await self._reserve_event_id(event.id)
        if not is_new_event:
            return WorkOSEventIngestionOutcome(
                duplicate=True, forwarded=False, audit_entry_hash=None
            )

        audit_payload: JSONDict = {
            "event_source": "workos",
            "event_id": event.id,
            "event_type": event.event,
            "created_at": event.created_at,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "data": event.data,
        }

        audit_entry_hash = await self._audit_client.report_validation(audit_payload)
        if audit_entry_hash is None:
            await self._release_event_id(event.id)
            if self._fail_closed_on_forward_error:
                raise WorkOSEventForwardingError("Failed to forward WorkOS event to audit service.")
            return WorkOSEventIngestionOutcome(
                duplicate=False, forwarded=False, audit_entry_hash=None
            )

        return WorkOSEventIngestionOutcome(
            duplicate=False,
            forwarded=True,
            audit_entry_hash=audit_entry_hash,
        )

    async def _reserve_event_id(self, event_id: str) -> bool:
        """Reserve event ID for first processor; returns False for duplicates."""
        self._cleanup_local_cache()
        redis_client = await self._get_redis_client()
        if redis_client is not None:
            try:
                key = f"{WORKOS_EVENT_REDIS_KEY_PREFIX}{event_id}"
                reserved = await redis_client.set(
                    key,
                    "1",
                    ex=self._dedupe_ttl_seconds,
                    nx=True,
                )
                return bool(reserved)
            except Exception as exc:
                self._redis_healthy = False
                logger.warning(f"WorkOS dedupe Redis reservation failed: {exc}")

        now = time.time()
        existing_expiry = self._local_seen_events.get(event_id)
        if existing_expiry and existing_expiry > now:
            return False
        self._local_seen_events[event_id] = now + self._dedupe_ttl_seconds
        return True

    async def _release_event_id(self, event_id: str) -> None:
        """Release reservation when forwarding fails, allowing safe retry."""
        redis_client = await self._get_redis_client()
        if redis_client is not None:
            try:
                key = f"{WORKOS_EVENT_REDIS_KEY_PREFIX}{event_id}"
                await redis_client.delete(key)
            except Exception as exc:
                self._redis_healthy = False
                logger.warning(f"WorkOS dedupe Redis release failed: {exc}")

        self._local_seen_events.pop(event_id, None)

    async def _get_redis_client(self) -> CacheClient | None:
        if self._redis_initialized:
            return self._redis_client if self._redis_healthy else None

        self._redis_initialized = True
        try:
            import redis.asyncio as aioredis

            global _workos_redis_connection_pool
            if _workos_redis_connection_pool is None:
                redis_url = (
                    f"redis://{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"
                )
                _workos_redis_connection_pool = aioredis.ConnectionPool.from_url(
                    redis_url,
                    password=getattr(settings.redis, "password", None),
                    decode_responses=True,
                    max_connections=WORKOS_EVENT_REDIS_MAX_CONNECTIONS,
                    socket_timeout=1.0,
                    socket_connect_timeout=1.0,
                )

            client = aioredis.Redis(connection_pool=_workos_redis_connection_pool)
            await client.ping()
            self._redis_client = client
            self._redis_healthy = True
            return client
        except Exception as exc:
            logger.info(f"WorkOS dedupe using local cache fallback (Redis unavailable): {exc}")
            self._redis_client = None
            self._redis_healthy = False
            return None

    def _cleanup_local_cache(self) -> None:
        now = time.time()
        expired_ids = [
            event_id
            for event_id, expiry_time in self._local_seen_events.items()
            if expiry_time <= now
        ]
        for event_id in expired_ids:
            self._local_seen_events.pop(event_id, None)


_workos_ingestion_service: WorkOSEventIngestionService | None = None


def reset_workos_ingestion_service() -> None:
    """Reset singleton service for tests."""
    global _workos_ingestion_service
    _workos_ingestion_service = None


def get_workos_ingestion_service() -> WorkOSEventIngestionService:
    """Get singleton WorkOS ingestion service."""
    global _workos_ingestion_service
    if _workos_ingestion_service is None:
        _workos_ingestion_service = WorkOSEventIngestionService(
            dedupe_ttl_seconds=settings.sso.workos_webhook_dedupe_ttl_seconds,
            fail_closed_on_forward_error=settings.sso.workos_webhook_fail_closed,
            audit_service_url=settings.services.audit_service_url,
        )
    return _workos_ingestion_service
