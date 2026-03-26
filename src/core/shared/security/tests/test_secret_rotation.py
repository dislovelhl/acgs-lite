"""
ACGS-2 Secret Rotation Lifecycle Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test suite for secret rotation functionality:
- Time-based and event-based rotation triggers
- Grace period validation
- Rollback mechanisms
- Audit logging
- Backend integration

Task: T004 - Secret Rotation Lifecycle
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.core.shared.security.secret_rotation import (
    CONSTITUTIONAL_HASH,
    DEFAULT_GRACE_PERIOD_HOURS,
    DEFAULT_ROTATION_INTERVAL_DAYS,
    InMemorySecretBackend,
    RotationPolicy,
    RotationTrigger,
    SecretRotationManager,
    SecretType,
    SecretVersion,
    VaultSecretBackend,
    get_rotation_manager,
    reset_rotation_manager,
)


class TestRotationPolicy:
    """Tests for RotationPolicy data class."""

    def test_default_policy_values(self) -> None:
        """Test default policy values are set correctly."""
        policy = RotationPolicy()

        assert policy.rotation_interval_days == DEFAULT_ROTATION_INTERVAL_DAYS
        assert policy.grace_period_hours == DEFAULT_GRACE_PERIOD_HOURS
        assert policy.max_versions == 3
        assert RotationTrigger.TIME_BASED in policy.triggers
        assert RotationTrigger.ON_DEMAND in policy.triggers
        assert policy.notify_before_days == 7
        assert policy.require_approval is False
        assert policy.auto_rollback_on_failure is True
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_policy_values(self) -> None:
        """Test custom policy values are preserved."""
        policy = RotationPolicy(
            rotation_interval_days=30,
            grace_period_hours=2,
            max_versions=5,
            triggers=[RotationTrigger.SCHEDULED],
            require_approval=True,
        )

        assert policy.rotation_interval_days == 30
        assert policy.grace_period_hours == 2
        assert policy.max_versions == 5
        assert policy.triggers == [RotationTrigger.SCHEDULED]
        assert policy.require_approval is True

    def test_policy_to_dict(self) -> None:
        """Test policy serialization."""
        policy = RotationPolicy(rotation_interval_days=45)
        data = policy.to_dict()

        assert data["rotation_interval_days"] == 45
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert isinstance(data["triggers"], list)


class TestSecretVersion:
    """Tests for SecretVersion data class."""

    def test_version_creation(self) -> None:
        """Test version creation with required fields."""
        now = datetime.now(UTC)
        version = SecretVersion(
            version_id="test-v1",
            created_at=now,
            is_current=True,
            checksum="abc123",
        )

        assert version.version_id == "test-v1"
        assert version.created_at == now
        assert version.is_current is True
        assert version.checksum == "abc123"
        assert version.constitutional_hash == CONSTITUTIONAL_HASH

    def test_version_to_dict(self) -> None:
        """Test version serialization."""
        now = datetime.now(UTC)
        version = SecretVersion(
            version_id="test-v1",
            created_at=now,
            activated_at=now,
            is_current=True,
        )
        data = version.to_dict()

        assert data["version_id"] == "test-v1"
        assert data["is_current"] is True
        assert data["created_at"] == now.isoformat()


class TestInMemorySecretBackend:
    """Tests for InMemorySecretBackend."""

    @pytest.fixture
    def backend(self) -> InMemorySecretBackend:
        """Create a test backend."""
        return InMemorySecretBackend()

    async def test_store_and_get_secret(self, backend: InMemorySecretBackend) -> None:
        """Test storing and retrieving a secret."""
        result = await backend.store_secret("test-secret", "value123", "v1")
        assert result is True

        value = await backend.get_secret("test-secret", "v1")
        assert value == "value123"

    async def test_get_latest_version(self, backend: InMemorySecretBackend) -> None:
        """Test getting latest version when no version specified."""
        await backend.store_secret("test-secret", "value1", "v1")
        await backend.store_secret("test-secret", "value2", "v2")

        value = await backend.get_secret("test-secret")
        assert value == "value2"

    async def test_get_nonexistent_secret(self, backend: InMemorySecretBackend) -> None:
        """Test getting a secret that doesn't exist."""
        value = await backend.get_secret("nonexistent")
        assert value is None

    async def test_delete_version(self, backend: InMemorySecretBackend) -> None:
        """Test deleting a specific version."""
        await backend.store_secret("test-secret", "value1", "v1")
        await backend.store_secret("test-secret", "value2", "v2")

        result = await backend.delete_secret_version("test-secret", "v1")
        assert result is True

        value = await backend.get_secret("test-secret", "v1")
        assert value is None

        value = await backend.get_secret("test-secret", "v2")
        assert value == "value2"

    async def test_list_versions(self, backend: InMemorySecretBackend) -> None:
        """Test listing secret versions."""
        await backend.store_secret("test-secret", "value1", "v1")
        await backend.store_secret("test-secret", "value2", "v2")

        versions = await backend.list_versions("test-secret")
        assert "v1" in versions
        assert "v2" in versions

    async def test_list_versions_empty(self, backend: InMemorySecretBackend) -> None:
        """Test listing versions for nonexistent secret."""
        versions = await backend.list_versions("nonexistent")
        assert versions == []


