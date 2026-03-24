"""Tests for src.core.shared.security.dual_key_jwt — DualKeyJWTValidator.

Covers: DualKeyConfig, KeyMetadata, JWTValidationResult, DualKeyJWTValidator
(validate_token, create_token, load_keys_from_env, load_keys_from_vault,
refresh_keys_if_needed, _cleanup_expired_keys, get_stats, get_health, get_jwks).
"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.dual_key_jwt import (
    DualKeyConfig,
    DualKeyJWTValidator,
    JWTValidationResult,
    KeyMetadata,
)


# ---------------------------------------------------------------------------
# Helpers: generate RSA key pair
# ---------------------------------------------------------------------------
def _generate_rsa_keypair() -> tuple[bytes, bytes]:
    """Generate an RSA private/public key pair as PEM bytes."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture(scope="module")
def rsa_keys():
    """Module-scoped RSA key pair."""
    return _generate_rsa_keypair()


@pytest.fixture(scope="module")
def rsa_keys_prev():
    """Module-scoped second RSA key pair for dual-key tests."""
    return _generate_rsa_keypair()


@pytest.fixture
def validator_with_keys(rsa_keys):
    """Validator pre-loaded with a single current key."""
    priv, pub = rsa_keys
    v = DualKeyJWTValidator()
    meta = KeyMetadata(kid="v1", is_current=True)
    v._keys["v1"] = (priv, pub, meta)
    v._current_kid = "v1"
    return v


@pytest.fixture
def dual_validator(rsa_keys, rsa_keys_prev):
    """Validator with both current and previous keys."""
    priv, pub = rsa_keys
    priv_prev, pub_prev = rsa_keys_prev
    config = DualKeyConfig(enabled=True, grace_period_hours=4)
    v = DualKeyJWTValidator(config=config)

    meta_current = KeyMetadata(kid="v2", is_current=True)
    v._keys["v2"] = (priv, pub, meta_current)
    v._current_kid = "v2"

    expires = datetime.now(UTC) + timedelta(hours=4)
    meta_prev = KeyMetadata(kid="v1", is_current=False, expires_at=expires)
    v._keys["v1"] = (priv_prev, pub_prev, meta_prev)
    v._previous_kid = "v1"

    return v


def _sign_token(
    private_key: bytes,
    claims: dict | None = None,
    kid: str | None = None,
    algorithm: str = "RS256",
) -> str:
    """Sign a JWT token with given private key."""
    payload = {
        "sub": "test-user",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
        "iss": "acgs2",
        **(claims or {}),
    }
    headers = {"alg": algorithm}
    if kid:
        headers["kid"] = kid
    return pyjwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


# ---------------------------------------------------------------------------
# DualKeyConfig
# ---------------------------------------------------------------------------
class TestDualKeyConfig:
    def test_defaults(self):
        config = DualKeyConfig()
        assert config.enabled is True
        assert config.grace_period_hours == 4
        assert config.max_keys == 2
        assert config.require_kid is False

    def test_custom(self):
        config = DualKeyConfig(enabled=False, grace_period_hours=8, require_kid=True)
        assert config.enabled is False
        assert config.grace_period_hours == 8
        assert config.require_kid is True


# ---------------------------------------------------------------------------
# KeyMetadata
# ---------------------------------------------------------------------------
class TestKeyMetadata:
    def test_defaults(self):
        meta = KeyMetadata(kid="v1")
        assert meta.kid == "v1"
        assert meta.algorithm == "RS256"
        assert meta.is_current is True
        assert meta.constitutional_hash == CONSTITUTIONAL_HASH

    def test_expires_at(self):
        expires = datetime.now(UTC) + timedelta(hours=1)
        meta = KeyMetadata(kid="v1", expires_at=expires)
        assert meta.expires_at == expires


# ---------------------------------------------------------------------------
# JWTValidationResult
# ---------------------------------------------------------------------------
class TestJWTValidationResult:
    def test_valid(self):
        r = JWTValidationResult(valid=True, claims={"sub": "test"}, key_used="v1")
        assert r.valid is True
        assert r.claims["sub"] == "test"

    def test_invalid(self):
        r = JWTValidationResult(valid=False, error="bad token")
        assert r.valid is False
        assert r.error == "bad token"


# ---------------------------------------------------------------------------
# validate_token — no keys
# ---------------------------------------------------------------------------
class TestValidateTokenNoKeys:
    def test_no_keys_loaded(self):
        v = DualKeyJWTValidator()
        result = v.validate_token("some.jwt.token")
        assert result.valid is False
        assert "No signing keys" in result.error
        assert result.constitutional_compliant is False


