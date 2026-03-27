from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from src.core.services.api_gateway.routes._x402_common import (
    DEFAULT_ATTESTATION_DEV_KEY,
    PAID_RESPONSE_DISCLAIMER,
    RelatedEndpoint,
    build_related_endpoint,
    configure_x402_payment_middleware,
    ensure_attestation_secret_config,
    resolve_attestation_secret,
)


# ---------------------------------------------------------------------------
# resolve_attestation_secret
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveAttestationSecret:
    """Cover all three branches of resolve_attestation_secret()."""

    def test_returns_attestation_secret_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATTESTATION_SECRET", "real-secret-123")
        monkeypatch.delenv("JWT_SECRET", raising=False)
        assert resolve_attestation_secret() == "real-secret-123"

    def test_falls_back_to_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.setenv("JWT_SECRET", "jwt-fallback-456")
        assert resolve_attestation_secret() == "jwt-fallback-456"

    def test_returns_default_dev_key_when_nothing_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        assert resolve_attestation_secret() == DEFAULT_ATTESTATION_DEV_KEY

    def test_attestation_secret_takes_precedence_over_jwt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATTESTATION_SECRET", "att-secret")
        monkeypatch.setenv("JWT_SECRET", "jwt-secret")
        assert resolve_attestation_secret() == "att-secret"

    def test_empty_attestation_secret_falls_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty string is falsy, so it should fall through to JWT_SECRET."""
        monkeypatch.setenv("ATTESTATION_SECRET", "")
        monkeypatch.setenv("JWT_SECRET", "jwt-backup")
        assert resolve_attestation_secret() == "jwt-backup"

    def test_empty_both_falls_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATTESTATION_SECRET", "")
        monkeypatch.setenv("JWT_SECRET", "")
        assert resolve_attestation_secret() == DEFAULT_ATTESTATION_DEV_KEY


# ---------------------------------------------------------------------------
# ensure_attestation_secret_config
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnsureAttestationSecretConfig:
    """Cover production guard, staging guard, and dev passthrough."""

    def test_raises_in_production_with_default_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError, match="non-default value"):
            ensure_attestation_secret_config()

    def test_raises_in_prod_short_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "prod")
        with pytest.raises(RuntimeError, match="production/staging"):
            ensure_attestation_secret_config()

    def test_raises_in_staging_with_default_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        with pytest.raises(RuntimeError, match="ATTESTATION_SECRET"):
            ensure_attestation_secret_config()

    def test_production_with_real_secret_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATTESTATION_SECRET", "supersecret-prod-key")
        monkeypatch.setenv("ENVIRONMENT", "production")
        result = ensure_attestation_secret_config()
        assert result == "supersecret-prod-key"

    def test_dev_with_default_key_is_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        result = ensure_attestation_secret_config()
        assert result == DEFAULT_ATTESTATION_DEV_KEY

    def test_uses_env_fallback_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ENVIRONMENT is unset, falls back to ENV variable."""
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENV", "production")
        with pytest.raises(RuntimeError, match="non-default value"):
            ensure_attestation_secret_config()

    def test_defaults_to_development_when_no_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        result = ensure_attestation_secret_config()
        assert result == DEFAULT_ATTESTATION_DEV_KEY

    def test_environment_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "  PRODUCTION  ")
        with pytest.raises(RuntimeError):
            ensure_attestation_secret_config()

    def test_staging_with_jwt_secret_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATTESTATION_SECRET", raising=False)
        monkeypatch.setenv("JWT_SECRET", "jwt-staging-secret")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        result = ensure_attestation_secret_config()
        assert result == "jwt-staging-secret"


# ---------------------------------------------------------------------------
# build_related_endpoint
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBuildRelatedEndpoint:
    """Ensure build_related_endpoint returns a valid RelatedEndpoint model."""

    def test_returns_related_endpoint_instance(self) -> None:
        result = build_related_endpoint(
            endpoint="/x402/validate",
            method="POST",
            price_usd="0.01",
            relation="validates",
            reason="Constitutional compliance check",
        )
        assert isinstance(result, RelatedEndpoint)

    def test_field_values_match(self) -> None:
        result = build_related_endpoint(
            endpoint="/x402/audit",
            method="POST",
            price_usd="0.05",
            relation="audits",
            reason="Risk breakdown analysis",
        )
        assert result.endpoint == "/x402/audit"
        assert result.method == "POST"
        assert result.price_usd == "0.05"
        assert result.relation == "audits"
        assert result.reason == "Risk breakdown analysis"

    def test_model_serializes_to_dict(self) -> None:
        result = build_related_endpoint(
            endpoint="/x402/certify",
            method="POST",
            price_usd="0.50",
            relation="certifies",
            reason="Signed attestation",
        )
        data = result.model_dump()
        assert data == {
            "endpoint": "/x402/certify",
            "method": "POST",
            "price_usd": "0.50",
            "relation": "certifies",
            "reason": "Signed attestation",
        }


# ---------------------------------------------------------------------------
# RelatedEndpoint model
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestRelatedEndpointModel:
    """Direct model construction and validation."""

    def test_construct_directly(self) -> None:
        ep = RelatedEndpoint(
            endpoint="/test",
            method="GET",
            price_usd="1.00",
            relation="related",
            reason="testing",
        )
        assert ep.endpoint == "/test"
        assert ep.method == "GET"

    def test_model_json_round_trip(self) -> None:
        ep = RelatedEndpoint(
            endpoint="/x402/batch",
            method="POST",
            price_usd="0.10",
            relation="batches",
            reason="Bulk validation",
        )
        json_str = ep.model_dump_json()
        restored = RelatedEndpoint.model_validate_json(json_str)
        assert restored == ep


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConstants:
    """Verify module-level constants have expected values."""

    def test_default_attestation_dev_key(self) -> None:
        assert DEFAULT_ATTESTATION_DEV_KEY == "acgs2-dev-key"

    def test_paid_response_disclaimer_is_nonempty_string(self) -> None:
        assert isinstance(PAID_RESPONSE_DISCLAIMER, str)
        assert len(PAID_RESPONSE_DISCLAIMER) > 0
        assert "Not legal advice" in PAID_RESPONSE_DISCLAIMER


