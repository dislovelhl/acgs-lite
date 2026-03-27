"""
Test Token Revocation Service - TDD Implementation
Constitutional Hash: cdd01ef066bc6cf2

Tests for JWT token revocation system with Redis blacklist and graceful degradation.
Following session_manager.py pattern for blacklist implementation.

Coverage target: 95%+ (critical security path)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis_mock = AsyncMock()
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.ping = AsyncMock(return_value=True)
    return redis_mock


@pytest.fixture
def valid_jti() -> str:
    """Generate a valid JWT ID."""
    return str(uuid4())


@pytest.fixture
def user_id() -> str:
    """Generate a valid user ID."""
    return f"user_{uuid4().hex[:8]}"


@pytest.fixture
def expires_at() -> datetime:
    """Generate expiry timestamp 1 hour from now."""
    return datetime.now(UTC) + timedelta(hours=1)


class TestTokenRevocationService:
    """Test suite for TokenRevocationService."""

    @pytest.mark.asyncio
    async def test_revoke_token_adds_to_blacklist(self, mock_redis, valid_jti, expires_at):
        """
        Test that revoking a token adds it to Redis blacklist with correct TTL.

        CRITICAL: Tokens must be blacklisted immediately to prevent reuse.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        result = await service.revoke_token(valid_jti, expires_at)

        # Assert
        assert result is True, "Token revocation should succeed"

        # Verify Redis setex was called with correct key pattern
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        # Check key pattern: token_blacklist:{jti}
        assert call_args[0][0] == f"token_blacklist:{valid_jti}"

        # Check TTL is calculated from expires_at
        ttl = call_args[0][1]
        assert ttl > 0, "TTL must be positive"
        assert ttl <= 3600 + 60, "TTL should be ~1 hour + buffer"

        # Check value indicates revocation
        assert call_args[0][2] == "revoked"

    @pytest.mark.asyncio
    async def test_is_token_revoked_returns_true_for_blacklisted(self, mock_redis, valid_jti):
        """
        Test that blacklisted tokens are correctly identified.

        CRITICAL: Must detect revoked tokens to prevent unauthorized access.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - token exists in blacklist
        mock_redis.exists.return_value = 1

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        result = await service.is_token_revoked(valid_jti)

        # Assert
        assert result is True, "Blacklisted token should return True"
        mock_redis.exists.assert_called_once_with(f"token_blacklist:{valid_jti}")

    @pytest.mark.asyncio
    async def test_is_token_revoked_returns_false_for_valid(self, mock_redis, valid_jti):
        """
        Test that non-blacklisted tokens return False.

        Valid tokens must not be blocked.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - token not in blacklist
        mock_redis.exists.return_value = 0

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        result = await service.is_token_revoked(valid_jti)

        # Assert
        assert result is False, "Valid token should return False"
        mock_redis.exists.assert_called_once_with(f"token_blacklist:{valid_jti}")

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens_invalidates_all(self, mock_redis, user_id, expires_at):
        """
        Test that revoking all user tokens sets user revocation timestamp.

        CRITICAL: On logout/compromise, all user tokens must be invalidated.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - simulate 3 active tokens
        mock_redis.keys.return_value = [
            b"token_blacklist:token1",
            b"token_blacklist:token2",
            b"token_blacklist:token3",
        ]

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert
        assert count >= 1, "Should revoke at least the user revocation record"

        # Verify user revocation timestamp was set
        mock_redis.setex.assert_called()

        # Check that user_revoked key was set
        calls = [str(call) for call in mock_redis.setex.call_args_list]
        user_key_set = any(f"user_revoked:{user_id}" in call for call in calls)
        assert user_key_set, "User revocation timestamp must be set"

    @pytest.mark.asyncio
    async def test_token_revocation_ttl_expires(self, mock_redis, valid_jti):
        """
        Test that revoked tokens naturally expire via TTL.

        Ensures blacklist doesn't grow unbounded - Redis TTL handles cleanup.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - short TTL (1 second in past)
        expires_at = datetime.now(UTC) - timedelta(seconds=1)

        # Act
        result = await service.revoke_token(valid_jti, expires_at)

        # Assert - should still succeed (Redis will expire immediately)
        assert result is True

        # Verify TTL was set (even if 0 or negative, Redis will handle)
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_graceful_degradation_when_redis_unavailable(self, valid_jti, expires_at):
        """
        Test graceful degradation when Redis is unavailable.

        CRITICAL: Must not crash when Redis is down - fail open with logging.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - Redis client that raises ConnectionError
        failing_redis = AsyncMock()
        failing_redis.setex.side_effect = ConnectionError("Redis unavailable")
        failing_redis.exists.side_effect = ConnectionError("Redis unavailable")

        service = TokenRevocationService(redis_client=failing_redis)

        # Act - revoke_token should not raise, but return False
        result = await service.revoke_token(valid_jti, expires_at)
        assert result is False, "Should return False when Redis unavailable"

        # Act - is_token_revoked should not raise, but return False (fail open)
        revoked = await service.is_token_revoked(valid_jti)
        assert revoked is False, "Should fail open when Redis unavailable"

    @pytest.mark.asyncio
    async def test_revoke_token_without_redis_client(self, valid_jti, expires_at):
        """
        Test behavior when TokenRevocationService initialized without Redis.

        Must handle None redis_client gracefully.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - no Redis client
        service = TokenRevocationService(redis_client=None)

        # Act
        result = await service.revoke_token(valid_jti, expires_at)

        # Assert - should fail gracefully
        assert result is False, "Should return False when no Redis client"

    @pytest.mark.asyncio
    async def test_is_token_revoked_without_redis_client(self, valid_jti):
        """
        Test checking revocation without Redis client.

        Must fail open (return False) when Redis unavailable.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange
        service = TokenRevocationService(redis_client=None)

        # Act
        result = await service.is_token_revoked(valid_jti)

        # Assert - fail open
        assert result is False, "Should fail open when no Redis client"

    @pytest.mark.asyncio
    async def test_is_token_revoked_without_redis_client_fails_closed_in_production(
        self, valid_jti, monkeypatch
    ):
        from src.core.shared.config import settings
        from src.core.shared.security.token_revocation import TokenRevocationService

        # _runtime_environment() reads settings.env, not AGENT_RUNTIME_ENVIRONMENT.
        monkeypatch.setattr(settings, "env", "production")
        monkeypatch.delenv("TOKEN_REVOCATION_FAIL_OPEN", raising=False)

        service = TokenRevocationService(redis_client=None)

        result = await service.is_token_revoked(valid_jti)

        assert result is True, "Should fail closed in production-like environments"

    @pytest.mark.asyncio
    async def test_is_token_revoked_honors_explicit_fail_open_override(
        self, valid_jti, monkeypatch
    ):
        from src.core.shared.config import settings
        from src.core.shared.security.token_revocation import TokenRevocationService

        monkeypatch.setattr(settings, "env", "production")
        monkeypatch.setenv("TOKEN_REVOCATION_FAIL_OPEN", "true")

        service = TokenRevocationService(redis_client=None)

        result = await service.is_token_revoked(valid_jti)

        assert result is False, "Explicit fail-open override should take precedence"

    @pytest.mark.asyncio
    async def test_constitutional_hash_in_audit_logs(
        self, mock_redis, valid_jti, expires_at, caplog
    ):
        """
        Test that constitutional hash appears in audit logs.

        GOVERNANCE: All security operations must include constitutional hash.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        with caplog.at_level("INFO"):
            await service.revoke_token(valid_jti, expires_at)

        # Assert - constitutional hash in logs
        log_messages = [record.message for record in caplog.records]
        hash_in_logs = any(CONSTITUTIONAL_HASH in msg for msg in log_messages)

        assert hash_in_logs, f"Constitutional hash {CONSTITUTIONAL_HASH} must appear in audit logs"

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens_with_existing_tokens(
        self, mock_redis, user_id, valid_jti, expires_at
    ):
        """
        Test bulk revocation when user has multiple active tokens.

        Edge case: Ensure all tokens are invalidated, not just new ones.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Arrange - multiple existing tokens
        existing_tokens = [
            f"token_blacklist:{uuid4()}".encode(),
        ]
        mock_redis.keys.return_value = existing_tokens

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert - should set user revocation timestamp
        assert count >= 1

        # Verify user_revoked key exists
        calls = mock_redis.setex.call_args_list
        user_keys = [call[0][0] for call in calls if "user_revoked" in call[0][0]]
        assert len(user_keys) > 0, "User revocation timestamp must be set"

    @pytest.mark.asyncio
    async def test_ttl_calculation_accuracy(self, mock_redis, valid_jti):
        """
        Test that TTL is calculated accurately from expires_at.

        Edge case: Verify TTL math is correct for various expiry times.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Test cases: various expiry times
        test_cases = [
            (datetime.now(UTC) + timedelta(hours=1), 3600),  # 1 hour
            (datetime.now(UTC) + timedelta(minutes=30), 1800),  # 30 min
            (datetime.now(UTC) + timedelta(days=1), 86400),  # 1 day
        ]

        for expires_at, expected_ttl in test_cases:
            mock_redis.setex.reset_mock()

            await service.revoke_token(valid_jti, expires_at)

            call_args = mock_redis.setex.call_args
            actual_ttl = call_args[0][1]

            # Allow 60 second buffer for test execution time
            assert abs(actual_ttl - expected_ttl) <= 60, (
                f"TTL {actual_ttl} should be close to {expected_ttl}"
            )

    @pytest.mark.asyncio
    async def test_maci_separation_of_powers(self, mock_redis, valid_jti, expires_at):
        """
        Test MACI compliance - no self-validation.

        GOVERNANCE: TokenRevocationService should not validate its own operations.
        This is a design test - ensure no self-validation logic exists.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Revoke a token
        await service.revoke_token(valid_jti, expires_at)

        # The service should NOT automatically validate its own revocation
        # This is validated by code inspection and architecture review
        # No self-validation methods should exist
        assert not hasattr(service, "validate_revocation"), (
            "Service must not self-validate (MACI separation of powers)"
        )
        assert not hasattr(service, "_validate_own_operation"), (
            "Service must not self-validate (MACI separation of powers)"
        )

    @pytest.mark.asyncio
    async def test_concurrent_revocation_safety(self, mock_redis, user_id, expires_at):
        """
        Test thread/async safety of concurrent revocations.

        Edge case: Multiple simultaneous revoke_all_user_tokens calls.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Simulate concurrent revocations
        tasks = [service.revoke_all_user_tokens(user_id, expires_at) for _ in range(5)]

        # Act - run concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - all should succeed or handle gracefully
        for result in results:
            assert not isinstance(result, Exception), (
                f"Concurrent revocations should not raise: {result}"
            )
            assert isinstance(result, int), "Should return count"

    @pytest.mark.asyncio
    async def test_null_jti_handling(self, mock_redis, expires_at):
        """
        Test handling of null/empty JTI.

        Edge case: Invalid input should be rejected gracefully.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Act & Assert - should handle gracefully
        with pytest.raises((ValueError, ACGSValidationError), match="JTI cannot be empty"):
            await service.revoke_token("", expires_at)

        with pytest.raises((ValueError, ACGSValidationError), match="JTI cannot be empty"):
            await service.is_token_revoked("")

    @pytest.mark.asyncio
    async def test_null_user_id_handling(self, mock_redis, expires_at):
        """
        Test handling of null/empty user_id.

        Edge case: Invalid input should be rejected.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Act & Assert
        with pytest.raises((ValueError, ACGSValidationError), match="User ID cannot be empty"):
            await service.revoke_all_user_tokens("", expires_at)

    @pytest.mark.asyncio
    async def test_expired_token_ttl_handling(self, mock_redis, valid_jti):
        """
        Test handling when expires_at is in the past.

        Edge case: Already-expired tokens should still be blacklisted briefly.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - token already expired
        expires_at = datetime.now(UTC) - timedelta(hours=1)

        # Act - should still revoke (with minimal TTL)
        result = await service.revoke_token(valid_jti, expires_at)

        # Assert
        assert result is True, "Should still revoke expired tokens"

        # Verify it was added with TTL (even if minimal)
        mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
class TestTokenRevocationIntegration:
    """Integration tests with real Redis patterns."""

    async def test_revocation_workflow_end_to_end(self, mock_redis):
        """
        Integration test: Full revocation workflow.

        1. Token is valid
        2. Token is revoked
        3. Token is detected as revoked
        4. Token expires naturally
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)
        jti = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        # Step 1: Token is valid initially
        mock_redis.exists.return_value = 0
        assert await service.is_token_revoked(jti) is False

        # Step 2: Revoke token
        result = await service.revoke_token(jti, expires_at)
        assert result is True

        # Step 3: Token is now revoked
        mock_redis.exists.return_value = 1
        assert await service.is_token_revoked(jti) is True

    async def test_user_logout_scenario(self, mock_redis):
        """
        Integration test: User logout revokes all tokens.

        Simulates user clicking "logout" which should invalidate all sessions.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)
        user_id = f"user_{uuid4().hex[:8]}"
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        # Simulate multiple active sessions
        mock_redis.keys.return_value = [
            b"token_blacklist:session1",
            b"token_blacklist:session2",
        ]

        # Act - logout (revoke all)
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert - all sessions invalidated
        assert count >= 1
        mock_redis.setex.assert_called()

    async def test_redis_failure_recovery(self, mock_redis):
        """
        Integration test: Redis fails then recovers.

        Ensures service handles transient Redis failures gracefully.
        """
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)
        jti = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        # Step 1: Redis fails
        mock_redis.setex.side_effect = ConnectionError("Connection lost")
        result = await service.revoke_token(jti, expires_at)
        assert result is False, "Should handle Redis failure"

        # Step 2: Redis recovers
        mock_redis.setex.side_effect = None
        mock_redis.setex.return_value = True
        result = await service.revoke_token(jti, expires_at)
        assert result is True, "Should succeed after recovery"


# Edge case tests
@pytest.mark.asyncio
class TestTokenRevocationEdgeCases:
    """Edge case and error handling tests."""

    async def test_redis_timeout_handling(self, valid_jti, expires_at):
        """Test handling of Redis timeouts."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        timeout_redis = AsyncMock()
        timeout_redis.setex.side_effect = TimeoutError("Operation timed out")

        service = TokenRevocationService(redis_client=timeout_redis)

        result = await service.revoke_token(valid_jti, expires_at)
        assert result is False, "Should handle timeouts gracefully"

    async def test_redis_memory_error_handling(self, valid_jti, expires_at):
        """Test handling when Redis is out of memory."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        oom_redis = AsyncMock()
        oom_redis.setex.side_effect = RuntimeError("OOM command not allowed")

        service = TokenRevocationService(redis_client=oom_redis)

        result = await service.revoke_token(valid_jti, expires_at)
        assert result is False, "Should handle OOM gracefully"

    async def test_extremely_long_ttl(self, mock_redis, valid_jti):
        """Test handling of very long TTL (years in future)."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # 10 years in future
        expires_at = datetime.now(UTC) + timedelta(days=3650)

        result = await service.revoke_token(valid_jti, expires_at)
        assert result is True

        # Verify TTL was set (should be capped or reasonable)
        call_args = mock_redis.setex.call_args
        ttl = call_args[0][1]
        assert ttl > 0, "TTL must be positive"

    async def test_unicode_jti_handling(self, mock_redis, expires_at):
        """Test handling of Unicode characters in JTI."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Unicode JTI
        jti = "token_🔒_𝕦𝕟𝕚𝕔𝕠𝕕𝕖"

        result = await service.revoke_token(jti, expires_at)
        assert result is True

        # Verify Redis key was set with Unicode preserved
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert jti in call_args[0][0]


@pytest.mark.asyncio
class TestUserRevocationTracking:
    """Tests for user-level revocation tracking (is_user_revoked)."""

    async def test_is_user_revoked_returns_true_when_token_old(self, mock_redis, user_id):
        """Test that tokens issued before user revocation are detected."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - user revoked at 12:00
        revocation_time = datetime.now(UTC).replace(hour=12, minute=0, second=0)
        mock_redis.get.return_value = revocation_time.isoformat().encode()

        # Token issued at 11:00 (before revocation)
        token_issued_at = revocation_time - timedelta(hours=1)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert
        assert result is True, "Token issued before revocation should be revoked"
        mock_redis.get.assert_called_once_with(f"user_revoked:{user_id}")

    async def test_is_user_revoked_returns_false_when_token_new(self, mock_redis, user_id):
        """Test that tokens issued after user revocation are valid."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - user revoked at 12:00
        revocation_time = datetime.now(UTC).replace(hour=12, minute=0, second=0)
        mock_redis.get.return_value = revocation_time.isoformat().encode()

        # Token issued at 13:00 (after revocation)
        token_issued_at = revocation_time + timedelta(hours=1)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert
        assert result is False, "Token issued after revocation should be valid"

    async def test_is_user_revoked_returns_false_when_no_revocation(self, mock_redis, user_id):
        """Test that users without revocation records are not flagged."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - no revocation record
        mock_redis.get.return_value = None

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert
        assert result is False, "Users without revocation should not be flagged"

    async def test_is_user_revoked_handles_redis_failure(self, user_id):
        """Test graceful degradation when Redis fails on user revocation check."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        failing_redis = AsyncMock()
        failing_redis.get.side_effect = ConnectionError("Redis unavailable")

        service = TokenRevocationService(redis_client=failing_redis)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open
        assert result is False, "Should fail open when Redis unavailable"

    async def test_is_user_revoked_handles_invalid_timestamp(self, mock_redis, user_id):
        """Test handling of corrupted/invalid revocation timestamp."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - invalid timestamp
        mock_redis.get.return_value = b"not-a-timestamp"

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open on corruption
        assert result is False, "Should fail open on corrupted timestamp"

    async def test_is_user_revoked_without_redis_client(self, user_id):
        """Test is_user_revoked without Redis client."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=None)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert
        assert result is False, "Should fail open without Redis"

    async def test_is_user_revoked_without_redis_client_fails_closed_in_production(
        self, user_id, monkeypatch
    ):
        from src.core.shared.config import settings
        from src.core.shared.security.token_revocation import TokenRevocationService

        monkeypatch.setattr(settings, "env", "production")
        monkeypatch.delenv("TOKEN_REVOCATION_FAIL_OPEN", raising=False)

        service = TokenRevocationService(redis_client=None)

        token_issued_at = datetime.now(UTC)

        result = await service.is_user_revoked(user_id, token_issued_at)

        assert result is True, "Should fail closed in production-like environments"

    async def test_is_user_revoked_with_timezone_naive_dates(self, mock_redis, user_id):
        """Test handling of timezone-naive datetimes."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # Arrange - timezone-naive timestamp
        revocation_time = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        mock_redis.get.return_value = revocation_time.isoformat().encode()

        # Timezone-naive token issued time
        token_issued_at = datetime(2024, 1, 1, 11, 0, 0)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - should handle gracefully
        assert result is True, "Should handle timezone-naive datetimes"