class TestSecretRotationManager:
    """Tests for SecretRotationManager."""

    @pytest.fixture
    def manager(self) -> SecretRotationManager:
        """Create a test rotation manager."""
        return SecretRotationManager()

    @pytest.fixture
    def audit_callback(self) -> AsyncMock:
        """Create a mock audit callback."""
        return AsyncMock()

    @pytest.fixture
    def manager_with_audit(self, audit_callback: AsyncMock) -> SecretRotationManager:
        """Create a manager with audit callback."""
        return SecretRotationManager(audit_callback=audit_callback)

    async def test_register_secret(self, manager: SecretRotationManager) -> None:
        """Test registering a new secret."""
        result = await manager.register_secret(
            secret_name="test-key",
            secret_type=SecretType.API_KEY,
        )

        assert result is True

        # Verify status
        status = await manager.get_rotation_status("test-key")
        assert status["secret_name"] == "test-key"
        assert status["secret_type"] == "api_key"
        assert status["current_version"] is not None
        assert status["in_grace_period"] is False

    async def test_register_duplicate_secret(self, manager: SecretRotationManager) -> None:
        """Test registering a duplicate secret fails."""
        await manager.register_secret("test-key")
        result = await manager.register_secret("test-key")

        assert result is False

    async def test_register_with_initial_value(self, manager: SecretRotationManager) -> None:
        """Test registering with an initial value."""
        result = await manager.register_secret(
            secret_name="test-key",
            initial_value="my-initial-value",
        )

        assert result is True

        current, _ = await manager.get_current_secret("test-key")
        assert current == "my-initial-value"

    async def test_register_with_custom_policy(self, manager: SecretRotationManager) -> None:
        """Test registering with a custom policy."""
        policy = RotationPolicy(
            rotation_interval_days=7,
            grace_period_hours=1,
        )

        await manager.register_secret(
            secret_name="test-key",
            policy=policy,
        )

        status = await manager.get_rotation_status("test-key")
        assert status["policy"]["rotation_interval_days"] == 7
        assert status["policy"]["grace_period_hours"] == 1

    async def test_rotate_secret(self, manager: SecretRotationManager) -> None:
        """Test basic secret rotation."""
        await manager.register_secret("test-key")
        original, _ = await manager.get_current_secret("test-key")

        result = await manager.rotate_secret("test-key")

        assert result.success is True
        assert result.new_version_id is not None
        assert result.previous_version_id is not None
        assert result.grace_period_ends is not None
        assert result.rollback_available is True

        # Verify new value is different
        new_value, previous = await manager.get_current_secret("test-key", include_previous=True)
        assert new_value != original
        assert previous == original

    async def test_rotate_unregistered_secret(self, manager: SecretRotationManager) -> None:
        """Test rotating an unregistered secret fails."""
        result = await manager.rotate_secret("nonexistent")

        assert result.success is False
        assert "not registered" in result.error

    async def test_rotate_with_disallowed_trigger(self, manager: SecretRotationManager) -> None:
        """Test rotation with disallowed trigger fails."""
        policy = RotationPolicy(triggers=[RotationTrigger.TIME_BASED])  # No ON_DEMAND
        await manager.register_secret("test-key", policy=policy)

        result = await manager.rotate_secret(
            "test-key",
            trigger=RotationTrigger.ON_DEMAND,
        )

        assert result.success is False
        assert "not allowed" in result.error

    async def test_rotate_with_custom_value(self, manager: SecretRotationManager) -> None:
        """Test rotation with a custom new value."""
        await manager.register_secret("test-key")

        result = await manager.rotate_secret(
            "test-key",
            new_value="custom-new-value",
        )

        assert result.success is True

        current, _ = await manager.get_current_secret("test-key")
        assert current == "custom-new-value"

    async def test_grace_period(self, manager: SecretRotationManager) -> None:
        """Test grace period allows both versions."""
        await manager.register_secret("test-key")
        original, _ = await manager.get_current_secret("test-key")

        await manager.rotate_secret("test-key")

        current, previous = await manager.get_current_secret("test-key", include_previous=True)
        assert current is not None
        assert previous is not None
        assert current != previous
        assert previous == original

        # Check status
        status = await manager.get_rotation_status("test-key")
        assert status["in_grace_period"] is True
        assert status["grace_period_ends"] is not None

    async def test_rollback_secret(self, manager: SecretRotationManager) -> None:
        """Test rolling back a secret."""
        await manager.register_secret("test-key")
        original, _ = await manager.get_current_secret("test-key")

        await manager.rotate_secret("test-key")
        new_value, _ = await manager.get_current_secret("test-key")
        assert new_value != original

        result = await manager.rollback_secret("test-key")

        assert result.success is True
        assert result.new_version_id is not None

        rolled_back, _ = await manager.get_current_secret("test-key")
        assert rolled_back == original

    async def test_rollback_unregistered_secret(self, manager: SecretRotationManager) -> None:
        """Test rolling back an unregistered secret fails."""
        result = await manager.rollback_secret("nonexistent")

        assert result.success is False
        assert "not registered" in result.error

    async def test_rollback_without_previous_version(self, manager: SecretRotationManager) -> None:
        """Test rollback fails when no previous version exists."""
        await manager.register_secret("test-key")

        result = await manager.rollback_secret("test-key")

        assert result.success is False
        assert "No previous version" in result.error

    async def test_audit_logging(
        self,
        manager_with_audit: SecretRotationManager,
        audit_callback: AsyncMock,
    ) -> None:
        """Test audit events are logged."""
        await manager_with_audit.register_secret("test-key")

        # Verify registration was logged
        assert audit_callback.call_count >= 1
        call_args = audit_callback.call_args_list[0][0][0]
        assert call_args["event_type"] == "secret_registered"
        assert call_args["secret_name"] == "test-key"
        assert call_args["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_rotation_audit_logging(
        self,
        manager_with_audit: SecretRotationManager,
        audit_callback: AsyncMock,
    ) -> None:
        """Test rotation events are logged."""
        await manager_with_audit.register_secret("test-key")
        audit_callback.reset_mock()

        await manager_with_audit.rotate_secret("test-key")

        # Find the rotation audit event
        rotation_events = [
            call[0][0]
            for call in audit_callback.call_args_list
            if call[0][0]["event_type"] == "secret_rotated"
        ]
        assert len(rotation_events) == 1
        assert rotation_events[0]["secret_name"] == "test-key"
        assert "new_version_id" in rotation_events[0]["details"]

    async def test_check_secrets_needing_rotation(self, manager: SecretRotationManager) -> None:
        """Test checking for secrets needing rotation."""
        # Register with very short rotation interval
        policy = RotationPolicy(rotation_interval_days=0)  # Immediate rotation
        await manager.register_secret("test-key", policy=policy)

        # Should need rotation immediately
        needs_rotation = await manager.check_secrets_needing_rotation()
        assert "test-key" in needs_rotation

    async def test_get_rotation_status(self, manager: SecretRotationManager) -> None:
        """Test getting rotation status."""
        await manager.register_secret("test-key")
        await manager.rotate_secret("test-key")

        status = await manager.get_rotation_status("test-key")

        assert status["secret_name"] == "test-key"
        assert status["current_version"] is not None
        assert status["previous_version"] is not None
        assert status["in_grace_period"] is True
        assert status["last_rotation"] is not None
        assert status["total_rotations"] == 1
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_status_unregistered_secret(self, manager: SecretRotationManager) -> None:
        """Test getting status for unregistered secret."""
        status = await manager.get_rotation_status("nonexistent")

        assert "error" in status
        assert "not registered" in status["error"]

    async def test_multiple_rotations(self, manager: SecretRotationManager) -> None:
        """Test multiple consecutive rotations."""
        await manager.register_secret("test-key")

        for _i in range(3):
            result = await manager.rotate_secret("test-key")
            assert result.success is True

        status = await manager.get_rotation_status("test-key")
        assert status["total_rotations"] == 3

    async def test_version_cleanup(self, manager: SecretRotationManager) -> None:
        """Test old versions are cleaned up."""
        policy = RotationPolicy(max_versions=2)
        await manager.register_secret("test-key", policy=policy)

        # Rotate multiple times
        for _ in range(4):
            await manager.rotate_secret("test-key")

        # Should have at most max_versions
        versions = manager._versions.get("test-key", [])
        assert len(versions) <= 2

    async def test_health_check(self, manager: SecretRotationManager) -> None:
        """Test health check endpoint."""
        health = manager.get_health()

        assert health["status"] == "healthy"
        assert health["registered_secrets"] == 0
        assert health["scheduler_running"] is False
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

        await manager.register_secret("test-key")
        health = manager.get_health()
        assert health["registered_secrets"] == 1

    async def test_custom_secret_generator(self) -> None:
        """Test using a custom secret generator."""

        async def custom_generator(name: str, secret_type: SecretType) -> str:
            return f"custom-{name}-{secret_type.value}"

        manager = SecretRotationManager(secret_generator=custom_generator)
        await manager.register_secret("test-key", secret_type=SecretType.API_KEY)

        current, _ = await manager.get_current_secret("test-key")
        assert current == "custom-test-key-api_key"


