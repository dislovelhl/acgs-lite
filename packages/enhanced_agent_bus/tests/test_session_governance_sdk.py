"""
Session Governance SDK Tests
Constitutional Hash: cdd01ef066bc6cf2

Phase 10 Task 13: Session Governance SDK

Tests:
- Session lifecycle management (create, validate, extend, revoke)
- Session governance policies (max duration, idle timeout, concurrent sessions)
- Session monitoring and analytics
- Cross-tenant session isolation
- Token management with refresh
- Constitutional compliance validation
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enterprise_sso.session_governance_sdk import (  # noqa: E402
    CONSTITUTIONAL_HASH,
    ConcurrencyPolicy,
    SessionAnalytics,
    SessionConfig,
    SessionEvent,
    SessionEventType,
    SessionGovernanceClient,
    SessionGovernanceError,
    SessionGovernancePolicy,
    SessionLifecycleManager,
    SessionMonitor,
    SessionState,
    SessionToken,
    SessionTokenManager,
    SessionValidationResult,
    TenantSessionStore,
)

_TEST_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _TEST_RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

# ============================================================================
# Test Classes
# ============================================================================


class TestSessionLifecycle:
    """Tests for session lifecycle management."""

    @pytest.fixture
    def lifecycle_manager(self):
        return SessionLifecycleManager()

    @pytest.fixture
    def session_config(self):
        return SessionConfig(
            tenant_id="tenant-001",
            user_id="user-123",
            max_duration_minutes=60,
            idle_timeout_minutes=15,
            refresh_threshold_minutes=5,
        )

    async def test_create_session(self, lifecycle_manager, session_config):
        """Test creating a new session."""
        session = await lifecycle_manager.create_session(session_config)

        assert session is not None
        assert session.session_id is not None
        assert session.tenant_id == "tenant-001"
        assert session.user_id == "user-123"
        assert session.state == SessionState.ACTIVE
        assert session.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_validate_active_session(self, lifecycle_manager, session_config):
        """Test validating an active session."""
        session = await lifecycle_manager.create_session(session_config)

        result = await lifecycle_manager.validate_session(session.session_id)

        assert result.is_valid is True
        assert result.session_id == session.session_id
        assert result.state == SessionState.ACTIVE

    async def test_validate_expired_session(self, lifecycle_manager, session_config):
        """Test validating an expired session."""
        session_config.max_duration_minutes = 0
        session = await lifecycle_manager.create_session(session_config)

        # Force expiration
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await lifecycle_manager._update_session(session)

        result = await lifecycle_manager.validate_session(session.session_id)

        assert result.is_valid is False
        assert result.reason == "session_expired"

    async def test_extend_session(self, lifecycle_manager, session_config):
        """Test extending a session."""
        session = await lifecycle_manager.create_session(session_config)
        original_expires = session.expires_at

        extended = await lifecycle_manager.extend_session(session.session_id, extension_minutes=30)

        assert extended.expires_at > original_expires
        assert extended.extension_count == 1

    async def test_revoke_session(self, lifecycle_manager, session_config):
        """Test revoking a session."""
        session = await lifecycle_manager.create_session(session_config)

        revoked = await lifecycle_manager.revoke_session(session.session_id, reason="user_logout")

        assert revoked.state == SessionState.REVOKED
        assert revoked.revocation_reason == "user_logout"

    async def test_refresh_session_activity(self, lifecycle_manager, session_config):
        """Test refreshing session activity."""
        session = await lifecycle_manager.create_session(session_config)
        original_activity = session.last_activity

        await asyncio.sleep(0.01)  # Small delay
        refreshed = await lifecycle_manager.refresh_activity(session.session_id)

        assert refreshed.last_activity > original_activity

    async def test_session_idle_timeout(self, lifecycle_manager, session_config):
        """Test session idle timeout detection."""
        session_config.idle_timeout_minutes = 0
        session = await lifecycle_manager.create_session(session_config)

        # Force idle
        session.last_activity = datetime.now(UTC) - timedelta(minutes=1)
        await lifecycle_manager._update_session(session)

        result = await lifecycle_manager.validate_session(session.session_id)

        assert result.is_valid is False
        assert result.reason == "idle_timeout"


class TestSessionGovernancePolicy:
    """Tests for session governance policies."""

    @pytest.fixture
    def policy(self):
        return SessionGovernancePolicy(
            tenant_id="tenant-001",
            max_session_duration_minutes=480,
            idle_timeout_minutes=30,
            max_concurrent_sessions=5,
            require_mfa=True,
            allowed_ip_ranges=["10.0.0.0/8", "192.168.0.0/16"],
            session_refresh_enabled=True,
        )

    def test_policy_validation(self, policy):
        """Test policy validation."""
        assert policy.is_valid() is True
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_policy_max_concurrent_sessions(self, policy):
        """Test concurrent session limit."""
        assert policy.max_concurrent_sessions == 5
        assert policy.enforce_concurrent_limit is True

    def test_policy_mfa_requirement(self, policy):
        """Test MFA requirement policy."""
        assert policy.require_mfa is True

    def test_policy_ip_restrictions(self, policy):
        """Test IP restriction policy."""
        assert len(policy.allowed_ip_ranges) == 2
        assert "10.0.0.0/8" in policy.allowed_ip_ranges

    def test_policy_defaults(self):
        """Test default policy values."""
        policy = SessionGovernancePolicy(tenant_id="tenant-001")

        assert policy.max_session_duration_minutes == 480
        assert policy.idle_timeout_minutes == 30
        assert policy.max_concurrent_sessions == 3
        assert policy.require_mfa is False


class TestConcurrencyPolicy:
    """Tests for session concurrency management."""

    @pytest.fixture
    def concurrency_policy(self):
        return ConcurrencyPolicy(
            tenant_id="tenant-001",
            max_sessions_per_user=3,
            enforcement_mode="strict",
            eviction_strategy="oldest_first",
        )

    @pytest.fixture
    def session_store(self):
        return TenantSessionStore(tenant_id="tenant-001")

    async def test_check_concurrency_allowed(self, concurrency_policy, session_store):
        """Test concurrency check when under limit."""
        result = await concurrency_policy.check_concurrency(
            user_id="user-123", session_store=session_store
        )

        assert result.allowed is True
        assert result.current_count == 0

    async def test_check_concurrency_exceeded(self, concurrency_policy, session_store):
        """Test concurrency check when at limit."""
        # Add 3 sessions
        for i in range(3):
            await session_store.add_session(
                session_id=f"session-{i}", user_id="user-123", created_at=datetime.now(UTC)
            )

        result = await concurrency_policy.check_concurrency(
            user_id="user-123", session_store=session_store
        )

        assert result.allowed is False
        assert result.current_count == 3

    async def test_evict_oldest_session(self, concurrency_policy, session_store):
        """Test eviction of oldest session."""
        # Add 3 sessions with different ages
        for i in range(3):
            await session_store.add_session(
                session_id=f"session-{i}",
                user_id="user-123",
                created_at=datetime.now(UTC) - timedelta(hours=3 - i),
            )

        evicted = await concurrency_policy.evict_session(
            user_id="user-123", session_store=session_store
        )

        assert evicted.session_id == "session-0"  # Oldest

    async def test_strict_enforcement_blocks(self, concurrency_policy, session_store):
        """Test strict enforcement blocks new sessions."""
        # Fill to limit
        for i in range(3):
            await session_store.add_session(
                session_id=f"session-{i}", user_id="user-123", created_at=datetime.now(UTC)
            )

        with pytest.raises(SessionGovernanceError) as exc_info:
            await concurrency_policy.enforce(user_id="user-123", session_store=session_store)

        assert "concurrent session limit exceeded" in str(exc_info.value).lower()


class TestSessionTokenManager:
    """Tests for session token management."""

    @pytest.fixture
    def token_manager(self):
        return SessionTokenManager(
            private_key=TEST_PRIVATE_KEY,
            token_ttl_minutes=60,
            refresh_token_ttl_days=7,
        )

    async def test_generate_access_token(self, token_manager):
        """Test access token generation."""
        token = await token_manager.generate_access_token(
            session_id="session-123",
            tenant_id="tenant-001",
            user_id="user-123",
            roles=["admin", "user"],
        )

        assert token.access_token is not None
        assert len(token.access_token) > 0
        assert token.token_type == "Bearer"  # noqa: S105
        assert token.expires_in > 0

    async def test_generate_refresh_token(self, token_manager):
        """Test refresh token generation."""
        token = await token_manager.generate_refresh_token(
            session_id="session-123", tenant_id="tenant-001", user_id="user-123"
        )

        assert token.refresh_token is not None
        assert len(token.refresh_token) > 0
        assert token.expires_in > 0

    async def test_validate_access_token(self, token_manager):
        """Test access token validation."""
        token = await token_manager.generate_access_token(
            session_id="session-123", tenant_id="tenant-001", user_id="user-123", roles=["admin"]
        )

        result = await token_manager.validate_token(token.access_token)

        assert result.is_valid is True
        assert result.session_id == "session-123"
        assert result.tenant_id == "tenant-001"

    async def test_refresh_access_token(self, token_manager):
        """Test refreshing access token."""
        # Generate initial tokens
        access = await token_manager.generate_access_token(
            session_id="session-123", tenant_id="tenant-001", user_id="user-123", roles=["user"]
        )
        refresh = await token_manager.generate_refresh_token(
            session_id="session-123", tenant_id="tenant-001", user_id="user-123"
        )

        # Refresh
        new_token = await token_manager.refresh_access_token(refresh.refresh_token)

        assert new_token.access_token is not None
        assert new_token.access_token != access.access_token

    async def test_revoke_token(self, token_manager):
        """Test token revocation."""
        token = await token_manager.generate_access_token(
            session_id="session-123", tenant_id="tenant-001", user_id="user-123", roles=["user"]
        )

        await token_manager.revoke_token(token.access_token)
        result = await token_manager.validate_token(token.access_token)

        assert result.is_valid is False
        assert result.reason == "token_revoked"


class TestSessionMonitor:
    """Tests for session monitoring and analytics."""

    @pytest.fixture
    def monitor(self):
        return SessionMonitor(tenant_id="tenant-001")

    @pytest.fixture
    def sample_events(self):
        now = datetime.now(UTC)
        return [
            SessionEvent(
                event_type=SessionEventType.CREATED,
                session_id="session-1",
                user_id="user-1",
                timestamp=now - timedelta(hours=2),
            ),
            SessionEvent(
                event_type=SessionEventType.ACTIVITY,
                session_id="session-1",
                user_id="user-1",
                timestamp=now - timedelta(hours=1),
            ),
            SessionEvent(
                event_type=SessionEventType.EXPIRED,
                session_id="session-2",
                user_id="user-2",
                timestamp=now - timedelta(minutes=30),
            ),
        ]

    async def test_record_session_event(self, monitor):
        """Test recording a session event."""
        event = SessionEvent(
            event_type=SessionEventType.CREATED,
            session_id="session-123",
            user_id="user-123",
            timestamp=datetime.now(UTC),
        )

        await monitor.record_event(event)

        events = await monitor.get_events(session_id="session-123")
        assert len(events) == 1
        assert events[0].event_type == SessionEventType.CREATED

    async def test_get_active_session_count(self, monitor, sample_events):
        """Test getting active session count."""
        for event in sample_events:
            await monitor.record_event(event)

        count = await monitor.get_active_session_count()

        assert count >= 0

    async def test_get_session_analytics(self, monitor, sample_events):
        """Test getting session analytics."""
        for event in sample_events:
            await monitor.record_event(event)

        analytics = await monitor.get_analytics(
            start_time=datetime.now(UTC) - timedelta(hours=24),
            end_time=datetime.now(UTC),
        )

        assert isinstance(analytics, SessionAnalytics)
        assert analytics.total_sessions >= 0
        assert analytics.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_get_user_session_history(self, monitor, sample_events):
        """Test getting user session history."""
        for event in sample_events:
            await monitor.record_event(event)

        history = await monitor.get_user_session_history(user_id="user-1")

        assert len(history) >= 1


class TestTenantSessionStore:
    """Tests for tenant session isolation."""

    @pytest.fixture
    def store(self):
        return TenantSessionStore(tenant_id="tenant-001")

    async def test_add_and_get_session(self, store):
        """Test adding and retrieving a session."""
        await store.add_session(
            session_id="session-123", user_id="user-123", created_at=datetime.now(UTC)
        )

        session = await store.get_session("session-123")

        assert session is not None
        assert session.session_id == "session-123"

    async def test_session_isolation_between_tenants(self):
        """Test session isolation between tenants."""
        store1 = TenantSessionStore(tenant_id="tenant-001")
        store2 = TenantSessionStore(tenant_id="tenant-002")

        await store1.add_session(
            session_id="session-123", user_id="user-123", created_at=datetime.now(UTC)
        )

        # Should not find session in other tenant's store
        session = await store2.get_session("session-123")

        assert session is None

    async def test_list_user_sessions(self, store):
        """Test listing all sessions for a user."""
        for i in range(3):
            await store.add_session(
                session_id=f"session-{i}", user_id="user-123", created_at=datetime.now(UTC)
            )

        sessions = await store.list_user_sessions("user-123")

        assert len(sessions) == 3

    async def test_remove_session(self, store):
        """Test removing a session."""
        await store.add_session(
            session_id="session-123", user_id="user-123", created_at=datetime.now(UTC)
        )

        await store.remove_session("session-123")
        session = await store.get_session("session-123")

        assert session is None

    async def test_cleanup_expired_sessions(self, store):
        """Test cleanup of expired sessions."""
        # Add expired session
        await store.add_session(
            session_id="session-expired",
            user_id="user-123",
            created_at=datetime.now(UTC) - timedelta(hours=24),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        # Add active session
        await store.add_session(
            session_id="session-active",
            user_id="user-123",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        removed = await store.cleanup_expired()

        assert removed == 1
        assert await store.get_session("session-expired") is None
        assert await store.get_session("session-active") is not None


class TestSessionGovernanceClient:
    """Tests for session governance SDK client."""

    @pytest.fixture
    def client(self):
        return SessionGovernanceClient(
            base_url="http://localhost:8000", api_key="test-api-key", tenant_id="tenant-001"
        )

    async def test_client_create_session(self, client):
        """Test client session creation."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "session_id": "session-123",
                "state": "active",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

            session = await client.create_session(user_id="user-123", metadata={"source": "web"})

            assert session["session_id"] == "session-123"

    async def test_client_validate_session(self, client):
        """Test client session validation."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "is_valid": True,
                "session_id": "session-123",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

            result = await client.validate_session("session-123")

            assert result["is_valid"] is True

    async def test_client_revoke_session(self, client):
        """Test client session revocation."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "session_id": "session-123",
                "state": "revoked",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

            result = await client.revoke_session(session_id="session-123", reason="user_logout")

            assert result["state"] == "revoked"

    async def test_client_with_retry(self, client):
        """Test client retry on transient errors."""
        client.max_retries = 3

        with patch.object(client, "_make_request") as mock_request:
            mock_request.side_effect = [
                ConnectionError("Connection failed"),
                ConnectionError("Connection failed again"),
                {"session_id": "session-123"},
            ]

            result = await client.create_session(user_id="user-123")

            assert result is not None
            assert mock_request.call_count == 3


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_session_config_includes_hash(self):
        """Test session config includes constitutional hash."""
        config = SessionConfig(tenant_id="tenant-001", user_id="user-123")
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_governance_policy_includes_hash(self):
        """Test governance policy includes constitutional hash."""
        policy = SessionGovernancePolicy(tenant_id="tenant-001")
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_concurrency_policy_includes_hash(self):
        """Test concurrency policy includes constitutional hash."""
        policy = ConcurrencyPolicy(tenant_id="tenant-001", max_sessions_per_user=3)
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_session_token_includes_hash(self):
        """Test session token includes constitutional hash."""
        token = SessionToken(access_token="token-123", token_type="Bearer", expires_in=3600)  # noqa: S106
        assert token.constitutional_hash == CONSTITUTIONAL_HASH

    def test_session_analytics_includes_hash(self):
        """Test session analytics includes constitutional hash."""
        analytics = SessionAnalytics(tenant_id="tenant-001", total_sessions=100)
        assert analytics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_validation_result_includes_hash(self):
        """Test validation result includes constitutional hash."""
        result = SessionValidationResult(is_valid=True, session_id="session-123")
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
