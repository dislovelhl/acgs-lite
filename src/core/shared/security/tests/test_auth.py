from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.security import auth
from src.core.shared.security.testing import create_test_token

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"
EXPECTED_RSA_KEYS_ERROR = (
    "RS256 requested but RSA verification keys are not configured. Set JWT_PUBLIC_KEY for "
    "verification, JWT_PRIVATE_KEY for signing, or change JWT_ALGORITHM to HS256."
)


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


def _make_settings(
    *,
    jwt_algorithm: str = "RS256",
    jwt_private_key: str = "",
    jwt_public_key: str = "SYSTEM_PUBLIC_KEY_PLACEHOLDER",
    jwt_secret_value: str | None = None,
) -> SimpleNamespace:
    jwt_secret = None
    if jwt_secret_value is not None:
        jwt_secret = SimpleNamespace(
            get_secret_value=lambda secret=jwt_secret_value: secret,
        )

    return SimpleNamespace(
        jwt_algorithm=jwt_algorithm,
        jwt_private_key=jwt_private_key,
        jwt_public_key=jwt_public_key,
        security=SimpleNamespace(
            jwt_secret=jwt_secret,
            jwt_public_key=jwt_public_key,
        ),
    )


def test_configured_jwt_algorithm_rejects_unsupported_algorithm(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS1024")

    with pytest.raises(ConfigurationError) as exc_info:
        auth._configured_jwt_algorithm()

    assert exc_info.value.error_code == "JWT_ALGORITHM_NOT_ALLOWED"
    assert exc_info.value.message == "Unsupported JWT algorithm: HS1024"


def test_configured_jwt_algorithm_normalizes_eddsa(monkeypatch):
    monkeypatch.delenv("JWT_ALGORITHM", raising=False)
    monkeypatch.setattr(auth, "settings", _make_settings(jwt_algorithm="edDsa"))

    assert auth._configured_jwt_algorithm() == "EdDSA"


def test_create_access_token_requires_rsa_keys_for_rs256(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    monkeypatch.setattr(auth, "settings", _make_settings())

    with pytest.raises(ConfigurationError) as exc_info:
        auth.create_access_token("user-1", "tenant-1")

    assert exc_info.value.error_code == "JWT_RSA_KEYS_MISSING"
    assert exc_info.value.message == EXPECTED_RSA_KEYS_ERROR


def test_verify_token_surfaces_rsa_key_configuration_error(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    monkeypatch.setattr(auth, "settings", _make_settings())
    monkeypatch.setattr(auth, "_current_jwt_private_key", lambda: None)
    monkeypatch.setattr(auth, "_current_jwt_public_key", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        auth.verify_token("invalid-token")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == EXPECTED_RSA_KEYS_ERROR


def test_verify_token_accepts_public_key_only_for_rs256(monkeypatch):
    private_key, public_key = _generate_rsa_keypair()
    token = jwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "tenant-1",
            "roles": ["user"],
            "permissions": ["read"],
            "exp": 4_102_444_800,
            "iat": 1_700_000_000,
            "iss": "acgs2",
            "aud": "acgs2-api",
            "jti": "test-jti-123",
            "constitutional_hash": auth.CONSTITUTIONAL_HASH,
        },
        private_key,
        algorithm="RS256",
    )

    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(
        auth,
        "settings",
        _make_settings(jwt_algorithm="RS256", jwt_private_key="", jwt_public_key=public_key),
    )

    claims = auth.verify_token(token)

    assert claims.sub == "user-1"
    assert auth.has_jwt_verification_material() is True


def test_create_test_token_uses_testing_helper(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = create_test_token(user_id="user-1", tenant_id="tenant-1")
    payload = jwt.decode(
        token,
        TEST_JWT_SECRET,
        algorithms=["HS256"],
        audience="acgs2-api",
    )

    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["roles"] == ["user"]
    assert payload["permissions"] == ["read"]
    assert payload["iss"] == "acgs2"
    assert payload["constitutional_hash"] == auth.CONSTITUTIONAL_HASH


def test_is_production_environment_prefers_environment_over_defaulted_settings_env(monkeypatch):
    monkeypatch.setattr(auth.settings, "env", "development")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert auth._is_production_environment() is True


@pytest.mark.asyncio
async def test_get_current_user_fails_closed_when_only_environment_is_production(monkeypatch):
    from unittest.mock import MagicMock

    claims = auth.UserClaims(
        sub="user-1",
        tenant_id="tenant-1",
        roles=["user"],
        permissions=["read"],
        exp=4_102_444_800,
        iat=1_700_000_000,
        aud="acgs2-api",
        iss="acgs2",
        jti="test-jti-123",
    )
    credentials = MagicMock()
    credentials.credentials = "test-token"

    monkeypatch.setattr(auth.settings, "env", "development")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(auth, "verify_token", lambda _token: claims)
    monkeypatch.setattr(auth, "_get_revocation_service", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(credentials=credentials)

    assert exc_info.value.status_code == 503


def test_has_jwt_verification_material_false_when_no_keys(monkeypatch):
    """has_jwt_verification_material returns False when neither secret nor public key is set."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "")
    assert auth.has_jwt_verification_material() is False
