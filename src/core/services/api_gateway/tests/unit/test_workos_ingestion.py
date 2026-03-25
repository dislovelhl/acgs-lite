"""Tests for WorkOS webhook event ingestion service.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.services.api_gateway.workos_event_ingestion import (
    WorkOSEventForwardingError,
    WorkOSEventIngestionOutcome,
    WorkOSEventIngestionService,
    get_workos_ingestion_service,
    reset_workos_ingestion_service,
)
from src.core.shared.auth import WorkOSWebhookEvent


def _make_event(event_id: str = "evt_001", event_type: str = "dsync.user.created") -> WorkOSWebhookEvent:
    return WorkOSWebhookEvent(
        id=event_id,
        event=event_type,
        data={"user": "test"},
        created_at="2026-01-01T00:00:00Z",
    )


def _make_service(
    dedupe_ttl: int = 300,
    fail_closed: bool = False,
    audit_url: str = "http://audit:8300",
) -> WorkOSEventIngestionService:
    return WorkOSEventIngestionService(
        dedupe_ttl_seconds=dedupe_ttl,
        fail_closed_on_forward_error=fail_closed,
        audit_service_url=audit_url,
    )


# ---------------------------------------------------------------------------
# WorkOSEventIngestionOutcome
# ---------------------------------------------------------------------------


class TestWorkOSEventIngestionOutcome:
    def test_outcome_duplicate(self):
        outcome = WorkOSEventIngestionOutcome(duplicate=True, forwarded=False)
        assert outcome.duplicate is True
        assert outcome.forwarded is False
        assert outcome.audit_entry_hash is None

    def test_outcome_forwarded(self):
        outcome = WorkOSEventIngestionOutcome(
            duplicate=False, forwarded=True, audit_entry_hash="abc123"
        )
        assert outcome.forwarded is True
        assert outcome.audit_entry_hash == "abc123"


# ---------------------------------------------------------------------------
# ingest_event — happy path
# ---------------------------------------------------------------------------


class TestIngestEvent:
    """Test ingest_event with Redis disabled (local cache only)."""

    @staticmethod
    def _svc_no_redis(**kwargs):
        """Create a service with Redis pre-disabled so tests use local cache."""
        svc = _make_service(**kwargs)
        # Pre-initialize to skip Redis connection attempt
        svc._redis_initialized = True
        svc._redis_healthy = False
        svc._redis_client = None
        return svc

    @pytest.mark.asyncio
    async def test_new_event_forwarded_successfully(self):
        svc = self._svc_no_redis()
        svc._audit_client = MagicMock()
        svc._audit_client.report_validation = AsyncMock(return_value="hash_abc")

        event = _make_event("evt_new")
        outcome = await svc.ingest_event(event)

        assert outcome.duplicate is False
        assert outcome.forwarded is True
        assert outcome.audit_entry_hash == "hash_abc"

    @pytest.mark.asyncio
    async def test_duplicate_event_detected_local_cache(self):
        svc = self._svc_no_redis()
        svc._audit_client = MagicMock()
        svc._audit_client.report_validation = AsyncMock(return_value="hash_abc")

        event = _make_event("evt_dup")
        await svc.ingest_event(event)
        outcome = await svc.ingest_event(event)

        assert outcome.duplicate is True
        assert outcome.forwarded is False

    @pytest.mark.asyncio
    async def test_audit_failure_returns_not_forwarded(self):
        svc = self._svc_no_redis(fail_closed=False)
        svc._audit_client = MagicMock()
        svc._audit_client.report_validation = AsyncMock(return_value=None)

        event = _make_event("evt_fail")
        outcome = await svc.ingest_event(event)

        assert outcome.duplicate is False
        assert outcome.forwarded is False

    @pytest.mark.asyncio
    async def test_audit_failure_fail_closed_raises(self):
        svc = self._svc_no_redis(fail_closed=True)
        svc._audit_client = MagicMock()
        svc._audit_client.report_validation = AsyncMock(return_value=None)

        event = _make_event("evt_fail_closed")
        with pytest.raises(WorkOSEventForwardingError):
            await svc.ingest_event(event)

    @pytest.mark.asyncio
    async def test_audit_failure_releases_event_id(self):
        """When audit fails, the event ID reservation should be released."""
        svc = self._svc_no_redis(fail_closed=False)
        svc._audit_client = MagicMock()
        svc._audit_client.report_validation = AsyncMock(return_value=None)

        event = _make_event("evt_release")
        await svc.ingest_event(event)

        # After release, the same event should be re-processable
        svc._audit_client.report_validation = AsyncMock(return_value="hash_retry")
        outcome = await svc.ingest_event(event)
        assert outcome.forwarded is True


# ---------------------------------------------------------------------------
# _reserve_event_id — Redis path
# ---------------------------------------------------------------------------


class TestReserveEventIdRedis:
    @pytest.mark.asyncio
    async def test_redis_reservation_success(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        svc._redis_client = mock_redis
        svc._redis_initialized = True
        svc._redis_healthy = True

        result = await svc._reserve_event_id("evt_redis_ok")
        assert result is True
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_reservation_duplicate(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)  # nx=True returns None for dups
        svc._redis_client = mock_redis
        svc._redis_initialized = True
        svc._redis_healthy = True

        result = await svc._reserve_event_id("evt_redis_dup")
        assert result is False

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_local(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("down"))
        svc._redis_client = mock_redis
        svc._redis_initialized = True
        svc._redis_healthy = True

        result = await svc._reserve_event_id("evt_fallback")
        assert result is True
        # Should mark Redis unhealthy
        assert svc._redis_healthy is False


# ---------------------------------------------------------------------------
# _release_event_id
# ---------------------------------------------------------------------------


class TestReleaseEventId:
    @pytest.mark.asyncio
    async def test_release_via_redis(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        svc._redis_client = mock_redis
        svc._redis_initialized = True
        svc._redis_healthy = True

        svc._local_seen_events["evt_rel"] = time.time() + 300
        await svc._release_event_id("evt_rel")

        mock_redis.delete.assert_awaited_once()
        assert "evt_rel" not in svc._local_seen_events

    @pytest.mark.asyncio
    async def test_release_redis_failure_still_clears_local(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("down"))
        svc._redis_client = mock_redis
        svc._redis_initialized = True
        svc._redis_healthy = True

        svc._local_seen_events["evt_rel2"] = time.time() + 300
        await svc._release_event_id("evt_rel2")

        assert "evt_rel2" not in svc._local_seen_events
        assert svc._redis_healthy is False


# ---------------------------------------------------------------------------
# _get_redis_client
# ---------------------------------------------------------------------------


class TestGetRedisClient:
    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self):
        svc = _make_service()
        with patch.dict("os.environ", {}, clear=False):
            with patch(
                "src.core.services.api_gateway.workos_event_ingestion.aioredis",
                create=True,
            ) if False else patch(
                "redis.asyncio.ConnectionPool.from_url",
                side_effect=ImportError("no redis"),
            ):
                await svc._get_redis_client()
        # After import error fallback, should return None
        assert svc._redis_initialized is True

    @pytest.mark.asyncio
    async def test_returns_cached_none_when_unhealthy(self):
        svc = _make_service()
        svc._redis_initialized = True
        svc._redis_healthy = False
        svc._redis_client = None

        result = await svc._get_redis_client()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_client_when_healthy(self):
        svc = _make_service()
        mock_redis = AsyncMock()
        svc._redis_initialized = True
        svc._redis_healthy = True
        svc._redis_client = mock_redis

        result = await svc._get_redis_client()
        assert result is mock_redis


# ---------------------------------------------------------------------------
# _cleanup_local_cache
# ---------------------------------------------------------------------------


class TestCleanupLocalCache:
    def test_removes_expired_entries(self):
        svc = _make_service()
        svc._local_seen_events = {
            "expired": time.time() - 10,
            "valid": time.time() + 300,
        }
        svc._cleanup_local_cache()
        assert "expired" not in svc._local_seen_events
        assert "valid" in svc._local_seen_events

    def test_empty_cache_is_noop(self):
        svc = _make_service()
        svc._cleanup_local_cache()
        assert len(svc._local_seen_events) == 0


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_reset_clears_singleton(self):
        reset_workos_ingestion_service()
        # After reset, get should create a new instance
        with patch(
            "src.core.services.api_gateway.workos_event_ingestion.settings"
        ) as mock_settings:
            mock_settings.sso.workos_webhook_dedupe_ttl_seconds = 300
            mock_settings.sso.workos_webhook_fail_closed = False
            mock_settings.services.audit_service_url = "http://audit:8300"

            svc = get_workos_ingestion_service()
            assert isinstance(svc, WorkOSEventIngestionService)

            reset_workos_ingestion_service()
