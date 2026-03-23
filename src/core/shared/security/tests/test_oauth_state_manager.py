"""
OAuth2 State Manager Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive test suite for OAuth2StateManager service with Redis-backed storage.
Tests cover:
- High-entropy state generation
- State validation with client binding
- IP and user agent mismatch detection
- TTL expiry handling
- One-time use enforcement
- Graceful degradation without Redis
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError

# Import will be created
try:
    from src.core.shared.security.oauth_state_manager import (
        OAuth2StateExpiredError,
        OAuth2StateManager,
        OAuth2StateNotFoundError,
        OAuth2StateValidationError,
    )
except ImportError:
    # Tests will fail until implementation exists (RED phase)
    pass


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
async def state_manager(mock_redis):
    """Create OAuth2StateManager with mock Redis."""
    manager = OAuth2StateManager(redis_client=mock_redis)
    return manager


@pytest.fixture
async def state_manager_no_redis(monkeypatch):
    """Create OAuth2StateManager without Redis (degraded mode)."""
    monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "development")
    monkeypatch.delenv("OAUTH_STATE_ALLOW_DEGRADED_MODE", raising=False)
    manager = OAuth2StateManager(redis_client=None)
    return manager


class TestStateGeneration:
    """Test state parameter generation and entropy."""

    async def test_create_state_generates_high_entropy(self, state_manager):
        """Test that generated state has sufficient entropy (256-bit minimum)."""
        state = await state_manager.create_state(
            client_ip="192.168.1.100",
            user_agent="Mozilla/5.0 Test",
            provider="okta",
            callback_url="/sso/oidc/callback",
        )

        # State should be URL-safe base64 encoded
        assert isinstance(state, str)
        assert len(state) > 0

        # secrets.token_urlsafe(32) generates 256 bits (32 bytes)
        # Base64 encoding: 32 bytes -> 43 chars (32 * 4/3 rounded up)
        assert len(state) >= 43, "State entropy too low (< 256 bits)"

        # Should be URL-safe (no +, /, =)
        assert "+" not in state
        assert "/" not in state
        assert state.replace("-", "").replace("_", "").isalnum()

    async def test_create_state_stores_metadata_in_redis(self, state_manager, mock_redis):
        """Test that state metadata is stored in Redis with correct structure."""
        state = await state_manager.create_state(
            client_ip="10.0.0.5",
            user_agent="Chrome/120.0",
            provider="auth0",
            callback_url="/sso/callback",
        )

        # Verify Redis set was called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # Check Redis key format: oauth:state:{state_value}
        redis_key = call_args[0][0]
        assert redis_key.startswith("oauth:state:")
        assert redis_key.endswith(state)

        # Check stored value is JSON
        stored_value = call_args[0][1]
        import json

        stored_data = json.loads(stored_value)
        assert stored_data["provider"] == "auth0"
        assert stored_data["callback_url"] == "/sso/callback"
        assert stored_data["client_ip"] == "10.0.0.5"
        assert stored_data["user_agent"] == "Chrome/120.0"
        assert "created_at" in stored_data
        assert stored_data["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Check TTL is 5 minutes (300 seconds)
        assert call_args[1]["ex"] == 300

    async def test_create_state_unique_values(self, state_manager):
        """Test that consecutive calls generate unique state values."""
        states = []
        for _ in range(10):
            state = await state_manager.create_state(
                client_ip="127.0.0.1",
                user_agent="Test",
                provider="okta",
                callback_url="/callback",
            )
            states.append(state)

        # All states should be unique
        assert len(set(states)) == 10, "Generated states are not unique"

    async def test_create_state_validates_inputs(self, state_manager):
        """Test that create_state validates input parameters."""
        with pytest.raises((ValueError, ACGSValidationError), match="client_ip cannot be empty"):
            await state_manager.create_state(
                client_ip="",
                user_agent="Test",
                provider="okta",
                callback_url="/callback",
            )

        with pytest.raises((ValueError, ACGSValidationError), match="user_agent cannot be empty"):
            await state_manager.create_state(
                client_ip="127.0.0.1",
                user_agent="",
                provider="okta",
                callback_url="/callback",
            )

        with pytest.raises((ValueError, ACGSValidationError), match="provider cannot be empty"):
            await state_manager.create_state(
                client_ip="127.0.0.1",
                user_agent="Test",
                provider="",
                callback_url="/callback",
            )

        with pytest.raises((ValueError, ACGSValidationError), match="callback_url cannot be empty"):
            await state_manager.create_state(
                client_ip="127.0.0.1",
                user_agent="Test",
                provider="okta",
                callback_url="",
            )


class TestStateValidation:
    """Test state validation and retrieval."""

    async def test_validate_state_returns_stored_data(self, state_manager, mock_redis):
        """Test successful state validation returns stored metadata."""
        # Setup: Create state
        state = await state_manager.create_state(
            client_ip="192.168.1.50",
            user_agent="Firefox/120.0",
            provider="okta",
            callback_url="/sso/callback",
        )

        # Mock Redis to return the stored data
        import json

        stored_data = {
            "provider": "okta",
            "callback_url": "/sso/callback",
            "client_ip": "192.168.1.50",
            "user_agent": "Firefox/120.0",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        # Validate state
        result = await state_manager.validate_state(
            state=state,
            client_ip="192.168.1.50",
            user_agent="Firefox/120.0",
        )

        # Check returned data
        assert result["provider"] == "okta"
        assert result["callback_url"] == "/sso/callback"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_validate_state_fails_on_ip_mismatch(self, state_manager, mock_redis):
        """Test state validation fails when client IP doesn't match."""
        state = await state_manager.create_state(
            client_ip="10.0.0.1",
            user_agent="Chrome/120.0",
            provider="auth0",
            callback_url="/callback",
        )

        # Mock Redis with stored state
        import json

        stored_data = {
            "provider": "auth0",
            "callback_url": "/callback",
            "client_ip": "10.0.0.1",
            "user_agent": "Chrome/120.0",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        # Validate with different IP (CSRF attack simulation)
        with pytest.raises(OAuth2StateValidationError, match="Client IP mismatch"):
            await state_manager.validate_state(
                state=state,
                client_ip="10.0.0.99",  # Different IP
                user_agent="Chrome/120.0",
            )

    async def test_validate_state_fails_on_user_agent_mismatch(self, state_manager, mock_redis):
        """Test state validation fails when user agent doesn't match."""
        state = await state_manager.create_state(
            client_ip="127.0.0.1",
            user_agent="Safari/17.0",
            provider="okta",
            callback_url="/callback",
        )

        # Mock Redis with stored state
        import json

        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "127.0.0.1",
            "user_agent": "Safari/17.0",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        # Validate with different user agent (session hijacking simulation)
        with pytest.raises(OAuth2StateValidationError, match="User agent mismatch"):
            await state_manager.validate_state(
                state=state,
                client_ip="127.0.0.1",
                user_agent="Chrome/120.0",  # Different user agent
            )

    async def test_validate_state_fails_on_not_found(self, state_manager, mock_redis):
        """Test state validation fails when state not found in Redis."""
        # Mock Redis to return None (state not found)
        mock_redis.get.return_value = None

        with pytest.raises(OAuth2StateNotFoundError, match="State not found or expired"):
            await state_manager.validate_state(
                state="nonexistent_state_12345",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_validate_state_fails_after_expiry(self, state_manager, mock_redis):
        """Test state validation fails after TTL expiry (5 minutes)."""
        # Create state with expired timestamp
        import json

        expired_time = datetime.now(UTC) - timedelta(minutes=6)
        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "127.0.0.1",
            "user_agent": "Test",
            "created_at": expired_time.isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        with pytest.raises(OAuth2StateExpiredError, match="State has expired"):
            await state_manager.validate_state(
                state="expired_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_state_one_time_use(self, state_manager, mock_redis):
        """Test state is invalidated after first successful validation (one-time use)."""
        state = await state_manager.create_state(
            client_ip="10.0.0.1",
            user_agent="Chrome",
            provider="auth0",
            callback_url="/callback",
        )

        # Mock Redis with stored state
        import json

        stored_data = {
            "provider": "auth0",
            "callback_url": "/callback",
            "client_ip": "10.0.0.1",
            "user_agent": "Chrome",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        # First validation succeeds
        result = await state_manager.validate_state(
            state=state,
            client_ip="10.0.0.1",
            user_agent="Chrome",
        )
        assert result["provider"] == "auth0"

        # Verify state was deleted from Redis (one-time use)
        mock_redis.delete.assert_called_with(f"oauth:state:{state}")

        # Second validation should fail (state already used)
        mock_redis.get.return_value = None
        with pytest.raises(OAuth2StateNotFoundError):
            await state_manager.validate_state(
                state=state,
                client_ip="10.0.0.1",
                user_agent="Chrome",
            )


class TestStateInvalidation:
    """Test manual state invalidation."""

    async def test_invalidate_state_removes_from_redis(self, state_manager, mock_redis):
        """Test that invalidate_state removes state from Redis."""
        state = "test_state_12345"

        # Mock Redis delete to return 1 (key existed and was deleted)
        mock_redis.delete.return_value = 1

        result = await state_manager.invalidate_state(state)
        assert result is True

        # Verify Redis delete was called
        mock_redis.delete.assert_called_once_with(f"oauth:state:{state}")

    async def test_invalidate_state_returns_false_if_not_found(self, state_manager, mock_redis):
        """Test invalidate_state returns False if state doesn't exist."""
        # Mock Redis delete to return 0 (key didn't exist)
        mock_redis.delete.return_value = 0

        result = await state_manager.invalidate_state("nonexistent_state")
        assert result is False


class TestGracefulDegradation:
    """Test graceful degradation when Redis is unavailable."""

    async def test_graceful_degradation_without_redis(self, state_manager_no_redis):
        """Test service operates in degraded mode without Redis."""
        # Create state should still work (logged only)
        state = await state_manager_no_redis.create_state(
            client_ip="127.0.0.1",
            user_agent="Test",
            provider="okta",
            callback_url="/callback",
        )

        # State should still be generated
        assert isinstance(state, str)
        assert len(state) >= 43

    def test_without_redis_fails_closed_in_production_like_env(self, monkeypatch):
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        monkeypatch.delenv("OAUTH_STATE_ALLOW_DEGRADED_MODE", raising=False)

        with pytest.raises(OSError, match="Redis is required for OAuth2StateManager"):
            OAuth2StateManager(redis_client=None)

    def test_without_redis_fails_closed_when_only_environment_is_production(self, monkeypatch):
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "development")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("OAUTH_STATE_ALLOW_DEGRADED_MODE", raising=False)

        with pytest.raises(OSError, match="Redis is required for OAuth2StateManager"):
            OAuth2StateManager(redis_client=None)

    def test_without_redis_allows_explicit_degraded_override(self, monkeypatch):
        from src.core.shared.config import settings

        monkeypatch.setattr(settings, "env", "production")
        monkeypatch.setenv("OAUTH_STATE_ALLOW_DEGRADED_MODE", "true")

        manager = OAuth2StateManager(redis_client=None)
        assert manager is not None

    async def test_degraded_mode_validation_fails_gracefully(self, state_manager_no_redis):
        """Test validation fails gracefully without Redis (no crash)."""
        with pytest.raises(OAuth2StateNotFoundError, match="Redis unavailable"):
            await state_manager_no_redis.validate_state(
                state="any_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_invalidate_state_without_redis(self, state_manager_no_redis):
        """Test invalidate_state returns False without Redis."""
        result = await state_manager_no_redis.invalidate_state("any_state")
        assert result is False

    async def test_redis_connection_failure_during_create(self, mock_redis):
        """Test graceful handling of Redis connection failure during create_state."""
        # Mock Redis to raise connection error
        mock_redis.set.side_effect = ConnectionError("Redis connection lost")

        manager = OAuth2StateManager(redis_client=mock_redis)

        # Should not crash, but log error
        with pytest.raises(ConnectionError):
            await manager.create_state(
                client_ip="127.0.0.1",
                user_agent="Test",
                provider="okta",
                callback_url="/callback",
            )

    async def test_redis_connection_failure_during_validate(self, mock_redis):
        """Test graceful handling of Redis connection failure during validation."""
        # Mock Redis to raise connection error
        mock_redis.get.side_effect = ConnectionError("Redis connection lost")

        manager = OAuth2StateManager(redis_client=mock_redis)

        with pytest.raises(ConnectionError):
            await manager.validate_state(
                state="any_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_redis_delete_failure_during_validation(self, mock_redis):
        """Test that validation succeeds even if delete fails (one-time use enforcement)."""
        import json

        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "127.0.0.1",
            "user_agent": "Test",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)
        # Mock delete to raise error
        mock_redis.delete.side_effect = ConnectionError("Redis delete failed")

        manager = OAuth2StateManager(redis_client=mock_redis)

        # Validation should succeed despite delete failure (state was valid)
        result = await manager.validate_state(
            state="test_state",
            client_ip="127.0.0.1",
            user_agent="Test",
        )
        assert result["provider"] == "okta"

    async def test_invalidate_state_redis_error(self, mock_redis):
        """Test invalidate_state handles Redis errors gracefully."""
        mock_redis.delete.side_effect = ConnectionError("Redis connection lost")

        manager = OAuth2StateManager(redis_client=mock_redis)

        # Should return False on error, not crash
        result = await manager.invalidate_state("test_state")
        assert result is False


class TestConstitutionalCompliance:
    """Test constitutional hash validation and logging."""

    async def test_stored_data_includes_constitutional_hash(self, state_manager, mock_redis):
        """Test that stored state data includes constitutional hash."""
        await state_manager.create_state(
            client_ip="127.0.0.1",
            user_agent="Test",
            provider="okta",
            callback_url="/callback",
        )

        # Check stored data includes hash
        call_args = mock_redis.set.call_args
        stored_value = call_args[0][1]
        import json

        stored_data = json.loads(stored_value)
        assert "constitutional_hash" in stored_data
        assert stored_data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_validation_checks_constitutional_hash(self, state_manager, mock_redis):
        """Test that validation fails if constitutional hash is missing or wrong."""
        import json

        # Mock Redis with data missing constitutional_hash
        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "127.0.0.1",
            "user_agent": "Test",
            "created_at": datetime.now(UTC).isoformat(),
            # Missing constitutional_hash
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        with pytest.raises(OAuth2StateValidationError, match="Constitutional hash missing"):
            await state_manager.validate_state(
                state="test_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

        # Mock Redis with wrong hash
        stored_data["constitutional_hash"] = "wrong_hash_12345"
        mock_redis.get.return_value = json.dumps(stored_data)

        with pytest.raises(OAuth2StateValidationError, match="Constitutional hash mismatch"):
            await state_manager.validate_state(
                state="test_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_validation_without_created_at(self, state_manager, mock_redis):
        """Test validation succeeds if created_at is missing (edge case)."""
        import json

        # Mock Redis with data missing created_at
        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "127.0.0.1",
            "user_agent": "Test",
            # Missing created_at - should skip expiry check
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        mock_redis.get.return_value = json.dumps(stored_data)

        # Should succeed (expiry check skipped)
        result = await state_manager.validate_state(
            state="test_state",
            client_ip="127.0.0.1",
            user_agent="Test",
        )
        assert result["provider"] == "okta"


class TestEdgeCases:
    """Test edge cases and security scenarios."""

    async def test_concurrent_state_creation(self, state_manager):
        """Test concurrent state creation doesn't cause collisions."""
        # Create multiple states concurrently
        tasks = [
            state_manager.create_state(
                client_ip=f"192.168.1.{i}",
                user_agent=f"Browser{i}",
                provider="okta",
                callback_url="/callback",
            )
            for i in range(50)
        ]

        states = await asyncio.gather(*tasks)

        # All states should be unique
        assert len(set(states)) == 50

    async def test_state_with_special_characters_in_metadata(self, state_manager, mock_redis):
        """Test state creation/validation with special characters in metadata."""
        state = await state_manager.create_state(
            client_ip="127.0.0.1",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            provider="auth0-test-123",
            callback_url="/sso/oidc/callback?foo=bar&baz=qux",
        )

        # Should not crash, special chars should be JSON-encoded properly
        assert isinstance(state, str)

    async def test_replay_attack_prevention(self, state_manager, mock_redis):
        """Test that replay attacks are prevented by one-time use."""
        import json

        state = "replay_test_state"
        stored_data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "10.0.0.1",
            "user_agent": "Chrome",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # First request succeeds
        mock_redis.get.return_value = json.dumps(stored_data)
        result1 = await state_manager.validate_state(
            state=state,
            client_ip="10.0.0.1",
            user_agent="Chrome",
        )
        assert result1["provider"] == "okta"

        # State is deleted (one-time use)
        mock_redis.delete.assert_called_once()

        # Replay attempt fails
        mock_redis.get.return_value = None
        with pytest.raises(OAuth2StateNotFoundError):
            await state_manager.validate_state(
                state=state,
                client_ip="10.0.0.1",
                user_agent="Chrome",
            )

    async def test_empty_string_state_validation(self, state_manager):
        """Test validation with empty state string."""
        with pytest.raises((ValueError, ACGSValidationError), match="state cannot be empty"):
            await state_manager.validate_state(
                state="",
                client_ip="127.0.0.1",
                user_agent="Test",
            )

    async def test_malformed_json_in_redis(self, state_manager, mock_redis):
        """Test handling of malformed JSON in Redis."""
        # Mock Redis to return invalid JSON
        mock_redis.get.return_value = "invalid{json}data"

        with pytest.raises(OAuth2StateValidationError, match="Invalid state data"):
            await state_manager.validate_state(
                state="test_state",
                client_ip="127.0.0.1",
                user_agent="Test",
            )