@pytest.mark.asyncio
class TestRevocationStats:
    """Tests for get_revocation_stats method."""

    async def test_get_revocation_stats_with_redis(self, mock_redis):
        """Test retrieving revocation statistics."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # scan_iter returns an async iterator, not a coroutine.
        async def _scan_iter_side_effect(pattern, count=100):
            if "token_blacklist" in pattern:
                for key in [b"token_blacklist:1", b"token_blacklist:2", b"token_blacklist:3"]:
                    yield key
            elif "user_revoked" in pattern:
                for key in [b"user_revoked:user1", b"user_revoked:user2"]:
                    yield key

        mock_redis.scan_iter = _scan_iter_side_effect

        # Act
        stats = await service.get_revocation_stats()

        # Assert
        assert stats["redis_available"] is True
        assert stats["blacklist_count"] == 3
        assert stats["user_revocations"] == 2
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_revocation_stats_without_redis(self):
        """Test stats when Redis is not available."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=None)

        # Act
        stats = await service.get_revocation_stats()

        # Assert
        assert stats["redis_available"] is False
        assert stats["blacklist_count"] == 0
        assert stats["user_revocations"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_revocation_stats_redis_failure(self):
        """Test stats when Redis fails."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        failing_redis = AsyncMock()

        # scan_iter is an async generator; make it raise on iteration.
        async def _scan_iter_raises(pattern, count=100):
            raise ConnectionError("Redis down")
            # Make this a generator with a yield that never executes.
            yield

        failing_redis.scan_iter = _scan_iter_raises

        service = TokenRevocationService(redis_client=failing_redis)

        # Act
        stats = await service.get_revocation_stats()

        # Assert
        assert stats["redis_available"] is False
        assert stats["blacklist_count"] == 0
        assert stats["user_revocations"] == 0
        assert "error" in stats

    async def test_get_revocation_stats_empty_blacklist(self, mock_redis):
        """Test stats when blacklist is empty."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        service = TokenRevocationService(redis_client=mock_redis)

        # scan_iter returns an async iterator that yields nothing for empty blacklist.
        async def _scan_iter_empty(pattern, count=100):
            return
            yield

        mock_redis.scan_iter = _scan_iter_empty

        # Act
        stats = await service.get_revocation_stats()

        # Assert
        assert stats["blacklist_count"] == 0
        assert stats["user_revocations"] == 0


@pytest.mark.asyncio
class TestCreateTokenRevocationService:
    """Tests for the convenience factory function."""

    async def test_create_service_fallback_on_connection_error(self):
        """Test graceful fallback when Redis connection fails."""
        from src.core.shared.security.token_revocation import create_token_revocation_service

        # Arrange - mock that raises on ping
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("Cannot connect"))

        mock_redis_async = MagicMock()
        mock_redis_async.from_url = AsyncMock(return_value=mock_client)

        # Act
        with patch.dict("sys.modules", {"redis.asyncio": mock_redis_async}):
            service = await create_token_revocation_service("redis://invalid:6379")

        # Assert - should return degraded service
        assert service is not None
        assert service._use_redis is False

    async def test_create_service_handles_import_error(self):
        """Test handling when redis module not available."""
        from src.core.shared.security.token_revocation import create_token_revocation_service

        # Arrange - simulate ImportError when importing redis.asyncio
        def mock_import(name, *args, **kwargs):
            if "redis" in name:
                raise ImportError(f"No module named '{name}'")
            return __import__(name, *args, **kwargs)

        # Act
        with patch("builtins.__import__", side_effect=mock_import):
            service = await create_token_revocation_service("redis://localhost:6379")

        # Assert
        assert service is not None
        assert service._use_redis is False