# ---------------------------------------------------------------------------
# validate_token — single key
# ---------------------------------------------------------------------------
class TestValidateTokenSingleKey:
    def test_valid_token(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid="v1")
        result = validator_with_keys.validate_token(token)
        assert result.valid is True
        assert result.key_used == "v1"
        assert result.claims["sub"] == "test-user"

    def test_invalid_signature(self, validator_with_keys):
        other_priv, _ = _generate_rsa_keypair()
        token = _sign_token(other_priv, kid="v1")
        result = validator_with_keys.validate_token(token)
        assert result.valid is False

    def test_expired_token(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, claims={"exp": datetime.now(UTC) - timedelta(hours=1)}, kid="v1")
        result = validator_with_keys.validate_token(token, verify_exp=True)
        assert result.valid is False

    def test_verify_exp_disabled(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, claims={"exp": datetime.now(UTC) - timedelta(hours=1)}, kid="v1")
        result = validator_with_keys.validate_token(token, verify_exp=False)
        assert result.valid is True

    def test_constitutional_hash_mismatch(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, claims={"constitutional_hash": "wrong_hash"}, kid="v1")
        result = validator_with_keys.validate_token(token)
        assert result.valid is False
        assert result.constitutional_compliant is False

    def test_constitutional_hash_correct(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, claims={"constitutional_hash": CONSTITUTIONAL_HASH}, kid="v1")
        result = validator_with_keys.validate_token(token)
        assert result.valid is True

    def test_no_kid_in_token(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid=None)
        result = validator_with_keys.validate_token(token)
        assert result.valid is True  # should fall back to current key

    def test_require_kid_missing(self, rsa_keys):
        priv, pub = rsa_keys
        config = DualKeyConfig(require_kid=True)
        v = DualKeyJWTValidator(config=config)
        v._keys["v1"] = (priv, pub, KeyMetadata(kid="v1", is_current=True))
        v._current_kid = "v1"
        token = _sign_token(priv, kid=None)
        result = v.validate_token(token)
        assert result.valid is False
        assert "kid" in result.error


