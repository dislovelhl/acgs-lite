"""
Tests for ACGS-2 Service-to-Service Authentication

Constitutional Hash: cdd01ef066bc6cf2
"""

import time

import jwt
import pytest

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.security.service_auth import (
    SERVICE_SECRET,
    ServiceAuth,
    _configured_service_algorithm,
    _get_service_secret,
)


class TestServiceAuth:
    """Test service JWT token creation and verification."""

    def test_create_and_verify_token(self):
        """Test roundtrip of token creation and verification."""
        service_name = "test-service"
        token = ServiceAuth.create_service_token(service_name)

        verified_name = ServiceAuth.verify_service_token(token)
        assert verified_name == service_name

    def test_expired_token(self):
        """Test that expired tokens are rejected."""
        service_name = "test-service"
        # Create a token that's already expired
        payload = {
            "sub": service_name,
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
            "iss": "acgs2-internal",
            "type": "service",
        }
        token = jwt.encode(
            payload,
            SERVICE_SECRET,
            algorithm=_configured_service_algorithm(),
        )

        assert ServiceAuth.verify_service_token(token) is None

    def test_invalid_issuer(self):
        """Test that tokens with wrong issuer are rejected."""
        payload = {
            "sub": "test-service",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "wrong-issuer",
            "type": "service",
        }
        token = jwt.encode(
            payload,
            SERVICE_SECRET,
            algorithm=_configured_service_algorithm(),
        )

        assert ServiceAuth.verify_service_token(token) is None

    def test_wrong_type(self):
        """Test that non-service tokens are rejected."""
        payload = {
            "sub": "user-123",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "acgs2-internal",
            "type": "user",
        }
        token = jwt.encode(
            payload,
            SERVICE_SECRET,
            algorithm=_configured_service_algorithm(),
        )

        assert ServiceAuth.verify_service_token(token) is None

    def test_tampered_token(self):
        """Test that tampered tokens are rejected."""
        token = ServiceAuth.create_service_token("test-service")
        tampered_token = token[:-5] + "aaaaa"

        assert ServiceAuth.verify_service_token(tampered_token) is None

    def test_development_secret_fallback_is_available(self, monkeypatch):
        monkeypatch.setenv("ACGS2_ENV", "development")
        monkeypatch.delenv("ACGS2_SERVICE_SECRET", raising=False)

        assert _get_service_secret() == "dev-service-secret-32-bytes-minimum-length"

    def test_production_secret_requires_configuration(self, monkeypatch):
        monkeypatch.setenv("ACGS2_ENV", "production")
        monkeypatch.delenv("ACGS2_SERVICE_SECRET", raising=False)

        with pytest.raises(ConfigurationError, match="ACGS2_SERVICE_SECRET not configured"):
            _get_service_secret()

    def test_environment_var_also_blocks_dev_fallback(self, monkeypatch):
        """ENVIRONMENT=production without ACGS2_ENV must still block dev fallback.

        This is the exact PM2 deployment scenario that triggered the P0.
        """
        monkeypatch.delenv("ACGS2_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ACGS2_SERVICE_SECRET", raising=False)

        with pytest.raises(ConfigurationError, match="ACGS2_SERVICE_SECRET not configured"):
            _get_service_secret()

    def test_rs256_without_keys_raises_configuration_error(self, monkeypatch):
        monkeypatch.setenv("SERVICE_JWT_ALGORITHM", "RS256")
        monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)

        with pytest.raises(
            ConfigurationError,
            match=(
                r"RS256 requested but RSA keys are not configured\. Set JWT_PRIVATE_KEY and "
                r"JWT_PUBLIC_KEY, or set SERVICE_JWT_ALGORITHM=HS256\."
            ),
        ):
            ServiceAuth.create_service_token("test-service")
