import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

jwt = pytest.importorskip("jwt")


def _generate_rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_signed_id_token(
    private_key,
    *,
    issuer: str,
    audience: str,
    kid: str,
    nonce: str,
    subject: str = "user-123",
) -> tuple[str, dict[str, str]]:
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "nonce": nonce,
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int((now - timedelta(seconds=5)).timestamp()),
    }

    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "alg": "RS256"},
    )

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"

    return token, jwk


@pytest.fixture
def oidc_provider():
    from ...mcp_integration.auth.oidc_provider import (
        OIDCConfig,
        OIDCProvider,
        OIDCProviderMetadata,
    )

    issuer = "https://issuer.example.com"
    provider = OIDCProvider(
        OIDCConfig(
            issuer_url=issuer,
            client_id="acgs-client",
            validate_id_token=True,
        )
    )
    provider._metadata = OIDCProviderMetadata(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/authorize",
        token_endpoint=f"{issuer}/token",
        jwks_uri=f"{issuer}/jwks",
        id_token_signing_alg_values_supported=["RS256"],
    )

    assert provider._metadata.constitutional_hash == CONSTITUTIONAL_HASH
    return provider


async def test_validate_id_token_accepts_valid_signed_token(oidc_provider, monkeypatch):
    private_key = _generate_rsa_private_key()
    id_token, jwk = _build_signed_id_token(
        private_key,
        issuer=oidc_provider._metadata.issuer,
        audience=oidc_provider.config.client_id,
        kid="test-key-1",
        nonce="nonce-123",
    )

    async def _fetch_jwks():
        return [jwk]

    monkeypatch.setattr(oidc_provider, "_fetch_jwks", _fetch_jwks)

    claims, errors = await oidc_provider._validate_id_token(
        id_token=id_token,
        access_token="access-token",
        expected_nonce="nonce-123",
    )

    assert errors == []
    assert claims["sub"] == "user-123"
    assert claims["iss"] == oidc_provider._metadata.issuer


async def test_validate_id_token_rejects_invalid_signature(oidc_provider, monkeypatch):
    trusted_key = _generate_rsa_private_key()
    attacker_key = _generate_rsa_private_key()

    id_token, _ = _build_signed_id_token(
        attacker_key,
        issuer=oidc_provider._metadata.issuer,
        audience=oidc_provider.config.client_id,
        kid="shared-kid",
        nonce="nonce-123",
    )
    _, trusted_jwk = _build_signed_id_token(
        trusted_key,
        issuer=oidc_provider._metadata.issuer,
        audience=oidc_provider.config.client_id,
        kid="shared-kid",
        nonce="nonce-123",
    )

    async def _fetch_jwks():
        return [trusted_jwk]

    monkeypatch.setattr(oidc_provider, "_fetch_jwks", _fetch_jwks)

    claims, errors = await oidc_provider._validate_id_token(
        id_token=id_token,
        access_token="access-token",
        expected_nonce="nonce-123",
    )

    assert claims == {}
    assert errors
    assert any("Validation error" in error for error in errors)


async def test_validate_id_token_fails_closed_when_jwks_unavailable(oidc_provider, monkeypatch):
    private_key = _generate_rsa_private_key()
    id_token, _ = _build_signed_id_token(
        private_key,
        issuer=oidc_provider._metadata.issuer,
        audience=oidc_provider.config.client_id,
        kid="test-key-2",
        nonce="nonce-123",
    )

    async def _fetch_jwks():
        return []

    monkeypatch.setattr(oidc_provider, "_fetch_jwks", _fetch_jwks)

    claims, errors = await oidc_provider._validate_id_token(
        id_token=id_token,
        access_token="access-token",
        expected_nonce="nonce-123",
    )

    assert claims == {}
    assert any("No JWKS keys available" in error for error in errors)
