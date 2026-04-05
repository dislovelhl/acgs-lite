import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security import auth_dependency

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"


@pytest.fixture(autouse=True)
def _force_hs256(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")


def _build_token(secret: str, **overrides: object) -> str:
    payload: dict[str, object] = {
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "roles": ["user"],
        "permissions": ["read"],
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "iss": "acgs2",
        "aud": "acgs2-api",
        "jti": "test-jti-123",
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


def _generate_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


async def test_require_auth_allows_bypass_only_in_development(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setattr(settings, "env", "development")
    # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)

    result = await auth_dependency.require_auth(None)

    assert result["sub"] == "dev-user"


async def test_require_auth_rejects_bypass_in_production(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)

    with pytest.raises(HTTPException, match="Authentication required") as exc_info:
        await auth_dependency.require_auth(None)

    assert exc_info.value.status_code == 401


async def test_require_auth_uses_runtime_environment_precedence(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setattr(settings, "env", "development")
    # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(HTTPException, match="Authentication required"):
        await auth_dependency.require_auth(None)


async def test_require_auth_validates_token_with_runtime_secret(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")

    token = _build_token(os.environ["JWT_SECRET_KEY"])
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(return_value=False)
    auth_dependency._revocation_service = mock_service

    result = await auth_dependency.require_auth(credentials)

    assert result["sub"] == "user-1"
    auth_dependency._revocation_service = None


# ============================================================================
# Additional coverage tests
# ============================================================================


async def test_configure_revocation_service():
    """configure_revocation_service registers the service."""
    from unittest.mock import MagicMock

    from src.core.shared.security import auth

    mock_service = MagicMock()
    auth_dependency.configure_revocation_service(mock_service)

    # Verify it was set
    assert auth_dependency._revocation_service is mock_service
    assert auth._revocation_service is mock_service
    assert auth._revocation_service_initialized is True

    # Clean up
    auth_dependency._revocation_service = None
    auth._revocation_service = None
    auth._revocation_service_initialized = False


async def test_check_revocation_skips_when_no_service():
    """_check_revocation skips when no service configured."""
    auth_dependency._revocation_service = None
    # Should not raise
    await auth_dependency._check_revocation("test-jti")


async def test_check_revocation_skips_when_no_jti():
    """_check_revocation skips when no JTI provided."""
    from unittest.mock import AsyncMock, MagicMock

    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(return_value=False)
    auth_dependency._revocation_service = mock_service

    # Should not call is_token_revoked when jti is None
    await auth_dependency._check_revocation(None)
    mock_service.is_token_revoked.assert_not_called()

    # Clean up
    auth_dependency._revocation_service = None


async def test_check_revocation_raises_when_token_revoked():
    """_check_revocation raises 401 when token is revoked."""
    from unittest.mock import AsyncMock, MagicMock

    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(return_value=True)
    auth_dependency._revocation_service = mock_service

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency._check_revocation("revoked-jti")

    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()

    # Clean up
    auth_dependency._revocation_service = None


async def test_check_revocation_handles_service_errors_in_non_production(monkeypatch):
    """_check_revocation degrades gracefully outside production."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(settings, "env", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)

    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(side_effect=RuntimeError("Redis down"))
    auth_dependency._revocation_service = mock_service

    await auth_dependency._check_revocation("test-jti")

    auth_dependency._revocation_service = None


async def test_check_revocation_production_missing_service_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    auth_dependency._revocation_service = None

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency._check_revocation("test-jti")

    assert exc_info.value.status_code == 503


async def test_check_revocation_environment_only_production_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "env", "development")
    # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    auth_dependency._revocation_service = None

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency._check_revocation("test-jti")

    assert exc_info.value.status_code == 503


async def test_check_revocation_production_service_error_fails_closed(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(side_effect=RuntimeError("Redis down"))
    auth_dependency._revocation_service = mock_service

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency._check_revocation("test-jti")

    assert exc_info.value.status_code == 503
    auth_dependency._revocation_service = None


async def test_require_auth_missing_jwt_secret(monkeypatch):
    """require_auth raises 500 when no verification material is configured."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 500
    assert "JWT verification material" in exc_info.value.detail


async def test_require_auth_accepts_rs256_public_key_only(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    private_key, public_key = _generate_rsa_keypair()
    token = jwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "tenant-1",
            "roles": ["user"],
            "permissions": ["read"],
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "iss": "acgs2",
            "aud": "acgs2-api",
            "jti": "test-jti-123",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
        private_key,
        algorithm="RS256",
    )

    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_key)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(return_value=False)
    auth_dependency._revocation_service = mock_service

    result = await auth_dependency.require_auth(credentials)

    assert result["sub"] == "user-1"
    auth_dependency._revocation_service = None


async def test_require_auth_expired_token(monkeypatch):
    """require_auth raises 401 for expired token."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    # Create expired token
    token = _build_token(TEST_JWT_SECRET, exp=int(time.time()) - 3600)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


async def test_require_auth_invalid_token(monkeypatch):
    """require_auth raises 401 for invalid token."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


async def test_require_auth_optional_no_credentials():
    """require_auth_optional returns None when no credentials."""
    result = auth_dependency.require_auth_optional(None)
    assert result is None


async def test_require_auth_optional_valid_token(monkeypatch):
    """require_auth_optional returns payload for valid token."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    result = auth_dependency.require_auth_optional(credentials)

    assert result is not None
    assert result["sub"] == "user-1"


async def test_require_auth_optional_no_secret(monkeypatch):
    """require_auth_optional returns None when no verification material is configured."""
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")

    result = auth_dependency.require_auth_optional(credentials)
    assert result is None


async def test_require_auth_optional_invalid_token_raises(monkeypatch):
    """require_auth_optional raises 401 for invalid token."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

    with pytest.raises(HTTPException) as exc_info:
        auth_dependency.require_auth_optional(credentials)

    assert exc_info.value.status_code == 401


async def test_require_auth_rejects_invalid_audience(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET, aud="wrong-audience")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401


async def test_require_auth_rejects_constitutional_hash_mismatch(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    # Clear env vars that would override settings.env (e.g. conftest sets ENVIRONMENT=test)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ACGS2_ENV", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET, constitutional_hash="wrong-hash")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "constitutional hash" in exc_info.value.detail.lower()
