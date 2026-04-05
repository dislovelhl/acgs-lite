# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for enterprise_sso/session_governance_sdk.py
Target: >=90% coverage
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.enterprise_sso.session_governance_sdk import (
    ConcurrencyCheckResult,
    ConcurrencyPolicy,
    Session,
    SessionAnalytics,
    SessionConfig,
    SessionEvent,
    SessionEventType,
    SessionExpiredError,
    SessionGovernanceClient,
    SessionGovernanceError,
    SessionGovernancePolicy,
    SessionLifecycleManager,
    SessionMonitor,
    SessionNotFoundError,
    SessionState,
    SessionToken,
    SessionTokenManager,
    SessionValidationResult,
    StoredSession,
    TenantSessionStore,
    TokenValidationError,
    TokenValidationResult,
)

_TEST_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _TEST_RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

# ============================================================================
# Exception Tests
# ============================================================================


class TestSessionGovernanceError:
    def test_session_governance_error_is_exception(self):
        err = SessionGovernanceError("test error")
        assert isinstance(err, SessionGovernanceError)
        assert "test error" in str(err)

    def test_session_governance_error_http_status(self):
        assert SessionGovernanceError.http_status_code == 500

    def test_session_governance_error_code(self):
        assert SessionGovernanceError.error_code == "SESSION_GOVERNANCE_ERROR"

    def test_session_not_found_error_inherits(self):
        err = SessionNotFoundError("not found")
        assert isinstance(err, SessionGovernanceError)

    def test_session_expired_error_inherits(self):
        err = SessionExpiredError("expired")
        assert isinstance(err, SessionGovernanceError)

    def test_token_validation_error_inherits(self):
        err = TokenValidationError("invalid token")
        assert isinstance(err, SessionGovernanceError)


# ============================================================================
# Enum Tests
# ============================================================================


class TestSessionState:
    def test_all_states_exist(self):
        assert SessionState.PENDING.value == "pending"
        assert SessionState.ACTIVE.value == "active"
        assert SessionState.IDLE.value == "idle"
        assert SessionState.EXPIRED.value == "expired"
        assert SessionState.REVOKED.value == "revoked"


class TestSessionEventType:
    def test_all_event_types_exist(self):
        assert SessionEventType.CREATED.value == "created"
        assert SessionEventType.VALIDATED.value == "validated"
        assert SessionEventType.EXTENDED.value == "extended"
        assert SessionEventType.ACTIVITY.value == "activity"
        assert SessionEventType.IDLE.value == "idle"
        assert SessionEventType.EXPIRED.value == "expired"
        assert SessionEventType.REVOKED.value == "revoked"


# ============================================================================
# Data Class Tests
# ============================================================================


class TestSessionConfig:
    def test_default_values(self):
        config = SessionConfig(tenant_id="t1", user_id="u1")
        assert config.tenant_id == "t1"
        assert config.user_id == "u1"
        assert config.max_duration_minutes == 60
        assert config.idle_timeout_minutes == 15
        assert config.refresh_threshold_minutes == 5
        assert config.metadata == {}
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        config = SessionConfig(
            tenant_id="t1",
            user_id="u1",
            max_duration_minutes=120,
            idle_timeout_minutes=30,
            refresh_threshold_minutes=10,
            metadata={"key": "value"},
        )
        assert config.max_duration_minutes == 120
        assert config.idle_timeout_minutes == 30
        assert config.refresh_threshold_minutes == 10
        assert config.metadata == {"key": "value"}


class TestSession:
    def test_session_creation(self):
        now = datetime.now(UTC)
        session = Session(
            session_id="sid1",
            tenant_id="t1",
            user_id="u1",
            state=SessionState.ACTIVE,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_activity=now,
        )
        assert session.session_id == "sid1"
        assert session.state == SessionState.ACTIVE
        assert session.extension_count == 0
        assert session.revocation_reason is None
        assert session.metadata == {}
        assert session.constitutional_hash == CONSTITUTIONAL_HASH


class TestSessionValidationResult:
    def test_valid_result(self):
        result = SessionValidationResult(is_valid=True, session_id="sid1")
        assert result.is_valid is True
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_invalid_result(self):
        result = SessionValidationResult(is_valid=False, reason="expired")
        assert result.is_valid is False
        assert result.reason == "expired"


class TestSessionGovernancePolicy:
    def test_default_policy_is_valid(self):
        policy = SessionGovernancePolicy(tenant_id="t1")
        assert policy.is_valid() is True

    def test_invalid_duration_zero(self):
        policy = SessionGovernancePolicy(tenant_id="t1", max_session_duration_minutes=0)
        assert policy.is_valid() is False

    def test_invalid_concurrent_sessions_zero(self):
        policy = SessionGovernancePolicy(tenant_id="t1", max_concurrent_sessions=0)
        assert policy.is_valid() is False

    def test_zero_idle_timeout_is_valid(self):
        policy = SessionGovernancePolicy(tenant_id="t1", idle_timeout_minutes=0)
        assert policy.is_valid() is True

    def test_policy_attributes(self):
        policy = SessionGovernancePolicy(
            tenant_id="t1",
            max_session_duration_minutes=240,
            idle_timeout_minutes=20,
            max_concurrent_sessions=5,
            require_mfa=True,
            allowed_ip_ranges=["192.168.1.0/24"],
            session_refresh_enabled=False,
            enforce_concurrent_limit=False,
        )
        assert policy.max_session_duration_minutes == 240
        assert policy.require_mfa is True
        assert policy.allowed_ip_ranges == ["192.168.1.0/24"]
        assert policy.session_refresh_enabled is False
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH


class TestConcurrencyCheckResult:
    def test_allowed_result(self):
        result = ConcurrencyCheckResult(allowed=True, current_count=1, max_allowed=3)
        assert result.allowed is True
        assert result.sessions_to_evict == []
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_denied_result(self):
        result = ConcurrencyCheckResult(allowed=False, current_count=3, max_allowed=3)
        assert result.allowed is False


class TestSessionToken:
    def test_default_values(self):
        token = SessionToken(access_token="tok123")
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert token.refresh_token is None
        assert token.scope is None
        assert token.constitutional_hash == CONSTITUTIONAL_HASH


class TestTokenValidationResult:
    def test_valid_result(self):
        result = TokenValidationResult(is_valid=True, session_id="sid", user_id="u1")
        assert result.roles == []
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_invalid_result(self):
        result = TokenValidationResult(is_valid=False, reason="expired")
        assert result.is_valid is False


class TestSessionEvent:
    def test_event_creation_defaults(self):
        event = SessionEvent(
            event_type=SessionEventType.CREATED,
            session_id="sid1",
            user_id="u1",
        )
        assert event.event_type == SessionEventType.CREATED
        assert event.session_id == "sid1"
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_event_with_metadata(self):
        event = SessionEvent(
            event_type=SessionEventType.ACTIVITY,
            session_id="sid1",
            user_id="u1",
            metadata={"ip": "127.0.0.1"},
        )
        assert event.metadata == {"ip": "127.0.0.1"}


class TestSessionAnalytics:
    def test_default_analytics(self):
        analytics = SessionAnalytics(tenant_id="t1")
        assert analytics.total_sessions == 0
        assert analytics.active_sessions == 0
        assert analytics.expired_sessions == 0
        assert analytics.revoked_sessions == 0
        assert analytics.average_duration_minutes == 0.0
        assert analytics.peak_concurrent_sessions == 0
        assert analytics.period_start is None
        assert analytics.period_end is None
        assert analytics.constitutional_hash == CONSTITUTIONAL_HASH


class TestStoredSession:
    def test_stored_session_creation(self):
        now = datetime.now(UTC)
        stored = StoredSession(
            session_id="sid1",
            user_id="u1",
            created_at=now,
        )
        assert stored.session_id == "sid1"
        assert stored.expires_at is None
        assert stored.last_activity is None
        assert stored.metadata == {}


# ============================================================================
# TenantSessionStore Tests
# ============================================================================


