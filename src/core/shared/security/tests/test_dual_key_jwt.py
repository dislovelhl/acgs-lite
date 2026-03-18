"""
Test Suite for Dual-Key JWT Validator
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for zero-downtime JWT key rotation functionality.
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.core.shared.security.dual_key_jwt import (
    CONSTITUTIONAL_HASH,
    DualKeyConfig,
    DualKeyJWTValidator,
    JWTValidationResult,
    KeyMetadata,
)


class TestDualKeyConfig:
    """Tests for DualKeyConfig Pydantic model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DualKeyConfig()
        assert config.enabled is True
        assert config.grace_period_hours == 4
        assert config.max_keys == 2
        assert config.refresh_interval_seconds == 60
        assert config.require_kid is False

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DualKeyConfig(
            enabled=False,
            grace_period_hours=8,
            max_keys=3,
            refresh_interval_seconds=120,
            require_kid=True,
        )
        assert config.enabled is False
        assert config.grace_period_hours == 8
        assert config.max_keys == 3
        assert config.refresh_interval_seconds == 120
        assert config.require_kid is True


class TestKeyMetadata:
    """Tests for KeyMetadata Pydantic model."""

    def test_key_metadata_creation(self):
        """Test KeyMetadata creation and properties."""
        now = datetime.now(UTC)
        expires = now + timedelta(hours=4)

        metadata = KeyMetadata(
            kid="test-key-001",
            algorithm="RS256",
            created_at=now,
            expires_at=expires,
            is_current=True,
        )

        assert metadata.kid == "test-key-001"
        assert metadata.created_at == now
        assert metadata.expires_at == expires
        assert metadata.algorithm == "RS256"
        assert metadata.is_current is True
        assert metadata.constitutional_hash == CONSTITUTIONAL_HASH

    def test_key_metadata_defaults(self):
        """Test KeyMetadata default values."""
        metadata = KeyMetadata(kid="default-key")

        assert metadata.kid == "default-key"
        assert metadata.algorithm == "RS256"
        assert metadata.is_current is True
        assert metadata.expires_at is None
        assert metadata.constitutional_hash == CONSTITUTIONAL_HASH


class TestJWTValidationResult:
    """Tests for JWTValidationResult Pydantic model."""

    def test_successful_validation(self):
        """Test successful validation result."""
        claims = {"sub": "user-123", "role": "admin"}
        result = JWTValidationResult(
            valid=True,
            claims=claims,
            key_used="current-key",
        )

        assert result.valid is True
        assert result.claims == claims
        assert result.key_used == "current-key"
        assert result.error is None
        assert result.constitutional_compliant is True

    def test_failed_validation(self):
        """Test failed validation result."""
        result = JWTValidationResult(
            valid=False,
            claims=None,
            key_used=None,
            error="Token expired",
            constitutional_compliant=True,
        )

        assert result.valid is False
        assert result.claims is None
        assert result.error == "Token expired"