@pytest.mark.asyncio
class TestExceptionHandling:
    """Tests for exception handling paths."""

    async def test_is_token_revoked_unexpected_exception(self, valid_jti):
        """Test handling of unexpected exceptions in is_token_revoked."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        # Raise an unexpected exception (not Connection/Timeout)
        mock_redis.exists.side_effect = RuntimeError("Unexpected error")

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        result = await service.is_token_revoked(valid_jti)

        # Assert - should fail open
        assert result is False, "Should fail open on unexpected exceptions"

    async def test_revoke_all_user_tokens_connection_error(self, user_id, expires_at):
        """Test handling of ConnectionError in revoke_all_user_tokens."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = ConnectionError("Connection lost")

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert
        assert count == 0, "Should return 0 on connection error"

    async def test_revoke_all_user_tokens_unexpected_exception(self, user_id, expires_at):
        """Test handling of unexpected exceptions in revoke_all_user_tokens."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = RuntimeError("Unexpected error")

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert
        assert count == 0, "Should return 0 on unexpected exceptions"

    async def test_revoke_all_user_tokens_timeout_error(self, user_id, expires_at):
        """Test handling of TimeoutError in revoke_all_user_tokens."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = TimeoutError("Operation timed out")

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert
        assert count == 0, "Should return 0 on timeout"

    async def test_revoke_all_user_tokens_os_error(self, user_id, expires_at):
        """Test handling of OSError in revoke_all_user_tokens."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = OSError("Network error")

        service = TokenRevocationService(redis_client=mock_redis)

        # Act
        count = await service.revoke_all_user_tokens(user_id, expires_at)

        # Assert
        assert count == 0, "Should return 0 on OS error"

    async def test_is_user_revoked_connection_error(self, user_id):
        """Test handling of ConnectionError in is_user_revoked."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("Connection lost")

        service = TokenRevocationService(redis_client=mock_redis)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open
        assert result is False

    async def test_is_user_revoked_timeout_error(self, user_id):
        """Test handling of TimeoutError in is_user_revoked."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        mock_redis = AsyncMock()
        mock_redis.get.side_effect = TimeoutError("Operation timed out")

        service = TokenRevocationService(redis_client=mock_redis)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open
        assert result is False

    async def test_is_user_revoked_value_error(self, mock_redis, user_id):
        """Test handling of ValueError in timestamp parsing."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Return malformed timestamp that will cause ValueError
        mock_redis.get.return_value = b"2024-99-99T99:99:99"  # Invalid date

        service = TokenRevocationService(redis_client=mock_redis)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open on parse error
        assert result is False

    async def test_is_user_revoked_type_error(self, mock_redis, user_id):
        """Test handling of TypeError in is_user_revoked."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Return value that will cause TypeError
        mock_redis.get.return_value = 12345  # Not a string/bytes

        service = TokenRevocationService(redis_client=mock_redis)

        token_issued_at = datetime.now(UTC)

        # Act
        result = await service.is_user_revoked(user_id, token_issued_at)

        # Assert - fail open
        assert result is False

    async def test_is_user_revoked_unexpected_exception(self, mock_redis, user_id):
        """Test handling of unexpected exceptions in is_user_revoked."""
        from src.core.shared.security.token_revocation import TokenRevocationService

        # Make get() work but cause exception in date comparison
        mock_redis.get.return_value = datetime.now(UTC).isoformat().encode()

        service = TokenRevocationService(redis_client=mock_redis)

        # Pass None as token_issued_at to cause exception
        with patch.object(service, "_redis_client", mock_redis):
            # This will raise when trying to compare datetime
            result = await service.is_user_revoked(user_id, "not-a-datetime")  # type: ignore

        # Should fail open
        assert result is False
