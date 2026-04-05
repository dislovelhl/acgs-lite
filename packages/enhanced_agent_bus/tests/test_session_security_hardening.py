"""
Session Security Hardening Tests
Constitutional Hash: 608508a9bd224290

Regression tests for:
- H1: JWT iss/aud claim enforcement (PyJWT migration)
- M1: JTI-based revocation with optional Redis persistence
- M3: Maximum session extension cap
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from enterprise_sso.session_governance_sdk import (
    SESSION_JWT_ALGORITHM,
    SESSION_JWT_AUDIENCE,
    SESSION_JWT_ISSUER,
    SessionConfig,
    SessionGovernanceError,
    SessionLifecycleManager,
    SessionTokenManager,
    TokenValidationError,
)

_TEST_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWT_PRIVATE_KEY = _TEST_RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
JWT_PUBLIC_KEY = _TEST_RSA_KEY.public_key()

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ============================================================================
# H1 -- JWT iss/aud/jti claim enforcement
# ============================================================================


class TestJWTClaimEnforcement:
    """H1: SessionTokenManager now issues and enforces iss/aud/jti claims."""

    @pytest.fixture
    def manager(self) -> SessionTokenManager:
        return SessionTokenManager(private_key=JWT_PRIVATE_KEY)

    async def test_access_token_contains_iss_aud_jti(self, manager):
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        payload = jwt.decode(
            token_obj.access_token,
            JWT_PUBLIC_KEY,
            algorithms=[manager._algorithm],
            audience=SESSION_JWT_AUDIENCE,
            issuer=SESSION_JWT_ISSUER,
        )
        assert payload["iss"] == SESSION_JWT_ISSUER
        assert payload["aud"] == SESSION_JWT_AUDIENCE
        assert "jti" in payload and len(payload["jti"]) > 0
        assert payload["sub"] == "u1"

    async def test_wrong_audience_rejected(self, manager):
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(
                token_obj.access_token,
                JWT_PUBLIC_KEY,
                algorithms=[manager._algorithm],
                audience="wrong-audience",
                issuer=SESSION_JWT_ISSUER,
            )

    async def test_wrong_issuer_rejected(self, manager):
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        with pytest.raises(jwt.InvalidIssuerError):
            jwt.decode(
                token_obj.access_token,
                JWT_PUBLIC_KEY,
                algorithms=[manager._algorithm],
                audience=SESSION_JWT_AUDIENCE,
                issuer="wrong-issuer",
            )

    async def test_tampered_token_rejected(self, manager):
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        tampered = token_obj.access_token[:-5] + "XXXXX"
        result = await manager.validate_token(tampered)
        assert result.is_valid is False
        assert result.reason == "invalid_token"

    async def test_validate_returns_correct_claims(self, manager):
        token_obj = await manager.generate_access_token("sess-99", "tenant-A", "user-Z", ["admin"])
        result = await manager.validate_token(token_obj.access_token)
        assert result.is_valid is True
        assert result.session_id == "sess-99"
        assert result.tenant_id == "tenant-A"
        assert result.user_id == "user-Z"
        assert "admin" in result.roles


class TestPrivateKeyValidation:
    """Constructor guardrails for asymmetric JWT private keys."""

    def test_non_pem_private_key_is_rejected(self):
        with pytest.raises(
            ValueError,
            match=(f"private_key must be a PEM-encoded private key for {SESSION_JWT_ALGORITHM}"),
        ):
            SessionTokenManager(private_key="not-a-pem")


# ============================================================================
# M1 -- JTI-based revocation, optional Redis persistence
# ============================================================================


class TestJTIRevocation:
    """M1: Revocation is JTI-based and optionally Redis-durable."""

    @pytest.fixture
    def manager(self) -> SessionTokenManager:
        return SessionTokenManager(private_key=JWT_PRIVATE_KEY)

    async def test_revoked_token_fails_validation(self, manager):
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        await manager.revoke_token(token_obj.access_token)
        result = await manager.validate_token(token_obj.access_token)
        assert result.is_valid is False
        assert result.reason == "token_revoked"

    async def test_revocation_uses_jti_not_full_token(self, manager):
        """Verify that revocation stores the JTI, not the raw token string."""
        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        payload = jwt.decode(
            token_obj.access_token,
            JWT_PUBLIC_KEY,
            algorithms=[manager._algorithm],
            audience=SESSION_JWT_AUDIENCE,
            issuer=SESSION_JWT_ISSUER,
        )
        jti = payload["jti"]
        await manager.revoke_token(token_obj.access_token)
        assert jti in manager._revoked_jtis
        assert token_obj.access_token not in manager._revoked_jtis

    async def test_redis_sadd_called_on_revoke(self):
        redis_mock = MagicMock()
        redis_mock.sadd = AsyncMock()
        redis_mock.expire = AsyncMock()
        manager = SessionTokenManager(private_key=JWT_PRIVATE_KEY, redis_client=redis_mock)

        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        await manager.revoke_token(token_obj.access_token)

        redis_mock.sadd.assert_called_once()
        redis_mock.expire.assert_called_once()

    async def test_redis_sismember_checked_on_validate(self):
        redis_mock = MagicMock()
        redis_mock.sadd = AsyncMock()
        redis_mock.expire = AsyncMock()
        redis_mock.sismember = AsyncMock(return_value=True)
        manager = SessionTokenManager(private_key=JWT_PRIVATE_KEY, redis_client=redis_mock)

        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        result = await manager.validate_token(token_obj.access_token)

        redis_mock.sismember.assert_called_once()
        assert result.is_valid is False
        assert result.reason == "token_revoked"

    async def test_redis_failure_does_not_break_validation(self):
        """Redis errors must not propagate -- fall back to in-memory set."""
        redis_mock = MagicMock()
        redis_mock.sismember = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager = SessionTokenManager(private_key=JWT_PRIVATE_KEY, redis_client=redis_mock)

        token_obj = await manager.generate_access_token("s1", "t1", "u1")
        result = await manager.validate_token(token_obj.access_token)
        # In-memory set is empty → token is valid (Redis failure is silently absorbed)
        assert result.is_valid is True


# ============================================================================
# M3 -- Maximum session extension cap
# ============================================================================


class TestMaxExtensionCap:
    """M3: extend_session must refuse extensions beyond the cap."""

    @pytest.fixture
    def manager(self) -> SessionLifecycleManager:
        return SessionLifecycleManager()

    @pytest.fixture
    def short_config(self) -> SessionConfig:
        return SessionConfig(
            tenant_id="t1",
            user_id="u1",
            max_duration_minutes=30,  # short session for testing
        )

    async def test_small_extension_accepted(self, manager, short_config):
        session = await manager.create_session(short_config)
        extended = await manager.extend_session(session.session_id, extension_minutes=15)
        assert extended.extension_count == 1

    async def test_excessive_extension_rejected(self, manager, short_config):
        """A single extension that would push total lifetime far beyond cap must fail."""
        session = await manager.create_session(short_config)
        with pytest.raises(SessionGovernanceError, match="maximum allowed session duration"):
            # max_duration=30, cap = min(1440, 30*4) = 120; session is 30 min;
            # request 200 min extension → 230 min total > 120 min cap
            await manager.extend_session(session.session_id, extension_minutes=200)

    async def test_cumulative_extensions_capped(self, manager, short_config):
        """Multiple small extensions should fail once they cross the cap."""
        session = await manager.create_session(short_config)
        # cap = 120 min; session starts at 30 min
        # Extend 3x by 25 min each → 30 + 75 = 105 min (OK)
        for _ in range(3):
            session = await manager.extend_session(session.session_id, extension_minutes=25)
        # Next 25-min extension → 130 min > 120 min cap → should fail
        with pytest.raises(SessionGovernanceError, match="maximum allowed session duration"):
            await manager.extend_session(session.session_id, extension_minutes=25)

    async def test_extension_count_incremented(self, manager, short_config):
        session = await manager.create_session(short_config)
        assert session.extension_count == 0
        session = await manager.extend_session(session.session_id, extension_minutes=10)
        assert session.extension_count == 1
        session = await manager.extend_session(session.session_id, extension_minutes=10)
        assert session.extension_count == 2
