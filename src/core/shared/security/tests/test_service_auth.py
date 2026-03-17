"""
Tests for ACGS-2 Service-to-Service Authentication

Constitutional Hash: cdd01ef066bc6cf2
"""

import time

import jwt

from src.core.shared.security.service_auth import (
    SERVICE_ALGORITHM,
    SERVICE_SECRET,
    ServiceAuth,
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
        token = jwt.encode(payload, SERVICE_SECRET, algorithm=SERVICE_ALGORITHM)

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
        token = jwt.encode(payload, SERVICE_SECRET, algorithm=SERVICE_ALGORITHM)

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
        token = jwt.encode(payload, SERVICE_SECRET, algorithm=SERVICE_ALGORITHM)

        assert ServiceAuth.verify_service_token(token) is None

    def test_tampered_token(self):
        """Test that tampered tokens are rejected."""
        token = ServiceAuth.create_service_token("test-service")
        tampered_token = token[:-5] + "aaaaa"

        assert ServiceAuth.verify_service_token(tampered_token) is None
