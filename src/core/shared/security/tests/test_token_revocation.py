"""Tests for src.core.shared.security.token_revocation — TokenRevocationService.

Covers: revoke_token, is_token_revoked, revoke_all_user_tokens, is_user_revoked,
get_revocation_stats, close, _calculate_ttl, _parse_bool_env, graceful degradation,
fail-open/fail-closed modes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis_mock = AsyncMock()
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.ping = AsyncMock(return_value=True)

    async def _scan_iter(pattern, count=100):
        return
        yield  # make it an async generator that yields nothing

    redis_mock.scan_iter = _scan_iter
    return redis_mock


@pytest.fixture
def valid_jti() -> str:
    return str(uuid4())


@pytest.fixture
def user_id() -> str:
    return f"user_{uuid4().hex[:8]}"


@pytest.fixture
def expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


def _make_service(redis_client=None):
    from src.core.shared.security.token_revocation import TokenRevocationService

    return TokenRevocationService(redis_client=redis_client)


# ---------------------------------------------------------------------------
# _parse_bool_env
# ---------------------------------------------------------------------------
class TestParseBoolEnv:
    def test_true_values(self):
        from src.core.shared.security.token_revocation import _parse_bool_env

        for val in ("true", "1", "yes", "on", "TRUE", " True "):
            assert _parse_bool_env(val) is True

    def test_false_values(self):
        from src.core.shared.security.token_revocation import _parse_bool_env

        for val in ("false", "0", "no", "off", "FALSE"):
            assert _parse_bool_env(val) is False

    def test_none(self):
        from src.core.shared.security.token_revocation import _parse_bool_env

        assert _parse_bool_env(None) is None

    def test_unrecognized(self):
        from src.core.shared.security.token_revocation import _parse_bool_env

        assert _parse_bool_env("maybe") is None


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
class TestInit:
    def test_init_with_redis(self, mock_redis):
        svc = _make_service(mock_redis)
        assert svc._use_redis is True

    def test_init_without_redis(self):
        svc = _make_service(None)
        assert svc._use_redis is False

    def test_runtime_environment_prefers_environment_over_defaulted_settings_env(self, monkeypatch):
        from src.core.shared.security import token_revocation

        monkeypatch.setattr(token_revocation.settings, "env", "development")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert token_revocation._runtime_environment() == "production"


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------
class TestClose:
    async def test_close_with_aclose(self, mock_redis):
        mock_redis.aclose = AsyncMock()
        svc = _make_service(mock_redis)
        await svc.close()
        mock_redis.aclose.assert_awaited_once()
        assert svc._redis_client is None
        assert svc._use_redis is False

    async def test_close_with_sync_close(self):
        redis_mock = MagicMock()
        redis_mock.close = MagicMock(return_value=None)
        del redis_mock.aclose  # no aclose method
        svc = _make_service(redis_mock)
        await svc.close()
        redis_mock.close.assert_called_once()

    async def test_close_with_async_close_fallback(self):
        redis_mock = MagicMock()
        del redis_mock.aclose

        async def _async_close():
            pass

        redis_mock.close = MagicMock(return_value=_async_close())
        svc = _make_service(redis_mock)
        await svc.close()

    async def test_close_no_redis(self):
        svc = _make_service(None)
        await svc.close()  # should not raise

    async def test_close_error_handled(self, mock_redis):
        mock_redis.aclose = AsyncMock(side_effect=RuntimeError("close failed"))
        svc = _make_service(mock_redis)
        await svc.close()
        assert svc._redis_client is None


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------
class TestRevokeToken:
    async def test_success(self, mock_redis, valid_jti, expires_at):
        svc = _make_service(mock_redis)
        result = await svc.revoke_token(valid_jti, expires_at)
        assert result is True
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == f"token_blacklist:{valid_jti}"
        assert call_args[1] > 0
        assert call_args[2] == "revoked"

    async def test_empty_jti_raises(self, mock_redis, expires_at):
        svc = _make_service(mock_redis)
        with pytest.raises(ACGSValidationError):
            await svc.revoke_token("", expires_at)
        with pytest.raises(ACGSValidationError):
            await svc.revoke_token("   ", expires_at)

    async def test_no_redis_returns_false(self, valid_jti, expires_at):
        svc = _make_service(None)
        result = await svc.revoke_token(valid_jti, expires_at)
        assert result is False

    async def test_connection_error_returns_false(self, mock_redis, valid_jti, expires_at):
        mock_redis.setex.side_effect = ConnectionError("down")
        svc = _make_service(mock_redis)
        result = await svc.revoke_token(valid_jti, expires_at)
        assert result is False

    async def test_unexpected_error_returns_false(self, mock_redis, valid_jti, expires_at):
        mock_redis.setex.side_effect = RuntimeError("unexpected")
        svc = _make_service(mock_redis)
        result = await svc.revoke_token(valid_jti, expires_at)
        assert result is False


# ---------------------------------------------------------------------------
# is_token_revoked
# ---------------------------------------------------------------------------
class TestIsTokenRevoked:
    async def test_revoked_token(self, mock_redis, valid_jti):
        mock_redis.exists.return_value = 1
        svc = _make_service(mock_redis)
        assert await svc.is_token_revoked(valid_jti) is True

    async def test_valid_token(self, mock_redis, valid_jti):
        mock_redis.exists.return_value = 0
        svc = _make_service(mock_redis)
        assert await svc.is_token_revoked(valid_jti) is False

    async def test_empty_jti_raises(self, mock_redis):
        svc = _make_service(mock_redis)
        with pytest.raises(ACGSValidationError):
            await svc.is_token_revoked("")

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_no_redis_fail_open(self, valid_jti):
        svc = _make_service(None)
        assert await svc.is_token_revoked(valid_jti) is False

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "false"})
    @patch("src.core.shared.security.token_revocation._runtime_environment", return_value="production")
    async def test_no_redis_strict_mode(self, _mock_env, valid_jti):
        svc = _make_service(None)
        assert await svc.is_token_revoked(valid_jti) is True

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_connection_error_fail_open(self, mock_redis, valid_jti):
        mock_redis.exists.side_effect = ConnectionError("down")
        svc = _make_service(mock_redis)
        assert await svc.is_token_revoked(valid_jti) is False

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "false"})
    @patch("src.core.shared.security.token_revocation._runtime_environment", return_value="production")
    async def test_connection_error_strict_mode(self, _mock_env, mock_redis, valid_jti):
        mock_redis.exists.side_effect = ConnectionError("down")
        svc = _make_service(mock_redis)
        assert await svc.is_token_revoked(valid_jti) is True

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_unexpected_error_fail_open(self, mock_redis, valid_jti):
        mock_redis.exists.side_effect = RuntimeError("unexpected")
        svc = _make_service(mock_redis)
        assert await svc.is_token_revoked(valid_jti) is False


# ---------------------------------------------------------------------------
# revoke_all_user_tokens
# ---------------------------------------------------------------------------
class TestRevokeAllUserTokens:
    async def test_success(self, mock_redis, user_id, expires_at):
        svc = _make_service(mock_redis)
        result = await svc.revoke_all_user_tokens(user_id, expires_at)
        assert result == 1
        mock_redis.setex.assert_called_once()
        call_key = mock_redis.setex.call_args[0][0]
        assert call_key == f"user_revoked:{user_id}"

    async def test_empty_user_id_raises(self, mock_redis, expires_at):
        svc = _make_service(mock_redis)
        with pytest.raises(ACGSValidationError):
            await svc.revoke_all_user_tokens("", expires_at)

    async def test_no_redis_returns_zero(self, user_id, expires_at):
        svc = _make_service(None)
        assert await svc.revoke_all_user_tokens(user_id, expires_at) == 0

    async def test_connection_error_returns_zero(self, mock_redis, user_id, expires_at):
        mock_redis.setex.side_effect = ConnectionError("down")
        svc = _make_service(mock_redis)
        assert await svc.revoke_all_user_tokens(user_id, expires_at) == 0

    async def test_unexpected_error_returns_zero(self, mock_redis, user_id, expires_at):
        mock_redis.setex.side_effect = RuntimeError("unexpected")
        svc = _make_service(mock_redis)
        assert await svc.revoke_all_user_tokens(user_id, expires_at) == 0


# ---------------------------------------------------------------------------
# is_user_revoked
# ---------------------------------------------------------------------------
class TestIsUserRevoked:
    async def test_not_revoked(self, mock_redis, user_id):
        mock_redis.get.return_value = None
        svc = _make_service(mock_redis)
        token_iat = datetime.now(UTC) - timedelta(minutes=5)
        assert await svc.is_user_revoked(user_id, token_iat) is False

    async def test_revoked_after_token_issued(self, mock_redis, user_id):
        revocation_time = datetime.now(UTC).isoformat()
        mock_redis.get.return_value = revocation_time
        svc = _make_service(mock_redis)
        token_iat = datetime.now(UTC) - timedelta(hours=1)
        assert await svc.is_user_revoked(user_id, token_iat) is True

    async def test_revoked_before_token_issued(self, mock_redis, user_id):
        revocation_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        mock_redis.get.return_value = revocation_time
        svc = _make_service(mock_redis)
        token_iat = datetime.now(UTC) - timedelta(minutes=5)
        assert await svc.is_user_revoked(user_id, token_iat) is False

    async def test_bytes_timestamp(self, mock_redis, user_id):
        revocation_time = datetime.now(UTC).isoformat().encode("utf-8")
        mock_redis.get.return_value = revocation_time
        svc = _make_service(mock_redis)
        token_iat = datetime.now(UTC) - timedelta(hours=1)
        assert await svc.is_user_revoked(user_id, token_iat) is True

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_no_redis_fail_open(self, user_id):
        svc = _make_service(None)
        assert await svc.is_user_revoked(user_id, datetime.now(UTC)) is False

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "false"})
    @patch("src.core.shared.security.token_revocation._runtime_environment", return_value="production")
    async def test_no_redis_strict_mode(self, _mock_env, user_id):
        svc = _make_service(None)
        assert await svc.is_user_revoked(user_id, datetime.now(UTC)) is True

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_connection_error_fail_open(self, mock_redis, user_id):
        mock_redis.get.side_effect = ConnectionError("down")
        svc = _make_service(mock_redis)
        assert await svc.is_user_revoked(user_id, datetime.now(UTC)) is False

    async def test_invalid_timestamp_returns_false(self, mock_redis, user_id):
        mock_redis.get.return_value = "not-a-date"
        svc = _make_service(mock_redis)
        assert await svc.is_user_revoked(user_id, datetime.now(UTC)) is False

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"})
    async def test_unexpected_error_fail_open(self, mock_redis, user_id):
        mock_redis.get.side_effect = RuntimeError("unexpected")
        svc = _make_service(mock_redis)
        assert await svc.is_user_revoked(user_id, datetime.now(UTC)) is False

    async def test_naive_datetime_handled(self, mock_redis, user_id):
        """Naive datetimes should be treated as UTC."""
        revocation_time = datetime.now(UTC).isoformat()
        mock_redis.get.return_value = revocation_time
        svc = _make_service(mock_redis)
        # Naive datetime (no tzinfo)
        token_iat = datetime(2020, 1, 1, 0, 0, 0)
        assert await svc.is_user_revoked(user_id, token_iat) is True


# ---------------------------------------------------------------------------
# _calculate_ttl
# ---------------------------------------------------------------------------
class TestCalculateTTL:
    def test_future_expiry(self):
        svc = _make_service(None)
        future = datetime.now(UTC) + timedelta(hours=1)
        ttl = svc._calculate_ttl(future)
        assert 3500 <= ttl <= 3700

    def test_past_expiry_minimum_1(self):
        svc = _make_service(None)
        past = datetime.now(UTC) - timedelta(hours=1)
        ttl = svc._calculate_ttl(past)
        assert ttl == 1

    def test_naive_datetime_assumed_utc(self):
        svc = _make_service(None)
        future = datetime(2099, 1, 1, 0, 0, 0)
        ttl = svc._calculate_ttl(future)
        assert ttl > 0


# ---------------------------------------------------------------------------
# get_revocation_stats
# ---------------------------------------------------------------------------
class TestGetRevocationStats:
    async def test_no_redis(self):
        svc = _make_service(None)
        stats = await svc.get_revocation_stats()
        assert stats["redis_available"] is False
        assert stats["blacklist_count"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_with_redis(self, mock_redis):
        svc = _make_service(mock_redis)
        stats = await svc.get_revocation_stats()
        assert stats["redis_available"] is True

    async def test_redis_error(self, mock_redis):
        async def _bad_scan(pattern, count=100):
            raise ConnectionError("down")
            yield  # noqa: unreachable — make it async gen

        mock_redis.scan_iter = _bad_scan
        svc = _make_service(mock_redis)
        stats = await svc.get_revocation_stats()
        assert stats["redis_available"] is False
        assert "error" in stats


# ---------------------------------------------------------------------------
# create_token_revocation_service
# ---------------------------------------------------------------------------
class TestCreateService:
    async def test_connection_failure_returns_degraded(self):
        from src.core.shared.security.token_revocation import (
            create_token_revocation_service,
        )

        # Use a URL that will fail to connect
        svc = await create_token_revocation_service("redis://invalid-host:9999")
        assert svc._use_redis is False

    async def test_uses_env_var_when_no_url(self):
        from src.core.shared.security.token_revocation import (
            create_token_revocation_service,
        )

        with patch.dict("os.environ", {"REDIS_URL": "redis://also-invalid:1234"}):
            svc = await create_token_revocation_service()
            # Should fail and degrade gracefully
            assert svc._use_redis is False
