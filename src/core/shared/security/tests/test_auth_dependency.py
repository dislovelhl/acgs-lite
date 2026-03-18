import os
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security import auth_dependency

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"  # noqa: S105


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


@pytest.mark.asyncio
async def test_require_auth_allows_bypass_only_in_development(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setattr(settings, "env", "development")

    result = await auth_dependency.require_auth(None)

    assert result["sub"] == "dev-user"


@pytest.mark.asyncio
async def test_require_auth_rejects_bypass_in_production(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    # Must patch settings.env — it's pre-computed at import time, not read from
    # AGENT_RUNTIME_ENVIRONMENT per-call.
    monkeypatch.setattr(settings, "env", "production")

    with pytest.raises(HTTPException, match="Authentication required") as exc_info:
        await auth_dependency.require_auth(None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_uses_runtime_environment_precedence(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    # settings.env is the canonical source — env vars are only read once at startup.
    monkeypatch.setattr(settings, "env", "production")

    with pytest.raises(HTTPException, match="Authentication required"):
        await auth_dependency.require_auth(None)


@pytest.mark.asyncio
async def test_require_auth_validates_token_with_runtime_secret(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")

    token = _build_token(os.environ["JWT_SECRET_KEY"])
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    result = await auth_dependency.require_auth(credentials)

    assert result["sub"] == "user-1"


# ============================================================================
# Additional coverage tests
# ============================================================================


@pytest.mark.asyncio
async def test_configure_revocation_service():
    """configure_revocation_service registers the service."""
    from unittest.mock import MagicMock

    mock_service = MagicMock()
    auth_dependency.configure_revocation_service(mock_service)

    # Verify it was set
    assert auth_dependency._revocation_service is mock_service

    # Clean up
    auth_dependency._revocation_service = None


@pytest.mark.asyncio
async def test_check_revocation_skips_when_no_service():
    """_check_revocation skips when no service configured."""
    auth_dependency._revocation_service = None
    # Should not raise
    await auth_dependency._check_revocation("test-jti")


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_check_revocation_handles_service_errors():
    """_check_revocation handles service errors gracefully."""
    from unittest.mock import AsyncMock, MagicMock

    mock_service = MagicMock()
    mock_service.is_token_revoked = AsyncMock(side_effect=RuntimeError("Redis down"))
    auth_dependency._revocation_service = mock_service

    # Should not raise - errors are logged but not propagated
    await auth_dependency._check_revocation("test-jti")

    # Clean up
    auth_dependency._revocation_service = None


@pytest.mark.asyncio
async def test_require_auth_missing_jwt_secret(monkeypatch):
    """require_auth raises 500 when no supported JWT secret is configured."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 500
    assert "JWT secret" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_auth_expired_token(monkeypatch):
    """require_auth raises 401 for expired token."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    # Create expired token
    token = _build_token(TEST_JWT_SECRET, exp=int(time.time()) - 3600)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_invalid_token(monkeypatch):
    """require_auth raises 401 for invalid token."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_optional_no_credentials():
    """require_auth_optional returns None when no credentials."""
    result = auth_dependency.require_auth_optional(None)
    assert result is None


@pytest.mark.asyncio
async def test_require_auth_optional_valid_token(monkeypatch):
    """require_auth_optional returns payload for valid token."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    result = auth_dependency.require_auth_optional(credentials)

    assert result is not None
    assert result["sub"] == "user-1"


@pytest.mark.asyncio
async def test_require_auth_optional_no_secret(monkeypatch):
    """require_auth_optional returns None when no JWT secret configured."""
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "")

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")

    result = auth_dependency.require_auth_optional(credentials)
    assert result is None


@pytest.mark.asyncio
async def test_require_auth_optional_invalid_token_raises(monkeypatch):
    """require_auth_optional raises 401 for invalid token."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

    with pytest.raises(HTTPException) as exc_info:
        auth_dependency.require_auth_optional(credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_rejects_invalid_audience(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET, aud="wrong-audience")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_rejects_constitutional_hash_mismatch(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = _build_token(TEST_JWT_SECRET, constitutional_hash="wrong-hash")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await auth_dependency.require_auth(credentials)

    assert exc_info.value.status_code == 401
    assert "constitutional hash" in exc_info.value.detail.lower()