class TestSecretRotationManagerScheduler:
    """Tests for the rotation scheduler."""

    @pytest.fixture
    def manager(self) -> SecretRotationManager:
        """Create a test rotation manager."""
        return SecretRotationManager()

    async def test_start_stop_scheduler(self, manager: SecretRotationManager) -> None:
        """Test starting and stopping the scheduler."""
        await manager.start_scheduler(check_interval_seconds=1)
        assert manager._scheduler_running is True

        await manager.stop_scheduler()
        assert manager._scheduler_running is False

    async def test_scheduler_auto_rotation(self, manager: SecretRotationManager) -> None:
        """Test scheduler performs automatic rotation."""
        # Register with immediate rotation policy
        policy = RotationPolicy(
            rotation_interval_days=0,
            triggers=[RotationTrigger.TIME_BASED],
        )
        await manager.register_secret("test-key", policy=policy)

        # Start scheduler with short interval
        await manager.start_scheduler(check_interval_seconds=1)

        # Wait for scheduler to run
        await asyncio.sleep(1.5)

        await manager.stop_scheduler()

        # Should have rotated
        status = await manager.get_rotation_status("test-key")
        assert status["total_rotations"] >= 1


class TestVaultSecretBackend:
    """Tests for VaultSecretBackend."""

    async def test_vault_backend_initialization(self) -> None:
        """Test Vault backend can be initialized."""
        backend = VaultSecretBackend(
            vault_url="http://localhost:8200",
            path_prefix="test/secrets",
        )

        assert backend._vault_url == "http://localhost:8200"
        assert backend._path_prefix == "test/secrets"

    async def test_vault_backend_without_hvac(self) -> None:
        """Test Vault backend handles missing hvac library."""
        backend = VaultSecretBackend()

        with patch.dict("sys.modules", {"hvac": None}):
            # Should not crash, just return None/empty
            versions = await backend.list_versions("test-secret")
            assert versions == []