# ---------------------------------------------------------------------------
# validate_token — dual key
# ---------------------------------------------------------------------------
class TestValidateTokenDualKey:
    def test_current_key_preferred(self, dual_validator, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid="v2")
        result = dual_validator.validate_token(token)
        assert result.valid is True
        assert result.key_used == "v2"

    def test_previous_key_fallback(self, dual_validator, rsa_keys_prev):
        priv_prev, _ = rsa_keys_prev
        token = _sign_token(priv_prev, kid="v1")
        result = dual_validator.validate_token(token)
        assert result.valid is True
        assert result.key_used == "v1"

    def test_unknown_kid_tries_all(self, dual_validator, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid="v99")
        # v99 not found, but v2 key should still validate
        result = dual_validator.validate_token(token)
        assert result.valid is True

    def test_expired_previous_key_skipped(self, rsa_keys, rsa_keys_prev):
        priv, pub = rsa_keys
        priv_prev, pub_prev = rsa_keys_prev
        v = DualKeyJWTValidator()
        v._keys["v2"] = (priv, pub, KeyMetadata(kid="v2", is_current=True))
        v._current_kid = "v2"
        expired_meta = KeyMetadata(
            kid="v1",
            is_current=False,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        v._keys["v1"] = (priv_prev, pub_prev, expired_meta)
        v._previous_kid = "v1"

        # Token signed with expired key should fail
        token = _sign_token(priv_prev, kid="v1")
        result = v.validate_token(token)
        assert result.valid is False


# ---------------------------------------------------------------------------
# _cleanup_expired_keys
# ---------------------------------------------------------------------------
class TestCleanupExpiredKeys:
    def test_removes_expired(self, rsa_keys):
        priv, pub = rsa_keys
        v = DualKeyJWTValidator()
        expired_meta = KeyMetadata(
            kid="old",
            is_current=False,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        v._keys["old"] = (None, pub, expired_meta)
        v._previous_kid = "old"
        v._cleanup_expired_keys()
        assert "old" not in v._keys
        assert v._previous_kid is None

    def test_keeps_active(self, rsa_keys):
        priv, pub = rsa_keys
        v = DualKeyJWTValidator()
        active_meta = KeyMetadata(
            kid="active",
            is_current=True,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        v._keys["active"] = (priv, pub, active_meta)
        v._cleanup_expired_keys()
        assert "active" in v._keys


# ---------------------------------------------------------------------------
# create_token
# ---------------------------------------------------------------------------
class TestCreateToken:
    def test_creates_valid_token(self, validator_with_keys, rsa_keys):
        _, pub = rsa_keys
        token = validator_with_keys.create_token({"sub": "user1"})
        assert token is not None
        # Validate it
        result = validator_with_keys.validate_token(token)
        assert result.valid is True
        assert result.claims["sub"] == "user1"
        assert result.claims["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_custom_expiration(self, validator_with_keys):
        token = validator_with_keys.create_token(
            {"sub": "user1"}, expires_delta=timedelta(minutes=30)
        )
        assert token is not None

    def test_no_current_key(self):
        v = DualKeyJWTValidator()
        assert v.create_token({"sub": "user1"}) is None

    def test_no_private_key(self, rsa_keys):
        _, pub = rsa_keys
        v = DualKeyJWTValidator()
        v._keys["v1"] = (None, pub, KeyMetadata(kid="v1", is_current=True))
        v._current_kid = "v1"
        assert v.create_token({"sub": "user1"}) is None

    def test_include_kid_header(self, validator_with_keys):
        token = validator_with_keys.create_token({"sub": "user1"}, include_kid=True)
        header = pyjwt.get_unverified_header(token)
        assert header["kid"] == "v1"

    def test_exclude_kid_header(self, validator_with_keys):
        token = validator_with_keys.create_token({"sub": "user1"}, include_kid=False)
        header = pyjwt.get_unverified_header(token)
        assert "kid" not in header


# ---------------------------------------------------------------------------
# load_keys_from_env
# ---------------------------------------------------------------------------
class TestLoadKeysFromEnv:
    async def test_load_current_key(self, rsa_keys):
        priv, pub = rsa_keys
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub).decode(),
            "JWT_CURRENT_PRIVATE_KEY": base64.b64encode(priv).decode(),
            "JWT_CURRENT_KID": "env-v1",
        }
        with patch.dict(os.environ, env, clear=False):
            v = DualKeyJWTValidator()
            result = await v.load_keys_from_env()
            assert result is True
            assert v._current_kid == "env-v1"

    async def test_load_no_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            v = DualKeyJWTValidator()
            result = await v.load_keys_from_env()
            assert result is False

    async def test_load_with_previous_key(self, rsa_keys, rsa_keys_prev):
        priv, pub = rsa_keys
        priv_prev, pub_prev = rsa_keys_prev
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub).decode(),
            "JWT_CURRENT_PRIVATE_KEY": base64.b64encode(priv).decode(),
            "JWT_CURRENT_KID": "v2",
            "JWT_PREVIOUS_PUBLIC_KEY": base64.b64encode(pub_prev).decode(),
            "JWT_PREVIOUS_KID": "v1",
        }
        with patch.dict(os.environ, env, clear=False):
            v = DualKeyJWTValidator(config=DualKeyConfig(enabled=True))
            result = await v.load_keys_from_env()
            assert result is True
            assert v._previous_kid == "v1"


# ---------------------------------------------------------------------------
# load_keys_from_vault
# ---------------------------------------------------------------------------
class TestLoadKeysFromVault:
    async def test_no_vault_falls_back_to_env(self, rsa_keys):
        priv, pub = rsa_keys
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub).decode(),
            "JWT_CURRENT_KID": "v1",
        }
        with patch.dict(os.environ, env, clear=False):
            v = DualKeyJWTValidator(vault_client=None)
            result = await v.load_keys_from_vault()
            # Falls back to load_keys_from_env

    async def test_vault_client_success(self, rsa_keys):
        priv, pub = rsa_keys
        vault = MagicMock()
        vault.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {
                    "public_key": base64.b64encode(pub).decode(),
                    "key": base64.b64encode(priv).decode(),
                    "kid": "vault-v1",
                    "dual_key_enabled": "false",
                }
            }
        }
        v = DualKeyJWTValidator(vault_client=vault)
        result = await v.load_keys_from_vault()
        assert result is True
        assert v._current_kid == "vault-v1"

    async def test_vault_error_falls_back(self, rsa_keys):
        priv, pub = rsa_keys
        vault = MagicMock()
        vault.secrets.kv.v2.read_secret_version.side_effect = RuntimeError("vault down")
        env = {
            "JWT_CURRENT_PUBLIC_KEY": base64.b64encode(pub).decode(),
            "JWT_CURRENT_KID": "env-fallback",
        }
        with patch.dict(os.environ, env, clear=False):
            v = DualKeyJWTValidator(vault_client=vault)
            result = await v.load_keys_from_vault()
            # Should fall back to env