class TestTenantSessionStore:
    def test_init(self):
        store = TenantSessionStore(tenant_id="t1")
        assert store.tenant_id == "t1"
        assert store.constitutional_hash == CONSTITUTIONAL_HASH
        assert store._sessions == {}

    def test_init_custom_hash(self):
        store = TenantSessionStore(tenant_id="t1", constitutional_hash="custom_hash")
        assert store.constitutional_hash == "custom_hash"

    async def test_add_session_with_metadata(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        expires = now + timedelta(hours=1)
        session = await store.add_session("sid1", "u1", now, expires, {"key": "val"})
        assert session.session_id == "sid1"
        assert session.user_id == "u1"
        assert session.last_activity == now
        assert session.metadata == {"key": "val"}

    async def test_add_session_no_metadata(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        session = await store.add_session("sid1", "u1", now)
        assert session.metadata == {}

    async def test_add_session_stored_in_dict(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        assert "sid1" in store._sessions

    async def test_get_session_existing(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        result = await store.get_session("sid1")
        assert result is not None
        assert result.session_id == "sid1"

    async def test_get_session_nonexistent(self):
        store = TenantSessionStore(tenant_id="t1")
        result = await store.get_session("nonexistent")
        assert result is None

    async def test_remove_session(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        await store.remove_session("sid1")
        result = await store.get_session("sid1")
        assert result is None

    async def test_remove_nonexistent_session_no_error(self):
        store = TenantSessionStore(tenant_id="t1")
        # Should not raise
        await store.remove_session("nonexistent")

    async def test_list_user_sessions_multiple(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        await store.add_session("sid2", "u1", now)
        await store.add_session("sid3", "u2", now)
        sessions = await store.list_user_sessions("u1")
        assert len(sessions) == 2
        assert all(s.user_id == "u1" for s in sessions)

    async def test_list_user_sessions_empty(self):
        store = TenantSessionStore(tenant_id="t1")
        sessions = await store.list_user_sessions("u_none")
        assert sessions == []

    async def test_cleanup_expired_removes_expired(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=1)
        await store.add_session("expired", "u1", past, past)
        await store.add_session("active", "u1", now, future)
        count = await store.cleanup_expired()
        assert count == 1
        assert await store.get_session("expired") is None
        assert await store.get_session("active") is not None

    async def test_cleanup_no_expired(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        await store.add_session("active", "u1", now, future)
        count = await store.cleanup_expired()
        assert count == 0

    async def test_cleanup_session_without_expires_at_not_removed(self):
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("no_expiry", "u1", now, None)
        count = await store.cleanup_expired()
        assert count == 0

    async def test_cleanup_empty_store(self):
        store = TenantSessionStore(tenant_id="t1")
        count = await store.cleanup_expired()
        assert count == 0


# ============================================================================
# SessionLifecycleManager Tests
# ============================================================================


class TestSessionLifecycleManager:
    def test_init_defaults(self):
        manager = SessionLifecycleManager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH
        assert manager._sessions == {}
        assert manager._stores == {}

    def test_init_custom_hash(self):
        manager = SessionLifecycleManager(constitutional_hash="custom")
        assert manager.constitutional_hash == "custom"

    def test_get_store_creates_new(self):
        manager = SessionLifecycleManager()
        store = manager._get_store("t1")
        assert isinstance(store, TenantSessionStore)
        assert store.tenant_id == "t1"

    def test_get_store_reuses_existing(self):
        manager = SessionLifecycleManager()
        store1 = manager._get_store("t1")
        store2 = manager._get_store("t1")
        assert store1 is store2

    def test_get_store_different_tenants(self):
        manager = SessionLifecycleManager()
        store1 = manager._get_store("t1")
        store2 = manager._get_store("t2")
        assert store1 is not store2

    async def test_create_session_basic(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        assert session.tenant_id == "t1"
        assert session.user_id == "u1"
        assert session.state == SessionState.ACTIVE
        assert session.constitutional_hash == CONSTITUTIONAL_HASH
        assert "idle_timeout_minutes" in session.metadata
        assert session.metadata["idle_timeout_minutes"] == 15

    async def test_create_session_with_metadata(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1", metadata={"role": "admin"})
        session = await manager.create_session(config)
        assert session.metadata.get("role") == "admin"
        assert session.metadata.get("idle_timeout_minutes") == 15

    async def test_create_session_stores_in_dict(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        assert session.session_id in manager._sessions

    async def test_create_session_adds_to_tenant_store(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        store = manager._get_store("t1")
        stored = await store.get_session(session.session_id)
        assert stored is not None

    async def test_validate_session_valid(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is True
        assert result.session_id == session.session_id
        assert result.tenant_id == "t1"
        assert result.user_id == "u1"

    async def test_validate_session_not_found(self):
        manager = SessionLifecycleManager()
        result = await manager.validate_session("nonexistent")
        assert result.is_valid is False
        assert result.reason == "session_not_found"

    async def test_validate_session_expired(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        # Force expiry
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is False
        assert result.reason == "session_expired"
        assert result.state == SessionState.EXPIRED
        assert session.state == SessionState.EXPIRED

    async def test_validate_session_idle(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1", idle_timeout_minutes=15)
        session = await manager.create_session(config)
        # Force last_activity to be in the past beyond idle threshold
        session.last_activity = datetime.now(UTC) - timedelta(minutes=20)
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is False
        assert result.reason == "idle_timeout"
        assert result.state == SessionState.IDLE
        assert session.state == SessionState.IDLE

    async def test_validate_session_revoked(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        session.state = SessionState.REVOKED
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is False
        assert result.reason == "session_revoked"

    async def test_validate_session_returns_hash(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        result = await manager.validate_session(session.session_id)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_extend_session_success(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        original_expiry = session.expires_at
        extended = await manager.extend_session(session.session_id, 30)
        assert extended.expires_at > original_expiry
        assert extended.extension_count == 1

    async def test_extend_session_default_minutes(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        original_expiry = session.expires_at
        extended = await manager.extend_session(session.session_id)
        assert extended.expires_at > original_expiry
        assert extended.extension_count == 1

    async def test_extend_session_not_found(self):
        manager = SessionLifecycleManager()
        with pytest.raises(SessionNotFoundError):
            await manager.extend_session("nonexistent")

    async def test_revoke_session_success(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        revoked = await manager.revoke_session(session.session_id, "admin_action")
        assert revoked.state == SessionState.REVOKED
        assert revoked.revocation_reason == "admin_action"

    async def test_revoke_session_default_reason(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        revoked = await manager.revoke_session(session.session_id)
        assert revoked.revocation_reason == "user_logout"

    async def test_revoke_session_removes_from_store(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        await manager.revoke_session(session.session_id)
        store = manager._get_store("t1")
        stored = await store.get_session(session.session_id)
        assert stored is None

    async def test_revoke_session_not_found(self):
        manager = SessionLifecycleManager()
        with pytest.raises(SessionNotFoundError):
            await manager.revoke_session("nonexistent")

    async def test_refresh_activity_success(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        old_activity = session.last_activity
        # Small delay to ensure timestamp differs
        await asyncio.sleep(0.01)
        refreshed = await manager.refresh_activity(session.session_id)
        assert refreshed.last_activity >= old_activity

    async def test_refresh_activity_not_found(self):
        manager = SessionLifecycleManager()
        with pytest.raises(SessionNotFoundError):
            await manager.refresh_activity("nonexistent")

    async def test_update_session(self):
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1")
        session = await manager.create_session(config)
        session.extension_count = 99
        await manager._update_session(session)
        assert manager._sessions[session.session_id].extension_count == 99


# ============================================================================
# ConcurrencyPolicy Tests
# ============================================================================


class TestConcurrencyPolicy:
    def test_init_defaults(self):
        policy = ConcurrencyPolicy(tenant_id="t1")
        assert policy.max_sessions_per_user == 3
        assert policy.enforcement_mode == "strict"
        assert policy.eviction_strategy == "oldest_first"
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_check_concurrency_allowed(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=3)
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        await store.add_session("sid2", "u1", now)
        result = await policy.check_concurrency("u1", store)
        assert result.allowed is True
        assert result.current_count == 2
        assert result.max_allowed == 3
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_check_concurrency_denied_at_limit(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=2)
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        await store.add_session("sid2", "u1", now)
        result = await policy.check_concurrency("u1", store)
        assert result.allowed is False
        assert result.current_count == 2

    async def test_check_concurrency_no_sessions(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=3)
        store = TenantSessionStore(tenant_id="t1")
        result = await policy.check_concurrency("u1", store)
        assert result.allowed is True
        assert result.current_count == 0

    async def test_evict_session_oldest_first(self):
        policy = ConcurrencyPolicy(tenant_id="t1", eviction_strategy="oldest_first")
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        oldest = now - timedelta(hours=2)
        await store.add_session("sid_old", "u1", oldest)
        await store.add_session("sid_new", "u1", now)
        evicted = await policy.evict_session("u1", store)
        assert evicted.session_id == "sid_old"
        assert await store.get_session("sid_old") is None
        assert await store.get_session("sid_new") is not None

    async def test_evict_session_no_sessions_raises(self):
        policy = ConcurrencyPolicy(tenant_id="t1")
        store = TenantSessionStore(tenant_id="t1")
        with pytest.raises(SessionGovernanceError, match="No sessions to evict"):
            await policy.evict_session("u1", store)

    async def test_evict_session_unknown_strategy_raises(self):
        policy = ConcurrencyPolicy(tenant_id="t1", eviction_strategy="unknown_strat")
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        with pytest.raises(SessionGovernanceError, match="Unknown eviction strategy"):
            await policy.evict_session("u1", store)

    async def test_enforce_within_limit_no_raise(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=5)
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        # Should not raise
        await policy.enforce("u1", store)

    async def test_enforce_strict_exceeds_limit_raises(self):
        policy = ConcurrencyPolicy(
            tenant_id="t1", max_sessions_per_user=1, enforcement_mode="strict"
        )
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        with pytest.raises(SessionGovernanceError, match="Concurrent session limit exceeded"):
            await policy.enforce("u1", store)

    async def test_enforce_soft_mode_exceeds_limit_no_raise(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=1, enforcement_mode="soft")
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        # Should not raise in soft mode
        await policy.enforce("u1", store)

    async def test_enforce_warn_mode_exceeds_limit_no_raise(self):
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=1, enforcement_mode="warn")
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)
        await store.add_session("sid1", "u1", now)
        await policy.enforce("u1", store)


# ============================================================================
# SessionTokenManager Tests
# ============================================================================


class TestSessionTokenManager:
    def test_init_defaults(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        assert manager._private_key == TEST_PRIVATE_KEY
        assert manager.token_ttl_minutes == 60
        assert manager.refresh_token_ttl_days == 7
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH
        # JWT-based implementation: revoked JTIs stored in a set, no in-memory token cache
        assert len(manager._revoked_jtis) == 0
        assert manager._refresh_tokens == {}

    def test_init_custom_values(self):
        manager = SessionTokenManager(
            private_key=TEST_PRIVATE_KEY,
            token_ttl_minutes=30,
            refresh_token_ttl_days=14,
        )
        assert manager.token_ttl_minutes == 30
        assert manager.refresh_token_ttl_days == 14

    async def test_generate_access_token_with_roles(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        token = await manager.generate_access_token("sid1", "t1", "u1", ["admin", "viewer"])
        assert token.access_token != ""
        assert token.token_type == "Bearer"
        assert token.expires_in == 60 * 60
        assert token.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_generate_access_token_no_roles(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        token = await manager.generate_access_token("sid1", "t1", "u1")
        assert token.access_token != ""

    async def test_generate_access_token_returns_jwt(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        token = await manager.generate_access_token("sid1", "t1", "u1")
        # JWT implementation: token is a signed JWT string, not stored in memory
        assert len(token.access_token) > 20
        assert token.access_token.count(".") == 2  # header.payload.signature

    async def test_generate_refresh_token(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        token = await manager.generate_refresh_token("sid1", "t1", "u1")
        assert token.refresh_token is not None
        assert token.access_token == ""
        assert token.expires_in == 7 * 24 * 3600
        assert token.constitutional_hash == CONSTITUTIONAL_HASH
        assert token.refresh_token in manager._refresh_tokens

    async def test_validate_token_valid(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        access_token_obj = await manager.generate_access_token("sid1", "t1", "u1", ["viewer"])
        result = await manager.validate_token(access_token_obj.access_token)
        assert result.is_valid is True
        assert result.session_id == "sid1"
        assert result.tenant_id == "t1"
        assert result.user_id == "u1"
        assert result.roles == ["viewer"]
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_validate_token_revoked(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        access_token_obj = await manager.generate_access_token("sid1", "t1", "u1")
        await manager.revoke_token(access_token_obj.access_token)
        result = await manager.validate_token(access_token_obj.access_token)
        assert result.is_valid is False
        assert result.reason == "token_revoked"

    async def test_validate_token_invalid_garbage(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        result = await manager.validate_token("garbage_token_xyz")
        assert result.is_valid is False
        assert result.reason == "invalid_token"

    async def test_validate_token_expired(self):
        # JWT-based implementation: build a real expired JWT using PyJWT
        from datetime import timedelta

        import jwt as pyjwt

        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY, token_ttl_minutes=60)
        now = datetime.now(UTC)
        past = now - timedelta(hours=2)
        payload = {
            "jti": "test-jti-expired",
            "sub": "u1",
            "iss": manager._issuer,
            "aud": manager._audience,
            "iat": int(past.timestamp()),
            "exp": int(past.timestamp()),
            "session_id": "sid1",
            "tenant_id": "t1",
            "user_id": "u1",
            "roles": [],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        expired_token = pyjwt.encode(payload, manager._private_key, algorithm=manager._algorithm)
        result = await manager.validate_token(expired_token)
        assert result.is_valid is False
        assert result.reason == "token_expired"

    async def test_refresh_access_token_success(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        refresh_token_obj = await manager.generate_refresh_token("sid1", "t1", "u1")
        new_token = await manager.refresh_access_token(refresh_token_obj.refresh_token)
        assert new_token.access_token != ""

    async def test_refresh_access_token_invalid_raises(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        with pytest.raises(TokenValidationError, match="Invalid refresh token"):
            await manager.refresh_access_token("nonexistent_refresh_xyz")

    async def test_refresh_access_token_expired_raises(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        refresh_token_obj = await manager.generate_refresh_token("sid1", "t1", "u1")
        # Force expiry: _refresh_tokens["exp"] stores a Unix timestamp int
        manager._refresh_tokens[refresh_token_obj.refresh_token]["exp"] = int(
            (datetime.now(UTC) - timedelta(days=1)).timestamp()
        )
        with pytest.raises(TokenValidationError, match="Refresh token expired"):
            await manager.refresh_access_token(refresh_token_obj.refresh_token)

    async def test_revoke_token_removes_from_tokens(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        access_token_obj = await manager.generate_access_token("sid1", "t1", "u1")
        token_str = access_token_obj.access_token
        await manager.revoke_token(token_str)
        # JWT implementation: revocation stores the JTI in _revoked_jtis, not the raw token
        result = await manager.validate_token(token_str)
        assert result.is_valid is False
        assert result.reason == "token_revoked"

    async def test_revoke_nonexistent_token_no_error(self):
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        # Malformed token: revoke_token stores the raw string as fallback in _revoked_jtis
        await manager.revoke_token("nonexistent_token_xyz")
        assert "nonexistent_token_xyz" in manager._revoked_jtis


# ============================================================================
# SessionMonitor Tests
# ============================================================================


class TestSessionMonitor:
    def test_init(self):
        monitor = SessionMonitor(tenant_id="t1")
        assert monitor.tenant_id == "t1"
        assert monitor.constitutional_hash == CONSTITUTIONAL_HASH
        assert monitor._events == []
        assert monitor._active_sessions == set()

    def test_init_custom_hash(self):
        monitor = SessionMonitor(tenant_id="t1", constitutional_hash="custom")
        assert monitor.constitutional_hash == "custom"

    async def test_record_event_created_adds_to_active(self):
        monitor = SessionMonitor(tenant_id="t1")
        event = SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        await monitor.record_event(event)
        assert "sid1" in monitor._active_sessions
        assert len(monitor._events) == 1

    async def test_record_event_expired_removes_from_active(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.EXPIRED, session_id="sid1", user_id="u1")
        )
        assert "sid1" not in monitor._active_sessions
        assert len(monitor._events) == 2

    async def test_record_event_revoked_removes_from_active(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.REVOKED, session_id="sid1", user_id="u1")
        )
        assert "sid1" not in monitor._active_sessions

    async def test_record_event_activity_does_not_add_to_active(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.ACTIVITY, session_id="sid1", user_id="u1")
        )
        assert "sid1" not in monitor._active_sessions

    async def test_record_event_validated_does_not_change_active(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.VALIDATED, session_id="sid1", user_id="u1")
        )
        assert "sid1" not in monitor._active_sessions

    async def test_get_events_no_filter(self):
        monitor = SessionMonitor(tenant_id="t1")
        for i in range(3):
            await monitor.record_event(
                SessionEvent(
                    event_type=SessionEventType.CREATED, session_id=f"sid{i}", user_id="u1"
                )
            )
        events = await monitor.get_events()
        assert len(events) == 3

    async def test_get_events_filter_by_session_id(self):
        monitor = SessionMonitor(tenant_id="t1")
        for i in range(3):
            await monitor.record_event(
                SessionEvent(
                    event_type=SessionEventType.CREATED, session_id=f"sid{i}", user_id="u1"
                )
            )
        events = await monitor.get_events(session_id="sid1")
        assert len(events) == 1
        assert events[0].session_id == "sid1"

    async def test_get_events_filter_by_event_type(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.EXPIRED, session_id="sid1", user_id="u1")
        )
        events = await monitor.get_events(event_type=SessionEventType.EXPIRED)
        assert len(events) == 1
        assert events[0].event_type == SessionEventType.EXPIRED

    async def test_get_events_filter_by_start_time(self):
        monitor = SessionMonitor(tenant_id="t1")
        now = datetime.now(UTC)
        old_event = SessionEvent(
            event_type=SessionEventType.ACTIVITY,
            session_id="sid1",
            user_id="u1",
            timestamp=now - timedelta(hours=2),
        )
        recent_event = SessionEvent(
            event_type=SessionEventType.ACTIVITY,
            session_id="sid1",
            user_id="u1",
            timestamp=now,
        )
        await monitor.record_event(old_event)
        await monitor.record_event(recent_event)
        events = await monitor.get_events(start_time=now - timedelta(minutes=30))
        assert len(events) == 1

    async def test_get_events_filter_by_end_time(self):
        monitor = SessionMonitor(tenant_id="t1")
        now = datetime.now(UTC)
        old_event = SessionEvent(
            event_type=SessionEventType.ACTIVITY,
            session_id="sid1",
            user_id="u1",
            timestamp=now - timedelta(hours=2),
        )
        recent_event = SessionEvent(
            event_type=SessionEventType.ACTIVITY,
            session_id="sid1",
            user_id="u1",
            timestamp=now,
        )
        await monitor.record_event(old_event)
        await monitor.record_event(recent_event)
        events = await monitor.get_events(end_time=now - timedelta(hours=1))
        assert len(events) == 1

    async def test_get_events_combined_filters(self):
        monitor = SessionMonitor(tenant_id="t1")
        now = datetime.now(UTC)
        await monitor.record_event(
            SessionEvent(
                event_type=SessionEventType.CREATED,
                session_id="sid1",
                user_id="u1",
                timestamp=now - timedelta(minutes=5),
            )
        )
        await monitor.record_event(
            SessionEvent(
                event_type=SessionEventType.ACTIVITY,
                session_id="sid1",
                user_id="u1",
                timestamp=now - timedelta(minutes=3),
            )
        )
        await monitor.record_event(
            SessionEvent(
                event_type=SessionEventType.CREATED,
                session_id="sid2",
                user_id="u2",
                timestamp=now - timedelta(minutes=2),
            )
        )
        events = await monitor.get_events(
            session_id="sid1",
            event_type=SessionEventType.CREATED,
        )
        assert len(events) == 1

    async def test_get_active_session_count_zero(self):
        monitor = SessionMonitor(tenant_id="t1")
        assert await monitor.get_active_session_count() == 0

    async def test_get_active_session_count_nonzero(self):
        monitor = SessionMonitor(tenant_id="t1")
        for i in range(4):
            await monitor.record_event(
                SessionEvent(
                    event_type=SessionEventType.CREATED, session_id=f"sid{i}", user_id="u1"
                )
            )
        assert await monitor.get_active_session_count() == 4

    async def test_get_analytics_periods(self):
        monitor = SessionMonitor(tenant_id="t1")
        now = datetime.now(UTC)
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.EXPIRED, session_id="sid2", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.REVOKED, session_id="sid3", user_id="u1")
        )
        analytics = await monitor.get_analytics(start, end)
        assert analytics.tenant_id == "t1"
        assert analytics.total_sessions == 1
        assert analytics.expired_sessions == 1
        assert analytics.revoked_sessions == 1
        assert analytics.active_sessions == 1  # sid1 is in _active_sessions
        assert analytics.period_start == start
        assert analytics.period_end == end
        assert analytics.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_get_user_session_history(self):
        monitor = SessionMonitor(tenant_id="t1")
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.ACTIVITY, session_id="sid1", user_id="u1")
        )
        await monitor.record_event(
            SessionEvent(event_type=SessionEventType.CREATED, session_id="sid2", user_id="u2")
        )
        history = await monitor.get_user_session_history("u1")
        assert len(history) == 2
        assert all(e.user_id == "u1" for e in history)

    async def test_get_user_session_history_empty(self):
        monitor = SessionMonitor(tenant_id="t1")
        history = await monitor.get_user_session_history("unknown_user")
        assert history == []


# ============================================================================
# SessionGovernanceClient Tests
# ============================================================================


class TestSessionGovernanceClient:
    def test_init_strips_trailing_slash(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com/",
            api_key="key123",
            tenant_id="t1",
        )
        assert client.base_url == "https://api.example.com"

    def test_init_no_trailing_slash(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com",
            api_key="key123",
            tenant_id="t1",
        )
        assert client.base_url == "https://api.example.com"

    def test_init_defaults(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com",
            api_key="k",
            tenant_id="t1",
        )
        assert client.max_retries == 3
        assert client.constitutional_hash == CONSTITUTIONAL_HASH

    def test_init_custom_retries(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com",
            api_key="k",
            tenant_id="t1",
            max_retries=5,
        )
        assert client.max_retries == 5

    async def test_make_request_raises_not_implemented(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        with pytest.raises(NotImplementedError):
            await client._make_request("GET", "/test")

    async def test_request_succeeds_first_attempt(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        expected = {"status": "ok"}
        client._make_request = AsyncMock(return_value=expected)
        result = await client._request("GET", "/test")
        assert result == expected
        client._make_request.assert_called_once()

    async def test_request_with_data(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        expected = {"created": True}
        client._make_request = AsyncMock(return_value=expected)
        result = await client._request("POST", "/test", {"foo": "bar"})
        assert result == expected
        client._make_request.assert_called_once_with("POST", "/test", {"foo": "bar"})

    async def test_request_retries_on_connection_error(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1", max_retries=3
        )
        call_count = 0

        async def mock_req(method, path, data=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("refused")
            return {"ok": True}

        client._make_request = mock_req
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("GET", "/test")
        assert result == {"ok": True}
        assert call_count == 3

    async def test_request_exhausts_retries_raises(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1", max_retries=2
        )
        client._make_request = AsyncMock(side_effect=ConnectionError("always fails"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ConnectionError):
                await client._request("GET", "/test")

    async def test_create_session_with_metadata(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        expected = {"session_id": "new_sid"}
        client._make_request = AsyncMock(return_value=expected)
        result = await client.create_session("u1", {"role": "admin"})
        assert result == expected
        client._make_request.assert_called_once_with(
            "POST",
            "/tenants/t1/sessions",
            {"user_id": "u1", "metadata": {"role": "admin"}},
        )

    async def test_create_session_no_metadata(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        client._make_request = AsyncMock(return_value={})
        await client.create_session("u1")
        client._make_request.assert_called_once_with(
            "POST",
            "/tenants/t1/sessions",
            {"user_id": "u1", "metadata": {}},
        )

    async def test_validate_session_calls_correct_path(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        expected = {"is_valid": True}
        client._make_request = AsyncMock(return_value=expected)
        result = await client.validate_session("sid1")
        assert result == expected
        client._make_request.assert_called_once_with(
            "GET",
            "/tenants/t1/sessions/sid1/validate",
            None,
        )

    async def test_revoke_session_with_reason(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        client._make_request = AsyncMock(return_value={})
        await client.revoke_session("sid1", "admin_kick")
        client._make_request.assert_called_once_with(
            "DELETE",
            "/tenants/t1/sessions/sid1",
            {"reason": "admin_kick"},
        )

    async def test_revoke_session_default_reason(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        client._make_request = AsyncMock(return_value={})
        await client.revoke_session("sid1")
        client._make_request.assert_called_once_with(
            "DELETE",
            "/tenants/t1/sessions/sid1",
            {"reason": "user_logout"},
        )

    async def test_extend_session_custom_minutes(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        client._make_request = AsyncMock(return_value={})
        await client.extend_session("sid1", 45)
        client._make_request.assert_called_once_with(
            "POST",
            "/tenants/t1/sessions/sid1/extend",
            {"extension_minutes": 45},
        )

    async def test_extend_session_default_minutes(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        client._make_request = AsyncMock(return_value={})
        await client.extend_session("sid1")
        client._make_request.assert_called_once_with(
            "POST",
            "/tenants/t1/sessions/sid1/extend",
            {"extension_minutes": 30},
        )

    async def test_get_analytics_correct_params(self):
        client = SessionGovernanceClient(
            base_url="https://api.example.com", api_key="k", tenant_id="t1"
        )
        now = datetime.now(UTC)
        start = now - timedelta(hours=1)
        end = now
        expected = {"total": 10}
        client._make_request = AsyncMock(return_value=expected)
        result = await client.get_analytics(start, end)
        assert result == expected
        client._make_request.assert_called_once_with(
            "GET",
            "/tenants/t1/sessions/analytics",
            {"start_time": start.isoformat(), "end_time": end.isoformat()},
        )


# ============================================================================
# Integration-style Tests
# ============================================================================


class TestSessionLifecycleIntegration:
    async def test_full_session_lifecycle(self):
        """Create -> validate -> extend -> revoke."""
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1", max_duration_minutes=60)

        session = await manager.create_session(config)
        assert session.state == SessionState.ACTIVE

        result = await manager.validate_session(session.session_id)
        assert result.is_valid is True

        extended = await manager.extend_session(session.session_id, 30)
        assert extended.extension_count == 1

        revoked = await manager.revoke_session(session.session_id)
        assert revoked.state == SessionState.REVOKED

        result2 = await manager.validate_session(session.session_id)
        assert result2.is_valid is False
        assert result2.reason == "session_revoked"

    async def test_token_full_lifecycle(self):
        """Generate access token -> validate -> revoke -> validate again."""
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        token_obj = await manager.generate_access_token("sid1", "t1", "u1", ["admin"])

        result = await manager.validate_token(token_obj.access_token)
        assert result.is_valid is True
        assert result.roles == ["admin"]

        await manager.revoke_token(token_obj.access_token)
        result2 = await manager.validate_token(token_obj.access_token)
        assert result2.is_valid is False
        assert result2.reason == "token_revoked"

    async def test_refresh_token_lifecycle(self):
        """Generate refresh token -> use it -> expired refresh raises."""
        manager = SessionTokenManager(private_key=TEST_PRIVATE_KEY)
        refresh_obj = await manager.generate_refresh_token("sid1", "t1", "u1")
        new_access = await manager.refresh_access_token(refresh_obj.refresh_token)
        assert new_access.access_token != ""

    async def test_monitor_full_flow(self):
        """Record multiple event types and verify analytics."""
        monitor = SessionMonitor(tenant_id="t1")
        now = datetime.now(UTC)

        for i in range(5):
            await monitor.record_event(
                SessionEvent(
                    event_type=SessionEventType.CREATED,
                    session_id=f"sid{i}",
                    user_id="u1",
                )
            )

        for i in range(2):
            await monitor.record_event(
                SessionEvent(
                    event_type=SessionEventType.EXPIRED,
                    session_id=f"sid{i}",
                    user_id="u1",
                )
            )

        assert await monitor.get_active_session_count() == 3

        analytics = await monitor.get_analytics(
            now - timedelta(minutes=1), now + timedelta(minutes=1)
        )
        assert analytics.total_sessions == 5
        assert analytics.expired_sessions == 2

    async def test_tenant_store_isolation(self):
        """Different tenants have isolated stores."""
        store1 = TenantSessionStore(tenant_id="t1")
        store2 = TenantSessionStore(tenant_id="t2")
        now = datetime.now(UTC)
        await store1.add_session("sid1", "u1", now)
        assert await store2.get_session("sid1") is None

    async def test_concurrency_policy_with_store(self):
        """Full concurrency check flow."""
        policy = ConcurrencyPolicy(tenant_id="t1", max_sessions_per_user=2)
        store = TenantSessionStore(tenant_id="t1")
        now = datetime.now(UTC)

        result = await policy.check_concurrency("u1", store)
        assert result.allowed is True

        await store.add_session("sid1", "u1", now)
        result = await policy.check_concurrency("u1", store)
        assert result.allowed is True

        await store.add_session("sid2", "u1", now)
        result = await policy.check_concurrency("u1", store)
        assert result.allowed is False

    async def test_multiple_sessions_different_users(self):
        """Multiple users, each with multiple sessions."""
        manager = SessionLifecycleManager()
        sessions = []
        for uid in ["u1", "u2", "u3"]:
            for _ in range(2):
                config = SessionConfig(tenant_id="t1", user_id=uid)
                s = await manager.create_session(config)
                sessions.append(s)

        store = manager._get_store("t1")
        u1_sessions = await store.list_user_sessions("u1")
        assert len(u1_sessions) == 2

    async def test_session_idle_timeout_uses_config(self):
        """Different idle_timeout_minutes values affect validation."""
        manager = SessionLifecycleManager()
        config_short = SessionConfig(tenant_id="t1", user_id="u1", idle_timeout_minutes=5)
        session = await manager.create_session(config_short)
        # Activity 6 minutes ago → should be idle
        session.last_activity = datetime.now(UTC) - timedelta(minutes=6)
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is False
        assert result.reason == "idle_timeout"

    async def test_session_idle_timeout_just_under(self):
        """Activity just within idle timeout boundary should be valid."""
        manager = SessionLifecycleManager()
        config = SessionConfig(tenant_id="t1", user_id="u1", idle_timeout_minutes=30)
        session = await manager.create_session(config)
        # Activity 25 minutes ago → should still be valid
        session.last_activity = datetime.now(UTC) - timedelta(minutes=25)
        result = await manager.validate_session(session.session_id)
        assert result.is_valid is True