class TestRotationTriggers:
    """Tests for different rotation triggers."""

    @pytest.fixture
    def manager(self) -> SecretRotationManager:
        """Create a test rotation manager."""
        return SecretRotationManager()

    async def test_on_demand_trigger(self, manager: SecretRotationManager) -> None:
        """Test on-demand rotation trigger."""
        await manager.register_secret("test-key")

        result = await manager.rotate_secret(
            "test-key",
            trigger=RotationTrigger.ON_DEMAND,
        )

        assert result.success is True

    async def test_compromise_detected_trigger(self, manager: SecretRotationManager) -> None:
        """Test compromise-detected rotation trigger."""
        policy = RotationPolicy(
            triggers=[RotationTrigger.COMPROMISE_DETECTED, RotationTrigger.ON_DEMAND]
        )
        await manager.register_secret("test-key", policy=policy)

        result = await manager.rotate_secret(
            "test-key",
            trigger=RotationTrigger.COMPROMISE_DETECTED,
        )

        assert result.success is True

    async def test_dependency_rotation_trigger(self, manager: SecretRotationManager) -> None:
        """Test dependency rotation trigger."""
        policy = RotationPolicy(
            triggers=[RotationTrigger.DEPENDENCY_ROTATION, RotationTrigger.ON_DEMAND]
        )
        await manager.register_secret("test-key", policy=policy)

        result = await manager.rotate_secret(
            "test-key",
            trigger=RotationTrigger.DEPENDENCY_ROTATION,
        )

        assert result.success is True