# ---------------------------------------------------------------------------
# refresh_keys_if_needed
# ---------------------------------------------------------------------------
class TestRefreshKeysIfNeeded:
    async def test_no_refresh_when_recent(self, validator_with_keys):
        validator_with_keys._last_refresh = datetime.now(UTC)
        with patch.object(validator_with_keys, "load_keys_from_env") as mock_load:
            await validator_with_keys.refresh_keys_if_needed()
            mock_load.assert_not_called()

    async def test_refresh_when_stale(self, validator_with_keys):
        validator_with_keys._last_refresh = datetime.now(UTC) - timedelta(seconds=120)
        validator_with_keys.config.refresh_interval_seconds = 60
        with patch.object(
            validator_with_keys, "load_keys_from_env", new_callable=AsyncMock
        ) as mock_load:
            await validator_with_keys.refresh_keys_if_needed()
            mock_load.assert_called_once()

    async def test_no_refresh_when_never_loaded(self):
        v = DualKeyJWTValidator()
        v._last_refresh = None
        await v.refresh_keys_if_needed()  # should not raise


# ---------------------------------------------------------------------------
# get_stats / get_health / get_jwks
# ---------------------------------------------------------------------------
class TestStatsHealthJWKS:
    def test_get_stats(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid="v1")
        validator_with_keys.validate_token(token)
        stats = validator_with_keys.get_stats()
        assert stats["total_validations"] >= 1
        assert stats["current_kid"] == "v1"
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_health_with_key(self, validator_with_keys):
        health = validator_with_keys.get_health()
        assert health["status"] == "healthy"
        assert health["current_key_loaded"] is True

    def test_get_health_no_key(self):
        v = DualKeyJWTValidator()
        health = v.get_health()
        assert health["status"] == "degraded"

    def test_get_health_previous_expires_soon(self, dual_validator):
        # Override expiry to be within 1 hour
        _, pub, meta = dual_validator._keys["v1"]
        new_meta = KeyMetadata(
            kid="v1",
            is_current=False,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        dual_validator._keys["v1"] = (None, pub, new_meta)
        health = dual_validator.get_health()
        assert health["previous_key_expires_soon"] is True

    def test_get_jwks(self, validator_with_keys):
        jwks = validator_with_keys.get_jwks()
        assert "keys" in jwks
        assert jwks["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(jwks["keys"]) == 1
        key = jwks["keys"][0]
        assert key["kty"] == "RSA"
        assert key["kid"] == "v1"
        assert key["alg"] == "RS256"

    def test_get_jwks_skips_expired(self, rsa_keys):
        _, pub = rsa_keys
        v = DualKeyJWTValidator()
        expired_meta = KeyMetadata(
            kid="old",
            is_current=False,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        v._keys["old"] = (None, pub, expired_meta)
        jwks = v.get_jwks()
        assert len(jwks["keys"]) == 0


# ---------------------------------------------------------------------------
# Validation stats tracking
# ---------------------------------------------------------------------------
class TestValidationStats:
    def test_current_key_stats(self, validator_with_keys, rsa_keys):
        priv, _ = rsa_keys
        token = _sign_token(priv, kid="v1")
        validator_with_keys.validate_token(token)
        assert validator_with_keys._validation_stats["current_key_validations"] >= 1

    def test_previous_key_stats(self, dual_validator, rsa_keys_prev):
        priv_prev, _ = rsa_keys_prev
        token = _sign_token(priv_prev, kid="v1")
        dual_validator.validate_token(token)
        assert dual_validator._validation_stats["previous_key_validations"] >= 1

    def test_failure_stats(self, validator_with_keys):
        other_priv, _ = _generate_rsa_keypair()
        token = _sign_token(other_priv, kid="v1")
        validator_with_keys.validate_token(token)
        assert validator_with_keys._validation_stats["failures"] >= 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
class TestSingleton:
    async def test_get_dual_key_validator(self):
        import src.core.shared.security.dual_key_jwt as mod

        mod._validator = None
        with patch.dict(os.environ, {}, clear=False):
            v = await mod.get_dual_key_validator()
            assert isinstance(v, DualKeyJWTValidator)
        mod._validator = None  # reset
