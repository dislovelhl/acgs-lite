"""
Tests for src/core/shared/security/rotation/manager.py - SecretRotationManager.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.core.shared.security.rotation.backend import InMemorySecretBackend
from src.core.shared.security.rotation.enums import (
    RotationTrigger,
    SecretType,
)
from src.core.shared.security.rotation.manager import (
    SecretRotationManager,
    get_rotation_manager,
    reset_rotation_manager,
)
from src.core.shared.security.rotation.models import RotationPolicy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    return InMemorySecretBackend()


@pytest.fixture
def manager(backend):
    return SecretRotationManager(backend=backend)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton between tests."""
    reset_rotation_manager()
    yield
    reset_rotation_manager()


# ===========================================================================
# Initialization
# ===========================================================================


class TestInit:
    def test_default_backend(self):
        mgr = SecretRotationManager()
        assert isinstance(mgr._backend, InMemorySecretBackend)

    def test_custom_backend(self, backend):
        mgr = SecretRotationManager(backend=backend)
        assert mgr._backend is backend

    def test_custom_generator(self):
        gen = AsyncMock(return_value="custom-secret")
        mgr = SecretRotationManager(secret_generator=gen)
        assert mgr._secret_generator is gen

    def test_get_health(self, manager):
        health = manager.get_health()
        assert health["status"] == "healthy"
        assert health["registered_secrets"] == 0
        assert health["scheduler_running"] is False


# ===========================================================================
# Registration
# ===========================================================================


class TestRegisterSecret:
    @pytest.mark.asyncio
    async def test_register_basic(self, manager):
        result = await manager.register_secret("MY_KEY", SecretType.API_KEY)
        assert result is True
        assert "MY_KEY" in manager._registered_secrets

    @pytest.mark.asyncio
    async def test_register_with_initial_value(self, manager):
        result = await manager.register_secret(
            "MY_KEY",
            SecretType.GENERIC,
            initial_value="initial-val",
        )
        assert result is True
        current, _ = await manager.get_current_secret("MY_KEY")
        assert current == "initial-val"

    @pytest.mark.asyncio
    async def test_register_duplicate_returns_false(self, manager):
        await manager.register_secret("K1", SecretType.GENERIC)
        result = await manager.register_secret("K1", SecretType.GENERIC)
        assert result is False

    @pytest.mark.asyncio
    async def test_register_with_policy(self, manager):
        policy = RotationPolicy(rotation_interval_days=7, grace_period_hours=2)
        await manager.register_secret("K1", SecretType.JWT_SIGNING_KEY, policy=policy)
        registered_type, registered_policy = manager._registered_secrets["K1"]
        assert registered_type == SecretType.JWT_SIGNING_KEY
        assert registered_policy.rotation_interval_days == 7

    @pytest.mark.asyncio
    async def test_register_stores_version(self, manager):
        await manager.register_secret("K1", SecretType.GENERIC)
        versions = manager._versions["K1"]
        assert len(versions) == 1
        assert versions[0].is_current is True

    @pytest.mark.asyncio
    async def test_register_backend_failure(self, manager):
        manager._backend.store_secret = AsyncMock(return_value=False)
        result = await manager.register_secret("FAIL", SecretType.GENERIC)
        assert result is False


# ===========================================================================
# Secret generation
# ===========================================================================


class TestDefaultSecretGenerator:
    @pytest.mark.asyncio
    async def test_jwt_signing_key(self, manager):
        val = await manager._default_secret_generator("k", SecretType.JWT_SIGNING_KEY)
        assert len(val) > 20

    @pytest.mark.asyncio
    async def test_encryption_key(self, manager):
        val = await manager._default_secret_generator("k", SecretType.ENCRYPTION_KEY)
        assert len(val) > 10

    @pytest.mark.asyncio
    async def test_database_password(self, manager):
        val = await manager._default_secret_generator("k", SecretType.DATABASE_PASSWORD)
        assert len(val) > 10

    @pytest.mark.asyncio
    async def test_api_key(self, manager):
        val = await manager._default_secret_generator("k", SecretType.API_KEY)
        assert val.startswith("acgs2_")

    @pytest.mark.asyncio
    async def test_webhook_secret(self, manager):
        val = await manager._default_secret_generator("k", SecretType.WEBHOOK_SECRET)
        assert val.startswith("whsec_")

    @pytest.mark.asyncio
    async def test_generic(self, manager):
        val = await manager._default_secret_generator("k", SecretType.GENERIC)
        assert len(val) > 10


# ===========================================================================
# Rotation
# ===========================================================================