# ---------------------------------------------------------------------------
# configure_x402_payment_middleware — additional edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConfigureMiddlewareEdgeCases:
    """Additional edge cases beyond the existing test file."""

    def test_empty_evm_address_disables_middleware(self) -> None:
        app = FastAPI()
        result = configure_x402_payment_middleware(app, environ={"EVM_ADDRESS": ""})
        assert result is False

    def test_uses_os_environ_when_environ_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When environ is None, falls back to os.environ."""
        monkeypatch.delenv("EVM_ADDRESS", raising=False)
        app = FastAPI()
        result = configure_x402_payment_middleware(app, environ=None)
        assert result is False

    def test_custom_prices_via_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom price env vars are passed through to route config."""

        class _FakeResourceServer:
            def __init__(self, clients: list) -> None:
                self.clients = clients

            def register(self, network: str, scheme: object) -> None:
                pass

        payment_option_calls: list[dict] = []

        class _PaymentOption:
            def __init__(self, **kwargs: object) -> None:
                payment_option_calls.append(kwargs)

        route_config_calls: list[dict] = []

        class _RouteConfig:
            def __init__(self, **kwargs: object) -> None:
                route_config_calls.append(kwargs)

        module_map = {
            "x402": SimpleNamespace(FacilitatorConfig=lambda url: None),
            "x402.http": SimpleNamespace(HTTPFacilitatorClient=lambda cfg: None),
            "x402.http.middleware.fastapi": SimpleNamespace(
                PaymentMiddlewareASGI=type("MW", (), {})
            ),
            "x402.http.types": SimpleNamespace(
                RouteConfig=_RouteConfig, PaymentOption=_PaymentOption
            ),
            "x402.mechanisms.evm.exact": SimpleNamespace(
                ExactEvmServerScheme=lambda: None
            ),
            "x402.server": SimpleNamespace(
                x402ResourceServer=lambda clients: _FakeResourceServer(clients)
            ),
        }

        def _fake_import(name: str) -> object:
            if name not in module_map:
                raise ImportError(name)
            return module_map[name]

        monkeypatch.setattr(
            "src.core.services.api_gateway.routes._x402_common.importlib.import_module",
            _fake_import,
        )

        app = FastAPI()
        app.add_middleware = MagicMock()  # type: ignore[method-assign]

        result = configure_x402_payment_middleware(
            app,
            environ={
                "EVM_ADDRESS": "0xdeadbeef1234567890",
                "X402_PRICE_VALIDATE": "0.99",
                "X402_PRICE_AUDIT": "1.00",
            },
        )

        assert result is True
        # Verify the custom price was picked up (check payment option calls)
        prices = [call.get("price") for call in payment_option_calls]
        assert "$0.99" in prices
        assert "$1.00" in prices

    def test_default_network_and_facilitator_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify defaults when X402_NETWORK and FACILITATOR_URL are not set."""

        captured_facilitator_url: list[str] = []
        captured_network: list[str] = []

        class _FakeResourceServer:
            def __init__(self, clients: list) -> None:
                pass

            def register(self, network: str, scheme: object) -> None:
                captured_network.append(network)

        class _FacilitatorConfig:
            def __init__(self, url: str) -> None:
                captured_facilitator_url.append(url)

        module_map = {
            "x402": SimpleNamespace(FacilitatorConfig=_FacilitatorConfig),
            "x402.http": SimpleNamespace(HTTPFacilitatorClient=lambda cfg: cfg),
            "x402.http.middleware.fastapi": SimpleNamespace(
                PaymentMiddlewareASGI=type("MW", (), {})
            ),
            "x402.http.types": SimpleNamespace(
                RouteConfig=lambda **kw: None, PaymentOption=lambda **kw: None
            ),
            "x402.mechanisms.evm.exact": SimpleNamespace(
                ExactEvmServerScheme=lambda: None
            ),
            "x402.server": SimpleNamespace(
                x402ResourceServer=lambda clients: _FakeResourceServer(clients)
            ),
        }

        def _fake_import(name: str) -> object:
            if name not in module_map:
                raise ImportError(name)
            return module_map[name]

        monkeypatch.setattr(
            "src.core.services.api_gateway.routes._x402_common.importlib.import_module",
            _fake_import,
        )

        app = FastAPI()
        app.add_middleware = MagicMock()  # type: ignore[method-assign]

        configure_x402_payment_middleware(
            app,
            environ={"EVM_ADDRESS": "0xabc123"},
        )

        assert captured_network == ["eip155:84532"]
        assert captured_facilitator_url == ["https://facilitator.xpay.sh"]

    def test_import_error_chains_original_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError should chain the original ImportError via __cause__."""

        def _raise_import(name: str) -> None:
            raise ImportError(f"No module named '{name}'")

        monkeypatch.setattr(
            "src.core.services.api_gateway.routes._x402_common.importlib.import_module",
            _raise_import,
        )

        app = FastAPI()
        with pytest.raises(RuntimeError) as exc_info:
            configure_x402_payment_middleware(app, environ={"EVM_ADDRESS": "0xabc"})

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ImportError)
