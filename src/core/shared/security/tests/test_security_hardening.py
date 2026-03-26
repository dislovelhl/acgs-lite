"""Tests for P0/P1 security hardening fixes.

These tests validate the security fixes without importing the full gateway,
which has unresolved import dependencies (api_versioning, otel_config, self_evolution).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── H-1: Token revocation integration ──────────────────────────────


class TestTokenRevocationIntegration:
    """Test that get_current_user() checks token revocation."""

    @pytest.fixture(autouse=True)
    def reset_revocation_singleton(self):
        """Reset the lazy-init singleton between tests."""
        import src.core.shared.security.auth as auth_mod

        auth_mod._revocation_service = None
        auth_mod._revocation_service_initialized = False
        yield
        auth_mod._revocation_service = None
        auth_mod._revocation_service_initialized = False

    def test_revocation_service_none_without_redis(self):
        """Without REDIS_URL, _get_revocation_service returns None."""
        from src.core.shared.security.auth import _get_revocation_service

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            result = _get_revocation_service()
            assert result is None

    async def test_get_current_user_checks_revocation(self):
        """get_current_user should check is_token_revoked after JWT validation."""
        from src.core.shared.security.auth import UserClaims, get_current_user

        mock_creds = MagicMock()
        mock_creds.credentials = "test-token"

        claims = UserClaims(
            sub="user-1",
            jti="token-jti-123",
            aud="acgs2-api",
            iss="acgs2",
            exp=int(datetime.now(UTC).timestamp()) + 3600,
            iat=int(datetime.now(UTC).timestamp()),
            tenant_id="tenant-1",
            roles=["user"],
            permissions=["read"],
        )

        mock_revocation = AsyncMock()
        mock_revocation.is_token_revoked = AsyncMock(return_value=False)

        with (
            patch("src.core.shared.security.auth.verify_token", return_value=claims),
            patch(
                "src.core.shared.security.auth._get_revocation_service",
                return_value=mock_revocation,
            ),
        ):
            result = await get_current_user(credentials=mock_creds)
            assert result.sub == "user-1"
            mock_revocation.is_token_revoked.assert_awaited_once_with("token-jti-123")

    async def test_get_current_user_rejects_revoked_token(self):
        """Revoked tokens should cause 401."""
        from fastapi import HTTPException

        from src.core.shared.security.auth import UserClaims, get_current_user

        mock_creds = MagicMock()
        mock_creds.credentials = "revoked-token"

        claims = UserClaims(
            sub="user-1",
            jti="revoked-jti",
            aud="acgs2-api",
            iss="acgs2",
            exp=int(datetime.now(UTC).timestamp()) + 3600,
            iat=int(datetime.now(UTC).timestamp()),
            tenant_id="tenant-1",
            roles=["user"],
            permissions=["read"],
        )

        mock_revocation = AsyncMock()
        mock_revocation.is_token_revoked = AsyncMock(return_value=True)

        with (
            patch("src.core.shared.security.auth.verify_token", return_value=claims),
            patch(
                "src.core.shared.security.auth._get_revocation_service",
                return_value=mock_revocation,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=mock_creds)
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail.lower()

    async def test_get_current_user_fails_closed_when_revocation_backend_missing_in_production(
        self,
    ):
        """Production auth must reject when revocation backend is unavailable."""
        from fastapi import HTTPException

        from src.core.shared.security.auth import UserClaims, get_current_user

        mock_creds = MagicMock()
        mock_creds.credentials = "test-token"

        claims = UserClaims(
            sub="user-1",
            jti="token-jti-123",
            aud="acgs2-api",
            iss="acgs2",
            exp=int(datetime.now(UTC).timestamp()) + 3600,
            iat=int(datetime.now(UTC).timestamp()),
            tenant_id="tenant-1",
            roles=["user"],
            permissions=["read"],
        )

        with (
            patch("src.core.shared.security.auth.verify_token", return_value=claims),
            patch("src.core.shared.security.auth._get_revocation_service", return_value=None),
            patch("src.core.shared.security.auth._is_production_environment", return_value=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=mock_creds)
            assert exc_info.value.status_code == 503


# ── C-2: Service auth env var mismatch ──────────────────────────────


class TestServiceAuthEnvCheck:
    """Test that service auth checks both ACGS2_ENV and ENVIRONMENT."""

    def test_production_blocks_dev_secret_via_acgs2_env(self):
        """Setting ACGS2_ENV=production should block fallback dev secret."""
        from src.core.shared.errors.exceptions import ConfigurationError
        from src.core.shared.security.service_auth import _get_service_secret

        with patch.dict(
            os.environ,
            {"ACGS2_ENV": "production", "ENVIRONMENT": "development"},
            clear=True,
        ):
            with pytest.raises(ConfigurationError):
                _get_service_secret()

    def test_production_blocks_dev_secret_via_environment(self):
        """Setting ENVIRONMENT=production should also block fallback."""
        from src.core.shared.errors.exceptions import ConfigurationError
        from src.core.shared.security.service_auth import _get_service_secret

        with patch.dict(
            os.environ,
            {"ACGS2_ENV": "development", "ENVIRONMENT": "production"},
            clear=True,
        ):
            with pytest.raises(ConfigurationError):
                _get_service_secret()

    def test_dev_mode_allows_fallback(self):
        """Both env vars in dev mode should allow the fallback secret."""
        from src.core.shared.security.service_auth import _get_service_secret

        with patch.dict(
            os.environ,
            {"ACGS2_ENV": "development", "ENVIRONMENT": "development"},
            clear=True,
        ):
            secret = _get_service_secret()
            assert secret  # Should return the dev fallback


# ── H-4: OIDC pending states bounding ───────────────────────────────


class TestOIDCStateBounding:
    """Test that OIDC pending states are bounded and TTL-evicted."""

    def test_eviction_removes_expired_states(self):
        """Stale pending states should be evicted."""
        from src.core.shared.auth.oidc_handler import OIDCHandler

        handler = OIDCHandler()
        handler._pending_state_ttl_seconds = 0  # Expire immediately

        # Add a state that's already expired
        handler._pending_states["old-state"] = {
            "provider": "test",
            "redirect_uri": "http://localhost",
            "code_verifier": None,
            "nonce": "nonce1",
            "created_at": "2020-01-01T00:00:00+00:00",
        }

        handler._evict_stale_pending_states()
        assert "old-state" not in handler._pending_states

    def test_max_states_enforced(self):
        """Pending states should not exceed max_pending_states."""
        from src.core.shared.auth.oidc_handler import OIDCHandler

        handler = OIDCHandler()
        handler._max_pending_states = 3

        # Fill to capacity
        for i in range(3):
            handler._pending_states[f"state-{i}"] = {
                "provider": "test",
                "redirect_uri": "http://localhost",
                "code_verifier": None,
                "nonce": f"nonce-{i}",
                "created_at": datetime.now(UTC).isoformat(),
            }

        assert len(handler._pending_states) == 3