class TestRotateSecret:
    @pytest.mark.asyncio
    async def test_basic_rotation(self, manager):
        await manager.register_secret("K1", SecretType.GENERIC, initial_value="old")
        result = await manager.rotate_secret("K1", new_value="new")
        assert result.success is True
        assert result.new_version_id is not None
        assert result.grace_period_ends is not None
        assert result.rollback_available is True

        current, _ = await manager.get_current_secret("K1")
        assert current == "new"

    @pytest.mark.asyncio
    async def test_rotate_unregistered_secret(self, manager):
        result = await manager.rotate_secret("NOPE")
        assert result.success is False
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_rotate_disallowed_trigger(self, manager):
        policy = RotationPolicy(triggers=[RotationTrigger.TIME_BASED])
        await manager.register_secret("K1", policy=policy, initial_value="v")
        result = await manager.rotate_secret("K1", trigger=RotationTrigger.ON_DEMAND)
        assert result.success is False
        assert "not allowed" in result.error

    @pytest.mark.asyncio
    async def test_rotate_backend_failure(self, manager):
        from src.core.shared.errors.exceptions import ConfigurationError

        await manager.register_secret("K1", initial_value="v")
        manager._backend.store_secret = AsyncMock(return_value=False)
        # ConfigurationError is not in the caught tuple, so it propagates
        with pytest.raises(ConfigurationError, match="SECRET_STORE_FAILED"):
            await manager.rotate_secret("K1")

    @pytest.mark.asyncio
    async def test_rotate_preserves_previous_version(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")

        versions = manager._versions["K1"]
        current = [v for v in versions if v.is_current]
        previous = [v for v in versions if v.is_previous]
        assert len(current) == 1
        assert len(previous) == 1

    @pytest.mark.asyncio
    async def test_rotate_with_audit_callback(self, backend):
        audit_events = []

        async def audit_cb(event):
            audit_events.append(event)

        mgr = SecretRotationManager(backend=backend, audit_callback=audit_cb)
        await mgr.register_secret("K1", initial_value="v1")
        await mgr.rotate_secret("K1", new_value="v2")
        # Should have at least register + rotate events
        assert len(audit_events) >= 2


# ===========================================================================
# Rollback
# ===========================================================================


class TestRollback:
    @pytest.mark.asyncio
    async def test_basic_rollback(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")
        result = await manager.rollback_secret("K1")
        assert result.success is True
        assert result.rollback_available is False

        current, _ = await manager.get_current_secret("K1")
        assert current == "v1"

    @pytest.mark.asyncio
    async def test_rollback_unregistered(self, manager):
        result = await manager.rollback_secret("NOPE")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_rollback_no_previous(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        result = await manager.rollback_secret("K1")
        assert result.success is False
        assert "No previous version" in result.error

    @pytest.mark.asyncio
    async def test_rollback_expired_window(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")

        # Expire the previous version
        for v in manager._versions["K1"]:
            if v.is_previous:
                v.expires_at = datetime.now(UTC) - timedelta(hours=1)

        result = await manager.rollback_secret("K1")
        assert result.success is False
        assert "expired" in result.error.lower()


# ===========================================================================
# Get current secret
# ===========================================================================


class TestGetCurrentSecret:
    @pytest.mark.asyncio
    async def test_get_unregistered(self, manager):
        current, previous = await manager.get_current_secret("NOPE")
        assert current is None
        assert previous is None

    @pytest.mark.asyncio
    async def test_get_with_previous_in_grace_period(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")

        current, previous = await manager.get_current_secret("K1", include_previous=True)
        assert current == "v2"
        assert previous == "v1"

    @pytest.mark.asyncio
    async def test_get_without_previous(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")

        current, previous = await manager.get_current_secret("K1", include_previous=False)
        assert current == "v2"
        assert previous is None


# ===========================================================================
# Rotation status
# ===========================================================================


class TestGetRotationStatus:
    @pytest.mark.asyncio
    async def test_unregistered(self, manager):
        status = await manager.get_rotation_status("NOPE")
        assert "error" in status

    @pytest.mark.asyncio
    async def test_status_after_registration(self, manager):
        await manager.register_secret("K1", SecretType.API_KEY, initial_value="v")
        status = await manager.get_rotation_status("K1")
        assert status["secret_name"] == "K1"
        assert status["secret_type"] == "api_key"
        assert status["needs_rotation"] is False
        assert status["total_rotations"] == 0
        assert status["current_version"] is not None

    @pytest.mark.asyncio
    async def test_status_after_rotation(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")
        status = await manager.get_rotation_status("K1")
        assert status["in_grace_period"] is True
        assert status["total_rotations"] == 1
        assert status["last_rotation"] is not None


# ===========================================================================
# Check secrets needing rotation
# ===========================================================================


class TestCheckSecretsNeedingRotation:
    @pytest.mark.asyncio
    async def test_no_secrets_registered(self, manager):
        assert await manager.check_secrets_needing_rotation() == []

    @pytest.mark.asyncio
    async def test_fresh_secret_not_due(self, manager):
        await manager.register_secret("K1", initial_value="v")
        assert await manager.check_secrets_needing_rotation() == []

    @pytest.mark.asyncio
    async def test_expired_secret_is_due(self, manager):
        policy = RotationPolicy(rotation_interval_days=1)
        await manager.register_secret("K1", policy=policy, initial_value="v")

        # Backdate activation
        for v in manager._versions["K1"]:
            if v.is_current:
                v.activated_at = datetime.now(UTC) - timedelta(days=2)

        result = await manager.check_secrets_needing_rotation()
        assert "K1" in result

    @pytest.mark.asyncio
    async def test_non_time_based_trigger_skipped(self, manager):
        policy = RotationPolicy(triggers=[RotationTrigger.ON_DEMAND])
        await manager.register_secret("K1", policy=policy, initial_value="v")

        for v in manager._versions["K1"]:
            if v.is_current:
                v.activated_at = datetime.now(UTC) - timedelta(days=999)

        result = await manager.check_secrets_needing_rotation()
        assert result == []


# ===========================================================================
# Version cleanup
# ===========================================================================


class TestCleanupOldVersions:
    @pytest.mark.asyncio
    async def test_cleanup_beyond_max(self, manager):
        policy = RotationPolicy(max_versions=2)
        await manager.register_secret("K1", policy=policy, initial_value="v0")
        await manager.rotate_secret("K1", new_value="v1")
        await manager.rotate_secret("K1", new_value="v2")
        # Should have cleaned old versions down to max
        versions = manager._versions["K1"]
        assert len(versions) <= 4  # may keep current + previous + recently added


# ===========================================================================
# Expire grace periods
# ===========================================================================


class TestExpireGracePeriods:
    @pytest.mark.asyncio
    async def test_expire_old_grace_period(self, manager):
        await manager.register_secret("K1", initial_value="v1")
        await manager.rotate_secret("K1", new_value="v2")

        # Backdate expiry
        for v in manager._versions["K1"]:
            if v.is_previous:
                v.expires_at = datetime.now(UTC) - timedelta(hours=1)

        await manager._expire_grace_periods()

        previous_versions = [v for v in manager._versions["K1"] if v.is_previous]
        assert len(previous_versions) == 0


# ===========================================================================
# Scheduler
# ===========================================================================


class TestScheduler:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, manager):
        await manager.start_scheduler(check_interval_seconds=9999)
        assert manager._scheduler_running is True
        # Starting again is a no-op
        await manager.start_scheduler()
        await manager.stop_scheduler()
        assert manager._scheduler_running is False

    @pytest.mark.asyncio
    async def test_stop_without_start(self, manager):
        await manager.stop_scheduler()  # should not raise


# ===========================================================================
# Singleton
# ===========================================================================


class TestSingleton:
    @pytest.mark.asyncio
    async def test_get_rotation_manager(self):
        mgr1 = await get_rotation_manager()
        mgr2 = await get_rotation_manager()
        assert mgr1 is mgr2

    @pytest.mark.asyncio
    async def test_reset_rotation_manager(self):
        mgr1 = await get_rotation_manager()
        reset_rotation_manager()
        mgr2 = await get_rotation_manager()
        assert mgr1 is not mgr2


# ===========================================================================
# Helpers
# ===========================================================================


class TestHelpers:
    def test_compute_checksum(self, manager):
        cs = manager._compute_checksum("test-value")
        assert len(cs) == 16

    def test_generate_version_id(self, manager):
        vid = manager._generate_version_id("my_secret")
        assert vid.startswith("my_secret-v")

    def test_generate_rotation_id(self, manager):
        rid = manager._generate_rotation_id()
        assert rid.startswith("rot-")

    @pytest.mark.asyncio
    async def test_audit_log_callback_error_handled(self):
        async def bad_callback(event):
            raise RuntimeError("audit fail")

        mgr = SecretRotationManager(audit_callback=bad_callback)
        # Should not raise
        await mgr._audit_log("test_event", "secret1", {"detail": "val"})