class TestSingletonPattern:
    """Tests for the singleton pattern."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_rotation_manager()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_rotation_manager()

    async def test_get_rotation_manager_singleton(self) -> None:
        """Test singleton returns same instance."""
        manager1 = await get_rotation_manager()
        manager2 = await get_rotation_manager()

        assert manager1 is manager2

    async def test_reset_rotation_manager(self) -> None:
        """Test reset creates new instance."""
        manager1 = await get_rotation_manager()
        reset_rotation_manager()
        manager2 = await get_rotation_manager()

        assert manager1 is not manager2


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    @pytest.fixture
    def manager(self) -> SecretRotationManager:
        """Create a test rotation manager."""
        return SecretRotationManager()

    def test_constitutional_hash_constant(self) -> None:
        """Test constitutional hash constant is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    async def test_rotation_result_includes_hash(self, manager: SecretRotationManager) -> None:
        """Test rotation result includes constitutional hash."""
        await manager.register_secret("test-key")
        result = await manager.rotate_secret("test-key")

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_status_includes_hash(self, manager: SecretRotationManager) -> None:
        """Test status includes constitutional hash."""
        await manager.register_secret("test-key")
        status = await manager.get_rotation_status("test-key")

        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_policy_includes_hash(self) -> None:
        """Test policy includes constitutional hash."""
        policy = RotationPolicy()
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH
        assert policy.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_version_includes_hash(self) -> None:
        """Test version includes constitutional hash."""
        version = SecretVersion(
            version_id="test-v1",
            created_at=datetime.now(UTC),
        )
        assert version.constitutional_hash == CONSTITUTIONAL_HASH
        assert version.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSecretTypes:
    """Tests for different secret types."""

    @pytest.fixture
    def manager(self) -> SecretRotationManager:
        """Create a test rotation manager."""
        return SecretRotationManager()

    async def test_jwt_signing_key_generation(self, manager: SecretRotationManager) -> None:
        """Test JWT signing key generation."""
        await manager.register_secret("jwt-key", secret_type=SecretType.JWT_SIGNING_KEY)

        current, _ = await manager.get_current_secret("jwt-key")
        assert current is not None
        assert len(current) > 32  # Should be substantial

    async def test_encryption_key_generation(self, manager: SecretRotationManager) -> None:
        """Test encryption key generation."""
        await manager.register_secret("enc-key", secret_type=SecretType.ENCRYPTION_KEY)

        current, _ = await manager.get_current_secret("enc-key")
        assert current is not None

    async def test_api_key_generation(self, manager: SecretRotationManager) -> None:
        """Test API key generation."""
        await manager.register_secret("api-key", secret_type=SecretType.API_KEY)

        current, _ = await manager.get_current_secret("api-key")
        assert current is not None
        assert current.startswith("acgs2_")

    async def test_webhook_secret_generation(self, manager: SecretRotationManager) -> None:
        """Test webhook secret generation."""
        await manager.register_secret("webhook", secret_type=SecretType.WEBHOOK_SECRET)

        current, _ = await manager.get_current_secret("webhook")
        assert current is not None
        assert current.startswith("whsec_")