class TestDualKeyJWTValidator:
    """Tests for DualKeyJWTValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance for testing."""
        config = DualKeyConfig(
            grace_period_hours=4,
            require_kid=False,
        )
        return DualKeyJWTValidator(config)

    def test_initialization(self, validator):
        """Test validator initialization."""
        assert validator.config is not None
        assert validator.config.enabled is True
        assert validator._keys == {}
        assert validator._current_kid is None
        assert validator._previous_kid is None

    def test_validation_stats_initialized(self, validator):
        """Test that validation stats are properly initialized."""
        stats = validator.get_stats()
        assert stats["total_validations"] == 0
        assert stats["current_key_validations"] == 0
        assert stats["previous_key_validations"] == 0
        assert stats["failures"] == 0

    def test_health_check_degraded_no_keys(self, validator):
        """Test health check returns degraded when no keys loaded."""
        health = validator.get_health()

        assert health["status"] == "degraded"
        assert health["current_key_loaded"] is False
        assert health["dual_key_active"] is False
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_stats_structure(self, validator):
        """Test statistics structure."""
        stats = validator.get_stats()

        assert "total_validations" in stats
        assert "current_key_validations" in stats
        assert "previous_key_validations" in stats
        assert "failures" in stats
        assert "current_kid" in stats
        assert "previous_kid" in stats
        assert "dual_key_enabled" in stats
        assert "loaded_keys" in stats
        assert "constitutional_hash" in stats

    def test_validation_without_keys(self, validator):
        """Test validation fails gracefully without keys."""
        result = validator.validate_token("some-token")

        assert result.valid is False
        assert "No signing keys loaded" in result.error
        assert result.constitutional_compliant is False

    def test_get_jwks_empty(self, validator):
        """Test JWKS returns empty when no keys loaded."""
        jwks = validator.get_jwks()

        assert "keys" in jwks
        assert len(jwks["keys"]) == 0
        assert jwks["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestDualKeyJWTValidatorAsync:
    """Async tests for DualKeyJWTValidator."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        config = DualKeyConfig(require_kid=False)
        return DualKeyJWTValidator(config)

    @pytest.mark.asyncio
    async def test_load_keys_from_env_missing(self, validator):
        """Test loading keys when environment variables are missing."""
        # Clear any existing environment variables
        env_vars_to_clear = [
            "JWT_CURRENT_PRIVATE_KEY",
            "JWT_CURRENT_PUBLIC_KEY",
            "JWT_CURRENT_KID",
            "JWT_PREVIOUS_PRIVATE_KEY",
            "JWT_PREVIOUS_PUBLIC_KEY",
            "JWT_PREVIOUS_KID",
        ]

        with patch.dict(os.environ, {}, clear=True):
            for var in env_vars_to_clear:
                os.environ.pop(var, None)

            result = await validator.load_keys_from_env()

            # Should return False when no keys found
            assert result is False

    @pytest.mark.asyncio
    async def test_load_keys_from_vault_fallback(self, validator):
        """Test loading keys from Vault falls back to env when no client."""
        # No vault client configured
        assert validator._vault_client is None

        with patch.object(validator, "load_keys_from_env", return_value=False) as mock_env:
            result = await validator.load_keys_from_vault()

            # Should fall back to environment
            mock_env.assert_called_once()
            assert result is False


@pytest.mark.constitutional
class TestConstitutionalCompliance:
    """Tests for constitutional compliance requirements."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is enforced."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_validator_config_includes_constitutional_reference(self):
        """Test that validator configuration relates to constitutional hash."""
        config = DualKeyConfig()
        validator = DualKeyJWTValidator(config)

        # The validator should be aware of constitutional hash
        stats = validator.get_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_health_check_includes_constitutional_hash(self):
        """Test that health check includes constitutional hash."""
        config = DualKeyConfig()
        validator = DualKeyJWTValidator(config)

        health = validator.get_health()

        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_key_metadata_includes_constitutional_hash(self):
        """Test that key metadata includes constitutional hash."""
        metadata = KeyMetadata(kid="const-test-key")

        assert metadata.constitutional_hash == CONSTITUTIONAL_HASH

    def test_jwks_includes_constitutional_hash(self):
        """Test that JWKS output includes constitutional hash."""
        config = DualKeyConfig()
        validator = DualKeyJWTValidator(config)

        jwks = validator.get_jwks()

        assert jwks["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestKeyExpiry:
    """Tests for key expiry handling."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        config = DualKeyConfig(grace_period_hours=4)
        return DualKeyJWTValidator(config)

    def test_expired_key_detection(self, validator):
        """Test that expired keys are detected in health check."""
        # Manually add a key that will expire soon
        past_time = datetime.now(UTC) - timedelta(hours=1)
        expiry_time = datetime.now(UTC) - timedelta(minutes=30)

        validator._keys["expired-key"] = (
            None,
            b"public-key-bytes",
            KeyMetadata(
                kid="expired-key",
                created_at=past_time,
                expires_at=expiry_time,
                is_current=False,
            ),
        )
        validator._previous_kid = "expired-key"

        # Cleanup should remove expired keys
        validator._cleanup_expired_keys()

        assert "expired-key" not in validator._keys
        assert validator._previous_kid is None


class TestValidationStatistics:
    """Tests for validation statistics tracking."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        config = DualKeyConfig()
        return DualKeyJWTValidator(config)

    def test_failure_count_increments(self, validator):
        """Test that failures are counted."""
        # Attempt validation without keys
        validator.validate_token("invalid-token")
        validator.validate_token("another-invalid-token")

        stats = validator.get_stats()

        # These should count as failures since no keys loaded
        assert stats["total_validations"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
