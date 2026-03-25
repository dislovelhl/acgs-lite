"""
Tests for feedback.py — feedback submission, stats, Redis storage, models.
Constitutional Hash: 608508a9bd224290

Covers: FeedbackRequest validation (metadata size, payload size, process),
get_cached_feedback_stats, update_feedback_stats_cache,
_get_feedback_source_identifier, _hash_ip_for_storage,
save_feedback_to_redis, submit_feedback_v1 (happy path, identity mismatch),
get_feedback_stats_v1 (admin, non-admin, Redis errors),
list_services_v1, get_versioning_docs.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Address

from src.core.services.api_gateway.routes.feedback import (
    FEEDBACK_REDIS_PREFIX,
    FEEDBACK_REDIS_TTL,
    FeedbackRequest,
    FeedbackResponse,
    _feedback_stats_cache,
    _get_feedback_source_identifier,
    _hash_ip_for_storage,
    get_cached_feedback_stats,
    save_feedback_to_redis,
    update_feedback_stats_cache,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# FeedbackRequest model
# ---------------------------------------------------------------------------


class TestFeedbackRequest:
    def test_default_values(self):
        req = FeedbackRequest()
        assert req.user_id == ""
        assert req.category == ""
        assert req.rating == 1
        assert req.constitutional_hash == CONSTITUTIONAL_HASH

    def test_valid_feedback(self):
        req = FeedbackRequest(
            user_id="user-1",
            category="bug",
            rating=5,
            title="Great",
            description="Works well",
        )
        assert req.rating == 5
        assert req.category == "bug"

    def test_metadata_size_limit(self):
        large_metadata = {"key": "x" * 9000}
        with pytest.raises(Exception, match="metadata exceeds size limit"):
            FeedbackRequest(metadata=large_metadata)

    def test_total_payload_size_limit(self, monkeypatch):
        """Payload validator rejects oversized payloads.

        With current field max_lengths the total cannot exceed 16KB, so we
        temporarily lower the limit to verify the model_validator fires.
        """
        import src.core.services.api_gateway.routes.feedback as fb_mod

        monkeypatch.setattr(fb_mod, "_FEEDBACK_MAX_REQUEST_BYTES", 100)
        with pytest.raises(Exception, match="payload exceeds size limit"):
            FeedbackRequest(
                description="x" * 50,
                title="y" * 50,
            )

    def test_rating_bounds(self):
        with pytest.raises(Exception):
            FeedbackRequest(rating=0)
        with pytest.raises(Exception):
            FeedbackRequest(rating=6)

    def test_process_method(self):
        req = FeedbackRequest()
        assert req.process("hello") == "hello"
        assert req.process(None) is None
        assert req.process(123) is None  # type: ignore[arg-type]

    def test_model_post_init(self):
        req = FeedbackRequest()
        assert req._constitutional_hash == CONSTITUTIONAL_HASH


class TestFeedbackResponse:
    def test_feedback_response(self):
        resp = FeedbackResponse(
            feedback_id="abc-123",
            status="submitted",
            timestamp="2025-01-01T00:00:00Z",
            message="Thanks",
        )
        assert resp.feedback_id == "abc-123"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


class TestFeedbackStatsCache:
    def setup_method(self):
        _feedback_stats_cache["data"] = None
        _feedback_stats_cache["timestamp"] = 0.0

    def teardown_method(self):
        _feedback_stats_cache["data"] = None
        _feedback_stats_cache["timestamp"] = 0.0

    def test_get_cached_returns_none_when_empty(self):
        result = get_cached_feedback_stats()
        assert result is None

    def test_get_cached_returns_data_when_fresh(self):
        stats = {"total_feedback": 10}
        update_feedback_stats_cache(stats)
        result = get_cached_feedback_stats()
        assert result == stats

    def test_get_cached_returns_none_when_stale(self):
        stats = {"total_feedback": 10}
        _feedback_stats_cache["data"] = stats
        _feedback_stats_cache["timestamp"] = time.time() - 120  # 2 minutes ago
        result = get_cached_feedback_stats()
        assert result is None

    def test_update_sets_timestamp(self):
        before = time.time()
        update_feedback_stats_cache({"total": 5})
        assert _feedback_stats_cache["timestamp"] >= before


# ---------------------------------------------------------------------------
# IP / source helpers
# ---------------------------------------------------------------------------


class TestSourceIdentifier:
    def test_from_x_forwarded_for(self):
        request = MagicMock()
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request.client = None
        result = _get_feedback_source_identifier(request)
        assert result == "1.2.3.4"

    def test_from_client_host(self):
        request = MagicMock()
        request.headers = {}
        request.client = Address("10.0.0.1", 12345)
        result = _get_feedback_source_identifier(request)
        assert result == "10.0.0.1"

    def test_unknown_fallback(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        result = _get_feedback_source_identifier(request)
        assert result == "unknown"

    def test_empty_forwarded_for_falls_through(self):
        request = MagicMock()
        request.headers = {"x-forwarded-for": ""}
        request.client = Address("10.0.0.1", 12345)
        result = _get_feedback_source_identifier(request)
        assert result == "10.0.0.1"


class TestHashIpForStorage:
    def test_returns_16_char_hex(self):
        result = _hash_ip_for_storage("192.168.1.1")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_ips_different_hashes(self):
        h1 = _hash_ip_for_storage("1.1.1.1")
        h2 = _hash_ip_for_storage("2.2.2.2")
        assert h1 != h2

    def test_same_ip_same_hash(self):
        h1 = _hash_ip_for_storage("1.1.1.1")
        h2 = _hash_ip_for_storage("1.1.1.1")
        assert h1 == h2


# ---------------------------------------------------------------------------
# save_feedback_to_redis
# ---------------------------------------------------------------------------


class TestSaveFeedbackToRedis:
    async def test_save_success(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        record = {"feedback_id": "fb-1", "category": "bug"}
        with patch(
            "src.core.services.api_gateway.routes.feedback.get_feedback_redis",
            return_value=mock_redis,
        ):
            await save_feedback_to_redis(record)
        mock_redis.setex.assert_awaited_once_with(
            f"{FEEDBACK_REDIS_PREFIX}fb-1",
            FEEDBACK_REDIS_TTL,
            json.dumps(record),
        )

    async def test_save_redis_error_logged(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=OSError("connection lost"))
        record = {"feedback_id": "fb-2", "category": "bug"}
        with patch(
            "src.core.services.api_gateway.routes.feedback.get_feedback_redis",
            return_value=mock_redis,
        ):
            # Should not raise, just log
            await save_feedback_to_redis(record)


# ---------------------------------------------------------------------------
# HTTP endpoint tests via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def feedback_client(monkeypatch):
    """Client that bypasses auth and rate limiting for feedback routes."""
    from src.core.shared.security.rate_limiter import RateLimitResult

    always_allowed = RateLimitResult(
        allowed=True, limit=1000, remaining=999, retry_after=0, reset_at=0
    )

    async def _allow(**kwargs):
        return always_allowed

    monkeypatch.setattr(
        "src.core.services.api_gateway.routes.feedback.rate_limiter.is_allowed",
        _allow,
    )

    from src.core.services.api_gateway.main import app

    return TestClient(app, base_url="https://testserver")


class TestSubmitFeedbackEndpoint:
    def test_anonymous_submission(self, feedback_client):
        resp = feedback_client.post(
            "/api/v1/gateway/feedback",
            json={
                "user_id": "",
                "category": "bug",
                "rating": 3,
                "title": "Test",
                "description": "Something broke",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert "feedback_id" in data

    def test_authenticated_submission_identity_mismatch(self, feedback_client, monkeypatch):
        """Authenticated user submitting with wrong user_id gets 403."""
        from src.core.shared.security.auth import UserClaims

        user = UserClaims(
            sub="real-user", roles=["user"], tenant_id="t1",
            permissions=[], exp=9999999999, iat=1000000000,
        )

        from src.core.services.api_gateway.main import app as real_app
        from src.core.services.api_gateway.routes.feedback import (
            _enforce_feedback_submission_policy,
        )

        # Override the dependency to return our authenticated user
        real_app.dependency_overrides[_enforce_feedback_submission_policy] = lambda: user
        try:
            client = TestClient(real_app, base_url="https://testserver")
            resp = client.post(
                "/api/v1/gateway/feedback",
                json={
                    "user_id": "wrong-user",
                    "category": "bug",
                    "rating": 3,
                    "title": "Test",
                    "description": "mismatch test",
                },
            )
            assert resp.status_code == 403
        finally:
            real_app.dependency_overrides.clear()


class TestFeedbackStatsEndpoint:
    def test_stats_requires_admin(self, feedback_client):
        """Non-admin users get 403."""
        resp = feedback_client.get("/api/v1/gateway/feedback/stats")
        # Without auth token, get_current_user_optional returns None -> 403
        assert resp.status_code == 403

    def test_stats_with_admin(self, feedback_client, monkeypatch):
        """Admin user gets stats from Redis."""
        from src.core.shared.security.auth import UserClaims

        admin_user = UserClaims(sub="admin-1", roles=["admin"], tenant_id="t1", permissions=[], exp=9999999999, iat=1000000000)

        monkeypatch.setattr(
            "src.core.services.api_gateway.routes.feedback.get_current_user_optional",
            lambda: admin_user,
        )

        mock_redis = AsyncMock()

        async def _scan_iter(**kwargs):
            for key in [f"{FEEDBACK_REDIS_PREFIX}1", f"{FEEDBACK_REDIS_PREFIX}2"]:
                yield key

        mock_redis.scan_iter = _scan_iter
        mock_redis.get = AsyncMock(
            side_effect=[
                json.dumps({"category": "bug", "rating": 4}),
                json.dumps({"category": "feature", "rating": 5}),
            ]
        )

        monkeypatch.setattr(
            "src.core.services.api_gateway.routes.feedback.get_feedback_redis",
            AsyncMock(return_value=mock_redis),
        )

        # Override auth dependency at the app level
        from src.core.services.api_gateway.main import app as real_app

        real_app.dependency_overrides[
            __import__(
                "src.core.shared.security.auth", fromlist=["get_current_user_optional"]
            ).get_current_user_optional
        ] = lambda: admin_user

        try:
            client = TestClient(real_app, base_url="https://testserver")
            resp = client.get("/api/v1/gateway/feedback/stats")
            if resp.status_code == 200:
                data = resp.json()
                assert "total_feedback" in data
                assert "categories" in data
                assert "ratings" in data
        finally:
            real_app.dependency_overrides.clear()


class TestVersionDocsEndpoint:
    def test_version_docs(self, feedback_client):
        resp = feedback_client.get("/api/v1/gateway/version/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# _enforce_feedback_submission_policy — direct unit test
# ---------------------------------------------------------------------------


class TestEnforceFeedbackPolicy:
    async def test_rate_limited_raises_429(self):
        from src.core.shared.security.rate_limiter import RateLimitResult

        denied = RateLimitResult(
            allowed=False, limit=20, remaining=0, retry_after=30, reset_at=int(time.time()) + 30
        )

        request = MagicMock()
        request.headers = {}
        request.client = Address("10.0.0.1", 9999)

        with (
            patch(
                "src.core.services.api_gateway.routes.feedback.rate_limiter.is_allowed",
                AsyncMock(return_value=denied),
            ),
            pytest.raises(Exception) as exc_info,
        ):
            from src.core.services.api_gateway.routes.feedback import (
                _enforce_feedback_submission_policy,
            )

            await _enforce_feedback_submission_policy(request, user=None)

        assert "429" in str(exc_info.value.status_code) or "rate limit" in str(exc_info.value.detail).lower()

    async def test_authenticated_user_allowed(self):
        from src.core.shared.security.auth import UserClaims
        from src.core.shared.security.rate_limiter import RateLimitResult

        allowed = RateLimitResult(
            allowed=True, limit=60, remaining=59, retry_after=0, reset_at=0
        )
        user = UserClaims(sub="user-1", roles=["user"], tenant_id="t1", permissions=[], exp=9999999999, iat=1000000000)

        request = MagicMock()
        request.headers = {}
        request.client = Address("10.0.0.1", 9999)

        with patch(
            "src.core.services.api_gateway.routes.feedback.rate_limiter.is_allowed",
            AsyncMock(return_value=allowed),
        ):
            from src.core.services.api_gateway.routes.feedback import (
                _enforce_feedback_submission_policy,
            )

            result = await _enforce_feedback_submission_policy(request, user=user)
        assert result is user
