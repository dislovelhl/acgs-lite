from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.security import auth
from src.core.shared.security.testing import create_test_token

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"
EXPECTED_RSA_KEYS_ERROR = (
    "RS256 requested but RSA keys (JWT_PRIVATE_KEY, JWT_PUBLIC_KEY) are not configured. "
    "Set keys or change JWT_ALGORITHM to HS256."
)


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

    with pytest.raises(HTTPException) as exc_info:
        auth.verify_token("invalid-token")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == EXPECTED_RSA_KEYS_ERROR


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
